"""Data-integrity audit of the collected Firefox CI pool windows.

    uv run --with pandas --with numpy --with pyarrow python fci_audit.py

Nothing downstream may run before this passes.  It checks, per pool:
  * field presence, duplicate (task, run) pairs, timestamp order
  * the window is continuous (runs in every hour) and how the load varies
  * per-worker run overlap (a hardware worker must run one task at a time) and the gap
    between consecutive runs on the same worker (the setup/teardown estimate)
  * the number of distinct workers busy per hour -- our estimate of k and of how far it
    is from constant
  * service = resolved - started, pure queue wait = started - scheduled, dependency
    wait = scheduled - created, and how service sits against the task's own maxRunTime
  * the tail of the cost distribution (share of work in the top 1% / 5%)
"""
import os
import sys

sys.dont_write_bytecode = True

import numpy as np
import pandas as pd

import fci_common as C
from fci_collect import pool_tag

QS = (1, 5, 25, 50, 75, 90, 95, 99, 99.9, 100)


def qline(name, x, unit="s"):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if x.size == 0:
        return f"  {name:26s} (empty)"
    q = np.percentile(x, QS)
    return (f"  {name:26s} n={x.size:7d} mean={x.mean():10.1f} "
            + " ".join(f"p{p:g}={v:.1f}" for p, v in zip(QS, q)) + f"  [{unit}]")


def work_share_top(x, fracs=(0.01, 0.05, 0.10)):
    x = np.sort(np.asarray(x, float))[::-1]
    tot = x.sum()
    return {f: float(x[:max(1, int(round(f * x.size)))].sum() / tot) for f in fracs}


