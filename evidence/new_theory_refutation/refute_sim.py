"""Adversarial search against the draft clock / fluid / absolute-bound statements.

Written from scratch; it shares no code with evidence/timeout_rule.  Model of
paper/sections/03_problem_model.tex and the Conventions of 06_theory.tex:
k identical non-preemptive work-conserving servers, rank = (arrival, index),
events at one instant processed as completions, arrivals, dispatches; the
dispatches of one instant form a phase whose order is the dispatch order.
All times and sizes are integers; theta is carried doubled (theta2 = 2 theta)
so half-integer theta is tested exactly.

Policies are explored, not sampled, in the exhaustive part: every dispatch at
which the rule leaves a choice branches over every allowed waiting job, so the
set of runs is the set of all base policies (static, dynamic, clairvoyant,
randomised: any realisation of a randomised policy is one of the branches).

Rules (mode):
  FREE       any waiting job                       -> every work-conserving policy
  CLOCK      head (minimum rank) if it has waited >= theta, else any
  CLOCK_TIE  oldest by arrival TIME if aged, ties among equal arrival times free
  GUARD      Algorithm 1, constant budget B: min-rank of E if E nonempty, else any
  UNION      head if aged, else min-rank of E, else any   (= min-rank of E u Aged)
  UNION_GF   min-rank of E if nonempty, else head if aged, else any
GUARD/UNION/UNION_GF take a report delay delta: the size C_c of a job completing
at t reaches the counter at t + delta (servers are still seen free at once).

Checks (index: statement, strict or not):
  0 PABS    k W <= V_i + (k-1)L + In_i                      every policy
  1 L1UP    U(t) <= V(t) + (k-1)L                           every policy, every t
  2 L1LO    V(t) <= U(t)
  3 FABS    k W_FCFS <= V_i + (k-1)L
  4 CIN     In_i < k(theta + L)             (i with an overtaker)   CLOCK, UNION
  5 CEX     W - W_FCFS < theta + (3 - 2/k)L                          CLOCK, UNION
  6 CABS    W < V_i/k + theta + (2 - 1/k)L                           CLOCK, UNION
  7 GIN     In_i < B + kL                   (i with an overtaker)   GUARD, UNION (delta 0)
  8 GEX     W - W_FCFS < B/k + (3 - 2/k)L                            GUARD, UNION (delta 0)
  9 GABS    W < (V_i + B)/k + (2 - 1/k)L                             GUARD, UNION (delta 0)
 10 TIEEX   check 5 under CLOCK_TIE
 11 GFEX    check 5 under UNION_GF
 12 DGEX    check 8 under UNION with delta > 0
 13 DGIN    check 7 under UNION with delta > 0
 14 IDENT   k W = R_i + In_i - Out_i - rho_i exactly (simulator invariant)
 15 GFIN    check 4 under UNION_GF
 16 TIEIN   check 4 under CLOCK_TIE
Ratio = lhs / rhs; a violation is ratio >= 1 for a strict bound, > 1 otherwise
(evaluated in integers, not through the float ratio).
"""

from __future__ import annotations

import itertools
import json
import sys
import time

import numba as nb
import numpy as np

FREE, CLOCK, CLOCK_TIE, GUARD, UNION, UNION_GF = 0, 1, 2, 3, 4, 5
NCHK = 17
NAMES = ["PABS", "L1UP", "L1LO", "FABS", "CIN", "CEX", "CABS", "GIN", "GEX", "GABS",
         "TIEEX", "GFEX", "DGEX", "DGIN", "IDENT", "GFIN", "TIEIN"]
ENUM = -1  # base = enumerate choices
B_RANDOM, B_SJF, B_LJF, B_LIFO, B_BIGYOUNG = 0, 1, 2, 3, 4
NEG = -1e300


