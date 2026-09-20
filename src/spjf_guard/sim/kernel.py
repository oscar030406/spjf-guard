"""The event-driven k-server non-preemptive kernel, in exact integer microseconds.

One kernel covers every policy in the study; the rule is fixed by its parameters.

    k identical servers, non-preemptive, work-conserving (no server idles while a job
    waits), every service time at most L.  Jobs carry the rank induced by (arrival, input
    index) and the input arrays are already in that order.  The scheduler reads a job's
    true service time only when that job completes.

    over[q](t) = total true service of the jobs of rank above q that have COMPLETED by t.
                 Held for the whole waiting set at once as over[q] = TC - F(q), with TC
                 the total completed work and F a Fenwick prefix sum over ranks.
    budget(q,t) = min(B0 + gam w_q + (en/ed)(t - a_q), Bmax), w_q = jobs waiting at a_q
    E(t)        = {q waiting : over[q](t) >= budget(q,t)}

    dispatch: serve the minimum-rank member of E(t) when E(t) is non-empty, otherwise
    serve whatever the base policy chooses (smallest score, ties to the smaller rank).

Serving the minimum-rank member is what makes the per-job bound hold when budgets differ
between jobs: a job is overtaken only at instants at which its own budget is unspent.  At
a constant threshold over[q] is non-increasing in rank, so the fired set is non-empty
exactly when the head belongs to it and the rule degenerates to a test on the head.

The firing test is a segment tree over a window of waiting ranks supporting suffix
range-add and "leftmost leaf with value at least T", after rewriting the condition as

    en a_q - ed B0 - ed F(q)  >=  en t - ed TC

whose left side is a per-job value changed only by range-add at completions and whose
right side depends on the clock alone.  Every quantity is int64 microseconds, so the test
is exact and no float comparison decides a dispatch.  Each event costs O(log n).

Modes: 0 FCFS, 1 base score alone, 2 work-budget guard, 3 dispatch-charged finite skip.
"""

from __future__ import annotations

import numpy as np
from numba import njit

NEG = -(1 << 62)

MODE_FCFS = 0
MODE_SCORE = 1
MODE_GUARD = 2
MODE_SKIP = 3

# indices into the scalar state vector carried through the helpers
S_NRUN = 0
S_NHEAP = 1
S_FIFO_HEAD = 2
S_FIFO_TAIL = 3
S_NEXT_ARRIVAL = 4
S_NWAIT = 5
S_NSTARTED = 6
S_NDISP = 7
S_NFORCED = 8
S_QW_TOTAL = 9
S_QW_FORCED = 10
S_COMPLETED_WORK = 11
S_WINDOW_BASE = 12
S_ERR = 13
S_NDISPATCHED_RANKS = 14
S_NREBUILD = 15
S_MAX_SPAN = 16
S_LEN = 17


# --------------------------------------------------------------------------- #
# segment tree: suffix range add, query "leftmost leaf with value >= T"
# Lazy tags sit on internal nodes and are never pushed down: the true maximum of a
# subtree is tre[node] plus the tags of its strict ancestors.
# --------------------------------------------------------------------------- #
@njit(cache=True)
def _st_clear(tre, lz, size):
    for i in range(2 * size):
        tre[i] = NEG
    for i in range(size):
        lz[i] = 0


@njit(cache=True, inline="always")
def _st_pull(tre, lz, node):
    while node >= 1:
        x = tre[2 * node]
        y = tre[2 * node + 1]
        tre[node] = (x if x > y else y) + lz[node]
        node >>= 1


@njit(cache=True)
def _st_set(tre, lz, size, pos, val):
    node = 1
    acc = 0
    half = size
    while half > 1:
        acc += lz[node]
        half >>= 1
        node = 2 * node + 1 if (pos & half) else 2 * node
    tre[node] = val - acc
    _st_pull(tre, lz, node >> 1)


@njit(cache=True)
def _st_add_suffix(tre, lz, size, lo, val):
    if lo >= size:
        return
    if lo < 0:
        lo = 0
    left = lo + size
    right = 2 * size
    l0 = left
    r0 = right - 1
    while left < right:
        if left & 1:
            tre[left] += val
            if left < size:
                lz[left] += val
            left += 1
        if right & 1:
            right -= 1
            tre[right] += val
            if right < size:
                lz[right] += val
        left >>= 1
        right >>= 1
    _st_pull(tre, lz, l0 >> 1)
    _st_pull(tre, lz, r0 >> 1)


