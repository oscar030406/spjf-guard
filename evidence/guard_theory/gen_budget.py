"""Numerical attack on the GENERAL wrapper theorem (paper thm:guard / thm:guardmult).

The paper states the wrapper bound for an ARBITRARY budget rule that respects a
cap:

    0 <= budget(q,t) <= Bmax                                (the only hypothesis)
    E(t) = { q waiting at t : over_q(t) >= budget(q,t) }
    dispatch the min-rank member of E if E != {}, else whatever the base wants

    (A1)  In_i < Bmax + k L             (whenever i has at least one overtaker)
    (A2)  k W_P[i] <= k W_FCFS[i] + Bmax + (3k-2) L  (strict unless Bmax = L = 0)

and the multiplicative bound only for the age-relative shape with ONE constant
B0 for every job:

    budget(q,t) = min(B0 + eta k (t - a_q), Bmax),  eta in [0,1)
    (M1)  In_i < B0 + eta k W + k L
    (M2)  (1-eta) W <= W_FCFS[i] + B0/k + (3-2/k) L

This file tests both, plus the structural questions the proof turns on: does the
bound survive budget rules that DECREASE in time (a fired job becomes un-fired),
that differ per job, that are drawn adversarially per (job, dispatch epoch);
does budget == 0 reduce the wrapper to FCFS; and is the min-rank tie-break
inside E load-bearing.

Six budget rules, all clamped into [0, Bmax] so the hypothesis of the general
theorem holds by construction:

    rule 0  constant B0
    rule 1  age-relative, common B0:   min(B0 + eta k (t-a_q), Bmax)
    rule 2  queue-length + age:        min(B0 + gam n_q + eta k (t-a_q), Bmax)
    rule 3  DECREASING in time:        clamp(B0 - dec (t-a_q), 0, Bmax)
    rule 4  per-job constant B0_q      (drawn independently per job)
    rule 5  adversarial: an independent value in [0,Bmax] per (job, epoch)

Exact int64 throughout; eta = en/ed is a rational and every comparison is cross
multiplied, so no float touches a decision or a test.  The base policy is either
a "tape" (at the d-th dispatch decision the base takes waiting job tape[d] % nw,
so ranging over all tapes ranges over ALL work-conserving non-preemptive
schedules) or a static priority key, used for Theorem 4C's family.

NOTE on eta.  sharp_kernel.sched_guardB implements the growth term as
(en/ed)*(t-a_q), i.e. eta*(t-a_q), while run_thmB.py's checks assume the
paper's rule eta*k*(t-a_q).  That makes run_thmB.py's sweep a test of a SLOWER
budget than the one claimed (they coincide only at k=1).  The kernel here uses
en*k*(t-a_q) over ed, which is the paper's rule.

    env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME \
        uv run --no-project --with numpy --with numba python gen_budget.py
"""
import sys

sys.dont_write_bytecode = True

from fractions import Fraction
from math import gcd

import numpy as np
from numba import njit

import sharp_kernel as K

NEG = -(1 << 60)


# --------------------------------------------------------------------------- #
# the general wrapper
# --------------------------------------------------------------------------- #
@njit(cache=True)
def sched_gen(a, x, k, tape, pri, usepri, rule, par, bud, nq, start, order,
              free, wait, tiemax):
    """par = [B0, gam, en, ed, Bmax, dec];  Bmax < 0 means "no cap".

    tiemax = 0 -> dispatch the MIN-rank member of E (the paper's guard);
    tiemax = 1 -> dispatch the MAX-rank member of E (a deliberately wrong
    variant, used to show the tie-break is load-bearing).
    usepri = 1 -> the base picks the waiting job of least pri key (ties by
    rank); otherwise it reads the tape.
    Returns n on success, -1 if the loop cannot advance.
    """
    n = a.shape[0]
    B0 = par[0]; gam = par[1]; en = par[2]; ed = par[3]
    Bmax = par[4]; dec = par[5]
    for m in range(k):
        free[m] = a[0]
    for j in range(n):
        start[j] = NEG
        nq[j] = 0
    nw = 0
    nxt = 0
    t = a[0]
    d = 0
    while d < n:
        while nxt < n and a[nxt] <= t:
            nq[nxt] = nw            # jobs waiting at the moment nxt arrives
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
                if rule == 0:
                    rhs = ed * B0
                elif rule == 1:
                    rhs = ed * B0 + en * k * (t - a[q])
                elif rule == 2:
                    rhs = ed * (B0 + gam * nq[q]) + en * k * (t - a[q])
                elif rule == 3:
                    v = B0 - dec * (t - a[q])
                    if v < 0:
                        v = 0
                    rhs = ed * v
                elif rule == 4:
                    rhs = ed * bud[q, 0]
                else:
                    rhs = ed * bud[q, d]
                if rhs < 0:
                    rhs = 0
                if Bmax >= 0 and rhs > ed * Bmax:
                    rhs = ed * Bmax
                if ed * ov >= rhs:
                    c = cc
                    if tiemax == 0:
                        break
            if c < 0:
                if usepri == 1:
                    c = 0
                    for cc in range(1, nw):
                        if pri[wait[cc]] < pri[wait[c]]:
                            c = cc
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


