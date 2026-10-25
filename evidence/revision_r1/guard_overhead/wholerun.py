"""Part 1: time whole simulations of overlay 0 with the production kernel.

    python wholerun.py [--reps 5] [--levels 0,1,2] [--out whole_gate.json]

Every repeat runs FCFS, SPJF-E and Guard(300/600/1200) at each load level.  The first
repeat also checks every compared column of main_cells.csv (overlay 0) for exact
equality and records the peak queue length; the timed call is the bare simulate_kernel
call, so the check and the metrics are outside the timing.
"""

from __future__ import annotations

import argparse
import statistics
import time

import common


def run(reps, levels, log=print):
    t_load = time.perf_counter()
    cfg, selection, window, trace, labels, ks = common.load_setup()
    n = len(trace)
    log(f"loaded overlay 0: n = {n:,} jobs, K = {ks}, window = {window} "
        f"({time.perf_counter() - t_load:.1f} s)")
    records, checks = [], []
    fcfs_wait = {}
    for level in levels:
        common.warm_up(trace, common.policy_set(cfg, selection, ks[level]), ks[level], window)
    log("numba warm-up done")
    for rep in range(reps):
        for level in levels:
            k = ks[level]
            ref = common.reference_rows(level) if rep == 0 else None
            for policy in common.policy_set(cfg, selection, k):
                args = common.kernel_args(trace, policy, k, window)
                out, wall_ns, cpu_ns = common.timed_run(args)
                res, extra = common.to_results(policy, k, out)
                rec = {"rep": rep, "level": level, "k": k, "policy": policy.name,
                       "wall_ns": wall_ns, "cpu_ns": cpu_ns, "n_jobs": n,
                       "events": 3 * n, **extra}
                if rep == 0:
                    rec["peak_queue"] = common.peak_queue(trace.arrival_us, res.start_us)
                    if policy.name == "FCFS":
                        fcfs_wait[level] = res.wait_us.copy()
                    summary = common.summarise_run(res, fcfs_wait[level], labels)
                    bad = common.compare(summary, ref[policy.name])
                    checks.append({"level": level, "policy": policy.name,
                                   "match": not bad, "mismatches": bad,
                                   "p99_dl_s": summary.p99_dl_s,
                                   "max_excess_s": summary.max_excess_s})
                    log(f"  check L{level} {policy.name}: {'EXACT' if not bad else bad}")
                records.append(rec)
                log(f"rep {rep} L{level} k={k} {policy.name:12s} wall {wall_ns / 1e9:7.2f} s "
                    f"cpu {cpu_ns / 1e9:7.2f} s  {cpu_ns / (3 * n):6.1f} ns/event "
                    f"rebuilds {extra['n_rebuild']}"
                    + (f" peak queue {rec['peak_queue']:,}" if rep == 0 else ""))
                del out, res, args
    return {"n_jobs": n, "K": ks, "window": window, "records": records, "checks": checks,
            "summary": summarise_records(records)}


def summarise_records(records):
    """Median and spread (min, max) over repeats, per (level, policy)."""
    groups = {}
    for r in records:
        groups.setdefault((r["level"], r["policy"]), []).append(r)
    rows = []
    for (level, policy), rs in sorted(groups.items(),
                                      key=lambda kv: (kv[0][0], common.POLICIES.index(kv[0][1]))):
        row = {"level": level, "k": rs[0]["k"], "policy": policy, "repeats": len(rs)}
        for key in ("cpu_ns", "wall_ns"):
            per_event = [r[key] / r["events"] for r in rs]
            per_job = [r[key] / r["n_jobs"] for r in rs]
            row[f"{key[:-3]}_ns_per_event_median"] = statistics.median(per_event)
            row[f"{key[:-3]}_ns_per_event_min"] = min(per_event)
            row[f"{key[:-3]}_ns_per_event_max"] = max(per_event)
            row[f"{key[:-3]}_ns_per_job_median"] = statistics.median(per_job)
            row[f"{key[:-3]}_s_median"] = statistics.median(r[key] for r in rs) / 1e9
        first = next(r for r in rs if r["rep"] == 0)
        for key in ("peak_queue", "max_span", "n_rebuild", "mean_waiting_at_dispatch",
                    "n_forced", "n_dispatch"):
            row[key] = first.get(key)
        rows.append(row)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--levels", default="0,1,2")
    ap.add_argument("--out", default="whole_gate.json")
    a = ap.parse_args()
    t0 = time.time()
    result = run(a.reps, [int(x) for x in a.levels.split(",")])
    result["machine"] = common.machine_info()
    result["elapsed_s"] = round(time.time() - t0, 1)
    ok = all(c["match"] for c in result["checks"])
    result["gate_exact_reproduction"] = "PASS" if ok else "FAIL"
    common.write_json(common.OUT / a.out, result)
    print(f"gate exact reproduction: {result['gate_exact_reproduction']} "
          f"({sum(c['match'] for c in result['checks'])}/{len(result['checks'])} rows); "
          f"elapsed {result['elapsed_s']} s -> {common.OUT / a.out}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
