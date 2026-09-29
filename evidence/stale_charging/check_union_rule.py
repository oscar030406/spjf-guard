"""Guard OR clock: which job is served when both fire (derivation.md, Section 5).

UN  serves the minimum-rank member of E(t) union A_theta(t), A_theta = {waiting q : t - a_q >= theta}.
    A_theta is a prefix of the waiting set, so UN is "the head if aged, otherwise Algorithm 1".
UG  guard-first: the minimum-rank member of E(t) if E is non-empty, else the head if aged, else
    the base policy.  This is the reading evidence/new_theory_refutation/refutation.md refutes.

Part 1 replays the refuter's two witnesses (refutation.md, section P-union) under both rules.
Part 2 runs the same random instances under both rules, with constant, queue-length (gamma),
age-relative (eta) and mixed budget shapes, and delta in {0, 1..2L, INF}.

Run from the repository root:
  env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME NUMBA_NUM_THREADS=4 OMP_NUM_THREADS=4 \
    uv run --no-sync python -u evidence/stale_charging/check_union_rule.py \
    > evidence/stale_charging/out_check_union_rule.txt
"""

import os
import sys
import time

import numpy as np
from numba import njit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim_stale import (  # noqa: E402
    CHECKS,
    INF,
    MODEL_NAMES,
    NCHK,
    UG,
    UN,
    check_run,
    fcfs_starts,
    gen_random,
    make_work_nb,
    sim_guard,
)

SHAPES = ("const", "gamma", "eta", "mixed")


def replay(name, k, L, a, C, key, B0, gam, eta, Bmax, theta, model):
    a = np.array(a, np.int64)
    C = np.array(C, np.int64)
    key = np.array(key, np.float64)
    n = len(a)
    delay = np.zeros(n, np.int64)
    fs = np.zeros(n, np.int64)
    fcfs_starts(k, a, C, fs, np.zeros(k, np.int64))
    w, sc = make_work_nb(n, k)
    sim_guard(k, a, C, key, B0, gam, eta, Bmax, model, delay, 0, theta, w)
    viol = np.zeros(NCHK, np.int64)
    r = np.array([-1.0, 0, 0, 0])
    check_run(k, L, 0, a, C, fs, B0, gam, eta, Bmax, model, theta, w, viol, sc, r)
    start = w[0]
    exc = start - fs
    worst = int(np.argmax(exc))
    vv = " ".join(f"{CHECKS[c]}={viol[c]}" for c in range(NCHK) if viol[c]) or "none"
    print(
        f"   {name:34s} {MODEL_NAMES[model]}  starts {start.tolist()}  FCFS {fs.tolist()}"
        f"  max excess {int(exc[worst])} (job {worst})  clock bound {theta + (3 - 2 / k) * L:.2f}"
        f"  violations {vv}"
    )


@njit(cache=True)
def seed_nb(s):
    np.random.seed(s)


@njit(cache=True)
def draw_budget(shape, L):
    Bmax = np.random.randint(0, 6 * L + 1)
    B0, gam, eta = float(Bmax), 0.0, 0.0
    if shape == 1 or shape == 3:
        B0 = float(np.random.randint(0, Bmax + 1))
        gam = np.array([0.5, 1.0, 2.0, 3.0])[np.random.randint(0, 4)]
    if shape == 2 or shape == 3:
        if shape == 2:
            B0 = float(np.random.randint(0, Bmax + 1))
        eta = np.array([0.125, 0.25, 0.5, 0.75])[np.random.randint(0, 4)]
    return Bmax, B0, gam, eta


