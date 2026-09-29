"""Stage 1: base arrays for the neural predictors.

Reads (read-only) the verified v2 cache: ev.parquet (events on the jittered clock) and
feat_ires0.parquet (leak-free per-submission features).  Rebuilds, for the PRIMARY config
ires0 (reading I-res, delta = 0 s, TEST-outcome lag 60 s, jittered clock):

    arrival[j] = ts'[j] - C[j],   available[j] = ts'[j]        (ts' = ts + u, u from the
                                                                keyed hash of the record id)

and the integer EVENT RANK that makes every visibility test an integer comparison.  The
event stream of service_precheck_v2.sweep() is sorted by (time, type, record) with

    type 0  a result becomes available          visible to a read at the SAME time
    type 1  a submission reads its features
    type 2  a record registers its existence    NOT visible to a read at the same time
    type 3  a result whose availability equals its own arrival (C == 0, delta 0)
                                                NOT visible to a read at the same time

so "record j's result is usable by submission i" is rank(avail[j], ty_j) < rank(arr[i], 1)
and "record j's existence is usable by submission i" is rank(arr[j], 2) < rank(arr[i], 1).
Ranks are assigned once by lexsort over (type, time); after that no float compares.

Outputs (cache directory, .npy/.npz): ids, ranks, target, split masks, and the M4/M5 design
matrix X built exactly as service_precheck_v2.build_X.

VERIFICATION: the exercise- and user-node statistics this script recomputes from its own
arrays are compared column by column against feat_ires0.parquet (ex_*, u_*, ex_nres,
u_nres).  An exact match proves the clock (jitter included), the availability rule and the
event ordering here are the ones the verified pipeline used.

Params: CACHE, OUT, CONFIG = ires0.  No randomness.
"""
from __future__ import annotations

import os
import sys

sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

from collections import deque
from math import log1p, sqrt

import numpy as np
import pandas as pd

CACHE = r"<cache-dir>\cb_v2_cache_r4"
OUT = r"<cache-dir>\pn"
HERE = os.path.dirname(os.path.abspath(__file__))

JITTER_KEY = "cbjitter20260919"
JITTER_ID = ["semester", "class", "user", "assessment", "exercise", "blk_i"]
L_CAP = 60.0
TRAIN_CORE = ["2018-1", "2018-2", "2019-1", "2019-2"]
REMOTE = ["2020-ERE", "2020-1", "2020-2", "2021-1", "2021-2"]
VALID = ["2022-1"]
TEST = ["2022-2"]
HOLDOUT = ["2023-1", "2023-2", "2024-1"]

FEAT_CODE = [
    "chars", "lines", "nonblank_lines", "max_line_len", "n_comment_lines",
    "n_while", "n_for", "n_input", "n_def", "n_if", "n_print", "n_range",
    "n_try", "n_class", "n_return", "n_lambda", "n_len", "n_append",
    "n_import", "imp_math", "imp_random", "imp_time", "imp_sys", "imp_os",
    "imp_numpy", "imp_itertools", "imp_string", "imp_other",
    "max_indent", "nest_loop_depth", "has_while_true", "has_recursion",
    "max_num_digits", "max_range_digits", "has_sleep", "has_evalexec", "has_open",
]
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
PERM_COLS = [c + "_perm" for c in REL_COLS]
X_COLS = FEAT_CODE + CTX_COLS + HIST_COLS + REL_COLS + PERM_COLS

LOG = open(os.path.join(HERE, "out_build_base.txt"), "w", encoding="utf-8")


