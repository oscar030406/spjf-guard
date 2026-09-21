"""Focused search for the true constants: per k, maximise
  obj 0 :  D / L        (signed, upper direction of Theorem 1)
  obj 1 : -D / L        (lower direction of Theorem 1)
  obj 2 : (k*excess - B) / L for guard(A,B) with an arbitrary base A
over random instances with a free-choice dispatch tape (= every work-conserving
non-preemptive schedule) plus greedy hill-climbing from each sample.

usage: run_tight.py <obj> <blocks> <samples_per_block> <climb_steps>
"""
import sys, time
sys.dont_write_bytecode = True
import numpy as np
from numba import njit, prange, set_num_threads
from fractions import Fraction
import fastsim as F

MAXN = 16
MAXK = 8
# LMAX is passed in as an argument (a module global would be frozen into the
# numba cache and silently ignored on later runs)


@njit(inline='always')
def rnd(st):
    v = st[0]
    v ^= (v << np.uint64(13)) & np.uint64(0xFFFFFFFFFFFFFFFF)
    v ^= (v >> np.uint64(7))
    v ^= (v << np.uint64(17)) & np.uint64(0xFFFFFFFFFFFFFFFF)
    st[0] = v
    return np.int64(v >> np.uint64(11))


@njit(inline='always')
def sortarr(a, n):
    for p in range(1, n):
        v = a[p]; q = p - 1
        while q >= 0 and a[q] > v:
            a[q + 1] = a[q]; q -= 1
        a[q + 1] = v


@njit(cache=True)
def ev(a, x, tape, n, k, B, obj, st, cp, od, fst, fcp, fod, se, sj, wt,
       In, Out, pos, rs):
    aa = a[:n]; xx = x[:n]
    L = np.int64(0)
    for j in range(n):
        if xx[j] > L:
            L = xx[j]
    if L == 0:
        return np.int64(-1 << 40), np.int64(1)
    F.sim(aa, xx, k, F.FCFS, tape[:n], B, fst[:n], fcp[:n], fod[:n], se, sj,
          wt[:n], rs)
    m = F.GCHOICE if obj == 2 else F.CHOICE
    F.sim(aa, xx, k, m, tape[:n], B, st[:n], cp[:n], od[:n], se, sj, wt[:n], rs)
    F.in_out(xx, od[:n], n, In[:n], Out[:n], pos[:n])
    best = np.int64(-1 << 40)
    for i in range(n):
        e = st[i] - fst[i]
        if obj == 0:
            v = k * e - (In[i] - Out[i])
        elif obj == 1:
            v = -(k * e - (In[i] - Out[i]))
        else:
            v = k * e - B
        if v > best:
            best = v
    return best, L


