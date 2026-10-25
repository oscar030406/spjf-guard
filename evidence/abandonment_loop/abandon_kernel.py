"""Closed-loop kernel with abandonment and resubmission (model in MODEL.md).

A copy of evidence/closed_loop/closed_kernel.py (helpers verbatim) whose run adds one
pass per instant: a waiting attempt whose patience runs out is removed lazily, the way
the package removes a dispatched job (its rank is marked in `served`, its segment-tree
leaf set to NEG), and the job is either resubmitted at that instant as a new attempt
with a new rank, or withdrawn.  The late-submission drop treatment of closed_loop is not
carried over (MODEL.md section 4).

Ranks live in their own space of capacity `rank_cap` >= n (a resubmission takes a new
rank); `orig_of_rank[r]` is the input job that took rank `r`.  Every time is an exact
int64 microsecond count.
"""

from __future__ import annotations

import numpy as np
from numba import njit

NEG = -(1 << 62)

MODE_FCFS = 0
MODE_SCORE = 1
MODE_GUARD = 2

GATE_SUBMIT = 0
"""delta < 0: the next submission was made before the previous result was available."""
GATE_RESULT = 1
"""delta >= 0: the next submission followed the previous result by delta."""

S_NRUN = 0
S_NHEAP = 1
S_FIFO_HEAD = 2
S_FIFO_TAIL = 3
S_NWAIT = 5
S_NSTARTED = 6
S_NDISP = 7
S_NFORCED = 8
S_QW_TOTAL = 9
S_QW_FORCED = 10
S_COMPLETED_WORK = 11
S_WINDOW_BASE = 12
S_ERR = 13
S_NRANKS = 14
S_NREBUILD = 15
S_MAX_SPAN = 16
S_NARR = 17
S_NABANDON = 18
S_NRESUB = 19
S_NWITHDRAWN = 20
S_LEN = 21

INF_PATIENCE = np.int64(1) << 60
STATUS_SERVED = 1
STATUS_WITHDRAWN = 2
ERR_WINDOW = 1
ERR_RANK_CAP = 2


# --------------------------------------------------------------------------- #
# segment tree (verbatim from spjf_guard.sim.kernel)
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
# heaps
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


# the arrival queue: min-heap on (release instant, input index), so that equal arrival
# instants are ranked in input order -- the package's (arrival, input index) convention.
@njit(cache=True, inline="always")
def _arr_push(key, idx, m, new_key, new_idx):
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
def _arr_pop(key, idx, m):
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


# --------------------------------------------------------------------------- #
# the run
# --------------------------------------------------------------------------- #
@njit(cache=True)
def _rebuild_window(st, fifo, served, fen_work, zs, tre, lz, size, mslots, ed, arrival_rank):
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
    head = _fifo_head(st, fifo, served)
    if bmax_us > 0 and st[S_COMPLETED_WORK] - _fen_pref(fen_work, head) >= bmax_us:
        return head
    pos = _st_leftmost(tre, lz, size, en * t - ed * st[S_COMPLETED_WORK])
    if pos >= 0:
        return pos + st[S_WINDOW_BASE]
    return -1



