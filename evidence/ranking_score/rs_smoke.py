"""Smoke test: base load + reproduce one cell of the verified forward table.

Refits the target 2022-2 M4 log-scale regression with num_threads=4 and checks that the
AUROC matches fwdtab_ires0.csv (0.9183) -- i.e. that our training loop is the pipeline's.
"""
import time

import numpy as np
import pandas as pd

import rs_common as C
from rs_common import SP, say

t0 = time.time()
ev, D, S, X, arr, avail = C.load_base()
say(f"base loaded in {time.time() - t0:.0f} s; events {len(ev):,}; submissions {len(D['sidx']):,}; "
    f"X {X.shape}; heavy_thr {D['heavy_thr']:.4f}")

sidx = D["sidx"]
sem = D["sem"][sidx]
Ccap = np.minimum(D["C"][sidx], SP.L_CAP)
y = np.log1p(Ccap)
hh = (Ccap > D["heavy_thr"]).astype(int)
a_s = avail[sidx]
order, first = C.targets_in_order(D, arr)
say("calendar order:", order)

s = "2022-2"
prior = [q for q in order if first[q] < first[s]]
m_tr = np.isin(sem, prior) & (a_s < first[s])
m_te = sem == s
say(f"target {s}: n_train {m_tr.sum():,} (table 822,305), n_target {m_te.sum():,} (table 40,844)")

ci = [SP.COLI[c] for c in C.FEATS]
p = dict(SP.v1.LGB_REG, random_state=C.SEED, num_threads=C.NTHREADS)
n = p.pop("n_estimators")
p.pop("n_jobs", None)
t = time.time()
import lightgbm as lgb
mdl = lgb.train(p, lgb.Dataset(X[m_tr][:, ci], label=y[m_tr]), num_boost_round=n)
yp = mdl.predict(X[m_te][:, ci])
r = SP.v1.metrics(y[m_te], hh[m_te], yp, yp)
say(f"M4 log-scale refit ({time.time() - t:.0f} s): auroc {r['auroc']:.4f} (table 0.9183), "
    f"rmse {r['rmse']:.4f} (table 0.2357), spearman {r['spearman']:.3f} (table 0.360)")

fw = pd.read_parquet(f"{C.CACHE}/forward_{C.CFG}.parquet")
say("cached forward M4 on this target: corr with refit =",
    round(float(np.corrcoef(fw['M4'].values[m_te], yp)[0, 1]), 6))
say(f"total {time.time() - t0:.0f} s")
