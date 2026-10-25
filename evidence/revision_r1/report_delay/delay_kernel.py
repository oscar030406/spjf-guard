"""The production static kernel with completion reports that reach the guard late.

Copied from src/spjf_guard/sim/kernel.py (segment tree, Fenwick tree and heaps verbatim;
the source file is not edited).  The event loop is rewritten with server identities and
the late-charge models of evidence/stale_charging/sim_stale.py:

  U   one shared counter; the charge of job c, completed at f_c, is applied at f_c + d_c.
  A1  as U, and a server applies its own last completion to the shared counter
      immediately before it pulls its next job (report-before-pull).
  A2  each server dispatches from its own view: its own completions are in it at once,
      another server's completion c enters it at f_c + d_c.

Order at one instant, as in sim_stale: completions (servers freed), charges due by t,
arrivals, dispatches.  A free server is the lowest-index one (sorder 0) or the
highest-index one (sorder 1).  Every charge goes through the pending heap, so delta = 0
runs the same code path; there every model is Algorithm 1 exactly.

over_v[q](t) = applied charges of ranks above q in view v, held as TC_v - F_v(q) with a
Fenwick tree and one segment tree per view (k views for A2, one otherwise).
"""

from __future__ import annotations

import numpy as np
from numba import njit

NEG = -(1 << 62)

MODE_FCFS = 0
MODE_SCORE = 1
MODE_GUARD = 2

MODEL_U = 0
MODEL_A1 = 1
MODEL_A2 = 2
MODEL_NAMES = ("U", "A1", "A2")


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
# late charges
# --------------------------------------------------------------------------- #
@njit(cache=True)
def _charge(v, c, s_us, n, fen, tre, lz, size, wbase, ed, cw):
    """Apply the charge of completed job c to view v."""
    work = s_us[c]
    cw[v] += work
    _fen_add(fen[v], n, c, work)
    _st_add_suffix(tre[v], lz[v], size, c - wbase, -ed * work)


@njit(cache=True)
def _rebuild_views(nview, fifo, fhead, ftail, served, fen, zs, tre, lz, size, ed, new_base):
    for v in range(nview):
        _st_clear(tre[v], lz[v], size)
        for p in range(fhead, ftail):
            q = fifo[p]
            if served[q] == 1:
                continue
            _st_set(tre[v], lz[v], size, q - new_base, zs[q] - ed * _fen_pref(fen[v], q))