# --------------------------------------------------------------------------- #
# the checks
# --------------------------------------------------------------------------- #
@njit(cache=True)
def check_all(a, x, k, start, order, startF, pos, par, rule, nq, bud, res):
    """res[0] (A1) In_i < Bmax + kL failures
       res[1] (A2) k W <= k W_F + Bmax + (3k-2)L failures
       res[2] (A2) strictness failures (equality while Bmax + kL > 0)
       res[3] identity |D_i| <= 2(k-1)L failures
       res[4] (M2) with the COMMON nominal B0 failures
       res[5] (M2) with the per-job B_{0,i} failures
       res[6] (M1) In_i < B_{0,i} + eta k W + kL failures
       res[7] job-checks
       res[8] max (k*excess - Bmax)
       res[9] max k*excess
    """
    n = a.shape[0]
    B0 = par[0]; gam = par[1]; en = par[2]; ed = par[3]; Bmax = par[4]
    L = 0
    for j in range(n):
        if x[j] > L:
            L = x[j]
    for p in range(n):
        pos[order[p]] = p
    for i in range(n):
        W = start[i] - a[i]
        WF = startF[i] - a[i]
        In = 0
        Out = 0
        has_ov = False
        for j in range(i + 1, n):
            if pos[j] < pos[i]:
                In += x[j]
                has_ov = True
        for j in range(i):
            if pos[j] > pos[i]:
                Out += x[j]
        if Bmax >= 0:
            if has_ov and In >= Bmax + k * L:
                res[0] += 1
            if k * W > k * WF + Bmax + (3 * k - 2) * L:
                res[1] += 1
            if (Bmax + k * L) > 0 and k * W == k * WF + Bmax + (3 * k - 2) * L:
                res[2] += 1
            v = k * (W - WF) - Bmax
            if v > res[8]:
                res[8] = v
        D = k * (W - WF) - (In - Out)
        if D > 2 * (k - 1) * L or D < -2 * (k - 1) * L:
            res[3] += 1
        if rule == 1 or rule == 2 or rule == 4:
            if rule == 1:
                B0i = B0
            elif rule == 2:
                B0i = B0 + gam * nq[i]
            else:
                B0i = bud[i, 0]
            if Bmax >= 0 and B0i > Bmax:
                B0i = Bmax
            if (ed * k - en * k) * W > ed * (k * WF + B0 + (3 * k - 2) * L):
                res[4] += 1
            if (ed * k - en * k) * W > ed * (k * WF + B0i + (3 * k - 2) * L):
                res[5] += 1
            if has_ov and ed * In >= ed * B0i + en * k * W + ed * k * L:
                res[6] += 1
        res[7] += 1
        w2 = k * (W - WF)
        if w2 > res[9]:
            res[9] = w2


@njit(cache=True)
def one_combo(a, x, k, tape, pri, usepri, rule, par, bud, tiemax, res,
              start, order, free, wait, startF, orderF, pos, nq):
    n = a.shape[0]
    if sched_gen(a, x, k, tape, pri, usepri, rule, par, bud, nq, start, order,
                 free, wait, tiemax) < 0:
        return -1
    if K.sched(a, x, k, tape, 0, startF, orderF, free, wait) < 0:
        return -1
    check_all(a, x, k, start, order, startF, pos, par, rule, nq, bud, res)
    return 0


