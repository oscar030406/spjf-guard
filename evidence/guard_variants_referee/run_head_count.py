"""Head-check equivalence in the special case, including the count channel
(finite-skip rule): is min-rank-fired == 'test the head only' whenever every job
has the SAME threshold?  Also re-tested with eps>0, where it should FAIL."""
import sys
sys.dont_write_bytecode = True
import random
import numpy as np
import fastkern as F

random.seed(31415)
diff_const = 0
diff_eps = 0
n_const = 0
n_eps = 0
for trial in range(400000):
    n = random.randint(2, 10)
    k = random.randint(1, 4)
    L = random.randint(1, 4)
    m = random.randint(0, 2)
    if m == 0:
        a = [0] * n
    elif m == 1:
        a = sorted(random.randint(0, 5) for _ in range(n))
    else:
        a = sorted(random.choice([0, 0, 2, 2, 5]) for _ in range(n))
    s = [random.randint(1, L) for _ in range(n)]
    p = [random.randint(0, n) for _ in range(n)]
    B = random.randint(0, n * L + 1)
    theta = random.choice([0, 0, 1, 2, L])
    Ncap = 0 if theta == 0 else random.randint(1, 3)
    uw = random.choice([0, 1]) if Ncap > 0 else 1
    en, ed = random.choice([(0, 1), (0, 1), (1, 2), (2 * k - 1, 2)])
    if en >= k * ed:
        en, ed = 0, 1
    aa = np.array(a, np.int64); ss = np.array(s, np.int64); pp = np.array(p, np.int64)
    o = [np.empty(n, np.int64) for _ in range(4)]
    se = np.empty(k, np.int64); sj = np.empty(k, np.int64)
    wt = np.empty(n, np.bool_); cw = np.empty(n, np.int64); cc = np.empty(n, np.int64)
    BM = B if en == 0 else 10**9
    F.sim(aa, ss, pp, k, 1, B, BM, en, ed, Ncap, theta, uw, o[0], o[1], se, sj, wt, cw, cc)
    F.sim(aa, ss, pp, k, 2, B, BM, en, ed, Ncap, theta, uw, o[2], o[3], se, sj, wt, cw, cc)
    same = bool((o[0] == o[2]).all())
    if en == 0:
        n_const += 1
        if not same:
            diff_const += 1
            if diff_const == 1:
                print("CONST-BUDGET MISMATCH a=%s s=%s p=%s k=%d B=%d theta=%d Ncap=%d "
                      "uw=%d\n  minrank=%s\n  head   =%s"
                      % (a, s, p, k, B, theta, Ncap, uw, o[0].tolist(), o[2].tolist()))
    else:
        n_eps += 1
        if not same:
            diff_eps += 1
print("constant budget (eps=0, incl. count channel): %d cases, head-rule differs in %d"
      % (n_const, diff_const))
print("eps>0 (equivalence NOT claimed):              %d cases, head-rule differs in %d"
      % (n_eps, diff_eps))
