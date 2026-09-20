"""Write the paper's tables and the map of every number the paper quotes.

    uv run python scripts/emit_paper_tables.py [--dev-dir outputs/dev_tables] \
        [--k1-dir outputs/dev_tables/k1] [--selection outputs/selection_v3] \
        [--out-dir outputs/paper_tables] [--paper paper]

Two products.  `outputs/paper_tables/*.tex` holds the six development tables with every
number wrapped in `\\devnum{}`, in the structure the paper's tables already have.
`outputs/paper_tables/numbers.csv` lists every `\\devnum{}` the paper carries, where in
the paper it sits, and whether this package produces it: a number this package cannot
produce (the cross-domain traces, ACcoding, the CI pool, the predictor comparison) is
marked as such rather than quietly dropped.

Nothing here writes into `paper/`.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from spjf_guard import config as cfgmod  # noqa: E402
from spjf_guard.experiment import paper_tables as pt  # noqa: E402

DEVNUM = re.compile(r"\\devnum\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}")
LABEL = re.compile(r"\\label\{(tab:[A-Za-z0-9_]+)\}")

NOT_PRODUCED = (
    ("cross-domain", ("cross-domain", "OULAD", "Kaggle", "transfer")),
    ("accoding", ("ACcoding", "accoding")),
    ("ci-pool", ("CI pool", "continuous integration", "Travis", "GitHub Actions")),
    ("predictor-comparison", ("GRU", "refitted", "AUC", "Spearman", "MAE")),
    ("sealed", ("sealed", "2023-1", "2023-2", "2024-1", "held out")),
)
"""Substrings in the surrounding line that mark a number this package does not produce."""

BY_SECTION = {
    "01_introduction": "headline-quote",
    "03_problem_model": "model-constant",
    "04_prediction": "predictor-comparison",
    "05_scheduling": "mechanism-constant",
    "06_theory": "theory-constant",
    "07_data": "data-description",
    "09_limitations": "limitation-quote",
    "A_proofs": "theory-constant",
    "main": "abstract-quote",
    "main_article": "abstract-quote",
}
"""What a number belongs to when nothing in its own line says otherwise.  A headline
quote is a number this package does produce, restated in prose; the rest are outside the
package: the data description, the predictor comparison, the theory's own constants."""

BY_TABLE = {
    "tab:cross": "cross-domain",
    "tab:scores": "predictor-comparison",
    "tab:sens": "sensitivity-study",
    "tab:policies": "mechanism-constant",
}

OURS = ("08_experiments", "fig_")
"""Where a number that fails to match is this package's own: the experiment section and
the figure captions print what the development run measured, so a mismatch there means
the package now prints a different value, not that the number came from elsewhere.  Those
rows are labelled `package-differs` and counted on their own -- they are the answer to
"which paper numbers changed".  A number that matches nothing and sits nowhere on this
list gets no reason at all, and `check_generated.py` fails on it."""

DIFFERS = "package-differs"


def read_rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def parameter_map(rows: list[dict], promises) -> dict:
    """{(level, policy): parameters} with the promise each guarded policy carries."""
    out = {}
    for row in rows:
        promise = None
        for candidate in promises:
            if f"({candidate:g})" in row["policy"]:
                promise = candidate
        entry = {k: float(v) for k, v in row.items() if k not in ("policy",)}
        entry["promise_s"] = promise
        out[(int(float(row["level"])), row["policy"])] = entry
    return out


def guard_row_order(cfg) -> list[str]:
    """The order the guard table prints: per promise, the winner, its ablations, then the
    comparators."""
    names = []
    for promise in cfg.promises_s:
        names.append(f"Guard({promise:g})")
        for family in ("fixed", "capped", "hybrid"):
            names.append(f"{cfg.family_label(family)}({promise:g})")
        names.append(f"Fixed({promise:g})")
        names.append(f"Skip({promise:g})")
    return names


