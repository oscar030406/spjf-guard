"""Adversarial probe of the FIXSEL claim: is the builder's fixed-budget grid fine enough?

v3.1 decides "the capped relative budget beats the best FEASIBLE fixed budget" against a
fixed family of only four points per G: B0 = {30, 120, 600} k/4 s and B0 = Bmax.  At
G = 300 s the admitted point is 120 k/4 (worst-cell harm 102.65 s against a 150 s limit)
and the next one up, 600 k/4, is infeasible (212.04 s) -- so the constraint is nowhere
near tight and the chosen point may be far from the best feasible fixed budget.

This script runs a FINER eta = 0 grid on all 15 validation cells with the independent
simulator, applies the report's own rule to it, and then measures what the better fixed
budget does on the primary trace, i.e. how much of the reported CAP - FIXSEL margin is an
artefact of the coarse grid.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

ROOT = r"<repo-root>"
V31 = os.path.join(ROOT, "evidence", "main_v3", "v31")
HERE = os.path.dirname(os.path.abspath(__file__))
SCRATCH = r"<cache-dir>"
MINE = os.path.join(SCRATCH, "mv31_verify", "cells")
L = 60.0
GS = (300.0, 600.0, 1200.0)
OUT = []


def say(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    OUT.append(s)


def bmax_of(G, k):
    return float(k) * (G - (3.0 - 2.0 / k) * L)


def main():
    rows = []
    for rep in range(5):
        for lev in range(3):
            p = os.path.join(MINE, f"valid_rep{rep}_L{lev}_fixgrid.csv")
            d = pd.read_csv(p).set_index("policy")
            k = float(d.k.iloc[0])
            f99, s99 = d.loc["FCFS", "w_p99_dl"], d.loc["SJF-ref", "w_p99_dl"]
            for pol in d.index:
                if not pol.startswith("FIXG-"):
                    continue
                b0b = float(pol.split("B")[1])
                rows.append(dict(rep=rep, level=lev, k=k, b0b=b0b,
                                 B0=float(d.loc[pol, "B0"]),
                                 gap=(f99 - d.loc[pol, "w_p99_dl"]) / (f99 - s99),
                                 harm=float(d.loc[pol, "harm_wf1s"]),
                                 guar=float(d.loc[pol, "guar_excess_max"])))
    D = pd.DataFrame(rows)
    say("=" * 96)
    say("A FINER FIXED-BUDGET GRID ON ALL 15 VALIDATION CELLS (my own simulator)")
    say("=" * 96)
    say(f"  {D.b0b.nunique()} budgets x 15 cells = {len(D)} runs, eta = 0 throughout")
    agg = D.groupby("b0b").agg(worst_gap=("gap", "min"), worst_harm=("harm", "max"),
                               worst_guar=("guar", "max"),
                               min_guar=("guar", "min")).reset_index()
    say("")
    say("   B0 (x k/4 s)   worst-cell gap   worst-cell harm   promise range over the cells")
    for r in agg.itertuples():
        say(f"   {r.b0b:12.0f}   {r.worst_gap:14.4f}   {r.worst_harm:15.2f}   "
            f"{r.min_guar:7.1f} - {r.worst_guar:7.1f} s")

    say("")
    say("=" * 96)
    say("THE REPORT'S OWN RULE ON THE FINER GRID")
    say("=" * 96)
    BUILDER = {300.0: 120.0, 600.0: 600.0, 1200.0: 600.0}
    better = {}
    for Gv in GS:
        # a fixed budget is only admissible at G if it is <= Bmax(G) in every cell,
        # exactly as the builder's min(B0, Bmax) does.
        ok = []
        for r in agg.itertuples():
            fits = all(r.b0b * float(k) / 4.0 <= bmax_of(Gv, float(k)) + 1e-9
                       for k in D.k.unique())
            if fits and r.worst_harm <= Gv * 0.5:
                ok.append(r)
        b = max(ok, key=lambda r: (r.worst_gap, -r.worst_harm, -r.b0b)) if ok else None
        bb = agg[agg.b0b == BUILDER[Gv]].iloc[0]
        better[Gv] = b
        say(f"  G = {Gv:6.0f} s (harm limit {Gv * 0.5:g} s):")
        say(f"     builder's admitted fixed budget  B0 = {BUILDER[Gv]:g} k/4 s: "
            f"worst gap {bb.worst_gap:.4f}, worst harm {bb.worst_harm:.2f} s")
        if b is None:
            say("     finer grid: no feasible point")
            continue
        say(f"     best on the finer grid           B0 = {b.b0b:g} k/4 s: "
            f"worst gap {b.worst_gap:.4f}, worst harm {b.worst_harm:.2f} s")
        say(f"     -> the objective the fixed family can reach rises by "
            f"{b.worst_gap - bb.worst_gap:+.4f} on validation")
    open(os.path.join(HERE, "out_fixgrid.txt"), "w",
         encoding="utf-8").write("\n".join(OUT) + "\n")
    return better


def primary_impact():
    """What the better fixed budget does on the reported (primary) trace."""
    better = {300.0: 300.0, 600.0: 900.0, 1200.0: 1200.0}
    T = pd.read_csv(os.path.join(V31, "table_main_primary.csv"))
    H = pd.read_csv(os.path.join(V31, "report_cap_vs_fix.csv"))
    say("")
    say("=" * 96)
    say("WHAT IT DOES TO THE REPORTED CAP - FIXSEL MARGIN (primary trace, 5 overlays)")
    say("=" * 96)
    say("  level  G      gap CAP   gap FIXSEL(builder)   gap FIXSEL'(finer grid)   "
        "d_reported   d_corrected   harm CAP / FIXSEL'")
    for lev in (0, 1, 2):
        cells = {}
        fg = {}
        for r in range(5):
            cells[r] = pd.read_csv(os.path.join(
                MINE, f"primary_rep{r}_L{lev}_main.csv")).set_index("policy")
            fg[r] = pd.read_csv(os.path.join(
                MINE, f"primary_rep{r}_L{lev}_fixgrid.csv")).set_index("policy")
        F = np.array([cells[r].loc["FCFS", "w_p99_dl"] for r in range(5)])
        S = np.array([cells[r].loc["SJF-ref", "w_p99_dl"] for r in range(5)])

        def gap(src, pol):
            P = np.array([src[r].loc[pol, "w_p99_dl"] for r in range(5)])
            return float(np.mean((F - P) / (F - S)))

        def harm(src, pol):
            return float(np.max([src[r].loc[pol, "harm_wf1s"] for r in range(5)]))

        for Gv in GS:
            gc = gap(cells, f"CAP-G{Gv:g}")
            gf = gap(cells, f"FIXSEL-G{Gv:g}")
            gn = gap(fg, f"FIXG-B{better[Gv]:g}")
            hc = harm(cells, f"CAP-G{Gv:g}")
            hn = harm(fg, f"FIXG-B{better[Gv]:g}")
            row = H[(H.trace == "primary") & (H.level == lev) & (H.G == Gv)]
            say(f"  {lev:5d} {Gv:6.0f}   {gc:8.4f}   {gf:19.4f}   {gn:23.4f}   "
                f"{gc - gf:+10.4f}   {gc - gn:+11.4f}   {hc:6.1f} / {hn:6.1f}"
                f"   (report d = {float(row.d_gap_cap_minus_fixsel.iloc[0]):+.3f})")
    say("")
    say("  Read: 'd_corrected' is the same comparison the report makes, but against the")
    say("  best fixed budget the SAME rule admits on a grid that is not coarse.  The")
    say("  capped budget still wins every cell, but by much less than the report prints.")
    open(os.path.join(HERE, "out_fixgrid.txt"), "w",
         encoding="utf-8").write("\n".join(OUT) + "\n")


if __name__ == "__main__":
    main()
    primary_impact()
