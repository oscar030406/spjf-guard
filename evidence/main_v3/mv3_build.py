"""Stage 1: build every trace this experiment runs on, through the verified pipeline.

Nothing here is new.  SP.p2_inputs / ms_entries / overlay / rebase / level_ks /
copies_probe / k1_select / busy_comp are the pipeline's own; only the pool restriction
(validation = the 60 s-regime DEV semesters minus the dev-test semester 2022-2; t222 =
2022-2 alone) and the choice of which ranking scores to carry are ours.

    primary  rep 0..4   pool SP.POOL60, copies from the cache's copies.csv, week set from
                        the cache's p2weeks.csv -- byte-identical to the v2.1 trace.
    valid    rep 0,1    pool minus 2022-2, copy count from SP.copies_probe (the probe is
                        written to copies_probe_valid.csv), week set from the overlays.
    t222     rep 0      pool = 2022-2 alone; built only if the probe needs <= 100 copies.
    k1       rep 0      SP.k1_select, busy-hour rho ~ 0.80 at one server.

output:  <scratch>/mv3/traces/<trace>_rep<r>.npz  (a, svc, dl, exam, hvt, wk, weeks, K, W
         and one array per ranking score);  trace_summary.csv here.
usage:   mv3_build.py [--traces primary,valid,t222,k1] [--reps 0,1,2,3,4]
"""
from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd

import mv3_common as C
from mv3_common import SP


def week_index(a_raw, weeks):
    wk = np.floor((a_raw - SP.REF_MON) / SP.WEEK).astype(np.int64)
    wki = np.searchsorted(weeks, wk)
    assert np.array_equal(weeks[np.minimum(wki, len(weeks) - 1)], wk), "job outside week set"
    return wki.astype(np.int16)


