"""Process set-up shared by the scripts here; import it before numba or numpy.

Two numba/OMP threads, the numba cache under outputs/ (so no cache file is written next to
src/ or another prechecks directory), BelowNormal priority, and the peak commit charge.
"""

from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
OUT = ROOT / "outputs" / "revision_r1" / "report_delay"

for _var in ("NUMBA_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_var] = "2"
os.environ["NUMBA_CACHE_DIR"] = str(OUT / "numba_cache")
sys.dont_write_bytecode = True
for _p in (ROOT / "src", HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


def below_normal() -> None:
    k32 = ctypes.windll.kernel32
    k32.SetPriorityClass(k32.GetCurrentProcess(), 0x00004000)  # BELOW_NORMAL_PRIORITY_CLASS


class _Counters(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def peak_commit_gb() -> float:
    """Peak private commit of this process (PeakPagefileUsage), in GB."""
    c = _Counters()
    c.cb = ctypes.sizeof(c)
    psapi = ctypes.windll.psapi
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_Counters), wintypes.DWORD]
    k32 = ctypes.windll.kernel32
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    if not psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(c), c.cb):
        raise OSError("GetProcessMemoryInfo failed")
    return c.PeakPagefileUsage / 1e9
