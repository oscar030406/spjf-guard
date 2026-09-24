"""Independent model of Algorithm 1 under late completion charges.

Time is an integer grid (inputs are pre-scaled so that delta is an integer).
Jobs are indexed in rank order. The adversary (base policy + budget rule) is
maximal: at a dispatch it may take any waiting job whose rank is <= the
minimum rank of a waiting job whose visible over[] has reached B_max
(such a job is forced into the fired set, since budget <= B_max; any other job
can be fired with budget 0 or kept out with budget B_max).

Modes
  shared : one shared counter; charge of c arrives at f_c + d_c, d_c in [0, delta],
           adversary picks d_c (delivery may happen before any dispatch, also mid-phase).
  rbp    : report-before-pull: a server applies its own last report when it next
           pulls; the network may deliver any report at any time or never.
  pserv  : per-server views; own completions seen at once, others' within delta.
"""
from functools import lru_cache
from itertools import combinations

NEG = -10**9


def fcfs(arr, C, k):
    n = len(arr)
    run = []
    start = [None] * n
    waiting = []
    nxt = 0
    t = arr[0]
    while True:
        run = [f for f in run if f > t]
        while nxt < n and arr[nxt] <= t:
            waiting.append(nxt); nxt += 1
        while len(run) < k and waiting:
            j = waiting.pop(0); start[j] = t; run.append(t + C[j])
        if nxt == n and not waiting:
            return start
        cand = list(run) + ([arr[nxt]] if nxt < n else [])
        t = min(cand)


def subsets(xs):
    for r in range(len(xs) + 1):
        for s in combinations(xs, r):
            yield s


def bounds(mode, k, L, B, d):
    """Return (kW_bound, In_bound) as integers: violation if k*excess >= kW_bound or In >= In_bound."""
    if mode == 'shared':
        return B + (4 * k - 2) * L + k * d, B + k * L + k * (L + d)
    if mode == 'rbp':
        return B + (3 * k - 2) * L, B + k * L
    if mode == 'pserv':
        return B + (3 * k - 2) * L + (k - 1) * (L + d), B + k * L + (k - 1) * (L + d)
    raise ValueError(mode)


