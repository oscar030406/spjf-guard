"""Exact-integer kernels for the sharp-constant search (revision of theory.md).

Everything is int64: arrival times, service times, start times.  A "tape" is a
vector of integers; at the d-th dispatch decision the policy takes waiting job
number tape[d] % (number waiting), so ranging over all tapes ranges over ALL
non-preemptive work-conserving schedules.  Two accounting conventions are
computed side by side:

    In_i   = sum{ x_j : j > i, j dispatched before i in the SEQUENCE }
    Ine_i  = work of rank > i jobs actually EXECUTED during [a_i, s_i)
    Out_i  = sum{ x_j : j < i, j dispatched after i in the sequence }
             ( = remaining work at s_i of the undispatched rank < i jobs)

    D_i  = k (W_P[i] - W_F[i]) - (In_i  - Out_i)     sequence convention
    De_i = k (W_P[i] - W_F[i]) - (Ine_i - Out_i)     executed-work convention

This file is new for the revision; it does not import sim_core.py, so the two
paths are independent and `run_sharp.py agree` cross-checks them.
"""
import sys
sys.dont_write_bytecode = True

import numpy as np
from numba import njit

NEG = -(1 << 60)


# --------------------------------------------------------------------------- #
# schedule builders
# --------------------------------------------------------------------------- #
@njit(cache=True)
def sched(a, x, k, tape, mode, start, order, free, wait):
    """mode 0 = FCFS (always the minimum-rank waiting job), 1 = tape.

    Ties: completions are processed before arrivals (a server that frees at t is
    free at t), arrivals before dispatches, and dispatches happen one at a time
    in the order the loop performs them -- that order IS the dispatch sequence.
    Returns n on success, -1 if the loop cannot advance.
    """
    n = a.shape[0]
    for m in range(k):
        free[m] = a[0]
    nw = 0
    nxt = 0
    t = a[0]
    d = 0
    while d < n:
        while nxt < n and a[nxt] <= t:
            wait[nw] = nxt
            nw += 1
            nxt += 1
        si = -1
        for m in range(k):
            if free[m] <= t:
                si = m
                break
        if si >= 0 and nw > 0:
            if mode == 0:
                c = 0
            else:
                c = tape[d] % nw
            j = wait[c]
            for q in range(c, nw - 1):
                wait[q] = wait[q + 1]
            nw -= 1
            start[j] = t
            order[d] = j
            free[si] = t + x[j]
            d += 1
            continue
        has = False
        nt = 0
        if nxt < n:
            nt = a[nxt]
            has = True
        for m in range(k):
            if free[m] > t:
                if (not has) or free[m] < nt:
                    nt = free[m]
                    has = True
        if not has:
            return -1
        t = nt
    return n


@njit(cache=True)
def sched_guard(a, x, k, tape, B, start, order, free, wait):
    """guard(tape-base, B): at every dispatch instant, if some waiting job q has
    over_q(t) = total work of rank > q jobs COMPLETED by t at least B, dispatch
    the minimum-rank such q; otherwise let the tape choose."""
    n = a.shape[0]
    for m in range(k):
        free[m] = a[0]
    for j in range(n):
        start[j] = NEG
    nw = 0
    nxt = 0
    t = a[0]
    d = 0
    while d < n:
        while nxt < n and a[nxt] <= t:
            wait[nw] = nxt
            nw += 1
            nxt += 1
        si = -1
        for m in range(k):
            if free[m] <= t:
                si = m
                break
        if si >= 0 and nw > 0:
            c = -1
            for cc in range(nw):
                q = wait[cc]
                ov = 0
                for j in range(q + 1, n):
                    if start[j] != NEG and start[j] + x[j] <= t:
                        ov += x[j]
                if ov >= B:
                    c = cc
                    break
            if c < 0:
                c = tape[d] % nw
            j = wait[c]
            for q in range(c, nw - 1):
                wait[q] = wait[q + 1]
            nw -= 1
            start[j] = t
            order[d] = j
            free[si] = t + x[j]
            d += 1
            continue
        has = False
        nt = 0
        if nxt < n:
            nt = a[nxt]
            has = True
        for m in range(k):
            if free[m] > t:
                if (not has) or free[m] < nt:
                    nt = free[m]
                    has = True
        if not has:
            return -1
        t = nt
    return n


# --------------------------------------------------------------------------- #
# per-job accounting
# --------------------------------------------------------------------------- #
@njit(cache=True)
def analyse(a, x, k, start, order, startF, pos, res):
    """res[0..3] = max D, min D, max De, min De; res[4..5] = argmax D, argmin D.
    res[6..7] = argmax De, argmin De."""
    n = a.shape[0]
    for p in range(n):
        pos[order[p]] = p
    mxD = NEG
    mnD = -NEG
    mxE = NEG
    mnE = -NEG
    aD = -1
    bD = -1
    aE = -1
    bE = -1
    for i in range(n):
        In = 0
        Ine = 0
        for j in range(i + 1, n):
            if pos[j] < pos[i]:
                In += x[j]
            e = start[j] + x[j]
            if e > start[i]:
                e = start[i]
            e -= start[j]
            if e > 0:
                Ine += e
        Out = 0
        for j in range(i):
            if pos[j] > pos[i]:
                Out += x[j]
        base = k * (start[i] - startF[i]) + Out
        D = base - In
        E = base - Ine
        if D > mxD:
            mxD = D
            aD = i
        if D < mnD:
            mnD = D
            bD = i
        if E > mxE:
            mxE = E
            aE = i
        if E < mnE:
            mnE = E
            bE = i
    res[0] = mxD
    res[1] = mnD
    res[2] = mxE
    res[3] = mnE
    res[4] = aD
    res[5] = bD
    res[6] = aE
    res[7] = bE


