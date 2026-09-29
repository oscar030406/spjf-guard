"""Reviewer's independent checks of the v2 service pre-check.

Written from the stated rules, not from service_precheck_v2.py's code:

    known(j)    arrival[j] <  arrival[i]
    visible(j)  known(j) and done[j] + delta <= arrival[i]
    I-res  arrival = ts - C, done = ts        I-sub  arrival = ts, done = ts + C
    TEST (and any row without an execution time): arrival = ts, outcome done = ts + lag

Two copies of the v2 script exist.  The numbers in the builder's report were produced by
the cache directory copy service_precheck_v2_merged.py (cache cb_v2_cache); the file in this
folder is a different, later version (cache cb_v2_cache_r3).  Both are checked where the
check applies.

Stages (each well under 10 min; intermediates in the cache directory, never in this folder):
    data      rebuild the DEV event order from the raw parquet tables, compare with the
              cached event table; heavy cut-off and tercile cuts, incl. the cut-offs a
              forward model for 2019-1 / 2019-2 could legitimately have known
    features  brute-force recomputation of 28 features (21 history, 5 relational, 2 counts)
              for 200 random 2022-2 and 200 random DEV submissions, 5 configurations, against
              both caches; power check with the result-availability rule switched off
    fwdleak   the heavy cut-off and tercile cuts are fitted on 2018-1..2019-2 and used in the
              features of the forward models for 2019-1 and 2019-2; refit those two forward
              M4 models with cut-offs known at each target's start and compare
    guard     per-job bound W_guard <= W_FCFS + B + 60 at k = 1 on fresh traces with
              adversarial predictors: own O(n^2) guard vs both copies of simulate()
    auroc     refit M4's classifier (seed 3, train 2018-1..2021-2) on features rebuilt here
              (code + context) and cached history columns; test AUROC on 2022-2 --config
    tables    headline numbers recomputed from the cached CSVs; I-res arrival artefact
Every run rewrites verify_review.txt from the stage logs present.

Run:  uv run --with pandas --with numpy --with scipy --with pyarrow --with lightgbm
          --with scikit-learn python verify_review.py --stage data
Sealed semesters 2023-1, 2023-2, 2024-1 are never opened.  No code text is read.
"""
from __future__ import annotations

import os
import sys

for _v in ("PYTHONHOME", "PYTHONPATH", "UV_INTERNAL__PYTHONHOME"):
    os.environ.pop(_v, None)
sys.dont_write_bytecode = True          # importing the two v2 copies must not write __pycache__

import argparse
import importlib.util
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = r"<repo-root>"
PQ = os.path.join(ROOT, "data", "codebench", "parquet")
SP = r"<cache-dir>"
MCACHE = os.path.join(SP, "cb_v2_cache")          # merged copy: source of the reported numbers
RCACHE = os.path.join(SP, "cb_v2_cache_r3")       # this folder's copy (other writer)
VC = os.path.join(SP, "verify_review_cache")
CANON = os.path.join(HERE, "service_precheck_v2.py")
MERGED = os.path.join(SP, "service_precheck_v2_merged.py")
OUT = os.path.join(HERE, "verify_review.txt")

TRAIN_CORE = ["2018-1", "2018-2", "2019-1", "2019-2"]
REMOTE = ["2020-ERE", "2020-1", "2020-2", "2021-1", "2021-2"]
DEV = TRAIN_CORE + REMOTE + ["2022-1", "2022-2"]
TEST = ["2022-2"]
HOLDOUT = ["2023-1", "2023-2", "2024-1"]
L = 60.0
SEED = 20260919
CFG = {"ires0": ("res", 0.0, 60.0), "ires600": ("res", 600.0, 60.0), "ires0_t600": ("res", 0.0, 600.0),
       "isub0": ("sub", 0.0, 60.0), "isub600": ("sub", 600.0, 60.0)}
FEAT_CODE = ["chars", "lines", "nonblank_lines", "max_line_len", "n_comment_lines", "n_while", "n_for",
             "n_input", "n_def", "n_if", "n_print", "n_range", "n_try", "n_class", "n_return", "n_lambda",
             "n_len", "n_append", "n_import", "imp_math", "imp_random", "imp_time", "imp_sys", "imp_os",
             "imp_numpy", "imp_itertools", "imp_string", "imp_other", "max_indent", "nest_loop_depth",
             "has_while_true", "has_recursion", "max_num_digits", "max_range_digits", "has_sleep",
             "has_evalexec", "has_open"]
HIST = ["ex_n", "ex_mean_log", "ex_sd_log", "ex_p50_log", "ex_p90_log", "ex_max_log", "ex_err_rate",
        "ex_heavy_rate", "ex_ntc_mean", "u_n", "u_mean_log", "u_sd_log", "u_p50_log", "u_p90_log",
        "u_err_rate", "u_heavy_rate", "ue_n", "ue_last_log", "ue_last_err", "ue_log_sec_since",
        "prev_ev_err", "prev_ev_log_sec"]
CTX = ["a_is_exam", "a_weight", "a_nex", "hours_to_deadline", "hours_since_open", "hour", "dow", "is_remote"]
CHECKED = ["ex_n", "ex_mean_log", "ex_sd_log", "ex_p50_log", "ex_p90_log", "ex_max_log", "ex_err_rate",
           "ex_heavy_rate", "ex_ntc_mean", "u_n", "u_mean_log", "u_sd_log", "u_p50_log", "u_err_rate",
           "u_heavy_rate", "ue_n", "ue_last_log", "ue_last_err", "ue_log_sec_since", "prev_ev_err",
           "prev_ev_log_sec", "r_ex_simuser_log", "r_ex_simuser_heavy", "r_ass_other_log",
           "r_ass_other_heavy", "r_ex_sameclass_log", "ex_nres", "u_nres"]

