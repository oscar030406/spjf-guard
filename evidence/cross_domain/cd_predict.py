"""Cost predictors on the two non-education traces, mirroring the project's M1/M3/M4.

    uv run ... python cd_predict.py azure
    uv run ... python cd_predict.py netbatch

Feature sets  : ENT (entity history only), STATIC (calendar/context only), ALL (tabular).
Objectives    : log-L2 (LightGBM regression on log1p(cost)) and Tweedie (E[cost]).
Baselines     : entity running mean of log1p(cost), global running mean.
All model choices are made on the validation window; the test window is scored once.
Confidence intervals: entity-block bootstrap (blocks = the prediction entity).

Writes out_predict_<trace>.txt and pred_<trace>.csv here, and the test-window
predictions used by cd_sim.py to the cache directory.
"""
import sys

sys.dont_write_bytecode = True

import os
import numpy as np
import pandas as pd
import lightgbm as lgb
from scipy.stats import rankdata

import cd_common as C
from cd_build import FEAT_ENT, FEAT_STATIC, FEAT_ALL

N_THREADS = 4
B_BOOT = 200
BOOT_CAP = 200_000
MAX_TRAIN = 2_000_000
N_ROUNDS = 600
PARAMS = dict(learning_rate=0.05, num_leaves=63, min_data_in_leaf=100,
              feature_fraction=0.9, bagging_fraction=0.8, bagging_freq=1,
              num_threads=N_THREADS, verbose=-1, seed=C.SEED,
              deterministic=True, force_row_wise=True)


def auroc(y, s):
    y = np.asarray(y, bool)
    n1, n0 = int(y.sum()), int((~y).sum())
    if n1 == 0 or n0 == 0:
        return float("nan")
    r = rankdata(s)
    return (r[y].sum() - n1 * (n1 + 1) / 2.0) / (n1 * n0)


def auprc(y, s):
    y = np.asarray(y, bool)
    if y.sum() == 0:
        return float("nan")
    o = np.argsort(-s, kind="mergesort")
    yy = y[o]
    tp = np.cumsum(yy)
    prec = tp / np.arange(1, len(yy) + 1)
    return float((prec * yy).sum() / yy.sum())


def spearman(a, b):
    return float(np.corrcoef(rankdata(a), rankdata(b))[0, 1])


def metrics(true, pred, heavy):
    lt, lp = np.log1p(true), np.log1p(np.maximum(pred, 0.0))
    return dict(rmse_log=float(np.sqrt(np.mean((lp - lt) ** 2))),
                spearman=spearman(pred, true),
                auroc=auroc(heavy, pred), auprc=auprc(heavy, pred))


def block_boot(true, pred, heavy, ent, rng, b=B_BOOT):
    uniq, inv = np.unique(ent, return_inverse=True)
    order = np.argsort(inv, kind="mergesort")
    starts = np.searchsorted(inv[order], np.arange(len(uniq)))
    ends = np.append(starts[1:], len(order))
    out = {k: [] for k in ("rmse_log", "spearman", "auroc", "auprc")}
    for _ in range(b):
        pick = rng.integers(0, len(uniq), size=len(uniq))
        idx = np.concatenate([order[starts[p]:ends[p]] for p in pick])
        if idx.size > BOOT_CAP:
            idx = rng.choice(idx, BOOT_CAP, replace=False)
        m = metrics(true[idx], pred[idx], heavy[idx])
        for k in out:
            out[k].append(m[k])
    return {k: (float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5)))
            for k, v in out.items()}


def fit_one(tr, va, cols, objective, y_tr, y_va, fh, tag):
    p = dict(PARAMS)
    if objective == "tweedie":
        p.update(objective="tweedie", tweedie_variance_power=1.5, metric="tweedie")
    else:
        p.update(objective="regression", metric="l2")
    ds_tr = lgb.Dataset(tr[cols].values.astype(np.float32), label=y_tr,
                        feature_name=list(cols), free_raw_data=True)
    ds_va = lgb.Dataset(va[cols].values.astype(np.float32), label=y_va,
                        reference=ds_tr, free_raw_data=True)
    bst = lgb.train(p, ds_tr, num_boost_round=N_ROUNDS, valid_sets=[ds_va],
                    callbacks=[lgb.early_stopping(40, verbose=False)])
    C.log(fh, f"   {tag}: best_iter={bst.best_iteration} n_feat={len(cols)}")
    return bst


