"""Process limits shared by the scripts of this directory.

Import this module before numpy.  It caps the numerical threads at 2, lowers the process to
BelowNormal priority (child processes inherit it on Windows), and puts the process in a
job object.  The job object records the peak commit of the process and of every child it
starts, which is the figure the machine's limit is stated in.
"""

import ctypes
import os
import sys
from ctypes import wintypes
from pathlib import Path

for _name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
    os.environ.setdefault(_name, "2")

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
OUT = ROOT / "outputs" / "revision_r1" / "small_k_shapes"
for _path in (ROOT / "src", ROOT / "scripts", HERE):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

CONFIG = ROOT / "configs" / "main_frozen_1289aa2.yaml"
SELECTION = ROOT / "outputs" / "selection_v4" / "selected_parameters.csv"
SCORES = ROOT / "data" / "derived" / "package_ranking_scores" / "forward_scores.parquet"
K1_DIR = ROOT / "outputs" / "steady_online_g18b" / "overlays"
OVERLAY_DIR = OUT / "overlays"
LOADS = {"u50": 0.50, "u80": 0.80, "u95": 0.95}
REPS = range(5)

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.GetCurrentProcess.restype = wintypes.HANDLE
_k32.CreateJobObjectW.restype = wintypes.HANDLE
_k32.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
_k32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
_k32.SetPriorityClass.argtypes = (wintypes.HANDLE, wintypes.DWORD)
_k32.QueryInformationJobObject.argtypes = (
    wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p
)
BELOW_NORMAL_PRIORITY_CLASS = 0x4000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9


class _Basic(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _Io(ctypes.Structure):
    _fields_ = [(n, ctypes.c_ulonglong) for n in ("r", "w", "o", "rb", "wb", "ob")]


class _Extended(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _Basic),
        ("IoInfo", _Io),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def _enter_job():
    me = _k32.GetCurrentProcess()
    if not _k32.SetPriorityClass(me, BELOW_NORMAL_PRIORITY_CLASS):
        raise ctypes.WinError(ctypes.get_last_error())
    job = _k32.CreateJobObjectW(None, None)
    if not job or not _k32.AssignProcessToJobObject(job, me):
        raise ctypes.WinError(ctypes.get_last_error())
    return job


_JOB = _enter_job()


def peak_commit_gb() -> float:
    """Peak commit of this process and all its children so far, in GB."""
    info = _Extended()
    if not _k32.QueryInformationJobObject(
        _JOB, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION, ctypes.byref(info), ctypes.sizeof(info), None
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    return info.PeakJobMemoryUsed / 1e9
