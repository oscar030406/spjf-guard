"""Stage 4 (v3.2): gains, week-block paired bootstrap CIs, and the reported tables.

Machinery unchanged from v3/v3.1 (SP.boot_weights: whole weeks of the overlay timeline
drawn with replacement, the same 2,000 draws for every policy, level and overlay).  Two
additions:

  * CAP - FIXSEL is carried as a first-class paired difference in every (G, load) cell --
    that is the comparison the verifier's G1 says v3.1 got wrong by searching the two
    families unequally;
  * every table row carries its parameters PER OVERLAY (k, B0, Bmax, Ncap), because the
    overlays do not all run the same k -- overlays 0-3 run k = 8/5/4 and overlay 4 runs
    k = 7/5/4, and every budget and skip count scales with k (verifier finding G3).

usage: v32_gain.py --trace primary --reps 0,1,2,3,4
"""
from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd

import v32_common as C

METRICS = (("p99dl", "w_p99_dl"), ("mean", "w_mean"))
LW = ("lw_n", "lw_ex_mean", "lw_ex_p50", "lw_ex_p90", "lw_ex_p99", "lw_ex_max",
      "lw_ratio_p99", "lw_ratio_max")


def pairs(pols):
    out = []
    if "SPJF-M4" in pols and "SPJF-tweedie" in pols:
        out.append(("SPJF-tweedie", "SPJF-M4", "ranking score: Tweedie vs log M4"))
    if "SPJF-M4refit" in pols:
        out.append(("SPJF-M4refit", "SPJF-M4", "refit-noise control"))
    if "SPJF-r1s" in pols:
        out.append(("SPJF-r1s", "SPJF-tweedie", "R1S-Tweedie vs Tweedie"))
    for G in C.GS:
        cap, fsl, fix = f"CAP-G{G:g}", f"FIXSEL-G{G:g}", f"FIX-G{G:g}"
        hyb, skp = f"HYB-G{G:g}", f"SKIP-G{G:g}"
        if cap in pols and fsl in pols:
            out.append((cap, fsl, f"capped relative vs the selected fixed budget, "
                                  f"equal grids, G = {G:g} s"))
        if cap in pols and fix in pols:
            out.append((cap, fix, f"capped relative vs the equal-promise fixed budget "
                                  f"B0 = Bmax, G = {G:g} s"))
        if hyb in pols and cap in pols:
            out.append((hyb, cap, f"hybrid (queue-length term) vs capped, G = {G:g} s"))
        if hyb in pols and fsl in pols:
            out.append((hyb, fsl, f"hybrid vs the selected fixed budget, G = {G:g} s"))
        if fsl in pols and fix in pols:
            out.append((fsl, fix, f"selected fixed budget vs B0 = Bmax, G = {G:g} s"))
        if cap in pols:
            out.append((cap, "SPJF-tweedie", f"guard vs unguarded, G = {G:g} s"))
        if skp in pols and cap in pols:
            out.append((cap, skp, f"capped relative vs finite skip, G = {G:g} s"))
    for adv in ("reversed", "random", "top1short"):
        a, b = f"CAP-G{C.ADV_G:g}-{adv}", f"SPJF-{adv}"
        if a in pols and b in pols:
            out.append((a, b, f"guard vs unguarded under the {adv} predictor"))
    return out


