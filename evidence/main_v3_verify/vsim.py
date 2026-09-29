"""Independent k-server non-preemptive simulator, written for the audit of main_v3.

Nothing here imports guardkern, refsim or service_precheck_v2.  The policy definitions are
taken from docs/research_plan.md chapters 4-5:

    k identical servers, non-preemptive, work conserving (never idle while a job waits).
    Rank order = (arrival, input index); the input arrays are already in that order.
    Events at one instant: completions, then arrivals, then one dispatch.

    over[q]      = true service of the jobs of rank > q that COMPLETED while q waited
    budget(q,t)  = min(B0 + eta*k*(t - a_q), Bmax)
    fired(t)     = {waiting q : over[q] >= budget(q,t)}
    dispatch      = smallest-rank fired job if any, else the base policy's choice
                    (base = smallest predicted cost, ties to the smaller rank)

    finite-skip baseline: no work budget; a waiting job fires when Ncap jobs of larger
    rank have completed during its wait.

Exact arithmetic: over, budgets and the clock in integer microseconds, eta*k as an exact
fraction en/ed, so the firing test never depends on floating point.

    fired(q,t)  <=>  over[q] >= Bmax                        (capped branch)
                 or  en*a_us[q] - ed*B0_us - ed*F(q) >= en*t_us - ed*TC   (sloped branch)

with F(q) = completed work of ranks <= q (Fenwick) and TC = all completed work, so
over[q] = TC - F(q).  min(x, Bmax) is reached by either branch, which is why the two
tests are or-ed.  The leftmost fired rank comes from a lazy max-segment-tree over the
whole rank range (range add on a suffix, "leftmost leaf >= T").
"""
from __future__ import annotations

import os
import sys
from fractions import Fraction

sys.dont_write_bytecode = True
for _v in ("PYTHONHOME", "PYTHONPATH", "UV_INTERNAL__PYTHONHOME"):
    os.environ.pop(_v, None)
os.environ.setdefault("NUMBA_NUM_THREADS", "4")
os.environ.setdefault("OMP_NUM_THREADS", "4")
SCRATCH = r"<cache-dir>"
WORK = os.path.join(SCRATCH, "mv3_verify")
os.makedirs(WORK, exist_ok=True)
os.environ["NUMBA_CACHE_DIR"] = os.path.join(WORK, "numba_cache")
os.makedirs(os.environ["NUMBA_CACHE_DIR"], exist_ok=True)

import numpy as np                                                      # noqa: E402
from numba import njit                                                  # noqa: E402

NEG = -(1 << 62)
L = 60.0
BUILDER_TRACES = os.path.join(SCRATCH, "mv3", "traces")


# --------------------------------------------------------------------------- #
# lazy max-segment-tree: leaf assign, suffix add, leftmost leaf >= T
# true value of a node = tre[node] + sum of lz over its STRICT ancestors
# --------------------------------------------------------------------------- #
@njit(cache=True)
def _anc_lazy(lz, leaf):
    s = 0
    p = leaf >> 1
    while p >= 1:
        s += lz[p]
        p >>= 1
    return s


@njit(cache=True)
def _pull(tre, lz, node):
    while node >= 1:
        l = tre[2 * node]
        r = tre[2 * node + 1]
        m = l if l > r else r
        tre[node] = m + lz[node]
        node >>= 1


@njit(cache=True)
def _leaf_set(tre, lz, size, pos, val):
    leaf = size + pos
    tre[leaf] = val - _anc_lazy(lz, leaf)
    _pull(tre, lz, leaf >> 1)


@njit(cache=True)
def _suffix_add(tre, lz, size, lo, delta):
    """add `delta` to every leaf in [lo, size)"""
    if lo >= size:
        return
    l = size + lo
    r = size + size - 1
    l0 = l
    r0 = r
    while l <= r:
        if l & 1:
            tre[l] += delta
            if l < size:
                lz[l] += delta
            l += 1
        if not (r & 1):
            tre[r] += delta
            if r < size:
                lz[r] += delta
            r -= 1
        l >>= 1
        r >>= 1
    _pull(tre, lz, l0 >> 1)
    _pull(tre, lz, r0 >> 1)


@njit(cache=True)
def _leftmost_ge(tre, lz, size, T):
    if tre[1] < T:
        return -1
    node = 1
    acc = 0
    while node < size:
        acc += lz[node]
        if tre[2 * node] + acc >= T:
            node = 2 * node
        else:
            node = 2 * node + 1
    return node - size


# --------------------------------------------------------------------------- #
# Fenwick tree of completed work by rank (point add, prefix sum)
# --------------------------------------------------------------------------- #
@njit(cache=True)
def _fw_add(F, n, i, v):
    p = i + 1
    while p <= n:
        F[p] += v
        p += p & -p


