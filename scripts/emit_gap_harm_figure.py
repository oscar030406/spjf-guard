"""Write paper/figures/fig_gap_harm.tex from the selection and development tables.

    uv run python scripts/emit_gap_harm_figure.py [--selection outputs/selection_v4]

Upper rows: every selected budget shape and Fixed(G) at each promise and load, from
outputs/dev_tables/main_table.csv, with Aging(600) from the visibility comparison.
Bottom row: every validation candidate and the per-family selections.  Each series
carries a comment naming the CSV row and fields its coordinates come from.
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROMISES = (300, 600, 1200)
LOADS = ((0, "0.5"), (1, "0.8"), (2, "1.0"))
# Series styles are keys of paper/figures/pgfstyle.tex, the style every figure shares.
SHAPES = (
    ("Guard-fixed", "fixed", "spjf gfixed"),
    ("Guard-age", "capped", "spjf gage"),
    ("Guard-queue", "hybrid", "spjf gqueue"),
)
FIXED_STYLE = "spjf fixed"
AGING_STYLE = "spjf aging"
# Panel box width and gap, and the row step, as fractions of \linewidth: three panels
# fill the text block at \small text with nothing scaled.
COL_STEP = 0.295
ROW_STEP = 0.285

HEAD = r"""% Coordinates copied from the CSV fields stated beside each series.
% Style: figures/pgfstyle.tex; widths are fractions of \linewidth and nothing is scaled,
% so the text is \small, the caption size.
\begin{figure}[p]
\input{figures/pgfstyle}%
\centering
\begin{tikzpicture}
\pgfplotsset{tradeaxis/.style={spjf axis,width=0.27\linewidth,height=0.19\linewidth,
 xmin=0,xmax=1150,ymin=0,ymax=1,xtick={0,300,600,900},
 ytick={0,0.25,0.5,0.75,1},grid=major}}
