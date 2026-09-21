"""Hill-climb / annealing adversary.

Objective 1 (tightness of the additive constant), eps = 0, budget B:
    obj = k*W_guard[i] - k*W_FCFS[i] - (B-1)        maximised over jobs i
(B-1 and not B because with integer services a real budget in (B-1, B] produces the
same schedule as the integer budget B while allowing only B-1+ ; so this is the
supremum of  k*Wg - k*Wf - B  over all REAL budgets.)
Claimed ceiling: (3k-2)*L.

Objective 2: the used/allowed ratio  (k*Wg - k*Wf) / (B + (3k-2)L).

Any objective above the ceiling is a counterexample and is dumped in full.
"""
import sys
sys.dont_write_bytecode = True
import time
import numpy as np
from numba import njit, prange
import fastkern as F

FCFS, GUARD = 0, 1
MASK = 0xFFFFFFFFFFFFFFFF


@njit(inline="always")
def rnd(st):
    x = st[0]
    x ^= (x << 13) & MASK
    x ^= (x >> 7)
    x ^= (x << 17) & MASK
    st[0] = x
    return (x >> 11) & 0x1FFFFFFFFFFFFF


@njit(inline="always")
def ri(st, lo, hi):
    return lo + rnd(st) % (hi - lo + 1)


@njit
def evaluate(a, s, p, n, k, B, L, obj, start, comp, stf, cpf, se, sj, wt, cw, cc):
    F.sim(a[:n], s[:n], p[:n], k, FCFS, 0, 0, 0, 1, 0, 0, 1,
          stf[:n], cpf[:n], se, sj, wt[:n], cw[:n], cc[:n])
    F.sim(a[:n], s[:n], p[:n], k, GUARD, B, B, 0, 1, 0, 0, 1,
          start[:n], comp[:n], se, sj, wt[:n], cw[:n], cc[:n])
    best = -1000000
    bratio = -1.0e18
    for i in range(n):
        d = k * (start[i] - a[i]) - k * (stf[i] - a[i])
        v = d - (B - 1)
        if v > best:
            best = v
        r = d / (B + (3 * k - 2) * L)
        if r > bratio:
            bratio = r
    if obj == 0:
        return best * 1.0
    return bratio