@njit(cache=True)
def _fw_pref(F, i):
    s = 0
    p = i + 1
    while p > 0:
        s += F[p]
        p -= p & -p
    return s


# --------------------------------------------------------------------------- #
# binary min-heap on (pred, rank)
# --------------------------------------------------------------------------- #
@njit(cache=True)
def _push(hk, hx, m, key, ix):
    hk[m] = key
    hx[m] = ix
    c = m
    while c > 0:
        p = (c - 1) >> 1
        if hk[p] > hk[c] or (hk[p] == hk[c] and hx[p] > hx[c]):
            hk[p], hk[c] = hk[c], hk[p]
            hx[p], hx[c] = hx[c], hx[p]
            c = p
        else:
            break
    return m + 1


@njit(cache=True)
def _pop(hk, hx, m):
    m -= 1
    hk[0] = hk[m]
    hx[0] = hx[m]
    c = 0
    while True:
        l = 2 * c + 1
        if l >= m:
            break
        r = l + 1
        b = l
        if r < m and (hk[r] < hk[l] or (hk[r] == hk[l] and hx[r] < hx[l])):
            b = r
        if hk[b] < hk[c] or (hk[b] == hk[c] and hx[b] < hx[c]):
            hk[b], hk[c] = hk[c], hk[b]
            hx[b], hx[c] = hx[c], hx[b]
            c = b
        else:
            break
    return m


