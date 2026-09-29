"""Diagnose the claim-A failures in G3(i)."""
import sys
sys.dont_write_bytecode = True
import numpy as np
from fractions import Fraction
import sim_core as S


def lam_sets(jobs, k, sP, dP, oP, sF, dF, oF, i):
    n = len(jobs)
    a = [j[0] for j in jobs]
    x = [j[1] for j in jobs]
    lam_pref = max(x[j] for j in range(n) if a[j] <= a[i])
    # rho^P : jobs other than i dispatched no later than s^P_i and not finished then
    posP = {j: p for p, j in enumerate(oP)}
    posF = {j: p for p, j in enumerate(oF)}
    lamP = 1
    for j in range(n):
        if j == i:
            continue
        if sP[j] <= sP[i] and dP[j] > sP[i] and posP[j] < posP[i]:
            lamP = max(lamP, x[j])
    lamF = 1
    for j in range(n):
        if j == i:
            continue
        if sF[j] <= sF[i] and dF[j] > sF[i] and posF[j] < posF[i]:
            lamF = max(lamF, x[j])
    return lam_pref, lamP, lamF


rng = np.random.default_rng(555)
bad = 0
shown = 0
worst = Fraction(0)
for it in range(200000):
    k = int(rng.integers(1, 5))
    n = int(rng.integers(1, 12))
    a = np.sort(rng.integers(0, 20, n))
    x = (rng.pareto(0.7, n) * 3 + 1).astype(np.int64)
    jobs = [(int(a[i]), int(x[i])) for i in range(n)]
    ch = S.make_random(rng)
    sP, oP, dP = S.simulate(jobs, k, ch)
    sF, oF, dF = S.simulate(jobs, k, S.fcfs)
    In, Out = S.in_out(jobs, oP)
    for i in range(n):
        D = k * (sP[i] - sF[i]) - (In[i] - Out[i])
        lp, lP, lF = lam_sets(jobs, k, sP, dP, oP, sF, dF, oF, i)
        # refined two-sided bound:  -(k-1)(lp+lP) <= D <= (k-1)(lp+lF)
        if D > (k - 1) * (lp + lF) or D < -(k - 1) * (lp + lP):
            bad += 1
            LA = max(lp, lP, lF)
            worst = max(worst, Fraction(abs(D), LA))
            if shown < 3:
                shown += 1
                print("FAIL k=%d i=%d D=%d lam_pref=%d lamP=%d lamF=%d" % (k, i, D, lp, lP, lF))
                print("   jobs=%s" % (jobs,))
                print("   orderP=%s  orderF=%s" % (list(oP), list(oF)))
print("refined two-sided local bound failures:", bad, " worst |D|/max(lam) =", worst)