"""
TAIL = r"""\end{tikzpicture}
\caption{Gap--harm trade-offs for every selected budget shape and Fixed($G$), at each
promise and load (upper rows); validation candidates and per-family selections
(bottom row). A joint winner coincides with its selected family point. The dashed
line is the \devnum{300} s validation limit for $G=\devnum{600}$ s; it is shown in
every panel as a common reference, not as the constraint for every promise.
The other promise-specific limits follow harm $\le G/2$.
All budget-family points use original scores. The purple cross is the only selected
aging comparator, Aging(600), with conservative scores and no proved guarantee;
it is repeated across promise panels for orientation, not retuned at other promises.
Cross-protocol points do not establish Pareto dominance. Maxima have no population
interval; gap intervals for the selected rows are reported in the tables.}
% Sources: {selection}/selected_parameters.csv (harm_limit_s=300 for G=600);
% all plotted coordinates have their input row and fields cited above.
\label{fig:gap_harm}
\end{figure}
"""


def _rows(path: Path) -> list[dict[str, str]]:
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _point(x: str | float, y: str | float) -> str:
    return f"({float(x):.6f},{float(y):.6f})"


def _series(style: str, point: str, source: str, legend: str | None) -> list[str]:
    lines = [
        rf"\addplot[only marks,{style}] coordinates {{{point}}};",
        f"% Source: {source}",
    ]
    if legend is not None:
        lines.append(rf"\addlegendentry{{{legend}}}")
    return lines


def _axis_open(row: int, col: int, promise: int, title: str, last: bool) -> str:
    options = [
        "tradeaxis",
        f"name=cell{row}{col}",
        f"at={{({col * COL_STEP:.3f}\\linewidth,{-row * ROW_STEP:.3f}\\linewidth)}}",
        f"title={{$G={promise}$ s, {title}}}",
    ]
    options.append("ylabel={gap closed}" if col == 0 and row < 3 else "")
    if row == 3:
        options[-1] = "ylabel={worst-cell gap}" if col == 0 else "yticklabels={}"
        options.append("xlabel={maximum harm (s)}")
        if last:
            # Centred under the middle panel of the bottom row.
            options.append("legend style={at={(-0.593,-0.40)},anchor=north,legend columns=3}")
    elif col > 0:
        options[-1] = "yticklabels={}"
    return rf"\begin{{axis}}[{','.join(options)}]"


def _reference(selection_name: str) -> list[str]:
    return [
        r"\addplot[spjf ref,black,forget plot] coordinates "
        r"{(300,0) (300,1)};",
        f"% Source: {selection_name}/selected_parameters.csv, G=600, harm_limit_s=300.",
    ]


def _upper(args, main, visibility, selection_name) -> list[str]:
    lines = []
    for row, (level, rho) in enumerate(LOADS):
        for col, promise in enumerate(PROMISES):
            lines.append(_axis_open(row, col, promise, f"$\\rho={rho}$", False))
            lines += _reference(selection_name)
            for label, _, style in SHAPES:
                name = f"{label}({promise})"
                hit = main[(str(level), name)]
                lines += _series(
                    style,
                    _point(hit["harm_s"], hit["gap_closed"]),
                    f"{args.dev_tables_name}/main_table.csv, level={level}, policy={name}, "
                    "harm_s/gap_closed.",
                    None,
                )
            hit = main[(str(level), f"Fixed({promise})")]
            lines += _series(
                FIXED_STYLE,
                _point(hit["harm_s"], hit["gap_closed"]),
                f"{args.dev_tables_name}/main_table.csv, level={level}, "
                f"policy=Fixed({promise}), harm_s/gap_closed.",
                None,
            )
            hit = visibility[str(level)]
            lines += _series(
                AGING_STYLE,
                _point(hit["harm_s"], hit["gap_closed"]),
                f"outputs/dev_visibility/visibility_comparison.csv, level={level}, "
                "policy=Aging(600), harm_s/gap_closed.",
                None,
            )
            lines.append(r"\end{axis}")
    return lines


def _bottom(args, selection_name) -> list[str]:
    frontier = _rows(args.selection / "selection_frontier.csv")
    selected = _rows(args.selection / "selected_parameters.csv")
    worst = _rows(args.selection / "selection_worst.csv")
    aging = _rows(args.aging)[0]
    lines = []
    for col, promise in enumerate(PROMISES):
        last = col == len(PROMISES) - 1
        lines.append(_axis_open(3, col, promise, "validation", last))
        lines += _reference(selection_name)
        cloud = " ".join(
            _point(r["worst_harm_s"], r["worst_gap_closed"])
            for r in frontier
            if float(r["promise_s"]) == promise
        )
        lines.append(
            r"\addplot[only marks,mark=*,mark size=0.7pt,black!35,mark options={line width=0.3pt},forget plot] coordinates "
            f"{{{cloud}}};"
        )
        lines.append(
            f"% Source: {selection_name}/selection_frontier.csv, promise_s={promise}, "
            "worst_harm_s/worst_gap_closed (all candidate rows)."
        )
        for label, family, style in SHAPES:
            hit = next(
                r
                for r in selected
                if r["family"] == family and float(r["promise_s"]) == promise
            )
            lines += _series(
                style,
                _point(hit["worst_harm_s"], hit["worst_gap_closed"]),
                f"{selection_name}/selected_parameters.csv, family={family}, "
                f"promise_s={promise}.",
                label if last else None,
            )
        hit = next(
            r
            for r in worst
            if r["family"] == "fixed"
            and float(r["promise_s"]) == promise
            and math.isinf(float(r["b0_base_s"]))
        )
        lines += _series(
            FIXED_STYLE,
            _point(hit["worst_harm_s"], hit["worst_gap_closed"]),
            f"{selection_name}/selection_worst.csv, fixed/inf, promise_s={promise}.",
            "Fixed" if last else None,
        )
        lines += _series(
            AGING_STYLE,
            _point(aging["worst_harm_s"], aging["worst_gap_closed"]),
            "outputs/selection_aging/selected_aging.csv, worst_harm_s/worst_gap_closed.",
            "Aging(600), conservative" if last else None,
        )
        lines.append(r"\end{axis}")
    return lines


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selection", type=Path, default=ROOT / "outputs" / "selection_v4")
    ap.add_argument("--dev-tables", type=Path, default=ROOT / "outputs" / "dev_tables")
    ap.add_argument(
        "--visibility",
        type=Path,
        default=ROOT / "outputs" / "dev_visibility" / "visibility_comparison.csv",
    )
    ap.add_argument(
        "--aging",
        type=Path,
        default=ROOT / "outputs" / "selection_aging" / "selected_aging.csv",
    )
    ap.add_argument("--out", type=Path, default=ROOT / "paper" / "figures" / "fig_gap_harm.tex")
    args = ap.parse_args()
    selection_name = args.selection.resolve().relative_to(ROOT).as_posix()
    args.dev_tables_name = "outputs/dev_tables"
    main_rows = {
        (r["level"], r["policy"]): r for r in _rows(args.dev_tables / "main_table.csv")
    }
    visibility = {r["level"]: r for r in _rows(args.visibility) if r["policy"] == "Aging(600)"}
    lines = _upper(args, main_rows, visibility, selection_name) + _bottom(args, selection_name)
    text = HEAD + "\n".join(lines) + "\n" + TAIL.replace("{selection}", selection_name)
    args.out.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
