"""Iso-guarantee and iso-harm comparison, plus the reserved-server designs.

The headline table of run_trace.py compares tiered designs with SPJF+guard at the same
BUDGET, which is not a fair comparison: the tiered designs do not keep the promise that
budget buys (they waste work, see notes.md).  Here each design is placed on two honest
axes instead:

  guaranteed excess   the largest per-job excess over plain FCFS the design can PROVE
                      on this trace: B/k + (3-2/k)L with no tiering, and the
                      waste-corrected (B + Delta_max)/k + (3-2/k)L with tiering
                      (Proposition W of notes.md; Delta_max is measured by the kernel)
  measured excess     max_i (W[i] - W_FCFS[i]) actually observed on the trace

and the question is: at the same value of either axis, which design closes more of the
FCFS -> true-SJF gap?  A grid of SPJF+guard budgets draws the reference curve.

Also run here: the reserved-server designs of the task ((a) partition, (b) a cap of m
tier-2 jobs in service).  Both are NON work conserving, so no guarantee survives at all;
the numbers show what they cost as well.

Every tiered guarded run asserts Proposition W on EVERY job.

usage:  run_iso.py <level 0|1|2> [tau list]     ->  out_iso_L<level>.txt, iso_L<level>.csv
"""
import sys
sys.dont_write_bytecode = True
import os
import csv
import time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tierkern as T

SCRATCH = r"<cache-dir>"
IN = SCRATCH + "/gv_inputs"
L = 60.0
GGRID = (200.0, 300.0, 400.0, 500.0, 700.0, 1000.0, 1500.0, 2000.0, 3000.0)
T0 = time.time()


