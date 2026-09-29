"""Kill-and-restart tiering on the real development trace (rep0 overlay, 17.6 M jobs).

usage:  run_trace.py <level 0|1|2> [taus]          e.g.  run_trace.py 2 1,2,5,10
        level 0 -> k=8 (rho 0.53), 1 -> k=5 (0.85), 2 -> k=4 (1.06)

Reads only the development cache built by `../guard_variants/build_inputs.py`
(<cache-dir>/gv_inputs/rep0.npz: arrivals, capped service, the M4 prediction, the
deadline-window and heavy masks).  No sealed data is touched.

Policies (G = 300 s = 5L is the service level of the paper's guard row; the budget that
buys it for the NON-tiered guard is B = k(G - (3-2/k)L)):

    FCFS            plain first-come-first-served, the reference of every guarantee
    SJF-ref         true shortest job first, not deployable, the denominator of "gap"
    SPJF            sort by the M4 prediction, no guard
    SPJF+guard      the paper's method
    TFCFS-tau       tiering dispatched by rank: the cost of the wasted work alone
    TIER-blind      tier-1 first by rank, tier-2 by rank; NO prediction used
    TIER-pred       tier-1 first by prediction, tier-2 by rank
    TIER-skip       TIER-pred + jobs predicted >= tau skip tier 1 and go straight to 2
    (every tiered design is also run with the same guard budget B)

Outputs: results_L<level>.csv (one row per policy) and out_trace_L<level>.txt.
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
G_SERVICE = 300.0            # 5L, the row of ../guard_variants/pareto_tables.txt
T0 = time.time()


def log(f, *a):
    print(f"[{time.time()-T0:6.0f}s]", *a, flush=True)
    print(f"[{time.time()-T0:6.0f}s]", *a, file=f, flush=True)


def main():
    lev = int(sys.argv[1])
    taus = [float(x) for x in (sys.argv[2] if len(sys.argv) > 2 else "1,2,5,10").split(",")]
    fh = open(os.path.join(HERE, f"out_trace_L{lev}.txt"), "w")
    Z = np.load(os.path.join(IN, "rep0.npz"))
    a = np.ascontiguousarray(Z["a"], np.float64)
    svc = np.ascontiguousarray(Z["svc"], np.float64)
    pred = np.ascontiguousarray(Z["M4"].astype(np.float64))
    dm = Z["dl"]
    k = int(Z["K"][lev])
    W = float(Z["W"])
    n = len(a)
    tot_work = float(svc.sum())
    B = T.B_for_G(k, G_SERVICE)
    log(fh, f"rep0 level{lev}: k={k} busy-hour rho={W/(3600.0*k):.4f} n={n:,} "
            f"total work={tot_work:,.0f}s  G={G_SERVICE:g}s -> B={B:g}s")
    for th in (0.5, 1.0, 2.0, 5.0, 10.0):
        log(fh, f"  jobs with C > {th:4.1f}s: {int((svc>th).sum()):>9,} "
                f"({(svc>th).mean()*100:6.3f}%), carrying "
                f"{svc[svc>th].sum()/tot_work*100:5.2f}% of the work; "
                f"waste if all are killed at {th:4.1f}s: "
                f"{(svc>th).sum()*th/tot_work*100:5.2f}% of the work")

    wf = T.run(a, svc, k, "rank").w
    ws = T.run(a, svc, k, "pred", pred=svc).w
    fq, sq = float(np.quantile(wf[dm], .99)), float(np.quantile(ws[dm], .99))
    fm, sm = float(wf.mean()), float(ws.mean())
    del ws
    log(fh, f"  FCFS p99_dl {fq:.3f}s mean {fm:.4f}s | true-SJF p99_dl {sq:.3f}s "
            f"mean {sm:.4f}s")

    rows = []
    jobs = [("FCFS", dict(mode="rank"), None),
            ("SJF-ref", dict(mode="pred", pred=svc), None),
            ("SPJF", dict(mode="pred", pred=pred), None),
            (f"SPJF+guard", dict(mode="pred", pred=pred, B=B), None)]
    for tau in taus:
        t = f"{tau:g}"
        jobs += [
            (f"TFCFS-t{t}", dict(mode="rank", tau=tau), tau),
            (f"TIER-blind-t{t}", dict(mode="t1rank", tau=tau), tau),
            (f"TIER-blind-t{t}+guard", dict(mode="t1rank", tau=tau, B=B), tau),
            (f"TIER-pred-t{t}", dict(mode="t1pred", pred=pred, tau=tau), tau),
            (f"TIER-pred-t{t}+guard", dict(mode="t1pred", pred=pred, tau=tau, B=B), tau),
            (f"TIER-skip-t{t}+guard", dict(mode="t1pred", pred=pred, tau=tau, B=B,
                                           skip_thr=tau), tau),
        ]
    path = os.path.join(HERE, f"results_L{lev}.csv")
    fcsv = open(path, "w", newline="")
    wr = None
    for name, kw, tau in jobs:
        t0 = time.time()
        r = T.run(a, svc, k, name=name, **kw)
        ex = r.w - wf
        lt = svc <= (tau if tau else L)
        hv = ~lt
        row = dict(level=lev, k=k, policy=name, tau=(tau or 0.0), B=(kw.get("B") or -1),
                   n_jobs=n,
                   w_mean=float(r.w.mean()), w_p99_dl=float(np.quantile(r.w[dm], .99)),
                   w_p95_dl=float(np.quantile(r.w[dm], .95)),
                   w_max=float(r.w.max()),
                   gap_p99dl=(fq - float(np.quantile(r.w[dm], .99))) / (fq - sq),
                   gap_mean=(fm - float(r.w.mean())) / (fm - sm),
                   max_excess=float(ex.max()),
                   max_excess_light=float(ex[lt].max()) if lt.any() else float("nan"),
                   max_excess_heavy=float(ex[hv].max()) if hv.any() else float("nan"),
                   p99_excess=float(np.quantile(ex, .99)),
                   mean_excess=float(ex.mean()),
                   max_excess_wf0=float(ex[wf <= 1.0].max()),
                   waste_s=r.waste, waste_frac=r.waste / tot_work,
                   n_killed=r.n_killed, delta_max=r.dmax,
                   guar_thmA=T.guar_excess(k, B) if kw.get("B") else float("nan"),
                   guar_waste_corrected=((B + r.dmax) / k + (3 - 2 / k) * L
                                         if kw.get("B") else float("nan")),
                   forced_frac=r.n_forced / max(r.n_disp, 1),
                   qw_forced_frac=r.qw_forced / max(r.qw_total, 1),
                   secs=round(time.time() - t0, 1))
        rows.append(row)
        if wr is None:
            wr = csv.DictWriter(fcsv, fieldnames=list(row))
            wr.writeheader()
        wr.writerow(row)
        fcsv.flush()
        log(fh, f"  {name:24s} {row['secs']:6.1f}s  p99_dl {row['w_p99_dl']:9.3f} "
                f"gap {row['gap_p99dl']:6.3f} mean {row['w_mean']:8.4f} "
                f"gapM {row['gap_mean']:6.3f} | maxExc {row['max_excess']:9.1f} "
                f"(light {row['max_excess_light']:9.1f} heavy {row['max_excess_heavy']:9.1f}) "
                f"| waste {row['waste_frac']*100:5.2f}% D_max {row['delta_max']:9.1f} "
                f"| forced {row['forced_frac']*100:6.3f}%")
        del r, ex
    fcsv.close()
    log(fh, f"wrote {path}")
    fh.close()


if __name__ == "__main__":
    main()