_LOG: list[str] = []


def say(*a):
    s = " ".join(str(x) for x in a)
    _LOG.append(s)
    print(s, flush=True)


def dump(stage):
    os.makedirs(os.path.join(VC, "txt"), exist_ok=True)
    with open(os.path.join(VC, "txt", stage + ".txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(_LOG) + "\n")
    _LOG.clear()
    blocks = []
    for st in ("data", "features", "guard", "auroc_isub0", "auroc_ires0", "fwdleak", "fwdsim", "tables"):
        p = os.path.join(VC, "txt", st + ".txt")
        if os.path.exists(p):
            blocks.append(open(p, encoding="utf-8").read().rstrip("\n"))
    hdr = ("verify_review.txt -- reviewer's independent checks of service_precheck_v2 "
           "(script: verify_review.py; stage logs in run order)\n")
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(hdr + "\n\n".join(blocks) + "\n")


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# --------------------------------------------------------------------------- #
# data
# --------------------------------------------------------------------------- #
EVCOLS = ["semester", "class", "user", "assessment", "exercise", "ts", "kind", "exec_time", "has_error",
          "n_testcases"]


def stage_data():
    say("=" * 78 + "\nDATA: DEV event order rebuilt from the raw parquet tables\n" + "=" * 78)
    parts = []
    for s in DEV:
        assert s not in HOLDOUT
        parts.append(pd.read_parquet(os.path.join(PQ, "events", f"{s}.parquet"), columns=EVCOLS))
    ev = pd.concat(parts, ignore_index=True)
    ev = ev.sort_values("ts", kind="stable").reset_index(drop=True)
    frac = (ev["ts"].dt.microsecond != 0).mean()
    say(f"events {len(ev):,}; ts with a sub-second part: {frac:.6f} (the scripts floor ts to whole seconds)")
    theirs = pd.read_parquet(os.path.join(MCACHE, "ev.parquet"), columns=EVCOLS)
    assert len(theirs) == len(ev), (len(theirs), len(ev))
    same = {c: bool((ev[c].astype(str).values == theirs[c].astype(str).values).all()) for c in
            ("semester", "class", "user", "assessment", "exercise", "kind")}
    same["ts"] = bool((ev["ts"].values == theirs["ts"].values).all())
    a, b = ev["exec_time"].values, theirs["exec_time"].values
    same["exec_time"] = bool(((a == b) | (np.isnan(a) & np.isnan(b))).all())
    same["has_error"] = bool((ev["has_error"].values == theirs["has_error"].values).all())
    same["n_testcases"] = bool((ev["n_testcases"].values == theirs["n_testcases"].values).all())
    say(f"row-by-row equal to cb_v2_cache/ev.parquet (merged copy's event table): {same}")
    if os.path.exists(os.path.join(RCACHE, "ev.parquet")):
        t2 = pd.read_parquet(os.path.join(RCACHE, "ev.parquet"), columns=["user", "ts", "exec_time"])
        a2 = t2["exec_time"].values
        ok2 = (len(t2) == len(ev) and (t2["user"].values == ev["user"].values).all()
               and (t2["ts"].values == ev["ts"].values).all() and ((a2 == a) | (np.isnan(a2) & np.isnan(a))).all())
        say(f"row-by-row equal to cb_v2_cache_r3/ev.parquet (this folder's copy): {bool(ok2)}")
    sub = (ev["kind"].astype(str).values == "submit") & ev["exec_time"].notna().values
    sem = ev["semester"].values
    say(f"submissions with an execution time: {sub.sum():,}; submit rows without one (treated like TEST "
        f"rows by both copies): {int(((ev['kind'].astype(str).values == 'submit') & ~sub).sum()):,}")
    y32 = ev["exec_time"].values
    rows = []
    for name, sems in (("TRAIN_CORE 2018-1..2019-2 (used everywhere)", TRAIN_CORE),
                       ("2018-1..2018-2 (known before 2019-1 starts)", TRAIN_CORE[:2]),
                       ("2018-1..2019-1 (known before 2019-2 starts)", TRAIN_CORE[:3])):
        m = sub & np.isin(sem, sems)
        cc = np.minimum(y32[m], L)
        lt = np.log1p(cc)
        rows.append((name, int(m.sum()), float(np.quantile(cc, .95)), float(np.quantile(lt, 1 / 3)),
                     float(np.quantile(lt, 2 / 3))))
    th = pd.DataFrame(rows, columns=["cut-offs fitted on", "n", "heavy_p95_Ccap", "tercile_lo", "tercile_hi"])
    say(th.round(4).to_string(index=False))
    cc_all = np.minimum(y32[sub], L)
    for name, sems in (("2019-1", ["2019-1"]), ("2019-2", ["2019-2"])):
        m = np.isin(sem[sub], sems)
        say(f"  share of {name} submissions labelled heavy: with the used cut-off {np.mean(cc_all[m] > rows[0][2]):.4f}; "
            f"with the cut-off known at its start {np.mean(cc_all[m] > rows[1 if name == '2019-1' else 2][2]):.4f}")
    keep = ev[EVCOLS].copy()
    keep["C"] = ev["exec_time"].values.astype("float64")
    keep["sub"] = sub
    os.makedirs(VC, exist_ok=True)
    keep.to_parquet(os.path.join(VC, "ev_min.parquet"), index=False)
    pd.DataFrame({"thr": [rows[0][2]], "lo": [rows[0][3]], "hi": [rows[0][4]]}).to_csv(
        os.path.join(VC, "cuts.csv"), index=False)
    dump("data")


# --------------------------------------------------------------------------- #
# features
# --------------------------------------------------------------------------- #
def clock(ev, cfg):
    mode, delta, lag = CFG[cfg]
    ts = ev["ts"].values.astype("datetime64[s]").astype("int64").astype("float64")
    sub = ev["sub"].values
    C = np.where(sub, np.nan_to_num(ev["C"].values), 0.0)
    if mode == "res":
        arr, done = ts - C, ts.copy()
    else:
        arr, done = ts.copy(), ts + C
    done = np.where(sub, done, ts + lag)
    return arr, done + delta


def tercile(m, lo, hi):
    return 0 if m < lo else (1 if m < hi else 2)


def brute_row(i, arr, av, zf, lg, hv, err, ntc, sub, ex, us, cl, asm, byu, byex, byasm, tag, lo, hi):
    t = arr[i]
    out = dict.fromkeys(CHECKED, np.nan)

    def vis(g):
        return g[(arr[g] < t) & (av[g] <= t)]

    def last120(R):
        o = np.lexsort((R, zf[R], av[R]))            # availability order: time, zero-lag last, row
        return np.sort(lg[R[o]][-120:])

    def q(s, p):
        n1 = len(s) - 1
        return s[min(n1, int(p * n1 + 0.5))]

    E = byex[ex[i]]
    out["ex_n"] = float((arr[E] < t).sum())
    R = vis(E)
    out["ex_nres"] = float(len(R))
    if len(R):
        out["ex_mean_log"], out["ex_sd_log"] = lg[R].mean(), lg[R].std()
        s = last120(R)
        out["ex_p50_log"], out["ex_p90_log"], out["ex_max_log"] = q(s, .5), q(s, .9), s[-1]
        out["ex_err_rate"], out["ex_heavy_rate"], out["ex_ntc_mean"] = err[R].mean(), hv[R].mean(), ntc[R].mean()
    Ua = byu[us[i]]                                   # every record of the user, any kind
    Us = Ua[sub[Ua]]
    out["u_n"] = float((arr[Us] < t).sum())
    R = vis(Us)
    out["u_nres"] = float(len(R))
    terc = 1
    if len(R):
        m = lg[R].mean()
        out["u_mean_log"], out["u_sd_log"] = m, lg[R].std()
        out["u_p50_log"] = q(last120(R), .5)
        out["u_err_rate"], out["u_heavy_rate"] = err[R].mean(), hv[R].mean()
        terc = tercile(m, lo, hi)
    UE = Us[ex[Us] == ex[i]]
    K = UE[arr[UE] < t]
    out["ue_n"] = float(len(K))
    if len(K):
        out["ue_log_sec_since"] = np.log1p(max(t - arr[K].max(), 0.0))
    R = vis(UE)
    if len(R):
        j = R[np.lexsort((R, arr[R]))[-1]]            # latest arrival, ties to the later row
        out["ue_last_log"], out["ue_last_err"] = lg[j], err[j]
    K = Ua[arr[Ua] < t]
    if len(K):
        out["prev_ev_log_sec"] = np.log1p(max(t - arr[K].max(), 0.0))
    R = vis(Ua)
    if len(R):
        out["prev_ev_err"] = err[R[np.lexsort((R, arr[R]))[-1]]]
    R = vis(E)
    T3 = R[tag[R] == terc]
    if len(T3):
        out["r_ex_simuser_log"], out["r_ex_simuser_heavy"] = lg[T3].mean(), hv[T3].mean()
    A = vis(byasm[asm[i]])
    A = A[ex[A] != ex[i]]
    if len(A):
        out["r_ass_other_log"], out["r_ass_other_heavy"] = lg[A].mean(), hv[A].mean()
    Cc = R[cl[R] == cl[i]]
    if len(Cc):
        out["r_ex_sameclass_log"] = lg[Cc].mean()
    return out


def groups(codes, idx):
    c = codes[idx]
    o = np.argsort(c, kind="stable")
    c, ii = c[o], idx[o]
    cut = np.flatnonzero(np.r_[True, c[1:] != c[:-1]])
    return {int(c[s]): ii[s:e] for s, e in zip(cut, np.r_[cut[1:], len(c)])}


def stage_features(n_rows=200):
    say("=" * 78 + f"\nFEATURES: brute force, {n_rows} random 2022-2 + {n_rows} random DEV submissions "
        f"(seeds {SEED}, {SEED + 1}), rule as stated\n"
        + "=" * 78)
    ev = pd.read_parquet(os.path.join(VC, "ev_min.parquet"))
    cuts = pd.read_csv(os.path.join(VC, "cuts.csv")).iloc[0]
    thr, lo, hi = float(cuts.thr), float(cuts.lo), float(cuts.hi)
    sub = ev["sub"].values
    sidx = np.flatnonzero(sub)
    rowof = np.full(len(ev), -1, np.int64)
    rowof[sidx] = np.arange(len(sidx))
    Cz = np.nan_to_num(ev["C"].values)
    lg, hv = np.log1p(Cz), (Cz > thr).astype(float)
    err = ev["has_error"].values.astype(float)
    ntc = ev["n_testcases"].values.astype(float)
    ex = pd.factorize(ev["exercise"])[0]
    us = pd.factorize(ev["user"])[0]
    csk = ev["semester"].astype(str) + "|" + ev["class"].astype(str)
    cl = pd.factorize(csk)[0]
    asm = pd.factorize(csk + "|" + ev["assessment"].astype(str))[0]
    byu = groups(us, np.arange(len(ev)))
    byex, byasm = groups(ex, sidx), groups(asm, sidx)
    te = sidx[np.isin(ev["semester"].values[sidx], TEST)]
    samples = {"2022-2": np.sort(np.random.default_rng(SEED).choice(te, n_rows, replace=False)),
               "all DEV": np.sort(np.random.default_rng(SEED + 1).choice(sidx, n_rows, replace=False))}
    say(f"heavy cut-off {thr:.4f}, tercile cuts {lo:.4f} {hi:.4f} (recomputed in stage data)")
    caches = [("merged/cb_v2_cache", MCACHE), ("folder/cb_v2_cache_r3", RCACHE)]
    rows, fails = [], {}
    for (sname, samp), cfg in ((x, c) for x in samples.items() for c in CFG):
        arr, av = clock(ev, cfg)
        zf = (av == arr).astype(np.int64)
        # user-slowness tag of every result, from its user's mean right after it becomes available
        o = sidx[np.lexsort((sidx, zf[sidx], av[sidx]))]
        cm = pd.Series(lg[o]).groupby(us[o]).cumsum().values / (pd.Series(lg[o]).groupby(us[o]).cumcount().values + 1)
        tag = np.full(len(ev), -1, np.int64)
        tag[o] = np.where(cm < lo, 0, np.where(cm < hi, 1, 2))
        t0 = time.time()
        B = pd.DataFrame([brute_row(i, arr, av, zf, lg, hv, err, ntc, sub, ex, us, cl, asm, byu, byex, byasm,
                                    tag, lo, hi) for i in samp])[CHECKED].values.astype(float)
        # power check: the same brute force with results visible at the owner's arrival (no done rule)
        av_leak = arr.copy()
        Bl = pd.DataFrame([brute_row(i, arr, av_leak, np.zeros(len(ev), np.int64), lg, hv, err, ntc, sub, ex, us,
                                     cl, asm, byu, byex, byasm, tag, lo, hi) for i in samp])[CHECKED].values.astype(float)
        for cname, cdir in caches:
            p = os.path.join(cdir, f"feat_{cfg}.parquet")
            if not os.path.exists(p):
                rows.append((sname, cfg, cname, "missing", "", "", ""))
                continue
            F = pd.read_parquet(p, columns=CHECKED).values[rowof[samp]].astype(float)
            ok = (np.isnan(F) & np.isnan(B)) | (np.abs(F - B) <= 1e-5 + 1e-5 * np.abs(B))
            okl = (np.isnan(F) & np.isnan(Bl)) | (np.abs(F - Bl) <= 1e-5 + 1e-5 * np.abs(Bl))
            fin = np.isfinite(F) & np.isfinite(B)
            rows.append((sname, cfg, cname, int((~ok.all(1)).sum()), int((~ok).sum()),
                         f"{np.abs(F - B)[fin].max():.2e}", int((~okl.all(1)).sum())))
            if (~ok).any():
                fails[(sname, cfg, cname)] = {c: int(v) for c, v in zip(CHECKED, (~ok).sum(0)) if v}
        say(f"  {sname} {cfg}: brute force {time.time() - t0:.1f} s")
    say(pd.DataFrame(rows, columns=["sample", "config", "cache", "rows_failing", "cells_failing", "max_abs_diff",
                                    "rows_failing_vs_no_done_rule (power)"]).to_string(index=False))
    for k, v in fails.items():
        say(f"  mismatches {k}: {v}")
    say(f"{len(CHECKED)} features per row: 21 history (all but u_p90_log), the 5 relational ones, and the two")
    say("available-result counts; ex_p50/p90/max and u_p50 use the last 120 results in availability order.")
    dump("features")


# --------------------------------------------------------------------------- #
# guard
# --------------------------------------------------------------------------- #
def lindley(a, s):
    w = np.zeros(len(a))
    for i in range(1, len(a)):
        w[i] = max(0.0, w[i - 1] + s[i - 1] - (a[i] - a[i - 1]))
    return w


def guard_ref(a, s, p, k, B):
    """Overtake-budget guard written from research_plan 4.3: over[h] = true service time of
    later-arrived jobs (higher index) that have COMPLETED by the decision time; serve the
    earliest-arrived waiting job h if over[h] >= B, else the smallest (prediction, index).
    Non-idling k servers; O(n^2)."""
    n = len(a)
    free = [0.0] * k
    wait = np.full(n, np.nan)
    waiting, done_list = [], []           # done_list: (finish time, job)
    i, t = 0, -np.inf
    while i < n or waiting:
        f = min(free)
        srv = free.index(f)
        t = max(t, f)
        if not waiting:
            t = max(t, a[i])
        while i < n and a[i] <= t:
            waiting.append(i)
            i += 1
        h = min(waiting)
        over = sum(s[j] for fin, j in done_list if fin <= t and j > h)
        j = h if over >= B else min(waiting, key=lambda q: (p[q], q))
        waiting.remove(j)
        wait[j] = t - a[j]
        free[srv] = t + s[j]
        done_list.append((t + s[j], j))
    return wait


def fresh_trace(rng, n):
    gaps = rng.choice([0.0, 1 / 64, 0.5, 4.0], n, p=[.3, .3, .3, .1])
    a = np.cumsum(gaps)
    u = rng.random(n)
    s = np.where(u < .75, rng.exponential(0.25, n), np.where(u < .95, rng.uniform(1, 20, n), 60.0))
    s = np.clip(np.round(s * 64) / 64, 1 / 64, L)
    return a, s


def adversaries(a, s, rng, pm4=None):
    n = len(s)
    top1 = (pm4.copy() if pm4 is not None else s.copy())
    top1[np.argsort(-s, kind="stable")[:max(1, n // 100)]] = top1.min() - 1.0
    lie5 = s.copy()
    lie5[np.argsort(-s, kind="stable")[:max(1, n // 20)]] = 0.0
    P = {"reversed": -s, "lifo": -np.arange(n, dtype=float), "random": rng.permutation(s),
         "top1short": top1, "long5pct_as_0": lie5}
    if pm4 is not None:
        P = {"M4_forward": pm4, **P}
    return P


def stage_guard():
    say("=" * 78 + "\nGUARD: per-job bound at k = 1 on fresh traces, adversarial predictors\n" + "=" * 78)
    canon, merged = load_module(CANON, "v2_folder_copy"), load_module(MERGED, "v2_merged_copy")
    rng = np.random.default_rng(SEED)
    rows = []
    traces = [(f"synthetic seed-{r}", *fresh_trace(np.random.default_rng(SEED + r), 1500), None) for r in (1, 2)]
    # a real stress slice: 1,500 consecutive 2022-2 submissions under ires0 arrivals around the busiest
    # hour, C_cap service, the merged copy's forward M4 prediction, time compressed 10x (k = 1 overload)
    ev = pd.read_parquet(os.path.join(VC, "ev_min.parquet"))
    sidx = np.flatnonzero(ev["sub"].values)
    arr, _ = clock(ev, "ires0")
    fw = pd.read_parquet(os.path.join(MCACHE, "forward_ires0.parquet"))["M4"].values
    te = np.flatnonzero(np.isin(ev["semester"].values[sidx], TEST) & (ev["C"].values[sidx] > 0))
    te = te[np.argsort(arr[sidx][te], kind="stable")]
    a_all, s_all = arr[sidx][te], np.minimum(ev["C"].values[sidx][te], L)
    hr = np.floor(a_all / 3600)
    busiest = pd.Series(s_all).groupby(hr).sum().idxmax()
    st = max(0, int(np.searchsorted(hr, busiest)) - 500)
    sl = slice(st, st + 1500)
    a_r = (a_all[sl] - a_all[sl][0]) / 10.0
    traces.append(("real 2022-2 slice (ires0, /10)", a_r, s_all[sl], fw[te][sl]))
    for name, a, s, pm4 in traces:
        wf = lindley(a, s)
        for mod, lbl in ((canon, "folder"), (merged, "merged")):
            assert np.allclose(mod.simulate(a, s, None, 1, "fcfs"), wf, atol=1e-9), lbl
        for pn, p in adversaries(a, s, rng, pm4).items():
            wu = canon.simulate(a, s, p, 1, "pri")
            for B in (30.0, 120.0, 600.0):
                wr = guard_ref(a, s, p, 1, B)
                wc = canon.simulate(a, s, p, 1, "guard", B)
                wm = merged.simulate(a, s, p, 1, "guard", B)
                ws = merged.simulate(a, s, p, 1, "guard", B, acct="start")
                ex = wr - wf
                assert (ex <= B + L + 1e-9).all(), (name, pn, B, ex.max())
                rows.append((name, pn, B, len(a), round(float(ex.max()), 3), B + L,
                             int(np.abs(wc - wr).max() > 1e-9), int(np.abs(wm - wr).max() > 1e-9),
                             int(np.abs(ws - wr).max() > 1e-9), round(float((wu - wf).max()), 1)))
    g = pd.DataFrame(rows, columns=["trace", "predictor", "B", "n", "max_excess_ref", "bound",
                                    "folder_differs", "merged_differs", "merged_start_differs",
                                    "unguarded_max_excess"])
    say(g.to_string(index=False))
    say(f"=> asserted W_guard[i] <= W_FCFS[i] + B + 60 for every job in {len(g)} (trace, predictor, B) runs; "
        f"own guard vs folder copy: {int(g.folder_differs.sum())} runs differ, vs merged copy: "
        f"{int(g.merged_differs.sum())}, vs merged start-time accounting: {int(g.merged_start_differs.sum())}.")
    # k = 2: completion accounting, own implementation vs both copies; the bound is not claimed
    rows = []
    for r in (3, 4):
        a, s = fresh_trace(np.random.default_rng(SEED + r), 1200)
        a = a / 2.2
        wf = canon.fcfs_kw(a, s, 2) if hasattr(canon, "fcfs_kw") else merged.fcfs_kw(a, s, 2)
        for pn, p in adversaries(a, s, rng).items():
            for B in (30.0, 120.0):
                wr = guard_ref(a, s, p, 2, B)
                wc = canon.simulate(a, s, p, 2, "guard", B)
                wm = merged.simulate(a, s, p, 2, "guard", B)
                rows.append((f"synthetic seed-{r}", pn, B, round(float((wr - wf).max()), 2), B + L,
                             int(np.abs(wc - wr).max() > 1e-9), int(np.abs(wm - wr).max() > 1e-9)))
    g2 = pd.DataFrame(rows, columns=["trace", "predictor", "B", "max_excess_k2", "B+60", "folder_differs",
                                     "merged_differs"])
    say("\nk = 2 (reported only; Proposition 3 is a k = 1 claim):")
    say(g2.to_string(index=False))
    say(f"k = 2 runs above B + 60: {int((g2.max_excess_k2 > g2['B+60']).sum())} of {len(g2)}")
    dump("guard")


# --------------------------------------------------------------------------- #
# fwdleak / fwdsim
# --------------------------------------------------------------------------- #
FWD_TARGETS = {"2019-1": ["2018-1", "2018-2"], "2019-2": ["2018-1", "2018-2", "2019-1"]}


def _cuts_from(ev, sems):
    y32 = ev["exec_time"].values
    m = (ev["kind"].astype(str).values == "submit") & ev["exec_time"].notna().values & ev["semester"].isin(sems).values
    cc = np.minimum(y32[m], L)
    lt = np.log1p(cc)
    return float(np.quantile(cc, .95)), (float(np.quantile(lt, 1 / 3)), float(np.quantile(lt, 2 / 3)))


def stage_fwdleak():
    from scipy.stats import spearmanr
    from sklearn.metrics import roc_auc_score
    say("=" * 78 + "\nFWDLEAK: forward M4 for 2019-1 / 2019-2 with cut-offs fitted on data before the target\n"
        + "=" * 78)
    mg = load_module(MERGED, "v2_merged_copy")
    ev = mg.load_events(MCACHE)                       # cached table, equal to the raw rebuild (stage data)
    D0 = mg.prep(ev)
    S = mg.static_sub(ev, D0)
    sidx = D0["sidx"]
    sem = D0["sem"][sidx]
    Ccap = np.minimum(D0["C"][sidx], L)
    y = np.log1p(Ccap)
    hv_used = Ccap > D0["heavy_thr"]
    arr, avail = mg.times(D0, "ires0")
    first = {s: float(arr[D0["sem"] == s].min()) for s in DEV}
    old = pd.read_parquet(os.path.join(MCACHE, "forward_ires0.parquet"))["M4"].values
    new = old.copy()
    F0 = pd.read_parquet(os.path.join(MCACHE, "feat_ires0.parquet"))
    rows = []
    for tgt, prior in FWD_TARGETS.items():
        m_tr = np.isin(sem, prior) & (avail[sidx] < first[tgt])
        m_te = sem == tgt
        thr, cuts = _cuts_from(ev, prior)
        t0 = time.time()
        X0 = mg.build_X(S, F0, arr[sidx])
        rep, _ = mg.fit_predict(X0[m_tr], y[m_tr], None, X0[m_te], mg.GROUPS["M4"], 3, clf=False)
        D = mg.prep(ev, fixed=(thr, cuts))
        H, R, RP, _ = mg.sweep(D, arr, avail)
        F = pd.DataFrame(np.hstack([H, R, RP]), columns=mg.HIST_COLS + mg.REL_COLS + mg.PERM_COLS)
        X = mg.build_X(S, F, arr[sidx])
        p, _ = mg.fit_predict(X[m_tr], y[m_tr], None, X[m_te], mg.GROUPS["M4"], 3, clf=False)
        new[m_te] = p
        for lbl, v in (("cached forward M4 (cut-offs 2018-1..2019-2)", old[m_te]),
                       ("refit here, same cut-offs (reproduction)", rep),
                       (f"refit, cut-offs from {prior[0]}..{prior[-1]}", p)):
            rows.append((tgt, lbl, int(m_tr.sum()), int(m_te.sum()), round(float(np.sqrt(((y[m_te] - v) ** 2).mean())), 4),
                         round(float(spearmanr(y[m_te], v).statistic), 4),
                         round(float(roc_auc_score(hv_used[m_te], v)), 4),
                         round(float(spearmanr(old[m_te], v).statistic), 4)))
        say(f"  {tgt}: heavy cut-off {thr:.4f}, tercile cuts {cuts[0]:.4f} {cuts[1]:.4f}; {time.time() - t0:.0f} s")
    say(pd.DataFrame(rows, columns=["target", "predictions", "n_train", "n_target", "rmse", "spearman",
                                    "auroc(C_cap>1.559)", "spearman_vs_cached"]).to_string(index=False))
    pd.DataFrame({"M4_new": new}).to_parquet(os.path.join(VC, "forward_ires0_M4_nolookahead.parquet"), index=False)
    dump("fwdleak")


def stage_fwdsim():
    say("=" * 78 + "\nFWDSIM: P2 ires0 pure, SPJF-M4 with cached vs look-ahead-free 2019 forward predictions\n"
        + "=" * 78)
    mg = load_module(MERGED, "v2_merged_copy")
    ev = mg.load_events(MCACHE)
    D = mg.prep(ev)
    S = mg.static_sub(ev, D)
    I = mg.p2_inputs(D, S, "ires0", MCACHE)
    new = pd.read_parquet(os.path.join(VC, "forward_ires0_M4_nolookahead.parquet"))["M4_new"].values
    rows = []
    for rep in range(5):
        a_ts, svc_ts, _, _ = mg.consolidate2(I["pool"], I["per_cs"], 3, mg.SEED * 100 + rep, "ts")
        a, svc, jidx, _ = mg.consolidate2(I["pool"], I["per_cs"], 3, mg.SEED * 100 + rep, "arr")
        W = mg.v1.busy_hour_work(a_ts, svc_ts)[0]
        k_prev = 10 ** 6
        for rho_t in (0.5, 0.8, 1.0):
            K = max(2, min(int(round(W / (3600.0 * rho_t))), k_prev - 1))
            k_prev = K
            wf = mg.simulate(a, svc, None, K, "fcfs").mean()
            wr = mg.simulate(a, svc, svc, K, "pri").mean()
            wo = mg.simulate(a, svc, I["P"]["M4"][jidx], K, "pri").mean()
            wn = mg.simulate(a, svc, new[jidx], K, "pri").mean()
            rows.append((rep, rho_t, K, wf, wr, wo, wn, (wf - wo) / (wf - wr), (wf - wn) / (wf - wr)))
    t = pd.DataFrame(rows, columns=["rep", "rho_target", "k", "fcfs", "sjf_ref", "spjf_m4_cached",
                                    "spjf_m4_nolookahead", "gain_cached", "gain_nolookahead"])
    say(t.groupby("rho_target")[["k", "fcfs", "sjf_ref", "spjf_m4_cached", "spjf_m4_nolookahead",
                                 "gain_cached", "gain_nolookahead"]].mean().round(4).to_string())
    dump("fwdsim")


# --------------------------------------------------------------------------- #
# auroc
# --------------------------------------------------------------------------- #
def stage_auroc(cfg, seed=3):
    import lightgbm as lgb
    from sklearn.metrics import roc_auc_score
    say("=" * 78 + f"\nAUROC: M4 heavy classifier refit, config {cfg}, seed {seed}, train 2018-1..2021-2, "
        f"test 2022-2\n" + "=" * 78)
    ev = pd.read_parquet(os.path.join(VC, "ev_min.parquet"))
    cuts = pd.read_csv(os.path.join(VC, "cuts.csv")).iloc[0]
    sub = ev["sub"].values
    sidx = np.flatnonzero(sub)
    arr, _ = clock(ev, cfg)
    a = arr[sidx]
    parts = []
    for s in DEV:
        parts.append(pd.read_parquet(os.path.join(PQ, "assessments", f"{s}.parquet")))
    ass = pd.concat(parts, ignore_index=True)[["semester", "class", "assessment", "type", "weight", "start",
                                               "end", "n_exercises"]]
    e = ev.iloc[sidx][["semester", "class", "assessment"]].reset_index(drop=True)
    m = e.merge(ass, on=["semester", "class", "assessment"], how="left", validate="many_to_one")
    assert len(m) == len(e)
    sec = lambda x: (x - pd.Timestamp("1970-01-01")).dt.total_seconds().values
    ctx = np.column_stack([(m["type"].astype(str).values == "exam"),
                           pd.to_numeric(m["weight"], errors="coerce").values,
                           pd.to_numeric(m["n_exercises"], errors="coerce").values,
                           (sec(m["end"]) - a) / 3600.0, (a - sec(m["start"])) / 3600.0,
                           np.floor(np.mod(a, 86400.0) / 3600.0), np.mod(np.floor(a / 86400.0) + 3.0, 7.0),
                           np.isin(e["semester"].values, REMOTE)]).astype("float32")
    code = pd.read_parquet(os.path.join(MCACHE, "ev.parquet"), columns=FEAT_CODE).values[sidx].astype("float32")
    hist = pd.read_parquet(os.path.join(MCACHE, f"feat_{cfg}.parquet"), columns=HIST).values.astype("float32")
    X = np.hstack([code, ctx, hist])
    Ccap = np.minimum(ev["C"].values[sidx], L)
    h = (Ccap > float(cuts.thr)).astype(int)
    sem = ev["semester"].values[sidx]
    tr, te = np.isin(sem, TRAIN_CORE + REMOTE), np.isin(sem, TEST)
    say(f"train rows {tr.sum():,} (heavy {h[tr].mean():.4f}), test rows {te.sum():,} (heavy {h[te].mean():.4f}); "
        f"{X.shape[1]} columns = 37 code + 8 context (rebuilt here from arrival) + 22 history (cached)")
    t0 = time.time()
    clf = lgb.LGBMClassifier(objective="binary", n_estimators=300, learning_rate=0.06, num_leaves=63,
                             min_child_samples=50, colsample_bytree=1.0, subsample=0.8, subsample_freq=1,
                             random_state=seed, verbose=-1, n_jobs=6).fit(X[tr], h[tr])
    p = clf.predict_proba(X[te])[:, 1]
    auc = roc_auc_score(h[te], p)
    say(f"refit here: test AUROC {auc:.4f} ({time.time() - t0:.0f} s)")
    rep = pd.read_csv(os.path.join(MCACHE, f"p1_{cfg}.csv"))
    r = rep[(rep.train == "remote") & (rep.model == "M4")]
    pr = pd.read_parquet(os.path.join(MCACHE, f"p1pred_{cfg}.parquet"))
    a3 = [roc_auc_score(h[te], pr[f"remote|M4|{s_}|h"].values) for s_ in (3, 4, 5)]
    say(f"merged copy's p1_{cfg}.csv, remote M4: seed 3 {float(r[r.seed == 3].auroc.iloc[0]):.4f}, "
        f"3-seed mean {r.auroc.mean():.4f}; AUROC recomputed from its cached predictions "
        f"{', '.join(f'{x:.4f}' for x in a3)} (mean {np.mean(a3):.4f})")
    say(f"refit vs cached seed-3 prediction: max |diff| of P(heavy) "
        f"{np.abs(p - pr['remote|M4|3|h'].values).max():.2e}")
    dump(f"auroc_{cfg}")


# --------------------------------------------------------------------------- #
# tables
# --------------------------------------------------------------------------- #
def stage_tables():
    from scipy.stats import spearmanr
    from sklearn.metrics import roc_auc_score
    say("=" * 78 + "\nTABLES: reported numbers recomputed from the merged copy's cached CSVs\n" + "=" * 78)
    rows = []
    for cfg in ("v1", "ires0", "ires600", "ires0_t600", "isub0", "isub60", "isub600", "isub3600"):
        p = os.path.join(MCACHE, f"p1_{cfg}.csv")
        if os.path.exists(p):
            d = pd.read_csv(p)
            d = d[d.train == "remote"].groupby("model").auroc.mean()
            rows.append(dict(config=cfg, **{m: round(d.get(m, np.nan), 4) for m in ("M1", "M2", "M4", "M5", "M6")}))
    say("P1 AUROC, train incl. remote, 3-seed mean:")
    say(pd.DataFrame(rows).to_string(index=False))
    for cfg in ("ires0", "isub0"):
        fs = [os.path.join(MCACHE, f"p2_{cfg}_rep{r}.csv") for r in range(5)]
        s2 = pd.concat([pd.read_csv(f) for f in fs if os.path.exists(f)], ignore_index=True)
        pure = s2[s2.setting == "pure"]
        key = ["rep", "rho_target"]
        F = pure[pure.policy == "FCFS"].set_index(key)
        R = pure[pure.policy == "SJF-ref"].set_index(key)
        pure = pure.set_index(key)
        pure = pure.assign(gain=(F.w_mean.reindex(pure.index) - pure.w_mean) /
                           (F.w_mean.reindex(pure.index) - R.w_mean.reindex(pure.index)))
        pure = pure.reset_index()
        t = pure.pivot_table(index="policy", columns="rho_target", values="gain", aggfunc="mean")
        say(f"\nP2 {cfg} pure, gain on mean wait (mean over {pure.rep.nunique()} overlays):")
        say(t.loc[[p for p in ("SPJF-M1", "SPJF-M4", "SPJF-M5", "SPJF-M4-d600", "SPJF-M4-v1feat",
                               "GUARD-M4-B30", "GUARD-M4-B120", "GUARD-M4-B600", "ADV-rev", "ADV-rev+G30")
                   if p in t.index]].round(3).to_string())
        fc = pure[pure.policy == "FCFS"].groupby("rho_target")[["k", "rho_busy", "w_mean"]].mean()
        say(f"FCFS per target level: mean k, realised busy-hour rho, mean wait:\n{fc.round(3).to_string()}")
        gx = pure[pure.policy.str.contains("GUARD|\\+G")].groupby("policy").max_excess.max()
        say("max per-job excess over FCFS at k > 1 (pure): " +
            ", ".join(f"{p} {v:.1f}" for p, v in gx.items()))
    g = pd.read_csv(os.path.join(MCACHE, "guardk1.csv"))
    say("\nguardk1.csv, max excess per B over predictors: " +
        ", ".join(f"{c} {g[c].max():.3f}" for c in g.columns if c.endswith("max_excess") and c.startswith("B")))
    # I-res arrival artefact: in same-second groups the reconstructed arrival order is the cost order
    ev = pd.read_parquet(os.path.join(VC, "ev_min.parquet"))
    sidx = np.flatnonzero(ev["sub"].values)
    rowof = np.full(len(ev), -1, np.int64)
    rowof[sidx] = np.arange(len(sidx))
    cuts = pd.read_csv(os.path.join(VC, "cuts.csv")).iloc[0]
    e = ev.iloc[sidx]
    tsec = e["ts"].values.astype("datetime64[s]").astype("int64")
    grp = pd.DataFrame({"s": e.semester.values, "u": e.user.values, "x": e.exercise.values, "t": tsec})
    ing = grp.duplicated(["s", "u", "x", "t"], keep=False).values
    te = np.isin(e.semester.values, TEST)
    Ccap = np.minimum(e["C"].values, L)
    hvy = Ccap > float(cuts.thr)
    rows = []
    for cfg in ("ires0", "isub0"):
        F = pd.read_parquet(os.path.join(MCACHE, f"feat_{cfg}.parquet"), columns=["ue_n", "ue_log_sec_since"])
        for lbl, m in (("same-second (user, exercise) group members", te & ing), ("other test rows", te & ~ing)):
            gap = F.ue_log_sec_since.values[m]
            fin = np.isfinite(gap)
            rho = spearmanr(gap[fin], np.log1p(Ccap[m][fin])).statistic if fin.sum() > 10 else np.nan
            au = (roc_auc_score(hvy[m][fin], gap[fin]) if 0 < hvy[m][fin].sum() < fin.sum() else np.nan)
            rows.append((cfg, lbl, int(m.sum()), round(float(fin.mean()), 3), round(float(rho), 3),
                         round(float(au), 3), round(float(hvy[m].mean()), 4)))
    say("\nI-res reconstruction: arrival = ts - C orders same-second members by cost.  ue_log_sec_since")
    say("(time since the user's previous same-exercise arrival) vs the row's own cost, test 2022-2:")
    say(pd.DataFrame(rows, columns=["config", "rows", "n", "share_with_prev", "spearman(gap, logC)",
                                    "AUROC(gap -> heavy)", "heavy_share"]).to_string(index=False))
    dump("tables")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True,
                    choices=["data", "features", "guard", "fwdleak", "fwdsim", "auroc", "tables"])
    ap.add_argument("--config", default="isub0")
    a = ap.parse_args()
    t0 = time.time()
    {"data": stage_data, "features": stage_features, "guard": stage_guard, "tables": stage_tables,
     "fwdleak": stage_fwdleak, "fwdsim": stage_fwdsim, "auroc": lambda: stage_auroc(a.config)}[a.stage]()
    print(f"[{a.stage}] done in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
