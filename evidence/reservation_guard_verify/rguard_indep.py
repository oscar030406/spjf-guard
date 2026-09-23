"""Independent re-implementation of the reservation-and-refund rule R.

Written from the prose definition in ``../reservation_guard/report.md`` and
``../reservation_guard/README.md``.  No code is taken from
``../reservation_guard/rguard.py`` or from ``../guard_theory/sim_core.py``;
nothing from those directories is imported.

Model.  k identical unit-speed servers, non-preemptive, work-conserving.  A job
j has arrival a_j and service C_j; rank is the position in the input list, which
is sorted by (arrival, input index).  Every job carries an ENFORCED cap
ell_j with C_j <= ell_j <= L, known at the job's arrival.

Rule R.  At a dispatch epoch t with waiting set Q (in increasing rank), the base
policy proposes a waiting job j.  The proposal is accepted if j is the
minimum-rank member of Q, or if

    overR[q](t) + ell_j <= Z_q   for every q in Q with rank below j,

    overR[q](t) = sum over ranks r > q already dispatched of
                      C_r    if that job has completed by t (refunded)
                      ell_r  otherwise                      (reserved)

and is otherwise rejected, in which case the minimum-rank member of Q is
dispatched.  Dispatches at one instant form a phase and are tested one at a
time in the order they are made; a job dispatched earlier in the same phase is
"dispatched, not completed" and therefore carries its full reservation.

In_i / Out_i are read off the dispatch sequence (global order of dispatches),
excess_i = W_R[i] - W_FCFS[i].

Usage:  python rguard_indep.py <c1|c1rand|c2|c3|c4|c6|edge>
"""
import sys
from fractions import Fraction
from itertools import product
from random import Random

sys.dont_write_bytecode = True

INF = float("inf")


# --------------------------------------------------------------------------
# core simulator
# --------------------------------------------------------------------------
def _next_time(t, busy, arr, nxt, n):
    """Earliest strictly-later event: an arrival or a completion."""
    best = INF
    if nxt < n and arr[nxt] > t:
        best = arr[nxt]
    for f in busy:
        if f > t and f < best:
            best = f
    return best


def run_with_chooser(jobs, k, chooser):
    """Run one schedule.  chooser(t, queue, fin) -> index inside `queue`.

    `queue` is a tuple of ranks in increasing order; `fin` is a list with the
    completion time of every dispatched job and None elsewhere.
    Returns (start, seq) with start indexed by rank and seq the dispatch order.
    """
    n = len(jobs)
    arr = [j[0] for j in jobs]
    svc = [j[1] for j in jobs]
    busy = [-INF] * k                      # per-server completion time
    fin = [None] * n
    start = [None] * n
    seq = []
    queue = ()
    nxt = 0
    t = arr[0]
    while len(seq) < n:
        while nxt < n and arr[nxt] <= t:
            queue = queue + (nxt,)
            nxt += 1
        moved = False
        while queue:
            m = -1
            for idx in range(k):
                if busy[idx] <= t:
                    m = idx
                    break
            if m < 0:
                break
            c = chooser(t, queue, fin)
            j = queue[c]
            queue = queue[:c] + queue[c + 1:]
            start[j] = t
            fin[j] = t + svc[j]
            busy[m] = t + svc[j]
            seq.append(j)
            moved = True
        if len(seq) == n:
            break
        t2 = _next_time(t, busy, arr, nxt, n)
        if t2 == INF:
            raise RuntimeError("deadlock: %r" % (jobs,))
        t = t2
        if not moved and t2 == INF:
            raise RuntimeError("no progress")
    return start, seq


def fcfs_chooser(t, queue, fin):
    return 0


def fcfs_wait(jobs, k):
    start, _ = run_with_chooser(jobs, k, fcfs_chooser)
    return [start[i] - jobs[i][0] for i in range(len(jobs))]


