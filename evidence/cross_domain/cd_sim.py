"""Scheduling on the real arrival times of the two non-education traces.

    uv run ... python cd_sim.py azure
    uv run ... python cd_sim.py netbatch

k identical non-preemptive servers, service capped at L (= train p99.9, frozen in
cd_build.py).  k is set from the busiest hour of the window being simulated so that its
utilisation is about 0.5 / 0.8 / 1.0.  Policies: FCFS, true-size SJF (reference, not
deployable), SPJF on the log-L2 and on the Tweedie score, and the overtake-budget guard
on the Tweedie score at three guarantees plus the capped relative budget.

Every guarded run is checked job by job against the theorem of
evidence/guard_variants/guardkern.py:
    constant budget B : W <= W_FCFS + B/k + (3 - 2/k) L
    budget min(C0 + eta*k*wait, Bmax) : W <= min( (W_FCFS + C0/k + (3-2/k)L)/(1-eta),
                                                   W_FCFS + Bmax/k + (3-2/k)L )
"""
import sys

sys.dont_write_bytecode = True

import os
import numpy as np
import pandas as pd
from numba import njit

import cd_common as C
from cd_kernel import simulate, POL_FCFS, POL_SPJF, POL_GUARD

RHOS = (0.5, 0.8, 1.0)
RHO_WINDOW = (0.8, 0.95)   # second capacity rule: whole-window utilisation
GUARANTEES = (2.0, 5.0, 15.0)     # in units of L
ETAS = (0.5, 0.75)
ABS_BUDGETS = (0.001, 0.01, 0.1)   # per-job budget B/k in units of L, empirical
TOL = 1e-6


def us(x):
    return np.int64(round(float(x) * 1e6))


