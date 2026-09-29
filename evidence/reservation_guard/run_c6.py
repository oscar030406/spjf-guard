"""C6.  Narrowing the maximality gap numerically, for both charging rules.

E(B) = max excess over every instance in a finite family and every base policy
(enum_runs branches over all of them).  E is non-decreasing in B because the
permitted set grows with B under both rules.  Then

    B*_emp(G) = max { B : E(B) <= G }

is an UPPER bound on the true largest promise-G constant budget (the family is
finite, the real worst case needs hundreds of jobs).  Proved lower bounds:
rule C, B >= kG - (3k-2)L (Cor. "params");  rule R, B >= kG - (2k-2)L (C1).
Adversary upper bound quoted in the task: k(G-L).

    env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME \
        uv run --no-project --with numpy python run_c6.py
"""
import sys
import itertools

sys.dont_write_bytecode = True
import rguard  # noqa: E402


def E_table(rule, k, L, n, sizes, arrivals, bmax, capmode):
    E = {B: 0 for B in range(bmax + 1)}
    runs = 0
    for a in arrivals:
        for x in itertools.product(sizes, repeat=n):
            jobs = list(zip(a, x))
            ell = ([L] * n if capmode == 'L' else list(x)) \
                if rule == 'R' else None
            for B in range(bmax + 1):
                for order, start in rguard.enum_runs(jobs, k, rule, B, ell):
                    runs += 1
                    In, Out, W, WF, exc = rguard.metrics(jobs, k, order, start)
                    m = max(exc)
                    if m > E[B]:
                        E[B] = m
    return E, runs


def main():
    L = 3
    n = 5
    sizes = (1, 2, 3)
    arrivals = [(0,) * n, (0, 0, 0, 1, 1)]
    bmax = 12
    print("=" * 78)
    print("C6  E(B) = worst excess over all base policies, n=%d L=%d sizes%s"
          % (n, L, sizes))
    print("=" * 78)
    tabs = {}
    for k in (1, 2):
        for rule, capmode, tag in (('C', None, 'C (completed work)'),
                                   ('R', 'L', 'R, ell = L'),
                                   ('R', 'C', 'R, ell = C')):
            E, runs = E_table(rule, k, L, n, sizes, arrivals, bmax, capmode)
            tabs[(k, tag)] = E
            print()
            print("k=%d  rule %-20s  (%d runs)" % (k, tag, runs))
            print("   B    : %s" % "  ".join("%2d" % B for B in
                                             range(bmax + 1)))
            print("   E(B) : %s" % "  ".join("%2d" % E[B] for B in
                                             range(bmax + 1)))
    print()
    print("=" * 78)
    print("largest constant budget with promise G (upper bound from this "
          "family)")
    print("=" * 78)
    for k in (1, 2):
        print()
        print("k = %d   proved lower bounds: rule C  kG-(3k-2)L , "
              "rule R  kG-(2k-2)L ;  adversary upper bound k(G-L)" % k)
        hdr = ["G"] + [t for (kk, t) in sorted(tabs) if kk == k] + \
              ["kG-(3k-2)L", "kG-(2k-2)L", "k(G-L)"]
        print("   " + "  ".join("%-20s" % h for h in hdr))
        for G in range(L, 5 * L + 1):
            row = ["%d" % G]
            for (kk, t) in sorted(tabs):
                if kk != k:
                    continue
                E = tabs[(kk, t)]
                ok = [B for B in range(bmax + 1) if E[B] <= G]
                row.append("%s%s" % (max(ok) if ok else "-",
                                     "+" if (ok and max(ok) == bmax) else ""))
            row.append("%d" % (k * G - (3 * k - 2) * L))
            row.append("%d" % (k * G - (2 * k - 2) * L))
            row.append("%d" % (k * (G - L)))
            print("   " + "  ".join("%-20s" % c for c in row))
    print()
    print("'+' means the search grid ran out (B = %d still safe on this "
          "family), so the entry is only a lower bound on B*_emp." % bmax)


if __name__ == "__main__":
    main()
