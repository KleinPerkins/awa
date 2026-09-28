from __future__ import annotations

import hashlib
import unittest

from engine import registration_executor


class StagedSecretTransferTest(unittest.TestCase):
    def test_precreated_anonymous_socketpair_is_one_use_and_zeroized(self) -> None:
        secret = bytearray(b"s" * 32)
        expected = hashlib.sha256(
            b"awa-registration-executor/v1\0" + bytes(secret)
        ).hexdigest()
        transfer = registration_executor.StagedSecretTransfer.precreate()
        self.assertGreaterEqual(transfer.sender_fd, 0)
        self.assertGreaterEqual(transfer.receiver_fd, 0)
        received = transfer.transfer(secret, expected)
        self.assertEqual(received, b"s" * 32)
        self.assertEqual(secret, bytearray(32))
        self.assertEqual(transfer.sender_fd, -1)
        self.assertEqual(transfer.receiver_fd, -1)
        with self.assertRaises(registration_executor.SecretTransferError):
            transfer.transfer(bytearray(b"x" * 32), expected)

    def test_hash_mismatch_closes_and_zeroizes(self) -> None:
        secret = bytearray(b"s" * 32)
        transfer = registration_executor.StagedSecretTransfer.precreate()
        with self.assertRaises(registration_executor.SecretTransferError):
            transfer.transfer(secret, "00" * 32)
        self.assertEqual(secret, bytearray(32))
        self.assertEqual(transfer.sender_fd, -1)
        self.assertEqual(transfer.receiver_fd, -1)

    def test_staged_sender_and_receiver_are_separate_one_use_steps(self) -> None:
        secret = bytearray(b"z" * 32)
        expected = hashlib.sha256(
            b"awa-registration-executor/v1\0" + bytes(secret)
        ).hexdigest()
        transfer = registration_executor.StagedSecretTransfer.precreate()
        transfer.send(secret, expected)
        self.assertEqual(secret, bytearray(32))
        self.assertEqual(transfer.sender_fd, -1)
        self.assertGreaterEqual(transfer.receiver_fd, 0)
        self.assertEqual(transfer.receive(expected), b"z" * 32)
        self.assertEqual(transfer.receiver_fd, -1)


if __name__ == "__main__":
    unittest.main()
