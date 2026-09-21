"""k-server non-preemptive queue with KILL-AND-RESTART TIERING and a constant-budget guard.

Self-contained numba kernel for this study.  The plain (non-tiered) modes reproduce
`../guard_variants/guardkern.py` job by job (checked in `verify.py`); the data structures
follow that kernel, simplified to the constant budget B (for which the fired set's
minimum-rank member IS the FCFS head, so no segment tree is needed -- only a Fenwick tree
of executed work).

MODEL
-----
k identical servers, non-preemptive, work conserving.  Job j has arrival a_j, rank j
(arrival order), true capped service C_j in (0, L].  With a tier-1 cap `tau`:

    tier 1: job j occupies a server for min(C_j, tau).  If C_j > tau it is KILLED at
            tau (the tau seconds are WASTED, the job is not advanced at all) and becomes
            a tier-2 waiting job at that instant, keeping its original rank.
    tier 2: job j occupies a server for C_j and completes.

`skip_thr > 0` sends every job with pred_j >= skip_thr straight to tier 2 at its arrival
(a prediction-driven skip of the kill).  tau = +inf disables tiering entirely.

A job's reported wait is  W[i] = (start of the run that COMPLETES it) - a_i,  so that
flow time = W[i] + C_i in both the tiered and the plain system and the two are directly
comparable.  `w_first` additionally records the first dispatch.

GUARD (constant budget B, at piece level)
-----------------------------------------
    over[q] = executed work of jobs of rank > q that has been executed while q waits
              (kept as TC - Fenwick prefix; a killed tier-1 piece contributes its tau)
    fired   = { waiting q : over[q] >= B };  if non-empty serve its minimum rank,
              else serve the base policy's choice.
With a constant budget over[.] is non-increasing in rank, so the minimum-rank fired job
is the minimum-rank waiting job ("head") and one Fenwick query per decision suffices.

BASE MODES
----------
    0 RANK   minimum rank over all waiting pieces      (tau=inf: plain FCFS; else T-FCFS)
    1 PRED   minimum pred over all waiting pieces      (tau=inf: SPJF)
    2 T1RANK tier-1 pieces first, by rank; tier 2 by rank
    3 T1PRED tier-1 pieces first, by pred; tier 2 by rank

WHAT IS *NOT* CLAIMED HERE: the per-job bound of the project's Theorem A is proved for a
fixed job set.  A tier-2 piece's release time is the kill time, which DIFFERS between two
policies on the same input, so the theorem does not transfer to the tiered system by
relabelling.  `brute.py` measures what actually holds.
"""
import numpy as np
from numba import njit

L_CAP = 60.0
INF_TAU = 1.0e18


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


@njit(cache=True, inline="always")
def _fen_pref(F, i):
    s = 0
    p = i + 1
    while p > 0:
        s += F[p]
        p -= p & -p
    return s


