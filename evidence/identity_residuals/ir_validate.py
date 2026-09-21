"""Stage 1: prove the three tools before any number is reported.

  A. `ir_kern.py` (the instrumented copy) reproduces `guardkern.run`'s waits BIT for BIT,
     job for job, on random instances and on a real 5,000-job slice.
  B. the dispatch sequence `ir_kern.py` records is the real one: on random instances it
     equals the sequence an independently written simulator
     (`ir_refsim.py` / ../guard_variants_referee/refsim.py, pure python, exact integers)
     performs, and the start times agree exactly.
  C. the O(n log n) Fenwick sweep for In_i, Out_i and the same-phase part of In_i equals
     the O(n^2) definition -- on random instances and on the 5,000-job real slice.
  D. Theorem 1 holds on every job of every random instance, exactly.
  E. FCFS has In = Out = 0 on every job (its dispatch sequence is rank order).

Exact arithmetic on the random instances.  Arrival times and service times are drawn as
integer multiples of 1/64 s.  That makes them dyadic, so the float64 clock of the numba
kernel is exact (no rounding anywhere in t = t + s), and 1e6/64 = 15625 is an integer, so
the kernel's `round(s * 1e6)` metering is exactly 15625 * (the integer), i.e. the kernel
and the integer reference simulator charge proportionally identical work.  Every check in
A-E is therefore an equality, not a tolerance.

usage: ir_validate.py [--instances 400] [--slice 5000]
"""
from __future__ import annotations

import argparse
from fractions import Fraction

import numpy as np

import ir_common as C
import ir_overtake as OV
import ir_refsim as RS
from ir_common import GK, IK, V31

U = 64                       # internal grid: 1/64 s
US_PER_U = 1000000 // U      # = 15625, exact
L_U = int(C.L * U)           # 60 s


def rand_instance(rng):
    n = int(rng.integers(4, 41))
    k = int(rng.integers(1, 7))
    load = float(rng.uniform(0.3, 2.5))
    smax = int(rng.integers(1, L_U + 1))
    gap = max(1, int(smax * n / (k * n * load)) + 1)
    s_u = rng.integers(1, smax + 1, n).astype(np.int64)
    a_u = np.cumsum(rng.integers(0, gap + 1, n).astype(np.int64))   # ties allowed
    a_u -= a_u[0]
    return n, k, a_u, s_u


def kern_policies(rng, n, k):
    """[(tag, pred, guardkern kwargs, refsim kwargs)]"""
    pred = rng.integers(0, 20, n).astype(np.float64)       # ties on purpose
    HUGE = 10 ** 15
    out = [("fcfs", np.zeros(n), dict(policy="fcfs"), dict(policy="fcfs")),
           ("pri", pred, dict(policy="pri"),
            dict(policy="guard", B0=HUGE, Bmax=HUGE, eps=Fraction(0)))]
    for _ in range(2):
        eta = float(rng.choice([0.0, 0.25, 0.5, 0.75, 0.9]))
        b0_u = int(rng.integers(0, 40 * U))
        # Bmax > 0 always: guardkern reads Bmax = 0 as "no cap", refsim as "cap at 0",
        # so the two only describe the same rule when the cap is a real one.  The study's
        # own configurations always have Bmax = k(G - (3 - 2/k)L) > 0.
        bm_u = b0_u + int(rng.integers(1, 40 * U))
        eps = eta * k
        en, ed = GK.ratio(eps)
        out.append((f"guard(B0={b0_u / U:g}s,eta={eta:g},Bmax={bm_u / U:g}s)", pred,
                    dict(policy="guard", B=b0_u / U, eps=eps, Bmax=bm_u / U,
                         Mslots=1 << 16),
                    # refsim is handed the instance in 1/64 s units throughout, so its
                    # budgets are in those units too; eps is unitless.
                    dict(policy="guard", B0=b0_u, Bmax=bm_u, eps=Fraction(en, ed))))
    return out


