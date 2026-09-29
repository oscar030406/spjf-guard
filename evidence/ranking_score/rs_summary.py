"""Final tables: scheduling results per policy (waits averaged over the overlay reps, gain
with its week-block CI, and the difference of the gain against the current SPJF-M4 score),
and the misranking decomposition.

usage: rs_summary.py --trace primary --reps 0,1,2,3,4 --suffix 5reps
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
ORDER = ["FCFS", "SJF-ref", "SPJF-M4", "SPJF-M4refit", "SPJF-tweedie", "SPJF-gamma",
         "SPJF-hurdle", "SPJF-phv", "SPJF-logvar", "SPJF-q99", "SPJF-q90", "SPJF-q50",
         "SPJF-l2raw"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace", default="primary")
    ap.add_argument("--reps", default="0,1,2,3,4")
    ap.add_argument("--suffix", default="5reps")
    a = ap.parse_args()
    reps = [int(x) for x in a.reps.split(",")]

    rows = []
    for f in sorted(glob.glob(os.path.join(OUT, f"rs_{a.trace}_rep*_r*_*.csv"))):
        r = int(re.search(r"_rep(\d+)_", f).group(1))
        if r in reps:
            rows.append(pd.read_csv(f))
    d = pd.concat(rows, ignore_index=True).drop_duplicates(["rep", "rho_target", "policy"])
    n = d.groupby(["rho_target", "policy"]).rep.nunique()
    keep = set(n[n == len(reps)].index.get_level_values(1))
    d = d[d.policy.isin(keep)]
    g = pd.read_csv(f"{C.HERE}/gain_{a.trace}_{a.suffix}.csv") if os.path.exists(
        f"{C.HERE}/gain_{a.trace}_{a.suffix}.csv") else pd.read_csv(f"{C.HERE}/gain_{a.trace}.csv")
    dg = pd.read_csv(f"{C.HERE}/gaindiff_{a.trace}_{a.suffix}.csv") if os.path.exists(
        f"{C.HERE}/gaindiff_{a.trace}_{a.suffix}.csv") else pd.read_csv(f"{C.HERE}/gaindiff_{a.trace}.csv")
    G = {(r.rho, r.metric, r.policy): r for r in g.itertuples()}
    Dg = {(r.rho, r.metric, r.pair.split(" - ")[0]): r for r in dg.itertuples()}

    m = d.groupby(["rho_target", "policy"]).agg(
        k=("k", "mean"), p99_dl=("w_p99_dl", "mean"), mean=("w_mean", "mean"),
        p99=("w_p99", "mean"), max_heavy=("max_heavy", "mean"),
        p99_heavy=("p99_heavy", "mean"), p99_exam=("w_p99_exam", "mean")).reset_index()
    out = []
    for _, r in m.iterrows():
        row = dict(trace=a.trace, reps=a.reps, rho=r.rho_target, k=int(r.k), policy=r.policy,
                   p99_dl_s=round(r.p99_dl, 4), mean_s=round(r["mean"], 4), p99_s=round(r.p99, 4),
                   max_heavy_s=round(r.max_heavy, 1), p99_heavy_s=round(r.p99_heavy, 2),
                   p99_exam_s=round(r.p99_exam, 4))
        for mk, tag in (("p99dl", "p99dl"), ("mean", "mean")):
            k = (r.rho_target, mk, r.policy)
            row[f"gain_{tag}"] = (f"{G[k].gain:.4f} [{G[k].lo:.4f},{G[k].hi:.4f}]" if k in G else "")
            q = Dg.get(k)
            row[f"dgain_{tag}_vs_M4"] = (f"{q.d_gain:+.4f} [{q.lo:+.4f},{q.hi:+.4f}]"
                                         f"{'' if q.resolved else ' ns'}" if q else "")
        out.append(row)
    T = pd.DataFrame(out)
    T["ord"] = [ORDER.index(p) if p in ORDER else 100 + i for i, p in enumerate(T.policy)]
    T = T.sort_values(["rho", "ord"]).drop(columns="ord")
    T.to_csv(f"{C.HERE}/table_{a.trace}_{a.suffix}.csv", index=False)
    for rho in SP.RHOS:
        z = T[T.rho == rho]
        say(f"\n=== {a.trace}, reps {a.reps}, busy-hour rho target {rho} (k = {z.k.iloc[0]}) ===")
        say(z.drop(columns=["trace", "reps", "rho", "k"]).to_string(index=False))


if __name__ == "__main__":
    main()
