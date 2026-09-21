"""In_i and Out_i by one sweep over the dispatch sequence, plus the O(n^2) definition.

    In_i  = sum{ x_j : rank j > i and j dispatched before i }
    Out_i = sum{ x_j : rank j < i and i dispatched before j }

Sweep (O(n log n)).  Walk the dispatch sequence.  A Fenwick tree over ARRIVAL RANK holds
the metered work of the jobs dispatched so far, and `tot` their total.  When i is
dispatched, the tree contains exactly {j : j -< i}, so

    In_i  = tot - prefix(i)          work of dispatched jobs of rank > i
    Out_i = pre[i] - prefix(i-1)     rank < i, total minus the part already dispatched

where pre is the static prefix sum of x over ranks.  Then x_i is inserted.  Every
quantity is int64 microseconds, so the sweep is exact.

Same-phase share (Remark 1.0/1.3).  A phase is a maximal run of dispatches at one clock
instant; a job dispatched in i's own phase before i contributes its whole x_j to In_i and
its whole x_j to rho_new, and the two cancel inside Theorem 1's proof, so this part of
In_i is pure bookkeeping.  `in_same_phase` measures it with a second Fenwick that is
filled over a phase and unwound at its end -- O(phase log n), so O(n log n) overall.

`in_out_quadratic` is the definition written out as a double loop; `ir_validate.py`
checks the sweep against it on random small instances and on a 5,000-job real slice.
"""
from __future__ import annotations

import numpy as np
from numba import njit


@njit(cache=True, inline="always")
def _fen_add(F, n, i, v):
    p = i + 1
    while p <= n:
        F[p] += v
        p += p & -p


@njit(cache=True, inline="always")
def _fen_pref(F, i):
    """sum over ranks 0..i (i < 0 gives 0)."""
    s = 0
    p = i + 1
    while p > 0:
        s += F[p]
        p -= p & -p
    return s


@njit(cache=True)
def dispatch_order(dord):
    """order[p] = the job dispatched at sequence position p."""
    n = dord.shape[0]
    order = np.empty(n, np.int64)
    for j in range(n):
        order[dord[j]] = j
    return order


@njit(cache=True)
def in_out_fenwick(svc_us, order):
    n = svc_us.shape[0]
    F = np.zeros(n + 1, np.int64)
    pre = np.zeros(n + 1, np.int64)
    for j in range(n):
        pre[j + 1] = pre[j] + svc_us[j]
    In = np.empty(n, np.int64)
    Out = np.empty(n, np.int64)
    tot = 0
    for p in range(n):
        i = order[p]
        # i itself is not in the tree yet, so prefix(i) == prefix(i-1)
        up_to_i = _fen_pref(F, i)
        In[i] = tot - up_to_i                # dispatched already, rank > i
        Out[i] = pre[i] - up_to_i            # rank < i, not dispatched yet
        _fen_add(F, n, i, svc_us[i])
        tot += svc_us[i]
    return In, Out


@njit(cache=True)
def in_same_phase(svc_us, order, dtime):
    """Part of In_i contributed by jobs dispatched in i's OWN phase."""
    n = svc_us.shape[0]
    G = np.zeros(n + 1, np.int64)
    same = np.zeros(n, np.int64)
    p = 0
    while p < n:
        t0 = dtime[order[p]]
        q = p
        while q < n and dtime[order[q]] == t0:
            q += 1
        tot = 0
        for r in range(p, q):
            i = order[r]
            same[i] = tot - _fen_pref(G, i)
            _fen_add(G, n, i, svc_us[i])
            tot += svc_us[i]
        for r in range(p, q):                # unwind, so G is all zeros again
            i = order[r]
            _fen_add(G, n, i, -svc_us[i])
        p = q
    return same


@njit(cache=True)
def phase_id(order, dtime):
    """ph[j] = index of the phase j was dispatched in."""
    n = order.shape[0]
    ph = np.empty(n, np.int64)
    c = -1
    prev = np.nan
    for p in range(n):
        j = order[p]
        if p == 0 or dtime[j] != prev:
            c += 1
            prev = dtime[j]
        ph[j] = c
    return ph


@njit(cache=True)
def in_out_quadratic(svc_us, dord):
    """The definition, written out.  O(n^2) -- small instances only."""
    n = svc_us.shape[0]
    In = np.zeros(n, np.int64)
    Out = np.zeros(n, np.int64)
    for i in range(n):
        di = dord[i]
        for j in range(n):
            if j > i and dord[j] < di:
                In[i] += svc_us[j]
            elif j < i and dord[j] > di:
                Out[i] += svc_us[j]
    return In, Out


@njit(cache=True)
def in_same_phase_quadratic(svc_us, dord, dtime):
    n = svc_us.shape[0]
    same = np.zeros(n, np.int64)
    for i in range(n):
        di = dord[i]
        for j in range(n):
            if j > i and dord[j] < di and dtime[j] == dtime[i]:
                same[i] += svc_us[j]
    return same
