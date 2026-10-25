"""Ordering by score inside fixed windows of W ranks, Block(W), in the package kernel.

sim/kernel.simulate_kernel, step for step in its score mode (as evidence/rl_base/
rl_kernel.py copies the loop), with one change: the heap orders the waiting jobs by
(rank // W, score, rank) instead of (score, rank).  Ranks are cut into consecutive blocks
of W jobs, and the job served is the one with the smallest score in the earliest block that
still has a waiting job.  This is the rule of evidence/referee_round4/maxwait_baseline.py
(simulate_rule with key_block = rank // W and no timer), a rank-block stand-in for
fixed-window ordering by predicted cost.  W = 1 is FCFS and W >= n is the package's score
order (SPJF); both must reproduce sim.kernel job for job.  Block(W) carries no per-job
promise, so nothing is asserted about its waits.
"""

from __future__ import annotations

import numpy as np
from numba import njit

from spjf_guard.sim import JobResults
from spjf_guard.sim.kernel import (
    MODE_SCORE,
    S_LEN,
    S_NDISP,
    S_NEXT_ARRIVAL,
    S_NFORCED,
    S_NHEAP,
    S_NRUN,
    S_NSTARTED,
    S_NWAIT,
    S_QW_FORCED,
    S_QW_TOTAL,
    _dispatch,
    _next_instant,
    _run_pop,
)


@njit(cache=False, inline="always")
def _before(key_a, idx_a, key_b, idx_b, w):
    """(idx_a // w, key_a, idx_a) < (idx_b // w, key_b, idx_b)."""
    block_a = idx_a // w
    block_b = idx_b // w
    if block_a != block_b:
        return block_a < block_b
    if key_a != key_b:
        return key_a < key_b
    return idx_a < idx_b


@njit(cache=False, inline="always")
def _block_push(key, idx, m, new_key, new_idx, w):
    """sim.kernel._score_push under the block order."""
    key[m] = new_key
    idx[m] = new_idx
    c = m
    while c > 0:
        p = (c - 1) >> 1
        if _before(key[c], idx[c], key[p], idx[p], w):
            key[p], key[c] = key[c], key[p]
            idx[p], idx[c] = idx[c], idx[p]
            c = p
        else:
            break
    return m + 1


@njit(cache=False, inline="always")
def _block_pop(key, idx, m, w):
    """sim.kernel._score_pop under the block order."""
    m -= 1
    key[0] = key[m]
    idx[0] = idx[m]
    c = 0
    while True:
        left = 2 * c + 1
        if left >= m:
            break
        right = left + 1
        b = left
        if right < m and _before(key[right], idx[right], key[left], idx[left], w):
            b = right
        if _before(key[b], idx[b], key[c], idx[c], w):
            key[b], key[c] = key[c], key[b]
            idx[b], idx[c] = idx[c], idx[b]
            c = b
        else:
            break
    return m


@njit(cache=False)
def simulate_block(a_us, s_us, score, k, w):
    n = a_us.shape[0]
    wait_us = np.empty(n, np.int64)
    start_us = np.empty(n, np.int64)
    dispatch_index = np.empty(n, np.int64)
    st = np.zeros(S_LEN, np.int64)
    rt = np.empty(k + 1, np.int64)
    rj = np.empty(k + 1, np.int64)
    hk = np.empty(n + 1, np.float64)
    hi = np.empty(n + 1, np.int64)
    served = np.zeros(n, np.uint8)
    fen_count = np.zeros(1, np.int64)
    horizon = np.int64(1) << 62
    t = -(np.int64(1) << 62)
    while st[S_NSTARTED] < n:
        # sim.kernel._apply_completions in MODE_SCORE
        while st[S_NRUN] > 0 and rt[0] <= t:
            st[S_NRUN] = _run_pop(rt, rj, st[S_NRUN])
        # sim.kernel._admit_arrivals in MODE_SCORE, keyed by block
        while st[S_NEXT_ARRIVAL] < n and a_us[st[S_NEXT_ARRIVAL]] <= t:
            i = st[S_NEXT_ARRIVAL]
            st[S_NHEAP] = _block_push(hk, hi, st[S_NHEAP], score[i], i, w)
            st[S_NWAIT] += 1
            st[S_NEXT_ARRIVAL] += 1
        if st[S_NRUN] < k and st[S_NWAIT] > 0:
            # sim.kernel._base_choice under the block order
            while served[hi[0]] == 1:
                st[S_NHEAP] = _block_pop(hk, hi, st[S_NHEAP], w)
            j = hi[0]
            st[S_NHEAP] = _block_pop(hk, hi, st[S_NHEAP], w)
            start_us[j] = t
            _dispatch(t, j, 0, st, a_us, s_us, wait_us, dispatch_index, served, rt, rj,
                      fen_count, n, MODE_SCORE)
            continue
        nxt = _next_instant(t, st, a_us, rt, n, horizon)
        if nxt >= horizon:
            break
        t = nxt
    return (wait_us, start_us, dispatch_index, st[S_NDISP], st[S_NFORCED], st[S_QW_TOTAL],
            st[S_QW_FORCED])


def run_block(arrival_us, service_us, score, k, w, name) -> JobResults:
    wait, start, dispatch, n_disp, n_forced, qw_total, qw_forced = simulate_block(
        np.ascontiguousarray(arrival_us, np.int64),
        np.ascontiguousarray(service_us, np.int64),
        np.ascontiguousarray(score, np.float64),
        int(k),
        int(w),
    )
    return JobResults(
        policy=name,
        servers=int(k),
        wait_us=wait,
        start_us=start,
        dispatch_index=dispatch,
        n_dispatch=int(n_disp),
        n_forced=int(n_forced),
        queue_weighted_dispatch=int(qw_total),
        queue_weighted_forced=int(qw_forced),
    )
