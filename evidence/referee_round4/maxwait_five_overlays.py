"""Referee round 4: MaxWait(T) at the three promises on all five development overlays.

Same rule and kernel as maxwait_baseline.py (imported from it), aggregated the way the
manuscript's guard table aggregates: p99 and gap closed are means over the five
overlays, maximum excess and harm are the worst over them.  The package guard rows of
outputs/dev_tables/main_table.csv are read beside them, not recomputed.  Each cell
repeats the tool check (the kernel as FCFS and as SPJF-E against the package waits).

Run from the repository root:
  env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME NUMBA_NUM_THREADS=4 \
      OMP_NUM_THREADS=4 uv run --no-sync python evidence/referee_round4/maxwait_five_overlays.py
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
    NEVER,
    ROOT,
    SCORE_KEY,
    _metrics,
    _sha256,
    fcfs,
    load_overlay,
    simulate,
    simulate_rule,
    sjf,
    spjf,
)

REPS = (0, 1, 2, 3, 4)
LEVELS = (0, 1, 2)
PROMISES_S = (300, 600, 1200)
MAIN_TABLE = ROOT / "outputs" / "dev_tables" / "main_table.csv"


def _cells() -> tuple[list[dict], list[dict]]:
    rows, checks = [], []
    for rep in REPS:
        path = ROOT / "data" / "derived" / "overlay_traces" / f"primary_rep{rep}.npz"
        for level in LEVELS:
            trace, k, labels = load_overlay(path, level)
            a = np.ascontiguousarray(trace.arrival_us)
            svc = np.ascontiguousarray(trace.service_us)
            score = np.ascontiguousarray(trace.score_for(SCORE_KEY))
            zeros = np.zeros(len(a), np.int64)
            in_window = labels["in_window"]
            ref = {p.name: simulate(trace, p, k).wait_us for p in (fcfs(), sjf(), spjf(SCORE_KEY, "SPJF-E"))}
            fcfs_us = ref["FCFS"]
            fcfs_p99 = float(np.quantile(fcfs_us[in_window] / MICROS, 0.99))
            sjf_p99 = float(np.quantile(ref["SJF"][in_window] / MICROS, 0.99))
            mine_fcfs, _ = simulate_rule(a, svc, score, zeros, k, 0)
            mine_spjf, _ = simulate_rule(a, svc, score, zeros, k, NEVER)
            d_f = int(((mine_fcfs - a) != fcfs_us).sum())
            d_s = int(((mine_spjf - a) != ref["SPJF-E"]).sum())
            checks.append({"rep": rep, "level": level, "k": k, "fcfs_differing": d_f, "spjf_differing": d_s})
            if d_f or d_s:
                raise SystemExit(f"rep{rep} level{level}: kernel disagrees with the package")
            rows.append({"rep": rep, "level": level, "k": k, "policy": "SPJF-E",
                         **_metrics(ref["SPJF-E"], fcfs_us, in_window, fcfs_p99, sjf_p99)})
            for g in PROMISES_S:
                st, _ = simulate_rule(a, svc, score, zeros, k, g * MICROS)
                rows.append({"rep": rep, "level": level, "k": k, "policy": f"MaxWait({g})",
                             **_metrics(st - a, fcfs_us, in_window, fcfs_p99, sjf_p99)})
            print(f"rep{rep} level{level} k={k} done", flush=True)
            del trace, labels, ref, a, svc, score
    return rows, checks


def _aggregate(rows: list[dict]) -> list[dict]:
    guard = {}
    with open(MAIN_TABLE, newline="") as f:
        for r in csv.DictReader(f):
            guard[(int(r["level"]), r["policy"])] = r
    out = []
    for level in LEVELS:
        for g in PROMISES_S:
            cells = [r for r in rows if r["level"] == level and r["policy"] == f"MaxWait({g})"]
            gr = guard[(level, f"Guard({g})")]
            out.append({
                "level": level,
                "promise_s": g,
                "maxwait_p99_dl_s": float(np.mean([c["p99_dl_s"] for c in cells])),
                "maxwait_gap_closed": float(np.mean([c["gap_closed"] for c in cells])),
                "maxwait_gap_min_overlay": float(np.min([c["gap_closed"] for c in cells])),
                "maxwait_max_excess_s": float(np.max([c["max_excess_s"] for c in cells])),
                "maxwait_harm_s": float(np.max([c["harm_s"] for c in cells])),
                "maxwait_jobs_over_G": int(sum(c["jobs_over_600s_excess"] for c in cells)) if g == 600 else -1,
                "guard_p99_dl_s": float(gr["p99_dl_s"]),
                "guard_gap_closed": float(gr["gap_closed"]),
                "guard_max_excess_s": float(gr["max_excess_s"]),
                "guard_harm_s": float(gr["harm_s"]),
            })
    return out


def main() -> None:
    t0 = time.time()
    rows, checks = _cells()
    cells_csv = HERE / "maxwait_five_cells.csv"
    with open(cells_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    agg = _aggregate(rows)
    agg_csv = HERE / "maxwait_five_vs_guard.csv"
    with open(agg_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(agg[0]))
        w.writeheader()
        w.writerows(agg)
    manifest = {
        "script": str(Path(__file__).relative_to(ROOT)),
        "script_sha256": _sha256(Path(__file__)),
        "kernel_script_sha256": _sha256(HERE / "maxwait_baseline.py"),
        "inputs": {f"primary_rep{r}.npz": _sha256(ROOT / "data" / "derived" / "overlay_traces" / f"primary_rep{r}.npz") for r in REPS},
        "guard_rows_from": str(MAIN_TABLE.relative_to(ROOT)),
        "guard_rows_sha256": _sha256(MAIN_TABLE),
        "outputs": {p.name: _sha256(p) for p in (cells_csv, agg_csv)},
        "tool_checks": checks,
        "elapsed_s": round(time.time() - t0, 1),
    }
    (HERE / "maxwait_five_manifest.json").write_text(json.dumps(manifest, indent=2))
    for r in agg:
        print(r)


if __name__ == "__main__":
    main()
