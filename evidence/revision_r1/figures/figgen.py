"""Shared by the make_<label>.py scripts: read a CSV, hash it, and rewrite the generated
block of a figure file.

A figure file keeps its axes, styles and caption by hand.  Its coordinates sit between
the two marker lines BEGIN and END below, and only the script that names itself on the
BEGIN line writes there.  The block holds pgfplots tables (\\pgfplotstableread, one per
series) and \\def macros for the few numbers the caption quotes.  Output is
deterministic: no time stamps, rows in a fixed order, fixed float formats, LF line ends;
a second run therefore writes the same bytes.
"""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BEGIN = "% BEGIN GENERATED BLOCK"
END = "% END GENERATED BLOCK"


def rows(rel: str) -> list[dict[str, str]]:
    with open(ROOT / rel, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def sha256(rel: str) -> str:
    return hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()


def ratio(value: float) -> str:
    """A derived ratio, printed to six decimals like the CSV fields it comes from."""
    return f"{value:.6f}"


def table(name: str, columns: list[str], data: list[list[str]]) -> list[str]:
    """One \\pgfplotstableread block; rows end in \\\\ so TeX line ends do not matter."""
    lines = [r"\pgfplotstableread[row sep=\\]{", " ".join(columns) + r"\\"]
    lines += [" ".join(row) + r"\\" for row in data]
    lines.append("}\\" + name)
    return lines


def define(name: str, value: str) -> str:
    return f"\\def\\{name}{{{value}}}"


def write_block(figure: str, script: str, inputs: list[str], body: list[str]) -> Path:
    """Replace the generated block of paper/figures/<figure> with body."""
    path = ROOT / "paper" / "figures" / figure
    text = path.read_text(encoding="utf-8")
    head, start, rest = text.partition(BEGIN)
    old, stop, tail = rest.partition(END)
    if not start or not stop:
        raise SystemExit(f"{path.relative_to(ROOT)} has no '{BEGIN}' ... '{END}' block")
    lines = [
        f"{BEGIN}: written by {script}; do not edit by hand.",
        "% Inputs (sha256):",
        *[f"%   {rel}  {sha256(rel)}" for rel in inputs],
        *body,
    ]
    path.write_text(head + "\n".join(lines) + "\n" + END + tail, encoding="utf-8", newline="\n")
    return path
