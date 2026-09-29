"""Stage 5 (v3.2): cross-check both kernels against independent simulators.

Same design as v3.1's, extended to the two things v3.2 adds:
  * the HYBRID budget (a queue-length term gam * (jobs waiting when q arrived) inside the
    capped relative budget) is drawn in the small-instance sweep and compared against the
    referee's pure-python reference, which computes the same rule from its own definitions;
  * the selected fixed and capped budgets are both checked on a real busy slice.

usage: v32_xcheck.py [--small 3000] [--trace primary --rep 0 --level 2] [--skip-real]
"""
from __future__ import annotations

import argparse
import os
import random
import sys
from fractions import Fraction

import numpy as np
import pandas as pd

import v32_common as C
from v32_common import SP, GK, SK

sys.path.insert(0, C.REFDIR)
import refsim                                                          # noqa: E402

SEED = 20260921


def ref_wait(a, s, pred, k, **kw):
    start, _ = refsim.simulate(a, s, pred, k, **kw)
    return np.array([st - aa for st, aa in zip(start, a)], float)


def small(lg, n_inst):
    rng = random.Random(SEED)
    bad = 0
    kinds = {"fcfs": 0, "pri": 0, "cap": 0, "fix": 0, "hyb": 0, "skip": 0}
    worst_w, worst_s, anchors = 0.0, 0.0, 0
    for _ in range(n_inst):
        n = rng.randint(2, 12)
        k = rng.randint(1, 4)
        Lm = rng.randint(1, 5)
        mode = rng.randint(0, 2)
        a = ([0] * n if mode == 0 else
             sorted(rng.randint(0, 6) for _ in range(n)) if mode == 1 else
             sorted(rng.choice([0, 0, 1, 3, 3, 7]) for _ in range(n)))
        s = [rng.choice([Lm, rng.randint(1, Lm)]) for _ in range(n)]
        pred = [float(rng.randint(0, n)) for _ in range(n)]
        af, sf, pf = np.array(a, float), np.array(s, float), np.array(pred, float)
        kind = rng.choice(["fcfs", "pri", "cap", "fix", "hyb", "skip"])
        kinds[kind] += 1
        wf = GK.run(af, sf, k, "fcfs").w
        w1 = w2 = w3 = None
        if kind == "fcfs":
            w1 = wf
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
            assert (w2 <= ub + 1e-9).all(), ("bound violated on refsim", a, s, pred)
            worst_w = max(worst_w, float(np.max((w2 - wf) / np.maximum(ub - wf, 1e-12))))
        elif kind in ("cap", "hyb"):
            B0 = rng.randint(0, n * Lm + 2)
            eta = rng.choice([0.0, 0.25, 0.5, 0.75, 0.9, 0.95])
            Bm = max(1, B0 + rng.randint(0, n * Lm + 2))
            gam = float(rng.choice([1, 4, 16])) if kind == "hyb" else 0.0
            r = GK.run(af, sf, k, "guard", pred=pf, B=float(B0), eps=eta * k, gam=gam,
                       Bmax=float(Bm), Mslots=64)
            w1 = r.w
            if kind == "cap":       # refsim has no queue-length term; check the cap case
                w2 = ref_wait(a, s, pred, k, policy="guard", B0=B0, Bmax=Bm,
                              eps=Fraction(int(round(eta * 100)), 100) * k,
                              use_work=True)
            ub = GK.guaranteed(wf, k, r.cbud / 1e6, eps=eta * k, L=float(Lm),
                               Bmax=float(Bm))
            chk = w2 if w2 is not None else w1
            assert (chk <= ub + 1e-9).all(), ("bound violated", kind, a, s, pred)
            worst_w = max(worst_w, float(np.max((chk - wf) / np.maximum(ub - wf, 1e-12))))
        else:
            N = rng.randint(0, 6)
            w1 = SK.run(af, sf, pf, k, N).w
            w2 = np.array(SK.brute(a, s, pred, k, N), float)
            ub = SK.guaranteed(wf, k, N, float(Lm))
            assert (w2 <= ub + 1e-9).all(), ("skip bound violated", a, s, pred, k, N)
            worst_s = max(worst_s, float(np.max((w2 - wf) / np.maximum(ub - wf, 1e-12))))
            if not np.array_equal(SK.run(af, sf, pf, k, 0).w, wf):
                bad += 1
                lg.w(f"  ANCHOR FAIL N=0 != FCFS: {a} {s} {pred} k={k}")
            elif not np.array_equal(SK.run(af, sf, pf, k, n + 5).w,
                                    GK.run(af, sf, k, "pri", pred=pf).w):
                bad += 1
                lg.w(f"  ANCHOR FAIL N>=n != pure order: {a} {s} k={k}")
            else:
                anchors += 1
        for nm, w in (("independent reference", w2), ("project simulator", w3)):
            if w is None:
                continue
            if not np.array_equal(w1, w):
                bad += 1
                lg.w(f"  MISMATCH vs {nm}: {kind} k={k} a={a} s={s} pred={pred}")
                lg.w(f"    kernel {w1.tolist()}\n    other  {w.tolist()}")
                break
    lg.w(f"small instances: {n_inst} drawn {kinds}; mismatches and anchor failures: "
         f"{bad}; {anchors} finite-skip instances also reproduced FCFS at N = 0 and the "
         f"pure predictor order at N >= n; per-job bounds asserted on the independent "
         f"waits where one exists (and on the kernel's own for the hybrid, which the "
         f"reference does not implement): worst used/allowed {worst_w:.4f} (work budget) "
         f"and {worst_s:.4f} (finite skip)")
    return bad


