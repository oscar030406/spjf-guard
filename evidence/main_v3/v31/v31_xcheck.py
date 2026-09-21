"""Stage 5 (v3.1): cross-check both simulation kernels against independent simulators.

(a) small  random integer instances run through
      - guardkern.simulate            the work-budget kernel (FCFS, priority, capped
                                      relative, fixed, completion-charged finite skip)
      - v31_skipkern.simulate_skip    the dispatch-charged finite-skip kernel added here
      - refsim.simulate               the referee's pure-python reference (read-only)
      - v31_skipkern.brute            a literal reference for the dispatch charge that
                                      recomputes the whole fired set instead of using
                                      the head check the fast kernel relies on
      - service_precheck_v2.simulate  the project simulator, where it covers the policy
    compared job by job, with both per-job bounds asserted on the INDEPENDENT waits.
    Two anchors pin the new kernel from outside: N = 0 must reproduce FCFS exactly and
    N >= n must reproduce the pure predictor order exactly.

(b) real   one real load level of the primary trace, job by job: FCFS, SPJF-tweedie and
    the fixed-budget guard against the project simulator, and the dispatch-charged
    finite skip against an independent recomputation of its own definition on a slice.

usage: v31_xcheck.py [--small 3000] [--trace primary --rep 0 --level 2] [--skip-real]
"""
from __future__ import annotations

import argparse
import os
import random
import sys
from fractions import Fraction

import numpy as np
import pandas as pd

import v31_common as C
from v31_common import SP, GK, SK

sys.path.insert(0, C.REFDIR)
import refsim                                                          # noqa: E402

SEED = 20260920


def ref_wait(a, s, pred, k, **kw):
    start, _ = refsim.simulate(a, s, pred, k, **kw)
    return np.array([st - aa for st, aa in zip(start, a)], float)