@njit(parallel=True, cache=True)
def anneal(seed0, nrestart, nstep, k, n, L, AMAX, obj,
           outv, outa, outs, outp, outB):
    for r in prange(nrestart):
        st = np.empty(1, np.int64)
        st[0] = seed0 + 104729 * (r + 1)
        for _ in range(60):
            rnd(st)
        a = np.empty(n, np.int64)
        s = np.empty(n, np.int64)
        p = np.empty(n, np.int64)
        start = np.empty(n, np.int64)
        comp = np.empty(n, np.int64)
        stf = np.empty(n, np.int64)
        cpf = np.empty(n, np.int64)
        se = np.empty(k, np.int64)
        sj = np.empty(k, np.int64)
        wt = np.empty(n, np.bool_)
        cw = np.empty(n, np.int64)
        cc = np.empty(n, np.int64)
        for i in range(n):
            a[i] = ri(st, 0, AMAX)
            s[i] = ri(st, 1, L)
            p[i] = ri(st, 0, n)
        for i in range(1, n):
            key = a[i]
            j = i - 1
            while j >= 0 and a[j] > key:
                a[j + 1] = a[j]
                j -= 1
            a[j + 1] = key
        B = ri(st, 1, n * L)
        cur = evaluate(a, s, p, n, k, B, L, obj, start, comp, stf, cpf,
                       se, sj, wt, cw, cc)
        bv = cur
        ba = a.copy()
        bs = s.copy()
        bp = p.copy()
        bB = B
        for step in range(nstep):
            mv = rnd(st) % 5
            i1 = ri(st, 0, n - 1)
            i2 = ri(st, 0, n - 1)
            oa = a[i1]
            os_ = s[i1]
            op = p[i1]
            op2 = p[i2]
            oB = B
            if mv == 0:
                a[i1] = ri(st, 0, AMAX)
                for i in range(1, n):
                    key = a[i]
                    j = i - 1
                    while j >= 0 and a[j] > key:
                        a[j + 1] = a[j]
                        j -= 1
                    a[j + 1] = key
            elif mv == 1:
                s[i1] = ri(st, 1, L)
            elif mv == 2:
                p[i1] = op2
                p[i2] = op
            elif mv == 3:
                p[i1] = ri(st, 0, n)
            else:
                B = B + (1 if rnd(st) % 2 == 0 else -1)
                if B < 1:
                    B = 1
                if B > n * L + 1:
                    B = n * L + 1
            new = evaluate(a, s, p, n, k, B, L, obj, start, comp, stf, cpf,
                           se, sj, wt, cw, cc)
            acc = new >= cur
            if not acc:
                # occasional uphill move (fixed small temperature)
                if rnd(st) % 100 < 4:
                    acc = True
            if acc:
                cur = new
                if new > bv:
                    bv = new
                    for q in range(n):
                        ba[q] = a[q]
                        bs[q] = s[q]
                        bp[q] = p[q]
                    bB = B
            else:
                if mv == 0:
                    # restore by full copy from best-known ordering is wrong; redo sort
                    a[i1] = oa
                    for i in range(1, n):
                        key = a[i]
                        j = i - 1
                        while j >= 0 and a[j] > key:
                            a[j + 1] = a[j]
                            j -= 1
                        a[j + 1] = key
                elif mv == 1:
                    s[i1] = os_
                elif mv == 2:
                    p[i1] = op
                    p[i2] = op2
                elif mv == 3:
                    p[i1] = op
                else:
                    B = oB
        outv[r] = bv
        outB[r] = bB
        for q in range(n):
            outa[r, q] = ba[q]
            outs[r, q] = bs[q]
            outp[r, q] = bp[q]


def main():
    ks = [int(x) for x in sys.argv[1].split(",")]
    ns = [int(x) for x in sys.argv[2].split(",")]
    Ls = [int(x) for x in sys.argv[3].split(",")]
    nrestart = int(sys.argv[4])
    nstep = int(sys.argv[5])
    obj = int(sys.argv[6])
    seed = int(sys.argv[7])
    for k in ks:
        gbest = -1e18
        grec = None
        for n in ns:
            if n < k:
                continue
            for L in Ls:
                AMAX = 2 * n
                outv = np.empty(nrestart)
                outa = np.zeros((nrestart, n), np.int64)
                outs = np.zeros((nrestart, n), np.int64)
                outp = np.zeros((nrestart, n), np.int64)
                outB = np.zeros(nrestart, np.int64)
                t0 = time.time()
                anneal(seed + 7 * k + 131 * n + 977 * L, nrestart, nstep, k, n, L,
                       AMAX, obj, outv, outa, outs, outp, outB)
                dt = time.time() - t0
                j = int(np.argmax(outv))
                if obj == 0:
                    c = outv[j] / (k * L)
                else:
                    c = outv[j]
                if c > gbest:
                    gbest = c
                    grec = (n, L, int(outB[j]), outa[j].tolist(), outs[j].tolist(),
                            outp[j].tolist(), outv[j])
                print("  k=%d n=%2d L=%2d  best=%8.3f  c=%.5f  (%.1fs)"
                      % (k, n, L, outv[j], c, dt), flush=True)
        lim = (3 - 2 / k) if obj == 0 else 1.0
        print("k=%d  OBJ%d  global best c = %.6f   claimed ceiling = %.6f   %s"
              % (k, obj, gbest, lim, "VIOLATION" if gbest > lim + 1e-12 else "ok"),
              flush=True)
        print("     conj (2-1/k) = %.6f   at n=%d L=%d B=%d" % (2 - 1 / k, grec[0],
                                                                grec[1], grec[2]),
              flush=True)
        print("     a=%s\n     s=%s\n     p=%s" % (grec[3], grec[4], grec[5]), flush=True)


main()