# --------------------------------------------------------------------------- #
# the seeded draws (MODEL.md section 2); the reference calls these same functions
# --------------------------------------------------------------------------- #
@njit(cache=True, inline="always")
def _mix(x):
    x = (x ^ (x >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
    x = (x ^ (x >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
    return x ^ (x >> np.uint64(31))


@njit(cache=True)
def draw_u(seed, job, attempt, stream):
    """Uniform in (0, 1) keyed by (seed, job, attempt, stream) and nothing else."""
    h = _mix(_mix(_mix(np.uint64(seed)) ^ np.uint64(job)) ^ np.uint64(4 * attempt + stream))
    return (np.float64(h >> np.uint64(11)) + 0.5) / 9007199254740992.0


@njit(cache=True)
def patience_us(seed, job, attempt, mean_us):
    """Exponential patience with mean `mean_us`, floored at 1 us; mean <= 0 is infinite."""
    if mean_us <= 0.0:
        return INF_PATIENCE
    return np.int64(-mean_us * np.log(draw_u(seed, job, attempt, 0))) + 1


@njit(cache=True)
def resubmits(seed, job, attempt, p_resub, max_resub):
    return attempt < max_resub and draw_u(seed, job, attempt, 1) < p_resub


# --------------------------------------------------------------------------- #
# the run
# --------------------------------------------------------------------------- #
@njit(cache=True)
def simulate_abandon(
    a0_us,
    s_us,
    score,
    succ,
    gate,
    delta_us,
    offset_us,
    k,
    mode,
    b0_us,
    en,
    ed,
    bmax_us,
    mslots,
    gam_us,
    closed,
    seed,
    mean_patience_us,
    p_resub,
    max_resub,
    rank_cap,
    open_order,
):
    """One policy on one trace, with per-user gating and abandonment.

    `closed = 0` disables gating (every job's first attempt at its recorded arrival);
    `open_order` is then the input indices sorted by (a0, index), fed into the arrival
    heap as the clock reaches them so the heap stays small.
    `mean_patience_us <= 0` is infinite patience.  Returns
    (wait_us, a_prime_us, a_first_us, end_us, status, n_att, counters, err): per input
    job the wait of the served attempt (-1 if withdrawn), the arrival of its last
    attempt, of its first attempt, the instant it ended (start of service or
    withdrawal), STATUS_SERVED / STATUS_WITHDRAWN, the index of its last attempt;
    counters is (n_disp, n_forced, qw_total, qw_forced, n_abandon, n_resub,
    n_withdrawn, n_rebuild, max_span, n_ranks).  err = ERR_RANK_CAP means rank_cap was
    too small, ERR_WINDOW that the segment-tree window was.
    """
    n = a0_us.shape[0]
    wait_us = np.full(n, -1, np.int64)
    a_prime = np.full(n, -1, np.int64)
    a_first = np.full(n, -1, np.int64)
    end_us = np.full(n, -1, np.int64)
    status = np.zeros(n, np.uint8)
    att = np.zeros(n, np.int64)

    st = np.zeros(S_LEN, np.int64)
    rt = np.empty(k + 1, np.int64)
    rj = np.empty(k + 1, np.int64)
    scoring = mode != MODE_FCFS
    hk = np.empty(rank_cap + 1 if scoring else 1, np.float64)
    hi = np.empty(rank_cap + 1 if scoring else 1, np.int64)
    served = np.zeros(rank_cap, np.uint8)
    fifo = np.empty(rank_cap + 1 if mode != MODE_SCORE else 1, np.int64)
    orig_of_rank = np.empty(rank_cap, np.int64)
    ak = np.empty(n + 1, np.int64)
    ai = np.empty(n + 1, np.int64)
    bk = np.empty(rank_cap + 1, np.int64)  # abandonment timers: (due instant, rank)
    bi = np.empty(rank_cap + 1, np.int64)
    nab = 0

    guarding = mode == MODE_GUARD
    size = 1
    while size < mslots:
        size *= 2
    tsize = 2 * size if guarding else 2
    tre = np.empty(tsize, np.int64)
    lz = np.empty(tsize // 2, np.int64)
    if guarding:
        _st_clear(tre, lz, size)
    zs = np.empty(rank_cap if guarding else 1, np.int64)
    fen_work = np.zeros((rank_cap + 1) if guarding else 1, np.int64)

    # seed the arrival queue (a job has at most one pending entry at any time)
    nah = 0
    nopen = 0
    if closed == 1:
        for i in range(n):
            if gate[i] == 2:  # a first submission of its user: recorded arrival
                nah = _arr_push(ak, ai, nah, a0_us[i], i)

    horizon = np.int64(1) << 62
    t = -(np.int64(1) << 62)
    while True:
        # ---- completions at t, and the result-gated successors they release ----
        while st[S_NRUN] > 0 and rt[0] <= t:
            done = rt[0]
            c = rj[0]
            st[S_NRUN] = _run_pop(rt, rj, st[S_NRUN])
            o = orig_of_rank[c]
            if guarding:
                work = s_us[o]
                st[S_COMPLETED_WORK] += work
                _fen_add(fen_work, rank_cap, c, work)
                _st_add_suffix(tre, lz, size, c - st[S_WINDOW_BASE], -ed * work)
            if closed == 1:
                nx = succ[o]
                if nx >= 0 and gate[nx] == GATE_RESULT:
                    nah = _arr_push(ak, ai, nah, done + delta_us[nx], nx)

        # ---- abandonments due at or before t ----
        while nab > 0 and bk[0] <= t:
            due = bk[0]
            r = bi[0]
            nab = _arr_pop(bk, bi, nab)
            if served[r] == 1:
                continue  # dispatched before its patience ran out
            served[r] = 1
            if guarding:
                _st_set(tre, lz, size, r - st[S_WINDOW_BASE], NEG)
            st[S_NWAIT] -= 1
            st[S_NABANDON] += 1
            o = orig_of_rank[r]
            if resubmits(seed, o, att[o], p_resub, max_resub):
                att[o] += 1
                st[S_NRESUB] += 1
                nah = _arr_push(ak, ai, nah, due, o)
            else:
                status[o] = STATUS_WITHDRAWN
                end_us[o] = due
                st[S_NWITHDRAWN] += 1
                if closed == 1:
                    nx = succ[o]
                    if nx >= 0 and gate[nx] == GATE_RESULT:
                        nah = _arr_push(ak, ai, nah, due + delta_us[nx], nx)

        # ---- arrivals at t ----
        if closed == 0:
            while nopen < n and a0_us[open_order[nopen]] <= t:
                nah = _arr_push(ak, ai, nah, a0_us[open_order[nopen]], open_order[nopen])
                nopen += 1
        while nah > 0 and ak[0] <= t:
            o = ai[0]
            rel = ak[0]
            nah = _arr_pop(ak, ai, nah)
            a_prime[o] = rel
            if att[o] == 0:
                a_first[o] = rel
                nx = succ[o]
                if closed == 1 and nx >= 0 and gate[nx] == GATE_SUBMIT:
                    nah = _arr_push(ak, ai, nah, rel + offset_us[nx], nx)
            i = st[S_NRANKS]
            if i >= rank_cap:
                st[S_ERR] = ERR_RANK_CAP
                break
            orig_of_rank[i] = o
            st[S_NRANKS] += 1
            if guarding:
                if st[S_NWAIT] == 0:
                    st[S_WINDOW_BASE] = i
                elif i - st[S_WINDOW_BASE] >= mslots:
                    _rebuild_window(
                        st, fifo, served, fen_work, zs, tre, lz, size, mslots, ed, i
                    )
                    if st[S_ERR] != 0:
                        break
                span = i - st[S_WINDOW_BASE] + 1
                if span > st[S_MAX_SPAN]:
                    st[S_MAX_SPAN] = span
                cb = b0_us + gam_us * st[S_NWAIT]
                if bmax_us > 0 and cb > bmax_us:
                    cb = bmax_us
                zs[i] = en * rel - ed * cb
                _st_set(tre, lz, size, i - st[S_WINDOW_BASE], zs[i] - ed * _fen_pref(fen_work, i))
            if mode != MODE_SCORE:
                fifo[st[S_FIFO_TAIL]] = i
                st[S_FIFO_TAIL] += 1
            if scoring:
                st[S_NHEAP] = _score_push(hk, hi, st[S_NHEAP], score[o], i)
            nab = _arr_push(bk, bi, nab, rel + patience_us(seed, o, att[o], mean_patience_us), i)
            st[S_NWAIT] += 1
            st[S_NARR] += 1
        if st[S_ERR] != 0:
            break

        # ---- one dispatch ----
        if st[S_NRUN] < k and st[S_NWAIT] > 0:
            if mode == MODE_FCFS:
                j = _fifo_head(st, fifo, served)
                st[S_FIFO_HEAD] += 1
                forced = 1
            elif mode == MODE_SCORE:
                j = _base_choice(st, hk, hi, served)
                forced = 0
            else:
                cand = _fired_member(
                    t, st, fifo, served, fen_work, tre, lz, size, en, ed, bmax_us
                )
                if cand >= 0:
                    j = cand
                    forced = 1
                else:
                    j = _base_choice(st, hk, hi, served)
                    forced = 0
                _st_set(tre, lz, size, j - st[S_WINDOW_BASE], NEG)
            served[j] = 1
            st[S_QW_TOTAL] += st[S_NWAIT]
            if forced == 1:
                st[S_NFORCED] += 1
                st[S_QW_FORCED] += st[S_NWAIT]
            st[S_NWAIT] -= 1
            o = orig_of_rank[j]
            wait_us[o] = t - a_prime[o]
            end_us[o] = t
            status[o] = STATUS_SERVED
            st[S_NDISP] += 1
            st[S_NSTARTED] += 1
            st[S_NRUN] = _run_push(rt, rj, st[S_NRUN], t + s_us[o], j)
            continue

        # ---- advance the clock ----
        while nab > 0 and served[bi[0]] == 1:  # drop timers of attempts already gone
            nab = _arr_pop(bk, bi, nab)
        nxt = rt[0] if st[S_NRUN] > 0 else horizon
        if nah > 0 and ak[0] < nxt:
            nxt = ak[0]
        if closed == 0 and nopen < n and a0_us[open_order[nopen]] < nxt:
            nxt = a0_us[open_order[nopen]]
        if nab > 0 and bk[0] < nxt:
            nxt = bk[0]
        if nxt < t:
            nxt = t
        if nxt >= horizon:
            break
        t = nxt

    counters = np.array(
        [
            st[S_NDISP],
            st[S_NFORCED],
            st[S_QW_TOTAL],
            st[S_QW_FORCED],
            st[S_NABANDON],
            st[S_NRESUB],
            st[S_NWITHDRAWN],
            st[S_NREBUILD],
            st[S_MAX_SPAN],
            st[S_NRANKS],
        ],
        np.int64,
    )
    return wait_us, a_prime, a_first, end_us, status, att, counters, st[S_ERR]