# --------------------------------------------------------------------------- #
# the simulator
# --------------------------------------------------------------------------- #
@njit(cache=True)
def _sim(a, svc, pred, k, mode, B0_us, en, ed, Bmax_us, Ncap, use_work, use_cnt, size):
    """mode 0 FCFS, 1 pure pred order, 2 guard.  Returns (wait, n_disp, n_forced,
    qw_total, qw_forced)."""
    n = a.shape[0]
    wait = np.empty(n, np.float64)
    served = np.zeros(n, np.uint8)
    a_us = np.empty(n, np.int64)
    for i in range(n):
        a_us[i] = np.int64(round(a[i] * 1000000.0))

    # servers: finish time per busy slot, +inf when free
    INF = 1.0e300
    fin = np.full(k, INF, np.float64)
    who = np.full(k, -1, np.int64)

    hk = np.empty(n + 1, np.float64)
    hx = np.empty(n + 1, np.int64)
    nh = 0

    guard = mode == 2
    tre = np.full(2 * size if guard and use_work else 2, NEG, np.int64)
    lz = np.zeros((2 * size if guard and use_work else 2) // 2, np.int64)
    tre2 = np.full(2 * size if guard and use_cnt else 2, NEG, np.int64)
    lz2 = np.zeros((2 * size if guard and use_cnt else 2) // 2, np.int64)
    F = np.zeros(n + 2, np.int64)          # completed work by rank
    FC = np.zeros(n + 2, np.int64)         # completed count by rank
    TC = 0
    TCNT = 0

    head = 0            # smallest rank not yet dispatched
    i = 0               # next arrival
    nwait = 0
    nstarted = 0
    n_disp = 0
    n_forced = 0
    qw_total = 0
    qw_forced = 0
    t = -1.0e300
    while nstarted < n:
        # ---- completions at or before t
        for sl in range(k):
            if who[sl] >= 0 and fin[sl] <= t:
                c = who[sl]
                who[sl] = -1
                fin[sl] = INF
                if guard:
                    cus = np.int64(round(svc[c] * 1000000.0))
                    if use_cnt:
                        # every service is <= theta = L here, so the completed overtaker
                        # charges one unit of the count budget and nothing to the work one
                        _fw_add(FC, n, c, 1)
                        TCNT += 1
                        _suffix_add(tre2, lz2, size, c, -1)
                    else:
                        _fw_add(F, n, c, cus)
                        TC += cus
                        if use_work:
                            _suffix_add(tre, lz, size, c, -ed * cus)
        # ---- arrivals at or before t
        while i < n and a[i] <= t:
            if guard:
                if use_work:
                    z = en * a_us[i] - ed * B0_us - ed * _fw_pref(F, i)
                    _leaf_set(tre, lz, size, i, z)
                if use_cnt:
                    _leaf_set(tre2, lz2, size, i, -_fw_pref(FC, i))
            if mode != 0:
                nh = _push(hk, hx, nh, pred[i], i)
            nwait += 1
            i += 1
        # ---- one dispatch
        if nwait > 0:
            slot = -1
            for sl in range(k):
                if who[sl] < 0:
                    slot = sl
                    break
            if slot >= 0:
                while served[head] == 1:
                    head += 1
                forced = 0
                if mode == 0:
                    j = head
                    forced = 1
                elif mode == 1:
                    while served[hx[0]] == 1:
                        nh = _pop(hk, hx, nh)
                    j = hx[0]
                    nh = _pop(hk, hx, nh)
                else:
                    cand = -1
                    if Bmax_us > 0 and TC - _fw_pref(F, head) >= Bmax_us:
                        cand = head                      # over[head] >= Bmax
                    else:
                        if use_work:
                            t_us = np.int64(round(t * 1000000.0))
                            p1 = _leftmost_ge(tre, lz, size, en * t_us - ed * TC)
                            if p1 >= 0:
                                cand = p1
                        if use_cnt:
                            p2 = _leftmost_ge(tre2, lz2, size, Ncap - TCNT)
                            if p2 >= 0 and (cand < 0 or p2 < cand):
                                cand = p2
                    if cand >= 0:
                        j = cand
                        forced = 1
                    else:
                        while served[hx[0]] == 1:
                            nh = _pop(hk, hx, nh)
                        j = hx[0]
                        nh = _pop(hk, hx, nh)
                    if use_work:
                        _leaf_set(tre, lz, size, j, NEG)
                    if use_cnt:
                        _leaf_set(tre2, lz2, size, j, NEG)
                served[j] = 1
                n_disp += 1
                qw_total += nwait
                if forced == 1:
                    n_forced += 1
                    qw_forced += nwait
                nwait -= 1
                nstarted += 1
                wait[j] = t - a[j]
                fin[slot] = t + svc[j]
                who[slot] = j
                continue
        # ---- advance the clock
        nxt = INF
        for sl in range(k):
            if who[sl] >= 0 and fin[sl] < nxt:
                nxt = fin[sl]
        if i < n and a[i] < nxt:
            nxt = a[i]
        if nxt >= INF:
            break
        if nxt < t:
            nxt = t
        t = nxt
    return wait, n_disp, n_forced, qw_total, qw_forced


def _pow2(n):
    s = 1
    while s < n:
        s *= 2
    return s


def frac(eps):
    if eps == 0.0:
        return 0, 1
    f = Fraction(eps).limit_denominator(1 << 20)
    assert abs(float(f) - eps) < 1e-12, eps
    return f.numerator, f.denominator


def run(a, svc, k, policy="fcfs", pred=None, B0=0.0, eta=0.0, Bmax=0.0, Ncap=0):
    """policy 'fcfs' | 'pri' | 'cap' (work budget, eta may be 0 = fixed budget) |
    'skip' (finite-skip / position count).  B0, Bmax in seconds."""
    a = np.ascontiguousarray(a, np.float64)
    svc = np.ascontiguousarray(svc, np.float64)
    n = len(a)
    if pred is None:
        pred = np.zeros(n)
    pred = np.ascontiguousarray(pred, np.float64)
    mode = {"fcfs": 0, "pri": 1, "cap": 2, "skip": 2}[policy]
    use_work = policy == "cap"
    use_cnt = policy == "skip"
    if use_cnt:
        assert svc.max() <= L + 1e-9, "the count channel assumes every service <= L"
    eps = eta * k
    en, ed = frac(eps)
    size = _pow2(max(n, 2))
    w, nd, nf, qt, qf = _sim(a, svc, pred, int(k), mode,
                             int(round(min(B0, Bmax if Bmax > 0 else B0) * 1e6)),
                             int(en), int(ed), int(round(Bmax * 1e6)), int(Ncap),
                             use_work, use_cnt, size)
    return dict(w=w, n_disp=nd, n_forced=nf, qw_total=qt, qw_forced=qf,
                qw_forced_frac=qf / max(qt, 1))


def bound(wf, k, B0=0.0, eta=0.0, Bmax=0.0, Ncap=0, theta=L):
    """Per-job upper bound of chapter 5 (the smaller of the two), extra = Ncap*theta."""
    extra = Ncap * theta
    ub = np.full(len(wf), np.inf)
    if Bmax > 0:
        ub = wf + (Bmax + extra) / k + (3.0 - 2.0 / k) * L
    if eta > 0:
        ub = np.minimum(ub, (wf + (B0 + extra) / k + (3.0 - 2.0 / k) * L) / (1.0 - eta))
    if Bmax <= 0 and eta <= 0:                      # finite skip: work channel off
        ub = wf + (extra + (3 * k - 2) * L) / k
    return ub


def gmax(G, k):
    """Bmax for the service promise G, and the finite-skip count at the same promise."""
    return float(k) * (G - (3.0 - 2.0 / k) * L)


def skip_n(G, k):
    return int(round(G * k / L - (3 * k - 2)))


def load_trace(trace, rep, keys):
    z = np.load(os.path.join(BUILDER_TRACES, f"{trace}_rep{rep}.npz"))
    return {q: z[q] for q in keys}