# --------------------------------------------------------------------------
# rule R accounting
# --------------------------------------------------------------------------
def overR(q, t, svc, ell, fin, n):
    s = 0
    for r in range(q + 1, n):
        f = fin[r]
        if f is None:
            continue
        s += svc[r] if f <= t else ell[r]
    return s


def overC(q, t, svc, fin, n):
    s = 0
    for r in range(q + 1, n):
        f = fin[r]
        if f is not None and f <= t:
            s += svc[r]
    return s


def zget(Z, q):
    return Z[q] if isinstance(Z, (list, tuple)) else Z


def allowed_R(t, queue, fin, svc, ell, Z, n):
    """Positions inside `queue` that rule R permits to be dispatched now."""
    ok = [0]
    for c in range(1, len(queue)):
        j = queue[c]
        good = True
        for q in queue[:c]:
            if overR(q, t, svc, ell, fin, n) + ell[j] > zget(Z, q):
                good = False
                break
        if good:
            ok.append(c)
    return ok


def allowed_C(t, queue, fin, svc, Z, n):
    """Algorithm 1 (completed-work charging): if some waiting job is fired,
    only the minimum-rank fired job may go; otherwise anything may go."""
    for c, q in enumerate(queue):
        if overC(q, t, svc, fin, n) >= zget(Z, q):
            return [c]
    return list(range(len(queue)))


def make_R_chooser(base, svc, ell, Z, n):
    def f(t, queue, fin):
        c = base(t, queue, fin)
        if c == 0:
            return 0
        return c if c in allowed_R(t, queue, fin, svc, ell, Z, n) else 0
    return f


# --------------------------------------------------------------------------
# enumeration of every dispatch sequence a wrapped run can produce
# --------------------------------------------------------------------------
def enumerate_runs(jobs, k, rule, Z, ell=None, limit=2_000_000):
    """All (start, seq) reachable under `rule` over ALL base policies.

    rule in {'R', 'C', 'free'}.  For 'R' the reachable set at an epoch is the
    head (the wrapper's fallback, and also the base's own legal choice) plus
    every waiting job passing rule R's test.
    """
    n = len(jobs)
    arr = [j[0] for j in jobs]
    svc = [j[1] for j in jobs]
    if ell is None:
        ell = list(svc)
    out = []

    def choices(t, queue, fin):
        if rule == "free":
            return list(range(len(queue)))
        if rule == "C":
            return allowed_C(t, queue, fin, svc, Z, n)
        return allowed_R(t, queue, fin, svc, ell, Z, n)

    def rec(t, busy, nxt, queue, seq, start, fin):
        if len(out) >= limit:
            return
        while nxt < n and arr[nxt] <= t:
            queue = queue + (nxt,)
            nxt += 1
        free = -1
        for idx in range(k):
            if busy[idx] <= t:
                free = idx
                break
        if free >= 0 and queue:
            for c in choices(t, queue, fin):
                j = queue[c]
                nb = list(busy)
                nb[free] = t + svc[j]
                ns = list(start)
                ns[j] = t
                nf = list(fin)
                nf[j] = t + svc[j]
                rec(t, tuple(nb), nxt, queue[:c] + queue[c + 1:],
                    seq + (j,), tuple(ns), tuple(nf))
            return
        if len(seq) == n:
            out.append((start, seq))
            return
        t2 = _next_time(t, busy, arr, nxt, n)
        if t2 == INF:
            return
        rec(t2, busy, nxt, queue, seq, start, fin)

    rec(arr[0], tuple([-INF] * k), 0, (), (), tuple([None] * n),
        tuple([None] * n))
    return out


# --------------------------------------------------------------------------
# metrics
# --------------------------------------------------------------------------
def in_out(jobs, seq):
    n = len(jobs)
    svc = [j[1] for j in jobs]
    pos = [0] * n
    for p, j in enumerate(seq):
        pos[j] = p
    In = []
    Out = []
    for i in range(n):
        In.append(sum(svc[j] for j in range(i + 1, n) if pos[j] < pos[i]))
        Out.append(sum(svc[j] for j in range(i) if pos[j] > pos[i]))
    return In, Out


