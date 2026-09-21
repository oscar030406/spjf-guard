"""Referee simulator, written from theory.md's definitions only.

Independent of evidence/guard_theory/sim_core.py (the author's) and of
evidence/guard_variants/guardkern.py.  Exact integer arithmetic throughout
(speeds are handled by scaling time by lcm(v), see sim_speeds).

Model (theory.md section 1):
  * k servers, non-preemptive, work conserving (no server idles while a job waits)
  * jobs given ALREADY in rank order: rank == array index == (arrival, input index)
  * event order at an instant: completions -> arrivals -> dispatch
  * a dispatch phase repeats "pick a waiting job, put it on a free server" while
    a server is free and a job waits; the order inside the phase is the policy's
  * FCFS = always pick the minimum-rank waiting job

  In_i  = sum{ x_j : j > i, j dispatched before i in the dispatch SEQUENCE }
  Out_i = sum{ x_j : j < i, i dispatched before j in the dispatch SEQUENCE }
  (note: purely sequence based, so a job dispatched in the same phase as i,
   before it, counts in In_i even though it executes no work while i waits)
"""
import sys
sys.dont_write_bytecode = True
from itertools import count


# ---------------------------------------------------------------- simulation

def simulate(a, x, k, chooser):
    """chooser(t, waiting_list, state) -> job id to dispatch.

    state is a dict with 'start', 'comp', 'srv_end', 'srv_job', 'order'.
    Returns (start, comp, order) with order = dispatch sequence (job ids).
    """
    n = len(a)
    start = [-1] * n
    comp = [-1] * n
    srv_end = [None] * k
    srv_job = [-1] * k
    waiting = []
    order = []
    state = {'start': start, 'comp': comp, 'srv_end': srv_end,
             'srv_job': srv_job, 'order': order, 'x': x, 'a': a, 'k': k}
    nxt = 0
    done = 0
    t = a[0]
    while done < n:
        for r in range(k):                                   # 1. completions
            if srv_end[r] is not None and srv_end[r] == t:
                j = srv_job[r]
                comp[j] = t
                srv_end[r] = None
                srv_job[r] = -1
                done += 1
        while nxt < n and a[nxt] == t:                       # 2. arrivals
            waiting.append(nxt)
            nxt += 1
        while waiting and any(e is None for e in srv_end):   # 3. dispatch
            j = chooser(t, waiting, state)
            r = srv_end.index(None)
            srv_end[r] = t + x[j]
            srv_job[r] = j
            start[j] = t
            order.append(j)
            waiting.remove(j)
            # a zero-length job completes at this same instant: free it now so
            # that work conservation keeps holding inside the phase
            if x[j] == 0:
                comp[j] = t
                srv_end[r] = None
                srv_job[r] = -1
                done += 1
        nt = None                                            # 4. next event
        for e in srv_end:
            if e is not None and (nt is None or e < nt):
                nt = e
        if nxt < n and (nt is None or a[nxt] < nt):
            nt = a[nxt]
        if nt is None:
            break
        t = nt
    return start, comp, order


def fcfs_chooser(t, waiting, state):
    return min(waiting)


def make_score_chooser(score):
    """dispatch argmin (score[j], j) among waiting jobs."""
    def ch(t, waiting, state):
        return min(waiting, key=lambda j: (score[j], j))
    return ch


def make_choice_chooser(tape):
    """free-choice tape: at the p-th dispatch take the (tape[p] mod nw)-th
    waiting job in rank order.  Reaches every work-conserving schedule."""
    def ch(t, waiting, state):
        p = len(state['order'])
        w = sorted(waiting)
        return w[tape[p] % len(w)]
    return ch


def make_guard_choice_chooser(tape, B, x, n):
    def ch(t, waiting, state):
        comp = state['comp']
        suf = [0] * (n + 1)
        for j in range(n - 1, -1, -1):
            done_by_t = (comp[j] != -1 and comp[j] <= t)
            suf[j] = suf[j + 1] + (x[j] if done_by_t else 0)
        E = [q for q in waiting if suf[q + 1] >= B]
        if E:
            return min(E)
        p = len(state['order'])
        w = sorted(waiting)
        return w[tape[p] % len(w)]
    return ch


def make_guard_chooser(base_score, B, x, n):
    """theory.md section 4 wrapper.

    over_q(t) = total true work of jobs of rank > q COMPLETED by t.
    E(t) = { q waiting : over_q(t) >= B }; dispatch min E(t) if non-empty,
    else the base policy's pick (argmin (base_score, rank)).
    """
    def ch(t, waiting, state):
        comp = state['comp']
        # suffix sums of completed work
        suf = [0] * (n + 1)
        for j in range(n - 1, -1, -1):
            done_by_t = (comp[j] != -1 and comp[j] <= t)
            suf[j] = suf[j + 1] + (x[j] if done_by_t else 0)
        E = [q for q in waiting if suf[q + 1] >= B]
        if E:
            return min(E)
        return min(waiting, key=lambda j: (base_score[j], j))
    return ch


