"""C1b.  Is the residual (2-2/k)L still attained under rule R at k >= 2?

Runs the S8.2 upward witness (imported unmodified from
evidence/guard_theory/family_tight.py) inside both wrappers, with the budget
of Theorem "tight2" part (ii), B = f + L + 1 where f = rho_m/(k-1), and reports
(k*excess - B)/L for the victim.  Rule C's supremum is 3k-2; rule R should lose
exactly the kL overshoot and sit at 2k-2.

    env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME \
        uv run --no-project --with numpy python run_c1b.py
"""
import sys
from fractions import Fraction

sys.dont_write_bytecode = True
import rguard  # noqa: E402
import sim_core  # noqa: E402
import family_tight  # noqa: E402


def prio_chooser(prio):
    def f(t, waiting, state):
        best = 0
        for c in range(1, len(waiting)):
            if prio[waiting[c]] < prio[waiting[best]]:
                best = c
        return best
    return f


def main():
    print("=" * 78)
    print("C1b  the S8.2 upward witness inside both wrappers")
    print("=" * 78)
    print("%-3s %-5s %-3s %-6s %-5s %-6s %-11s %-11s %-11s %s"
          % ("k", "L", "m", "n", "f", "B", "(k e-B)/L R", "(k e-B)/L C",
             "In_R", "In_C"))
    for k in (2, 3, 4):
        L = k ** 4
        for m in (1, 2, 3, 4):
            f = family_tight.rho_seq(k, L, m)[m] // (k - 1)
            B = f + L + 1
            jobs, prio, v = family_tight.build_upper(
                k, L, m, s=1, ntiny=2 * k * L + 2 * B + 4)
            n = len(jobs)
            x = [j[1] for j in jobs]
            base = prio_chooser(prio)
            row = {}
            for tag, wrap in (('R', rguard.make_rguard(base, B, x)),
                              ('C', rguard.make_cguard(base, B))):
                sP, oP, _ = sim_core.simulate(jobs, k, wrap)
                In, Out, W, WF, exc = rguard.metrics(jobs, k, oP, sP)
                row[tag] = (Fraction(k * exc[v] - B, L), In[v], exc[v])
            print("%-3d %-5d %-3d %-6d %-5d %-6d %-11s %-11s %-11d %d"
                  % (k, L, m, n, f, B, row['R'][0], row['C'][0],
                     row['R'][1], row['C'][1]))
        print("   k=%d: rule R target 2k-2 = %d ; rule C target 3k-2 = %d ; "
              "B/k + (2-2/k)L and B/k + (3-2/k)L respectively"
              % (k, 2 * k - 2, 3 * k - 2))


if __name__ == "__main__":
    main()
