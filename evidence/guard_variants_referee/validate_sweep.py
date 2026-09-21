from headrule import head_rule
"""Recompute the sweep's headline numbers on a small subspace with the pure-python
reference simulator only, and compare.  Guards against the fast sweep silently
doing nothing."""
import sys
sys.dont_write_bytecode = True
import itertools
from fractions import Fraction
from refsim import simulate, workload

n, L, amax, K = 4, 2, 1, [1, 2, 3]
arrs = list(itertools.combinations_with_replacement(range(amax + 1), n))
srvs = list(itertools.product(range(1, L + 1), repeat=n))
perms = list(itertools.permutations(range(n)))
Bhi = n * L + 1
for k in K:
    mx = -10**9; mx2 = -10**9; nv = 0; nl = 0; nh = 0; nsim = 0
    for a in arrs:
        for s in srvs:
            stf, cpf = simulate(list(a), list(s), list(perms[0]), k, "fcfs")
            for p in perms:
                for B in range(Bhi + 1):
                    st, cp = simulate(list(a), list(s), list(p), k, "guard", B0=B, Bmax=B)
                    nsim += 1
                    # head-check rule, written out here independently
                    sth = head_rule(list(a), list(s), list(p), k, B)
                    if st != sth:
                        nh += 1
                    T = max(max(cp), max(cpf))
                    for t in range(T + 1):
                        g = abs(workload(a, s, st, cp, t) - workload(a, s, stf, cpf, t))
                        if g > (k - 1) * L:
                            nl += 1
                    for i in range(n):
                        d = k * (st[i] - a[i]) - k * (stf[i] - a[i])
                        mx = max(mx, d - B)
                        mx2 = max(mx2, d - (B - 1 if B >= 1 else 0))
                        if d - B > (3 * k - 2) * L:
                            nv += 1
    print("k=%d sims=%d maxA/L=%.4f supform/L=%.4f viol=%d lemma=%d headmismatch=%d"
          % (k, nsim, mx / L, mx2 / L, nv, nl, nh))
