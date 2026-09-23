"""Write the paper's tables and the map of every number the paper quotes.

    uv run python scripts/emit_paper_tables.py [--dev-dir outputs/dev_tables] \
        [--k1-dir outputs/dev_tables/k1] [--selection outputs/selection_v3] \
        [--sealed-dir outputs/sealed_tables] [--sealed-k1-dir <dir>] \
        [--sealed-predictor-dir <dir>] [--sealed-visibility-dir <dir>] \
        [--dev-exact-dir <dir>] [--sealed-exact-dir <dir>] \
        [--out-dir outputs/paper_tables] [--paper paper]

Two products.  `outputs/paper_tables/*.tex` holds the six development tables with every
number wrapped in `\\devnum{}`, in the structure the paper's tables already have.
`outputs/paper_tables/numbers.csv` lists every `\\devnum{}` the paper carries, where in
the paper it sits, and whether this package produces it: a number this package cannot
produce (the cross-domain traces, ACcoding, the CI pool, the predictor comparison) is
marked as such rather than quietly dropped.

Given a sealed directory, the same five result tables are emitted a second time from the
sealed run's CSVs as `tab_*_sealed.tex`, with `_sealed` on the label and every figure in
`\\sealednum{}` rather than `\\devnum{}` -- the development macro says "not a sealed
term" (`paper/main.tex`), so a sealed figure cannot go through it.  `numbers.csv` then
also carries the paper's `\\sealednum{}` figures, under keys prefixed `sealed.`, and the
classifier stops excusing a number because its line says "sealed": from then on those
numbers have a producing table and are checked like any other.  Without the option
nothing changes, which is why it is an option.

`--dev-exact-dir` and `--sealed-exact-dir` add two exact-policy tables, rewrite
`tab_visibility.tex` from the exact comparison, and give the attribution ladder and the
class-history sensitivity a source as well.  They are opt-in so the historical
`outputs/paper_tables/` files, including `numbers.csv`, stay byte-identical; use
`--out-dir outputs/consistent_paper_tables` when enabling them.

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
SEALED_MACRO = "sealednum"
"""What the paper wraps a sealed-term figure in, as `\\devnum{}` wraps a development one.
The paper defines it beside `\\devnum` and the two are what tell the reader, and every
check in this package, which run a printed number came from."""
SEALEDNUM = re.compile(r"\\sealednum\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}")
SEALED_PREFIX = "sealed."
"""What a `numbers.csv` key carries when the figure is a sealed-term one, so that the two
namespaces cannot collide and a list that names a key says which run it belongs to."""
LABEL = re.compile(r"\\label\{(tab:[A-Za-z0-9_]+)\}")
SECTION_CMD = re.compile(r"\\(?:sub){0,2}section\*?\{([^{}]*)\}")
NOT_WORD = re.compile(r"[^a-z0-9]+")

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
    "S_theory_additions": "theory-constant",
    "main": "abstract-quote",
    "main_article": "abstract-quote",
    "supplementary": "moved-from-main",
}
"""What a number belongs to when nothing in its own line says otherwise.  A headline
quote is a number this package does produce, restated in prose; the rest are outside the
package: the data description, the predictor comparison, the theory's own constants.
`supplementary` is the running text of the supplementary file, whose every item was in the
main manuscript until the referee asked for the paper to be shortened; the tables it
carries are classified by their own label below, not by this entry."""

BY_TABLE = {
    "tab:cross": "cross-domain",
    "tab:scores": "predictor-comparison",
    "tab:sens": "sensitivity-study",
    "tab:policies": "mechanism-constant",
    "tab:pred_cross": "predictor-comparison",
}
"""What a table's numbers belong to, by the table's main-text label.  A table that has
moved into the supplementary file carries the same rows under `tab:s_...` and is read
under the same entry."""

OURS_TABLES = (
    "tab:rank",
    "tab:guard",
    "tab:guard_abl",
    "tab:adv",
    "tab:resid",
    "tab:k1",
    "tab:setup",
    "tab:exact_visibility",
    "tab:same_copy_exposure",
)
"""Tables whose rows this package produces.  A value of theirs that matches nothing is
this package printing something else, so it is counted as `package-differs` rather than
excused by the file the table happens to sit in.  The manuscript is being shortened by
moving tables into the supplementary file, where they are renamed `tab:s_...`; the names
here are the main-text spelling, and a label is read under that spelling."""

SUPPLEMENT_PREFIX = "tab:s_"


def base_label(table: str) -> str:
    """A table's label in its main-text spelling: `tab:s_k1` is `tab:k1` moved.

    What a table is classified as follows the table, not the file it ended up in.
    """
    if table.startswith(SUPPLEMENT_PREFIX):
        return "tab:" + table[len(SUPPLEMENT_PREFIX) :]
    return table


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


EXACT_SOURCE_FILES = ("exact_comparison.csv", "same_copy_exposure.csv")


def read_exact_rows(tables: Path) -> tuple[list[dict], list[dict]]:
    """Read a caller-supplied exact source, rejecting incomplete inputs."""
    loaded: list[list[dict]] = []
    for filename in EXACT_SOURCE_FILES:
        path = tables / filename
        if not path.is_file():
            raise SystemExit(f"explicit exact source is missing required file: {path}")
        rows = read_rows(path)
        if not rows:
            raise SystemExit(f"explicit exact source has no data rows: {path}")
        loaded.append(rows)
    return loaded[0], loaded[1]


def read_optional_exact(tables: Path | None) -> tuple[list[dict], list[dict]] | None:
    """The exact source when a directory was given, and nothing at all when none was."""
    return read_exact_rows(tables) if tables is not None else None


def exact_pair(rows: tuple[list[dict], list[dict]] | None) -> tuple[list[dict], list[dict]]:
    """The exact comparison and its exposure audit, as two lists a run can always index."""
    return rows if rows is not None else ([], [])


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


def reasons(sealed: bool) -> tuple:
    """The `NOT_PRODUCED` list a run classifies with.

    Once a sealed directory is given, "sealed", "2023-1" and "held out" stop being
    reasons for a number to have no source: the sealed tables produce those numbers, and
    a sealed figure that matches none of them is a number with no source, which is the
    failure this file exists to find.
    """
    return tuple(entry for entry in NOT_PRODUCED if not sealed or entry[0] != "sealed")


def classify(context: str, section: str, table: str, not_produced=NOT_PRODUCED) -> str:
    """Why this package does not produce the number, in one word.

    Empty means there is no reason: the number matches nothing this package writes and
    belongs to no part of the paper that is outside the package.  That is a failure, and
    `check_generated.py` reports it as one.
    """
    for label, needles in not_produced:
        if any(needle in context for needle in needles):
            return label
    base = base_label(table)
    if base in BY_TABLE:
        return BY_TABLE[base]
    if base in OURS_TABLES:
        return DIFFERS
    if section in BY_SECTION:
        return BY_SECTION[section]
    return DIFFERS if section.startswith(OURS) else ""


def slug(title: str) -> str:
    """A section title as an anchor: lower case, punctuation and macros dropped."""
    text = re.sub(r"\\[A-Za-z]+", " ", title).lower()
    return NOT_WORD.sub("-", text).strip("-")[:40] or "untitled"


def _number_row(found: dict, produced: dict, not_produced: tuple) -> dict:
    """One `numbers.csv` row: where the figure sits, and who produces it or why nobody."""
    cleaned = found["value"].replace("{,}", "").replace(r"\%", "")
    return {
        "key": found["key"],
        "section": found["section"],
        "line": found["line"],
        "table": found["table"] or "running text",
        "value": found["value"],
        "produced_by": produced.get(cleaned, ""),
        "not_produced": ""
        if cleaned in produced
        else classify(found["context"], found["section"], found["table"], not_produced),
        "context": found["context"].strip()[:160],
    }


def _macros(produced: dict, sealed: dict | None) -> list[tuple]:
    """The macros a run reads, with the values each one is matched against.  The sealed
    macro joins the list only once a sealed run's values are given."""
    return [(DEVNUM, produced, "")] + (
        [(SEALEDNUM, sealed, SEALED_PREFIX)] if sealed is not None else []
    )


