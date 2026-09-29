"""Stage 7b: batch-1 LightGBM inference latency (uv environment), so that the hybrid
models G3 / R1S can be costed end to end: their total is the network's graph/sequence
lookup + forward pass (latency.py) plus the numbers here.

M4 is re-timed with the same harness so that the comparison is like for like; the
pre-check's own figure for M4 is about 0.08 ms.

Params: N_LAT = 2000, seed 7, n_jobs 1 for prediction.
Run with: env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME uv run --with pandas
  --with numpy --with pyarrow --with lightgbm python latency_lgb.py
"""
from __future__ import annotations

import os
import sys
import time

sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import numpy as np
import lightgbm as lgb

OUT = r"<cache-dir>\pn"
HERE = os.path.dirname(os.path.abspath(__file__))
N_LAT = 2000
SEED = 7
TRAIN_CORE = ["2018-1", "2018-2", "2019-1", "2019-2"]
LGB = dict(objective="regression", learning_rate=0.06, num_leaves=63, min_child_samples=50,
           colsample_bytree=1.0, subsample=0.8, subsample_freq=1, verbose=-1, n_jobs=6,
           random_state=3)
LOG = open(os.path.join(HERE, "out_latency_lgb.txt"), "w", encoding="utf-8")


def say(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    LOG.write(s + "\n")
    LOG.flush()


def q(v):
    v = np.sort(np.asarray(v)) * 1e3
    return f"median {np.median(v):.3f} ms  mean {v.mean():.3f} ms  p99 {v[int(.99 * len(v))]:.3f} ms"


def main():
    rng = np.random.default_rng(SEED)
    B = np.load(os.path.join(OUT, "base.npz"), allow_pickle=False)
    X = np.load(os.path.join(OUT, "X.npy"))
    xcols = open(os.path.join(OUT, "xcols.txt")).read().split("\n")
    sem = B["sem"]
    m_tr = np.isin(sem, TRAIN_CORE)
    te = np.flatnonzero(np.isin(sem, ["2022-2"]))
    M4 = [c for c in xcols if not c.startswith("r_")]
    ci = [xcols.index(c) for c in M4]
    y = B["y"].astype("float64")
    E = np.load(os.path.join(OUT, "emb_G1_core_lr0.001_mean_wd0.0_dr0.1_s3_final.npz"))
    ER = np.load(os.path.join(OUT, "emb_R1_core_lr0.0003_mean_wd0.0_dr0.1_s3_final.npz"))
    sets = {"M4 (67 columns)": (X[m_tr][:, ci], X[te][:, ci]),
            "G3 (67 + 128 columns)": (np.hstack([X[m_tr][:, ci], E["tr"]]),
                                      np.hstack([X[te][:, ci], E["te"]])),
            "R1S (67 + 64 columns)": (np.hstack([X[m_tr][:, ci], ER["tr"]]),
                                      np.hstack([X[te][:, ci], ER["te"]]))}
    for nm, (A, Bt) in sets.items():
        p = dict(LGB)
        bst = lgb.train(p, lgb.Dataset(A.astype(np.float64), label=y[m_tr]), num_boost_round=300)
        rows = rng.choice(len(Bt), N_LAT, replace=False)
        one = [Bt[i:i + 1].astype(np.float64) for i in rows]
        for x in one[:200]:
            bst.predict(x, num_threads=1)
        t = []
        for x in one:
            t0 = time.perf_counter()
            bst.predict(x, num_threads=1)
            t.append(time.perf_counter() - t0)
        say(f"LightGBM 300 trees, batch 1, {nm}: {q(t)}")


if __name__ == "__main__":
    main()
