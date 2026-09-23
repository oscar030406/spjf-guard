"""C1b independent: does the residual (2-2/k)L survive rule R, and is it
actually approached?

The S8.2 upward witness is rebuilt here from its description (cascade of m
rounds, then k-1 long jobs, the victim, and a stream of tiny jobs the base
prefers); nothing is imported from ../guard_theory/.  Budget B = f + L + 1 with
f = rho_m/(k-1), caps ell = C (clairvoyant), as in the report.

Rule R with a CONSTANT allowance Z only has to test the queue head, because
overR[q] is non-increasing in rank; part 0 checks that equivalence by brute
force before part 1 relies on it for the large witnesses.

Usage: python check_c1b.py
"""
import sys
from fractions import Fraction

sys.dont_write_bytecode = True
import rguard_indep as R   # noqa: E402


def rho_seq(k, L, m):
    r = 0
    out = [0]
    for _ in range(m):
        assert (k - 1) * (r + L) % k == 0, "choose L = k**m"
        r = (k - 1) * (r + L) // k
        out.append(r)
    return out


def build_upper(k, L, m, s, ntiny):
    jobs = []
    prio = []
    for j in range(m):
        T = j * L
        for _ in range(k - 1):
            jobs.append((T, L))
            prio.append(2 * j + 1)
        for _ in range(L // s):
            jobs.append((T, s))
            prio.append(2 * j)
    T = m * L
    for _ in range(k - 1):
        jobs.append((T, L))
        prio.append(2 * m)
    victim = len(jobs)
    jobs.append((T, L))
    prio.append(2 * m + 2)
    for _ in range(ntiny):
        jobs.append((T, s))
        prio.append(2 * m + 1)
    return jobs, prio, victim


def head_only_chooser(base, svc, ell, Z, n):
    """Rule R with a constant allowance: only the head has to be tested."""
    def f(t, queue, fin):
        c = base(t, queue, fin)
        if c == 0:
            return 0
        h = queue[0]
        if R.overR(h, t, svc, ell, fin, n) + ell[queue[c]] > Z:
            return 0
        return c
    return f


def prio_chooser(prio):
    def f(t, queue, fin):
        best = 0
        for c in range(1, len(queue)):
            if prio[queue[c]] < prio[queue[best]]:
                best = c
        return best
    return f


def part0():
    print("part 0  head-only test == full test, for a constant allowance Z")
    from random import Random
    rng = Random(3)
    bad = 0
    checks = 0
    for _ in range(3000):
        n = rng.randint(3, 10)
        k = rng.choice([1, 2, 3])
        L = rng.choice([2, 5, 9])
        svc = [rng.randint(1, L) for _ in range(n)]
        ell = [rng.randint(c, L) for c in svc]
        arr = sorted(rng.randint(0, 8) for _ in range(n))
        jobs = tuple(zip(arr, svc))
        Z = rng.randint(0, 2 * L)

        def base(t, queue, fin, _rng=rng):
            return _rng.randrange(len(queue))

        def wrapped(t, queue, fin, _svc=svc, _ell=ell, _Z=Z, _n=n):
            c = base(t, queue, fin)
            full = c in R.allowed_R(t, queue, fin, _svc, _ell, _Z, _n)
            h = queue[0]
            headonly = (R.overR(h, t, _svc, _ell, fin, _n) + _ell[queue[c]]
                        <= _Z) if c else True
            nonlocal_bad[0] += (full != headonly)
            nonlocal_bad[1] += 1
            return c if full else 0

        nonlocal_bad = [0, 0]
        R.run_with_chooser(jobs, k, wrapped)
        bad += nonlocal_bad[0]
        checks += nonlocal_bad[1]
    print("   %d decisions, %d disagreements between the head-only test and "
          "the full test" % (checks, bad))


def part1():
    print()
    print("part 1  (k*excess - B)/L for the victim of the S8.2 upward witness "
          "under rule R")
    print("  %-3s %-4s %-7s %-8s %-8s %-8s %-14s %-8s %s"
          % ("k", "m", "L", "n", "f", "B", "(k e - B)/L", "In_R", "target 2k-2"))
    for k, ms in ((2, (1, 2, 3, 4, 5, 6, 7, 8)), (3, (1, 2, 3, 4, 5)),
                  (4, (1, 2, 3, 4))):
        for m in ms:
            L = k ** m
            f = rho_seq(k, L, m)[m] // (k - 1)
            B = f + L + 1
            jobs, prio, v = build_upper(k, L, m, 1, 2 * k * L + 2 * B + 4)
            n = len(jobs)
            jobs = tuple(jobs)
            svc = [j[1] for j in jobs]
            ell = list(svc)
            ch = head_only_chooser(prio_chooser(prio), svc, ell, B, n)
            sP, seqP = R.run_with_chooser(jobs, k, ch)
            WF = R.fcfs_wait(jobs, k)
            In, Out = R.in_out(jobs, seqP)
            exc = sP[v] - jobs[v][0] - WF[v]
            print("  %-3d %-4d %-7d %-8d %-8d %-8d %-14s %-8d %d"
                  % (k, m, L, n, f, B, Fraction(k * exc - B, L), In[v],
                     2 * k - 2))


if __name__ == "__main__":
    part0()
    part1()