@njit(cache=True)
def simulate_delay(
    a_us, s_us, score, k, mode, b0_us, en, ed, bmax_us, mslots, gam_us,
    model, delay_us, sorder, record,
):
    """Run one policy over one trace with late charges.  Every time is int64 microseconds.

    delay_us[c] is the report delay of job c.  record = True fills rec[v, c] with the
    number of dispatches made when the charge of c entered view v (-1: never), the
    quantity sim_stale.py calls appg and app2.

    Returns (wait_us, dispatch_index, start_us, server, n_disp, n_forced, qw_total,
    qw_forced, n_rebuild, max_span, err, rec).  err = 1: the window was too small.
    """
    n = a_us.shape[0]
    guarding = mode == MODE_GUARD
    nview = k if (guarding and model == MODEL_A2) else 1
    wait_us = np.empty(n, np.int64)
    start_us = np.empty(n, np.int64)
    dispatch_index = np.empty(n, np.int64)
    srv_of = np.empty(n, np.int32)
    busy = np.zeros(k, np.int64)
    sjob = np.full(k, -1, np.int64)
    pend = np.full(k, -1, np.int64)
    npt = n + 1 if guarding else 1
    pt = np.empty(npt, np.int64)
    pj = np.empty(npt, np.int64)
    applied = np.zeros(n if (guarding and model == MODEL_A1) else 1, np.uint8)
    rec = np.full((nview if record else 1, n if record else 1), -1, np.int64)
    hk = np.empty(n + 1, np.float64)
    hi = np.empty(n + 1, np.int64)
    served = np.zeros(n, np.uint8)
    fifo = np.empty(n + 1, np.int64)
    size = 1
    while size < mslots:
        size *= 2
    tre = np.empty((nview, 2 * size if guarding else 2), np.int64)
    lz = np.empty((nview, size if guarding else 1), np.int64)
    if guarding:
        for v in range(nview):
            _st_clear(tre[v], lz[v], size)
    zs = np.empty(n if guarding else 1, np.int64)
    fen = np.zeros((nview, (n + 1) if guarding else 1), np.int64)
    cw = np.zeros(nview, np.int64)

    horizon = np.int64(1) << 62
    npend = 0
    nbusy = 0
    nheap = 0
    fhead = 0
    ftail = 0
    nxt = 0
    nwait = 0
    nstarted = 0
    ndisp = 0
    nforced = 0
    qw_total = 0
    qw_forced = 0
    wbase = 0
    err = 0
    nrebuild = 0
    maxspan = 0
    t = a_us[0] if n > 0 else 0
    while nstarted < n:
        # 1. completions at or before t free their servers; the charge is reported late
        for s in range(k):
            c = sjob[s]
            if c >= 0 and busy[s] <= t:
                sjob[s] = -1
                nbusy -= 1
                if guarding:
                    if model == MODEL_A2:
                        _charge(s, c, s_us, n, fen, tre, lz, size, wbase, ed, cw)
                        if record:
                            rec[s, c] = ndisp
                    elif model == MODEL_A1:
                        pend[s] = c
                    npend = _run_push(pt, pj, npend, busy[s] + delay_us[c], c)
        # 2. charges due by t
        while npend > 0 and pt[0] <= t:
            c = pj[0]
            npend = _run_pop(pt, pj, npend)
            if model == MODEL_A2:
                for v in range(nview):
                    if v != srv_of[c]:
                        _charge(v, c, s_us, n, fen, tre, lz, size, wbase, ed, cw)
                        if record:
                            rec[v, c] = ndisp
            elif model == MODEL_U or applied[c] == 0:
                if model == MODEL_A1:
                    applied[c] = 1
                _charge(0, c, s_us, n, fen, tre, lz, size, wbase, ed, cw)
                if record:
                    rec[0, c] = ndisp
        # 3. arrivals at or before t
        while nxt < n and a_us[nxt] <= t:
            i = nxt
            if guarding:
                if nwait == 0:
                    wbase = i
                elif i - wbase >= mslots:
                    while served[fifo[fhead]] == 1:
                        fhead += 1
                    new_base = fifo[fhead]
                    if i - new_base >= mslots:
                        err = 1
                        break
                    _rebuild_views(
                        nview, fifo, fhead, ftail, served, fen, zs, tre, lz, size, ed, new_base
                    )
                    wbase = new_base
                    nrebuild += 1
                span = i - wbase + 1
                if span > maxspan:
                    maxspan = span
                cb = b0_us + gam_us * nwait
                if bmax_us > 0 and cb > bmax_us:
                    cb = bmax_us
                zs[i] = en * a_us[i] - ed * cb
                for v in range(nview):
                    _st_set(tre[v], lz[v], size, i - wbase, zs[i] - ed * _fen_pref(fen[v], i))
            if mode != MODE_SCORE:
                fifo[ftail] = i
                ftail += 1
            if mode != MODE_FCFS:
                nheap = _score_push(hk, hi, nheap, score[i], i)
            nwait += 1
            nxt += 1
        if err == 1:
            break
        # 4. one dispatch
        if nbusy < k and nwait > 0:
            s = -1
            if sorder == 0:
                for x in range(k):
                    if sjob[x] < 0:
                        s = x
                        break
            else:
                for x in range(k - 1, -1, -1):
                    if sjob[x] < 0:
                        s = x
                        break
            if mode == MODE_FCFS:
                while served[fifo[fhead]] == 1:
                    fhead += 1
                j = fifo[fhead]
                fhead += 1
                forced = 1
            elif mode == MODE_SCORE:
                while served[hi[0]] == 1:
                    nheap = _score_pop(hk, hi, nheap)
                j = hi[0]
                nheap = _score_pop(hk, hi, nheap)
                forced = 0
            else:
                if model == MODEL_A1 and pend[s] >= 0:
                    c = pend[s]
                    pend[s] = -1
                    if applied[c] == 0:
                        applied[c] = 1
                        _charge(0, c, s_us, n, fen, tre, lz, size, wbase, ed, cw)
                        if record:
                            rec[0, c] = ndisp
                v = s if model == MODEL_A2 else 0
                while served[fifo[fhead]] == 1:
                    fhead += 1
                head = fifo[fhead]
                cand = -1
                if bmax_us > 0 and cw[v] - _fen_pref(fen[v], head) >= bmax_us:
                    cand = head
                else:
                    pos = _st_leftmost(tre[v], lz[v], size, en * t - ed * cw[v])
                    if pos >= 0:
                        cand = pos + wbase
                if cand >= 0:
                    j = cand
                    forced = 1
                else:
                    while served[hi[0]] == 1:
                        nheap = _score_pop(hk, hi, nheap)
                    j = hi[0]
                    nheap = _score_pop(hk, hi, nheap)
                    forced = 0
                for v2 in range(nview):
                    _st_set(tre[v2], lz[v2], size, j - wbase, NEG)
            served[j] = 1
            qw_total += nwait
            if forced == 1:
                nforced += 1
                qw_forced += nwait
            nwait -= 1
            wait_us[j] = t - a_us[j]
            start_us[j] = t
            dispatch_index[j] = ndisp
            ndisp += 1
            nstarted += 1
            srv_of[j] = s
            sjob[s] = j
            busy[s] = t + s_us[j]
            nbusy += 1
            continue
        nt = horizon
        for s in range(k):
            if sjob[s] >= 0 and busy[s] < nt:
                nt = busy[s]
        if nxt < n and a_us[nxt] < nt:
            nt = a_us[nxt]
        if nt >= horizon:
            break
        if nt < t:
            nt = t
        t = nt
    return (
        wait_us, dispatch_index, start_us, srv_of, ndisp, nforced, qw_total, qw_forced,
        nrebuild, maxspan, err, rec,
    )
