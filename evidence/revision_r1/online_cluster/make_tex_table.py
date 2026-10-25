"""Write the LaTeX body of the online class-term bootstrap table (Supplementary), the
online counterpart of Table S18. Class-term intervals: outputs/online_cluster_bootstrap/
bootstrap_summary.csv (scripts/run_online_cluster_bootstrap.py, 100 resamples). Week-block
intervals: outputs/dev_online_visibility/online_comparison.csv (gap closed) and
outputs/online_paired/online_paired_differences.csv (guard minus SPJF-E, variant online).
Writes outputs/revision_r1/online_cluster/tab_s_online_cluster_body.tex. No computation
beyond selecting rows and rounding; it checks that the three files agree on every point.

    python evidence/revision_r1/online_cluster/make_tex_table.py
"""
import csv
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
OUT = ROOT / "outputs/revision_r1/online_cluster"
GUARDS = ["300", "600", "1200"]


def rows(path):
    return list(csv.DictReader(open(ROOT / path, encoding="utf-8")))


def fmt(x):
    return ("$-$%.3f" % -x) if x < -5e-4 else "%.3f" % abs(x) if abs(x) < 5e-4 else "%.3f" % x


def interval(lo, hi):
    return "\\devnum{%s [%s, %s]}" % (fmt(hi - lo), fmt(lo), fmt(hi))


def main():
    cluster = {(r["level"], r["quantity"]): r for r in rows("outputs/online_cluster_bootstrap/bootstrap_summary.csv")}
    week = {(r["level"], r["policy"]): r for r in rows("outputs/dev_online_visibility/online_comparison.csv")}
    pairs = {(r["level"], r["left"]): r for r in rows("outputs/online_paired/online_paired_differences.csv")
             if r["variant"] == "online" and r["right"] == "SPJF-E"}
    lines = []
    for level in ("0", "1", "2"):
        if level != "0":
            lines.append("\\midrule")
        for name, label in [("SPJF-E", "SPJF-E")] + [(f"Guard({g})", f"Guard($\\devnum{{{g}}}$)") for g in GUARDS]:
            c = cluster[(level, f"{name}|online")]
            w = week[(level, f"{name}|online")]
            point = float(c["point"])
            assert abs(point - float(w["gap_closed"])) < 1e-9, (level, name)
            lines.append(" & ".join([
                "\\devnum{%s}" % level, label, "\\devnum{%s}" % fmt(point),
                interval(float(w["gap_closed_lo"]), float(w["gap_closed_hi"])),
                interval(float(c["lo"]), float(c["hi"])),
            ]) + " \\\\")
        for g in GUARDS:
            c = cluster[(level, f"Guard({g})|online - SPJF-E|online")]
            p = pairs[(level, f"Guard({g})")]
            point = float(c["point"])
            assert abs(point - float(p["difference_gap"])) < 1e-9, (level, g)
            lines.append(" & ".join([
                "\\devnum{%s}" % level, f"Guard($\\devnum{{{g}}}$) $-$ SPJF-E", "\\devnum{%s}" % fmt(point),
                interval(float(p["gap_lo"]), float(p["gap_hi"])),
                interval(float(c["lo"]), float(c["hi"])),
            ]) + " \\\\")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "tab_s_online_cluster_body.tex").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print("wrote", OUT / "tab_s_online_cluster_body.tex", len(lines), "lines")


if __name__ == "__main__":
    main()
