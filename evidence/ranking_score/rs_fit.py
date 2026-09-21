"""Rolling-origin forward predictors of the job cost, one per candidate ranking score.

Protocol, features and hyper-parameters are the pipeline's (service_precheck_v2.stage_forward):
for each target semester s, train on the submissions of the semesters whose first arrival is
before s, minus every record whose availability time (done + delta) is at or after s's first
arrival; M4 feature set; LightGBM with v1.LGB_REG / v1.LGB_CLF, seed 3, num_threads 4.
Only the objective (and for the hurdle / variance parts, the training subset and label) changes.

Targets: the six overlay-pool semesters POOL60.  2023-1 / 2023-2 / 2024-1 are never read.

Scores written (all on the raw C_cap scale unless said otherwise; only the induced ORDER
matters to the scheduler, so monotone transforms of a score are the same policy):
  log        L2 on log1p(C_cap)                     -- the current M4 score, refit here as a check
  l2raw      L2 on C_cap                            -- E[C] by squared error
  tweedie    Tweedie(p = 1.5) on C_cap              -- E[C], variance ~ mean^1.5
  gamma      Gamma on max(C_cap, 1e-3)              -- E[C], variance ~ mean^2
  hurdle     P(heavy) E[C|heavy] + (1-P) E[C|light] -- two-part model
  q50/q90/q99 pinball on log1p(C_cap), alpha = .5/.9/.99
  phv        P(C_cap > heavy_thr), binary objective
  logvar     mu + s2/2 with mu the log model and s2 a second L2 model of the squared
             log-residual (2-fold out-of-fold residuals on the training rows): the
             lognormal correction that turns exp(E[log C]) into E[C]

usage: rs_fit.py [--targets 2020-ERE,2020-2] [--out NAME]
"""
from __future__ import annotations

import argparse
import time

import numpy as np
import pandas as pd

import rs_common as C
from rs_common import SP, say

import lightgbm as lgb

EPS = 1e-3
SCORES = ["log", "l2raw", "tweedie", "gamma", "hurdle", "q50", "q90", "q99", "phv", "logvar"]


def fit(params, Xtr, ytr, Xte, extra=None):
    p = dict(SP.v1.LGB_REG if params.get("objective") != "binary" else SP.v1.LGB_CLF)
    p.update(params)
    p.update(random_state=C.SEED, num_threads=C.NTHREADS, verbose=-1)
    p.pop("n_jobs", None)
    n = p.pop("n_estimators")
    m = lgb.train(p, lgb.Dataset(Xtr, label=ytr), num_boost_round=n)
    return m.predict(Xte)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", default=",".join(C.POOL))
    ap.add_argument("--out", default=C.PRED_PARQUET)
    a = ap.parse_args()
    tgts = a.targets.split(",")

    t0 = time.time()
    ev, D, S, X, arr, avail = C.load_base()
    sidx = D["sidx"]
    sem = D["sem"][sidx]
    Ccap = np.minimum(D["C"][sidx], SP.L_CAP)
    ylog = np.log1p(Ccap)
    hv = (Ccap > D["heavy_thr"]).astype(np.float64)
    a_s = avail[sidx]
    order, first = C.targets_in_order(D, arr)
    ci = [SP.COLI[c] for c in C.FEATS]
    Xm = X[:, ci]
    say(f"base {time.time() - t0:.0f} s; heavy_thr {D['heavy_thr']:.4f}; "
        f"heavy rate overall {hv.mean():.4f}; targets {tgts}")

    out = {k: np.full(len(sidx), np.nan) for k in SCORES}
    if a.out and pd.io.common.file_exists(a.out):
        prev = pd.read_parquet(a.out)
        for k in SCORES:
            if k in prev.columns:
                v = prev[k].values
                out[k] = np.where(np.isfinite(v), v, out[k])
        say(f"resumed from {a.out}")

    rows = []
    for s in tgts:
        t = time.time()
        prior = [q for q in order if first[q] < first[s]]
        m_tr = np.isin(sem, prior) & (a_s < first[s])
        m_te = sem == s
        # the fixed 2018-1..2019-2 cut-offs inside the features are valid only when all of
        # TRAIN_CORE is a training row of this target (SP.stage_forward); assert it here.
        core = np.isin(sem, SP.TRAIN_CORE)
        assert m_tr[core].all(), f"{s}: fixed feature cut-offs would include the target"
        A, B = Xm[m_tr], Xm[m_te]
        yl, yr, hh = ylog[m_tr], Ccap[m_tr], hv[m_tr]
        say(f"\n[{s}] train {m_tr.sum():,} ({prior[0]}..{prior[-1]}), target {m_te.sum():,}, "
            f"train heavy rate {hh.mean():.4f}")

        out["log"][m_te] = fit({}, A, yl, B)
        out["l2raw"][m_te] = fit({}, A, yr, B)
        out["tweedie"][m_te] = fit(dict(objective="tweedie", tweedie_variance_power=1.5), A, yr, B)
        out["gamma"][m_te] = fit(dict(objective="gamma"), A, np.maximum(yr, EPS), B)
        for q in (0.5, 0.9, 0.99):
            out[f"q{int(q * 100)}"][m_te] = fit(dict(objective="quantile", alpha=q), A, yl, B)
        ph = fit(dict(objective="binary"), A, hh, B)
        out["phv"][m_te] = ph
        mh, ml = hh > 0.5, hh <= 0.5
        eh = fit({}, A[mh], yr[mh], B)
        elg = fit({}, A[ml], yr[ml], B)
        out["hurdle"][m_te] = ph * eh + (1.0 - ph) * elg
        # two-fold out-of-fold log residuals on the training rows -> variance model
        h2 = (np.arange(len(yl)) + int(m_tr.sum())) % 2 == 0
        r2 = np.empty(len(yl))
        r2[~h2] = (yl[~h2] - fit({}, A[h2], yl[h2], A[~h2])) ** 2
        r2[h2] = (yl[h2] - fit({}, A[~h2], yl[~h2], A[h2])) ** 2
        s2 = np.maximum(fit({}, A, r2, B), 0.0)
        out["logvar"][m_te] = out["log"][m_te] + 0.5 * s2
        rows.append(dict(target=s, n_train=int(m_tr.sum()), n_target=int(m_te.sum()),
                         train_sems=f"{prior[0]}..{prior[-1]}", heavy_rate_train=round(float(hh.mean()), 4),
                         heavy_rate_target=round(float(hv[m_te].mean()), 4),
                         mean_C_target=round(float(Ccap[m_te].mean()), 4),
                         s2_mean=round(float(s2.mean()), 4), sec=round(time.time() - t)))
        say(f"  {rows[-1]}")
        pd.DataFrame(out).to_parquet(a.out, index=False)

    ft = pd.DataFrame(rows)
    ft.to_csv(f"{C.HERE}/fit_targets.csv", index=False,
              mode="a", header=not pd.io.common.file_exists(f"{C.HERE}/fit_targets.csv"))
    say("\n" + ft.to_string(index=False))
    say(f"\nwrote {a.out}; total {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
