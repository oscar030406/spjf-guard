"""Two things the main sweeps do not cover.

(1) The LEMMA is claimed for ANY two non-preemptive work-conserving k-server
    policies, not just guard vs FCFS.  Here it is checked pairwise over a diverse
    family: FCFS, LIFO, shortest-true-service-first, longest-true-service-first,
    smallest-prediction-first, and two guards with different budgets.

(2) The COUNT-CHANNEL corollary in its mixed form: work channel with budget B AND
    a count cap Ncap for overtakers of true service <= theta, 0 < theta < L.
    Claim: the bounds hold with B replaced by B + Ncap*theta.
"""
import sys
sys.dont_write_bytecode = True
import time
import numpy as np
from numba import njit, prange
import fastkern as F

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
def sim_key(a, s, key, k, start, comp, srv_end, srv_job, wait):
    """Work-conserving non-preemptive: always dispatch argmin (key[q], q)."""
    n = a.shape[0]
    for i in range(n):
        start[i] = -1
        comp[i] = -1
        wait[i] = False
    for r in range(k):
        srv_end[r] = -1
        srv_job[r] = -1
    nxt = 0
    done = 0
    t = a[0]
    while done < n:
        for r in range(k):
            if srv_end[r] == t:
                comp[srv_job[r]] = t
                srv_end[r] = -1
                srv_job[r] = -1
                done += 1
        while nxt < n and a[nxt] == t:
            wait[nxt] = True
            nxt += 1
        while True:
            free = -1
            for r in range(k):
                if srv_end[r] == -1:
                    free = r
                    break
            if free == -1:
                break
            pick = -1
            bk = 0
            for q in range(n):
                if wait[q]:
                    if pick == -1 or key[q] < bk:
                        pick = q
                        bk = key[q]
            if pick == -1:
                break
            srv_end[free] = t + s[pick]
            srv_job[free] = pick
            start[pick] = t
            wait[pick] = False
        nt = -1
        for r in range(k):
            if srv_end[r] != -1 and (nt == -1 or srv_end[r] < nt):
                nt = srv_end[r]
        if nxt < n and (nt == -1 or a[nxt] < nt):
            nt = a[nxt]
        if nt == -1:
            break
        t = nt
    return 0


@njit(parallel=True, cache=True)
def run(seed0, per_thread, nthread, k, NMAX, LMAX, AMAX, cnts, worst):
    NP = 7
    for th in prange(nthread):
        st = np.empty(1, np.int64)
        st[0] = seed0 + 7919 * (th + 1)
        for _ in range(50):
            rnd(st)
        a = np.empty(NMAX, np.int64)
        s = np.empty(NMAX, np.int64)
        p = np.empty(NMAX, np.int64)
        key = np.empty(NMAX, np.int64)
        ST = np.empty((NP, NMAX), np.int64)
        CP = np.empty((NP, NMAX), np.int64)
        se = np.empty(k, np.int64)
        sj = np.empty(k, np.int64)
        wt = np.empty(NMAX, np.bool_)
        cw = np.empty(NMAX, np.int64)
        cc = np.empty(NMAX, np.int64)
        c_lemma = 0
        c_count = 0
        wl = 0
        wc = -1.0e18
        for it in range(per_thread):
            n = ri(st, max(2, k), NMAX)
            L = ri(st, 1, LMAX)
            m = rnd(st) % 3
            for i in range(n):
                if m == 0:
                    a[i] = 0
                elif m == 1:
                    a[i] = ri(st, 0, AMAX)
                else:
                    a[i] = ri(st, 0, 2) * ri(st, 0, 2)
            for i in range(1, n):
                kk = a[i]
                j = i - 1
                while j >= 0 and a[j] > kk:
                    a[j + 1] = a[j]
                    j -= 1
                a[j + 1] = kk
            for i in range(n):
                s[i] = L if rnd(st) % 3 == 0 else ri(st, 1, L)
                p[i] = ri(st, 0, n)
            B1 = ri(st, 0, n * L + 2)
            B2 = ri(st, 0, n * L + 2)
            for i in range(n):
                key[i] = i
            sim_key(a[:n], s[:n], key[:n], k, ST[0, :n], CP[0, :n], se, sj, wt[:n])
            for i in range(n):
                key[i] = -i
            sim_key(a[:n], s[:n], key[:n], k, ST[1, :n], CP[1, :n], se, sj, wt[:n])
            for i in range(n):
                key[i] = s[i]
            sim_key(a[:n], s[:n], key[:n], k, ST[2, :n], CP[2, :n], se, sj, wt[:n])
            for i in range(n):
                key[i] = -s[i]
            sim_key(a[:n], s[:n], key[:n], k, ST[3, :n], CP[3, :n], se, sj, wt[:n])
            for i in range(n):
                key[i] = p[i]
            sim_key(a[:n], s[:n], key[:n], k, ST[4, :n], CP[4, :n], se, sj, wt[:n])
            F.sim(a[:n], s[:n], p[:n], k, 1, B1, B1, 0, 1, 0, 0, 1,
                  ST[5, :n], CP[5, :n], se, sj, wt[:n], cw[:n], cc[:n])
            F.sim(a[:n], s[:n], p[:n], k, 1, B2, B2, 1, 2, 0, 0, 1,
                  ST[6, :n], CP[6, :n], se, sj, wt[:n], cw[:n], cc[:n])
            for x in range(NP):
                for y in range(x + 1, NP):
                    g = F.lemma_gap(a[:n], s[:n], ST[x, :n], CP[x, :n],
                                    ST[y, :n], CP[y, :n])
                    if g > wl:
                        wl = g - (k - 1) * L
                    if g > (k - 1) * L:
                        c_lemma += 1
            # mixed count channel
            theta = ri(st, 1, L)
            Ncap = ri(st, 1, 4)
            B = ri(st, 0, n * L)
            F.sim(a[:n], s[:n], p[:n], k, 1, B, B, 0, 1, Ncap, theta, 1,
                  ST[6, :n], CP[6, :n], se, sj, wt[:n], cw[:n], cc[:n])
            Beff = B + Ncap * theta
            for i in range(n):
                Wg = ST[6, i] - a[i]
                Wf = ST[0, i] - a[i]
                x = (k * Wg - k * Wf - Beff) / (k * L)
                if x > wc:
                    wc = x
                if k * Wg - k * Wf - Beff > (3 * k - 2) * L:
                    c_count += 1
        cnts[th, 0] = c_lemma
        cnts[th, 1] = c_count
        worst[th, 0] = wl
        worst[th, 1] = wc


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
        cnts = np.zeros((nth, 2), np.int64)
        worst = np.zeros((nth, 2), np.float64)
        t0 = time.time()
        run(seed + 313 * k, per, nth, k, NMAX, LMAX, AMAX, cnts, worst)
        print("k=%d instances=%d (%d policy pairs each) %.1fs" % (k, per * nth, 21,
                                                                 time.time() - t0),
              flush=True)
        print("   Lemma violations over all 21 policy pairs = %d   (worst excess over "
              "(k-1)L = %g)" % (cnts[:, 0].sum(), worst[:, 0].max()), flush=True)
        print("   mixed count-channel violations = %d   worst c = %.4f (claim <= %.4f)"
              % (cnts[:, 1].sum(), worst[:, 1].max(), 3 - 2 / k), flush=True)


main()
