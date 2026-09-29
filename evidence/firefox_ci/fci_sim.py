"""SPJF + overtake-budget guard on a trace whose congestion was RECORDED, not assumed.

    uv run --with pandas --with numpy --with pyarrow --with numba python fci_sim.py <pool-tag>

Same protocol as evidence/cross_domain/cd_sim.py.  k identical non-preemptive servers,
service capped at L' (train p99.9, frozen in fci_build.py).  Arrivals are the recorded
`scheduled` times of the test window; service times are the recorded
`resolved - started`.

Two capacity levels only: the pool's own recorded size (so the congestion in the run is
the congestion the pool actually had) and one reduced level.

Policies: FCFS, true-size SJF (a reference, not an optimum), SPJF on the predicted
expected cost, and SPJF wrapped in the overtake-budget guard at G in {3, 5, 10} L'.
The ranking score is chosen on the VALIDATION window and then frozen.  Every guarded run
is checked job by job against the theorem of guardkern_snapshot.py:

    constant budget B :  W <= W_FCFS + B/k + (3 - 2/k) L'
"""
import os
import sys

sys.dont_write_bytecode = True

import numpy as np
import pandas as pd

import fci_common as C
import guardkern_snapshot as GK
from fci_simval import k_series, simulate_kt

GUARANTEES = (3.0, 5.0, 10.0)
TOL = 1e-6
PRED_COLS = ("pred_tweedie", "pred_log", "pred_ent")


