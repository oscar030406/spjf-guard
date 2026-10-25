"""Write the LaTeX body of the small-k shape ablation table (Supplementary) from the
final outputs. Reads outputs/revision_r1/small_k_shapes/shape_table.csv and guidance.csv,
writes outputs/revision_r1/small_k_shapes/tab_s_small_k_body.tex. No computation beyond
selecting rows and rounding.

    python evidence/revision_r1/small_k_shapes/make_tex_table.py
"""
import csv
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
OUT = ROOT / "outputs/revision_r1/small_k_shapes"
SERIES = [("k1", "1"), ("k2", "2"), ("k3", "3")]
GS = ["300", "600", "1200"]
LOADS = ["0.5", "0.8", "0.95"]


def key(s, load, pol):
    return (s, load, pol)


def main():
    shape = {}
    for r in csv.DictReader(open(OUT / "shape_table.csv", encoding="utf-8")):
        shape[key(r["series"], r["load"], r["policy"])] = r
    guid = {}
    for r in csv.DictReader(open(OUT / "guidance.csv", encoding="utf-8")):
        guid[(r["series"], r["load"], r["G"])] = r
    lines = []
    for s, k in SERIES:
        for g in GS:
            for load in LOADS:
                cells = []
                for pol in (f"Guard-fixed({g})", f"Guard-age({g})", f"Guard-queue({g})",
                            f"Fixed({g})", f"Guard-default({g})"):
                    r = shape[key(s, load, pol)]
                    cells.append("\\devnum{%.3f}" % float(r["gap_closed"]))
                gd = guid[(s, load, g)]
                harm = float(gd["Guard-default_harm_s"])
                limit = float(gd["harm_limit_s"])
                ok = "yes" if gd["Guard-default_adequate"] == "True" else "no"
                lines.append(" & ".join([k if (g == "300" and load == "0.5") else "",
                                         g if load == "0.5" else "",
                                         "\\devnum{%s}" % load] + cells +
                                        ["\\devnum{%.0f}/\\devnum{%.0f}" % (harm, limit), ok]) + " \\\\")
            if not (s == "k3" and g == "1200"):
                lines.append("\\addlinespace" if g != "1200" else "\\midrule")
    (OUT / "tab_s_small_k_body.tex").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print("wrote", OUT / "tab_s_small_k_body.tex", len(lines), "lines")


if __name__ == "__main__":
    main()
