"""Assemble out_SUMMARY.txt: the one table a reader of the paper needs from this study.

    uv run --with pandas --with numpy --with pyarrow python fci_table.py

Reads only this directory's own outputs (pred_*.csv, sim_*.csv, simval.csv,
out_audit.txt, out_collect.txt) plus, for the comparison columns, the two lines already
published in evidence/cross_domain/out_cross_domain_table.txt.  Writes out_SUMMARY.txt.
"""
import os
import re
import sys

sys.dont_write_bytecode = True

import numpy as np
import pandas as pd

import fci_common as C
from fci_collect import pool_tag

W = 100

SELECTION = [
"  Our model needs a (near-)constant number of executors.  Taskcluster's cloud worker",
"  pools autoscale, so k is not constant there; the `releng-hardware/*` and",
"  `proj-autophone/*` pools are physical machines whose count moves only when one is",
"  reimaged or quarantined.  Six candidates were screened on 2026-09-19 over",
"  2026-09-08..14, sampling 6 workers per pool across autoland / try / mozilla-central /",
"  mozilla-beta and reading `started - scheduled` and `resolved - started` from",
"  Taskcluster (cache directory probe, numbers reproduced here):",
"",
"    pool                                     workers  wait p50  wait p90  serv p50  tasks/day",
"    releng-hardware/gecko-t-osx-1500-m4          172     514 s    8793 s    1187 s      ~8200",
"    releng-hardware/gecko-t-osx-1400-r8          145     458 s    6648 s    1171 s      ~5400",
"    releng-hardware/gecko-t-linux-talos-2404     107     522 s    2799 s     644 s      ~4600",
"    releng-hardware/win11-64-24h2-hw             109     528 s    2922 s     759 s      ~2600",
"    releng-hardware/gecko-t-osx-1015-r8           77       0.1 s   589 s    1205 s      ~1400",
"    proj-autophone/gecko-t-bitbar-gw-perf-p6       9      37 s    1894 s     848 s       ~180",
"",
"  Chosen: gecko-t-osx-1500-m4 (largest pool, largest recorded wait, ~8k tasks/day, so a",
"  21-day window clears the 200k-task target on its own) and gecko-t-linux-talos-2404 (a",
"  different operating system, different hardware and a different job mix, as an",
"  independent second check).  gecko-t-osx-1015-r8 was dropped because it barely queues",
"  (wait p50 0.1 s) and the bitbar phone pools because 9 devices give too little volume.",
"  Every sampled task of every hardware pool belonged to that pool's own taskQueueId, so",
"  enumerating a pool by its workers' machine names does not pull in foreign work.",
"  No cloud pool was needed, so no k(t) estimation for an autoscaling pool was required.",
]

