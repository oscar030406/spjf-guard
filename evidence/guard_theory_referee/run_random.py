"""Large random attack on Theorem 1 / Cor 1.1 / Cor 1.2 / Lemma 2 / Theorem 2
/ Theorem 4, with the policy drawn from many families including a uniformly
random work-conserving dispatcher (which covers EVERY policy in the limit).

Exact integers.  Per (k) we keep the worst observed |D|/L as an exact pair
(|D|, L) and compare ratios by cross-multiplication.

usage: run_random.py [blocks] [per_block]
"""
import sys, time
sys.dont_write_bytecode = True
import numpy as np
from numba import njit, prange, set_num_threads
import fastsim as F

MAXN = 14
MAXK = 6
NK = MAXK + 1


@njit(inline='always')
def rnd(st):
    x = st[0]
    x ^= (x << np.uint64(13)) & np.uint64(0xFFFFFFFFFFFFFFFF)
    x ^= (x >> np.uint64(7))
    x ^= (x << np.uint64(17)) & np.uint64(0xFFFFFFFFFFFFFFFF)
    st[0] = x
    return np.int64(x >> np.uint64(11))


@njit(parallel=True, cache=True)
def sweep(nblocks, per_block, seed0, wD, wL, wT4D, wT4L, viol, njob,
          ndisp, worst_out, worst_in):
    for b in prange(nblocks):
        rs = np.zeros(1, np.uint64)
        rs[0] = np.uint64(seed0 + 2654435761 * (b + 1))
        for _ in range(37):
            rnd(rs)
        a = np.zeros(MAXN, np.int64)
        x = np.zeros(MAXN, np.int64)
        sc = np.zeros(MAXN, np.int64)
        st = np.zeros(MAXN, np.int64); cp = np.zeros(MAXN, np.int64)
        od = np.zeros(MAXN, np.int64)
        fst = np.zeros(MAXN, np.int64); fcp = np.zeros(MAXN, np.int64)
        fod = np.zeros(MAXN, np.int64)
        se = np.zeros(MAXK, np.int64); sj = np.zeros(MAXK, np.int64)
        wt = np.zeros(MAXN, np.int64)
        In = np.zeros(MAXN, np.int64); Out = np.zeros(MAXN, np.int64)
        pos = np.zeros(MAXN, np.int64)
        for _it in range(per_block):
            n = 1 + rnd(rs) % MAXN
            k = 1 + rnd(rs) % MAXK
            pat = rnd(rs) % 5
            L = np.int64(1 + rnd(rs) % 9)
            amax = np.int64(1 + rnd(rs) % 12)
            for j in range(n):
                if pat == 0:
                    a[j] = rnd(rs) % (amax + 1)
                elif pat == 1:
                    a[j] = 0                      # all tied
                elif pat == 2:
                    a[j] = (rnd(rs) % 3) * (rnd(rs) % 4)
                elif pat == 3:
                    a[j] = j * (rnd(rs) % 2)      # bursty
                else:
                    a[j] = rnd(rs) % 2
            # sort arrivals (rank order)
            for p in range(1, n):
                v = a[p]
                q = p - 1
                while q >= 0 and a[q] > v:
                    a[q + 1] = a[q]
                    q -= 1
                a[q + 1] = v
            spat = rnd(rs) % 4
            for j in range(n):
                if spat == 0:
                    x[j] = rnd(rs) % (L + 1)
                elif spat == 1:
                    x[j] = L
                elif spat == 2:
                    x[j] = 1
                else:
                    x[j] = 1 + rnd(rs) % L
            # guarantee at least one job of size L so that L = max x
            x[rnd(rs) % n] = L
            for j in range(n):
                sc[j] = rnd(rs) % 100
            mode = rnd(rs) % 6
            B = np.int64(rnd(rs) % (3 * L * k + 2))
            if mode == 0:
                m = F.RANDOM
            elif mode == 1:
                m = F.SCORE
            elif mode == 2:
                m = F.MAXRANK
            elif mode == 3:
                m = F.GUARD
            elif mode == 4:
                m = F.SCORE
                for j in range(n):
                    sc[j] = x[j]              # SJF on true sizes
            else:
                m = F.SCORE
                for j in range(n):
                    sc[j] = -x[j]             # LJF on true sizes
            aa = a[:n]; xx = x[:n]
            F.sim(aa, xx, k, F.FCFS, sc[:n], B, fst[:n], fcp[:n], fod[:n],
                  se, sj, wt[:n], rs)
            F.sim(aa, xx, k, m, sc[:n], B, st[:n], cp[:n], od[:n],
                  se, sj, wt[:n], rs)
            F.in_out(xx, od[:n], n, In[:n], Out[:n], pos[:n])
            G = np.int64(0)
            for i in range(n):
                e = (st[i] - a[i]) - (fst[i] - a[i])
                if e > G:
                    G = e
            ndisp[b] += 1
            for i in range(n):
                njob[b] += 1
                e = st[i] - fst[i]
                D = k * e - (In[i] - Out[i])
                ad = D if D >= 0 else -D
                if ad > 2 * (k - 1) * L:
                    viol[b, 0] += 1
                if k == 1 and D != 0:
                    viol[b, 1] += 1
                if ad * wL[b, k] > wD[b, k] * L:
                    wD[b, k] = ad
                    wL[b, k] = L
                # Lemma 2 and Theorem 2 with the realised G
                if Out[i] > k * (G - e + L):
                    viol[b, 2] += 1
                if In[i] > k * G + (3 * k - 2) * L:
                    viol[b, 3] += 1
                if k * e > (In[i] - Out[i]) + 2 * (k - 1) * L:
                    viol[b, 4] += 1
                so = k * (G - e + L) - Out[i]
                if so < worst_out[b]:
                    worst_out[b] = so
                si = k * G + (3 * k - 2) * L - In[i]
                if si < worst_in[b]:
                    worst_in[b] = si
                if m == F.GUARD:
                    if In[i] >= B + k * L:
                        viol[b, 5] += 1
                    if k * e > B + (3 * k - 2) * L:
                        viol[b, 6] += 1
                    q = k * e - B
                    if q > 0 and q * wT4L[b, k] > wT4D[b, k] * L:
                        wT4D[b, k] = q
                        wT4L[b, k] = L


