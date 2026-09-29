"""Independent k-server non-preemptive work-conserving simulator.

Written from the model spec in evidence/guard_theory/theory.md section 1 only.
Nothing is imported from prechecks/guard_optimality/ or from the project's
guardkern.py; the point of this file is to be a second, disagreeing witness.

Conventions implemented (theory.md 1.1):
  * jobs are given already in rank order: rank = (a_j, input index), so index
    order IS rank order and j < i means "j has smaller rank".
  * at each instant: completions first, then arrivals, then dispatches one at a
    time while a server is free and the queue is non-empty.
  * W[i] = s_i - a_i.
  * In_i  = sum x_j over j with rank > i dispatched strictly before i.
  * Out_i = sum x_j over j with rank < i dispatched strictly after i.
  * R^Q_i = remaining work at a_i, AFTER the arrivals at a_i, of jobs of rank < i.
  * rho^Q_i = remaining work at s_i of jobs dispatched strictly before i that
    are still in service at s_i (a job finishing exactly at s_i is done, because
    completions are processed first).
  * U_Q(t) = unfinished work at t over jobs with a_j <= t.
  * Gamma_Q(t) = k*(t - t_0) - (work executed by Q on [t_0, t]).

Sizes are non-negative integers (zero allowed); arrivals non-negative integers.
"""

# ------------------------------------------------------------- quantities ---

def executed(k, a, x, s, t):
    """Work executed on [t_0, t]."""
    tot = 0
    for j in range(len(a)):
        if s[j] is not None and s[j] < t:
            tot += min(x[j], t - s[j])
    return tot


def gamma(k, a, x, s, t):
    return k * (t - a[0]) - executed(k, a, x, s, t)


def unfinished(a, x, s, t):
    tot = 0
    for j in range(len(a)):
        if a[j] <= t:
            if s[j] is None or s[j] >= t:
                tot += x[j]
            else:
                tot += max(0, x[j] - (t - s[j]))
    return tot


def run_full(k, a, x, chooser):
    """Run and return a dict of every derived quantity."""
    n = len(a)
    s = [None] * n
    done_at = [None] * n
    seq = []
    waiting = []
    busy = []
    nxt = 0
    t = a[0]
    ctx = {'k': k, 'a': a, 'x': x, 'start': s, 'done_at': done_at, 'seq': seq}
    it = 0
    while len(seq) < n:
        it += 1
        if it > 50 * n + 1000:
            raise RuntimeError('event loop did not terminate')
        busy = [(f, j) for (f, j) in busy if f > t]
        while nxt < n and a[nxt] <= t:
            waiting.append(nxt)
            nxt += 1
        progressed = True
        while progressed:
            progressed = False
            while len(busy) < k and waiting:
                ctx['t'] = t
                idx = chooser(waiting, t, ctx)
                j = waiting.pop(idx)
                s[j] = t
                done_at[j] = t + x[j]
                seq.append(j)
                busy.append((t + x[j], j))
                progressed = True
            before = len(busy)
            busy = [(f, jj) for (f, jj) in busy if f > t]
            if len(busy) != before:
                progressed = True
        if len(seq) == n:
            break
        cands = []
        if busy:
            cands.append(min(f for (f, _) in busy))
        if nxt < n:
            cands.append(a[nxt])
        t = min(cands)

    pos = [0] * n
    for p, j in enumerate(seq):
        pos[j] = p
    W = [s[j] - a[j] for j in range(n)]
    In = [0] * n
    Out = [0] * n
    for i in range(n):
        for j in range(n):
            if j > i and pos[j] < pos[i]:
                In[i] += x[j]
            if j < i and pos[j] > pos[i]:
                Out[i] += x[j]
    R = [0] * n
    for i in range(n):
        tot = 0
        for j in range(i):
            if s[j] < a[i]:
                tot += max(0, x[j] - (a[i] - s[j]))
            else:
                tot += x[j]
        R[i] = tot
    rho = [0] * n
    for i in range(n):
        tot = 0
        for j in range(n):
            if pos[j] < pos[i] and s[j] + x[j] > s[i]:
                tot += x[j] - (s[i] - s[j])
        rho[i] = tot
    return {'s': s, 'seq': seq, 'pos': pos, 'W': W, 'In': In, 'Out': Out,
            'R': R, 'rho': rho, 'a': a, 'x': x, 'k': k}


