"""Randomised attack.  Heavy on ties, bursts, all-equal arrivals, s = L, reversed
predictions.  Checks Lemma, Theorem A (with and without a binding cap), Theorem B,
the eps=0 head-check equivalence, and the count-channel corollary."""
import sys
sys.dont_write_bytecode = True
import time
import numpy as np
from numba import njit, prange
import fastkern as F

FCFS, GUARD, HEAD = 0, 1, 2
BIG = 1000000
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


@njit(parallel=True, cache=True)
def attack(seed0, per_thread, nthread, k, NMAX, LMAX, AMAX,
           bestA, bestB, bestAcap, bestN, recA, cnts):
    for th in prange(nthread):
        st = np.empty(1, np.int64)
        st[0] = seed0 + 7919 * (th + 1)
        for _ in range(50):
            rnd(st)
        a = np.empty(NMAX, np.int64)
        s = np.empty(NMAX, np.int64)
        p = np.empty(NMAX, np.int64)
        start = np.empty(NMAX, np.int64)
        comp = np.empty(NMAX, np.int64)
        stf = np.empty(NMAX, np.int64)
        cpf = np.empty(NMAX, np.int64)
        sth = np.empty(NMAX, np.int64)
        cph = np.empty(NMAX, np.int64)
        se = np.empty(k, np.int64)
        sj = np.empty(k, np.int64)
        wt = np.empty(NMAX, np.bool_)
        cw = np.empty(NMAX, np.int64)
        cc = np.empty(NMAX, np.int64)
        vA = -1.0e18
        vB = -1.0e18
        vAc = -1.0e18
        vN = -1.0e18
        c0 = 0
        c1 = 0
        c2 = 0
        c3 = 0
        c4 = 0
        lo = k if k > 2 else 2
        for it in range(per_thread):
            n = ri(st, lo, NMAX)
            L = ri(st, 1, LMAX)
            amode = rnd(st) % 5
            if amode == 0:
                for i in range(n):
                    a[i] = 0
            elif amode == 1:
                for i in range(n):
                    a[i] = ri(st, 0, AMAX)
            elif amode == 2:
                nb = ri(st, 1, 3)
                for i in range(n):
                    a[i] = (rnd(st) % nb) * ri(st, 0, 3)
            elif amode == 3:
                v = 0
                for i in range(n):
                    a[i] = v
                    if rnd(st) % 3 == 0:
                        v += ri(st, 0, 2)
            else:
                for i in range(n):
                    a[i] = (i * ri(st, 0, 2)) % (AMAX + 1)
            for i in range(1, n):
                key = a[i]
                j = i - 1
                while j >= 0 and a[j] > key:
                    a[j + 1] = a[j]
                    j -= 1
                a[j + 1] = key
            smode = rnd(st) % 4
            for i in range(n):
                if smode == 0:
                    s[i] = L
                elif smode == 1:
                    s[i] = ri(st, 1, L)
                elif smode == 2:
                    s[i] = L if rnd(st) % 4 == 0 else 1
                else:
                    s[i] = 1 if rnd(st) % 4 == 0 else L
            pmode = rnd(st) % 4
            for i in range(n):
                if pmode == 0:
                    p[i] = n - 1 - i
                elif pmode == 1:
                    p[i] = ri(st, 0, 2)
                elif pmode == 2:
                    p[i] = ri(st, 0, n)
                else:
                    p[i] = n - 1 - i if rnd(st) % 2 == 0 else ri(st, 0, n)
            B0 = ri(st, 0, n * L + 2)
            emode = rnd(st) % 4
            if emode == 0:
                en = 0
                ed = 1
            elif emode == 1:
                en = 1
                ed = 2
            elif emode == 2:
                en = ri(st, 0, k * 2 - 1)
                ed = 2
            else:
                en = ri(st, 0, k * 4 - 1)
                ed = 4
            cmode = rnd(st) % 3
            Bmax = BIG if cmode == 0 else B0 + ri(st, 0, 4)
            F.sim(a[:n], s[:n], p[:n], k, FCFS, 0, 0, 0, 1, 0, 0, 1,
                  stf[:n], cpf[:n], se, sj, wt[:n], cw[:n], cc[:n])
            F.sim(a[:n], s[:n], p[:n], k, GUARD, B0, Bmax, en, ed, 0, 0, 1,
                  start[:n], comp[:n], se, sj, wt[:n], cw[:n], cc[:n])
            g = F.lemma_gap(a[:n], s[:n], start[:n], comp[:n], stf[:n], cpf[:n])
            if g > (k - 1) * L:
                c2 += 1
            if en == 0:
                F.sim(a[:n], s[:n], p[:n], k, HEAD, B0, Bmax, en, ed, 0, 0, 1,
                      sth[:n], cph[:n], se, sj, wt[:n], cw[:n], cc[:n])
                for i in range(n):
                    if start[i] != sth[i]:
                        c3 += 1
                        break
            for i in range(n):
                Wg = start[i] - a[i]
                Wf = stf[i] - a[i]
                lhs = (k * ed - en) * Wg
                rhs0 = ed * (k * Wf + B0)
                xB = (lhs - rhs0) / (ed * k * L)
                if xB > vB:
                    vB = xB
                if lhs > rhs0 + ed * (3 * k - 2) * L:
                    c0 += 1
                if Bmax < BIG:
                    xA = (k * Wg - k * Wf - Bmax) / (k * L)
                    if xA > vAc:
                        vAc = xA
                    if k * Wg - k * Wf - Bmax > (3 * k - 2) * L:
                        c1 += 1
                if en == 0 and Bmax >= B0:
                    xA = (k * Wg - k * Wf - B0) / (k * L)
                    if xA > vA:
                        vA = xA
                        recA[th, 0] = n
                        recA[th, 1] = L
                        recA[th, 2] = B0
                        recA[th, 3] = i
                        for q in range(n):
                            recA[th, 8 + q] = a[q]
                            recA[th, 8 + NMAX + q] = s[q]
                            recA[th, 8 + 2 * NMAX + q] = p[q]
            Ncap = ri(st, 1, 4)
            F.sim(a[:n], s[:n], p[:n], k, GUARD, 0, 0, 0, 1, Ncap, L, 0,
                  start[:n], comp[:n], se, sj, wt[:n], cw[:n], cc[:n])
            for i in range(n):
                Wg = start[i] - a[i]
                Wf = stf[i] - a[i]
                xN = (k * Wg - k * Wf - Ncap * L) / (k * L)
                if xN > vN:
                    vN = xN
                if k * Wg - k * Wf - Ncap * L > (3 * k - 2) * L:
                    c4 += 1
        bestA[th] = vA
        bestB[th] = vB
        bestAcap[th] = vAc
        bestN[th] = vN
        cnts[th, 0] = c0
        cnts[th, 1] = c1
        cnts[th, 2] = c2
        cnts[th, 3] = c3
        cnts[th, 4] = c4