@nb.njit(cache=True)
def simulate(arr, C, k, mode, theta2, B, delta, gamma, choice, nchoice, radix, base, s, order):
    """Run one schedule; fill start times s and dispatch order; return decision depth.

    Guard budget of job q: B (the cap) when gamma = 0, else min(gamma * n_q, B) with n_q
    the number of jobs waiting when q arrives (the queue-length shape with B_0 = 0)."""
    n = arr.size
    nq = np.zeros(n, np.int64)
    busy_until = np.zeros(k, np.int64)
    job_on = np.full(k, -1, np.int64)
    started = np.zeros(n, np.bool_)
    credited = np.zeros(n, np.bool_)
    comp = np.zeros(n, np.int64)
    over = np.zeros(n, np.int64)
    w = np.zeros(n, np.int64)
    opt = np.zeros(n, np.int64)
    arrived = 0
    nstarted = 0
    depth = 0
    pos = 0
    t = arr[0]
    while nstarted < n:
        for m in range(k):  # completions at t
            if job_on[m] >= 0 and busy_until[m] == t:
                job_on[m] = -1
        if mode >= GUARD:  # completion reports reaching the counter by t
            for c in range(n):
                if started[c] and (not credited[c]) and comp[c] + delta <= t:
                    credited[c] = True
                    for q in range(min(c, arrived)):
                        if not started[q]:
                            over[q] += C[c]
        while arrived < n and arr[arrived] == t:  # arrivals at t
            cnt = 0
            for q in range(arrived):
                if not started[q]:
                    cnt += 1
            nq[arrived] = cnt
            arrived += 1
        while True:  # dispatch phase
            m = -1
            for mm in range(k):
                if job_on[mm] < 0:
                    m = mm
                    break
            if m < 0:
                break
            nw = 0
            for q in range(arrived):
                if not started[q]:
                    w[nw] = q
                    nw += 1
            if nw == 0:
                break
            head = w[0]
            aged = 2 * (t - arr[head]) >= theta2
            minE = -1
            if mode >= GUARD:
                for x in range(nw):
                    bud = B if gamma == 0 else min(gamma * nq[w[x]], B)
                    if over[w[x]] >= bud:
                        minE = w[x]
                        break
            forced = -1
            nopt = 0
            if mode == CLOCK:
                if aged:
                    forced = head
            elif mode == GUARD:
                forced = minE
            elif mode == UNION:
                if aged:
                    forced = head
                elif minE >= 0:
                    forced = minE
            elif mode == UNION_GF:
                if minE >= 0:
                    forced = minE
                elif aged:
                    forced = head
            if forced >= 0:
                j = forced
            else:
                if mode == CLOCK_TIE and aged:
                    for x in range(nw):
                        if arr[w[x]] == arr[head]:
                            opt[nopt] = w[x]
                            nopt += 1
                else:
                    for x in range(nw):
                        opt[nopt] = w[x]
                        nopt += 1
                if nopt == 1:
                    j = opt[0]
                elif base == ENUM:
                    if depth >= nchoice:
                        choice[depth] = 0
                    radix[depth] = nopt
                    j = opt[choice[depth]]
                    depth += 1
                elif base == B_RANDOM:
                    j = opt[np.random.randint(nopt)]
                elif base == B_SJF:
                    j = opt[0]
                    for x in range(nopt):
                        if C[opt[x]] < C[j]:
                            j = opt[x]
                elif base == B_LJF:
                    j = opt[0]
                    for x in range(nopt):
                        if C[opt[x]] >= C[j]:
                            j = opt[x]
                elif base == B_LIFO:
                    j = opt[nopt - 1]
                else:  # youngest among the small ones first, then big: hurts the head
                    j = opt[nopt - 1]
                    for x in range(nopt - 1, -1, -1):
                        if C[opt[x]] < C[j]:
                            j = opt[x]
            s[j] = t
            comp[j] = t + C[j]
            busy_until[m] = comp[j]
            job_on[m] = j
            started[j] = True
            order[pos] = j
            pos += 1
            nstarted += 1
        nt = np.int64(1 << 60)
        if arrived < n:
            nt = arr[arrived]
        for m in range(k):
            if job_on[m] >= 0 and busy_until[m] < nt:
                nt = busy_until[m]
        t = nt
    return depth


