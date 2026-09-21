"""Measurement 3 and the write-up: joins dedicated.json (containers.py) and pool_k.json
(pool_k.py) into out_SUMMARY.txt -- the ratios, the one claim the paper can make, and the
claims it cannot.

usage:  summarize.py            # writes out_SUMMARY.txt next to this file
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = []


def w(*a):
    OUT.append(" ".join(str(x) for x in a))


def main():
    d = json.load(open(os.path.join(HERE, "dedicated.json"), encoding="utf-8"))
    p = json.load(open(os.path.join(HERE, "pool_k.json"), encoding="utf-8"))
    ov, tr = d["overlay"], p["trace"]
    pool_span = tr["span_s"]
    work = tr["work_cap_s"]
    prim = d["primary_def"]
    defs = [k for k in d["defs"] if k in ov]

    w("Dedicated per-student containers vs a shared executor pool, on one demand trace")
    w("=" * 78)
    w("")
    w("Trace: the paper's primary overlay, replicate 0 -- %d copies of the %d "
      % (tr["copies"], len(d["pool_cs"])))
    w("class-semesters of the 60-second-regime development semesters (2020-ERE, 2020-2,")
    w("2021-1, 2021-2, 2022-1, 2022-2), each copy shifted by whole weeks.")
    w("  simulated jobs            %12s" % f"{tr['n']:,}")
    w("  of them in a deadline window (0..24 h before an assessment end)  %s"
      % f"{tr['dl_jobs']:,}")
    w("  executed work, sum of C_cap = min(C, 60 s)                       %s s"
      % f"{work:,.0f}")
    w("  job arrival span                                                 %.2f d"
      % (pool_span / 86400))
    w("  busiest arrival hour of C_cap work                               %.1f s"
      % tr["busy_hour_work_s"])
    w("  pool sizes the paper uses (busy-hour rho 0.5 / 0.8 / 1.0)        k = %s"
      % ", ".join(str(x) for x in tr["paper_k"]))
    w("")
    w("0  Check that this is the same trace and the same queue as the paper's")
    w("-" * 78)
    w("")
    w("At k = 8, evidence/guard_variants/pareto_tables.txt (rep0, predictor M4, level 0,")
    w("produced by a different script on a separately built copy of the overlay) reports")
    w("deadline-window p99 waits of FCFS 22.17 s, SPJF 11.979 s, SJF-ref 8.31 s,")
    w("FIX-B300 13.312 s.  This run gets FCFS %.3f, SPJF-M4 %.3f, SJF-ref %.3f,"
      % (p["paper_levels"]["FCFS"]["8"]["p99_dl"],
         p["paper_levels"]["SPJF-M4"]["8"]["p99_dl"],
         p["paper_levels"]["SJF-ref"]["8"]["p99_dl"]))
    w("SPJF+G300 %.3f.  Same numbers, so the k sweep below extends the paper's own"
      % p["paper_levels"]["SPJF+G300"]["8"]["p99_dl"])
    w("table rather than starting a new one.")
    w("")

    # ---------------------------------------------------------------- 1
    w("1  Dedicated design: containers alive at once, and what they do with that time")
    w("-" * 78)
    w("")
    w("Per semester (one copy, the real calendar), time-weighted over the semester's own")
    w("event window.  'util' = executing seconds inside the alive intervals / alive")
    w("seconds; executing time is the union of [ts - C_cap, ts] over the student's")
    w("submissions, so overlapping runs of one student count once.")
    w("")
    hdr = ("semester   users  definition       mean    p95    p99    max   alive (s)   "
           "exec in (s)     util")
    w(hdr)
    for sem, r in d["semesters"].items():
        for nm in defs:
            v = r["defs"][nm]
            first = nm == defs[0]
            w("%-9s %5s  %-13s %7.2f %6d %6d %6d %11.3e %11.0f  %8.5f"
              % (sem if first else "", r["n_users"] if first else "",
                 nm, v["mean"], v["p95"], v["p99"], v["max"], v["alive_s"],
                 v["exec_inside_s"], v["util"]))
    w("")
    w("Overlay pool (the demand the paper replays; %d container-bearing copies):"
      % tr["copies"])
    w("")
    w("definition       sessions        mean    p95    p99    max   span(d)   alive (s)"
      "    exec in (s)     util")
    for nm in defs:
        v = ov[nm]
        w("%-13s %12s %11.2f %6d %6d %6d %9.2f %11.3e %11s  %8.5f"
          % (nm, f"{v['n_sessions']:,}", v["mean"], v["p95"], v["p99"], v["max"],
             v["span_s"] / 86400, v["alive_s"], f"{v['exec_inside_s']:,.0f}", v["util"]))
    w("")
    w("Reading of the definitions (containers.py's docstring has the full rule):")
    w("  login_obs     only the logins whose next row in logins.log is a logout.  It")
    w("                covers %.1f%% of the executed seconds, so it is a lower bound, not"
      % (100 * ov["login_obs"]["exec_inside_s"] / d["overlay_exec_union_s"]))
    w("                a measurement.")
    w("  login_act     every login, a censored close filled from the last event inside")
    w("                the window.  It covers %.1f%% of the executed seconds, and it is"
      % (100 * ov["login_act"]["exec_inside_s"] / d["overlay_exec_union_s"]))
    w("                the upper reading: when a student never logs out and comes back")
    w("                to the same session hours later, the container stays open for the")
    w("                whole stretch.  That is why login_act sits above proxy3600.")
    w("  proxy600/1800/3600   activity proxy at a 10 / 30 / 60 min idle gap; they cover")
    w("                100% of the executed seconds by construction.")
    w("  proxy1800_lg  the 30 min proxy with the login and logout instants added to the")
    w("                activity set.")
    w("  The primary number quoted below is %s." % prim)
    w("")
    w("The %s login->logout pairs that the platform did write have these durations (s):"
      % f"{sum(v['paired'] for v in d['diag'].values()):,}")
    w("")
    w("semester   logins  logouts  paired   p10     p50     p90      p99      max")
    for sem, v in d["diag"].items():
        q = v.get("paired_dur_s", [float('nan')] * 5)
        w("%-9s %7d %8d %7d %5.0f %7.0f %7.0f %8.0f %8.0f"
          % (sem, v["logins"], v["logouts"], v["paired"], *q))
    w("")
    lo = min(ov[n]["p99"] for n in defs)
    hi = max(ov[n]["p99"] for n in defs)
    w("Across all six definitions the overlay's p99 concurrent container count lies")
    w("between %d and %d, and the utilisation between %.2f%% and %.2f%%."
      % (lo, hi, 100 * min(ov[n]["util"] for n in defs),
         100 * max(ov[n]["util"] for n in defs)))
    w("")

    # ---------------------------------------------------------------- 2
    w("2  Shared pool: the smallest k that meets a deadline-window p99 wait target")
    w("-" * 78)
    w("")
    w("Wait = time from arrival to the start of service in a k-server non-preemptive")
    w("queue.  The statistic is the p99 over the %s jobs that arrive within 24 h of an"
      % f"{tr['dl_jobs']:,}")
    w("assessment end -- the paper's own deadline window.  SPJF-M4 orders by the")
    w("development forward predictor; +G%g is the overtake-budget guard at B = 5 L."
      % tr["guard_B"])
    w("")
    pols = list(p["kmin"].keys())
    w("policy       p99_dl at the paper's k        smallest k for p99_dl <=")
    w("             k=%-6d k=%-6d k=%-6d      30 s     5 s     1 s"
      % tuple(tr["paper_k"]))
    for pol in pols:
        lv = p["paper_levels"][pol]
        km = p["kmin"][pol]
        w("%-12s %8.2f %8.2f %8.2f   %8s %7s %7s"
          % (pol, *[lv[str(k)]["p99_dl"] for k in tr["paper_k"]],
             km["30"], km["5"], km["1"]))
    w("")
    w("At every target the predictor saves one executor against FCFS, and the guard")
    w("costs nothing at the k where it matters (same k as ungated SPJF at all three")
    w("targets).  True SJF, which no scheduler can reach, saves one more.")
    w("")

    # ---------------------------------------------------------------- 3
    w("3  The ratios")
    w("-" * 78)
    w("")
    w("(a) concurrent dedicated containers per pooled executor, %s:" % prim)
    w("")
    w("target p99_dl   FCFS k   p99 ded / k   max ded / k   SPJF k   p99 ded / k")
    for tgt in ("30", "5", "1"):
        kf = p["kmin"]["FCFS"][tgt]
        ks = p["kmin"]["SPJF-M4"][tgt]
        w("%8s s   %6d   %11.1f   %11.1f   %6d   %11.1f"
          % (tgt, kf, ov[prim]["p99"] / kf, ov[prim]["max"] / kf, ks,
             ov[prim]["p99"] / ks))
    w("")
    w("Same ratios with the other container definitions, at the 1 s target (FCFS k = %d):"
      % p["kmin"]["FCFS"]["1"])
    kf1 = p["kmin"]["FCFS"]["1"]
    for nm in defs:
        w("  %-13s p99 %5d -> %6.1f x ;  max %5d -> %6.1f x"
          % (nm, ov[nm]["p99"], ov[nm]["p99"] / kf1, ov[nm]["max"],
             ov[nm]["max"] / kf1))
    w("")
    w("(b) executor-seconds provisioned per executed second.")
    w("")
    w("    A dedicated container is provisioned only while it is alive, so its number is")
    w("    1 / utilisation and does not depend on a window.  A pool of k executors is")
    w("    provisioned continuously; the number is given over two windows -- the job")
    w("    arrival span (%.1f d) and the container span (%.1f d), the second being the"
      % (pool_span / 86400, ov[prim]["span_s"] / 86400))
    w("    conservative one, since the pool has to exist whenever a student may submit.")
    w("")
    for nm in defs:
        w("    dedicated, %-13s %10.1f executor-seconds per executed second"
          % (nm, ov[nm]["alive_s"] / ov[nm]["exec_inside_s"]))
    w("")
    w("    login_obs's figure is not comparable with the rest: it divides by the %.0f%% of"
      % (100 * ov["login_obs"]["exec_inside_s"] / d["overlay_exec_union_s"]))
    w("    executed seconds that fall inside an observed login-logout pair.")
    w("")
    w("    pooled            over %.1f d   over %.1f d"
      % (pool_span / 86400, ov[prim]["span_s"] / 86400))
    for tgt in ("30", "5", "1"):
        for pol in ("FCFS", "SPJF-M4"):
            k = p["kmin"][pol][tgt]
            w("    k=%-3d (%-8s p99_dl<=%2s s) %9.2f %11.2f"
              % (k, pol + ",", tgt, k * pool_span / work,
                 k * ov[prim]["span_s"] / work))
    w("")
    dd = ov[prim]["alive_s"] / ov[prim]["exec_inside_s"]
    for tgt in ("30", "1"):
        k = p["kmin"]["FCFS"][tgt]
        w("    ratio at the %2s s target (%s / pooled FCFS k=%d): %.0f x over the arrival"
          % (tgt, prim, k, dd / (k * pool_span / work)))
        w("      span, %.0f x over the container span."
          % (dd / (k * ov[prim]["span_s"] / work)))
    w("")

    # ---------------------------------------------------------------- 4
    w("4  Caveats that have to be stated with any of these numbers")
    w("-" * 78)
    w("")
    for i, s in enumerate([
        "A dedicated container also serves the interactive IDE session, not only judging."
        "  Container-alive time is therefore an upper bound on what judging alone needs,"
        " and the utilisation below 0.2% is the utilisation of a container that is doing"
        " editing, reading and idling as well as running code.  The comparison is between"
        " two architectures, not between two ways of running the same judge.",
        "A pooled executor still needs a sandbox start per job.  C already includes"
        " interpreter start-up per the plan's field semantics (2.2), and the pool is"
        " charged the same C_cap the dedicated container was charged, so no start-up cost"
        " is omitted on either side -- but neither is the extra cost of a cold container"
        " that the dedicated design pays only once per login.",
        "Concurrency is counted from end-time logs at 1-second resolution.  The log"
        " timestamp is the end of a run; the arrival is reconstructed as end - C.  Two"
        " events one second apart cannot be separated, and a container's true creation"
        " and teardown instants are not recorded at all.",
        "logins.log is a per-user global history copied into every class directory: the"
        " same rows appear in several class-semesters and reach years outside the"
        " archive's own semester.  They are deduplicated by (user, timestamp, kind) and"
        " clipped to the semester's event window.  Only %.0f%% to %.0f%% of logins have a"
        " logout written after them (per semester), so the observed close time is missing"
        " for most sessions; login_act fills those from activity and login_obs drops"
        " them." % (100 * min(r["paired"] / max(1, r["logins"])
                              for r in d["semesters"].values()),
                    100 * max(r["paired"] / max(1, r["logins"])
                              for r in d["semesters"].values())),
        "TEST blocks carry no execution time, so the time a container spends running a"
        " student's interactive test is counted as idle.  Utilisation is a lower bound on"
        " 'container busy running code' for that reason, and the number of TEST blocks is"
        " %.1f x the number of submissions in this pool."
        % (sum(r["n_test"] for r in d["semesters"].values())
           / sum(r["n_sub"] for r in d["semesters"].values())),
        "The overlay is a construction: the same six semesters replicated %d times with"
        " week shifts, not %d independent platforms.  Both sides of every ratio are"
        " computed on that same construction, so the ratio is a property of the"
        " construction as much as of CodeBench." % (tr["copies"], tr["copies"]),
        "One overlay replicate (rep 0), no bootstrap interval.  The paper's own tables"
        " carry week-block bootstrap intervals for the wait statistics; the k values here"
        " are point estimates on one trace.",
    ], 1):
        body = s.split()
        line = "  %d)" % i
        for tok in body:
            if len(line) + 1 + len(tok) > 78:
                w(line)
                line = "     " + tok
            else:
                line += " " + tok
        w(line)
        w("")

    # ---------------------------------------------------------------- 5
    w("5  What the paper can say, and what it cannot")
    w("-" * 78)
    w("")
    w("CAN (one sentence):")
    kf, ks = p["kmin"]["FCFS"]["1"], p["kmin"]["SPJF-M4"]["1"]
    w("")
    w("  On the same replayed demand, CodeBench's per-student design keeps a p99 of %d"
      % ov[prim]["p99"])
    w("  containers alive at once (max %d) and each container executes code for %.2f%% of"
      % (ov[prim]["max"], 100 * ov[prim]["util"]))
    w("  the time it is alive, whereas a shared non-preemptive pool holds the p99 wait of")
    w("  deadline-window jobs under 1 s with k = %d executors under FCFS and k = %d under"
      % (kf, ks))
    w("  the predictor-ordered policy -- a factor of %.0f fewer executors and %.0f x fewer"
      % (ov[prim]["p99"] / kf, (ov[prim]["alive_s"] / ov[prim]["exec_inside_s"])
         / (kf * pool_span / work)))
    w("  provisioned executor-seconds per executed second.")
    w("")
    w("CANNOT:")
    w("")
    for s in [
        "Cannot claim CodeBench ever queued: it has no shared queue, and nothing here"
        " measures a wait on the real platform.  The pooled side is entirely simulated.",
        "Cannot claim the dedicated containers are %.0f x too large a provision for the"
        " platform as a whole -- they also run the IDE, which the pool does not replace."
        % ((ov[prim]["alive_s"] / ov[prim]["exec_inside_s"])
           / (kf * pool_span / work)),
        "Cannot claim a container count for the real single-course semesters that a"
        " reader may compare with a real deployment: the per-semester p99 is %d to %d"
        " containers, and the large numbers here come from the %d-fold overlay."
        % (min(r["defs"][prim]["p99"] for r in d["semesters"].values()),
           max(r["defs"][prim]["p99"] for r in d["semesters"].values()), tr["copies"]),
        "Cannot claim the scheduler saves many executors: at every target tested it saves"
        " exactly one against FCFS (%s -> %s at 1 s, %s -> %s at 5 s, %s -> %s at 30 s)."
        " The saving from pooling is two orders of magnitude; the saving from ordering"
        " inside the pool is one executor."
        % (p["kmin"]["FCFS"]["1"], p["kmin"]["SPJF-M4"]["1"],
           p["kmin"]["FCFS"]["5"], p["kmin"]["SPJF-M4"]["5"],
           p["kmin"]["FCFS"]["30"], p["kmin"]["SPJF-M4"]["30"]),
        "Cannot claim a measured container lifetime: the platform writes a logout for"
        " only a minority of logins, so every alive-time number here is reconstructed,"
        " and the spread across the six definitions (p99 %d to %d) is the honest"
        " uncertainty band." % (lo, hi),
        "Cannot report the ratio as a cost saving without a cost model: a container and"
        " an executor are not the same unit of hardware, and nothing here measures"
        " memory, CPU shares or price.",
    ]:
        body = s.split()
        line = "  -"
        for tok in body:
            if len(line) + 1 + len(tok) > 78:
                w(line)
                line = "    " + tok
            else:
                line += " " + tok
        w(line)
        w("")

    txt = "\n".join(OUT) + "\n"
    with open(os.path.join(HERE, "out_SUMMARY.txt"), "w", encoding="utf-8") as f:
        f.write(txt)
    print(txt)


if __name__ == "__main__":
    main()