# --------------------------------------------------------------------------- #
# exhaustive sweeps
# --------------------------------------------------------------------------- #
@njit(cache=True)
def exh_instance(a, x, k, L, bud, res, ncomb):
    """Every base tape x every rule x a grid of parameters, for one instance."""
    n = a.shape[0]
    start = np.empty(n, np.int64); order = np.empty(n, np.int64)
    free = np.empty(k, np.int64); wait = np.empty(n, np.int64)
    startF = np.empty(n, np.int64); orderF = np.empty(n, np.int64)
    pos = np.empty(n, np.int64); nq = np.empty(n, np.int64)
    tape = np.empty(n, np.int64)
    pri = np.zeros(n, np.int64)
    par = np.empty(6, np.int64)
    ntape = 1
    for _ in range(n):
        ntape *= n
    for code in range(ntape):
        c = code
        for j in range(n):
            tape[j] = c % n
            c //= n
        for rule in range(6):
            for bi in range(3):
                if bi == 0:
                    Bmax = 0
                elif bi == 1:
                    Bmax = k * L
                else:
                    Bmax = 3 * k * L
                for pi in range(3):
                    if pi == 0:
                        B0 = 0; gam = 0; en = 0; ed = 1; dec = 0
                    elif pi == 1:
                        B0 = L; gam = L; en = 1; ed = 2; dec = 1
                    else:
                        B0 = 2 * L; gam = 1; en = 3; ed = 4; dec = 2 * L
                    par[0] = B0; par[1] = gam; par[2] = en; par[3] = ed
                    par[4] = Bmax; par[5] = dec
                    if one_combo(a, x, k, tape, pri, 0, rule, par, bud, 0, res,
                                 start, order, free, wait, startF, orderF,
                                 pos, nq) == 0:
                        ncomb[0] += 1


def run_exhaustive(seed=20260920, per=40):
    rng = np.random.default_rng(seed)
    res = np.zeros(10, np.int64)
    ncomb = np.zeros(1, np.int64)
    ninst = 0
    for k in (1, 2, 3):
        for n in (3, 4, 5):
            for L in (2, 3):
                for _ in range(per):
                    a = np.sort(rng.integers(0, 4, n)).astype(np.int64)
                    a = a - a[0]
                    x = rng.integers(0, L + 1, n).astype(np.int64)
                    x[int(rng.integers(0, n))] = L
                    bud = rng.integers(0, 3 * L + 1, (n, n)).astype(np.int64)
                    exh_instance(a, x, k, L, bud, res, ncomb)
                    ninst += 1
    return res, int(ncomb[0]), ninst


@njit(cache=True)
def many_tapes(a, x, k, L, bud, tapes, res, ncomb):
    n = a.shape[0]
    start = np.empty(n, np.int64); order = np.empty(n, np.int64)
    free = np.empty(k, np.int64); wait = np.empty(n, np.int64)
    startF = np.empty(n, np.int64); orderF = np.empty(n, np.int64)
    pos = np.empty(n, np.int64); nq = np.empty(n, np.int64)
    pri = np.zeros(n, np.int64)
    par = np.empty(6, np.int64)
    for ti in range(tapes.shape[0]):
        tape = tapes[ti]
        for rule in range(6):
            for bi in range(2):
                if bi == 0:
                    Bmax = k * L
                else:
                    Bmax = 3 * k * L
                for pi in range(2):
                    if pi == 0:
                        B0 = 0; gam = L; en = 1; ed = 2; dec = 1
                    else:
                        B0 = L; gam = 1; en = 3; ed = 4; dec = L
                    par[0] = B0; par[1] = gam; par[2] = en; par[3] = ed
                    par[4] = Bmax; par[5] = dec
                    if one_combo(a, x, k, tape, pri, 0, rule, par, bud, 0, res,
                                 start, order, free, wait, startF, orderF,
                                 pos, nq) == 0:
                        ncomb[0] += 1


def run_n67(seed=771, per=40, ntape=1500):
    rng = np.random.default_rng(seed)
    res = np.zeros(10, np.int64)
    ncomb = np.zeros(1, np.int64)
    ninst = 0
    for k in (1, 2, 3):
        for n in (6, 7):
            for L in (2, 3):
                tapes = rng.integers(0, n, (ntape, n)).astype(np.int64)
                for _ in range(per):
                    a = np.sort(rng.integers(0, 5, n)).astype(np.int64)
                    a = a - a[0]
                    x = rng.integers(0, L + 1, n).astype(np.int64)
                    x[int(rng.integers(0, n))] = L
                    bud = rng.integers(0, 3 * L + 1, (n, n)).astype(np.int64)
                    many_tapes(a, x, k, L, bud, tapes, res, ncomb)
                    ninst += 1
    return res, int(ncomb[0]), ninst


