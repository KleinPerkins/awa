"""Current-boot suspend-inclusive monotonic sampling for macOS M1 profile."""

from __future__ import annotations

import ctypes
import platform


class ClockUnavailable(RuntimeError):
    pass


class _Timebase(ctypes.Structure):
    _fields_ = [("numer", ctypes.c_uint32), ("denom", ctypes.c_uint32)]


def mach_continuous_time_ns() -> int:
    if platform.system() != "Darwin":
        raise ClockUnavailable("mach_continuous_time requires darwin")
    library = ctypes.CDLL(None, use_errno=True)
    try:
        continuous = library.mach_continuous_time
        timebase = library.mach_timebase_info
    except AttributeError as exc:
        raise ClockUnavailable("mach continuous clock unavailable") from exc
    continuous.restype = ctypes.c_uint64
    info = _Timebase()
    if timebase(ctypes.byref(info)) != 0 or info.denom == 0:
        raise ClockUnavailable("mach timebase unavailable")
    ticks = int(continuous())
    return ticks * int(info.numer) // int(info.denom)
