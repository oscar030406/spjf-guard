"""Stage 4 (v3.1): gains, week-block paired bootstrap CIs, and the reported tables.

Identical machinery to v3 (SP.boot_weights: whole weeks of the overlay timeline drawn
with replacement, the same 2,000 draws for every policy, level and overlay, so replicates
are paired).  The difference list gains the comparisons v3.1 exists to make: the capped
relative budget against the best FEASIBLE fixed budget at the same promise, and the
dispatch-charged finite skip against v3's completion-charged one.

usage: v31_gain.py --trace primary --reps 0,1,2,3,4
"""
from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd

import v31_common as C

METRICS = (("p99dl", "w_p99_dl"), ("mean", "w_mean"))


def pairs(pols):
    out = []
    if "SPJF-M4" in pols and "SPJF-tweedie" in pols:
        out.append(("SPJF-tweedie", "SPJF-M4", "ranking score: Tweedie vs current log M4"))
    if "SPJF-M4refit" in pols:
        out.append(("SPJF-M4refit", "SPJF-M4", "refit-noise control: same score, refit"))
    if "SPJF-r1s" in pols:
        out.append(("SPJF-r1s", "SPJF-tweedie", "R1S-Tweedie vs Tweedie"))
    if "SPJF-r1s" in pols and "SPJF-tweedie_itr" in pols:
        out.append(("SPJF-r1s", "SPJF-tweedie_itr",
                    "R1S vs the Tweedie control on the same 90% of rows"))
    for G in C.GS:
        cap, fix, fsl = f"CAP-G{G:g}", f"FIX-G{G:g}", f"FIXSEL-G{G:g}"
        skp, skc = f"SKIP-G{G:g}", f"SKIPC-G{G:g}"
        if cap in pols and fsl in pols:
            out.append((cap, fsl, f"capped relative vs the BEST FEASIBLE fixed budget, "
                                  f"G = {G:g} s"))
        if cap in pols and fix in pols:
            out.append((cap, fix, f"capped relative vs B0 = Bmax at G = {G:g} s"))
        if cap in pols:
            out.append((cap, "SPJF-tweedie", f"guard vs unguarded, G = {G:g} s"))
        if skp in pols:
            out.append((skp, "SPJF-tweedie", f"finite skip vs unguarded at G = {G:g} s"))
            out.append((cap, skp, f"capped relative vs finite skip at G = {G:g} s"))
        if skp in pols and skc in pols:
            out.append((skp, skc, f"finite skip: dispatch vs completion charge, "
                                  f"G = {G:g} s"))
    for adv in ("reversed", "random", "top1short"):
        a, b = f"CAP-G{C.ADV_G:g}-{adv}", f"SPJF-{adv}"
        if a in pols and b in pols:
            out.append((a, b, f"guard vs unguarded under the {adv} predictor"))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace", default="primary")
    ap.add_argument("--reps", default="0,1,2,3,4")
    ap.add_argument("--levels", default="0,1,2")
    a = ap.parse_args()
    reps = [int(x) for x in a.reps.split(",")]
    levs = [int(x) for x in a.levels.split(",")]

    lg = C.Log("gain")
    grows, drows, trows = [], [], []
    for lev in levs:
        cs, bw = {}, {}
        for r in reps:
            tag = f"{a.trace}_rep{r}_L{lev}_main"
            cs[r] = pd.read_csv(os.path.join(C.SIMDIR, f"{tag}.csv")).set_index("policy")
            z = np.load(os.path.join(C.SIMDIR, f"bw_{tag}.npz"))
            bw[r] = {p: {m: z[f"{m}|{p}"] for m, _ in METRICS} for p in cs[r].index}
        pols = [p for p in cs[reps[0]].index if all(p in cs[r].index for r in reps)]
        assert int(cs[reps[0]].loc[pols, "bound_viol"].max()) == 0
        for mk, col in METRICS:
            F = np.array([cs[r].loc["FCFS", col] for r in reps], float)
            S = np.array([cs[r].loc["SJF-ref", col] for r in reps], float)
            Fb = np.array([bw[r]["FCFS"][mk] for r in reps])
            Sb = np.array([bw[r]["SJF-ref"][mk] for r in reps])
            gb, rb, gp, rp = {}, {}, {}, {}
            for p in pols:
                P = np.array([cs[r].loc[p, col] for r in reps], float)
                Pb = np.array([bw[r][p][mk] for r in reps])
                with np.errstate(divide="ignore", invalid="ignore"):
                    gb[p] = np.mean((Fb - Pb) / (Fb - Sb), axis=0)
                    rb[p] = np.mean(100.0 * (Fb - Pb) / Fb, axis=0)
                gp[p] = float(np.mean((F - P) / (F - S)))
                rp[p] = float(np.mean(100.0 * (F - P) / F))
                fg, fr = np.isfinite(gb[p]), np.isfinite(rb[p])
                grows.append(dict(
                    trace=a.trace, reps=a.reps, level=lev,
                    rho_target=float(cs[reps[0]].loc[p, "rho_target"]),
                    k=float(np.mean([cs[r].loc[p, "k"] for r in reps])), metric=mk,
                    policy=p, wait=float(P.mean()), gain=gp[p],
                    gain_lo=float(np.percentile(gb[p][fg], 2.5)),
                    gain_hi=float(np.percentile(gb[p][fg], 97.5)),
                    red_pct=rp[p], red_lo=float(np.percentile(rb[p][fr], 2.5)),
                    red_hi=float(np.percentile(rb[p][fr], 97.5)),
                    fcfs=float(F.mean()), sjf=float(S.mean())))
            for x, y, lab in pairs(pols):
                for nm, bb, pp in (("gain", gb, gp), ("red_pct", rb, rp)):
                    dd = bb[x] - bb[y]
                    fin = np.isfinite(dd)
                    lo = float(np.percentile(dd[fin], 2.5))
                    hi = float(np.percentile(dd[fin], 97.5))
                    drows.append(dict(trace=a.trace, level=lev, metric=mk, quantity=nm,
                                      pair=f"{x} - {y}", label=lab,
                                      diff=pp[x] - pp[y], lo=lo, hi=hi,
                                      resolved=bool(lo > 0 or hi < 0),
                                      verdict=(f"{x} better" if lo > 0 else
                                               f"{y} better" if hi < 0 else "unresolved")))
        for p in pols:
            m = {c: float(np.mean([cs[r].loc[p, c] for r in reps])) for c in
                 ("w_p99_dl", "w_mean", "w_p99", "qw_forced_frac", "guar_excess_max", "k")}
            w = {c: float(np.max([cs[r].loc[p, c] for r in reps])) for c in
                 ("max_excess", "harm_wf1s", "max_heavy", "used_over_allowed")}
            g99 = [x for x in grows if x["level"] == lev and x["policy"] == p
                   and x["metric"] == "p99dl"][0]
            gme = [x for x in grows if x["level"] == lev and x["policy"] == p
                   and x["metric"] == "mean"][0]
            trows.append(dict(trace=a.trace, level=lev,
                              rho_target=float(cs[reps[0]].loc[p, "rho_target"]),
                              k=m["k"], policy=p, score=cs[reps[0]].loc[p, "score"],
                              guard=cs[reps[0]].loc[p, "guard"],
                              G=cs[reps[0]].loc[p, "G"], B0=cs[reps[0]].loc[p, "B0"],
                              eta=cs[reps[0]].loc[p, "eta"], Bmax=cs[reps[0]].loc[p, "Bmax"],
                              Ncap=cs[reps[0]].loc[p, "Ncap"],
                              p99_dl_s=m["w_p99_dl"], gap_closed=g99["gain"],
                              gap_lo=g99["gain_lo"], gap_hi=g99["gain_hi"],
                              red_pct=g99["red_pct"], red_lo=g99["red_lo"],
                              red_hi=g99["red_hi"], mean_s=m["w_mean"],
                              mean_gap=gme["gain"], mean_gap_lo=gme["gain_lo"],
                              mean_gap_hi=gme["gain_hi"], mean_red_pct=gme["red_pct"],
                              p99_all_s=m["w_p99"], max_excess_s=w["max_excess"],
                              harm_wf1s_s=w["harm_wf1s"], max_heavy_s=w["max_heavy"],
                              qw_fired=m["qw_forced_frac"],
                              used_over_allowed=w["used_over_allowed"],
                              guar_excess_s=m["guar_excess_max"]))
    g, d, t = pd.DataFrame(grows), pd.DataFrame(drows), pd.DataFrame(trows)
    g.to_csv(os.path.join(C.HERE, f"gain_{a.trace}.csv"), index=False)
    d.to_csv(os.path.join(C.HERE, f"gaindiff_{a.trace}.csv"), index=False)
    t.to_csv(os.path.join(C.HERE, f"table_main_{a.trace}.csv"), index=False)
    for mk, _ in METRICS:
        z = g[g.metric == mk].assign(
            cell=lambda x: [f"{v:.4f} [{l:.4f},{h:.4f}]" for v, l, h in
                            zip(x.gain, x.gain_lo, x.gain_hi)])
        lg.w(f"\n=== {a.trace}, reps {a.reps}: gap closed on {mk} "
             f"(point [95% week-block CI]) ===")
        lg.w(z.pivot_table(index="policy", columns="level", values="cell",
                           aggfunc="first", sort=False).to_string())
    lg.w("\n=== differences (paired week-block bootstrap, gap closed on p99dl) ===")
    dd = d[(d.metric == "p99dl") & (d.quantity == "gain")]
    lg.w(dd[["level", "pair", "label", "diff", "lo", "hi", "resolved", "verdict"]]
         .round(4).to_string(index=False))
    lg.w("\n=== per-job guarantee: worst used/allowed and worst harm over the overlays ===")
    lg.w(t[t.G > 0][["level", "k", "policy", "G", "B0", "eta", "Bmax", "Ncap",
                     "guar_excess_s", "max_excess_s", "used_over_allowed", "harm_wf1s_s"]]
         .round(4).to_string(index=False))
    lg.close()


if __name__ == "__main__":
    main()