def _anchor_state(line: str, table: str, anchor: str) -> tuple[str, str]:
    """Where a figure on this line sits: inside which table, under which section."""
    heading = SECTION_CMD.search(line)
    if heading:
        anchor = slug(heading.group(1))
    found = LABEL.search(line)
    if found:
        table = found.group(1)
    if r"\end{table}" in line or r"\end{table*}" in line:
        table = ""
    return table, anchor


def _file_numbers(path: Path, macros: list[tuple], not_produced: tuple) -> list[dict]:
    """Every marked figure in one file, in the order the file prints them."""
    rows: list[dict] = []
    table, anchor = "", "front-matter"
    seen: dict[str, int] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        table, anchor = _anchor_state(line, table, anchor)
        for pattern, values, prefix in macros:
            for value in pattern.findall(line):
                spot = table or anchor
                where = f"{prefix}{spot}"
                seen[where] = seen.get(where, 0) + 1
                rows.append(
                    _number_row(
                        {
                            "key": f"{prefix}{path.stem}:{spot}:{seen[where]}",
                            "section": path.stem,
                            "line": number,
                            "table": table,
                            "value": value,
                            "context": line,
                        },
                        values or {},
                        not_produced,
                    )
                )
    return rows


def paper_numbers(paper_dir: Path, produced: dict, sealed: dict | None = None) -> list[dict]:
    """Every marked figure in the paper, with where it sits and who produces it.

    The key is `<file>:<anchor>:<n>`, where the anchor is the table's label when the number
    sits in a table and the enclosing section otherwise, and `n` counts the numbers under
    that anchor.  It carries no line number on purpose: the paper is re-laid-out between
    passes -- floats move, appendices become supplementary sections -- and a key that moved
    with them would make every list that names one stale.  The line is kept as its own
    column, for a person looking the number up.

    `\\devnum{}` is a development figure and `\\sealednum{}` a sealed-term one; the second
    is read only when a sealed run's values are given, and its keys carry the `sealed.`
    prefix, counted in their own sequence.
    """
    macros = _macros(produced, sealed)
    not_produced = reasons(sealed is not None)
    rows: list[dict] = []
    for path in sorted(paper_dir.rglob("*.tex")):
        rows += _file_numbers(path, macros, not_produced)
    return rows


