"""Cost predictor for a Firefox CI pool, mirroring evidence/cross_domain/cd_predict.py.

    uv run --with pandas --with numpy --with scipy --with pyarrow --with lightgbm \
        --with numba python fci_predict.py <pool-tag>

Feature sets  : ENT (label history only), STATIC (clock / repo / priority / tier only),
                ALL (everything tabular).
Objectives    : log-L2 (LightGBM on log1p(service)) and Tweedie (E[service], p = 1.5),
                the ranking score chapter 4.2 of the plan settled on.
Baselines     : the label's running mean of log1p(service), and the global running mean.
Model choices are made on the validation window; the test window is scored once.
Confidence intervals: entity-block bootstrap, blocks = the prediction entity (label).
"""
import os
import sys

sys.dont_write_bytecode = True

import numpy as np
import pandas as pd
import lightgbm as lgb
from scipy.stats import rankdata

import fci_common as C
from fci_build import FEAT_ENT, FEAT_STATIC, FEAT_ALL

N_THREADS = 4
B_BOOT = 200
BOOT_CAP = 200_000
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
    yy = y[np.argsort(-s, kind="mergesort")]
    prec = np.cumsum(yy) / np.arange(1, len(yy) + 1)
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


def main(tag):
    meta = pd.read_csv(os.path.join(C.HERE, f"meta_{tag}.csv")).iloc[0]
    df = pd.read_parquet(os.path.join(C.SCRATCH, f"{tag}_feats.parquet"))
    out = os.path.join(C.HERE, f"out_predict_{tag}.txt")
    rng = np.random.default_rng(C.SEED)
    with open(out, "w", encoding="utf-8") as fh:
        C.log(fh, f"=== cost prediction, {tag} ===")
        tr_d, va_d = int(meta.train_day), int(meta.valid_day)
        day = df.day.values
        m_tr, m_va, m_te = day < tr_d, (day >= tr_d) & (day < va_d), day >= va_d
        C.log(fh, f"rows train/valid/test = {int(m_tr.sum())}/{int(m_va.sum())}/"
                  f"{int(m_te.sum())}   heavy threshold = {meta.heavy_thr:.1f}s   "
                  f"heavy rate (test) = {df.heavy.values[m_te].mean():.4f}")
        tr, va, te = df[m_tr], df[m_va], df[m_te]
        y = {"log": lambda d: np.log1p(d.dur.values), "tweedie": lambda d: d.dur.values}
        sets = {"ENT": FEAT_ENT, "STATIC": FEAT_STATIC, "ALL": FEAT_ALL}
        true = te.dur.values
        heavy = te.heavy.values.astype(bool)
        ent = te.ent.values
        rows, preds, vpreds = [], {}, {}
        preds["M0-label-running-mean"] = np.expm1(
            np.where(te.e_n.values > 0, te.e_mean.values, te.g_ewm.values))
        preds["M0-global-running-mean"] = np.expm1(te.g_ewm.values)
        C.log(fh, "fitting:")
        for sname, cols in sets.items():
            for obj in ("log", "tweedie"):
                mdl = fit_one(tr, va, cols, obj, y[obj](tr), y[obj](va), fh,
                              f"{sname}/{obj}")
                pv = mdl.predict(te[cols].values.astype(np.float32),
                                 num_iteration=mdl.best_iteration)
                vp = mdl.predict(va[cols].values.astype(np.float32),
                                 num_iteration=mdl.best_iteration)
                if obj == "log":
                    pv, vp = np.expm1(pv), np.expm1(vp)
                preds[f"{sname}/{obj}"] = np.maximum(pv, 0.0)
                vpreds[f"{sname}/{obj}"] = np.maximum(vp, 0.0)
                mv = metrics(va.dur.values, np.maximum(vp, 0), va.heavy.values.astype(bool))
                C.log(fh, f"      validation {sname}/{obj}: rmse_log={mv['rmse_log']:.4f} "
                          f"spearman={mv['spearman']:.4f} auroc={mv['auroc']:.4f}")
        # identity share of the variance, as in cd_predict
        g = df[m_tr].groupby("ent").dur.agg(["count", "mean"])
        yy = np.log1p(df[m_tr].dur.values)
        gm = df[m_tr].groupby("ent").apply(lambda d: np.log1p(d.dur.values).mean())
        ss_tot = ((yy - yy.mean()) ** 2).sum()
        ss_b = (g["count"] * (gm - yy.mean()) ** 2).sum()
        C.log(fh, f"\neta^2 of the label identity on log1p(service), train window: "
                  f"{ss_b/ss_tot:.4f}")
        C.log(fh, "\ntest-window scores (entity-block bootstrap, "
                  f"{B_BOOT} reps, blocks = label):")
        C.log(fh, f"{'model':26s} {'rmse_log':>22s} {'spearman':>22s} "
                  f"{'auroc':>22s} {'auprc':>22s}")
        for name, pv in preds.items():
            m = metrics(true, pv, heavy)
            ci = block_boot(true, pv, heavy, ent, rng)
            line = f"{name:26s}"
            for k in ("rmse_log", "spearman", "auroc", "auprc"):
                line += f" {m[k]:8.4f}[{ci[k][0]:6.3f},{ci[k][1]:6.3f}]"
            C.log(fh, line)
            rows.append(dict(model=name, **m, **{f"{k}_lo": ci[k][0] for k in ci},
                             **{f"{k}_hi": ci[k][1] for k in ci}))
        pd.DataFrame(rows).to_csv(os.path.join(C.HERE, f"pred_{tag}.csv"), index=False)
        C.log(fh, "\nby label history at arrival (test window):")
        for lab, msk in (("cold label (<5 past runs)", te.e_n.values < 5),
                         ("warm label (>=5)", te.e_n.values >= 5)):
            if msk.sum() < 100:
                continue
            m = metrics(true[msk], preds["ALL/tweedie"][msk], heavy[msk])
            C.log(fh, f"   ALL/tweedie on {lab}: n={int(msk.sum())} "
                      f"rmse_log={m['rmse_log']:.4f} spearman={m['spearman']:.4f} "
                      f"auroc={m['auroc']:.4f}")
        for part, sub, pd_ in (("valid", va, vpreds), ("test", te, preds)):
            keep = pd.DataFrame({
                "arrival": sub.arrival.values, "dur": sub.dur.values,
                "wait_rec": sub.wait_rec.values, "ent": sub.ent.values,
                "ent2": sub.ent2.values, "heavy": sub.heavy.values,
                "prio": sub.prio.values, "max_run_time": sub.max_run_time.values,
                "pred_log": pd_["ALL/log"], "pred_tweedie": pd_["ALL/tweedie"],
                "pred_ent": pd_["ENT/tweedie"]})
            p = os.path.join(C.SCRATCH, f"{tag}_{part}_pred.parquet")
            keep.to_parquet(p, index=False)
            C.log(fh, f"wrote {p} ({len(keep)} rows)")
    print("wrote", out)


if __name__ == "__main__":
    main(sys.argv[1])
