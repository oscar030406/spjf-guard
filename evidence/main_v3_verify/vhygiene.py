"""C1: selection hygiene, checked against the artefacts rather than against the prose.

1. the validation trace really is the primary pool minus one semester's worth of jobs:
   the service-time multiset of the primary trace is 44 copies of a per-copy multiset P,
   the validation trace's is 49 copies of V, and P - V must be non-negative everywhere
   (i.e. the validation pool is a sub-pool), with |P| - |V| jobs removed.
2. the selection rule of the report, re-applied by me to select_grid.csv, must reproduce
   selected_params.csv; and the gaps in select_grid.csv must follow from the raw
   validation grid cells.
3. what the G = 600 admission in section 9 costs: capped vs fixed, per overlay.

usage: vhygiene.py
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

import vsim
from vsim import SCRATCH

MAIN = r"<repo-root>\evidence\main_v3"
BSIM = os.path.join(SCRATCH, "mv3", "sim")
GS = (300.0, 600.0, 1200.0)


def multiset_check():
    print("=" * 90)
    print("1. IS THE VALIDATION TRACE THE PRIMARY POOL MINUS ONE SEMESTER?")
    out = {}
    for trace, rep in (("primary", 0), ("valid", 0)):
        z = np.load(os.path.join(vsim.BUILDER_TRACES, f"{trace}_rep{rep}.npz"))
        svc = z["svc"]
        cop = int(z["copies"])
        u, c = np.unique(svc, return_counts=True)
        assert (c % cop == 0).all(), f"{trace}: counts are not a multiple of {cop} copies"
        out[trace] = (u, c // cop, cop, len(svc))
        print(f"  {trace} rep{rep}: {len(svc):,} jobs = {cop} copies x "
              f"{len(svc) // cop:,} jobs, {len(u):,} distinct service times")
        del z, svc
    (up, cp, _, np_), (uv, cv, _, nv) = out["primary"], out["valid"]
    idx = np.searchsorted(up, uv)
    assert np.array_equal(up[idx], uv), "validation has a service time the primary has not"
    d = cp.copy()
    d[idx] -= cv
    print(f"  per copy: primary {cp.sum():,} jobs, validation {cv.sum():,}; "
          f"difference {d.sum():,} jobs, negative entries {int((d < 0).sum())}")
    print("  -> the validation per-copy pool is a strict sub-multiset of the primary one"
          if (d >= 0).all() else "  -> NOT a sub-pool: the validation trace is not a subset")
    t = pd.read_csv(os.path.join(MAIN, "trace_summary.csv"))
    print(t[["trace", "rep", "copies", "class_semesters", "n_jobs"]].to_string(index=False))
    print(f"  class-semesters: primary {t.loc[t.trace == 'primary', 'class_semesters'].iloc[0]},"
          f" validation {t.loc[t.trace == 'valid', 'class_semesters'].iloc[0]},"
          f" 2022-2 alone {t.loc[t.trace == 't222', 'class_semesters'].iloc[0]}")


def selection_check():
    print("=" * 90)
    print("2. THE SELECTION RULE, RE-APPLIED TO THE GRID")
    raw = {l: pd.read_csv(os.path.join(BSIM, f"valid_rep0_L{l}_grid.csv")).set_index("policy")
           for l in range(3)}
    g = pd.read_csv(os.path.join(MAIN, "select_grid.csv"))
    bad = 0
    for _, r in g.iterrows():
        s = raw[int(r.level)]
        f99, s99 = s.loc["FCFS", "w_p99_dl"], s.loc["SJF-ref", "w_p99_dl"]
        gap = (f99 - s.loc[r.policy, "w_p99_dl"]) / (f99 - s99)
        harm = s.loc[r.policy, "harm_wf1s"]
        if abs(gap - r.gap) > 1e-9 or abs(harm - r.harm) > 1e-9:
            bad += 1
            print(f"  MISMATCH {r.policy} L{r.level}: gap {r.gap} vs {gap}, "
                  f"harm {r.harm} vs {harm}")
    print(f"  select_grid.csv rows re-derived from the raw validation cells: {len(g)}, "
          f"mismatches {bad}")
    sel = pd.read_csv(os.path.join(MAIN, "selected_params.csv"))
    print(f"  grid points per G: {len(g[(g.G == 600) & (g.guard == 'cap')]) // 3} capped "
          f"+ 1 fixed, on 3 levels")
    for G in GS:
        sub = g[(g.G == G) & (g.guard == "cap")]
        agg = (sub.groupby(["B0_base", "eta"])
               .agg(worst_gap=("gap", "min"), worst_harm=("harm", "max"),
                    n=("gap", "size")).reset_index())
        assert (agg.n == 3).all()
        ok = agg[agg.worst_harm <= G / 2.0]
        best = ok.sort_values(["worst_gap", "worst_harm", "B0_base", "eta"],
                              ascending=[False, True, True, True]).iloc[0]
        row = sel[sel.G == G].iloc[0]
        mark = "OK" if (best.B0_base == row.B0_base and best.eta == row.eta) else "DIFFERENT"
        print(f"  G={G:6.0f}: my pick B0={best.B0_base:g}*k/4 eta={best.eta:g} "
              f"(worst gap {best.worst_gap:.4f}, worst harm {best.worst_harm:.1f}); "
              f"reported B0={row.B0_base:g} eta={row.eta:g} -> {mark}")
        runner = ok.sort_values("worst_gap", ascending=False).head(3)
        print("        top three feasible: " +
              "; ".join(f"B0={r.B0_base:g},eta={r.eta:g}: gap {r.worst_gap:.4f}, "
                        f"harm {r.worst_harm:.0f}" for _, r in runner.iterrows()))
        print(f"        feasible {len(ok)} of {len(agg)}; the fixed-budget guard at the "
              f"same G: worst harm "
              f"{g[(g.G == G) & (g.guard == 'fix')].harm.max():.1f} "
              f"(limit {G / 2:.0f}) -> "
              f"{'feasible' if g[(g.G == G) & (g.guard == 'fix')].harm.max() <= G / 2 else 'infeasible'}")


def sec9_check():
    print("=" * 90)
    print("3. CAPPED VS FIXED AT EQUAL G, PER OVERLAY (what section 9 admits)")
    for lev in range(3):
        cs = {r: pd.read_csv(os.path.join(BSIM, f"primary_rep{r}_L{lev}_main.csv"))
              .set_index("policy") for r in range(5)}
        for G in GS:
            hf = np.array([cs[r].loc[f"FIX-G{G:g}", "harm_wf1s"] for r in range(5)])
            hc = np.array([cs[r].loc[f"CAP-G{G:g}", "harm_wf1s"] for r in range(5)])
            gf = np.array([cs[r].loc[f"FIX-G{G:g}", "w_p99_dl"] for r in range(5)])
            gc = np.array([cs[r].loc[f"CAP-G{G:g}", "w_p99_dl"] for r in range(5)])
            print(f"  L{lev} G={G:6.0f}  harm FIX {np.round(hf, 1)}  max {hf.max():7.1f}")
            print(f"              harm CAP {np.round(hc, 1)}  max {hc.max():7.1f}  "
                  f"ratio of maxima {hf.max() / hc.max():.2f}  "
                  f"per-overlay ratios {np.round(hf / hc, 2)}")
            print(f"              p99dl FIX {gf.mean():.2f} vs CAP {gc.mean():.2f}")


if __name__ == "__main__":
    multiset_check()
    selection_check()
    sec9_check()
