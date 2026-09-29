"""Stage 5: the hybrid predictors G3 (and the analogous R1 stack), in the uv environment
because LightGBM is not installed in the GPU environment.

G3 = LightGBM on M4's tabular columns PLUS the 128 node-representation dimensions
[h2_user, h2_exercise] that the trained G1 produces for the same submission.  Same LightGBM
parameters as the pre-check (service_precheck.LGB_REG / LGB_CLF, native API), same three
seeds, same split, so G3 vs M4 is a clean "do the learned node representations add anything
to the tabular model".

R1S = the same construction with R1's 64-dimensional GRU state instead.

M4R = LightGBM on M4's columns alone, refitted here.  It must reproduce the cached
p1pred_ires0_core predictions; that is the check that this script's design matrix, seeds
and parameters are the pre-check's.

Params: seeds 3/4/5, LGB as in v1.  Run with:
  env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME uv run --with pandas --with
  numpy --with pyarrow --with lightgbm --with scipy python stack_lgb.py
"""
from __future__ import annotations

import os
import sys

sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import argparse

import numpy as np
import pandas as pd
import lightgbm as lgb

OUT = r"<cache-dir>\pn"
CACHE = r"<cache-dir>\cb_v2_cache_r4"
HERE = os.path.dirname(os.path.abspath(__file__))
SEEDS = (3, 4, 5)
TRAIN_CORE = ["2018-1", "2018-2", "2019-1", "2019-2"]
VALID = ["2022-1"]
TEST = ["2022-2"]
LGB_REG = dict(objective="regression", n_estimators=300, learning_rate=0.06,
               num_leaves=63, min_child_samples=50, colsample_bytree=1.0,
               subsample=0.8, subsample_freq=1, verbose=-1, n_jobs=6)
LGB_CLF = dict(LGB_REG, objective="binary")
G1NAME = "G1_{}_lr0.001_mean_wd0.0_dr0.1_s{}_final"
R1NAME = "R1_{}_lr0.0003_mean_wd0.0_dr0.1_s{}_final"
REMOTE = ["2020-ERE", "2020-1", "2020-2", "2021-1", "2021-2"]

LOG = open(os.path.join(HERE, f"out_stack_lgb_{sys.argv[-1]}.txt"), "w", encoding="utf-8")


def say(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    LOG.write(s + "\n")
    LOG.flush()


def fit(params, X, y, seed, Xte):
    p = dict(params, random_state=seed)
    n = p.pop("n_estimators")
    return lgb.train(p, lgb.Dataset(X, label=y), num_boost_round=n).predict(Xte)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--variant", default="core")
    V = ap.parse_args().variant
    trsem = TRAIN_CORE if V == "core" else TRAIN_CORE + REMOTE
    B = np.load(os.path.join(OUT, "base.npz"), allow_pickle=False)
    X = np.load(os.path.join(OUT, "X.npy"))
    xcols = open(os.path.join(OUT, "xcols.txt")).read().split("\n")
    sem, y, hv = B["sem"], B["y"].astype("float64"), B["hv"].astype("float64")
    M4 = [c for c in xcols if not c.startswith("r_")]
    ci = [xcols.index(c) for c in M4]
    m_tr = np.isin(sem, trsem); m_te = np.isin(sem, TEST)
    say(f"M4 columns {len(M4)}  train {int(m_tr.sum()):,}  test {int(m_te.sum()):,}")
    A, Bm = X[m_tr][:, ci], X[m_te][:, ci]

    ref = pd.read_parquet(os.path.join(CACHE, f"p1pred_ires0_{V}.parquet"))
    res = {}
    for seed in SEEDS:
        yp = fit(LGB_REG, A, y[m_tr], seed, Bm)
        hp = fit(LGB_CLF, A, hv[m_tr], seed, Bm)
        d1 = float(np.abs(yp - ref[f"{V}|M4|{seed}|y"].values).max())
        d2 = float(np.abs(hp - ref[f"{V}|M4|{seed}|h"].values).max())
        say(f"  M4 refit seed {seed}: max |y - cached| {d1:.3e}   max |h - cached| {d2:.3e}")
        res[f"M4R|{seed}|y"], res[f"M4R|{seed}|h"] = yp, hp

    for tag, nm, dim in (("G3", G1NAME, None), ("R1S", R1NAME, None)):
        for seed in SEEDS:
            f = os.path.join(OUT, f"emb_{nm.format(V, seed)}.npz")
            if not os.path.exists(f):
                say(f"  {tag} seed {seed}: no embedding file, skipped")
                continue
            E = np.load(f)
            Atr = np.hstack([A, E["tr"]]).astype(np.float32)
            Ate = np.hstack([Bm, E["te"]]).astype(np.float32)
            yp = fit(LGB_REG, Atr, y[m_tr], seed, Ate)
            hp = fit(LGB_CLF, Atr, hv[m_tr], seed, Ate)
            res[f"{tag}|{seed}|y"], res[f"{tag}|{seed}|h"] = yp, hp
            say(f"  {tag} seed {seed}: fitted on {Atr.shape[1]} columns "
                f"({E['tr'].shape[1]} from the network)")
    pd.DataFrame(res).to_parquet(os.path.join(OUT, f"stack_pred_{V}.parquet"), index=False)
    say(f"wrote stack_pred_{V}.parquet  keys {len(res)}")


if __name__ == "__main__":
    main()
