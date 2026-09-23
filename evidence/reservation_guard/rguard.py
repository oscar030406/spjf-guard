"""Exact integer simulators for the reservation-and-refund guard (rule R).

Model (identical to evidence/guard_theory/sim_core.py, which is imported and
not modified): k identical non-preemptive work-conserving servers, jobs given in
rank order as (a, C), rank = (arrival, input index), In_i / Out_i defined against
the dispatch sequence, same-phase dispatches counted in the dispatch sequence.

Rule R.  Every job j carries an ENFORCED cap ell_j with C_j <= ell_j <= L, known
at j's arrival.  For a waiting job q define, at a dispatch epoch t,

    overR[q](t) = sum over j > q already dispatched of
                      C_j     if j has completed by t   (refunded)
                      ell_j   otherwise                 (reserved)

The base policy proposes a waiting job j.  If j is the minimum-rank waiting job
the proposal is accepted (it overtakes nobody).  Otherwise it is accepted iff

    overR[q](t) + ell_j <= Z_q   for every waiting q of rank below j,

and rejected otherwise, in which case the minimum-rank waiting job is dispatched.
Every dispatch of a phase is tested separately and in the order the policy makes
them; a job dispatched earlier in the same phase is already "dispatched, not
completed" and is therefore charged its full reservation ell.

Rule C (the paper's Algorithm 1, for comparison): overC[q](t) = sum of C_j over
j > q completed by t; fired set E = {q : overC[q] >= B}; if E is non-empty the
minimum-rank member of E is dispatched, else the base proposal is accepted.
"""
import sys
import os

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "guard_theory"))

import sim_core  # noqa: E402


# --------------------------------------------------------------- accounting --
def overR(q, t, x, ell, done, n):
    s = 0
    for r in range(q + 1, n):
        d = done[r]
        if d is not None:
            s += x[r] if d <= t else ell[r]
    return s


def overC(q, t, x, done, n):
    s = 0
    for r in range(q + 1, n):
        d = done[r]
        if d is not None and d <= t:
            s += x[r]
    return s


# ------------------------------------------------------------- the wrappers --
def make_rguard(base, Z, ell):
    """Z is either an int (common allowance) or a list indexed by rank."""
    def zof(q):
        return Z[q] if isinstance(Z, (list, tuple)) else Z

    def f(t, waiting, state):
        x, done, n = state['x'], state['done'], state['n']
        c = base(t, waiting, state)
        if c == 0:
            return 0
        j = waiting[c]
        for cq in range(c):
            q = waiting[cq]
            if overR(q, t, x, ell, done, n) + ell[j] > zof(q):
                return 0
        return c
    return f


def make_cguard(base, B):
    """Algorithm 1 exactly as in the paper (completed-work charging)."""
    def bof(q):
        return B[q] if isinstance(B, (list, tuple)) else B

    def f(t, waiting, state):
        x, done, n = state['x'], state['done'], state['n']
        for c, q in enumerate(waiting):
            if overC(q, t, x, done, n) >= bof(q):
                return c
        return base(t, waiting, state)
    return f


# ------------------------------------------------- exhaustive adversarial base
def enum_runs(jobs, k, rule, par, ell=None, cap=400000):
    """Every dispatch sequence a wrapped run can produce, over ALL base policies.

    rule == 'R': at each epoch the permitted proposals are the minimum-rank
    waiting job plus every waiting job passing rule R's test.
    rule == 'C': if the fired set is non-empty only its minimum-rank member is
    permitted; otherwise every waiting job is.
    rule == 'free': every waiting job (no wrapper) -- all work-conserving runs.
    Returns a list of (order, start) with start indexed by rank.
    """
    n = len(jobs)
    a = [j[0] for j in jobs]
    x = [j[1] for j in jobs]
    if ell is None:
        ell = list(x)
    out = []

    def zof(q):
        return par[q] if isinstance(par, (list, tuple)) else par

    def allowed(t, waiting, done):
        if rule == 'free':
            return list(range(len(waiting)))
        if rule == 'C':
            for c, q in enumerate(waiting):
                if overC(q, t, x, done, n) >= zof(q):
                    return [c]
            return list(range(len(waiting)))
        ok = [0]
        for c in range(1, len(waiting)):
            j = waiting[c]
            good = True
            for cq in range(c):
                q = waiting[cq]
                if overR(q, t, x, ell, done, n) + ell[j] > zof(q):
                    good = False
                    break
            if good:
                ok.append(c)
        return ok

    def rec(t, free, nxt, waiting, order, start, done):
        if len(out) >= cap:
            return
        while nxt < n and a[nxt] <= t:
            waiting = waiting + (nxt,)
            nxt += 1
        si = -1
        for m in range(k):
            if free[m] <= t:
                si = m
                break
        if si >= 0 and waiting:
            for c in allowed(t, waiting, done):
                j = waiting[c]
                nf = list(free)
                nf[si] = t + x[j]
                ns = list(start)
                ns[j] = t
                nd = list(done)
                nd[j] = t + x[j]
                rec(t, tuple(nf), nxt, waiting[:c] + waiting[c + 1:],
                    order + (j,), tuple(ns), tuple(nd))
            return
        if len(order) == n:
            out.append((order, start))
            return
        cand = []
        if nxt < n:
            cand.append(a[nxt])
        for m in range(k):
            if free[m] > t:
                cand.append(free[m])
        if not cand:
            return
        rec(min(cand), free, nxt, waiting, order, start, done)

    rec(a[0], tuple([a[0]] * k), 0, (), (), tuple([None] * n),
        tuple([None] * n))
    return out


# ------------------------------------------------------------------ metrics --
def metrics(jobs, k, order, start):
    """In, Out, wait, excess against FCFS, for every job."""
    n = len(jobs)
    a = [j[0] for j in jobs]
    x = [j[1] for j in jobs]
    pos = [0] * n
    for p, j in enumerate(order):
        pos[j] = p
    In = [sum(x[j] for j in range(i + 1, n) if pos[j] < pos[i]) for i in range(n)]
    Out = [sum(x[j] for j in range(i) if pos[j] > pos[i]) for i in range(n)]
    WF = sim_core.fcfs_wait(jobs, k)
    W = [start[i] - a[i] for i in range(n)]
    exc = [W[i] - WF[i] for i in range(n)]
    return In, Out, W, WF, exc


def lam_instance(jobs, k, i, sP_i):
    """Lambda of verification.md section 8: the k largest raw sizes among jobs of
    rank > i arrived by sP_i (the reservoir the kL term charges), and the k-1
    largest among ranks < i (the rho^FCFS reservoir)."""
    a = [j[0] for j in jobs]
    x = [j[1] for j in jobs]
    hi = sorted((x[j] for j in range(i + 1, len(jobs)) if a[j] <= sP_i),
                reverse=True)[:k]
    lo = sorted((x[j] for j in range(i)), reverse=True)[:k - 1]
    return sum(hi), sum(lo)
