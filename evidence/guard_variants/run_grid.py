"""Run the guard designs on the real primary trace and check their per-job bound.

usage:  run_grid.py <rep0|rep1|k1rep0> <level 0|1|2> <predictor> <group>[,<group>...]
        predictor: M4 | reversed | random | top1short | M1
        group:     base | fixed | rel | qlen | thresh | blend | relblend | all

Every guard run asserts, for EVERY job,
      (k - eps) * W_guard[i] <= k * W_fcfs[i] + C_i + Ncap*theta + (3k-2)*L        (Thm A/B)
with C_i the job's own constant budget (B0 + gam * jobs waiting at its arrival), and
records how much of the allowance was actually used.  One row per policy is appended to
results/grid_<rep>_L<level>_<predictor>.csv.

Parameters are written here, not passed on the command line.
"""
import sys
sys.dont_write_bytecode = True
import os
import time
import csv
import numpy as np
import guardkern as G

SCRATCH = r"<cache-dir>"
IN = SCRATCH + "/gv_inputs"
HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
L = 60.0
SEED = 3                      # the project's seed, for the 'random' adversarial predictor
T0 = time.time()

FIXED_B = (30.0, 120.0, 300.0, 600.0, 1200.0, 1800.0, 3600.0, 7200.0)
REL_B0 = (30.0, 120.0, 600.0, 1800.0)
REL_ETA = (0.25, 0.5, 0.75, 0.9)           # eps = eta * k, so the factor is 1/(1-eta)
QLEN_B0 = (30.0, 120.0)
QLEN_GAM = (1.0, 4.0, 16.0)           # work-seconds of budget per job waiting at arrival
TH_B = (120.0, 600.0)
TH_TH = (1.0, 5.0)                    # a completed overtaker under theta charges the count
TH_N = (10, 50)
BLEND_AL = (1e-5, 1e-4, 1e-3)           # predicted cost minus alpha * age
RELBLEND = ((120.0, 0.5, 1e-4), (600.0, 0.5, 1e-4), (120.0, 0.5, 1e-3))
SKIP_N = (1, 2, 5, 10, 20, 50)        # finite-skip baseline: at most N completed overtakes
CAP = ((30.0, 0.5, 600.0), (30.0, 0.5, 1200.0), (120.0, 0.5, 600.0),
       (120.0, 0.5, 1200.0), (120.0, 0.5, 3600.0), (30.0, 0.75, 1200.0),
       (30.0, 0.75, 3600.0), (120.0, 0.75, 1200.0), (120.0, 0.75, 3600.0),
       (30.0, 0.9, 1200.0), (30.0, 0.9, 3600.0), (600.0, 0.5, 3600.0))


def log(*a):
    print(f"[{time.time()-T0:6.0f}s]", *a, flush=True)


def stats(w, dm, xm, hv, wf, q0, q10):
    q = np.quantile
    ex = w - wf
    d = dict(w_mean=w.mean(), w_p95=q(w, .95), w_p99=q(w, .99), w_max=w.max(),
             w_mean_dl=w[dm].mean(), w_p95_dl=q(w[dm], .95), w_p99_dl=q(w[dm], .99),
             w_mean_exam=w[xm].mean(), w_p99_exam=q(w[xm], .99),
             mean_heavy=w[hv].mean(), p95_heavy=q(w[hv], .95), p99_heavy=q(w[hv], .99),
             max_heavy=w[hv].max(), max_excess=ex.max(), max_excess_dl=ex[dm].max(),
             p99_excess=q(ex, .99), mean_excess=ex.mean(),
             max_excess_wf0=ex[q0].max(), p9999_excess_wf0=q(ex[q0], .9999),
             max_excess_wflt10=ex[q10].max())
    return {k_: float(v) for k_, v in d.items()}