def small(lg, n_inst):
    rng = random.Random(SEED)
    bad = 0
    kinds = {"fcfs": 0, "pri": 0, "cap": 0, "fix": 0, "skipc": 0, "skip": 0}
    worst_w, worst_s = 0.0, 0.0
    anchors = 0
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
        kind = rng.choice(["fcfs", "pri", "cap", "fix", "skipc", "skip"])
        kinds[kind] += 1
        wf = GK.run(af, sf, k, "fcfs").w
        w1 = w2 = w3 = None
        if kind == "fcfs":
            w1 = GK.run(af, sf, k, "fcfs").w
            w2 = ref_wait(a, s, pred, k, policy="fcfs")
            w3 = SP.simulate(af, sf, None, k, "fcfs")
        elif kind == "pri":
            w1 = GK.run(af, sf, k, "pri", pred=pf).w
            w3 = SP.simulate(af, sf, pf, k, "pri")
        elif kind == "fix":
            B = rng.randint(0, n * Lm + 2)
            r = GK.run(af, sf, k, "guard", pred=pf, B=float(B), Mslots=64)
            w1 = r.w
            w2 = ref_wait(a, s, pred, k, policy="guard", B0=B, Bmax=B, use_work=True)
            w3 = SP.simulate(af, sf, pf, k, "guard", B=float(B))
            ub = GK.guaranteed(wf, k, r.cbud / 1e6, L=float(Lm), Bmax=float(B))
            assert (w2 <= ub + 1e-9).all(), ("bound violated on refsim", kind, a, s, pred)
            worst_w = max(worst_w, float(np.max((w2 - wf) / np.maximum(ub - wf, 1e-12))))
        elif kind == "cap":
            B0 = rng.randint(0, n * Lm + 2)
            eta = rng.choice([0.0, 0.25, 0.5, 0.75, 0.9])
            Bm = max(1, B0 + rng.randint(0, n * Lm + 2))   # Bmax = 0 is guardkern's
            r = GK.run(af, sf, k, "guard", pred=pf, B=float(B0), eps=eta * k,   # "no cap"
                       Bmax=float(Bm), Mslots=64)          # sentinel; refsim reads it as
            w1 = r.w                                       # a cap of zero (v3 finding)
            w2 = ref_wait(a, s, pred, k, policy="guard", B0=B0, Bmax=Bm,
                          eps=Fraction(int(round(eta * 100)), 100) * k, use_work=True)
            ub = GK.guaranteed(wf, k, r.cbud / 1e6, eps=eta * k, L=float(Lm),
                               Bmax=float(Bm))
            assert (w2 <= ub + 1e-9).all(), ("bound violated on refsim", kind, a, s, pred)
            worst_w = max(worst_w, float(np.max((w2 - wf) / np.maximum(ub - wf, 1e-12))))
        elif kind == "skipc":
            N = rng.randint(1, 6)
            r = GK.run(af, sf, k, "guard", pred=pf, B=-1.0, theta=float(Lm), Ncap=N,
                       Mslots=64)
            w1 = r.w
            w2 = ref_wait(a, s, pred, k, policy="guard", B0=0, Bmax=0, Ncap=N,
                          theta=Lm, use_work=False)
            ub = GK.guaranteed(wf, k, np.zeros(1), extra=N * Lm, L=float(Lm))
            assert (w2 <= ub + 1e-9).all(), ("bound violated on refsim", kind, a, s, pred)
        else:                                              # dispatch-charged finite skip
            N = rng.randint(0, 6)
            w1 = SK.run(af, sf, pf, k, N).w
            w2 = np.array(SK.brute(a, s, pred, k, N), float)
            ub = SK.guaranteed(wf, k, N, float(Lm))
            assert (w2 <= ub + 1e-9).all(), ("skip bound violated on the brute force",
                                             a, s, pred, k, N)
            worst_s = max(worst_s, float(np.max((w2 - wf) / np.maximum(ub - wf, 1e-12))))
            if not np.array_equal(SK.run(af, sf, pf, k, 0).w, wf):
                bad += 1
                lg.w(f"  ANCHOR FAIL: N=0 is not FCFS  a={a} s={s} pred={pred} k={k}")
            elif not np.array_equal(SK.run(af, sf, pf, k, n + 5).w,
                                    GK.run(af, sf, k, "pri", pred=pf).w):
                bad += 1
                lg.w(f"  ANCHOR FAIL: N>=n is not the pure order  a={a} s={s} k={k}")
            else:
                anchors += 1
        for nm, w in (("independent reference", w2), ("project simulator", w3)):
            if w is None:
                continue
            if not np.array_equal(w1, w):
                bad += 1
                lg.w(f"  MISMATCH vs {nm}: kind={kind} k={k} a={a} s={s} pred={pred}")
                lg.w(f"    kernel {w1.tolist()}\n    other  {w.tolist()}")
                break
    lg.w(f"small instances: {n_inst} drawn {kinds}; job-by-job mismatches and anchor "
         f"failures: {bad}; {anchors} finite-skip instances also reproduced FCFS at "
         f"N = 0 and the pure predictor order at N >= n; both per-job bounds asserted on "
         f"the INDEPENDENT waits, worst used/allowed {worst_w:.4f} (work budget) and "
         f"{worst_s:.4f} (finite skip)")
    return bad


def busy_slice(a, n_take):
    """A contiguous run of n_take jobs starting at the busiest arrival hour: a real
    instance (arrivals already sorted) with a real queue in it."""
    hr = np.floor(a / 3600.0).astype(np.int64)
    uh, inv = np.unique(hr, return_inverse=True)
    st = int(np.searchsorted(inv, int(np.bincount(inv).argmax())))
    st = min(st, len(a) - n_take)
    sl = slice(st, st + n_take)
    return sl, float(a[st])