# --------------------------------------------------------------------------- #
# random sweep
# --------------------------------------------------------------------------- #
@njit(cache=True)
def seed_rng(s):
    np.random.seed(s)


@njit(cache=True)
def random_block(m, res, ncomb):
    for _ in range(m):
        n = 2 + np.random.randint(0, 11)
        k = 1 + np.random.randint(0, 5)
        L = 1 + np.random.randint(0, 11)
        a = np.empty(n, np.int64)
        for j in range(n):
            a[j] = np.random.randint(0, 3 * n)
        a.sort()
        for j in range(n - 1, -1, -1):
            a[j] = a[j] - a[0]
        x = np.empty(n, np.int64)
        for j in range(n):
            x[j] = np.random.randint(0, L + 1)
        LL = 0
        for j in range(n):
            if x[j] > LL:
                LL = x[j]
        tape = np.empty(n, np.int64)
        for j in range(n):
            tape[j] = np.random.randint(0, 1 << 20)
        par = np.empty(6, np.int64)
        ed = 1 + np.random.randint(0, 8)
        en = np.random.randint(0, ed)
        Bmax = np.random.randint(0, 6 * k * (LL + 1))
        bud = np.empty((n, n), np.int64)
        for i in range(n):
            for j in range(n):
                bud[i, j] = np.random.randint(0, Bmax + 1)
        par[0] = np.random.randint(0, 3 * (LL + 1))
        par[1] = np.random.randint(0, 2 * (LL + 1))
        par[2] = en
        par[3] = ed
        par[4] = Bmax
        par[5] = np.random.randint(0, 2 * (LL + 1))
        rule = np.random.randint(0, 6)
        pri = np.zeros(n, np.int64)
        start = np.empty(n, np.int64); order = np.empty(n, np.int64)
        free = np.empty(k, np.int64); wait = np.empty(n, np.int64)
        startF = np.empty(n, np.int64); orderF = np.empty(n, np.int64)
        pos = np.empty(n, np.int64); nq = np.empty(n, np.int64)
        if one_combo(a, x, k, tape, pri, 0, rule, par, bud, 0, res, start,
                     order, free, wait, startF, orderF, pos, nq) == 0:
            ncomb[0] += 1


def run_random(total=1_000_000, block=50_000, seed=4242):
    seed_rng(seed)
    res = np.zeros(10, np.int64)
    ncomb = np.zeros(1, np.int64)
    done = 0
    while done < total:
        m = min(block, total - done)
        random_block(m, res, ncomb)
        done += m
    return res, int(ncomb[0])


# --------------------------------------------------------------------------- #
# probes
# --------------------------------------------------------------------------- #
@njit(cache=True)
def zero_is_fcfs(a, x, k, tapes, par, bud):
    """budget == 0 fires every waiting job, so the wrapper must reproduce FCFS
    exactly -- same dispatch sequence AND same start times."""
    n = a.shape[0]
    start = np.empty(n, np.int64); order = np.empty(n, np.int64)
    free = np.empty(k, np.int64); wait = np.empty(n, np.int64)
    startF = np.empty(n, np.int64); orderF = np.empty(n, np.int64)
    nq = np.empty(n, np.int64)
    pri = np.zeros(n, np.int64)
    bad = 0
    for ti in range(tapes.shape[0]):
        if sched_gen(a, x, k, tapes[ti], pri, 0, 0, par, bud, nq, start, order,
                     free, wait, 0) < 0:
            continue
        if K.sched(a, x, k, tapes[ti], 0, startF, orderF, free, wait) < 0:
            continue
        for j in range(n):
            if start[j] != startF[j] or order[j] != orderF[j]:
                bad += 1
                break
    return bad


