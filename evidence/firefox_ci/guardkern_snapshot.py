"""Event-driven k-server non-preemptive queue with a family of overtake-budget guards.

One numba kernel covers every policy studied here; the rule is fixed by its parameters.

    k identical servers, non-preemptive, work conserving (a server never idles while a
    job waits), every service time <= L.  Jobs carry a stable arrival rank (arrival
    time, input index) and the input arrays must already be in that order.  The
    scheduler reads a job's TRUE service time only when that job completes.

    over[q]   = total true service of jobs that arrived after q (rank > q) and have
                COMPLETED while q was waiting.  Kept for the whole waiting set at once
                as over[q] = TC - F(q):  TC = total completed work, F = Fenwick prefix
                sum of completed work over ranks <= q.
    budget(q) = C_q + eps * (t - a_q),   C_q = C0 + gam * (jobs waiting when q arrived)
    fired(q)  = over[q] >= budget(q)                       [work channel]
                or cntfree[q] >= Ncap                      [count channel, optional]
    When theta > 0 a completed overtaker charges the work channel only if its true
    service exceeds theta, and otherwise charges 1 to the count channel.

    DISPATCH: let E = {waiting q : fired(q)}.  If E is non-empty serve its SMALLEST-RANK
    member, otherwise serve the smallest `pred` (ties to the smaller rank).

Serving the smallest-rank member of E is what makes the per-job theorem work when the
budget is not the same for every job: a job is overtaken only at instants when its own
budget is still unspent.  For a constant budget (eps = gam = theta = 0) over[q] is
non-increasing in rank, so E is non-empty iff the head is in it and its smallest-rank
member IS the head; the rule is then exactly the head check of the existing guard.

Implementation: `over` and the budgets are integer microseconds; the clock is float64
seconds, as in the project simulator, so the two agree job by job.  The firing test is a
segment tree over a window of ranks (range add, "leftmost leaf >= T"), both O(log M);
the window is rebuilt, rarely, when the span of waiting ranks outgrows it.

Condition algebra used by the tree (int64, exact), eps = en/ed:
    over[q] >= C_q + eps (t - a_q)
    <=>  en*a_us[q] - ed*C_q - ed*F(q)  >=  en*t_us - ed*TC
         Z(q), suffix range-add             T(t), recomputed per decision

===============================================================================
WHAT IS GUARANTEED  (`guaranteed()` below evaluates these bounds job by job)
===============================================================================
Setting: k identical servers, non-preemptive, work conserving, service times in (0, L].
FCFS is the same-input schedule that always dispatches the earliest-ranked waiting job.
Arrivals, service times and predictions are arbitrary (adversarial predictions included).

LEMMA (workload comparison).  For any two non-preemptive work-conserving k-server
policies A, B on the same input, the total unfinished work obeys
        |U_A(t) - U_B(t)| <= (k-1) L      for all t.
Proof.  Arrivals add the same amount to both, so U_A - U_B only moves between arrivals,
at rate -(min(N_A,k) - min(N_B,k)).  If U_A(t) > (k-1)L then more than k-1 jobs are
present (each carries at most L of remaining work), so all k servers are busy and
min(N_A,k) = k >= min(N_B,k): the difference is non-increasing there.  Let t0 be the last
time <= t with U_A(t0) <= (k-1)L (if none, U_A(t) <= (k-1)L and the claim is immediate
since U_B >= 0).  On (t0, t] the difference does not increase, so
U_A(t) - U_B(t) <= U_A(t0) - U_B(t0) <= (k-1)L - 0.  Swap A and B for the other side. []

THEOREM A (constant budget B, any k).  The head-check guard of the project (eps = gam =
theta = 0, budget B) satisfies, for EVERY job i,
        W_guard[i] <= W_FCFS[i] + B/k + (3 - 2/k) L.
At k = 1 this is exactly the known W <= W_FCFS + B + L.

THEOREM B (budget C_i + eps*(elapsed wait), eps < k, smallest-rank-fired dispatch).
        (k - eps) W_guard[i] <= k W_FCFS[i] + C_i + (3k - 2) L,
i.e. with eps = eta*k, eta in [0,1):
        W_guard[i] <= ( W_FCFS[i] + C_i/k + (3 - 2/k) L ) / (1 - eta).
If the budget is additionally capped at Bmax, Theorem A applies with B = Bmax as well,
so the bound is the smaller of the two.  Reading of eta: a waiting job tolerates at most
a fraction eta of the system's whole service capacity, over its own waiting time, being
spent on jobs that arrived after it.

Proof of A and B (one argument; A is B with eps = 0).  Fix i and write W = W_guard[i].
(1) Throughout [a_i, start_i) job i waits, so by work conservation all k servers are
    busy and the work executed in that interval is exactly k*W.  Split it into E_old
    (jobs of rank < i) and E_new (jobs of rank > i, the overtakers).
(2) E_old <= R_i, the remaining work at time a_i of the jobs with rank < i, since those
    are the only ones that can contribute.
(3) Every overtaker j of i is dispatched at an instant when i is waiting and i is not in
    the fired set E (either E is empty, or j = min E and rank i < rank j so i is not in
    E).  Hence at that instant over[i] < budget_i <= C_i + eps*(t - a_i) < C_i + eps*W.
    over[i] counts only COMPLETED overtakers; at most k-1 more are in service (one server
    is free, it is taking j), so the total service of the overtakers dispatched strictly
    before j is < C_i + eps*W + (k-1)L.  Adding j itself, taken at the last such instant,
        E_new < C_i + eps*W + k L.
(4) Under FCFS, during [a_i, start^F_i) all k servers are busy too and every job they run
    has rank < i (FCFS never starts a later-ranked job before i).  At start^F_i every
    rank < i job has been dispatched and at most k-1 are still running, each with less
    than L left, so   k W_FCFS[i] >= R^F_i - (k-1) L,  where R^F_i is FCFS's remaining
    work of the rank < i jobs at a_i.
(5) Before a_i only jobs of rank < i exist, so both schedules see the same input on
    [0, a_i) and the Lemma gives R_i <= R^F_i + (k-1) L.
Combining (1)-(5):  k W <= R_i + E_new <= [k W_FCFS[i] + (k-1)L] + (k-1)L + C_i + eps*W
+ kL, i.e. (k - eps) W <= k W_FCFS[i] + C_i + (3k-2) L. []

COUNT CHANNEL.  If completed overtakers with service <= theta are charged 1 to a count
budget Ncap instead of charging their work, step (3) gives E_new < C_i + eps*W + Ncap*
theta + kL, so the bounds hold with C_i replaced by C_i + Ncap*theta.  Setting C_i = -1
(work channel off) and theta = L makes this the finite-skip / position-count rule, with
        W_guard[i] <= W_FCFS[i] + L (Ncap + 3k - 2)/k.

NOT GUARANTEED.  Charging nothing for short overtakers (theta > 0, no count cap) and
age-blended ranking (argmin pred - alpha*age) admit no per-job bound; brute.py builds the
counterexamples.
"""
import numpy as np
from numba import njit