@njit(cache=True)
def simulate(a, s, pred, k, tau, B_us, base_mode, skip_thr, cap2, m2):
    """Returns
        w      final-dispatch wait (start of the completing run - arrival)
        w1     first-dispatch wait
        waste  total wasted seconds (us), n_killed, n_disp, n_forced, qw_total, qw_forced
    """
    n = a.shape[0]
    w = np.empty(n, np.float64)
    w1 = np.empty(n, np.float64)
    state = np.zeros(n, np.uint8)          # 0 unborn 1 t1-wait 2 running 3 t2-wait 4 done
    guard = B_us >= 0

    rt = np.empty(k + 1, np.float64)       # server completion heap
    rj = np.empty(k + 1, np.int64)
    rkill = np.empty(k + 1, np.uint8)      # 1 = this run ends in a kill
    rt2 = np.empty(k + 1, np.uint8)        # 1 = this run is a tier-2 piece
    nrun = 0
    nrun2 = 0                              # tier-2 pieces in service (capped by m2)

    hk = np.empty(n + 1, np.float64)       # tier-1 waiting, by pred
    hi = np.empty(n + 1, np.int64)
    nh = 0
    q2k = np.empty(cap2 + 1, np.int64)     # tier-2 waiting, by rank
    q2i = np.empty(cap2 + 1, np.int64)
    n2 = 0
    p2k = np.empty(cap2 + 1, np.float64)   # tier-2 waiting, by pred (mode 1 only)
    p2i = np.empty(cap2 + 1, np.int64)
    np2 = 0

    F = np.zeros((n + 1) if guard else 1, np.int64)
    TC = np.int64(0)

    fp = 0                                 # min rank with state == 1
    i = 0
    ndone = 0
    nwait = 0
    n_disp = 0
    n_forced = 0
    n_killed = 0
    waste_us = np.int64(0)
    wsince = 0.0        # waste injected since the last time <= k-1 jobs were present
    dmax = 0.0          # max over jobs, at the dispatch that completes them, of wsince
    qw_total = np.int64(0)
    qw_forced = np.int64(0)
    t = -1.0e300
    INF = 1.0e300

    while ndone < n:
        # ---------------- completions at or before t
        while nrun > 0 and rt[0] <= t:
            c = rj[0]
            kl = rkill[0]
            nrun2 -= rt2[0]
            nrun -= 1
            rt[0] = rt[nrun]
            rj[0] = rj[nrun]
            rkill[0] = rkill[nrun]
            rt2[0] = rt2[nrun]
            cc = 0
            while True:
                l = 2 * cc + 1
                if l >= nrun:
                    break
                r = l + 1
                b = l
                if r < nrun and rt[r] < rt[l]:
                    b = r
                if rt[b] < rt[cc]:
                    rt[b], rt[cc] = rt[cc], rt[b]
                    rj[b], rj[cc] = rj[cc], rj[b]
                    rkill[b], rkill[cc] = rkill[cc], rkill[b]
                    rt2[b], rt2[cc] = rt2[cc], rt2[b]
                    cc = b
                else:
                    break
            ex = tau if kl == 1 else s[c]
            if guard:
                cus = np.int64(round(ex * 1000000.0))
                TC += cus
                p = c + 1
                while p <= n:
                    F[p] += cus
                    p += p & -p
            if kl == 1:
                state[c] = 3
                n2 = _hpush(q2k, q2i, n2, c, c)
                np2 = _hpush(p2k, p2i, np2, pred[c], c)
                nwait += 1
                n_killed += 1
                waste_us += np.int64(round(tau * 1000000.0))
                wsince += tau
            else:
                state[c] = 4
                ndone += 1
        # ---------------- arrivals at or before t
        while i < n and a[i] <= t:
            if skip_thr > 0.0 and pred[i] >= skip_thr and tau < INF_TAU:
                state[i] = 3
                n2 = _hpush(q2k, q2i, n2, i, i)
                np2 = _hpush(p2k, p2i, np2, pred[i], i)
            else:
                state[i] = 1
                nh = _hpush(hk, hi, nh, pred[i], i)
            nwait += 1
            i += 1
        # ---------------- one dispatch
        if nwait + nrun <= k - 1:
            wsince = 0.0
        if nrun < k and nwait > 0:
            while fp < i and state[fp] != 1:
                fp += 1
            while n2 > 0 and state[q2i[0]] != 3:
                n2 = _hpop(q2k, q2i, n2)
            h1 = fp if fp < i else n
            h2 = q2i[0] if n2 > 0 else n
            if nrun2 >= m2:            # tier-2 slots full: only tier-1 pieces may start
                h2 = n
                if h1 >= n:
                    nxt = rt[0] if nrun > 0 else INF
                    if i < n and a[i] < nxt:
                        nxt = a[i]
                    if nxt >= INF:
                        break
                    t = nxt if nxt > t else t
                    continue
            head = h1 if h1 < h2 else h2
            forced = 0
            j = -1
            if guard and TC - _fen_pref(F, head) >= B_us:
                j = head
                forced = 1
            elif base_mode == 0:
                j = head
            elif base_mode == 1:
                while nh > 0 and state[hi[0]] != 1:
                    nh = _hpop(hk, hi, nh)
                while np2 > 0 and state[p2i[0]] != 3:
                    np2 = _hpop(p2k, p2i, np2)
                if h2 >= n or np2 == 0:
                    j = hi[0]
                elif nh == 0:
                    j = p2i[0]
                else:
                    j = hi[0] if hk[0] <= p2k[0] else p2i[0]
            else:
                while nh > 0 and state[hi[0]] != 1:
                    nh = _hpop(hk, hi, nh)
                if nh > 0:
                    j = hi[0] if base_mode == 3 else h1
                else:
                    j = h2
            # ---- run it
            kill = 0
            dur = s[j]
            is2 = 1 if state[j] == 3 else 0
            if state[j] == 1:
                w1[j] = t - a[j]
                if s[j] > tau:
                    kill = 1
                    dur = tau
            if kill == 0:
                w[j] = t - a[j]
                if wsince > dmax:
                    dmax = wsince
            state[j] = 2
            n_disp += 1
            qw_total += nwait
            if forced == 1:
                n_forced += 1
                qw_forced += nwait
            nwait -= 1
            rt[nrun] = t + dur
            rj[nrun] = j
            rkill[nrun] = kill
            rt2[nrun] = is2
            nrun2 += is2
            c = nrun
            nrun += 1
            while c > 0:
                p = (c - 1) >> 1
                if rt[p] > rt[c]:
                    rt[p], rt[c] = rt[c], rt[p]
                    rj[p], rj[c] = rj[c], rj[p]
                    rkill[p], rkill[c] = rkill[c], rkill[p]
                    rt2[p], rt2[c] = rt2[c], rt2[p]
                    c = p
                else:
                    break
            continue
        # ---------------- advance the clock
        nxt = rt[0] if nrun > 0 else INF
        if i < n and a[i] < nxt:
            nxt = a[i]
        if nxt >= INF:
            break
        if nxt < t:
            nxt = t
        t = nxt
    return (w, w1, waste_us / 1.0e6, n_killed, n_disp, n_forced, qw_total, qw_forced,
            ndone, dmax)


