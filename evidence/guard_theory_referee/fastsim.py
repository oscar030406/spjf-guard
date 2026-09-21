"""numba transcription of refsim2.simulate, checked against it by agree.py.

All integer.  Jobs are given in rank order.  Policies:
  0 FCFS               min-rank waiting job
  1 SCORE              argmin (score[j], j)          (LIFO/SJF/LJF/random perm)
  2 RANDOM             uniform among waiting jobs
  3 GUARD              theory.md section 4 wrapper over the SCORE base
  4 ADV_MAXIN          always dispatch the max-rank waiting job (LIFO by rank)
"""
import sys
sys.dont_write_bytecode = True
import numpy as np
from numba import njit

FCFS, SCORE, RANDOM, GUARD, MAXRANK, CHOICE, GCHOICE = 0, 1, 2, 3, 4, 5, 6


@njit(inline='always')
def _rnd(st):
    x = st[0]
    x ^= (x << np.uint64(13)) & np.uint64(0xFFFFFFFFFFFFFFFF)
    x ^= (x >> np.uint64(7))
    x ^= (x << np.uint64(17)) & np.uint64(0xFFFFFFFFFFFFFFFF)
    st[0] = x
    return np.int64(x >> np.uint64(11))


@njit(cache=True)
def sim(a, x, k, mode, score, B, start, comp, order, srv_end, srv_job, wait,
        rstate):
    """wait[] is used as a boolean array of length n.  Returns nothing; fills
    start, comp, order (order[p] = p-th dispatched job)."""
    n = a.shape[0]
    for i in range(n):
        start[i] = -1
        comp[i] = -1
        wait[i] = 0
        order[i] = -1
    for r in range(k):
        srv_end[r] = -1
        srv_job[r] = -1
    nxt = 0
    done = 0
    nord = 0
    t = a[0]
    while done < n:
        for r in range(k):
            if srv_end[r] == t and srv_job[r] >= 0:
                j = srv_job[r]
                comp[j] = t
                srv_end[r] = -1
                srv_job[r] = -1
                done += 1
        while nxt < n and a[nxt] == t:
            wait[nxt] = 1
            nxt += 1
        while True:
            free = -1
            for r in range(k):
                if srv_job[r] < 0:
                    free = r
                    break
            if free < 0:
                break
            nw = 0
            for j in range(n):
                if wait[j] == 1:
                    nw += 1
            if nw == 0:
                break
            pick = -1
            if mode == FCFS:
                for j in range(n):
                    if wait[j] == 1:
                        pick = j
                        break
            elif mode == MAXRANK:
                for j in range(n - 1, -1, -1):
                    if wait[j] == 1:
                        pick = j
                        break
            elif mode == SCORE:
                best = np.int64(0)
                for j in range(n):
                    if wait[j] == 1:
                        if pick < 0 or score[j] < best:
                            pick = j
                            best = score[j]
            elif mode == RANDOM:
                c = _rnd(rstate) % nw
                cc = 0
                for j in range(n):
                    if wait[j] == 1:
                        if cc == c:
                            pick = j
                            break
                        cc += 1
            elif mode == CHOICE:
                # score[] doubles as the free-choice tape: at the p-th dispatch
                # take the (score[p] mod nw)-th waiting job.  Every
                # work-conserving non-preemptive schedule is reachable.
                c = score[nord] % nw
                cc = 0
                for j in range(n):
                    if wait[j] == 1:
                        if cc == c:
                            pick = j
                            break
                        cc += 1
            else:  # GUARD (over the SCORE base, or over the CHOICE base)
                # over_q(t) = work of ranks > q completed by t
                suf = np.int64(0)
                fired = -1
                for j in range(n - 1, -1, -1):
                    if wait[j] == 1 and suf >= B:
                        fired = j
                    if comp[j] >= 0 and comp[j] <= t:
                        suf += x[j]
                if fired >= 0:
                    pick = fired
                elif mode == GCHOICE:
                    c = score[nord] % nw
                    cc = 0
                    for j in range(n):
                        if wait[j] == 1:
                            if cc == c:
                                pick = j
                                break
                            cc += 1
                else:
                    best = np.int64(0)
                    for j in range(n):
                        if wait[j] == 1:
                            if pick < 0 or score[j] < best:
                                pick = j
                                best = score[j]
            srv_end[free] = t + x[pick]
            srv_job[free] = pick
            start[pick] = t
            order[nord] = pick
            nord += 1
            wait[pick] = 0
            if x[pick] == 0:
                comp[pick] = t
                srv_end[free] = -1
                srv_job[free] = -1
                done += 1
        nt = np.int64(-1)
        for r in range(k):
            if srv_job[r] >= 0:
                if nt < 0 or srv_end[r] < nt:
                    nt = srv_end[r]
        if nxt < n and (nt < 0 or a[nxt] < nt):
            nt = a[nxt]
        if nt < 0:
            break
        t = nt


@njit(cache=True)
def in_out(x, order, n, In, Out, pos):
    for p in range(n):
        pos[order[p]] = p
    for i in range(n):
        In[i] = 0
        Out[i] = 0
    for i in range(n):
        for j in range(n):
            if j > i and pos[j] < pos[i]:
                In[i] += x[j]
            elif j < i and pos[i] < pos[j]:
                Out[i] += x[j]
