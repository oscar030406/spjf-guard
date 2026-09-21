"""Simulated annealing on the slack of Theorem 1 / Theorem 4 / Theorem 2 /
Lemma 2.  The policy is a free-choice tape, so the search ranges over EVERY
work-conserving non-preemptive schedule, not over a list of named policies.

objectives
  0  max |k(W_P-W_F) - (In-Out)| / L                 (Theorem 1, bound 2(k-1))
  1  max (k*excess - B) / L for guard(A,B)           (Theorem 4, bound 3k-2)
  2  max In_i - kG - (3k-2)L                         (Theorem 2, must stay <=0)
  3  max Out_i - k(G - excess_i + L)                 (Lemma 2,   must stay <=0)

usage: run_anneal.py <obj> <restarts> <steps>
"""
import sys, time
sys.dont_write_bytecode = True
import numpy as np
from numba import njit, prange, set_num_threads
from fractions import Fraction
import fastsim as F

MAXN = 16
MAXK = 8


@njit(inline='always')
def rnd(st):
    v = st[0]
    v ^= (v << np.uint64(13)) & np.uint64(0xFFFFFFFFFFFFFFFF)
    v ^= (v >> np.uint64(7))
    v ^= (v << np.uint64(17)) & np.uint64(0xFFFFFFFFFFFFFFFF)
    st[0] = v
    return np.int64(v >> np.uint64(11))


@njit(cache=True)
def evaluate(a, x, tape, n, k, B, obj, st, cp, od, fst, fcp, fod, se, sj, wt,
             In, Out, pos, rs):
    aa = a[:n]; xx = x[:n]
    L = np.int64(0)
    for j in range(n):
        if xx[j] > L:
            L = xx[j]
    if L == 0:
        return np.int64(0), np.int64(1)
    F.sim(aa, xx, k, F.FCFS, tape[:n], B, fst[:n], fcp[:n], fod[:n], se, sj,
          wt[:n], rs)
    m = F.GCHOICE if obj == 1 else F.CHOICE
    F.sim(aa, xx, k, m, tape[:n], B, st[:n], cp[:n], od[:n], se, sj, wt[:n], rs)
    F.in_out(xx, od[:n], n, In[:n], Out[:n], pos[:n])
    G = np.int64(0)
    for i in range(n):
        e = st[i] - fst[i]
        if e > G:
            G = e
    best = np.int64(-1 << 50)
    for i in range(n):
        e = st[i] - fst[i]
        if obj == 0:
            D = k * e - (In[i] - Out[i])
            v = D if D >= 0 else -D
        elif obj == 1:
            v = k * e - B
        elif obj == 2:
            v = In[i] - k * G - (3 * k - 2) * L
        else:
            v = Out[i] - k * (G - e + L)
        if v > best:
            best = v
    return best, L


