"""Finite-skip (position-count) baseline with the count charged at DISPATCH.

This is the prior-art reading of "a waiting job may be passed at most N times": the
counter moves when an overtaker is SENT TO A SERVER, not when it finishes.  v3 used
guardkern's count channel, which charges on COMPLETION, and had to pay an extra k L for
the overtakers still in service; that costs the baseline 11-13 % of its skips at the same
promise (verifier finding F4).  Charging at dispatch removes that term.

    k identical servers, non-preemptive, work conserving, service times in (0, L].
    Jobs are in arrival rank order.  For a waiting job q,
        cnt[q] = number of jobs of rank > q dispatched since q arrived.
    A job of rank > q cannot be dispatched before q arrives (ranks follow arrivals), so
    cnt[q] is simply the number of dispatched jobs of rank > q; it is therefore
    NON-INCREASING in rank, the fired set {q : cnt[q] >= N} is non-empty exactly when
    the head is in it, and its smallest-rank member IS the head.  The rule is a head
    check, and the min-rank dispatch of the guard family is automatic.

    DISPATCH: if cnt[head] >= N serve the head, else serve the smallest `pred`
    (ties to the smaller rank).

BOUND.  Fix i and let W = W_skip[i].  Steps (1), (2), (4), (5) of the guard proof in
guardkern.py are unchanged; only step (3) differs.  Every overtaker j of i is dispatched
at an instant when no job fires (if any job fired, the head would be served, and the head
has rank <= i, so it is not an overtaker of i); in particular cnt[i] < N at that instant,
and dispatching j raises cnt[i] to at most N.  So at most N overtakers are dispatched
while i waits and E_new <= N L.  With k W <= R_i + E_new and R_i <= k W_FCFS[i] +
2(k-1) L from steps (2), (4), (5),

        W_skip[i] <= W_FCFS[i] + (N + 2k - 2) L / k.

`guaranteed()` evaluates this job by job; N = 0 is exactly FCFS and N >= n is exactly the
pure `pred` order, which is what the cross-check in v31_xcheck.py uses as its anchors.
"""
import numpy as np
from numba import njit


@njit(cache=True)
def _fen_pref(F, i):
    s = 0
    p = i + 1
    while p > 0:
        s += F[p]
        p -= p & -p
    return s


@njit(cache=True)
def simulate_skip(a, s, pred, k, N):
    """Returns (wait, n_disp, n_forced, qw_total, qw_forced)."""
    n = a.shape[0]
    wait = np.empty(n, np.float64)
    rt = np.empty(k + 1, np.float64)
    rj = np.empty(k + 1, np.int64)
    nrun = 0
    hk = np.empty(n + 1, np.float64)
    hi = np.empty(n + 1, np.int64)
    nh = 0
    served = np.zeros(n, np.uint8)
    fq = np.empty(n + 1, np.int64)
    fh = 0
    ft = 0
    F = np.zeros(n + 1, np.int64)      # Fenwick over ranks of DISPATCHED jobs
    TD = 0                              # total dispatched
    i = 0
    nwait = 0
    nstarted = 0
    n_disp = 0
    n_forced = 0
    qw_total = 0
    qw_forced = 0
    t = -1.0e300
    INF = 1.0e300
    while nstarted < n:
        while nrun > 0 and rt[0] <= t:              # completions (no accounting here)
            nrun -= 1
            rt[0] = rt[nrun]
            rj[0] = rj[nrun]
            c = 0
            while True:
                l = 2 * c + 1
                if l >= nrun:
                    break
                r = l + 1
                b = l
                if r < nrun and rt[r] < rt[l]:
                    b = r
                if rt[b] < rt[c]:
                    rt[b], rt[c] = rt[c], rt[b]
                    rj[b], rj[c] = rj[c], rj[b]
                    c = b
                else:
                    break
        while i < n and a[i] <= t:                  # arrivals
            fq[ft] = i
            ft += 1
            nh = _hpush(hk, hi, nh, pred[i], i)
            nwait += 1
            i += 1
        if nrun < k and nwait > 0:                  # one dispatch
            while served[fq[fh]] == 1:
                fh += 1
            hd = fq[fh]
            forced = 0
            if TD - _fen_pref(F, hd) >= N:
                j = hd
                forced = 1
            else:
                while served[hi[0]] == 1:
                    nh = _hpop(hk, hi, nh)
                j = hi[0]
                nh = _hpop(hk, hi, nh)
            served[j] = 1
            TD += 1                                 # charge the skip AT DISPATCH
            p = j + 1
            while p <= n:
                F[p] += 1
                p += p & -p
            n_disp += 1
            qw_total += nwait
            if forced == 1:
                n_forced += 1
                qw_forced += nwait
            nwait -= 1
            nstarted += 1
            wait[j] = t - a[j]
            rt[nrun] = t + s[j]
            rj[nrun] = j
            c = nrun
            nrun += 1
            while c > 0:
                pp = (c - 1) >> 1
                if rt[pp] > rt[c]:
                    rt[pp], rt[c] = rt[c], rt[pp]
                    rj[pp], rj[c] = rj[c], rj[pp]
                    c = pp
                else:
                    break
            continue
        nxt = rt[0] if nrun > 0 else INF            # advance the clock
        if i < n and a[i] < nxt:
            nxt = a[i]
        if nxt >= INF:
            break
        if nxt < t:
            nxt = t
        t = nxt
    return wait, n_disp, n_forced, qw_total, qw_forced


