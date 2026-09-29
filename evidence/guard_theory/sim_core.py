"""Independent exact-integer k-server non-preemptive work-conserving simulator.

Written from scratch for the theory checks; it shares no code with guardkern.py.
All times and service times are Python ints, so every reported slack is exact.

Conventions
-----------
jobs        list of (a, x) sorted by rank; rank i = position in the list, so
            rank order == (arrival, input index).  x >= 0 (0 allowed on purpose).
speeds      list of k ints (default all 1).  A job of work x on server m occupies
            it for x * LCM/v_m time units -- to stay in integers we instead scale:
            see simulate_speed().
dispatch    a global sequence number; In/Out are defined against that order, which
            is a legal total order for simultaneous dispatches.
"""
import sys
sys.dont_write_bytecode = True


def simulate(jobs, k, chooser, state=None):
    """Return (start, order, done).

    chooser(t, waiting, state) -> position inside `waiting` (a list of ranks,
    kept in increasing-rank order).  `state` is handed through untouched and may
    carry policy memory; the simulator also writes bookkeeping into it.
    """
    n = len(jobs)
    if n == 0:
        return [], [], []
    a = [j[0] for j in jobs]
    x = [j[1] for j in jobs]
    free = [a[0]] * k
    start = [None] * n
    done = [None] * n
    order = []
    waiting = []
    nxt = 0
    t = a[0]
    if state is None:
        state = {}
    state['x'] = x
    state['a'] = a
    state['done'] = done
    state['n'] = n
    while len(order) < n:
        while nxt < n and a[nxt] <= t:
            waiting.append(nxt)
            nxt += 1
        while waiting:
            si = -1
            for m in range(k):
                if free[m] <= t:
                    si = m
                    break
            if si < 0:
                break
            state['t'] = t
            c = chooser(t, waiting, state)
            j = waiting.pop(c)
            start[j] = t
            done[j] = t + x[j]
            free[si] = t + x[j]
            order.append(j)
        if len(order) == n:
            break
        cand = []
        if nxt < n:
            cand.append(a[nxt])
        for m in range(k):
            if free[m] > t:
                cand.append(free[m])
        if not cand:
            raise RuntimeError("stuck")
        t = min(cand)
    return start, order, done


def in_out(jobs, order):
    """In_i / Out_i against the dispatch order."""
    n = len(jobs)
    x = [j[1] for j in jobs]
    pos = [0] * n
    for p, j in enumerate(order):
        pos[j] = p
    In = [0] * n
    Out = [0] * n
    for i in range(n):
        pi = pos[i]
        s = 0
        for j in range(i + 1, n):
            if pos[j] < pi:
                s += x[j]
        In[i] = s
        s = 0
        for j in range(0, i):
            if pos[j] > pi:
                s += x[j]
        Out[i] = s
    return In, Out


# ---------------------------------------------------------------- choosers ---
def fcfs(t, waiting, state):
    return 0                      # waiting is kept in increasing rank order


def lifo(t, waiting, state):
    return len(waiting) - 1


def sjf_true(t, waiting, state):
    x = state['x']
    best = 0
    for c in range(1, len(waiting)):
        if x[waiting[c]] < x[waiting[best]]:
            best = c
    return best


def ljf_true(t, waiting, state):
    x = state['x']
    best = 0
    for c in range(1, len(waiting)):
        if x[waiting[c]] > x[waiting[best]]:
            best = c
    return best


def by_pred(t, waiting, state):
    p = state['pred']
    best = 0
    for c in range(1, len(waiting)):
        if p[waiting[c]] < p[waiting[best]]:
            best = c
    return best


def make_random(rng):
    def f(t, waiting, state):
        return int(rng.integers(len(waiting)))
    return f


# ------------------------------------------------------------------- guard ---
def make_guard(base, B, Ncap=None, k=None):
    """over[q] = true service of higher-rank jobs completed while q waited.
    Fired set E = {q : over[q] >= B}.  Serve min-rank member of E, else base.
    Ncap (optional) counts overtakers instead of their work (finite-skip rule).
    """
    def f(t, waiting, state):
        x = state['x']
        done = state['done']
        n = state['n']
        for c, q in enumerate(waiting):      # waiting is in increasing rank order
            ov = 0
            cnt = 0
            for j in range(q + 1, n):
                dj = done[j]
                if dj is not None and dj <= t:
                    ov += x[j]
                    cnt += 1
            if B is not None and ov >= B:
                return c
            if Ncap is not None and cnt >= Ncap:
                return c
        return base(t, waiting, state)
    return f


def run(jobs, k, chooser, state=None):
    start, order, done = simulate(jobs, k, chooser, state)
    In, Out = in_out(jobs, order)
    a = [j[0] for j in jobs]
    W = [start[i] - a[i] for i in range(len(jobs))]
    return W, In, Out, order, start


def fcfs_wait(jobs, k):
    start, order, done = simulate(jobs, k, fcfs)
    a = [j[0] for j in jobs]
    return [start[i] - a[i] for i in range(len(jobs))]


def all_schedules(jobs, k, cap=200000):
    """Every non-preemptive work-conserving schedule, as a dispatch order list.

    Enumerates the branching of the event loop: at every instant where a server
    is free and jobs wait, branch over every waiting job.
    """
    n = len(jobs)
    a = [j[0] for j in jobs]
    x = [j[1] for j in jobs]
    out = []

    def rec(t, free, nxt, waiting, order, start):
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
            for c in range(len(waiting)):
                j = waiting[c]
                nf = list(free)
                nf[si] = t + x[j]
                ns = list(start)
                ns[j] = t
                rec(t, tuple(nf), nxt, waiting[:c] + waiting[c + 1:],
                    order + (j,), tuple(ns))
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
        rec(min(cand), free, nxt, waiting, order, start)

    rec(a[0], tuple([a[0]] * k), 0, (), (), tuple([None] * n))
    return out