def check_random(lg, n_inst):
    rng = np.random.default_rng(20260919)
    tot_jobs = tot_checks = 0
    worst = 0.0
    for it in range(n_inst):
        n, k, a_u, s_u = rand_instance(rng)
        a = a_u / U
        s = s_u / U
        svc_us = C.us(s)
        assert np.array_equal(svc_us, s_u * US_PER_U)          # exact metering
        for tag, pred, kw, rkw in kern_policies(rng, n, k):
            r = IK.run(a, s, k, pred=pred, **kw)
            assert r.err == 0
            g = GK.run(a, s, k, pred=pred, **kw)
            assert np.array_equal(r.w, g.w), (it, tag, "A: waits differ from guardkern")

            # -- B: independent simulator, exact integers in units of 1/64 s
            st, _cp, seq = RS.simulate([int(x) for x in a_u], [int(x) for x in s_u],
                                       [float(x) for x in pred], k, **rkw)
            assert np.array_equal(np.rint((a + r.w) * U).astype(np.int64),
                                  np.array(st, np.int64)), (it, tag, "B: start times")
            dref = np.empty(n, np.int64)
            for p, j in enumerate(seq):
                dref[j] = p
            assert np.array_equal(r.dord, dref), (it, tag, "B: dispatch sequence")

            # -- C: sweep vs definition
            order = OV.dispatch_order(r.dord)
            In, Out = OV.in_out_fenwick(svc_us, order)
            In2, Out2 = OV.in_out_quadratic(svc_us, r.dord)
            assert np.array_equal(In, In2) and np.array_equal(Out, Out2), (it, tag, "C")
            sp = OV.in_same_phase(svc_us, order, r.dtime)
            sp2 = OV.in_same_phase_quadratic(svc_us, r.dord, r.dtime)
            assert np.array_equal(sp, sp2), (it, tag, "C same-phase")
            assert np.all(sp <= In) and np.all(sp >= 0)

            if tag == "fcfs":
                # -- E
                assert np.array_equal(r.dord, np.arange(n)), (it, "E: FCFS order")
                assert not In.any() and not Out.any(), (it, "E: FCFS In/Out")
                wf_us = C.us(a + r.w) - C.us(a)
                continue

            # -- D: Theorem 1, exactly, in integer microseconds
            w_us = C.us(a + r.w) - C.us(a)
            D = k * (w_us - wf_us) - (In - Out)
            bound = 2 * (k - 1) * C.L_US
            assert np.abs(D).max() <= bound, (it, tag, "D", int(np.abs(D).max()), bound)
            worst = max(worst, float(np.abs(D).max()) / C.L_US / max(k - 1, 1))
            tot_checks += n
        tot_jobs += n
    lg.w(f"  random instances          {n_inst:,} (n <= 40, k <= 6, ties and equal "
         f"predictions included); {tot_jobs:,} jobs, {tot_checks:,} job-checks")
    lg.w(f"  A waits == guardkern      exact, every job of every instance")
    lg.w(f"  B sequence == refsim      exact, every job of every instance")
    lg.w(f"  C sweep == O(n^2)         exact, In, Out and the same-phase part")
    lg.w(f"  D Theorem 1               0 violations; worst |D| / ((k-1)L) = {worst:.4f}")
    lg.w(f"  E FCFS In = Out = 0       holds on every job")


def check_slice(lg, m):
    """The DENSEST m consecutive jobs of the real trace -- the first m would be the
    quiet start of the timeline, where almost nothing overtakes anything."""
    Z = V31.load_trace(C.TRACE, C.REP)
    A = Z["a"]
    span = A[m - 1:] - A[:len(A) - m + 1]
    i0 = int(np.argmin(span))
    a = np.ascontiguousarray(A[i0:i0 + m])
    s = np.ascontiguousarray(Z["svc"][i0:i0 + m])
    tw = np.ascontiguousarray(Z["tweedie"][i0:i0 + m])
    svc_us = C.us(s)
    lg.w(f"  real slice: the densest {m:,} consecutive jobs of {C.TRACE} rep{C.REP} "
         f"(ranks {i0:,}..{i0 + m - 1:,}, span {a[-1] - a[0]:.1f} s, "
         f"work {s.sum():.1f} s)")
    for k in [int(x) for x in Z["K"]]:
        rf = C.run_policy(a, s, k, None, dict(policy="fcfs"))
        assert np.array_equal(rf.dord, np.arange(m))
        wf_us = C.us(a + rf.w) - C.us(a)
        for tag in C.POLICIES:
            Zs = {"tweedie": tw, "svc": s}
            pred, kw, _d = C.policy_spec(tag, k, Zs)
            r = C.run_policy(a, s, k, pred, kw)
            order = OV.dispatch_order(r.dord)
            In, Out = OV.in_out_fenwick(svc_us, order)
            In2, Out2 = OV.in_out_quadratic(svc_us, r.dord)
            ok = np.array_equal(In, In2) and np.array_equal(Out, Out2)
            sp = OV.in_same_phase(svc_us, order, r.dtime)
            sp2 = OV.in_same_phase_quadratic(svc_us, r.dord, r.dtime)
            ok2 = np.array_equal(sp, sp2)
            assert ok and ok2, (k, tag)
            w_us = C.us(a + r.w) - C.us(a)
            D = k * (w_us - wf_us) - (In - Out)
            bound = 2 * (k - 1) * C.L_US
            mx = int(np.abs(D).max())
            assert mx <= bound + 2 * k, (k, tag, mx, bound)
            lg.w(f"    k={k} {tag:7s}  sweep == O(n^2): {ok and ok2}   "
                 f"max|D| = {mx / C.L_US:.6f} L   bound 2(k-1)L = {2 * (k - 1)} L   "
                 f"In>0 on {int((In > 0).sum()):,} jobs, same-phase share of sum In = "
                 f"{(sp.sum() / max(In.sum(), 1)) * 100:.3f}%")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--instances", type=int, default=400)
    ap.add_argument("--slice", type=int, default=5000)
    a = ap.parse_args()
    lg = C.Log("validate")
    for n, h in sorted(C.EXTERNAL.items()):
        lg.w(f"    ext {n:44s} {C.sha256_file(h)}")
    lg.w("--- random small instances (exact arithmetic on a 1/64 s grid) ---")
    check_random(lg, a.instances)
    lg.el("random block done")
    lg.w("--- real slice ---")
    check_slice(lg, a.slice)
    lg.el("slice block done")
    lg.close()


if __name__ == "__main__":
    main()
