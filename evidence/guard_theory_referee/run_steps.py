"""Per-step audit of the proof of Theorem 1.  Every intermediate quantity of
theory.md's proof is recomputed from the simulation and each displayed step is
checked separately, so that a failure localises to a step rather than to the
theorem.

  (1) k*W_P[i]  = R^P_i + In_i - Out_i - rho^P_i
  (2) k*W_F[i]  = R^F_i - rho^F_i                     (and In^F = Out^F = 0)
  (2') 0 <= rho^Q_i <= (k-1)L                          (step 2)
  (4) U_P(a_i) - U_F(a_i) = R^P_i - R^F_i  and  |R^P_i - R^F_i| <= (k-1)L
  Lemma 1: |U_P(t) - U_F(t)| <= (k-1)L at every event time
"""
import sys, random
sys.dont_write_bytecode = True
from refsim2 import (simulate, fcfs_chooser, make_choice_chooser, in_out)


def remaining(a, x, start, comp, t, mask=None):
    """unfinished work at time t of the jobs in mask (default: all arrived)."""
    U = 0
    for j in range(len(a)):
        if mask is not None and not mask(j):
            continue
        if a[j] <= t and t < comp[j]:
            U += x[j] if t <= start[j] else comp[j] - t
    return U


def rho(a, x, start, comp, order, i):
    """theory.md's rho^Q_i: total remaining work at s_i of the jobs DISPATCHED
    BEFORE i (in the dispatch sequence) that are still in service at s_i.
    A job dispatched in the same phase but AFTER i is not in service yet and is
    accounted for in Out_i at full work."""
    pos = [0] * len(a)
    for p, j in enumerate(order):
        pos[j] = p
    t = start[i]
    s = 0
    for j in range(len(a)):
        if j != i and pos[j] < pos[i] and start[j] <= t < comp[j]:
            s += comp[j] - t
    return s


def main():
    rng = random.Random(8080)
    log = open("out_steps.txt", "w")
    cnt = {k: 0 for k in ["n", "e1", "e2", "erho", "e4", "eR", "lem1", "inF"]}
    for trial in range(60000):
        n = rng.randint(1, 8)
        k = rng.randint(1, 4)
        a = sorted(rng.randint(0, 6) for _ in range(n))
        x = [rng.randint(0, 5) for _ in range(n)]
        if max(x) == 0:
            continue
        L = max(x)
        tp = [rng.randint(0, 8) for _ in range(n)]
        fst, fcp, fod = simulate(a, x, k, fcfs_chooser)
        st, cp, od = simulate(a, x, k, make_choice_chooser(tp))
        In, Out = in_out(x, od, n)
        InF, OutF = in_out(x, fod, n)
        if any(InF) or any(OutF):
            cnt["inF"] += 1
        times = sorted(set(a) | set(st) | set(cp) | set(fst) | set(fcp))
        for t in times:
            UP = remaining(a, x, st, cp, t)
            UF = remaining(a, x, fst, fcp, t)
            if abs(UP - UF) > (k - 1) * L:
                cnt["lem1"] += 1
        for i in range(n):
            cnt["n"] += 1
            RP = remaining(a, x, st, cp, a[i], mask=lambda j: j < i)
            RF = remaining(a, x, fst, fcp, a[i], mask=lambda j: j < i)
            rP = rho(a, x, st, cp, od, i)
            rF = rho(a, x, fst, fcp, fod, i)
            WP = st[i] - a[i]
            WF = fst[i] - a[i]
            if k * WP != RP + In[i] - Out[i] - rP:
                cnt["e1"] += 1
                if cnt["e1"] <= 3:
                    log.write("  STEP(1) FAILS a=%s x=%s k=%d od=%s i=%d "
                              "kW=%d RP=%d In=%d Out=%d rho=%d\n"
                              % (a, x, k, od, i, k * WP, RP, In[i], Out[i], rP))
            if k * WF != RF - rF:
                cnt["e2"] += 1
                if cnt["e2"] <= 3:
                    log.write("  STEP(2) FAILS a=%s x=%s k=%d i=%d kWF=%d "
                              "RF=%d rhoF=%d\n" % (a, x, k, i, k * WF, RF, rF))
            if not (0 <= rP <= (k - 1) * L) or not (0 <= rF <= (k - 1) * L):
                cnt["erho"] += 1
            UPa = remaining(a, x, st, cp, a[i])
            UFa = remaining(a, x, fst, fcp, a[i])
            if UPa - UFa != RP - RF:
                cnt["e4"] += 1
            if abs(RP - RF) > (k - 1) * L:
                cnt["eR"] += 1
    log.write("per-step audit of Theorem 1: job-checks=%d\n" % cnt["n"])
    log.write("  step (1) k W_P = R^P + In - Out - rho^P   : %d failures\n" % cnt["e1"])
    log.write("  step (2) k W_F = R^F - rho^F              : %d failures\n" % cnt["e2"])
    log.write("  step (3) In^F = Out^F = 0                 : %d failures\n" % cnt["inF"])
    log.write("  step (2) 0 <= rho <= (k-1)L               : %d failures\n" % cnt["erho"])
    log.write("  step (4) U_P(a_i)-U_F(a_i) = R^P-R^F      : %d failures\n" % cnt["e4"])
    log.write("  step (4) |R^P-R^F| <= (k-1)L              : %d failures\n" % cnt["eR"])
    log.write("  Lemma 1 |U_P-U_F| <= (k-1)L at all events : %d failures\n" % cnt["lem1"])
    log.close()
    print(open("out_steps.txt").read())


if __name__ == "__main__":
    main()
