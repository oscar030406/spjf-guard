"""Does our k-server non-preemptive simulator reproduce the waits the pool RECORDED?

    uv run --with pandas --with numpy --with pyarrow --with numba python fci_simval.py

This is the reason the trace was collected.  Everywhere else in the project the queue is
simulated; here the same queue was observed, so the simulator can be checked against it.

Input replayed per run: arrival = `scheduled` (the instant Taskcluster made the run
claimable, i.e. after its dependencies resolved), service = `resolved - started`.
Target: the recorded wait `started - scheduled`.

Three things the real pool does that a fixed-k work-conserving FCFS simulator does not:
  (a) capacity is not constant -- machines reboot, get reimaged, get quarantined, so the
      number of workers able to claim varies by the hour;
  (b) the real discipline is priority-then-FIFO, not FCFS (Taskcluster serves a task
      queue in priority order and, within a priority, in the order tasks became
      pending);
  (c) a worker is not instantly reusable: generic-worker tears down and sets up between
      tasks, so a fraction of the wall clock is not service and not queueing.
Each is added one at a time and the residual is reported, so the reader can see which
part of the gap each one explains.

A second, independent simulator (the project's own kernel, copied to this directory as
guardkern_snapshot.py, sha256 recorded in README.md) is run on the same input with
constant k and must agree job by job with the local kernel -- the local kernel is only
trusted after that.
"""
import os
import sys

sys.dont_write_bytecode = True

import numpy as np
import pandas as pd
from numba import njit

import fci_common as C
from fci_collect import pool_tag
import guardkern_snapshot as GK

HOURS = 3600.0


# --------------------------------------------------------------------------- #
# local kernel: k(t) piecewise-constant per hour, non-preemptive, work conserving
# --------------------------------------------------------------------------- #
@njit(cache=True)
def _hpush(key, rnk, n, k_, r_):
    key[n] = k_
    rnk[n] = r_
    i = n
    while i > 0:
        p = (i - 1) >> 1
        if key[p] > key[i] or (key[p] == key[i] and rnk[p] > rnk[i]):
            key[p], key[i] = key[i], key[p]
            rnk[p], rnk[i] = rnk[i], rnk[p]
            i = p
        else:
            break
    return n + 1


@njit(cache=True)
def _hpop(key, rnk, n):
    tk, tr = key[0], rnk[0]
    n -= 1
    key[0], rnk[0] = key[n], rnk[n]
    i = 0
    while True:
        l = 2 * i + 1
        r = l + 1
        s = i
        if l < n and (key[l] < key[s] or (key[l] == key[s] and rnk[l] < rnk[s])):
            s = l
        if r < n and (key[r] < key[s] or (key[r] == key[s] and rnk[r] < rnk[s])):
            s = r
        if s == i:
            break
        key[s], key[i] = key[i], key[s]
        rnk[s], rnk[i] = rnk[i], rnk[s]
        i = s
    return tk, tr, n