@njit(cache=True)
def _st_leftmost(tre, lz, size, threshold):
    if tre[1] < threshold:
        return -1
    node = 1
    acc = 0
    while node < size:
        acc += lz[node]
        if tre[2 * node] + acc >= threshold:
            node = 2 * node
        else:
            node = 2 * node + 1
    return node - size


@njit(cache=True, inline="always")
def _fen_add(tree, n, rank, value):
    p = rank + 1
    while p <= n:
        tree[p] += value
        p += p & -p


@njit(cache=True, inline="always")
def _fen_pref(tree, rank):
    s = 0
    p = rank + 1
    while p > 0:
        s += tree[p]
        p -= p & -p
    return s


# --------------------------------------------------------------------------- #
# min-heaps
# --------------------------------------------------------------------------- #
@njit(cache=True, inline="always")
def _score_push(key, idx, m, new_key, new_idx):
    key[m] = new_key
    idx[m] = new_idx
    c = m
    while c > 0:
        p = (c - 1) >> 1
        if key[p] > key[c] or (key[p] == key[c] and idx[p] > idx[c]):
            key[p], key[c] = key[c], key[p]
            idx[p], idx[c] = idx[c], idx[p]
            c = p
        else:
            break
    return m + 1


@njit(cache=True, inline="always")
def _score_pop(key, idx, m):
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
        if right < m and (
            key[right] < key[left] or (key[right] == key[left] and idx[right] < idx[left])
        ):
            b = right
        if key[b] < key[c] or (key[b] == key[c] and idx[b] < idx[c]):
            key[b], key[c] = key[c], key[b]
            idx[b], idx[c] = idx[c], idx[b]
            c = b
        else:
            break
    return m


@njit(cache=True, inline="always")
def _run_push(rt, rj, nrun, done_us, job):
    rt[nrun] = done_us
    rj[nrun] = job
    c = nrun
    while c > 0:
        p = (c - 1) >> 1
        if rt[p] > rt[c]:
            rt[p], rt[c] = rt[c], rt[p]
            rj[p], rj[c] = rj[c], rj[p]
            c = p
        else:
            break
    return nrun + 1


@njit(cache=True, inline="always")
def _run_pop(rt, rj, nrun):
    nrun -= 1
    rt[0] = rt[nrun]
    rj[0] = rj[nrun]
    c = 0
    while True:
        left = 2 * c + 1
        if left >= nrun:
            break
        right = left + 1
        b = left
        if right < nrun and rt[right] < rt[left]:
            b = right
        if rt[b] < rt[c]:
            rt[b], rt[c] = rt[c], rt[b]
            rj[b], rj[c] = rj[c], rj[b]
            c = b
        else:
            break
    return nrun


# --------------------------------------------------------------------------- #
# event handling
# --------------------------------------------------------------------------- #
@njit(cache=True)
def _apply_completions(t, st, rt, rj, s_us, fen_work, n, tre, lz, size, ed, mode):
    """Charge every job completing at or before t.  Service times are read here and
    nowhere earlier, which is what makes the wrapper implementable."""
    while st[S_NRUN] > 0 and rt[0] <= t:
        c = rj[0]
        st[S_NRUN] = _run_pop(rt, rj, st[S_NRUN])
        if mode == MODE_GUARD:
            work = s_us[c]
            st[S_COMPLETED_WORK] += work
            _fen_add(fen_work, n, c, work)
            _st_add_suffix(tre, lz, size, c - st[S_WINDOW_BASE], -ed * work)


@njit(cache=True)
def _rebuild_window(st, fifo, served, fen_work, zs, tre, lz, size, mslots, ed, arrival_rank):
    """Slide the segment tree's window of ranks forward when the live span outgrows it."""
    while served[fifo[st[S_FIFO_HEAD]]] == 1:
        st[S_FIFO_HEAD] += 1
    new_base = fifo[st[S_FIFO_HEAD]]
    if arrival_rank - new_base >= mslots:
        st[S_ERR] = 1
        return
    _st_clear(tre, lz, size)
    for p in range(st[S_FIFO_HEAD], st[S_FIFO_TAIL]):
        q = fifo[p]
        if served[q] == 1:
            continue
        _st_set(tre, lz, size, q - new_base, zs[q] - ed * _fen_pref(fen_work, q))
    st[S_WINDOW_BASE] = new_base
    st[S_NREBUILD] += 1