NEG = -(1 << 62)
L_CAP = 60.0


# --------------------------------------------------------------------------- #
# segment tree: range add, query "leftmost leaf with value >= T".
# Lazy tags sit on internal nodes and are never pushed down:
#   true max of subtree(node) = tre[node] + sum of lz over the STRICT ancestors.
# --------------------------------------------------------------------------- #
@njit(cache=True)
def _st_clear(tre, lz, size):
    for i in range(2 * size):
        tre[i] = NEG
    for i in range(size):
        lz[i] = 0


@njit(cache=True, inline="always")
def _st_pull(tre, lz, node):
    while node >= 1:
        x = tre[2 * node]
        y = tre[2 * node + 1]
        tre[node] = (x if x > y else y) + lz[node]
        node >>= 1


@njit(cache=True)
def _st_set(tre, lz, size, pos, val):
    """Assign `val` as the true value of leaf `pos`."""
    node = 1
    acc = 0
    half = size
    while half > 1:
        acc += lz[node]
        half >>= 1
        node = 2 * node + 1 if (pos & half) else 2 * node
    acc += 0
    tre[node] = val - acc
    _st_pull(tre, lz, node >> 1)


@njit(cache=True)
def _st_add_suffix(tre, lz, size, lo, val):
    """Add `val` to the true value of every leaf in [lo, size-1]."""
    if lo >= size:
        return
    if lo < 0:
        lo = 0
    l = lo + size
    r = 2 * size - 1
    l0 = l
    r0 = r
    r += 1
    while l < r:
        if l & 1:
            tre[l] += val
            if l < size:
                lz[l] += val
            l += 1
        if r & 1:
            r -= 1
            tre[r] += val
            if r < size:
                lz[r] += val
        l >>= 1
        r >>= 1
    _st_pull(tre, lz, l0 >> 1)
    _st_pull(tre, lz, r0 >> 1)


@njit(cache=True)
def _st_leftmost(tre, lz, size, T):
    """Smallest leaf index whose true value is >= T, or -1."""
    if tre[1] < T:
        return -1
    node = 1
    acc = 0
    while node < size:
        acc += lz[node]
        if tre[2 * node] + acc >= T:
            node = 2 * node
        else:
            node = 2 * node + 1
    return node - size