def setup_items(cfg, table, selection_rows, parameters) -> list[tuple[str, str]]:
    """The description table, filled from what the run and the selection actually did."""
    limit = cfg.limit_s
    items = [
        (
            "Trace and pool",
            rf"CodeBench development terms under the \devnum{{{limit:g}}} s limit, "
            rf"five overlays, three load levels",
        ),
        (
            "Load levels",
            r"$k = \devnum{8/5/4}$ on four overlays and $\devnum{7/5/4}$ on the fifth",
        ),
        (
            "Promise to parameter",
            rf"$B_{{\max}} = k(G - (3-2/k)L)$ with $L = \devnum{{{limit:g}}}$ s, no data used",
        ),
        (
            "Budget shapes",
            r"one mechanism, three shapes under the same cap: constant, "
            r"$+\,\eta k (t - a_q)$, $+\,\gamma w_q$",
        ),
        (
            "Selection rule",
            r"feasible iff harm $\le G/2$ in every one of the \devnum{15} validation "
            r"cells; objective the worst-cell gap closed; ties to smaller worst harm, "
            r"then $B_0$, then $\eta$, then $\gamma$",
        ),
    ]
    for row in selection_rows:
        if row.get("family") != "joint":
            continue
        promise = float(row["promise_s"])
        items.append(
            (
                rf"Selected, $G = \devnum{{{promise:g}}}$ s",
                rf"{row['from_family']} shape, "
                rf"$B_0 = \devnum{{{float(row['b0_base_s']):g}}}k/4$ s, "
                rf"$\eta = \devnum{{{float(row['eta']):.2f}}}$, "
                rf"$\gamma = \devnum{{{float(row['gam_base_s']):g}}}k/4$ s; worst-cell gap "
                rf"\devnum{{{float(row['worst_gap_closed']):.4f}}}, worst-cell harm "
                rf"\devnum{{{float(row['worst_harm_s']):.1f}}} s against "
                rf"\devnum{{{float(row['harm_limit_s']):.0f}}} s, "
                rf"\devnum{{{int(row['n_feasible'])}}} of "
                rf"\devnum{{{int(row['n_candidates'])}}} candidates feasible",
            )
        )
    return items


def classify(context: str, section: str, table: str) -> str:
    """Why this package does not produce the number, in one word.

    Empty means there is no reason: the number matches nothing this package writes and
    belongs to no part of the paper that is outside the package.  That is a failure, and
    `check_generated.py` reports it as one.
    """
    for label, needles in NOT_PRODUCED:
        if any(needle in context for needle in needles):
            return label
    if table in BY_TABLE:
        return BY_TABLE[table]
    if section in BY_SECTION:
        return BY_SECTION[section]
    return DIFFERS if section.startswith(OURS) else ""


def paper_numbers(paper_dir: Path, produced: dict) -> list[dict]:
    """Every `\\devnum{}` in the paper, with where it sits and who produces it."""
    rows = []
    for path in sorted(paper_dir.rglob("*.tex")):
        table = ""
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            found = LABEL.search(line)
            if found:
                table = found.group(1)
            if r"\end{table}" in line:
                table = ""
            for index, value in enumerate(DEVNUM.findall(line)):
                key = f"{path.stem}:{number}:{index}"
                cleaned = value.replace("{,}", "").replace(r"\%", "")
                rows.append(
                    {
                        "key": key,
                        "section": path.stem,
                        "line": number,
                        "table": table or "running text",
                        "value": value,
                        "produced_by": produced.get(cleaned, ""),
                        "not_produced": ""
                        if cleaned in produced
                        else classify(line, path.stem, table),
                        "context": line.strip()[:160],
                    }
                )
    return rows


def difference_values(rows: list[dict], out: dict) -> None:
    """The paired differences, in the two shapes the paper prints them in.

    The paper states a difference of two policies as one `\\devnum{}`: an estimate and its
    interval together, sometimes inside math mode and sometimes bare.  Both spellings are
    indexed, so a claim like "Guard(600) gives up 0.116 [0.077, 0.143] of the gap" matches
    the row that produced it instead of counting as a number with no source.
    """
    for row in rows:
        where = f"dev_tables/paired_differences.csv[{row['left']} - {row['right']}]"
        for field, lo_field, hi_field in (
            ("difference_gap", "gap_lo", "gap_hi"),
            ("difference_s", "lo", "hi"),
        ):
            try:
                value = float(row[field])
                low, high = float(row[lo_field]), float(row[hi_field])
            except (KeyError, TypeError, ValueError):
                continue
            out.setdefault(f"{value:.3f} [{low:.3f}, {high:.3f}]", where)
            out.setdefault(f"${value:+.3f}$ $[{low:.3f}, {high:.3f}]$", where)
            out.setdefault(f"{value:.3f}", where)