@nb.njit(cache=True)
def fluid_V(arr, C, k):
    """V_i^-: rate-k fluid backlog of ranks < i at a_i, read after arrivals of lower rank."""
    n = arr.size
    V = np.zeros(n, np.int64)
    for i in range(1, n):
        v = V[i - 1] + C[i - 1] - k * (arr[i] - arr[i - 1])
        V[i] = v if v > 0 else 0
    return V


@nb.njit(cache=True)
def upd(r, viol, idx, lhs, rhs, strict):
    if rhs > 0:
        x = lhs / rhs
    elif lhs > 0:
        x = 1e9
    else:
        x = 0.0
    if x > r[idx]:
        r[idx] = x
    if (strict and lhs >= rhs) or ((not strict) and lhs > rhs):
        viol[idx] += 1


@nb.njit(cache=True)
def evaluate(arr, C, k, L, mode, theta2, B, delta, s, order, WF, V, r, viol, do_l1):
    n = arr.size
    posi = np.zeros(n, np.int64)
    for p in range(n):
        posi[order[p]] = p
    for i in range(n):
        W = s[i] - arr[i]
        In = 0
        Out = 0
        for j in range(n):
            if j > i and posi[j] < posi[i]:
                In += C[j]
            if j < i and posi[j] > posi[i]:
                Out += C[j]
        # every-policy statements
        upd(r, viol, 0, k * W, V[i] + (k - 1) * L + In, False)
        if mode == FREE:
            R = 0
            for j in range(i):
                if s[j] > arr[i]:
                    R += C[j]
                else:
                    rem = C[j] - (arr[i] - s[j])
                    if rem > 0:
                        R += rem
            rho = 0
            for j in range(n):
                if posi[j] < posi[i]:
                    rem = s[j] + C[j] - s[i]
                    if rem > 0:
                        rho += rem
            r[14] = 0.0
            lhs = k * W
            rhs = R + In - Out - rho
            if lhs != rhs:
                viol[14] += 1
        ex2k = 2 * k * (W - WF[i])
        if mode == CLOCK or mode == UNION:
            if In > 0:
                upd(r, viol, 4, 2 * In, k * theta2 + 2 * k * L, True)
            upd(r, viol, 5, ex2k, k * theta2 + 2 * (3 * k - 2) * L, True)
            upd(r, viol, 6, 2 * k * W, 2 * V[i] + k * theta2 + 2 * (2 * k - 1) * L, True)
        if mode == CLOCK_TIE:
            upd(r, viol, 10, ex2k, k * theta2 + 2 * (3 * k - 2) * L, True)
            if In > 0:
                upd(r, viol, 16, 2 * In, k * theta2 + 2 * k * L, True)
        if mode == UNION_GF:
            upd(r, viol, 11, ex2k, k * theta2 + 2 * (3 * k - 2) * L, True)
            if In > 0:
                upd(r, viol, 15, 2 * In, k * theta2 + 2 * k * L, True)
        if mode == GUARD or mode == UNION_GF or (mode == UNION and delta == 0):
            if In > 0:
                upd(r, viol, 7, In, B + k * L, True)
            upd(r, viol, 8, k * (W - WF[i]), B + (3 * k - 2) * L, True)
            upd(r, viol, 9, k * W, V[i] + B + (2 * k - 1) * L, True)
        if mode == UNION and delta > 0:
            if In > 0:
                upd(r, viol, 13, In, B + k * L, True)
            upd(r, viol, 12, k * (W - WF[i]), B + (3 * k - 2) * L, True)
    if do_l1:
        tend = 0
        for j in range(n):
            if s[j] + C[j] > tend:
                tend = s[j] + C[j]
        Vt = 0
        cap = (k - 1) * L
        for t in range(arr[0], tend + 1):
            A = 0
            U = 0
            nb_ = 0
            for j in range(n):
                if arr[j] == t:
                    A += C[j]
                if arr[j] <= t:
                    if s[j] > t:
                        U += C[j]
                    else:
                        rem = C[j] - (t - s[j])
                        if rem > 0:
                            U += rem
                if s[j] <= t and t < s[j] + C[j]:
                    nb_ += 1
            if t > arr[0]:
                Vt = Vt - k
                if Vt < 0:
                    Vt = 0
            Vt += A
            D = U - Vt
            upd(r, viol, 1, D, cap, False)
            upd(r, viol, 2, -D, 0, False)
            if 0 < Vt and Vt < k:  # fluid empties inside (t, t+1): D = U there
                kU0 = k * U - nb_ * Vt
                upd(r, viol, 1, kU0, k * cap, False)
                upd(r, viol, 2, -kU0, 0, False)


