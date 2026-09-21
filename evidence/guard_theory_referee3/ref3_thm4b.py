"""Item 2: Theorem 4B (capped relative budget), attacked by EXHAUSTIVE
enumeration of every work-conserving schedule the base policy could produce.

The base is adversarial in the strongest sense: at every dispatch at which the
fired set E(t) is empty, every waiting job is tried.  When E(t) is non-empty the
choice is forced to min E(t) (that is the wrapper).  So the enumeration covers
all base policies at once, including clairvoyant ones.

All arithmetic is exact integer arithmetic: eta = en/ed, and every claim is
cleared of denominators before it is checked.

    (5)  In_i  <  B0_i + eta k W + kL        and  In_i < Bmax + kL
    (6)  (1-eta) W  <=  W_F + B0_i/k + (3-2/k) L
    (7)  W  <=  W_F + Bmax/k + (3-2/k) L
"""
import itertools
import random
import sys

from ref3_sim import simulate, fcfs

OUT = []
INF = None          # Bmax = None means +infinity


def p(*args):
    s = " ".join(str(x) for x in args)
    OUT.append(s)
    print(s)


# ------------------------------------------------------------- enumerator
def enum_guard(a, x, k, B0, en, ed, Bmax, on_schedule, cap=None):
    """Enumerate every schedule of the wrapper with budget
    budget_q(t) = min(B0[q] + (en/ed) k (t - a_q), Bmax).
    on_schedule(s, order, fin) is called for each complete schedule."""
    n = len(a)
    s = [None] * n
    fin = [None] * n
    order = [None] * n
    box = {'cnt': 0, 'stop': False}

    def over(q, t):
        tot = 0
        for j in range(q + 1, n):
            f = fin[j]
            if f is not None and f <= t:
                tot += x[j]
        return tot

    def fired(q, t):
        # over_q(t) >= min(B0_q + (en/ed) k (t-a_q), Bmax)   cleared of ed
        lhs = over(q, t) * ed
        r1 = B0[q] * ed + en * k * (t - a[q])
        rhs = r1 if Bmax is None else min(r1, Bmax * ed)
        return lhs >= rhs

    def rec(t, busy, waiting, nxt, cnt):
        if box['stop']:
            return
        free = None
        for m in range(k):
            if busy[m] is None:
                free = m
                break
        if waiting and free is not None:
            E = [q for q in waiting if fired(q, t)]
            cands = [min(E)] if E else list(waiting)
            for jid in cands:
                nb = list(busy)
                s[jid] = t
                fin[jid] = t + x[jid]
                order[jid] = cnt
                if x[jid] != 0:
                    nb[free] = t + x[jid]
                nw = [w for w in waiting if w != jid]
                rec(t, tuple(nb), nw, nxt, cnt + 1)
                s[jid] = None
                fin[jid] = None
                order[jid] = None
                if box['stop']:
                    return
            return
        # advance
        cands = []
        if nxt < n:
            cands.append(a[nxt])
        for m in range(k):
            if busy[m] is not None:
                cands.append(busy[m])
        if not cands:
            box['cnt'] += 1
            if cap is not None and box['cnt'] > cap:
                box['stop'] = True
                return
            on_schedule(list(s), list(order), list(fin))
            return
        t2 = min(cands)
        nb = [None if (busy[m] is not None and busy[m] <= t2) else busy[m]
              for m in range(k)]
        nw = list(waiting)
        j = nxt
        while j < n and a[j] <= t2:
            nw.append(j)
            j += 1
        nw.sort()
        rec(t2, tuple(nb), nw, j, cnt)

    t0 = a[0]
    w0 = [j for j in range(n) if a[j] <= t0]
    rec(t0, tuple([None] * k), w0, len(w0), 0)
    return box['cnt']


# -------------------------------------------------------------- the checks
def check_schedule(a, x, k, B0, en, ed, Bmax, L, WF, s, order, fin):
    """Returns list of violation dicts."""
    n = len(a)
    bad = []
    pos = order
    for i in range(n):
        W = s[i] - a[i]
        In = 0
        for j in range(i + 1, n):
            if pos[j] < pos[i]:
                In += x[j]
        Out = 0
        for j in range(i):
            if pos[j] > pos[i]:
                Out += x[j]
        # (5a) In < B0_i + eta k W + kL    (only claimed when i has an overtaker)
        if In > 0:
            if not (In * ed < B0[i] * ed + en * k * W + k * L * ed):
                bad.append(('5a', i, In, W))
            if Bmax is not None and not (In < Bmax + k * L):
                bad.append(('5b', i, In, W))
        # (6) (ed-en) k W <= ed (k WF + B0_i + (3k-2) L)
        if not ((ed - en) * k * W <= ed * (k * WF[i] + B0[i] + (3 * k - 2) * L)):
            bad.append(('6', i, In, W))
        # (7) k W <= k WF + Bmax + (3k-2) L
        if Bmax is not None and not (k * W <= k * WF[i] + Bmax + (3 * k - 2) * L):
            bad.append(('7', i, In, W))
        # Theorem 1 as well, for free
        D = k * (W - WF[i]) - (In - Out)
        if abs(D) > 2 * (k - 1) * L:
            bad.append(('Thm1', i, D, 2 * (k - 1) * L))
    return bad


def fcfs_waits(a, x, k):
    r = simulate(a, x, k, fcfs)
    return [r['s'][i] - a[i] for i in range(len(a))]