def difference_values(rows: list[dict], out: dict, source: str = "dev_tables") -> None:
    """The paired differences, in the two shapes the paper prints them in.

    The paper states a difference of two policies as one marked figure: an estimate and its
    interval together, sometimes inside math mode and sometimes bare.  Both spellings are
    indexed, so a claim like "Guard(600) gives up 0.116 [0.077, 0.143] of the gap" matches
    the row that produced it instead of counting as a number with no source.
    """
    for row in rows:
        where = f"{source}/paired_differences.csv[{row['left']} - {row['right']}]"
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


def _adder(out: dict):
    """Index one printed spelling of a value, the first source for it winning."""

    def add(value, digits, where):
        if value in ("", None):
            return
        try:
            text = f"{float(value):.{digits}f}"
        except (TypeError, ValueError):
            return
        out.setdefault(text, where)

    return add


def produced_values(
    table: list[dict], k1: list[dict], residuals: list[dict], source: str = "dev_tables"
) -> dict:
    """{printed value: which table of ours carries it}, for the matching above."""
    out: dict[str, str] = {}
    add = _adder(out)
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
            add(row.get(field), digits, f"{source}/main_table.csv[{row['policy']}]")
    for row in k1:
        for field, digits in (("p99_dl_s", 2), ("gap_closed", 3), ("harm_s", 1)):
            add(row.get(field), digits, f"{source}/k1/main_table.csv[{row['policy']}]")
    for row in residuals:
        for field, digits in (
            ("max_abs_residual_L", 3),
            ("ratio_to_bound", 3),
            ("r2_net_over_k", 3),
        ):
            add(row.get(field), digits, f"{source}/identity_residuals.csv[{row['policy']}]")
    return out


def predictor_values(rows: list[dict], out: dict, source: str = "sealed_predictor") -> None:
    """The sealed terms' predictor metrics, in the spellings section 4 prints them in.

    These have no table of their own in the paper: the section quotes them in running
    text, so indexing them here is what gives a sealed AUROC a source instead of leaving
    it as a number nobody produces.
    """
    add = _adder(out)
    for row in rows:
        where = f"{source}/predictor_metrics.csv[{row['target']} {row['score']}]"
        for field, digits in (
            ("auroc", 4),
            ("auroc", 3),
            ("average_precision", 3),
            ("rmse_log1p", 4),
            ("spearman", 3),
        ):
            add(row.get(field), digits, where)


