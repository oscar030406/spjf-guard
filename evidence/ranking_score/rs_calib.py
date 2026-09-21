"""Calibration of every candidate score, per target semester.

(a) reliability of the mean: target rows binned into deciles of the score (on the raw C_cap
    scale: expm1 for log / logvar / q*), mean predicted vs mean actual C_cap per decile, and
    the overall ratio sum(pred) / sum(actual).
(b) quantile coverage: P(C_cap <= q_alpha_hat) per alpha, target by target.
(c) classifier: heavy rate by decile of P(heavy), Brier score, AUROC, and the predicted vs
    realised heavy rate (the level of the probability, not only its order).
(d) rank quality of each score against the true C_cap: Spearman, AUROC of the score as a
    heavy detector, and the share of the total work carried by the jobs the score puts in
    its own top 1.3% (= the realised heavy rate) -- the quantity the scheduler cares about.

Calibration under semester shift is the point: the training heavy rate falls from 5.0% to
3.0% while the target heavy rate is 0.8-1.6%.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

import rs_common as C
from rs_common import SP, say

MEANS = ["log", "l2raw", "tweedie", "gamma", "hurdle", "logvar"]      # E[C]-type scores
QS = {"q50": 0.50, "q90": 0.90, "q99": 0.99}
RAW = {"log", "logvar", "q50", "q90", "q99"}                          # stored on log1p scale


def to_raw(name, v):
    return np.expm1(v) if name in RAW else v


def main():
    ev, D, S, X, arr, avail = C.load_base()
    sidx = D["sidx"]
    sem = D["sem"][sidx]
    Ccap = np.minimum(D["C"][sidx], SP.L_CAP)
    thr = D["heavy_thr"]
    P = pd.read_parquet(C.PRED_PARQUET)
    say(f"heavy_thr = {thr:.4f} s (fixed p95 of 2018-1..2019-2 C_cap); scores {list(P.columns)}")

    rel, cov, clf, rk = [], [], [], []
    for s in C.POOL:
        m = sem == s
        y = Ccap[m]
        hv = y > thr
        for nm in MEANS:
            p = to_raw(nm, P[nm].values[m])
            d = np.clip(np.searchsorted(np.quantile(p, np.arange(1, 10) / 10.0), p), 0, 9)
            row = dict(target=s, score=nm, n=len(y), ratio_sum=round(float(p.sum() / y.sum()), 4),
                       mean_pred=round(float(p.mean()), 4), mean_true=round(float(y.mean()), 4))
            for k in range(10):
                z = d == k
                row[f"d{k}"] = (f"{p[z].mean():.3f}/{y[z].mean():.3f}" if z.any() else "-")
            rel.append(row)
        for nm, al in QS.items():
            q = to_raw(nm, P[nm].values[m])
            cov.append(dict(target=s, score=nm, alpha=al, coverage=round(float((y <= q).mean()), 4),
                            med_pred=round(float(np.median(q)), 4),
                            true_q=round(float(np.quantile(y, al)), 4)))
        ph = P["phv"].values[m]
        d = np.clip(np.searchsorted(np.quantile(ph, np.arange(1, 10) / 10.0), ph), 0, 9)
        row = dict(target=s, n=len(y), heavy_rate=round(float(hv.mean()), 4),
                   mean_p=round(float(ph.mean()), 4), brier=round(float(((ph - hv) ** 2).mean()), 5),
                   auroc=round(float(SP.roc_auc_score(hv, ph)), 4))
        for k in range(10):
            z = d == k
            row[f"d{k}"] = (f"{ph[z].mean():.4f}/{hv[z].mean():.4f}" if z.any() else "-")
        clf.append(row)
        # rank quality: what each score puts in its own top-(heavy rate) slice
        f = float(hv.mean())
        ntop = max(1, int(round(f * len(y))))
        for nm in P.columns:
            v = P[nm].values[m]
            o = np.argsort(-v, kind="stable")[:ntop]
            rk.append(dict(target=s, score=nm, spearman=round(float(spearmanr(v, y).statistic), 4),
                           auroc_heavy=round(float(SP.roc_auc_score(hv, v)), 4),
                           top_slice_pct=round(100 * f, 2),
                           work_share_top=round(float(y[o].sum() / y.sum()), 4),
                           heavy_recall_top=round(float(hv[o].mean()), 4)))
    ideal = []
    for s in C.POOL:
        y = Ccap[sem == s]
        f = float((y > thr).mean())
        n = max(1, int(round(f * len(y))))
        ideal.append(dict(target=s, score="TRUE C_cap", work_share_top=round(float(np.sort(y)[-n:].sum() / y.sum()), 4)))

    for nm, df in (("reliability of the mean by predicted decile (pred/true mean C_cap, s)", pd.DataFrame(rel)),
                   ("quantile coverage P(C_cap <= q_hat)", pd.DataFrame(cov)),
                   ("P(heavy) reliability by decile (pred/observed heavy rate)", pd.DataFrame(clf)),
                   ("rank quality of each score", pd.DataFrame(rk))):
        say(f"\n=== {nm} ===")
        say(df.to_string(index=False))
        df.to_csv(f"{C.HERE}/calib_{nm.split()[0]}.csv", index=False)
    say("\nwork share of the TRUE top slice (the ceiling of work_share_top):")
    say(pd.DataFrame(ideal).to_string(index=False))


if __name__ == "__main__":
    main()
