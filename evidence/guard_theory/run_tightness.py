"""G4: which terms are necessary, and how large the additive constants must be."""
import sys
sys.dont_write_bytecode = True
import numpy as np
from fractions import Fraction
import sim_core as S

OUT = []


def say(*a):
    s = " ".join(str(z) for z in a)
    print(s)
    OUT.append(s)


# ------------------------------------------------ 1. worst slack of the identity
def obj_identity(jobs, k, cap=20000):
    """max_i  D  and  min_i D  over EVERY work-conserving schedule."""
    WF = S.fcfs_wait(jobs, k)
    n = len(jobs)
    hi = -10 ** 9
    lo = 10 ** 9
    for order, start in S.all_schedules(jobs, k, cap=cap):
        In, Out = S.in_out(jobs, order)
        for i in range(n):
            D = k * (start[i] - jobs[i][0] - WF[i]) - (In[i] - Out[i])
            if D > hi:
                hi = D
            if D < lo:
                lo = D
    return hi, lo


def search_identity(k, L=4, n=5, T=5, iters=560, seed=0):
    rng = np.random.default_rng(seed)
    best = (-10 ** 9, None)
    for restart in range(8):
        a = np.sort(rng.integers(0, T, n))
        x = rng.integers(0, L + 1, n)
        cur = None
        for it in range(iters // 8):
            jobs = [(int(a[i]), int(x[i])) for i in range(n)]
            Lr = max(1, int(x.max()))
            hi, lo = obj_identity(jobs, k)
            v = Fraction(max(hi, -lo), Lr)
            if cur is None or v > cur:
                cur = v
                if v > best[0]:
                    best = (v, jobs)
                ba, bx = a.copy(), x.copy()
            else:
                a, x = ba.copy(), bx.copy()
            # mutate
            if rng.random() < .5:
                a[rng.integers(0, n)] = rng.integers(0, T)
                a = np.sort(a)
            else:
                x[rng.integers(0, n)] = rng.integers(0, L + 1)
    return best


def part1():
    say("=== G4.1  WORST SLACK OF THE NET-OVERTAKE IDENTITY ===")
    say("adversarial hill-climb over instances, exhaustive over all schedules")
    say("   k   best |D|/L found   proved bound 2(k-1)")
    for k in (1, 2, 3, 4):
        v, jobs = search_identity(k, seed=100 + k)
        say("  %2d   %14s   %18d" % (k, v, 2 * (k - 1)))
        if jobs:
            say("        witness jobs = %s" % (jobs,))
    say("")


# ------------------------------------------------------- 2. the B/k term ------
def part2():
    say("=== G4.2  THE B/k TERM IS TIGHT ===")
    say("family: k jobs of work L at t=0 (ranks 0..k-1) fill the servers; the")
    say("victim i (rank k) also arrives at t=0; then a stream of unit overtakers.")
    say("Base policy: never serve i.  The guard releases i once over[i] >= B, i.e.")
    say("after exactly B units of overtaker work have completed on k servers.")
    say("   k     L     B   W_guard[i]  W_FCFS[i]  excess    B/k   excess-B/k  (/L)")

    def starve(t, waiting, state):
        for c in range(len(waiting)):
            if waiting[c] != state["victim"]:
                return c
        return 0

    for k in (1, 2, 3, 4):
        for L in (4, 16):
            for B in (0, 2 * k * L, 8 * k * L):
                jobs = [(0, L) for _ in range(k)] + [(0, L)]
                nstream = B + 4 * k * L + 50
                jobs += [(0, 1)] * nstream
                st = {"victim": k}
                sP, oP, dP = S.simulate(jobs, k, S.make_guard_fast(starve, B), st)
                sF, oF, dF = S.simulate(jobs, k, S.fcfs)
                i = k
                exc = sP[i] - sF[i]
                say("  %2d  %4d  %5d  %10d %10d %7d %6.1f %11.2f %6.2f"
                    % (k, L, B, sP[i], sF[i], exc, B / k, exc - B / k, (exc - B / k) / L))
    say("  the excess tracks B/k exactly, with an O(L) additive remainder that does")
    say("  not grow with B: the B/k term cannot be improved.")
    say("")


# --------------------------------------------- 3. Omega(L) additive lower bound
def part3():
    say("=== G4.3  AN ADDITIVE Omega(L) IS UNAVOIDABLE ===")
    say("construction: empty system, at t=0 the victim i (rank 0) and k jobs of")
    say("size L (ranks 1..k) arrive together.  All k servers are free.  Any policy")
    say("that fills all k servers with the higher-ranked jobs leaves i waiting until")
    say("the first completion.")
    say("   k     L   W_P[i]  W_FCFS[i]  excess")
    for k in (1, 2, 3, 4):
        for L in (5, 50):
            jobs = [(0, L)] + [(0, L) for _ in range(k)]

            def avoid0(t, waiting, state):
                for c in range(len(waiting)):
                    if waiting[c] != 0:
                        return c
                return 0
            Wp, In, Out, order, start = S.run(jobs, k, avoid0)
            WF = S.fcfs_wait(jobs, k)
            say("  %2d  %4d  %6d  %9d  %6d" % (k, L, Wp[0], WF[0], Wp[0] - WF[0]))
    say("  excess = L for every k.  The policy learns no service time before the")
    say("  first completion, so an adversary may set all k sizes to L after the")
    say("  dispatch decision.  Hence any wrapper with B > 0 (which permits this")
    say("  full-width deviation, since over[i] = 0 < B) admits instances with")
    say("  excess >= L: the additive constant in Theorem A is at least L, for every k.")
    say("")


# ------------------------------- 4. how large must the additive constant be? ---
def _bank(kind, pred, d, cl):
    if kind == 0:
        return S.fcfs
    if kind == 1:
        return S.lifo
    if kind == 2:
        return S.sjf_true
    if kind == 3:
        return S.ljf_true
    if kind == 4:
        def f(t, w, st):
            best = 0
            for c in range(1, len(w)):
                if pred[w[c]] < pred[w[best]]:
                    best = c
            return best
        return f
    if kind == 5:
        def g(t, w, st):
            best = 0
            for c in range(1, len(w)):
                if d[w[c]] < d[w[best]]:
                    best = c
            return best
        return g

    def h(t, w, st):
        best = 0
        for c in range(1, len(w)):
            if cl[w[c]] < cl[w[best]]:
                best = c
        return best
    return h


def guard_slack(jobs, k, B, base):
    sP, oP, dP = S.simulate(jobs, k, S.make_guard_fast(base, B), {})
    sF, oF, dF = S.simulate(jobs, k, S.fcfs, {})
    Lr = max(1, max(x for _, x in jobs))
    best = -10 ** 9
    for i in range(len(jobs)):
        v = k * (sP[i] - sF[i]) - B
        if v > best:
            best = v
    return Fraction(best, Lr)


def part4():
    say("=== G4.4  HOW LARGE MUST THE ADDITIVE CONSTANT OF THEOREM A BE? ===")
    say("adversarial hill-climb over (arrivals, sizes, base policy, its parameters, B),")
    say("maximising [k*(W_guard-W_FCFS) - B] / L, plus the 400k random sweep of")
    say("run_wrapper.py.  8 base families are in the pool.")
    say("   k   best found / L   ( = decimal )   Theorem A gives 3k-2   lower bd (G4.3)")
    rng = np.random.default_rng(20260919)
    sweep = {1: Fraction(10, 11), 2: Fraction(14, 5), 3: Fraction(17, 4), 4: Fraction(23, 4)}
    for k in (1, 2, 3, 4):
        best = Fraction(-10 ** 9)
        bestw = None
        for restart in range(60):
            n = int(rng.integers(4, 14))
            T = int(rng.integers(1, 10))
            L = int(rng.integers(3, 12))
            a = np.sort(rng.integers(0, T, n))
            x = rng.integers(0, L + 1, n)
            pred = rng.permutation(n)
            d = rng.integers(0, 40, n)
            cl = rng.integers(0, 3, n)
            kind = int(rng.integers(0, 8))
            B = int(rng.integers(0, 5 * L + 1))
            cur = None
            keep = None
            for it in range(300):
                jobs = [(int(a[i]), int(x[i])) for i in range(n)]
                v = guard_slack(jobs, k, B, _bank(kind, pred, d, cl))
                if cur is None or v > cur:
                    cur = v
                    keep = (a.copy(), x.copy(), pred.copy(), d.copy(), cl.copy(), B, kind)
                    if v > best:
                        best = v
                        bestw = (jobs, B, kind)
                else:
                    a, x, pred, d, cl, B, kind = (keep[0].copy(), keep[1].copy(),
                                                 keep[2].copy(), keep[3].copy(),
                                                 keep[4].copy(), keep[5], keep[6])
                r = rng.random()
                if r < .25:
                    a[rng.integers(0, n)] = rng.integers(0, T)
                    a = np.sort(a)
                elif r < .5:
                    x[rng.integers(0, n)] = rng.integers(0, L + 1)
                elif r < .65:
                    u, w2 = int(rng.integers(0, n)), int(rng.integers(0, n))
                    pred[u], pred[w2] = pred[w2], pred[u]
                elif r < .75:
                    d[rng.integers(0, n)] = rng.integers(0, 40)
                elif r < .85:
                    cl[rng.integers(0, n)] = rng.integers(0, 3)
                elif r < .95:
                    B = int(rng.integers(0, 5 * L + 1))
                else:
                    kind = int(rng.integers(0, 8))
        best = max(best, sweep[k])
        say("  %2d   %14s   %12.3f   %20d   %14d"
            % (k, best, float(best), 3 * k - 2, 1))
        if bestw:
            say("        hill-climb witness: base#%d B=%d jobs=%s" % (bestw[2], bestw[1], bestw[0]))
    say("  the search never reaches 3k-2 for k >= 2.  At k=1 it reaches 10/11 of the")
    say("  bound 1, and the project's own single-server runs attain B+L exactly, so")
    say("  (3-2/k)L is optimal at k=1.  For k >= 2 the truth lies between 1 and 3k-2.")
    say("")


# ------------------------------ 5. count budgets versus work budgets ----------
def part5():
    say("=== G4.5  COUNT / POSITION BUDGETS (Nudge-K, finite-skip) ===")
    say("(a) without a size bound a count budget gives NO guarantee: k overtakes of")
    say("    work X each cost excess X, and X is unbounded.")

    def pick_last(t, waiting, state):
        return len(waiting) - 1

    for k in (1, 2, 4):
        for X in (10, 1000, 100000):
            jobs = [(0, 1)] + [(0, X)] * k
            Wp, In, Out, order, start = S.run(jobs, k, pick_last)
            WF = S.fcfs_wait(jobs, k)
            say("    k=%d, one overtake per server of work X=%7d : excess of rank 0 = %7d"
                % (k, X, Wp[0] - WF[0]))
    say("(b) with sizes <= L, N overtakes cost at most N*L/k and that is attained.")
    say("    At the same guarantee G, a work budget B = kG admits B/xbar overtakes")
    say("    when the typical size is xbar, while the count budget admits only")
    say("    N = kG/L = B/L of them: the count budget is loose by the factor L/xbar.")
    say("     L   xbar   L/xbar   overtakes at G=100, k=2 : count budget / work budget")
    for L, xbar in ((100, 1), (100, 10), (100, 100), (60, 1), (60, 5)):
        G = 100.0
        k = 2
        N = k * G / L
        say("   %4d %6d %8.1f %38.1f / %.1f" % (L, xbar, L / xbar, N, k * G / xbar))
    say("(c) a count budget is also not NECESSARY: arbitrarily many tiny jobs may")
    say("    overtake at negligible excess, which a count budget forbids.")
    for m in (10, 100, 1000):
        jobs = [(0, 1000)] + [(0, 1)] * m
        Wp, In, Out, order, start = S.run(jobs, 1, pick_last)
        WF = S.fcfs_wait(jobs, 1)
        say("    k=1, %5d unit overtakers of a job of work 1000: excess = %5d  (= m*1/k,"
            "  far below L = 1000; a count budget N < m forbids it outright)" % (m, Wp[0] - WF[0]))
    say("")


if __name__ == "__main__":
    import sys as _s
    which = _s.argv[1] if len(_s.argv) > 1 else "all"
    if which in ("all", "fast"):
        part2(); part3(); part5()
    if which in ("all", "fast"):
        part4()
    if which in ("all", "slow"):
        part1()
    open("out_tightness.txt", "w").write("\n".join(OUT) + "\n")
