"""Fit the effective capacity on one chronological part of the window, test on another.

For every pool and every split (see fch_common.SPLITS):

  1. FIT PART ONLY.  The setup/teardown term s0 is re-estimated on it (median inter-run
     gap < 600 s on the same worker) and the effective capacity k_eff is chosen on it, by
     the criterion ../firefox_ci/fci_simval.py uses -- minimise
     |log(mean ratio)| + |log(p90 ratio)| against the RECORDED waits -- on the original's
     coarse grid and, separately, on the step-1 grid.  Those two numbers, and nothing
     else, are what gets fitted; the discipline (priority-then-FIFO), the priority map,
     the arrivals and the services are all read from the data.
  2. FREEZE and simulate the whole window with them, reading the metrics off the TEST
     part only.  The whole window is simulated so the queue state is carried across the
     split boundary; a run's start depends only on runs that became pending earlier, so
     this is exactly "simulate up to the end of the test part with the state that the
     fit part left behind".  A burn-in variant that additionally drops the first 12 h of
     the test part is reported beside it, because the reverse split's test part starts at
     the window boundary, where the simulator starts from an empty system and the real
     pool did not.
  3. NO-FIT BASELINES on the same test part: k = the nominal machine count (every worker
     that appears in the pool's window), with and without the setup term; and, for
     reference, the whole-window fit of ../firefox_ci/ (k_eff = 156 / 96), which is the
     circular one.

usage: fch_holdout.py [pool-tag ...]        (default: both pools)
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

import fch_common as C
from fch_common import FC


def fit_k(lg, df, t0, t1, mfit, s0, nwork, fine):
    """Choose k on the fit part alone.  Returns (k, objective, table of the search)."""
    rec = df.wait.values[mfit]
    sched = df.scheduled.values[mfit]
    rows, best = [], None
    for k in C.k_grid(nwork, fine=fine):
        w = C.simulate(df, t0, t1, k, s0)[mfit]
        e = C.fit_objective(w, rec)
        rows.append(dict(k=k, sim_mean=float(w.mean()), rec_mean=float(rec.mean()),
                         sim_p90=float(np.percentile(w, 90)),
                         rec_p90=float(np.percentile(rec, 90)), objective=float(e),
                         grid="fine" if fine else "coarse"))
        if best is None or e < best[1]:
            best = (k, e)
    del sched
    return best[0], best[1], rows


def run_pool(lg, pool, all_rows, all_search):
    tag = pool.replace("/", "__")
    df, t0, t1 = C.load_pool(pool)
    sched = df.scheduled.values.astype(np.float64)
    rec = df.wait.values.astype(np.float64)
    nwork = int(df.worker.nunique())
    win_days = (t1 - t0) / FC.DAY
    keff_orig = int(pd.read_csv(
        os.path.join(C.FCIDIR, f"keff_{tag}.csv")).k_eff.iloc[0])
    s0_orig = float(pd.read_csv(
        os.path.join(C.FCIDIR, f"keff_{tag}.csv")).setup_s.iloc[0])
    lg.w(f"\n================ {pool} ================")
    lg.w(f"  window {FC.window(pool)[0]} .. {FC.window(pool)[1]}  ({win_days:.0f} d), "
         f"{len(df):,} runs, {nwork} distinct workers, "
         f"recorded wait mean {rec.mean():.1f} s p90 {np.percentile(rec, 90):.1f} s")
    lg.w(f"  ../firefox_ci fitted on the WHOLE window: k_eff = {keff_orig}, "
         f"setup = {s0_orig:.1f} s  <- the circular fit this study replaces")
    lg.w(f"  k search grid (the original's): {C.k_grid(nwork)}")

    for name, (f0, f1), (g0, g1) in C.SPLITS[pool]:
        mfit = (sched >= t0 + f0 * FC.DAY) & (sched < t0 + f1 * FC.DAY)
        mtest = (sched >= t0 + g0 * FC.DAY) & (sched < t0 + g1 * FC.DAY)
        mburn = mtest & (sched >= t0 + (g0 * 24 + C.BURN_IN_H) * 3600.0)
        lg.w(f"\n  ---- split {name}: fit days [{f0:g},{f1:g}) = {int(mfit.sum()):,} runs"
             f" -> test days [{g0:g},{g1:g}) = {int(mtest.sum()):,} runs ----")
        s0 = C.setup_seconds(df[mfit])
        lg.w(f"    setup/teardown fitted on the fit part: {s0:.1f} s "
             f"(whole-window value {s0_orig:.1f} s)")
        kc, ec, rowsc = fit_k(lg, df, t0, t1, mfit, s0, nwork, fine=False)
        kf, ef, rowsf = fit_k(lg, df, t0, t1, mfit, s0, nwork, fine=True)
        for r in rowsc + rowsf:
            r.update(pool=pool, split=name)
        all_search.extend(rowsc + rowsf)
        lg.w(f"    k_eff fitted on the fit part: {kc} on the original's coarse grid "
             f"(objective {ec:.4f}); {kf} on the step-1 grid (objective {ef:.4f})")

        variants = [
            (f"HELD OUT  k_eff={kc} (coarse grid, fit part) + setup {s0:.0f}s", kc, s0),
            (f"HELD OUT  k_eff={kf} (step-1 grid, fit part) + setup {s0:.0f}s", kf, s0),
            (f"no fit    k = nominal machines = {nwork} + setup {s0:.0f}s", nwork, s0),
            (f"no fit    k = nominal machines = {nwork}, no setup", nwork, 0.0),
            (f"circular  k_eff={keff_orig} (whole window) + setup {s0_orig:.0f}s",
             keff_orig, s0_orig),
        ]
        for vt, k, extra in variants:
            w = C.simulate(df, t0, t1, k, extra)
            for part, m in (("test", mtest), ("test-burnin", mburn), ("fit", mfit)):
                r = C.metrics(rec[m], w[m], sched[m], t0, vt)
                r.update(pool=pool, pool_tag=tag, split=name, part=part, k=int(k),
                         setup_s=float(extra), n_fit=int(mfit.sum()),
                         n_test=int(mtest.sum()), nominal_k=nwork,
                         k_eff_coarse=kc, k_eff_fine=kf, s0_fit=float(s0),
                         k_eff_whole=keff_orig, s0_whole=s0_orig)
                all_rows.append(r)
            t = [r for r in all_rows if r["variant"] == vt and r["split"] == name
                 and r["pool"] == pool]
            tt = [r for r in t if r["part"] == "test"][0]
            lg.w(f"    {vt:58s}  TEST  mean {tt['sim_mean']:8.1f} "
                 f"(rec {tt['rec_mean']:8.1f}, x{tt['mean_ratio']:.2f})  "
                 f"p90 x{tt['p90_ratio']:.2f}  p99 x{tt['p99_ratio']:.2f}  "
                 f"rho_h {tt['hourly_pearson']:.3f}  sp {tt['job_spearman']:.3f}  "
                 f"med|e| {tt['med_abs_err']:.0f}s")


def main():
    args = sys.argv[1:]
    pools = [FC.pool_from_tag(t) for t in args] if args else list(C.POOLS)
    lg = C.Log("holdout")
    for f, h in C.manifest()[1]:
        lg.w(f"    {f:70s} {h}")
    rows, search = [], []
    for pool in pools:
        run_pool(lg, pool, rows, search)
    p = os.path.join(C.HERE, "holdout.csv")
    old = pd.read_csv(p).to_dict("records") if os.path.exists(p) else []
    t = pd.DataFrame(old + rows).drop_duplicates(
        subset=["pool", "split", "part", "variant"], keep="last")
    t.to_csv(p, index=False)
    ps = os.path.join(C.HERE, "ksearch.csv")
    olds = pd.read_csv(ps).to_dict("records") if os.path.exists(ps) else []
    ts = pd.DataFrame(olds + search).drop_duplicates(
        subset=["pool", "split", "grid", "k"], keep="last")
    ts.to_csv(ps, index=False)
    lg.el(f"wrote {p} ({len(t)} rows) and {ps} ({len(ts)} rows)")
    lg.close()


if __name__ == "__main__":
    main()
