"""Stage 1 (v3.1): rebuild every trace under this manifest.

Identical to v3's build except that the VALIDATION trace now gets as many overlays as the
primary trace has (5), because the selection is now worst-case over overlays as well as
over load levels (verifier finding F8).  Its week set is the union over all five overlays.

The build also logs the sha256 of the data artefacts every number is computed from
(the v2.1 cache, the ranking-score predictions, the R1S forward predictions); those are
inputs, not code, so they sit beside the manifest rather than inside it.

output: <scratch>/mv31/traces/<trace>_rep<r>.npz;  trace_summary.csv here
usage:  v31_build.py [--traces primary,valid,t222,k1] [--reps 0,1,2,3,4]
"""
from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd

import v31_common as C
from v31_common import SP


def week_index(a_raw, weeks):
    wk = np.floor((a_raw - SP.REF_MON) / SP.WEEK).astype(np.int64)
    wki = np.searchsorted(weeks, wk)
    assert np.array_equal(weeks[np.minimum(wki, len(weeks) - 1)], wk), "job outside week set"
    return wki.astype(np.int16)


def build_one(lg, I, key, trace, rep, entries, weeks, D, S, copies):
    a_raw, svc, jidx, _ = SP.overlay(entries, I["per_cs"], key)
    comp, W = SP.busy_comp(a_raw, svc, jidx, D, S)
    K = SP.level_ks(W) if trace != "k1" else [1]
    if trace != "k1":
        assert SP.k_ok(K), (trace, rep, W, K)
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
               busy_hour=comp["hour"])
    lg.el(f"{trace} rep{rep}: n={len(a):,} W={W:,.1f}s k={K} "
          f"rho={[round(W / (3600.0 * k), 4) for k in K]} weeks={len(weeks)} "
          f"dl={int(I['in_dl'][jidx].sum()):,} heavy={int(I['hvt'][jidx].sum()):,}")
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
    for n, h in C.input_table():
        lg.w(f"    input {n:44s} {h}")
    ev, D, S = C.load_base()
    I = SP.p2_inputs(D, S, C.CFG, C.CACHE, "base")
    key = SP.trace_key(C.CFG)
    lg.el(f"p2_inputs {C.CFG}: {I['info']}; {len(I['per_cs'])} class-semesters; "
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
            lg.el(f"primary: {len(pool)} class-semesters, {copies} copies, "
                  f"{len(weeks)} weeks (both from the v2.1 cache)")
            for rep in reps:
                rows.append(build_one(lg, I, key, trace, rep,
                                      SP.ms_entries(pool, copies, rep), weeks, D, S, copies))
        elif trace in ("valid", "t222"):
            use = [r for r in reps if r in (C.VALID_REPS if trace == "valid" else (0,))]
            J = dict(I, per_cs={cs: I["per_cs"][cs] for cs in pool}, pool=pool)
            copies, Ws = SP.copies_probe(pool, J["per_cs"], key, SP.PROBE_REPS)
            pd.DataFrame({f"rep{r}_W": v for r, v in Ws.items()}).assign(
                copies=lambda x: np.arange(1, len(x) + 1)).to_csv(
                os.path.join(C.HERE, f"copies_probe_{trace}.csv"), index=False)
            lg.el(f"{trace}: {len(pool)} class-semesters; probe stops at {copies} copies")
            if trace == "t222" and copies > C.T222_CMAX_OK:
                lg.el(f"t222: NOT USABLE -- {copies} copies of the same {len(pool)} course "
                      f"calendars needed (> {C.T222_CMAX_OK}); unchanged from v3.")
                rows.append(dict(trace=trace, rep=-1, copies=copies,
                                 class_semesters=len(pool), n_jobs=0, k_per_rho="n/a",
                                 scores=f"not usable: needs {copies} copies"))
                continue
            wks = set()
            for r in (C.VALID_REPS if trace == "valid" else (0,)):
                a_raw, _, _, _ = SP.overlay(SP.ms_entries(pool, copies, r), J["per_cs"], key)
                wks |= set(np.unique(np.floor((a_raw - SP.REF_MON) / SP.WEEK)
                                     .astype(np.int64)).tolist())
                del a_raw
            weeks = np.array(sorted(wks), dtype=np.int64)
            lg.el(f"{trace}: week set = union over overlays "
                  f"{list(C.VALID_REPS if trace == 'valid' else (0,))}, {len(weeks)} weeks")
            for rep in use:
                rows.append(build_one(lg, J, key, trace, rep,
                                      SP.ms_entries(pool, copies, rep), weeks, D, S, copies))
        elif trace == "k1":
            sel, rho_p = SP.k1_select(pool, I["per_cs"], SP.SEED * 100 + 50 + 0, key)
            a_raw, _, _, _ = SP.overlay(sel, I["per_cs"], key)
            weeks = np.array(sorted(set(np.unique(np.floor(
                (a_raw - SP.REF_MON) / SP.WEEK).astype(np.int64)).tolist())), np.int64)
            del a_raw
            lg.el(f"k1: {len(sel)} class-semester copies, busy-hour rho = {rho_p:.4f}")
            rows.append(build_one(lg, I, key, "k1", 0, sel, weeks, D, S, len(sel)))
        else:
            raise SystemExit(trace)

    t = pd.DataFrame(rows).drop_duplicates(subset=["trace", "rep"], keep="last")
    t.to_csv(csvp, index=False)
    lg.w("\n" + t.to_string(index=False))
    lg.close()


if __name__ == "__main__":
    main()
