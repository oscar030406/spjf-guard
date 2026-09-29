"""Event-driven k-server non-preemptive simulator with the overtake-budget guard.

Written from scratch for this study (the project's own kernel in
evidence/guard_variants/ is not imported); cd_sim.py checks this kernel against an
independent O(waiting) brute-force simulator on a small slice before it is used.

Model.  k identical servers, non-preemptive, work conserving, service times in (0, L].
Jobs carry a stable arrival rank (arrival time, input index) and the arrays must already
be in that order.  At each instant the simulator processes completions, then arrivals,
then dispatches.  The scheduler learns a job's true service time only when it completes.

    over[q] = total true service of jobs of rank > q that COMPLETED while q was waiting
            = TC - F(q),   TC = total completed work, F(q) = completed work of ranks <= q
    budget(q, t) = min( C0 + eps * (t - a_q),  Bcap )        eps = en/ed,  Bcap optional
    fired(q)     = over[q] >= budget(q, t)
    dispatch: if the fired set is non-empty serve its SMALLEST-RANK member, else serve
              the waiting job with the smallest predicted cost (ties to smaller rank).

Condition algebra (int64 microseconds, exact):
    over[q] >= C0 + (en/ed)(t - a_q)
    <=>  en*a_us[q] - ed*C0 - ed*F(q)  >=  en*t_us - ed*TC
         Z(q)  (leaf value, suffix range-add on completion)   T(t)  (per decision)
The cap is the same test with en = 0, ed = 1, C0 = Bcap, so it runs as a second tree;
the fired set of the capped rule is the union of the two, and its smallest rank is the
smaller of the two leftmost hits.
"""
import sys

sys.dont_write_bytecode = True

import numpy as np
from numba import njit

NEG = -(1 << 62)
POL_FCFS = 0
POL_SPJF = 1
POL_GUARD = 2


@njit(cache=True, inline="always")
def _apply(tre, lz, size, v, delta):
    tre[v] += delta
    if v < size:
        lz[v] += delta


@njit(cache=True)
def _pull(tre, lz, v):
    v >>= 1
    while v >= 1:
        a = tre[2 * v]
        b = tre[2 * v + 1]
        tre[v] = lz[v] + (a if a > b else b)
        v >>= 1


@njit(cache=True)
def _range_add(tre, lz, size, l, r, delta):
    """add delta to leaves [l, r] inclusive."""
    if l > r:
        return
    lo = l + size
    hi = r + size + 1
    l0, r0 = lo, hi
    while lo < hi:
        if lo & 1:
            _apply(tre, lz, size, lo, delta)
            lo += 1
        if hi & 1:
            hi -= 1
            _apply(tre, lz, size, hi, delta)
        lo >>= 1
        hi >>= 1
    _pull(tre, lz, l0)
    _pull(tre, lz, r0 - 1)


@njit(cache=True)
def _point_assign(tre, lz, size, pos, val):
    leaf = pos + size
    acc = 0
    v = leaf >> 1
    while v >= 1:
        acc += lz[v]
        v >>= 1
    tre[leaf] = val - acc
    _pull(tre, lz, leaf)


@njit(cache=True)
def _leftmost_ge(tre, lz, size, T):
    if tre[1] < T:
        return -1
    v = 1
    acc = 0
    while v < size:
        acc += lz[v]
        if tre[2 * v] + acc >= T:
            v = 2 * v
        else:
            v = 2 * v + 1
    return v - size




@njit(cache=True)
def _hpush_p(key, rnk, n, k_, r_):
    key[n] = k_
    rnk[n] = r_
    i = n
    while i > 0:
        p = (i - 1) >> 1
        if key[p] > key[i] or (key[p] == key[i] and rnk[p] > rnk[i]):
            key[p], key[i] = key[i], key[p]
            rnk[p], rnk[i] = rnk[i], rnk[p]
            i = p
        else:
            break
    return n + 1


@njit(cache=True)
def _hpop_p(key, rnk, n):
    tk = key[0]
    tr = rnk[0]
    n -= 1
    key[0] = key[n]
    rnk[0] = rnk[n]
    i = 0
    while True:
        l = 2 * i + 1
        r = l + 1
        s = i
        if l < n and (key[l] < key[s] or (key[l] == key[s] and rnk[l] < rnk[s])):
            s = l
        if r < n and (key[r] < key[s] or (key[r] == key[s] and rnk[r] < rnk[s])):
            s = r
        if s == i:
            break
        key[s], key[i] = key[i], key[s]
        rnk[s], rnk[i] = rnk[i], rnk[s]
        i = s
    return tk, tr, n