def excess(jobs, start, WF):
    return [start[i] - jobs[i][0] - WF[i] for i in range(len(jobs))]


# --------------------------------------------------------------------------
# C1: In <= Z, k=1 excess <= B, k>=2 excess <= B/k + (2-2/k)L
# --------------------------------------------------------------------------
class Tally(object):
    def __init__(self):
        self.runs = 0
        self.checks = 0
        self.viol_in = 0
        self.viol_exc = 0
        self.worst_in = None          # max(In_i - Z_i)
        self.worst_exc = None         # max(k*exc - Z_i - (2k-2)L)
        self.worst_k1 = None          # max(exc - Z_i) at k=1
        self.examples = []

    def note(self, key, val, inst):
        cur = getattr(self, key)
        if cur is None or val > cur:
            setattr(self, key, val)
            if val > 0 and len(self.examples) < 6:
                self.examples.append((key, val, inst))


def check_instance(jobs, k, Z, ell, L, tally, rule="R"):
    n = len(jobs)
    WF = fcfs_wait(jobs, k)
    for start, seq in enumerate_runs(jobs, k, rule, Z, ell):
        tally.runs += 1
        In, Out = in_out(jobs, seq)
        exc = excess(jobs, start, WF)
        for i in range(n):
            tally.checks += 1
            zi = zget(Z, i)
            d = In[i] - zi
            if d > 0:
                tally.viol_in += 1
            tally.note("worst_in", d, (jobs, k, Z, tuple(ell), seq, i))
            d2 = k * exc[i] - zi - (2 * k - 2) * L
            if d2 > 0:
                tally.viol_exc += 1
            tally.note("worst_exc", d2, (jobs, k, Z, tuple(ell), seq, i))
            if k == 1:
                tally.note("worst_k1", exc[i] - zi,
                           (jobs, k, Z, tuple(ell), seq, i))


def size_cap_vectors(n, sizes, L):
    for sv in product(sizes, repeat=n):
        for cv in product(*[range(c, L + 1) for c in sv]):
            yield sv, cv


ARR4 = [(0, 0, 0, 0), (0, 0, 1, 1), (0, 1, 2, 3), (0, 0, 0, 3),
        (0, 0, 2, 2), (0, 3, 6, 9)]
ARR5 = [(0, 0, 0, 0, 0), (0, 0, 1, 1, 2), (0, 1, 2, 3, 4), (0, 0, 0, 2, 2)]
ARR6 = [(0,) * 6, (0, 0, 1, 1, 2, 2), (0, 0, 0, 3, 3, 3)]


def c1():
    print("=" * 78)
    print("C1 (independent)  rule R: In_i <= Z_i ; k=1 exc <= B ; "
          "k>=2 k*exc - B <= (2k-2)L")
    print("=" * 78)
    grand = Tally()
    blocks = [
        ("n=4 L=3 sizes{1,2,3} caps[C..L] k=1,2,3 B=0,1,2,3,5", 4, (1, 2, 3),
         3, ARR4, (1, 2, 3), (0, 1, 2, 3, 5)),
        ("n=5 L=3 sizes{1,3} caps[C..L] k=1..4 B=0,1,2,4,6", 5, (1, 3), 3,
         ARR5, (1, 2, 3, 4), (0, 1, 2, 4, 6)),
        ("n=6 L=2 sizes{1,2} caps[C..L] k=1,2,3 B=0,1,2,3", 6, (1, 2), 2,
         ARR6, (1, 2, 3), (0, 1, 2, 3)),
    ]
    for name, n, sizes, L, arrs, ks, Bs in blocks:
        t = Tally()
        for sv, cv in size_cap_vectors(n, sizes, L):
            for arr in arrs:
                jobs = tuple(zip(arr, sv))
                for k in ks:
                    for B in Bs:
                        check_instance(jobs, k, B, list(cv), L, t)
        grand.runs += t.runs
        grand.checks += t.checks
        grand.viol_in += t.viol_in
        grand.viol_exc += t.viol_exc
        print("  %s" % name)
        print("     runs %-9d checks %-9d  max(In-Z)=%s  "
              "max(k*exc-Z-(2k-2)L)=%s  max(exc-Z | k=1)=%s  viol In/exc %d/%d"
              % (t.runs, t.checks, t.worst_in, t.worst_exc, t.worst_k1,
                 t.viol_in, t.viol_exc))
        for e in t.examples:
            print("      COUNTEREXAMPLE", e)
    print("  TOTAL runs %d checks %d   violations In %d  excess %d"
          % (grand.runs, grand.checks, grand.viol_in, grand.viol_exc))
    return grand


