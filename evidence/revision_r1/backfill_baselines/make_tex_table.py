"""Write the LaTeX body of the backfilling table (manuscript, Section 8). Backfilling rows
come from outputs/revision_r1/backfill_baselines/backfill_table.csv, which make_table.py
builds; Guard(G) rows from outputs/dev_online_visibility/online_cells.csv, variant
original, aggregated as make_table.py does (mean over overlays of the gap closed, worst
over overlays of the largest excess). Writes
outputs/revision_r1/backfill_baselines/tab_backfill_body.tex. No computation beyond
selecting rows, that aggregation and rounding; it checks that the slack rows do not
depend on G.

    python evidence/revision_r1/backfill_baselines/make_tex_table.py
"""
import csv
import pathlib
from statistics import mean

ROOT = pathlib.Path(__file__).resolve().parents[3]
OUT = ROOT / "outputs/revision_r1/backfill_baselines"
ONLINE_CELLS = ROOT / "outputs/dev_online_visibility/online_cells.csv"
LEVELS = ["0", "1", "2"]
ROWS = [
    ("Guard(300)", "Guard(\\devnum{300})", "$W \\le W_{\\mathrm{FCFS}} + \\devnum{300}$ s"),
    ("Guard(600)", "Guard(\\devnum{600})", "$W \\le W_{\\mathrm{FCFS}} + \\devnum{600}$ s"),
    ("Guard(1200)", "Guard(\\devnum{1200})", "$W \\le W_{\\mathrm{FCFS}} + \\devnum{1200}$ s"),
    ("CBF-L", "CBF-L", "start by the reservation made at arrival"),
    ("Slack-L(600)", "Slack-L($G$)", "start by the plan at arrival $+\\,G$"),
    ("CBF-P", "CBF-P", "none"),
    ("Slack-P(600)", "Slack-P($G$)", "none"),
]


def num(x, digits):
    s = f"{x:,.{digits}f}".replace(",", "{,}")
    return "\\devnum{%s}" % s


def main():
    t = {(r["level"], r["policy"]): r for r in csv.DictReader(open(OUT / "backfill_table.csv", encoding="utf-8"))}
    guard = {}
    for r in csv.DictReader(open(ONLINE_CELLS, encoding="utf-8")):
        if r["variant"] == "original" and r["policy"].startswith("Guard("):
            guard.setdefault((r["level"], r["policy"].removesuffix("|original")), []).append(r)
    for (lv, pol), group in guard.items():
        assert len(group) == 5, (lv, pol, len(group))
        t[(lv, pol)] = {"gap_closed": mean(float(r["gap_closed"]) for r in group),
                        "max_excess_s": max(float(r["max_excess_s"]) for r in group)}
    for family in ("Slack-L", "Slack-P"):
        for lv in LEVELS:
            vals = {(t[(lv, f"{family}({g})")]["gap_closed"], t[(lv, f"{family}({g})")]["max_excess_s"]) for g in (300, 600, 1200)}
            assert len(vals) == 1, (family, lv, vals)
    lines = []
    for key, name, promise in ROWS:
        cells = [name, promise]
        for lv in LEVELS:
            r = t[(lv, key)]
            gap = float(r["gap_closed"])
            cells.append("%s / %s" % (num(abs(gap) if abs(gap) < 5e-4 else gap, 3), num(float(r["max_excess_s"]), 1)))
        lines.append(" & ".join(cells) + " \\\\")
        if key == "Guard(1200)":
            lines.append("\\midrule")
    (OUT / "tab_backfill_body.tex").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print("wrote", OUT / "tab_backfill_body.tex", len(lines), "lines")


if __name__ == "__main__":
    main()
