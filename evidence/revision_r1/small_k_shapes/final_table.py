"""The small-k shape table and the no-grid guidance, from the cell files of run_cells.py.

    python final_table.py [--allow-partial]

Reads outputs/revision_r1/small_k_shapes/cells/k<k>[L<n>]u<load>_rep<rep>_l0.csv (with the
_bounds.csv and _replicates.npz of each cell).  A series is k1, k1L16, k2 or k3: k1 is the
published k = 1 trace family (8 listings), k1L16 the k = 1 traces built like k = 2, 3 (16
listings, REPORT.md 6).  It writes, in the same output directory:

  shape_table.csv   per (series, load, policy): means over overlays of the waits and the gap
                    closed, worst over overlays of harm and of the excess over FCFS
  bound_summary.csv per (series, policy): jobs checked, violations, largest used/allowed
  guidance.csv      per (series, G, load): the best shape, the shortfall of Guard-default(G),
                    Guard-fixed(G) and Fixed(G) against it with paired week-block intervals,
                    their worst harm, and the pre-registered adequacy test (REPORT.md 1)
  guidance.txt      the same per (series, G), as the lines the report quotes
  trend.csv         per (G, load, candidate): the shortfall at k = 1, 2, 3 on the series
                    built the same way (k1L16, k2, k3), with k1 beside it for reference

Without --allow-partial a missing cell of the 60 is an error.
"""

import common

import argparse
import csv
import re
from collections import defaultdict

import numpy as np
from spjf_guard.experiment import bootstrap as bs

PROMISES = (300, 600, 1200)
SHAPES = ("Guard-fixed", "Guard-age", "Guard-queue")
CANDIDATES = ("Guard-default", "Guard-fixed", "Fixed")
SHORTFALL_LIMIT = 0.05
HARM_FRACTION = 0.5
MEAN = ("p99_dl_s", "mean_s", "p99_all_s", "gap_closed", "rho_realised", "fired_pct")
WORST = ("harm_s", "max_excess_s", "max_heavy_s")
NAME = re.compile(r"^k(\d)(L\d+)?u(\d\d)_rep(\d)_l0\.csv$")
SERIES = ("k1", "k1L16", "k2", "k3")
TREND = ("k1L16", "k2", "k3")


def read_cells(cells_dir):
    cells = []
    for path in sorted(cells_dir.glob("k*_l0.csv")):
        match = NAME.search(path.name)
        if not match:
            continue
        k, load, rep = int(match[1]), int(match[3]) / 100, int(match[4])
        series = f"k{k}{match[2] or ''}"
        with open(path, encoding="utf-8", newline="") as fh:
            rows = {r["policy"]: r for r in csv.DictReader(fh)}
        with open(path.with_name(path.stem + "_bounds.csv"), encoding="utf-8", newline="") as fh:
            bounds = list(csv.DictReader(fh))
        with np.load(path.with_name(path.stem + "_replicates.npz")) as z:
            p99 = {key.split("|")[0]: z[key] for key in z.files if key.endswith("|p99_dl")}
        cells.append({"series": series, "k": k, "load": load, "rep": rep, "rows": rows, "bounds": bounds,
                      "p99": p99})
    return cells


def gap_replicates(cell, policy):
    p99 = cell["p99"]
    return (p99["FCFS"] - p99[policy]) / (p99["FCFS"] - p99["SJF"])


def shape_table(groups):
    out = []
    for (series, load), cells in sorted(groups.items()):
        for policy in cells[0]["rows"]:
            rows = [c["rows"][policy] for c in cells]
            out.append({
                "series": series, "k": cells[0]["k"], "load": load, "policy": policy, "n_overlays": len(rows),
                **{f: float(np.mean([float(r[f]) for r in rows])) for f in MEAN},
                **{f: float(np.max([float(r[f]) for r in rows])) for f in WORST},
            })
    return out


