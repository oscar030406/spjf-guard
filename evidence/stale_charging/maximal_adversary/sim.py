"""Deterministic event simulator for one adversary strategy.

prio[j]: static base priority (smaller = preferred).
dl[j]  : delay of j's charge (int >= 0) or None = lost (rbp only).
budget : 'const' (Algorithm 1 with constant B) or 'max' (maximal adversary:
         any job of rank <= min forced rank, chosen by prio).
mode   : 'shared', 'rbp', 'pserv'.
"""
import heapq


def run(arr, C, k, B, dl, prio, mode='shared', budget='const'):
    n = len(arr)
    order = sorted(range(n), key=lambda j: (arr[j], j))
    assert order == list(range(n)), 'jobs must be in rank order'
    start = [None] * n
    In = [0] * n
    server_of = [None] * n
    views = [[0] * n for _ in range(k)] if mode == 'pserv' else None
    over = [0] * n
    waiting = []
    running = {}  # server -> (finish, job)
    own = [None] * k  # rbp: unapplied own report per server
    applied = [False] * n
    charges = []  # heap of (time, job, target) ; target -1 shared
    times = set(arr)
    nxt = 0
    seq = 0

    def charge(c, target):
        if mode == 'rbp':
            if applied[c]:
                return
            applied[c] = True
        vec = over if target < 0 else views[target]
        for q in waiting:
            if q < c:
                vec[q] += C[c]

    t_heap = sorted(times)
    heapq.heapify(t_heap)
    seen_t = set(t_heap)

    def push_t(x):
        if x not in seen_t:
            seen_t.add(x); heapq.heappush(t_heap, x)

    while t_heap:
        t = heapq.heappop(t_heap)
        # completions
        for s in list(running):
            f, c = running[s]
            if f == t:
                del running[s]
                if mode == 'shared':
                    heapq.heappush(charges, (t + dl[c], c, -1)); push_t(t + dl[c])
                elif mode == 'pserv':
                    charge(c, s)
                    for s2 in range(k):
                        if s2 != s:
                            heapq.heappush(charges, (t + dl[c], c, s2)); push_t(t + dl[c])
                else:
                    own[s] = c
                    if dl[c] is not None:
                        heapq.heappush(charges, (t + dl[c], c, -1)); push_t(t + dl[c])
        while charges and charges[0][0] <= t:
            _, c, tg = heapq.heappop(charges)
            charge(c, tg)
        while nxt < n and arr[nxt] == t:
            waiting.append(nxt); nxt += 1
        while waiting and len(running) < k:
            free = [s for s in range(k) if s not in running]
            if mode == 'rbp':
                # adversary: prefer a server with no pending own report
                free.sort(key=lambda s: (own[s] is not None and not applied[own[s]], s))
                s = free[0]
                if own[s] is not None:
                    charge(own[s], -1); own[s] = None
                vec = over
            elif mode == 'pserv':
                def rs(s):
                    for q in waiting:
                        if views[s][q] >= B:
                            return q
                    return n
                s = max(free, key=lambda s: (rs(s), -s))
                vec = views[s]
            else:
                s = free[0]; vec = over
            fired = [q for q in waiting if vec[q] >= B]
            if budget == 'const':
                j = fired[0] if fired else min(waiting, key=lambda q: (prio[q], q))
            else:
                r = fired[0] if fired else n
                j = min((q for q in waiting if q <= r), key=lambda q: (prio[q], q))
            start[j] = t; server_of[j] = s
            for q in waiting:
                if q < j:
                    In[q] += C[j]
            waiting.remove(j)
            running[s] = (t + C[j], j)
            push_t(t + C[j])
        if nxt == n and not waiting:
            break
    return start, In


def fcfs(arr, C, k):
    return run(arr, C, k, 0, [0] * len(arr), list(range(len(arr))), 'shared', 'const')[0]


def evaluate(arr, C, k, L, B, d, dl, prio, mode='shared', budget='const'):
    st, In = run(arr, C, k, B, dl, prio, mode, budget)
    sf = fcfs(arr, C, k)
    from core import bounds
    kWb, Inb = bounds(mode, k, L, B, d)
    best = (-1, -1, None, None)
    exc = [st[j] - sf[j] for j in range(len(arr))]
    r1 = max(k * e / kWb for e in exc)
    r2 = max((In[j] / Inb for j in range(len(arr)) if In[j] > 0), default=0)
    j1 = max(range(len(arr)), key=lambda j: exc[j])
    return r1, r2, j1, exc[j1], In[j1]
