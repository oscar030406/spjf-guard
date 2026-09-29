"""V1 (paper-side): re-derive the 15-cell selection outcome from the builder's own
artefacts, independently of v31_select.py, and check the validation pool.

  (a) rebuild select_grid.csv from the raw cell csv files <scratch>/mv31/sim/
      valid_rep{0..4}_L{0,1,2}_grid.csv (gap, harm, feasibility recomputed here);
  (b) apply the rule stated in section 3 of out_main_v31.txt to BOTH families and
      compare with selected_params.csv and with the printed section-3 table;
  (c) FIX family: is it judged by the identical rule, and is it infeasible at every G;
  (d) validation pool: no 2022-2 job, by the structural sub-multiset argument.
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
SCRATCH = r"<cache-dir>"
SIM = os.path.join(SCRATCH, "mv31", "sim")
TR = os.path.join(SCRATCH, "mv31", "traces")
OUT = []
GS = (300.0, 600.0, 1200.0)
FIXS = 1e9


def say(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    OUT.append(s)


def rebuild_grid():
    """select_grid.csv, recomputed from the raw cells by my own code."""
    rows = []
    for rep in range(5):
        for lev in range(3):
            d = pd.read_csv(os.path.join(SIM, f"valid_rep{rep}_L{lev}_grid.csv"))
            s = d.set_index("policy")
            f99 = float(s.loc["FCFS", "w_p99_dl"])
            s99 = float(s.loc["SJF-ref", "w_p99_dl"])
            for p in s.index:
                if s.loc[p, "guard"] not in ("cap", "fix"):
                    continue
                k = float(s.loc[p, "k"])
                rows.append(dict(
                    rep=rep, level=lev, k=k, policy=p, G=float(s.loc[p, "G"]),
                    guard=s.loc[p, "guard"],
                    B0_base=(FIXS if s.loc[p, "guard"] == "fix"
                             else float(s.loc[p, "B0"]) * 4.0 / k),
                    eta=float(s.loc[p, "eta"]),
                    gap=(f99 - float(s.loc[p, "w_p99_dl"])) / (f99 - s99),
                    red_pct=100.0 * (f99 - float(s.loc[p, "w_p99_dl"])) / f99,
                    harm=float(s.loc[p, "harm_wf1s"]),
                    w_p99_dl=float(s.loc[p, "w_p99_dl"]),
                    used_over_allowed=float(s.loc[p, "used_over_allowed"])))
    return pd.DataFrame(rows)


def choose(agg, pool_mask, Gv):
    """the rule of section 3, implemented here from its English statement."""
    pool = agg[(agg.G == Gv) & pool_mask(agg)]
    ok = pool[pool.worst_harm <= Gv * 0.5]
    fell_back = False
    if not len(ok):
        ok = pool.sort_values("worst_harm").head(1)
        fell_back = True
    best = ok.sort_values(["worst_gap", "worst_harm", "B0_base", "eta"],
                          ascending=[False, True, True, True]).iloc[0]
    return best, int((pool.worst_harm <= Gv * 0.5).sum()), len(pool), fell_back


def main():
    txt = open(REP, encoding="utf-8").read()

    say("=" * 96)
    say("A. select_grid.csv REBUILT FROM THE RAW CELLS")
    say("=" * 96)
    mine = rebuild_grid()
    theirs = pd.read_csv(os.path.join(V31, "select_grid.csv"))
    say(f"  rows: mine {len(mine)}, builder {len(theirs)}  "
        f"(expected 48 configs x 15 cells = 720)")
    key = ["rep", "level", "policy"]
    m = mine.set_index(key).sort_index()
    t = theirs.set_index(key).sort_index()
    say(f"  index identical: {m.index.equals(t.index)}")
    worst = {}
    for c in ["k", "G", "B0_base", "eta", "gap", "red_pct", "harm", "w_p99_dl",
              "used_over_allowed"]:
        worst[c] = float(np.nanmax(np.abs(m[c].values - t[c].values)))
    say("  max |mine - builder| per column: "
        + ", ".join(f"{c}={v:.3g}" for c, v in worst.items()))
    fz = pd.Series(mine.harm.values <= mine.G.values * 0.5,
                   index=pd.MultiIndex.from_frame(mine[key])).sort_index()
    say(f"  feasible_cell flag disagreements: "
        f"{int((fz.values != t.feasible_cell.values).sum())}")
    say(f"  cells: {len(set(zip(mine.rep, mine.level)))}  "
        f"(5 validation overlays x 3 levels)")
    say(f"  k per cell: {dict(sorted({(r, l): int(g.k.iloc[0]) for (r, l), g in mine.groupby(['rep', 'level'])}.items()))}")

    say("")
    say("=" * 96)
    say("B. THE RULE, APPLIED HERE")
    say("=" * 96)
    agg = (mine.groupby(["G", "guard", "B0_base", "eta"], dropna=False)
           .agg(worst_gap=("gap", "min"), worst_harm=("harm", "max"),
                worst_red=("red_pct", "min"), mean_gap=("gap", "mean"),
                n_cells=("gap", "size"),
                n_feas_cells=("gap", "size"),
                max_used=("used_over_allowed", "max")).reset_index())
    nfc = (mine.assign(f=mine.harm <= mine.G * 0.5)
           .groupby(["G", "guard", "B0_base", "eta"]).f.sum().reset_index())
    agg = agg.drop(columns=["n_feas_cells"]).merge(nfc, on=["G", "guard", "B0_base", "eta"])
    assert (agg.n_cells == 15).all()
    sw = pd.read_csv(os.path.join(V31, "select_worst.csv"))
    j = agg.merge(sw, on=["G", "guard", "B0_base", "eta"], suffixes=("_mine", "_b"))
    say(f"  select_worst.csv rows {len(sw)}, joined {len(j)}")
    for c in ["worst_gap", "worst_harm", "worst_red", "mean_gap", "max_used"]:
        say(f"    max |mine - builder| {c:11s} = "
            f"{np.nanmax(np.abs(j[c + '_mine'] - j[c + '_b'])):.3g}")
    say(f"    n_feasible_cells disagreements: {int((j.f != j.n_feasible_cells).sum())}")

    sel = pd.read_csv(os.path.join(V31, "selected_params.csv"))
    say("")
    say("  family  G      my pick             builder pick        n_feas(mine/builder)  "
        "worst_gap  worst_harm")
    nbad = 0
    for Gv in GS:
        for fam, mask in (("cap", lambda a: a.guard == "cap"),
                          ("fixsel", lambda a: (a.guard == "fix")
                           | ((a.guard == "cap") & (a.eta == 0.0)))):
            best, nf, ng, fb = choose(agg, mask, Gv)
            b = sel[(sel.family == fam) & (sel.G == Gv)].iloc[0]
            same = (abs(best.B0_base - b.B0_base) < 1e-9
                    and abs(best.eta - b.eta) < 1e-9)
            nbad += 0 if same else 1
            nbad += 0 if (nf == b.n_feasible and ng == b.n_grid) else 1
            nbad += 0 if abs(round(float(best.worst_gap), 4) - b.worst_gap) < 5e-5 else 1
            nbad += 0 if abs(round(float(best.worst_harm), 2)
                             - b.worst_harm_s) < 5e-3 else 1
            say(f"  {fam:7s} {Gv:6.0f}  B0={best.B0_base:>9.0f} eta={best.eta:4.2f}   "
                f"B0={b.B0_base:>9.0f} eta={b.eta:4.2f}   {nf:2d}/{ng} vs "
                f"{b.n_feasible:2d}/{b.n_grid}   {best.worst_gap:.4f}/{b.worst_gap:.4f}  "
                f"{best.worst_harm:.2f}/{b.worst_harm_s:.2f}  SAME={same} fellback={fb}")
    say(f"  DISAGREEMENTS with selected_params.csv: {nbad}")

    say("")
    say("  the v3 choice under the new rule (report section 3 claims):")
    for Gv, (b0, e) in ((300.0, (30.0, 0.5)), (600.0, (30.0, 0.9)), (1200.0, (120.0, 0.9))):
        r = agg[(agg.G == Gv) & (agg.guard == "cap") & np.isclose(agg.B0_base, b0)
                & np.isclose(agg.eta, e)].iloc[0]
        say(f"    G={Gv:6.0f} v3=({b0:g}*k/4, {e}): worst_gap {r.worst_gap:.4f}  "
            f"worst_harm {r.worst_harm:.2f} s  limit {Gv * 0.5:.0f}  "
            f"feasible={bool(r.worst_harm <= Gv * 0.5)}  feasible cells {int(r.f)}/15")
    # the two headline harm numbers
    r600 = agg[(agg.G == 600.0) & (agg.guard == "cap") & np.isclose(agg.B0_base, 30.0)
               & np.isclose(agg.eta, 0.9)].iloc[0]
    rsel = agg[(agg.G == 600.0) & (agg.guard == "cap") & np.isclose(agg.B0_base, 120.0)
               & np.isclose(agg.eta, 0.75)].iloc[0]
    say(f"    claimed 358.9 s for the REJECTED v3 G=600 setting -> {r600.worst_harm:.2f} "
        f"MATCH={abs(r600.worst_harm - 358.9) < 0.05}")
    say(f"    claimed 293.3 s for the SELECTED G=600 setting     -> {rsel.worst_harm:.2f} "
        f"MATCH={abs(rsel.worst_harm - 293.3) < 0.05}")
    wc = mine[(mine.G == 600.0) & (mine.guard == "cap") & np.isclose(mine.B0_base, 30.0)
              & np.isclose(mine.eta, 0.9)].sort_values("harm", ascending=False)
    say("    worst cells for the rejected setting (harm, rep, level):")
    for r in wc.head(5).itertuples():
        say(f"       harm {r.harm:8.2f} s  rep {r.rep} level {r.level}  gap {r.gap:.4f}")
    wc2 = mine[(mine.G == 600.0) & (mine.guard == "cap") & np.isclose(mine.B0_base, 120.0)
               & np.isclose(mine.eta, 0.75)].sort_values("harm", ascending=False)
    say("    worst cells for the selected setting:")
    for r in wc2.head(3).itertuples():
        say(f"       harm {r.harm:8.2f} s  rep {r.rep} level {r.level}  gap {r.gap:.4f}")
    wg = mine[(mine.G == 600.0) & (mine.guard == "cap") & np.isclose(mine.B0_base, 120.0)
              & np.isclose(mine.eta, 0.75)].sort_values("gap")
    say(f"    worst-GAP cell for the selected setting: gap {wg.gap.iloc[0]:.4f} at "
        f"rep {wg.rep.iloc[0]} level {wg.level.iloc[0]}")

    say("")
    say("=" * 96)
    say("C. THE FIXED-BUDGET FAMILY UNDER THE SAME RULE")
    say("=" * 96)
    for Gv in GS:
        fx = agg[(agg.G == Gv) & (agg.guard == "fix")].iloc[0]
        say(f"  G={Gv:6.0f}  FIX (eta=0, B0=Bmax): worst_gap {fx.worst_gap:.4f}  "
            f"worst_harm {fx.worst_harm:.2f} s  limit {Gv * 0.5:.0f}  "
            f"FEASIBLE={bool(fx.worst_harm <= Gv * 0.5)}  ({int(fx.f)}/15 cells)")
        sub = agg[(agg.G == Gv) & (((agg.guard == "fix")
                                    | ((agg.guard == "cap") & (agg.eta == 0.0))))]
        say(f"           fixsel pool ({len(sub)} points):")
        for r in sub.sort_values("B0_base").itertuples():
            say(f"             B0_base={r.B0_base:>9.0f} eta={r.eta:4.2f} "
                f"worst_gap {r.worst_gap:7.4f} worst_harm {r.worst_harm:7.2f} "
                f"feasible={bool(r.worst_harm <= Gv * 0.5)}")
    say("  claim 'FIX infeasible at all three G': "
        f"{all(agg[(agg.G == g) & (agg.guard == 'fix')].worst_harm.iloc[0] > g * 0.5 for g in GS)}")
    say("  claim 'FIXSEL = 120*k/4 at G=300, 600*k/4 at G=600 and 1200': "
        f"{[float(sel[(sel.family == 'fixsel') & (sel.G == g)].B0_base.iloc[0]) for g in GS]}")

    say("")
    say("=" * 96)
    say("D. SECTION 3 TABLE OF out_main_v31.txt, NUMBER BY NUMBER")
    say("=" * 96)
    blk = txt.split("3. GUARD PARAMETERS UNDER THE RESTATED RULE (F8)")[1].split(
        "4. MAIN RESULTS")[0]
    nmis = 0
    for ln in blk.splitlines():
        p = ln.split()
        if len(p) < 10 or p[0] not in ("cap", "fixsel"):
            continue
        fam = p[0]
        Gv = float(p[1])
        b = sel[(sel.family == fam) & (sel.G == Gv)].iloc[0]
        # printed: family G B0 '*' 'k/4' 's' eta worst_gap worst_harm limit nfeas ngrid ...
        b0p, etap = float(p[2]), float(p[6])
        gapp, harmp, limp = float(p[7]), float(p[8]), float(p[9])
        nfp, ngp = int(p[10]), int(p[11])
        best, nf, ng, _ = choose(agg, (lambda a: a.guard == "cap") if fam == "cap"
                                 else (lambda a: (a.guard == "fix")
                                       | ((a.guard == "cap") & (a.eta == 0.0))), Gv)
        chk = [("B0", b0p, float(best.B0_base), 1e-9),
               ("eta", etap, float(best.eta), 1e-9),
               ("worst_gap", gapp, float(best.worst_gap), 5e-5),
               ("worst_harm", harmp, float(best.worst_harm), 5e-3),
               ("limit", limp, Gv * 0.5, 1e-9),
               ("n_feasible", nfp, nf, 0.5), ("n_grid", ngp, ng, 0.5)]
        bad = [c for c, x, y, tol in chk if abs(x - y) > tol]
        nmis += len(bad)
        say(f"  {fam:7s} G={Gv:6.0f}  printed vs mine OK"
            + ("" if not bad else f"  MISMATCH in {bad}"))
    say(f"  section-3 mismatches: {nmis}")

    say("")
    say("=" * 96)
    say("E. VALIDATION POOL: NO 2022-2 JOB")
    say("=" * 96)
    zp = np.load(os.path.join(TR, "primary_rep0.npz"))
    zv = np.load(os.path.join(TR, "valid_rep0.npz"))
    cp, cv = int(zp["copies"]), int(zv["copies"])
    np_, nv_ = len(zp["a"]), len(zv["a"])
    say(f"  primary rep0: {cp} copies x {np_ // cp:,} jobs = {np_:,}")
    say(f"  valid   rep0: {cv} copies x {nv_ // cv:,} jobs = {nv_:,}")
    # per-copy service multiset, taken over the WHOLE array and divided by the copy
    # count, so the test does not assume a contiguous copy-major layout.
    def percopy(z, c):
        us = np.rint(np.asarray(z["svc"], np.float64) * 1e6).astype(np.int64)
        u, n = np.unique(us, return_counts=True)
        assert (n % c == 0).all(), "service multiset is not c identical copies"
        return u, n // c
    up, cnp = percopy(zp, cp)
    uv, cnv = percopy(zv, cv)
    idx = np.searchsorted(up, uv)
    missing = int(((idx >= len(up)) | (up[np.minimum(idx, len(up) - 1)] != uv)).sum())
    over = 0 if missing else int((cnv > cnp[idx]).sum())
    say(f"  per-copy service multiset of valid is a sub-multiset of primary: "
        f"values absent from primary {missing}, values with a larger count {over}  "
        f"(jobs removed per copy {np_ // cp - nv_ // cv:,})")
    say(f"  distinct service values: primary {len(up):,}, valid {len(uv):,}; "
        f"per-copy jobs primary {int(cnp.sum()):,} valid {int(cnv.sum()):,}")
    ts = pd.read_csv(os.path.join(V31, "trace_summary.csv"))
    say(f"  trace_summary class_semesters: primary "
        f"{int(ts[(ts.trace == 'primary') & (ts.rep == 0)].class_semesters.iloc[0])}, "
        f"valid {int(ts[(ts.trace == 'valid') & (ts.rep == 0)].class_semesters.iloc[0])}, "
        f"t222 {int(ts[ts.trace == 't222'].class_semesters.iloc[0])}  -> "
        f"40 - 32 = 8 = the 2022-2 count: "
        f"{int(ts[(ts.trace == 'primary') & (ts.rep == 0)].class_semesters.iloc[0]) - int(ts[(ts.trace == 'valid') & (ts.rep == 0)].class_semesters.iloc[0]) == int(ts[ts.trace == 't222'].class_semesters.iloc[0])}")
    src = open(os.path.join(V31, "v31_common.py"), encoding="utf-8").read()
    mm = re.search(r'def pool_of.*?raise SystemExit\(trace\)', src, re.S)
    say("  code path (v31_common.pool_of):")
    for ln in mm.group(0).splitlines():
        say("    " + ln)
    say(f'  TEST_SEM = {re.search(chr(34) + "?TEST_SEM = .*", src).group(0)}')
    say("  NOTE: the npz carries no semester label, so this is a structural + code check,")
    say("        exactly as the v3 verifier recorded it.")

    open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "out_select.txt"),
         "w", encoding="utf-8").write("\n".join(OUT) + "\n")


if __name__ == "__main__":
    main()
