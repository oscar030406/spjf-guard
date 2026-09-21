"""Exhaustive sweep, eps = 0, constant budget B.  Checks
   - Theorem A            k*Wg <= k*Wf + B + (3k-2)L
   - Theorem A, sup form  (worst real B in (B-1, B]):  k*Wg <= k*Wf + (B-1) + (3k-2)L
   - Lemma                |U_guard - U_FCFS| <= (k-1)L
   - head-check equivalence of the eps=0 rule
and reports the worst attained constants."""
import sys
sys.dont_write_bytecode = True
import time
import numpy as np
from numba import njit, prange
import fastkern as F
from enum_util import arrival_sets, service_sets, pred_sets

FCFS, GUARD, HEAD = 0, 1, 2


@njit(parallel=True, cache=True)
def sweep(arrs, srvs, perms, k, L, Bhi, bestv, bestr, bestv2, bestrat, cnts, vio):
    nA, n = arrs.shape
    nS = srvs.shape[0]
    nP = perms.shape[0]
    for ai in prange(nA):
        a = arrs[ai]
        st = np.empty(n, np.int64); cp = np.empty(n, np.int64)
        stf = np.empty(n, np.int64); cpf = np.empty(n, np.int64)
        sth = np.empty(n, np.int64); cph = np.empty(n, np.int64)
        se = np.empty(k, np.int64); sj = np.empty(k, np.int64)
        wt = np.empty(n, np.bool_); cw = np.empty(n, np.int64); cc = np.empty(n, np.int64)
        bv = -1000000; bv2 = -1000000; brat = -1.0e18
        c0 = 0; c1 = 0; c2 = 0; c3 = 0
        for si in range(nS):
            s = srvs[si]
            F.sim(a, s, perms[0], k, FCFS, 0, 0, 0, 1, 0, 0, 1,
                  stf, cpf, se, sj, wt, cw, cc)
            for pi in range(nP):
                p = perms[pi]
                for B in range(0, Bhi + 1):
                    F.sim(a, s, p, k, GUARD, B, B, 0, 1, 0, 0, 1,
                          st, cp, se, sj, wt, cw, cc)
                    F.sim(a, s, p, k, HEAD, B, B, 0, 1, 0, 0, 1,
                          sth, cph, se, sj, wt, cw, cc)
                    for i in range(n):
                        if st[i] != sth[i]:
                            c3 += 1
                            if vio[ai, 3, 0] == 0:
                                vio[ai, 3, 0] = 1; vio[ai, 3, 1] = si
                                vio[ai, 3, 2] = pi; vio[ai, 3, 3] = B; vio[ai, 3, 4] = i
                            break
                    g = F.lemma_gap(a, s, st, cp, stf, cpf)
                    if g > (k - 1) * L:
                        c2 += 1
                        if vio[ai, 2, 0] == 0:
                            vio[ai, 2, 0] = 1; vio[ai, 2, 1] = si
                            vio[ai, 2, 2] = pi; vio[ai, 2, 3] = B; vio[ai, 2, 4] = g
                    for i in range(n):
                        Wg = st[i] - a[i]
                        Wf = stf[i] - a[i]
                        d = k * Wg - k * Wf
                        v = d - B
                        if v > bv:
                            bv = v
                            bestr[ai, 0] = si; bestr[ai, 1] = pi
                            bestr[ai, 2] = B; bestr[ai, 3] = i
                        Beff = B - 1 if B >= 1 else 0
                        v2 = d - Beff
                        if v2 > bv2:
                            bv2 = v2
                        r = d / (B + (3 * k - 2) * L)
                        if r > brat:
                            brat = r
                        if v > (3 * k - 2) * L:
                            c0 += 1
                            if vio[ai, 0, 0] == 0:
                                vio[ai, 0, 0] = 1; vio[ai, 0, 1] = si
                                vio[ai, 0, 2] = pi; vio[ai, 0, 3] = B; vio[ai, 0, 4] = i
                        if B >= 1 and v2 > (3 * k - 2) * L:
                            c1 += 1
                            if vio[ai, 1, 0] == 0:
                                vio[ai, 1, 0] = 1; vio[ai, 1, 1] = si
                                vio[ai, 1, 2] = pi; vio[ai, 1, 3] = B; vio[ai, 1, 4] = i
        bestv[ai] = bv
        bestv2[ai] = bv2
        bestrat[ai] = brat
        cnts[ai, 0] = c0; cnts[ai, 1] = c1; cnts[ai, 2] = c2; cnts[ai, 3] = c3


def main():
    n = int(sys.argv[1]); L = int(sys.argv[2]); amax = int(sys.argv[3])
    ks = [int(x) for x in sys.argv[4].split(",")]
    arrs = arrival_sets(n, amax); srvs = service_sets(n, L); perms = pred_sets(n)
    Bhi = n * L + 1
    print("n=%d L=%d amax=%d  |arr|=%d |srv|=%d |pred|=%d  B in 0..%d"
          % (n, L, amax, len(arrs), len(srvs), len(perms), Bhi), flush=True)
    for k in ks:
        nA = len(arrs)
        bestv = np.empty(nA, np.int64); bestv2 = np.empty(nA, np.int64)
        bestrat = np.empty(nA, np.float64)
        bestr = np.zeros((nA, 4), np.int64)
        cnts = np.zeros((nA, 4), np.int64)
        vio = np.zeros((nA, 4, 5), np.int64)
        t0 = time.time()
        sweep(arrs, srvs, perms, k, L, Bhi, bestv, bestr, bestv2, bestrat, cnts, vio)
        dt = time.time() - t0
        nsim = len(arrs) * len(srvs) * (len(perms) * (Bhi + 1) * 2 + 1)
        mx = int(bestv.max()); mx2 = int(bestv2.max())
        j = int(np.argmax(bestv))
        print("k=%d  sims=%d  %.1fs" % (k, nsim, dt), flush=True)
        print("   ThmA violations=%d   supB-form violations=%d   Lemma violations=%d"
              "   head-equiv mismatches=%d"
              % (cnts[:, 0].sum(), cnts[:, 1].sum(), cnts[:, 2].sum(), cnts[:, 3].sum()),
              flush=True)
        print("   max (k*Wg-k*Wf-B)/L = %.4f  (claim <= %d)   -> c = %.4f (claim <= %.4f)"
              % (mx / L, 3 * k - 2, mx / (k * L), 3 - 2 / k), flush=True)
        print("   sup-B form: max = %.4f L  -> c = %.4f" % (mx2 / L, mx2 / (k * L)), flush=True)
        print("   worst used/allowed ratio = %.4f" % bestrat.max(), flush=True)
        print("   argmax: arrivals=%s services=%s pred=%s B=%d job=%d"
              % (arrs[j].tolist(), srvs[bestr[j, 0]].tolist(), perms[bestr[j, 1]].tolist(),
                 bestr[j, 2], bestr[j, 3]), flush=True)
        for w in range(4):
            r = vio[:, w, 0].nonzero()[0]
            if len(r):
                z = r[0]
                print("   VIOLATION class %d at arrivals=%s rec=%s"
                      % (w, arrs[z].tolist(), vio[z, w].tolist()), flush=True)


main()
