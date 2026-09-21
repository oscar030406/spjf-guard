"""Stage 3 (v3.1): choose the guard parameters over EVERY validation overlay.

v3's rule took the worst of the three load levels on ONE validation overlay.  The
verifier showed (F8) that on the overlay v3 built but never used, the G = 600 winner
violates the very harm constraint the rule is built on (358.9 s against a 300 s limit),
and the same rule there picks (120 k/4, 0.75) instead.  The rule is therefore restated,
before looking at any v3.1 number, as worst-case over overlays as well as levels:

    feasible   harm (max excess over FCFS among jobs FCFS would start within 1 s)
               <= G/2 at EVERY load level of EVERY validation overlay;
    objective  the deadline-window p99 gap closed, in the WORST (overlay, level) cell;
    choice     the feasible configuration with the largest worst-cell objective; ties
               to smaller worst-cell harm, then smaller B0, then smaller eta.

The identical rule is applied twice:
    cap     over all 15 (B0, eta) grid points -> CAP-G<G>;
    fixsel  over the fixed-budget sub-family only (eta = 0, i.e. a constant budget
            min(B0, Bmax)) together with the equal-G baseline B0 = Bmax -> FIXSEL-G<G>.
So "does the capped relative budget beat a fixed budget at the same promise" is decided
against the best FEASIBLE fixed budget, not only against B0 = Bmax, which is infeasible
at all three G.

input:  <scratch>/mv31/sim/valid_rep{0..4}_L{0,1,2}_grid.csv
output: select_grid.csv (every configuration in every cell), select_worst.csv (the
        worst-cell summary per configuration), selected_params.csv
usage:  v31_select.py [--trace valid]
"""
from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd

import v31_common as C