@nb.njit(cache=True)
def fcfs_reference(arr, C, k):
    """Independent FCFS: start_i = max(a_i, earliest server free), in rank order."""
    n = arr.size
    free = np.zeros(k, np.int64)
    for m in range(k):
        free[m] = arr[0]
    st = np.zeros(n, np.int64)
    for i in range(n):
        m = 0
        for mm in range(k):
            if free[mm] < free[m]:
                m = mm
        st[i] = max(arr[i], free[m])
        free[m] = st[i] + C[i]
    return st


@nb.njit(cache=True)
def explore(arr, C, k, L, mode, theta2, B, delta, gamma, WF, V, r, viol, do_l1):
    """All runs of the rule over every base policy; returns number of leaves."""
    n = arr.size
    choice = np.zeros(n + 1, np.int64)
    radix = np.zeros(n + 1, np.int64)
    s = np.zeros(n, np.int64)
    order = np.zeros(n, np.int64)
    nchoice = 0
    leaves = 0
    while True:
        depth = simulate(arr, C, k, mode, theta2, B, delta, gamma, choice, nchoice, radix, ENUM, s, order)
        evaluate(arr, C, k, L, mode, theta2, B, delta, s, order, WF, V, r, viol, do_l1)
        leaves += 1
        d = depth - 1
        while d >= 0 and choice[d] + 1 >= radix[d]:
            d -= 1
        if d < 0:
            return leaves
        choice[d] += 1
        nchoice = d + 1


@nb.njit(cache=True)
def prepare(arr, C, k, L, r, viol):
    n = arr.size
    s = np.zeros(n, np.int64)
    order = np.zeros(n, np.int64)
    dummy = np.zeros(n + 1, np.int64)
    simulate(arr, C, k, CLOCK, 0, 0, 0, 0, dummy, 0, dummy, ENUM, s, order)
    ref = fcfs_reference(arr, C, k)
    for i in range(n):
        if ref[i] != s[i]:
            viol[14] += 1000000  # FCFS mismatch: simulator bug
    WF = s - arr
    V = fluid_V(arr, C, k)
    for i in range(n):
        upd(r, viol, 3, k * WF[i], V[i] + (k - 1) * L, False)
    return WF, V


@nb.njit(cache=True, parallel=True)
def exhaustive_batch(ARR, CC, k, L, runs, R, VI, LEAVES):
    """ARR, CC: instances (padded rows with length column); runs: (mode, theta2, B, delta)."""
    N = ARR.shape[0]
    for x in nb.prange(N):
        n = ARR[x, 0]
        arr = ARR[x, 1:1 + n].copy()
        C = CC[x, :n].copy()
        r = np.full(NCHK, NEG)
        viol = np.zeros(NCHK, np.int64)
        WF, V = prepare(arr, C, k, L, r, viol)
        tot = 0
        for q in range(runs.shape[0]):
            mode = runs[q, 0]
            tot += explore(arr, C, k, L, mode, runs[q, 1], runs[q, 2], runs[q, 3], runs[q, 4], WF, V, r, viol,
                           mode == FREE)
        for c in range(NCHK):
            R[x, c] = r[c]
            VI[x, c] = viol[c]
        LEAVES[x] = tot


