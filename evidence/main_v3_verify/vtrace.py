"""C3: does every number printed in out_main_v3.txt come from a cell that exists on disk?

The report's tables are parsed out of the text, then every quantity is recomputed here
from the per-cell simulator outputs -- first from the builder's own cells
(<scratch>/mv3/sim/*.csv), then, where my rerun exists, from MY cells
(<scratch>/mv3_verify/vcell_*.csv).  Aggregation rules are re-derived from the report's
own footnote: "max_excess / harm / max_heavy are the worst over the five overlays; the
rest are means over them".

usage: vtrace.py [--mine]        (--mine compares against my own simulator's cells)
"""
from __future__ import annotations

import argparse
import os
import re

import numpy as np
import pandas as pd

from vsim import SCRATCH

MAIN = r"<repo-root>\evidence\main_v3"
BSIM = os.path.join(SCRATCH, "mv3", "sim")
MSIM = os.path.join(SCRATCH, "mv3_verify")
REPORT = os.path.join(MAIN, "out_main_v3.txt")
REPS = [0, 1, 2, 3, 4]


def load_cells(level, mine, trace="primary", reps=REPS):
    out = {}
    for r in reps:
        p = (os.path.join(MSIM, f"vcell_{trace}_rep{r}_L{level}.csv") if mine else
             os.path.join(BSIM, f"{trace}_rep{r}_L{level}_main.csv"))
        if not os.path.exists(p):
            return None
        out[r] = pd.read_csv(p).set_index("policy")
    return out


def agg(cells, policy):
    reps = sorted(cells)
    if not all(policy in cells[r].index for r in reps):
        return None
    g = lambda c: np.array([float(cells[r].loc[policy, c]) for r in reps])   # noqa: E731
    F = np.array([float(cells[r].loc["FCFS", "w_p99_dl"]) for r in reps])
    S = np.array([float(cells[r].loc["SJF-ref", "w_p99_dl"]) for r in reps])
    P = g("w_p99_dl")
    Fm = np.array([float(cells[r].loc["FCFS", "w_mean"]) for r in reps])
    Sm = np.array([float(cells[r].loc["SJF-ref", "w_mean"]) for r in reps])
    d = dict(p99_dl_s=P.mean(), gap_closed=float(np.mean((F - P) / (F - S))),
             red_pct=float(np.mean(100.0 * (F - P) / F)), mean_s=g("w_mean").mean(),
             mean_gap=float(np.mean((Fm - g("w_mean")) / (Fm - Sm))),
             p99_all_s=g("w_p99").mean(), max_excess_s=g("max_excess").max(),
             harm_s=g("harm_wf1s").max(), harm_wf1s_s=g("harm_wf1s").max(),
             max_heavy_s=g("max_heavy").max(), qw_fired=g("qw_forced_frac").mean())
    if "used_over_allowed" in cells[reps[0]].columns:
        u = g("used_over_allowed")
        if np.isfinite(u).all():
            d["used_over_allowed"] = u.max()
    return d


def parse_main(txt):
    """section 3: one block per level."""
    out = {}
    for m in re.finditer(r"--- level (\d): target busy-hour rho ([\d.]+), k = (\d+) ---\n"
                         r"(.*?)\n\n", txt, re.S):
        lev = int(m.group(1))
        rows = {}
        for line in m.group(4).splitlines()[1:]:
            tk = line.split()
            if len(tk) != 14:
                raise SystemExit(f"level {lev}: cannot parse {line!r}")
            rows[tk[0]] = dict(
                p99_dl_s=float(tk[1]), gap_closed=float(tk[2]), red_pct=float(tk[4]),
                mean_s=float(tk[6]), mean_gap=float(tk[7]), p99_all_s=float(tk[9]),
                max_excess_s=float(tk[10]), harm_s=float(tk[11]),
                max_heavy_s=float(tk[12]), qw_fired=float(tk[13]))
        out[lev] = rows
    return out


def parse_table(txt, start, ncols_names):
    """a plain pandas to_string table: header line then rows."""
    i = txt.index(start)
    blk = txt[i:].splitlines()
    hdr = None
    rows = []
    for line in blk:
        tk = line.split()
        if hdr is None:
            if tk[:len(ncols_names)] == ncols_names:
                hdr = tk
            continue
        if not tk or len(tk) != len(hdr):
            if rows:
                break
            continue
        rows.append(tk)
    return hdr, rows