def explore(arr, C, k, L, B, d, mode, bmode=None):
    """Exhaustive search over every adversary choice. Returns
    (max k*excess - kWbound, max In - Inbound, max excess ratio, max In ratio, leaves)."""
    n = len(arr)
    WF = [s - a for s, a in zip(fcfs(arr, C, k), arr)]
    kWb, Inb = bounds(bmode or mode, k, L, B, d)

    def score(j, W, In):
        m1 = k * (W - WF[j]) - kWb
        r1 = k * (W - WF[j]) / kWb
        if In > 0:
            return (m1, In - Inb, r1, In / Inb)
        return (m1, NEG, r1, 0.0)

    def comb(a, b):
        return (max(a[0], b[0]), max(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))

    LEAF = (NEG, NEG, -1.0, -1.0)

    # ---------------- shared counter ----------------
    if mode == 'shared':
        @lru_cache(maxsize=None)
        def phase(t, running, waiting, nxt, over, pending, inp):
            # over, inp: tuples aligned with waiting
            free = k - len(running)
            if free > 0 and waiting:
                best = LEAF
                cnt = 0
                wl = list(waiting)
                rel = [p for p in pending if any(q < p[1] for q in wl)]
                for S in subsets(rel):
                    ov = list(over)
                    for (f, c) in S:
                        for x, q in enumerate(wl):
                            if q < c:
                                ov[x] += C[c]
                    pend = tuple(p for p in rel if p not in S)
                    rstar = n
                    for x, q in enumerate(wl):
                        if ov[x] >= B:
                            rstar = q
                            break
                    for y, j in enumerate(wl):
                        if j > rstar:
                            break
                        sc = score(j, t - arr[j], inp[y])
                        nw = wl[:y] + wl[y + 1:]
                        nov = tuple(ov[:y] + ov[y + 1:])
                        ninp = tuple((inp[x] + C[j]) if wl[x] < j else inp[x]
                                     for x in range(len(wl)) if x != y)
                        nrun = tuple(sorted(running + ((t + C[j], j),)))
                        v, c2 = phase(t, nrun, tuple(nw), nxt, nov, pend, ninp)
                        best = comb(best, comb(v, sc))
                        cnt += c2
                return best, cnt
            if not waiting and nxt == n:
                return LEAF, 1
            cand = [r[0] for r in running]
            if nxt < n:
                cand.append(arr[nxt])
            t2 = min(cand)
            done = [r for r in running if r[0] == t2]
            nrun = tuple(r for r in running if r[0] != t2)
            wl = list(waiting)
            ov = list(over)
            pend = list(pending) + [(t2, c) for (_, c) in done]
            keep = []
            for (f, c) in pend:
                if f + d <= t2:
                    for x, q in enumerate(wl):
                        if q < c:
                            ov[x] += C[c]
                else:
                    keep.append((f, c))
            inp = list(inp)
            while nxt < n and arr[nxt] == t2:
                wl.append(nxt); ov.append(0); inp.append(0); nxt += 1
            keep = tuple(p for p in keep if any(q < p[1] for q in wl))
            return phase(t2, nrun, tuple(wl), nxt, tuple(ov), tuple(sorted(keep)), tuple(inp))

        res = phase(-1, (), (), 0, (), (), ())
        phase.cache_clear()
        return res[0] + (res[1],)

    # ---------------- report before pull ----------------
    if mode == 'rbp':
        # running: tuple of (finish, job, server); own: tuple per server of pending own job or -1
        # pending: set of jobs whose report is unapplied (network may deliver any time or never)
        @lru_cache(maxsize=None)
        def phase(t, running, waiting, nxt, over, pending, own, inp):
            busy = {r[2] for r in running}
            freeS = [s for s in range(k) if s not in busy]
            if freeS and waiting:
                best = LEAF
                cnt = 0
                wl = list(waiting)
                rel = [c for c in pending if any(q < c for q in wl)]
                # choose pulling server: each free server with own pending report, plus one clean one
                choices = []
                seen_clean = False
                for s in freeS:
                    if own[s] in rel:
                        choices.append(s)
                    elif not seen_clean:
                        choices.append(s); seen_clean = True
                for s in choices:
                  for S in subsets([c for c in rel if c != own[s]]):
                        applied = set(S)
                        if own[s] in rel:
                            applied.add(own[s])
                        ov = list(over)
                        for c in applied:
                            for x, q in enumerate(wl):
                                if q < c:
                                    ov[x] += C[c]
                        pend = tuple(c for c in rel if c not in applied)
                        nown = list(own)
                        for s2 in range(k):
                            if nown[s2] not in pend:
                                nown[s2] = -1
                        rstar = n
                        for x, q in enumerate(wl):
                            if ov[x] >= B:
                                rstar = q
                                break
                        for y, j in enumerate(wl):
                            if j > rstar:
                                break
                            sc = score(j, t - arr[j], inp[y])
                            nw = wl[:y] + wl[y + 1:]
                            nov = tuple(ov[:y] + ov[y + 1:])
                            ninp = tuple((inp[x] + C[j]) if wl[x] < j else inp[x]
                                         for x in range(len(wl)) if x != y)
                            nrun = tuple(sorted(running + ((t + C[j], j, s),)))
                            v, c2 = phase(t, nrun, tuple(nw), nxt, nov, pend, tuple(nown), ninp)
                            best = comb(best, comb(v, sc))
                            cnt += c2
                return best, cnt
            if not waiting and nxt == n:
                return LEAF, 1
            cand = [r[0] for r in running]
            if nxt < n:
                cand.append(arr[nxt])
            t2 = min(cand)
            done = [r for r in running if r[0] == t2]
            nrun = tuple(r for r in running if r[0] != t2)
            wl = list(waiting); ov = list(over); inp = list(inp)
            pend = set(pending)
            nown = list(own)
            for (_, c, s) in done:
                pend.add(c)
                nown[s] = c
            while nxt < n and arr[nxt] == t2:
                wl.append(nxt); ov.append(0); inp.append(0); nxt += 1
            pend = tuple(sorted(c for c in pend if any(q < c for q in wl)))
            nown = tuple(x if x in pend else -1 for x in nown)
            return phase(t2, nrun, tuple(wl), nxt, tuple(ov), pend, nown, tuple(inp))

        res = phase(-1, (), (), 0, (), (), tuple([-1] * k), ())
        phase.cache_clear()
        return res[0] + (res[1],)

    # ---------------- per-server views ----------------
    if mode == 'pserv':
        # over: tuple per server of tuple aligned with waiting
        # pending: tuple of (f, c, target_server)
        @lru_cache(maxsize=None)
        def phase(t, running, waiting, nxt, over, pending, inp):
            busy = {r[2] for r in running}
            freeS = [s for s in range(k) if s not in busy]
            if freeS and waiting:
                best = LEAF
                cnt = 0
                wl = list(waiting)
                seenv = set()
                for s in freeS:
                    rel = [p for p in pending if p[2] == s and any(q < p[1] for q in wl)]
                    sig = (over[s], tuple((p[0], p[1]) for p in rel))
                    if sig in seenv:
                        continue
                    seenv.add(sig)
                    for S in subsets(rel):
                        ovs = [list(o) for o in over]
                        for (f, c, _) in S:
                            for x, q in enumerate(wl):
                                if q < c:
                                    ovs[s][x] += C[c]
                        pend = tuple(p for p in pending if p not in S)
                        rstar = n
                        for x, q in enumerate(wl):
                            if ovs[s][x] >= B:
                                rstar = q
                                break
                        for y, j in enumerate(wl):
                            if j > rstar:
                                break
                            sc = score(j, t - arr[j], inp[y])
                            nw = tuple(wl[:y] + wl[y + 1:])
                            nov = tuple(tuple(o[:y] + o[y + 1:]) for o in ovs)
                            ninp = tuple((inp[x] + C[j]) if wl[x] < j else inp[x]
                                         for x in range(len(wl)) if x != y)
                            nrun = tuple(sorted(running + ((t + C[j], j, s),)))
                            npend = tuple(p for p in pend if any(q < p[1] for q in nw))
                            v, c2 = phase(t, nrun, nw, nxt, nov, npend, ninp)
                            best = comb(best, comb(v, sc))
                            cnt += c2
                return best, cnt
            if not waiting and nxt == n:
                return LEAF, 1
            cand = [r[0] for r in running]
            if nxt < n:
                cand.append(arr[nxt])
            t2 = min(cand)
            done = [r for r in running if r[0] == t2]
            nrun = tuple(r for r in running if r[0] != t2)
            wl = list(waiting); inp = list(inp)
            ovs = [list(o) for o in over]
            pend = list(pending)
            for (_, c, s) in done:
                for x, q in enumerate(wl):  # own view at once
                    if q < c:
                        ovs[s][x] += C[c]
                for s2 in range(k):
                    if s2 != s:
                        pend.append((t2, c, s2))
            keep = []
            for (f, c, s2) in pend:
                if f + d <= t2:
                    for x, q in enumerate(wl):
                        if q < c:
                            ovs[s2][x] += C[c]
                else:
                    keep.append((f, c, s2))
            while nxt < n and arr[nxt] == t2:
                wl.append(nxt); inp.append(0); nxt += 1
                for o in ovs:
                    o.append(0)
            keep = tuple(sorted(p for p in keep if any(q < p[1] for q in wl)))
            return phase(t2, nrun, tuple(wl), nxt, tuple(tuple(o) for o in ovs), keep, tuple(inp))

        res = phase(-1, (), (), 0, tuple(() for _ in range(k)), (), ())
        phase.cache_clear()
        return res[0] + (res[1],)