@njit(cache=True)
def tiebreak_probe(a, x, k, L, bud, tapes, res, ncomb):
    """The same sweep, but the wrapper serves the MAX-rank member of E."""
    n = a.shape[0]
    start = np.empty(n, np.int64); order = np.empty(n, np.int64)
    free = np.empty(k, np.int64); wait = np.empty(n, np.int64)
    startF = np.empty(n, np.int64); orderF = np.empty(n, np.int64)
    pos = np.empty(n, np.int64); nq = np.empty(n, np.int64)
    pri = np.zeros(n, np.int64)
    par = np.empty(6, np.int64)
    for ti in range(tapes.shape[0]):
        for r in range(2):
            rule = 4 + r
            for bi in range(2):
                if bi == 0:
                    Bmax = k * L
                else:
                    Bmax = 2 * k * L
                par[0] = L; par[1] = 1; par[2] = 1; par[3] = 2
                par[4] = Bmax; par[5] = 1
                if one_combo(a, x, k, tapes[ti], pri, 0, rule, par, bud, 1, res,
                             start, order, free, wait, startF, orderF, pos,
                             nq) == 0:
                    ncomb[0] += 1


@njit(cache=True)
def tiebreak_random(m, res, ncomb):
    """The random sweep again, with the wrapper serving the MAX-rank member of
    E.  Larger instances than the exhaustive probe, to see whether the WAIT
    bound (A2) and not only the In bound (A1) can be broken."""
    for _ in range(m):
        n = 4 + np.random.randint(0, 13)
        k = 1 + np.random.randint(0, 4)
        L = 1 + np.random.randint(0, 8)
        a = np.empty(n, np.int64)
        for j in range(n):
            a[j] = np.random.randint(0, 2 * n)
        a.sort()
        for j in range(n - 1, -1, -1):
            a[j] = a[j] - a[0]
        x = np.empty(n, np.int64)
        for j in range(n):
            x[j] = np.random.randint(0, L + 1)
        LL = 0
        for j in range(n):
            if x[j] > LL:
                LL = x[j]
        tape = np.empty(n, np.int64)
        for j in range(n):
            tape[j] = np.random.randint(0, 1 << 20)
        par = np.empty(6, np.int64)
        Bmax = np.random.randint(0, 3 * k * (LL + 1))
        bud = np.empty((n, n), np.int64)
        for i in range(n):
            for j in range(n):
                bud[i, j] = np.random.randint(0, Bmax + 1)
        par[0] = np.random.randint(0, 2 * (LL + 1))
        par[1] = np.random.randint(0, LL + 1)
        par[2] = 1
        par[3] = 2
        par[4] = Bmax
        par[5] = np.random.randint(0, LL + 1)
        rule = np.random.randint(0, 6)
        pri = np.zeros(n, np.int64)
        start = np.empty(n, np.int64); order = np.empty(n, np.int64)
        free = np.empty(k, np.int64); wait = np.empty(n, np.int64)
        startF = np.empty(n, np.int64); orderF = np.empty(n, np.int64)
        pos = np.empty(n, np.int64); nq = np.empty(n, np.int64)
        if one_combo(a, x, k, tape, pri, 0, rule, par, bud, 1, res, start,
                     order, free, wait, startF, orderF, pos, nq) == 0:
            ncomb[0] += 1


def run_probes(seed=31337):
    rng = np.random.default_rng(seed)
    bad0 = 0
    ntest = 0
    par = np.zeros(6, np.int64)
    par[3] = 1
    par[4] = 0
    for k in (1, 2, 3, 4):
        for n in (3, 4, 5, 6):
            for _ in range(150):
                a = np.sort(rng.integers(0, 5, n)).astype(np.int64)
                a = a - a[0]
                x = rng.integers(0, 4, n).astype(np.int64)
                tapes = rng.integers(0, n, (150, n)).astype(np.int64)
                bud = np.zeros((n, n), np.int64)
                bad0 += zero_is_fcfs(a, x, k, tapes, par, bud)
                ntest += 150
    res = np.zeros(10, np.int64)
    ncomb = np.zeros(1, np.int64)
    for k in (2, 3):
        for n in (4, 5, 6):
            for L in (2, 3):
                tapes = rng.integers(0, n, (400, n)).astype(np.int64)
                for _ in range(80):
                    a = np.sort(rng.integers(0, 4, n)).astype(np.int64)
                    a = a - a[0]
                    x = rng.integers(0, L + 1, n).astype(np.int64)
                    x[int(rng.integers(0, n))] = L
                    bud = rng.integers(0, 2 * k * L + 1, (n, n)).astype(np.int64)
                    tiebreak_probe(a, x, k, L, bud, tapes, res, ncomb)
    seed_rng(seed)
    resr = np.zeros(10, np.int64)
    ncombr = np.zeros(1, np.int64)
    tiebreak_random(1_000_000, resr, ncombr)
    return bad0, ntest, res, int(ncomb[0]), resr, int(ncombr[0])