def visibility_values(rows: list[dict], out: dict, source: str = "visibility") -> None:
    """Scheduling and exposure values printed by the policy-consistency tables."""
    add = _adder(out)
    for row in rows:
        where = f"{source}/visibility_comparison.csv[{row['policy']} level {row['level']}]"
        for field, digits in (
            ("p99_dl_s", 2),
            ("gap_closed", 3),
            ("gap_closed_lo", 3),
            ("gap_closed_hi", 3),
            ("max_excess_s", 1),
            ("harm_s", 1),
            ("fired_pct", 2),
        ):
            add(row.get(field), digits, where)


def visibility_exposure_values(rows: list[dict], out: dict, source: str = "visibility") -> None:
    """Exposure values, including the percent spellings used by the generated table."""
    add = _adder(out)
    for row in rows:
        where = f"{source}/visibility_exposure.csv[{row['policy']} level {row['level']}]"
        for field in (
            "overall_affected_share",
            "deadline_affected_share",
            "unreplayed_overall_affected_share",
            "overall_any_exposure_share",
        ):
            value = row.get(field)
            add(100.0 * float(value) if value not in (None, "") else value, 2, where)
        for field in ("overall_premature_mean", "overall_premature_p99"):
            add(row.get(field), 1, where)
    _exposure_means(rows, add, source)


def _exposure_means(rows: list[dict], add, source: str) -> None:
    """The same exposure figures averaged over the overlays, as the audit table prints
    them: a mean the paper quotes has to find the cell group it came from."""
    groups = {(row["level"], row["policy"]) for row in rows}
    for level, policy in groups:
        selected = [row for row in rows if row["level"] == level and row["policy"] == policy]
        where = f"{source}/visibility_exposure.csv[{policy} level {level} mean]"

        def mean(field: str) -> float:
            return sum(float(row[field]) for row in selected) / len(selected)

        for field in (
            "overall_affected_share",
            "deadline_affected_share",
            "unreplayed_overall_affected_share",
        ):
            add(100.0 * mean(field), 2, where)
        for field in ("overall_premature_mean", "overall_premature_p99"):
            add(mean(field), 1, where)


def exact_values(
    rows: list[dict],
    out: dict,
    source: str = "consistent_visibility",
    filename: str = "exact_comparison.csv",
) -> None:
    """Scheduling figures printed by the exact policy-specific comparison.

    The attribution ladder and the class-history sensitivity write the same columns, so
    they are indexed through this function under their own file name.
    """
    add = _adder(out)
    for row in rows:
        name = row.get("policy") or f"{row['base_policy']}|{row['variant']}"
        where = f"{source}/{filename}[{name} level {row['level']}]"
        for field, digits in (
            ("p99_dl_s", 2),
            ("gap_closed", 3),
            ("gap_closed_lo", 3),
            ("gap_closed_hi", 3),
            ("max_excess_s", 1),
            ("harm_s", 1),
            ("fired_pct", 2),
        ):
            add(row.get(field), digits, where)


def exact_exposure_values(
    rows: list[dict], out: dict, source: str = "consistent_visibility"
) -> None:
    """Affected-share and displacement figures printed by the exact audit table."""
    add = _adder(out)
    for row in rows:
        where = f"{source}/same_copy_exposure.csv[{row['policy']} level {row['level']}]"
        for field in ("affected_share", "deadline_affected_share"):
            value = row.get(field)
            add(100.0 * float(value) if value not in (None, "") else value, 2, where)
        for field, digits in (
            ("records_mean", 2),
            ("records_p99", 1),
            ("abs_delta_score_p99", 3),
            ("abs_rank_displacement_p99", 1),
            ("abs_rank_displacement_max", 0),
        ):
            add(row.get(field), digits, where)


RESIDUAL_POLICIES = ("SPJF-E", "Guard(600)", "SPJF-reversed")
"""The three policies `tab:resid` prints, on the first overlay."""


def as_sealed(text: str) -> str:
    """The same table, marked as sealed-term figures rather than development ones.

    `\\devnum{}` means "this number is development data, not a sealed term"
    (`paper/main.tex`), so the sealed copy cannot go through it: the macro becomes
    `\\sealednum{}` and the label gains the `_sealed` suffix, which is what lets the two
    tables sit in one document and be found by their own labels.
    """
    text = LABEL.sub(lambda m: rf"\label{{{m.group(1)}_sealed}}", text)
    return text.replace(r"\devnum{", "\\" + SEALED_MACRO + "{")


