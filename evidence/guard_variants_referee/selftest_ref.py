import sys
sys.dont_write_bytecode = True
import random
from fractions import Fraction
from refsim import simulate, workload, rank_order

random.seed(1)
bad = 0
for trial in range(4000):
    n = random.randint(1, 6)
    k = random.randint(1, 3)
    L = random.choice([2, 3])
    a = sorted(random.randint(0, 4) for _ in range(n))
    s = [random.randint(1, L) for _ in range(n)]
    pr = list(range(n)); random.shuffle(pr)
    # B = 0 must reproduce FCFS exactly (over[q] >= 0 always fires)
    g0, _ = simulate(a, s, pr, k, "guard", B0=0, Bmax=0)
    f0, _ = simulate(a, s, pr, k, "fcfs")
    if g0 != f0:
        bad += 1; print("B=0 != FCFS", a, s, pr, k, g0, f0); break
    # huge B must never fire -> pure smallest-prediction
    gH, _ = simulate(a, s, pr, k, "guard", B0=10**6, Bmax=10**6)
    gH2, _ = simulate(a, s, pr, k, "guard", B0=10**6, Bmax=10**6, eps=Fraction(1,2))
    if gH != gH2:
        bad += 1; print("huge B eps-dependence", a, s, pr, k); break
    # every job starts after it arrives, services non-overlapping per server count
    st, cp = simulate(a, s, pr, k, "guard", B0=2, Bmax=2)
    for j in range(n):
        assert st[j] >= a[j] and cp[j] == st[j] + s[j]
    T = max(cp)
    for t in range(0, T + 1):
        busy = sum(1 for j in range(n) if st[j] <= t < cp[j])
        wait = sum(1 for j in range(n) if a[j] <= t < st[j])
        assert busy <= k, (a, s, pr, k, t)
        assert not (busy < k and wait > 0), ("idle server with waiting job", a, s, pr, k, t)
    # work conservation: total work executed equals sum s
    assert sum(cp[j]-st[j] for j in range(n)) == sum(s)
print("selftest done, failures =", bad)
