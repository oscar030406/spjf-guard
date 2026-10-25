"""Imported first by the runners of limit/ and family/.

Lowers the process to BELOW_NORMAL (spawned workers inherit the class), writes no bytecode,
and keeps numba's cache under cache/ here, so nothing is written into the directories this
code imports read-only.  Copied from evidence/skipc_block_online/_setup.py, whose cache
directory is that task's own.
"""

import ctypes
import hashlib
import os
import sys
from pathlib import Path

HERE = Path(os.path.abspath(__file__)).parent  # abspath keeps a junction in the checkout path
ROOT = HERE.parent.parent
sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
os.environ["NUMBA_CACHE_DIR"] = str(HERE / "cache" / "numba")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

_K32 = ctypes.windll.kernel32
_K32.GetCurrentProcess.restype = ctypes.c_void_p
_K32.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
_K32.GetPriorityClass.argtypes = [ctypes.c_void_p]
_K32.SetPriorityClass(_K32.GetCurrentProcess(), 0x4000)
if _K32.GetPriorityClass(_K32.GetCurrentProcess()) != 0x4000:
    raise RuntimeError("could not lower this process to BELOW_NORMAL priority")


class _Counters(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong),
        ("PageFaultCount", ctypes.c_ulong),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


_PSAPI = ctypes.windll.psapi
_PSAPI.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(_Counters), ctypes.c_ulong]


def peak_gb() -> tuple[float, float]:
    """(peak commit, peak working set) of this process so far, in GB."""
    counters = _Counters()
    counters.cb = ctypes.sizeof(_Counters)
    if not _PSAPI.GetProcessMemoryInfo(_K32.GetCurrentProcess(), counters, counters.cb):
        raise ctypes.WinError()
    return counters.PeakPagefileUsage / 2**30, counters.PeakWorkingSetSize / 2**30


def code_tag(*paths: Path) -> str:
    """First 8 hex digits of the sha256 of these files: names an output directory, so a
    checkpoint left by other code is never resumed (rov's signature does not cover them)."""
    return hashlib.sha256(b"".join(Path(p).read_bytes() for p in paths)).hexdigest()[:8]


def require_tag(argv: list[str], stem: str, tag: str) -> None:
    out_dir = Path(argv[argv.index("--out-dir") + 1]).as_posix()
    if f"{stem}_{tag}" not in out_dir:
        raise SystemExit(f"--out-dir must lie under outputs/{stem}_{tag}/, this code's tag")