def c1rand():
    """Larger random instances, per-job caps, per-job allowances, random base."""
    print()
    print("=" * 78)
    print("C1 random  larger instances, per-job caps and per-job allowances")
    print("=" * 78)
    rng = Random(20260923)
    worst_in = None
    worst_exc = None
    worst_k1 = None
    nchk = 0
    nrun = 0
    for _ in range(20000):
        k = rng.choice([1, 1, 2, 3, 4, 5])
        n = rng.randint(2, 14)
        L = rng.choice([2, 3, 5, 8, 12])
        sizes = [rng.randint(1, L) for _ in range(n)]
        ell = [rng.randint(c, L) for c in sizes]
        arr = sorted(rng.randint(0, rng.choice([0, 2, 6, 20]))
                     for _ in range(n))
        jobs = tuple(zip(arr, sizes))
        if rng.random() < 0.3:
            Z = [rng.randint(0, 3 * L) for _ in range(n)]
        else:
            Z = rng.randint(0, 3 * L)
        WF = fcfs_wait(jobs, k)
        svc = [j[1] for j in jobs]

        def base(t, queue, fin, _rng=rng):
            return _rng.randrange(len(queue))

        ch = make_R_chooser(base, svc, ell, Z, n)
        start, seq = run_with_chooser(jobs, k, ch)
        nrun += 1
        In, Out = in_out(jobs, seq)
        exc = excess(jobs, start, WF)
        for i in range(n):
            nchk += 1
            zi = zget(Z, i)
            d = In[i] - zi
            if worst_in is None or d > worst_in:
                worst_in = d
                if d > 0:
                    print("   COUNTEREXAMPLE In>Z", jobs, k, Z, ell, seq, i)
            d2 = k * exc[i] - zi - (2 * k - 2) * L
            if worst_exc is None or d2 > worst_exc:
                worst_exc = d2
                if d2 > 0:
                    print("   COUNTEREXAMPLE exc", jobs, k, Z, ell, seq, i)
            if k == 1:
                e = exc[i] - zi
                if worst_k1 is None or e > worst_k1:
                    worst_k1 = e
    print("  runs %d  job checks %d   max(In-Z)=%s  max(k*exc-Z-(2k-2)L)=%s  "
          "max(exc-Z | k=1)=%s" % (nrun, nchk, worst_in, worst_exc, worst_k1))