class Res:
    __slots__ = ("w", "w1", "waste", "n_killed", "n_disp", "n_forced", "qw_total",
                 "qw_forced", "ndone", "dmax", "name", "k", "tau", "B")


MODES = {"rank": 0, "pred": 1, "t1rank": 2, "t1pred": 3}


def run(a, s, k, mode="rank", pred=None, tau=None, B=None, skip_thr=0.0, m2=None,
        name=""):
    """mode in MODES; tau=None means no tiering; B=None means no guard (B in seconds).
    m2 = at most this many tier-2 pieces in service at once (None = k = no cap).  A cap
    m2 < k makes the policy NON work conserving: a server idles while only tier-2 jobs
    wait.  Proposition 10 of ../guard_theory/theory.md voids every guarantee in that
    case; the option is here to measure what it costs, not because it is sound."""
    a = np.ascontiguousarray(a, np.float64)
    s = np.ascontiguousarray(s, np.float64)
    if pred is None:
        pred = np.zeros(len(a), np.float64)
    pred = np.ascontiguousarray(pred, np.float64)
    tau_f = INF_TAU if tau is None else float(tau)
    B_us = -1 if B is None else int(round(B * 1e6))
    if tau is None:
        cap2 = 1
    else:
        cap2 = int((s > tau_f).sum()) + (int((pred >= skip_thr).sum())
                                         if skip_thr > 0 else 0) + 8
    r = Res()
    (r.w, r.w1, r.waste, r.n_killed, r.n_disp, r.n_forced, r.qw_total, r.qw_forced,
     r.ndone, r.dmax) = simulate(a, s, pred, int(k), tau_f, B_us, MODES[mode],
                                 float(skip_thr), cap2, int(k if m2 is None else m2))
    r.name, r.k, r.tau, r.B = name, int(k), tau_f, B
    assert r.ndone == len(a), f"{name}: only {r.ndone}/{len(a)} finished"
    return r


def guar_excess(k, B, L=L_CAP):
    """Theorem A's guaranteed per-job excess over FCFS, for the NON-tiered guard."""
    return B / k + (3.0 - 2.0 / k) * L


def B_for_G(k, G, L=L_CAP):
    """Budget that buys a guaranteed excess of G seconds (Theorem A, non-tiered)."""
    return k * (G - (3.0 - 2.0 / k) * L)