def busy_hour_load(arrival, serv):
    t0 = arrival.min()
    nb = int(np.ceil((np.max(arrival + serv) - t0) / 3600.0)) + 1
    a = np.zeros(nb)
    for s_, d_ in zip(arrival, serv):
        e_ = s_ + d_
        b0, b1 = int((s_ - t0) // 3600), min(nb - 1, int((e_ - t0) // 3600))
        if b0 == b1:
            a[b0] += e_ - s_
        else:
            a[b0] += t0 + (b0 + 1) * 3600 - s_
            for b in range(b0 + 1, b1):
                a[b] += 3600.0
            a[b1] += e_ - (t0 + b1 * 3600)
    return float(a.max() / 3600.0), a


def summarise(name, wait, wf, heavy, k, L, fired, ndisp, bound=None):
    d = dict(policy=name, mean_s=float(wait.mean()),
             p50_s=float(np.percentile(wait, 50)),
             p90_s=float(np.percentile(wait, 90)),
             p99_s=float(np.percentile(wait, 99)),
             p999_s=float(np.percentile(wait, 99.9)), max_s=float(wait.max()),
             p99_heavy_s=float(np.percentile(wait[heavy], 99)) if heavy.any() else np.nan,
             max_heavy_s=float(wait[heavy].max()) if heavy.any() else np.nan,
             max_excess_fcfs_s=float((wait - wf).max()),
             fire_rate=float(fired / max(1, ndisp)))
    if bound is not None:
        d["bound_violation_s"] = float((wait - bound).max())
        d["bound_slack_med_L"] = float(np.median(bound - wait) / L)
    return d


MSLOTS = 1 << 19        # > any live span of waiting ranks here; keeps the trees small


def choose_score(fh, valid, L, k):
    """Pick the ranking score on the VALIDATION window only."""
    a = valid.arrival.values.astype(np.float64)
    s = np.maximum(np.minimum(valid.dur.values.astype(np.float64), L), 1e-3)
    wf = GK.run(a, s, k, policy="fcfs", Mslots=MSLOTS).w
    ws = GK.run(a, s, k, policy="pri", pred=s, Mslots=MSLOTS).w
    b99, r99 = np.percentile(wf, 99), np.percentile(ws, 99)
    C.log(fh, f"  score selection on the validation window (n={len(valid)}, k={k}): "
              f"FCFS p99 {b99:.1f}s / mean {wf.mean():.1f}s, "
              f"SJF-true p99 {r99:.1f}s / mean {ws.mean():.1f}s")
    usable = b99 > r99
    if not usable:
        C.log(fh, "  !! true-size SJF has a WORSE p99 wait than FCFS on this window, so "
                  "the 'gap closed on p99' statistic has no usable denominator here "
                  "(same situation as Intel Netbatch in evidence/cross_domain).  The "
                  "ranking score is therefore selected on the p99 wait itself, and the "
                  "p99 gap is reported as not-a-number wherever the denominator is "
                  "non-positive.")
    best, bestscore = None, -np.inf
    for col in PRED_COLS:
        w = GK.run(a, s, k, policy="pri", pred=valid[col].values.astype(np.float64),
                   Mslots=MSLOTS).w
        p99 = float(np.percentile(w, 99))
        g = (b99 - p99) / (b99 - r99) if usable else np.nan
        score = g if usable else -p99
        C.log(fh, f"     {col:14s} p99={p99:9.1f}  mean={w.mean():9.1f}  "
                  f"gap_p99={g:.4f}")
        if score > bestscore:
            best, bestscore = col, score
    C.log(fh, f"  -> ranking score frozen to {best} "
              f"({'validation gap_p99' if usable else 'smallest validation p99'} "
              f"{bestscore if usable else -bestscore:.4f})")
    return best


def main(tag):
    meta = pd.read_csv(os.path.join(C.HERE, f"meta_{tag}.csv")).iloc[0]
    L = float(meta.L)
    te = pd.read_parquet(os.path.join(C.SCRATCH, f"{tag}_test_pred.parquet"))
    va = pd.read_parquet(os.path.join(C.SCRATCH, f"{tag}_valid_pred.parquet"))
    te = te.sort_values("arrival", kind="mergesort").reset_index(drop=True)
    va = va.sort_values("arrival", kind="mergesort").reset_index(drop=True)
    runs_all = pd.read_parquet(os.path.join(C.DATA, f"runs_{tag}.parquet"))
    runs_all = runs_all[np.isfinite(runs_all.started) & np.isfinite(runs_all.resolved)]
    runs_all = runs_all[(runs_all.resolved - runs_all.started) > 0]

    arrival = te.arrival.values.astype(np.float64)
    serv = np.maximum(np.minimum(te.dur.values.astype(np.float64), L), 1e-3)
    heavy = te.heavy.values.astype(bool)
    rec = te.wait_rec.values.astype(np.float64)

    out = os.path.join(C.HERE, f"out_sim_{tag}.txt")
    rows = []
    with open(out, "w", encoding="utf-8") as fh:
        C.log(fh, f"=== scheduling on the RECORDED arrival times, {tag} (test window) ===")
        t0, t1 = arrival.min(), arrival.max()
        ks = k_series(runs_all[(runs_all.scheduled >= t0) & (runs_all.scheduled <= t1)],
                      t0, t1 + 3600.0)
        # "the recorded k" is the capacity that reproduces the RECORDED waits, not the
        # number of machines the pool lists: fci_simval.py fits it on the whole window
        # (some listed machines are up but not claiming).  Falling back to the busiest
        # hour's worker count only if fci_simval.py has not been run.
        kp = os.path.join(C.HERE, f"keff_{tag}.csv")
        if os.path.exists(kp):
            km = pd.read_csv(kp).iloc[0]
            k_rec = int(km.k_eff)
            C.log(fh, f"k from keff_{tag}.csv: effective k = {k_rec} "
                      f"(pool lists {int(km.n_workers)} workers, {int(km.k_max_busy)} "
                      f"busy at once; setup/teardown {km.setup_s:.1f}s is already inside "
                      f"the service times)")
        else:
            k_rec = int(ks.max())
        C.log(fh, f"runs={len(te)}  span={(t1-t0)/C.DAY:.2f} days  L'={L:.1f}s  "
                  f"total work={serv.sum()/86400:.2f} server-days  "
                  f"heavy share={heavy.mean():.4f}")
        C.log(fh, f"recorded k over the test window: max busy in an hour = {k_rec}, "
                  f"median = {int(np.median(ks))}, min = {int(ks.min())}")
        a_max, _ = busy_hour_load(arrival, serv)
        C.log(fh, f"busiest hour of the test window needs {a_max:.2f} server-equivalents; "
                  f"at k={k_rec} that is utilisation {a_max/k_rec:.4f}; "
                  f"whole-window utilisation {serv.sum()/((t1-t0)*k_rec):.4f}")
        C.log(fh, f"RECORDED wait in this window: mean={rec.mean():.1f} "
                  f"p50={np.percentile(rec,50):.1f} p90={np.percentile(rec,90):.1f} "
                  f"p99={np.percentile(rec,99):.1f} max={rec.max():.1f}")

        # the ranking score is picked with the VALIDATION window's own capacity, so no
        # quantity of the test window enters the choice
        v0, v1 = va.arrival.min(), va.arrival.max()
        kv = k_series(runs_all[(runs_all.scheduled >= v0) & (runs_all.scheduled <= v1)],
                      v0, v1 + 3600.0)
        score = choose_score(fh, va, L, int(kv.max()))

        caps = [(f"recorded k={k_rec}", k_rec), (f"reduced k={max(1,int(0.8*k_rec))}",
                                                 max(1, int(0.8 * k_rec)))]
        for label, k in caps:
            C.log(fh, f"\n---- {label}  (busy-hour utilisation {a_max/k:.4f}, "
                      f"whole-window {serv.sum()/((t1-t0)*k):.4f}) ----")
            wf = GK.run(arrival, serv, k, policy="fcfs", Mslots=MSLOTS).w
            ws = GK.run(arrival, serv, k, policy="pri", pred=serv, Mslots=MSLOTS).w
            runs = [("FCFS", wf, 0, 0, None), ("SJF-true (reference)", ws, 0, 0, None)]
            for col in PRED_COLS:
                w = GK.run(arrival, serv, k, policy="pri",
                           pred=te[col].values.astype(np.float64), Mslots=MSLOTS).w
                runs.append((f"SPJF {col}" + (" [chosen]" if col == score else ""),
                             w, 0, 0, None))
            pred = te[score].values.astype(np.float64)
            for G in GUARANTEES:
                B = k * G * L - (3 * k - 2) * L
                if B < 0:
                    C.log(fh, f"   guarantee G={G:g}L' is below the theorem's floor "
                              f"(3-2/k)L' = {(3-2/k)*L:.1f}s; B set to 0 (= FCFS)")
                    B = 0.0
                r = GK.run(arrival, serv, k, policy="guard", pred=pred, B=B,
                           Mslots=MSLOTS)
                bnd = GK.guaranteed(wf, k, B, L=L)
                runs.append((f"guard G={G:g}L' (B={B:.0f}s)", r.w, r.n_forced,
                             r.n_disp, bnd))
            base_p99, base_mean = np.percentile(wf, 99), wf.mean()
            ref_p99, ref_mean = np.percentile(ws, 99), ws.mean()
            C.log(fh, f"{'policy':34s} {'mean_s':>10s} {'p50':>9s} {'p90':>10s} "
                      f"{'p99_s':>10s} {'max_s':>11s} {'p99heavy':>10s} {'gapP99':>8s} "
                      f"{'gapMean':>8s} {'maxExcess':>11s} {'fire%':>7s} {'boundOK':>9s}")
            for name, wt, nf, nd, bnd in runs:
                d = summarise(name, wt, wf, heavy, k, L, nf, nd, bnd)
                gp = ((base_p99 - d["p99_s"]) / (base_p99 - ref_p99)
                      if base_p99 > ref_p99 else np.nan)
                gm = ((base_mean - d["mean_s"]) / (base_mean - ref_mean)
                      if base_mean > ref_mean else np.nan)
                ok = ("-" if bnd is None else
                      ("yes" if d["bound_violation_s"] <= TOL
                       else f"NO {d['bound_violation_s']:.3g}"))
                C.log(fh, f"{name:34s} {d['mean_s']:10.1f} {d['p50_s']:9.1f} "
                          f"{d['p90_s']:10.1f} {d['p99_s']:10.1f} {d['max_s']:11.1f} "
                          f"{d['p99_heavy_s']:10.1f} {gp:8.4f} {gm:8.4f} "
                          f"{d['max_excess_fcfs_s']:11.1f} {d['fire_rate']*100:7.3f} "
                          f"{ok:>9s}")
                d.update(pool_tag=tag, cap=label, k=k, L=L, gap_p99=gp, gap_mean=gm,
                         n=len(te), fcfs_p99_over_L=base_p99 / L, score=score)
                rows.append(d)
            C.log(fh, f"  applicability: FCFS p99 wait / L' = {base_p99/L:.3f}; the "
                      f"theorem's smallest expressible guarantee is (3-2/k)L' = "
                      f"{(3-2/k)*L:.1f}s = {(3-2/k):.2f} L'")
        pd.DataFrame(rows).to_csv(os.path.join(C.HERE, f"sim_{tag}.csv"), index=False)
    print("wrote", out)


if __name__ == "__main__":
    main(sys.argv[1])
