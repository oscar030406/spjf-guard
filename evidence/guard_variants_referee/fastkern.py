"""Fast (numba) re-implementation of the same definitions as refsim.py.

Nothing here is derived from the colleague's guardkern.py; it is a literal
transcription of refsim.py into flat int64 arrays so that tens of millions of
instances can be enumerated.  check_agree.py verifies the two against each other.

All arithmetic is exact integer.  eps = en/ed is rational; the firing test
    over[q] >= min(Bmax, B0 + (en/ed)*(t-a_q))
is evaluated as
    over[q]*ed >= min(Bmax*ed, B0*ed + en*(t-a_q)).
"""
import sys
sys.dont_write_bytecode = True
import numpy as np
from numba import njit

FCFS = 0
GUARD = 1
HEAD = 2   # the claimed eps=0 equivalent: fire on the HEAD only


@njit(cache=True)
def sim(a, s, pred, k, policy, B0, Bmax, en, ed, Ncap, theta, use_work,
        start, comp, srv_end, srv_job, wait, chw, chc):
    n = a.shape[0]
    for i in range(n):
        start[i] = -1
        comp[i] = -1
        chw[i] = 0
        chc[i] = 0
        wait[i] = False
    for r in range(k):
        srv_end[r] = -1
        srv_job[r] = -1
    nxt = 0
    done = 0
    t = a[0]
    while done < n:
        # 1. completions
        for r in range(k):
            if srv_end[r] == t:
                j = srv_job[r]
                comp[j] = t
                if theta > 0 and s[j] <= theta:
                    chc[j] = 1
                else:
                    chw[j] = s[j]
                srv_end[r] = -1
                srv_job[r] = -1
                done += 1
        # 2. arrivals
        while nxt < n and a[nxt] == t:
            wait[nxt] = True
            nxt += 1
        # 3. dispatch
        while True:
            free = -1
            for r in range(k):
                if srv_end[r] == -1:
                    free = r
                    break
            if free == -1:
                break
            pick = -1
            if policy == FCFS:
                for q in range(n):
                    if wait[q]:
                        pick = q
                        break
            elif policy == HEAD:
                head = -1
                for q in range(n):
                    if wait[q]:
                        head = q
                        break
                ow = 0
                oc = 0
                for r in range(head + 1, n):
                    ow += chw[r]
                    oc += chc[r]
                f = False
                if use_work == 1:
                    bud = B0 * ed + en * (t - a[head])
                    cap = Bmax * ed
                    if bud > cap:
                        bud = cap
                    if ow * ed >= bud:
                        f = True
                if Ncap > 0 and oc >= Ncap:
                    f = True
                if f:
                    pick = head
                else:
                    bp = 0
                    for q in range(n):
                        if wait[q]:
                            if pick == -1 or pred[q] < bp:
                                pick = q
                                bp = pred[q]
            else:
                # suffix sums of charged work / count over ranks > q
                ow = 0
                oc = 0
                firedmin = -1
                # descending pass records, for each q, the suffix over ranks > q
                # we need the SMALLEST fired rank, so collect then scan
                for q in range(n - 1, -1, -1):
                    if wait[q]:
                        f = False
                        if use_work == 1:
                            bud = B0 * ed + en * (t - a[q])
                            cap = Bmax * ed
                            if bud > cap:
                                bud = cap
                            if ow * ed >= bud:
                                f = True
                        if Ncap > 0 and oc >= Ncap:
                            f = True
                        if f:
                            firedmin = q
                    ow += chw[q]
                    oc += chc[q]
                if firedmin >= 0:
                    pick = firedmin
                else:
                    bp = 0
                    for q in range(n):
                        if wait[q]:
                            if pick == -1 or pred[q] < bp:
                                pick = q
                                bp = pred[q]
            if pick == -1:
                break
            srv_end[free] = t + s[pick]
            srv_job[free] = pick
            start[pick] = t
            wait[pick] = False
        # 4. next event
        nt = -1
        for r in range(k):
            if srv_end[r] != -1 and (nt == -1 or srv_end[r] < nt):
                nt = srv_end[r]
        if nxt < n and (nt == -1 or a[nxt] < nt):
            nt = a[nxt]
        if nt == -1:
            break
        t = nt
    return 0


@njit(cache=True)
def workload_at(a, s, start, comp, t):
    U = 0
    for j in range(a.shape[0]):
        if a[j] <= t and t < comp[j]:
            if t < start[j]:
                U += s[j]
            else:
                U += comp[j] - t
    return U


@njit(cache=True)
def lemma_gap(a, s, stA, cpA, stB, cpB):
    """max_t |U_A(t) - U_B(t)| over every integer instant up to the horizon.
    U is piecewise linear in t with breakpoints only at integer event times, so
    the integer grid attains the maximum."""
    T = 0
    for j in range(a.shape[0]):
        if cpA[j] > T:
            T = cpA[j]
        if cpB[j] > T:
            T = cpB[j]
    g = 0
    for t in range(0, T + 1):
        d = workload_at(a, s, stA, cpA, t) - workload_at(a, s, stB, cpB, t)
        if d < 0:
            d = -d
        if d > g:
            g = d
    return g
