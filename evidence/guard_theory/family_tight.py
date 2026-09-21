"""Explicit families showing that the constant 2(k-1)L of Theorem 1 is the exact
SUPREMUM of |k(W_P - W_FCFS) - (In - Out)|, in both directions.

Both families use a "cascade" that drives the workload gap U_P - U_FCFS to its
Lemma-1 ceiling (k-1)L geometrically (ratio (k-1)/k per round), followed by a
one-batch finale that adds a second (k-1)L.

  upper family:  P lags FCFS in workload; the finale makes FCFS dispatch k-1
                 jobs of work L at the very instant it dispatches the victim
                 (rho^F = (k-1)L) while P has nothing in service (rho^P ~ 0).
  lower family:  the mirror image; P runs ahead in workload and dispatches k-1
                 jobs of work L in the victim's own dispatch phase
                 (rho^P = (k-1)L) while FCFS has nothing in service.

P is a static-priority policy in both (a legal work-conserving policy: it always
dispatches the waiting job with the smallest priority key).  Everything is exact
integer arithmetic and is simulated by sim_core.py, which knows nothing about
this construction.

    env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME \
        uv run --with numpy python family_tight.py
"""
import sys
sys.dont_write_bytecode = True

from fractions import Fraction

import sim_core


def prio_chooser(prio):
    def f(t, waiting, state):
        best = 0
        for c in range(1, len(waiting)):
            if prio[waiting[c]] < prio[waiting[best]]:
                best = c
        return best
    return f


def rho_seq(k, L, m):
    """rho_j = total remaining work P still holds when round j ends."""
    r = 0
    out = [0]
    for _ in range(m):
        assert (k - 1) * (r + L) % k == 0, "choose L = k**m"
        r = (k - 1) * (r + L) // k
        out.append(r)
    return out


def build_upper(k, L, m, s, ntiny):
    """Returns (jobs, prio, victim).  jobs are already in rank order."""
    jobs = []
    prio = []
    for j in range(m):                      # cascade
        T = j * L
        for _ in range(k - 1):              # the bigs: FCFS takes them first
            jobs.append((T, L)); prio.append(2 * j + 1)
        for _ in range(L // s):             # the tinies: P takes them first
            jobs.append((T, s)); prio.append(2 * j)
    T = m * L                               # finale
    for _ in range(k - 1):
        jobs.append((T, L)); prio.append(2 * m)
    victim = len(jobs)
    jobs.append((T, L)); prio.append(2 * m + 2)
    for _ in range(ntiny):
        jobs.append((T, s)); prio.append(2 * m + 1)
    return jobs, prio, victim


def build_lower(k, L, m, s):
    jobs = []
    prio = []
    for j in range(m):                      # mirror cascade
        T = j * L
        for _ in range(L // s):             # tinies first in RANK
            jobs.append((T, s)); prio.append(2 * j + 1)
        for _ in range(k - 1):              # bigs later in rank, first for P
            jobs.append((T, L)); prio.append(2 * j)
    T = m * L
    f = rho_seq(k, L, m)[m] // (k - 1) if k > 1 else 0
    jobs.append((T, f)); prio.append(2 * m + 2)        # filler, rank < victim
    victim = len(jobs)
    jobs.append((T, L - 1)); prio.append(2 * m + 1)    # victim
    for _ in range(k - 1):
        jobs.append((T, L)); prio.append(2 * m)        # overtakers, P first
    return jobs, prio, victim


def measure(jobs, prio, k, victim):
    """Exact D, and its decomposition, for one job of one instance."""
    n = len(jobs)
    a = [j[0] for j in jobs]
    x = [j[1] for j in jobs]
    sP, oP, _ = sim_core.simulate(jobs, k, prio_chooser(prio))
    sF, oF, _ = sim_core.simulate(jobs, k, sim_core.fcfs)
    posP = [0] * n
    for p, j in enumerate(oP):
        posP[j] = p
    posF = [0] * n
    for p, j in enumerate(oF):
        posF[j] = p
    i = victim
    In = sum(x[j] for j in range(i + 1, n) if posP[j] < posP[i])
    Out = sum(x[j] for j in range(i) if posP[j] > posP[i])
    Ine = 0
    for j in range(i + 1, n):
        e = min(sP[j] + x[j], sP[i]) - sP[j]
        if e > 0:
            Ine += e
    RP = RF = 0
    for j in range(i):
        RP += x[j] if sP[j] >= a[i] else max(0, sP[j] + x[j] - a[i])
        RF += x[j] if sF[j] >= a[i] else max(0, sF[j] + x[j] - a[i])
    rP = sum(max(0, sP[j] + x[j] - sP[i]) for j in range(n)
             if j != i and posP[j] < posP[i])
    rF = sum(max(0, sF[j] + x[j] - sF[i]) for j in range(n)
             if j != i and posF[j] < posF[i])
    WP = sP[i] - a[i]
    WF = sF[i] - a[i]
    D = k * (WP - WF) - (In - Out)
    De = k * (WP - WF) - (Ine - Out)
    assert D == RP - RF - rP + rF, (D, RP, RF, rP, rF)
    return dict(D=D, De=De, RP=RP, RF=RF, rP=rP, rF=rF, In=In, Ine=Ine,
                Out=Out, WP=WP, WF=WF, n=n)


def main():
    print("=" * 74)
    print("Theorem 1's constant 2(k-1)L: explicit families approaching it")
    print("=" * 74)
    for k, ms in ((2, (1, 2, 3, 4, 5, 6)), (3, (1, 2, 3, 4)), (4, (1, 2, 3))):
        L = k ** max(ms)
        s = 1
        print()
        print("UPPER family, k=%d, L=%d (= k**m_max), tiny size %d,"
              " proved bound 2(k-1)L = %d" % (k, L, s, 2 * (k - 1) * L))
        for m in ms:
            jobs, prio, v = build_upper(k, L, m, s, ntiny=2 * k * L + 1)
            r = measure(jobs, prio, k, v)
            g = Fraction(r['RP'] - r['RF'], L)
            print("   m=%d n=%-5d D = %-7s L   [R^P-R^F = %-6s L, rho^F = %-4s L,"
                  " rho^P = %-6s L]  De = %s L"
                  % (m, r['n'], Fraction(r['D'], L), g, Fraction(r['rF'], L),
                     Fraction(r['rP'], L), Fraction(r['De'], L)))
        print("   predicted limit 2(k-1) = %d ;  round-j gap (k-1)L(1-((k-1)/k)^j)"
              % (2 * (k - 1)))

        print("LOWER (mirror) family, k=%d, L=%d" % (k, L))
        for m in ms:
            jobs, prio, v = build_lower(k, L, m, s)
            r = measure(jobs, prio, k, v)
            g = Fraction(r['RF'] - r['RP'], L)
            print("   m=%d n=%-5d D = %-7s L   [R^F-R^P = %-6s L, rho^P = %-4s L,"
                  " rho^F = %-6s L]  De = %s L"
                  % (m, r['n'], Fraction(r['D'], L), g, Fraction(r['rP'], L),
                     Fraction(r['rF'], L), Fraction(r['De'], L)))


if __name__ == "__main__":
    main()
