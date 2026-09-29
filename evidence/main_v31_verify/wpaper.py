"""Section 8 of the paper against v3.1's CSVs, number by number.  READ-ONLY on the paper.

Tables checked: tab:setup, tab:rank, tab:guard, tab:adv, tab:k1 (tab:scores comes from a
different study, evidence/ranking_score, and is out of scope here -- noted, not checked).
"""
from __future__ import annotations

import os
import re

import numpy as np
import pandas as pd

ROOT = r"<repo-root>"
V31 = os.path.join(ROOT, "evidence", "main_v3", "v31")
TEX = os.path.join(ROOT, "paper", "sections", "08_experiments.tex")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = []
BAD = []


def say(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    OUT.append(s)


def dn(line):
    """the \\devnum{...} payloads of one line, thousands separators removed"""
    return [x.replace("{,}", "").replace("\\", "").strip()
            for x in re.findall(r"\\devnum\{((?:[^{}]|\{[^{}]*\})*)\}", line)]


def cmp(tag, got, want):
    """got/want are lists of strings; compare as text after normalising numbers."""
    ok = len(got) == len(want)
    diffs = []
    for i, (g, w) in enumerate(zip(got, want)):
        gs, ws = g.replace(" ", "").replace(",", ""), w.replace(" ", "").replace(",", "")
        if gs != ws:
            ok = False
            diffs.append(f"[{i}] paper {g!r} vs csv {w!r}")
    if not ok:
        BAD.append((tag, got, want, diffs))
        say(f"  !! {tag}")
        say(f"     paper: {got}")
        say(f"     csv  : {want}")
        for d in diffs:
            say(f"     {d}")
    return ok


def f(x, d):
    return f"{x:.{d}f}"


def ci(v, lo, hi, d=3):
    return f"{v:.{d}f} [{lo:.{d}f}, {hi:.{d}f}]"


def main():
    import hashlib, time
    tex = open(TEX, encoding="utf-8").read()
    h = hashlib.sha256(open(TEX, "rb").read()).hexdigest()
    say(f"paper/sections/08_experiments.tex  sha256 {h}")
    say(f"  size {os.path.getsize(TEX)} bytes, mtime "
        f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(os.path.getmtime(TEX)))}")
    say("  NOTE: the paper is being edited in parallel while this runs; this check")
    say("        pins the version above.")
    say("")
    lines = tex.splitlines()
    M = pd.read_csv(os.path.join(V31, "report_main.csv"))
    T = pd.read_csv(os.path.join(V31, "table_main_primary.csv"))
    K1 = pd.read_csv(os.path.join(V31, "table_main_k1.csv"))
    A = pd.read_csv(os.path.join(V31, "report_adversarial.csv"))
    SEL = pd.read_csv(os.path.join(V31, "selected_params.csv"))
    TR = pd.read_csv(os.path.join(V31, "trace_summary.csv"))
    B = pd.read_csv(os.path.join(V31, "report_bound.csv"))
    nrow = 0

    # ------------------------------------------------------------------ setup
    say("=" * 96)
    say("tab:setup")
    say("=" * 96)
    p0 = TR[(TR.trace == "primary") & (TR.rep == 0)].iloc[0]
    k1r = TR[TR.trace == "k1"].iloc[0]
    pr = TR[TR.trace == "primary"]
    lo_ov = int(pr.busy_hour_work_s.idxmin())
    setup = {}
    for ln in lines[27:50]:
        if "&" in ln and "\\devnum" in ln:
            setup[ln.split("&")[0].strip()] = dn(ln)
    exp = {
        "Trace and pool": ["60", f"{int(p0.n_jobs):,}", f"{p0.n_weeks:.0f}"],
        "Load levels": ["8/5/4", "7/5/4", "0.529", "0.847", "1.059"],
        "Single-server configuration": [f"{int(k1r.copies)}", f"{int(k1r.n_jobs):,}",
                                        "0.80"],
        "Primary metric": ["24"],
        "Intervals": ["2{,}000".replace("{,}", ""), "30"],
        "Promise to parameter": ["60"],
        "Selection rule": ["15"],
    }
    for Gv, key in ((300.0, "Selected, $G = \\devnum{300}$ s"),
                    (600.0, "Selected, $G = \\devnum{600}$ s"),
                    (1200.0, "Selected, $G = \\devnum{1200}$ s")):
        r = SEL[(SEL.family == "cap") & (SEL.G == Gv)].iloc[0]
        exp[key] = [f"{Gv:.0f}", f"{r.B0_base:.0f}", f"{r.eta:.2f}",
                    f"{r.worst_gap:.4f}", f"{r.worst_harm_s:.1f}",
                    f"{r.harm_limit_s:.0f}", f"{int(r.n_feasible)}", f"{int(r.n_grid)}"]
    for key, want in exp.items():
        k2 = key if key in setup else next((s for s in setup if s.startswith(
            key.split("$")[0].strip())), None)
        got = setup.get(key) or (setup.get(k2) if k2 else None)
        if got is None:
            say(f"  !! row not found: {key}")
            BAD.append((key, None, want, []))
            continue
        nrow += 1
        cmp(f"tab:setup / {key}", got, want)
    # the sentence "the fifth, whose work per busy hour is the lowest"
    say(f"  busy-hour work per overlay: "
        f"{[round(x, 1) for x in pr.busy_hour_work_s.tolist()]}; the k = 7/5/4 overlay is "
        f"{pr[pr.k_per_rho == '7/5/4'].rep.tolist()}, the lowest-work overlay is "
        f"{int(pr.loc[lo_ov, 'rep'])}  MATCH="
        f"{pr[pr.k_per_rho == '7/5/4'].rep.tolist() == [int(pr.loc[lo_ov, 'rep'])]}")
    say(f"  admitted fixed budget rule: paper says 120k/4 at G=300 and 600k/4 at "
        f"G=600,1200; csv says "
        f"{[float(SEL[(SEL.family == 'fixsel') & (SEL.G == g)].B0_base.iloc[0]) for g in (300.0, 600.0, 1200.0)]}")

    # ------------------------------------------------------------------ rank
    say("")
    say("=" * 96)
    say("tab:rank")
    say("=" * 96)
    RANK = [("FCFS", "FCFS"), ("SJF", "SJF-ref"), ("SPJF-log", "SPJF-M4"),
            ("SPJF-log, refitted", "SPJF-M4refit"), ("SPJF-E", "SPJF-tweedie"),
            ("SPJF-E, GRU state", "SPJF-r1s")]
    blk = tex.split("\\label{tab:rank}")[1].split("\\end{tabular}")[0]
    for lev, head in ((0, "$\\rho = \\devnum{0.5}$, $k = \\devnum{8}$"),
                      (1, "$\\rho = \\devnum{0.8}$, $k = \\devnum{5}$"),
                      (2, "$\\rho = \\devnum{1.0}$, $k = \\devnum{4}$")):
        part = blk.split(head)[1].split("\\midrule")[0]
        tm = T[T.level == lev].set_index("policy")
        for lbl, pol in RANK:
            ln = next((x for x in part.splitlines()
                       if x.strip().startswith("& " + lbl + " ")
                       or x.strip().startswith("& " + lbl + "  ")), None)
            if ln is None:
                say(f"  !! L{lev} row {lbl} not found")
                BAD.append((f"tab:rank L{lev} {lbl}", None, None, []))
                continue
            r = tm.loc[pol]
            want = [f(r.p99_dl_s, 2)]
            want.append("0.000" if pol == "FCFS" else
                        "1.000" if pol == "SJF-ref" else
                        ci(r.gap_closed, r.gap_lo, r.gap_hi))
            want.append("0.0" if pol == "FCFS" else ci(r.red_pct, r.red_lo, r.red_hi, 1))
            want.append(f(r.mean_s, 3))
            nrow += 1
            cmp(f"tab:rank L{lev} {lbl}", dn(ln), want)

    # ------------------------------------------------------------------ guard
    say("")
    say("=" * 96)
    say("tab:guard")
    say("=" * 96)
    blk = tex.split("\\label{tab:guard}")[1].split("\\bottomrule")[0]
    for lev, head in ((0, "k = \\devnum{8}"), (1, "k = \\devnum{5}"),
                      (2, "k = \\devnum{4}")):
        part = blk.split(head)[1].split("\\midrule")[0]
        tm = T[T.level == lev].set_index("policy")
        hdr = blk.split(head)[0].splitlines()[-1] + head + \
            blk.split(head)[1].splitlines()[0]
        # the header line: FCFS p99_dl, SPJF-E p99_dl and its max excess
        hv = dn(hdr)
        nrow += 1
        cmp(f"tab:guard L{lev} header", hv[-3:],
            [f(tm.loc["FCFS", "p99_dl_s"], 2), f(tm.loc["SPJF-tweedie", "p99_dl_s"], 2),
             f(tm.loc["SPJF-tweedie", "max_excess_s"], 1)])
        rows = []
        for G in (300, 600, 1200):
            rows += [(f"Guard($\\devnum{{{G}}}$)", f"CAP-G{G}"),
                     (f"Fixed($\\devnum{{{G}}}$)", f"FIX-G{G}"),
                     (f"Skip($\\devnum{{{G}}}$)", f"SKIP-G{G}")]
        for lbl, pol in rows:
            ln = next((x for x in part.splitlines() if lbl in x), None)
            if ln is None:
                say(f"  !! L{lev} {lbl} not found")
                BAD.append((f"tab:guard L{lev} {lbl}", None, None, []))
                continue
            r = tm.loc[pol]
            want = [str(int(r.G))]
            if pol.startswith("SKIP"):
                mN = re.search(r"\$N=(\d+)\$", ln)
                nrow_n = str(int(r.Ncap))
                cmp(f"tab:guard L{lev} {lbl} N", [mN.group(1) if mN else "?"], [nrow_n])
            want += [str(int(r.G)), f(r.p99_dl_s, 2),
                     ci(r.gap_closed, r.gap_lo, r.gap_hi), f(r.red_pct, 1),
                     f(r.max_excess_s, 1), f(r.harm_wf1s_s, 1),
                     f(100.0 * r.qw_fired, 2)]
            nrow += 1
            cmp(f"tab:guard L{lev} {lbl}", dn(ln), want)
        # the two "Fixed, admitted" rows
        fs = [tm.loc[f"FIXSEL-G{G}"] for G in (300, 600, 1200)]
        uniq = []
        for r in fs:
            if not any(abs(r.guar_excess_s - u.guar_excess_s) < 1e-9 for u in uniq):
                uniq.append(r)
        adm = [x for x in part.splitlines() if "Fixed, admitted" in x]
        say(f"  L{lev}: distinct FIXSEL settings {len(uniq)} "
            f"(promises {[round(u.guar_excess_s, 1) for u in uniq]}), "
            f"paper prints {len(adm)} rows")
        for r, ln in zip(sorted(uniq, key=lambda x: x.guar_excess_s), adm):
            want = [f(r.guar_excess_s, 1), f(r.p99_dl_s, 2),
                    ci(r.gap_closed, r.gap_lo, r.gap_hi), f(r.red_pct, 1),
                    f(r.max_excess_s, 1), f(r.harm_wf1s_s, 1),
                    f(100.0 * r.qw_fired, 2)]
            nrow += 1
            cmp(f"tab:guard L{lev} Fixed-admitted {r.guar_excess_s:g}", dn(ln), want)

    # ------------------------------------------------------------------ adv
    say("")
    say("=" * 96)
    say("tab:adv")
    say("=" * 96)
    blk = tex.split("\\label{tab:adv}")[1].split("\\bottomrule")[0]
    names = {"reversed": "reversed", "random": "random",
             "longest as shortest": "top1short"}
    for lev in (0, 1, 2):
        sub = A[A.level == lev].set_index("policy")
        for lbl, adv in names.items():
            ln = next((x for x in blk.splitlines()
                       if re.search(r"&\s*" + re.escape(lbl) + r"\s*&", x)), None)
            cand = [x for x in blk.splitlines()
                    if re.search(r"&\s*" + re.escape(lbl) + r"\s*&", x)]
            ln = cand[lev] if len(cand) > lev else None
            if ln is None:
                say(f"  !! L{lev} {lbl} not found")
                continue
            u, g = sub.loc[f"SPJF-{adv}"], sub.loc[f"CAP-G600-{adv}"]
            want = ([] if lev == 0 and lbl == "reversed" else [])
            want = [f(u.p99_dl_s, 2), f(g.p99_dl_s, 2), f(u.max_excess_s, 1),
                    f(g.max_excess_s, 1), f(g.harm_wf1s_s, 1)]
            got = dn(ln)
            if got and got[0] in ("0.5", "0.8", "1.0"):
                got = got[1:]
            nrow += 1
            cmp(f"tab:adv L{lev} {lbl}", got, want)

    # ------------------------------------------------------------------ k1
    say("")
    say("=" * 96)
    say("tab:k1")
    say("=" * 96)
    blk = tex.split("\\label{tab:k1}")[1].split("\\bottomrule")[0]
    k1 = K1.set_index("policy")
    K1ROWS = [("FCFS", "FCFS"), ("SJF on true sizes", "SJF-ref"),
              ("SPJF-E", "SPJF-tweedie")]
    for G in (300, 600, 1200):
        K1ROWS += [(f"Guard($\\devnum{{{G}}}$)", f"CAP-G{G}"),
                   (f"Fixed($\\devnum{{{G}}}$)", f"FIX-G{G}"),
                   (f"Skip($\\devnum{{{G}}}$)", f"SKIP-G{G}")]
    for lbl, pol in K1ROWS:
        ln = next((x for x in blk.splitlines() if x.strip().startswith(lbl)
                   or lbl in x.split("&")[0]), None)
        if ln is None:
            say(f"  !! {lbl} not found")
            continue
        r = k1.loc[pol]
        want = []
        if pol.startswith(("CAP", "FIX", "SKIP")):
            if pol.startswith("SKIP"):
                mN = re.search(r"\$N=(\d+)\$", ln)
                cmp(f"tab:k1 {lbl} N", [mN.group(1) if mN else "?"],
                    [str(int(r.Ncap))])
            want += [str(int(r.G)), str(int(r.G))]
        want += [f(r.p99_dl_s, 2)]
        want.append("0.000" if pol == "FCFS" else "1.000" if pol == "SJF-ref"
                    else ci(r.gap_closed, r.gap_lo, r.gap_hi))
        want += [f(r.max_excess_s, 1), f(r.harm_wf1s_s, 1), f(100.0 * r.qw_fired, 2)]
        got = dn(ln)
        if got and got[0] == str(G if pol[-4:].isdigit() else ""):
            pass
        nrow += 1
        cmp(f"tab:k1 {lbl}", got, want)
    fs = [k1.loc[f"FIXSEL-G{G}"] for G in (300, 600, 1200)]
    uniq = []
    for r in fs:
        if not any(abs(r.guar_excess_s - u.guar_excess_s) < 1e-9 for u in uniq):
            uniq.append(r)
    adm = [x for x in blk.splitlines() if "Fixed, admitted" in x]
    say(f"  distinct FIXSEL settings {len(uniq)} "
        f"(promises {[round(u.guar_excess_s, 1) for u in uniq]}), paper rows {len(adm)}")
    for r, ln in zip(sorted(uniq, key=lambda x: x.guar_excess_s), adm):
        want = [f(r.guar_excess_s, 0), f(r.p99_dl_s, 2),
                ci(r.gap_closed, r.gap_lo, r.gap_hi), f(r.max_excess_s, 1),
                f(r.harm_wf1s_s, 1), f(100.0 * r.qw_fired, 2)]
        nrow += 1
        cmp(f"tab:k1 Fixed-admitted {r.guar_excess_s:g}", dn(ln), want)

    # ---------------------------------------------------- prose in section 8
    say("")
    say("=" * 96)
    say("PROSE NUMBERS OF SECTION 8 THAT COME FROM v3.1")
    say("=" * 96)
    D = pd.read_csv(os.path.join(V31, "gaindiff_primary.csv"))
    D = D[(D.metric == "p99dl") & (D.quantity == "gain")]
    for G, lev in ((600, 2), (1200, 2), (300, 2)):
        r = D[(D.level == lev) & (D.pair == f"CAP-G{G} - SPJF-tweedie")].iloc[0]
        say(f"  guard cost at G={G}, rho 1.0: csv {r['diff']:.3f} "
            f"[{r.lo:.3f}, {r.hi:.3f}]  (paper quotes the magnitude)")
    r = D[(D.level == 2) & (D.pair == "SPJF-tweedie - SPJF-M4")].iloc[0]
    say(f"  Tweedie - log M4 at rho 1.0: csv {r['diff']:+.4f} [{r.lo:+.4f}, {r.hi:+.4f}]")
    H = pd.read_csv(os.path.join(V31, "report_cap_vs_fix.csv"))
    say(f"  k1 harm ratios fix/cap: "
        f"{H[H.trace == 'k1'].harm_ratio_fix_over_cap.tolist()}  (paper: 4.53/3.40/1.94)")
    say(f"  CAP-G600-top1short max excess at k=1: "
        f"{K1.set_index('policy').loc['CAP-G600-top1short', 'max_excess_s']:.1f} s "
        f"(paper: 597.0)")

    say("")
    say("=" * 96)
    say(f"ROWS CHECKED {nrow}; ROWS WITH A DISAGREEMENT {len(BAD)}")
    for tag, g, w, d in BAD:
        say(f"  {tag}: {d if d else 'row missing / length mismatch'}")
    say("=" * 96)
    say("NOT checked here: tab:scores and tab:policies (a different study, "
        "evidence/ranking_score), and the figures.")
    open(os.path.join(HERE, "out_paper.txt"), "w",
         encoding="utf-8").write("\n".join(OUT) + "\n")


if __name__ == "__main__":
    main()
