"""Final stage (v3.1): assemble ../out_main_v31.txt and the CSV behind every table.

Same refusal rule as v3, with the F1 fix: the manifest now hashes the imported modules
(guardkern.py, the v2.1 pipeline, the referee simulator, the ranking-score fitter) as
well as this study's scripts, so "no reported number can come from code that has since
changed" covers everything a number depends on.  Data artefacts are hashed too and quoted
from the build log.

usage: v31_report.py [--allow-stale]
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import time

import numpy as np
import pandas as pd

import v31_common as C

OUT = os.path.join(C.PARENT, "out_main_v31.txt")
ADV = ("reversed", "random", "top1short")


def stale(cur):
    bad = []
    for p in sorted(glob.glob(os.path.join(C.HERE, "out_*.txt"))):
        for h in set(re.findall(r"^## .*manifest=([0-9a-f]{64})",
                                open(p, encoding="utf-8").read(), re.M)):
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
        raise SystemExit(1)
    if a.allow_stale:
        print("no stale stage logs")
        return

    G = pd.read_csv(os.path.join(C.HERE, "gain_primary.csv"))
    T = pd.read_csv(os.path.join(C.HERE, "table_main_primary.csv"))
    D = pd.read_csv(os.path.join(C.HERE, "gaindiff_primary.csv"))
    TR = pd.read_csv(os.path.join(C.HERE, "trace_summary.csv"))
    SEL = pd.read_csv(os.path.join(C.HERE, "selected_params.csv"))
    SW = pd.read_csv(os.path.join(C.HERE, "select_worst.csv"))
    K1 = pd.read_csv(os.path.join(C.HERE, "table_main_k1.csv"))
    L = []

    def w(*x):
        s = " ".join(str(y) for y in x)
        L.append(s)
        print(s, flush=True)

    w("=" * 100)
    w("CONSOLIDATED MAIN EXPERIMENT v3.1 -- CodeBench DEV data")
    w("Tweedie ranking score + capped relative overtake-budget guard + the k-server "
      "per-job bound")
    w("=" * 100)
    w(f"written {time.strftime('%Y-%m-%d %H:%M:%S')}")
    w("")
    w("v3.1 supersedes ../out_main_v3.txt (left untouched) on three points raised by the "
      "independent verifier in ../../main_v3_verify/out_VERDICT.txt:")
    w("  F8  guard parameters are now selected worst-case over FIVE validation overlays "
      "as well as over the three load levels, and the same rule is applied to the "
      "fixed-budget family, so 'capped beats fixed at equal promise' is decided against "
      "the best FEASIBLE fixed budget.")
    w("  F4  the finite-skip baseline is charged at DISPATCH and gets the largest skip "
      "count that still guarantees excess <= G under that accounting (34 rather than 30 "
      "at k = 4, G = 600 s), so it is not handicapped.")
    w("  F1  the manifest hashes the imported modules as well as this study's scripts.")
    w("Everything else the verifier checked -- simulator agreement job for job, the 1,364 "
      "headline numbers, the bootstrap, the adversarial and k = 1 tables, completeness -- "
      "was CONFIRMED, so the pipeline is unchanged.")
    w("")
    w(f"manifest of the code that produced every number below: {cur}")
    for f, h in tab:
        w(f"    {f:46s} {h}")
    w(f"    {'v31_report.py':46s} "
      f"{C.sha256_file(os.path.join(C.HERE, 'v31_report.py'))}   (formats only)")
    w("data artefacts consumed (inputs, not code):")
    for n, h in C.input_table():
        w(f"    {n:46s} {h}")
    w("")
    w("DATA.  CodeBench development semesters only.  2023-1, 2023-2 and 2024-1 were not "
      "opened.  No student source code and no personal attribute is read.")
    w("")

    w("-" * 100)
    w("1. SELECTION PROVENANCE -- READ THIS BEFORE ANY NUMBER")
    w("-" * 100)
    w("The guard family itself and the coarse (B0, eta) grid were NOT invented on "
      "validation data.  They were explored earlier, on the PRIMARY evaluation trace, in "
      "evidence/guard_variants (all_runs.csv holds runs on primary overlays 0 and 1 and "
      "on the k = 1 configuration at all three levels, for CAP-B{30,120,600}-"
      "e{0.5,0.75,0.9}-M{600,1200,3600} and FIX-B{30..3600}); docs/research_plan.md 4.3 "
      "tabulates them.  v3 and v3.1 then select WITHIN that pre-narrowed family using "
      "validation semesters only.  The selection rule's pre-registration cannot be "
      "established from disk either: research_plan.md was last written after v3's "
      "selection ran.")
    w("")
    w("Consequence, stated plainly: NOTHING in this report is a held-out or out-of-sample "
      "result.  The validation pool (the 60 s-regime DEV semesters minus 2022-2) is held "
      "out of the SELECTION, not of the development process.  The 2022-2-only trace "
      "cannot carry load (190 copies) and is not evaluated.  The only held-out evidence "
      "this project will ever have is the sealed semesters 2023-1, 2023-2 and 2024-1, to "
      "be opened exactly once after the protocol freeze.  Do not write 'held out', 'out "
      "of sample' or 'generalises' about any number here.")
    w("")
    w("What v3 claimed and what survives in v3.1:")
    for s in ["the per-job guarantee as empirical fact on this data -- SURVIVES, and is "
              "now also asserted on an independently written simulator's waits by the "
              "verifier (5.7e9 checks, 0 violations)",
              "Tweedie beats the log-scale M4 score at rho 0.8 and 1.0 -- SURVIVES "
              "unchanged (selection does not touch the ranking score)",
              "the guard converts an unbounded tail into the promised one -- SURVIVES",
              "the position-count baseline buys essentially nothing at equal promise -- "
              "SURVIVES, now with the larger skip count the dispatch charge allows",
              "'the G = 600 parameters are validated' -- WITHDRAWN in v3: v3's choice "
              "(30 k/4, eta 0.9) is infeasible on 4 of the 5 validation overlays under "
              "the restated rule; v3.1 reports the setting that is feasible on all of "
              "them (see section 3)",
              "'the capped budget beats the fixed budget at G = 600' -- see section 9; "
              "v3.1 decides it against the best FEASIBLE fixed budget, not against "
              "B0 = Bmax, which is infeasible at every G"]:
        w(f"    * {s}")
    w("")

    w("-" * 100)
    w("2. TRACES")
    w("-" * 100)
    w(TR.to_string(index=False))
    t222 = TR[TR.trace == "t222"]
    if len(t222):
        w(f"\n2022-2-only trace: NOT USABLE, {int(t222.iloc[0]['copies'])} copies of its "
          f"8 class-semesters would be needed to load the busiest hour; unchanged from v3.")
    w("")

    w("-" * 100)
    w("3. GUARD PARAMETERS UNDER THE RESTATED RULE (F8)")
    w("-" * 100)
    w("Rule, worst-case over BOTH axes: a configuration is feasible only if its harm "
      "(max excess over FCFS among jobs FCFS would start within 1 s) is <= G/2 at every "
      "one of the 3 load levels of every one of the 5 validation overlays -- 15 cells; "
      "the objective is the deadline-window p99 gap closed in the WORST cell; ties to "
      "smaller worst harm, then smaller B0, then smaller eta.  Applied twice: over all "
      "15 (B0, eta) points (family 'cap') and over the fixed-budget sub-family eta = 0 "
      "together with B0 = Bmax (family 'fixsel').")
    w("")
    w(SEL[["family", "G", "B0_rule", "eta", "worst_gap", "worst_harm_s", "harm_limit_s",
           "n_feasible", "n_grid", "v3_choice", "v3_worst_gap", "v3_worst_harm_s",
           "v3_feasible_now", "same_as_v3"]].to_string(index=False))
    w("")
    w("v3 -> v3.1, capped family:")
    for _, r in SEL[SEL.family == "cap"].iterrows():
        w(f"    G = {r.G:6g} s: v3 chose {r.v3_choice}; v3.1 chooses B0 = {r.B0_rule}, "
          f"eta = {r.eta:g}."
          f"  {'UNCHANGED' if r.same_as_v3 else 'CHANGED'} -- v3's setting has worst-cell "
          f"harm {r.v3_worst_harm_s:.1f} s against a {r.harm_limit_s:g} s limit "
          f"(feasible now: {r.v3_feasible_now}).")
    w("")
    w("The equal-G fixed baseline (eta = 0, B0 = Bmax) remains infeasible at every G, as "
      "in v3.  Full worst-cell table in select_worst.csv, all 15 cells in select_grid.csv.")
    w("")

    w("-" * 100)
    w("4. MAIN RESULTS -- primary trace, 5 overlays, pure scheduling")
    w("-" * 100)
    w("Primary metric: p99 of the wait among jobs arriving in the 24 h before their own "
      "deadline.  gap = fraction of the FCFS -> true-size-SJF gap closed; red% = plain "
      "percentage reduction against FCFS.  THESE ARE DIFFERENT NUMBERS.  [95% CI] = "
      "2,000-resample week-block paired bootstrap over the 30 weeks of the overlay "
      "timeline; it covers time only, not which semesters entered the pool, and the five "
      "overlays are one construction, not five platforms.")
    rows = []
    for lev in sorted(T.level.unique()):
        for _, r in T[T.level == lev].iterrows():
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
      "means.  SKIP = finite skip charged at dispatch (the fair count, F4); SKIPC = v3's "
      "completion-charged variant at the same promise.  FIX = B0 = Bmax; FIXSEL = the "
      "best feasible fixed budget; CAP = the selected capped relative budget.")
    w("")

    w("-" * 100)
    w("5. DIFFERENCES (paired week-block bootstrap; resolved = the 95% CI excludes 0)")
    w("-" * 100)
    d = D[(D.metric == "p99dl") & (D.quantity == "gain")].copy()
    d["d_gap"] = [cell(v, l, h) for v, l, h in zip(d["diff"], d.lo, d.hi)]
    dd = d[["level", "pair", "label", "d_gap", "resolved", "verdict"]]
    dd.to_csv(os.path.join(C.HERE, "report_diff.csv"), index=False)
    w(dd.to_string(index=False))
    w("")

    w("-" * 100)
    w("6. ADVERSARIAL PREDICTORS")
    w("-" * 100)
    w(f"Guarded runs use the selected capped guard at G = {C.ADV_G:g} s.")
    ar = T[[p.split("-")[-1] in ADV for p in T.policy]].copy()
    ar = ar[["level", "rho_target", "k", "policy", "p99_dl_s", "gap_closed", "red_pct",
             "mean_s", "max_excess_s", "harm_wf1s_s", "max_heavy_s", "guar_excess_s",
             "used_over_allowed", "qw_fired"]].round(3)
    ar.to_csv(os.path.join(C.HERE, "report_adversarial.csv"), index=False)
    w(ar.to_string(index=False))
    w("The guarantee is per job, not per quantile: a guarded run may still have a worse "
      "p99 than FCFS, by at most G.  What the guard removes is the worst single job.")
    w("")

    w("-" * 100)
    w("7. SINGLE-SERVER CONFIGURATION (k = 1, busy-hour rho ~ 0.80)")
    w("-" * 100)
    k1 = K1[["policy", "score", "G", "B0", "eta", "Bmax", "Ncap", "p99_dl_s",
             "gap_closed", "gap_lo", "gap_hi", "red_pct", "mean_s", "max_excess_s",
             "harm_wf1s_s", "max_heavy_s", "guar_excess_s", "used_over_allowed",
             "qw_fired"]].round(4)
    k1.to_csv(os.path.join(C.HERE, "report_k1.csv"), index=False)
    w(k1.to_string(index=False))
    w("")

    w("-" * 100)
    w("8. THE PER-JOB THEOREM, ASSERTED ON EVERY JOB OF EVERY GUARDED RUN")
    w("-" * 100)
    w("Work-budget guards (k identical non-preemptive work-conserving servers, "
      "service <= L = 60 s):")
    w("    W_guard[i] <= W_FCFS[i] + Bmax/k + (3 - 2/k) L                        (Thm A)")
    w("    W_guard[i] <= (W_FCFS[i] + B0/k + (3 - 2/k) L) / (1 - eta)            (Thm B)")
    w("Finite skip charged at dispatch (proof in v31_skipkern.py's docstring):")
    w("    W_skip[i]  <= W_FCFS[i] + (N + 2k - 2) L / k")
    b = pd.concat([T, K1], ignore_index=True)
    b = b[b.G > 0][["trace", "level", "k", "policy", "G", "B0", "eta", "Bmax", "Ncap",
                    "guar_excess_s", "max_excess_s", "used_over_allowed"]].round(4)
    b.to_csv(os.path.join(C.HERE, "report_bound.csv"), index=False)
    w(b.to_string(index=False))
    vt = pd.concat([pd.read_csv(f) for f in
                    sorted(glob.glob(os.path.join(C.SIMDIR, "*_main.csv")))],
                   ignore_index=True)
    gv = vt[vt.bound_viol >= 0]
    vg = pd.concat([pd.read_csv(f) for f in
                    sorted(glob.glob(os.path.join(C.SIMDIR, "*_grid.csv")))],
                   ignore_index=True)
    gg = vg[vg.bound_viol >= 0]
    w(f"\nreported runs: {len(gv)} guarded (trace x overlay x level x policy), "
      f"{int(gv.n_jobs.sum()):,} per-job checks, violations {int(gv.bound_viol.sum())}")
    w(f"selection grid: {len(gg)} guarded runs, {int(gg.n_jobs.sum()):,} per-job checks, "
      f"violations {int(gg.bound_viol.sum())}")
    w(f"worst used/allowed anywhere in the reported runs: "
      f"{b.used_over_allowed.max():.4f} "
      f"(policy {b.loc[b.used_over_allowed.idxmax(), 'policy']}, "
      f"trace {b.loc[b.used_over_allowed.idxmax(), 'trace']}, "
      f"k = {b.loc[b.used_over_allowed.idxmax(), 'k']:.0f})")
    w("")

    w("-" * 100)
    w("9. CAPPED RELATIVE vs FIXED BUDGET AT EQUAL PROMISE")
    w("-" * 100)
    h = []
    for src, nm in ((T, "primary"), (K1, "k1")):
        for lev in sorted(src.level.unique()):
            s = src[src.level == lev].set_index("policy")
            for g in C.GS:
                f, fs, c = f"FIX-G{g:g}", f"FIXSEL-G{g:g}", f"CAP-G{g:g}"
                if not all(x in s.index for x in (f, fs, c)):
                    continue
                h.append(dict(trace=nm, level=lev, k=s.loc[f, "k"], G=g,
                              gap_fix=round(s.loc[f, "gap_closed"], 3),
                              gap_fixsel=round(s.loc[fs, "gap_closed"], 3),
                              gap_cap=round(s.loc[c, "gap_closed"], 3),
                              harm_fix_s=round(s.loc[f, "harm_wf1s_s"], 1),
                              harm_fixsel_s=round(s.loc[fs, "harm_wf1s_s"], 1),
                              harm_cap_s=round(s.loc[c, "harm_wf1s_s"], 1),
                              guar_fixsel_s=round(s.loc[fs, "guar_excess_s"], 1),
                              guar_cap_s=round(s.loc[c, "guar_excess_s"], 1),
                              d_gap_cap_minus_fixsel=round(s.loc[c, "gap_closed"] -
                                                           s.loc[fs, "gap_closed"], 3),
                              harm_ratio_fix_over_cap=round(
                                  s.loc[f, "harm_wf1s_s"] /
                                  max(s.loc[c, "harm_wf1s_s"], 1e-9), 2)))
    H = pd.DataFrame(h)
    H.to_csv(os.path.join(C.HERE, "report_cap_vs_fix.csv"), index=False)
    w(H.to_string(index=False))
    w("")
    w("How to read this, carefully.  A FIXED budget can only satisfy the harm constraint "
      "by being SMALL, and a small constant budget delivers a promise TIGHTER than G "
      "(guar_fixsel_s below G), not the promise G.  So FIXSEL is not an equal-promise "
      "competitor: it is the best a fixed budget can do while meeting the same harm "
      "constraint, and it buys that by giving up most of the benefit "
      "(d_gap_cap_minus_fixsel, resolved in every cell in section 5).  The equal-promise "
      "fixed budget is FIX (B0 = Bmax), and the selection rule rejects it as infeasible "
      "at every G on the validation overlays.  The defensible statement is therefore: "
      "under a harm constraint, no fixed budget reaches what the capped relative budget "
      "reaches -- either it is infeasible (FIX) or it is far weaker (FIXSEL).  The "
      "harm_ratio_fix_over_cap column, the v3 claim, is the weaker one and still ties at "
      "G = 600, rho 0.5 on the worst overlay.")
    w("")

    w("-" * 100)
    w("10. SIMULATOR CROSS-CHECK")
    w("-" * 100)
    for line in open(os.path.join(C.HERE, "out_xcheck.txt"), encoding="utf-8"):
        if not line.startswith("##"):
            w(line.rstrip())
    w("")

    w("-" * 100)
    w("11. LIMITATIONS AND WHAT WAS NOT DONE")
    w("-" * 100)
    for i, s in enumerate([
        "No held-out or test claim of any kind -- see section 1.  Sealed semesters not "
        "opened; the 2022-2-only trace cannot carry load; the guard family was tuned on "
        "the primary trace before validation-only selection existed.",
        "The selection is now worst-case over five validation overlays and three levels, "
        "but those five overlays are five draws of the same 32 class-semesters, not five "
        "independent platforms; robustness across overlays is not robustness across "
        "populations.",
        "R1S-Tweedie is not a consistent improvement over Tweedie and must not be "
        "claimed as one.",
        "The intervals cover time only: 30 week blocks of one overlay construction.",
        "Pure scheduling only; feature and prediction cost is not charged.",
        "The constant (3 - 2/k)L is not tight for k >= 2.  The finite-skip bound, by "
        "contrast, is tight: the cross-check reaches used/allowed = 1.0000 on small "
        "instances.",
        "A float64 clock with microsecond budget accounting can resolve a completion that "
        "coincides exactly with an arrival on either side (verifier F5).  No reported "
        "number moves measurably, but both kernels here share the convention, so this "
        "cross-check cannot detect it either.",
        "Protocol B (history updated inside the simulation from each policy's own "
        "completions) was not rerun; the availability protocol is the pipeline's A.",
    ], 1):
        w(f"  ({i}) {s}")
    w("")

    w("-" * 100)
    w("12. STAGE LOGS (this directory)")
    w("-" * 100)
    for p in sorted(glob.glob(os.path.join(C.HERE, "out_*.txt"))):
        w(f"    {os.path.basename(p):20s} "
          f"{sum(1 for _ in open(p, encoding='utf-8')):6d} lines")
    open(OUT, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
