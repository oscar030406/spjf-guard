"""Shared pieces: environment, the overlay-0 cells as run_main builds them, one timed
call of the production kernel, the reproduction check, machine facts and the idle wait.

Import this module before numpy/numba anywhere in this directory: it pins the numba
thread count and points the numba cache away from src/.
"""

from __future__ import annotations

import csv
import ctypes
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "outputs" / "revision_r1" / "guard_overhead"
OUT.mkdir(parents=True, exist_ok=True)
for _v in ("PYTHONHOME", "PYTHONPATH", "UV_INTERNAL__PYTHONHOME"):
    os.environ.pop(_v, None)
os.environ.setdefault("NUMBA_NUM_THREADS", "2")
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("NUMBA_CACHE_DIR", str(OUT / "numba_cache"))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np  # noqa: E402

from spjf_guard import config as cfgmod  # noqa: E402
from spjf_guard.experiment.metrics import summarise  # noqa: E402
from spjf_guard.experiment.reproduce import load_overlay  # noqa: E402
from spjf_guard.sim.kernel import simulate_kernel  # noqa: E402
from spjf_guard.sim.policy import eta_fraction, fcfs  # noqa: E402
from spjf_guard.sim.runner import JobResults, _mode_of  # noqa: E402

CONFIG = ROOT / "configs" / "main_frozen_1289aa2.yaml"
OVERLAY = ROOT / "data" / "derived" / "overlay_traces" / "primary_rep0.npz"
SCORES = ROOT / "data" / "derived" / "package_ranking_scores" / "forward_scores.parquet"
SELECTION = ROOT / "outputs" / "selection_v4" / "selected_parameters.csv"
CELLS = ROOT / "outputs" / "dev_tables" / "main_cells.csv"
POLICIES = ("FCFS", "SPJF-E", "Guard(300)", "Guard(600)", "Guard(1200)")
COMPARED = (
    "p99_dl_s",
    "mean_s",
    "p99_all_s",
    "max_excess_s",
    "harm_s",
    "max_heavy_s",
    "fired_fraction_queue_weighted",
)


def load_setup():
    """Config, window, the overlay-0 trace with the run's spjf_e score, labels, K per level.

    Mirrors scripts/run_main.py sweep_cells: empty score map, then the regenerated score
    attached by job_row.  Only the ranking score is attached (the others are unused here).
    The trace arrays are the same at every level; only k changes.
    """
    import pandas as pd
    from run_main import read_selection

    from spjf_guard.sim import Trace

    cfg = cfgmod.load(CONFIG)
    selection = read_selection(SELECTION)
    window = int(cfg["run"]["segment_tree_window_ranks"])
    trace, _, labels = load_overlay(OVERLAY, 0, {}, cfg.limit_s)
    with np.load(OVERLAY) as z:
        job_row = z["job_row"]
        ks = [int(x) for x in z["K"]]
    key = str(cfg["scheduling"]["ranking_score"])
    score = pd.read_parquet(SCORES, columns=[key])[key].to_numpy("float64")[job_row]
    if not np.isfinite(score).all():
        raise ValueError("score not finite")
    trace = Trace(trace.arrival_us, trace.service_us, {key: score}, trace.limit_s)
    return cfg, selection, window, trace, labels, ks


def policy_set(cfg, selection, k):
    by_name = {p.name: p for p in cfg.policies(k, False, selection)}
    by_name["FCFS"] = fcfs()
    return [by_name[n] for n in POLICIES]


