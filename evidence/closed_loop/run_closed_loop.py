"""Closed-loop (think-time-preserving) replay of the development overlays.

    uv run --no-sync python evidence/closed_loop/run_closed_loop.py validate
    uv run --no-sync python evidence/closed_loop/run_closed_loop.py run \
        [--reps 0,1,2] [--levels 0,1,2] [--keep-late 1,0]

`validate` runs the closed-loop kernel with gating disabled and compares it job for job
with `spjf_guard.sim.simulate` on the same overlay; the maximum absolute difference must
be zero.  `run` replays FCFS, SJF, SPJF-E and Guard(600) under gating and writes one row
per (overlay, level, policy, edge treatment) to out/closed_cells.csv.

The reference the per-job guarantee is stated against is FCFS run OPEN-loop on the
policy's own realised arrival sequence: that is the counterfactual Theorem 3 compares to,
and under gating each policy produces a different arrival sequence.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))

from closed_kernel import (  # noqa: E402
    MODE_FCFS,
    MODE_GUARD,
    MODE_SCORE,
    simulate_closed,
)
from spjf_guard.sim import MICROS, Trace, simulate  # noqa: E402
from spjf_guard.sim.bounds import guard_upper_bound  # noqa: E402
from spjf_guard.sim.policy import eta_fraction, fcfs, guard, sjf, spjf  # noqa: E402

OVERLAYS = ROOT / "data" / "derived" / "overlay_traces"
CHAINS = HERE / "out" / "chains"
OUT = HERE / "out"

SCORE_ARRAY = "tweedie"
"""The stored expected-cost score; the paper's SPJF-E on the original clock."""
LIMIT_S = 60.0
PROMISE_S = 600.0
B0_BASE_S = 120.0
ETA = 0.75
WINDOW = 1 << 22
STARTS_IMMEDIATELY_S = 1.0


def policy_for(name: str, k: int):
    if name == "FCFS":
        return fcfs()
    if name == "SJF":
        return sjf()
    if name == "SPJF-E":
        return spjf(SCORE_ARRAY, "SPJF-E")
    if name == "Guard(600)":
        return guard(PROMISE_S, k, LIMIT_S, B0_BASE_S * k / 4.0, ETA, SCORE_ARRAY)
    raise ValueError(name)


def kernel_args(policy, k: int):
    """(mode, b0_us, en, ed, bmax_us, gam_us) for the closed-loop kernel."""
    if policy.wrapper == "work":
        mode = MODE_GUARD
    elif policy.base == "fcfs":
        mode = MODE_FCFS
    else:
        mode = MODE_SCORE
    en, ed = eta_fraction(policy.eta_k)
    return mode, int(policy.b0_us), int(en), int(ed), int(policy.bmax_us), int(policy.gam_us)


def load_cell(rep: int, level: int) -> dict:
    with np.load(OVERLAYS / f"primary_rep{rep}.npz") as z:
        a_us = np.rint(z["a"] * MICROS).astype(np.int64)
        s_us = np.rint(z["svc"] * MICROS).astype(np.int64)
        tweedie = np.ascontiguousarray(z[SCORE_ARRAY], np.float64)
        dl = z["dl"].astype(bool)
        hvt = z["hvt"].astype(bool)
        wk = z["wk"].astype(np.int32)
        k = int(z["K"][level])
    with np.load(CHAINS / f"chain_rep{rep}.npz") as z:
        pred = z["pred"].astype(np.int64)
        deadline_us = np.rint(z["deadline"] * MICROS).astype(np.int64)
    n = len(a_us)
    succ = np.full(n, -1, np.int64)
    has = pred >= 0
    succ[pred[has]] = np.flatnonzero(has)
    delta_us = np.zeros(n, np.int64)
    offset_us = np.zeros(n, np.int64)
    delta_us[has] = a_us[has] - (a_us[pred[has]] + s_us[pred[has]])
    offset_us[has] = a_us[has] - a_us[pred[has]]
    gate = np.full(n, 2, np.uint8)
    gate[has] = np.where(delta_us[has] >= 0, 1, 0).astype(np.uint8)
    return {
        "rep": rep,
        "level": level,
        "k": k,
        "a_us": a_us,
        "s_us": s_us,
        "tweedie": tweedie,
        "dl": dl,
        "hvt": hvt,
        "wk": wk,
        "succ": succ,
        "gate": gate,
        "delta_us": delta_us,
        "offset_us": offset_us,
        "deadline_us": deadline_us,
    }


