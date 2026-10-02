"""Bounded two-ack anonymous AF_UNIX staged executor transfer."""

from __future__ import annotations

import hashlib
import socket
from dataclasses import dataclass
from typing import Callable

from . import registration_clock, registration_jcs


class SecretTransferError(RuntimeError):
    pass


_FRAME_FIELDS = (
    "member_id",
    "effect_id",
    "executor_token_hash",
    "operation_id",
    "member_tuple_hash",
    "status_hash",
    "protocol_hash",
    "staged_epoch_hash",
)


@dataclass(frozen=True)
class StagedGrantFrame:
    member_id: str
    effect_id: str
    executor_token_hash: str
    operation_id: str
    member_tuple_hash: str
    status_hash: str
    protocol_hash: str
    staged_epoch_hash: str

    def __post_init__(self) -> None:
        for field in _FRAME_FIELDS:
            value = getattr(self, field)
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)
            ):
                raise SecretTransferError(f"{field} must be lowercase 64-hex")

    def object(self) -> dict[str, str]:
        return {
            "schema": "awa-registration-staged-grant-frame/v1",
            **{field: getattr(self, field) for field in _FRAME_FIELDS},
        }

    @property
    def digest(self) -> str:
        return hashlib.sha256(
            b"awa-registration-staged-grant-frame/v1\0"
            + registration_jcs.canonical_bytes(self.object())
        ).hexdigest()

    @classmethod
    def from_bytes(cls, value: bytes) -> "StagedGrantFrame":
        parsed = registration_jcs.parse_canonical(value)
        if (
            not isinstance(parsed, dict)
            or set(parsed) != {"schema", *_FRAME_FIELDS}
            or parsed["schema"] != "awa-registration-staged-grant-frame/v1"
        ):
            raise SecretTransferError("invalid staged grant frame")
        return cls(**{field: parsed[field] for field in _FRAME_FIELDS})

@dataclass
class ReceivedStagedGrant:
    frame: StagedGrantFrame
    secret: bytearray
    _closed: bool = False

    def take_secret(self) -> bytes:
        if self._closed:
            raise SecretTransferError("received staged grant is closed")
        return bytes(self.secret)

    def close(self) -> None:
        if self._closed:
            return
        for index in range(len(self.secret)):
            self.secret[index] = 0
        self._closed = True

    def __enter__(self) -> "ReceivedStagedGrant":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


