"""Measurement 2: the smallest shared pool size k that meets a responsiveness target on
the same demand the dedicated containers of `containers.py` serve.

Target: p99 of the wait, over the jobs that arrive inside a deadline window (the paper's
own definition: 0 <= assessment end - arrival <= 24 h), <= 1 s, 5 s, 30 s.

Policies, all on the k-server non-preemptive queue with the project's kernel
(`evidence/guard_variants/guardkern.py`, imported read-only):
  FCFS         -- first come first served
  SPJF-M4      -- shortest predicted job first, M4 = the development forward predictor
                  (trained only on semesters before the target semester, frozen)
  SPJF+G300    -- the same order wrapped in the overtake-budget guard at B = 300 s = 5L,
                  the FIX-B300 row of evidence/guard_variants/pareto_tables.txt
  SJF-ref      -- true shortest job first, reported as the unreachable reference

Trace: the paper's primary overlay, rep 0 -- 44 copies of the 40 class-semesters of the
60-second-regime development semesters, each copy shifted by whole weeks, rebuilt through
`evidence/codebench_service_v2.p2_inputs` so that it is the same trace the paper's tables
use.  One replicate, as agreed.

usage:  pool_k.py            # writes pool_k.json next to this file; stdout -> out_pool_k.txt
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True
import json
import os
import time

import numpy as np

ROOT = r"<repo-root>"
V2 = os.path.join(ROOT, "evidence", "codebench_service_v2")
GV = os.path.join(ROOT, "evidence", "guard_variants")
SCRATCH = r"<cache-dir>"
CACHE = os.path.join(SCRATCH, "cb_v2_cache_r4")
INP = os.path.join(SCRATCH, "consol_inputs")
HERE = os.path.dirname(os.path.abspath(__file__))

CFG = "ires0"
COPIES = 44
REP = 0
GUARD_B = 300.0                       # 5 L, the FIX-B300 design
TARGETS = (1.0, 5.0, 30.0)
POLICIES = ("FCFS", "SPJF-M4", f"SPJF+G{GUARD_B:g}", "SJF-ref")
KMAX = 2048
T0 = time.time()


def log(*a):
    print(f"[{time.time() - T0:6.1f}s]", *a, flush=True)


def build():
    """Rebuild the primary overlay (rep 0) exactly as the project does, and cache it."""
    p = os.path.join(INP, f"rep{REP}.npz")
    if os.path.exists(p):
        z = np.load(p)
        log(f"reusing {p}")
        return {k: z[k] for k in z.files}
    os.makedirs(INP, exist_ok=True)
    sys.path.insert(0, V2)
    import service_precheck_v2 as b                      # noqa: E402  read-only reuse
    ev = b.load_events(CACHE)
    D = b.prep(ev)
    S = b.static_sub(ev, D)
    I = b.p2_inputs(D, S, CFG, CACHE)
    ent = b.ms_entries(I["pool"], COPIES, REP)
    a, svc, jidx, _ = b.overlay(ent, I["per_cs"], b.trace_key(CFG))
    _, W = b.busy_comp(a, svc, jidx, D, S)
    K = b.level_ks(W)
    a = b.rebase(a)
    assert np.all(np.diff(a) >= 0)
    d = dict(a=a, svc=svc, M4=I["P"]["M4"][jidx].astype(np.float64),
             dl=I["in_dl"][jidx], K=np.array(K), W=np.float64(W))
    np.savez(p, **d)
    log(f"built {p}: n={len(a):,} busy-hour work W={W:.3f}s paper k={K} "
        f"deadline-window jobs {int(d['dl'].sum()):,}")
    return d


def main():
    d = build()
    sys.path.insert(0, GV)
    import guardkern as G                                # noqa: E402  read-only reuse
    a, svc, M4, dl = d["a"], d["svc"], d["M4"], d["dl"].astype(bool)
    span_s = float(a[-1] - a[0])
    work_s = float(svc.sum())
    log(f"trace: n={len(a):,}  deadline-window jobs={int(dl.sum()):,}  "
        f"arrival span={span_s / 86400:.2f} d  C_cap work={work_s:,.1f} s  "
        f"paper k at rho 0.5/0.8/1.0 = {list(d['K'])}  busy-hour work={float(d['W']):.1f} s")

    cache = {}

    def p99(pol, k):
        key = (pol, int(k))
        if key in cache:
            return cache[key]
        t = time.time()
        if pol == "FCFS":
            r = G.run(a, svc, k, "fcfs")
        elif pol == "SPJF-M4":
            r = G.run(a, svc, k, "pri", pred=M4)
        elif pol == "SJF-ref":
            r = G.run(a, svc, k, "pri", pred=svc)
        else:
            r = G.run(a, svc, k, "guard", pred=M4, B=GUARD_B)
        w = r.w
        v = dict(p99_dl=float(np.quantile(w[dl], .99)), p95_dl=float(np.quantile(w[dl], .95)),
                 mean_dl=float(w[dl].mean()), p99=float(np.quantile(w, .99)),
                 mean=float(w.mean()), max=float(w.max()),
                 rho_busy=float(d["W"]) / (3600.0 * k), sec=round(time.time() - t, 1))
        cache[key] = v
        log(f"  {pol:10s} k={k:5d}  p99_dl={v['p99_dl']:9.3f}  p95_dl={v['p95_dl']:8.3f}  "
            f"mean_dl={v['mean_dl']:7.3f}  p99_all={v['p99']:8.3f}  ({v['sec']}s)")
        return v

    res = {"trace": {"n": int(len(a)), "dl_jobs": int(dl.sum()), "span_s": span_s,
                     "work_cap_s": work_s, "paper_k": [int(x) for x in d["K"]],
                     "busy_hour_work_s": float(d["W"]), "copies": COPIES, "rep": REP,
                     "guard_B": GUARD_B},
           "paper_levels": {}, "kmin": {}, "curve": {}}

    log("p99 of the deadline-window wait at the three pool sizes the paper uses")
    for pol in POLICIES:
        res["paper_levels"][pol] = {int(k): p99(pol, int(k)) for k in d["K"]}

    def smallest(pol, tgt):
        k = int(d["K"][-1])                              # the paper's rho = 1.0 level
        if p99(pol, k)["p99_dl"] <= tgt:
            lo, hi = 1, k
            if p99(pol, 1)["p99_dl"] <= tgt:
                return 1
        else:
            hi = k
            while p99(pol, hi)["p99_dl"] > tgt:
                lo, hi = hi, hi * 2
                if hi > KMAX:
                    return None
        while hi - lo > 1:
            m = (lo + hi) // 2
            if p99(pol, m)["p99_dl"] <= tgt:
                hi = m
            else:
                lo = m
        return hi

    log("smallest k reaching each deadline-window p99 target")
    for pol in POLICIES:
        res["kmin"][pol] = {}
        for tgt in sorted(TARGETS, reverse=True):
            k = smallest(pol, tgt)
            res["kmin"][pol][f"{tgt:g}"] = k
            if k is None:
                log(f"  {pol:10s} target p99_dl <= {tgt:5g} s : not reached by k <= {KMAX}")
            else:
                v = cache[(pol, k)]
                log(f"  {pol:10s} target p99_dl <= {tgt:5g} s : k = {k:4d}  "
                    f"(p99_dl={v['p99_dl']:.3f} s, busy-hour rho={v['rho_busy']:.4f}); "
                    f"k-1 = {k - 1} gives "
                    f"{cache[(pol, k - 1)]['p99_dl'] if (pol, k - 1) in cache else float('nan'):.3f} s")

    # monotonicity check on everything that was evaluated
    bad = []
    for pol in POLICIES:
        ks = sorted(k for (p, k) in cache if p == pol)
        for x, y in zip(ks, ks[1:]):
            if cache[(pol, y)]["p99_dl"] > cache[(pol, x)]["p99_dl"] + 1e-9:
                bad.append((pol, x, y))
    log(f"non-monotone (k, k') pairs among the evaluated points: {bad if bad else 'none'}")
    res["non_monotone"] = [[p, int(x), int(y)] for p, x, y in bad]
    res["curve"] = {pol: {str(k): cache[(p, k)] for (p, k) in sorted(cache) if p == pol}
                    for pol in POLICIES}
    with open(os.path.join(HERE, "pool_k.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1, default=float)
    log("wrote pool_k.json")


if __name__ == "__main__":
    main()
