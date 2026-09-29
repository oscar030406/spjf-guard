"""Smallest witness for the (B4a) failures seen by run_thmB.py: is the step
    In_i < B0_i + eta*k*W_guard[i] + kL
true when the base budgets B0_q differ from job to job?
"""
import sys
sys.dont_write_bytecode = True

import numpy as np
import sharp_kernel as K

rng = np.random.default_rng(606)
best = None
for _ in range(150000):
    n = int(rng.integers(2, 13))
    k = int(rng.integers(1, 6))
    L = int(rng.integers(1, 12))
    a = np.sort(rng.integers(0, 3 * n, n)).astype(np.int64)
    a = a - a[0]
    x = rng.integers(0, L + 1, n).astype(np.int64)
    L = int(max(1, x.max()))
    tape = rng.integers(0, 1 << 20, n).astype(np.int64)
    ed = int(rng.integers(1, 9))
    en = int(rng.integers(0, ed))
    C = rng.integers(0, 3 * L + 1, n).astype(np.int64)
    st, od = np.empty(n, np.int64), np.empty(n, np.int64)
    fr, wt = np.empty(k, np.int64), np.empty(n, np.int64)
    Bmax = int(rng.integers(-1, 6 * k * L))
    if K.sched_guardB(a, x, k, tape, C, en, ed, Bmax, st, od, fr, wt) < 0:
        continue
    pos = np.empty(n, np.int64)
    for p in range(n):
        pos[od[p]] = p
    for i in range(n):
        W = int(st[i] - a[i])
        In = sum(int(x[j]) for j in range(i + 1, n) if pos[j] < pos[i])
        if ed * In >= ed * int(C[i]) + en * k * W + ed * k * L:
            if best is None or n < best[0]:
                best = (n, k, L, a.copy(), x.copy(), C.copy(), en, ed,
                        Bmax,
                        st.copy(), od.copy(), i, In, W)
if best is None:
    print("no (B4a) failure found")
    raise SystemExit
n, k, L, a, x, C, en, ed, Bmax, st, od, i, In, W = best
print("smallest (B4a) witness: n=%d k=%d L=%d eta=%d/%d Bmax=%d" % (n, k, L, en, ed, Bmax))
print("  a     =", list(a))
print("  x     =", list(x))
print("  B0    =", list(C))
print("  guard : starts", list(st), " dispatch order", list(od))
print("  victim i=%d  W=%d  In_i=%d" % (i, W, In))
print("  claim : In_i < B0_i + eta*k*W + kL = %d + %d*%d*%d/%d + %d*%d = %s"
      % (C[i], en, k, W, ed, k, L,
         float(C[i]) + en * k * W / ed + k * L))
print()
print("  what the guard saw, dispatch by dispatch:")
for p, j in enumerate(od):
    t = int(st[j])
    ov = sum(int(x[q]) for q in range(i + 1, n)
             if st[q] + x[q] <= t and st[q] < t + 1 and int(st[q]) != -(1 << 60))
    ovi = 0
    for q in range(i + 1, n):
        if int(st[q]) + int(x[q]) <= t:
            ovi += int(x[q])
    bud = float(C[i]) + en * (t - int(a[i])) / ed
    print("    t=%-3d dispatch rank %-2d   over_i(t)=%-3d  budget_i(t)=%-6.2f  %s"
          % (t, j, ovi, bud, "i FIRED" if ovi >= bud else ""))
