"""Exhaustive sweep with eps > 0 (Theorem B) and with the cap Bmax.
Checks   (k-eps) Wg <= k Wf + B0 + (3k-2)L      [Theorem B]
and      k Wg     <= k Wf + Bmax + (3k-2)L      [Theorem A with the cap]
and the Lemma, and whether the head-check rule still coincides with min-rank-fired."""
import sys
sys.dont_write_bytecode = True
import time
import numpy as np
from numba import njit, prange
import fastkern as F
from enum_util import arrival_sets, service_sets, pred_sets

FCFS, GUARD, HEAD = 0, 1, 2
BIG = 1000000


@njit(parallel=True, cache=True)
def sweep(arrs, srvs, perms, k, L, Bhi, epsn, epsd, caps, bB, bA, cnts, vio, brec):
    nA, n = arrs.shape
    nS = srvs.shape[0]; nP = perms.shape[0]; nE = epsn.shape[0]; nC = caps.shape[0]
    for ai in prange(nA):
        a = arrs[ai]
        st = np.empty(n, np.int64); cp = np.empty(n, np.int64)
        stf = np.empty(n, np.int64); cpf = np.empty(n, np.int64)
        sth = np.empty(n, np.int64); cph = np.empty(n, np.int64)
        se = np.empty(k, np.int64); sj = np.empty(k, np.int64)
        wt = np.empty(n, np.bool_); cw = np.empty(n, np.int64); cc = np.empty(n, np.int64)
        vB = -1.0e18; vA = -1.0e18
        c0 = 0; c1 = 0; c2 = 0; c3 = 0
        for si in range(nS):
            s = srvs[si]
            F.sim(a, s, perms[0], k, FCFS, 0, 0, 0, 1, 0, 0, 1,
                  stf, cpf, se, sj, wt, cw, cc)
            for pi in range(nP):
                p = perms[pi]
                for ei in range(nE):
                    en = epsn[ei]; ed = epsd[ei]
                    for B0 in range(0, Bhi + 1):
                        for ci in range(nC):
                            Bmax = B0 + caps[ci] if caps[ci] < BIG else BIG
                            F.sim(a, s, p, k, GUARD, B0, Bmax, en, ed, 0, 0, 1,
                                  st, cp, se, sj, wt, cw, cc)
                            F.sim(a, s, p, k, HEAD, B0, Bmax, en, ed, 0, 0, 1,
                                  sth, cph, se, sj, wt, cw, cc)
                            for i in range(n):
                                if st[i] != sth[i]:
                                    c3 += 1
                                    break
                            g = F.lemma_gap(a, s, st, cp, stf, cpf)
                            if g > (k - 1) * L:
                                c2 += 1
                                vio[ai, 2] = 1
                            for i in range(n):
                                Wg = st[i] - a[i]; Wf = stf[i] - a[i]
                                lhs = (k * ed - en) * Wg
                                rhs0 = ed * (k * Wf + B0)
                                xB = (lhs - rhs0) / (ed * k * L)
                                if xB > vB:
                                    vB = xB
                                    brec[ai, 0] = si; brec[ai, 1] = pi; brec[ai, 2] = ei
                                    brec[ai, 3] = B0; brec[ai, 4] = ci; brec[ai, 5] = i
                                if lhs > rhs0 + ed * (3 * k - 2) * L:
                                    c0 += 1
                                    vio[ai, 0] = 1
                                bb = Bmax if Bmax < BIG else BIG
                                xA = (k * Wg - k * Wf - bb) / (k * L)
                                if bb < BIG and xA > vA:
                                    vA = xA
                                if bb < BIG and k * Wg - k * Wf - bb > (3 * k - 2) * L:
                                    c1 += 1
                                    vio[ai, 1] = 1
        bB[ai] = vB; bA[ai] = vA
        cnts[ai, 0] = c0; cnts[ai, 1] = c1; cnts[ai, 2] = c2; cnts[ai, 3] = c3


def main():
    n = int(sys.argv[1]); L = int(sys.argv[2]); amax = int(sys.argv[3])
    ks = [int(x) for x in sys.argv[4].split(",")]
    arrs = arrival_sets(n, amax); srvs = service_sets(n, L); perms = pred_sets(n)
    Bhi = n * L + 1
    caps = np.array([0, 2, 5, BIG], np.int64)
    print("n=%d L=%d amax=%d |arr|=%d |srv|=%d |pred|=%d B0 in 0..%d caps=%s"
          % (n, L, amax, len(arrs), len(srvs), len(perms), Bhi, caps.tolist()), flush=True)
    for k in ks:
        cand = [(0, 1), (1, 2), (1, 1), (2 * k - 1, 2)]
        cand = [(en, ed) for en, ed in cand if en < k * ed]
        epsn = np.array([c[0] for c in cand], np.int64)
        epsd = np.array([c[1] for c in cand], np.int64)
        nA = len(arrs)
        bB = np.empty(nA, np.float64); bA = np.empty(nA, np.float64)
        cnts = np.zeros((nA, 4), np.int64); vio = np.zeros((nA, 3), np.int64)
        brec = np.zeros((nA, 6), np.int64)
        t0 = time.time()
        sweep(arrs, srvs, perms, k, L, Bhi, epsn, epsd, caps, bB, bA, cnts, vio, brec)
        dt = time.time() - t0
        nsim = len(arrs) * len(srvs) * (len(perms) * len(cand) * (Bhi + 1) * len(caps) * 2 + 1)
        j = int(np.argmax(bB))
        print("k=%d eps=%s sims=%d %.1fs" % (k, cand, nsim, dt), flush=True)
        print("   ThmB violations=%d  ThmA(cap) violations=%d  Lemma violations=%d"
              "  head-rule differs in %d cases (expected >0 for eps>0)"
              % (cnts[:, 0].sum(), cnts[:, 1].sum(), cnts[:, 2].sum(), cnts[:, 3].sum()),
              flush=True)
        print("   max ThmB constant c = %.4f  (claim <= %.4f)" % (bB.max(), 3 - 2 / k), flush=True)
        print("   max ThmA(cap) constant c = %.4f" % bA.max(), flush=True)
        print("   ThmB argmax: arrivals=%s services=%s pred=%s eps=%s B0=%d cap=+%s job=%d"
              % (arrs[j].tolist(), srvs[brec[j, 0]].tolist(), perms[brec[j, 1]].tolist(),
                 cand[brec[j, 2]], brec[j, 3], caps[brec[j, 4]], brec[j, 5]), flush=True)


main()