def real(lg, trace, rep, lev):
    Z = C.load_trace(trace, rep)
    K = list(Z["K"])
    k = int(K[lev]) if len(K) > 1 else int(K[0])
    a, svc, pred = Z["a"], Z["svc"], Z["tweedie"]
    bm = C.bmax_of(C.ADV_G, k)
    bad = 0
    for nm, kw, sp in (
            ("FCFS", dict(policy="fcfs"), dict(pri=None, mode="fcfs", B=None)),
            ("SPJF-tweedie", dict(policy="pri", pred=pred),
             dict(pri=pred, mode="pri", B=None)),
            (f"FIX-G{C.ADV_G:g}", dict(policy="guard", pred=pred, B=bm, Bmax=bm,
                                       Mslots=C.MSLOTS),
             dict(pri=pred, mode="guard", B=bm))):
        w1 = GK.run(a, svc, k, **kw).w
        w2 = SP.simulate(a, svc, sp["pri"], k, sp["mode"], sp["B"])
        nd = int((w1 != w2).sum())
        bad += nd
        lg.el(f"real {trace} rep{rep} level{lev} (k={k}, {len(a):,} jobs) {nm}: vs the "
              f"project simulator, differing jobs {nd}, max |diff| "
              f"{float(np.abs(w1 - w2).max()):g}")
        del w1, w2
    # real-data checks of the two policies the project simulator does NOT cover, on a
    # contiguous busy slice, against the literal pure-python references
    sl, t0 = busy_slice(a, 1000)
    aa = np.ascontiguousarray(a[sl]) - a[sl][0]
    ss, pp = np.ascontiguousarray(svc[sl]), np.ascontiguousarray(pred[sl])
    N = C.skip_ncap_dispatch(C.ADV_G, k)
    w1 = SK.run(aa, ss, pp, k, N).w
    w2 = np.array(SK.brute(aa.tolist(), ss.tolist(), pp.tolist(), k, N), float)
    nd = int((w1 != w2).sum())
    bad += nd
    lg.el(f"real busy slice, 1,000 jobs from the busiest arrival hour, finite skip "
          f"(dispatch charge, N={N}, k={k}): kernel vs the literal reference, differing "
          f"jobs {nd}, max |diff| {float(np.abs(w1 - w2).max()):g}")
    n2 = 400
    aa2, ss2, pp2 = aa[:n2], ss[:n2], pp[:n2]
    sp = pd.read_csv(os.path.join(C.HERE, "selected_params.csv"))
    srow = sp[(sp.family == "cap") & (sp.G == C.ADV_G)].iloc[0]
    b0b, eta = float(srow.B0_base), float(srow.eta)
    b0 = min(b0b * k / 4.0, bm)
    w1 = GK.run(aa2, ss2, k, "guard", pred=pp2, B=b0, eps=eta * k, Bmax=bm,
                Mslots=1 << 12).w
    w2 = ref_wait(aa2.tolist(), ss2.tolist(), pp2.tolist(), k, policy="guard", B0=b0,
                  Bmax=bm, eps=Fraction(int(round(eta * 100)), 100) * k, use_work=True)
    nd = int((np.abs(w1 - w2) > 1e-9).sum())
    bad += nd
    lg.el(f"real busy slice, 400 jobs, selected capped relative guard (B0={b0:g} s, "
          f"eta={eta:g}, Bmax={bm:g} s): kernel vs the referee's reference simulator, "
          f"differing jobs {nd}, max |diff| {float(np.abs(w1 - w2).max()):g}")
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--small", type=int, default=3000)
    ap.add_argument("--trace", default="primary")
    ap.add_argument("--rep", type=int, default=0)
    ap.add_argument("--level", type=int, default=2)
    ap.add_argument("--skip-real", action="store_true")
    a = ap.parse_args()
    lg = C.Log("xcheck")
    bad = small(lg, a.small)
    if not a.skip_real:
        bad += real(lg, a.trace, a.rep, a.level)
    lg.w(f"TOTAL disagreements: {bad}")
    assert bad == 0
    lg.close()


if __name__ == "__main__":
    main()
