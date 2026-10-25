"""Falsification pre-check of the SERVICE side of CodeBench.

Three questions, asked so they can fail:
  P0  what is the cost variable, and is there an enforced time limit?
  P1  can the judging cost of a submission be predicted BEFORE it runs?
  P2  does predicted-shortest-job-first cut waiting under REAL arrival times?
  P3  does Mitzenmacher's non-preemptive M/G/1 priority formula predict P2?

HOLDOUT: 2023-1, 2023-2, 2024-1 are never read.
DEV = 2018-1 .. 2022-2 (EXECUTION TIME is recorded on 100% of SUBMIT events there).
Split by time: train 2018-1..2019-2, validate 2022-1, test 2022-2; the remote
semesters 2020-1/2020-2/2020-ERE/2021-1/2021-2 are reported in and out of train.

Usage:
    uv run --with pandas --with numpy --with scipy --with pyarrow \
           --with lightgbm --with scikit-learn python service_precheck.py
"""
from __future__ import annotations

import os

for _v in ("PYTHONHOME", "PYTHONPATH", "UV_INTERNAL__PYTHONHOME"):
    os.environ.pop(_v, None)

import argparse
import heapq
import sys
import time
from collections import deque

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import average_precision_score, roc_auc_score

import lightgbm as lgb

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PQ = os.path.join(ROOT, "data", "codebench", "parquet")

SEED = 3
TRAIN_CORE = ["2018-1", "2018-2", "2019-1", "2019-2"]
REMOTE = ["2020-ERE", "2020-1", "2020-2", "2021-1", "2021-2"]
VALID = ["2022-1"]
TEST = ["2022-2"]
DEV = TRAIN_CORE + REMOTE + VALID + TEST
HOLDOUT = ["2023-1", "2023-2", "2024-1"]
L_CAP = 60.0          # enforced limit, justified in P0

T0 = time.time()
N_REP = 5          # random consolidations per load level
N_BOOT = 400
_OUT = []


def say(*a):
    s = " ".join(str(x) for x in a)
    _OUT.append(s)
    print(s, flush=True)


def head(t):
    say("\n" + "=" * 78)
    say(t)
    say("=" * 78)


def fmt(df, **kw):
    return df.to_string(**kw)


# --------------------------------------------------------------------------- #
# load
# --------------------------------------------------------------------------- #
def load_events():
    ev, cf, ass = [], [], []
    for s in DEV:
        assert s not in HOLDOUT
        e = pd.read_parquet(os.path.join(PQ, "events", f"{s}.parquet"))
        e["blk_i"] = e.groupby(["class", "user", "assessment", "exercise"],
                               observed=True).cumcount().astype("int32")
        ev.append(e)
        c = pd.read_parquet(os.path.join(PQ, "code_features", f"{s}.parquet"))
        cf.append(c)
        ass.append(pd.read_parquet(os.path.join(PQ, "assessments", f"{s}.parquet")))
    ev = pd.concat(ev, ignore_index=True)
    cf = pd.concat(cf, ignore_index=True)
    ass = pd.concat(ass, ignore_index=True)
    key = ["semester", "class", "user", "assessment", "exercise", "blk_i"]
    cf = cf.drop(columns=["kind"]).rename(columns={"code_len": "code_len_cf"})
    ev = ev.merge(cf, on=key, how="left")
    ok = (ev["code_len"] == ev["code_len_cf"]).mean()
    say(f"events={len(ev):,}  code-feature join: matched code_len on {ok:.5f} of rows "
        f"(missing {ev['code_len_cf'].isna().mean():.5f})")
    ev = ev.drop(columns=["code_len_cf"])
    ass = ass.rename(columns={"start": "a_start", "end": "a_end", "type": "a_type",
                              "weight": "a_weight", "n_exercises": "a_nex"})
    ev = ev.merge(ass[["semester", "class", "assessment", "a_type", "a_weight",
                       "a_start", "a_end", "a_nex"]],
                  on=["semester", "class", "assessment"], how="left")
    ev["remote"] = ev["semester"].isin(REMOTE)
    ev = ev.sort_values("ts", kind="mergesort").reset_index(drop=True)
    return ev


FEAT_CODE = [
    "chars", "lines", "nonblank_lines", "max_line_len", "n_comment_lines",
    "n_while", "n_for", "n_input", "n_def", "n_if", "n_print", "n_range",
    "n_try", "n_class", "n_return", "n_lambda", "n_len", "n_append",
    "n_import", "imp_math", "imp_random", "imp_time", "imp_sys", "imp_os",
    "imp_numpy", "imp_itertools", "imp_string", "imp_other",
    "max_indent", "nest_loop_depth", "has_while_true", "has_recursion",
    "max_num_digits", "max_range_digits", "has_sleep", "has_evalexec", "has_open",
]


