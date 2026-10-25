"""Collect the backfilling cells and put them next to the guard and Timeout rows.

    python evidence/revision_r1/backfill_baselines/make_table.py [--cells DIR]

Writes to outputs/revision_r1/backfill_baselines/:
  backfill_cells.csv   one row per (overlay, level, policy), main_cells.csv columns + extras
  backfill_table.csv   per (level, policy): mean over overlays of waits and gap closed,
                       worst over overlays of max excess, harm and jobs with excess > G
                       (the aggregation of scripts/run_main.py), wall time summed
  backfill_table.md    the same with FCFS, SJF, SPJF-E (main_cells.csv) and Guard(G),
                       Timeout(G) (dev_online_visibility/online_cells.csv, variant
                       original) aggregated the same way, for the cells present
"""
import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "outputs" / "revision_r1" / "backfill_baselines"
MAIN_CELLS = ROOT / "outputs" / "dev_tables" / "main_cells.csv"
ONLINE_CELLS = ROOT / "outputs" / "dev_online_visibility" / "online_cells.csv"
BASE = ["overlay", "level", "k", "rho_target", "rho_realised", "policy", "servers", "n_jobs",
        "p99_dl_s", "mean_s", "p99_all_s", "max_excess_s", "harm_s", "max_heavy_s",
        "fired_fraction_queue_weighted", "fired_pct", "gap_closed", "reduction_pct"]
EXTRA = ["estimate", "slack_G_s", "n_excess_gt_300", "n_excess_gt_600", "n_excess_gt_1200",
         "promise_violations", "n_start_differs_from_fcfs", "wall_s", "peak_commit_gb"]
MEAN = ("p99_dl_s", "mean_s", "gap_closed", "reduction_pct")
WORST = ("max_excess_s", "harm_s", "n_excess_gt_300", "n_excess_gt_600", "n_excess_gt_1200",
         "promise_violations")
POLICY_ORDER = ["FCFS", "SJF", "SPJF-E", "Guard(300)", "Timeout(300)", "Slack-L(300)",
                "Slack-P(300)", "Guard(600)", "Timeout(600)", "Slack-L(600)", "Slack-P(600)",
                "Guard(1200)", "Timeout(1200)", "Slack-L(1200)", "Slack-P(1200)", "CBF-L",
                "CBF-P"]


def read_csv(path, keep):
    with path.open(newline="") as f:
        return [r for r in csv.DictReader(f) if keep(r)]


def as_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return math.nan


def aggregate(rows):
    out = []
    for level in sorted({int(r["level"]) for r in rows}):
        block = [r for r in rows if int(r["level"]) == level]
        for policy in dict.fromkeys(r["policy"] for r in block):
            cells = [r for r in block if r["policy"] == policy]
            row = {"level": level, "policy": policy, "n_overlays": len(cells),
                   "k": cells[0]["k"]}
            for f in MEAN:
                row[f] = float(np.mean([as_float(c[f]) for c in cells]))
            for f in WORST:
                vals = [as_float(c.get(f)) for c in cells]
                row[f] = float(np.max(vals)) if not all(math.isnan(v) for v in vals) else math.nan
            row["wall_s"] = float(np.sum([as_float(c.get("wall_s")) for c in cells]))
            out.append(row)
    return out


def fmt(v, digits=3):
    if isinstance(v, float):
        if math.isnan(v):
            return "-"
        if v == int(v):
            return str(int(v))
        return f"{v:.{digits}f}"
    return str(v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cells", type=Path, default=OUT / "cells")
    args = ap.parse_args()
    rows = [json.loads(p.read_text()) for p in sorted(args.cells.glob("o*_l*_*.json"))]
    rows = [r for r in rows if not r.get("prefix")]
    if not rows:
        raise SystemExit(f"no cells in {args.cells}")
    present = {(int(r["overlay"]), int(r["level"])) for r in rows}
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "backfill_cells.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, BASE + EXTRA, extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["overlay"], r["level"], r["policy"])))
    table = aggregate(rows)
    cols = ["level", "policy", "n_overlays", "k"] + list(MEAN) + list(WORST) + ["wall_s"]
    with (OUT / "backfill_table.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, cols)
        w.writeheader()
        w.writerows(table)

    def in_present(r):
        return (int(r["overlay"]), int(r["level"])) in present

    ref = read_csv(MAIN_CELLS, lambda r: in_present(r) and r["policy"] in ("FCFS", "SJF", "SPJF-E"))
    online = read_csv(ONLINE_CELLS, lambda r: in_present(r) and r["variant"] == "original"
                      and r["base_policy"].startswith(("Guard(", "Timeout(")))
    for r in online:
        r["policy"] = r["base_policy"]
    combined = aggregate(ref + online + rows)
    combined.sort(key=lambda r: (r["level"], POLICY_ORDER.index(r["policy"])
                                 if r["policy"] in POLICY_ORDER else 99))
    head = ["level", "policy", "overlays", "p99 wait (s)", "gap closed", "harm (s)",
            "max excess (s)", "jobs excess > 300/600/1200 s (worst)", "wall (s, sum)"]
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for r in combined:
        n_ex = "/".join(fmt(r[f"n_excess_gt_{g}"]) for g in (300, 600, 1200))
        lines.append("| " + " | ".join([
            str(r["level"]), r["policy"], str(r["n_overlays"]), fmt(r["p99_dl_s"]),
            fmt(r["gap_closed"], 4), fmt(r["harm_s"], 1), fmt(r["max_excess_s"], 1), n_ex,
            fmt(r["wall_s"], 0) if r["wall_s"] > 0 else "-"]) + " |")
    note = ("FCFS, SJF, SPJF-E from outputs/dev_tables/main_cells.csv; Guard(G), Timeout(G) "
            "from outputs/dev_online_visibility/online_cells.csv (variant original); "
            "backfilling from this directory.  Mean over overlays of p99 and gap closed, "
            "worst over overlays of harm, max excess and job counts.  Cells: "
            + ", ".join(f"o{o}l{lv}" for o, lv in sorted(present)) + ".")
    (OUT / "backfill_table.md").write_text("\n".join(lines) + "\n\n" + note + "\n")
    print("\n".join(lines))
    print(note)


if __name__ == "__main__":
    main()