def say(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    LOG.write(s + "\n")
    LOG.flush()


def jitter_u(ev, key=JITTER_KEY):
    idf = ev.reindex(columns=[c for c in JITTER_ID if c != "blk_i"]).astype(str)
    idf["blk_i"] = ev["blk_i"].values.astype(np.int64)
    h = pd.util.hash_pandas_object(idf, index=False, hash_key=key).values
    return (h >> np.uint64(11)).astype(np.float64) * 2.0 ** -53


def main():
    os.makedirs(OUT, exist_ok=True)
    ev = pd.read_parquet(os.path.join(CACHE, "ev.parquet"))
    say(f"events {len(ev):,}  semesters {sorted(ev['semester'].unique().tolist())}")
    for s in HOLDOUT:
        assert s not in set(ev["semester"].unique()), f"sealed semester {s} present"

    sub = (ev["kind"].astype(str).values == "submit") & ev["exec_time"].notna().values
    sidx = np.flatnonzero(sub)
    ns = len(sidx)
    say(f"submission rows {ns:,}")

    ts = ev["ts"].values.astype("datetime64[s]").astype("int64").astype("float64")
    u = jitter_u(ev)
    tsp = ts + u                                        # jittered clock ts'
    C = ev["exec_time"].values.astype("float64")
    Cz = np.nan_to_num(C)
    # ires0: I-res reading, delta = 0.  Submissions: arr = ts'-C, avail = ts'.
    arr_all = tsp - np.where(sub, Cz, 0.0)
    avail_all = np.where(sub, tsp, tsp + 60.0)          # TEST outcome lag 60 s (unused here)

    arr = arr_all[sidx]
    avail = avail_all[sidx]
    assert np.all(avail >= arr)

    # ---- global event ranks: lexsort over (type, time) ------------------------------
    # points: (avail, 0 or 3) per submission, (arr, 1) read, (arr, 2) register
    ty_av = np.where(avail == arr, 3, 0).astype(np.int64)
    T = np.concatenate([avail, arr, arr])
    TY = np.concatenate([ty_av, np.ones(ns, np.int64), np.full(ns, 2, np.int64)])
    o = np.lexsort((TY, T))
    ordkey = np.empty(len(T), np.int64)
    ordkey[o] = np.arange(len(T))
    # consolidate exact ties of (T, TY) to the same rank so that "<" is the right test
    Ts, TYs = T[o], TY[o]
    newgrp = np.r_[True, (Ts[1:] != Ts[:-1]) | (TYs[1:] != TYs[:-1])]
    grp = np.cumsum(newgrp) - 1
    rank_sorted = grp
    rank = np.empty(len(T), np.int64)
    rank[o] = rank_sorted
    r_avail = rank[:ns]
    r_read = rank[ns:2 * ns]
    r_reg = rank[2 * ns:]
    say(f"event ranks: {int(rank.max()) + 1:,} distinct (time,type) points over {len(T):,} points")

    # ---- ids ------------------------------------------------------------------------
    exc, _ = pd.factorize(ev["exercise"])
    usc, _ = pd.factorize(ev["user"])
    cls_s = ev["semester"].astype(str) + "|" + ev["class"].astype(str)
    clc, _ = pd.factorize(cls_s)
    asm_s = cls_s + "|" + ev["assessment"].astype(str)
    asc, _ = pd.factorize(asm_s)
    ex = exc[sidx].astype(np.int32); us = usc[sidx].astype(np.int32)
    cl = clc[sidx].astype(np.int32); asm = asc[sidx].astype(np.int32)
    NE, NU, NC, NA = int(ex.max()) + 1, int(us.max()) + 1, int(cl.max()) + 1, int(asm.max()) + 1
    say(f"nodes: exercise {NE:,}  user {NU:,}  class {NC:,}  assessment {NA:,}")

    sem = np.asarray(ev["semester"].astype(str))[sidx]
    Ccap = np.minimum(Cz[sidx], L_CAP)
    m_trcore = np.isin(sem, TRAIN_CORE)
    heavy_thr = float(np.quantile(np.minimum(ev["exec_time"].values[sidx], L_CAP)[m_trcore], .95))
    say(f"heavy threshold (train-core p95 of C_cap) = {heavy_thr:.6f} s")
    y = np.log1p(Ccap).astype(np.float32)
    hv = (Ccap > heavy_thr).astype(np.float32)
    errf = ev["has_error"].values.astype("float64")[sidx]
    ntc = ev["n_testcases"].values.astype("float64")[sidx]
    lg = np.log1p(Cz[sidx])

    # ---- verification pass: node statistics as-of each read -------------------------
    # replay availability and read events in rank order, keeping exactly the state that
    # sweep() keeps for exercise and user nodes.
    F = pd.read_parquet(os.path.join(CACHE, "feat_ires0.parquet"))
    assert len(F) == ns
    say("replaying the event stream to recompute ex_*/u_* node statistics ...")

    order = np.argsort(np.concatenate([r_avail, r_read, r_reg]), kind="stable")
    kind_arr = np.concatenate([np.zeros(ns, np.int8), np.ones(ns, np.int8), np.full(ns, 2, np.int8)])
    which = np.concatenate([np.arange(ns), np.arange(ns), np.arange(ns)])
    kl, wl = kind_arr[order].tolist(), which[order].tolist()
    exl, usl = ex.tolist(), us.tolist()
    lgl, hvl, erl, ntl = lg.tolist(), hv.astype("float64").tolist(), errf.tolist(), ntc.tolist()

    EX, U, EXN, UN = {}, {}, {}, {}
    outE = np.full((ns, 10), np.nan, np.float64)   # n_arr, mean, sd, p50, p90, max, err, heavy, ntc, nres
    outU = np.full((ns, 8), np.nan, np.float64)    # n_arr, mean, sd, p50, p90, err, heavy, nres
    for k, j in zip(kl, wl):
        if k == 1:
            e, uu = exl[j], usl[j]
            E = EX.get(e)
            if E is not None:
                nn, sl, sl2, ne, nh, sn, dq = E
                m = sl / nn
                s = sorted(dq); L = len(s) - 1
                outE[j] = (EXN.get(e, 0), m, sqrt(max(sl2 / nn - m * m, 0.0)),
                           s[min(L, int(.5 * L + .5))], s[min(L, int(.9 * L + .5))], s[-1],
                           ne / nn, nh / nn, sn / nn, nn)
            else:
                outE[j, 0] = EXN.get(e, 0); outE[j, 9] = 0
            Uu = U.get(uu)
            if Uu is not None:
                nn, sl, sl2, ne, nh, dq = Uu
                m = sl / nn
                s = sorted(dq); L = len(s) - 1
                outU[j] = (UN.get(uu, 0), m, sqrt(max(sl2 / nn - m * m, 0.0)),
                           s[min(L, int(.5 * L + .5))], s[min(L, int(.9 * L + .5))],
                           ne / nn, nh / nn, nn)
            else:
                outU[j, 0] = UN.get(uu, 0); outU[j, 7] = 0
        elif k == 2:
            EXN[exl[j]] = EXN.get(exl[j], 0) + 1
            UN[usl[j]] = UN.get(usl[j], 0) + 1
        else:
            e, uu = exl[j], usl[j]
            x, h_, er = lgl[j], hvl[j], erl[j]
            E = EX.get(e)
            if E is None:
                EX[e] = [1, x, x * x, er, h_, ntl[j], deque([x], maxlen=120)]
            else:
                E[0] += 1; E[1] += x; E[2] += x * x; E[3] += er; E[4] += h_
                E[5] += ntl[j]; E[6].append(x)
            Uu = U.get(uu)
            if Uu is None:
                U[uu] = [1, x, x * x, er, h_, deque([x], maxlen=120)]
            else:
                Uu[0] += 1; Uu[1] += x; Uu[2] += x * x; Uu[3] += er; Uu[4] += h_
                Uu[5].append(x)

    bad = 0
    for i, c in enumerate(["ex_n", "ex_mean_log", "ex_sd_log", "ex_p50_log", "ex_p90_log",
                           "ex_max_log", "ex_err_rate", "ex_heavy_rate", "ex_ntc_mean"]):
        a, b = outE[:, i].astype(np.float32), F[c].values.astype(np.float32)
        ok = np.allclose(a, b, rtol=1e-5, atol=1e-6, equal_nan=True)
        bad += (not ok)
        say(f"  match {c:16s} {'OK' if ok else 'MISMATCH  maxdiff=' + str(np.nanmax(np.abs(a - b)))}")
    for i, c in enumerate(["u_n", "u_mean_log", "u_sd_log", "u_p50_log", "u_p90_log",
                           "u_err_rate", "u_heavy_rate"]):
        a, b = outU[:, i].astype(np.float32), F[c].values.astype(np.float32)
        ok = np.allclose(a, b, rtol=1e-5, atol=1e-6, equal_nan=True)
        bad += (not ok)
        say(f"  match {c:16s} {'OK' if ok else 'MISMATCH  maxdiff=' + str(np.nanmax(np.abs(a - b)))}")
    for arr_, c in ((outE[:, 9], "ex_nres"), (outU[:, 7], "u_nres")):
        ok = np.array_equal(arr_.astype(np.int64), F[c].values.astype(np.int64))
        bad += (not ok)
        say(f"  match {c:16s} {'OK' if ok else 'MISMATCH'}")
    if bad:
        raise SystemExit("clock / availability reconstruction does not match the verified cache")
    say("clock, jitter and availability rule reproduce the verified cache exactly.")

    # ---- design matrix X (exactly service_precheck_v2.build_X) ----------------------
    e_ = ev.iloc[sidx]
    code = np.column_stack([e_[c].values.astype("float32") for c in FEAT_CODE])
    a_end = (e_["a_end"] - pd.Timestamp("1970-01-01")).dt.total_seconds().values.astype("float64")
    a_start = (e_["a_start"] - pd.Timestamp("1970-01-01")).dt.total_seconds().values.astype("float64")
    hour = np.floor(np.mod(arr, 86400.0) / 3600.0)
    dow = np.mod(np.floor(arr / 86400.0) + 3.0, 7.0)
    ctx = np.column_stack([
        (e_["a_type"].astype(str).values == "exam").astype("float32"),
        pd.to_numeric(e_["a_weight"], errors="coerce").values.astype("float32"),
        pd.to_numeric(e_["a_nex"], errors="coerce").values.astype("float32"),
        (a_end - arr) / 3600.0, (arr - a_start) / 3600.0, hour, dow,
        e_["remote"].values.astype("float32")]).astype("float32")
    X = np.empty((ns, len(X_COLS)), np.float32)
    X[:, :len(FEAT_CODE)] = code
    X[:, len(FEAT_CODE):len(FEAT_CODE) + len(CTX_COLS)] = ctx
    X[:, len(FEAT_CODE) + len(CTX_COLS):] = F[HIST_COLS + REL_COLS + PERM_COLS].values
    say(f"X {X.shape} columns {len(X_COLS)}")

    np.save(os.path.join(OUT, "X.npy"), X)
    np.savez(os.path.join(OUT, "base.npz"),
             ex=ex, us=us, cl=cl, asm=asm, sem=sem.astype("U8"),
             r_avail=r_avail, r_read=r_read, r_reg=r_reg,
             arr=arr, avail=avail, y=y, hv=hv, Ccap=Ccap.astype(np.float32),
             lg=lg.astype(np.float32), errf=errf.astype(np.float32), ntc=ntc.astype(np.float32),
             ex_nres=F["ex_nres"].values.astype(np.int32),
             u_nres=F["u_nres"].values.astype(np.int32),
             heavy_thr=np.float64(heavy_thr),
             user_str=np.asarray(ev["user"].astype(str))[sidx].astype("U24"),
             NE=NE, NU=NU, NC=NC, NA=NA,
             a_is_exam=ctx[:, 0].astype(np.float32))
    with open(os.path.join(OUT, "xcols.txt"), "w") as f:
        f.write("\n".join(X_COLS))
    say(f"wrote {OUT}")
    for nm, m in (("train_core", m_trcore), ("remote+", np.isin(sem, TRAIN_CORE + REMOTE)),
                  ("valid 2022-1", np.isin(sem, VALID)), ("test 2022-2", np.isin(sem, TEST))):
        say(f"  {nm:14s} n={int(m.sum()):>7,}  heavy rate {hv[m].mean():.4%}")


if __name__ == "__main__":
    main()
