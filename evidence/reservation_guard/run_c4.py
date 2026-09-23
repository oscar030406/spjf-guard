"""C4.  Multiserver propagation: the L-scale residual at k >= 2 is a workload-gap
effect, not a charging effect.

Part A.  Run the cascade of Supplementary S8.1 (the construction in
evidence/guard_theory/family_tight.py, reimplemented here so nothing is
imported from it) for m rounds, so that at T_m = m*L the reference is empty and
the policy still holds k-1 jobs with remaining f each, gap delta = (k-1)f.
Then inject one job of LOWER rank than the victim and the victim itself.  The
victim's excess is f = delta/(k-1) while In_i = Out_i = 0: no charging rule of
any kind can see it, because nothing overtook the victim.

Part B.  Wrap the same cascade base policy in the guard (both charging rules)
with budget B and measure the largest workload gap the run still reaches, and
the largest excess, as a function of B.  This asks whether a budget B < L caps
the cascade's gap at O(B) instead of (k-1)L.

    env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME \
        uv run --no-project --with numpy python run_c4.py
"""
import sys
from fractions import Fraction

sys.dont_write_bytecode = True
import rguard  # noqa: E402
import sim_core  # noqa: E402


def prio_chooser(prio):
    def f(t, waiting, state):
        best = 0
        for c in range(1, len(waiting)):
            if prio[waiting[c]] < prio[waiting[best]]:
                best = c
        return best
    return f


