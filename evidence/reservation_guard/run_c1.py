"""C1.  In_i <= B under rule R (no overshoot), and the resulting excess bound.

Exhaustive over ALL base policies (enum_runs branches over every proposal the
wrapper permits), over small instances, for both charging rules.

Checks per job i of every enumerated run:
  A  In_i <= Z_i                                           (rule R invariant)
  B  k*excess_i <= Z_i + Lam_{k-1}(a_i) + Lam^{<i}_{k-1}   (instance form)
  C  k*excess_i <= Z_i + (2k-2)L                           (uniform form, R)
  D  k*excess_i <  Z_i + (3k-2)L                           (the paper's bound)
and records the attained suprema of (k*excess_i - Z_i)/L and In_i - Z_i.

    env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME \
        uv run --no-project --with numpy python run_c1.py
"""
import sys
import itertools
from collections import Counter
from fractions import Fraction

sys.dont_write_bytecode = True
import rguard  # noqa: E402


def cap_profiles(x, L):
    yield 'ell=C  (clairvoyant)', list(x)
    yield 'ell=L  (oblivious)', [L] * len(x)
    yield 'ell=min(L,C+1)', [min(L, c + 1) for c in x]


def lam_pair(jobs, k, i):
    """Lam_{k-1}(a_i) and Lam^{<i}_{k-1} of verification.md section 8."""
    a = [j[0] for j in jobs]
    x = [j[1] for j in jobs]
    hi = sorted((x[j] for j in range(len(jobs)) if a[j] <= a[i]),
                reverse=True)[:k - 1]
    lo = sorted((x[j] for j in range(i)), reverse=True)[:k - 1]
    return sum(hi), sum(lo)


def sweep(rule, arrivals, sizes_pool, L, ks, budgets, n):
    worst = {}
    viol = []
    runs = 0
    jobcount = 0
    for a in arrivals:
        for x in itertools.product(sizes_pool, repeat=n):
            jobs = list(zip(a, x))
            for cname, ell in cap_profiles(x, L):
                if rule == 'C' and cname != 'ell=C  (clairvoyant)':
                    continue                     # rule C ignores caps
                for k in ks:
                    for B in budgets:
                        for order, start in rguard.enum_runs(
                                jobs, k, rule, B, ell):
                            runs += 1
                            In, Out, W, WF, exc = rguard.metrics(
                                jobs, k, order, start)
                            for i in range(n):
                                jobcount += 1
                                lhi, llo = lam_pair(jobs, k, i)
                                key = (rule, cname, k)
                                w = worst.setdefault(
                                    key, dict(dIn=-10 ** 9, ratio=None,
                                              inst=-10 ** 9))
                                w['dIn'] = max(w['dIn'], In[i] - B)
                                r = Fraction(k * exc[i] - B, L)
                                if w['ratio'] is None or r > w['ratio']:
                                    w['ratio'] = r
                                w['inst'] = max(w['inst'],
                                                k * exc[i] - B - lhi - llo)
                                rec = (rule, cname, jobs, ell, k, B, i)
                                if rule == 'R' and In[i] > B:
                                    viol.append(('A',) + rec)
                                if k * exc[i] > B + lhi + llo:
                                    viol.append(('B',) + rec)
                                if rule == 'R' and \
                                        k * exc[i] > B + (2 * k - 2) * L:
                                    viol.append(('C',) + rec)
                                if k * exc[i] >= B + (3 * k - 2) * L:
                                    viol.append(('D',) + rec)
    return worst, viol, runs, jobcount


def block(title, arrivals, sizes, L, ks, budgets, n):
    print()
    print("=" * 78)
    print("%s  n=%d L=%d sizes%s k%s B%s" % (title, n, L, sizes, ks, budgets))
    print("=" * 78)
    allviol = []
    tr = tj = 0
    for rule in ('R', 'C'):
        worst, viol, runs, jc = sweep(rule, arrivals, sizes, L, ks, budgets, n)
        allviol += viol
        tr += runs
        tj += jc
        print()
        print("rule %s : %d enumerated runs, %d job checks" % (rule, runs, jc))
        for key in sorted(worst, key=lambda z: (z[1], z[2])):
            w = worst[key]
            print("   %-22s k=%d  max(In_i-B)=%-4d  max (k*exc-B)/L=%-6s  "
                  "max (k*exc-B-Lam_hi-Lam_lo)=%d"
                  % (key[1], key[2], w['dIn'], w['ratio'], w['inst']))
    print()
    print("violations by (check, rule): %s"
          % dict(Counter((v[0], v[1]) for v in allviol)))
    print("reference: 2k-2 = %s , 3k-2 = %s for k%s"
          % ([2 * k - 2 for k in ks], [3 * k - 2 for k in ks], ks))
    print("block total %d runs, %d job checks" % (tr, tj))
    return allviol


def main():
    v1 = block("C1 sweep 1", [(0, 0, 0, 0), (0, 0, 1, 1), (0, 1, 1, 2),
                              (0, 0, 0, 1), (0, 1, 2, 2)],
               (1, 2, 3), 3, (1, 2, 3), (0, 1, 2, 3, 4, 5, 6), 4)
    v2 = block("C1 sweep 2", [(0, 0, 0, 0, 0), (0, 0, 1, 1, 2),
                              (0, 1, 1, 2, 3)],
               (1, 3), 3, (1, 2, 3, 4), (0, 1, 2, 3, 4, 6), 5)
    bad = [v for v in v1 + v2 if v[1] == 'R']
    print()
    print("RULE-R VIOLATIONS OVER BOTH SWEEPS: %d" % len(bad))
    for v in bad[:5]:
        print("   ", v)


if __name__ == "__main__":
    main()
