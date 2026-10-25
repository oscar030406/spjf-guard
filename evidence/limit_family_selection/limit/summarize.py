"""Tabulate the L sensitivity against L = 60 s (outputs/dev_online_visibility).

    python evidence/limit_family_selection/limit/summarize.py outputs/limit_sensitivity_<tag>

Reads every jobs/*/online_cells.csv.  Per (L, clock, policy, level): the mean and the minimum
gap_closed over the overlays present, the largest harm_s and the largest max_excess_s, and
the same numbers at L = 60 s on the same cells.  A policy run_limit.py found without a budget
at that L (it is FCFS) gets the row 'FCFS' with gap 0, harm 0 and excess 0 by definition.
Writes limit_summary.csv beside this script.
"""

import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parents[2]
from make_jobs import POLICIES  # noqa: E402
from run_limit import admissible  # noqa: E402

DEV = ROOT / "outputs" / "dev_online_visibility" / "online_cells.csv"
NAME = re.compile(r"(Guard|Fixed|Skip)\(([0-9]+)\)")


def read(path):
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def stats(rows):
    gaps = [float(r["gap_closed"]) for r in rows]
    return {"cells": len(rows), "gap_mean": sum(gaps) / len(gaps), "gap_min": min(gaps),
            "harm_max": max(float(r["harm_s"]) for r in rows),
            "excess_max": max(float(r["max_excess_s"]) for r in rows)}


run = Path(sys.argv[1])
by_limit = defaultdict(list)
for path in sorted(run.glob("jobs/*/online_cells.csv")):
    by_limit[int(path.parent.name.split("_")[1][1:])] += read(path)
dev = defaultdict(list)
for r in read(DEV):
    dev[(r["policy"], r["level"])].append(r)
levels_k = defaultdict(set)
for r in read(DEV):
    levels_k[r["level"]].add(int(r["k"]))

out = []
for limit, policies in POLICIES.items():
    rows = defaultdict(list)
    for r in by_limit[limit]:
        rows[(r["policy"], r["level"])].append(r)
    for policy in policies:
        for clock in ("original", "online"):
            for level in ("0", "1", "2"):
                label = f"{policy}|{clock}"
                mine = rows.get((label, level), [])
                kind = NAME.fullmatch(policy)
                fcfs = kind is not None and not all(
                    admissible(kind.group(1), float(kind.group(2)), k, float(limit))
                    for k in levels_k[level])
                cells = {(r["overlay"]) for r in mine}
                base = [r for r in dev[(label, level)] if r["overlay"] in cells] if mine else \
                    dev[(label, level)]
                row = {"L_s": limit, "policy": policy, "clock": clock, "level": level}
                if fcfs:
                    row |= {"status": "FCFS", "cells": 0, "gap_mean": 0.0, "gap_min": 0.0,
                            "harm_max": 0.0, "excess_max": 0.0}
                elif not mine:
                    row |= {"status": "missing"}
                else:
                    row |= {"status": "run", **stats(mine)}
                row |= {f"L60_{k}": v for k, v in stats(base).items()}
                out.append(row)

fields = list(dict.fromkeys(k for r in out for k in r))
with open(HERE / "limit_summary.csv", "w", encoding="utf-8", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=fields)
    writer.writeheader()
    writer.writerows(out)
done = sum(r["status"] == "run" for r in out)
print(f"wrote limit_summary.csv: {len(out)} rows, {done} with runs, "
      f"{sum(r['status'] == 'FCFS' for r in out)} FCFS, "
      f"{sum(r['status'] == 'missing' for r in out)} missing")