def edge():
    """The boundary cases the report may not have covered."""
    print()
    print("=" * 78)
    print("EDGE  boundary cases")
    print("=" * 78)

    # (a) can a job be the queue head at one epoch and a non-head later?
    rng = Random(7)
    bad = 0
    trials = 0
    for _ in range(4000):
        k = rng.choice([1, 2, 3])
        n = rng.randint(2, 9)
        L = rng.choice([2, 4, 7])
        sizes = [rng.randint(1, L) for _ in range(n)]
        ell = [rng.randint(c, L) for c in sizes]
        arr = sorted(rng.randint(0, 10) for _ in range(n))
        jobs = tuple(zip(arr, sizes))
        Z = rng.randint(0, 2 * L)
        svc = [j[1] for j in jobs]
        was_head = set()
        state = {"bad": 0}

        def base(t, queue, fin, _rng=rng, _wh=was_head, _st=state):
            for q in _wh:
                if q in queue and q != queue[0]:
                    _st["bad"] += 1
            _wh.add(queue[0])
            return _rng.randrange(len(queue))

        run_with_chooser(jobs, k, make_R_chooser(base, svc, ell, Z, n))
        trials += 1
        bad += state["bad"]
    print("  (a) head monotonicity: %d runs, %d epochs at which a job that had "
          "been the head was waiting behind a lower rank" % (trials, bad))

    # (b) zero-size jobs (outside the paper's 0 < C <= L, probed anyway)
    t = Tally()
    for sv, cv in size_cap_vectors(4, (0, 1, 2), 2):
        for arr in [(0, 0, 0, 0), (0, 0, 1, 1)]:
            jobs = tuple(zip(arr, sv))
            for k in (1, 2):
                for B in (0, 1, 2, 3):
                    check_instance(jobs, k, B, list(cv), 2, t)
    print("  (b) with C_j = 0 allowed: runs %d  max(In-Z)=%s  "
          "max(k*exc-Z-(2k-2)L)=%s  violations %d/%d"
          % (t.runs, t.worst_in, t.worst_exc, t.viol_in, t.viol_exc))

    # (c) k >= 2 with genuinely idle servers (n < k, sparse arrivals)
    t = Tally()
    for n, arrs in ((2, [(0, 5), (0, 0)]), (3, [(0, 5, 11), (0, 0, 7)])):
        for sv, cv in size_cap_vectors(n, (1, 2, 3), 3):
            for arr in arrs:
                jobs = tuple(zip(arr, sv))
                for k in (3, 4, 5):
                    for B in (0, 2, 5, 9):
                        check_instance(jobs, k, B, list(cv), 3, t)
    print("  (c) idle servers (n<=k, sparse arrivals): runs %d  max(In-Z)=%s  "
          "max(k*exc-Z-(2k-2)L)=%s  violations %d/%d"
          % (t.runs, t.worst_in, t.worst_exc, t.viol_in, t.viol_exc))

    # (d) jobs arriving strictly inside an overtaker's service
    t = Tally()
    for sv, cv in size_cap_vectors(5, (1, 3), 3):
        for arr in [(0, 0, 1, 2, 2), (0, 0, 1, 1, 3), (0, 1, 1, 2, 4)]:
            jobs = tuple(zip(arr, sv))
            for k in (1, 2, 3):
                for B in (0, 1, 3, 6):
                    check_instance(jobs, k, B, list(cv), 3, t)
    print("  (d) arrivals during an overtaker's run: runs %d  max(In-Z)=%s  "
          "max(k*exc-Z-(2k-2)L)=%s  violations %d/%d"
          % (t.runs, t.worst_in, t.worst_exc, t.viol_in, t.viol_exc))

    # (e) equal sizes, different caps, and caps strictly inside (C, L)
    t = Tally()
    for arr in [(0, 0, 0, 0), (0, 0, 1, 1)]:
        sv = (2, 2, 2, 2)
        for cv in product(range(2, 6), repeat=4):
            jobs = tuple(zip(arr, sv))
            for k in (1, 2, 3):
                for B in (0, 2, 3, 4, 7, 11):
                    check_instance(jobs, k, B, list(cv), 5, t)
    print("  (e) equal sizes with unequal caps, C<ell<L: runs %d  "
          "max(In-Z)=%s  max(k*exc-Z-(2k-2)L)=%s  violations %d/%d"
          % (t.runs, t.worst_in, t.worst_exc, t.viol_in, t.viol_exc))


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "c1"
    if which == "c1":
        c1()
    elif which == "c1rand":
        c1rand()
    elif which == "edge":
        edge()
    else:
        raise SystemExit("unknown: %s" % which)
