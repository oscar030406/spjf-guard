"""Turning measured cells into the tables the paper prints.

Two outputs, from one set of rows: a CSV that carries the full precision, and a LaTeX
table whose every number is wrapped in `\\devnum{}` so that development figures can be
told apart from sealed-term figures at a glance.  Both land in `outputs/`; nothing here
writes into `paper/`.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np

DEVNUM = r"\devnum{%s}"


def devnum(value, digits: int = 2, interval=None) -> str:
    """One number, optionally with its interval, wrapped for the paper's macro."""
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return r"\devnum{---}"
    body = f"{value:.{digits}f}"
    if interval is not None and all(np.isfinite(x) for x in interval):
        body += f" [{interval[0]:.{digits}f}, {interval[1]:.{digits}f}]"
    return DEVNUM % body


@dataclass(frozen=True)
class Column:
    """One column of a reported table: where the number comes from and how it prints."""

    header: str
    field: str
    digits: int = 2
    interval_fields: tuple[str, str] | None = None
    align: str = "r"


MAIN_COLUMNS = (
    Column(r"p99$_{\mathrm{dl}}$", "p99_dl_s", 2),
    Column("Gap closed", "gap_closed", 3, ("gap_closed_lo", "gap_closed_hi"), "l"),
    Column(r"Red.\ (\%)", "reduction_pct", 1, ("reduction_pct_lo", "reduction_pct_hi"), "l"),
    Column("Mean", "mean_s", 3),
    Column("Max exc.", "max_excess_s", 1),
    Column("Harm", "harm_s", 1),
    Column(r"Fired (\%)", "fired_pct", 1),
)


def write_csv(rows: list[dict], path: Path) -> Path:
    """The full-precision table.  Column order follows the first row."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def _body_rows(rows, columns, group_field, group_label, policy_field):
    out = []
    for group in sorted({r[group_field] for r in rows}):
        block = [r for r in rows if r[group_field] == group]
        out.append(group_label(block[0]))
        for row in block:
            cells = []
            for column in columns:
                interval = (
                    None
                    if column.interval_fields is None
                    else (
                        row.get(column.interval_fields[0], float("nan")),
                        row.get(column.interval_fields[1], float("nan")),
                    )
                )
                cells.append(devnum(row.get(column.field), column.digits, interval))
            out.append(f" & {row[policy_field]:<22s} & " + " & ".join(cells) + r" \\")
        out.append(r"\midrule")
    if out and out[-1] == r"\midrule":
        out.pop()
    return out


def latex_table(
    rows: list[dict],
    caption: str,
    label: str,
    columns=MAIN_COLUMNS,
    group_field: str = "level",
    policy_field: str = "policy",
) -> str:
    """A table body whose numbers are all wrapped in `\\devnum{}`.

    `paper/sections/08_experiments.tex` defines `\\devnum` and consumes rows of exactly
    this shape; the file is written to outputs/ and copied in by hand.
    """

    def group_label(row):
        return (
            rf"$\rho = \devnum{{{row['rho_target']:g}}}$, "
            rf"$k = \devnum{{{row['k']:g}}}$"
        )

    spec = "ll" + "".join(c.align for c in columns)
    head = " & ".join(["Load", "Policy"] + [c.header for c in columns])
    lines = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\footnotesize",
        rf"\caption{{{caption}}}",
        rf"\label{{{label}}}",
        r"\setlength{\tabcolsep}{4pt}",
        rf"\begin{{tabular}}{{{spec}}}",
        r"\toprule",
        head + r" \\",
        r"\midrule",
        *_body_rows(rows, columns, group_field, group_label, policy_field),
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
    ]
    return "\n".join(lines) + "\n"


def write_latex(
    rows: list[dict],
    path: Path,
    caption: str,
    label: str,
    columns=MAIN_COLUMNS,
    source_note: str = "",
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = latex_table(rows, caption, label, columns)
    if source_note:
        text += "% Source: " + source_note + "\n"
    path.write_text(text, encoding="utf-8")
    return path
