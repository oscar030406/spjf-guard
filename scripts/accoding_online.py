"""Online-clock scores of an ACcoding replay in one causal pass.

Under the online clock a job is scored at its arrival from the evaluated block's results
that completed strictly before it (`online_block_features`).  The package kernel reads a
job's score once, when it admits the job at its arrival instant, and by then every
completion before that instant has happened.  `_advance` below is `simulate_kernel`'s
loop, built from the same helpers, that stops before admitting a job with no score yet.
`online_scores` then folds the results completed strictly before that instant, in
completion order with ties by row as `online_block_features` does, queries the arriving
jobs' features, scores them and resumes.

The schedule up to an instant depends only on the scores of jobs that arrived by then,
and each score only on completions strictly before its arrival, so the scores this pass
produces are the unique fixed point that `online_fixed_point` iterates towards; started
from them, its first iteration reproduces them, which is the check that they are.
"""

from __future__ import annotations

import copy
import ctypes
import heapq

import numpy as np
from lightgbm.basic import _LIB, _c_str, _safe_call
from numba import njit

from prechecks.accoding_v2 import accoding_v2 as pre
from spjf_guard.sim.kernel import (
    MODE_GUARD,
    MODE_SKIP,
    NEG,
    S_LEN,
    S_ERR,
    S_NDISP,
    S_NEXT_ARRIVAL,
    S_NRUN,
    S_NSTARTED,
    S_NWAIT,
    _admit_arrivals,
    _apply_completions,
    _choose,
    _dispatch,
    _next_instant,
    _st_clear,
)
from spjf_guard.sim.policy import eta_fraction
from spjf_guard.sim.runner import DEFAULT_WINDOW, _mode_of

PAUSED, FINISHED, OVERFLOW = 0, 1, 2


def single_row_scorer(boosters, columns):
    """(score_rows, close): score_model_predict's ensemble mean on the given feature
    columns, row by row through LightGBM's single-row C API.  It runs the same tree code
    without building a predictor per call, which cost 0.1-0.4 ms at each pause of
    online_scores.  close() frees the C handles."""
    handles = []
    for booster in boosters:
        handle = ctypes.c_void_p()
        _safe_call(_LIB.LGBM_BoosterPredictForMatSingleRowFastInit(
            booster._handle, ctypes.c_int(0), ctypes.c_int(0),
            ctypes.c_int(booster.best_iteration), ctypes.c_int(0),
            ctypes.c_int32(len(columns)), _c_str("num_threads=1"), ctypes.byref(handle),
        ))
        handles.append(handle)
    out = np.empty(1, np.float64)
    out_ptr = out.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
    out_len = ctypes.c_int64()

    def score_rows(features):
        x = np.ascontiguousarray(features[:, columns])
        rows = [ctypes.c_void_p(x.ctypes.data + i * x.strides[0]) for i in range(len(x))]
        per_booster = []
        for handle in handles:
            p = np.empty(len(x), np.float64)
            for i, row in enumerate(rows):
                _safe_call(_LIB.LGBM_BoosterPredictForMatSingleRowFast(
                    handle, row, ctypes.byref(out_len), out_ptr
                ))
                p[i] = out[0]
            per_booster.append(p.astype(np.float32))
        return np.mean(per_booster, axis=0)

    def close():
        for handle in handles:
            _safe_call(_LIB.LGBM_FastConfigFree(handle))

    return score_rows, close


@njit(cache=True)
def _advance(
    t, a_us, s_us, score, scored, k, mode, b0_us, en, ed, bmax_us, ncap, mslots, gam_us,
    st, rt, rj, hk, hi, served, fifo, tre, lz, size, zs, fen_work, fen_count,
    wait_us, start_us, dispatch_index, disp_job,
):
    """simulate_kernel's loop from instant t; returns (t, PAUSED) before admitting a job
    whose score is not set, (t, FINISHED) when every job has started."""
    n = a_us.shape[0]
    horizon = np.int64(1) << 62
    while st[S_NSTARTED] < n:
        _apply_completions(t, st, rt, rj, s_us, fen_work, n, tre, lz, size, ed, mode)
        nxt = st[S_NEXT_ARRIVAL]
        if nxt < n and a_us[nxt] <= t and scored[nxt] == 0:
            return t, PAUSED
        _admit_arrivals(
            t, st, a_us, score, n, fifo, hk, hi, served, fen_work, zs, tre, lz, size,
            mslots, en, ed, b0_us, gam_us, bmax_us, mode,
        )
        if st[S_ERR] == 1:
            return t, OVERFLOW
        if st[S_NRUN] < k and st[S_NWAIT] > 0:
            j, forced = _choose(
                t, st, fifo, hk, hi, served, fen_work, fen_count, tre, lz, size, en, ed,
                bmax_us, ncap, mode,
            )
            start_us[j] = t
            disp_job[st[S_NDISP]] = j
            _dispatch(
                t, j, forced, st, a_us, s_us, wait_us, dispatch_index, served, rt, rj,
                fen_count, n, mode,
            )
            continue
        t = _next_instant(t, st, a_us, rt, n, horizon)
        if t >= horizon:
            break
    return t, FINISHED


