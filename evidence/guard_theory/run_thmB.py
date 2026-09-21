"""Numerical attack on Theorem B of theory.md: the CAPPED RELATIVE budget

    budget_q(t) = min( B0_q + eta*k*(t - a_q), Bmax ),   0 <= eta < 1
    E(t)        = { waiting q : over_q(t) >= budget_q(t) }
    dispatch     min-rank member of E, else whatever the base policy wants.

Checked:
  (B1)  (k - eta*k) W_guard[i] <= k W_FCFS[i] + B0_i + (3k-2) L
  (B2)  with a cap,  W_guard[i] <= W_FCFS[i] + Bmax/k + (3-2/k) L
  (B3)  the design rule Bmax = k(G - (3-2/k)L)  gives  excess <= G
  (B4)  In_i < B0_i + eta*k*W_guard[i] + kL   (the step the proof turns on)

Exhaustive over every work-conserving base tape on small instances, plus a
large random sweep.  Exact integers: eta = en/ed and every test is cross
multiplied.  Run:

    env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME \
        uv run --with numpy --with numba python run_thmB.py
"""
import sys
sys.dont_write_bytecode = True

import itertools
from fractions import Fraction

import numpy as np
from numba import njit

import sharp_kernel as K


@njit(cache=True)
def check(a, x, k, tape, C, en, ed, Bmax, st, od, fr, wt, stF, odF, pos, res):
    """res[0] = #B1 failures, res[1] = #B2 failures, res[2] = #B4 failures,
    res[3] = max over i of ed*(k-en/ed*k)... (kept as the worst slack numerator),
    res[4] = worst (k*excess - Bmax)/1 when a cap is in force."""
    n = a.shape[0]
    if K.sched_guardB(a, x, k, tape, C, en, ed, Bmax, st, od, fr, wt) < 0:
        return -1
    if K.sched(a, x, k, tape, 0, stF, odF, fr, wt) < 0:
        return -1
    L = 0
    for j in range(n):
        if x[j] > L:
            L = x[j]
    for p in range(n):
        pos[od[p]] = p
    for i in range(n):
        W = st[i] - a[i]
        WF = stF[i] - a[i]
        # (B1) (k*ed - en*k) W <= ed*(k WF + C_i + (3k-2)L)
        if (k * ed - en * k) * W > ed * (k * WF + C[i] + (3 * k - 2) * L):
            res[0] += 1
        # (B2) k*W <= k*WF + Bmax + (3k-2)L
        if Bmax > 0 and k * W > k * WF + Bmax + (3 * k - 2) * L:
            res[1] += 1
        In = 0
        for j in range(i + 1, n):
            if pos[j] < pos[i]:
                In += x[j]
        # (B4) ed*In < ed*C_i + en*k*W + ed*k*L   (and In < Bmax + kL under a cap).
        # The strict form is claimed only when i actually HAS an overtaker; with
        # In_i = 0 and L = 0 (every job of zero work) both sides are 0.
        if In > 0:
            if ed * In >= ed * C[i] + en * k * W + ed * k * L:
                res[2] += 1
            if Bmax > 0 and In >= Bmax + k * L:
                res[3] += 1
        v = k * (W - WF)
        if v > res[4]:
            res[4] = v
    return 0


def run_random(iters, seed):
    rng = np.random.default_rng(seed)
    tot = np.zeros(5, np.int64)
    checks = 0
    worst = Fraction(-10 ** 9)
    for _ in range(iters):
        n = int(rng.integers(2, 13))
        k = int(rng.integers(1, 6))
        L = int(rng.integers(1, 12))
        a = np.sort(rng.integers(0, 3 * n, n)).astype(np.int64)
        a = a - a[0]
        x = rng.integers(0, L + 1, n).astype(np.int64)
        L = int(max(1, x.max()))
        tape = rng.integers(0, 1 << 20, n).astype(np.int64)
        ed = int(rng.integers(1, 9))
        en = int(rng.integers(0, ed))          # eta = en/ed in [0,1)
        C = rng.integers(0, 3 * L + 1, n).astype(np.int64)
        Bmax = int(rng.integers(-1, 6 * k * L))
        st, od, fr, wt = (np.empty(n, np.int64), np.empty(n, np.int64),
                          np.empty(k, np.int64), np.empty(n, np.int64))
        stF, odF, pos = (np.empty(n, np.int64), np.empty(n, np.int64),
                         np.empty(n, np.int64))
        res = np.zeros(5, np.int64)
        if check(a, x, k, tape, C, en, ed, Bmax, st, od, fr, wt, stF, odF,
                 pos, res) < 0:
            continue
        tot[:4] += res[:4]
        checks += n
        if Bmax > 0:
            f = Fraction(int(res[4]) - Bmax, L)
            if f > worst:
                worst = f
    return tot, checks, worst