@njit(cache=True)
def _occupancy(arrival, serv, t0, nb):
    """Service actually performed in each hour under an infinite-server schedule.

    For jobs much shorter than an hour this is the same as binning a job's whole cost
    into its arrival hour; for jobs that last hours or days it is not, and only this
    version measures the concurrency a server pool has to supply.
    """
    a = np.zeros(nb, np.float64)
    for i in range(arrival.shape[0]):
        s = arrival[i] - t0
        e = s + serv[i]
        b0 = int(s // 3600.0)
        b1 = int(e // 3600.0)
        if b1 >= nb:
            b1 = nb - 1
        if b0 == b1:
            a[b0] += e - s
        else:
            a[b0] += (b0 + 1) * 3600.0 - s
            for b in range(b0 + 1, b1):
                a[b] += 3600.0
            a[b1] += e - b1 * 3600.0
    return a


def busiest_hour_load(arrival, serv):
    t0 = arrival.min()
    nb = int(np.ceil((np.max(arrival + serv) - t0) / 3600.0)) + 1
    w = _occupancy(arrival, serv, t0, nb)
    return float(w.max() / 3600.0), int(np.argmax(w)), w


def summarise(name, wait, wf, heavy, k, L, n_fired, n_disp, bound=None):
    d = dict(policy=name, mean_s=float(wait.mean()), p99_s=float(np.percentile(wait, 99)),
             p999_s=float(np.percentile(wait, 99.9)), max_s=float(wait.max()),
             p99_heavy_s=float(np.percentile(wait[heavy], 99)) if heavy.any() else np.nan,
             max_heavy_s=float(wait[heavy].max()) if heavy.any() else np.nan,
             frac_waiting=float((wait > 1e-9).mean()),
             max_excess_fcfs_s=float((wait - wf).max()),
             fire_rate=float(n_fired / max(1, n_disp)))
    if bound is not None:
        d["bound_violation_s"] = float((wait - bound).max())
        d["bound_slack_med_L"] = float(np.median(bound - wait) / L)
    return d


def main(which):
    meta = pd.read_csv(os.path.join(C.HERE, f"meta_{which}.csv")).iloc[0]
    L = float(meta.L)
    df = pd.read_parquet(os.path.join(C.SCRATCH, f"{which}_test_pred.parquet"))
    df = df.sort_values("arrival", kind="mergesort").reset_index(drop=True)
    arrival = df.arrival.values.astype(np.float64)
    serv = np.minimum(df.dur.values.astype(np.float64), L)
    serv = np.maximum(serv, 1e-3)
    heavy = df.heavy.values.astype(bool)
    out = os.path.join(C.HERE, f"out_sim_{which}.txt")
    rows = []
    with open(out, "w", encoding="utf-8") as fh:
        C.log(fh, f"=== scheduling on the real arrival times, {which} (test window) ===")
        C.log(fh, f"jobs={len(df)}  span={(arrival.max()-arrival.min())/86400:.2f} days  "
                  f"L={L:.3f}s  total work={serv.sum():.0f}s  "
                  f"heavy share={heavy.mean():.4f}")
        a_max, h_max, w = busiest_hour_load(arrival, serv)
        C.log(fh, f"busiest hour of the window: index {h_max}, "
                  f"{a_max:.3f} server-equivalents; median hour "
                  f"{np.median(w)/3600:.3f}; mean {w.mean()/3600:.3f}")
        span = arrival.max() - arrival.min()
        a_mean = serv.sum() / span
        caps = [(f"busy-hour rho={r}", max(1, int(np.ceil(a_max / r))), r) for r in RHOS]
        caps += [(f"window rho={r}", max(1, int(np.ceil(a_mean / r))), r)
                 for r in RHO_WINDOW]
        seen = set()
        for label, k, rho in caps:
            if k in seen:
                C.log(fh, f"\n---- {label} gives k={k}, already run ----")
                continue
            seen.add(k)
            ach = a_max / k
            C.log(fh, f"\n---- target {label} -> k={k} "
                      f"(achieved busy-hour utilisation {ach:.4f}; "
                      f"whole-window utilisation {serv.sum()/(span*k):.4f}) ----")
            s_f, _, _ = simulate(arrival, serv, arrival, k, POL_FCFS, 0, 1, 0, -1)
            wf = s_f - arrival
            s_s, _, _ = simulate(arrival, serv, serv, k, POL_SPJF, 0, 1, 0, -1)
            ws = s_s - arrival
            runs = [("FCFS", wf, 0, 0, None),
                    ("SJF-true (reference)", ws, 0, 0, None)]
            for tag, col in (("SPJF-log", "pred_log"), ("SPJF-tweedie", "pred_tweedie"),
                             ("SPJF-ent-tweedie", "pred_ent")):
                p = df[col].values.astype(np.float64)
                st, _, _ = simulate(arrival, serv, p, k, POL_SPJF, 0, 1, 0, -1)
                runs.append((tag, st - arrival, 0, 0, None))
            pred = df["pred_tweedie"].values.astype(np.float64)
            for G in GUARANTEES:
                B = k * G * L - (3 * k - 2) * L
                if B < 0:
                    C.log(fh, f"   guarantee G={G:g}L is below the theorem's floor "
                              f"(3-2/k)L = {(3-2/k)*L:.1f}s at k={k}: B would be "
                              f"{B:.1f}s; the run uses B=0, which is FCFS.")
                    B = 0.0
                st, nf, nd = simulate(arrival, serv, pred, k, POL_GUARD, 0, 1, us(B), -1)
                wg = st - arrival
                bnd = wf + B / k + (3 - 2 / k) * L
                runs.append((f"guard G={G:g}L (B={B:.0f}s)", wg, nf, nd, bnd))
            for frac in ABS_BUDGETS:
                B = k * frac * L          # per-job overtake budget of frac*L seconds
                st, nf, nd = simulate(arrival, serv, pred, k, POL_GUARD, 0, 1, us(B), -1)
                wg = st - arrival
                bnd = wf + B / k + (3 - 2 / k) * L
                runs.append((f"guard B/k={frac:g}L (B={B:.0f}s)", wg, nf, nd, bnd))
            Bmax = k * GUARANTEES[-1] * L - (3 * k - 2) * L
            C0 = k * L
            for eta in ETAS:
                en, ed = int(round(eta * 4)) * k, 4
                st, nf, nd = simulate(arrival, serv, pred, k, POL_GUARD, en, ed,
                                      us(C0), us(Bmax))
                wg = st - arrival
                b1 = (wf + C0 / k + (3 - 2 / k) * L) / (1 - eta)
                b2 = wf + Bmax / k + (3 - 2 / k) * L
                bnd = np.minimum(b1, b2)
                runs.append((f"guard rel eta={eta:g} (C0={C0:.0f}s,Bmax={Bmax:.0f}s)",
                             wg, nf, nd, bnd))
            base_p99, base_mean = np.percentile(wf, 99), wf.mean()
            ref_p99, ref_mean = np.percentile(ws, 99), ws.mean()
            hdr = (f"{'policy':40s} {'mean_s':>10s} {'p99_s':>10s} {'p99.9_s':>10s} "
                   f"{'max_s':>11s} {'p99heavy':>10s} {'gapP99':>8s} {'gapMean':>8s} "
                   f"{'maxExcess':>11s} {'fire%':>7s} {'boundOK':>9s}")
            C.log(fh, hdr)
            for name, wt, nf, nd, bnd in runs:
                d = summarise(name, wt, wf, heavy, k, L, nf, nd, bnd)
                gp = (base_p99 - d["p99_s"]) / (base_p99 - ref_p99) if base_p99 > ref_p99 else np.nan
                gm = (base_mean - d["mean_s"]) / (base_mean - ref_mean) if base_mean > ref_mean else np.nan
                ok = "-" if bnd is None else ("yes" if d["bound_violation_s"] <= TOL else
                                              f"NO {d['bound_violation_s']:.3g}")
                C.log(fh, f"{name:40s} {d['mean_s']:10.4f} {d['p99_s']:10.4f} "
                          f"{d['p999_s']:10.4f} {d['max_s']:11.2f} {d['p99_heavy_s']:10.2f} "
                          f"{gp:8.4f} {gm:8.4f} {d['max_excess_fcfs_s']:11.2f} "
                          f"{d['fire_rate']*100:7.3f} {ok:>9s}")
                d.update(trace=which, cap=label, rho=rho, k=k, L=L, gap_p99=gp, gap_mean=gm,
                         busy_hour_load=a_max, n=len(df))
                rows.append(d)
        pd.DataFrame(rows).to_csv(os.path.join(C.HERE, f"sim_{which}.csv"), index=False)
    print("wrote", out)


if __name__ == "__main__":
    main(sys.argv[1])
