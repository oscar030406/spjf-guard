"""Backfilling baselines on one main-table cell (original clock, main-table k).

    python -u evidence/revision_r1/backfill_baselines/run_backfill.py \
        --rep 0 --level 2 --policies CBF-L,Slack-L(300) [--prefix N] [--out-dir DIR]

Policies: CBF-L, Slack-L(G) use the limit L = 60 s as every job's runtime estimate (the
only estimate with a guarantee); CBF-P, Slack-P(G) use the stored SPJF-E prediction
(forward_scores.parquet column spjf_e by job_row, the score of the main table), clipped to
[1 us, L], with overrun to L.  G in {300, 600, 1200}.  Slack uses candidates "now+anchor".

One JSON per (rep, level, policy) in --out-dir (default outputs/revision_r1/
backfill_baselines/cells); an existing file is skipped, so the step is restartable.  The
row has the main_cells.csv columns (gap_closed with the same FCFS and SJF p99 as the main
table: FCFS recomputed with the production kernel and checked against main_cells.csv,
SJF read from it) plus: jobs whose excess over FCFS exceeds 300/600/1200 s, the rule's own
promise violations, jobs starting at another time than FCFS, kernel counters, wall time
and peak commit.  The process runs at BelowNormal priority.
"""
from __future__ import annotations

import argparse
import csv
import ctypes
import json
import math
import re
import sys
import time
from ctypes import wintypes
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "src"))
import bf_kernel as bk  # noqa: E402
from spjf_guard.experiment.metrics import gap_closed, harm, reduction_percent  # noqa: E402
from spjf_guard.experiment.reproduce import load_overlay  # noqa: E402
from spjf_guard.sim import simulate  # noqa: E402
from spjf_guard.sim.policy import fcfs  # noqa: E402

OVERLAYS = ROOT / "data" / "derived" / "overlay_traces"
SCORES = ROOT / "data" / "derived" / "package_ranking_scores" / "forward_scores.parquet"
MAIN_CELLS = ROOT / "outputs" / "dev_tables" / "main_cells.csv"
OUT = ROOT / "outputs" / "revision_r1" / "backfill_baselines" / "cells"
MICROS = 1_000_000
L_S = 60.0
PROMISES = (300, 600, 1200)
PROFILE_CAP = 1 << 22
ALL_POLICIES = ["CBF-L"] + [f"Slack-L({g})" for g in PROMISES] + ["CBF-P"] + [
    f"Slack-P({g})" for g in PROMISES
]


class _PMC(ctypes.Structure):
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
    pmc = _PMC()
    pmc.cb = ctypes.sizeof(_PMC)
    k32 = ctypes.windll.kernel32
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    get = ctypes.windll.psapi.GetProcessMemoryInfo
    get.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PMC), wintypes.DWORD]
    get.restype = wintypes.BOOL
    if not get(k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb):
        raise OSError("GetProcessMemoryInfo failed")
    return pmc.PeakPagefileUsage / 2**30


def below_normal() -> None:
    k32 = ctypes.windll.kernel32
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    k32.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    if not k32.SetPriorityClass(k32.GetCurrentProcess(), 0x4000):
        raise OSError("SetPriorityClass failed")


def parse_policy(name: str):
    m = re.fullmatch(r"(CBF|Slack)-(L|P)(?:\((\d+)\))?", name)
    if m is None or (m.group(1) == "Slack") != (m.group(3) is not None):
        raise ValueError(f"unknown policy {name!r}; known: {ALL_POLICIES}")
    rule = bk.RULE_CBF if m.group(1) == "CBF" else bk.RULE_SLACK
    g_s = int(m.group(3)) if m.group(3) else 0
    return rule, m.group(2), g_s


def main_cell_rows(rep: int, level: int) -> dict:
    with MAIN_CELLS.open(newline="") as f:
        return {
            r["policy"]: r
            for r in csv.DictReader(f)
            if int(r["overlay"]) == rep and int(r["level"]) == level
        }


def load_cell(rep: int, level: int, prefix: int | None):
    path = OVERLAYS / f"primary_rep{rep}.npz"
    trace, k, labels = load_overlay(path, level, {}, L_S)
    with np.load(path) as z:
        job_row = z["job_row"]
        work_s = float(z["W"])
    a_us, s_us = trace.arrival_us, trace.service_us
    if prefix:
        a_us, s_us = a_us[:prefix], s_us[:prefix]
        labels = {key: v[:prefix] for key, v in labels.items()}
        job_row = job_row[:prefix]
        trace = type(trace)(a_us, s_us, {}, trace.limit_s)
    return trace, k, labels, job_row, work_s


def predicted_estimates(job_row: np.ndarray) -> np.ndarray:
    import pandas as pd

    pred = pd.read_parquet(SCORES, columns=["spjf_e"])["spjf_e"].to_numpy("float64")[job_row]
    if not np.isfinite(pred).all():
        raise ValueError("spjf_e is not finite on every job")
    return np.clip(np.rint(pred * MICROS), 1, int(L_S * MICROS)).astype(np.int64)


def run_policy(trace, k, est, rule, g_s):
    t0 = time.time()
    start, promise, cnt = bk.simulate_backfill(
        trace.arrival_us, trace.service_us, est, k, rule, g_s * MICROS, int(L_S * MICROS),
        PROFILE_CAP,
    )
    return start, promise, cnt, time.time() - t0