def guidance_rows(groups, table):
    index = {(r["series"], r["load"], r["policy"]): r for r in table}
    out = []
    for (k, load), cells in sorted(groups.items()):  # k here is the series name
        for promise in PROMISES:
            best = max(SHAPES, key=lambda s: index[(k, load, f"{s}({promise})")]["gap_closed"])
            best_name = f"{best}({promise})"
            best_reps = np.mean([gap_replicates(c, best_name) for c in cells], axis=0)
            row = {"series": k, "k": cells[0]["k"], "load": load, "G": promise, "best_shape": best_name,
                   "best_gap": index[(k, load, best_name)]["gap_closed"],
                   "best_harm_s": index[(k, load, best_name)]["harm_s"],
                   "harm_limit_s": HARM_FRACTION * promise}
            for candidate in CANDIDATES:
                name = f"{candidate}({promise})"
                diff = best_reps - np.mean([gap_replicates(c, name) for c in cells], axis=0)
                low, high = bs.interval(diff)
                shortfall = index[(k, load, best_name)]["gap_closed"] - index[(k, load, name)][
                    "gap_closed"]
                harm = index[(k, load, name)]["harm_s"]
                row.update({
                    f"{candidate}_gap": index[(k, load, name)]["gap_closed"],
                    f"{candidate}_shortfall": shortfall,
                    f"{candidate}_shortfall_lo": low,
                    f"{candidate}_shortfall_hi": high,
                    f"{candidate}_harm_s": harm,
                    f"{candidate}_adequate": bool(
                        shortfall <= SHORTFALL_LIMIT and harm <= HARM_FRACTION * promise),
                })
            out.append(row)
    return out


def summary_lines(rows):
    lines = [f"adequate = shortfall <= {SHORTFALL_LIMIT} of the gap and worst harm <= G/2 "
             "(pre-registered, REPORT.md 1)"]
    by = defaultdict(list)
    for r in rows:
        by[(r["series"], r["G"])].append(r)
    for (k, promise), block in sorted(by.items()):
        parts = []
        for candidate in CANDIDATES:
            short = [r[f"{candidate}_shortfall"] for r in block]
            parts.append(
                f"{candidate}: adequate {sum(r[f'{candidate}_adequate'] for r in block)}/"
                f"{len(block)}, shortfall max {max(short):.3f} median {np.median(short):.3f}")
        lines.append(f"{k}, G = {promise}: " + "; ".join(parts))
    return lines


def trend_rows(rows):
    """Shortfall against the best shape at k = 1, 2, 3, on traces built the same way."""
    at = {(r["series"], r["G"], r["load"]): r for r in rows}
    out = []
    for promise in PROMISES:
        for load in sorted({r["load"] for r in rows}):
            for candidate in CANDIDATES:
                row = {"G": promise, "load": load, "candidate": candidate}
                for series in SERIES:
                    hit = at.get((series, promise, load))
                    row[f"{series}_shortfall"] = hit[f"{candidate}_shortfall"] if hit else ""
                    row[f"{series}_best"] = hit["best_shape"] if hit else ""
                out.append(row)
    return out


def trend_lines(trend):
    lines = ["across k (k1L16 -> k2 -> k3, same construction; k1 = published traces):"]
    for r in trend:
        if r["candidate"] != "Guard-default":
            continue
        values = " -> ".join(
            f"{r[f'{s}_shortfall']:.3f}" if r[f"{s}_shortfall"] != "" else "n/a" for s in TREND)
        k1 = r["k1_shortfall"]
        lines.append(f"  Guard-default shortfall, G = {r['G']}, load {r['load']}: {values} "
                     f"(k1 {k1:.3f})" if k1 != "" else
                     f"  Guard-default shortfall, G = {r['G']}, load {r['load']}: {values}")
    return lines


def write(rows, path):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--allow-partial", action="store_true")
    args = ap.parse_args()
    cells = read_cells(common.OUT / "cells")
    groups = defaultdict(list)
    for cell in cells:
        groups[(cell["series"], cell["load"])].append(cell)
    expected = len(SERIES) * len(common.LOADS) * len(common.REPS)
    print(f"{len(cells)} of {expected} cells on disk")
    if len(cells) != expected and not args.allow_partial:
        raise SystemExit("cells are missing; rerun the chain or pass --allow-partial")
    table = shape_table(groups)
    write(table, common.OUT / "shape_table.csv")
    bounds = defaultdict(lambda: {"jobs_checked": 0, "violations": 0, "used_over_allowed": 0.0})
    for cell in cells:
        for b in cell["bounds"]:
            entry = bounds[(cell["series"], b["policy"])]
            entry["jobs_checked"] += int(b["jobs_checked"])
            entry["violations"] += int(b["violations"])
            entry["used_over_allowed"] = max(entry["used_over_allowed"],
                                             float(b["used_over_allowed"]))
    write([{"series": k, "policy": p, **v} for (k, p), v in sorted(bounds.items())],
          common.OUT / "bound_summary.csv")
    total = sum(v["violations"] for v in bounds.values())
    checked = sum(v["jobs_checked"] for v in bounds.values())
    rows = guidance_rows(groups, table)
    write(rows, common.OUT / "guidance.csv")
    trend = trend_rows(rows)
    write(trend, common.OUT / "trend.csv")
    lines = ([f"bound violations {total} over {checked:,} job-checks"] + summary_lines(rows)
             + trend_lines(trend))
    (common.OUT / "guidance.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