# --------------------------------------------------------------- quantities

def in_out(x, order, n):
    pos = [0] * n
    for p, j in enumerate(order):
        pos[j] = p
    In = [0] * n
    Out = [0] * n
    for i in range(n):
        for j in range(n):
            if j > i and pos[j] < pos[i]:
                In[i] += x[j]
            elif j < i and pos[i] < pos[j]:
                Out[i] += x[j]
    return In, Out


def waits(a, start):
    return [start[i] - a[i] for i in range(len(a))]


# ------------------------------------------------- exhaustive enumeration

def enumerate_schedules(a, x, k, cap=10 ** 9):
    """Yield (start, comp, order) for EVERY work-conserving non-preemptive
    schedule (every choice at every dispatch step, every order inside a
    dispatch phase).  Servers are identical, so which free server is used is
    irrelevant and is not branched on."""
    n = len(a)
    out = []

    def step(t, srv_end, srv_job, waiting, nxt, done, start, comp, order):
        if len(out) >= cap:
            return
        srv_end = list(srv_end)
        srv_job = list(srv_job)
        waiting = list(waiting)
        start = list(start)
        comp = list(comp)
        order = list(order)
        for r in range(k):
            if srv_end[r] is not None and srv_end[r] == t:
                j = srv_job[r]
                comp[j] = t
                srv_end[r] = None
                srv_job[r] = -1
                done += 1
        while nxt < n and a[nxt] == t:
            waiting.append(nxt)
            nxt += 1
        if waiting and any(e is None for e in srv_end):
            for j in list(waiting):
                se = list(srv_end)
                sj = list(srv_job)
                w = [q for q in waiting if q != j]
                st = list(start)
                cp = list(comp)
                od = order + [j]
                d = done
                r = se.index(None)
                se[r] = t + x[j]
                sj[r] = j
                st[j] = t
                if x[j] == 0:
                    cp[j] = t
                    se[r] = None
                    sj[r] = -1
                    d += 1
                step(t, se, sj, w, nxt, d, st, cp, od)
            return
        if done == n:
            out.append((start, comp, order))
            return
        nt = None
        for e in srv_end:
            if e is not None and (nt is None or e < nt):
                nt = e
        if nxt < n and (nt is None or a[nxt] < nt):
            nt = a[nxt]
        if nt is None:
            out.append((start, comp, order))
            return
        step(nt, srv_end, srv_job, waiting, nxt, done, start, comp, order)

    step(a[0], [None] * k, [-1] * k, [], 0, 0, [-1] * n, [-1] * n, [])
    return out


# ------------------------------------------------- heterogeneous speeds

def sim_speeds(a, x, v, chooser, assign="fastest"):
    """Speeds v[0..k-1]; time is measured in the SAME units as a and x, so the
    caller must pre-scale so that x*lcm(v)/v is an integer.  Internally we keep
    time as a Fraction-free integer by requiring v | x*scale.

    Occupancy of job j on server m is x[j]/v[m].  To stay exact we work in
    time units of 1/lcm(v): call with a already multiplied by lcm(v) and use
    dur = x[j]*lcm(v)//v[m].
    assign: 'fastest' (free server with the largest speed) or 'slowest'.
    """
    n = len(a)
    k = len(v)
    from math import gcd
    lc = 1
    for s in v:
        lc = lc * s // gcd(lc, s)
    start = [-1] * n
    comp = [-1] * n
    srv_end = [None] * k
    srv_job = [-1] * k
    waiting = []
    order = []
    state = {'start': start, 'comp': comp, 'srv_end': srv_end,
             'srv_job': srv_job, 'order': order, 'x': x, 'a': a, 'k': k}
    nxt = 0
    done = 0
    t = a[0]
    while done < n:
        for r in range(k):
            if srv_end[r] is not None and srv_end[r] == t:
                comp[srv_job[r]] = t
                srv_end[r] = None
                srv_job[r] = -1
                done += 1
        while nxt < n and a[nxt] == t:
            waiting.append(nxt)
            nxt += 1
        while waiting and any(e is None for e in srv_end):
            j = chooser(t, waiting, state)
            free = [r for r in range(k) if srv_end[r] is None]
            if assign == "fastest":
                r = max(free, key=lambda r: (v[r], -r))
            else:
                r = min(free, key=lambda r: (v[r], r))
            dur = x[j] * lc // v[r]
            srv_end[r] = t + dur
            srv_job[r] = j
            start[j] = t
            order.append(j)
            waiting.remove(j)
            if dur == 0:
                comp[j] = t
                srv_end[r] = None
                srv_job[r] = -1
                done += 1
        nt = None
        for e in srv_end:
            if e is not None and (nt is None or e < nt):
                nt = e
        if nxt < n and (nt is None or a[nxt] < nt):
            nt = a[nxt]
        if nt is None:
            break
        t = nt
    return start, comp, order, lc
