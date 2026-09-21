"""V1 (simulation side): the validation cells that decide the guard parameters, redone
with the independent simulator.

Cells chosen: valid rep1 L2 (the WORST cell -- it is where the rejected v3 G = 600
setting reaches harm 358.92 s and where the selected setting reaches 293.29 s), valid
rep1 L0 (the worst-GAP cell of the selected setting, i.e. the cell that sets its
objective value 0.7216), valid rep1 L1 and valid rep0 L2.
Configurations: the three v3.1 picks, the rejected v3 G = 600 pick, the two FIXSEL picks
and the three FIX baselines, plus FCFS / SJF-ref / SPJF-tweedie.
Read-only.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

ROOT = r"<repo-root>"
V31 = os.path.join(ROOT, "evidence", "main_v3", "v31")
HERE = os.path.dirname(os.path.abspath(__file__))
SCRATCH = r"<cache-dir>"
BSIM = os.path.join(SCRATCH, "mv31", "sim")
MINE = os.path.join(SCRATCH, "mv31_verify", "cells")
OUT = []

# my policy name -> the builder's grid name
MAP = {"FCFS": "FCFS", "SJF-ref": "SJF-ref", "SPJF-tweedie": "SPJF-tweedie",
       "CAP-G300-B30-e0.5": "CAP-G300-B30-e0.5",
       "CAP-G600-B120-e0.75": "CAP-G600-B120-e0.75",
       "CAP-G1200-B120-e0.9": "CAP-G1200-B120-e0.9",
       "CAP-G600-B30-e0.9": "CAP-G600-B30-e0.9",
       "FIXSEL-G300": "CAP-G300-B120-e0", "FIXSEL-G600": "CAP-G600-B600-e0",
       "FIX-G300": "FIX-G300", "FIX-G600": "FIX-G600", "FIX-G1200": "FIX-G1200"}
COLS = [("w_p99_dl", 5e-9), ("w_mean", 5e-9), ("w_p99", 5e-9), ("max_excess", 5e-9),
        ("harm_wf1s", 5e-9), ("max_heavy", 5e-9), ("used_over_allowed", 5e-7),
        ("guar_excess_max", 5e-7)]


def say(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    OUT.append(s)


def main():
    cells = [f[:-4] for f in sorted(os.listdir(MINE))
             if f.startswith("valid_") and f.endswith("_grid.csv")]
    say("=" * 96)
    say("VALIDATION CELLS RE-SIMULATED (independent simulator)")
    say("=" * 96)
    tot = bad = 0
    gridb = pd.read_csv(os.path.join(V31, "select_grid.csv"))
    for tag in cells:
        m = pd.read_csv(os.path.join(MINE, tag + ".csv")).set_index("policy")
        b = pd.read_csv(os.path.join(BSIM, tag + ".csv")).set_index("policy")
        rep, lev = int(tag.split("_")[1][3:]), int(tag.split("_")[2][1:])
        say("")
        say(f"--- {tag}  k={int(m.k.iloc[0])} ---")
        say(f"   {'policy':22s} {'p99_dl (mine/builder)':30s} "
            f"{'harm (mine/builder)':26s} {'max_excess (m/b)':24s} viol usedA usedB")
        f99, s99 = m.loc["FCFS", "w_p99_dl"], m.loc["SJF-ref", "w_p99_dl"]
        for mp, bp in MAP.items():
            if mp not in m.index or bp not in b.index:
                say(f"   !! missing {mp} / {bp}")
                continue
            r, q = m.loc[mp], b.loc[bp]
            for c, tol in COLS:
                x, y = float(r[c]), float(q[c])
                if not np.isfinite(x) and not np.isfinite(y):
                    continue
                tot += 1
                if abs(x - y) > tol * max(1.0, abs(y)):
                    bad += 1
                    say(f"   !! {mp} {c}: mine {x!r} builder {y!r}")
            gap = (f99 - r.w_p99_dl) / (f99 - s99)
            gb = gridb[(gridb.rep == rep) & (gridb.level == lev)
                       & (gridb.policy == bp)]
            gapb = float(gb.gap.iloc[0]) if len(gb) else float("nan")
            say(f"   {mp:22s} {r.w_p99_dl:12.4f}/{q.w_p99_dl:12.4f}  "
                f"{r.harm_wf1s:11.4f}/{q.harm_wf1s:11.4f}  "
                f"{r.max_excess:10.3f}/{q.max_excess:10.3f}  "
                f"{int(r.bound_viol):3d}  {r.usedA if np.isfinite(r.usedA) else float('nan'):.4f} "
                f"{r.usedB if np.isfinite(r.usedB) else float('nan'):.4f}"
                + (f"   gap mine {gap:.4f} / select_grid {gapb:.4f}"
                   if np.isfinite(gapb) else ""))
    say("")
    say(f"  numbers compared: {tot}, mismatches {bad}")

    say("")
    say("=" * 96)
    say("THE TWO HEADLINE SELECTION NUMBERS, FROM MY OWN WAITS")
    say("=" * 96)
    w = pd.read_csv(os.path.join(MINE, "valid_rep1_L2_grid.csv")).set_index("policy")
    say(f"  rejected v3 G=600 setting (30*k/4, eta 0.9), cell valid rep1 L2:")
    say(f"     harm = {w.loc['CAP-G600-B30-e0.9', 'harm_wf1s']:.4f} s   "
        f"(report 358.92, limit 300)   INFEASIBLE="
        f"{w.loc['CAP-G600-B30-e0.9', 'harm_wf1s'] > 300.0}")
    say(f"  selected G=600 setting (120*k/4, eta 0.75), same cell:")
    say(f"     harm = {w.loc['CAP-G600-B120-e0.75', 'harm_wf1s']:.4f} s   "
        f"(report 293.29, limit 300)   FEASIBLE="
        f"{w.loc['CAP-G600-B120-e0.75', 'harm_wf1s'] <= 300.0}")
    w0 = pd.read_csv(os.path.join(MINE, "valid_rep1_L0_grid.csv")).set_index("policy")
    f99, s99 = w0.loc["FCFS", "w_p99_dl"], w0.loc["SJF-ref", "w_p99_dl"]
    g = (f99 - w0.loc["CAP-G600-B120-e0.75", "w_p99_dl"]) / (f99 - s99)
    say(f"  worst-cell objective of the selected G=600 setting (cell valid rep1 L0):")
    say(f"     gap closed = {g:.4f}   (report worst_gap 0.7216)")
    g2 = (f99 - w0.loc["CAP-G600-B30-e0.9", "w_p99_dl"]) / (f99 - s99)
    say(f"     the rejected setting in the same cell: {g2:.4f}  "
        f"(report worst_gap 0.7210 -- the two are within 0.0006, so the rejected "
        f"setting buys nothing for its extra harm)")
    open(os.path.join(HERE, "out_valid.txt"), "w",
         encoding="utf-8").write("\n".join(OUT) + "\n")


if __name__ == "__main__":
    main()