# ---------------------------------------------------------------- choosers ---

def fcfs(waiting, t, ctx):
    return 0                                   # waiting is in rank order


def sjf(waiting, t, ctx):
    x = ctx['x']
    best = 0
    for idx in range(1, len(waiting)):
        if x[waiting[idx]] < x[waiting[best]]:
            best = idx
    return best                                # ties -> lowest rank


def sjf_advtie(waiting, t, ctx):
    x = ctx['x']
    best = 0
    for idx in range(1, len(waiting)):
        if x[waiting[idx]] <= x[waiting[best]]:
            best = idx
    return best                                # ties -> highest rank


def ljf(waiting, t, ctx):
    x = ctx['x']
    best = 0
    for idx in range(1, len(waiting)):
        if x[waiting[idx]] > x[waiting[best]]:
            best = idx
    return best


def lifo(waiting, t, ctx):
    return len(waiting) - 1


def make_random(rng):
    def f(waiting, t, ctx):
        return rng.randrange(len(waiting))
    return f


def make_nonrank(seed):
    """A deliberately non-rank-based, non-size-monotone rule: order by a hash of
    (job id, size, arrival). Depends on no monotone statistic."""
    def f(waiting, t, ctx):
        x, a = ctx['x'], ctx['a']
        best, bk = 0, None
        for idx, j in enumerate(waiting):
            key = ((j * 2654435761 + x[j] * 40503 + a[j] * 97 + seed)
                   % 1000003)
            if bk is None or key < bk:
                bk, best = key, idx
        return best
    return f


def make_score(score):
    """Rank by an arbitrary per-job score vector (a 'prediction')."""
    def f(waiting, t, ctx):
        best = 0
        for idx in range(1, len(waiting)):
            if score[waiting[idx]] < score[waiting[best]]:
                best = idx
        return best
    return f


# ------------------------------------------------------------------- guard ---

def make_guard(base, budget_fn):
    """Algorithm 1.  budget_fn(q, t, ctx) -> budget for waiting job q at t.

    over[q](t) = total size of jobs of rank > q completed by t.
    E(t) = {q waiting : over[q](t) >= budget(q,t)}; fire on min-rank member.
    """
    def f(waiting, t, ctx):
        x, done_at = ctx['x'], ctx['done_at']
        n = len(x)
        fired = None
        for idx, q in enumerate(waiting):
            ov = 0
            for j in range(q + 1, n):
                if done_at[j] is not None and done_at[j] <= t:
                    ov += x[j]
            if ov >= budget_fn(q, t, ctx):
                fired = idx
                break                          # waiting is in rank order
        if fired is not None:
            return fired
        return base(waiting, t, ctx)
    return f


def const_budget(B):
    return lambda q, t, ctx: B


# --------------------------------------------------------- instance helpers ---

def sort_by_rank(a, x):
    idx = sorted(range(len(a)), key=lambda j: (a[j], j))
    return [a[j] for j in idx], [x[j] for j in idx]


def enumerate_schedules(k, a, x, cap=None):
    """Yield the start-time vector of EVERY work-conserving non-preemptive
    schedule: branch over every waiting job at every dispatch epoch.

    This covers non-rank-based and size-blind choices alike; it excludes only
    schedules that idle a server while a job waits, which the model forbids.
    """
    n = len(a)
    out = []

    def rec(t, busy, waiting, nxt, s, seq):
        if cap is not None and len(out) >= cap:
            return
        busy2 = [(f, j) for (f, j) in busy if f > t]
        waiting2 = list(waiting)
        nxt2 = nxt
        while nxt2 < n and a[nxt2] <= t:
            waiting2.append(nxt2)
            nxt2 += 1
        if len(busy2) < k and waiting2:
            for idx in range(len(waiting2)):
                j = waiting2[idx]
                s2 = list(s)
                s2[j] = t
                rec(t, busy2 + [(t + x[j], j)],
                    waiting2[:idx] + waiting2[idx + 1:], nxt2, s2, seq + [j])
            return
        if len(seq) == n:
            out.append((s, seq))
            return
        cands = []
        if busy2:
            cands.append(min(f for (f, _) in busy2))
        if nxt2 < n:
            cands.append(a[nxt2])
        if not cands:
            return
        rec(min(cands), busy2, waiting2, nxt2, s, seq)

    rec(a[0], [], [], 0, [None] * n, [])
    return out