def build_one(lg, I, key, trace, rep, entries, weeks, D, S, copies):
    a_raw, svc, jidx, _ = SP.overlay(entries, I["per_cs"], key)
    comp, W = SP.busy_comp(a_raw, svc, jidx, D, S)
    K = SP.level_ks(W) if trace != "k1" else [1]
    wki = week_index(a_raw, weeks)
    a = SP.rebase(a_raw)
    assert np.all(np.diff(a) >= 0)
    del a_raw
    P = C.predictions(I, jidx)
    np.savez(C.trace_path(trace, rep), a=a, svc=svc, dl=I["in_dl"][jidx],
             exam=I["in_exam"][jidx], hvt=I["hvt"][jidx], wk=wki,
             weeks=weeks.astype(np.int64), K=np.array(K, np.int64), W=np.float64(W),
             copies=np.int64(copies), **P)
    row = dict(trace=trace, rep=rep, copies=copies, class_semesters=len(I["per_cs"]),
               n_jobs=len(a), n_weeks=len(weeks), busy_hour_work_s=round(W, 3),
               k_per_rho="/".join(map(str, K)),
               rho_busy="/".join(f"{W / (3600.0 * k):.4f}" for k in K),
               n_deadline_window=int(I["in_dl"][jidx].sum()), n_heavy=int(I["hvt"][jidx].sum()),
               span_days=round(float(a.max()) / 86400.0, 1), scores=",".join(sorted(P)),
               busy_hour=comp["hour"], busy_share_cap60=comp["share_Ccap60"])
    lg.el(f"{trace} rep{rep}: n={len(a):,} W={W:,.1f}s k={K} "
          f"rho={[round(W / (3600.0 * k), 4) for k in K]} weeks={len(weeks)} "
          f"dl={int(I['in_dl'][jidx].sum()):,} heavy={int(I['hvt'][jidx].sum()):,} "
          f"scores={sorted(P)}")
    del a, svc, jidx, P
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--traces", default="primary,valid,t222,k1")
    ap.add_argument("--reps", default="0,1,2,3,4")
    args = ap.parse_args()
    traces = args.traces.split(",")
    reps = [int(x) for x in args.reps.split(",")]

    lg = C.Log("build")
    ev, D, S = C.load_base()
    lg.el("cache loaded")
    I = SP.p2_inputs(D, S, C.CFG, C.CACHE, "base")
    key = SP.trace_key(C.CFG)
    lg.el(f"p2_inputs {C.CFG}: {I['info']}; {len(I['per_cs'])} class-semesters; key={key}; "
          f"heavy_thr={float(D['heavy_thr']):.4f} s")
    rows = []
    csvp = os.path.join(C.HERE, "trace_summary.csv")
    if os.path.exists(csvp):
        rows = pd.read_csv(csvp).to_dict("records")

    for trace in traces:
        pool = C.pool_of(trace, I)
        if trace == "primary":
            cp = pd.read_csv(os.path.join(C.CACHE, "copies.csv")).set_index("trace")
            copies = int(cp.loc["primary", "copies"])
            weeks = SP.p2_weeks(C.CACHE, "primary")
            lg.el(f"primary: {len(pool)} class-semesters, {copies} copies (cache copies.csv), "
                  f"{len(weeks)} weeks (cache p2weeks.csv)")
            for rep in reps:
                rows.append(build_one(lg, I, key, trace, rep,
                                      SP.ms_entries(pool, copies, rep), weeks, D, S, copies))
        elif trace in ("valid", "t222"):
            use = [r for r in reps if r < (2 if trace == "valid" else 1)]
            J = dict(I, per_cs={cs: I["per_cs"][cs] for cs in pool}, pool=pool)
            try:
                copies, Ws = SP.copies_probe(pool, J["per_cs"], key, SP.PROBE_REPS)
            except RuntimeError as e:
                lg.el(f"{trace}: NOT USABLE -- {e}")
                rows.append(dict(trace=trace, rep=-1, copies=-1,
                                 class_semesters=len(pool), n_jobs=0, k_per_rho="n/a",
                                 scores=f"not usable: {e}"))
                continue
            pd.DataFrame({f"rep{r}_W": v for r, v in Ws.items()}).assign(
                copies=lambda x: np.arange(1, len(x) + 1)).to_csv(
                os.path.join(C.HERE, f"copies_probe_{trace}.csv"), index=False)
            kk = {r: SP.level_ks(Ws[r][-1]) for r in Ws}
            lg.el(f"{trace}: {len(pool)} class-semesters; probe stops at {copies} copies "
                  f"(k >= {SP.K_MIN_RHO1} at rho 1.0 and three distinct k in every probe rep); "
                  f"k at the probe's last count {kk}")
            if trace == "t222" and copies > C.T222_CMAX_OK:
                lg.el(f"t222: NOT USABLE -- {copies} copies of the same {len(pool)} course "
                      f"calendars are needed to load the pool (> {C.T222_CMAX_OK}); stacking "
                      f"one semester that many times makes deadline spikes unlike the "
                      f"primary trace's, so it is not a held-out stand-in for it.")
                rows.append(dict(trace=trace, rep=-1, copies=copies,
                                 class_semesters=len(pool), n_jobs=0, k_per_rho="n/a",
                                 scores=f"not usable: needs {copies} copies"))
                continue
            wks = set()
            for r in use:
                a_raw, _, _, _ = SP.overlay(SP.ms_entries(pool, copies, r), J["per_cs"], key)
                wks |= set(np.unique(np.floor((a_raw - SP.REF_MON) / SP.WEEK)
                                     .astype(np.int64)).tolist())
                del a_raw
            weeks = np.array(sorted(wks), dtype=np.int64)
            for rep in use:
                rows.append(build_one(lg, J, key, trace, rep,
                                      SP.ms_entries(pool, copies, rep), weeks, D, S, copies))
        elif trace == "k1":
            sel, rho_p = SP.k1_select(pool, I["per_cs"], SP.SEED * 100 + 50 + 0, key)
            a_raw, _, _, _ = SP.overlay(sel, I["per_cs"], key)
            weeks = np.array(sorted(set(np.unique(np.floor(
                (a_raw - SP.REF_MON) / SP.WEEK).astype(np.int64)).tolist())), np.int64)
            del a_raw
            lg.el(f"k1: {len(sel)} class-semester copies, busy-hour rho at k=1 = {rho_p:.4f}")
            rows.append(build_one(lg, I, key, "k1", 0, sel, weeks, D, S, len(sel)))
        else:
            raise SystemExit(trace)

    t = pd.DataFrame(rows).drop_duplicates(subset=["trace", "rep"], keep="last")
    t.to_csv(csvp, index=False)
    lg.w("\n" + t.to_string(index=False))
    lg.close()


if __name__ == "__main__":
    main()