@njit(cache=True)
def simulate_kt(arrival, serv, order_key, kser, t0, dt):
    """k(t) = kser[floor((t - t0)/dt)].  Dispatch the smallest order_key (ties: rank).

    Returns the start time of every job.  Arrays must be sorted by arrival.
    """
    n = arrival.shape[0]
    nb = kser.shape[0]
    start = np.full(n, -1.0, np.float64)
    ckey = np.empty(n + 2, np.float64)     # completion times of running jobs
    crnk = np.empty(n + 2, np.int64)
    nbusy = 0
    pkey = np.empty(n + 1, np.float64)
    prnk = np.empty(n + 1, np.int64)
    nh = 0
    i_arr = 0
    n_disp = 0
    t = arrival[0]
    INF = 1.0e300
    while n_disp < n:
        while nbusy > 0 and ckey[0] <= t:
            _, _, nbusy = _hpop(ckey, crnk, nbusy)
        while i_arr < n and arrival[i_arr] <= t:
            nh = _hpush(pkey, prnk, nh, order_key[i_arr], i_arr)
            i_arr += 1
        b = int((t - t0) // dt)
        if b < 0:
            b = 0
        if b >= nb:
            b = nb - 1
        kt = kser[b]
        while nbusy < kt and nh > 0:
            _, q, nh = _hpop(pkey, prnk, nh)
            start[q] = t
            n_disp += 1
            nbusy = _hpush(ckey, crnk, nbusy, t + serv[q], q)
            b = int((t - t0) // dt)
            if b < 0:
                b = 0
            if b >= nb:
                b = nb - 1
            kt = kser[b]
        nxt = INF
        if i_arr < n and arrival[i_arr] < nxt:
            nxt = arrival[i_arr]
        if nbusy > 0 and ckey[0] < nxt:
            nxt = ckey[0]
        if nh > 0:                      # a capacity change can free a server
            nb_t = t0 + (int((t - t0) // dt) + 1) * dt
            if nb_t > t and nb_t < nxt:
                nxt = nb_t
        if nxt >= INF or nxt <= t:
            if nxt <= t and nh > 0 and nbusy == 0:
                # capacity is zero for this whole bucket: jump to the next bucket
                nxt = t0 + (int((t - t0) // dt) + 1) * dt
            else:
                break
        t = nxt
    return start


# --------------------------------------------------------------------------- #
PRIO_RANK = {"highest": 0, "very-high": 1, "high": 2, "medium": 3, "normal": 3,
             "low": 4, "very-low": 5, "lowest": 6}


def load(pool):
    df = pd.read_parquet(os.path.join(C.DATA, f"runs_{pool_tag(pool)}.parquet"))
    df = df[np.isfinite(df.started) & np.isfinite(df.resolved)].copy()
    df["service"] = df.resolved - df.started
    df["wait"] = (df.started - df.scheduled).clip(lower=0.0)
    df = df[df.service > 0]
    df = df.sort_values(["scheduled", "task_id", "run_id"],
                        kind="mergesort").reset_index(drop=True)
    return df


def busy_matrix(df, t0, t1, dt=HOURS):
    """Boolean (worker x bucket): was this worker running something in that bucket."""
    nb = int(np.ceil((t1 - t0) / dt))
    wk, uniq = pd.factorize(df.worker.values)
    M = np.zeros((len(uniq), nb), bool)
    for s_, e_, w_ in zip(df.started.values, df.resolved.values, wk):
        b0 = max(0, min(nb - 1, int((s_ - t0) // dt)))
        b1 = max(0, min(nb - 1, int((e_ - t0) // dt)))
        M[w_, b0:b1 + 1] = True
    return M


def k_series(df, t0, t1, dt=HOURS, halfwin=0):
    """Capacity estimate per bucket.

    halfwin = 0 counts the workers that were BUSY in the bucket, which understates
    capacity whenever the queue is empty.  halfwin = h counts the workers that ran
    something within +/- h buckets, which is the better estimate of how many machines
    were up and able to claim.  Never returns 0: a bucket with no worker at all would
    stall the simulator for ever.
    """
    M = busy_matrix(df, t0, t1, dt)
    if halfwin > 0:
        nb = M.shape[1]
        cs = np.cumsum(np.hstack([np.zeros((M.shape[0], 1), np.int64),
                                  M.astype(np.int64)]), axis=1)
        lo = np.maximum(0, np.arange(nb) - halfwin)
        hi = np.minimum(nb, np.arange(nb) + halfwin + 1)
        M = (cs[:, hi] - cs[:, lo]) > 0
    return np.maximum(M.sum(axis=0).astype(np.int64), 1)


def agree(fh, tag, rec, sim):
    """Report how close a simulated wait vector is to the recorded one."""
    q = (50, 90, 99, 99.9)
    rq = np.percentile(rec, q)
    sq = np.percentile(sim, q)
    d = sim - rec
    sp = pd.Series(sim).rank().corr(pd.Series(rec).rank())
    C.log(fh, f"  {tag:46s} mean {sim.mean():8.1f} (rec {rec.mean():8.1f}, "
              f"ratio {sim.mean()/max(rec.mean(),1e-9):5.2f})  "
              + "  ".join(f"p{p:g} {s:8.1f}/{r:8.1f}" for p, s, r in zip(q, sq, rq)))
    C.log(fh, f"  {'':46s} per-job: median|err| {np.median(np.abs(d)):8.1f}  "
              f"Spearman {sp:.4f}  Pearson {np.corrcoef(sim, rec)[0,1]:.4f}  "
              f"frac within 60 s {np.mean(np.abs(d) <= 60):.3f}")
    return dict(tag=tag, mean=float(sim.mean()), p50=float(sq[0]), p90=float(sq[1]),
                p99=float(sq[2]), p999=float(sq[3]),
                med_abs_err=float(np.median(np.abs(d))), spearman=float(sp),
                pearson=float(np.corrcoef(sim, rec)[0, 1]),
                within60=float(np.mean(np.abs(d) <= 60)))


def hourly_corr(fh, t0, sched, rec, sim, nb):
    hb = np.clip(((sched - t0) // HOURS).astype(int), 0, nb - 1)
    a = pd.Series(rec).groupby(hb).mean()
    b = pd.Series(sim).groupby(hb).mean()
    j = pd.concat([a, b], axis=1).dropna()
    r = float(np.corrcoef(j.iloc[:, 0], j.iloc[:, 1])[0, 1])
    rs = float(j.iloc[:, 0].rank().corr(j.iloc[:, 1].rank()))
    C.log(fh, f"      per-hour mean wait over {len(j)} hours: Pearson {r:.4f}, "
              f"Spearman {rs:.4f}")
    return r, rs


def setup_estimate(fh, df):
    """Median gap between consecutive runs on the same worker, short gaps only."""
    d = df.sort_values(["worker", "started"], kind="mergesort")
    gap = (d.started - d.resolved.shift(1))[d.worker == d.worker.shift(1)]
    gap = gap[(gap >= 0) & (gap < 600)]
    med = float(np.median(gap))
    C.log(fh, f"  setup/teardown estimate from {len(gap)} short inter-run gaps: "
              f"median {med:.1f} s, mean {gap.mean():.1f} s, p90 {np.percentile(gap,90):.1f} s")
    return med


def run_pool(fh, pool):
    C.log(fh, f"\n================ {pool} ================")
    df = load(pool)
    w0iso, w1iso, _ = C.window(pool)
    t0, t1 = C.iso_to_epoch(w0iso), C.iso_to_epoch(w1iso)
    n = len(df)
    arrival = df.scheduled.values.astype(np.float64)
    serv = df.service.values.astype(np.float64)
    rec = df.wait.values.astype(np.float64)
    nb = int(np.ceil((t1 - t0) / HOURS))
    ks = k_series(df, t0, t1)                 # workers BUSY in the hour
    ks6 = k_series(df, t0, t1, halfwin=6)     # workers seen within +/- 6 h: capacity
    kmax, kmed = int(ks.max()), int(np.median(ks))
    nwork = df.worker.nunique()
    C.log(fh, f"runs={n}  span={(arrival.max()-arrival.min())/C.DAY:.2f} d  "
              f"total service={serv.sum()/86400:.1f} server-days  "
              f"distinct workers={nwork}")
    C.log(fh, f"k(t) (distinct workers busy per hour): min={ks.min()} "
              f"p10={np.percentile(ks,10):.0f} median={kmed} "
              f"p90={np.percentile(ks,90):.0f} max={kmax}")
    C.log(fh, f"k(t) (workers seen within +/- 6 h, the capacity estimate): "
              f"min={ks6.min()} p10={np.percentile(ks6,10):.0f} "
              f"median={int(np.median(ks6))} p90={np.percentile(ks6,90):.0f} "
              f"max={ks6.max()}  (coefficient of variation "
              f"{ks6.std()/ks6.mean():.3f} -- this is how far from constant k is)")
    C.log(fh, f"recorded wait: mean={rec.mean():.1f} p50={np.percentile(rec,50):.1f} "
              f"p90={np.percentile(rec,90):.1f} p99={np.percentile(rec,99):.1f} "
              f"max={rec.max():.1f}")

    # ---- kernel cross-check: local kernel vs the project's kernel, constant k ----
    kconst = kmax
    kflat = np.full(nb, kconst, np.int64)
    st_local = simulate_kt(arrival, serv, np.arange(n, dtype=np.float64), kflat, t0, HOURS)
    w_local = st_local - arrival
    r = GK.run(arrival, serv, kconst, policy="fcfs")
    dmax = float(np.max(np.abs(w_local - r.w)))
    C.log(fh, f"\n-- kernel cross-check (constant k={kconst}, FCFS) --")
    C.log(fh, f"  local k(t) kernel vs guardkern_snapshot.py: max |difference| = "
              f"{dmax:.9f} s over {n} jobs  -> "
              f"{'AGREE' if dmax < 1e-6 else 'DISAGREE'}")
    if dmax >= 1e-6:
        C.log(fh, "  !! the two kernels disagree; nothing below is trustworthy")

    prio = df.priority.map(PRIO_RANK).fillna(3).values.astype(np.float64)
    C.log(fh, f"  priority mix: "
              + ", ".join(f"{k}={v}" for k, v in df.priority.value_counts().items()))
    key_fcfs = np.arange(n, dtype=np.float64)
    key_prio = prio * 1e9 + np.arange(n, dtype=np.float64)   # exact in float64

    s0 = setup_estimate(fh, df)
    rows = []
    C.log(fh, "\n-- simulated vs RECORDED wait  (sim/rec at each quantile) --")
    variants = []
    for klab, kser in (("k = max busy in any hour = %d" % kmax, kflat),
                       ("k = median busy per hour = %d" % kmed,
                        np.full(nb, kmed, np.int64)),
                       ("k = workers seen in the window = %d" % nwork,
                        np.full(nb, nwork, np.int64)),
                       ("k(t) = workers seen within +/- 6 h", ks6)):
        for dlab, key in (("FCFS", key_fcfs), ("priority-then-FIFO", key_prio)):
            for slab, sv in (("service as recorded", serv),
                             (f"service + {s0:.0f}s setup", serv + s0)):
                variants.append((f"{klab} | {dlab} | {slab}", kser, key, sv))
    for tag, kser, key, sv in variants:
        st = simulate_kt(arrival, sv, key, kser, t0, HOURS)
        w = np.maximum(st - arrival, 0.0)
        d = agree(fh, tag, rec, w)
        pr, sr = hourly_corr(fh, t0, arrival, rec, w, nb)
        d.update(pool=pool, hourly_pearson=pr, hourly_spearman=sr, n=n)
        rows.append(d)

    # ---- what constant capacity would reproduce the recorded waits? ----
    C.log(fh, "\n-- effective capacity: which constant k reproduces the recorded waits --")
    rec_m, rec_9 = rec.mean(), np.percentile(rec, 90)
    best = None
    for k in range(max(2, int(0.5 * nwork)), nwork + 1, max(1, nwork // 24)):
        st = simulate_kt(arrival, serv + s0, key_prio, np.full(nb, k, np.int64), t0, HOURS)
        w = np.maximum(st - arrival, 0.0)
        err = abs(np.log((w.mean() + 1) / (rec_m + 1))) + \
            abs(np.log((np.percentile(w, 90) + 1) / (rec_9 + 1)))
        C.log(fh, f"     k={k:4d}: mean {w.mean():8.1f} (rec {rec_m:8.1f})  "
                  f"p90 {np.percentile(w,90):9.1f} (rec {rec_9:9.1f})  "
                  f"log-error {err:.4f}")
        if best is None or err < best[1]:
            best = (k, err)
    C.log(fh, f"  -> effective k = {best[0]} against {nwork} distinct workers seen and "
              f"{kmax} busy at once; the shortfall is the machines that are up but not "
              f"claiming (reboot, reimage, quarantine, worker restart between tasks)")
    st = simulate_kt(arrival, serv + s0, key_prio, np.full(nb, best[0], np.int64),
                     t0, HOURS)
    w = np.maximum(st - arrival, 0.0)
    d = agree(fh, f"effective k = {best[0]} | priority-then-FIFO | service + setup",
              rec, w)
    pr, sr = hourly_corr(fh, t0, arrival, rec, w, nb)
    d.update(pool=pool, hourly_pearson=pr, hourly_spearman=sr, n=n, k_eff=best[0])
    rows.append(d)
    pd.DataFrame([{"pool": pool, "pool_tag": pool_tag(pool), "k_eff": best[0],
                   "k_max_busy": kmax, "n_workers": nwork, "setup_s": s0,
                   "rec_mean": float(rec.mean()),
                   "rec_p90": float(np.percentile(rec, 90)),
                   "rec_p99": float(np.percentile(rec, 99))}]).to_csv(
        os.path.join(C.HERE, f"keff_{pool_tag(pool)}.csv"), index=False)
    return rows


def main():
    """fci_simval.py [pool-tag ...]  (default: every pool in fci_common.POOLS)"""
    pools = ([C.pool_from_tag(t) for t in sys.argv[1:]] if len(sys.argv) > 1
             else list(C.POOLS))
    out = []
    suffix = "" if len(sys.argv) <= 1 else "_" + "_".join(sys.argv[1:])[:40]
    with open(os.path.join(C.HERE, f"out_simval{suffix}.txt"), "w",
              encoding="utf-8") as fh:
        C.log(fh, "=== simulator validation against the RECORDED waits of a real "
                  "shared non-preemptive queue ===")
        C.log(fh, "windows: " + "; ".join(f"{p} {C.window(p)[0]}..{C.window(p)[1]}"
                                          for p in C.POOLS))
        for pool in pools:
            out.extend(run_pool(fh, pool))
    pd.DataFrame(out).to_csv(os.path.join(C.HERE, f"simval{suffix}.csv"), index=False)
    print(f"wrote out_simval{suffix}.txt")


if __name__ == "__main__":
    main()