def read_run(cfg, tables: Path, k1_dir: Path | None) -> dict:
    """One run's CSVs.  A directory that is not there reads as no rows, not as an error:
    the sealed run has no single-server tables until its own k = 1 command is run."""
    k1 = read_rows(k1_dir / "main_table.csv") if k1_dir else []
    return {
        "table": read_rows(tables / "main_table.csv"),
        "residuals": read_rows(tables / "identity_residuals.csv"),
        "parameters": parameter_map(
            read_rows(tables / "policy_parameters.csv"), cfg.promises_s
        ),
        "k1": k1,
        "k1_parameters": parameter_map(
            read_rows(k1_dir / "policy_parameters.csv") if k1_dir else [], cfg.promises_s
        ),
        "differences": read_rows(tables / "paired_differences.csv"),
        "k1_differences": read_rows(k1_dir / "paired_differences.csv") if k1_dir else [],
    }


def emit_tables(cfg, run: dict, out_dir: Path, sealed: bool = False) -> list[str]:
    """The five result tables of one run.  `tab:setup` describes the protocol rather than
    a result, so it has no sealed copy: the protocol is the same document either way."""
    written: list[str] = []

    def put(stem: str, text: str) -> None:
        name = f"{stem}_sealed.tex" if sealed else f"{stem}.tex"
        (out_dir / name).write_text(as_sealed(text) if sealed else text, encoding="utf-8")
        written.append(name)

    if run["table"]:
        put("tab_rank", pt.rank_table(run["table"]))
        put("tab_guard", pt.guard_table(run["table"], run["parameters"], guard_row_order(cfg)))
        put("tab_adv", pt.adversarial_table(run["table"]))
    if run["residuals"]:
        put("tab_resid", pt.residual_table(run["residuals"], list(RESIDUAL_POLICIES)))
    if run["k1"]:
        order = ["FCFS", "SJF", "SPJF-E"] + guard_row_order(cfg)
        put("tab_k1", pt.single_server_table(run["k1"], run["k1_parameters"], order))
    return written


def emit_visibility(tables: Path, out_dir: Path, sealed: bool = False) -> list[str]:
    """The policy-consistency comparison and the original-clock exposure audit."""
    comparison = read_rows(tables / "visibility_comparison.csv")
    exposure = read_rows(tables / "visibility_exposure.csv")
    written: list[str] = []
    for stem, text in (
        ("tab_visibility", pt.visibility_table(comparison) if comparison else ""),
        ("tab_visibility_audit", pt.visibility_audit_table(exposure) if exposure else ""),
    ):
        if not text:
            continue
        name = f"{stem}_sealed.tex" if sealed else f"{stem}.tex"
        (out_dir / name).write_text(as_sealed(text) if sealed else text, encoding="utf-8")
        written.append(name)
    return written


def emit_exact(tables: Path, out_dir: Path, sealed: bool = False) -> list[str]:
    """The policy-specific exact comparison and same-copy exposure decomposition.

    `tab_visibility.tex` is rewritten from the exact comparison, which carries the three
    reference variants as well, so in an exact package that table's four rows have a
    single source.  It runs after `emit_visibility`, whose three-row copy it replaces;
    the historical directory never sees it, because the exact source is opt-in.
    """
    comparison, exposure = read_exact_rows(tables)
    written: list[str] = []
    for stem, text in (
        ("tab_exact_visibility", pt.exact_visibility_table(comparison) if comparison else ""),
        (
            "tab_same_copy_exposure",
            pt.same_copy_exposure_table(exposure) if exposure else "",
        ),
        ("tab_visibility", pt.exact_headline_table(comparison) if comparison else ""),
    ):
        if not text:
            continue
        name = f"{stem}_sealed.tex" if sealed else f"{stem}.tex"
        (out_dir / name).write_text(as_sealed(text) if sealed else text, encoding="utf-8")
        written.append(name)
    return written


def emit_optional_exact(tables: Path | None, out_dir: Path, sealed: bool = False) -> list[str]:
    """Emit nothing until an exact directory is explicitly supplied."""
    return emit_exact(tables, out_dir, sealed) if tables is not None else []