def score_for(cell: dict, policy) -> np.ndarray:
    if policy.base == "fcfs":
        return np.zeros(len(cell["a_us"]), np.float64)
    if policy.score_key == "true_size":
        return cell["s_us"].astype(np.float64)
    return cell["tweedie"]


def run_kernel(cell: dict, policy, closed: int, drop: int):
    mode, b0, en, ed, bmax, gam = kernel_args(policy, cell["k"])
    return simulate_closed(
        cell["a_us"],
        cell["s_us"],
        score_for(cell, policy),
        cell["succ"],
        cell["gate"],
        cell["delta_us"],
        cell["offset_us"],
        cell["deadline_us"],
        int(cell["k"]),
        mode,
        b0,
        en,
        ed,
        bmax,
        WINDOW,
        gam,
        int(closed),
        int(drop),
    )


def fcfs_open_on(a_prime_us: np.ndarray, s_us: np.ndarray, k: int) -> np.ndarray:
    """FCFS waits on the realised arrival sequence, in the input order of the subset."""
    order = np.argsort(a_prime_us, kind="stable")
    trace = Trace(
        np.ascontiguousarray(a_prime_us[order]),
        np.ascontiguousarray(s_us[order]),
        {},
        limit_s=LIMIT_S,
    )
    result = simulate(trace, fcfs(), k, window=WINDOW)
    out = np.empty(len(order), np.int64)
    out[order] = result.wait_us
    return out


def validate(rep: int, level: int) -> dict:
    cell = load_cell(rep, level)
    report = {}
    for name in ("FCFS", "SJF", "SPJF-E", "Guard(600)"):
        policy = policy_for(name, cell["k"])
        t0 = time.time()
        out = run_kernel(cell, policy, closed=0, drop=0)
        mine = out[0]
        assert out[10] == 0, "segment-tree window too small"
        assert int(out[2].sum()) == len(mine), "not every job was admitted"
        t1 = time.time()
        trace = Trace(
            cell["a_us"], cell["s_us"], {SCORE_ARRAY: cell["tweedie"]}, limit_s=LIMIT_S
        )
        theirs = simulate(trace, policy, cell["k"], window=WINDOW).wait_us
        t2 = time.time()
        diff = int(np.abs(mine - theirs).max())
        report[name] = {
            "max_abs_diff_us": diff,
            "n_differing": int((mine != theirs).sum()),
            "closed_kernel_s": round(t1 - t0, 1),
            "package_kernel_s": round(t2 - t1, 1),
            "p99_dl_s": float(np.quantile(mine[cell["dl"]] / MICROS, 0.99)),
        }
        print(f"  {name}: {report[name]}", flush=True)
    return report