def designs(group, k, pred, a):
    """(name, kwargs, eps, extra) for one group; kwargs go straight to guardkern.run."""
    out = []
    if group == "sel":
        for nm in ("FIX-B600", "FIX-B1200", "FIX-B3600", "REL-B30-e0.75",
                   "REL-B120-e0.5", "CAP-B30-e0.5-M600", "CAP-B30-e0.9-M1200",
                   "CAP-B120-e0.75-M1200", "CAP-B30-e0.9-M3600", "SKIP-N10",
                   "SKIP-N20"):
            for g in ("fixed", "rel", "cap", "skip"):
                out += [d for d in designs(g, k, pred, a) if d[0] == nm]
    if group in ("skip", "all"):
        for N in SKIP_N:
            out.append((f"SKIP-N{N}",
                        dict(policy="guard", pred=pred, B=-1.0, theta=L, Ncap=N),
                        0.0, N * L))
    if group in ("cap", "all"):
        for B0, et, bm in CAP:
            out.append((f"CAP-B{B0:g}-e{et:g}-M{bm:g}",
                        dict(policy="guard", pred=pred, B=B0, eps=et * k, Bmax=bm),
                        et * k, 0.0))
    if group in ("base", "all"):
        out += [("FCFS", dict(policy="fcfs"), 0.0, 0.0),
                ("SJF-ref", dict(policy="pri", pred=None), 0.0, 0.0),
                ("SPJF", dict(policy="pri", pred=pred), 0.0, 0.0)]
    if group in ("fixed", "all"):
        for B in FIXED_B:
            out.append((f"FIX-B{B:g}", dict(policy="guard", pred=pred, B=B), 0.0, 0.0))
    if group in ("rel", "all"):
        for B0 in REL_B0:
            for et in REL_ETA:
                out.append((f"REL-B{B0:g}-e{et:g}",
                            dict(policy="guard", pred=pred, B=B0, eps=et * k), et * k, 0.0))
    if group in ("qlen", "all"):
        for B0 in QLEN_B0:
            for gm in QLEN_GAM:
                out.append((f"QL-B{B0:g}-g{gm:g}",
                            dict(policy="guard", pred=pred, B=B0, gam=gm), 0.0, 0.0))
    if group in ("thresh", "all"):
        for B in TH_B:
            for th in TH_TH:
                for N in TH_N:
                    out.append((f"TH-B{B:g}-t{th:g}-N{N}",
                                dict(policy="guard", pred=pred, B=B, theta=th, Ncap=N),
                                0.0, N * th))
    if group in ("blend", "all"):
        for al in BLEND_AL:
            out.append((f"BLEND-a{al:g}", dict(policy="pri", pred=pred + al * a), 0.0, 0.0))
    if group in ("relblend", "all"):
        for B0, et, al in RELBLEND:
            out.append((f"RELBL-B{B0:g}-e{et:g}-a{al:g}",
                        dict(policy="guard", pred=pred + al * a, B=B0, eps=et * k),
                        et * k, 0.0))
    return out


