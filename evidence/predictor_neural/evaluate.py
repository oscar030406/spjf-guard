"""Stage 6: metrics and user-block paired bootstrap on the development test semester 2022-2.

Same split, same three seeds, same statistics and the same bootstrap as
service_precheck_v2.stage_boot: each resample draws the 190 test users with replacement and
every statistic is the mean over seeds 3/4/5; the CI is the 2.5/97.5 percentile of 2,000
resamples.  AUROC/AUPRC score the classifier output against the true heavy label
(C_cap > train p95 = 1.559 s); RMSE and Spearman score the regression output against
log1p(C_cap).

Groups: all test rows, cold-start exercises (< 5 available results) and cold-start users
(< 5).  The cold-start-user group has no heavy positives at all, so only RMSE and Spearman
are defined there.

Params: N_BOOT = 2000, bootstrap seed 3.
"""
from __future__ import annotations

import os
import sys

sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import argparse

import numpy as np
import pandas as pd
from scipy.stats import rankdata, spearmanr

OUT = r"<cache-dir>\pn"
CACHE = r"<cache-dir>\cb_v2_cache_r4"
HERE = os.path.dirname(os.path.abspath(__file__))
SEEDS = (3, 4, 5)
N_BOOT = 2000
BOOT_SEED = 3
TEST = ["2022-2"]
NEURAL = {"N0": "N0_{v}_lr0.001_mean_wd0.0_dr0.1_s{s}_final",
          "G0U": "G0U_{v}_lr0.001_mean_wd0.0_dr0.1_s{s}_final",
          "G0": "G0_{v}_lr0.001_mean_wd0.0_dr0.1_s{s}_final",
          "G1": "G1_{v}_lr0.001_mean_wd0.0_dr0.1_s{s}_final",
          "G2": "G2_{v}_lr0.001_mean_wd0.0_dr0.1_s{s}_final",
          "R1": "R1_{v}_lr0.0003_mean_wd0.0_dr0.1_s{s}_final"}
PAIRS = [("G1", "G2"), ("G1", "G0"), ("G0", "G0U"), ("G0U", "N0"),
         ("G1", "M5"), ("G1", "M4"), ("G0", "M4"), ("N0", "M4"),
         ("G3", "M4"), ("R1", "M4"), ("R1S", "M4"), ("R1", "N0"), ("M5", "M4"),
         ("G0U", "M4"), ("G1", "G0U"), ("G2", "G0U")]

LOG = open(os.path.join(HERE, f"out_evaluate_{sys.argv[-1]}.txt"), "w", encoding="utf-8")