# --------------------------------------------------------------------------- #
# the counterexample to a multiplicative bound with gamma > 0
# --------------------------------------------------------------------------- #
def newest_pri(n):
    """A static priority key that makes the base always take the NEWEST (that
    is, highest-rank) waiting job: pri[j] = -j, and the base takes the least
    key."""
    return -np.arange(n, dtype=np.int64)


def counterexample(Gam=8, verbose=True):
    """k = 1, L = 1, B0 = 0, gamma = Gam, Bmax = Gam, any eta in [0,1).

    rank 0: a=0, x=1   -- n_q = 0, so budget == 0: always fired, served first
    rank 1: a=0, x=1   -- THE VICTIM; n_q = 1, so budget = B0 + gamma = Gam
    rank 2..: a = 1,2,3,..., x = 1, all of rank above the victim; the base
              policy always prefers the newest waiting job.

    FCFS starts the victim at t = 1.  Under the guard the victim's budget is
    gamma, so gamma units of later work must COMPLETE before it fires and it
    starts at t = gamma + 1: excess = gamma exactly.
    """
    k = 1
    n = Gam + 4
    a = np.zeros(n, np.int64)
    x = np.ones(n, np.int64)
    for j in range(2, n):
        a[j] = j - 1
    tape = np.zeros(n, np.int64)
    pri = newest_pri(n)
    par = np.array([0, Gam, 0, 1, Gam, 0], np.int64)      # rule 2, gam = Gam
    bud = np.zeros((n, n), np.int64)
    nq = np.empty(n, np.int64)
    start = np.empty(n, np.int64); order = np.empty(n, np.int64)
    free = np.empty(k, np.int64); wait = np.empty(n, np.int64)
    startF = np.empty(n, np.int64); orderF = np.empty(n, np.int64)
    assert sched_gen(a, x, k, tape, pri, 1, 2, par, bud, nq, start, order,
                     free, wait, 0) == n
    assert K.sched(a, x, k, tape, 0, startF, orderF, free, wait) == n
    i = 1
    W = int(start[i] - a[i])
    WF = int(startF[i] - a[i])
    L = int(x.max())
    if verbose:
        print("  n = %d, k = %d, L = %d, B0 = 0, gamma = %d, Bmax = %d, eta free"
              % (n, k, L, Gam, par[4]))
        print("  arrivals  a = %s" % list(map(int, a)))
        print("  services  x = %s" % list(map(int, x)))
        print("  n_q at the victim's arrival = %d, so budget_victim = %d"
              % (nq[i], Gam))
        print("  guard start times  = %s" % list(map(int, start)))
        print("  FCFS  start times  = %s" % list(map(int, startF)))
        print("  victim: W = %d, W_FCFS = %d, excess = %d" % (W, WF, W - WF))
    return W, WF, L, Gam, int(par[4]), k


