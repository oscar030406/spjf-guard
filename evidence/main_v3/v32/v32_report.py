"""Final stage (v3.2): assemble ../out_main_v32.txt and the CSV behind every table.

Same refusal rule as v3/v3.1: every stage log records the manifest hash over this study's
scripts and the imported modules, and nothing is written if any stage log carries a
different one.

usage: v32_report.py [--allow-stale]
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import time

import numpy as np
import pandas as pd

import v32_common as C

OUT = os.path.join(C.PARENT, "out_main_v32.txt")
ADV = ("reversed", "random", "top1short")
FAMLAB = {"fixed": "FIXSEL", "capped": "CAP", "hybrid": "HYB"}


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

    T = pd.read_csv(os.path.join(C.HERE, "table_main_primary.csv"))
    D = pd.read_csv(os.path.join(C.HERE, "gaindiff_primary.csv"))
    TR = pd.read_csv(os.path.join(C.HERE, "trace_summary.csv"))
    SEL = pd.read_csv(os.path.join(C.HERE, "selected_params.csv"))
    SENS = pd.read_csv(os.path.join(C.HERE, "select_sensitivity.csv"))
    FR = pd.read_csv(os.path.join(C.HERE, "frontier.csv"))
    K1 = pd.read_csv(os.path.join(C.HERE, "table_main_k1.csv"))
    L = []

    def w(*x):
        s = " ".join(str(y) for y in x)
        L.append(s)
        print(s, flush=True)

    dg = D[(D.metric == "p99dl") & (D.quantity == "gain")]
    cf = dg[dg.pair.str.match(r"CAP-G\d+ - FIXSEL-G\d+")].copy()
    cf["G"] = [float(re.search(r"CAP-G(\d+)", p).group(1)) for p in cf.pair]
    win = cf[(cf.lo > 0)]
    lose = cf[(cf.hi < 0)]
    tie = cf[(cf.lo <= 0) & (cf.hi >= 0)]

    w("=" * 100)
    w("CONSOLIDATED MAIN EXPERIMENT v3.2 -- CodeBench DEV data")
    w("=" * 100)
    w(f"written {time.strftime('%Y-%m-%d %H:%M:%S')}")
    w("")
    w("-" * 100)
    w("1. THE HONEST CONCLUSION")
    w("-" * 100)
    w("v3.2 exists because the independent verifier found (G1, CRITICAL) that v3.1's "
      "headline comparison was rigged by an unequal search: the capped relative budget "
      "was chosen from 15 points and 'the best feasible fixed budget' from 4, leaving "
      "the harm constraint slack at the fixed family's point.  v3.2 gives both families "
      "pre-stated grids of comparable density (fixed: 39 budgets, of which 27-41 are "
      "admissible per promise; capped: 54 points; plus an 18-point hybrid) and applies "
      "the identical rule.  The verifier's prediction is confirmed: a properly searched "
      "fixed budget is far better than v3.1 reported.")
    w("")
    fx31 = {300.0: 0.0057, 600.0: 0.3693, 1200.0: 0.3693}
    for _, r in SEL[SEL.family == "fixed"].iterrows():
        w(f"    fixed family, G = {r.G:6g} s: worst-cell validation gap "
          f"{r.worst_gap:.4f} on the equal grid, against {fx31[r.G]:.4f} on v3.1's "
          f"four-point grid.")
    w("")
    w("What that does to the headline, measured on the primary trace (5 overlays, paired "
      "week-block bootstrap), CAP - FIXSEL on the deadline-window p99 gap closed:")
    for _, r in cf.sort_values(["G", "level"]).iterrows():
        w(f"    G = {r.G:6g} s, rho {r.rho_target}: {r['diff']:+.3f} "
          f"[{r.lo:+.3f},{r.hi:+.3f}]  {r.verdict}")
    w("")
    w(f"So: the capped relative budget wins {len(win)} of the 9 (promise, load) cells, "
      f"ties in {len(tie)}, and loses {len(lose)}.")
    if len(win):
        w(f"    where it wins, the margin runs from {win['diff'].min():+.3f} to "
          f"{win['diff'].max():+.3f} of the FCFS->SJF gap;")
    if len(lose):
        w(f"    where it loses, the margin runs from {lose['diff'].min():+.3f} to "
          f"{lose['diff'].max():+.3f}.")
    w("    v3.1's claim 'no fixed budget reaches what the capped relative budget "
      "reaches' is WITHDRAWN.  The defensible statement is the narrower one below.")
    w("")
    ww = SEL.sort_values(["G", "worst_gap"], ascending=[True, False])
    w("Which family the rule actually picks, per promise (validation, worst of 15 cells):")
    for G in C.GS:
        z = ww[ww.G == G]
        w(f"    G = {G:6g} s: " + " > ".join(
            f"{r.family} {r.worst_gap:.4f} (harm {r.worst_harm_s:.0f} s)"
            for r in z.itertuples()))
    w("")
    w("Does the capped budget buy anything a fixed one cannot, beyond the harm profile?  "
      "In principle yes: a constant budget B promises W <= W_FCFS + B/k + (3-2/k)L, the "
      "same number of extra seconds whether FCFS would have made the job wait 0 s or "
      "600 s, while the capped relative budget promises "
      "(W_FCFS + B0/k + (3-2/k)L)/(1-eta), an allowance that grows with the wait the job "
      "already had, up to Bmax.  Measured among the jobs FCFS already makes wait more "
      "than 60 s, at rho 1.0 (full table in section 7; excess is W_policy - W_FCFS, so "
      "negative means the policy HELPS those jobs):")
    lw = T[T.G > 0].copy()
    facts = []
    for G in C.GS:
        s = lw[(lw.G == G) & (lw.level == 2)].set_index("policy")
        a_, b_ = f"CAP-G{G:g}", f"FIXSEL-G{G:g}"
        if a_ not in s.index or b_ not in s.index:
            continue
        w(f"    G = {G:6g} s: mean excess {s.loc[a_, 'lw_ex_mean']:8.1f} s (CAP) vs "
          f"{s.loc[b_, 'lw_ex_mean']:8.1f} s (FIXSEL);  p99 excess "
          f"{s.loc[a_, 'lw_ex_p99']:7.1f} vs {s.loc[b_, 'lw_ex_p99']:7.1f};  worst "
          f"W/W_FCFS {s.loc[a_, 'lw_ratio_max']:6.2f} vs "
          f"{s.loc[b_, 'lw_ratio_max']:6.2f}")
        facts.append((G, s.loc[a_, "lw_ex_mean"] < 0 and s.loc[b_, "lw_ex_mean"] < 0,
                      s.loc[a_, "lw_ex_p99"] > s.loc[b_, "lw_ex_p99"],
                      s.loc[a_, "lw_ratio_max"] > s.loc[b_, "lw_ratio_max"]))
    nneg = sum(1 for f in facts if f[1])
    np99 = sum(1 for f in facts if f[2])
    nrat = sum(1 for f in facts if f[3])
    w(f"    Read straight off those rows: at all {nneg} of {len(facts)} promises BOTH "
      f"policies leave these jobs better off on average than FCFS -- prediction-driven "
      f"ordering helps the jobs that were queued behind long ones, and the guard does not "
      f"take that back.  The capped budget's worst single ratio W/W_FCFS is larger than "
      f"the fixed budget's at {nrat} of {len(facts)} promises, which is the multiplicative "
      f"allowance showing up where the theory says it should; but its p99 excess is larger "
      f"at only {np99} of {len(facts)}.  So the multiplicative shape is visible in the "
      f"extreme tail and not in the body of the distribution, and on this workload it is "
      f"not a practical advantage -- it is a different promise, not a better outcome, for "
      f"these jobs.")
    w("")
    w("None of this is a held-out result.  See section 2.")
    w("")

    w(f"manifest of the code that produced every number below: {cur}")
    for f, h in tab:
        w(f"    {f:46s} {h}")
    w(f"    {'v32_report.py':46s} "
      f"{C.sha256_file(os.path.join(C.HERE, 'v32_report.py'))}   (formats only)")
    w("data artefacts consumed (inputs, not code):")
    for n, h in C.input_table():
        w(f"    {n:46s} {h}")
    w("")

    w("-" * 100)
    w("2. SELECTION PROVENANCE")
    w("-" * 100)
    w("Unchanged from v3.1 and restated because it bounds everything above.  The guard "
      "family and the coarse (B0, eta) grid were explored on the PRIMARY evaluation "
      "trace in evidence/guard_variants before any validation-only selection existed, "
      "and the selection rule's pre-registration cannot be established from disk.  The "
      "validation pool (the 60 s-regime DEV semesters minus 2022-2) is held out of the "
      "SELECTION, not of the development process; the 2022-2-only trace cannot carry "
      "load; the sealed semesters 2023-1, 2023-2 and 2024-1 were not opened.  Do not "
      "write 'held out', 'out of sample' or 'generalises' about any number here.  The "
      "one fresh element in v3.2 is the fixed-budget grid, which was written down in "
      "v32_common.py's docstring before any v3.2 number existed.")
    w("")

    w("-" * 100)
    w("3. TRACES")
    w("-" * 100)
    w(TR.to_string(index=False))
    w("")

    w("-" * 100)
    w("4. SELECTION ON EQUAL GRIDS (15 validation cells = 5 overlays x 3 load levels)")
    w("-" * 100)
    w("Rule: feasible = harm <= G/2 in EVERY cell; objective = the deadline-window p99 "
      "gap closed in the WORST cell; ties to smaller worst harm, then smaller B0, eta, "
      "gam.  Every budget scales with k/4, so one setting serves every load level.")
    w("")
    w(SEL[["family", "G", "B0_base", "eta", "gam_base", "policy", "worst_gap",
           "worst_harm_s", "harm_limit_s", "harm_slack_s", "binds", "worst_promise_s",
           "n_feasible", "n_grid"]].to_string(index=False))
    w("")
    w("'binds' is True when the chosen point is within 5% of the harm limit.  The next "
      "point with a better worst-cell gap, and why it was rejected:")
    for _, r in SEL.iterrows():
        w(f"    G = {r.G:6g} {r.family:7s}: {r.next_better_point}")
    w("")
    w("Sensitivity (verifier G4): the selection when the single validation cell that "
      "decided v3.1's G = 600 choice (overlay 1, level 2) is dropped:")
    w(SENS.to_string(index=False))
    w("")
    w("Feasible frontier, gap against harm, per promise and family (frontier.csv holds "
      "every point; here the feasible ones, best 6 by gap):")
    for G in C.GS:
        w(f"\n  --- G = {G:g} s ---")
        for fam in ("fixed", "capped", "hybrid"):
            z = FR[(FR.G == G) & (FR.family == fam) & FR.feasible]
            z = z.sort_values("worst_gap", ascending=False).head(6)
            w(f"    {fam:7s} " + "  ".join(
                f"[{r.worst_gap:.3f}@{r.worst_harm:.0f}s]" for r in z.itertuples()))
    w("")

    w("-" * 100)
    w("5. MAIN RESULTS -- primary trace, 5 overlays, pure scheduling")
    w("-" * 100)
    w("gap = fraction of the FCFS -> true-size-SJF gap closed; red% = plain reduction "
      "against FCFS.  [95% CI] = 2,000-resample week-block paired bootstrap over the 30 "
      "weeks of the overlay timeline; it covers time only.")
    w("PARAMETERS ARE PER OVERLAY (verifier G3): the five overlays do not all run the "
      "same k -- overlays 0-3 run k = 8/5/4 by load level and overlay 4 runs k = 7/5/4 "
      "-- and every budget and skip count scales with k, so the columns below list one "
      "value per overlay in overlay order.")
    rows = []
    for lev in sorted(T.level.unique()):
        for _, r in T[T.level == lev].iterrows():
            if r.policy.split("-")[-1] in ADV:
                continue
            rows.append(dict(level=lev, rho=r.rho_target, k_by_overlay=r.k_by_overlay,
                             policy=r.policy, p99_dl_s=round(r.p99_dl_s, 2),
                             gap_closed=cell(r.gap_closed, r.gap_lo, r.gap_hi),
                             red_pct=cell(r.red_pct, r.red_lo, r.red_hi, 1),
                             mean_s=round(r.mean_s, 3),
                             max_excess_s=round(r.max_excess_s, 1),
                             harm_s=round(r.harm_wf1s_s, 1),
                             max_heavy_s=round(r.max_heavy_s, 1),
                             qw_fired=round(r.qw_fired, 4),
                             B0_by_overlay=r.B0_by_overlay,
                             Ncap_by_overlay=r.Ncap_by_overlay,
                             promise_by_overlay=r.promise_by_overlay))
    M = pd.DataFrame(rows)
    M.to_csv(os.path.join(C.HERE, "report_main.csv"), index=False)
    for lev in sorted(M.level.unique()):
        s = M[M.level == lev]
        w(f"\n--- level {lev}: target busy-hour rho {s.rho.iloc[0]}, k per overlay "
          f"{s.k_by_overlay.iloc[0]} ---")
        w(s.drop(columns=["level", "rho", "k_by_overlay"]).to_string(index=False))
    w("")
    w("max_excess / harm / max_heavy are the worst over the five overlays; the rest are "
      "means.  FIX = the equal-promise fixed budget B0 = Bmax; FIXSEL = the fixed budget "
      "the rule selects on the equal grid; CAP = the selected capped relative budget; "
      "HYB = the selected hybrid; SKIP = finite skip charged at dispatch.")
    w("")

    w("-" * 100)
    w("6. PAIRED DIFFERENCES (week-block paired bootstrap; resolved = CI excludes 0)")
    w("-" * 100)
    d = dg.copy()
    d["d_gap"] = [cell(v, l, h) for v, l, h in zip(d["diff"], d.lo, d.hi)]
    dd = d[["level", "rho_target", "pair", "label", "d_gap", "resolved", "verdict"]]
    dd.to_csv(os.path.join(C.HERE, "report_diff.csv"), index=False)
    w(dd.to_string(index=False))
    w("")

    w("-" * 100)
    w("7. EXCESS AMONG JOBS FCFS ALREADY MAKES WAIT (W_FCFS > 60 s)")
    w("-" * 100)
    lwt = T[T.G > 0][["level", "rho_target", "policy", "lw_ex_mean", "lw_ex_p50",
                      "lw_ex_p90", "lw_ex_p99", "lw_ex_max", "lw_ratio_p99",
                      "lw_ratio_max"]].round(3)
    lwt.to_csv(os.path.join(C.HERE, "report_longwait.csv"), index=False)
    w(lwt.to_string(index=False))
    w("lw_ex_* are excesses in seconds over that job's FCFS wait; lw_ratio_* are "
      "W_policy / W_FCFS.  Means are over the overlays, maxima are the worst overlay.")
    w("")

    w("-" * 100)
    w("8. ADVERSARIAL PREDICTORS")
    w("-" * 100)
    ar = T[[p.split("-")[-1] in ADV for p in T.policy]][
        ["level", "rho_target", "policy", "p99_dl_s", "gap_closed", "mean_s",
         "max_excess_s", "harm_wf1s_s", "lw_ex_max", "guar_excess_s",
         "used_over_allowed", "qw_fired"]].round(3)
    ar.to_csv(os.path.join(C.HERE, "report_adversarial.csv"), index=False)
    w(ar.to_string(index=False))
    w("")

    w("-" * 100)
    w("9. SINGLE-SERVER CONFIGURATION (k = 1, busy-hour rho ~ 0.80)")
    w("-" * 100)
    k1 = K1[["policy", "family", "G", "B0_by_overlay", "eta", "gam_by_overlay",
             "Ncap_by_overlay", "promise_by_overlay", "p99_dl_s", "gap_closed", "gap_lo",
             "gap_hi", "mean_s", "max_excess_s", "harm_wf1s_s", "lw_ex_p99", "lw_ex_max",
             "used_over_allowed"]].round(4)
    k1.to_csv(os.path.join(C.HERE, "report_k1.csv"), index=False)
    w(k1.to_string(index=False))
    w("")

    w("-" * 100)
    w("10. THE PER-JOB THEOREM")
    w("-" * 100)
    w("    work budget  W <= min( (k W_F + C_i + (3k-2)L)/(k - eps), "
      "W_F + (Bmax + (3k-2)L)/k )")
    w("    finite skip  W <= W_F + (N + 2k - 2) L / k")
    b = pd.concat([T, K1], ignore_index=True)
    b = b[b.G > 0][["trace", "level", "policy", "G", "B0_by_overlay", "eta",
                    "gam_by_overlay", "Bmax_by_overlay", "Ncap_by_overlay",
                    "promise_by_overlay", "guar_excess_s", "max_excess_s",
                    "used_over_allowed"]].round(4)
    b.to_csv(os.path.join(C.HERE, "report_bound.csv"), index=False)
    w(b.to_string(index=False))
    vt = pd.concat([pd.read_csv(f) for f in
                    sorted(glob.glob(os.path.join(C.SIMDIR, "*_main.csv")))],
                   ignore_index=True)
    vg = pd.concat([pd.read_csv(f) for f in
                    sorted(glob.glob(os.path.join(C.SIMDIR, "*_grid.csv")))],
                   ignore_index=True)
    gv, gg = vt[vt.bound_viol >= 0], vg[vg.bound_viol >= 0]
    w(f"\nreported runs: {len(gv)} guarded, {int(gv.n_jobs.sum()):,} per-job checks, "
      f"violations {int(gv.bound_viol.sum())}")
    w(f"selection grid: {len(gg)} guarded configurations, "
      f"{int(gg.n_jobs.sum()):,} per-job checks, violations "
      f"{int(gg.bound_viol.sum())}")
    w(f"worst used/allowed in the reported runs: {b.used_over_allowed.max():.4f}")
    w("")

    w("-" * 100)
    w("11. SIMULATOR CROSS-CHECK")
    w("-" * 100)
    for line in open(os.path.join(C.HERE, "out_xcheck.txt"), encoding="utf-8"):
        if not line.startswith("##"):
            w(line.rstrip())
    w("")

    w("-" * 100)
    w("12. LIMITATIONS")
    w("-" * 100)
    for i, s in enumerate([
        "No held-out or test claim of any kind (section 2).",
        "The five validation overlays are five draws of the same 32 class-semesters, "
        "not five independent tests; section 4's sensitivity table shows which choices "
        "a single cell decides.",
        "The grids are dense but still grids; the frontier in section 4 shows how flat "
        "the objective is near the chosen points, and at several promises the harm "
        "constraint binds, so the choice is a constraint corner, not an optimum.",
        "The intervals cover time only: 30 week blocks of one overlay construction.",
        "Pure scheduling only; feature and prediction cost is not charged.",
        "R1S-Tweedie is not claimed to improve on Tweedie.",
        "A float64 clock with microsecond budget accounting can resolve a completion "
        "coincident with an arrival on either side; both kernels share the convention.",
    ], 1):
        w(f"  ({i}) {s}")
    w("")
    w("-" * 100)
    w("13. STAGE LOGS")
    w("-" * 100)
    for p in sorted(glob.glob(os.path.join(C.HERE, "out_*.txt"))):
        w(f"    {os.path.basename(p):20s} "
          f"{sum(1 for _ in open(p, encoding='utf-8')):6d} lines")
    open(OUT, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