# --------------------------------------------------------------------------- #
# P0
# --------------------------------------------------------------------------- #
def part0(ev):
    head("P0. WHAT IS THE COST VARIABLE")
    sub = ev[(ev["kind"] == "submit") & ev["exec_time"].notna()].copy()
    say(f"SUBMIT rows with EXECUTION TIME: {len(sub):,} "
        f"({(ev['kind'] == 'submit').sum():,} submits, "
        f"{ev['exec_time'].notna().mean():.4f} of all events)")

    c = sub["exec_time"].values.astype("float64")
    qs = [.5, .9, .95, .99, .995, .999, .9999, 1.0]
    say("C = execution_time (s), all DEV: " +
        " ".join(f"p{q*100:g}={np.quantile(c, q):.4g}" for q in qs) +
        f"  mean={c.mean():.4g}")

    g = sub.groupby("semester", observed=True)["exec_time"]
    per = pd.DataFrame({
        "n": g.size(), "mean": g.mean(), "p50": g.quantile(.5), "p95": g.quantile(.95),
        "p99": g.quantile(.99), "p999": g.quantile(.999), "max": g.max(),
        "n_gt60": sub.assign(x=sub.exec_time > 60).groupby("semester", observed=True)["x"].sum(),
        "share_gt1000": sub.assign(x=sub.exec_time > 1000).groupby("semester", observed=True)["x"].mean(),
        "err_share": sub.groupby("semester", observed=True)["has_error"].mean(),
    }).reindex(DEV)
    say("\nper semester:")
    say(fmt(per.round(5)))

    say("\nmax execution time by calendar month (months with >1000 submits):")
    m = sub.assign(ym=sub.ts.dt.to_period("M")).groupby("ym").agg(
        n=("exec_time", "size"), mx=("exec_time", "max"),
        n_gt60=("exec_time", lambda x: int((x > 60).sum())))
    say(fmt(m[m.n > 1000].round(2)))

    say("\nis a limit enforced?  count of executions in [55,60) / [60,62] / >62 per semester")
    rows = []
    for s in DEV:
        x = sub.loc[sub.semester == s, "exec_time"].values
        rows.append((s, len(x), int(((x >= 55) & (x < 60)).sum()),
                     int(((x >= 60) & (x <= 62)).sum()), int((x > 62).sum()), x.max()))
    say(fmt(pd.DataFrame(rows, columns=["sem", "n", "[55,60)", "[60,62]", ">62", "max"]),
            index=False))

    say("\nthe >=1000 s executions:")
    h = sub[sub.exec_time >= 1000]
    say(f"n={len(h)}  ({len(h)/len(sub):.5f} of submits)  users={h.user.nunique()} "
        f"exercises={h.exercise.nunique()}  date range {h.ts.min()} .. {h.ts.max()}")
    say("  per semester: " + str(h.groupby("semester", observed=True).size().to_dict()))
    say("  error_type: " + str(h.error_type.value_counts(dropna=False).head(6).to_dict()))
    say(f"  has_error={h.has_error.mean():.3f}  grade recorded on {h.grade.notna().mean():.3f}, "
        f"all of them = {h.grade.dropna().unique()[:3]}  "
        f"(overall grade==100 share {(sub.grade == 100).mean():.3f})")
    tl = sub[sub.error_type.astype(str) == "TimeLimit"]["exec_time"]
    say(f"  rows whose ERROR section says killed / time limit: n={len(tl)} "
        f"min={tl.min():.1f} p50={tl.median():.1f} max={tl.max():.1f}")
    say("  -> they were killed, but at no fixed wall-clock value before 2020;")
    say("     from 2020-1 on no execution exceeds 60.0 s in ANY semester "
        "(max 59.97) and TimeLimit errors vanish.")
    say(f"  => L = {L_CAP:g} s is the platform's own enforced limit, in force since the")
    say("     2020 semesters; before it, runaway jobs ran to 8901 s.")

    say("\ncost concentration and the effect of the cap C_cap = min(C, 60):")
    rows = []
    for s in DEV + ["ALL DEV"]:
        x = c if s == "ALL DEV" else sub.loc[sub.semester == s, "exec_time"].values
        xc = np.minimum(x, L_CAP)
        top5 = x >= np.quantile(x, .95)
        rows.append((s, len(x), x.sum(), xc.sum(), 1 - xc.sum() / x.sum(),
                     x[top5].sum() / x.sum(), (x > L_CAP).mean()))
    say(fmt(pd.DataFrame(rows, columns=["sem", "n", "total_C_s", "total_Ccap_s",
                                        "cost_removed_by_cap", "top5pct_share_of_C",
                                        "share_over_L"]).round(5), index=False))
    say("\ncost by magnitude band (all DEV, C):")
    for lo, hi in [(0, .5), (.5, 1), (1, 10), (10, 60), (60, 300), (300, 1e9)]:
        m_ = (c >= lo) & (c < hi)
        say(f"  [{lo},{hi}): n={m_.sum():7d} share_n={m_.mean():.5f} "
            f"share_of_total_time={c[m_].sum()/c.sum():.4f}")
    return sub


# --------------------------------------------------------------------------- #
# P1 feature construction (single causal pass over ALL events in time order)
# --------------------------------------------------------------------------- #
HIST_COLS = [
    "ex_n", "ex_mean_log", "ex_sd_log", "ex_p50_log", "ex_p90_log", "ex_max_log",
    "ex_err_rate", "ex_heavy_rate", "ex_ntc_mean",
    "u_n", "u_mean_log", "u_sd_log", "u_p50_log", "u_p90_log", "u_err_rate", "u_heavy_rate",
    "ue_n", "ue_last_log", "ue_last_err", "ue_log_sec_since", "prev_ev_err", "prev_ev_log_sec",
]
REL_COLS = ["r_ex_simuser_log", "r_ex_simuser_heavy", "r_ass_other_log",
            "r_ass_other_heavy", "r_ex_sameclass_log"]
CTX_COLS = ["a_is_exam", "a_weight", "a_nex", "hours_to_deadline", "hours_since_open",
            "hour", "dow", "is_remote"]


def _q(dq, p):
    if not dq:
        return np.nan
    s = sorted(dq)
    return s[min(len(s) - 1, int(p * (len(s) - 1) + 0.5))]