def kernel_args(trace, policy, k, window):
    """The exact argument tuple runner.simulate passes to simulate_kernel."""
    from spjf_guard.sim.kernel import MODE_FCFS
    from spjf_guard.sim.policy import MICROS

    mode = _mode_of(policy)
    if mode == MODE_FCFS:
        score = np.zeros(len(trace), np.float64)
    else:
        score = trace.score_for(policy.score_key)
        if policy.age_credit_per_s > 0.0:
            arrival_s = (trace.arrival_us - trace.arrival_us[0]) / MICROS
            score = score + policy.age_credit_per_s * arrival_s
    en, ed = eta_fraction(policy.eta_k)
    return (
        np.ascontiguousarray(trace.arrival_us),
        np.ascontiguousarray(trace.service_us),
        np.ascontiguousarray(score),
        int(k),
        mode,
        int(policy.b0_us),
        int(en),
        int(ed),
        int(policy.bmax_us),
        int(policy.skip_count),
        int(window),
        int(policy.gam_us),
    )


def warm_up(trace, policies, k, window, m=2000):
    """Compile simulate_kernel for every mode used, on a short prefix, outside timing."""
    from spjf_guard.sim import Trace

    head = Trace(trace.arrival_us[:m].copy(), trace.service_us[:m].copy(),
                 {key: v[:m].copy() for key, v in trace.scores.items()}, trace.limit_s)
    for p in policies:
        simulate_kernel(*kernel_args(head, p, k, window))


def timed_run(args):
    """One production-kernel call; returns (outputs, wall_ns, thread_cpu_ns)."""
    c0 = time.thread_time_ns()
    w0 = time.perf_counter_ns()
    out = simulate_kernel(*args)
    w1 = time.perf_counter_ns()
    c1 = time.thread_time_ns()
    return out, w1 - w0, c1 - c0


def to_results(policy, k, out):
    wait_us, dispatch_index, start_us, n_disp, n_forced, qw_total, qw_forced, n_rebuild, \
        max_span, err = out
    if err:
        raise RuntimeError(f"{policy.name}: window too small")
    res = JobResults(policy.name, int(k), wait_us, start_us, dispatch_index, int(n_disp),
                     int(n_forced), int(qw_total), int(qw_forced))
    extra = {"n_rebuild": int(n_rebuild), "max_span": int(max_span),
             "n_dispatch": int(n_disp), "n_forced": int(n_forced),
             "mean_waiting_at_dispatch": int(qw_total) / max(int(n_disp), 1)}
    return res, extra


def peak_queue(arrival_us, start_us):
    """Largest number of waiting jobs: after the arrivals at an instant are admitted and
    before the dispatches at that instant (the kernel's order).  Arrivals are sorted."""
    starts = np.sort(start_us)
    t = np.unique(arrival_us)
    arrived = np.searchsorted(arrival_us, t, side="right")
    started = np.searchsorted(starts, t, side="left")
    return int((arrived - started).max())