# --------------------------------------------------------------------------- #
# min-heap on (key, idx) in preallocated arrays
# --------------------------------------------------------------------------- #
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
def simulate(a, s, pred, k, mode, C0_us, gam_us, en, ed, theta_us, Ncap, Bmax_us, Mslots):
    """mode 0 = FCFS, 1 = pure `pred` order, 2 = guard.
    Returns (wait, cbud_us, n_disp, n_forced, qw_total, qw_forced, n_rebuild, max_span)."""
    n = a.shape[0]
    wait = np.empty(n, np.float64)
    cbud = np.zeros(n, np.int64)
    rt = np.empty(k + 1, np.float64)
    rj = np.empty(k + 1, np.int64)
    nrun = 0
    hk = np.empty(n + 1, np.float64)
    hi = np.empty(n + 1, np.int64)
    nh = 0
    served = np.zeros(n, np.uint8)
    fq = np.empty(n + 1, np.int64)
    fh = 0
    ft = 0
    guard = mode == 2
    use_cnt = theta_us > 0 and Ncap > 0
    size = 1
    while size < Mslots:
        size *= 2
    ts = 2 * size if guard else 2
    tre = np.empty(ts, np.int64)
    lz = np.empty(ts // 2, np.int64)
    tre2 = np.empty(ts if use_cnt else 2, np.int64)
    lz2 = np.empty((ts if use_cnt else 2) // 2, np.int64)
    if guard:
        _st_clear(tre, lz, size)
        if use_cnt:
            _st_clear(tre2, lz2, size)
    base = 0
    Zs = np.empty(n if guard else 1, np.int64)
    F = np.zeros((n + 1) if guard else 1, np.int64)
    FC = np.zeros((n + 1) if use_cnt else 1, np.int64)
    TC = 0
    TCNT = 0
    i = 0
    nwait = 0
    nstarted = 0
    n_disp = 0
    n_forced = 0
    qw_total = 0
    qw_forced = 0
    n_rebuild = 0
    max_span = 0
    err = 0
    t = -1.0e300
    INF = 1.0e300
    while nstarted < n:
        # ---------------- completions at or before t
        while nrun > 0 and rt[0] <= t:
            c = rj[0]
            nrun -= 1
            rt[0] = rt[nrun]
            rj[0] = rj[nrun]
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
                    cc = b
                else:
                    break
            if guard:
                cus = np.int64(round(s[c] * 1000000.0))
                if use_cnt and cus <= theta_us:
                    TCNT += 1
                    p = c + 1
                    while p <= n:
                        FC[p] += 1
                        p += p & -p
                    _st_add_suffix(tre2, lz2, size, c - base, -1)
                else:
                    TC += cus
                    p = c + 1
                    while p <= n:
                        F[p] += cus
                        p += p & -p
                    _st_add_suffix(tre, lz, size, c - base, -ed * cus)
        # ---------------- arrivals at or before t
        while i < n and a[i] <= t:
            if guard:
                cb = C0_us + gam_us * nwait
                cbud[i] = cb
                if nwait == 0:
                    base = i
                elif i - base >= Mslots:
                    while served[fq[fh]] == 1:
                        fh += 1
                    nb = fq[fh]
                    if i - nb >= Mslots:      # window too small for the live span
                        err = 1
                        break
                    _st_clear(tre, lz, size)
                    if use_cnt:
                        _st_clear(tre2, lz2, size)
                    for p in range(fh, ft):
                        q = fq[p]
                        if served[q] == 1:
                            continue
                        _st_set(tre, lz, size, q - nb, Zs[q] - ed * _fen_pref(F, q))
                        if use_cnt:
                            _st_set(tre2, lz2, size, q - nb, -_fen_pref(FC, q))
                    base = nb
                    n_rebuild += 1
                if i - base + 1 > max_span:
                    max_span = i - base + 1
                aus = np.int64(round(a[i] * 1000000.0))
                z = en * aus - ed * cb
                Zs[i] = z
                _st_set(tre, lz, size, i - base, z - ed * _fen_pref(F, i))
                if use_cnt:
                    _st_set(tre2, lz2, size, i - base, -_fen_pref(FC, i))
            if mode != 1:
                fq[ft] = i
                ft += 1
            if mode != 0:
                nh = _hpush(hk, hi, nh, pred[i], i)
            nwait += 1
            i += 1
        if err == 1:
            break
        # ---------------- one dispatch
        if nrun < k and nwait > 0:
            forced = 0
            if mode == 0:
                while served[fq[fh]] == 1:
                    fh += 1
                j = fq[fh]
                fh += 1
                forced = 1
            elif mode == 1:
                while served[hi[0]] == 1:
                    nh = _hpop(hk, hi, nh)
                j = hi[0]
                nh = _hpop(hk, hi, nh)
            else:
                cand = -1
                while served[fq[fh]] == 1:
                    fh += 1
                hd = fq[fh]
                if Bmax_us > 0 and TC - _fen_pref(F, hd) >= Bmax_us:
                    cand = hd                     # capped budget: over[head] >= Bmax
                else:
                    if C0_us >= 0:            # C0 < 0 switches the work channel off
                        tus = np.int64(round(t * 1000000.0))
                        p1 = _st_leftmost(tre, lz, size, en * tus - ed * TC)
                        if p1 >= 0:
                            cand = p1 + base
                    if use_cnt:
                        p2 = _st_leftmost(tre2, lz2, size, Ncap - TCNT)
                        if p2 >= 0 and (cand < 0 or p2 + base < cand):
                            cand = p2 + base
                if cand >= 0:
                    j = cand
                    forced = 1
                else:
                    while served[hi[0]] == 1:
                        nh = _hpop(hk, hi, nh)
                    j = hi[0]
                    nh = _hpop(hk, hi, nh)
                _st_set(tre, lz, size, j - base, NEG)
                if use_cnt:
                    _st_set(tre2, lz2, size, j - base, NEG)
            served[j] = 1
            n_disp += 1
            qw_total += nwait
            if forced == 1:
                n_forced += 1
                qw_forced += nwait
            nwait -= 1
            nstarted += 1
            wait[j] = t - a[j]
            rt[nrun] = t + s[j]
            rj[nrun] = j
            c = nrun
            nrun += 1
            while c > 0:
                p = (c - 1) >> 1
                if rt[p] > rt[c]:
                    rt[p], rt[c] = rt[c], rt[p]
                    rj[p], rj[c] = rj[c], rj[p]
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
    return wait, cbud, n_disp, n_forced, qw_total, qw_forced, n_rebuild, max_span, err


# --------------------------------------------------------------------------- #
# python wrapper
# --------------------------------------------------------------------------- #
class Res:
    __slots__ = ("w", "cbud", "n_disp", "n_forced", "qw_total", "qw_forced",
                 "n_rebuild", "max_span", "err", "name", "k", "eps", "extra")

    def forced_frac(self):
        return self.n_forced / max(self.n_disp, 1)

    def qw_forced_frac(self):
        return self.qw_forced / max(self.qw_total, 1)


def _gcd(x, y):
    while y:
        x, y = y, x % y
    return x


def ratio(eps, den=720720):
    """eps as an exact fraction en/ed (den carries 2..12 and 16 as factors)."""
    if eps == 0.0:
        return 0, 1
    en = int(round(eps * den))
    g = _gcd(en, den)
    return en // g, den // g


def run(a, s, k, policy="fcfs", pred=None, B=0.0, eps=0.0, gam=0.0, theta=0.0,
        Ncap=0, Bmax=0.0, Mslots=1 << 22, name=""):
    """policy 'fcfs' | 'pri' | 'guard'.  B, gam, theta, Bmax in seconds; eps unitless.
    Bmax = 0 means no cap on the budget."""
    mode = {"fcfs": 0, "pri": 1, "guard": 2}[policy]
    if pred is None:
        pred = np.zeros(len(a), np.float64)
    en, ed = ratio(eps)
    r = Res()
    (r.w, r.cbud, r.n_disp, r.n_forced, r.qw_total, r.qw_forced, r.n_rebuild,
     r.max_span, r.err) = simulate(np.ascontiguousarray(a, np.float64),
                            np.ascontiguousarray(s, np.float64),
                            np.ascontiguousarray(pred, np.float64), int(k), mode,
                            int(round(B * 1e6)), int(round(gam * 1e6)), int(en), int(ed),
                            int(round(theta * 1e6)), int(Ncap), int(round(Bmax * 1e6)),
                            int(Mslots))
    r.name, r.k, r.eps, r.extra = name, int(k), float(eps), float(Ncap) * float(theta)
    return r


def guaranteed(wf, k, cbud_s, eps=0.0, extra=0.0, L=L_CAP, Bmax=0.0):
    """The per-job upper bound on W_guard, elementwise: Theorem B
       (k - eps) W_guard <= k W_fcfs + C + extra + (3k-2) L,
    and, when the budget is capped at Bmax, also Theorem A with B = Bmax.  The bound is
    the smaller of the two."""
    ub = (k * wf + cbud_s + extra + (3 * k - 2) * L) / (k - eps)
    if Bmax > 0:
        ub = np.minimum(ub, wf + (Bmax + extra + (3 * k - 2) * L) / k)
    return ub