def cascade(k, L, m, s):
    """Rounds of the S8.1 cascade; returns (jobs, prio, T_m)."""
    jobs = []
    prio = []
    for j in range(m):
        T = j * L
        for _ in range(k - 1):            # bigs: FCFS takes them first
            jobs.append((T, L))
            prio.append(2 * j + 1)
        for _ in range(L // s):           # tinies: the base takes them first
            jobs.append((T, s))
            prio.append(2 * j)
    return jobs, prio, m * L


def rho_seq(k, L, m):
    r = 0
    for _ in range(m):
        assert (k - 1) * (r + L) % k == 0
        r = (k - 1) * (r + L) // k
    return r


def workload(jobs, k, start, t):
    x = [j[1] for j in jobs]
    a = [j[0] for j in jobs]
    u = 0
    for i in range(len(jobs)):
        if a[i] <= t:
            if start[i] is None or start[i] >= t:
                u += x[i]
            else:
                u += max(0, start[i] + x[i] - t)
    return u


def part_a():
    print("=" * 78)
    print("C4 part A  a victim with In_i = Out_i = 0 and excess = f = "
          "delta/(k-1)")
    print("=" * 78)
    print("%-4s %-5s %-4s %-7s %-10s %-10s %-8s %-8s %s"
          % ("k", "L", "m", "n", "delta", "f=d/(k-1)", "In_i", "Out_i",
             "excess_i"))
    for k in (2, 3, 4):
        L = k ** 3
        for m in (1, 2, 3):
            jobs, prio, T = cascade(k, L, m, 1)
            g = len(jobs)
            jobs = jobs + [(T, L), (T, L)]        # g = lower rank, then victim
            prio = prio + [10 ** 6, 10 ** 6 + 1]
            victim = g + 1
            sP, oP, _ = sim_core.simulate(jobs, k, prio_chooser(prio))
            In, Out, W, WF, exc = rguard.metrics(jobs, k, oP, sP)
            sF, _, _ = sim_core.simulate(jobs, k, sim_core.fcfs)
            delta = workload(jobs, k, sP, T) - workload(jobs, k, sF, T)
            print("%-4d %-5d %-4d %-7d %-10s %-10s %-8d %-8d %s"
                  % (k, L, m, len(jobs), delta,
                     Fraction(delta, k - 1), In[victim], Out[victim],
                     exc[victim]))
    print("predicted delta after m rounds: (k-1)L(1-((k-1)/k)^m);  "
          "rho_m/(k-1) = f")
    for k in (2, 3, 4):
        L = k ** 3
        print("   k=%d L=%d  rho_m = %s , f = %s"
              % (k, L, [rho_seq(k, L, m) for m in (1, 2, 3)],
                 [Fraction(rho_seq(k, L, m), k - 1) for m in (1, 2, 3)]))


def part_b():
    print()
    print("=" * 78)
    print("C4 part B  the cascade under the guard: reached gap vs budget B")
    print("=" * 78)
    for k in (2, 3):
        L = k ** 3
        m = 3
        jobs, prio, T = cascade(k, L, m, 1)
        g = len(jobs)
        jobs2 = jobs + [(T, L), (T, L)]
        prio2 = prio + [10 ** 6, 10 ** 6 + 1]
        victim = g + 1
        n = len(jobs2)
        caps = [L] * n
        base = prio_chooser(prio2)
        sF, _, _ = sim_core.simulate(jobs2, k, sim_core.fcfs)
        print()
        print("k=%d L=%d m=%d n=%d   unguarded gap at T_m = %d , (k-1)L = %d"
              % (k, L, m, n,
                 workload(jobs2, k,
                          sim_core.simulate(jobs2, k, base)[0], T)
                 - workload(jobs2, k, sF, T), (k - 1) * L))
        xs = [j[1] for j in jobs2]
        print("  %-5s %-11s %-11s %-11s %-11s %s"
              % ("B", "maxgap R/L", "maxgap R/C", "maxgap C", "maxexc R/L",
                 "maxexc C"))
        grid = sorted(set([0, 1, 2, 3, 4, 6, L // 4, L // 2, L - 1, L,
                           L + 1, 2 * L, 3 * L]))
        for B in grid:
            row = {}
            for tag, wrap in (('RL', rguard.make_rguard(base, B, caps)),
                              ('RC', rguard.make_rguard(base, B, xs)),
                              ('C', rguard.make_cguard(base, B))):
                sP, oP, _ = sim_core.simulate(jobs2, k, wrap)
                mg = max(workload(jobs2, k, sP, t)
                         - workload(jobs2, k, sF, t)
                         for t in range(0, T + 2 * L + 1))
                In, Out, W, WF, exc = rguard.metrics(jobs2, k, oP, sP)
                row[tag] = (mg, max(exc), max(In))
            print("  %-5d %-11d %-11d %-11d %-11d %d"
                  % (B, row['RL'][0], row['RC'][0], row['C'][0],
                     row['RL'][1], row['C'][1]))
        print("  reference: (k-1)L = %d ; unguarded maxgap = %d ; "
              "(k-1)*B is the candidate law for B < L"
              % ((k - 1) * L,
                 max(workload(jobs2, k, sim_core.simulate(jobs2, k, base)[0],
                              t) - workload(jobs2, k, sF, t)
                     for t in range(0, T + 2 * L + 1))))


def part_c():
    """Is the guarded workload gap O(B) when B < L?  FALSE for rule C, and a
    measured law for rule R."""
    import numpy as np
    print()
    print("=" * 78)
    print("C4 part C  is the guarded gap O(B) for B < L?")
    print("=" * 78)
    print("H:  max_t (U_P - U_FCFS) <= (k-1)*min(L,B) for every guarded run.")
    print("exhaustive over ALL base policies, small instances, both rules:")
    import itertools
    L = 3
    for nn in (4, 5):
        for rule in ('R', 'C'):
            worst = {}
            cnt = 0
            for a in [(0,) * nn, tuple([0] * (nn - 2) + [1, 1]),
                      tuple(range(nn))]:
                for x in itertools.product((1, 2, 3), repeat=nn):
                    jobs = list(zip(a, x))
                    for k in (2, 3):
                        for B in (0, 1, 2, 3, 4, 6):
                            ell = [L] * nn if rule == 'R' else None
                            for order, start in rguard.enum_runs(
                                    jobs, k, rule, B, ell):
                                cnt += 1
                                sF, _, _ = sim_core.simulate(
                                    jobs, k, sim_core.fcfs)
                                hi = max(a) + sum(x) + 1
                                mg = max(workload(jobs, k, start, t)
                                         - workload(jobs, k, sF, t)
                                         for t in range(hi))
                                d = mg - (k - 1) * min(L, B)
                                if d > worst.get(k, (-99,))[0]:
                                    worst[k] = (d, mg, k, L, B, jobs)
            print("   n=%d rule %s : %d runs ;  %s"
                  % (nn, rule, cnt,
                     " ; ".join("k=%d worst gap-(k-1)min(L,B) = %+d (gap %d, "
                                "B %d)" % (k, w[0], w[1], w[4])
                                for k, w in sorted(worst.items()))))
    print()
    print("random test of  max_t |U_P - U_FCFS| <= (k-1)*min(L,B)  for rule R")
    rng = np.random.default_rng(4041)
    worst = {}
    for _ in range(4000):
        k = int(rng.integers(1, 5))
        L = int(rng.integers(3, 13))
        n = int(rng.integers(3, 10))
        a = np.sort(rng.integers(0, 2 * L, size=n)).tolist()
        x = rng.integers(1, L + 1, size=n).tolist()
        caps = [int(min(L, xi + rng.integers(0, L))) for xi in x]
        jobs = [(int(ai), int(xi)) for ai, xi in zip(a, x)]
        B = int(rng.integers(0, 3 * L))
        pr = rng.permutation(n).tolist()
        base = prio_chooser(pr)
        sF, _, _ = sim_core.simulate(jobs, k, sim_core.fcfs)
        sP, _, _ = sim_core.simulate(jobs, k, rguard.make_rguard(base, B, caps))
        hi = max(a) + sum(x) + 1
        mg = max(abs(workload(jobs, k, sP, t) - workload(jobs, k, sF, t))
                 for t in range(0, hi))
        lim = (k - 1) * min(L, B)
        d = mg - lim
        if d > worst.get(k, (-10 ** 9,))[0]:
            worst[k] = (d, mg, lim, k, L, B, jobs, caps)
    for k in sorted(worst):
        w = worst[k]
        print("   k=%d  worst (gap - (k-1)min(L,B)) = %+d   (gap=%d, "
              "limit=%d, L=%d, B=%d)" % (k, w[0], w[1], w[2], w[4], w[5]))
        if w[0] > 0:
            print("      COUNTEREXAMPLE jobs=%s caps=%s" % (w[6], w[7]))


if __name__ == "__main__":
    part_a()
    part_b()
    part_c()
