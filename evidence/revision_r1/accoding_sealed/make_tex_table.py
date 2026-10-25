"""Write the LaTeX body of the ACcoding sealed-part table (Supplementary S13.2) from the
frozen run's summary. Reads outputs/accoding_heldout_sealed_online_v2/summary.csv (rows are
means over seeds 300-304; max_excess_s is the maximum over the seeds) and writes
outputs/revision_r1/accoding_sealed/tab_s_accoding_sealed_body.tex. Online-clock rows for
the scored policies; FCFS and SJF read no score. No computation beyond selection and
rounding.

    python evidence/revision_r1/accoding_sealed/make_tex_table.py
"""
import csv
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
SRC = ROOT / "outputs/accoding_heldout_sealed_online_v2/summary.csv"
OUT = ROOT / "outputs/revision_r1/accoding_sealed/tab_s_accoding_sealed_body.tex"
GUARDS = ["Guard(300)", "Guard(600)", "Guard(1200)"]


def main():
    rows = list(csv.DictReader(open(SRC, encoding="utf-8")))
    by = {}
    for r in rows:
        online = r["score_definition"].endswith("online")
        if r["policy"] in ("FCFS", "SJF") or online:
            by[(r["shape"], r["rho_target"], r["policy"])] = r
    lines = []
    for shape in ("poisson", "deadline"):
        for rho in ("0.5", "0.8", "1.0"):
            f = by[(shape, rho, "FCFS")]
            cells = [shape if rho == "0.5" else "", "\\devnum{%s}" % rho, f["k"].split(".")[0],
                     "\\devnum{%.2f}" % float(f["rho_realised"]),
                     "\\devnum{%s}" % format(round(float(f["p99"]), 1), ",.1f").replace(",", "{,}"),
                     "\\devnum{$%.3f$}" % float(by[(shape, rho, "SPJF-E")]["gap_closed_p99"])]
            cells += ["\\devnum{$%.3f$}" % float(by[(shape, rho, g)]["gap_closed_p99"]) for g in GUARDS]
            cells.append("/".join("\\devnum{%.1f}" % float(by[(shape, rho, g)]["max_excess_s"]) for g in GUARDS))
            lines.append(" & ".join(cells) + " \\\\")
        if shape == "poisson":
            lines.append("\\addlinespace")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print("wrote", OUT, len(lines), "lines")


if __name__ == "__main__":
    main()