@nb.njit(cache=True)
def gen_random(k, L, nmax):
    """A bursty random instance: groups of same-instant arrivals, zero/short/long gaps."""
    n = np.random.randint(2, nmax + 1)
    arr = np.zeros(n, np.int64)
    C = np.zeros(n, np.int64)
    pL = np.random.random() * 0.7
    style = np.random.randint(3)
    t = 0
    i = 0
    while i < n:
        g = 1 + np.random.randint(1 + np.random.randint(2 * k + 2))
        for _ in range(g):
            if i >= n:
                break
            arr[i] = t
            u = np.random.random()
            if u < pL:
                C[i] = L
            elif style == 0:
                C[i] = 1 + np.random.randint(L)
            elif style == 1:
                C[i] = 1 + np.random.randint(max(1, L // 3))
            else:
                C[i] = 1 if np.random.random() < 0.5 else L - np.random.randint(2)
            i += 1
        u = np.random.random()
        if u < 0.3:
            t += 0
        elif u < 0.7:
            t += np.random.randint(1, L + 1)
        else:
            t += np.random.randint(1, 3 * L + 1)
    return arr, C


@nb.njit(cache=True, parallel=True)
def random_batch(seed0, N, kmax, R, VI, KS, PARAMS):
    for x in nb.prange(N):
        np.random.seed(seed0 + x)
        k = 1 + np.random.randint(kmax)
        L = 3 if np.random.random() < 0.4 else (10 if np.random.random() < 0.7 else 24)
        arr, C = gen_random(k, L, 40)
        n = arr.size
        u = np.random.randint(6)
        if u == 0:
            theta2 = 0
        elif u == 1:
            theta2 = 1
        elif u == 2:
            theta2 = 2 * L
        elif u == 3:
            theta2 = 2 * L + 1
        else:
            theta2 = np.random.randint(0, 8 * L + 1)
        u = np.random.randint(4)
        if u == 0:
            B = 0
        elif u == 1:
            B = L
        elif u == 2:
            B = k * L
        else:
            B = np.random.randint(0, 4 * k * L + 1)
        delta = np.random.randint(1, 3 * L + 1)
        gam = 0 if np.random.random() < 0.5 else np.random.randint(1, L + 1)
        r = np.full(NCHK, NEG)
        viol = np.zeros(NCHK, np.int64)
        WF, V = prepare(arr, C, k, L, r, viol)
        s = np.zeros(n, np.int64)
        order = np.zeros(n, np.int64)
        dummy = np.zeros(n + 1, np.int64)
        for base in range(5):
            reps = 3 if base == B_RANDOM else 1
            for _ in range(reps):
                for mode in range(6):
                    for dl in range(2):
                        if dl == 1 and mode != UNION:
                            continue
                        dd = delta if dl == 1 else 0
                        simulate(arr, C, k, mode, theta2, B, dd, gam, dummy, 0, dummy, base, s, order)
                        evaluate(arr, C, k, L, mode, theta2, B, dd, s, order, WF, V, r, viol,
                                 mode == FREE)
        for c in range(NCHK):
            R[x, c] = r[c]
            VI[x, c] = viol[c]
        KS[x] = k
        PARAMS[x, 0] = L
        PARAMS[x, 1] = theta2
        PARAMS[x, 2] = B
        PARAMS[x, 3] = delta
        PARAMS[x, 4] = gam


def instances(n):
    """Nondecreasing arrivals in 0..4 with a_1 = 0 (shift invariance), sizes in {1,2,3}."""
    rows_a, rows_c = [], []
    for tail in itertools.combinations_with_replacement(range(5), n - 1):
        a = (0,) + tail
        for c in itertools.product((1, 2, 3), repeat=n):
            rows_a.append((n,) + a + (0,) * (6 - n))
            rows_c.append(c + (0,) * (6 - n))
    return np.array(rows_a, np.int64), np.array(rows_c, np.int64)


def run_list():
    """Rows (mode, theta2, cap B, report delay, gamma)."""
    runs = [(FREE, 0, 0, 0, 0)]
    runs += [(CLOCK, t2, 0, 0, 0) for t2 in (0, 1, 2, 3, 4, 6, 8)]
    runs += [(CLOCK_TIE, t2, 0, 0, 0) for t2 in (0, 2, 6)]
    runs += [(GUARD, 0, b, 0, g) for b, g in ((0, 0), (1, 0), (3, 0), (6, 0), (6, 1), (6, 2))]
    runs += [(UNION, t2, b, 0, g) for t2, b, g in ((2, 3, 0), (6, 0, 0), (0, 6, 0), (3, 1, 0),
                                                   (8, 6, 0), (2, 6, 1), (4, 6, 2))]
    runs += [(UNION_GF, t2, b, 0, g) for t2, b, g in ((2, 3, 0), (0, 3, 0), (6, 1, 0),
                                                      (0, 6, 1), (2, 6, 1), (0, 6, 2), (2, 9, 3))]
    runs += [(UNION, t2, b, d, 0) for t2, b, d in ((2, 1, 2), (4, 0, 4), (6, 3, 3))]
    return np.array(runs, np.int64)


def witness(arr, C, k, L, mode, theta2, B, delta, gamma, check):
    """Replay every run of one rule on one instance; return the worst run of one check."""
    WF = fcfs_reference(arr, C, k) - arr
    V = fluid_V(arr, C, k)
    n = len(arr)
    choice = np.zeros(n + 1, np.int64)
    radix = np.zeros(n + 1, np.int64)
    s = np.zeros(n, np.int64)
    order = np.zeros(n, np.int64)
    best, nchoice = None, 0
    while True:
        depth = simulate(arr, C, k, mode, theta2, B, delta, gamma, choice, nchoice, radix, ENUM, s, order)
        r = np.full(NCHK, NEG)
        viol = np.zeros(NCHK, np.int64)
        evaluate(arr, C, k, L, mode, theta2, B, delta, s, order, WF, V, r, viol, mode == FREE)
        if best is None or r[check] > best[0]:
            best = (float(r[check]), s.copy().tolist(), order.copy().tolist())
        d = depth - 1
        while d >= 0 and choice[d] + 1 >= radix[d]:
            d -= 1
        if d < 0:
            break
        choice[d] += 1
        nchoice = d + 1
    return {"ratio": best[0], "arrivals": arr.tolist(), "sizes": C.tolist(), "k": k, "L": L,
            "mode": int(mode), "theta": theta2 / 2, "B": int(B), "delta": int(delta), "gamma": int(gamma),
            "starts": best[1], "dispatch_order": best[2], "W_FCFS": WF.tolist(),
            "V_minus": V.tolist()}


# check -> modes whose runs can produce it (for witness replay)
CHECK_MODES = {0: [FREE], 1: [FREE], 2: [FREE], 3: [FREE], 4: [CLOCK, UNION], 5: [CLOCK, UNION],
               6: [CLOCK, UNION], 7: [GUARD, UNION, UNION_GF], 8: [GUARD, UNION, UNION_GF],
               9: [GUARD, UNION, UNION_GF], 10: [CLOCK_TIE], 11: [UNION_GF], 12: [UNION],
               13: [UNION], 14: [FREE], 15: [UNION_GF], 16: [CLOCK_TIE]}


def find_witness(arr, C, k, L, runs, check):
    best = None
    for mode, t2, b, d, g in runs:
        if mode not in CHECK_MODES[check]:
            continue
        if check in (12, 13) and d == 0:
            continue
        if check in (7, 8, 9) and mode == UNION and d > 0:
            continue
        w = witness(arr, C, k, L, int(mode), int(t2), int(b), int(d), int(g), check)
        if best is None or w["ratio"] > best["ratio"]:
            best = w
    return best


def exhaustive(out):
    runs = run_list()
    L = 3
    for k in (1, 2, 3):
        t0 = time.time()
        allR, allV, allA, allC = [], [], [], []
        leaves = 0
        for n in range(1, 7):
            A, CC = instances(n)
            R = np.zeros((A.shape[0], NCHK))
            VI = np.zeros((A.shape[0], NCHK), np.int64)
            LV = np.zeros(A.shape[0], np.int64)
            exhaustive_batch(A, CC, k, L, runs, R, VI, LV)
            leaves += int(LV.sum())
            allR.append(R)
            allV.append(VI)
            allA.append(A)
            allC.append(CC)
        R = np.vstack(allR)
        VI = np.vstack(allV)
        A = np.vstack(allA)
        CC = np.vstack(allC)
        res = {"k": k, "instances": int(A.shape[0]), "runs_per_instance": int(runs.shape[0]),
               "leaves": leaves, "seconds": round(time.time() - t0, 1), "checks": {}}
        for c in range(NCHK):
            if R[:, c].max() == NEG:
                continue
            x = int(np.argmax(R[:, c]))
            nviol = int(VI[:, c].sum())
            n = int(A[x, 0])
            entry = {"worst_ratio": float(R[x, c]), "violations": nviol,
                     "instances_with_violation": int((VI[:, c] > 0).sum())}
            if c != 14:
                entry["witness"] = find_witness(A[x, 1:1 + n].copy(), CC[x, :n].copy(), k, L,
                                                runs, c)
            res["checks"][NAMES[c]] = entry
        out["exhaustive"].append(res)
        print(f"exhaustive k={k}: {res['instances']} instances, {leaves:,} runs, "
              f"{res['seconds']} s", flush=True)
        for name, e in res["checks"].items():
            print(f"  {name:6s} worst {e['worst_ratio']:.4f}  violations {e['violations']}",
                  flush=True)


def random_phase(out, N, kmax):
    R = np.zeros((N, NCHK))
    VI = np.zeros((N, NCHK), np.int64)
    KS = np.zeros(N, np.int64)
    P = np.zeros((N, 5), np.int64)
    t0 = time.time()
    seed0 = 20260923
    random_batch(seed0, N, kmax, R, VI, KS, P)
    res = {"instances": N, "seed0": seed0, "seconds": round(time.time() - t0, 1), "per_k": {}}
    for k in range(1, kmax + 1):
        sel = KS == k
        per = {"instances": int(sel.sum())}
        for c in range(NCHK):
            col = np.where(sel, R[:, c], NEG)
            if col.max() == NEG:
                continue
            x = int(np.argmax(col))
            per[NAMES[c]] = {"worst_ratio": float(R[x, c]), "violations": int(VI[sel, c].sum()),
                             "instances_with_violation": int((VI[sel, c] > 0).sum()),
                             "worst_instance_seed": seed0 + x,
                             "L_theta2_B_delta_gamma": P[x].tolist()}
        res["per_k"][str(k)] = per
    out["random"] = res
    print(f"random: {N:,} instances, {res['seconds']} s", flush=True)
    for k, per in res["per_k"].items():
        line = " ".join(f"{nm}={v['worst_ratio']:.3f}/{v['violations']}"
                        for nm, v in per.items() if nm != "instances")
        print(f"  k={k} ({per['instances']}): {line}", flush=True)


def main():
    part = sys.argv[1] if len(sys.argv) > 1 else "all"
    out = {"exhaustive": [], "names": NAMES}
    if part in ("all", "exhaustive"):
        exhaustive(out)
    if part in ("all", "random"):
        random_phase(out, 320_000, 4)
    path = f"evidence/new_theory_refutation/out_refute_{part}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print("wrote", path)


if __name__ == "__main__":
    main()