FIX_SENTINEL = 1e9          # B0_base meaning "B0 = Bmax", i.e. the equal-G baseline


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace", default="valid")
    a = ap.parse_args()

    lg = C.Log("select")
    frames = []
    for rep in C.VALID_REPS:
        for lev in range(3):
            p = os.path.join(C.SIMDIR, f"{a.trace}_rep{rep}_L{lev}_grid.csv")
            frames.append(pd.read_csv(p))
    d = pd.concat(frames, ignore_index=True)
    cells = sorted(set(zip(d.rep, d.level)))
    lg.w(f"selection cells: {len(cells)} = {len(C.VALID_REPS)} validation overlays x 3 "
         f"load levels; {d.policy.nunique()} policies each; k per cell "
         f"{ {c: int(d[(d.rep == c[0]) & (d.level == c[1])].k.iloc[0]) for c in cells} }")
    assert len(cells) == 3 * len(C.VALID_REPS)
    assert int(d[d.bound_viol >= 0].bound_viol.sum()) == 0

    g = []
    for rep, lev in cells:
        s = d[(d.rep == rep) & (d.level == lev)].set_index("policy")
        f99, s99 = s.loc["FCFS", "w_p99_dl"], s.loc["SJF-ref", "w_p99_dl"]
        for p in s.index:
            if s.loc[p, "guard"] not in ("cap", "fix"):
                continue
            k = float(s.loc[p, "k"])
            g.append(dict(rep=rep, level=lev, k=k, policy=p, G=float(s.loc[p, "G"]),
                          guard=s.loc[p, "guard"],
                          B0_base=(FIX_SENTINEL if s.loc[p, "guard"] == "fix"
                                   else s.loc[p, "B0"] * 4.0 / k),
                          eta=float(s.loc[p, "eta"]),
                          gap=(f99 - s.loc[p, "w_p99_dl"]) / (f99 - s99),
                          red_pct=100.0 * (f99 - s.loc[p, "w_p99_dl"]) / f99,
                          harm=float(s.loc[p, "harm_wf1s"]),
                          w_p99_dl=float(s.loc[p, "w_p99_dl"]),
                          used_over_allowed=float(s.loc[p, "used_over_allowed"])))
    G = pd.DataFrame(g)
    G["feasible_cell"] = G.harm <= G.G * C.HARM_FRAC
    G.sort_values(["G", "B0_base", "eta", "rep", "level"]).to_csv(
        os.path.join(C.HERE, "select_grid.csv"), index=False)

    agg = (G.groupby(["G", "guard", "B0_base", "eta"], dropna=False)
           .agg(worst_gap=("gap", "min"), worst_harm=("harm", "max"),
                worst_red=("red_pct", "min"), mean_gap=("gap", "mean"),
                n_cells=("gap", "size"), n_feasible_cells=("feasible_cell", "sum"),
                max_used=("used_over_allowed", "max")).reset_index())
    assert (agg.n_cells == len(cells)).all()
    agg["feasible"] = agg.worst_harm <= agg.G * C.HARM_FRAC
    agg.sort_values(["G", "B0_base", "eta"]).to_csv(
        os.path.join(C.HERE, "select_worst.csv"), index=False)

    V3 = {300.0: (30.0, 0.5), 600.0: (30.0, 0.9), 1200.0: (120.0, 0.9)}
    rows = []
    for Gv in C.GS:
        sub = agg[agg.G == Gv]
        fx = sub[sub.guard == "fix"].iloc[0]
        lg.w(f"\n=== G = {Gv:g} s   (harm limit {Gv * C.HARM_FRAC:g} s, "
             f"{len(cells)} validation cells) ===")
        show = sub.assign(B0=lambda x: np.where(x.B0_base >= FIX_SENTINEL, np.inf,
                                                x.B0_base))
        lg.w(show[["guard", "B0", "eta", "worst_gap", "worst_harm", "n_feasible_cells",
                   "feasible"]].sort_values(["guard", "B0", "eta"]).round(4)
             .to_string(index=False))
        for fam, pool in (("cap", sub[sub.guard == "cap"]),
                          ("fixsel", sub[(sub.guard == "fix") |
                                         ((sub.guard == "cap") & (sub.eta == 0.0))])):
            ok = pool[pool.feasible]
            note = ""
            if not len(ok):
                ok = pool.sort_values("worst_harm").head(1)
                note = "NO feasible configuration; fell back to the smallest worst harm"
            best = ok.sort_values(["worst_gap", "worst_harm", "B0_base", "eta"],
                                  ascending=[False, True, True, True]).iloc[0]
            v3b, v3e = V3[Gv]
            same = (fam == "cap" and abs(best.B0_base - v3b) < 1e-9
                    and abs(best.eta - v3e) < 1e-9)
            v3row = sub[(sub.guard == "cap") & (np.isclose(sub.B0_base, v3b))
                        & (np.isclose(sub.eta, v3e))]
            rows.append(dict(
                family=fam, G=Gv, B0_base=float(best.B0_base), eta=float(best.eta),
                B0_rule=("B0 = Bmax" if best.B0_base >= FIX_SENTINEL
                         else f"{best.B0_base:g} * k/4 s"),
                Bmax_rule="k*(G - (3 - 2/k)*60) s",
                worst_gap=round(float(best.worst_gap), 4),
                worst_red_pct=round(float(best.worst_red), 3),
                worst_harm_s=round(float(best.worst_harm), 2),
                harm_limit_s=Gv * C.HARM_FRAC,
                n_feasible=int(pool.feasible.sum()), n_grid=len(pool),
                v3_choice=f"{v3b:g}*k/4, eta {v3e:g}",
                v3_worst_gap=(round(float(v3row.worst_gap.iloc[0]), 4) if len(v3row)
                              else np.nan),
                v3_worst_harm_s=(round(float(v3row.worst_harm.iloc[0]), 2) if len(v3row)
                                 else np.nan),
                v3_feasible_now=(bool(v3row.feasible.iloc[0]) if len(v3row) else False),
                same_as_v3=bool(same), note=note))
            lg.w(f"-> [{fam}] B0 = {rows[-1]['B0_rule']}, eta = {best.eta:g}: worst-cell "
                 f"gap {best.worst_gap:.4f}, worst-cell harm {best.worst_harm:.2f} s "
                 f"({int(pool.feasible.sum())} of {len(pool)} feasible) {note}")
        lg.w(f"   equal-G fixed baseline FIX (eta = 0, B0 = Bmax): worst gap "
             f"{fx.worst_gap:.4f}, worst harm {fx.worst_harm:.2f} s, "
             f"feasible={bool(fx.feasible)} "
             f"({int(fx.n_feasible_cells)}/{len(cells)} cells)")
        v3b, v3e = V3[Gv]
        v3row = sub[(sub.guard == "cap") & (np.isclose(sub.B0_base, v3b))
                    & (np.isclose(sub.eta, v3e))].iloc[0]
        lg.w(f"   v3's choice ({v3b:g}*k/4, eta {v3e:g}) under the new rule: worst gap "
             f"{v3row.worst_gap:.4f}, worst harm {v3row.worst_harm:.2f} s, "
             f"feasible={bool(v3row.feasible)} "
             f"({int(v3row.n_feasible_cells)}/{len(cells)} cells)")
    t = pd.DataFrame(rows)
    t.to_csv(os.path.join(C.HERE, "selected_params.csv"), index=False)
    lg.w("\n=== selected parameters (validation overlays only) ===")
    lg.w(t.to_string(index=False))
    lg.close()


if __name__ == "__main__":
    main()
