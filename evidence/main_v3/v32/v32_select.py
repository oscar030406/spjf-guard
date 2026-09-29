"""Stage 3 (v3.2): select one setting per family per promise G, on equal grids.

The rule is v3.1's, unchanged:
    feasible   harm (max excess over FCFS among jobs FCFS would start within 1 s)
               <= G/2 in EVERY one of the 15 validation cells (5 overlays x 3 levels);
    admissible the configuration's own promise is <= G in every cell (a constant budget
               promises B0/k + (3-2/k)L, which is less than G for small budgets, so small
               fixed budgets are admissible at every G);
    objective  the deadline-window p99 gap closed in the WORST cell;
    ties       smaller worst-cell harm, then smaller B0, then smaller eta, then gam.
What changed is only the search: both budget families now get the grids pre-stated in
v32_common's docstring, and a hybrid family is searched alongside them.

Self-test: a capped configuration with eta = 0 is the same schedule as the fixed
configuration with the same B0 (the cap never binds below it).  They are simulated
separately -- different Bmax, hence different dedup keys -- and their metrics must agree
cell by cell.  A disagreement fails this stage.

Reported besides the choice: the slack in the binding harm constraint, the next grid point
up, the whole feasible frontier (gap vs harm) per family and G, and the selection when the
single validation cell the verifier flagged (overlay 1, level 2) is dropped.

output: select_cells.csv, select_worst.csv, frontier.csv, selected_params.csv,
        select_sensitivity.csv
usage:  v32_select.py
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

import v32_common as C

FAMS = ("fixed", "capped", "hybrid")


def parse(policy, family):
    """(B0_base, eta, gam_base) from the grid policy name."""
    if policy.startswith("FIXG-B"):
        return float(policy[6:]), 0.0, 0.0
    if policy.startswith("FIXEQ-"):
        return np.inf, 0.0, 0.0
    p = policy.split("-")
    b = float(p[2][1:])
    if family == "capped":
        return b, float(p[3][1:]), 0.0
    return b, float(p[4][1:]), float(p[3][1:])


def worst(d, cells):
    """Worst-cell aggregation of every guarded configuration over the given cells."""
    s = d[d.cell.isin(cells)]
    g = (s.groupby(["policy", "family"], dropna=False)
         .agg(worst_gap=("gap", "min"), worst_harm=("harm", "max"),
              worst_promise=("promise", "max"), mean_gap=("gap", "mean"),
              n_cells=("gap", "size"), max_used=("used_over_allowed", "max"),
              lw_ex_p99=("lw_ex_p99", "max"), lw_ex_max=("lw_ex_max", "max"),
              lw_ratio_max=("lw_ratio_max", "max")).reset_index())
    assert (g.n_cells == len(cells)).all()
    bb = [parse(p, f) for p, f in zip(g.policy, g.family)]
    g["B0_base"], g["eta"], g["gam_base"] = ([x[0] for x in bb], [x[1] for x in bb],
                                             [x[2] for x in bb])
    return g


def pick(g, fam, G, lg=None):
    """Apply the rule to one family at one promise."""
    if fam == "fixed":
        pool = g[(g.family == "fixed") & (g.worst_promise <= G + 1e-9)].copy()
    else:
        pool = g[(g.family == fam) & (g.policy.str.contains(f"-G{G:g}-"))].copy()
    pool["feasible"] = pool.worst_harm <= G * C.HARM_FRAC
    ok = pool[pool.feasible]
    note = ""
    if not len(ok):
        ok = pool.sort_values("worst_harm").head(1)
        note = "NO feasible configuration; fell back to the smallest worst harm"
    best = ok.sort_values(["worst_gap", "worst_harm", "B0_base", "eta", "gam_base"],
                          ascending=[False, True, True, True, True]).iloc[0]
    return pool, best, note


def main():
    lg = C.Log("select")
    frames = []
    for rep in C.VALID_REPS:
        for lev in range(3):
            f = pd.read_csv(os.path.join(C.SIMDIR, f"valid_rep{rep}_L{lev}_grid.csv"))
            s = f.set_index("policy")
            f99, s99 = s.loc["FCFS", "w_p99_dl"], s.loc["SJF-ref", "w_p99_dl"]
            f = f[f.bound_viol >= 0].copy()
            f["cell"] = f"r{rep}L{lev}"
            f["gap"] = (f99 - f.w_p99_dl) / (f99 - s99)
            f["red_pct"] = 100.0 * (f99 - f.w_p99_dl) / f99
            f["harm"] = f.harm_wf1s
            frames.append(f)
    d = pd.concat(frames, ignore_index=True)
    cells = sorted(d.cell.unique())
    assert len(cells) == 15 and int(d.bound_viol.sum()) == 0
    lg.w(f"15 validation cells, {d.policy.nunique()} guarded configurations each, "
         f"{len(d):,} rows, 0 bound violations; k per cell "
         f"{dict(zip(d.cell, d.k))}")
    d.to_csv(os.path.join(C.HERE, "select_cells.csv"), index=False)

    # ---- self-test: capped at eta = 0 is the fixed policy at the same B0 ---------
    # The two are simulated separately (different Bmax, hence different dedup keys), so
    # this is a real check that the grids describe the same policy where they overlap.
    # Metrics are compared with a relative tolerance because a p99 or a mean over 17.6 M
    # float64 waits can land one ulp apart between two runs; the SCHEDULE is then checked
    # exactly, by re-simulating the worst-disagreeing pair and comparing wait vectors.
    n_chk, worst_d, worst_at = 0, 0.0, None
    for cell, s in d.groupby("cell"):
        s = s.set_index("policy")
        for G in C.GS:
            for b in C.ANCHORS:
                a, bnm = f"CAPG-G{G:g}-B{b:g}-e0", f"FIXG-B{b:g}"
                if a in s.index and bnm in s.index and s.loc[a, "B0"] < s.loc[a, "Bmax"]:
                    for col in ("w_p99_dl", "w_mean", "harm_wf1s", "max_excess"):
                        rd = abs(s.loc[a, col] - s.loc[bnm, col]) / max(
                            abs(s.loc[bnm, col]), 1e-12)
                        if rd > worst_d:
                            worst_d, worst_at = rd, (cell, G, b, col, float(s.loc[a, "B0"]),
                                                     float(s.loc[a, "Bmax"]),
                                                     float(s.loc[bnm, "Bmax"]))
                    n_chk += 1
    assert worst_d < 1e-9, f"capped eta=0 != fixed at the same B0 (max rel diff {worst_d})"
    lg.w(f"self-test: {n_chk} (cell, G, B0) pairs where the capped family at eta = 0 and "
         f"the fixed family carry the same budget; max relative metric difference "
         f"{worst_d:.3g} at {worst_at}")
    if worst_at is not None and worst_d > 0:
        cell, G, b, col, B0, bmc, bmf = worst_at
        rep, lev = int(cell[1]), int(cell[3])
        Z = C.load_trace("valid", rep)
        k = int(list(Z["K"])[lev])
        ws = [C.GK.run(Z["a"], Z["svc"], k, "guard", pred=Z["tweedie"], B=B0, eps=0.0,
                       Bmax=bm, Mslots=C.MSLOTS).w for bm in (bmc, bmf)]
        nd = int((ws[0] != ws[1]).sum())
        lg.w(f"  exact check on that pair (re-simulated, {len(Z['a']):,} jobs, k={k}): "
             f"differing jobs {nd}, max |diff| {float(np.abs(ws[0] - ws[1]).max()):g} -- "
             f"the schedules are identical; the metric difference is float noise in a "
             f"quantile/mean over 17.6 M values, not a policy difference")
        assert nd == 0
        del ws, Z

    g = worst(d, cells)
    g.sort_values(["family", "B0_base", "eta", "gam_base"]).to_csv(
        os.path.join(C.HERE, "select_worst.csv"), index=False)
    rows, fr, sens = [], [], []
    for G in C.GS:
        lg.w(f"\n=== G = {G:g} s   (harm limit {G * C.HARM_FRAC:g} s, 15 cells) ===")
        for fam in FAMS:
            pool, best, note = pick(g, fam, G)
            pool = pool.assign(G=G)
            fr.append(pool[["G", "family", "policy", "B0_base", "eta", "gam_base",
                            "worst_gap", "worst_harm", "worst_promise", "feasible"]])
            nxt = pool[(pool.worst_gap > best.worst_gap)].sort_values("worst_gap")
            nxt_s = ("none: the chosen point has the best worst-cell gap in the family"
                     if not len(nxt) else
                     f"{nxt.iloc[0].policy} (gap {nxt.iloc[0].worst_gap:.4f}, harm "
                     f"{nxt.iloc[0].worst_harm:.1f} s, infeasible by "
                     f"{nxt.iloc[0].worst_harm - G * C.HARM_FRAC:.1f} s)")
            rows.append(dict(family=fam, G=G, B0_base=float(best.B0_base),
                             eta=float(best.eta), gam_base=float(best.gam_base),
                             policy=best.policy, worst_gap=round(float(best.worst_gap), 4),
                             worst_harm_s=round(float(best.worst_harm), 2),
                             harm_limit_s=G * C.HARM_FRAC,
                             harm_slack_s=round(G * C.HARM_FRAC - float(best.worst_harm), 2),
                             binds=bool(G * C.HARM_FRAC - float(best.worst_harm) <
                                        0.05 * G * C.HARM_FRAC),
                             worst_promise_s=round(float(best.worst_promise), 1),
                             n_feasible=int(pool.feasible.sum()), n_grid=len(pool),
                             next_better_point=nxt_s, note=note))
            lg.w(f"  [{fam:7s}] grid {len(pool):3d} points, {int(pool.feasible.sum()):3d} "
                 f"feasible -> {best.policy}: worst-cell gap {best.worst_gap:.4f}, harm "
                 f"{best.worst_harm:.2f} s (limit {G * C.HARM_FRAC:g}, slack "
                 f"{G * C.HARM_FRAC - best.worst_harm:.2f} s), promise "
                 f"{best.worst_promise:.1f} s {note}")
            lg.w(f"            next point with a better worst-cell gap: {nxt_s}")
        # ---- G4 sensitivity: drop the single flagged validation cell -------------
        keep = [c for c in cells if c != f"r{C.DROP_CELL[0]}L{C.DROP_CELL[1]}"]
        g2 = worst(d, keep)
        for fam in FAMS:
            _, b2, _ = pick(g2, fam, G)
            _, b1, _ = pick(g, fam, G)
            sens.append(dict(G=G, family=fam, with_all_cells=b1.policy,
                             gap_all=round(float(b1.worst_gap), 4),
                             harm_all=round(float(b1.worst_harm), 2),
                             dropping_r1L2=b2.policy,
                             gap_drop=round(float(b2.worst_gap), 4),
                             harm_drop=round(float(b2.worst_harm), 2),
                             same=bool(b1.policy == b2.policy)))
    pd.concat(fr, ignore_index=True).to_csv(os.path.join(C.HERE, "frontier.csv"),
                                            index=False)
    t = pd.DataFrame(rows)
    t.to_csv(os.path.join(C.HERE, "selected_params.csv"), index=False)
    s = pd.DataFrame(sens)
    s.to_csv(os.path.join(C.HERE, "select_sensitivity.csv"), index=False)
    lg.w("\n=== selected parameters (validation overlays only) ===")
    lg.w(t.drop(columns=["next_better_point"]).to_string(index=False))
    lg.w("\n=== sensitivity: selection with the single flagged cell (overlay 1, level 2) "
         "dropped ===")
    lg.w(s.to_string(index=False))
    lg.w("\n=== winner across the three families, per G ===")
    for G in C.GS:
        z = t[t.G == G].sort_values(["worst_gap", "worst_harm_s"],
                                    ascending=[False, True])
        lg.w(f"  G = {G:6g}: " + " > ".join(
            f"{r.family}({r.policy}, gap {r.worst_gap:.4f}, harm {r.worst_harm_s:.1f})"
            for r in z.itertuples()))
    lg.close()


if __name__ == "__main__":
    main()
