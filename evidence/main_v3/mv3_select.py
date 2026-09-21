"""Stage 3: choose (B0, eta) per service level G, on the VALIDATION trace only.

Rule, fixed before any number was looked at:
    feasible   observed harm (max excess over FCFS among the jobs FCFS would start within
               1 s) <= G/2 at EVERY one of the three load levels;
    objective  the deadline-window p99 gap closed, in the WORST of the three levels;
    choice     the feasible configuration with the largest worst-level objective; ties
               broken by smaller worst-level harm, then smaller B0, then smaller eta.
One setting per G serves all three levels.  B0 is carried as a multiple of k/4, so the
same setting means the same per-server budget on a trace with a different k.

The validation trace is the 60 s-regime DEV pool minus the dev-test semester 2022-2; no
number on any trace containing 2022-2 enters this stage.

input:  <scratch>/mv3/sim/valid_rep0_L{0,1,2}_grid.csv
output: select_grid.csv (every configuration, every level), selected_params.csv
usage:  mv3_select.py [--trace valid --rep 0]
"""
from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd

import mv3_common as C


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace", default="valid")
    ap.add_argument("--rep", type=int, default=0)
    a = ap.parse_args()

    lg = C.Log("select")
    d = pd.concat([pd.read_csv(os.path.join(C.SIMDIR, f"{a.trace}_rep{a.rep}_L{l}_grid.csv"))
                   for l in range(3)], ignore_index=True)
    ref = d[d.policy.isin(["FCFS", "SJF-ref"])].pivot(index="level", columns="policy")
    gap, red, harm = {}, {}, {}
    for l in sorted(d.level.unique()):
        s = d[d.level == l].set_index("policy")
        f99, s99 = s.loc["FCFS", "w_p99_dl"], s.loc["SJF-ref", "w_p99_dl"]
        gap[l] = (f99 - s.w_p99_dl) / (f99 - s99)
        red[l] = 100.0 * (f99 - s.w_p99_dl) / f99
        harm[l] = s.harm_wf1s
    g = d[d.guard.isin(["cap", "fix"])].copy()
    g["gap"] = [gap[l][p] for l, p in zip(g.level, g.policy)]
    g["red_pct"] = [red[l][p] for l, p in zip(g.level, g.policy)]
    g["harm"] = [harm[l][p] for l, p in zip(g.level, g.policy)]
    g["B0_base"] = np.where(g.guard == "cap", g.B0 * 4.0 / g.k, np.nan)
    g["feasible_level"] = g.harm <= g.G * C.HARM_FRAC
    cols = ["trace", "rep", "level", "k", "rho_busy", "G", "guard", "policy", "B0",
            "B0_base", "eta", "Bmax", "gap", "red_pct", "harm", "feasible_level",
            "w_p99_dl", "w_mean", "max_excess", "max_heavy", "qw_forced_frac",
            "used_over_allowed", "guar_excess_max", "bound_viol"]
    g[cols].sort_values(["G", "guard", "B0_base", "eta", "level"]).to_csv(
        os.path.join(C.HERE, "select_grid.csv"), index=False)

    agg = (g.groupby(["G", "guard", "policy", "B0_base", "eta"], dropna=False)
           .agg(worst_gap=("gap", "min"), worst_harm=("harm", "max"),
                worst_red=("red_pct", "min"), max_used=("used_over_allowed", "max"),
                viol=("bound_viol", "max"), n_lev=("gap", "size")).reset_index())
    assert (agg.n_lev == 3).all() and (agg.viol == 0).all()
    agg["feasible"] = agg.worst_harm <= agg.G * C.HARM_FRAC
    rows = []
    for G in C.GS:
        sub = agg[(agg.G == G) & (agg.guard == "cap")].copy()
        fx = agg[(agg.G == G) & (agg.guard == "fix")].iloc[0]
        ok = sub[sub.feasible]
        note = ""
        if not len(ok):
            ok = sub.sort_values("worst_harm").head(1)
            note = "NO feasible configuration; fell back to the smallest worst-level harm"
        best = ok.sort_values(["worst_gap", "worst_harm", "B0_base", "eta"],
                              ascending=[False, True, True, True]).iloc[0]
        rows.append(dict(G=G, B0_base=float(best.B0_base), eta=float(best.eta),
                         B0_rule=f"{best.B0_base:g} * k/4 s",
                         Bmax_rule=f"k*(G - (3 - 2/k)*60) s",
                         worst_gap=round(float(best.worst_gap), 4),
                         worst_red_pct=round(float(best.worst_red), 3),
                         worst_harm_s=round(float(best.worst_harm), 2),
                         harm_limit_s=G * C.HARM_FRAC,
                         n_feasible=int(sub.feasible.sum()), n_grid=len(sub),
                         fix_worst_gap=round(float(fx.worst_gap), 4),
                         fix_worst_harm_s=round(float(fx.worst_harm), 2),
                         fix_feasible=bool(fx.feasible), note=note))
        lg.w(f"\n=== G = {G:g} s  (harm limit {G * C.HARM_FRAC:g} s) "
             f"[{a.trace} rep{a.rep}] ===")
        lg.w(sub[["policy", "B0_base", "eta", "worst_gap", "worst_harm", "feasible"]]
             .sort_values(["B0_base", "eta"]).round(4).to_string(index=False))
        lg.w(f"fixed-budget baseline FIX-G{G:g} (eta = 0, B0 = Bmax): worst-level gap "
             f"{fx.worst_gap:.4f}, worst-level harm {fx.worst_harm:.2f} s, "
             f"feasible={bool(fx.feasible)}")
        lg.w(f"-> selected B0 = {best.B0_base:g} * k/4 s, eta = {best.eta:g}: worst-level "
             f"gap {best.worst_gap:.4f}, worst-level harm {best.worst_harm:.2f} s "
             f"({int(sub.feasible.sum())} of {len(sub)} grid points feasible) {note}")
    t = pd.DataFrame(rows)
    t.to_csv(os.path.join(C.HERE, "selected_params.csv"), index=False)
    lg.w("\n=== selected parameters (validation only) ===")
    lg.w(t.to_string(index=False))
    lg.close()


if __name__ == "__main__":
    main()