def build_history(ev, heavy_thr, tercile_cuts, perm=None):
    """One causal pass in time order.  Returns (hist, rel) arrays, row-aligned to ev.

    Every value written for row i uses only rows j < i (strictly earlier events).
    `perm` = (exercise_permutation, assessment_permutation); when given, the
    RELATIONAL features only are READ from a permuted neighbourhood while the
    state stays keyed by the true ids -- row i gets the aggregates of a different
    exercise / assessment.  (Permuting read AND write keys would be a consistent
    relabelling and would change nothing; that mistake was caught by M5==M6.)
    """
    n = len(ev)
    kind = (ev["kind"].astype(str).values == "submit")
    et = ev["exec_time"].values.astype("float64")
    has_err = ev["has_error"].values.astype(bool)
    ts = ev["ts"].values.astype("datetime64[s]").astype("int64")
    ntc = ev["n_testcases"].values.astype("float64")
    ex = ev["exercise"].values
    us = ev["user"].values
    cl = (ev["semester"].astype(str) + "|" + ev["class"].astype(str)).values
    asmt = (cl + "|" + ev["assessment"].astype(str)).astype(object)

    if perm is None:
        exk, ask = ex, asmt
    else:
        pe, pa = perm
        exk = np.array([pe.get(x, x) for x in ex], dtype=object)
        ask = np.array([pa.get(x, x) for x in asmt], dtype=object)

    EX, U, UE, ASS, ASSEX, EXT, EXC = {}, {}, {}, {}, {}, {}, {}
    last_ev = {}
    out_h = np.full((n, len(HIST_COLS)), np.nan, dtype="float32")
    out_r = np.full((n, len(REL_COLS)), np.nan, dtype="float32")
    lo, hi = tercile_cuts

    for i in range(n):
        u, e, ek, ak, c = us[i], ex[i], exk[i], ask[i], cl[i]
        t = ts[i]
        is_sub = kind[i] and not np.isnan(et[i])

        if is_sub:
            E = EX.get(e)
            U_ = U.get(u)
            P = UE.get((u, e))
            r = out_h[i]
            if E is not None:
                nn, sl, sl2, ne, nh, sn, dq = E
                r[0] = nn; r[1] = sl / nn
                r[2] = np.sqrt(max(sl2 / nn - (sl / nn) ** 2, 0))
                r[3] = _q(dq, .5); r[4] = _q(dq, .9); r[5] = max(dq)
                r[6] = ne / nn; r[7] = nh / nn; r[8] = sn / nn
            else:
                r[0] = 0
            if U_ is not None:
                nn, sl, sl2, ne, nh, dq = U_
                r[9] = nn; r[10] = sl / nn
                r[11] = np.sqrt(max(sl2 / nn - (sl / nn) ** 2, 0))
                r[12] = _q(dq, .5); r[13] = _q(dq, .9)
                r[14] = ne / nn; r[15] = nh / nn
                mu = sl / nn
                uterc = 0 if mu < lo else (1 if mu < hi else 2)
            else:
                r[9] = 0
                uterc = 1
            if P is not None:
                r[16] = P[0]; r[17] = P[1]; r[18] = P[2]
                r[19] = np.log1p(max(t - P[3], 0))
            else:
                r[16] = 0
            le = last_ev.get(u)
            if le is not None:
                r[20] = 1.0 if le[1] else 0.0
                r[21] = np.log1p(max(t - le[0], 0))

            rr = out_r[i]
            K = EXT.get((ek, uterc))
            if K is not None:
                rr[0] = K[1] / K[0]; rr[1] = K[2] / K[0]
            A = ASS.get(ak)
            if A is not None:
                AE = ASSEX.get((ak, ek), (0, 0.0, 0.0))
                rest = A[0] - AE[0]
                if rest > 0:
                    rr[2] = (A[1] - AE[1]) / rest
                    rr[3] = (A[2] - AE[2]) / rest
            K3 = EXC.get((ek, c))
            if K3 is not None:
                rr[4] = K3[1] / K3[0]

        # ---- update state with this row ---- #
        if is_sub:
            lg = np.log1p(et[i])
            hv = 1.0 if et[i] > heavy_thr else 0.0
            er = 1.0 if has_err[i] else 0.0
            E = EX.get(e)
            if E is None:
                EX[e] = [1, lg, lg * lg, er, hv, ntc[i], deque([lg], maxlen=120)]
            else:
                E[0] += 1; E[1] += lg; E[2] += lg * lg; E[3] += er; E[4] += hv
                E[5] += ntc[i]; E[6].append(lg)
            U_ = U.get(u)
            if U_ is None:
                U[u] = [1, lg, lg * lg, er, hv, deque([lg], maxlen=120)]
            else:
                U_[0] += 1; U_[1] += lg; U_[2] += lg * lg; U_[3] += er; U_[4] += hv
                U_[5].append(lg)
            mu = U[u][1] / U[u][0]
            ut2 = 0 if mu < lo else (1 if mu < hi else 2)
            UE[(u, e)] = (UE.get((u, e), (0,))[0] + 1, lg, er, t)
            a_true = asmt[i]
            for d, key in ((ASS, a_true), (ASSEX, (a_true, e)), (EXT, (e, ut2)),
                           (EXC, (e, c))):
                K = d.get(key)
                if K is None:
                    d[key] = [1, lg, hv]
                else:
                    K[0] += 1; K[1] += lg; K[2] += hv
        last_ev[u] = (t, bool(has_err[i]))

    return out_h, out_r


def make_matrix(ev, sub_idx, hist, rel, rel_perm):
    X = pd.DataFrame(index=np.arange(len(sub_idx)))
    e = ev.loc[sub_idx]
    for c in FEAT_CODE:
        X[c] = e[c].values.astype("float32")
    X["a_is_exam"] = (e["a_type"].astype(str).values == "exam").astype("float32")
    X["a_weight"] = pd.to_numeric(e["a_weight"], errors="coerce").values.astype("float32")
    X["a_nex"] = pd.to_numeric(e["a_nex"], errors="coerce").values.astype("float32")
    X["hours_to_deadline"] = ((e["a_end"] - e["ts"]).dt.total_seconds() / 3600).values.astype("float32")
    X["hours_since_open"] = ((e["ts"] - e["a_start"]).dt.total_seconds() / 3600).values.astype("float32")
    X["hour"] = e["ts"].dt.hour.values.astype("float32")
    X["dow"] = e["ts"].dt.dayofweek.values.astype("float32")
    X["is_remote"] = e["remote"].values.astype("float32")
    for j, c in enumerate(HIST_COLS):
        X[c] = hist[sub_idx, j]
    for j, c in enumerate(REL_COLS):
        X[c] = rel[sub_idx, j]
    for j, c in enumerate(REL_COLS):
        X[c + "_perm"] = rel_perm[sub_idx, j]
    return X


GROUPS = {
    "M1": [c for c in HIST_COLS if c.startswith("ex_")],
    "M2": [c for c in HIST_COLS if c.startswith(("u_", "ue_", "prev_"))],
    "M3": FEAT_CODE,
    "M4": FEAT_CODE + CTX_COLS + HIST_COLS,
    "M5": FEAT_CODE + CTX_COLS + HIST_COLS + REL_COLS,
    "M6": FEAT_CODE + CTX_COLS + HIST_COLS + [c + "_perm" for c in REL_COLS],
}

# colsample_bytree is 1.0 on purpose: with <1 the column-sampling pattern depends
# on the NUMBER of columns, so M4 vs M5 would differ even if the extra columns
# were pure noise.  No tuning of anything else.
LGB_REG = dict(objective="regression", n_estimators=300, learning_rate=0.06,
               num_leaves=63, min_child_samples=50, colsample_bytree=1.0,
               subsample=0.8, subsample_freq=1, random_state=SEED, verbose=-1, n_jobs=6)
LGB_CLF = dict(objective="binary", n_estimators=300, learning_rate=0.06,
               num_leaves=63, min_child_samples=50, colsample_bytree=1.0,
               subsample=0.8, subsample_freq=1, random_state=SEED, verbose=-1, n_jobs=6)


def fit_predict(Xtr, ytr, htr, Xte, cols):
    r = lgb.LGBMRegressor(**LGB_REG).fit(Xtr[cols], ytr)
    c = lgb.LGBMClassifier(**LGB_CLF).fit(Xtr[cols], htr)
    return r.predict(Xte[cols]), c.predict_proba(Xte[cols])[:, 1]


def metrics(y, h, yp, hp):
    out = {}
    out["rmse"] = float(np.sqrt(np.mean((y - yp) ** 2)))
    out["spearman"] = float(spearmanr(y, yp).statistic) if len(np.unique(yp)) > 1 else np.nan
    if h.sum() > 0 and h.sum() < len(h):
        out["auroc"] = float(roc_auc_score(h, hp))
        out["auprc"] = float(average_precision_score(h, hp))
    else:
        out["auroc"] = out["auprc"] = np.nan
    return out


