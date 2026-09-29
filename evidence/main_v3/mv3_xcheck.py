"""Stage 5: cross-check the simulation kernel against independent simulators.

(a) small  >= N_SMALL random integer instances (arrivals, services, predictions, k, B0,
    eta, Bmax, finite-skip Ncap all drawn), every one run through
      - guardkern.simulate            the kernel this experiment uses (numba)
      - refsim.simulate               the referee's pure-python reference, written from
                                      the written definitions only (evidence/
                                      guard_variants_referee/, imported read-only)
      - service_precheck_v2.simulate  the project's own simulator, for the settings it
                                      covers (FCFS, pure priority, constant budget)
    compared job by job, and the per-job theorem asserted on the REFEREE's output too, so
    the bound is not checked only by the implementation that is supposed to satisfy it.

(b) real   one real load level of the primary trace, job by job, for FCFS, SPJF-tweedie
    and the fixed-budget guard at G = 600 s: the kernel's wait vector must equal the
    project simulator's exactly (17.6 M jobs, no tolerance).

usage: mv3_xcheck.py [--small 2000] [--trace primary --rep 0 --level 2] [--skip-real]
"""
from __future__ import annotations

import argparse
import os
import random
import sys
from fractions import Fraction

import numpy as np

import mv3_common as C
from mv3_common import SP, GK

sys.path.insert(0, os.path.join(C.ROOT, "evidence", "guard_variants_referee"))
import refsim                                                          # noqa: E402

SEED = 20260919


def ref_wait(a, s, pred, k, **kw):
    start, _ = refsim.simulate(a, s, pred, k, **kw)
    return np.array([st - aa for st, aa in zip(start, a)], float)


def small(lg, n_inst):
    rng = random.Random(SEED)
    bad = 0
    kinds = {"fcfs": 0, "pri": 0, "cap": 0, "fix": 0, "skip": 0}
    worst_used = 0.0
    for _ in range(n_inst):
        n = rng.randint(2, 12)
        k = rng.randint(1, 4)
        Lm = rng.randint(1, 5)
        mode = rng.randint(0, 2)
        if mode == 0:
            a = [0] * n
        elif mode == 1:
            a = sorted(rng.randint(0, 6) for _ in range(n))
        else:
            a = sorted(rng.choice([0, 0, 1, 3, 3, 7]) for _ in range(n))
        s = [rng.choice([Lm, rng.randint(1, Lm)]) for _ in range(n)]
        pred = [float(rng.randint(0, n)) for _ in range(n)]
        af, sf, pf = np.array(a, float), np.array(s, float), np.array(pred, float)
        kind = rng.choice(["fcfs", "pri", "cap", "fix", "skip"])
        kinds[kind] += 1
        wf = GK.run(af, sf, k, "fcfs").w
        if kind == "fcfs":
            r = GK.run(af, sf, k, "fcfs")
            w2 = ref_wait(a, s, pred, k, policy="fcfs")
            w3 = SP.simulate(af, sf, None, k, "fcfs")
        elif kind == "pri":
            r = GK.run(af, sf, k, "pri", pred=pf)
            w2 = np.full(n, np.nan)
            w3 = SP.simulate(af, sf, pf, k, "pri")
        elif kind == "fix":
            B = rng.randint(0, n * Lm + 2)
            r = GK.run(af, sf, k, "guard", pred=pf, B=float(B), Mslots=64)
            w2 = ref_wait(a, s, pred, k, policy="guard", B0=B, Bmax=B, use_work=True)
            w3 = SP.simulate(af, sf, pf, k, "guard", B=float(B))
        elif kind == "cap":
            B0 = rng.randint(0, n * Lm + 2)
            eta = rng.choice([0.0, 0.25, 0.5, 0.75, 0.9])
            # Bmax >= 1: the two simulators read Bmax = 0 differently -- guardkern takes it
            # as "no cap" (its documented sentinel), refsim as a cap of zero, which fires
            # on every job.  The experiment's Bmax = k(G - (3-2/k)L) is never below 240 s,
            # so the degenerate value is outside the parameter range anyway.
            Bm = max(1, B0 + rng.randint(0, n * Lm + 2))
            r = GK.run(af, sf, k, "guard", pred=pf, B=float(B0), eps=eta * k,
                       Bmax=float(Bm), Mslots=64)
            w2 = ref_wait(a, s, pred, k, policy="guard", B0=B0, Bmax=Bm,
                          eps=Fraction(int(round(eta * 100)), 100) * k, use_work=True)
            w3 = np.full(n, np.nan)
        else:
            N = rng.randint(1, 6)
            r = GK.run(af, sf, k, "guard", pred=pf, B=-1.0, theta=float(Lm), Ncap=N,
                       Mslots=64)
            w2 = ref_wait(a, s, pred, k, policy="guard", B0=0, Bmax=0, Ncap=N,
                          theta=Lm, use_work=False)
            w3 = np.full(n, np.nan)
        for nm, w in (("refsim", w2), ("project", w3)):
            if np.isnan(w).any():
                continue
            if not np.array_equal(r.w, w):
                bad += 1
                lg.w(f"  MISMATCH vs {nm}: kind={kind} k={k} a={a} s={s} pred={pred}")
                lg.w(f"    kernel {r.w.tolist()}\n    {nm}  {w.tolist()}")
                break
        if kind in ("cap", "fix", "skip") and not np.isnan(w2).any():
            cb = np.zeros(1) if kind == "skip" else r.cbud / 1e6
            eps = (eta * k) if kind == "cap" else 0.0
            extra = (N * Lm) if kind == "skip" else 0.0
            bm = float(Bm) if kind == "cap" else (float(B) if kind == "fix" else 0.0)
            ub = GK.guaranteed(wf, k, cb, eps=eps, extra=extra, L=float(Lm), Bmax=bm)
            assert (w2 <= ub + 1e-9).all(), ("bound violated on the referee's output",
                                             kind, a, s, pred, k)
            worst_used = max(worst_used, float(np.max((w2 - wf) /
                                                      np.maximum(ub - wf, 1e-12))))
    lg.w(f"small instances: {n_inst} drawn {kinds}; job-by-job mismatches vs the referee "
         f"simulator and the project simulator: {bad}; the per-job bound holds on the "
         f"REFEREE's waits in every guarded instance, worst used/allowed {worst_used:.4f}")
    return bad