# ---------------------------------------------------------------- sweeps
def exhaustive(nmax, ks, smax, amax, params, tag):
    tot_sched = 0
    tot_inst = 0
    viol = []
    worst = {}
    for n in range(2, nmax + 1):
        for arr in itertools.combinations_with_replacement(range(amax + 1), n):
            for sz in itertools.product(range(smax + 1), repeat=n):
                a = list(arr)
                x = list(sz)
                L = max(x)
                if L == 0:
                    continue
                for k in ks:
                    WF = fcfs_waits(a, x, k)
                    for (B0mode, en, ed, Bmax) in params:
                        if B0mode == 'c0':
                            B0 = [0] * n
                        elif B0mode == 'c1':
                            B0 = [1] * n
                        elif B0mode == 'c3':
                            B0 = [3] * n
                        else:                       # per-job B0
                            B0 = [(j % 3) for j in range(n)]
                        tot_inst += 1
                        res = []

                        def cb(s, order, fin, _a=a, _x=x, _k=k, _B0=B0,
                               _en=en, _ed=ed, _Bmax=Bmax, _L=L, _WF=WF):
                            b = check_schedule(_a, _x, _k, _B0, _en, _ed,
                                               _Bmax, _L, _WF, s, order, fin)
                            if b:
                                res.append((b, list(s), list(order)))
                            # frontier: (k*excess - Bmax)/L under a cap
                            if _Bmax is not None:
                                for i in range(len(_a)):
                                    v = _k * ((s[i] - _a[i]) - _WF[i]) - _Bmax
                                    key = (_k,)
                                    if key not in worst or v * worst[key][1] > worst[key][0] * _L:
                                        worst[key] = (v, _L, (_a, _x, _Bmax, i))
                        c = enum_guard(a, x, k, B0, en, ed, Bmax, cb)
                        tot_sched += c
                        if res:
                            viol.append((a, x, k, B0, en, ed, Bmax, res[0]))
                            if len(viol) > 5:
                                return tot_inst, tot_sched, viol, worst
    return tot_inst, tot_sched, viol, worst


def random_sweep(trials, seed, kmax=5, nmax=9):
    rnd = random.Random(seed)
    viol = []
    checked = 0
    for _ in range(trials):
        k = rnd.randint(1, kmax)
        n = rnd.randint(2, nmax)
        a = sorted(rnd.randint(0, 6) for _ in range(n))
        x = [rnd.randint(0, 5) for _ in range(n)]
        L = max(x)
        if L == 0:
            continue
        ed = rnd.choice([1, 2, 3, 4, 5, 8, 10, 100])
        en = rnd.randint(0, ed - 1)
        Bmax = rnd.choice([None, 0, 1, 2, 3 * k * L, k * L])
        B0 = [rnd.randint(0, 2 * L) for _ in range(n)]
        WF = fcfs_waits(a, x, k)
        tape = [rnd.randint(0, 7) for _ in range(3 * n)]
        box = {'r': 0}

        def base(t, waiting, ctx):
            r = box['r']
            box['r'] += 1
            return waiting[tape[r % len(tape)] % len(waiting)]

        def budget(q, t, ctx):
            from fractions import Fraction
            v = Fraction(B0[q]) + Fraction(en, ed) * k * (t - a[q])
            return v if Bmax is None else min(v, Bmax)

        from ref3_sim import guard_chooser
        res = simulate(a, x, k, guard_chooser(base, budget))
        b = check_schedule(a, x, k, B0, en, ed, Bmax, L, WF,
                           res['s'], res['order'], res['fin'])
        checked += 1
        if b:
            viol.append((a, x, k, B0, en, ed, Bmax, b))
            if len(viol) > 3:
                break
    return checked, viol


def main():
    p("=" * 78)
    p("ITEM 2 -- Theorem 4B, exhaustive over EVERY base choice")
    p("=" * 78)
    p("")
    params = [
        ('c0', 0, 1, None), ('c1', 0, 1, None), ('c3', 0, 1, None),
        ('c0', 1, 2, None), ('c1', 1, 2, None), ('c3', 3, 4, None),
        ('c0', 0, 1, 0), ('c1', 1, 2, 2), ('c3', 3, 4, 2),
        ('c0', 1, 2, 6), ('per', 1, 2, None), ('per', 3, 4, 3),
        ('per', 0, 1, 1), ('c1', 9, 10, None), ('c0', 9, 10, 2),
    ]
    p("parameters (B0mode, eta=en/ed, Bmax):")
    for q in params:
        p("   ", q)
    p("")
    for (nmax, ks, smax, amax, tag) in [(4, (1, 2, 3), 3, 2, "n<=4"),
                                        (5, (2, 3), 2, 1, "n<=5")]:
        ti, ts, viol, worst = exhaustive(nmax, ks, smax, amax, params, tag)
        p("exhaustive %s  k in %s sizes<=%d arrivals<=%d:" % (tag, ks, smax, amax))
        p("   %d (instance,parameter) pairs, %d complete schedules enumerated"
          % (ti, ts))
        if viol:
            p("   *** VIOLATIONS ***")
            for v in viol:
                p("   ", v)
        else:
            p("   0 violations of (5), (6), (7) -- and 0 of Theorem 1")
        for kk, (v, LL, wit) in sorted(worst.items()):
            p("   worst (k*excess - Bmax)/L at k=%d : %.4f  witness a=%s x=%s "
              "Bmax=%s job=%d   (proved bound 3k-2 = %d)"
              % (kk[0], v / LL, wit[0], wit[1], wit[2], wit[3], 3 * kk[0] - 2))
        p("")
    ch, viol = random_sweep(60000, 20260919)
    p("random sweep (own simulator, random tape base, per-job B0, eta up to")
    p("   99/100, random caps, k<=5, n<=9): %d instances" % ch)
    if viol:
        p("   *** VIOLATIONS ***")
        for v in viol:
            p("   ", v)
    else:
        p("   0 violations")
    p("")
    with open("out_thm4b.txt", "w") as fh:
        fh.write("\n".join(OUT) + "\n")


if __name__ == "__main__":
    main()