def part1(ev, sub):
    head("P1. CAN THE COST BE PREDICTED BEFORE THE JOB RUNS?")
    say("leakage check on `number of test cases`: the parsed n_testcases is the count of")
    q = sub.groupby("exercise", observed=True)["n_testcases"].nunique()
    say(f"  TEST CASE sections actually written to the log; only {(q == 1).mean():.3f} of exercises")
    say(f"  have a single value and {(sub.n_testcases == 0).mean():.3f} of submits record 0 (the run")
    say("  crashed first).  It is therefore an OUTCOME, not a feature: the model gets the")
    say("  exercise's expanding historical mean (ex_ntc_mean) instead.")

    sub_idx = sub.index.values
    y_all = ev["exec_time"].values
    tr_core = ev["semester"].isin(TRAIN_CORE).values
    heavy_thr = float(np.quantile(np.minimum(y_all[sub_idx][tr_core[sub_idx]], L_CAP), .95))
    heavy_thr_raw = float(np.quantile(y_all[sub_idx][tr_core[sub_idx]], .95))
    say(f"\nheavy class H: C_cap above the train(2018-1..2019-2) p95 = {heavy_thr:.4f} s "
        f"(raw-C p95 = {heavy_thr_raw:.4f} s)")

    # tercile cut points of a user's mean log cost, from TRAIN rows only
    lt = np.log1p(np.minimum(y_all[sub_idx][tr_core[sub_idx]], L_CAP))
    cuts = (float(np.quantile(lt, 1 / 3)), float(np.quantile(lt, 2 / 3)))
    say(f"user-slowness tercile cuts (train only, mean log1p C_cap): {cuts[0]:.4f} {cuts[1]:.4f}")

    rng = np.random.default_rng(SEED)
    uex = np.asarray(ev["exercise"].unique(), dtype=object)
    uas = np.unique((ev["semester"].astype(str) + "|" + ev["class"].astype(str)
                     + "|" + ev["assessment"].astype(str)).values).astype(object)
    perm = (dict(zip(uex, rng.permutation(uex))), dict(zip(uas, rng.permutation(uas))))

    t = time.time()
    hist, rel = build_history(ev, heavy_thr, cuts, None)
    _, rel_p = build_history(ev, heavy_thr, cuts, perm)
    say(f"causal history pass over {len(ev):,} events: {time.time()-t:.0f} s "
        f"(x2, second pass on the permuted exercise->assessment graph)")

    X = make_matrix(ev, sub_idx, hist, rel, rel_p)
    meta = ev.loc[sub_idx, ["semester", "class", "user", "exercise", "assessment",
                            "ts", "exec_time", "has_error", "a_type", "a_start",
                            "a_end"]].reset_index(drop=True)
    C = meta["exec_time"].values.astype("float64")
    Ccap = np.minimum(C, L_CAP)

    res_rows, boot_store = [], {}
    for costname, cost, thr in (("C_cap", Ccap, heavy_thr), ("C", C, heavy_thr_raw)):
        y = np.log1p(cost)
        h = (cost > thr).astype(int)
        for vname, trsem in (("train=2018-1..2019-2", TRAIN_CORE),
                             ("train=+2020/2021 remote", TRAIN_CORE + REMOTE)):
            if costname == "C" and vname.startswith("train=2018"):
                continue
            m_tr = meta["semester"].isin(trsem).values
            models = ["M0", "M1", "M2", "M3", "M4", "M5", "M6"] if costname == "C_cap" \
                else ["M1", "M3", "M4", "M5"]
            for split, sems in (("valid 2022-1", VALID), ("test 2022-2", TEST)):
                m_te = meta["semester"].isin(sems).values
                if costname == "C" and split.startswith("valid"):
                    continue
                cold_ex = (X["ex_n"].values < 5) & m_te
                cold_u = (X["u_n"].values < 5) & m_te
                for mod in models:
                    if mod == "M0":
                        yp = np.full(m_te.sum(), y[m_tr].mean())
                        hp = np.full(m_te.sum(), h[m_tr].mean())
                    else:
                        yp, hp = fit_predict(X[m_tr], y[m_tr], h[m_tr], X[m_te], GROUPS[mod])
                    r = metrics(y[m_te], h[m_te], yp, hp)
                    r.update(cost=costname, train=vname, split=split, model=mod,
                             n=int(m_te.sum()), heavy_rate=float(h[m_te].mean()))
                    for tag, msk in (("cold_ex", cold_ex), ("cold_user", cold_u)):
                        idx = msk[m_te]
                        if idx.sum() > 30:
                            rr = metrics(y[m_te][idx], h[m_te][idx], yp[idx], hp[idx])
                            r[tag + "_n"] = int(idx.sum())
                            r[tag + "_rmse"] = rr["rmse"]
                            r[tag + "_spear"] = rr["spearman"]
                            r[tag + "_auroc"] = rr["auroc"]
                    res_rows.append(r)
                    if split.startswith("test") and costname == "C_cap":
                        boot_store[(vname, mod)] = (yp, hp)
                    say(f"  [{time.time()-T0:6.0f}s] {costname:6s} {vname:24s} {split:12s} "
                        f"{mod} rmse={r['rmse']:.4f} sp={r['spearman']:.3f} "
                        f"auroc={r['auroc']:.4f} auprc={r['auprc']:.4f}")

    res = pd.DataFrame(res_rows)
    say("\n--- P1 main table (all test / valid rows) ---")
    cols = ["cost", "train", "split", "model", "n", "heavy_rate", "rmse", "spearman",
            "auroc", "auprc"]
    say(fmt(res[cols].round(4), index=False))
    say("\n--- P1 cold-start rows (exercise with <5 prior submits / user with <5) ---")
    cc = [c for c in res.columns if c.startswith("cold")]
    say(fmt(res[["cost", "train", "split", "model"] + cc].round(4), index=False))

    # paired bootstrap, user blocks, on test rows, C_cap, train=+remote
    head(f"P1b. PAIRED BOOTSTRAP (user blocks, {N_BOOT} resamples, test 2022-2, C_cap)")
    m_te = meta["semester"].isin(TEST).values
    yte, hte = np.log1p(Ccap)[m_te], (Ccap > heavy_thr).astype(int)[m_te]
    users = meta.loc[m_te, "user"].values
    uu, uidx = np.unique(users, return_inverse=True)
    blocks = [np.flatnonzero(uidx == i) for i in range(len(uu))]
    rng = np.random.default_rng(SEED)
    for vname in ("train=2018-1..2019-2", "train=+2020/2021 remote"):
        say(f"\n{vname}   (negative delta-RMSE = first model better)")
        for a, b in (("M4", "M1"), ("M4", "M3"), ("M5", "M4"), ("M5", "M6")):
            if (vname, a) not in boot_store or (vname, b) not in boot_store:
                continue
            ya, ha = boot_store[(vname, a)]
            yb, hb = boot_store[(vname, b)]
            dr, da = [], []
            for _ in range(N_BOOT):
                pick = rng.integers(0, len(blocks), len(blocks))
                idx = np.concatenate([blocks[p] for p in pick])
                dr.append(np.sqrt(np.mean((yte[idx] - ya[idx]) ** 2))
                          - np.sqrt(np.mean((yte[idx] - yb[idx]) ** 2)))
                if 0 < hte[idx].sum() < len(idx):
                    da.append(roc_auc_score(hte[idx], ha[idx]) - roc_auc_score(hte[idx], hb[idx]))
            dr = np.array(dr); da = np.array(da)
            say(f"  {a}-{b}: dRMSE {dr.mean():+.4f} 95% CI [{np.quantile(dr,.025):+.4f},"
                f"{np.quantile(dr,.975):+.4f}]   dAUROC {da.mean():+.4f} "
                f"95% CI [{np.quantile(da,.025):+.4f},{np.quantile(da,.975):+.4f}]")

    # feature importance of the best model, for the write-up
    m_tr = meta["semester"].isin(TRAIN_CORE + REMOTE).values
    mdl = lgb.LGBMRegressor(**LGB_REG).fit(X[m_tr][GROUPS["M5"]], np.log1p(Ccap)[m_tr])
    imp = pd.Series(mdl.feature_importances_, index=GROUPS["M5"]).sort_values(ascending=False)
    say("\ntop 15 gain-split features of M5 (train=+remote, C_cap):")
    say(fmt(imp.head(15)))
    return X, meta, C, Ccap, heavy_thr