@njit(cache=True)
def excess_max(a, x, k, start, startF):
    """max_i k*(W_guard[i] - W_FCFS[i]); also returns max In_i is not needed here."""
    n = a.shape[0]
    m = NEG
    ai = -1
    for i in range(n):
        v = k * (start[i] - startF[i])
        if v > m:
            m = v
            ai = i
    return m, ai


@njit(cache=True)
def decomp(a, x, k, start, order, startF, orderF, pos, i):
    """Return (R_P, rho_P, R_F, rho_F, In, Out, D) for job i.

    R^Q_i  = remaining work at time a_i (AFTER arrivals are processed) of the
             jobs of rank < i.
    rho^Q_i= remaining work at s^Q_i of the jobs dispatched before i in Q's
             dispatch SEQUENCE that are still in service then.
    """
    n = a.shape[0]
    for p in range(n):
        pos[order[p]] = p
    RP = 0
    RF = 0
    for j in range(i):
        if start[j] >= a[i]:
            RP += x[j]
        else:
            r = start[j] + x[j] - a[i]
            if r > 0:
                RP += r
        if startF[j] >= a[i]:
            RF += x[j]
        else:
            r = startF[j] + x[j] - a[i]
            if r > 0:
                RF += r
    rP = 0
    for j in range(n):
        if j != i and pos[j] < pos[i]:
            r = start[j] + x[j] - start[i]
            if r > 0:
                rP += r
    rF = 0
    for j in range(i):                       # under FCFS every rank<i job precedes i
        r = startF[j] + x[j] - startF[i]
        if r > 0:
            rF += r
    In = 0
    Out = 0
    for j in range(i + 1, n):
        if pos[j] < pos[i]:
            In += x[j]
    for j in range(i):
        if pos[j] > pos[i]:
            Out += x[j]
    D = k * (start[i] - startF[i]) - (In - Out)
    return RP, rP, RF, rF, In, Out, D


@njit(cache=True)
def max_rgap(a, x, k, start, startF):
    """max_i (R^P_i - R^F_i) -- the Lemma 1 slack that actually enters Thm 1."""
    n = a.shape[0]
    best = NEG
    for i in range(n):
        RP = 0
        RF = 0
        for j in range(i):
            if start[j] >= a[i]:
                RP += x[j]
            else:
                r = start[j] + x[j] - a[i]
                if r > 0:
                    RP += r
            if startF[j] >= a[i]:
                RF += x[j]
            else:
                r = startF[j] + x[j] - a[i]
                if r > 0:
                    RF += r
        if RP - RF > best:
            best = RP - RF
    return best


@njit(cache=True)
def sched_guardB(a, x, k, tape, C, en, ed, Bmax, start, order, free, wait):
    """Theorem B guard: budget_q(t) = min(C_q + (en/ed)(t - a_q), Bmax), with
    Bmax <= 0 meaning "no cap".  E(t) = {waiting q : over_q(t) >= budget_q(t)};
    dispatch the minimum-RANK member of E, else let the base (tape) choose.
    over_q(t) = work of rank > q jobs COMPLETED by t.  Exact integers: the test
    ed*over >= ed*C_q + en*(t-a_q) is done without division."""
    n = a.shape[0]
    for m in range(k):
        free[m] = a[0]
    for j in range(n):
        start[j] = NEG
    nw = 0
    nxt = 0
    t = a[0]
    d = 0
    while d < n:
        while nxt < n and a[nxt] <= t:
            wait[nw] = nxt
            nw += 1
            nxt += 1
        si = -1
        for m in range(k):
            if free[m] <= t:
                si = m
                break
        if si >= 0 and nw > 0:
            c = -1
            for cc in range(nw):
                q = wait[cc]
                ov = 0
                for j in range(q + 1, n):
                    if start[j] != NEG and start[j] + x[j] <= t:
                        ov += x[j]
                lhs = ed * ov
                rhs = ed * C[q] + en * (t - a[q])
                if Bmax > 0 and ed * Bmax < rhs:
                    rhs = ed * Bmax
                if lhs >= rhs:
                    c = cc
                    break
            if c < 0:
                c = tape[d] % nw
            j = wait[c]
            for q in range(c, nw - 1):
                wait[q] = wait[q + 1]
            nw -= 1
            start[j] = t
            order[d] = j
            free[si] = t + x[j]
            d += 1
            continue
        has = False
        nt = 0
        if nxt < n:
            nt = a[nxt]
            has = True
        for m in range(k):
            if free[m] > t:
                if (not has) or free[m] < nt:
                    nt = free[m]
                    has = True
        if not has:
            return -1
        t = nt
    return n
