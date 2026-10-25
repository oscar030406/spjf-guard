"""Block(W) with W up to 8192 under the rule of select_families.py, beside the joint guard.

    python prechecks/limit_family_selection/family/block_wide.py

The rule's Block grid is {8, 32, 128, 512}, and 512 was best at G = 600 and 1200 s, the edge
of the grid.  This script adds the runs of Block(2048) and Block(8192) on the same 15
validation cells (fam_blockx_*), applies steps 1-4 of the rule to the six widths, and prints
the pick at each G beside the joint guard of choices.csv.  It does not change choices.csv.
"""

from __future__ import annotations

import csv
import glob
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from select_families import PROMISES, Point, pick, read_cells, summary  # noqa: E402

ROOT = HERE.parents[2]
VAL = ROOT / "outputs" / "family_selection_41e70726" / "validation"
WIDTHS = (8, 32, 128, 512, 2048, 8192)


def main() -> None:
    paths = sorted(glob.glob(str(VAL / "fam_block_o*_l*" / "online_cells.csv")))
    paths += sorted(glob.glob(str(VAL / "fam_blockx_o*_l*" / "online_cells.csv")))
    cells = read_cells(paths)
    points = [Point("Block", f"Block({w})", None, (float(w),), None) for w in WIDTHS]
    with open(HERE / "choices.csv", encoding="utf-8", newline="") as handle:
        guard = {(r["clock"], float(r["promise_s"])): r for r in csv.DictReader(handle)
                 if r["family"] == "winner"}
    rows = []
    for clock in ("online", "original"):
        sums = {p.name: summary(p, cells[(clock, p.name)]) for p in points}
        for p in points:
            s = sums[p.name]
            rows.append({"clock": clock, "promise_s": "", "block_pick": p.name,
                         "block_worst_gap": s["worst_gap_closed"], "block_worst_harm_s": s["worst_harm_s"],
                         "block_note": "width summary", "n_feasible": "", "guard": "",
                         "guard_worst_gap": "", "guard_worst_harm_s": ""})
            print(f"{clock:8s} {p.name:12s} worst gap {s['worst_gap_closed']:.4f}  worst harm {s['worst_harm_s']:.1f} s")
        for promise in PROMISES:
            choice = pick("Block", points, sums, promise)
            g = guard[(clock, promise)]
            rows.append({"clock": clock, "promise_s": promise, "block_pick": choice["name"],
                         "block_worst_gap": choice["worst_gap_closed"],
                         "block_worst_harm_s": choice["worst_harm_s"], "block_note": choice["note"],
                         "n_feasible": choice["n_feasible"], "guard": g["name"],
                         "guard_worst_gap": g["worst_gap_closed"], "guard_worst_harm_s": g["worst_harm_s"]})
            print(f"{clock:8s} G={promise:6.0f}  Block pick {choice['name']} gap {choice['worst_gap_closed']:.4f} "
                  f"harm {choice['worst_harm_s']:.1f}  feasible {choice['n_feasible']}/6 {choice['note']}  | "
                  f"guard {g['name']} gap {float(g['worst_gap_closed']):.4f}")
    with open(HERE / "block_wide.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
