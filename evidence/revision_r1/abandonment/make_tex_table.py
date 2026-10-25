"""Write the LaTeX body of the abandonment table (Supplementary) from the grid of
evidence/abandonment_loop (model in its MODEL.md, checks in its REPORT.md). Reads
evidence/abandonment_loop/out/cells.csv, writes
outputs/revision_r1/abandonment/tab_s_abandon_body.tex. Heaviest load (level 2, k = 4):
p99, gap closed and withdrawn fraction are means over the five overlays, the largest
excess and the worst share of the bound are the worst overlay. No computation beyond
selecting rows, averaging over overlays and rounding.

    python evidence/revision_r1/abandonment/make_tex_table.py
"""
import csv
import pathlib
from statistics import mean

ROOT = pathlib.Path(__file__).resolve().parents[3]
CELLS = ROOT / "evidence/abandonment_loop/out/cells.csv"
OUT = ROOT / "outputs/revision_r1/abandonment"
LEVEL = "2"
COMBOS = [("inf", "0.0")] + [(m, p) for m in ("1800.0", "300.0", "60.0") for p in ("0.0", "0.5", "1.0")]
GUARD = "Guard(600)"


def main():
    rows = {}
    for r in csv.DictReader(open(CELLS, encoding="utf-8")):
        if r["level"] == LEVEL:
            rows.setdefault((r["patience_mean_s"], r["p_resubmit"], r["policy"]), []).append(r)

    def avg(m, p, pol, col):
        group = rows[(m, p, pol)]
        assert len(group) == 5, (m, p, pol, len(group))
        return mean(float(r[col]) for r in group)

    def worst(m, p, pol, col):
        return max(float(r[col]) for r in rows[(m, p, pol)])

    lines = []
    for i, (m, p) in enumerate(COMBOS):
        if i in (1, 4, 7):
            lines.append("\\addlinespace")
        if m == "inf":
            patience, coin = "$\\infty$", "---"
        else:
            patience = "\\devnum{%s}" % format(int(float(m)), ",").replace(",", "{,}") if p == "0.0" else ""
            coin = "\\devnum{%g}" % float(p)
        cells = [
            patience,
            coin,
            "\\devnum{%.1f}" % avg(m, p, "FCFS", "p99_dl_s"),
            "\\devnum{%.3f}" % avg(m, p, "SPJF-E", "gap_closed"),
            "\\devnum{%.3f}" % avg(m, p, GUARD, "gap_closed"),
        ]
        cells += ["\\devnum{%.3f}" % (100 * avg(m, p, pol, "frac_withdrawn")) for pol in ("FCFS", "SPJF-E", GUARD)]
        cells += ["\\devnum{%s}" % format(round(worst(m, p, pol, "max_excess_s")), ",").replace(",", "{,}")
                  for pol in ("SPJF-E", GUARD)]
        cells.append("\\devnum{%.3f}" % worst(m, p, GUARD, "worst_ratio_to_bound"))
        assert worst(m, p, GUARD, "bound_violations") == 0
        lines.append(" & ".join(cells) + " \\\\")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "tab_s_abandon_body.tex").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print("wrote", OUT / "tab_s_abandon_body.tex", len(lines), "lines")


if __name__ == "__main__":
    main()