def reference_rows(level):
    rows = {}
    with open(CELLS, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["overlay"] == "0" and int(r["level"]) == level and r["policy"] in POLICIES:
                rows[r["policy"]] = r
    return rows


def compare(summary, ref_row):
    """Exact float equality on every compared column; returns the list of mismatches."""
    bad = []
    for f in COMPARED:
        got = float(getattr(summary, f))
        want = float(ref_row[f])
        same = got == want or (np.isnan(got) and np.isnan(want))
        if not same:
            bad.append({"field": f, "got": repr(got), "csv": ref_row[f]})
    if int(summary.n_jobs) != int(ref_row["n_jobs"]):
        bad.append({"field": "n_jobs", "got": summary.n_jobs, "csv": ref_row["n_jobs"]})
    return bad


def summarise_run(res, fcfs_wait, labels):
    return summarise(res, fcfs_wait, labels["in_window"], labels["is_heavy"])


# --------------------------------------------------------------------------- machine
# Everything below uses ctypes/winreg: spawning powershell or powercfg failed with
# 0xC0000142 while other heavy jobs were running, and a measurement must not die on it.
def _cpu_model():
    import winreg

    key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                         r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
    return winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()


class _GUID(ctypes.Structure):
    _fields_ = [("d1", ctypes.c_uint32), ("d2", ctypes.c_uint16), ("d3", ctypes.c_uint16),
                ("d4", ctypes.c_ubyte * 8)]


def _power_plan():
    powrprof = ctypes.windll.powrprof
    guid_p = ctypes.POINTER(_GUID)()
    if powrprof.PowerGetActiveScheme(None, ctypes.byref(guid_p)) != 0:
        raise OSError("PowerGetActiveScheme failed")
    g = guid_p.contents
    guid = (f"{g.d1:08x}-{g.d2:04x}-{g.d3:04x}-{bytes(g.d4[:2]).hex()}-"
            f"{bytes(g.d4[2:]).hex()}")
    size = ctypes.c_uint32(0)
    powrprof.PowerReadFriendlyName(None, guid_p, None, None, None, ctypes.byref(size))
    buf = ctypes.create_string_buffer(size.value)
    powrprof.PowerReadFriendlyName(None, guid_p, None, None, buf, ctypes.byref(size))
    ctypes.windll.kernel32.LocalFree(guid_p)
    name = ctypes.wstring_at(ctypes.addressof(buf))
    return f"{guid} ({name})"


def machine_info():
    import platform

    import numba

    return {
        "cpu_model": _cpu_model(),
        "logical_cpus": os.cpu_count(),
        "power_plan": _power_plan(),
        "os": platform.platform(),
        "python": sys.version.split()[0],
        "numpy": np.__version__,
        "numba": numba.__version__,
        "numba_num_threads": os.environ.get("NUMBA_NUM_THREADS"),
        "timer_resolution_thread_time_ns": time.get_clock_info("thread_time").resolution * 1e9,
        "timer_resolution_perf_counter_ns": time.get_clock_info("perf_counter").resolution * 1e9,
    }


class _FT(ctypes.Structure):
    _fields_ = [("lo", ctypes.c_uint32), ("hi", ctypes.c_uint32)]


def _system_times():
    idle, kern, user = _FT(), _FT(), _FT()
    ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kern),
                                          ctypes.byref(user))
    v = [(x.hi << 32) | x.lo for x in (idle, kern, user)]
    return v[0], v[1] + v[2]  # kernel time includes idle time


class _PMC(ctypes.Structure):  # PROCESS_MEMORY_COUNTERS_EX
    _fields_ = [("cb", ctypes.c_uint32), ("PageFaultCount", ctypes.c_uint32)]
    _fields_ += [(f, ctypes.c_size_t) for f in (
        "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
        "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage",
        "PagefileUsage", "PeakPagefileUsage", "PrivateUsage")]


class _PE32(ctypes.Structure):
    _fields_ = [("dwSize", ctypes.c_uint32), ("cntUsage", ctypes.c_uint32),
                ("th32ProcessID", ctypes.c_uint32), ("th32DefaultHeapID", ctypes.c_size_t),
                ("th32ModuleID", ctypes.c_uint32), ("cntThreads", ctypes.c_uint32),
                ("th32ParentProcessID", ctypes.c_uint32), ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", ctypes.c_uint32), ("szExeFile", ctypes.c_wchar * 260)]


SERVICE_DIRS = ("<service-dir>",)  # install folders of idle background services on the measuring machine


def _service_pids():
    """PIDs of idle background service processes and their descendants. One such service holds
    about 1 GB while idle and would otherwise block the idle wait forever (as it blocked
    the launcher of a timed physical run on 2026-10-06)."""
    k32 = ctypes.windll.kernel32
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)
    parent, entry = {}, _PE32()
    entry.dwSize = ctypes.sizeof(entry)
    ok = k32.Process32FirstW(snap, ctypes.byref(entry))
    while ok:
        parent[entry.th32ProcessID] = entry.th32ParentProcessID
        ok = k32.Process32NextW(snap, ctypes.byref(entry))
    k32.CloseHandle(snap)
    roots, name = set(), ctypes.create_unicode_buffer(1024)
    for pid in parent:
        h = k32.OpenProcess(0x1000, False, pid)
        if not h:
            continue
        size = ctypes.c_uint32(len(name))
        if k32.QueryFullProcessImageNameW(h, 0, name, ctypes.byref(size)) and \
                any(d in name.value.lower() for d in SERVICE_DIRS):
            roots.add(pid)
        k32.CloseHandle(h)
    out = set()
    for pid in parent:
        p, seen = pid, set()
        while p and p not in seen:
            if p in roots:
                out.add(pid)
                break
            seen.add(p)
            p = parent.get(p)
    return out