@njit(cache=True)
def random_pair(nrun, viol, cnt, worst):
    """viol[rule, shape, k-1, check], cnt[rule, shape, k-1], worst[rule, shape, k-1] = max excess/clock bound.
    rule 0 = UN, 1 = UG; both run on the same instance."""
    Ls = np.array([3, 4, 6, 10])
    vtmp = np.zeros(NCHK, np.int64)
    r = np.zeros(4, np.float64)
    for it in range(nrun):
        k = np.random.randint(1, 5)
        n = np.random.randint(2, 41)
        L = Ls[np.random.randint(0, 4)]
        dm = np.random.randint(0, 3)
        delta = 0 if dm == 0 else (np.random.randint(1, 2 * L + 1) if dm == 1 else INF)
        theta = np.random.randint(0, 3 * L + 1)
        shape = np.random.randint(0, 4)
        so = np.random.randint(0, 2)
        a = np.zeros(n, np.int64)
        C = np.zeros(n, np.int64)
        key = np.zeros(n, np.float64)
        delay = np.zeros(n, np.int64)
        gen_random(n, L, a, C, key, delay, delta)
        Bmax, B0, gam, eta = draw_budget(shape, L)
        fs = np.zeros(n, np.int64)
        fcfs_starts(k, a, C, fs, np.zeros(k, np.int64))
        for rule in range(2):
            model = UN if rule == 0 else UG
            w, sc = make_work_nb(n, k)
            sim_guard(k, a, C, key, B0, gam, eta, Bmax, model, delay, so, theta, w)
            r[0] = -1.0
            for c in range(NCHK):
                vtmp[c] = 0
            check_run(k, L, delta, a, C, fs, B0, gam, eta, Bmax, model, theta, w, vtmp, sc, r)
            cnt[rule, shape, k - 1] += 1
            for c in range(NCHK):
                viol[rule, shape, k - 1, c] += vtmp[c]
            if r[0] > worst[rule, shape, k - 1]:
                worst[rule, shape, k - 1] = r[0]


def main():
    print("check_union_rule.py: guard OR clock, head-first (UN) against guard-first (UG)")
    print("-- Part 1: the refuter's witnesses (refutation.md, P-union), delta = 0")
    print("   witness 1: k=1 L=3 theta=4 (refuter: 3.5; same schedule, integer time), budget min(3 n_q, 5)")
    for model in (UN, UG):
        replay("GFEX k=1 (gamma shape)", 1, 3, [0, 0, 0, 2, 2, 2], [1, 1, 1, 3, 1, 3],
               [0, 1, 5, 4, 2, 3], 0.0, 3.0, 0.0, 5, 4, model)
    print("   witness 2: k=1 L=3 theta=0, budget min(k age / 4, 6), base SJF")
    for model in (UN, UG):
        replay("eta witness k=1 (eta shape)", 1, 3, [0, 1, 2], [2, 3, 3], [2, 3, 3], 0.0, 0.0, 0.25, 6, 0, model)
    nrun = 200_000
    seed = 20260924
    print(f"-- Part 2: {nrun} random instances, seed {seed}, each run under UN and UG;")
    print("   k in 1..4, n in 2..40, L in {3,4,6,10}, theta in 0..3L, delta 0 / 1..2L / INF (one third each)")
    print("   ratio: max over jobs of excess / (theta + (3-2/k)L); CLOCK and CLKIN are the clock half,")
    print("   EXCESS/IN/GUARD/... the guard half with late charges (vacuous at delta = INF)")
    t0 = time.time()
    viol = np.zeros((2, 4, 4, NCHK), np.int64)
    cnt = np.zeros((2, 4, 4), np.int64)
    worst = np.full((2, 4, 4), -1.0)
    seed_nb(seed)
    random_pair(nrun, viol, cnt, worst)
    print("   rule  shape  k    runs  worst ratio  violations(by check)")
    for rule in range(2):
        for sh in range(4):
            for k in range(4):
                vv = " ".join(f"{CHECKS[c]}={viol[rule, sh, k, c]}" for c in range(NCHK) if viol[rule, sh, k, c])
                print(f"   {('UN', 'UG')[rule]:4s}  {SHAPES[sh]:5s}  {k + 1}  {cnt[rule, sh, k]:6d}  {worst[rule, sh, k]:11.4f}"
                      f"  {vv or 'none'}")
    for rule in range(2):
        print(f"   TOTAL {('UN', 'UG')[rule]}: runs {int(cnt[rule].sum())}, violations {int(viol[rule].sum())}")
    print(f"   wall {time.time() - t0:.1f} s")


if __name__ == "__main__":
    main()