def produced_values(table: list[dict], k1: list[dict], residuals: list[dict]) -> dict:
    """{printed value: which table of ours carries it}, for the matching above."""
    out: dict[str, str] = {}

    def add(value, digits, where):
        if value in ("", None):
            return
        try:
            text = f"{float(value):.{digits}f}"
        except (TypeError, ValueError):
            return
        out.setdefault(text, where)

    for row in table:
        for field, digits in (
            ("p99_dl_s", 2),
            ("mean_s", 3),
            ("gap_closed", 3),
            ("reduction_pct", 1),
            ("max_excess_s", 1),
            ("harm_s", 1),
            ("fired_pct", 2),
        ):
            add(row.get(field), digits, f"dev_tables/main_table.csv[{row['policy']}]")
    for row in k1:
        for field, digits in (("p99_dl_s", 2), ("gap_closed", 3), ("harm_s", 1)):
            add(row.get(field), digits, f"dev_tables/k1/main_table.csv[{row['policy']}]")
    for row in residuals:
        for field, digits in (
            ("max_abs_residual_L", 3),
            ("ratio_to_bound", 3),
            ("r2_net_over_k", 3),
        ):
            add(row.get(field), digits, f"dev_tables/identity_residuals.csv[{row['policy']}]")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, default=ROOT / "configs" / "main.yaml")
    ap.add_argument("--dev-dir", type=Path, default=ROOT / "outputs" / "dev_tables")
    ap.add_argument("--k1-dir", type=Path, default=None)
    ap.add_argument("--selection", type=Path, default=ROOT / "outputs" / "selection_v3")
    ap.add_argument("--out-dir", type=Path, default=ROOT / "outputs" / "paper_tables")
    ap.add_argument("--paper", type=Path, default=ROOT / "paper")
    args = ap.parse_args()

    cfg = cfgmod.load(args.config, expand_environment=False)
    k1_dir = args.k1_dir or args.dev_dir / "k1"
    table = read_rows(args.dev_dir / "main_table.csv")
    k1 = read_rows(k1_dir / "main_table.csv")
    residuals = read_rows(args.dev_dir / "identity_residuals.csv")
    parameters = parameter_map(
        read_rows(args.dev_dir / "policy_parameters.csv"), cfg.promises_s
    )
    k1_parameters = parameter_map(read_rows(k1_dir / "policy_parameters.csv"), cfg.promises_s)
    selection_rows = read_rows(args.selection / "selected_parameters.csv")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    if table:
        order = guard_row_order(cfg)
        (args.out_dir / "tab_rank.tex").write_text(pt.rank_table(table), encoding="utf-8")
        (args.out_dir / "tab_guard.tex").write_text(
            pt.guard_table(table, parameters, order), encoding="utf-8"
        )
        (args.out_dir / "tab_adv.tex").write_text(pt.adversarial_table(table), encoding="utf-8")
        (args.out_dir / "tab_setup.tex").write_text(
            pt.setup_table(setup_items(cfg, table, selection_rows, parameters)),
            encoding="utf-8",
        )
        written += ["tab_rank.tex", "tab_guard.tex", "tab_adv.tex", "tab_setup.tex"]
    if residuals:
        names = ["SPJF-E", "Guard(600)", "SPJF-reversed"]
        (args.out_dir / "tab_resid.tex").write_text(
            pt.residual_table(residuals, names), encoding="utf-8"
        )
        written.append("tab_resid.tex")
    if k1:
        order = ["FCFS", "SJF", "SPJF-E"] + guard_row_order(cfg)
        (args.out_dir / "tab_k1.tex").write_text(
            pt.single_server_table(k1, k1_parameters, order), encoding="utf-8"
        )
        written.append("tab_k1.tex")

    produced = produced_values(table, k1, residuals)
    difference_values(read_rows(args.dev_dir / "paired_differences.csv"), produced)
    difference_values(read_rows(k1_dir / "paired_differences.csv"), produced)
    numbers = paper_numbers(args.paper, produced)
    with open(args.out_dir / "numbers.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(numbers[0]))
        writer.writeheader()
        writer.writerows(numbers)
    written.append("numbers.csv")

    matched = sum(1 for r in numbers if r["produced_by"])
    unmatched = [r for r in numbers if not r["produced_by"]]
    by_reason: dict[str, int] = {}
    for row in unmatched:
        by_reason[row["not_produced"] or "no reason"] = (
            by_reason.get(row["not_produced"] or "no reason", 0) + 1
        )
    print(f"wrote {', '.join(written)} in {args.out_dir}")
    print(f"paper numbers: {len(numbers)}, matched to this package: {matched}")
    for reason, count in sorted(by_reason.items(), key=lambda kv: -kv[1]):
        print(f"  not produced [{reason}]: {count}")
    differs = [r for r in unmatched if r["not_produced"] == DIFFERS]
    if differs:
        where: dict[str, int] = {}
        for row in differs:
            key = f"{row['section']} {row['table']}"
            where[key] = where.get(key, 0) + 1
        print(f"  of which this package prints its own value for {len(differs)}:")
        for key, count in sorted(where.items(), key=lambda kv: -kv[1]):
            print(f"    {key}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