def report_counterexample():
    print("COUNTEREXAMPLE  the multiplicative bound stated with the COMMON B0")
    print("fails for gamma > 0 (equivalently for a per-job B_{0,i}).")
    print()
    W, WF, L, Gam, Bmax, k = counterexample(8)
    add = Fraction(Bmax, k) + Fraction(3 * k - 2, k) * L
    print()
    print("  the GENERAL additive bound still holds:")
    print("    W < W_F + Bmax/k + (3-2/k)L = %s + %s = %s   ->   %d < %s : %s"
          % (WF, add, WF + add, W, WF + add, W < WF + add))
    print()
    print("  the multiplicative bound with the common B0 = 0, at gamma = 8:")
    for en, ed in ((0, 1), (1, 2), (3, 4), (9, 10), (99, 100)):
        eta = Fraction(en, ed)
        rhs = (Fraction(WF) + Fraction(0, k)
               + Fraction(3 * k - 2, k) * L) / (1 - eta)
        print("    eta = %-8s  RHS = (W_F + B0/k + (3-2/k)L)/(1-eta) = %-10s"
              "  W = %d  VIOLATED: %s" % (eta, rhs, W, W > rhs))
    print()
    print("  gamma is free, so the bound fails for EVERY eta in [0,1): the")
    print("  excess is exactly gamma, and W = gamma + 1 against a fixed RHS of")
    print("  2/(1-eta).  Taking gamma = ceil(2/(1-eta)):")
    print("    %-10s %-8s %-10s %-8s %-8s %-8s"
          % ("eta", "gamma", "RHS", "W", "W_FCFS", "violated"))
    for en, ed in ((0, 1), (1, 2), (3, 4), (9, 10), (99, 100)):
        eta = Fraction(en, ed)
        rhs = (Fraction(1) + Fraction(3 * k - 2, k) * 1) / (1 - eta)
        G = int(rhs) + 1
        W2, WF2, _, _, _, _ = counterexample(G, verbose=False)
        print("    %-10s %-8d %-10s %-8d %-8d %-8s"
              % (eta, G, rhs, W2, WF2, W2 > rhs))
    print()
    print("  the excess is exactly gamma, so the violation is unbounded:")
    print("    %-8s %-8s %-8s %-8s" % ("gamma", "W", "W_FCFS", "excess"))
    for G in (1, 2, 4, 8, 16, 32, 64, 128):
        W2, WF2, _, _, _, _ = counterexample(G, verbose=False)
        print("    %-8d %-8d %-8d %-8d" % (G, W2, WF2, W2 - WF2))
    print()
    print("  the PER-JOB form does hold on the same instance,")
    print("  with B_{0,i} = B0 + gamma n_i = %d:" % Gam)
    for en, ed in ((0, 1), (1, 2), (3, 4)):
        eta = Fraction(en, ed)
        rhs = Fraction(WF) + Fraction(Gam, k) + Fraction(3 * k - 2, k) * L
        print("    eta = %-6s  (1-eta)W = %-8s <= %-8s : %s"
              % (eta, (1 - eta) * W, rhs, (1 - eta) * W <= rhs))


# --------------------------------------------------------------------------- #
# Theorem 4C's family under the general statement
# --------------------------------------------------------------------------- #
def tight_family_check():
    import wrapper_tight as WT
    print("THEOREM 4C's family, replayed through the GENERAL kernel")
    print("  (a constant budget is the general rule with budget == B0 == Bmax)")
    print()
    print("  %-3s %-6s %-3s %-6s %-6s %-8s %-20s %-6s"
          % ("k", "L", "m", "n", "B", "excess", "c(k) measured", "3k-2"))
    ok = True
    for k, m in ((2, 6), (2, 7), (3, 4), (3, 5), (4, 3), (4, 4), (5, 3), (6, 3)):
        L = k ** m
        a, x, pri, vic, f, B, Tm = WT.build(k, L, m)
        n = a.shape[0]
        par = np.array([B, 0, 0, 1, B, 0], np.int64)
        bud = np.zeros((n, n), np.int64)
        nq = np.empty(n, np.int64)
        tape = np.zeros(n, np.int64)
        start = np.empty(n, np.int64); order = np.empty(n, np.int64)
        free = np.empty(k, np.int64); wait = np.empty(n, np.int64)
        startF = np.empty(n, np.int64); orderF = np.empty(n, np.int64)
        if sched_gen(a, x, k, tape, pri, 1, 0, par, bud, nq, start, order,
                     free, wait, 0) < 0:
            print("    k=%d m=%d: could not advance" % (k, m))
            ok = False
            continue
        K.sched(a, x, k, tape, 0, startF, orderF, free, wait)
        Lx = int(x.max())
        exc = int(start[vic] - startF[vic])
        c = Fraction(k * exc - B, Lx)
        print("  %-3d %-6d %-3d %-6d %-6d %-8d %-20s %-6d"
              % (k, Lx, m, n, B, exc, "%s = %.4f" % (c, float(c)), 3 * k - 2))
        if not (c < 3 * k - 2):
            ok = False
    print()
    print("  every row satisfies c < 3k-2 strictly: %s" % ok)
    print("  (same numbers as theory.md's table -- the general statement covers")
    print("   the constant budget verbatim, so Theorem 4C is unaffected)")
    return ok


