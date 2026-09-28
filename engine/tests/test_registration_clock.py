from __future__ import annotations

import platform
import unittest

from engine import registration_clock


@unittest.skipUnless(platform.system() == "Darwin", "M1 supports macOS only")
class RegistrationClockTest(unittest.TestCase):
    def test_mach_continuous_time_is_nonnegative_and_monotonic(self) -> None:
        first = registration_clock.mach_continuous_time_ns()
        second = registration_clock.mach_continuous_time_ns()
        self.assertGreaterEqual(first, 0)
        self.assertGreaterEqual(second, first)


if __name__ == "__main__":
    unittest.main()
