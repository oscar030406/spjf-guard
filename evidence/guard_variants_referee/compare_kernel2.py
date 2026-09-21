"""Pass 2 rerun.  His kernel sets use_cnt = (theta>0 and Ncap>0): with Ncap = 0 the
theta split is switched OFF and short overtakers charge the WORK channel.  My
simulator, reading the written spec literally, always diverts s<=theta away from the
work channel.  That corner (theta>0, Ncap=0) is exactly the 'NOT GUARANTEED' regime.
Here: (i) count how many mismatches live in that corner, (ii) re-test with
Ncap >= 1 whenever theta > 0, (iii) re-test the corner with theta forced off on my
side, which is his semantics."""
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

for tag, force in (("as-written (theta>0 allowed with Ncap=0)", False),
                   ("his semantics: theta ignored when Ncap=0", True)):
    random.seed(424242)
    m = 0
    mcorner = 0
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
        th_mine = 0 if (force and Ncap == 0) else theta
        mine, _ = simulate(a, s, pred, k, "guard", B0=B, Bmax=Bmax, eps=eps,
                           Ncap=Ncap, theta=th_mine)
        Wm = [mine[i] - a[i] for i in range(n)]
        r = GK.run(np.array(a, float), np.array(s, float), k, policy="guard",
                   pred=np.array(pred, float), B=float(B), eps=float(eps), gam=0.0,
                   theta=float(theta), Ncap=Ncap, Bmax=float(Bmax))
        Hw = [float(x) for x in r.w]
        if r.err != 0 or any(abs(Hw[i] - Wm[i]) > 1e-9 for i in range(n)):
            m += 1
            if theta > 0 and Ncap == 0:
                mcorner += 1
    print("%-46s mismatches=%d  (of which theta>0 & Ncap=0: %d)" % (tag, m, mcorner))
