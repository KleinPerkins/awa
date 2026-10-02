from __future__ import annotations

import hashlib
import unittest

from engine import registration_executor


class StagedSecretTransferTest(unittest.TestCase):
    def test_bound_frame_requires_received_then_activated(self) -> None:
        token = hashlib.sha256(
            b"awa-registration-executor/v1\0" + b"q" * 32
        ).hexdigest()
        frame = registration_executor.StagedGrantFrame(
            member_id="1" * 64,
            effect_id="2" * 64,
            executor_token_hash=token,
            operation_id="3" * 64,
            member_tuple_hash="4" * 64,
            status_hash="5" * 64,
            protocol_hash="6" * 64,
            staged_epoch_hash="7" * 64,
        )
        transfer = registration_executor.StagedSecretTransfer.precreate(
            clock_ns=lambda: 100
        )
        self.addCleanup(transfer.close)
        deadline = transfer.deadline_after()
        transfer.send_frame(frame, b"q" * 32, deadline_ns=deadline)
        with self.assertRaises(registration_executor.SecretTransferError):
            transfer.acknowledge_activated(frame.digest, deadline_ns=deadline)
        received = transfer.receive_frame(
            deadline_ns=deadline,
            expected_frame_digest=frame.digest,
        )
        self.addCleanup(received.close)
        self.assertEqual(received.frame, frame)
        transfer.wait_received(frame.digest, deadline_ns=deadline)
        transfer.wait_received(frame.digest, deadline_ns=deadline)
        transfer.acknowledge_activated(frame.digest, deadline_ns=deadline)
        transfer.acknowledge_activated(frame.digest, deadline_ns=deadline)
        transfer.wait_activated(frame.digest, deadline_ns=deadline)
        transfer.wait_activated(frame.digest, deadline_ns=deadline)
        self.assertEqual(received.take_secret(), b"q" * 32)

    def test_timeout_and_frame_mismatch_fail_closed(self) -> None:
        unbounded = registration_executor.StagedSecretTransfer.precreate(
            clock_ns=lambda: 100
        )
        with self.assertRaises(registration_executor.SecretTransferError):
            unbounded.receive_frame(
                deadline_ns=6_000_000_100,
            )
        self.assertEqual(unbounded.sender_fd, -1)
        self.assertEqual(unbounded.receiver_fd, -1)

        timeout = registration_executor.StagedSecretTransfer.precreate(
            clock_ns=lambda: 100
        )
        with self.assertRaises(registration_executor.SecretTransferError):
            timeout.receive_frame(
                deadline_ns=timeout.deadline_after(0.01),
            )
        self.assertEqual(timeout.sender_fd, -1)
        self.assertEqual(timeout.receiver_fd, -1)

        token = hashlib.sha256(
            b"awa-registration-executor/v1\0" + b"q" * 32
        ).hexdigest()
        frame = registration_executor.StagedGrantFrame(
            member_id="1" * 64,
            effect_id="2" * 64,
            executor_token_hash=token,
            operation_id="3" * 64,
            member_tuple_hash="4" * 64,
            status_hash="5" * 64,
            protocol_hash="6" * 64,
            staged_epoch_hash="7" * 64,
        )
        mismatch = registration_executor.StagedSecretTransfer.precreate(
            clock_ns=lambda: 100
        )
        deadline = mismatch.deadline_after()
        mismatch.send_frame(frame, b"q" * 32, deadline_ns=deadline)
        with self.assertRaises(registration_executor.SecretTransferError):
            mismatch.receive_frame(
                deadline_ns=deadline,
                expected_frame_digest="0" * 64,
            )
        self.assertEqual(mismatch.sender_fd, -1)
        self.assertEqual(mismatch.receiver_fd, -1)


if __name__ == "__main__":
    unittest.main()