@njit(parallel=True, cache=True)
def anneal(restarts, steps, k, obj, seed0, bnum, bden, ba, bx, btape, bn, bB):
    for r in prange(restarts):
        rs = np.zeros(1, np.uint64)
        rs[0] = np.uint64(seed0 + 2654435761 * (r + 1))
        for _ in range(41):
            rnd(rs)
        a = np.zeros(MAXN, np.int64); x = np.zeros(MAXN, np.int64)
        tape = np.zeros(MAXN, np.int64)
        st = np.zeros(MAXN, np.int64); cp = np.zeros(MAXN, np.int64)
        od = np.zeros(MAXN, np.int64)
        fst = np.zeros(MAXN, np.int64); fcp = np.zeros(MAXN, np.int64)
        fod = np.zeros(MAXN, np.int64)
        se = np.zeros(MAXK, np.int64); sj = np.zeros(MAXK, np.int64)
        wt = np.zeros(MAXN, np.int64)
        In = np.zeros(MAXN, np.int64); Out = np.zeros(MAXN, np.int64)
        pos = np.zeros(MAXN, np.int64)
        ca = np.zeros(MAXN, np.int64); cx = np.zeros(MAXN, np.int64)
        ct = np.zeros(MAXN, np.int64)
        n = 2 + rnd(rs) % (MAXN - 1)
        LMAX = np.int64(12)
        for j in range(n):
            a[j] = rnd(rs) % 6
            x[j] = rnd(rs) % (LMAX + 1)
            tape[j] = rnd(rs) % 16
        for p in range(1, n):
            v = a[p]; q = p - 1
            while q >= 0 and a[q] > v:
                a[q + 1] = a[q]; q -= 1
            a[q + 1] = v
        B = np.int64(rnd(rs) % (4 * LMAX * k + 1))
        cur, curL = evaluate(a, x, tape, n, k, B, obj, st, cp, od, fst, fcp,
                             fod, se, sj, wt, In, Out, pos, rs)
        for s in range(steps):
            for j in range(n):
                ca[j] = a[j]; cx[j] = x[j]; ct[j] = tape[j]
            cn = n; cB = B
            mut = rnd(rs) % 5
            if mut == 0:
                a[rnd(rs) % n] = rnd(rs) % 8
                for p in range(1, n):
                    v = a[p]; q = p - 1
                    while q >= 0 and a[q] > v:
                        a[q + 1] = a[q]; q -= 1
                    a[q + 1] = v
            elif mut == 1:
                x[rnd(rs) % n] = rnd(rs) % (LMAX + 1)
            elif mut == 2:
                tape[rnd(rs) % n] = rnd(rs) % 16
            elif mut == 3:
                B = np.int64(rnd(rs) % (4 * LMAX * k + 1))
            else:
                if rnd(rs) % 2 == 0 and n < MAXN:
                    a[n] = rnd(rs) % 8
                    x[n] = rnd(rs) % (LMAX + 1)
                    tape[n] = rnd(rs) % 16
                    n += 1
                    for p in range(1, n):
                        v = a[p]; q = p - 1
                        while q >= 0 and a[q] > v:
                            a[q + 1] = a[q]; q -= 1
                        a[q + 1] = v
                elif n > 2:
                    n -= 1
            val, LL = evaluate(a, x, tape, n, k, B, obj, st, cp, od, fst, fcp,
                               fod, se, sj, wt, In, Out, pos, rs)
            # compare val/LL against cur/curL (obj 0,1) or val vs cur (2,3)
            better = False
            equal = False
            if obj <= 1:
                lhs = val * curL
                rhs = cur * LL
                better = lhs > rhs
                equal = lhs == rhs
            else:
                better = val > cur
                equal = val == cur
            if better or (equal and rnd(rs) % 2 == 0) or (rnd(rs) % 1000 < 12):
                cur = val; curL = LL
                if obj <= 1:
                    if val * bden[r] > bnum[r] * LL:
                        bnum[r] = val; bden[r] = LL
                        bn[r] = n; bB[r] = B
                        for j in range(n):
                            ba[r, j] = a[j]; bx[r, j] = x[j]; btape[r, j] = tape[j]
                else:
                    if val > bnum[r]:
                        bnum[r] = val; bden[r] = LL
                        bn[r] = n; bB[r] = B
                        for j in range(n):
                            ba[r, j] = a[j]; bx[r, j] = x[j]; btape[r, j] = tape[j]
            else:
                for j in range(MAXN):
                    a[j] = ca[j]; x[j] = cx[j]; tape[j] = ct[j]
                n = cn; B = cB


def main():
    obj = int(sys.argv[1])
    restarts = int(sys.argv[2]) if len(sys.argv) > 2 else 2000
    steps = int(sys.argv[3]) if len(sys.argv) > 3 else 4000
    set_num_threads(4)
    lines = []
    for k in range(1, 7):
        bnum = np.full(restarts, -(1 << 50), np.int64)
        bden = np.ones(restarts, np.int64)
        ba = np.zeros((restarts, MAXN), np.int64)
        bx = np.zeros((restarts, MAXN), np.int64)
        bt = np.zeros((restarts, MAXN), np.int64)
        bn = np.zeros(restarts, np.int64)
        bB = np.zeros(restarts, np.int64)
        t0 = time.time()
        anneal(restarts, steps, k, obj, 1000003 * (k + 7) + obj, bnum, bden,
               ba, bx, bt, bn, bB)
        bi = 0
        for r in range(restarts):
            if obj <= 1:
                if bnum[r] * bden[bi] > bnum[bi] * bden[r]:
                    bi = r
            else:
                if bnum[r] > bnum[bi]:
                    bi = r
        n = int(bn[bi])
        if obj <= 1:
            val = Fraction(int(bnum[bi]), int(bden[bi]))
            bound = 2 * (k - 1) if obj == 0 else 3 * k - 2
            lines.append("obj=%d k=%d best = %s (%.4f)  proved bound %d   [%.0fs]"
                         % (obj, k, val, float(val), bound, time.time() - t0))
        else:
            lines.append("obj=%d k=%d best (must be <= 0) = %d   [%.0fs]"
                         % (obj, k, int(bnum[bi]), time.time() - t0))
        lines.append("   witness n=%d B=%d a=%s x=%s tape=%s"
                     % (n, int(bB[bi]), list(ba[bi, :n]), list(bx[bi, :n]),
                        list(bt[bi, :n])))
    txt = "\n".join(lines)
    print(txt)
    with open("out_anneal.txt", "a") as f:
        f.write(txt + "\n")


if __name__ == "__main__":
    main()