def byov(cs, reps, p, col, fmt="{:g}"):
    """The per-overlay values of a parameter, as 'v0/v1/.../v4' (verifier G3)."""
    v = [cs[r].loc[p, col] for r in reps]
    return "/".join(fmt.format(x) for x in v)


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
                    trace=a.trace, level=lev,
                    rho_target=float(cs[reps[0]].loc[p, "rho_target"]),
                    k=float(np.mean([cs[r].loc[p, "k"] for r in reps])), metric=mk,
                    policy=p, wait=float(P.mean()), gain=gp[p],
                    gain_lo=float(np.percentile(gb[p][fg], 2.5)),
                    gain_hi=float(np.percentile(gb[p][fg], 97.5)),
                    red_pct=rp[p], red_lo=float(np.percentile(rb[p][fr], 2.5)),
                    red_hi=float(np.percentile(rb[p][fr], 97.5))))
            for x, y, lab in pairs(pols):
                for nm, bb, pp in (("gain", gb, gp), ("red_pct", rb, rp)):
                    dd = bb[x] - bb[y]
                    fin = np.isfinite(dd)
                    lo = float(np.percentile(dd[fin], 2.5))
                    hi = float(np.percentile(dd[fin], 97.5))
                    drows.append(dict(trace=a.trace, level=lev,
                                      rho_target=float(cs[reps[0]].loc[x, "rho_target"]),
                                      metric=mk, quantity=nm, pair=f"{x} - {y}",
                                      label=lab, diff=pp[x] - pp[y], lo=lo, hi=hi,
                                      resolved=bool(lo > 0 or hi < 0),
                                      verdict=(f"{x} better" if lo > 0 else
                                               f"{y} better" if hi < 0 else
                                               "unresolved")))
        for p in pols:
            m = {c: float(np.mean([cs[r].loc[p, c] for r in reps])) for c in
                 ("w_p99_dl", "w_mean", "w_p99", "qw_forced_frac", "guar_excess_max",
                  "k", "lw_ex_mean", "lw_ex_p50", "lw_ex_p90", "lw_ex_p99")}
            wo = {c: float(np.max([cs[r].loc[p, c] for r in reps])) for c in
                  ("max_excess", "harm_wf1s", "max_heavy", "used_over_allowed",
                   "lw_ex_max", "lw_ratio_p99", "lw_ratio_max")}
            g99 = [x for x in grows if x["level"] == lev and x["policy"] == p
                   and x["metric"] == "p99dl"][0]
            gme = [x for x in grows if x["level"] == lev and x["policy"] == p
                   and x["metric"] == "mean"][0]
            trows.append(dict(trace=a.trace, level=lev,
                              rho_target=float(cs[reps[0]].loc[p, "rho_target"]),
                              k=m["k"], k_by_overlay=byov(cs, reps, p, "k", "{:.0f}"),
                              policy=p, score=cs[reps[0]].loc[p, "score"],
                              family=cs[reps[0]].loc[p, "family"],
                              G=cs[reps[0]].loc[p, "G"],
                              B0_by_overlay=byov(cs, reps, p, "B0"),
                              eta=cs[reps[0]].loc[p, "eta"],
                              gam_by_overlay=byov(cs, reps, p, "gam"),
                              Bmax_by_overlay=byov(cs, reps, p, "Bmax"),
                              Ncap_by_overlay=byov(cs, reps, p, "Ncap", "{:.0f}"),
                              promise_by_overlay=byov(cs, reps, p, "promise", "{:.1f}"),
                              p99_dl_s=m["w_p99_dl"], gap_closed=g99["gain"],
                              gap_lo=g99["gain_lo"], gap_hi=g99["gain_hi"],
                              red_pct=g99["red_pct"], red_lo=g99["red_lo"],
                              red_hi=g99["red_hi"], mean_s=m["w_mean"],
                              mean_gap=gme["gain"], mean_gap_lo=gme["gain_lo"],
                              mean_gap_hi=gme["gain_hi"], p99_all_s=m["w_p99"],
                              max_excess_s=wo["max_excess"],
                              harm_wf1s_s=wo["harm_wf1s"], max_heavy_s=wo["max_heavy"],
                              lw_ex_mean=m["lw_ex_mean"], lw_ex_p50=m["lw_ex_p50"],
                              lw_ex_p90=m["lw_ex_p90"], lw_ex_p99=m["lw_ex_p99"],
                              lw_ex_max=wo["lw_ex_max"], lw_ratio_p99=wo["lw_ratio_p99"],
                              lw_ratio_max=wo["lw_ratio_max"],
                              qw_fired=m["qw_forced_frac"],
                              used_over_allowed=wo["used_over_allowed"],
                              guar_excess_s=m["guar_excess_max"]))
    g, d, t = pd.DataFrame(grows), pd.DataFrame(drows), pd.DataFrame(trows)
    g.to_csv(os.path.join(C.HERE, f"gain_{a.trace}.csv"), index=False)
    d.to_csv(os.path.join(C.HERE, f"gaindiff_{a.trace}.csv"), index=False)
    t.to_csv(os.path.join(C.HERE, f"table_main_{a.trace}.csv"), index=False)
    z = g[g.metric == "p99dl"].assign(
        cell=lambda x: [f"{v:.4f} [{l:.4f},{h:.4f}]" for v, l, h in
                        zip(x.gain, x.gain_lo, x.gain_hi)])
    lg.w(f"\n=== {a.trace}: gap closed on p99dl (point [95% week-block CI]) ===")
    lg.w(z.pivot_table(index="policy", columns="level", values="cell", aggfunc="first",
                       sort=False).to_string())
    lg.w("\n=== paired differences, gap closed on p99dl ===")
    dd = d[(d.metric == "p99dl") & (d.quantity == "gain")]
    lg.w(dd[["level", "rho_target", "pair", "diff", "lo", "hi", "resolved", "verdict"]]
         .round(4).to_string(index=False))
    lg.w("\n=== excess among jobs FCFS already makes wait (W_FCFS > 60 s) ===")
    lg.w(t[t.G > 0][["level", "policy", "lw_ex_mean", "lw_ex_p50", "lw_ex_p90",
                     "lw_ex_p99", "lw_ex_max", "lw_ratio_p99", "lw_ratio_max"]]
         .round(3).to_string(index=False))
    lg.w("\n=== parameters per overlay (overlays do not all run the same k) ===")
    lg.w(t[t.G > 0][["level", "policy", "k_by_overlay", "B0_by_overlay",
                     "Bmax_by_overlay", "Ncap_by_overlay", "promise_by_overlay"]]
         .to_string(index=False))
    lg.close()


if __name__ == "__main__":
    main()