# --------------------------------------------------------------------------- #
# P1c: honest (out-of-sample / out-of-fold) predictions for every DEV row
# --------------------------------------------------------------------------- #
def honest_predictions(X, meta, Ccap, heavy_thr):
    head("P1c. OUT-OF-SAMPLE PREDICTIONS FOR EVERY DEV ROW (used by P2/P3)")
    y = np.log1p(Ccap)
    h = (Ccap > heavy_thr).astype(int)
    trsem = TRAIN_CORE + REMOTE
    m_tr = meta["semester"].isin(trsem).values
    preds = {m: np.full(len(X), np.nan) for m in ("M1", "M3", "M4")}
    prob = np.full(len(X), np.nan)

    # rows outside the training semesters: straight fit
    for m in preds:
        yp, hp = fit_predict(X[m_tr], y[m_tr], h[m_tr], X[~m_tr], GROUPS[m])
        preds[m][~m_tr] = yp
        if m == "M4":
            prob[~m_tr] = hp
    # rows inside: 5-fold grouped by (semester, class)
    grp = (meta["semester"].astype(str) + "|" + meta["class"].astype(str)).values
    ug = np.unique(grp[m_tr])
    rng = np.random.default_rng(SEED)
    fold = dict(zip(ug, rng.integers(0, 5, len(ug))))
    fld = np.array([fold.get(g, -1) for g in grp])
    for f in range(5):
        a = m_tr & (fld != f)
        b = m_tr & (fld == f)
        for m in preds:
            yp, hp = fit_predict(X[a], y[a], h[a], X[b], GROUPS[m])
            preds[m][b] = yp
            if m == "M4":
                prob[b] = hp
        say(f"  [{time.time()-T0:6.0f}s] OOF fold {f}: {int(b.sum()):,} rows")
    for m in preds:
        r = metrics(y, h, preds[m], prob)
        say(f"  honest {m}: rmse={r['rmse']:.4f} spearman={r['spearman']:.3f} over all "
            f"{len(X):,} DEV submits")
    return preds, prob


# --------------------------------------------------------------------------- #
# P2: consolidation + trace-driven simulation
# --------------------------------------------------------------------------- #
def simulate(arr, svc, pri, k, mode="fcfs", lam=0.0, rng=None):
    """Non-preemptive k-server queue.  mode: fcfs | pri | mix."""
    n = len(arr)
    wait = np.empty(n)
    free = [0.0] * k
    heapq.heapify(free)
    i = 0
    hq = []           # (pri, idx) for pri / mix
    fq = deque()      # arrival order for fcfs / mix
    served = np.zeros(n, dtype=bool)
    qn = 0
    t_prev = -np.inf      # the clock must not run backwards: after an idle gap the
    #                       earliest-free worker's free time can lie in the past, and
    #                       taking it as the start time gives negative waits (k>1 only)
    while i < n or qn > 0:
        w = heapq.heappop(free)
        t = w if w > t_prev else t_prev
        if qn == 0 and i < n and arr[i] > t:
            t = arr[i]
        while i < n and arr[i] <= t:
            if mode == "fcfs":
                fq.append(i)
            elif mode == "pri":
                heapq.heappush(hq, (pri[i], i))
            else:
                fq.append(i); heapq.heappush(hq, (pri[i], i))
            qn += 1
            i += 1
        if qn == 0:
            heapq.heappush(free, w)
            continue
        if mode == "fcfs":
            j = fq.popleft()
        elif mode == "pri":
            j = heapq.heappop(hq)[1]
        else:
            if rng.random() < lam:
                while served[fq[0]]:
                    fq.popleft()
                j = fq.popleft()
            else:
                while served[hq[0][1]]:
                    heapq.heappop(hq)
                j = heapq.heappop(hq)[1]
        served[j] = True
        qn -= 1
        wait[j] = t - arr[j]
        t_prev = t
        heapq.heappush(free, t + svc[j])
    return wait


