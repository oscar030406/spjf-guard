"""LAST STEP ONLY: run the colleague's kernel on 1000 of my random instances and
compare the per-job waits against my own pure-python reference simulator.

Nothing in the referee's own numbers depends on this file.
"""
import sys
sys.dont_write_bytecode = True
import os
import random
from fractions import Fraction
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "guard_variants"))
import guardkern as GK
from refsim import simulate

random.seed(20260919)
N = 1000
mismatch = 0
first = None
cases = 0
for trial in range(N):
    n = random.randint(2, 12)
    k = random.randint(1, 4)
    L = random.randint(1, 5)
    mode = random.randint(0, 2)
    if mode == 0:
        a = [0] * n
    elif mode == 1:
        a = sorted(random.randint(0, 6) for _ in range(n))
    else:
        a = sorted(random.choice([0, 0, 1, 3, 3, 7]) for _ in range(n))
    s = [random.choice([L, random.randint(1, L)]) for _ in range(n)]
    pred = [float(random.randint(0, n)) for _ in range(n)]
    B = random.randint(0, n * L + 2)
    epsc = [Fraction(0), Fraction(1, 2), Fraction(1), Fraction(2 * k - 1, 2)]
    eps = random.choice([e for e in epsc if e < k])
    pol = random.choice(["fcfs", "guard"])
    mine, _ = simulate(a, s, pred, k, "guard" if pol == "guard" else "fcfs",
                       B0=B, Bmax=10 ** 9, eps=eps)
    Wmine = [mine[i] - a[i] for i in range(n)]
    r = GK.run(np.array(a, float), np.array(s, float), k, policy=pol,
               pred=np.array(pred, float), B=float(B), eps=float(eps),
               gam=0.0, theta=0.0, Ncap=0, Bmax=0.0)
    His = [float(x) for x in r.w]
    cases += 1
    ok = (r.err == 0) and all(abs(His[i] - Wmine[i]) < 1e-9 for i in range(n))
    if not ok:
        mismatch += 1
        if first is None:
            first = (a, s, pred, k, B, str(eps), pol, Wmine, His, int(r.err))
print("instances compared: %d" % cases)
print("job-by-job wait mismatches: %d" % mismatch)
if first is not None:
    print("first mismatch:")
    print("  a=%s\n  s=%s\n  pred=%s\n  k=%d B=%d eps=%s policy=%s err=%d"
          % (first[0], first[1], first[2], first[3], first[4], first[5],
             first[6], first[9]))
    print("  mine=%s\n  his =%s" % (first[7], first[8]))

# --- second pass: with the cap Bmax and with the count channel (theta, Ncap) ---
random.seed(424242)
m2 = 0
f2 = None
for trial in range(1000):
    n = random.randint(2, 12)
    k = random.randint(1, 4)
    L = random.randint(1, 5)
    a = sorted(random.choice([0, 0, 1, 2, 5]) for _ in range(n))
    s = [random.randint(1, L) for _ in range(n)]
    pred = [float(random.randint(0, n)) for _ in range(n)]
    B = random.randint(0, n * L)
    Bmax = B + random.choice([1, 3, 8])
    theta = random.choice([0, 1, 2])
    Ncap = random.choice([0, 1, 2, 3])
    epsc = [Fraction(0), Fraction(1, 2), Fraction(2 * k - 1, 2)]
    eps = random.choice([e for e in epsc if e < k])
    mine, _ = simulate(a, s, pred, k, "guard", B0=B, Bmax=Bmax, eps=eps,
                       Ncap=Ncap, theta=theta)
    Wm = [mine[i] - a[i] for i in range(n)]
    r = GK.run(np.array(a, float), np.array(s, float), k, policy="guard",
               pred=np.array(pred, float), B=float(B), eps=float(eps), gam=0.0,
               theta=float(theta), Ncap=Ncap, Bmax=float(Bmax))
    Hw = [float(x) for x in r.w]
    if r.err != 0 or any(abs(Hw[i] - Wm[i]) > 1e-9 for i in range(n)):
        m2 += 1
        if f2 is None:
            f2 = (a, s, pred, k, B, Bmax, theta, Ncap, str(eps), Wm, Hw, int(r.err))
print("pass 2 (cap + count channel): instances=1000 mismatches=%d" % m2)
if f2 is not None:
    print("  a=%s\n  s=%s\n  pred=%s\n  k=%d B=%d Bmax=%d theta=%d Ncap=%d eps=%s err=%d"
          % (f2[0], f2[1], f2[2], f2[3], f2[4], f2[5], f2[6], f2[7], f2[8], f2[11]))
    print("  mine=%s\n  his =%s" % (f2[9], f2[10]))
