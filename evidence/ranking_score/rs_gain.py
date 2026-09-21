"""Gains and paired week-block bootstrap CIs, as service_precheck_v2.stage_p2boot.

A resample draws whole weeks of the overlay timeline with replacement (the trace's week
set); every policy, level, overlay rep and policy GROUP of a trace uses the same draws
(SP.boot_weights is a pure function of the week count), so replicates are paired across
groups too.  Per resample: gain_r = (FCFS_r - policy_r) / (FCFS_r - SJF-ref_r) on overlay r,
averaged over the reps; the point gain uses the full trace.  CI = 2.5 / 97.5% of the
resamples.  A difference is gain(a) - gain(b), with b = SPJF-M4 (the current score);
"resolved" when its CI excludes 0.

usage: rs_gain.py --trace primary --reps 0,1
"""
from __future__ import annotations

import argparse
import glob
import os
import re

import numpy as np
import pandas as pd

import rs_common as C
from rs_common import SP, say

OUT = os.path.join(C.WORK, "sim")
BASE = "SPJF-M4"
METRICS = (("p99dl", "w_p99_dl"), ("mean", "w_mean"))


def load(trace, rep, rho):
    csv, bw = {}, {}
    for f in sorted(glob.glob(os.path.join(OUT, f"rs_{trace}_rep{rep}_r{rho:g}_*.csv"))):
        g = re.search(r"_r[0-9.]+_(\w+)\.csv$", f).group(1)
        d = pd.read_csv(f).set_index("policy")
        z = np.load(f.replace(".csv", ".npz").replace("rs_", "rsbw_"))
        for p in d.index:
            if p not in csv:
                csv[p], bw[p] = d.loc[p], {m: z[f"{m}|{p}"] for m, _ in METRICS}
    return csv, bw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace", default="primary")
    ap.add_argument("--reps", default="0,1")
    a = ap.parse_args()
    reps = [int(x) for x in a.reps.split(",")]

    grows, drows = [], []
    for rho in SP.RHOS:
        L = {r: load(a.trace, r, rho) for r in reps}
        pols = [p for p in L[reps[0]][0] if all(p in L[r][0] for r in reps)]
        for mk, col in METRICS:
            Fp = np.array([L[r][0]["FCFS"][col] for r in reps], float)
            Sp = np.array([L[r][0]["SJF-ref"][col] for r in reps], float)
            Fb = np.array([L[r][1]["FCFS"][mk] for r in reps])
            Sb = np.array([L[r][1]["SJF-ref"][mk] for r in reps])
            den = float(np.mean(Fp - Sp))
            gb, gp = {}, {}
            for p in pols:
                Pp = np.array([L[r][0][p][col] for r in reps], float)
                Pb = np.array([L[r][1][p][mk] for r in reps])
                with np.errstate(divide="ignore", invalid="ignore"):
                    gb[p] = np.mean((Fb - Pb) / (Fb - Sb), axis=0)
                gp[p] = float(np.mean((Fp - Pp) / (Fp - Sp)))
                fin = np.isfinite(gb[p])
                grows.append(dict(trace=a.trace, reps=a.reps, rho=rho, metric=mk, policy=p,
                                  k=float(np.mean([L[r][0][p]["k"] for r in reps])),
                                  wait=float(np.mean(Pp)), gain=gp[p],
                                  lo=float(np.percentile(gb[p][fin], 2.5)),
                                  hi=float(np.percentile(gb[p][fin], 97.5)),
                                  fcfs_minus_sjf=den))
            for p in pols:
                if p == BASE:
                    continue
                dd = gb[p] - gb[BASE]
                fin = np.isfinite(dd)
                lo, hi = float(np.percentile(dd[fin], 2.5)), float(np.percentile(dd[fin], 97.5))
                wa = np.array([L[r][0][p][col] for r in reps], float).mean()
                wb = np.array([L[r][0][BASE][col] for r in reps], float).mean()
                drows.append(dict(trace=a.trace, reps=a.reps, rho=rho, metric=mk,
                                  pair=f"{p} - {BASE}", d_gain=gp[p] - gp[BASE], lo=lo, hi=hi,
                                  resolved=bool(lo > 0 or hi < 0),
                                  verdict=(f"{p} better" if lo > 0 else f"{BASE} better" if hi < 0
                                           else "unresolved"),
                                  wait=wa, wait_base=wb, d_wait_pct=100.0 * (wa - wb) / wb))
    g, d = pd.DataFrame(grows), pd.DataFrame(drows)
    g.to_csv(f"{C.HERE}/gain_{a.trace}.csv", index=False)
    d.to_csv(f"{C.HERE}/gaindiff_{a.trace}.csv", index=False)
    for mk, _ in METRICS:
        z = g[g.metric == mk].assign(cell=lambda x: [f"{v:.4f} [{l:.4f},{h:.4f}]"
                                                     for v, l, h in zip(x.gain, x.lo, x.hi)])
        say(f"\n=== {a.trace}, reps {a.reps}: gain on {mk} (point [95% week-block CI]) ===")
        say(z.pivot_table(index="policy", columns="rho", values="cell", aggfunc="first",
                          sort=False).to_string())
        y = g[g.metric == mk].assign(cell=lambda x: x.wait.round(4))
        say(f"\nwait (s), {mk}:")
        say(y.pivot_table(index="policy", columns="rho", values="cell", aggfunc="first",
                          sort=False).to_string())
    say(f"\n=== differences of the gain against {BASE} (paired week-block bootstrap) ===")
    say(d.round(4).to_string(index=False))


if __name__ == "__main__":
    main()