EXACT_EXTRA_FILES = ("attribution_comparison.csv", "exact_sensitivity_comparison.csv")
"""The exact run's other two comparisons.  They print the same columns as the exact one
and no table of their own, so they are read only to give their figures a source."""


def read_exact_extras(tables: Path | None) -> tuple[list[dict], list[dict]]:
    """The attribution ladder and the class-history sensitivity, when they are there."""
    if tables is None:
        return [], []
    first, second = (read_rows(tables / name) for name in EXACT_EXTRA_FILES)
    return first, second


def run_values(
    run: dict,
    source: str,
    predictor: list[dict],
    visibility_comparison: list[dict] | None = None,
    visibility_exposure: list[dict] | None = None,
    exact_comparison: list[dict] | None = None,
    exact_exposure: list[dict] | None = None,
    exact_attribution: list[dict] | None = None,
    exact_sensitivity: list[dict] | None = None,
) -> dict:
    """Every figure one run produces, indexed by the way the paper would print it."""
    values = produced_values(run["table"], run["k1"], run["residuals"], source)
    difference_values(run["differences"], values, source)
    difference_values(run["k1_differences"], values, f"{source}/k1")
    predictor_values(predictor, values)
    visibility_values(
        visibility_comparison or [], values, source.replace("tables", "visibility")
    )
    visibility_exposure_values(
        visibility_exposure or [], values, source.replace("tables", "visibility")
    )
    exact_values(
        exact_comparison or [], values, source.replace("tables", "consistent_visibility")
    )
    exact_exposure_values(
        exact_exposure or [], values, source.replace("tables", "consistent_visibility")
    )
    for rows, filename in (
        (exact_attribution, "attribution_comparison.csv"),
        (exact_sensitivity, "exact_sensitivity_comparison.csv"),
    ):
        exact_values(
            rows or [],
            values,
            source.replace("tables", "consistent_visibility"),
            filename,
        )
    return values


def emit_development(cfg, args, development: dict, selection_rows: list[dict]) -> list[str]:
    """Every table the development run writes, `tab:setup` included.

    `tab:setup` describes what the run and the selection did rather than what they
    measured, so it is built here from both and has no counterpart in a sealed package.
    """
    written = emit_tables(cfg, development, args.out_dir)
    written += emit_visibility(args.dev_visibility_dir, args.out_dir)
    written += emit_optional_exact(args.dev_exact_dir, args.out_dir)
    if development["table"]:
        items = setup_items(
            cfg, development["table"], selection_rows, development["parameters"]
        )
        (args.out_dir / "tab_setup.tex").write_text(pt.setup_table(items), encoding="utf-8")
        written.append("tab_setup.tex")
    return written


def development_run_values(args, development: dict, exact_rows) -> dict:
    """Every figure the development run produces, indexed as the paper prints it."""
    return run_values(
        development,
        "dev_tables",
        [],
        read_rows(args.dev_visibility_dir / "visibility_comparison.csv"),
        read_rows(args.dev_visibility_dir / "visibility_exposure.csv"),
        *exact_pair(exact_rows),
        *read_exact_extras(args.dev_exact_dir),
    )


def emit_sealed(cfg, args, sealed_run: dict) -> list[str]:
    """The sealed run's copies of the result tables, the optional ones included."""
    written = emit_tables(cfg, sealed_run, args.out_dir, sealed=True)
    if args.sealed_visibility_dir is not None:
        written += emit_visibility(args.sealed_visibility_dir, args.out_dir, sealed=True)
    written += emit_optional_exact(args.sealed_exact_dir, args.out_dir, sealed=True)
    return written


def sealed_run_values(args, sealed_run: dict, exact_rows) -> dict:
    """Every figure the sealed run produces, from whichever of its directories were given."""
    visibility = args.sealed_visibility_dir
    return run_values(
        sealed_run,
        "sealed_tables",
        read_rows(args.sealed_predictor_dir / "predictor_metrics.csv")
        if args.sealed_predictor_dir
        else [],
        read_rows(visibility / "visibility_comparison.csv") if visibility else [],
        read_rows(visibility / "visibility_exposure.csv") if visibility else [],
        *exact_pair(exact_rows),
        *read_exact_extras(args.sealed_exact_dir),
    )


