"""One-use anonymous AF_UNIX staged executor-secret transfer."""

from __future__ import annotations

import hashlib
import socket
from dataclasses import dataclass


class SecretTransferError(RuntimeError):
    pass


@dataclass
class StagedSecretTransfer:
    _sender: socket.socket
    _receiver: socket.socket
    _sent: bool = False
    _received: bool = False

    @classmethod
    def precreate(cls) -> "StagedSecretTransfer":
        sender, receiver = socket.socketpair(
            socket.AF_UNIX, socket.SOCK_STREAM
        )
        sender.set_inheritable(False)
        receiver.set_inheritable(False)
        return cls(sender, receiver)

    @property
    def sender_fd(self) -> int:
        return self._sender.fileno()

    @property
    def receiver_fd(self) -> int:
        return self._receiver.fileno()

    def transfer(self, secret: bytearray, expected_hash: str) -> bytes:
        self.send(secret, expected_hash)
        return self.receive(expected_hash)

    def send(self, secret: bytearray, expected_hash: str) -> None:
        if self._sent:
            raise SecretTransferError("staged secret transfer is one-use")
        try:
            if not isinstance(secret, bytearray) or not 32 <= len(secret) <= 4096:
                raise SecretTransferError("invalid executor secret size")
            actual = hashlib.sha256(
                b"awa-registration-executor/v1\0" + bytes(secret)
            ).hexdigest()
            if actual != expected_hash:
                raise SecretTransferError("executor secret hash mismatch")
            payload = len(secret).to_bytes(4, "big") + bytes(secret)
            self._sender.sendall(payload)
            self._sender.shutdown(socket.SHUT_WR)
            self._sender.close()
            self._sent = True
        except Exception:
            self.close()
            self._sent = True
            self._received = True
            raise
        finally:
            if isinstance(secret, bytearray):
                for index in range(len(secret)):
                    secret[index] = 0

    def receive(self, expected_hash: str) -> bytes:
        if not self._sent or self._received:
            raise SecretTransferError("staged secret receive is out of order")
        received = bytearray()
        try:
            header = self._recv_exact(4)
            size = int.from_bytes(header, "big")
            if not 32 <= size <= 4096:
                raise SecretTransferError("invalid staged secret frame")
            received.extend(self._recv_exact(size))
            check = hashlib.sha256(
                b"awa-registration-executor/v1\0" + bytes(received)
            ).hexdigest()
            if check != expected_hash:
                raise SecretTransferError("received executor secret mismatch")
            return bytes(received)
        finally:
            for index in range(len(received)):
                received[index] = 0
            self.close()
            self._received = True

    def _recv_exact(self, size: int) -> bytes:
        result = bytearray()
        while len(result) < size:
            chunk = self._receiver.recv(size - len(result))
            if not chunk:
                raise SecretTransferError("truncated staged secret frame")
            result.extend(chunk)
        return bytes(result)

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