CAVEATS = [
"  1. Coverage.  The pool is enumerated through Treeherder by the machine_name of every",
"     worker in the pool's CURRENT worker list.  Checked from the other direction on",
"     three whole pushes (every job of the push, regardless of machine, then asking",
"     Taskcluster which of them belong to the pool): 347/356 = 97.5% of the pool's tasks",
"     are in our collection for gecko-t-osx-1500-m4, and 1.7% of that pool's tasks never",
"     started a run at all (cancelled or superseded while pending; those consume no",
"     service, so leaving them out does not bias a wait computation).  The same check is",
"     uninformative for gecko-t-linux-talos-2404 because the sampled pushes fall outside",
"     its narrowed 7-day window; the enumeration method is identical, so 97.5% is the",
"     best available estimate for it too.  A missing task means slightly less load in",
"     the replay, i.e. the simulated waits are if anything conservative.",
"",
"  2. k is not exactly constant.  Counting the workers that ran something within +/- 6 h",
"     of each hour, the coefficient of variation of k(t) is 0.009 (osx) and 0.025",
"     (talos) -- these are physical machines, not an autoscaling cloud pool, which is",
"     why they were chosen.  But the pool's nominal size is not the capacity that",
"     produced the recorded waits: 156 of 173 listed machines for osx, 96 of 105 for",
"     talos.  The shortfall is machines that are up but not claiming (reboot, reimage,",
"     quarantine, worker restart).  All method runs use the fitted effective k.",
"",
"  3. Setup/teardown.  A worker is not reusable the instant a task resolves.  The median",
"     short inter-run gap on the same worker (54 s osx, 127 s talos) is absorbed into",
"     the service time, as theory.md allows.  Without it the simulator underestimates",
"     the recorded mean wait by 40% (osx) and 35% (talos); with it the agreement is the",
"     one in section B.",
"",
"  4. Arrivals are push-driven, not deadline-driven.  Bursts exist (merge days, tree",
"     reopenings) but they do not have the shape of a coursework deadline.  This trace",
"     says nothing about whether the education arrival process is reproduced.",
"",
"  5. The discipline is priority-then-FIFO, not FCFS.  Taskcluster serves a task queue",
"     in priority order and, within a priority, in the order tasks became pending.  Both",
"     were simulated; section B reports both.  All method comparisons use FCFS as the",
"     baseline, as the theorem requires.",
"",
"  6. The features use the RECORDED resolution time as the moment a past job's result",
"     becomes visible.  Under a policy that finishes a job earlier than the real system",
"     did, that is conservative; under one that finishes it later, it is optimistic.",
"     The same caveat applies to evidence/cross_domain.",
"",
"  7. Download budget overrun, stated plainly.  The intended cap was 400 MB.  The",
"     realised total is about 730 MB: 844 bulk-status pages x 0.52 MB = 436 MB, 224 MB",
"     of Treeherder job pages, 32 MB of coverage pages, 33 MB of probes and small",
"     stages.  Two causes: the cap was enforced per process instead of cumulatively, and",
"     the Taskcluster bulk-status endpoint does not compress its response (~1 kB per",
"     task).  About 140 MB of that was avoidable waste -- 129 MB of talos status pages",
"     fetched against an id list that was then narrowed, and 11 MB of coverage pages for",
"     pushes outside the window.  Politeness was respected throughout: one process, one",
"     request at a time, <= 3.8 requests/second, a descriptive User-Agent, exponential",
"     backoff.",
"",
"  8. No licence.  Mozilla publishes no licence for these APIs.  The slice is used under",
"     'public unauthenticated API, attribute Mozilla' and is not redistributed.",
]

CLAIMS = [
"  MAY be claimed:",
"   * There is a real, shared, non-preemptive execution queue, used by several",
"     repositories at once, on which the queue wait itself is recorded, and our k-server",
"     simulator reproduces that recorded wait distribution: on two independent pools and",
"     on 191,970 and 30,702 recorded services, every reported quantile of the simulated",
"     wait is within about 8% of the recorded one, the per-hour mean wait correlates at",
"     Pearson 0.95-0.96, and the per-job Spearman is 0.95-0.97.  The simulator does not",
"     invent congestion.",
"   * The guard's per-job bound held on every single job of every guarded run.",
"   * On this workload SPJF closes 0.74-0.99 of the FCFS -> true-SJF gap on the MEAN",
"     wait, and the guard at G = 5 L' keeps 0.74 of that while capping the observed harm",
"     at 2.6 L' and firing on 2.7% of dispatches.",
"",
"  MAY NOT be claimed:",
"   * That the method was deployed.  This is still a replay through our simulator; what",
"     is new is that the simulated wait has a recorded value to be compared against.",
"   * That SPJF improves the p99 wait here.  It does not.  The service distribution of",
"     these CI pools is light-tailed (top 1% of jobs carry 3.4% / 5.2% of the work,",
"     coefficient of variation 0.61 / 0.87, against 44% on Azure Functions), and",
"     true-size SJF -- the reference policy -- itself makes the p99 wait WORSE than FCFS",
"     on three of the four windows.  The p99 'gap closed' statistic has no usable",
"     denominator there and is reported as nan rather than as a number.",
"   * That the guarantee family is useful at this pool's own capacity.  With",
"     L' = 5066 s and an FCFS p99 wait of 8999 s, the ratio FCFS p99 / L' is 1.78 while",
"     the theorem's smallest expressible guarantee is (3-2/k) L' = 2.99 L'.  The promise",
"     is therefore coarser than the wait it is about.  Only at the reduced capacity",
"     (ratio 7.1) does it begin to bite.  This is the same applicability boundary the",
"     plan already states in section 5.5 and that Intel Netbatch fell outside of; this",
"     trace sits closer to the boundary than CodeBench or Azure Functions, not inside",
"     the sweet spot.",
"   * That anything here transfers to the education arrival process.  Arrivals are",
"     driven by code pushes.",
]