def summary_row(rep, level, k, rho_target, work_s, policy, wait_us, fcfs_us, labels, ref):
    wait_s = wait_us / MICROS
    fcfs_s = fcfs_us / MICROS
    excess = wait_s - fcfs_s
    inw, heavy = labels["in_window"], labels["is_heavy"]
    p99 = float(np.quantile(wait_s[inw], 0.99))
    fcfs_p99, sjf_p99 = ref
    row = {
        "overlay": rep,
        "level": level,
        "k": k,
        "rho_target": rho_target,
        "rho_realised": round(work_s / (3600.0 * k), 6),
        "policy": policy,
        "servers": k,
        "n_jobs": len(wait_s),
        "p99_dl_s": p99,
        "mean_s": float(wait_s.mean()),
        "p99_all_s": float(np.quantile(wait_s, 0.99)),
        "max_excess_s": float(excess.max()),
        "harm_s": harm(excess, fcfs_s),
        "max_heavy_s": float(wait_s[heavy].max()) if heavy.any() else math.nan,
        "fired_fraction_queue_weighted": math.nan,
        "fired_pct": math.nan,
        "gap_closed": gap_closed(p99, fcfs_p99, sjf_p99),
        "reduction_pct": reduction_percent(p99, fcfs_p99),
    }
    for g in PROMISES:
        row[f"n_excess_gt_{g}"] = int(np.sum(excess > g))
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rep", type=int, required=True)
    ap.add_argument("--level", type=int, required=True)
    ap.add_argument("--policies", default=",".join(ALL_POLICIES))
    ap.add_argument("--prefix", type=int, default=None)
    ap.add_argument("--out-dir", type=Path, default=OUT)
    args = ap.parse_args()
    below_normal()
    policies = [p for p in args.policies.split(",") if p]
    for p in policies:
        parse_policy(p)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    tag = f"o{args.rep}_l{args.level}" + (f"_p{args.prefix}" if args.prefix else "")
    todo = [p for p in policies if not (args.out_dir / f"{tag}_{p}.json").exists()]
    if not todo:
        print(f"{tag}: every policy done", flush=True)
        return 0
    t0 = time.time()
    trace, k, labels, job_row, work_s = load_cell(args.rep, args.level, args.prefix)
    rows = main_cell_rows(args.rep, args.level)
    rho_target = float(rows["FCFS"]["rho_target"])
    fcfs_wait = simulate(trace, fcfs(), k).wait_us
    fcfs_start = trace.arrival_us + fcfs_wait
    fcfs_p99 = float(np.quantile(fcfs_wait[labels["in_window"]] / MICROS, 0.99))
    if args.prefix is None:
        csv_p99 = float(rows["FCFS"]["p99_dl_s"])
        if abs(fcfs_p99 - csv_p99) > 1e-9 * max(1.0, csv_p99):
            raise RuntimeError(f"FCFS p99 {fcfs_p99} != main_cells.csv {csv_p99}")
    ref = (fcfs_p99, float(rows["SJF"]["p99_dl_s"]))
    est_l = np.full(len(trace.arrival_us), int(L_S * MICROS), np.int64)
    est_p = predicted_estimates(job_row) if any("-P" in p for p in todo) else None
    print(f"{tag}: k = {k}, n = {len(est_l)}, load + FCFS {time.time() - t0:.0f} s,"
          f" FCFS p99_dl {fcfs_p99:.3f} s, SJF p99_dl {ref[1]:.3f} s", flush=True)
    for policy in todo:
        rule, kind, g_s = parse_policy(policy)
        est = est_l if kind == "L" else est_p
        start, promise, cnt, wall = run_policy(trace, k, est, rule, g_s)
        counters = {name: int(cnt[getattr(bk, name)]) for name in dir(bk)
                    if name.startswith("C_") and name != "C_LEN"}
        if cnt[bk.C_ERR] != 0:
            raise RuntimeError(f"{tag} {policy}: kernel error {counters}")
        wait = start - trace.arrival_us
        if (wait < 0).any():
            raise RuntimeError(f"{tag} {policy}: negative wait")
        row = summary_row(args.rep, args.level, k, rho_target, work_s, policy, wait, fcfs_wait,
                          labels, ref)
        row.update(
            {
                "estimate": "limit L" if kind == "L" else "SPJF-E prediction",
                "slack_G_s": g_s if rule == bk.RULE_SLACK else None,
                "promise_violations": int(np.sum(start > promise)),
                "n_start_differs_from_fcfs": int(np.sum(start != fcfs_start)),
                "counters": counters,
                "wall_s": round(wall, 1),
                "peak_commit_gb": round(peak_commit_gb(), 2),
                "prefix": args.prefix,
            }
        )
        out = args.out_dir / f"{tag}_{policy}.json"
        tmp = out.with_suffix(".tmp")
        tmp.write_text(json.dumps(row, indent=1))
        tmp.replace(out)
        print(f"{tag} {policy}: p99_dl {row['p99_dl_s']:.3f} s, gap {row['gap_closed']:.4f},"
              f" harm {row['harm_s']:.3f} s, max excess {row['max_excess_s']:.3f} s,"
              f" > 300/600/1200: {row['n_excess_gt_300']}/{row['n_excess_gt_600']}/"
              f"{row['n_excess_gt_1200']}, differs from FCFS {row['n_start_differs_from_fcfs']},"
              f" promise violations {row['promise_violations']}, {wall:.0f} s,"
              f" peak commit {row['peak_commit_gb']} GB, counters {counters}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