@njit(cache=True)
def _admit_arrivals(
    t,
    st,
    a_us,
    score,
    n,
    fifo,
    hk,
    hi,
    served,
    fen_work,
    zs,
    tre,
    lz,
    size,
    mslots,
    en,
    ed,
    b0_us,
    gam_us,
    bmax_us,
    mode,
):
    """Register every job arriving at or before t, after the completions at t.

    A job's constant budget is `B0 + gam * (jobs waiting when it arrived)`, clipped to the
    cap.  Clipping changes no schedule, because the budget is a minimum with the cap
    anyway, and it keeps the exact integer test inside int64 for any gamma.
    """
    while st[S_NEXT_ARRIVAL] < n and a_us[st[S_NEXT_ARRIVAL]] <= t:
        i = st[S_NEXT_ARRIVAL]
        if mode == MODE_GUARD:
            if st[S_NWAIT] == 0:
                st[S_WINDOW_BASE] = i
            elif i - st[S_WINDOW_BASE] >= mslots:
                _rebuild_window(st, fifo, served, fen_work, zs, tre, lz, size, mslots, ed, i)
                if st[S_ERR] == 1:
                    return
            span = i - st[S_WINDOW_BASE] + 1
            if span > st[S_MAX_SPAN]:
                st[S_MAX_SPAN] = span
            cb = b0_us + gam_us * st[S_NWAIT]
            if bmax_us > 0 and cb > bmax_us:
                cb = bmax_us
            zs[i] = en * a_us[i] - ed * cb
            _st_set(tre, lz, size, i - st[S_WINDOW_BASE], zs[i] - ed * _fen_pref(fen_work, i))
        if mode != MODE_SCORE:
            fifo[st[S_FIFO_TAIL]] = i
            st[S_FIFO_TAIL] += 1
        if mode != MODE_FCFS:
            st[S_NHEAP] = _score_push(hk, hi, st[S_NHEAP], score[i], i)
        st[S_NWAIT] += 1
        st[S_NEXT_ARRIVAL] += 1


@njit(cache=True, inline="always")
def _fifo_head(st, fifo, served):
    while served[fifo[st[S_FIFO_HEAD]]] == 1:
        st[S_FIFO_HEAD] += 1
    return fifo[st[S_FIFO_HEAD]]


@njit(cache=True, inline="always")
def _base_choice(st, hk, hi, served):
    while served[hi[0]] == 1:
        st[S_NHEAP] = _score_pop(hk, hi, st[S_NHEAP])
    j = hi[0]
    st[S_NHEAP] = _score_pop(hk, hi, st[S_NHEAP])
    return j


@njit(cache=True)
def _fired_member(t, st, fifo, served, fen_work, tre, lz, size, en, ed, bmax_us):
    """Minimum-rank member of E(t), or -1 when E(t) is empty."""
    head = _fifo_head(st, fifo, served)
    if bmax_us > 0 and st[S_COMPLETED_WORK] - _fen_pref(fen_work, head) >= bmax_us:
        return head
    pos = _st_leftmost(tre, lz, size, en * t - ed * st[S_COMPLETED_WORK])
    if pos >= 0:
        return pos + st[S_WINDOW_BASE]
    return -1


@njit(cache=True)
def _skip_member(st, fifo, served, fen_count, ncap):
    """The head when it has been passed at least `ncap` times, else -1.  The count is
    non-increasing in rank, so the head is the minimum-rank member of the fired set."""
    head = _fifo_head(st, fifo, served)
    if st[S_NDISPATCHED_RANKS] - _fen_pref(fen_count, head) >= ncap:
        return head
    return -1


@njit(cache=True)
def _choose(
    t, st, fifo, hk, hi, served, fen_work, fen_count, tre, lz, size, en, ed, bmax_us, ncap, mode
):
    """(job, forced) for this dispatch epoch."""
    if mode == MODE_FCFS:
        j = _fifo_head(st, fifo, served)
        st[S_FIFO_HEAD] += 1
        return j, 1
    if mode == MODE_SCORE:
        return _base_choice(st, hk, hi, served), 0
    if mode == MODE_SKIP:
        cand = _skip_member(st, fifo, served, fen_count, ncap)
    else:
        cand = _fired_member(t, st, fifo, served, fen_work, tre, lz, size, en, ed, bmax_us)
    if cand >= 0:
        j = cand
        forced = 1
    else:
        j = _base_choice(st, hk, hi, served)
        forced = 0
    if mode == MODE_GUARD:
        _st_set(tre, lz, size, j - st[S_WINDOW_BASE], NEG)
    return j, forced


