"""Optional stage: forward (rolling-origin) R1S-Tweedie ranking score.

R1S = LightGBM on the M4 columns PLUS the 64-dimensional per-target GRU state that
../predictor_neural/forward.py produced for that target semester
(<scratch>/pn/fwdemb_R1_<semester>.npz: `tr`/`te` embeddings with the row indices
`itr`/`ite` they belong to).  Objective and hyper-parameters are the ones the Tweedie
ranking score uses (../ranking_score/rs_fit.py): Tweedie p = 1.5 on raw C_cap,
v1.LGB_REG otherwise, seed 3.

The forward protocol is checked, not assumed, before anything is fitted:
  * `ite` is exactly the target semester's submission rows;
  * every row of `itr` belongs to a semester whose first arrival precedes the target's;
  * every row of `itr` has availability time < the target's first arrival -- the same
    rule SP.stage_forward and rs_fit.py apply;
  * `itr` is the inner-TRAINING part only: forward.py held out the latest 10% of the
    training rows to stop the GRU, so R1S sees ~90% of the rows the Tweedie score sees.
    That is a difference in training set, not a leak, so a control is fitted on the same
    `itr` rows with the M4 columns alone (`m4tw_itr`); R1S must be read against it.

output: <scratch>/mv3/r1s_forward.parquet (r1s_tweedie, m4tw_itr), r1s_targets.csv here
usage:  mv3_r1s.py [--targets 2020-ERE,2020-2]
"""
from __future__ import annotations

import argparse
import os
import time

import numpy as np
import pandas as pd
import lightgbm as lgb

import mv3_common as C
from mv3_common import SP

COLS = ("r1s_tweedie", "m4tw_itr")
TWEEDIE = dict(objective="tweedie", tweedie_variance_power=1.5)


def fit(Xtr, ytr, Xte, nthreads):
    p = dict(SP.v1.LGB_REG)
    p.update(TWEEDIE)
    p.update(random_state=C.SEED, num_threads=nthreads, verbose=-1)
    p.pop("n_jobs", None)
    n = p.pop("n_estimators")
    return lgb.train(p, lgb.Dataset(Xtr, label=ytr), num_boost_round=n).predict(Xte)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", default=",".join(SP.POOL60))
    ap.add_argument("--threads", type=int, default=6)
    a = ap.parse_args()
    lg = C.Log("r1s")

    missing = [s for s in a.targets.split(",")
               if not os.path.exists(os.path.join(C.PNDIR, f"fwdemb_R1_{s}.npz"))]
    if missing:
        lg.w(f"SKIPPED: forward GRU embeddings missing for {missing}; R1S cannot be built "
             f"without rerunning ../predictor_neural/forward.py --save_emb")
        lg.close()
        return

    ev, D, S = C.load_base()
    sidx = D["sidx"]
    sem = D["sem"][sidx]
    Ccap = np.minimum(D["C"][sidx], SP.L_CAP)
    arr, avail = SP.times(D, C.CFG)
    a_s, arr_s = avail[sidx], arr[sidx]
    first = {s: float(arr_s[sem == s].min()) for s in SP.DEV}
    X = SP.build_X(S, pd.read_parquet(SP.feat_path(C.CACHE, C.CFG)), arr_s)
    Xm = X[:, [SP.COLI[c] for c in SP.GROUPS["M4"]]]
    xc = [c for c in open(os.path.join(C.PNDIR, "xcols.txt")).read().split("\n")
          if c and not c.startswith("r_")]
    assert xc == list(SP.GROUPS["M4"]), (len(xc), len(SP.GROUPS["M4"]))
    B = np.load(os.path.join(C.PNDIR, "base.npz"), allow_pickle=False)
    assert np.array_equal(B["sem"], sem) and len(B["y"]) == len(sidx)
    # base.npz stores y = log1p(C_cap) in float32; 1e-5 is that rounding, not a mismatch
    assert float(np.abs(np.log1p(Ccap) - B["y"].astype(np.float64)).max()) < 1e-5
    assert float(np.abs(Ccap - B["Ccap"].astype(np.float64)).max()) < 1e-4
    lg.el(f"design matrix {Xm.shape}, M4 columns verified against the neural study's")

    out = {k: np.full(len(sidx), np.nan) for k in COLS}
    if os.path.exists(C.R1S_PARQUET):
        prev = pd.read_parquet(C.R1S_PARQUET)
        for k in COLS:
            if k in prev.columns:
                out[k] = np.where(np.isfinite(prev[k].values), prev[k].values, out[k])
        lg.w(f"resumed from {C.R1S_PARQUET}")

    rows = []
    for s in a.targets.split(","):
        t0 = time.time()
        E = np.load(os.path.join(C.PNDIR, f"fwdemb_R1_{s}.npz"))
        itr, ite = E["itr"], E["ite"]
        assert np.array_equal(np.flatnonzero(sem == s), ite), f"{s}: ite is not the target"
        prior = sorted({q for q in SP.DEV if first.get(q, np.inf) < first[s]})
        assert set(sem[itr]) <= set(prior), f"{s}: itr leaves the prior semesters"
        assert float(a_s[itr].max()) < first[s], f"{s}: itr row available after the origin"
        full = np.isin(sem, prior) & (a_s < first[s])
        Atr = np.hstack([Xm[itr], E["tr"]]).astype(np.float32)
        Ate = np.hstack([Xm[ite], E["te"]]).astype(np.float32)
        out["r1s_tweedie"][ite] = fit(Atr, Ccap[itr], Ate, a.threads)
        out["m4tw_itr"][ite] = fit(Xm[itr], Ccap[itr], Xm[ite], a.threads)
        rows.append(dict(target=s, n_itr=len(itr), n_forward_eligible=int(full.sum()),
                         itr_share=round(len(itr) / int(full.sum()), 4),
                         emb_dim=int(E["tr"].shape[1]), n_target=len(ite),
                         train_sems=f"{prior[0]}..{prior[-1]}", sec=round(time.time() - t0)))
        lg.el(f"{s}: {rows[-1]}")
        pd.DataFrame(out).to_parquet(C.R1S_PARQUET, index=False)
        del Atr, Ate
    t = pd.DataFrame(rows)
    p = os.path.join(C.HERE, "r1s_targets.csv")
    if os.path.exists(p):
        t = pd.concat([pd.read_csv(p), t], ignore_index=True).drop_duplicates(
            subset=["target"], keep="last")
    t.to_csv(p, index=False)
    lg.w("\n" + t.to_string(index=False))
    lg.close()


if __name__ == "__main__":
    main()