def main():
    rep, lev, pname, groups = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]
    os.makedirs(RES, exist_ok=True)
    G.run(np.zeros(2), np.ones(2), 1, "guard", pred=np.zeros(2), B=1.0, eps=0.5, Mslots=4)
    Z = np.load(os.path.join(IN, rep + ".npz"))
    a, svc, dm, xm, hv = Z["a"], Z["svc"], Z["dl"], Z["exam"], Z["hvt"]
    k = int(Z["K"][lev])
    rho = float(Z["W"]) / (3600.0 * k)
    n = len(a)
    if pname == "reversed":
        pred = -svc
    elif pname == "random":
        pred = np.random.default_rng(SEED + 0).permutation(svc)
    elif pname == "top1short":
        pred = Z["M4"].astype(np.float64).copy()
        pred[np.argsort(-svc, kind="stable")[:max(1, n // 100)]] = pred.min() - 1.0
    else:
        pred = Z[pname].astype(np.float64)
    pred = np.ascontiguousarray(pred, np.float64)
    log(f"{rep} level{lev}: k={k} rho_busy={rho:.4f} n={n:,} predictor={pname} "
        f"groups={groups}")

    wf = G.run(a, svc, k, "fcfs").w
    ws = G.run(a, svc, k, "pri", pred=svc).w
    fq = float(np.quantile(wf[dm], .99))
    sq = float(np.quantile(ws[dm], .99))
    fm, sm = float(wf.mean()), float(ws.mean())
    del ws
    log(f"  FCFS p99_dl {fq:.4f}s mean {fm:.4f}s | SJF-ref p99_dl {sq:.4f}s mean "
        f"{sm:.4f}s | gap {fq-sq:.4f}s / {fm-sm:.4f}s")

    q0 = wf <= 1.0
    q10 = wf <= 10.0
    log(f"  jobs with FCFS wait <= 1 s: {int(q0.sum()):,} ({q0.mean()*100:.1f}%); <= 10 s: "
        f"{int(q10.sum()):,} ({q10.mean()*100:.1f}%)")
    path = os.path.join(RES, f"grid_{rep}_L{lev}_{pname}.csv")
    new = not os.path.exists(path)
    done = set()
    if not new:
        with open(path, newline="") as fh:
            done = {r["policy"] for r in csv.DictReader(fh)}
    f = open(path, "a", newline="")
    wr = None
    for grp in groups.split(","):
        for name, kw, eps, extra in designs(grp, k, pred, a):
            if name in done:
                continue
            t = time.time()
            if name == "SJF-ref":
                kw = dict(policy="pri", pred=svc)
            r = G.run(a, svc, k, **kw)
            assert r.err == 0, (name, "segment-tree window too small")
            cb = np.zeros(1) if kw.get("B", 0.0) < 0 else r.cbud / 1e6
            bm = kw.get("Bmax", 0.0)
            if kw["policy"] == "guard":
                ub = G.guaranteed(wf, k, cb, eps=eps, extra=extra, L=L, Bmax=bm)
                viol = int((r.w > ub + 1e-6).sum())
                assert viol == 0, (name, float((r.w - ub).max()))
                used = float(np.max((r.w - wf) / np.maximum(ub - wf, 1e-12)))
                gmax = float((ub - wf).max())
                cm = np.float64(cb.max())
                gua0 = float(G.guaranteed(np.float64(0.0), k, cm, eps=eps, extra=extra,
                                          L=L, Bmax=bm))
                guaF = float(G.guaranteed(np.float64(fq), k, cm, eps=eps, extra=extra,
                                          L=L, Bmax=bm)) - fq
            else:
                viol, used, gua0, guaF, gmax = (-1, float("nan"), float("inf"),
                                                float("inf"), float("inf"))
            st = stats(r.w, dm, xm, hv, wf, q0, q10)
            row = dict(rep=rep, level=lev, k=k, rho_busy=rho, predictor=pname, policy=name,
                       n_jobs=n, **st,
                       gap_p99dl=(fq - st["w_p99_dl"]) / (fq - sq),
                       gap_mean=(fm - st["w_mean"]) / (fm - sm),
                       fcfs_p99dl=fq, sjf_p99dl=sq, fcfs_mean=fm, sjf_mean=sm,
                       guar_excess_at0=gua0, guar_excess_at_fcfs_p99dl=guaF,
                       guar_excess_max=gmax,
                       bound_viol=viol, used_over_allowed=used,
                       forced_frac=r.n_forced / max(r.n_disp, 1),
                       qw_forced_frac=r.qw_forced / max(r.qw_total, 1),
                       n_forced=r.n_forced, n_disp=r.n_disp, max_span=r.max_span,
                       n_rebuild=r.n_rebuild, secs=round(time.time() - t, 1))
            if wr is None:
                wr = csv.DictWriter(f, fieldnames=list(row))
                if new:
                    wr.writeheader()
            wr.writerow(row)
            f.flush()
            log(f"  {name:22s} {row['secs']:5.1f}s p99_dl {st['w_p99_dl']:9.3f} "
                f"gap {row['gap_p99dl']:6.3f} | max_excess {st['max_excess']:9.1f} "
                f"guar@0 {gua0:8.1f} guar@p99 {guaF:9.1f} guarmax {gmax:9.1f} used {used:.3f} | "
                f"exc|wf<1s {st['max_excess_wf0']:8.1f} | maxheavy {st['max_heavy']:8.1f} | forced {row['forced_frac']*100:6.3f}% "
                f"qw {row['qw_forced_frac']*100:6.2f}%")
            del r
    f.close()
    log(f"wrote {path}")


if __name__ == "__main__":
    main()