def real(lg, trace, rep, lev):
    Z = C.load_trace(trace, rep)
    K = list(Z["K"])
    k = int(K[lev]) if len(K) > 1 else int(K[0])
    a, svc, pred = Z["a"], Z["svc"], Z["tweedie"]
    bm = C.bmax_of(C.ADV_G, k)
    cases = [("FCFS", dict(policy="fcfs"), dict(pri=None, mode="fcfs", B=None)),
             ("SPJF-tweedie", dict(policy="pri", pred=pred), dict(pri=pred, mode="pri", B=None)),
             (f"FIX-G{C.ADV_G:g}", dict(policy="guard", pred=pred, B=bm, Bmax=bm,
                                        Mslots=C.MSLOTS),
              dict(pri=pred, mode="guard", B=bm))]
    bad = 0
    for nm, kw, sp in cases:
        w1 = GK.run(a, svc, k, **kw).w
        w2 = SP.simulate(a, svc, sp["pri"], k, sp["mode"], sp["B"])
        dev = float(np.abs(w1 - w2).max())
        nd = int((w1 != w2).sum())
        bad += nd
        lg.el(f"real {trace} rep{rep} level{lev} (k={k}, {len(a):,} jobs) {nm}: "
              f"kernel vs the project simulator, differing jobs {nd}, max |diff| {dev:g}")
        del w1, w2
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--small", type=int, default=2000)
    ap.add_argument("--trace", default="primary")
    ap.add_argument("--rep", type=int, default=0)
    ap.add_argument("--level", type=int, default=2)
    ap.add_argument("--skip-real", action="store_true")
    a = ap.parse_args()
    lg = C.Log("xcheck")
    bad = small(lg, a.small)
    if not a.skip_real:
        bad += real(lg, a.trace, a.rep, a.level)
    lg.w(f"TOTAL job-by-job disagreements: {bad}")
    assert bad == 0
    lg.close()


if __name__ == "__main__":
    main()
