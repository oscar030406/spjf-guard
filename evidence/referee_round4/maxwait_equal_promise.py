"""Referee round 4: MaxWait at the threshold that proves the same promise as Guard(G).

maxwait_five_overlays.py ran MaxWait(T) at T = G, which is not an equal promise: a
maximum-waiting-time rule with threshold theta lets overtakers through only while the
tagged job has waited less than theta, so In_i < k(theta + L) and, by Theorem 1 of the
manuscript, excess < theta + (3 - 2/k)L.  The threshold that offers the promise G is
therefore theta = G - (3 - 2/k)L, the same additive constant Guard(G) pays through
B_max = k(G - (3 - 2/k)L).  This script runs MaxWait at that theta on the five
development overlays and the three loads, and also records the realised maximum excess
against G, which checks that clock bound on the real trace.

The kernel and metrics are imported unchanged from maxwait_baseline.py.  FCFS is the
kernel at theta = 0 (the five-overlay run showed it equal to the package FCFS job by job
on all fifteen cells); SJF comes from the package simulator.

Run from the repository root:
  env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME NUMBA_NUM_THREADS=4 \
      OMP_NUM_THREADS=4 uv run --no-sync python evidence/referee_round4/maxwait_equal_promise.py
"""

from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from maxwait_baseline import (  # noqa: E402
    MICROS,
    ROOT,
    SCORE_KEY,
    _metrics,
    _sha256,
    load_overlay,
    simulate,
    simulate_rule,
    sjf,
)

REPS = (0, 1, 2, 3, 4)
LEVELS = (0, 1, 2)
PROMISES_S = (300, 600, 1200)
LIMIT_US = 60 * MICROS


def theta_us(promise_s: int, k: int) -> int:
    """G - (3 - 2/k)L in integer microseconds, rounded down so the promise is kept."""
    return (promise_s * MICROS * k - (3 * k - 2) * LIMIT_US) // k


def main() -> None:
    t0 = time.time()
    rows = []
    for rep in REPS:
        path = ROOT / "data" / "derived" / "overlay_traces" / f"primary_rep{rep}.npz"
        for level in LEVELS:
            trace, k, labels = load_overlay(path, level)
            a = np.ascontiguousarray(trace.arrival_us)
            svc = np.ascontiguousarray(trace.service_us)
            score = np.ascontiguousarray(trace.score_for(SCORE_KEY))
            zeros = np.zeros(len(a), np.int64)
            in_window = labels["in_window"]
            fcfs_start, _ = simulate_rule(a, svc, score, zeros, k, 0)
            fcfs_us = fcfs_start - a
            sjf_us = simulate(trace, sjf(), k).wait_us
            fcfs_p99 = float(np.quantile(fcfs_us[in_window] / MICROS, 0.99))
            sjf_p99 = float(np.quantile(sjf_us[in_window] / MICROS, 0.99))
            for g in PROMISES_S:
                th = theta_us(g, k)
                st, ntimer = simulate_rule(a, svc, score, zeros, k, th)
                wait = st - a
                m = _metrics(wait, fcfs_us, in_window, fcfs_p99, sjf_p99)
                excess_us = wait - fcfs_us
                rows.append({
                    "rep": rep, "level": level, "k": k, "promise_s": g,
                    "theta_s": th / MICROS, "timer_share": ntimer / len(a),
                    "p99_dl_s": m["p99_dl_s"], "mean_s": m["mean_s"],
                    "max_excess_s": m["max_excess_s"], "harm_s": m["harm_s"],
                    "gap_closed": m["gap_closed"],
                    "jobs_excess_ge_promise": int((excess_us >= g * MICROS).sum()),
                    "max_excess_over_promise": m["max_excess_s"] / g,
                })
                print(f"rep{rep} level{level} k={k} G={g} theta={th / MICROS:.3f}s "
                      f"gap={m['gap_closed']:.4f} max_exc={m['max_excess_s']:.1f}", flush=True)
            del trace, labels, a, svc, score, fcfs_us, sjf_us

    cells_csv = HERE / "maxwait_equal_promise_cells.csv"
    with open(cells_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    guard = {}
    with open(ROOT / "outputs" / "dev_tables" / "main_table.csv", newline="") as f:
        for r in csv.DictReader(f):
            guard[(int(r["level"]), r["policy"])] = r
    agg = []
    for level in LEVELS:
        for g in PROMISES_S:
            cells = [r for r in rows if r["level"] == level and r["promise_s"] == g]
            gr = guard[(level, f"Guard({g})")]
            agg.append({
                "level": level, "promise_s": g,
                "theta_s_by_k": ";".join(sorted({f"k{c['k']}:{c['theta_s']:.3f}" for c in cells})),
                "maxwait_p99_dl_s": float(np.mean([c["p99_dl_s"] for c in cells])),
                "maxwait_gap_closed": float(np.mean([c["gap_closed"] for c in cells])),
                "maxwait_gap_min_overlay": float(np.min([c["gap_closed"] for c in cells])),
                "maxwait_max_excess_s": float(np.max([c["max_excess_s"] for c in cells])),
                "maxwait_harm_s": float(np.max([c["harm_s"] for c in cells])),
                "maxwait_jobs_excess_ge_promise": int(sum(c["jobs_excess_ge_promise"] for c in cells)),
                "guard_p99_dl_s": float(gr["p99_dl_s"]),
                "guard_gap_closed": float(gr["gap_closed"]),
                "guard_max_excess_s": float(gr["max_excess_s"]),
                "guard_harm_s": float(gr["harm_s"]),
            })
    agg_csv = HERE / "maxwait_equal_promise_vs_guard.csv"
    with open(agg_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(agg[0]))
        w.writeheader()
        w.writerows(agg)

    manifest = {
        "script": str(Path(__file__).relative_to(ROOT)),
        "script_sha256": _sha256(Path(__file__)),
        "kernel_script_sha256": _sha256(HERE / "maxwait_baseline.py"),
        "inputs": {f"primary_rep{r}.npz": _sha256(ROOT / "data" / "derived" / "overlay_traces" / f"primary_rep{r}.npz") for r in REPS},
        "guard_rows_sha256": _sha256(ROOT / "outputs" / "dev_tables" / "main_table.csv"),
        "outputs": {p.name: _sha256(p) for p in (cells_csv, agg_csv)},
        "limit_s": LIMIT_US / MICROS,
        "score": SCORE_KEY,
        "elapsed_s": round(time.time() - t0, 1),
    }
    (HERE / "maxwait_equal_promise_manifest.json").write_text(json.dumps(manifest, indent=2))
    for r in agg:
        print(r)


if __name__ == "__main__":
    main()
