"""Final stage: assemble out_main_v3.txt and the CSV behind every table in it.

Refusal rule.  Every stage writes, at the head of each invocation, a line
    ## <time> manifest=<hash> argv=...
where <hash> is one sha256 over (name, content) of every mv3_*.py except this file.  This
script recomputes that hash and REFUSES to write a report if any stage log carries a
different one, i.e. if any number in the report was produced by code that has since
changed.  Its own hash is printed in the header.

usage: mv3_report.py [--allow-stale]   (--allow-stale only lists what is stale and exits)
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import time

import numpy as np
import pandas as pd

import mv3_common as C

OUT = os.path.join(C.HERE, "out_main_v3.txt")
ADV = ("reversed", "random", "top1short")


def stale(cur):
    bad = []
    for p in sorted(glob.glob(os.path.join(C.HERE, "out_*.txt"))):
        if os.path.basename(p) in ("out_main_v3.txt", "out_report.txt"):
            continue
        seen = set(re.findall(r"^## .*manifest=([0-9a-f]{64})", open(p, encoding="utf-8")
                              .read(), re.M))
        for h in seen:
            if h != cur:
                bad.append((os.path.basename(p), h))
    return bad


def cell(v, lo, hi, d=3):
    return f"{v:.{d}f} [{lo:.{d}f},{hi:.{d}f}]"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--allow-stale", action="store_true")
    a = ap.parse_args()
    cur, tab = C.manifest()
    bad = stale(cur)
    if bad:
        print(f"REFUSING to report: current manifest {cur}")
        for f, h in sorted(set(bad)):
            print(f"  stale stage log {f} ran under manifest {h}")
        print("rerun those stages on the final scripts, then report again.")
        raise SystemExit(1)
    if a.allow_stale:
        print("no stale stage logs")
        return

    G = pd.read_csv(os.path.join(C.HERE, "gain_primary.csv"))
    T = pd.read_csv(os.path.join(C.HERE, "table_main_primary.csv"))
    D = pd.read_csv(os.path.join(C.HERE, "gaindiff_primary.csv"))
    TR = pd.read_csv(os.path.join(C.HERE, "trace_summary.csv"))
    SEL = pd.read_csv(os.path.join(C.HERE, "selected_params.csv"))
    SG = pd.read_csv(os.path.join(C.HERE, "select_grid.csv"))
    K1 = pd.read_csv(os.path.join(C.HERE, "table_main_k1.csv"))
    L = []

    def w(*x):
        s = " ".join(str(y) for y in x)
        L.append(s)
        print(s, flush=True)

    w("=" * 100)
    w("CONSOLIDATED MAIN EXPERIMENT (v3) -- CodeBench DEV data")
    w("Tweedie ranking score + capped relative overtake-budget guard + the k-server "
      "per-job bound")
    w("=" * 100)
    w(f"written {time.strftime('%Y-%m-%d %H:%M:%S')}")
    w(f"manifest of the scripts that produced every number below: {cur}")
    for f, h in tab:
        w(f"    {f:20s} {h}")
    w(f"    {'mv3_report.py':20s} {C.sha256_file(os.path.join(C.HERE, 'mv3_report.py'))}"
      f"   (formats only; not part of the manifest)")
    w("every stage log in this directory carries this manifest; the report is refused "
      "otherwise.")
    w("")
    w("DATA.  CodeBench, development semesters only.  2023-1, 2023-2 and 2024-1 were not "
      "opened at any point of this experiment.  No student source code and no personal "
      "attribute is read: the features are the pipeline's M4 set.")
    w("")

    w("-" * 100)
    w("1. TRACES")
    w("-" * 100)
    w("All traces come from evidence/codebench_service_v2 (config ires0: leak-free "
      "features on the jittered clock, rolling-origin forward models), imported read-only.")
    w(TR.to_string(index=False))
    w("")
    t222 = TR[TR.trace == "t222"]
    if len(t222):
        w("2022-2-ONLY TRACE: " + str(t222.iloc[0]["scores"]) +
          f". The pipeline's own copy probe needs {int(t222.iloc[0]['copies'])} copies of "
          f"the {int(t222.iloc[0]['class_semesters'])} class-semesters of 2022-2 before the "
          f"busiest hour can be loaded at k >= 4 with three distinct k. Stacking one "
          f"semester's eight course calendars that many times piles every deadline on the "
          f"same weekday and hour, which is not the primary trace's load shape, so it is "
          f"NOT reported as a held-out result. See copies_probe_t222.csv.")
    w("")

    w("-" * 100)
    w("2. GUARD PARAMETERS, AND HOW THEY WERE CHOSEN")
    w("-" * 100)
    w("Knob: G = guaranteed maximum excess over FCFS, per job.  Bmax = k*(G - (3-2/k)L) "
      "with L = 60 s, so Theorem A at B = Bmax gives W_guard[i] <= W_FCFS[i] + G.")
    w("Budget of a waiting job q: min(B0 + eta*k*(t - a_q), Bmax); the dispatcher serves "
      "the SMALLEST-RANK job whose budget is spent, else the smallest predicted cost.")
    w("Chosen on the VALIDATION trace only (pool = the 60 s-regime DEV semesters minus "
      "2022-2, 32 class-semesters, 49 copies, k = 7/5/4).  No number on any trace "
      "containing 2022-2 entered the choice.")
    w("Rule: among B0 in {30,120,600} x k/4 and eta in {0,0.25,0.5,0.75,0.9}, keep the "
      "configurations whose observed harm (max excess over FCFS among jobs FCFS would "
      "start within 1 s) is <= G/2 at EVERY level, and take the one with the largest "
      "deadline-window p99 gap closed in the WORST level.")
    w(SEL.to_string(index=False))
    w("")
    w("At equal G the fixed-budget guard (eta = 0, B0 = Bmax) is the baseline.  On the "
      "validation trace it is infeasible at all three G under the harm constraint: it "
      "buys about the same gap while hurting jobs that would not have waited 1.8-2.2 "
      "times as much.  Full grid in select_grid.csv.")
    w("")

    w("-" * 100)
    w("3. MAIN RESULTS -- primary trace, 5 overlays, pure scheduling")
    w("-" * 100)
    w("Primary metric: p99 of the wait among jobs arriving in the 24 h before their own "
      "deadline.  gap = fraction of the FCFS -> true-size-SJF gap closed; red% = plain "
      "percentage reduction of the metric against FCFS.  THESE ARE DIFFERENT NUMBERS.")
    w("[95% CI] = 2,000-resample week-block paired bootstrap over the 30 whole weeks of "
      "the overlay timeline, the same draws for every policy.  The interval covers time "
      "only, not the sampling of semesters into the pool; the five overlays are one "
      "construction, not five independent platforms.")
    rows = []
    for lev in sorted(T.level.unique()):
        s = T[T.level == lev]
        for _, r in s.iterrows():
            if r.policy.split("-")[-1] in ADV:
                continue
            rows.append(dict(level=lev, rho_target=r.rho_target, k=r.k, policy=r.policy,
                             p99_dl_s=round(r.p99_dl_s, 2),
                             gap_closed=cell(r.gap_closed, r.gap_lo, r.gap_hi),
                             red_pct=cell(r.red_pct, r.red_lo, r.red_hi, 1),
                             mean_s=round(r.mean_s, 3),
                             mean_gap=cell(r.mean_gap, r.mean_gap_lo, r.mean_gap_hi),
                             p99_all_s=round(r.p99_all_s, 2),
                             max_excess_s=round(r.max_excess_s, 1),
                             harm_s=round(r.harm_wf1s_s, 1),
                             max_heavy_s=round(r.max_heavy_s, 1),
                             qw_fired=round(r.qw_fired, 4)))
    M = pd.DataFrame(rows)
    M.to_csv(os.path.join(C.HERE, "report_main.csv"), index=False)
    for lev in sorted(M.level.unique()):
        s = M[M.level == lev]
        w(f"\n--- level {lev}: target busy-hour rho {s.rho_target.iloc[0]}, k = "
          f"{int(s.k.iloc[0])} ---")
        w(s.drop(columns=["level", "rho_target", "k"]).to_string(index=False))
    w("")
    w("max_excess / harm / max_heavy are the worst over the five overlays; the rest are "
      "means over them.  harm = max excess over FCFS among jobs FCFS would start within "
      "1 s.  qw_fired = queue-weighted share of dispatches the guard forced.")
    w("")

    w("-" * 100)
    w("4. DIFFERENCES (paired week-block bootstrap; resolved = the 95% CI excludes 0)")
    w("-" * 100)
    d = D[(D.metric == "p99dl") & (D.quantity == "gain")].copy()
    d["d_gap"] = [cell(v, l, h) for v, l, h in zip(d["diff"], d.lo, d.hi)]
    dd = d[["level", "pair", "label", "d_gap", "resolved", "verdict"]]
    dd.to_csv(os.path.join(C.HERE, "report_diff.csv"), index=False)
    w(dd.to_string(index=False))
    w("")

    w("-" * 100)
    w("5. ADVERSARIAL PREDICTORS")
    w("-" * 100)
    w("reversed = predicted cost is minus the true cost; random = the true costs shuffled "
      "over the jobs; top1short = the Tweedie score with the truly longest 1% of jobs "
      f"forced to the front.  Guarded runs use the selected guard at G = {C.ADV_G:g} s.")
    ar = T[[p.split("-")[-1] in ADV for p in T.policy]].copy()
    ar = ar[["level", "rho_target", "k", "policy", "p99_dl_s", "gap_closed", "red_pct",
             "mean_s", "max_excess_s", "harm_wf1s_s", "max_heavy_s", "guar_excess_s",
             "used_over_allowed", "qw_fired"]].round(3)
    ar.to_csv(os.path.join(C.HERE, "report_adversarial.csv"), index=False)
    w(ar.to_string(index=False))
    w("")
    w("The guarantee is per job, not per quantile: a guarded run may still have a worse "
      "p99 than FCFS, by at most G.  What the guard removes is the unbounded tail: the "
      "worst single job.")
    w("")

    w("-" * 100)
    w("6. SINGLE-SERVER CONFIGURATION (k = 1, busy-hour rho ~ 0.80)")
    w("-" * 100)
    k1 = K1[["policy", "score", "G", "B0", "eta", "Bmax", "Ncap", "p99_dl_s", "gap_closed",
             "gap_lo", "gap_hi", "red_pct", "mean_s", "max_excess_s", "harm_wf1s_s",
             "max_heavy_s", "guar_excess_s", "used_over_allowed", "qw_fired"]].round(4)
    k1.to_csv(os.path.join(C.HERE, "report_k1.csv"), index=False)
    w(k1.to_string(index=False))
    w("At k = 1 the bound is W_guard[i] <= W_FCFS[i] + Bmax + L, i.e. the same G.")
    w("")

    w("-" * 100)
    w("7. THE PER-JOB THEOREM, ASSERTED ON EVERY JOB OF EVERY GUARDED RUN")
    w("-" * 100)
    w("For k identical non-preemptive work-conserving servers with service <= L = 60 s,")
    w("    W_guard[i] <= W_FCFS[i] + Bmax/k + (3 - 2/k) L                         (Thm A)")
    w("    W_guard[i] <= (W_FCFS[i] + B0/k + (3 - 2/k) L) / (1 - eta)             (Thm B)")
    w("and the guard's bound is the smaller of the two.  Every guarded run compares every "
      "job's wait with its own bound.")
    b = pd.concat([T.assign(trace="primary"), K1.assign(trace="k1")], ignore_index=True)
    b = b[b.G > 0][["trace", "level", "k", "policy", "G", "B0", "eta", "Bmax", "Ncap",
                    "guar_excess_s", "max_excess_s", "used_over_allowed"]].round(4)
    b.to_csv(os.path.join(C.HERE, "report_bound.csv"), index=False)
    w(b.to_string(index=False))
    vt = pd.concat([pd.read_csv(f) for f in
                    sorted(glob.glob(os.path.join(C.SIMDIR, "*_main.csv")))],
                   ignore_index=True)
    gv = vt[vt.bound_viol >= 0]
    w(f"\nguarded runs checked: {len(gv)} (trace x overlay x level x policy), "
      f"{int(gv.n_jobs.sum()):,} per-job bound checks, violations: "
      f"{int(gv.bound_viol.sum())}")
    w(f"worst used/allowed ratio anywhere: {b.used_over_allowed.max():.4f} "
      f"(policy {b.loc[b.used_over_allowed.idxmax(), 'policy']}, "
      f"trace {b.loc[b.used_over_allowed.idxmax(), 'trace']}, "
      f"k = {b.loc[b.used_over_allowed.idxmax(), 'k']:.0f})")
    w("")

    w("-" * 100)
    w("8. SIMULATOR CROSS-CHECK")
    w("-" * 100)
    for line in open(os.path.join(C.HERE, "out_xcheck.txt"), encoding="utf-8"):
        if line.startswith("##"):
            continue
        w(line.rstrip())
    w("")

    w("-" * 100)
    w("9. WHAT THE CAPPED BUDGET BUYS AT EQUAL GUARANTEE")
    w("-" * 100)
    w("Same G, same theorem, same ranking score: only the shape of the budget differs.")
    h = []
    for src, nm in ((T, "primary"), (K1, "k1")):
        for lev in sorted(src.level.unique()):
            s = src[src.level == lev].set_index("policy")
            for g in C.GS:
                f, c = f"FIX-G{g:g}", f"CAP-G{g:g}"
                if f in s.index and c in s.index:
                    h.append(dict(trace=nm, level=lev, k=s.loc[f, "k"], G=g,
                                  gap_fix=round(s.loc[f, "gap_closed"], 3),
                                  gap_cap=round(s.loc[c, "gap_closed"], 3),
                                  harm_fix_s=round(s.loc[f, "harm_wf1s_s"], 1),
                                  harm_cap_s=round(s.loc[c, "harm_wf1s_s"], 1),
                                  harm_ratio=round(s.loc[f, "harm_wf1s_s"] /
                                                   max(s.loc[c, "harm_wf1s_s"], 1e-9), 2)))
    H = pd.DataFrame(h)
    H.to_csv(os.path.join(C.HERE, "report_cap_vs_fix.csv"), index=False)
    w(H.to_string(index=False))
    w("harm_* is the worst over the overlays.  The capped relative budget cuts the harm "
      "to jobs that would not have waited by 1.5-4.6x at G = 300 and G = 1200 and at k = 1 "
      "at every G, at a gap difference of at most 0.04; at G = 600 on the primary trace "
      "the worst-over-five-overlays harm is the same as the fixed guard's at rho 0.8-1.0, "
      "so the advantage the validation trace showed there does not survive the worst "
      "overlay.  Reported as measured.")
    w("")

    w("-" * 100)
    w("10. LIMITATIONS AND WHAT WAS NOT DONE")
    w("-" * 100)
    for i, s in enumerate([
        "No held-out trace. 2022-2 alone needs 190 copies of its 8 class-semesters to "
        "load the busiest hour, which builds a load shape the primary trace does not "
        "have, so no 2022-2-only number is reported. The sealed semesters 2023-1, "
        "2023-2 and 2024-1 were not opened, so every number here is a development "
        "number and none of it is a final result.",
        "Guard parameters were chosen on ONE validation overlay (rep 0) at three load "
        "levels. Validation rep 1 was built but not used; the choice is therefore not "
        "checked for overlay-to-overlay stability, and section 9 shows one setting "
        "(G = 600) where the validation advantage does not carry to the worst primary "
        "overlay.",
        "R1S-Tweedie (M4 columns + the forward GRU state) was produced and its forward "
        "protocol checked, but it is not a consistent improvement: better than Tweedie "
        "at rho 0.8 (+0.007 [0.003,0.011]), worse at rho 0.5 (-0.010 [-0.022,-0.002]), "
        "unresolved at rho 1.0. It also trains on 90% of the rows, because forward.py "
        "held out the latest 10% to stop the GRU; the SPJF-tweedie_itr control isolates "
        "that, and the R1S-vs-control differences are the same sign and size, so the "
        "smaller training set is not the explanation.",
        "The intervals are a week-block bootstrap over the 30 weeks of the overlay "
        "timeline. They cover time only. They do not cover which semesters entered the "
        "pool, and the five overlays are one construction of the same data, not five "
        "independent platforms.",
        "Pure scheduling only: every policy shares the same enqueue times, which is what "
        "makes the per-job theorem apply. The cost of computing features and running the "
        "predictor is NOT added to the prediction policies here; the end-to-end "
        "comparison lives in ../codebench_service_v2.",
        "The constant (3 - 2/k)L in the bound is not tight for k >= 2: the worst "
        "used/allowed ratio observed is 0.93 at k = 4..8 against 0.995 at k = 1, which "
        "matches the referee's finding that the constant is tight only at k = 1.",
        "The finite-skip / position-count baseline is reported at equal guarantee and "
        "closes essentially none of the gap on this load (<= 0.02 at rho 0.8 and 1.0). "
        "That is a statement about this workload, where a handful of 60 s jobs carry the "
        "delay, not about position-counting rules in general.",
        "Protocol B (updating the history inside the simulation from each policy's own "
        "completions) was not rerun here; the availability protocol is the pipeline's "
        "protocol A, as in v2.1.",
    ], 1):
        w(f"  ({i}) {s}")
    w("")

    w("-" * 100)
    w("11. RUN COMPLETENESS")
    w("-" * 100)
    cnt = vt.groupby(["trace", "rep", "level"]).size()
    w(f"cells run under the manifest above: {len(cnt)} "
      f"(5 primary overlays x 3 levels + k = 1), 22 policies each; plus 3 validation "
      f"selection cells of 51 policies.  Every stage log in this directory contains one "
      f"'## done' line per invocation and carries the single manifest above.")
    w("An unrelated process on this host ran a machine-wide `taskkill /F /IM python.exe` at about 20:25 "
      "local time; every stage whose numbers appear here was started after 20:38 and ran "
      "to completion, and each cell was checked afterwards for its full policy count, "
      "2,000 finite bootstrap replicates per policy and metric, and zero bound "
      "violations.  Nothing in this report comes from a run that was interrupted.")
    w("")

    w("-" * 100)
    w("12. STAGE LOGS")
    w("-" * 100)
    for p in sorted(glob.glob(os.path.join(C.HERE, "out_*.txt"))):
        n = os.path.basename(p)
        if n in ("out_main_v3.txt",):
            continue
        k = sum(1 for _ in open(p, encoding="utf-8"))
        w(f"    {n:20s} {k:6d} lines")
    w("")
    open(OUT, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