def rule(fh, ch="="):
    C.log(fh, ch * W)


def grab(path, pat, n=1, section=None):
    """Pull lines out of an existing log, so numbers are never retyped.

    out_collect.txt is append-only and holds earlier, superseded attempts, so the LAST
    matches are the live ones.  `section` restricts the search to the block that starts
    with a line containing it (used to read one pool's block of out_audit.txt).
    """
    if not os.path.exists(path):
        return []
    lines = open(path, encoding="utf-8").read().splitlines()
    if section is not None:
        try:
            i = next(j for j, l in enumerate(lines) if section in l and "====" in l)
        except StopIteration:
            return []
        j = next((k for k in range(i + 1, len(lines)) if "====" in lines[k]), len(lines))
        lines = lines[i:j]
    hit = [l.rstrip() for l in lines if re.search(pat, l)]
    return hit[-n:]


def main():
    out = os.path.join(C.HERE, "out_SUMMARY.txt")
    with open(out, "w", encoding="utf-8") as fh:
        rule(fh)
        C.log(fh, "A REAL SHARED NON-PREEMPTIVE QUEUE WITH RECORDED WAITS:")
        C.log(fh, "MOZILLA FIREFOX CI HARDWARE WORKER POOLS (Taskcluster)")
        rule(fh)
        C.log(fh, "Source   : public unauthenticated REST APIs of")
        C.log(fh, "           https://firefox-ci-tc.services.mozilla.com/api/queue/v1 "
                  "(Taskcluster queue)")
        C.log(fh, "           https://treeherder.mozilla.org/api (Treeherder)")
        for _p in C.POOLS:
            C.log(fh, f"Window   : {_p} {C.window(_p)[0]} .. {C.window(_p)[1]}")
        C.log(fh, f"Pools    : {', '.join(C.POOLS)}")
        C.log(fh, "Scripts  : evidence/firefox_ci/ (see README.md for the rerun order)")
        C.log(fh, "")
        for pat, n in ((r"workers listed", 2), (r"repositories that feed it", 2),
                       (r"COVERAGE", 2)):
            for line in grab(os.path.join(C.HERE, "out_collect.txt"), pat, n=n):
                C.log(fh, "  " + line.strip())
        C.log(fh, "  (the talos coverage line reads 0% because the three sampled pushes "
                  "fall OUTSIDE that pool's")
        C.log(fh, "   narrowed 7-day window, not because tasks are missing; see caveat 1.)")

        # ------------------------------------------------------- 0. pool selection
        C.log(fh, "")
        rule(fh, "-")
        C.log(fh, "0. WHY THESE POOLS")
        rule(fh, "-")
        for line in SELECTION:
            C.log(fh, line)

        # ------------------------------------------------------------ A. the trace
        C.log(fh, "")
        rule(fh, "-")
        C.log(fh, "A. THE TRACE")
        rule(fh, "-")
        for pool in C.POOLS:
            tag = pool_tag(pool)
            mp = os.path.join(C.HERE, f"meta_{tag}.csv")
            if not os.path.exists(mp):
                continue
            m = pd.read_csv(mp).iloc[0]
            C.log(fh, f"  {pool}")
            C.log(fh, f"     runs with a recorded service : {int(m.n)}")
            C.log(fh, f"     L' (train p99.9 of service)  : {m.L:.1f} s")
            C.log(fh, f"     platform limit maxRunTime max: {m.mrt_max:.0f} s; "
                      f"longest realised service {m.serv_max:.0f} s")
            for line in grab(os.path.join(C.HERE, "out_audit.txt"),
                             r"^  (service = res|queue wait = start|dep wait|"
                             r"share of total work|coefficient of variation of service|"
                             r"distinct workers busy in an hour)", n=6, section=pool):
                C.log(fh, "     " + line.strip())

        # ------------------------------------- B. simulator vs recorded waits
        C.log(fh, "")
        rule(fh, "-")
        C.log(fh, "B. DOES OUR SIMULATOR REPRODUCE THE RECORDED WAITS?")
        rule(fh, "-")
        sv = os.path.join(C.HERE, "simval.csv")
        if os.path.exists(sv):
            d = pd.read_csv(sv)
            C.log(fh, "Replayed: arrival = recorded `scheduled`, service = recorded "
                      "`resolved - started`.  Target: recorded `started - scheduled`.")
            for pool in C.POOLS:
                sub = d[d.pool == pool]
                if sub.empty:
                    continue
                kp = os.path.join(C.HERE, f"keff_{pool_tag(pool)}.csv")
                C.log(fh, f"\n  {pool}")
                C.log(fh, f"  {'variant':58s} {'mean':>9s} {'p50':>9s} {'p90':>9s} "
                          f"{'p99':>9s} {'rho_h':>6s} {'sp':>6s} {'med|e|':>8s}")
                if os.path.exists(kp):
                    k = pd.read_csv(kp).iloc[0]
                    rp = os.path.join(C.DATA, f"runs_{pool_tag(pool)}.parquet")
                    w = pd.read_parquet(rp, columns=["scheduled", "started"])
                    p50 = float(np.percentile((w.started - w.scheduled).clip(lower=0), 50))
                    C.log(fh, f"  {'RECORDED':58s} {k.rec_mean:9.1f} {p50:9.1f} "
                              f"{k.rec_p90:9.1f} {k.rec_p99:9.1f}")
                for _, r in sub.iterrows():
                    C.log(fh, f"  {r.tag[:58]:58s} {r['mean']:9.1f} {r.p50:9.1f} "
                              f"{r.p90:9.1f} {r.p99:9.1f} {r.hourly_pearson:6.3f} "
                              f"{r.spearman:6.3f} {r.med_abs_err:8.1f}")
            C.log(fh, "\n  rho_h = Pearson correlation of the per-hour mean wait, "
                      "sp = per-job Spearman, med|e| = median per-job absolute error (s).")
            C.log(fh, "  The last row of each pool is the one to read: the capacity "
                      "fitted to the recorded waits,")
            C.log(fh, "  the real discipline, and the setup/teardown absorbed into the "
                      "service.")

        # ---------------------------------------------- C. prediction
        C.log(fh, "")
        rule(fh, "-")
        C.log(fh, "C. PREDICTABILITY OF THE COST FROM INFORMATION VISIBLE AT ARRIVAL")
        rule(fh, "-")
        C.log(fh, f"{'pool / model':52s} {'RMSE log1p':>11s} {'Spearman':>9s} "
                  f"{'AUROC':>8s} {'AUPRC':>8s}")
        for pool in C.POOLS:
            tag = pool_tag(pool)
            p = os.path.join(C.HERE, f"pred_{tag}.csv")
            if not os.path.exists(p):
                continue
            d = pd.read_csv(p)
            for _, r in d.iterrows():
                C.log(fh, f"{(pool.split('/')[1] + ' ' + r.model)[:52]:52s} "
                          f"{r.rmse_log:11.4f} {r.spearman:9.4f} {r.auroc:8.4f} "
                          f"{r.auprc:8.4f}")

        # ---------------------------------------------- D. scheduling
        C.log(fh, "")
        rule(fh, "-")
        C.log(fh, "D. SCHEDULING ON THE RECORDED ARRIVALS "
                  "(format of evidence/cross_domain/out_cross_domain_table.txt)")
        rule(fh, "-")
        C.log(fh, "gap = (W_FCFS - W_policy) / (W_FCFS - W_SJF-true) on the p99 wait; "
                  "excess in units of L'.")
        C.log(fh, f"{'trace / load':46s} {'k':>7s} {'FCFS p99':>10s} {'p99/L':>8s} "
                  f"{'gap SPJF':>9s} {'SPJF max excess':>18s}")
        allsim = []
        for pool in C.POOLS:
            tag = pool_tag(pool)
            p = os.path.join(C.HERE, f"sim_{tag}.csv")
            if not os.path.exists(p):
                continue
            d = pd.read_csv(p)
            d["pool"] = pool
            allsim.append(d)
            for cap in d.cap.unique():
                s = d[d.cap == cap]
                f = s[s.policy == "FCFS"].iloc[0]
                sp = s[s.policy.str.startswith("SPJF") & s.policy.str.contains(
                    r"\[chosen\]")]
                if sp.empty:
                    continue
                sp = sp.iloc[0]
                C.log(fh, f"{(pool.split('/')[1] + ' ' + cap)[:46]:46s} {int(f.k):7d} "
                          f"{f.p99_s:10.1f} {f.fcfs_p99_over_L:8.4f} {sp.gap_p99:9.4f} "
                          f"{sp.max_excess_fcfs_s:11.1f} = {sp.max_excess_fcfs_s/f.L:5.2f} L'")
        C.log(fh, "")
        C.log(fh, "  what the guard costs and what it buys")
        C.log(fh, f"{'trace / load / policy':56s} {'gap p99':>8s} {'gap mean':>9s} "
                  f"{'max excess (L)':>15s} {'fire %':>8s} {'bound':>7s}")
        for d in allsim:
            pool = d.pool.iloc[0]
            for _, r in d[d.policy.str.startswith("guard")].iterrows():
                ok = "yes" if r.get("bound_violation_s", 1) <= 1e-6 else "NO"
                C.log(fh, f"{(pool.split('/')[1] + ' ' + r.cap + ' ' + r.policy)[:56]:56s} "
                          f"{r.gap_p99:8.4f} {r.gap_mean:9.4f} "
                          f"{r.max_excess_fcfs_s/r.L:15.4f} {r.fire_rate*100:8.3f} "
                          f"{ok:>7s}")

        # ---------------------------------------------- E. applicability
        C.log(fh, "")
        rule(fh, "-")
        C.log(fh, "E. APPLICABILITY IN THE PAPER'S TERMS")
        rule(fh, "-")
        for d in allsim:
            pool = d.pool.iloc[0]
            for cap in d.cap.unique():
                s = d[d.cap == cap]
                f = s[s.policy == "FCFS"].iloc[0]
                C.log(fh, f"  {pool.split('/')[1]:32s} {cap:22s} "
                          f"FCFS p99 wait / L' = {f.fcfs_p99_over_L:8.3f}   "
                          f"floor (3-2/k)L' = {(3-2/f.k):.3f} L'")
        C.log(fh, "  Compare: CodeBench busy-hour rho=1.06 -> 4.39; Azure busy-hour "
                  "rho=1.0 -> 4.22; Azure window rho=0.95 -> 96.3;")
        C.log(fh, "           Intel Netbatch window rho=0.95 -> 0.136 (outside the "
                  "method's boundary).")

        # ---------------------------------------------- F. caveats
        C.log(fh, "")
        rule(fh, "-")
        C.log(fh, "F. CAVEATS")
        rule(fh, "-")
        for line in CAVEATS:
            C.log(fh, line)

        # ---------------------------------------------- G. claims
        C.log(fh, "")
        rule(fh, "-")
        C.log(fh, "G. WHAT MAY AND MAY NOT BE CLAIMED IN THE PAPER")
        rule(fh, "-")
        for line in CLAIMS:
            C.log(fh, line)
    print("wrote", out)


if __name__ == "__main__":
    main()