def online_scores(trace, policy, k, online, order, score_rows, window=DEFAULT_WINDOW):
    """Scores (float32, trace order) of `policy`'s online replay.  `online` and `order` are
    online_fixed_point's; score_rows(X) scores feature rows as score_model_predict does."""
    if policy.age_credit_per_s > 0.0:
        raise ValueError("online scores take no age credit")
    a_us = np.ascontiguousarray(trace.arrival_us)
    s_us = np.ascontiguousarray(trace.service_us)
    n = len(a_us)
    rows = online["rows"][order]
    state = {name: copy.deepcopy(table) for name, table in online["state"].items()}
    fold, query = pre.history_functions(online["A"], state)

    mode = _mode_of(policy)
    en, ed = eta_fraction(policy.eta_k)
    guarding = mode == MODE_GUARD
    size = 1
    while size < window:
        size *= 2
    st = np.zeros(S_LEN, np.int64)
    rt = np.empty(k + 1, np.int64)
    rj = np.empty(k + 1, np.int64)
    hk = np.empty(n + 1, np.float64)
    hi = np.empty(n + 1, np.int64)
    served = np.zeros(n, np.uint8)
    fifo = np.empty(n + 1, np.int64)
    tre = np.empty(2 * size if guarding else 2, np.int64)
    lz = np.empty((2 * size if guarding else 2) // 2, np.int64)
    if guarding:
        _st_clear(tre, lz, size)
    zs = np.empty(n if guarding else 1, np.int64)
    fen_work = np.zeros((n + 1) if guarding else 1, np.int64)
    fen_count = np.zeros((n + 1) if mode == MODE_SKIP else 1, np.int64)
    wait_us = np.empty(n, np.int64)
    start_us = np.empty(n, np.int64)
    dispatch_index = np.empty(n, np.int64)
    disp_job = np.empty(n, np.int64)

    scores = np.empty(n, np.float32)
    score = np.zeros(n, np.float64)
    scored = np.zeros(n, np.uint8)
    completed = []  # (completion, row) of dispatched jobs not yet folded
    seen = 0
    t = np.int64(NEG)
    while True:
        t, status = _advance(
            t, a_us, s_us, score, scored, int(k), mode, int(policy.b0_us), int(en), int(ed),
            int(policy.bmax_us), int(policy.skip_count), int(window), int(policy.gam_us),
            st, rt, rj, hk, hi, served, fifo, tre, lz, size, zs, fen_work, fen_count,
            wait_us, start_us, dispatch_index, disp_job,
        )
        if status == OVERFLOW:
            raise RuntimeError(f"{policy.name}: the waiting ranks outgrew the window")
        if status == FINISHED:
            return scores
        for d in range(seen, int(st[S_NDISP])):
            j = disp_job[d]
            heapq.heappush(completed, (int(start_us[j] + s_us[j]), int(rows[j])))
        seen = int(st[S_NDISP])
        while completed and completed[0][0] < t:
            fold(heapq.heappop(completed)[1])
        first = int(st[S_NEXT_ARRIVAL])
        last = first
        while last < n and a_us[last] <= t:
            last += 1
        X = np.full((last - first, len(pre.ALLF)), pre.NAN, dtype=np.float32)
        for m, i in enumerate(range(first, last)):
            query(rows[i], X[m])
        batch = score_rows(X)
        scores[first:last] = batch
        score[first:last] = batch.astype(np.float64)
        scored[first:last] = 1
