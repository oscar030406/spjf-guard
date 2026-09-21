"""Referee-3 simulator.  Written from the DEFINITIONS in theory.md section 1.1,
not from any code in evidence/guard_theory/ or the other referee directories.

Exact arithmetic (python ints / Fractions).  Event order at each instant t:
    (1) completions, (2) arrivals, (3) dispatches one at a time.

Nothing here knows about any theorem; the auditors below re-derive
work-conservation, non-preemption and the bookkeeping from the produced
schedule alone.
"""
from fractions import Fraction


# ----------------------------------------------------------------- simulate
def simulate(a, x, k, chooser, speeds=None):
    """a, x: lists in RANK order (a must be non-decreasing; index breaks ties).
    chooser(t, waiting, ctx) -> job id to dispatch, chosen from `waiting`
        (waiting is a rank-sorted list of job ids).
    ctx is a dict with 'a','x','s','fin','srv','done_work_gt' helper.
    speeds: None (all unit speed) or list of k positive speeds.
    Returns dict of arrays."""
    n = len(a)
    assert len(x) == n
    for i in range(1, n):
        assert a[i - 1] <= a[i], "input must be given in rank order"
    if speeds is None:
        speeds = [1] * k
    s = [None] * n
    fin = [None] * n
    srv = [None] * n
    order = [None] * n
    busy_until = [None] * k          # None == free
    waiting = []
    nxt = 0
    cnt = 0
    t = a[0] if n else 0
    completed = []                   # (fin_time, jid) appended in completion order

    ctx = {'a': a, 'x': x, 's': s, 'fin': fin, 'srv': srv, 'k': k,
           'completed': completed, 'n': n}

    while True:
        # (1) completions
        for m in range(k):
            if busy_until[m] is not None and busy_until[m] <= t:
                busy_until[m] = None
        # (2) arrivals
        while nxt < n and a[nxt] <= t:
            waiting.append(nxt)
            nxt += 1
        waiting.sort()
        ctx['t'] = t
        # (3) dispatches, one at a time
        while waiting:
            free = [m for m in range(k) if busy_until[m] is None]
            if not free:
                break
            jid = chooser(t, list(waiting), ctx)
            assert jid in waiting, "chooser returned a non-waiting job"
            m = free[0]
            waiting.remove(jid)
            s[jid] = t
            dur = Fraction(x[jid], 1) / speeds[m] if speeds[m] != 1 else x[jid]
            fin[jid] = t + dur
            srv[jid] = m
            order[jid] = cnt
            cnt += 1
            if dur == 0:
                completed.append((t, jid))   # frees the server at once
            else:
                busy_until[m] = t + dur
        # advance
        cands = []
        if nxt < n:
            cands.append(a[nxt])
        for m in range(k):
            if busy_until[m] is not None:
                cands.append(busy_until[m])
        if not cands:
            break
        t2 = min(cands)
        # record completions that happen at t2
        for jid in range(n):
            if fin[jid] is not None and fin[jid] == t2 and x[jid] != 0:
                completed.append((t2, jid))
        t = t2
    assert all(o is not None for o in order), "some job never dispatched"
    completed.sort()
    return {'a': a, 'x': x, 'k': k, 's': s, 'fin': fin, 'srv': srv,
            'order': order, 'n': n, 'speeds': speeds}


# ------------------------------------------------------------------ choosers
def fcfs(t, waiting, ctx):
    return waiting[0]


def lifo(t, waiting, ctx):
    return waiting[-1]


def priority(keyfn):
    """keyfn(jid, t, ctx) -> sortable; smallest key wins, ties by rank."""
    def ch(t, waiting, ctx):
        return min(waiting, key=lambda j: (keyfn(j, t, ctx), j))
    return ch


def tape_chooser(tape):
    """tape: list of ints; at the r-th dispatch pick waiting[tape[r] % len(waiting)].
    Every work-conserving schedule is reachable by some tape."""
    box = {'r': 0}

    def ch(t, waiting, ctx):
        r = box['r']
        box['r'] += 1
        idx = tape[r % len(tape)] % len(waiting) if tape else 0
        return waiting[idx]
    return ch


# ------------------------------------------------------------------ auditors
def audit(res, L=None):
    """Re-derive, from the schedule alone: non-overlap (non-preemption, one job
    per server at a time), work conservation (no server idle while a job waits),
    service <= L.  Returns list of failure strings (empty == clean)."""
    bad = []
    n, k = res['n'], res['k']
    a, x, s, fin, srv = res['a'], res['x'], res['s'], res['fin'], res['srv']
    if L is not None:
        for j in range(n):
            if x[j] > L:
                bad.append("service %s of job %d exceeds L=%s" % (x[j], j, L))
    # per-server intervals
    per = [[] for _ in range(k)]
    for j in range(n):
        per[srv[j]].append((s[j], fin[j], j))
    for m in range(k):
        per[m].sort()
        for q in range(1, len(per[m])):
            if per[m][q][0] < per[m][q - 1][1]:
                bad.append("server %d overlap: jobs %d,%d" %
                           (m, per[m][q - 1][2], per[m][q][2]))
    # work conservation: while job j waits on [a_j, s_j), every server is busy
    for j in range(n):
        if s[j] <= a[j]:
            continue
        lo, hi = a[j], s[j]
        for m in range(k):
            cov = lo
            for (b, e, jj) in per[m]:
                if e <= cov:
                    continue
                if b > cov:
                    break
                cov = e
                if cov >= hi:
                    break
            if cov < hi:
                bad.append("WORK-CONSERVATION: server %d idle in [%s,%s) while "
                           "job %d waits ([%s,%s))" % (m, cov, hi, j, lo, hi))
                break
    return bad