def main():
    lev = int(sys.argv[1])
    taus = [float(x) for x in (sys.argv[2] if len(sys.argv) > 2 else "1,2").split(",")]
    tag = sys.argv[3] if len(sys.argv) > 3 else ""
    fh = open(os.path.join(HERE, f"out_iso_L{lev}{tag}.txt"), "w")

    def log(*a):
        print(f"[{time.time()-T0:6.0f}s]", *a, flush=True)
        print(f"[{time.time()-T0:6.0f}s]", *a, file=fh, flush=True)

    Z = np.load(os.path.join(IN, "rep0.npz"))
    a = np.ascontiguousarray(Z["a"], np.float64)
    svc = np.ascontiguousarray(Z["svc"], np.float64)
    pred = np.ascontiguousarray(Z["M4"].astype(np.float64))
    dm = Z["dl"]
    k = int(Z["K"][lev])
    n = len(a)
    base = (3.0 - 2.0 / k) * L
    log(f"rep0 level{lev}: k={k} rho_busy={float(Z['W'])/(3600.0*k):.4f} n={n:,} "
        f"(3-2/k)L = {base:.1f}s")

    wf = T.run(a, svc, k, "rank").w
    ws = T.run(a, svc, k, "pred", pred=svc).w
    fq, sq = float(np.quantile(wf[dm], .99)), float(np.quantile(ws[dm], .99))
    fm, sm = float(wf.mean()), float(ws.mean())
    del ws
    log(f"  FCFS p99_dl {fq:.3f}s mean {fm:.4f}s | true-SJF p99_dl {sq:.3f}s "
        f"mean {sm:.4f}s")

    rows = []

    def add(name, kw, guar, tau=0.0):
        r = T.run(a, svc, k, name=name, **kw)
        ex = r.w - wf
        me = float(ex.max())
        gh = guar if r.waste == 0 else (kw["B"] + r.dmax) / k + base
        viol = -1
        if r.waste > 0 and kw.get("B") is not None:
            bound = wf + (kw["B"] + r.dmax) / k + base
            viol = int((r.w > bound + 1e-6).sum())     # Proposition W, every job
        row = dict(level=lev, k=k, policy=name, tau=tau, B=kw.get("B", -1) or -1,
                   guar_claimed=guar, guar_honest=gh, max_excess=me,
                   max_excess_light=float(ex[svc <= tau].max()) if tau else float("nan"),
                   max_excess_heavy=float(ex[svc > tau].max()) if tau else float("nan"),
                   w_p99_dl=float(np.quantile(r.w[dm], .99)), w_mean=float(r.w.mean()),
                   gap_p99dl=(fq - float(np.quantile(r.w[dm], .99))) / (fq - sq),
                   gap_mean=(fm - float(r.w.mean())) / (fm - sm),
                   waste_frac=r.waste / float(svc.sum()), delta_max=r.dmax,
                   prop_W_violations=viol,
                   forced_frac=r.n_forced / max(r.n_disp, 1))
        if kw.get("m2") is None:
            assert viol <= 0, (name, "Proposition W violated on the real trace")
        elif viol > 0:
            log(f"  !! {name}: Proposition W violated on {viol:,} jobs "
                f"({viol/n*100:.4f}%) -- expected: a server cap is not work conserving, "
                f"and Proposition 10 of ../guard_theory/theory.md shows that voids every "
                f"guarantee.")
        rows.append(row)
        log(f"  {name:26s} guar {gh:9.1f} (claimed {guar:8.1f})  maxExc {me:9.1f}  "
            f"p99_dl {row['w_p99_dl']:9.3f} gap {row['gap_p99dl']:6.3f} "
            f"gapM {row['gap_mean']:6.3f}  waste {row['waste_frac']*100:5.2f}% "
            f"D {r.dmax:8.1f}  PropW_viol {viol}")
        del r, ex
        return row

    log("\n-- reference curve: SPJF + guard, no tiering (the paper's method) --")
    add("FCFS", dict(mode="rank"), 0.0)
    add("SJF-ref", dict(mode="pred", pred=svc), float("inf"))
    add("SPJF", dict(mode="pred", pred=pred), float("inf"))
    for G in GGRID:
        B = T.B_for_G(k, G)
        if B < 0:
            continue
        add(f"SPJF+guard-G{G:g}", dict(mode="pred", pred=pred, B=B), G)

    log("\n-- kill-and-restart tiering, guard budget B = k(300 - (3-2/k)L) --")
    B3 = T.B_for_G(k, 300.0)
    for tau in taus:
        t = f"{tau:g}"
        add(f"TIER-blind-t{t}+guard", dict(mode="t1rank", tau=tau, B=B3), 300.0, tau)
        add(f"TIER-pred-t{t}+guard", dict(mode="t1pred", pred=pred, tau=tau, B=B3),
            300.0, tau)
        add(f"TIER-skip-t{t}+guard", dict(mode="t1pred", pred=pred, tau=tau, B=B3,
                                          skip_thr=tau), 300.0, tau)

    log("\n-- reserved-server designs (NOT work conserving: no guarantee survives) --")
    for tau in taus[:1]:
        for m2 in range(1, k):
            add(f"TIER-cap{m2}-t{tau:g}+guard",
                dict(mode="t1pred", pred=pred, tau=tau, B=B3, m2=m2), float("nan"), tau)

    path = os.path.join(HERE, f"iso_L{lev}{tag}.csv")
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    # ---- the comparison: SPJF+guard interpolated at each tiered design's own numbers
    ref = [r for r in rows if r["policy"].startswith("SPJF+guard")]
    gx = np.array([r["guar_honest"] for r in ref])
    mx = np.array([r["max_excess"] for r in ref])
    gy = np.array([r["gap_p99dl"] for r in ref])
    my = np.array([r["gap_mean"] for r in ref])
    log("\n== iso-comparison: what SPJF+guard alone achieves at the same worst case ==")
    log(f"{'tiered design':<26} {'guar':>8} {'gap':>6} {'SPJFg@guar':>11} {'dgap':>7} "
        f"| {'maxExc':>8} {'gap':>6} {'SPJFg@maxExc':>13} {'dgap':>7}")
    for r in rows:
        if not r["policy"].startswith("TIER"):
            continue
        a1 = float(np.interp(r["guar_honest"], gx, gy))
        a2 = float(np.interp(r["max_excess"], mx, gy))
        log(f"{r['policy']:<26} {r['guar_honest']:>8.1f} {r['gap_p99dl']:>6.3f} "
            f"{a1:>11.3f} {r['gap_p99dl']-a1:>+7.3f} | {r['max_excess']:>8.1f} "
            f"{r['gap_p99dl']:>6.3f} {a2:>13.3f} {r['gap_p99dl']-a2:>+7.3f}")
    log(f"(mean-wait axis: SPJF+guard gapMean at guar = "
        f"{[round(float(np.interp(r['guar_honest'], gx, my)), 3) for r in rows if r['policy'].startswith('TIER')]})")
    log(f"wrote {path}")
    fh.close()


if __name__ == "__main__":
    main()