@njit(cache=True, inline="always")
def _hpush(key, idx, m, k_, i_):
    key[m] = k_
    idx[m] = i_
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
def _hpop(key, idx, m):
    m -= 1
    key[0] = key[m]
    idx[0] = idx[m]
    c = 0
    while True:
        l = 2 * c + 1
        if l >= m:
            break
        r = l + 1
        b = l
        if r < m and (key[r] < key[l] or (key[r] == key[l] and idx[r] < idx[l])):
            b = r
        if key[b] < key[c] or (key[b] == key[c] and idx[b] < idx[c]):
            key[b], key[c] = key[c], key[b]
            idx[b], idx[c] = idx[c], idx[b]
            c = b
        else:
            break
    return m


class Res:
    __slots__ = ("w", "n_disp", "n_forced", "qw_total", "qw_forced", "N", "k")


def run(a, s, pred, k, N):
    if N < 0:
        raise ValueError("N must be >= 0")
    r = Res()
    (r.w, r.n_disp, r.n_forced, r.qw_total, r.qw_forced) = simulate_skip(
        np.ascontiguousarray(a, np.float64), np.ascontiguousarray(s, np.float64),
        np.ascontiguousarray(pred, np.float64), int(k), int(N))
    r.N, r.k = int(N), int(k)
    return r


def guaranteed(wf, k, N, L=60.0):
    """W_skip <= W_FCFS + (N + 2k - 2) L / k, elementwise."""
    return wf + (N + 2.0 * k - 2.0) * L / k


def brute(a, s, pred, k, N):
    """Deliberately literal pure-python reference: recomputes cnt[q] for the whole
    waiting set from the dispatch history at every decision, and picks the min-rank
    fired job rather than assuming the head check is equivalent."""
    n = len(a)
    end = [None] * k
    sjob = [-1] * k
    waiting = []
    start = [None] * n
    disp = []                                     # ranks dispatched, in order
    nxt = 0
    done = 0
    t = a[0]
    while done < n:
        for srv in range(k):
            if end[srv] is not None and end[srv] == t:
                end[srv] = None
                sjob[srv] = -1
                done += 1
        while nxt < n and a[nxt] == t:
            waiting.append(nxt)
            nxt += 1
        while waiting and (None in end):
            fired = [q for q in waiting if sum(1 for d in disp if d > q) >= N]
            pick = min(fired) if fired else min(waiting, key=lambda q: (pred[q], q))
            srv = end.index(None)
            end[srv] = t + s[pick]
            sjob[srv] = pick
            start[pick] = t
            disp.append(pick)
            waiting.remove(pick)
        nt = None
        for e in end:
            if e is not None and (nt is None or e < nt):
                nt = e
        if nxt < n and (nt is None or a[nxt] < nt):
            nt = a[nxt]
        if nt is None:
            break
        t = nt
    return [st - aa for st, aa in zip(start, a)]