@njit(cache=True)
def _dispatch(
    t, j, forced, st, a_us, s_us, wait_us, dispatch_index, served, rt, rj, fen_count, n, mode
):
    served[j] = 1
    st[S_QW_TOTAL] += st[S_NWAIT]
    if forced == 1:
        st[S_NFORCED] += 1
        st[S_QW_FORCED] += st[S_NWAIT]
    st[S_NWAIT] -= 1
    wait_us[j] = t - a_us[j]
    dispatch_index[j] = st[S_NDISP]
    st[S_NDISP] += 1
    st[S_NSTARTED] += 1
    if mode == MODE_SKIP:
        st[S_NDISPATCHED_RANKS] += 1
        _fen_add(fen_count, n, j, 1)
    st[S_NRUN] = _run_push(rt, rj, st[S_NRUN], t + s_us[j], j)


@njit(cache=True)
def _next_instant(t, st, a_us, rt, n, horizon):
    nxt = rt[0] if st[S_NRUN] > 0 else horizon
    if st[S_NEXT_ARRIVAL] < n and a_us[st[S_NEXT_ARRIVAL]] < nxt:
        nxt = a_us[st[S_NEXT_ARRIVAL]]
    if nxt < t:
        nxt = t
    return nxt


@njit(cache=True)
def simulate_kernel(a_us, s_us, score, k, mode, b0_us, en, ed, bmax_us, ncap, mslots, gam_us=0):
    """Run one policy over one trace.  Every time is an int64 microsecond count.

    Returns (wait_us, dispatch_index, start_us, n_disp, n_forced, qw_total, qw_forced,
    n_rebuild, max_span, err).  err = 1 means the segment-tree window was too small for
    the live span of waiting ranks, which invalidates the run.
    """
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
    fifo = np.empty(n + 1, np.int64)
    guarding = mode == MODE_GUARD
    size = 1
    while size < mslots:
        size *= 2
    tsize = 2 * size if guarding else 2
    tre = np.empty(tsize, np.int64)
    lz = np.empty(tsize // 2, np.int64)
    if guarding:
        _st_clear(tre, lz, size)
    zs = np.empty(n if guarding else 1, np.int64)
    fen_work = np.zeros((n + 1) if guarding else 1, np.int64)
    fen_count = np.zeros((n + 1) if mode == MODE_SKIP else 1, np.int64)
    horizon = np.int64(1) << 62
    t = -(np.int64(1) << 62)
    while st[S_NSTARTED] < n:
        _apply_completions(t, st, rt, rj, s_us, fen_work, n, tre, lz, size, ed, mode)
        _admit_arrivals(
            t,
            st,
            a_us,
            score,
            n,
            fifo,
            hk,
            hi,
            served,
            fen_work,
            zs,
            tre,
            lz,
            size,
            mslots,
            en,
            ed,
            b0_us,
            gam_us,
            bmax_us,
            mode,
        )
        if st[S_ERR] == 1:
            break
        if st[S_NRUN] < k and st[S_NWAIT] > 0:
            j, forced = _choose(
                t,
                st,
                fifo,
                hk,
                hi,
                served,
                fen_work,
                fen_count,
                tre,
                lz,
                size,
                en,
                ed,
                bmax_us,
                ncap,
                mode,
            )
            start_us[j] = t
            _dispatch(
                t,
                j,
                forced,
                st,
                a_us,
                s_us,
                wait_us,
                dispatch_index,
                served,
                rt,
                rj,
                fen_count,
                n,
                mode,
            )
            continue
        nxt = _next_instant(t, st, a_us, rt, n, horizon)
        if nxt >= horizon:
            break
        t = nxt
    return (
        wait_us,
        dispatch_index,
        start_us,
        st[S_NDISP],
        st[S_NFORCED],
        st[S_QW_TOTAL],
        st[S_QW_FORCED],
        st[S_NREBUILD],
        st[S_MAX_SPAN],
        st[S_ERR],
    )
