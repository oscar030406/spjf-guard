"""Write the LaTeX body of the sealed class-term table (Supplementary, E-SC1): the gap
closed of SPJF-E and of each guard on the sealed terms under the online protocol, with the
week-block interval of the sealed run and the class-term interval of
scripts/run_online_cluster_bootstrap.py --pool sealed (100 resamples), and each guard's
difference to SPJF-E with its class-term interval. The sealed run computed no week-block
interval for a difference, so that cell is a dash. No computation beyond selecting rows,
subtracting two points and rounding; it checks that the two files agree on every point.

    python evidence/revision_r1/sealed_online_cluster/make_tex_table.py
    python evidence/revision_r1/sealed_online_cluster/make_tex_table.py --dev   (dry run
        on the development files: its rows must equal those of Table S38, except the dash
        where Table S38 prints the week-block interval of a difference)
"""
import csv
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
GUARDS = ["300", "600", "1200"]
DEV = "--dev" in sys.argv
CLUSTER = "outputs/online_cluster_bootstrap" if DEV else "outputs/sealed_online_cluster_bootstrap"
WEEK = "outputs/dev_online_visibility" if DEV else "outputs/sealed_online_visibility"
OUT = ROOT / "outputs/revision_r1" / ("sealed_online_cluster_dev_dry_run" if DEV else "sealed_online_cluster")
# Table S28 marks sealed figures \sealednum{}, the development table S38 \devnum{}.
MACRO = "devnum" if DEV else "sealednum"


def rows(path):
    return list(csv.DictReader(open(ROOT / path, encoding="utf-8")))


def fmt(x):
    return ("$-$%.3f" % -x) if x < -5e-4 else "%.3f" % abs(x) if abs(x) < 5e-4 else "%.3f" % x


def interval(lo, hi):
    return "\\%s{%s [%s, %s]}" % (MACRO, fmt(hi - lo), fmt(lo), fmt(hi))


def main():
    cluster = {(r["level"], r["quantity"]): r for r in rows(f"{CLUSTER}/bootstrap_summary.csv")}
    week = {(r["level"], r["policy"]): r for r in rows(f"{WEEK}/online_comparison.csv")}
    lines = []
    for level in ("0", "1", "2"):
        if level != "0":
            lines.append("\\midrule")
        for name, label in [("SPJF-E", "SPJF-E")] + [(f"Guard({g})", f"Guard($\\{MACRO}{{{g}}}$)") for g in GUARDS]:
            c = cluster[(level, f"{name}|online")]
            w = week[(level, f"{name}|online")]
            point = float(c["point"])
            assert abs(point - float(w["gap_closed"])) < 1e-9, (level, name)
            assert int(c["resamples"]) == 100, (level, name, c["resamples"])
            lines.append(" & ".join([
                "\\%s{%s}" % (MACRO, level), label, "\\%s{%s}" % (MACRO, fmt(point)),
                interval(float(w["gap_closed_lo"]), float(w["gap_closed_hi"])),
                interval(float(c["lo"]), float(c["hi"])),
            ]) + " \\\\")
        spjf = float(week[(level, "SPJF-E|online")]["gap_closed"])
        for g in GUARDS:
            c = cluster[(level, f"Guard({g})|online - SPJF-E|online")]
            point = float(c["point"])
            assert abs(point - (float(week[(level, f"Guard({g})|online")]["gap_closed"]) - spjf)) < 1e-9, (level, g)
            assert int(c["resamples"]) == 100, (level, g, c["resamples"])
            lines.append(" & ".join([
                "\\%s{%s}" % (MACRO, level), f"Guard($\\{MACRO}{{{g}}}$) $-$ SPJF-E",
                "\\%s{%s}" % (MACRO, fmt(point)),
                "---", interval(float(c["lo"]), float(c["hi"])),
            ]) + " \\\\")
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "tab_s_sealed_online_cluster_body.tex"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print("wrote", path, len(lines), "lines")


if __name__ == "__main__":
    main()