def busy_slice(a, n_take):
    hr = np.floor(a / 3600.0).astype(np.int64)
    _, inv = np.unique(hr, return_inverse=True)
    st = int(np.searchsorted(inv, int(np.bincount(inv).argmax())))
    return slice(min(st, len(a) - n_take), min(st, len(a) - n_take) + n_take)


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
        lg.el(f"real {trace} rep{rep} L{lev} (k={k}, {len(a):,} jobs) {nm}: vs the "
              f"project simulator, differing jobs {nd}, max |diff| "
              f"{float(np.abs(w1 - w2).max()):g}")
        del w1, w2
    sl = busy_slice(a, 1000)
    aa = np.ascontiguousarray(a[sl]) - a[sl][0]
    ss, pp = np.ascontiguousarray(svc[sl]), np.ascontiguousarray(pred[sl])
    N = C.skip_ncap_dispatch(C.ADV_G, k)
    w1 = SK.run(aa, ss, pp, k, N).w
    w2 = np.array(SK.brute(aa.tolist(), ss.tolist(), pp.tolist(), k, N), float)
    nd = int((w1 != w2).sum())
    bad += nd
    lg.el(f"real busy slice (1,000 jobs) finite skip N={N}: vs the literal reference, "
          f"differing jobs {nd}")
    S = pd.read_csv(os.path.join(C.HERE, "selected_params.csv"))
    n2 = 400
    for fam in ("fixed", "capped"):
        r = S[(S.family == fam) & (S.G == C.ADV_G)].iloc[0]
        b0 = min(float(r.B0_base) * k / 4.0, bm)
        eta = float(r.eta)
        w1 = GK.run(aa[:n2], ss[:n2], k, "guard", pred=pp[:n2], B=b0, eps=eta * k,
                    Bmax=bm, Mslots=1 << 12).w
        w2 = ref_wait(aa[:n2].tolist(), ss[:n2].tolist(), pp[:n2].tolist(), k,
                      policy="guard", B0=b0, Bmax=bm,
                      eps=Fraction(int(round(eta * 100)), 100) * k, use_work=True)
        nd = int((np.abs(w1 - w2) > 1e-9).sum())
        bad += nd
        lg.el(f"real busy slice (400 jobs) selected {fam} budget (B0={b0:g} s, "
              f"eta={eta:g}, Bmax={bm:g} s): vs the referee's reference simulator, "
              f"differing jobs {nd}")
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
