"""Audit of the five PROOF STEPS individually, not just of the final inequality.

For every job i of every instance, using the guard schedule and the FCFS schedule:

 (1)  k*W_i == E_old + E_new                       (all k servers busy while i waits)
 (2)  E_old <= R_i
 (3a) over_i(t_last) <  budget_i(t_last)           (i not in the fired set)
 (3b) #overtakers in service when the LAST overtaker is placed  <= k-1
 (3c) S_new (total service of dispatched overtakers) < budget_i(t_last) + k*L
 (3d) E_new <= S_new
 (4)  k*W^F_i >= R^F_i - (k-1)L
 (5)  R_i <= R^F_i + (k-1)L

t_last = the last instant in [a_i, start_i) at which an overtaker of i is dispatched.
Pure python, exact rational/integer arithmetic.
"""
import sys
sys.dont_write_bytecode = True
import random
from fractions import Fraction
from refsim import simulate

ITER = int(sys.argv[1]) if len(sys.argv) > 1 else 30000
SEED = int(sys.argv[2]) if len(sys.argv) > 2 else 12345
random.seed(SEED)

names = ["1 k*W=E_old+E_new", "2 E_old<=R_i", "3a over<budget", "3b <=k-1 in service",
         "3c S_new<bud+kL", "3d E_new<=S_new", "4 kW_F>=R_F-(k-1)L",
         "5 R_i<=R_F+(k-1)L"]
bad = [0] * 8
tot = 0
worst_inservice = 0
worst_slack3c = None
ex = [None] * 8

for trial in range(ITER):
    n = random.randint(2, 9)
    k = random.randint(1, 4)
    L = random.randint(1, 4)
    m = random.randint(0, 2)
    if m == 0:
        a = [0] * n
    elif m == 1:
        a = sorted(random.randint(0, 5) for _ in range(n))
    else:
        a = sorted(random.choice([0, 0, 0, 2, 2, 5]) for _ in range(n))
    s = [random.choice([L, random.randint(1, L)]) for _ in range(n)]
    pred = [random.randint(0, n) for _ in range(n)]
    B0 = random.randint(0, n * L + 1)
    Bmax = random.choice([B0, B0 + 2, 10 ** 9])
    ec = [Fraction(0), Fraction(1, 2), Fraction(1), Fraction(2 * k - 1, 2)]
    eps = random.choice([e for e in ec if e < k])
    st, cp = simulate(a, s, pred, k, "guard", B0=B0, Bmax=Bmax, eps=eps)
    stf, cpf = simulate(a, s, pred, k, "fcfs")

    def overlap(j, lo, hi):
        return max(0, min(cp[j], hi) - max(st[j], lo))

    for i in range(n):
        tot += 1
        W = st[i] - a[i]
        lo, hi = a[i], st[i]
        E_old = sum(overlap(j, lo, hi) for j in range(i))
        E_new = sum(overlap(j, lo, hi) for j in range(i + 1, n))
        rec = (a, s, pred, k, B0, Bmax, str(eps), i)
        if k * W != E_old + E_new:
            bad[0] += 1
            ex[0] = ex[0] or rec
        R_i = 0
        for j in range(i):
            if cp[j] <= a[i]:
                pass
            elif st[j] <= a[i]:
                R_i += cp[j] - a[i]
            else:
                R_i += s[j]
        if E_old > R_i:
            bad[1] += 1
            ex[1] = ex[1] or rec
        ov = [j for j in range(i + 1, n) if a[i] <= st[j] < st[i]]
        if ov:
            tl = max(st[j] for j in ov)
            over = sum(s[j] for j in range(i + 1, n) if cp[j] <= tl and cp[j] > a[i])
            bud = min(Fraction(Bmax), B0 + eps * (tl - a[i]))
            if not over < bud:
                bad[2] += 1
                ex[2] = ex[2] or rec
            nis = sum(1 for j in ov if st[j] < tl < cp[j])
            nis += sum(1 for j in ov if st[j] == tl) - 1
            if nis > worst_inservice:
                worst_inservice = nis
            if nis > k - 1:
                bad[3] += 1
                ex[3] = ex[3] or rec
            S_new = sum(s[j] for j in ov)
            if not S_new < bud + k * L:
                bad[4] += 1
                ex[4] = ex[4] or rec
            sl = float(bud + k * L - S_new)
            if worst_slack3c is None or sl < worst_slack3c:
                worst_slack3c = sl
            if E_new > S_new:
                bad[5] += 1
                ex[5] = ex[5] or rec
        WF = stf[i] - a[i]
        R_F = 0
        for j in range(i):
            if cpf[j] <= a[i]:
                pass
            elif stf[j] <= a[i]:
                R_F += cpf[j] - a[i]
            else:
                R_F += s[j]
        if k * WF < R_F - (k - 1) * L:
            bad[6] += 1
            ex[6] = ex[6] or rec
        if R_i > R_F + (k - 1) * L:
            bad[7] += 1
            ex[7] = ex[7] or rec

print("instances=%d  job-checks=%d" % (ITER, tot))
for q in range(8):
    print("  step %-22s failures=%d" % (names[q], bad[q]))
    if ex[q] is not None:
        print("       first: a=%s s=%s pred=%s k=%d B0=%d Bmax=%d eps=%s job=%d"
              % ex[q])
print("  max overtakers in service at the last overtaker dispatch = %d (bound k-1)"
      % worst_inservice)
print("  tightest slack in step (3c) = %s" % worst_slack3c)