# --------------------------------------------------------------------------- #
def main():
    print("=" * 78)
    print("THE GENERAL WRAPPER THEOREM -- numerical attack")
    print("=" * 78)
    print()
    print("rules: 0 constant | 1 age-relative common B0 | 2 queue-length + age |")
    print("       3 DECREASING in time | 4 per-job constant | 5 adversarial per")
    print("       (job, dispatch epoch), redrawn every epoch")
    print("all clamped into [0, Bmax]; every comparison is exact integer.")
    print()

    bad0, ntest, resT, ncombT, resTr, ncombTr = run_probes()
    print("-" * 78)
    print("PROBE 1  budget == 0 must reduce the wrapper to FCFS")
    print("  %d (instance, base tape) pairs, k <= 4, n <= 6: %d mismatches"
          % (ntest, bad0))
    print()
    print("PROBE 2  the MIN-rank tie-break inside E is load-bearing")
    print("  the same wrapper serving the MAX-rank member of E instead,")
    print("  %d (schedule, parameter) combinations, %d job-checks:"
          % (ncombT, resT[7]))
    print("    (A1) In_i < Bmax + kL              : %d failures" % resT[0])
    print("    (A2) k W <= k W_F + Bmax + (3k-2)L : %d failures" % resT[1])
    print("  plus 1,000,000 random instances (n <= 16, k <= 4) with the same")
    print("  wrong tie-break, %d schedules, %d job-checks:"
          % (ncombTr, resTr[7]))
    print("    (A1) In_i < Bmax + kL              : %d failures" % resTr[0])
    print("    (A2) k W <= k W_F + Bmax + (3k-2)L : %d failures" % resTr[1])
    print("  (failures here are EXPECTED: they are the point of the probe)")
    print()

    res, ncomb, ninst = run_exhaustive()
    print("-" * 78)
    print("EXHAUSTIVE  k <= 3, n <= 5, EVERY base tape (hence every")
    print("  work-conserving schedule the base could produce), 6 rules, 9")
    print("  parameter settings: %d instances, %d (schedule, rule, parameter)"
          % (ninst, ncomb))
    print("  combinations, %d job-checks" % res[7])
    print("    (A1) In_i < Bmax + kL              : %d failures" % res[0])
    print("    (A2) k W <= k W_F + Bmax + (3k-2)L : %d failures" % res[1])
    print("    (A2) strictness                    : %d failures" % res[2])
    print("    identity |D_i| <= 2(k-1)L          : %d failures" % res[3])
    print("    (M2) with the per-job B_{0,i}      : %d failures" % res[5])
    print("    (M1) In_i < B_{0,i} + eta k W + kL : %d failures" % res[6])
    print("    (M2) with the COMMON B0            : %d failures  <- rules 2 and 4"
          % res[4])
    print("    worst (k*excess - Bmax) observed   : %d" % res[8])
    print()

    res6, ncomb6, ninst6 = run_n67()
    print("-" * 78)
    print("n = 6 and 7, k <= 3, 1,500 base tapes per shape, 6 rules, 4")
    print("  parameter settings: %d instances, %d combinations, %d job-checks"
          % (ninst6, ncomb6, res6[7]))
    print("    (A1) %d   (A2) %d   strictness %d   identity %d"
          % (res6[0], res6[1], res6[2], res6[3]))
    print("    (M2) per-job B_{0,i} %d   (M1) %d   (M2) common B0 %d"
          % (res6[5], res6[6], res6[4]))
    print()

    resr, ncombr = run_random()
    print("-" * 78)
    print("RANDOM  1,000,000 instances, k <= 5, n <= 12, rule drawn uniformly")
    print("  from the six, every parameter random: %d schedules, %d job-checks"
          % (ncombr, resr[7]))
    print("    (A1) In_i < Bmax + kL              : %d failures" % resr[0])
    print("    (A2) k W <= k W_F + Bmax + (3k-2)L : %d failures" % resr[1])
    print("    (A2) strictness                    : %d failures" % resr[2])
    print("    identity |D_i| <= 2(k-1)L          : %d failures" % resr[3])
    print("    (M2) with the per-job B_{0,i}      : %d failures" % resr[5])
    print("    (M1) In_i < B_{0,i} + eta k W + kL : %d failures" % resr[6])
    print("    (M2) with the COMMON B0            : %d failures  <- rules 2, 4"
          % resr[4])
    print("    worst (k*excess - Bmax) observed   : %d" % resr[8])
    print()

    print("-" * 78)
    report_counterexample()
    print()
    print("-" * 78)
    tight_family_check()


if __name__ == "__main__":
    main()
