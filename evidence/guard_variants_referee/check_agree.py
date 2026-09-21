import sys
sys.dont_write_bytecode = True
import random
import numpy as np
from fractions import Fraction
from refsim import simulate
import fastkern as F

random.seed(7)
scr = None
bad = 0
for trial in range(20000):
    n = random.randint(1, 7)
    k = random.randint(1, 4)
    L = random.choice([2, 3, 4])
    a = sorted(random.randint(0, 5) for _ in range(n))
    s = [random.randint(1, L) for _ in range(n)]
    pr = [random.randint(0, n) for _ in range(n)]
    en, ed = random.choice([(0, 1), (1, 2), (1, 1), (2 * k - 1, 2), (3, 4)])
    B0 = random.randint(0, 8)
    Bmax = B0 + random.choice([0, 0, 2, 100])
    Ncap = random.choice([0, 0, 0, 1, 2, 3])
    theta = random.choice([0, 0, 0, 1, 2])
    uw = random.choice([0, 1, 1, 1])
    pol = random.choice([0, 1])
    aa = np.array(a, dtype=np.int64); ss = np.array(s, dtype=np.int64)
    pp = np.array(pr, dtype=np.int64)
    st = np.empty(n, np.int64); cp = np.empty(n, np.int64)
    se = np.empty(k, np.int64); sj = np.empty(k, np.int64)
    wt = np.empty(n, np.bool_); cw = np.empty(n, np.int64); cc = np.empty(n, np.int64)
    F.sim(aa, ss, pp, k, pol, B0, Bmax, en, ed, Ncap, theta, uw,
          st, cp, se, sj, wt, cw, cc)
    rst, rcp = simulate(a, s, pr, k, "guard" if pol == 1 else "fcfs",
                        B0=B0, Bmax=Bmax, eps=Fraction(en, ed), Ncap=Ncap,
                        theta=theta, use_work=(uw == 1))
    if list(st) != rst or list(cp) != rcp:
        bad += 1
        print("MISMATCH", a, s, pr, k, pol, B0, Bmax, en, ed, Ncap, theta, uw)
        print("  fast", list(st), "ref", rst)
        if bad > 3:
            break
print("agreement check done, mismatches =", bad)
