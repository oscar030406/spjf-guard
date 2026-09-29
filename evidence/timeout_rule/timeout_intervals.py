"""Paired week-block intervals for Guard(G) - Timeout(G), the way the paper states
differences.

The same week draw as the package (configs/main.yaml bootstrap: 2,000 resamples, seed
20260919, row 0 the observed sample) moves every policy, so the interval of a difference
is the interval of the claim.  Gap closed is computed inside each resample with that
resample's own FCFS and SJF p99, then averaged over the five overlays, as
scripts/run_main.py paired_differences does.

Scores: the stored expected-cost score (original clock), the basis of Table tab:guard.
"""

from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))

from spjf_guard import config as cfgmod  # noqa: E402
from spjf_guard.experiment import bootstrap as bs  # noqa: E402
from spjf_guard.experiment.parallel import _bootstrap  # noqa: E402
from spjf_guard.experiment.reproduce import load_overlay  # noqa: E402
from spjf_guard.sim.policy import MICROS  # noqa: E402
from spjf_guard.sim.runner import simulate  # noqa: E402
from timeout_overlays import LIMIT_S, OVERLAYS, PROMISES, timeout_kernel  # noqa: E402


def cell_replicates(cfg, path, level, multiplicities):
    trace, k, labels = load_overlay(path, level, {"tweedie": "spjf_e"}, LIMIT_S)
    with np.load(path) as store:
        week = store["wk"].astype(np.int64)
    policies = {p.name: p for p in cfg.policies(k)}
    score = trace.score_for(policies["SPJF-E"].score_key)
    reps = {}
    for name in ("FCFS", "SJF") + tuple(f"Guard({g:g})" for g in PROMISES):
        wait = simulate(trace, policies[name], k).wait_us
        reps[name] = _bootstrap(wait, week, multiplicities, labels["in_window"])["p99_dl"]
    slack = (3 - 2 / k) * LIMIT_S
    for g in PROMISES:
        theta_us = np.int64(round((g - slack) * MICROS))
        wait = timeout_kernel(trace.arrival_us, trace.service_us, score, k, theta_us)
        reps[f"Timeout({g:g})"] = _bootstrap(wait, week, multiplicities, labels["in_window"])[
            "p99_dl"
        ]
    return reps


def main() -> None:
    cfg = cfgmod.load(ROOT / "configs" / "main.yaml")
    with np.load(OVERLAYS[0]) as store:
        n_weeks = len(store["weeks"])
    multiplicities = bs.with_point_estimate(
        bs.week_multiplicities(
            n_weeks, int(cfg["bootstrap"]["resamples"]), int(cfg["bootstrap"]["seed"])
        )
    )
    rows = []
    for level in (0, 1, 2):
        cells = []
        for overlay, path in enumerate(OVERLAYS):
            started = time.time()
            cells.append(cell_replicates(cfg, path, level, multiplicities))
            print(f"level {level} overlay {overlay} [{time.time() - started:.0f} s]", flush=True)
        for g in PROMISES:
            guard, clock = f"Guard({g:g})", f"Timeout({g:g})"
            gaps = {}
            for name in (guard, clock):
                gaps[name] = np.mean(
                    np.vstack([(c["FCFS"] - c[name]) / (c["FCFS"] - c["SJF"]) for c in cells]),
                    axis=0,
                )
            diff = gaps[guard] - gaps[clock]
            p99_diff = np.mean(np.vstack([c[clock] - c[guard] for c in cells]), axis=0)
            row = {
                "level": level,
                "promise_s": g,
                "guard_gap": round(float(gaps[guard][0]), 6),
                "guard_gap_lo": round(bs.interval(gaps[guard])[0], 6),
                "guard_gap_hi": round(bs.interval(gaps[guard])[1], 6),
                "timeout_gap": round(float(gaps[clock][0]), 6),
                "timeout_gap_lo": round(bs.interval(gaps[clock])[0], 6),
                "timeout_gap_hi": round(bs.interval(gaps[clock])[1], 6),
                "gap_difference": round(float(diff[0]), 6),
                "gap_difference_lo": round(bs.interval(diff)[0], 6),
                "gap_difference_hi": round(bs.interval(diff)[1], 6),
                "p99_timeout_minus_guard_s": round(float(p99_diff[0]), 6),
                "p99_diff_lo": round(bs.interval(p99_diff)[0], 6),
                "p99_diff_hi": round(bs.interval(p99_diff)[1], 6),
            }
            rows.append(row)
            print("  " + "  ".join(f"{k}={v}" for k, v in row.items()), flush=True)
    with open(HERE / "timeout_intervals.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print("EXIT 0")


if __name__ == "__main__":
    main()