def say(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    LOG.write(s + "\n")
    LOG.flush()


def auc_prep(score, label):
    o = np.argsort(score, kind="mergesort")
    s = score[o]
    gid = np.cumsum(np.r_[True, s[1:] != s[:-1]]) - 1
    return o, label[o].astype(bool), gid, int(gid[-1]) + 1


def w_auc(P, w):
    o, lab, gid, G = P
    ww = w[o]
    wn = np.bincount(gid, weights=np.where(lab, 0.0, ww), minlength=G)
    wp = np.bincount(gid, weights=np.where(lab, ww, 0.0), minlength=G)
    below = np.cumsum(wn) - wn
    return float((wp * (below + 0.5 * wn)).sum() / (wp.sum() * wn.sum()))


def w_ap(P, w):
    """Weighted step-wise average precision (one step per tie block, as in the pre-check's
    average_precision_score); equals it exactly at w = 1."""
    o, lab, gid, G = P
    ww = w[o]
    wp = np.bincount(gid, weights=np.where(lab, ww, 0.0), minlength=G)
    wa = np.bincount(gid, weights=ww, minlength=G)
    ctp = np.cumsum(wp[::-1])[::-1]            # ctp[g] = weight of positives with score >= g
    ca = np.cumsum(wa[::-1])[::-1]
    prec = ctp / np.maximum(ca, 1e-12)
    rec = ctp / max(ctp[0], 1e-12)
    r, pr = rec[::-1], prec[::-1]              # thresholds from the highest score downwards
    return float(np.sum(np.diff(np.r_[0.0, r]) * pr))


def rmse(y, yp, w=None):
    if w is None:
        return float(np.sqrt(np.mean((y - yp) ** 2)))
    return float(np.sqrt((w * (y - yp) ** 2).sum() / w.sum()))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--variant", default="core")
    V = ap.parse_args().variant
    B = np.load(os.path.join(OUT, "base.npz"), allow_pickle=False)
    sem = B["sem"]
    m_te = np.isin(sem, TEST)
    y = B["y"][m_te].astype("float64")
    h = B["hv"][m_te].astype("float64")
    users = B["user_str"][m_te]
    cold_ex = B["ex_nres"][m_te] < 5
    cold_us = B["u_nres"][m_te] < 5
    say(f"test rows {len(y):,}  heavy {int(h.sum())} ({h.mean():.4%})  users {len(np.unique(users))}")
    say(f"cold-start exercises {int(cold_ex.sum())}  cold-start users {int(cold_us.sum())} "
        f"(heavy among cold users: {int(h[cold_us].sum())})")

    P = {}
    ref = pd.read_parquet(os.path.join(CACHE, f"p1pred_ires0_{V}.parquet"))
    for m in ["M0", "M1", "M2", "M3", "M4", "M5", "M6"]:
        for s in SEEDS:
            P[m, s] = (ref[f"{V}|{m}|{s}|y"].values, ref[f"{V}|{m}|{s}|h"].values)
    for m, pat in NEURAL.items():
        for s in SEEDS:
            f_ = os.path.join(OUT, f"pred_{pat.format(v=V, s=s)}.npz")
            if not os.path.exists(f_):
                continue
            d = np.load(f_)
            P[m, s] = (d["yhat"].astype("float64"), d["hhat"].astype("float64"))
    st = pd.read_parquet(os.path.join(OUT, f"stack_pred_{V}.parquet"))
    for m in ["M4R", "G3", "R1S"]:
        for s in SEEDS:
            if f"{m}|{s}|y" in st:
                P[m, s] = (st[f"{m}|{s}|y"].values, st[f"{m}|{s}|h"].values)
    models = sorted({m for m, _ in P if all((m, s2) in P for s2 in SEEDS)})
    P = {k: v for k, v in P.items() if k[0] in models}
    say(f"training variant {V}")
    _o = np.argsort(-P["M4", 3][1], kind="mergesort")
    _h, _s = h[_o], P["M4", 3][1][_o]
    _last = np.r_[np.flatnonzero(_s[1:] != _s[:-1]), len(_s) - 1]
    _tp = np.cumsum(_h)[_last]
    _pr, _rc = _tp / (_last + 1), _tp / _h.sum()
    _ap = float(np.sum(np.diff(np.r_[0.0, _rc]) * _pr))
    assert abs(_ap - w_ap(auc_prep(P["M4", 3][1], h), np.ones(len(h)))) < 1e-9, "w_ap mismatch"
    say(f"w_ap self-check against the pre-check's average_precision_score: {_ap:.6f} OK")
    say(f"models {models}")

    # ---- point metrics ----
    rows = []
    for m in models:
        for gname, gm in (("all", np.ones(len(y), bool)), ("cold_ex", cold_ex),
                          ("cold_user", cold_us)):
            r = dict(model=m, group=gname, n=int(gm.sum()))
            for stat, f in (("rmse", lambda yp, hp: rmse(y[gm], yp[gm])),
                            ("spearman", lambda yp, hp: float(spearmanr(y[gm], yp[gm]).statistic)
                             if len(np.unique(yp[gm])) > 1 else np.nan),
                            ("auroc", lambda yp, hp: w_auc(auc_prep(hp[gm], h[gm]),
                                                           np.ones(int(gm.sum())))
                             if 0 < h[gm].sum() < gm.sum() else np.nan),
                            ("auprc", lambda yp, hp: w_ap(auc_prep(hp[gm], h[gm]),
                                                          np.ones(int(gm.sum())))
                             if 0 < h[gm].sum() < gm.sum() else np.nan)):
                v = [f(*P[m, s]) for s in SEEDS]
                r[stat] = float(np.mean(v))
                r[stat + "_sd"] = float(np.std(v))
            rows.append(r)
    T = pd.DataFrame(rows)
    T.to_csv(os.path.join(HERE, f"metrics_2022-2_{V}.csv"), index=False)
    for g in ("all", "cold_ex", "cold_user"):
        say(f"\n--- test 2022-2, group {g} (mean over seeds 3/4/5; sd in parentheses) ---")
        d = T[T.group == g].set_index("model")
        for m in ["M0", "M1", "M2", "M3", "M4", "M4R", "M5", "M6", "N0", "G0U", "G0",
                  "G1", "G2", "G3", "R1", "R1S"]:
            if m not in d.index:
                continue
            q = d.loc[m]
            say(f"  {m:4s} n={int(q['n']):>6,}  rmse {q['rmse']:.4f}({q['rmse_sd']:.4f})  "
                f"spearman {q['spearman']:.4f}({q['spearman_sd']:.4f})  "
                f"auroc {q['auroc']:.4f}({q['auroc_sd']:.4f})  "
                f"auprc {q['auprc']:.4f}({q['auprc_sd']:.4f})")

    # ---- user-block paired bootstrap ----
    uu, uidx = np.unique(users, return_inverse=True)
    prep = {(m, s): auc_prep(P[m, s][1], h) for m, s in P}
    brows = []
    for gname, gm in (("all", np.ones(len(y), bool)), ("cold_ex", cold_ex)):
        gi = np.flatnonzero(gm)
        prepg = {(m, s): auc_prep(P[m, s][1][gi], h[gi]) for m, s in P}
        rng = np.random.default_rng(BOOT_SEED)
        acc = {m: {"auroc": [], "auprc": []} for m in models}
        dacc = {p: {"dRMSE": [], "dAUROC": [], "dAUPRC": [], "dSpear": []} for p in PAIRS
                if all(x in models for x in p)}
        inpair = sorted({x for p in PAIRS for x in p if x in models})
        rk = {(m, s): rankdata(P[m, s][0][gi]) for m in inpair for s in SEEDS}
        ry = rankdata(y[gi])
        for _ in range(N_BOOT):
            w_u = np.bincount(rng.integers(0, len(uu), len(uu)), minlength=len(uu)).astype(float)
            w = w_u[uidx][gi]
            sw = w.sum()
            ok = 0 < (w * h[gi]).sum() < sw
            au, ap, rm, sp = {}, {}, {}, {}
            my = (w * ry).sum() / sw
            cy = np.sqrt((w * (ry - my) ** 2).sum() / sw)
            for m in models:
                for s in SEEDS:
                    au[m, s] = w_auc(prepg[m, s], w) if ok else np.nan
                    ap[m, s] = w_ap(prepg[m, s], w) if ok else np.nan
                    if m in inpair:
                        rm[m, s] = rmse(y[gi], P[m, s][0][gi], w)
                        mx = (w * rk[m, s]).sum() / sw
                        cx = np.sqrt((w * (rk[m, s] - mx) ** 2).sum() / sw)
                        sp[m, s] = float((w * (rk[m, s] - mx) * (ry - my)).sum() / sw
                                         / (cx * cy)) if cx > 0 and cy > 0 else np.nan
                acc[m]["auroc"].append(np.mean([au[m, s] for s in SEEDS]))
                acc[m]["auprc"].append(np.mean([ap[m, s] for s in SEEDS]))
            for a, b in dacc:
                dacc[a, b]["dRMSE"].append(np.mean([rm[a, s] - rm[b, s] for s in SEEDS]))
                dacc[a, b]["dAUROC"].append(np.mean([au[a, s] - au[b, s] for s in SEEDS]))
                dacc[a, b]["dAUPRC"].append(np.mean([ap[a, s] - ap[b, s] for s in SEEDS]))
                dacc[a, b]["dSpear"].append(np.mean([sp[a, s] - sp[b, s] for s in SEEDS]))
        one = np.ones(len(gi))
        for m in models:
            r = dict(group=gname, model=m, n=int(gm.sum()))
            for k in ("auroc", "auprc"):
                v = np.array(acc[m][k]); v = v[np.isfinite(v)]
                pt = np.mean([(w_auc if k == "auroc" else w_ap)(prepg[m, s], one) for s in SEEDS])
                r[k], r[k + "_lo"], r[k + "_hi"] = pt, np.quantile(v, .025), np.quantile(v, .975)
            brows.append(r)
        say(f"\n--- paired user-block bootstrap, {N_BOOT} resamples, group {gname} "
            f"(delta = first - second; negative dRMSE = first better) ---")
        prows = []
        for (a, b), d in dacc.items():
            rr = dict(group=gname, pair=f"{a}-{b}")
            pt = {"dRMSE": np.mean([rmse(y[gi], P[a, s][0][gi]) - rmse(y[gi], P[b, s][0][gi])
                                    for s in SEEDS]),
                  "dAUROC": np.mean([w_auc(prepg[a, s], one) - w_auc(prepg[b, s], one)
                                     for s in SEEDS]),
                  "dAUPRC": np.mean([w_ap(prepg[a, s], one) - w_ap(prepg[b, s], one)
                                     for s in SEEDS]),
                  "dSpear": np.mean([float(spearmanr(y[gi], P[a, s][0][gi]).statistic
                                           - spearmanr(y[gi], P[b, s][0][gi]).statistic)
                                     for s in SEEDS])}
            line = f"  {a}-{b:4s}"
            for k in ("dRMSE", "dSpear", "dAUROC", "dAUPRC"):
                v = np.array(d[k]); v = v[np.isfinite(v)]
                lo, hi = np.quantile(v, .025), np.quantile(v, .975)
                rr[k], rr[k + "_lo"], rr[k + "_hi"] = pt[k], lo, hi
                star = "*" if lo * hi > 0 else " "
                line += f"  {k} {pt[k]:+.4f} [{lo:+.4f},{hi:+.4f}]{star}"
            prows.append(rr)
            say(line)
        pd.DataFrame(prows).to_csv(os.path.join(HERE, f"boot_pairs_{V}_{gname}.csv"), index=False)
    pd.DataFrame(brows).to_csv(os.path.join(HERE, f"boot_models_{V}.csv"), index=False)
    say("\n(* = the 95% interval excludes zero)")


if __name__ == "__main__":
    main()
