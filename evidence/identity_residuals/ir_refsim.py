"""INSTRUMENTED COPY of ../guard_variants_referee/refsim.py, sha256
1195a8983303e8100cd852b2b0e42774bf4ea458d3c3f15a938b82f07ffec656 (the hash the v3.1
manifest carries for it).  The only edits, marked `# [ir]`, record the DISPATCH SEQUENCE
`seq` (the order in which the loop picks jobs) and return it; no decision is changed.
This file exists so that the dispatch order `ir_kern.py` reports is checked against a
simulator written independently of it rather than against itself.

Original docstring follows.
===============================================================================
Independent reference simulator, written from the written definitions only.

k identical servers, non-preemptive, work conserving.  Jobs are given ALREADY in
rank order (stable sort by (arrival, input index)), so rank == array index.
Event order at a time instant: completions, then arrivals, then dispatch.

over[q]  = total true service of jobs of rank > q that COMPLETED while q waits.
           (for a waiting q every rank>q completion necessarily happened at a time
           >= a_q, so it is just the sum of charged work over ranks > q.)
budget(q,t) = min(Bmax, B0 + eps*(t-a_q))
fired(q) = over[q] >= budget(q,t)   [work channel]  or  cnt[q] >= Ncap  [count]
dispatch = min-rank member of the fired set if non-empty, else argmin (pred, rank).

Pure python, Fractions for eps, integers everywhere else.  Deliberately slow and
literal; the numba kernel in fastkern.py is checked against this one.
"""
import sys
sys.dont_write_bytecode = True
from fractions import Fraction


def rank_order(a, s, pred):
    idx = sorted(range(len(a)), key=lambda i: (a[i], i))
    return [a[i] for i in idx], [s[i] for i in idx], [pred[i] for i in idx], idx


def simulate(a, s, pred, k, policy="guard", B0=0, Bmax=None, eps=Fraction(0),
             Ncap=0, theta=0, use_work=True):
    n = len(a)
    if Bmax is None:
        Bmax = B0
    eps = Fraction(eps)
    end = [None] * k
    sjob = [-1] * k
    waiting = []
    start = [-1] * n
    comp = [-1] * n
    chw = [0] * n          # work charged to the work channel on completion
    chc = [0] * n          # 1 charged to the count channel on completion
    seq = []                                                             # [ir]
    nxt = 0
    done = 0
    t = a[0]
    guard = (policy == "guard")
    while done < n:
        for srv in range(k):                      # 1. completions
            if end[srv] is not None and end[srv] == t:
                j = sjob[srv]
                comp[j] = t
                if theta > 0 and s[j] <= theta:
                    chc[j] = 1
                else:
                    chw[j] = s[j]
                end[srv] = None
                sjob[srv] = -1
                done += 1
        while nxt < n and a[nxt] == t:            # 2. arrivals
            waiting.append(nxt)
            nxt += 1
        while waiting and (None in end):          # 3. dispatch
            if guard:
                E = []
                for q in waiting:
                    ow = sum(chw[r] for r in range(q + 1, n))
                    oc = sum(chc[r] for r in range(q + 1, n))
                    fired = False
                    if use_work:
                        bud = B0 + eps * (t - a[q])
                        if bud > Bmax:
                            bud = Bmax
                        if ow >= bud:
                            fired = True
                    if Ncap > 0 and oc >= Ncap:
                        fired = True
                    if fired:
                        E.append(q)
                pick = min(E) if E else min(waiting, key=lambda q: (pred[q], q))
            else:
                pick = min(waiting)
            srv = end.index(None)
            end[srv] = t + s[pick]
            sjob[srv] = pick
            start[pick] = t
            seq.append(pick)                                             # [ir]
            waiting.remove(pick)
        nt = None                                  # 4. next event time
        for e in end:
            if e is not None and (nt is None or e < nt):
                nt = e
        if nxt < n and (nt is None or a[nxt] < nt):
            nt = a[nxt]
        if nt is None:
            break
        t = nt
    return start, comp, seq                                              # [ir]


def workload(a, s, start, comp, t):
    """Unfinished work present at time t, right-continuous convention."""
    U = 0
    for j in range(len(a)):
        if a[j] <= t < comp[j]:
            U += s[j] if t < start[j] else comp[j] - t
    return U