def python_processes():
    """[(pid, working_set_bytes, private_bytes)] for every python*.exe process except this
    one and its parent (the venv launcher).  Processes that cannot be opened are skipped:
    they belong to another user or are protected, and none of ours is."""
    k32 = ctypes.windll.kernel32
    pids = (ctypes.c_uint32 * 8192)()
    got = ctypes.c_uint32(0)
    if not k32.K32EnumProcesses(pids, ctypes.sizeof(pids), ctypes.byref(got)):
        raise OSError("EnumProcesses failed")
    me = {os.getpid(), os.getppid()}
    services = _service_pids()
    out = []
    name = ctypes.create_unicode_buffer(1024)
    for pid in pids[: got.value // 4]:
        if pid in me or pid == 0:
            continue
        h = k32.OpenProcess(0x1000 | 0x0400, False, pid)  # QUERY_LIMITED_INFORMATION | VM_READ
        if not h:
            h = k32.OpenProcess(0x1000, False, pid)
        if not h:
            continue
        try:
            size = ctypes.c_uint32(len(name))
            if not k32.QueryFullProcessImageNameW(h, 0, name, ctypes.byref(size)):
                continue
            exe = name.value.rsplit("\\", 1)[-1].lower()
            if not exe.startswith("python") or pid in services:
                continue
            pmc = _PMC()
            pmc.cb = ctypes.sizeof(pmc)
            if not k32.K32GetProcessMemoryInfo(h, ctypes.byref(pmc), pmc.cb):
                continue
            out.append((int(pid), int(pmc.WorkingSetSize), int(pmc.PrivateUsage)))
        finally:
            k32.CloseHandle(h)
    return out


def wait_until_idle(poll_s=30.0, need_s=120.0, cpu_limit=15.0, mem_limit=1 << 30, log=print):
    """Block until, for `need_s` in a row, total CPU stayed below `cpu_limit` percent in
    every poll interval and no other python process had a working set above `mem_limit`.
    No timeout.  Returns the observations of the qualifying window."""
    window = []
    i0, t0 = _system_times()
    started = time.time()
    while True:
        time.sleep(poll_s)
        i1, t1 = _system_times()
        busy = 100.0 * (1.0 - (i1 - i0) / max(t1 - t0, 1))
        i0, t0 = i1, t1
        procs = python_processes()
        heavy = [p for p in procs if p[1] > mem_limit]
        obs = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "cpu_pct": round(busy, 2),
               "n_python": len(procs),
               "max_python_ws_gb": round(max((p[1] for p in procs), default=0) / 2**30, 3),
               "max_python_private_gb": round(max((p[2] for p in procs), default=0) / 2**30, 3),
               "heavy_python": [p[0] for p in heavy]}
        ok = busy < cpu_limit and not heavy
        window = window + [obs] if ok else []
        log(f"idle poll {obs['time']}: cpu {busy:.1f}%, python>1GB {len(heavy)}, "
            f"qualifying {len(window) * poll_s:.0f}/{need_s:.0f} s "
            f"(waited {time.time() - started:.0f} s)")
        if len(window) * poll_s >= need_s:
            return {"waited_s": round(time.time() - started, 1), "polls": window}


def write_json(path, obj):
    Path(path).write_text(json.dumps(obj, indent=1, ensure_ascii=False), encoding="utf-8")