# ------------------------------------------------- heterogeneous speeds ------
def simulate_speeds(jobs, speeds, chooser, P, state=None, server_pick=0):
    """Times are in SCALED units (1 real second = P scaled units); a job of work
    x on a server of speed v occupies it for x*P//v scaled units, an integer
    because v divides P.  Work conserving: no server idles while a job waits.
    """
    n = len(jobs); k = len(speeds)
    if n == 0: return [], [], []
    a = [j[0] for j in jobs]; x = [j[1] for j in jobs]
    free = [a[0]] * k
    start = [None]*n; done = [None]*n; srv = [None]*n
    order = []; waiting = []; nxt = 0; t = a[0]
    if state is None: state = {}
    state['x'] = x; state['a'] = a; state['done'] = done; state['n'] = n
    while len(order) < n:
        while nxt < n and a[nxt] <= t:
            waiting.append(nxt); nxt += 1
        while waiting:
            cand = [m for m in range(k) if free[m] <= t]
            if not cand: break
            si = cand[0] if server_pick == 0 else cand[-1]
            state['t'] = t
            c = chooser(t, waiting, state)
            j = waiting.pop(c)
            d = x[j]*P//speeds[si]
            start[j] = t; done[j] = t+d; free[si] = t+d; srv[j] = si
            order.append(j)
        if len(order) == n: break
        cd = []
        if nxt < n: cd.append(a[nxt])
        for m in range(k):
            if free[m] > t: cd.append(free[m])
        if not cd: raise RuntimeError("stuck")
        t = min(cd)
    return start, order, done


# ------------------------------------------------------ pauses / vacations ---
def simulate_pauses(jobs, k, chooser, pauses, state=None):
    """pauses: list of (server, t_from, t_to) forced unavailability windows.
    A server cannot start a job inside its pause window, and a job already in
    service is NOT interrupted (non-preemptive).  Returns also the total
    server-idle-while-a-job-waits time accumulated up to each job's start.
    """
    n = len(jobs)
    if n == 0: return [], [], [], []
    a = [j[0] for j in jobs]; x = [j[1] for j in jobs]
    free = [a[0]]*k
    blocked = [[] for _ in range(k)]
    for (m, t0, t1) in pauses: blocked[m].append((t0, t1))
    def avail(m, t):
        if free[m] > t: return False
        for (t0, t1) in blocked[m]:
            if t0 <= t < t1: return False
        return True
    start=[None]*n; done=[None]*n; order=[]; waiting=[]; nxt=0; t=a[0]
    idle_acc = 0                 # server-time idle while >=1 job waits
    idle_at_start = [0]*n
    if state is None: state = {}
    state['x']=x; state['a']=a; state['done']=done; state['n']=n
    guard_iter = 0
    while len(order) < n:
        guard_iter += 1
        if guard_iter > 100000: raise RuntimeError("no progress")
        while nxt < n and a[nxt] <= t:
            waiting.append(nxt); nxt += 1
        while waiting:
            si = -1
            for m in range(k):
                if avail(m, t): si = m; break
            if si < 0: break
            state['t'] = t
            c = chooser(t, waiting, state)
            j = waiting.pop(c)
            start[j]=t; done[j]=t+x[j]; free[si]=t+x[j]; order.append(j)
            idle_at_start[j] = idle_acc
        if len(order) == n: break
        cd = []
        if nxt < n: cd.append(a[nxt])
        for m in range(k):
            if free[m] > t: cd.append(free[m])
            for (t0, t1) in blocked[m]:
                if t0 <= t < t1: cd.append(t1)
                elif t1 > t and t0 > t: cd.append(t0)
        cd = [c for c in cd if c > t]
        if not cd: raise RuntimeError("stuck")
        t2 = min(cd)
        if waiting:
            nidle = sum(1 for m in range(k) if free[m] <= t and not avail(m, t))
            idle_acc += nidle*(t2-t)
        t = t2
    return start, order, done, idle_at_start


# --------------------------------- constant-budget guard, O(log n) per decision
def make_guard_fast(base, B):
    """Same rule as make_guard for a CONSTANT budget.  For constant B the value
    over[q] = TC - F(q) is non-increasing in rank (F is a prefix sum of
    completed work), so the fired set is non-empty iff its minimum-rank member
    is the head of the waiting queue; only the head has to be tested.
    Maintained with a Fenwick tree over ranks and a completion heap.
    """
    import heapq

    def f(t, waiting, state):
        n = state['n']
        x = state['x']
        done = state['done']
        st = state.setdefault('_g', {'fen': [0] * (n + 1), 'TC': 0,
                                     'heap': [], 'seen': [False] * n})
        fen = st['fen']
        # register newly dispatched jobs
        for j in state.get('_newly', ()):
            pass
        # lazily push every dispatched-but-unregistered job
        for j in range(n):
            if done[j] is not None and not st['seen'][j]:
                st['seen'][j] = True
                heapq.heappush(st['heap'], (done[j], j))
        while st['heap'] and st['heap'][0][0] <= t:
            dt, j = heapq.heappop(st['heap'])
            st['TC'] += x[j]
            p = j + 1
            while p <= n:
                fen[p] += x[j]
                p += p & (-p)
        head = waiting[0]
        # F(head) = completed work among ranks <= head
        s = 0
        p = head + 1
        while p > 0:
            s += fen[p]
            p -= p & (-p)
        if st['TC'] - s >= B:
            return 0
        return base(t, waiting, state)
    return f
