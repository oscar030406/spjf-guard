"""Two presentational gaps in the write-up, made concrete.

G3: step (2) 'E_old <= R_i, the remaining work at time a_i of the jobs of rank < i'.
    Jobs of rank < i may arrive at EXACTLY a_i (equal arrival, smaller index).  Under
    the pre-arrival reading of 'at time a_i' the step is FALSE.  Count the failures.

G2: step (3) 'over[i] < budget <= C_i + eps*(t-a_i) < C_i + eps*W'.  The last strict
    step needs t_last < start_i.  Count how often an overtaker is dispatched at
    exactly start_i (same dispatch phase, ahead of i) -- those contribute no work to
    [a_i, start_i) and must be excluded by hand for the strictness to be justified.
"""
import sys
sys.dont_write_bytecode = True
import random
from fractions import Fraction
from refsim import simulate

random.seed(2718)
fail_pre = 0
fail_post = 0
same_instant = 0
tot = 0
first = None
for trial in range(40000):
    n = random.randint(2, 8)
    k = random.randint(1, 3)
    L = random.randint(1, 3)
    a = sorted(random.choice([0, 0, 0, 1, 1, 3]) for _ in range(n))
    s = [random.randint(1, L) for _ in range(n)]
    p = [random.randint(0, n) for _ in range(n)]
    B = random.randint(0, n * L)
    st, cp = simulate(a, s, p, k, "guard", B0=B, Bmax=B)
    for i in range(n):
        tot += 1
        lo, hi = a[i], st[i]
        E_old = sum(max(0, min(cp[j], hi) - max(st[j], lo)) for j in range(i))
        Rpost = 0
        Rpre = 0
        for j in range(i):
            if cp[j] <= a[i]:
                r = 0
            elif st[j] <= a[i]:
                r = cp[j] - a[i]
            else:
                r = s[j]
            Rpost += r
            if a[j] < a[i]:
                Rpre += r
        if E_old > Rpre:
            fail_pre += 1
            if first is None:
                first = (a[:], s[:], p[:], k, B, i, E_old, Rpre, Rpost)
        if E_old > Rpost:
            fail_post += 1
        # overtakers dispatched in the very same instant as i
        for j in range(i + 1, n):
            if st[j] == st[i] and st[i] > a[i]:
                same_instant += 1
                break
print("job-checks = %d" % tot)
print("G3  step(2) failures, PRE-arrival reading of R_i : %d" % fail_pre)
print("G3  step(2) failures, POST-arrival reading of R_i: %d" % fail_post)
if first:
    print("    smallest witness: a=%s s=%s pred=%s k=%d B=%d job=%d  E_old=%d "
          "R_pre=%d R_post=%d" % first)
print("G2  jobs with an overtaker dispatched at exactly start_i: %d" % same_instant)