@njit(parallel=True, cache=True)
def search(nblocks, nsamp, climb, k, obj, seed0, LMAX, bnum, bden, ba, bx, bt, bn, bB):
    for b in prange(nblocks):
        rs = np.zeros(1, np.uint64)
        rs[0] = np.uint64(seed0 + 2654435761 * (b + 1))
        for _ in range(53):
            rnd(rs)
        a = np.zeros(MAXN, np.int64); x = np.zeros(MAXN, np.int64)
        tape = np.zeros(MAXN, np.int64)
        sav = np.zeros(MAXN, np.int64)
        st = np.zeros(MAXN, np.int64); cp = np.zeros(MAXN, np.int64)
        od = np.zeros(MAXN, np.int64)
        fst = np.zeros(MAXN, np.int64); fcp = np.zeros(MAXN, np.int64)
        fod = np.zeros(MAXN, np.int64)
        se = np.zeros(MAXK, np.int64); sj = np.zeros(MAXK, np.int64)
        wt = np.zeros(MAXN, np.int64)
        In = np.zeros(MAXN, np.int64); Out = np.zeros(MAXN, np.int64)
        pos = np.zeros(MAXN, np.int64)
        for _s in range(nsamp):
            n = 2 + rnd(rs) % (MAXN - 1)
            amax = np.int64(1 + rnd(rs) % 20)
            for j in range(n):
                a[j] = rnd(rs) % (amax + 1)
                x[j] = rnd(rs) % (LMAX + 1)
                tape[j] = rnd(rs) % 16
            sortarr(a, n)
            B = np.int64(rnd(rs) % (3 * LMAX * k + 1))
            cur, curL = ev(a, x, tape, n, k, B, obj, st, cp, od, fst, fcp, fod,
                           se, sj, wt, In, Out, pos, rs)
            for _c in range(climb):
                w = rnd(rs) % 4
                if w == 0:
                    # the whole array must be saved: mutate-then-sort is not
                    # undone by restoring a single position
                    for q in range(n):
                        sav[q] = a[q]
                    a[rnd(rs) % n] = rnd(rs) % (amax + 1)
                    sortarr(a, n)
                    v2, L2 = ev(a, x, tape, n, k, B, obj, st, cp, od, fst, fcp,
                                fod, se, sj, wt, In, Out, pos, rs)
                    if v2 * curL > cur * L2:
                        cur = v2; curL = L2
                    else:
                        for q in range(n):
                            a[q] = sav[q]
                elif w == 1:
                    p = rnd(rs) % n; old = x[p]
                    x[p] = rnd(rs) % (LMAX + 1)
                    v2, L2 = ev(a, x, tape, n, k, B, obj, st, cp, od, fst, fcp,
                                fod, se, sj, wt, In, Out, pos, rs)
                    if v2 * curL > cur * L2:
                        cur = v2; curL = L2
                    else:
                        x[p] = old
                elif w == 2:
                    p = rnd(rs) % n; old = tape[p]
                    tape[p] = rnd(rs) % 16
                    v2, L2 = ev(a, x, tape, n, k, B, obj, st, cp, od, fst, fcp,
                                fod, se, sj, wt, In, Out, pos, rs)
                    if v2 * curL > cur * L2:
                        cur = v2; curL = L2
                    else:
                        tape[p] = old
                else:
                    old = B
                    B = np.int64(rnd(rs) % (3 * LMAX * k + 1))
                    v2, L2 = ev(a, x, tape, n, k, B, obj, st, cp, od, fst, fcp,
                                fod, se, sj, wt, In, Out, pos, rs)
                    if v2 * curL > cur * L2:
                        cur = v2; curL = L2
                    else:
                        B = old
            if cur * bden[b] > bnum[b] * curL:
                bnum[b] = cur; bden[b] = curL
                bn[b] = n; bB[b] = B
                for j in range(n):
                    ba[b, j] = a[j]; bx[b, j] = x[j]; bt[b, j] = tape[j]


def main():
    obj = int(sys.argv[1])
    nb = int(sys.argv[2]) if len(sys.argv) > 2 else 2000
    ns = int(sys.argv[3]) if len(sys.argv) > 3 else 200
    cl = int(sys.argv[4]) if len(sys.argv) > 4 else 300
    LMAX = int(sys.argv[5]) if len(sys.argv) > 5 else 40
    set_num_threads(4)
    lines = []
    for k in range(1, 7):
        bnum = np.full(nb, -(1 << 40), np.int64)
        bden = np.ones(nb, np.int64)
        ba = np.zeros((nb, MAXN), np.int64); bx = np.zeros((nb, MAXN), np.int64)
        bt = np.zeros((nb, MAXN), np.int64)
        bn = np.zeros(nb, np.int64); bB = np.zeros(nb, np.int64)
        t0 = time.time()
        search(nb, ns, cl, k, obj, 7919 * (k + 3) + 31 * obj, LMAX, bnum, bden,
               ba, bx, bt, bn, bB)
        bi = 0
        for b in range(nb):
            if bnum[b] * bden[bi] > bnum[bi] * bden[b]:
                bi = b
        n = int(bn[bi])
        val = Fraction(int(bnum[bi]), int(bden[bi]))
        bound = (2 * (k - 1)) if obj <= 1 else (3 * k - 2)
        lines.append("obj=%d k=%d best = %-10s (%.4f)  proved bound %d  [%.0fs]"
                     % (obj, k, str(val), float(val), bound, time.time() - t0))
        lines.append("   n=%d B=%d a=%s x=%s tape=%s"
                     % (n, int(bB[bi]), [int(v) for v in ba[bi, :n]],
                        [int(v) for v in bx[bi, :n]],
                        [int(v) for v in bt[bi, :n]]))
    txt = "\n".join(lines)
    print(txt)
    with open("out_tight.txt", "a") as f:
        f.write(txt + "\n")


if __name__ == "__main__":
    main()