def main(which):
    meta = pd.read_csv(os.path.join(C.HERE, f"meta_{which}.csv")).iloc[0]
    df = pd.read_parquet(os.path.join(C.SCRATCH, f"{which}_feats.parquet"))
    out = os.path.join(C.HERE, f"out_predict_{which}.txt")
    rng = np.random.default_rng(C.SEED)
    with open(out, "w", encoding="utf-8") as fh:
        C.log(fh, f"=== cost prediction, {which} ===")
        tr_d, va_d, te_d = int(meta.train_day), int(meta.valid_day), int(meta.end_day)
        day = df.day.values
        m_tr, m_va, m_te = day < tr_d, (day >= tr_d) & (day < va_d), day >= va_d
        C.log(fh, f"rows train/valid/test = {int(m_tr.sum())}/{int(m_va.sum())}/{int(m_te.sum())}"
                  f"   heavy threshold = {meta.heavy_thr:.4f}s"
                  f"   heavy rate (test) = {df.heavy.values[m_te].mean():.4f}")
        tr, va, te = df[m_tr], df[m_va], df[m_te]
        if len(tr) > MAX_TRAIN:
            tr = tr.sample(MAX_TRAIN, random_state=C.SEED).sort_index()
            C.log(fh, f"training rows subsampled to {len(tr)} (seed {C.SEED})")
        y = {"log": lambda d: np.log1p(d.dur.values), "tweedie": lambda d: d.dur.values}
        sets = {"ENT": FEAT_ENT, "STATIC": FEAT_STATIC, "ALL": FEAT_ALL}
        true = te.dur.values
        heavy = te.heavy.values.astype(bool)
        ent = te.ent.values
        rows = []
        preds = {}
        # ---- baselines ----
        base = np.expm1(np.where(te.e_n.values > 0, te.e_mean.values, te.g_ewm.values))
        preds["M0-entity-running-mean"] = base
        preds["M0-global-running-mean"] = np.expm1(te.g_ewm.values)
        C.log(fh, "fitting:")
        for sname, cols in sets.items():
            for obj in ("log", "tweedie"):
                mdl = fit_one(tr, va, cols, obj, y[obj](tr), y[obj](va), fh,
                              f"{sname}/{obj}")
                pv = mdl.predict(te[cols].values.astype(np.float32), num_iteration=mdl.best_iteration)
                if obj == "log":
                    pv = np.expm1(pv)
                preds[f"{sname}/{obj}"] = np.maximum(pv, 0.0)
                if sname == "ALL":
                    vp = mdl.predict(va[cols].values.astype(np.float32), num_iteration=mdl.best_iteration)
                    vp = np.expm1(vp) if obj == "log" else vp
                    mv = metrics(va.dur.values, np.maximum(vp, 0), va.heavy.values.astype(bool))
                    C.log(fh, f"   (validation, ALL/{obj}): rmse_log={mv['rmse_log']:.4f} "
                              f"spearman={mv['spearman']:.4f} auroc={mv['auroc']:.4f}")
        C.log(fh, "\ntest-window scores (entity-block bootstrap, "
                  f"{B_BOOT} reps, blocks = prediction entity):")
        hdr = f"{'model':26s} {'rmse_log':>22s} {'spearman':>22s} {'auroc':>22s} {'auprc':>22s}"
        C.log(fh, hdr)
        for name, pv in preds.items():
            m = metrics(true, pv, heavy)
            ci = block_boot(true, pv, heavy, ent, rng)
            line = f"{name:26s}"
            for k in ("rmse_log", "spearman", "auroc", "auprc"):
                line += f" {m[k]:8.4f}[{ci[k][0]:6.3f},{ci[k][1]:6.3f}]"
            C.log(fh, line)
            rows.append(dict(model=name, **m,
                             **{f"{k}_lo": ci[k][0] for k in ci},
                             **{f"{k}_hi": ci[k][1] for k in ci}))
        pd.DataFrame(rows).to_csv(os.path.join(C.HERE, f"pred_{which}.csv"), index=False)
        # cold-start split
        C.log(fh, "\nby entity history at arrival (test window):")
        for lab, msk in (("cold entity (<5 past jobs)", te.e_n.values < 5),
                         ("warm entity (>=5)", te.e_n.values >= 5)):
            if msk.sum() < 100:
                continue
            m = metrics(true[msk], preds["ALL/tweedie"][msk], heavy[msk])
            C.log(fh, f"   ALL/tweedie on {lab}: n={int(msk.sum())} "
                      f"rmse_log={m['rmse_log']:.4f} spearman={m['spearman']:.4f} "
                      f"auroc={m['auroc']:.4f}")
        keep = pd.DataFrame({"arrival": te.arrival.values, "dur": te.dur.values,
                             "ent": te.ent.values, "ent2": te.ent2.values,
                             "heavy": te.heavy.values,
                             "pred_log": preds["ALL/log"],
                             "pred_tweedie": preds["ALL/tweedie"],
                             "pred_ent": preds["ENT/tweedie"]})
        pq = os.path.join(C.SCRATCH, f"{which}_test_pred.parquet")
        keep.to_parquet(pq, index=False)
        C.log(fh, f"\nwrote {pq} ({len(keep)} test rows)")
    print("wrote", out)


if __name__ == "__main__":
    main(sys.argv[1])