def main():
    total = int(sys.argv[1])
    ks = [int(x) for x in sys.argv[2].split(",")]
    NMAX = int(sys.argv[3])
    LMAX = int(sys.argv[4])
    AMAX = int(sys.argv[5])
    seed = int(sys.argv[6])
    nth = 4
    per = total // nth
    for k in ks:
        bestA = np.empty(nth)
        bestB = np.empty(nth)
        bestAcap = np.empty(nth)
        bestN = np.empty(nth)
        recA = np.zeros((nth, 8 + 3 * NMAX), np.int64)
        cnts = np.zeros((nth, 5), np.int64)
        t0 = time.time()
        attack(seed + 1013 * k, per, nth, k, NMAX, LMAX, AMAX,
               bestA, bestB, bestAcap, bestN, recA, cnts)
        dt = time.time() - t0
        j = int(np.argmax(bestA))
        n = recA[j, 0]
        print("k=%d  instances=%d  %.1fs" % (k, per * nth, dt), flush=True)
        print("   violations: ThmB=%d ThmA(cap)=%d Lemma=%d head-equiv(eps=0)=%d "
              "count-channel=%d"
              % (cnts[:, 0].sum(), cnts[:, 1].sum(), cnts[:, 2].sum(),
                 cnts[:, 3].sum(), cnts[:, 4].sum()), flush=True)
        print("   max c: ThmA=%.4f ThmA(capped)=%.4f ThmB=%.4f count-ch=%.4f "
              "(claim <= %.4f)"
              % (bestA.max(), bestAcap.max(), bestB.max(), bestN.max(), 3 - 2 / k),
              flush=True)
        print("   ThmA argmax n=%d L=%d B=%d job=%d a=%s s=%s p=%s"
              % (n, recA[j, 1], recA[j, 2], recA[j, 3],
                 recA[j, 8:8 + n].tolist(),
                 recA[j, 8 + NMAX:8 + NMAX + n].tolist(),
                 recA[j, 8 + 2 * NMAX:8 + 2 * NMAX + n].tolist()), flush=True)


main()
