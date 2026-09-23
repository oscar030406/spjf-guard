"""Open versus closed side by side, plus a week-block bootstrap on one overlay.

    uv run --no-sync python evidence/closed_loop/make_tables.py [--bootstrap 400]

Reads out/closed_cells.csv (written by run_closed_loop.py) and writes
out/open_vs_closed.csv.  With --bootstrap > 0 it re-runs overlay 0 at the three load
levels, keeping late submissions, and resamples whole weeks with replacement -- the
paper's paired week-block scheme, at a smaller number of resamples -- to put an interval
on the deadline-window p99 and on the gap closed.  The weeks are the recorded weeks of
the jobs, and every policy sees the same resample, so the differences are paired.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
OUT = HERE / "out"

POLICIES = ("FCFS", "SJF", "SPJF-E", "Guard(600)")
FLOAT_FIELDS = (
    "p99_dl_s",
    "p99_dl_realised_window_s",
    "mean_s",
    "max_s",
    "p99_all_s",
    "max_heavy_s",
    "max_excess_s",
    "harm_s",
    "fired_fraction_queue_weighted",
    "fired_pct",
    "offered_work_s",
    "drift_mean_s",
    "drift_p50_s",
    "drift_p99_s",
    "drift_max_s",
    "share_arriving_past_deadline",
    "dl_arrivals_per_hour_mean",
    "dl_arrivals_per_hour_p99",
    "dl_arrivals_per_hour_max",
    "busy_hour_work_s",
    "rho_busy_hour",
    "span_days",
    "worst_ratio_to_bound",
    "max_fcfs_own_s",
)


def read_cells() -> list[dict]:
    with (OUT / "closed_cells.csv").open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for row in rows:
        for key in FLOAT_FIELDS:
            row[key] = float(row[key]) if row.get(key) not in (None, "") else float("nan")
        for key in ("overlay", "level", "k", "n_jobs", "n_dropped"):
            row[key] = int(row[key])
        row["bound_violations"] = (
            int(row["bound_violations"]) if row["bound_violations"] != "" else None
        )
    return rows


def gap(value: float, reference: float, target: float) -> float:
    den = reference - target
    return float("nan") if den == 0 else (reference - value) / den


def build_table(rows: list[dict]) -> list[dict]:
    index = {(r["overlay"], r["level"], r["mode"], r["late_submissions"], r["policy"]): r
             for r in rows}
    out = []
    for (ov, lv, mode, late, pol), row in index.items():
        ref = index.get((ov, lv, mode, late, "FCFS"))
        tgt = index.get((ov, lv, mode, late, "SJF"))
        row = dict(row)
        row["gap_closed"] = (
            gap(row["p99_dl_s"], ref["p99_dl_s"], tgt["p99_dl_s"]) if ref and tgt else float("nan")
        )
        row["reduction_pct"] = (
            100.0 * (ref["p99_dl_s"] - row["p99_dl_s"]) / ref["p99_dl_s"] if ref else float("nan")
        )
        out.append(row)
    out.sort(key=lambda r: (r["level"], r["late_submissions"], r["mode"], r["policy"], r["overlay"]))
    return out


def averaged(table: list[dict]) -> list[dict]:
    """Mean over overlays of the mean-fields, worst over overlays of the worst-fields."""
    mean_fields = (
        "p99_dl_s",
        "p99_dl_realised_window_s",
        "mean_s",
        "gap_closed",
        "reduction_pct",
        "fired_pct",
        "fired_fraction_queue_weighted",
        "drift_mean_s",
        "drift_p50_s",
        "drift_p99_s",
        "share_arriving_past_deadline",
        "dl_arrivals_per_hour_mean",
        "dl_arrivals_per_hour_p99",
        "rho_busy_hour",
        "span_days",
        "offered_work_s",
    )
    worst_fields = ("max_s", "max_excess_s", "harm_s", "max_heavy_s", "worst_ratio_to_bound",
                    "drift_max_s")
    groups = defaultdict(list)
    for row in table:
        groups[(row["level"], row["late_submissions"], row["mode"], row["policy"])].append(row)
    out = []
    for (lv, late, mode, pol), block in sorted(groups.items()):
        row = {
            "level": lv,
            "k": block[0]["k"],
            "late_submissions": late,
            "mode": mode,
            "policy": pol,
            "n_overlays": len(block),
            "n_jobs": int(np.mean([b["n_jobs"] for b in block])),
            "n_dropped": int(np.mean([b["n_dropped"] for b in block])),
            "bound_violations": sum(
                b["bound_violations"] for b in block if b["bound_violations"] is not None
            )
            if any(b["bound_violations"] is not None for b in block)
            else "",
        }
        for field in mean_fields:
            row[field] = float(np.nanmean([b[field] for b in block]))
        for field in worst_fields:
            values = [b[field] for b in block]
            row[field] = float(np.nanmax(values)) if not all(np.isnan(values)) else float("nan")
        out.append(row)
    return out


def markdown(mean_table: list[dict]) -> str:
    """The tables REPORT.md quotes, regenerated from out/closed_cells.csv."""
    index = {(r["level"], r["mode"], r["late_submissions"], r["policy"]): r for r in mean_table}
    lines = [
        "<!-- generated by make_tables.py from out/closed_cells.csv; do not edit -->",
        "",
        "## A. Open versus closed, deadline-window p99 (mean over overlays 0-2)",
        "",
        "| load | k | policy | open p99 (s) | closed p99, late kept (s) | closed p99, late dropped (s) "
        "| gap open | gap closed | fired open (%) | fired closed (%) |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for level in (0, 1, 2):
        for pol in POLICIES:
            o = index.get((level, "open", "kept", pol))
            c = index.get((level, "closed", "kept", pol))
            d = index.get((level, "closed", "dropped", pol))
            if not (o and c and d):
                continue
            lines.append(
                f"| {level} | {o['k']} | {pol} | {o['p99_dl_s']:.3f} | {c['p99_dl_s']:.3f} | "
                f"{d['p99_dl_s']:.3f} | {o['gap_closed']:.3f} | {c['gap_closed']:.3f} | "
                + (
                    f"{100 * o['fired_fraction_queue_weighted']:.4f} | "
                    f"{100 * c['fired_fraction_queue_weighted']:.4f} |"
                    if pol.startswith("Guard")
                    else "- | - |"
                )
            )
    lines += [
        "",
        "## B. What gating does to the stream (late submissions kept)",
        "",
        "| load | policy | busy-hour rho open | busy-hour rho closed | mean drift (s) | p99 drift (s) "
        "| max drift (s) | share arriving past own deadline, open | closed | dropped if refused | "
        "offered work lost if refused (%) |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for level in (0, 1, 2):
        for pol in POLICIES:
            o = index.get((level, "open", "kept", pol))
            c = index.get((level, "closed", "kept", pol))
            d = index.get((level, "closed", "dropped", pol))
            if not (o and c and d):
                continue
            lost = 100.0 * (o["offered_work_s"] - d["offered_work_s"]) / o["offered_work_s"]
            lines.append(
                f"| {level} | {pol} | {o['rho_busy_hour']:.4f} | {c['rho_busy_hour']:.4f} | "
                f"{c['drift_mean_s']:.1f} | {c['drift_p99_s']:.1f} | {c['drift_max_s']:.1f} | "
                f"{100 * o['share_arriving_past_deadline']:.3f}% | "
                f"{100 * c['share_arriving_past_deadline']:.3f}% | {d['n_dropped']} | {lost:.2f} |"
            )
    lines += [
        "",
        "## C. Harm, excess and the per-job guarantee (late submissions kept)",
        "",
        "the reference is FCFS run open-loop on the policy's own realised arrival sequence",
        "",
        "| load | policy | mode | mean (s) | max (s) | max heavy (s) | max excess (s) | harm (s) "
        "| worst W / bound | bound violations |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for level in (0, 1, 2):
        for pol in POLICIES:
            for mode in ("open", "closed"):
                r = index.get((level, mode, "kept", pol))
                if not r:
                    continue
                ratio = (
                    f"{r['worst_ratio_to_bound']:.4f}"
                    if not np.isnan(r["worst_ratio_to_bound"])
                    else "-"
                )
                lines.append(
                    f"| {level} | {pol} | {mode} | {r['mean_s']:.4f} | {r['max_s']:.1f} | "
                    f"{r['max_heavy_s']:.1f} | {r['max_excess_s']:.1f} | {r['harm_s']:.1f} | "
                    f"{ratio} | {r['bound_violations']} |"
                )
    return "\n".join(lines) + "\n"


def bootstrap(n_resamples: int, overlay: int, levels, seed: int = 20260923) -> dict:
    from run_closed_loop import MICROS, load_cell, policy_for, run_kernel

    report = {}
    for level in levels:
        cell = load_cell(overlay, level)
        dl = cell["dl"]
        week = cell["wk"][dl]
        order = np.argsort(week, kind="stable")
        week_sorted = week[order]
        edges = np.searchsorted(week_sorted, np.arange(week_sorted.max() + 2))
        blocks = [order[edges[w] : edges[w + 1]] for w in range(len(edges) - 1)]
        blocks = [b for b in blocks if b.size]
        waits = {}
        for mode_name, closed in (("open", 0), ("closed", 1)):
            for name in POLICIES:
                out = run_kernel(cell, policy_for(name, cell["k"]), closed=closed, drop=0)
                waits[(mode_name, name)] = (out[0][dl] / MICROS).astype(np.float32)
                del out
        rng = np.random.default_rng(seed + level)
        draws = {key: [] for key in waits}
        gaps = {(m, p): [] for m in ("open", "closed") for p in ("SPJF-E", "Guard(600)")}
        t0 = time.time()
        for _ in range(n_resamples):
            pick = rng.integers(0, len(blocks), len(blocks))
            idx = np.concatenate([blocks[i] for i in pick])
            per = {}
            for key, array in waits.items():
                value = float(np.quantile(array[idx], 0.99))
                per[key] = value
                draws[key].append(value)
            for mode_name in ("open", "closed"):
                for pol in ("SPJF-E", "Guard(600)"):
                    gaps[(mode_name, pol)].append(
                        gap(
                            per[(mode_name, pol)],
                            per[(mode_name, "FCFS")],
                            per[(mode_name, "SJF")],
                        )
                    )
        block = {"seconds": round(time.time() - t0, 1), "n_resamples": n_resamples,
                 "n_weeks": len(blocks), "k": cell["k"]}
        for (mode_name, pol), values in draws.items():
            values = np.asarray(values)
            block[f"p99_dl_{mode_name}_{pol}"] = [
                float(np.quantile(values, 0.025)),
                float(np.quantile(values, 0.975)),
            ]
        for (mode_name, pol), values in gaps.items():
            values = np.asarray(values)
            block[f"gap_{mode_name}_{pol}"] = [
                float(np.quantile(values, 0.025)),
                float(np.quantile(values, 0.975)),
            ]
        # the paired closed-minus-open difference in gap closed
        for pol in ("SPJF-E", "Guard(600)"):
            d = np.asarray(gaps[("closed", pol)]) - np.asarray(gaps[("open", pol)])
            block[f"gap_closed_minus_open_{pol}"] = [
                float(d.mean()),
                float(np.quantile(d, 0.025)),
                float(np.quantile(d, 0.975)),
            ]
        report[f"level{level}"] = block
        print(f"level {level}: {block['seconds']} s", flush=True)
        del cell, waits
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bootstrap", type=int, default=0)
    ap.add_argument("--overlay", type=int, default=0)
    args = ap.parse_args()
    rows = read_cells()
    table = build_table(rows)
    with (OUT / "open_vs_closed.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(table[0]))
        writer.writeheader()
        writer.writerows(table)
    mean_table = averaged(table)
    with (OUT / "open_vs_closed_mean.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(mean_table[0]))
        writer.writeheader()
        writer.writerows(mean_table)
    (OUT / "report_tables.md").write_text(markdown(mean_table), encoding="utf-8")
    print(f"{len(table)} cell rows, {len(mean_table)} averaged rows")
    if args.bootstrap > 0:
        report = bootstrap(args.bootstrap, args.overlay, (0, 1, 2))
        (OUT / "bootstrap.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