def write_numbers(numbers: list[dict], out_dir: Path) -> None:
    """`numbers.csv`: one row per marked figure, in the order the paper prints them."""
    with open(out_dir / "numbers.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(numbers[0]))
        writer.writeheader()
        writer.writerows(numbers)


def reason_counts(unmatched: list[dict]) -> dict[str, int]:
    """How many unmatched figures each reason accounts for.  A figure with no reason is
    counted under "no reason", which is what `check_generated.py` fails on."""
    counts: dict[str, int] = {}
    for row in unmatched:
        reason = row["not_produced"] or "no reason"
        counts[reason] = counts.get(reason, 0) + 1
    return counts


def report_differences(differs: list[dict]) -> None:
    """Where this package now prints its own value: the answer to "which numbers changed"."""
    if not differs:
        return
    where: dict[str, int] = {}
    for row in differs:
        key = f"{row['section']} {row['table']}"
        where[key] = where.get(key, 0) + 1
    print(f"  of which this package prints its own value for {len(differs)}:")
    for key, count in sorted(where.items(), key=lambda kv: -kv[1]):
        print(f"    {key}: {count}")


def report(numbers: list[dict], written: list[str], out_dir: Path) -> None:
    """What the run wrote, what it matched, and what it did not, largest reason first."""
    matched = sum(1 for r in numbers if r["produced_by"])
    unmatched = [r for r in numbers if not r["produced_by"]]
    print(f"wrote {', '.join(written)} in {out_dir}")
    print(f"paper numbers: {len(numbers)}, matched to this package: {matched}")
    for reason, count in sorted(reason_counts(unmatched).items(), key=lambda kv: -kv[1]):
        print(f"  not produced [{reason}]: {count}")
    report_differences([r for r in unmatched if r["not_produced"] == DIFFERS])


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, default=ROOT / "configs" / "main.yaml")
    ap.add_argument("--dev-dir", type=Path, default=ROOT / "outputs" / "dev_tables")
    ap.add_argument("--k1-dir", type=Path, default=None)
    ap.add_argument("--selection", type=Path, default=ROOT / "outputs" / "selection_v3")
    ap.add_argument(
        "--sealed-dir",
        type=Path,
        default=None,
        help="the sealed run's tables; without it nothing sealed is emitted or classified",
    )
    ap.add_argument("--sealed-k1-dir", type=Path, default=None, help="default: <sealed>/k1")
    ap.add_argument("--sealed-predictor-dir", type=Path, default=None)
    ap.add_argument(
        "--dev-visibility-dir", type=Path, default=ROOT / "outputs" / "dev_visibility"
    )
    ap.add_argument("--sealed-visibility-dir", type=Path, default=None)
    ap.add_argument(
        "--dev-exact-dir",
        type=Path,
        default=None,
        help="optional exact-policy CSVs; use a separate --out-dir to preserve old tables",
    )
    ap.add_argument("--sealed-exact-dir", type=Path, default=None)
    ap.add_argument("--out-dir", type=Path, default=ROOT / "outputs" / "paper_tables")
    ap.add_argument("--paper", type=Path, default=ROOT / "paper")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    dev_exact_rows = read_optional_exact(args.dev_exact_dir)
    sealed_exact_rows = read_optional_exact(args.sealed_exact_dir)

    cfg = cfgmod.load(args.config, expand_environment=False)
    k1_dir = args.k1_dir or args.dev_dir / "k1"
    development = read_run(cfg, args.dev_dir, k1_dir)
    selection_rows = read_rows(args.selection / "selected_parameters.csv")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    written = emit_development(cfg, args, development, selection_rows)
    produced = development_run_values(args, development, dev_exact_rows)
    sealed_values = None
    if args.sealed_dir is not None:
        sealed_k1 = args.sealed_k1_dir or args.sealed_dir / "k1"
        sealed_run = read_run(cfg, args.sealed_dir, sealed_k1)
        written += emit_sealed(cfg, args, sealed_run)
        sealed_values = sealed_run_values(args, sealed_run, sealed_exact_rows)

    numbers = paper_numbers(args.paper, produced, sealed_values)
    write_numbers(numbers, args.out_dir)
    written.append("numbers.csv")
    report(numbers, written, args.out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