# --------------------------- the simulator -------------------------------- #
@njit(cache=True)
def simulate(arrival, serv, pred, k, policy, en, ed, C0_us, Bcap_us):
    """Return (start, n_fired, n_dispatch).  Bcap_us < 0 disables the cap."""
    n = arrival.shape[0]
    start = np.full(n, -1.0, np.float64)
    a_us = np.empty(n, np.int64)
    w_us = np.empty(n, np.int64)
    for i in range(n):
        a_us[i] = np.int64(round(arrival[i] * 1e6))
        w_us[i] = np.int64(round(serv[i] * 1e6))
    size = 1
    while size < n:
        size *= 2
    use_tree = policy == POL_GUARD
    t1 = np.full(2 * size, NEG, np.int64) if use_tree else np.zeros(2, np.int64)
    l1 = np.zeros(2 * size if use_tree else 2, np.int64)
    use_cap = use_tree and Bcap_us >= 0
    t2 = np.full(2 * size, NEG, np.int64) if use_cap else np.zeros(2, np.int64)
    l2 = np.zeros(2 * size if use_cap else 2, np.int64)
    ckey = np.empty(k + 2, np.float64)     # completion time
    crnk = np.empty(k + 2, np.int64)       # rank of the job on that server
    n_busy = 0
    pkey = np.empty(n + 1, np.float64)
    prnk = np.empty(n + 1, np.int64)
    n_heap = 0
    done = np.zeros(n, np.uint8)
    head = 0
    i_arr = 0
    n_wait = 0
    TC = np.int64(0)
    n_disp = 0
    n_fired = 0
    t = arrival[0]
    INF = 1e30
    while n_disp < n:
        while n_busy > 0 and ckey[0] <= t:
            ct, cr, n_busy = _hpop_p(ckey, crnk, n_busy)
            TC += w_us[cr]
            if use_tree:
                _range_add(t1, l1, size, cr, n - 1, -ed * w_us[cr])
            if use_cap:
                _range_add(t2, l2, size, cr, n - 1, -w_us[cr])
        while i_arr < n and arrival[i_arr] <= t:
            n_wait += 1
            n_heap = _hpush_p(pkey, prnk, n_heap, pred[i_arr], i_arr)
            if use_tree:
                _point_assign(t1, l1, size, i_arr, en * a_us[i_arr] - ed * C0_us - ed * TC)
            if use_cap:
                _point_assign(t2, l2, size, i_arr, -Bcap_us - TC)
            i_arr += 1
        while n_busy < k and n_wait > 0:
            q = -1
            if policy == POL_FCFS:
                while done[head] == 1:
                    head += 1
                q = head
            elif policy == POL_SPJF:
                while True:
                    kk, rr, n_heap = _hpop_p(pkey, prnk, n_heap)
                    if done[rr] == 0:
                        q = rr
                        break
            else:
                q1 = -1
                q2 = -1
                q1 = _leftmost_ge(t1, l1, size, en * np.int64(round(t * 1e6)) - ed * TC)
                if use_cap:
                    q2 = _leftmost_ge(t2, l2, size, -TC)
                qf = q1
                if qf < 0 or (q2 >= 0 and q2 < qf):
                    qf = q2
                if qf >= 0:
                    q = qf
                    n_fired += 1
                else:
                    while True:
                        kk, rr, n_heap = _hpop_p(pkey, prnk, n_heap)
                        if done[rr] == 0:
                            q = rr
                            break
            start[q] = t
            done[q] = 1
            n_wait -= 1
            n_disp += 1
            n_busy = _hpush_p(ckey, crnk, n_busy, t + serv[q], q)
            if use_tree:
                _point_assign(t1, l1, size, q, NEG)
            if use_cap:
                _point_assign(t2, l2, size, q, NEG)
        nt = INF
        if i_arr < n and arrival[i_arr] < nt:
            nt = arrival[i_arr]
        if n_busy > 0 and ckey[0] < nt:
            nt = ckey[0]
        if nt >= INF:
            break
        t = nt
    return start, n_fired, n_disp