def main():
    nb = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
    pb = int(sys.argv[2]) if len(sys.argv) > 2 else 20000
    set_num_threads(4)
    wD = np.zeros((nb, NK), np.int64)
    wL = np.ones((nb, NK), np.int64)
    wT4D = np.zeros((nb, NK), np.int64)
    wT4L = np.ones((nb, NK), np.int64)
    viol = np.zeros((nb, 8), np.int64)
    njob = np.zeros(nb, np.int64)
    ndisp = np.zeros(nb, np.int64)
    worst_out = np.full(nb, 1 << 40, np.int64)
    worst_in = np.full(nb, 1 << 40, np.int64)
    t0 = time.time()
    sweep(nb, pb, 20260919, wD, wL, wT4D, wT4L, viol, njob, ndisp,
          worst_out, worst_in)
    dt = time.time() - t0
    names = ["T1 |D|>2(k-1)L", "C1.1 k=1 D!=0", "L2 Out>k(G-e+L)",
             "T2 In>kG+(3k-2)L", "C1.2", "T4(3) In>=B+kL",
             "T4(4) ke>B+(3k-2)L", "-"]
    lines = []
    lines.append("random sweep: instances=%d job-checks=%d  %.1fs"
                 % (ndisp.sum(), njob.sum(), dt))
    for c, nm in enumerate(names[:7]):
        lines.append("  violations %-22s = %d" % (nm, viol[:, c].sum()))
    lines.append("  min slack of Lemma 2  (k(G-e+L)-Out) = %d" % worst_out.min())
    lines.append("  min slack of Theorem 2 (kG+(3k-2)L-In) = %d" % worst_in.min())
    for k in range(1, MAXK + 1):
        bd, bl = 0, 1
        for b in range(nb):
            if wD[b, k] * bl > bd * wL[b, k]:
                bd, bl = wD[b, k], wL[b, k]
        td, tl = 0, 1
        for b in range(nb):
            if wT4D[b, k] * tl > td * wT4L[b, k]:
                td, tl = wT4D[b, k], wT4L[b, k]
        from fractions import Fraction
        lines.append("  k=%d worst |D|/L = %-8s (bound 2(k-1)=%d) | worst "
                     "(k*excess-B)/L for the guard = %-8s (bound 3k-2=%d)"
                     % (k, str(Fraction(int(bd), int(bl))), 2 * (k - 1),
                        str(Fraction(int(td), int(tl))), 3 * k - 2))
    txt = "\n".join(lines)
    print(txt)
    with open("out_random.txt", "a") as f:
        f.write(txt + "\n")


if __name__ == "__main__":
    main()
