"""V3: every number of out_main_v31.txt sections 4-9, three ways.

  (1) printed  vs the builder's own report_*.csv          (hand-edit check)
  (2) report_*.csv vs the builder's per-cell csv files, re-aggregated here
  (3) report_*.csv vs MY OWN re-simulated cells (wcells.py)
Read-only.
"""
from __future__ import annotations

import os
import re

import numpy as np
import pandas as pd

ROOT = r"<repo-root>"
V31 = os.path.join(ROOT, "evidence", "main_v3", "v31")
REP = os.path.join(ROOT, "evidence", "main_v3", "out_main_v31.txt")
HERE = os.path.dirname(os.path.abspath(__file__))
SCRATCH = r"<cache-dir>"
BSIM = os.path.join(SCRATCH, "mv31", "sim")
MINE = os.path.join(SCRATCH, "mv31_verify", "cells")
GS = (300.0, 600.0, 1200.0)
OUT = []
NUM = re.compile(r"-?\d+\.?\d*(?:[eE][-+]?\d+)?|inf|nan|True|False")


def say(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    OUT.append(s)


def block(txt, start, end):
    return txt.split(start)[1].split(end)[0]


def tokens(s):
    return NUM.findall(s)


# --------------------------------------------------------------------------- #
def part1(txt):
    say("=" * 96)
    say("1. PRINTED TABLES vs THE BUILDER'S OWN report_*.csv")
    say("=" * 96)
    tot = bad = 0
    # --- section 4: three level tables, from report_main.csv
    M = pd.read_csv(os.path.join(V31, "report_main.csv"))
    s4 = block(txt, "4. MAIN RESULTS", "max_excess / harm / max_heavy are the worst")
    for lev in sorted(M.level.unique()):
        sub = M[M.level == lev].drop(columns=["level", "rho_target", "k"])
        want = sub.to_string(index=False).splitlines()
        marker = f"--- level {lev}: "
        got = s4.split(marker)[1].splitlines()[1:]
        got = [g for g in got if g.strip()][: len(want)]
        for a, b in zip(want, got):
            ta, tb = tokens(a), tokens(b)
            tot += len(ta)
            if ta != tb:
                bad += sum(1 for x, y in zip(ta, tb) if x != y) + abs(len(ta) - len(tb))
                say(f"  !! section 4 level {lev} row mismatch\n     csv: {a}\n     txt: {b}")
    say(f"  section 4: {tot} numbers compared, {bad} mismatches")
    # --- section 5
    t0, b0 = tot, bad
    D = pd.read_csv(os.path.join(V31, "report_diff.csv"))
    s5 = block(txt, "5. DIFFERENCES (paired week-block bootstrap; resolved = the 95% CI"
                    " excludes 0)\n" + "-" * 100 + "\n", "\n" + "-" * 100)
    want = D.to_string(index=False).splitlines()
    got = [g for g in s5.splitlines() if g.strip()]
    for a, b in zip(want, got):
        ta, tb = tokens(a), tokens(b)
        tot += len(ta)
        if ta != tb:
            bad += max(len(ta), len(tb))
            say(f"  !! section 5 row\n     csv: {a}\n     txt: {b}")
    say(f"  section 5: {tot - t0} numbers compared, {bad - b0} mismatches "
        f"(rows csv {len(want)} / txt {len(got)})")
    # --- sections 6, 7, 8, 9
    for name, csv, start, end in (
            ("6", "report_adversarial.csv", "6. ADVERSARIAL PREDICTORS\n" + "-" * 100
             + "\n", "The guarantee is per job"),
            ("7", "report_k1.csv", "7. SINGLE-SERVER CONFIGURATION (k = 1, busy-hour "
             "rho ~ 0.80)\n" + "-" * 100 + "\n", "\n" + "-" * 100),
            ("8", "report_bound.csv", "    W_skip[i]  <= W_FCFS[i] + (N + 2k - 2) L / k"
             "\n", "\nreported runs:"),
            ("9", "report_cap_vs_fix.csv", "9. CAPPED RELATIVE vs FIXED BUDGET AT EQUAL "
             "PROMISE\n" + "-" * 100 + "\n", "\nHow to read this")):
        t0, b0 = tot, bad
        C_ = pd.read_csv(os.path.join(V31, csv))
        if name == "6":
            C_ = C_.drop(columns=[])
        want = C_.to_string(index=False).splitlines()
        got = [g for g in block(txt, start, end).splitlines() if g.strip()]
        if name == "6":
            got = [g for g in got if not g.startswith("Guarded runs use")]
        for a, b in zip(want, got):
            ta, tb = tokens(a), tokens(b)
            tot += len(ta)
            if ta != tb:
                bad += max(len(ta), len(tb))
                say(f"  !! section {name} row\n     csv: {a}\n     txt: {b}")
        say(f"  section {name}: {tot - t0} numbers compared, {bad - b0} mismatches "
            f"(rows csv {len(want)} / txt {len(got)})")
    say(f"  TOTAL printed-vs-csv: {tot} numbers, {bad} mismatches")
    return tot, bad


# --------------------------------------------------------------------------- #
MEANC = ("w_p99_dl", "w_mean", "w_p99", "qw_forced_frac", "guar_excess_max", "k")
MAXC = ("max_excess", "harm_wf1s", "max_heavy", "used_over_allowed")


def aggregate(cells):
    """cells: {rep: DataFrame indexed by policy}.  Returns the table_main columns."""
    reps = sorted(cells)
    pols = [p for p in cells[reps[0]].index
            if all(p in cells[r].index for r in reps)]
    F = np.array([cells[r].loc["FCFS", "w_p99_dl"] for r in reps])
    S = np.array([cells[r].loc["SJF-ref", "w_p99_dl"] for r in reps])
    Fm = np.array([cells[r].loc["FCFS", "w_mean"] for r in reps])
    Sm = np.array([cells[r].loc["SJF-ref", "w_mean"] for r in reps])
    rows = []
    for p in pols:
        P = np.array([cells[r].loc[p, "w_p99_dl"] for r in reps])
        Pm = np.array([cells[r].loc[p, "w_mean"] for r in reps])
        d = dict(policy=p, gap_closed=float(np.mean((F - P) / (F - S))),
                 red_pct=float(np.mean(100.0 * (F - P) / F)),
                 mean_gap=float(np.mean((Fm - Pm) / (Fm - Sm))))
        for c in MEANC:
            if c in cells[reps[0]].columns:
                d[c] = float(np.mean([cells[r].loc[p, c] for r in reps]))
        for c in MAXC:
            if c in cells[reps[0]].columns:
                d[c] = float(np.max([cells[r].loc[p, c] for r in reps]))
        rows.append(d)
    return pd.DataFrame(rows).set_index("policy")


def load(d, trace, reps, lev, suffix):
    out = {}
    for r in reps:
        p = os.path.join(d, f"{trace}_rep{r}_L{lev}_{suffix}.csv")
        if not os.path.exists(p):
            return None
        out[r] = pd.read_csv(p).set_index("policy")
    return out


COLMAP = [("p99_dl_s", "w_p99_dl", 5e-3), ("gap_closed", "gap_closed", 5e-4),
          ("red_pct", "red_pct", 5e-2), ("mean_s", "w_mean", 5e-4),
          ("mean_gap", "mean_gap", 5e-4), ("p99_all_s", "w_p99", 5e-3),
          ("max_excess_s", "max_excess", 5e-2), ("harm_wf1s_s", "harm_wf1s", 5e-2),
          ("max_heavy_s", "max_heavy", 5e-2), ("qw_fired", "qw_forced_frac", 5e-5),
          ("guar_excess_s", "guar_excess_max", 5e-5),
          ("used_over_allowed", "used_over_allowed", 5e-5)]


def part23(src, label):
    say("")
    say("=" * 96)
    say(f"{label}")
    say("=" * 96)
    T = pd.read_csv(os.path.join(V31, "table_main_primary.csv"))
    K1 = pd.read_csv(os.path.join(V31, "table_main_k1.csv"))
    tot = bad = 0
    for lev in (0, 1, 2):
        cells = load(src, "primary", range(5), lev, "main")
        if cells is None:
            say(f"  level {lev}: no cells of mine, skipped")
            continue
        A = aggregate(cells)
        sub = T[T.level == lev].set_index("policy")
        for p in sub.index:
            if p not in A.index:
                say(f"  !! policy {p} missing at level {lev}")
                bad += 1
                continue
            for tc, mc, tol in COLMAP:
                if mc not in A.columns or tc not in sub.columns:
                    continue
                if p == "FCFS" and tc == "qw_fired":
                    continue          # under FCFS every dispatch serves the head, so
                                      # the builder scores it 1.0 and my kernel 0.0;
                                      # a labelling convention, not a number
                x, y = float(sub.loc[p, tc]), float(A.loc[p, mc])
                if not np.isfinite(x) and not np.isfinite(y):
                    continue
                tot += 1
                if abs(x - y) > tol:
                    bad += 1
                    say(f"  !! L{lev} {p:20s} {tc:18s} builder {x:.6f} vs mine {y:.6f} "
                        f"(d={x - y:+.3g})")
        say(f"  level {lev}: {len(sub)} policies re-derived from 5 overlays")
    cells = load(src, "k1", [0], 0, "main")
    if cells is not None:
        A = aggregate(cells)
        sub = K1.set_index("policy")
        for p in sub.index:
            for tc, mc, tol in COLMAP:
                if mc not in A.columns or tc not in sub.columns:
                    continue
                if p == "FCFS" and tc == "qw_fired":
                    continue
                x, y = float(sub.loc[p, tc]), float(A.loc[p, mc])
                if not np.isfinite(x) and not np.isfinite(y):
                    continue
                tot += 1
                if abs(x - y) > tol:
                    bad += 1
                    say(f"  !! k1 {p:20s} {tc:18s} builder {x:.6f} vs mine {y:.6f} "
                        f"(d={x - y:+.3g})")
        say(f"  k = 1 cell: {len(sub)} policies re-derived")
    say(f"  {label}: {tot} numbers, {bad} mismatches")
    return tot, bad


# --------------------------------------------------------------------------- #
def part4(txt):
    say("")
    say("=" * 96)
    say("4. SECTION 8 COUNTS, AND THE BOUNDS ON MY OWN WAITS (V5)")
    say("=" * 96)
    gv = pd.concat([pd.read_csv(os.path.join(BSIM, f))
                    for f in sorted(os.listdir(BSIM)) if f.endswith("_main.csv")])
    gg = pd.concat([pd.read_csv(os.path.join(BSIM, f))
                    for f in sorted(os.listdir(BSIM)) if f.endswith("_grid.csv")])
    a, b = gv[gv.bound_viol >= 0], gg[gg.bound_viol >= 0]
    say(f"  builder cells: reported guarded runs {len(a)}, per-job checks "
        f"{int(a.n_jobs.sum()):,}, violations {int(a.bound_viol.sum())}")
    say(f"                 grid guarded runs {len(b)}, per-job checks "
        f"{int(b.n_jobs.sum()):,}, violations {int(b.bound_viol.sum())}")
    for pat, val in (("reported runs: (\\d+) guarded", len(a)),
                     ("reported runs: \\d+ guarded \\(trace x overlay x level x policy\\), "
                      "([\\d,]+) per-job checks", f"{int(a.n_jobs.sum()):,}"),
                     ("selection grid: (\\d+) guarded runs", len(b)),
                     ("selection grid: \\d+ guarded runs, ([\\d,]+) per-job checks",
                      f"{int(b.n_jobs.sum()):,}")):
        m = re.search(pat, txt)
        say(f"    report says {m.group(1)!r}; recomputed {val!r}  "
            f"MATCH={str(m.group(1)) == str(val)}")
    m = re.search(r"worst used/allowed anywhere in the reported runs: ([\d.]+) "
                  r"\(policy (\S+), trace (\S+), k = (\d+)\)", txt)
    say(f"    report worst used/allowed {m.group(1)} at {m.group(2)} / {m.group(3)} "
        f"k={m.group(4)}")

    mycells = [f for f in sorted(os.listdir(MINE)) if f.endswith(".csv")]
    d = pd.concat([pd.read_csv(os.path.join(MINE, f)) for f in mycells])
    g = d[d.bound_viol >= 0].reset_index(drop=True)
    say("")
    say(f"  MY cells: {len(mycells)} cells, {len(g)} guarded runs, "
        f"{int(g.nchecks.sum()):,} per-job checks on MY OWN waits")
    say(f"    violations, combined bound      : {int(g.bound_viol.sum())}")
    say(f"    violations, Theorem A (B_max)   : "
        f"{int(g[g.bound_violA >= 0].bound_violA.sum())} over "
        f"{int(g[g.bound_violA >= 0].nchecks.sum()):,} checks")
    say(f"    violations, Theorem B (eta)     : "
        f"{int(g[g.bound_violB >= 0].bound_violB.sum())} over "
        f"{int(g[g.bound_violB >= 0].nchecks.sum()):,} checks")
    say(f"    worst used/allowed, combined    : {g.used_over_allowed.max():.4f} "
        f"({g.loc[g.used_over_allowed.idxmax(), 'policy']}, "
        f"{g.loc[g.used_over_allowed.idxmax(), 'trace']} k="
        f"{int(g.loc[g.used_over_allowed.idxmax(), 'k'])})")
    for kk, sub in g.groupby("k"):
        say(f"      k = {int(kk)}: worst used/allowed {sub.used_over_allowed.max():.4f} "
            f"(Thm A {sub.usedA.max():.4f}, Thm B "
            f"{sub[sub.usedB.notna()].usedB.max() if sub.usedB.notna().any() else float('nan'):.4f})")


# --------------------------------------------------------------------------- #
def part5():
    """V6: the adversarial rows at G = 600, rho 1.0, from my own cells."""
    say("")
    say("=" * 96)
    say("5. ADVERSARIAL ROWS AT G = 600, rho 1.0 (V6), MY OWN SIMULATIONS")
    say("=" * 96)
    A = pd.read_csv(os.path.join(V31, "report_adversarial.csv"))
    cells = load(MINE, "primary", range(5), 2, "main")
    T = aggregate(cells)
    say("   policy                  p99_dl (builder / mine)     max_excess "
        "(builder / mine)    harm (b/m)")
    nbad = 0
    for adv in ("reversed", "random", "top1short"):
        for pol in (f"SPJF-{adv}", f"CAP-G600-{adv}"):
            r = A[(A.level == 2) & (A.policy == pol)].iloc[0]
            m = T.loc[pol]
            d1 = abs(r.p99_dl_s - m.w_p99_dl)
            d2 = abs(r.max_excess_s - m.max_excess)
            d3 = abs(r.harm_wf1s_s - m.harm_wf1s)
            nbad += sum(x > 5e-3 for x in (d1, d2, d3))
            say(f"   {pol:22s} {r.p99_dl_s:10.3f} / {m.w_p99_dl:10.3f}   "
                f"{r.max_excess_s:10.3f} / {m.max_excess:10.3f}   "
                f"{r.harm_wf1s_s:9.3f} / {m.harm_wf1s:9.3f}")
    say(f"   mismatches beyond the printed precision: {nbad}")
    # single-overlay rep0 numbers, for comparison with the v3 verifier's log
    c0 = pd.read_csv(os.path.join(MINE, "primary_rep0_L2_main.csv")).set_index("policy")
    say(f"   (overlay 0 alone: SPJF-top1short p99_dl {c0.loc['SPJF-top1short','w_p99_dl']:.4f}, "
        f"max excess {c0.loc['SPJF-top1short','max_excess']:.2f}; "
        f"CAP-G600-top1short p99_dl {c0.loc['CAP-G600-top1short','w_p99_dl']:.4f}, "
        f"max excess {c0.loc['CAP-G600-top1short','max_excess']:.2f}, "
        f"harm {c0.loc['CAP-G600-top1short','harm_wf1s']:.2f})")


def main():
    txt = open(REP, encoding="utf-8").read()
    t1, b1 = part1(txt)
    t2, b2 = part23(BSIM, "2. report_*.csv vs THE BUILDER'S OWN PER-CELL FILES")
    t3, b3 = part23(MINE, "3. report_*.csv vs MY OWN RE-SIMULATED CELLS")
    part4(txt)
    part5()
    say("")
    say("=" * 96)
    say(f"SUMMARY  printed-vs-csv {t1} numbers / {b1} bad; "
        f"csv-vs-builder-cells {t2} / {b2}; csv-vs-MY-cells {t3} / {b3}")
    say("=" * 96)
    open(os.path.join(HERE, "out_trace.txt"), "w",
         encoding="utf-8").write("\n".join(OUT) + "\n")


if __name__ == "__main__":
    main()
