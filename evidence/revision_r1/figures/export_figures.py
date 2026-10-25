"""Compile every paper figure alone and write its vector PDF and a 600 dpi PNG.

Run from the repository root (tectonic and poppler's pdftoppm must be on PATH):

    env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME .venv/Scripts/python.exe \
        evidence/revision_r1/figures/export_figures.py [--only fig_guard ...] [--out-dir DIR]

For each paper/figures/fig_<label>.tex the script writes the wrapper
paper/figures/export/src/fig_<label>.tex: the standalone class at the MDPI text width
(394.35522 pt, the \\textwidth of Definitions/mdpi.cls), the preamble in
export/src/preamble.tex, and the figure without its float and caption.  It compiles the
wrapper with tectonic into the output directory (default paper/figures/export/), giving
fig_<label>.pdf (vector, fonts embedded), and renders fig_<label>.png from that PDF with
pdftoppm.  tectonic runs with -Z deterministic-mode, so an unchanged figure gives the same
PDF bytes.  Standard library only.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FIGURES = ROOT / "paper" / "figures"
SRC = FIGURES / "export" / "src"
WRAPPER = """\
% Wrapper written by evidence/revision_r1/figures/export_figures.py: compiles
% figures/fig_{label}.tex alone, without its caption, at the MDPI {which} width.
\\documentclass[10pt,varwidth={width},border=2pt]{{standalone}}
\\input{{preamble}}
\\begin{{document}}
\\input{{figures/fig_{label}}}
\\end{{document}}
"""
# Text width of Definitions/mdpi.cls, and the full width that a figure set inside
# adjustwidth{-\extralength}{0cm} gets: text width plus \extralength = 4.61 cm.
TEXT_WIDTH = "394.35522pt"
FULL_WIDTH = "525.52245pt"


def labels(only: list[str]) -> list[str]:
    found = sorted(p.stem.removeprefix("fig_") for p in FIGURES.glob("fig_*.tex"))
    wanted = [name.removeprefix("fig_") for name in only] or found
    missing = sorted(set(wanted) - set(found))
    if missing:
        raise SystemExit(f"no paper/figures/fig_<label>.tex for: {', '.join(missing)}")
    return wanted


def tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise SystemExit(f"{name} is not on PATH")
    return path


def export(label: str, out_dir: Path, dpi: int, tectonic: str, pdftoppm: str) -> Path:
    wrapper = SRC / f"fig_{label}.tex"
    full = "adjustwidth" in (FIGURES / f"fig_{label}.tex").read_text(encoding="utf-8")
    wrapper.write_text(WRAPPER.format(label=label, which="full page" if full else "text",
                                      width=FULL_WIDTH if full else TEXT_WIDTH),
                       encoding="utf-8", newline="\n")
    run = subprocess.run(
        [tectonic, "-Z", "deterministic-mode", "-o", str(out_dir), wrapper.name],
        cwd=SRC,
        capture_output=True,
        text=True,
    )
    if run.returncode != 0:
        sys.stderr.write(run.stdout + run.stderr)
        raise SystemExit(f"tectonic failed on {wrapper.relative_to(ROOT)}")
    pdf = out_dir / f"fig_{label}.pdf"
    subprocess.run(
        [pdftoppm, "-r", str(dpi), "-png", "-singlefile", str(pdf), str(out_dir / f"fig_{label}")],
        check=True,
    )
    return pdf


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--only", nargs="*", default=[], help="fig_<label> names; default all")
    ap.add_argument("--out-dir", type=Path, default=FIGURES / "export")
    ap.add_argument("--dpi", type=int, default=600)
    args = ap.parse_args()
    tectonic, pdftoppm = tool("tectonic"), tool("pdftoppm")
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    for label in labels(args.only):
        pdf = export(label, out_dir, args.dpi, tectonic, pdftoppm)
        png = pdf.with_suffix(".png")
        print(f"fig_{label}: {pdf.stat().st_size:>9,} B pdf, {png.stat().st_size:>9,} B png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
