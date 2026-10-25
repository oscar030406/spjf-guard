"""The primary-pool (evaluation) rows of what select_families.py chose, beside the paper's Guard(G).

    python evidence/limit_family_selection/family/evaluate.py \
        --choices evidence/limit_family_selection/family/choices.csv [--source <online_cells.csv> ...]

For G in {300, 600, 1200}: the online winner, the online winner among the promise-carrying
families, and the paper's Guard(G).  Their online rows are looked up by policy name in
outputs/dev_online_visibility, outputs/online_selection/evaluation{,_all} and every --source.
An A3 point also matches a dev_online_visibility name whose Policy is field for field the same
at every k of the pool (only the name differs).  Per level: mean and minimum gap_closed, largest
harm_s, largest max_excess_s.  A choice without its 15 primary cells gets a queue line in
jobs_primary.txt instead.  Nothing here feeds back into the choice.
"""

import argparse
import csv
import json
import sys
from dataclasses import replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
from make_jobs import tag  # noqa: E402
from select_families import A3, PROMISES, guard_points, read_cells  # noqa: E402
from select_online import grid_point  # noqa: E402
from spjf_guard import config as cfgmod  # noqa: E402
from spjf_guard.experiment import grids  # noqa: E402

SOURCES = [ROOT / "outputs" / "dev_online_visibility" / "online_cells.csv",
           A3 / "evaluation" / "online_cells.csv", A3 / "evaluation_all" / "online_cells.csv"]
PRIMARY_K = (4, 5, 7, 8)
CELLS = {(o, lv) for o in range(5) for lv in range(3)}


def aliases(cfg) -> dict[str, str]:
    """A3 name -> the dev_online_visibility name of the same policy at every k."""
    with open(A3 / "candidates_all.csv", encoding="utf-8", newline="") as handle:
        points = [grid_point(r) for r in csv.DictReader(handle)]
    out = {}
    for p in points:
        for name in sorted({q.name for q in cfg.policies(4)}):
            if all(replace(grids.policy_for(p, k, cfg.limit_s, "spjf_e", cfg.promises_s), name="")
                   == replace(next(q for q in cfg.policies(k) if q.name == name), name="")
                   for k in PRIMARY_K):
                out[p.name] = name
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--choices", type=Path, required=True)
    ap.add_argument("--source", type=Path, action="append", default=[])
    args = ap.parse_args()
    cfg = cfgmod.load(ROOT / "configs" / "main.yaml")
    alias = aliases(cfg)
    cells = read_cells([*SOURCES, *args.source])
    with open(args.choices, encoding="utf-8", newline="") as handle:
        choices = [r for r in csv.DictReader(handle) if r["clock"] == "online"
                   and r["family"] in ("winner", "winner_with_promise")]
    wanted = [(float(r["promise_s"]), r["family"], r["name"]) for r in choices]
    wanted += [(g, "paper Guard(G)", f"Guard({g:g})") for g in PROMISES]
    rows, jobs, a3 = [], [], {p.name for p in guard_points(cfg)}
    for promise, role, name in sorted(wanted):
        looked = alias.get(name, name)
        block = cells.get(("online", looked), {})
        if set(block) != CELLS:
            jobs.append((role, name))
            rows.append({"promise_s": promise, "role": role, "name": name, "primary_as": looked,
                         "level": "", "cells": len(block)})
            continue
        for level in ("0", "1", "2"):
            sel = [r for (o, lv), r in block.items() if str(lv) == level]
            gaps = [float(r["gap_closed"]) for r in sel]
            rows.append({"promise_s": promise, "role": role, "name": name, "primary_as": looked,
                         "level": level, "cells": len(sel), "gap_mean": sum(gaps) / len(gaps),
                         "gap_min": min(gaps), "harm_max": max(float(r["harm_s"]) for r in sel),
                         "excess_max": max(float(r["max_excess_s"]) for r in sel)})
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with open(HERE / "evaluation.csv", "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    lines = []
    for role, name in dict.fromkeys(jobs):
        if name in a3:
            point = next(p for p in guard_points(cfg) if p.name == name)
            print(f"{role}: {name} needs a primary run through rov --candidates ({point.family})")
            continue
        for overlay in range(5):
            for level in (2, 1, 0):
                job = f"fam_primary_{name.replace('(', '_').replace(')', '').replace('=', '')}" \
                      f"_o{overlay}_l{level}"
                variant = "fixed_point" if name.startswith("Block(") else "online"
                lines.append(json.dumps({"name": job, "gb": 10, "cmd": [
                    "{python}", "-u", "evidence/limit_family_selection/family/run_family.py",
                    "--pool", "primary", "--variants", variant, "--policies", name,
                    "--reps", str(overlay), "--levels", str(level), "--workers", "1", "--resume",
                    "--out-dir", f"outputs/family_selection_{tag}/primary/{job}"]}))
    (HERE / "jobs_primary.txt").write_text("".join(f"{x}\n" for x in lines), encoding="utf-8")
    print(f"wrote evaluation.csv ({len(rows)} rows); {len(lines)} primary jobs in jobs_primary.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