@njit(cache=True)
def exh_one(a, x, k, L, out):
    """Every base tape (hence every work-conserving schedule the base could
    produce), every eta in {0, 1/2, 3/4}, every cap in {none, 0, kL, 3kL},
    every B0 in {0, L, 2L}, for ONE instance.  out[0..2] += failures,
    out[3] += job-checks, out[4] += (tape, parameter) combinations."""
    n = a.shape[0]
    st = np.empty(n, np.int64); od = np.empty(n, np.int64)
    fr = np.empty(k, np.int64); wt = np.empty(n, np.int64)
    stF = np.empty(n, np.int64); odF = np.empty(n, np.int64)
    pos = np.empty(n, np.int64); res = np.zeros(5, np.int64)
    tape = np.empty(n, np.int64); C = np.empty(n, np.int64)
    ntape = 1
    for _ in range(n):
        ntape *= n
    for code in range(ntape):
        c = code
        for j in range(n):
            tape[j] = c % n
            c //= n
        for e in range(3):
            if e == 0:
                en = 0; ed = 1
            elif e == 1:
                en = 1; ed = 2
            else:
                en = 3; ed = 4
            for bi in range(4):
                if bi == 0:
                    Bmax = -1
                elif bi == 1:
                    Bmax = 0
                elif bi == 2:
                    Bmax = k * L
                else:
                    Bmax = 3 * k * L
                for ci in range(3):
                    for j in range(n):
                        C[j] = ci * L
                    for q in range(5):
                        res[q] = 0
                    if check(a, x, k, tape, C, en, ed, Bmax, st, od, fr, wt,
                             stF, odF, pos, res) < 0:
                        continue
                    out[0] += res[0]; out[1] += res[1]
                    out[2] += res[2] + res[3]
                    out[3] += n
                    out[4] += 1


def run_exhaustive(ninst_per=140, seed=99):
    rng = np.random.default_rng(seed)
    out = np.zeros(5, np.int64)
    ninst = 0
    for k in (1, 2, 3):
        for n in (3, 4, 5):
            for L in (2, 3):
                for _ in range(ninst_per):
                    a = np.sort(rng.integers(0, 4, n)).astype(np.int64)
                    a = a - a[0]
                    x = rng.integers(0, L + 1, n).astype(np.int64)
                    x[int(rng.integers(0, n))] = L
                    exh_one(a, x, k, L, out)
                    ninst += 1
    return out[:3], int(out[3]), ninst, int(out[4])


def main():
    print("THEOREM B (capped relative budget) -- numerical attack")
    print()
    bad, checks, ninst, ncomb = run_exhaustive()
    print("EVERY base tape (hence every work-conserving schedule), eta in")
    print("  {0, 1/2, 3/4}, caps in {none, 0, kL, 3kL}, B0 in {0, L, 2L},")
    print("  k<=3, n<=5, L<=3:")
    print("  %d instances, %d (schedule, parameter) combinations, %d job-checks"
          % (ninst, ncomb, checks))
    print("  (B1) (k-eta*k)W <= kW_F + B0 + (3k-2)L : %d failures" % bad[0])
    print("  (B2) capped form W <= W_F + Bmax/k + (3-2/k)L : %d failures" % bad[1])
    print("  (B4) In_i < B0 + eta*k*W + kL (and In < Bmax + kL) : %d failures"
          % bad[2])
    print()
    tot, checks, worst = run_random(120000, 606)
    print("random: 120,000 instances, %d job-checks, k<=5, eta = en/ed in [0,1)"
          % checks)
    print("  (B1) %d failures   (B2) %d failures   (B4) %d failures"
          % (tot[0], tot[1], tot[2]))
    print("  (B4a) In_i < B0_i + eta*k*W + kL : %d failures" % tot[2])
    print("  (B4b) under a cap, In_i < Bmax + kL : %d failures" % tot[3])
    print("  worst observed (k*excess - Bmax)/L under a cap: %s = %.4f"
          "   (bound 3k-2 <= 13)" % (worst, float(worst)))
    print()
    print("design rule: Bmax = k(G - (3-2/k)L) makes (B2) read excess <= G;")
    print("it is usable only when G > (3-2/k)L, i.e. G > 3L is always safe.")


if __name__ == "__main__":
    main()