def enumerate_constrained(k, a, x, allowed, cap=None):
    """Every work-conserving schedule whose every dispatch is `allowed`.

    allowed(j, waiting, over, t) -> bool, where `waiting` is the rank-ordered
    list of waiting jobs at the epoch and `over[q]` the completed higher-ranked
    work.  With allowed == (lambda *_: True) this is enumerate_schedules.
    """
    n = len(a)
    out = []

    def overs(waiting, s, t):
        ov = {}
        for q in waiting:
            tot = 0
            for j in range(q + 1, n):
                if s[j] is not None and s[j] + x[j] <= t:
                    tot += x[j]
            ov[q] = tot
        return ov

    def rec(t, busy, waiting, nxt, s, seq):
        if cap is not None and len(out) >= cap:
            return
        busy2 = [(f, j) for (f, j) in busy if f > t]
        waiting2 = list(waiting)
        nxt2 = nxt
        while nxt2 < n and a[nxt2] <= t:
            waiting2.append(nxt2)
            nxt2 += 1
        if len(busy2) < k and waiting2:
            ov = overs(waiting2, s, t)
            for idx in range(len(waiting2)):
                j = waiting2[idx]
                if not allowed(j, waiting2, ov, t):
                    continue
                s2 = list(s)
                s2[j] = t
                rec(t, busy2 + [(t + x[j], j)],
                    waiting2[:idx] + waiting2[idx + 1:], nxt2, s2, seq + [j])
            return
        if len(seq) == n:
            out.append((s, seq))
            return
        cands = []
        if busy2:
            cands.append(min(f for (f, _) in busy2))
        if nxt2 < n:
            cands.append(a[nxt2])
        if not cands:
            return
        rec(min(cands), busy2, waiting2, nxt2, s, seq)

    rec(a[0], [], [], 0, [None] * n, [])
    return out


def guard_allowed(B):
    """Dispatches Algorithm 1 at constant budget B can make, over ALL bases."""
    def allowed(j, waiting, over, t):
        E = [q for q in waiting if over[q] >= B]
        return j == min(E) if E else True
    return allowed


def defer_allowed(thr):
    """The necessary condition the T1(b') lemma puts on any size-oblivious
    wrapper with promise G:  a job j may pass a waiting lower-ranked i only
    while over[i](t) <= thr = G - L."""
    def allowed(j, waiting, over, t):
        return all(over[i] <= thr for i in waiting if i < j)
    return allowed


def derive(k, a, x, s, seq):
    """Derived quantities for an externally supplied schedule."""
    n = len(a)
    pos = [0] * n
    for p, j in enumerate(seq):
        pos[j] = p
    W = [s[j] - a[j] for j in range(n)]
    In = [0] * n
    Out = [0] * n
    for i in range(n):
        for j in range(n):
            if j > i and pos[j] < pos[i]:
                In[i] += x[j]
            if j < i and pos[j] > pos[i]:
                Out[i] += x[j]
    R = [0] * n
    for i in range(n):
        tot = 0
        for j in range(i):
            tot += (max(0, x[j] - (a[i] - s[j])) if s[j] < a[i] else x[j])
        R[i] = tot
    rho = [0] * n
    for i in range(n):
        tot = 0
        for j in range(n):
            if pos[j] < pos[i] and s[j] + x[j] > s[i]:
                tot += x[j] - (s[i] - s[j])
        rho[i] = tot
    return {'s': s, 'seq': seq, 'pos': pos, 'W': W, 'In': In, 'Out': Out,
            'R': R, 'rho': rho, 'a': a, 'x': x, 'k': k}