@dataclass
class StagedSecretTransfer:
    _sender: socket.socket
    _receiver: socket.socket
    _clock_ns: Callable[[], int]
    _sent: bool = False
    _received: bool = False
    _received_ack: bool = False
    _activated: bool = False
    _activation_seen: bool = False
    _frame_digest: str | None = None

    @classmethod
    def precreate(
        cls,
        *,
        clock_ns: Callable[[], int] = (
            registration_clock.mach_continuous_time_ns
        ),
    ) -> "StagedSecretTransfer":
        if not callable(clock_ns):
            raise SecretTransferError("transfer clock must be callable")
        sender, receiver = socket.socketpair(
            socket.AF_UNIX, socket.SOCK_STREAM
        )
        sender.set_inheritable(False)
        receiver.set_inheritable(False)
        return cls(sender, receiver, clock_ns)

    @property
    def sender_fd(self) -> int:
        return self._sender.fileno()

    @property
    def receiver_fd(self) -> int:
        return self._receiver.fileno()

    def deadline_after(self, seconds: float = 5.0) -> int:
        if not isinstance(seconds, (int, float)) or isinstance(seconds, bool):
            raise SecretTransferError("invalid transfer timeout")
        if seconds <= 0 or seconds > 5:
            raise SecretTransferError("transfer timeout must be within five seconds")
        now = self._clock_ns()
        if type(now) is not int or now < 0:
            raise SecretTransferError("transfer clock is unavailable")
        return now + int(seconds * 1_000_000_000)

    def send_frame(
        self,
        frame: StagedGrantFrame,
        secret: bytes | bytearray,
        *,
        deadline_ns: int,
    ) -> None:
        if self._sent:
            raise SecretTransferError("staged secret transfer is one-use")
        try:
            if not isinstance(frame, StagedGrantFrame):
                raise SecretTransferError("staged grant frame is required")
            if not isinstance(secret, (bytes, bytearray)) or not 32 <= len(secret) <= 4096:
                raise SecretTransferError("invalid executor secret size")
            actual = hashlib.sha256(
                b"awa-registration-executor/v1\0" + bytes(secret)
            ).hexdigest()
            if actual != frame.executor_token_hash:
                raise SecretTransferError("executor secret hash mismatch")
            frame_bytes = registration_jcs.canonical_bytes(frame.object())
            payload = (
                len(frame_bytes).to_bytes(4, "big")
                + frame_bytes
                + len(secret).to_bytes(4, "big")
                + bytes(secret)
            )
            self._send_all(self._sender, payload, deadline_ns)
            self._sent = True
            self._frame_digest = frame.digest
        except Exception:
            self.close()
            self._sent = True
            self._received = True
            raise

    def receive_frame(
        self,
        *,
        deadline_ns: int,
        expected_frame_digest: str | None = None,
    ) -> ReceivedStagedGrant:
        if self._received:
            raise SecretTransferError("staged secret receive is out of order")
        received = bytearray()
        try:
            frame_size = int.from_bytes(
                self._recv_exact(self._receiver, 4, deadline_ns), "big"
            )
            if not 1 <= frame_size <= registration_jcs.MAX_BLOB_BYTES:
                raise SecretTransferError("invalid staged grant frame size")
            frame = StagedGrantFrame.from_bytes(
                self._recv_exact(self._receiver, frame_size, deadline_ns)
            )
            if (
                expected_frame_digest is not None
                and frame.digest != expected_frame_digest
            ):
                raise SecretTransferError("staged grant frame mismatch")
            size = int.from_bytes(
                self._recv_exact(self._receiver, 4, deadline_ns), "big"
            )
            if not 32 <= size <= 4096:
                raise SecretTransferError("invalid staged secret frame")
            received.extend(self._recv_exact(self._receiver, size, deadline_ns))
            check = hashlib.sha256(
                b"awa-registration-executor/v1\0" + bytes(received)
            ).hexdigest()
            if check != frame.executor_token_hash:
                raise SecretTransferError("received executor secret mismatch")
            self._send_ack(
                self._receiver, b"RECEIVED", frame.digest, deadline_ns
            )
            self._received = True
            return ReceivedStagedGrant(frame, received)
        except Exception:
            for index in range(len(received)):
                received[index] = 0
            self.close()
            self._received = True
            raise

    def wait_received(self, frame_digest: str, *, deadline_ns: int) -> None:
        if self._received_ack:
            return
        self._read_ack(self._sender, b"RECEIVED", frame_digest, deadline_ns)
        self._received_ack = True

    def acknowledge_activated(
        self, frame_digest: str, *, deadline_ns: int
    ) -> None:
        if self._activated:
            return
        if not self._received:
            raise SecretTransferError("activation is out of order")
        self._send_ack(self._receiver, b"ACTIVATED", frame_digest, deadline_ns)
        self._activated = True

    def wait_activated(self, frame_digest: str, *, deadline_ns: int) -> None:
        if self._activation_seen:
            return
        if not self._received_ack:
            raise SecretTransferError("activation wait is out of order")
        self._read_ack(self._sender, b"ACTIVATED", frame_digest, deadline_ns)
        self._activation_seen = True

    def _remaining(self, deadline_ns: int) -> float:
        if type(deadline_ns) is not int:
            raise SecretTransferError("transfer deadline must be an integer")
        now = self._clock_ns()
        if type(now) is not int or now < 0:
            raise SecretTransferError("transfer clock is unavailable")
        remaining = (deadline_ns - now) / 1_000_000_000
        if remaining <= 0 or remaining > 5:
            raise SecretTransferError(
                "staged transfer deadline is outside five-second bound"
            )
        return remaining

    def _send_all(
        self, endpoint: socket.socket, payload: bytes, deadline_ns: int
    ) -> None:
        endpoint.settimeout(self._remaining(deadline_ns))
        try:
            endpoint.sendall(payload)
        except (OSError, TimeoutError) as error:
            raise SecretTransferError("staged transfer send failed") from error

    def _recv_exact(
        self, endpoint: socket.socket, size: int, deadline_ns: int
    ) -> bytes:
        result = bytearray()
        while len(result) < size:
            endpoint.settimeout(self._remaining(deadline_ns))
            try:
                chunk = endpoint.recv(size - len(result))
            except (OSError, TimeoutError) as error:
                raise SecretTransferError("staged transfer receive failed") from error
            if not chunk:
                raise SecretTransferError("truncated staged secret frame")
            result.extend(chunk)
        return bytes(result)

    def _send_ack(
        self,
        endpoint: socket.socket,
        name: bytes,
        frame_digest: str,
        deadline_ns: int,
    ) -> None:
        self._send_all(
            endpoint,
            name + b"\0" + frame_digest.encode("ascii") + b"\n",
            deadline_ns,
        )

    def _read_ack(
        self,
        endpoint: socket.socket,
        name: bytes,
        frame_digest: str,
        deadline_ns: int,
    ) -> None:
        expected = name + b"\0" + frame_digest.encode("ascii") + b"\n"
        observed = self._recv_exact(endpoint, len(expected), deadline_ns)
        if observed != expected:
            raise SecretTransferError("staged transfer acknowledgement mismatch")

    def close(self) -> None:
        for endpoint in (self._sender, self._receiver):
            try:
                endpoint.close()
            except OSError:
                pass

    def __enter__(self) -> "StagedSecretTransfer":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
