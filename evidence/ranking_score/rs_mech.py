"""Where the ranking scores differ, and why the raw-scale mean score helps.

1. Misranking profile per target semester: the percentile rank each score gives to the
   truly-heavy jobs (low rank = dispatched early = blocks the queue) and to the truly-light
   ones, plus the count of truly-heavy jobs ranked in the bottom half.
2. Is the Tweedie score the log score plus a conditional-spread correction?  Spearman of
   each score against the other, and the correlation of the rank SHIFT (Tweedie rank minus
   log rank, in percentile points) with the estimated conditional variance s2 of the log
   residual (the logvar model's second stage) and with the classifier's P(heavy).
3. The realised cost of the two error directions, in job-seconds put in front of others:
   sum over truly-heavy jobs of C_cap x (1 - percentile rank) is a proxy for the work a
   score lets jump the queue.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

import rs_common as C
from rs_common import SP, say

SC = ["log", "tweedie", "gamma", "hurdle", "phv", "q50", "q90", "q99", "l2raw", "logvar"]


def pct_rank(v):
    r = np.empty(len(v))
    r[np.argsort(v, kind="stable")] = np.arange(len(v))
    return r / max(1, len(v) - 1)


def main():
    ev, D, S, X, arr, avail = C.load_base()
    sidx = D["sidx"]
    sem = D["sem"][sidx]
    Ccap = np.minimum(D["C"][sidx], SP.L_CAP)
    thr = D["heavy_thr"]
    P = pd.read_parquet(C.PRED_PARQUET)

    say("=== 1. percentile rank the score gives (0 = first to run); target semesters ===")
    rows = []
    for s in C.POOL:
        m = sem == s
        y, hv = Ccap[m], Ccap[m] > thr
        for nm in SC:
            r = pct_rank(P[nm].values[m])
            rows.append(dict(target=s, score=nm, n_heavy=int(hv.sum()),
                             heavy_rank_med=round(float(np.median(r[hv])), 4),
                             heavy_rank_p10=round(float(np.quantile(r[hv], .10)), 4),
                             heavy_in_bottom_half=int((r[hv] < 0.5).sum()),
                             light_rank_med=round(float(np.median(r[~hv])), 4),
                             light_in_top_2pct=int((r[~hv] > 0.98).sum()),
                             heavy_work_jumping=round(float((y[hv] * (1.0 - r[hv])).sum()), 1),
                             work_all=round(float(y.sum()), 1)))
    t1 = pd.DataFrame(rows)
    t1.to_csv(f"{C.HERE}/mech_rank_profile.csv", index=False)
    for s in (C.VALID_SEM, C.TEST_SEM):
        say(f"\n[{s}]")
        say(t1[t1.target == s].drop(columns="target").to_string(index=False))

    say("\n=== 2. Tweedie vs log: what the rank shift tracks ===")
    say("s2 = the fitted conditional variance of the log residual (logvar second stage),")
    say("recovered as 2 (logvar - log); shift = tweedie percentile rank - log percentile rank.")
    rows = []
    for s in C.POOL:
        m = sem == s
        lg, tw = P["log"].values[m], P["tweedie"].values[m]
        s2 = 2.0 * (P["logvar"].values[m] - lg)
        sh = pct_rank(tw) - pct_rank(lg)
        y = Ccap[m]
        up = sh > 0
        rows.append(dict(target=s, spearman_tw_log=round(float(spearmanr(tw, lg).statistic), 4),
                         spearman_shift_s2=round(float(spearmanr(sh, s2).statistic), 4),
                         spearman_shift_phv=round(float(spearmanr(sh, P["phv"].values[m]).statistic), 4),
                         mean_abs_shift=round(float(np.abs(sh).mean()), 4),
                         mean_C_moved_later=round(float(y[up].mean()), 4),
                         mean_C_moved_earlier=round(float(y[~up].mean()), 4),
                         s2_mean=round(float(s2.mean()), 4)))
    t2 = pd.DataFrame(rows)
    t2.to_csv(f"{C.HERE}/mech_tweedie_vs_log.csv", index=False)
    say(t2.to_string(index=False))

    say("\n=== 3. heavy work let through early, as a share of all work (lower is better) ===")
    p = t1.assign(share=(t1.heavy_work_jumping / t1.work_all).round(4))
    say(p.pivot_table(index="score", columns="target", values="share", sort=False).to_string())


if __name__ == "__main__":
    main()