def _self_test():
    """The simulator is the measuring instrument here, so it is checked first."""
    rng = np.random.default_rng(SEED)
    for k in (1, 2, 4, 7):
        for mode in ("fcfs", "pri", "mix"):
            n = 20000
            # arrivals with long idle gaps and many ties, like the real trace
            a = np.sort(np.round(np.cumsum(rng.exponential(0.4, n))
                                 + 900 * (np.arange(n) // 2000))) + 1.6e9
            s = rng.lognormal(-1.4, 1.8, n)
            s[rng.integers(0, n, 20)] = 900.0
            s[rng.integers(0, n, 50)] = 0.0
            p = rng.normal(0, 1, n)
            w = simulate(a, s, p, k, mode, 0.3, np.random.default_rng(1))
            assert np.isfinite(w).all() and (w >= -1e-6).all(), (k, mode, w.min())
            # work conservation: with k=1 the last completion equals the serial bound
            if k == 1 and mode == "fcfs":
                assert abs((w + s + a).max() - max(a[0] + s.sum(), a.max() + s[-1])) < 1e6
    # M/G/1 FCFS against Pollaczek-Khinchine
    n = 400000
    s = rng.lognormal(-1.0, 1.0, n)
    rho = 0.7
    a = np.cumsum(rng.exponential(s.mean() / rho, n))
    w = simulate(a, s, s, 1, "fcfs")
    pk = (s ** 2).mean() / (2 * s.mean()) * rho / (1 - rho)
    say(f"simulator self-test: M/M-like M/G/1 FCFS rho=0.7 -> sim E[W]={w.mean():.4f}, "
        f"Pollaczek-Khinchine={pk:.4f}, ratio={w.mean()/pk:.3f}")
    assert 0.9 < w.mean() / pk < 1.1


def busy_hour_work(arr, svc):
    hr = np.floor(arr / 3600).astype("int64")
    o = np.argsort(hr, kind="stable")
    hs, ss = hr[o], svc[o]
    b = np.flatnonzero(np.r_[True, hs[1:] != hs[:-1]])
    tot = np.add.reduceat(ss, b)
    return float(tot.max()), float(np.quantile(tot, .99))


def build_trace(pool, ev_sub, target_rho, k, seed):
    """Superpose class-semesters aligned on real calendar weeks.

    Each class-semester keeps its own timestamps; it is shifted by a whole number
    of weeks so the Monday 00:00 of the week of its first submission lands on a
    common reference Monday.  Week-of-semester, day-of-week and hour-of-day are
    therefore all preserved exactly; only the absolute year/week changes.
    """
    rng = np.random.default_rng(seed)
    # the pool is listed REP_POOL times so high loads stay reachable; each listing
    # of a class-semester gets its own whole-week jitter, so two copies of the same
    # class land on different weeks of the reference calendar
    order = rng.permutation(len(pool) * 3)
    ref = np.datetime64("2020-01-06T00:00:00")  # a Monday
    sel, arrs, svcs, idxs = [], [], [], []
    best, cur = None, 0.0
    for oi in order:
        cs = pool[oi % len(pool)]
        g = ev_sub[cs]
        t0 = g["t"].min()
        mon = (np.datetime64("1970-01-05T00:00:00")
               + np.timedelta64(int((t0 - 345600) // 604800) * 604800, "s"))
        shift = ((ref - mon).astype("timedelta64[s]").astype("int64")
                 + int(rng.integers(0, 6)) * 604800)
        cand_a = arrs + [g["t"] + shift]
        cand_s = svcs + [g["svc"]]
        a = np.concatenate(cand_a); s = np.concatenate(cand_s)
        o = np.argsort(a, kind="stable")
        rho = busy_hour_work(a[o].astype("float64"), s[o])[0] / (3600.0 * k)
        if rho > target_rho * 1.12:
            continue                      # would overshoot: skip this class-semester
        arrs, svcs = cand_a, cand_s
        idxs.append(g["idx"]); sel.append(cs)
        cur = rho
        if best is None or abs(rho - target_rho) < abs(best[0] - target_rho):
            best = (rho, len(sel), a[o].astype("float64"), s[o],
                    np.concatenate(idxs)[o], list(sel))
        if cur >= target_rho * 0.97:
            break
    if best is None:                      # every class-semester alone overshoots
        cs = min(pool, key=lambda c: busy_hour_work(ev_sub[c]["t"].astype("float64"),
                                                    ev_sub[c]["svc"])[0])
        g = ev_sub[cs]
        rho = busy_hour_work(g["t"].astype("float64"), g["svc"])[0] / (3600.0 * k)
        best = (rho, 1, g["t"].astype("float64"), g["svc"], g["idx"], [cs])
    return best


def consolidate(pool, ev_sub, copies, seed):
    """Superpose the pool `copies` times, aligned on real calendar weeks.

    Each class-semester is shifted by a WHOLE number of weeks so that the Monday
    00:00 of the week of its first submission lands on a common reference Monday,
    plus a jitter of 0-11 further weeks drawn per copy.  Day-of-week and
    hour-of-day are therefore preserved exactly and the within-semester deadline
    structure is untouched; only which calendar week a class lands on changes.
    Superposing the pool more than once is what lets a single course-sized trace
    reach server-scale load; the jitter is what makes the five repetitions (and
    the copies inside one repetition) differ in how the deadline peaks line up.
    """
    rng = np.random.default_rng(seed)
    sel = [cs for _ in range(copies) for cs in pool]
    ref = np.datetime64("2020-01-06T00:00:00")
    arrs, svcs, idxs = [], [], []
    for cs in sel:
        g = ev_sub[cs]
        t0 = g["t"].min()
        mon = (np.datetime64("1970-01-05T00:00:00")
               + np.timedelta64(int((t0 - 345600) // 604800) * 604800, "s"))
        shift = ((ref - mon).astype("timedelta64[s]").astype("int64")
                 + int(rng.integers(0, 12)) * 604800)
        arrs.append(g["t"] + shift); svcs.append(g["svc"]); idxs.append(g["idx"])
    a = np.concatenate(arrs); o = np.argsort(a, kind="stable")
    return (a[o].astype("float64"), np.concatenate(svcs)[o],
            np.concatenate(idxs)[o], sel)


def part2(ev, meta, C, Ccap, preds, prob, heavy_thr):
    head("P2. TRACE-DRIVEN SIMULATION WITH REAL ARRIVAL TIMES")
    t = meta["ts"].values.astype("datetime64[s]").astype("int64").astype("float64")
    in_dl = ((meta["a_end"] - meta["ts"]).dt.total_seconds().values <= 24 * 3600) & \
            ((meta["a_end"] - meta["ts"]).dt.total_seconds().values >= 0)
    in_exam = (meta["a_type"].astype(str).values == "exam") & \
              ((meta["ts"] >= meta["a_start"]) & (meta["ts"] <= meta["a_end"])).values
    say(f"jobs in a deadline window (last 24 h): {in_dl.mean():.4f}; inside an exam "
        f"window: {in_exam.mean():.4f}")

    cs_key = (meta["semester"].astype(str) + "|" + meta["class"].astype(str)).values
    pool = sorted(set(cs_key))
    say(f"pool = {len(pool)} DEV class-semesters; every prediction used here is "
        f"out-of-sample or out-of-fold")

    per_cs = {}
    for cs in pool:
        m = cs_key == cs
        idx = np.flatnonzero(m)
        o = np.argsort(t[idx], kind="stable")
        per_cs[cs] = {"t": t[idx][o], "svc": Ccap[idx][o], "idx": idx[o]}

    hthr_pred = np.quantile(prob, .95)
    policies = ["FCFS", "SPJF-oracle", "SPJF-M1", "SPJF-M3", "SPJF-M4",
                "SPJF-mix0.1", "SPJF-mix0.3", "2queue-M4"]
    rows = []
    say("load levels: one consolidation per repetition = the whole pool superposed 3x,")
    say("each copy week-aligned with an independent 0-11 week jitter; k is then set per")
    say("level as round(busy_hour_work(C_cap)/(3600*rho)), so the three levels share an")
    say("arrival trace and differ only in worker count.  rho_busy below is the achieved")
    say("busiest-hour utilisation, which integer k cannot hit exactly.")
    for rep in range(N_REP):
        arr, svc_cap, jidx, sel = consolidate(pool, per_cs, 3, SEED * 100 + rep)
        svc_raw = C[jidx]
        W = busy_hour_work(arr, svc_cap)[0]
        k_prev = 10 ** 6
        for rho_t in (0.5, 0.8, 1.0):
            # closest integer k, but the levels must stay distinct: k strictly
            # decreases with the target, so rho=1.0 lands on the k below rho=0.8
            K = max(2, min(int(round(W / (3600.0 * rho_t))), k_prev - 1))
            k_prev = K
            for svcname, svc in (("C_cap", svc_cap), ("C", svc_raw)):
                rho_eff = busy_hour_work(arr, svc)[0] / (3600.0 * K)
                mean_rho = svc.sum() / (K * (arr[-1] - arr[0]))
                res = {}
                for pol in policies:
                    rng = np.random.default_rng(SEED)
                    if pol == "FCFS":
                        w = simulate(arr, svc, None, K, "fcfs")
                    elif pol == "SPJF-oracle":
                        w = simulate(arr, svc, svc, K, "pri")
                    elif pol.startswith("SPJF-M"):
                        w = simulate(arr, svc, preds[pol.split("-")[1]][jidx], K, "pri")
                    elif pol.startswith("SPJF-mix"):
                        lam = float(pol[8:])
                        w = simulate(arr, svc, preds["M4"][jidx], K, "mix", lam, rng)
                    else:
                        hv = prob[jidx] >= hthr_pred
                        # workers given to the heavy queue in proportion to the WORK
                        # the predicted-heavy jobs carry, not to their job count
                        wshare = svc[hv].sum() / svc.sum() if hv.sum() else 0.0
                        kh = int(min(K - 1, max(1, round(K * wshare))))
                        w = np.full(len(arr), np.nan)
                        if hv.sum() > 0:
                            w[hv] = simulate(arr[hv], svc[hv], None, kh, "fcfs")
                        w[~hv] = simulate(arr[~hv], svc[~hv], preds["M4"][jidx][~hv],
                                          K - kh, "pri")
                        twoq_note = (wshare, kh)
                    if not (np.isfinite(w).all() and (w >= -1e-6).all()):
                        raise RuntimeError(
                            f"bad waits in {pol}: nan={np.isnan(w).sum()} "
                            f"min={np.nanmin(w)} n={len(w)} svc_min={svc.min()}")
                    res[pol] = w
                w0, wo = res["FCFS"], res["SPJF-oracle"]
                hv = prob[jidx] >= hthr_pred
                d = in_dl[jidx]; xm = in_exam[jidx]
                for pol in policies:
                    w = res[pol]
                    gain = (w0.mean() - w.mean()) / (w0.mean() - wo.mean())                         if w0.mean() > wo.mean() else np.nan
                    rows.append(dict(
                        rho_target=rho_t, k=K, rho_busy=round(rho_eff, 3), rep=rep,
                        svc=svcname, m_cs=len(sel), n_jobs=len(arr),
                        mean_rho=round(mean_rho, 5), policy=pol,
                        w_mean=w.mean(), w_p95=np.quantile(w, .95),
                        w_p99=np.quantile(w, .99),
                        w_mean_dl=w[d].mean() if d.sum() else np.nan,
                        w_p99_dl=np.quantile(w[d], .99) if d.sum() else np.nan,
                        w_mean_exam=w[xm].mean() if xm.sum() else np.nan,
                        slowdown=float(np.mean((w + svc) / np.maximum(svc, 1e-3))),
                        w_max_heavy=w[hv].max() if hv.sum() else np.nan,
                        oracle_gain=gain))
            say(f"  [{time.time()-T0:6.0f}s] rep{rep} rho~{rho_t}: k={K}, {len(sel)} "
                f"class-semester copies, {len(arr):,} jobs, busy-hour rho(C_cap)="
                f"{busy_hour_work(arr, svc_cap)[0]/(3600.0*K):.3f} "
                f"rho(C)={busy_hour_work(arr, svc_raw)[0]/(3600.0*K):.3f}; "
                f"predicted-heavy jobs carry {twoq_note[0]:.3f} of the work -> "
                f"{twoq_note[1]} of {K} workers dedicated to them")
    sim = pd.DataFrame(rows)
    say(f"\nk={K} workers.  5 random consolidations per load level, mean +- std over them.")
    for svcname in ("C_cap", "C"):
        say(f"\n--- service time = {svcname} ---")
        s = sim[sim.svc == svcname]
        agg = s.groupby(["rho_target", "policy"], observed=True).agg(
            k=("k", "mean"), rho_busy=("rho_busy", "mean"), n=("n_jobs", "mean"),
            w_mean=("w_mean", "mean"), w_mean_sd=("w_mean", "std"),
            p95=("w_p95", "mean"), p99=("w_p99", "mean"),
            w_dl=("w_mean_dl", "mean"), p99_dl=("w_p99_dl", "mean"),
            w_exam=("w_mean_exam", "mean"), slowdown=("slowdown", "mean"),
            max_heavy=("w_max_heavy", "mean"), oracle_gain=("oracle_gain", "mean"))
        say(fmt(agg.round(3)))
    return sim, per_cs, pool, cs_key


# --------------------------------------------------------------------------- #
# P3: Mitzenmacher non-preemptive priority formula
# --------------------------------------------------------------------------- #
def mg1_classes(svc, pri, lam_rate, nclass=10):
    """E[W_i] for non-preemptive priority with classes by ascending predicted size."""
    q = np.quantile(pri, np.linspace(0, 1, nclass + 1))
    q[0] -= 1e-9; q[-1] += 1e-9
    cls = np.clip(np.searchsorted(q, pri, side="right") - 1, 0, nclass - 1)
    ES = svc.mean()
    ES2 = (svc ** 2).mean()
    R = lam_rate * ES2 / 2.0
    rho_i = np.array([lam_rate * (cls == i).mean() * svc[cls == i].mean()
                      if (cls == i).sum() else 0.0 for i in range(nclass)])
    sig = np.cumsum(rho_i)
    EW = np.zeros(nclass)
    for i in range(nclass):
        a = 1 - (sig[i - 1] if i > 0 else 0.0)
        b = 1 - sig[i]
        EW[i] = np.inf if (a <= 0 or b <= 0) else R / (a * b)
    p = np.array([(cls == i).mean() for i in range(nclass)])
    return float((p * EW).sum()), EW, rho_i, R, ES, ES2


def part3(ev, meta, C, Ccap, preds, prob, pool, per_cs, cs_key):
    head("P3. MITZENMACHER M/G/1 NON-PREEMPTIVE PRIORITY FORMULA, k=1")
    say("E[W_i] = R / ((1 - sum_{j<i} rho_j)(1 - sum_{j<=i} rho_j)),  R = lambda E[S^2]/2,")
    say("10 classes by ascending PREDICTED size (M4), class loads from the data.")
    say("Two rho's are reported because a deadline-driven trace has no single one:")
    say("  rho_busy  = work arriving in the busiest hour / (k*3600)  (what P2 targets)")
    say("  rho_mean  = total work / (k * trace span)                 (the stationary rate)")
    rows = []
    for rho_t in (0.5, 0.8, 0.95):
        for rep in range(N_REP):
            rho, m_cs, arr, svc, jidx, sel = build_trace(pool, per_cs, rho_t, 1,
                                                         SEED * 100 + rep)
            span = arr[-1] - arr[0]
            lam_mean = len(arr) / span
            pr = preds["M4"][jidx]
            EWp_mean, _, _, R, ES, ES2 = mg1_classes(svc, pr, lam_mean)
            EWt_mean, _, _, _, _, _ = mg1_classes(svc, svc, lam_mean)
            lam_busy = rho / ES
            EWp_busy, _, _, _, _, _ = mg1_classes(svc, pr, lam_busy)
            EWt_busy, _, _, _, _, _ = mg1_classes(svc, svc, lam_busy)
            # simulations
            w_real_p = simulate(arr, svc, pr, 1, "pri")
            w_real_t = simulate(arr, svc, svc, 1, "pri")
            w_real_f = simulate(arr, svc, None, 1, "fcfs")
            # Poisson variants: the same empirical service-time distribution, but
            # i.i.d. -- the jobs are shuffled so the trace's own clustering of long
            # jobs inside a class-semester does not leak into the "M/G/1" baseline.
            rg = np.random.default_rng(SEED + rep)
            sh = rg.permutation(len(arr))
            svc_s, pr_s = svc[sh], pr[sh]
            ap = np.cumsum(rg.exponential(1 / lam_mean, len(arr)))
            wp_p = simulate(ap, svc_s, pr_s, 1, "pri")
            wp_t = simulate(ap, svc_s, svc_s, 1, "pri")
            ab = np.cumsum(rg.exponential(1 / lam_busy, len(arr)))
            wb_p = simulate(ab, svc_s, pr_s, 1, "pri")
            wb_t = simulate(ab, svc_s, svc_s, 1, "pri")
            rows.append(dict(
                rho_target=rho_t, rep=rep, m_cs=m_cs, n=len(arr),
                rho_busy=rho, rho_mean=lam_mean * ES, ES=ES, ES2=ES2, R=R,
                form_mean_pred=EWp_mean, form_mean_true=EWt_mean,
                form_busy_pred=EWp_busy, form_busy_true=EWt_busy,
                sim_pois_mean_pred=wp_p.mean(), sim_pois_mean_true=wp_t.mean(),
                sim_pois_busy_pred=wb_p.mean(), sim_pois_busy_true=wb_t.mean(),
                sim_real_pred=w_real_p.mean(), sim_real_true=w_real_t.mean(),
                sim_real_fcfs=w_real_f.mean(),
                pom_formula=EWp_mean / EWt_mean if EWt_mean > 0 else np.nan,
                pom_formula_busy=EWp_busy / EWt_busy if EWt_busy > 0 else np.nan,
                pom_pois_busy=wb_p.mean() / wb_t.mean() if wb_t.mean() > 0 else np.nan,
                pom_pois=wp_p.mean() / wp_t.mean() if wp_t.mean() > 0 else np.nan,
                pom_real=w_real_p.mean() / w_real_t.mean() if w_real_t.mean() > 0 else np.nan))
            say(f"  [{time.time()-T0:6.0f}s] k=1 rho_busy~{rho_t} rep{rep}: {m_cs} cs, "
                f"{len(arr):,} jobs, rho_mean={lam_mean*ES:.4f}")
    p3 = pd.DataFrame(rows)
    g = p3.groupby("rho_target").mean(numeric_only=True)
    say("\n--- formula vs simulation, mean wait in seconds (mean over 5 consolidations) ---")
    say(fmt(g[["m_cs", "n", "rho_busy", "rho_mean", "ES", "ES2", "R"]].round(4)))
    say("\nA. stationary rate rho_mean (the honest long-run load of the trace):")
    say(fmt(g[["form_mean_pred", "sim_pois_mean_pred", "sim_real_pred",
               "form_mean_true", "sim_pois_mean_true", "sim_real_true"]].round(3)))
    say("\nB. busy-hour rate rho_busy (the load the burst actually presents):")
    say(fmt(g[["form_busy_pred", "sim_pois_busy_pred", "sim_real_pred",
               "form_busy_true", "sim_pois_busy_true", "sim_real_true"]].round(3)))
    say("\nC. price of misprediction  E[W|predicted classes] / E[W|true classes]:")
    say(fmt(g[["pom_formula", "pom_formula_busy", "pom_pois", "pom_pois_busy",
               "pom_real"]].round(4)))
    say("\nD. gap factors (simulation / formula), real timestamps:")
    gg = pd.DataFrame({
        "real/formula@rho_mean": g.sim_real_pred / g.form_mean_pred,
        "real/formula@rho_busy": g.sim_real_pred / g.form_busy_pred,
        "poisson@rho_mean/formula": g.sim_pois_mean_pred / g.form_mean_pred,
        "poisson@rho_busy/formula": g.sim_pois_busy_pred / g.form_busy_pred})
    say(fmt(gg.round(3)))
    return p3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                  "out_service.txt"))
    a = ap.parse_args()
    if a.quick:
        globals()["TRAIN_CORE"] = ["2019-1", "2019-2"]
        globals()["REMOTE"] = ["2021-2"]
        globals()["DEV"] = ["2019-1", "2019-2", "2021-2", "2022-1", "2022-2"]
        globals()["N_REP"] = 2
        globals()["N_BOOT"] = 30
    np.random.seed(SEED)
    pd.set_option("display.width", 250, "display.max_columns", 60,
                  "display.float_format", lambda v: f"{v:,.4f}")
    _self_test()
    ev = load_events()
    sub = ev[(ev["kind"] == "submit") & ev["exec_time"].notna()]
    part0(ev)
    X, meta, C, Ccap, hthr = part1(ev, sub)
    preds, prob = honest_predictions(X, meta, Ccap, hthr)
    sim, per_cs, pool, cs_key = part2(ev, meta, C, Ccap, preds, prob, hthr)
    part3(ev, meta, C, Ccap, preds, prob, pool, per_cs, cs_key)
    say(f"\ndone in {(time.time()-T0)/60:.1f} min")
    with open(a.out, "w", encoding="utf-8") as f:
        f.write("\n".join(_OUT) + "\n")


if __name__ == "__main__":
    main()