def cmp(tag, a, b, tol, bad):
    if b is None or not np.isfinite(b) or not np.isfinite(a):
        return
    if abs(a - b) > tol:
        bad.append(f"{tag}: report {a} vs recomputed {b:.6f} (diff {a - b:+.6f})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mine", action="store_true")
    args = ap.parse_args()
    txt = open(REPORT, encoding="utf-8").read()
    bad, checked, skipped = [], 0, 0

    # ---- section 3, the main table
    for lev, rows in parse_main(txt).items():
        cells = load_cells(lev, args.mine)
        if cells is None:
            print(f"level {lev}: no {'my' if args.mine else 'builder'} cells on disk")
            skipped += len(rows) * 10
            continue
        for pol, r in rows.items():
            a = agg(cells, pol)
            if a is None:
                bad.append(f"L{lev} {pol}: NOT FOUND in the per-cell csv files")
                continue
            for key, tol in (("p99_dl_s", 5e-3), ("gap_closed", 5e-4), ("red_pct", 5e-2),
                             ("mean_s", 5e-4), ("mean_gap", 5e-4), ("p99_all_s", 5e-3),
                             ("max_excess_s", 5e-2), ("harm_s", 5e-2),
                             ("max_heavy_s", 5e-2), ("qw_fired", 5e-5)):
                cmp(f"L{lev} {pol} {key}", r[key], a[key], tol, bad)
                checked += 1

    # ---- section 5, adversarial predictors
    hdr, rows = parse_table(txt, "5. ADVERSARIAL PREDICTORS",
                            ["level", "rho_target", "k", "policy"])
    for tk in rows:
        d = dict(zip(hdr, tk))
        lev = int(d["level"])
        cells = load_cells(lev, args.mine)
        if cells is None:
            skipped += 5
            continue
        a = agg(cells, d["policy"])
        if a is None:
            if not args.mine:
                bad.append(f"adversarial L{lev} {d['policy']}: NOT FOUND in the per-cell csvs")
            skipped += 5
            continue
        for key, tol in (("p99_dl_s", 5e-3), ("gap_closed", 5e-3), ("red_pct", 5e-3),
                         ("mean_s", 5e-3), ("max_excess_s", 5e-3),
                         ("harm_wf1s_s", 5e-3), ("max_heavy_s", 5e-3),
                         ("qw_fired", 5e-4)):
            if key in d:
                cmp(f"adv L{lev} {d['policy']} {key}", float(d[key]), a[key], tol, bad)
                checked += 1

    # ---- section 6, k = 1
    hdr, rows = parse_table(txt, "6. SINGLE-SERVER CONFIGURATION", ["policy", "score"])
    k1 = load_cells(0, args.mine, trace="k1", reps=[0])
    for tk in rows:
        d = dict(zip(hdr, tk))
        if k1 is None:
            skipped += 5
            continue
        a = agg(k1, d["policy"])
        if a is None:
            if not args.mine:
                bad.append(f"k1 {d['policy']}: NOT FOUND in the per-cell csv")
            skipped += 5
            continue
        for key, tol in (("p99_dl_s", 5e-4), ("gap_closed", 5e-4), ("red_pct", 5e-4),
                         ("mean_s", 5e-4), ("max_excess_s", 5e-4),
                         ("harm_wf1s_s", 5e-4), ("max_heavy_s", 5e-4),
                         ("qw_fired", 5e-5)):
            if key in d:
                cmp(f"k1 {d['policy']} {key}", float(d[key]), a[key], tol, bad)
                checked += 1

    # ---- section 9, capped vs fixed at equal G
    hdr, rows = parse_table(txt, "9. WHAT THE CAPPED BUDGET BUYS",
                            ["trace", "level", "k", "G"])
    for tk in rows:
        d = dict(zip(hdr, tk))
        lev = int(d["level"])
        cells = (load_cells(lev, args.mine) if d["trace"] == "primary"
                 else load_cells(0, args.mine, trace="k1", reps=[0]))
        if cells is None:
            skipped += 5
            continue
        G = float(d["G"])
        af = agg(cells, f"FIX-G{G:g}")
        ac = agg(cells, f"CAP-G{G:g}")
        if af is None or ac is None:
            skipped += 5
            continue
        cmp(f"sec9 {d['trace']} L{lev} G{G:g} gap_fix", float(d["gap_fix"]),
            af["gap_closed"], 5e-4, bad)
        cmp(f"sec9 {d['trace']} L{lev} G{G:g} gap_cap", float(d["gap_cap"]),
            ac["gap_closed"], 5e-4, bad)
        cmp(f"sec9 {d['trace']} L{lev} G{G:g} harm_fix", float(d["harm_fix_s"]),
            af["harm_s"], 5e-2, bad)
        cmp(f"sec9 {d['trace']} L{lev} G{G:g} harm_cap", float(d["harm_cap_s"]),
            ac["harm_s"], 5e-2, bad)
        cmp(f"sec9 {d['trace']} L{lev} G{G:g} harm_ratio", float(d["harm_ratio"]),
            af["harm_s"] / ac["harm_s"], 5e-3, bad)
        checked += 5

    # ---- section 4, the paired differences, against gaindiff_<trace>.csv
    gd = pd.read_csv(os.path.join(MAIN, "gaindiff_primary.csv"))
    gd = gd[(gd.metric == "p99dl") & (gd.quantity == "gain")].set_index(["level", "pair"])
    i = txt.index("4. DIFFERENCES")
    for line in txt[i:].splitlines():
        m = re.match(r"\s*(\d)\s+(\S+ - \S+)\s+(.*?)\s+(-?[\d.]+) \[(-?[\d.]+),"
                     r"(-?[\d.]+)\]\s+(True|False)\s+(.*)$", line)
        if not m:
            if line.startswith("---") and "DIFFERENCES" not in line and checked > 900:
                break
            continue
        lev, pair = int(m.group(1)), m.group(2)
        if (lev, pair) not in gd.index:
            bad.append(f"sec4 L{lev} {pair}: no row in gaindiff_primary.csv")
            continue
        r = gd.loc[(lev, pair)]
        for j, col in ((4, "diff"), (5, "lo"), (6, "hi")):
            cmp(f"sec4 L{lev} {pair} {col}", float(m.group(j)), float(r[col]), 5e-4, bad)
            checked += 1
        if bool(r["resolved"]) != (m.group(7) == "True"):
            bad.append(f"sec4 L{lev} {pair}: resolved flag differs")

    # ---- section 7, the per-job bound table, against the per-cell csv files
    hdr, rows = parse_table(txt, "7. THE PER-JOB THEOREM", ["trace", "level", "k", "policy"])
    for tk in rows:
        d = dict(zip(hdr, tk))
        lev = int(d["level"])
        cells = (load_cells(lev, args.mine) if d["trace"] == "primary"
                 else load_cells(0, args.mine, trace="k1", reps=[0]))
        if cells is None:
            skipped += 3
            continue
        reps = sorted(cells)
        p = d["policy"]
        if p not in cells[reps[0]].index:
            if not args.mine:
                bad.append(f"sec7 {d['trace']} L{lev} {p}: not in the per-cell csv")
            skipped += 2
            continue
        mx = max(float(cells[r].loc[p, "max_excess"]) for r in reps)
        uo = max(float(cells[r].loc[p, "used_over_allowed"]) for r in reps)
        cmp(f"sec7 {d['trace']} L{lev} {p} max_excess", float(d["max_excess_s"]), mx,
            5e-3, bad)
        cmp(f"sec7 {d['trace']} L{lev} {p} used_over_allowed",
            float(d["used_over_allowed"]), uo, 5e-4, bad)
        if not args.mine:
            for col in ("B0", "eta", "Bmax", "Ncap"):
                cmp(f"sec7 {d['trace']} L{lev} {p} {col}", float(d[col]),
                    float(cells[reps[0]].loc[p, col]), 1e-6, bad)
                checked += 1
        checked += 2

    src = "MY simulator's cells" if args.mine else "the builder's per-cell csv files"
    print(f"numbers checked against {src}: {checked}; not covered (cells missing): {skipped}")
    print(f"mismatches: {len(bad)}")
    for b in bad:
        print("  " + b)


if __name__ == "__main__":
    main()