def unfinished(res, t):
    """U(t): total remaining work of jobs with a_j <= t, AFTER completions and
    arrivals at t are processed."""
    tot = 0
    for j in range(res['n']):
        if res['a'][j] > t:
            continue
        if res['s'][j] is None or res['s'][j] >= t:
            tot += res['x'][j]
        else:
            rem = res['fin'][j] - t
            if rem > 0:
                tot += rem
    return tot


def n_present(res, t):
    """N(t): jobs arrived (<=t) and not completed (fin > t)."""
    c = 0
    for j in range(res['n']):
        if res['a'][j] <= t and res['fin'][j] > t:
            c += 1
    return c


# ------------------------------------------------------- per-job bookkeeping
def bookkeeping(resP, resF, i):
    """All quantities of section 1.1 for job i, from the two schedules."""
    n, k = resP['n'], resP['k']
    a, x = resP['a'], resP['x']
    oP, oF = resP['order'], resF['order']
    WP = resP['s'][i] - a[i]
    WF = resF['s'][i] - a[i]
    In = sum(x[j] for j in range(n) if j > i and oP[j] < oP[i])
    Out = sum(x[j] for j in range(n) if j < i and oP[j] > oP[i])
    InF = sum(x[j] for j in range(n) if j > i and oF[j] < oF[i])
    OutF = sum(x[j] for j in range(n) if j < i and oF[j] > oF[i])

    def R(res):
        tot = 0
        for j in range(i):
            sj = res['s'][j]
            if sj >= a[i]:
                tot += x[j]
            else:
                rem = res['fin'][j] - a[i]
                if rem > 0:
                    tot += rem
        return tot

    def rho(res):
        si = res['s'][i]
        tot = 0
        for j in range(n):
            if j == i or res['order'][j] >= res['order'][i]:
                continue
            rem = res['fin'][j] - si
            if rem > 0:
                tot += rem
        return tot

    def rho_new(res):          # overtakers still in service at s_i
        si = res['s'][i]
        tot = 0
        for j in range(n):
            if j <= i or res['order'][j] >= res['order'][i]:
                continue
            rem = res['fin'][j] - si
            if rem > 0:
                tot += rem
        return tot

    RP, RF = R(resP), R(resF)
    rP, rF = rho(resP), rho(resF)
    rnew = rho_new(resP)
    D = k * (WP - WF) - (In - Out)
    De = k * (WP - WF) - ((In - rnew) - Out)
    return {'W_P': WP, 'W_F': WF, 'excess': WP - WF, 'In': In, 'Out': Out,
            'In_F': InF, 'Out_F': OutF, 'R_P': RP, 'R_F': RF,
            'rho_P': rP, 'rho_F': rF, 'rho_new': rnew, 'D': D, 'De': De}


def check_identity(resP, resF, i, bk=None):
    """Assert the three structural identities of Theorem 1's proof."""
    k = resP['k']
    b = bk or bookkeeping(resP, resF, i)
    errs = []
    if b['D'] != (b['R_P'] - b['R_F']) - b['rho_P'] + b['rho_F']:
        errs.append("decomposition D != (R^P-R^F)-rho^P+rho^F")
    if k * b['W_P'] != b['R_P'] + b['In'] - b['Out'] - b['rho_P']:
        errs.append("busy-period identity (1) fails under P")
    if k * b['W_F'] != b['R_F'] - b['rho_F']:
        errs.append("busy-period identity (2) fails under FCFS")
    if b['In_F'] or b['Out_F']:
        errs.append("FCFS has In=%s Out=%s (should be 0)" % (b['In_F'], b['Out_F']))
    return errs


# --------------------------------------------------------------- the wrapper
def guard_chooser(base_chooser, budget_fn):
    """E(t) = { q waiting : over_q(t) >= budget_q(t) }; serve min-rank member of
    E(t) if non-empty, else whatever the base chooses.
    over_q(t) = total true service of rank > q jobs COMPLETED by t.
    budget_fn(q, t, ctx) -> number."""
    def ch(t, waiting, ctx):
        x = ctx['x']
        done = [jid for (ft, jid) in ctx['completed'] if ft <= t]
        E = []
        for q in waiting:
            over = sum(x[j] for j in done if j > q)
            if over >= budget_fn(q, t, ctx):
                E.append(q)
        if E:
            return min(E)
        return base_chooser(t, waiting, ctx)
    return ch


def over_of(res, q, t):
    """over_q(t) from a finished schedule."""
    return sum(res['x'][j] for j in range(res['n'])
               if j > q and res['fin'][j] is not None and res['fin'][j] <= t)
