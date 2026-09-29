"""Why the refit of the current M4 score differs from the cached forward M4:
per-target max |diff|, and whether num_threads is the cause (the cached run used n_jobs=6)."""
import numpy as np
import pandas as pd
import lightgbm as lgb

import rs_common as C
from rs_common import SP, say

ev, D, S, X, arr, avail = C.load_base()
sidx = D["sidx"]
sem = D["sem"][sidx]
Ccap = np.minimum(D["C"][sidx], SP.L_CAP)
ylog = np.log1p(Ccap)
a_s = avail[sidx]
order, first = C.targets_in_order(D, arr)
ci = [SP.COLI[c] for c in C.FEATS]
cached = pd.read_parquet(f"{C.CACHE}/forward_{C.CFG}.parquet")["M4"].values
mine = pd.read_parquet(C.PRED_PARQUET)["log"].values
for s in C.POOL:
    m = sem == s
    say(f"{s}: max|diff| {np.abs(mine[m] - cached[m]).max():.6f}  "
        f"spearman-ish corr {np.corrcoef(mine[m], cached[m])[0,1]:.8f}")

s = "2020-ERE"
prior = [q for q in order if first[q] < first[s]]
m_tr = np.isin(sem, prior) & (a_s < first[s])
m_te = sem == s
A, B = X[m_tr][:, ci], X[m_te][:, ci]
for nt in (4, 6):
    p = dict(SP.v1.LGB_REG, random_state=C.SEED, num_threads=nt, verbose=-1)
    p.pop("n_jobs", None)
    n = p.pop("n_estimators")
    yp = lgb.train(p, lgb.Dataset(A, label=ylog[m_tr]), num_boost_round=n).predict(B)
    say(f"{s} num_threads={nt}: max|diff| vs cached {np.abs(yp - cached[m_te]).max():.6f}")