def audit_pool(fh, pool):
    tag = pool_tag(pool)
    p = os.path.join(C.DATA, f"runs_{tag}.parquet")
    df = pd.read_parquet(p)
    C.log(fh, f"\n================ {pool} ================")
    C.log(fh, f"file {p}  rows(runs)={len(df)}  tasks={df.task_id.nunique()}  "
              f"size={os.path.getsize(p)/1e6:.1f} MB")
    w0iso, w1iso, _ = C.window(pool)
    t0, t1 = C.iso_to_epoch(w0iso), C.iso_to_epoch(w1iso)
    C.log(fh, f"window {w0iso} .. {w1iso}  "
              f"({(t1-t0)/C.DAY:.0f} days)")

    # ---- 1. presence & duplicates
    C.log(fh, "\n-- 1. field presence --")
    for c in ("scheduled", "started", "resolved", "worker", "label", "repo",
              "max_run_time", "priority", "deadline", "created"):
        miss = int(df[c].isna().sum())
        C.log(fh, f"  {c:16s} missing {miss:7d} ({miss/len(df)*100:6.3f}%)")
    dup = int(df.duplicated(["task_id", "run_id"]).sum())
    C.log(fh, f"  duplicate (task_id, run_id) rows: {dup}")
    C.log(fh, f"  state x reason_resolved:")
    for (s, r), n in df.groupby(["state", "reason_resolved"], dropna=False).size(
            ).sort_values(ascending=False).items():
        C.log(fh, f"      {str(s):12s} {str(r):26s} {n:8d}  {n/len(df)*100:6.3f}%")
    nrun = df.groupby("task_id").run_id.nunique()
    C.log(fh, f"  tasks with more than one run (retries): "
              f"{int((nrun > 1).sum())} ({(nrun > 1).mean()*100:.3f}% of tasks); "
              f"max runs on a task = {int(nrun.max())}")
    C.log(fh, f"  repositories: " + ", ".join(
        f"{k}={v}" for k, v in df.repo.value_counts(dropna=False).items()))
    C.log(fh, f"  priorities: " + ", ".join(
        f"{k}={v}" for k, v in df.priority.value_counts(dropna=False).items()))
    C.log(fh, f"  tiers: " + ", ".join(
        f"{k}={v}" for k, v in df.tier.value_counts(dropna=False).items()))
    C.log(fh, f"  distinct labels: {df.label.nunique()}   distinct workers: "
              f"{df.worker.nunique()}")

    # ---- 2. only completed runs carry a service time
    done = df[np.isfinite(df.started) & np.isfinite(df.resolved)].copy()
    C.log(fh, f"\n-- 2. runs with both started and resolved: {len(done)} "
              f"({len(done)/len(df)*100:.3f}%) --")
    nostart = df[~np.isfinite(df.started)]
    C.log(fh, f"  runs that never started: {len(nostart)}  "
              f"(states: {dict(nostart.state.value_counts())})")

    done["service"] = done.resolved - done.started
    done["wait"] = done.started - done.scheduled
    done["depwait"] = done.scheduled - done.created
    bad = int((done.service < 0).sum() + (done.wait < -1e-6).sum())
    C.log(fh, f"  negative service or wait: {bad}")
    C.log(fh, f"  scheduled >= created on {np.isfinite(done.depwait).sum()} rows with a "
              f"created time; violations: {int((done.depwait < -1).sum())}")

    C.log(fh, "\n-- 3. the three time components --")
    C.log(fh, qline("service = res - start", done.service))
    C.log(fh, qline("queue wait = start-sched", done.wait))
    C.log(fh, qline("dep wait = sched-created", done.depwait.dropna()))
    C.log(fh, f"  share of runs with queue wait > 60 s: {(done.wait > 60).mean():.4f}; "
              f"> 600 s: {(done.wait > 600).mean():.4f}")
    C.log(fh, f"  mean wait / mean service = "
              f"{done.wait.mean()/done.service.mean():.3f}")

    # ---- 4. maxRunTime
    mrt = done.max_run_time
    C.log(fh, "\n-- 4. per-task limit L (payload.maxRunTime) --")
    C.log(fh, f"  distinct values: "
              f"{sorted(pd.unique(mrt.dropna()))[:20]}")
    C.log(fh, f"  missing on {int(mrt.isna().sum())} runs "
              f"({mrt.isna().mean()*100:.2f}%)")
    ok = np.isfinite(mrt)
    over = (done.service[ok] > mrt[ok] + 60)
    C.log(fh, f"  runs whose service exceeds its own maxRunTime by >60 s: "
              f"{int(over.sum())} ({over.mean()*100:.3f}%)  "
              f"[a timeout kill resolves the run as failed, so a few are expected]")
    C.log(fh, f"  service / maxRunTime: " + qline("", (done.service[ok]/mrt[ok]),
                                                  unit="ratio").strip())
    C.log(fh, f"  deadline - scheduled: "
              + qline("", (done.deadline - done.scheduled), unit="s").strip())

    # ---- 5. continuity and load
    C.log(fh, "\n-- 5. continuity of the window --")
    hr = ((done.scheduled - t0) // 3600).astype(int)
    nb = int(np.ceil((t1 - t0) / 3600))
    cnt = np.bincount(hr[(hr >= 0) & (hr < nb)], minlength=nb)
    C.log(fh, f"  hours in window: {nb}; hours with zero arrivals: {int((cnt==0).sum())}; "
              f"arrivals/hour min={cnt.min()} p10={np.percentile(cnt,10):.0f} "
              f"median={np.median(cnt):.0f} p90={np.percentile(cnt,90):.0f} "
              f"max={cnt.max()}")
    ido = float(cnt.var(ddof=1) / cnt.mean())
    C.log(fh, f"  index of dispersion of hourly arrivals = {ido:.2f} "
              f"(1.0 would be Poisson)")
    day = ((done.scheduled - t0) // C.DAY).astype(int)
    per_day = np.bincount(day[(day >= 0)], minlength=int((t1-t0)//C.DAY))
    C.log(fh, f"  runs per day: {list(per_day)}")

    # ---- 6. k from the workers that are busy
    C.log(fh, "\n-- 6. how many executors (k) --")
    occ = np.zeros(nb + 2)
    busy = [set() for _ in range(nb + 2)]
    st = done.started.values
    rv = done.resolved.values
    wk = pd.factorize(done.worker.values)[0]
    for s_, e_, w_ in zip(st, rv, wk):
        b0 = int((s_ - t0) // 3600)
        b1 = int((e_ - t0) // 3600)
        b0, b1 = max(0, min(nb, b0)), max(0, min(nb, b1))
        for b in range(b0, b1 + 1):
            lo = max(s_, t0 + b * 3600)
            hi = min(e_, t0 + (b + 1) * 3600)
            if hi > lo:
                occ[b] += hi - lo
                busy[b].add(w_)
    nbusy = np.array([len(b) for b in busy[:nb]])
    occ = occ[:nb] / 3600.0
    C.log(fh, f"  distinct workers busy in an hour: min={nbusy.min()} "
              f"p10={np.percentile(nbusy,10):.0f} median={np.median(nbusy):.0f} "
              f"p90={np.percentile(nbusy,90):.0f} max={nbusy.max()}  "
              f"(coefficient of variation {nbusy.std()/nbusy.mean():.3f})")
    C.log(fh, f"  server-equivalents of work per hour (busy time / 3600): "
              f"min={occ.min():.2f} median={np.median(occ):.2f} "
              f"p90={np.percentile(occ,90):.2f} max={occ.max():.2f}")
    C.log(fh, f"  distinct workers over the whole window: {done.worker.nunique()}; "
              f"in the worker list now: see out_collect.txt")
    kd = done.groupby(day).worker.nunique()
    C.log(fh, f"  distinct workers per day: {list(kd.values)}")
    C.log(fh, f"  utilisation against max busy-workers ({nbusy.max()}): "
              f"median hour {np.median(occ)/nbusy.max():.3f}, "
              f"busiest hour {occ.max()/nbusy.max():.3f}")

    # ---- 7. per-worker overlap and inter-run gaps (setup / teardown)
    C.log(fh, "\n-- 7. per-worker timeline --")
    d2 = done.sort_values(["worker", "started"], kind="mergesort")
    g = d2.groupby("worker")
    prev_end = g.resolved.shift(1)
    gap = d2.started - prev_end
    same = d2.worker == d2.worker.shift(1)
    gap = gap[same]
    overlap = int((gap < -1e-6).sum())
    C.log(fh, f"  consecutive runs on the same worker that overlap: {overlap} "
              f"({overlap/max(1,len(gap))*100:.4f}%) -- a hardware worker should run one "
              f"task at a time")
    g2 = gap[gap >= 0]
    C.log(fh, qline("inter-run gap", g2))
    C.log(fh, f"  gaps below 10 min (the setup/teardown candidate): "
              f"{(g2 < 600).mean()*100:.2f}% of gaps, median "
              f"{np.median(g2[g2 < 600]):.1f} s, mean {g2[g2<600].mean():.1f} s")

    # ---- 8. tail of the cost
    C.log(fh, "\n-- 8. tail of the service time --")
    ws = work_share_top(done.service.values)
    C.log(fh, "  share of total work carried by the top: "
              + ", ".join(f"{int(f*100)}% -> {v:.3f}" for f, v in ws.items()))
    C.log(fh, f"  coefficient of variation of service = "
              f"{done.service.std()/done.service.mean():.3f}")
    lab_sz = done.groupby("label").service.agg(["count", "mean"])
    C.log(fh, f"  labels: {len(lab_sz)}; runs per label median "
              f"{lab_sz['count'].median():.0f}; mean service per label ranges "
              f"{lab_sz['mean'].min():.0f} .. {lab_sz['mean'].max():.0f} s")
    return done


def main():
    with open(os.path.join(C.HERE, "out_audit.txt"), "w", encoding="utf-8") as fh:
        C.log(fh, "=== Firefox CI hardware-pool trace: data integrity audit ===")
        for pool in C.POOLS:
            audit_pool(fh, pool)
    print("wrote out_audit.txt")


if __name__ == "__main__":
    main()