def arrivals_per_hour(a_prime_us: np.ndarray, in_window: np.ndarray, s_us, k: int) -> dict:
    hour = (a_prime_us[in_window] // (3600 * MICROS)).astype(np.int64)
    out = {}
    if hour.size:
        counts = np.bincount(hour - hour.min())
        counts = counts[counts > 0]
        out.update(
            {
                "dl_arrivals_per_hour_mean": float(counts.mean()),
                "dl_arrivals_per_hour_p99": float(np.quantile(counts, 0.99)),
                "dl_arrivals_per_hour_max": float(counts.max()),
            }
        )
    allhour = (a_prime_us // (3600 * MICROS)).astype(np.int64)
    allhour -= allhour.min()
    work = np.bincount(allhour, weights=s_us / MICROS)
    out["busy_hour_work_s"] = float(work.max())
    out["rho_busy_hour"] = float(work.max()) / (3600.0 * k)
    out["span_days"] = float(a_prime_us.max() - a_prime_us.min()) / MICROS / 86400.0
    return out


def summarise(cell: dict, name: str, out, closed: int, drop: int, elapsed: float) -> dict:
    wait_us, a_prime, admitted = out[0], out[1], out[2].astype(bool)
    n_disp, n_forced, qw_total, qw_forced, n_dropped = (
        int(out[3]),
        int(out[4]),
        int(out[5]),
        int(out[6]),
        int(out[7]),
    )
    k = cell["k"]
    w = wait_us[admitted]
    ap = a_prime[admitted]
    sv = cell["s_us"][admitted]
    dl_rec = cell["dl"][admitted]
    hv = cell["hvt"][admitted]
    dl_real = (ap <= cell["deadline_us"][admitted]) & (
        ap >= cell["deadline_us"][admitted] - 86400 * MICROS
    )
    wf = fcfs_open_on(ap, sv, k) if name != "FCFS" else w
    excess = (w - wf) / MICROS
    undelayed = wf <= STARTS_IMMEDIATELY_S * MICROS
    row = {
        "overlay": cell["rep"],
        "level": cell["level"],
        "k": k,
        "policy": name,
        "mode": "closed" if closed else "open",
        "late_submissions": "kept" if drop == 0 else "dropped",
        "n_jobs": int(admitted.sum()),
        "n_dropped": n_dropped,
        "offered_work_s": float(sv.sum()) / MICROS,
        "p99_dl_s": float(np.quantile(w[dl_rec] / MICROS, 0.99)) if dl_rec.any() else float("nan"),
        "p99_dl_realised_window_s": (
            float(np.quantile(w[dl_real] / MICROS, 0.99)) if dl_real.any() else float("nan")
        ),
        "n_dl_recorded": int(dl_rec.sum()),
        "n_dl_realised": int(dl_real.sum()),
        "mean_s": float(w.mean()) / MICROS,
        "p99_all_s": float(np.quantile(w / MICROS, 0.99)),
        "max_s": float(w.max()) / MICROS,
        "max_heavy_s": float(w[hv].max()) / MICROS if hv.any() else float("nan"),
        "max_excess_s": float(excess.max()),
        "harm_s": float(excess[undelayed].max()) if undelayed.any() else float("nan"),
        "fired_fraction_queue_weighted": qw_forced / max(qw_total, 1),
        "fired_pct": 100.0 * n_forced / max(n_disp, 1),
        "max_fcfs_own_s": float(wf.max()) / MICROS,
        "seconds": round(elapsed, 1),
    }
    drift = (ap - cell["a_us"][admitted]) / MICROS
    row.update(
        {
            "drift_mean_s": float(drift.mean()),
            "drift_p50_s": float(np.quantile(drift, 0.5)),
            "drift_p99_s": float(np.quantile(drift, 0.99)),
            "drift_max_s": float(drift.max()),
            "share_arriving_past_deadline": float(
                (ap > cell["deadline_us"][admitted]).mean()
            ),
        }
    )
    row.update(arrivals_per_hour(ap, dl_rec, sv, k))
    policy = policy_for(name, k)
    if policy.wrapper == "work":
        bound = guard_upper_bound(wf, policy, k, LIMIT_S)
        ws = w / MICROS
        row["bound_violations"] = int((ws > bound).sum())
        ratio = ws / np.maximum(bound, 1e-12)
        row["worst_ratio_to_bound"] = float(ratio.max())
        row["bmax_s"] = policy.bmax_us / MICROS
    else:
        row["bound_violations"] = ""
        row["worst_ratio_to_bound"] = ""
        row["bmax_s"] = ""
    return row


def run(reps, levels, keeps) -> None:
    rows = []
    path = OUT / "closed_cells.csv"
    for rep in reps:
        for level in levels:
            cell = load_cell(rep, level)
            plan = [(0, 0)] + [(1, d) for d in keeps]
            for closed, drop in plan:
                for name in ("FCFS", "SJF", "SPJF-E", "Guard(600)"):
                    t0 = time.time()
                    out = run_kernel(
                        cell, policy_for(name, cell["k"]), closed=closed, drop=drop
                    )
                    assert out[10] == 0, "segment-tree window too small"
                    row = summarise(cell, name, out, closed, drop, time.time() - t0)
                    rows.append(row)
                    print(
                        f"rep{rep} L{level} k{cell['k']} {name} "
                        f"{'open' if closed == 0 else 'closed'}/"
                        f"{'kept' if drop == 0 else 'dropped'}: "
                        f"p99_dl={row['p99_dl_s']:.3f} mean={row['mean_s']:.4f} "
                        f"max={row['max_s']:.1f} ({row['seconds']}s)",
                        flush=True,
                    )
                    del out
                    with path.open("w", newline="", encoding="utf-8") as fh:
                        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
                        writer.writeheader()
                        writer.writerows(rows)
            del cell


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["validate", "run"])
    ap.add_argument("--reps", default="0,1,2")
    ap.add_argument("--levels", default="0,1,2")
    ap.add_argument("--keep-late", default="0,1", help="0 keeps late submissions, 1 drops them")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if args.action == "validate":
        import json

        report = {}
        for level in (0, 1, 2):
            print(f"overlay 0, level {level}", flush=True)
            report[f"level{level}"] = validate(0, level)
        (OUT / "validation.json").write_text(__import__("json").dumps(report, indent=2))
        del json
        return
    run(
        [int(x) for x in args.reps.split(",")],
        [int(x) for x in args.levels.split(",")],
        [int(x) for x in args.keep_late.split(",")],
    )


if __name__ == "__main__":
    main()
