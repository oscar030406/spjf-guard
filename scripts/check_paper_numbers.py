"""Does the paper print what this package produced?

    uv run python scripts/check_paper_numbers.py [--paper paper] \
        [--dev-dir outputs/dev_tables] [--package-dir outputs/paper_tables] \
        [--sealed-dir outputs/sealed_tables] [--sealed-k1-dir <dir>] \
        [--sealed-predictor-dir <dir>] [--sealed-visibility-dir <dir>] \
        [--dev-exact-dir <dir>] [--sealed-exact-dir <dir>] [--only A]

`check_generated.py --only paper_numbers` asks a different question: whether every number
in the paper has *some* stated source.  This script asks whether the numbers that claim
this package as their source are the ones the package actually prints.  Three checks, any
of which can fail on its own:

A. **Table bodies.**  For each package table, the multiset of `\\devnum{}` payloads in its
   body against the same extraction from the paper tables that carry its rows -- which is
   one table in the manuscript, one in the supplementary file, or both, since the referee's
   length cuts moved three of the five.  Typography is normalised away (thousands braces,
   math mode); everything else has to match.  The deliberate differences are listed below
   with their reasons, and a difference that is not on that list is a leftover.  The skip
   counts, which name a policy rather than report a result and so carry no `\\devnum{}`,
   are compared as well, and a table the paper prints twice at two lengths is checked
   against its own longer copy.

B. **Running text, captions and plot coordinates.**  Figures the paper quotes from this
   package are recomputed here from `outputs/dev_tables/*.csv` and looked for in the paper.
   This is the check that catches a number rounded by hand, or a number that was right
   before a rerun and was not updated after it.

C. **The sourced rows of `numbers.csv`.**  Every row in the "has a source" state must
   still be printed; one that is not is either a leftover or a coincidence match, and the
   coincidences are listed with their reasons.

D. **The sealed tables**, only when `--sealed-dir` is given.  The package's
   `tab_*_sealed.tex` against the paper's tables of the same label, on the `\\sealednum{}`
   figures, and every sealed figure the paper quotes in prose against the sealed terms'
   predictor table.  A sealed table the paper does not carry yet is reported and skipped: the
   sealed run comes first and the paper is written after it.  Without the option nothing
   in A, B or C changes, which is the point of it being an option.

None of the four is keyed to a place in the paper.  A table is found by its label in any
of the sources and under either spelling of it, a figure by the sources that print it; the
file an expectation names is where the check looks first and what it reports a move
against, not a requirement.  The manuscript is being shortened by moving tables,
paragraphs and proofs into the supplementary file, and a move changes nothing here: the
same values are compared either way, and a figure printed nowhere at all still fails.

Nothing here writes into `paper/`, and the paper is only ever read.
"""

from __future__ import annotations

import argparse
import csv
import math
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DEVNUM = re.compile(r"\\devnum\{((?:[^{}]|\{[^{}]*\})*)\}")
THOUSANDS = re.compile(r"(?<=\d),(?=\d\d\d(\D|$))")

TABLES = ("tab:rank", "tab:guard", "tab:adv", "tab:k1", "tab:resid")
"""The tables whose bodies are the package's own.  `tab:setup` is prose rows whose set
differs from the paper's by design, and is covered by check C instead."""

PACKAGE_FILE = {
    "tab:rank": "tab_rank.tex",
    "tab:guard": "tab_guard.tex",
    "tab:adv": "tab_adv.tex",
    "tab:k1": "tab_k1.tex",
    "tab:resid": "tab_resid.tex",
}

EXACT_PACKAGE_FILE = {
    "tab:exact_visibility": "tab_exact_visibility.tex",
    "tab:same_copy_exposure": "tab_same_copy_exposure.tex",
}
"""Optional exact-policy tables.  They are checked only after their CSV directory exists."""

EXPERIMENTS = "sections/08_experiments.tex"
LIMITATIONS = "sections/09_limitations.tex"
THEORY = "sections/06_theory.tex"
SUPPLEMENT = "supplementary.tex"

PAPER_TABLES = {
    "tab:rank": ((EXPERIMENTS, "tab:rank"),),
    "tab:guard": ((EXPERIMENTS, "tab:guard"), (SUPPLEMENT, "tab:s_guard_abl")),
    "tab:adv": ((EXPERIMENTS, "tab:adv"),),
    "tab:k1": ((SUPPLEMENT, "tab:s_k1"),),
    "tab:resid": ((SUPPLEMENT, "tab:s_resid"),),
}
"""Which of the paper's tables carry each package table's rows.

The referee asked for a shorter manuscript, so three of the five moved: the single-server
table and the residual table went to the supplementary file whole, and the guard table was
split, its two ablation shapes going to Table S3 while the winner, its fixed-budget
ablation, the equal-promise budget and the skip count stayed in the main text.  A package
table is therefore compared against the union of the paper tables listed here, as one
multiset: a row that was moved is still printed, a row that was dropped is not.

The file is where the table sat when this list was written, and is printed so that a
reader can find it; the label is what the table is looked for by, in every source and
under either spelling, so a table that moves again is found where it lands."""

SUBSETS = (
    (
        (EXPERIMENTS, "tab:resid"),
        (SUPPLEMENT, "tab:s_resid"),
        "the main text keeps four of the nine cells the supplement prints in full",
    ),
)
"""(smaller table, larger table, why).  A table the paper prints twice at different
lengths is checked against its own longer copy, which is the one checked against the
package.  Any cell that disagrees between the two is a hand edit to one of them."""

SHORT_COPIES = frozenset(short for (_, short), _, _ in SUBSETS)
"""The labels of the paper's own shortened copies.  Check A compares the package against
the union of the paper's tables, and a shortened copy would add its cells to that union a
second time, so it is left out of it and checked by `check_subsets` instead."""

PAPER_PLAIN = (
    (
        "tab:k1",
        "100.00",
        "---",
        "FCFS has no guard, so no dispatch epoch can fire one; the package's 100.00 is the"
        " convention that every FCFS dispatch serves the queue head (referee item RR-24)",
    ),
    ("tab:k1", "0.00", "---", "SJF has no guard, so its firing rate is not defined"),
    ("tab:k1", "0.00", "---", "SPJF-E has no guard, so its firing rate is not defined"),
)
"""(table, what the package prints, the literal the paper prints instead, why).

Unlike a respelling, the paper's side is not a number at all, so it cannot be matched in
the multiset.  The check instead counts that literal in both bodies and requires the
paper's count to exceed the package's by exactly the number of entries here: replacing one
of these cells with a different number, or silently dropping a row, still fails."""

RESPELT = (
    (
        "tab:rank",
        "0.000 [0.000, 0.000]",
        "0.000",
        "FCFS closes 0 of the gap by"
        " construction; the paper prints the degenerate interval bare",
    ),
    ("tab:rank", "1.000 [1.000, 1.000]", "1.000", "SJF closes 1 by construction"),
    ("tab:rank", "0.0 [0.0, 0.0]", "0.0", "FCFS reduces nothing by construction"),
    ("tab:k1", "0.000 [0.000, 0.000]", "0.000", "FCFS closes 0 by construction"),
    ("tab:k1", "1.000 [1.000, 1.000]", "1.000", "SJF closes 1 by construction"),
    ("tab:resid", "0", "0.5", "load label: the package prints the level index"),
    ("tab:resid", "0", "0.8", "load label: the package prints the level index"),
    ("tab:resid", "0", "1.0", "load label: the package prints the level index"),
    ("tab:rank", "1", "1.0", "load label: rho = 1 is printed 1.0"),
    ("tab:guard", "1", "1.0", "load label: rho = 1 is printed 1.0"),
    ("tab:adv", "1", "1.0", "load label: rho = 1 is printed 1.0"),
)
"""(table, what the package prints, what the paper prints, why they differ).

An entry that never fires is reported at the end of check A.  It means the paper stopped
respelling that cell, and the entry is then excusing nothing -- it has to be removed, or it
will one day excuse a real difference that happens to take the same two values."""

PACKAGE_ONLY = (
    (
        "tab:resid",
        "samephase",
        "the package's residual table carries the same-phase"
        " share of sum In; the paper quotes that figure in running text instead, where"
        " check B verifies it",
    ),
)
"""(table, tag, reason) -- values the package prints and the paper deliberately does not.
A tag is matched by `_package_only_values`, which knows which cells it covers."""

PAPER_ONLY = {
    "tab:rank": [
        # The two development-study rows: another predictor, not this package's.
        "14.72",
        "0.753 [0.722, 0.776]",
        "46.7 [44.0, 50.0]",
        "0.295",
        "14.87",
        "0.741 [0.707, 0.767]",
        "45.9 [43.2, 48.8]",
        "0.290",
        "44.41",
        "0.873 [0.851, 0.886]",
        "62.7 [57.4, 66.2]",
        "1.251",
        "42.82",
        "0.891 [0.870, 0.904]",
        "64.0 [58.5, 67.7]",
        "1.230",
        "67.36",
        "0.896 [0.871, 0.913]",
        "75.3 [70.1, 78.5]",
        "2.352",
        "62.71",
        "0.917 [0.895, 0.929]",
        "77.0 [71.7, 80.3]",
        "2.302",
    ],
}
"""Values the paper prints that this package does not produce, kept on purpose with a
table note saying where they come from."""

COINCIDENCE: dict[str, str] = {}
"""Rows of `numbers.csv` whose value matched a package artefact by accident: they are
reported apart from real leftovers, because dropping them is the right outcome.

Empty at the moment.  The two the editor found (an old `tab:resid` ratio cell and the old
same-phase cell) are gone: the package now produces the same-phase share itself, and the
table was regenerated.  A key here is `<file>:<table or section>:<n>`, which survives a
re-layout of the paper; it does not survive the number moving to another section, and an
entry that stops matching should be re-derived rather than kept."""

SECTION_FILE = {
    "01_introduction": "sections/01_introduction.tex",
    "03_problem_model": "sections/03_problem_model.tex",
    "04_prediction": "sections/04_prediction.tex",
    "05_scheduling": "sections/05_scheduling.tex",
    "06_theory": "sections/06_theory.tex",
    "07_data": "sections/07_data.tex",
    "08_experiments": "sections/08_experiments.tex",
    "09_limitations": "sections/09_limitations.tex",
    "A_proofs": "sections/A_proofs.tex",
    "supplementary": "supplementary.tex",
    "fig_threejob": "figures/fig_threejob.tex",
    "fig_excess": "figures/fig_excess.tex",
    "fig_gapvsg": "figures/fig_gapvsg.tex",
    "fig_guard": "figures/fig_guard.tex",
}
"""Which file a `numbers.csv` row was found in when it was emitted.  It is where check C
looks first and what it reports a move against; the check itself asks whether the number
is still printed, not where it lives, so a file missing from the paper -- the supplement
before it existed, an appendix after it is folded in -- costs nothing."""

PAPER_GLOBS = ("*.tex", "sections/*.tex", "figures/*.tex")
"""Where the paper's own text sits, relative to `--paper`.  The class files under
`Definitions/` are the journal's, not the paper's, and are never read: they are long lists
of names and code points, and a figure found in one of those would mean nothing."""

SOURCES = "\x00sources"
"""The key the list of source names is cached under.  No file can be named this."""

SUPPLEMENT_PREFIX = "tab:s_"
"""What a table's label gains when it moves into the supplementary file."""


def paper_files(paper: Path) -> list[str]:
    """Every source of the paper, as paper-relative names."""
    return sorted(
        {
            str(path.relative_to(paper)).replace("\\", "/")
            for pattern in PAPER_GLOBS
            for path in paper.glob(pattern)
            if path.is_file()
        }
    )


def _text(paper: Path, cache: dict, relative: str) -> str:
    return cache.setdefault(relative, (paper / relative).read_text(encoding="utf-8"))


def paper_texts(paper: Path, cache: dict) -> dict[str, str]:
    """Every source, read once and kept for the checks that follow."""
    names = cache.get(SOURCES)
    if names is None:
        names = cache[SOURCES] = paper_files(paper)
    return {name: _text(paper, cache, name) for name in names}


def spellings(label: str) -> tuple[str, ...]:
    """A table's label and the other spelling of it, main text against supplement.

    A table moved into the supplementary file is renamed there -- `tab:rank` becomes
    `tab:s_rank` -- so both are looked for, and whichever the paper carries is the one
    checked.  A table split between the two is carried under both, and both are taken.
    """
    if label.startswith(SUPPLEMENT_PREFIX):
        return label, "tab:" + label[len(SUPPLEMENT_PREFIX) :]
    if label.startswith("tab:"):
        return label, SUPPLEMENT_PREFIX + label[len("tab:") :]
    return (label,)


def find_label(paper: Path, cache: dict, label: str) -> list[tuple[str, str]]:
    """Every (file, spelling) the paper carries this table under, its own spelling first."""
    texts = paper_texts(paper, cache)
    return [
        (name, spelling)
        for spelling in spellings(label)
        for name, text in texts.items()
        if "\\label{" + spelling + "}" in text
    ]


def normalise(value: str) -> str:
    """Compare on the printed digits: thousands separators and math mode are typography."""
    text = value.replace("{,}", "").replace("\\%", "%").replace("$", "").replace("\\", "")
    text = THOUSANDS.sub("", text)
    return " ".join(text.split())


def table_body(tex: str, label: str) -> str:
    """The tabular that carries `label`, from `\\begin{tabular}` to `\\end{tabular}`."""
    at = tex.find("\\label{" + label + "}")
    if at < 0:
        raise SystemExit(f"no table labelled {label}")
    start = tex.find("\\begin{tabular}", at)
    end = tex.find("\\end{tabular}", start)
    if start < 0 or end < 0:
        raise SystemExit(f"no tabular for {label}")
    return tex[start:end]


def body_values(tex: str, label: str) -> Counter:
    """The `\\devnum{}` payloads inside the tabular that carries `label`."""
    return Counter(normalise(v) for v in DEVNUM.findall(table_body(tex, label)))


def skip_counts(body: str) -> Counter:
    """The skip counts spelled into the policy names of a table body.

    They sit outside `\\devnum{}` because they name a policy rather than report a result,
    which would leave them unchecked; they come from `policy_parameters.csv` like every
    other number in the row.  The symbol was `N` and is now `\\kappa` (referee item RR-13),
    so both are read."""
    return Counter(re.findall(r"\$(?:\\kappa|N)\s*=\s*(\d+)\$", body))


def read_rows(path: Path, optional: bool = False) -> list[dict]:
    """The CSV, or nothing when it is optional and absent.

    Optional is for the sealed run's single-server tables: the sealed pool's k = 1 run is
    a command of its own, so the directory may legitimately not be there.
    """
    if not path.is_file():
        if optional:
            return []
        raise SystemExit(f"{path} is missing; run scripts/run_main.py first")
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _package_only_values(label: str, rows: list[dict]) -> Counter:
    """The values a package table prints that the paper does not, by tag."""
    out: Counter = Counter()
    for table, tag, _ in PACKAGE_ONLY:
        if table != label or tag != "samephase":
            continue
        for row in rows:
            share = float(row["samephase_share_sum_in"])
            out[normalise(f"{100.0 * share:.2f}%")] += 1
    return out


def resid_table_rows(residuals: list[dict]) -> list[dict]:
    """The nine rows `tab:resid` prints: three policies on the first overlay."""
    printed = ("SPJF-E", "Guard(600)", "SPJF-reversed")
    return [r for r in residuals if r["policy"] in printed and int(float(r["overlay"])) == 0]


def _wanted(label: str) -> list[str]:
    """The labels the paper may carry a package table's rows under."""
    return [s for _, paper_label in PAPER_TABLES[label] for s in spellings(paper_label)]


def _paper_bodies(paper: Path, cache: dict, label: str) -> tuple[str, list[str]]:
    """The tabulars the paper carries a package table's rows in, and where they are.

    The label is looked for in every source and in either spelling, so a table that moved
    into the supplementary file is found there, and one whose rows were spread over a main
    and a supplement table is the union of the two.  Nothing is added twice, and the
    paper's own shortened copy of a table is left to `check_subsets`.
    """
    bodies, where, seen = [], [], set()
    for _, paper_label in PAPER_TABLES[label]:
        for name, spelling in find_label(paper, cache, paper_label):
            short = spelling in SHORT_COPIES and spelling != paper_label
            if short or (name, spelling) in seen:
                continue
            seen.add((name, spelling))
            bodies.append(table_body(_text(paper, cache, name), spelling))
            where.append(f"{spelling} in {name}")
    return "\n".join(bodies), where


def _plain_cells(label: str, package_body: str, paper_body: str) -> tuple[Counter, str]:
    """The cells the paper prints as a literal instead of a number, and what is wrong.

    Each literal has to be as common in the paper's table as in the package's plus one per
    entry: a cell that became a number again, or a row that went missing, moves the count.
    """
    drop: Counter = Counter()
    wanted: Counter = Counter()
    for table, ours, literal, _ in PAPER_PLAIN:
        if table != label:
            continue
        drop[normalise(ours)] += 1
        wanted[literal] += 1
    for literal, extra in wanted.items():
        expected = package_body.count(literal) + extra
        found = paper_body.count(literal)
        if found != expected:
            return drop, (
                f"{label}: the paper prints {literal!r} {found} times where"
                f" {expected} are accounted for"
            )
    return drop, ""


def _respell(label: str, package: Counter, paper: Counter, used: set) -> None:
    """Take the cells the paper deliberately spells differently out of both sides."""
    for entry in RESPELT:
        table, ours, theirs, _ = entry
        if table == label and package[ours] and paper[theirs]:
            shared = min(package[ours], paper[theirs])
            package[ours] -= shared
            paper[theirs] -= shared
            used.add(entry)


def _one_table(
    label: str, package_body: str, paper_body: str, residuals: list[dict], used: set
) -> tuple[list[str], bool]:
    """One package table against the paper's copies of it."""
    complaints = []
    package = Counter(normalise(v) for v in DEVNUM.findall(package_body))
    paper = Counter(normalise(v) for v in DEVNUM.findall(paper_body))
    _respell(label, package, paper, used)
    dropped, complaint = _plain_cells(label, package_body, paper_body)
    if complaint:
        complaints.append(complaint)
    for value, count in (dropped + _package_only_values(label, residuals)).items():
        package[value] -= min(count, package[value])
    for value in PAPER_ONLY.get(label, []):
        if paper[normalise(value)]:
            paper[normalise(value)] -= 1
    package_only, paper_only = +(package - paper), +(paper - package)
    ours, theirs = skip_counts(package_body), skip_counts(paper_body)
    if package_only:
        complaints.append(f"{label}: the paper does not print {dict(package_only)}")
    if paper_only:
        complaints.append(f"{label}: the package does not print {dict(paper_only)}")
    if ours != theirs:
        complaints.append(
            f"{label}: the skip counts differ, package {sorted(ours.elements())}"
            f" against paper {sorted(theirs.elements())}"
        )
    return complaints, not complaints


def check_tables(
    paper: Path, package_dir: Path, residuals: list[dict], cache: dict
) -> list[str]:
    """A: the package's table bodies against the paper's, value for value."""
    complaints: list[str] = []
    used: set[tuple] = set()
    print("A. table bodies, package against paper")
    for label in TABLES:
        package_body = table_body((package_dir / PACKAGE_FILE[label]).read_text("utf-8"), label)
        paper_body, where = _paper_bodies(paper, cache, label)
        if not where:
            wanted = " or ".join(_wanted(label))
            complaints.append(f"{label}: the paper carries no table labelled {wanted}")
            print(f"   {label:11s} labelled {wanted}  ->  NOT IN THE PAPER")
            continue
        found, ok = _one_table(label, package_body, paper_body, residuals, used)
        complaints += found
        print(
            f"   {label:11s} package {len(DEVNUM.findall(package_body)):4d} values,"
            f" paper {len(DEVNUM.findall(paper_body)):4d}"
            f" in {', '.join(where)}  ->  {'ok' if ok else 'MISMATCH'}"
        )
    complaints += check_subsets(paper, cache)
    for entry in RESPELT:
        if entry not in used:
            print(f"   unused exemption: {entry[0]} {entry[1]!r} -> {entry[2]!r}")
    return complaints


LOAD_LABEL = re.compile(r"(?:\\rho|k)\s*=\s*\\devnum\{([^{}]*)\}")


def _load_labels(body: str) -> set[str]:
    """The load a block of rows is headed with.  The full table heads each block once; a
    table that keeps some of the rows repeats the head on each kept row, so these are
    compared as a set while every other cell is compared as a multiset."""
    return {normalise(v) for v in LOAD_LABEL.findall(body)}


def _one_body(paper: Path, cache: dict, label: str) -> tuple[str, str] | None:
    """The tabular the paper carries this label under, and where, or None.

    Its own spelling wins when the paper carries both, so a table that was moved and
    renamed is compared in its new spelling and one that stayed in its old one.
    """
    found = find_label(paper, cache, label)
    if not found:
        return None
    name, spelling = found[0]
    return table_body(_text(paper, cache, name), spelling), f"{spelling} in {name}"


def _subset(short: tuple[str, str], long: tuple[str, str], why: str) -> list[str]:
    """One shortened copy of a table against the full one, cell for cell."""
    complaints = []
    (short_body, short_where), (long_body, long_where) = short, long
    labels = _load_labels(short_body) | _load_labels(long_body)
    counts = Counter(normalise(v) for v in DEVNUM.findall(short_body))
    full = Counter(normalise(v) for v in DEVNUM.findall(long_body))
    data = Counter({v: c for v, c in counts.items() if v not in labels})
    extra = +(data - full)
    stray = _load_labels(short_body) - _load_labels(long_body)
    print(
        f"   {short_where:24s} {sum(counts.values()):4d} values, all of them in"
        f" {long_where}  ->  {'ok' if not extra and not stray else 'MISMATCH'}"
        f"   ({why})"
    )
    if extra:
        complaints.append(f"{short_where}: {long_where} does not print {dict(extra)}")
    if stray:
        complaints.append(f"{short_where}: {long_where} has no block headed {stray}")
    return complaints


def check_subsets(paper: Path, cache: dict) -> list[str]:
    """Every cell of a shortened copy of a table is a cell of the full one.

    Both copies are found by their labels, so the pair may sit anywhere; when the shorter
    copy has been folded into the longer one the two resolve to the same table, which is
    the right answer and says so in the line it prints.
    """
    complaints = []
    for (_, short_label), (_, long_label), why in SUBSETS:
        short = _one_body(paper, cache, short_label)
        long = _one_body(paper, cache, long_label)
        if short is None or long is None:
            absent = [
                lab for lab, body in ((short_label, short), (long_label, long)) if body is None
            ]
            complaints.append(
                f"{short_label}: the paper carries no table labelled {', '.join(absent)}"
            )
            continue
        complaints += _subset(short, long, why)
    return complaints


class Tables:
    """The development tables, indexed the way the expectations below ask for them."""

    def __init__(self, dev: Path):
        self.main = {
            (int(r["level"]), r["policy"]): r for r in read_rows(dev / "main_table.csv")
        }
        self.k1 = {r["policy"]: r for r in read_rows(dev / "k1" / "main_table.csv")}
        self.paired = {
            (int(r["level"]), r["left"], r["right"]): r
            for r in read_rows(dev / "paired_differences.csv")
        }
        self.bound = read_rows(dev / "bound_checks.csv")
        self.bound_k1 = read_rows(dev / "k1" / "bound_checks.csv")
        self.residuals = read_rows(dev / "identity_residuals.csv")
        self.printed_residuals = resid_table_rows(self.residuals)
        """The nine cells `tab:resid` prints.  The identity ratio the paper quotes is over
        all 81, and says so; the same-phase share it quotes is over these nine, where the
        sentence sits.  Over all 81 the maximum is far higher, because a randomised
        ranking ties many jobs into one dispatch instant -- that is a fact about the
        corrupted order, not about the workload the sentence is describing."""

    def cell(self, level: int, policy: str, column: str, digits: int) -> str:
        return f"{float(self.main[(level, policy)][column]):.{digits}f}"

    def single(self, policy: str, column: str = "gap_closed", digits: int = 3) -> str:
        return f"{float(self.k1[policy][column]):.{digits}f}"

    def largest_same_phase_share(self) -> float:
        return max(float(r["samephase_share_sum_in"]) for r in self.printed_residuals)

    def difference(self, level: int, left: str, right: str) -> str:
        """The size of a paired difference in gap units; the paper states the direction
        in words, so the sign is not part of the printed figure."""
        return f"{abs(float(self.paired[(level, left, right)]['difference_gap'])):.3f}"


def thousands(value: int) -> str:
    """The paper's own spelling of a long integer."""
    return f"{value:,}".replace(",", "{,}")


def policy_expectations(t: Tables, promises=(300, 600, 1200), levels=(0, 1, 2)) -> list:
    """What the guard costs, what the shapes differ by, and the harms that are quoted."""
    want = []
    for promise in promises:  # the cost of the promise, stated at the heaviest load
        given_up = float(t.main[(2, "SPJF-E")]["gap_closed"]) - float(
            t.main[(2, f"Guard({promise})")]["gap_closed"]
        )
        want.append(
            (EXPERIMENTS, f"cost of the promise G={promise} at rho=1.0", f"{given_up:.3f}")
        )
    for promise in promises:
        for level in levels:
            want.append(
                (
                    EXPERIMENTS,
                    f"Guard({promise}) - Guard-fixed({promise}) at level {level}",
                    t.difference(level, f"Guard({promise})", f"Guard-fixed({promise})"),
                )
            )
    for level in levels:
        for policy in ("Guard-queue(600)", "Guard(600)"):
            want.append(
                (
                    EXPERIMENTS,
                    f"{policy} harm at level {level}",
                    t.cell(level, policy, "harm_s", 1),
                )
            )
        for policy in ("FCFS", "SPJF-E", "Guard(600)"):
            worst_heavy = float(t.main[(level, policy)]["max_heavy_s"])
            want.append(
                (
                    EXPERIMENTS,
                    f"{policy} worst heavy-job wait at level {level}",
                    f"{worst_heavy:,.0f}",
                )
            )
        for promise in promises:
            want.append(
                (
                    EXPERIMENTS,
                    f"Fixed({promise}) harm at level {level}",
                    t.cell(level, f"Fixed({promise})", "harm_s", 1),
                )
            )
        want.append(
            (
                EXPERIMENTS,
                f"SPJF-E - SPJF-log at level {level}",
                t.difference(level, "SPJF-E", "SPJF-log"),
            )
        )
    return want


def assertion_expectations(t: Tables, promises=(300, 600, 1200)) -> list:
    """The two things the runs assert job by job, and the single-server trace."""
    legacy_residuals = [row for row in t.residuals if row["policy"] != "Aging(600)"]
    want = [
        (EXPERIMENTS, "guarded runs", str(len(t.bound))),
        (
            EXPERIMENTS,
            "per-job checks",
            thousands(sum(int(r["jobs_checked"]) for r in t.bound)),
        ),
        (EXPERIMENTS, "single-server runs", str(len(t.bound_k1))),
        (
            EXPERIMENTS,
            "single-server checks",
            thousands(sum(int(r["jobs_checked"]) for r in t.bound_k1)),
        ),
        (
            EXPERIMENTS,
            "worst used/allowed at k=1",
            f"{max(float(r['used_over_allowed']) for r in t.bound_k1):.4f}",
        ),
        (
            EXPERIMENTS,
            "identity job-checks",
            thousands(sum(int(r["n_jobs"]) for r in legacy_residuals)),
        ),
        (
            EXPERIMENTS,
            "worst identity ratio over all cells",
            f"{max(float(r['ratio_to_bound']) for r in t.residuals):.3f}",
        ),
        (
            EXPERIMENTS,
            "largest same-phase share of sum In, over the printed cells",
            f"{100 * t.largest_same_phase_share():.2f}%",
        ),
    ]
    for servers in sorted({int(float(r["k"])) for r in t.bound}):
        worst = max(
            float(r["used_over_allowed"]) for r in t.bound if int(float(r["k"])) == servers
        )
        want.append((EXPERIMENTS, f"worst used/allowed at k={servers}", f"{worst:.4f}"))
    for promise in promises:
        for policy in (f"Guard({promise})", f"Guard-fixed({promise})"):
            want.append((EXPERIMENTS, f"single-server {policy} gap", t.single(policy)))
    for policy in ("Guard(1200)", "Guard-age(1200)"):
        want.append((LIMITATIONS, f"single-server {policy} gap", t.single(policy)))
    return want


def residual_expectations(t: Tables) -> list:
    """The range of the identity residual, as the theory and the experiments quote it.

    Both sentences are the same two numbers out of `identity_residuals.csv`: the smallest
    and the largest `ratio_to_bound` over all 81 cells.  Section 6 gives the range and
    section 8 the upper end, and the upper end is rounded *outwards* in both, so that
    "never exceeds" stays true of the printed figure; the lower end is rounded to nearest,
    which is also outwards of nothing the text claims.  Rounding the maximum the ordinary
    way would print 0.517 and make the sentence false by 0.0003.
    """
    low = min(float(r["ratio_to_bound"]) for r in t.residuals)
    high = max(float(r["ratio_to_bound"]) for r in t.residuals)
    outward = math.ceil(high * 1000) / 1000
    return [
        ((THEORY, SUPPLEMENT), "smallest identity ratio over all cells", f"{low:.3f}"),
        ((THEORY, SUPPLEMENT), "largest identity ratio, rounded outwards", f"{outward:.3f}"),
        (EXPERIMENTS, "largest identity ratio, four decimals", f"{high:.4f}"),
        (EXPERIMENTS, "largest identity ratio, rounded outwards", f"{outward:.3f}"),
    ]


def figure_expectations(t: Tables, promises=(300, 600, 1200), levels=(0, 1, 2)) -> list:
    """The plot coordinates, which the figures carry as plain text rather than devnum."""
    want = []
    for level in levels:
        for policy in ("Guard(600)", "SPJF-E"):
            want.append(
                (
                    "figures/fig_excess.tex",
                    f"{policy} max excess at level {level}",
                    t.cell(level, policy, "max_excess_s", 1),
                )
            )
        for promise in promises:
            for policy in (
                f"Guard({promise})",
                f"Guard-fixed({promise})",
                f"Fixed({promise})",
            ):
                want.append(
                    (
                        "figures/fig_gapvsg.tex",
                        f"{policy} gap at level {level}",
                        t.cell(level, policy, "gap_closed", 3),
                    )
                )
    return want


def expectations(dev: Path) -> list[tuple[str, str, str]]:
    """(file, what it is, the string that file has to contain), recomputed from the CSVs.

    Every entry is a number the paper quotes from this package outside a table body.
    """
    tables = Tables(dev)
    return (
        policy_expectations(tables)
        + assertion_expectations(tables)
        + residual_expectations(tables)
        + figure_expectations(tables)
    )


def _printed(text: str, value: str) -> bool:
    """Is this figure in the file, in any of the spellings LaTeX gives it?

    Thousands are braced (`17{,}634{,}760`) and a percent sign is escaped (`0.36\\%`);
    neither is part of the value.
    """
    flat = text.replace("{,}", ",").replace("\\%", "%")
    return value.replace("{,}", ",").replace("\\%", "%") in flat


def _where_printed(texts: dict[str, str], files, value: str) -> str | None:
    """The source that prints this figure: the file it is expected in, then the
    supplement, then every other source.  A file the paper no longer has is passed over."""
    order: list[str] = []
    for name in [*files, SUPPLEMENT, *sorted(texts)]:
        if name in texts and name not in order:
            order.append(name)
    return next((name for name in order if _printed(texts[name], value)), None)


def check_recomputed(paper: Path, want: list[tuple], cache: dict) -> list[str]:
    """B: every recomputed figure is printed somewhere in the paper.

    The expectation names the file the sentence was written in, and that is where the
    search starts; a sentence that has since moved into the supplement, or into another
    section, is found there and the move is reported.  A figure printed in none of the
    sources is the failure this check exists for: a number rounded by hand, or one that
    was right before a rerun.
    """
    texts = paper_texts(paper, cache)
    complaints: list[str] = []
    moved: Counter = Counter()
    for where, what, value in want:
        files = (where,) if isinstance(where, str) else where
        found = _where_printed(texts, files, value)
        if found is None:
            complaints.append(
                f"{' or '.join(files)}: {what} = {value} is not printed in the paper"
            )
        elif found not in files:
            moved[f"{files[0]} -> {found}"] += 1
    print(
        f"\nB. running text, captions and plot coordinates recomputed from the CSVs\n"
        f"   {len(want) - len(complaints)} of {len(want)} printed,"
        f" {sum(moved.values())} of them outside the file they were written in"
    )
    for move, count in sorted(moved.items()):
        print(f"   moved: {count:4d} figure(s) {move}")
    return complaints


def check_sourced(paper: Path, package_dir: Path, cache: dict) -> list[str]:
    """C: the rows of `numbers.csv` that name a package source are still printed.

    Somewhere in the paper.  The row records the file the number was found in when the map
    was emitted, and that is where the search starts; a number whose paragraph has since
    moved into the supplement is counted as moved, not as gone.
    """
    rows = [r for r in read_rows(package_dir / "numbers.csv") if r["produced_by"]]
    texts = paper_texts(paper, cache)
    gone: list[dict] = []
    dropped: list[dict] = []
    moved = 0
    for row in rows:
        home = SECTION_FILE.get(row["section"], "")
        found = _where_printed(texts, (home,), "\\devnum{" + row["value"] + "}")
        if found is None:
            (dropped if row["key"] in COINCIDENCE else gone).append(row)
        elif found != home:
            moved += 1
    print(
        f"\nC. the {len(rows)} numbers.csv rows with a package source\n"
        f"   {len(rows) - len(gone) - len(dropped)} still printed unchanged "
        f"({moved} of them in another file than the one they were found in), "
        f"{len(dropped)} dropped as coincidence matches"
    )
    for row in dropped:
        print(f"   dropped  {row['key']}: {row['value']} -- {COINCIDENCE[row['key']]}")
    return [
        f"{r['key']}: \\devnum{{{r['value']}}} (package source {r['produced_by']})"
        for r in gone
    ]


SEALEDNUM = re.compile(r"\\sealednum\{((?:[^{}]|\{[^{}]*\})*)\}")
"""What the paper wraps a sealed-term figure in.  `\\devnum{}` says the opposite, so the
two are never read from the same expression."""

SEALED_SUFFIX = "_sealed"
PREDICTOR_SECTION = "sections/04_prediction.tex"
"""Where the sentences that quote a sealed predictor figure sit today.  Check D2 reads
every source rather than this one, so moving them into the supplement neither breaks the
check nor turns it silent."""

TABLE_ENV = re.compile(r"\\begin\{table\*?\}.*?\\end\{table\*?\}", re.S)
MACRO_DEFINITION = re.compile(r"^.*\\newcommand\{\\(?:dev|sealed)num\}.*$", re.M)


def _running_text(paper: Path, cache: dict) -> dict[str, str]:
    """The paper's prose: every source without its table floats.

    A sealed figure inside a table is check D1's business, and the line that defines the
    macro is not a printed figure at all.
    """
    return {
        name: MACRO_DEFINITION.sub(" ", TABLE_ENV.sub(" ", text))
        for name, text in paper_texts(paper, cache).items()
    }


def check_sealed_tables(paper: Path, package_dir: Path, labels, cache=None) -> list[str]:
    """D1: the package's sealed tables against the paper's, figure for figure.

    The paper's copy is found by its label wherever it sits and in either spelling, so a
    sealed table that lands in the supplementary file is checked there.
    """
    complaints = []
    cache = {} if cache is None else cache
    print("\nD. sealed tables, package against paper")
    for label in labels:
        name = PACKAGE_FILE[label].replace(".tex", f"{SEALED_SUFFIX}.tex")
        path = package_dir / name
        if not path.is_file():
            complaints.append(f"{name} is missing; run emit_paper_tables.py --sealed-dir")
            continue
        sealed_label = label + SEALED_SUFFIX
        ours = Counter(
            normalise(v)
            for v in SEALEDNUM.findall(table_body(path.read_text("utf-8"), sealed_label))
        )
        found = _one_body(paper, cache, sealed_label)
        if found is None:
            print(f"   {label + SEALED_SUFFIX:18s} not in the paper yet, skipped")
            continue
        theirs = Counter(normalise(v) for v in SEALEDNUM.findall(found[0]))
        extra, missing = +(ours - theirs), +(theirs - ours)
        print(
            f"   {label + SEALED_SUFFIX:18s} package {sum(ours.values()):4d} values,"
            f" paper {sum(theirs.values()):4d} in {found[1]}"
            f"  ->  {'ok' if not extra and not missing else 'MISMATCH'}"
        )
        if extra:
            complaints.append(f"{label}{SEALED_SUFFIX}: the paper does not print {dict(extra)}")
        if missing:
            complaints.append(
                f"{label}{SEALED_SUFFIX}: the package does not print {dict(missing)}"
            )
    return complaints


def load_exact_source(exact_dir: Path) -> tuple[dict[str, list[dict]], list[str]]:
    """Load both required exact CSVs, reporting protocol errors as complaints."""
    rows: dict[str, list[dict]] = {}
    complaints: list[str] = []
    sources = {
        "tab:exact_visibility": exact_dir / "exact_comparison.csv",
        "tab:same_copy_exposure": exact_dir / "same_copy_exposure.csv",
    }
    for label, path in sources.items():
        if not path.is_file():
            complaints.append(f"explicit exact source is missing required file: {path}")
            rows[label] = []
            continue
        rows[label] = read_rows(path, optional=True)
        if not rows[label]:
            complaints.append(f"explicit exact source has no data rows: {path}")
    return rows, complaints


def check_exact_tables(
    paper: Path,
    package_dir: Path,
    exact_dir: Path,
    *,
    sealed: bool = False,
    cache=None,
    source_rows: dict[str, list[dict]] | None = None,
) -> list[str]:
    """Exact tables against their CSV recipe and, when pasted, the paper.

    Calling this function means the exact source was explicitly selected, so both source
    CSVs are mandatory. A paper copy is compared value-for-value when present.
    """
    from emit_paper_tables import as_sealed
    from spjf_guard.experiment import paper_tables as pt

    rows, source_complaints = (
        load_exact_source(exact_dir) if source_rows is None else (source_rows, [])
    )
    builders = {
        "tab:exact_visibility": pt.exact_visibility_table,
        "tab:same_copy_exposure": pt.same_copy_exposure_table,
    }
    complaints = list(source_complaints)
    cache = {} if cache is None else cache
    macro = SEALEDNUM if sealed else DEVNUM
    suffix = SEALED_SUFFIX if sealed else ""
    for label, source_rows in rows.items():
        if not source_rows:
            continue
        expected = builders[label](source_rows)
        if sealed:
            expected = as_sealed(expected)
        filename = EXACT_PACKAGE_FILE[label].replace(".tex", f"{suffix}.tex")
        path = package_dir / filename
        if not path.is_file():
            complaints.append(
                f"{filename} is missing; run emit_paper_tables.py with the exact dir"
            )
            continue
        actual = path.read_text(encoding="utf-8")
        if actual != expected:
            complaints.append(f"{filename} does not match the exact CSV recipe")
            continue
        paper_label = label + suffix
        found = _one_body(paper, cache, paper_label)
        if found is None:
            print(f"   {paper_label:28s} not in the paper yet, skipped")
            continue
        ours = Counter(
            normalise(value) for value in macro.findall(table_body(actual, paper_label))
        )
        theirs = Counter(normalise(value) for value in macro.findall(found[0]))
        extra, missing = +(ours - theirs), +(theirs - ours)
        if extra:
            complaints.append(f"{paper_label}: the paper does not print {dict(extra)}")
        if missing:
            complaints.append(f"{paper_label}: the package does not print {dict(missing)}")
    return complaints


def check_sealed_prose(
    paper: Path,
    predictor: list[dict],
    visibility_comparison: list[dict],
    visibility_exposure: list[dict],
    cache=None,
    exact_comparison: list[dict] | None = None,
    exact_exposure: list[dict] | None = None,
) -> list[str]:
    """D2: every sealed figure in prose comes from a pinned sealed output.

    The predictor's figures have no table of their own: the paper states them in running
    text, and that text is read wherever it sits.
    """
    from emit_paper_tables import (
        exact_exposure_values,
        exact_values,
        predictor_values,
        visibility_exposure_values,
        visibility_values,
    )

    if not (
        predictor
        or visibility_comparison
        or visibility_exposure
        or exact_comparison
        or exact_exposure
    ):
        return []
    values: dict[str, str] = {}
    predictor_values(predictor, values)
    visibility_values(visibility_comparison, values, "sealed_visibility")
    visibility_exposure_values(visibility_exposure, values, "sealed_visibility")
    exact_values(exact_comparison or [], values, "sealed_consistent_visibility")
    exact_exposure_values(exact_exposure or [], values, "sealed_consistent_visibility")
    known = {normalise(v) for v in values}
    printed, stray = 0, []
    for name, text in _running_text(paper, {} if cache is None else cache).items():
        for value in SEALEDNUM.findall(text):
            printed += 1
            if normalise(value) not in known:
                stray.append((name, normalise(value)))
    print(
        f"   sealed prose       {printed - len(stray)} of {printed} sealed figures"
        f" come from predictor, visibility, or exact outputs"
    )
    return [
        f"{name}: sealed figure {value} is not in a sealed predictor, visibility, "
        "or exact output"
        for name, value in stray
    ]


def check_sealed_predictor(paper: Path, rows: list[dict], cache=None) -> list[str]:
    """Backward-compatible predictor-only spelling used by focused tests."""
    return check_sealed_prose(paper, rows, [], [], cache)


def run(
    paper: Path,
    dev: Path,
    package_dir: Path,
    only: str | None = None,
    sealed: Path | None = None,
    sealed_k1: Path | None = None,
    sealed_predictor: Path | None = None,
    sealed_visibility: Path | None = None,
    dev_exact: Path | None = None,
    sealed_exact: Path | None = None,
) -> list[str]:
    """Every check that `only` allows; returns the complaints, empty when the paper agrees."""
    cache: dict = {}
    complaints: list[str] = []
    dev_exact_rows: dict[str, list[dict]] = {}
    sealed_exact_rows: dict[str, list[dict]] = {}
    if dev_exact is not None:
        dev_exact_rows, source_complaints = load_exact_source(dev_exact)
        complaints += source_complaints
    if sealed_exact is not None:
        sealed_exact_rows, source_complaints = load_exact_source(sealed_exact)
        complaints += source_complaints
    residuals = resid_table_rows(read_rows(dev / "identity_residuals.csv"))
    if only in (None, "A"):
        complaints += check_tables(paper, package_dir, residuals, cache)
        if dev_exact is not None:
            complaints += check_exact_tables(
                paper,
                package_dir,
                dev_exact,
                cache=cache,
                source_rows=dev_exact_rows,
            )
    if only in (None, "B"):
        complaints += check_recomputed(paper, expectations(dev), cache)
    if only in (None, "C"):
        complaints += check_sourced(paper, package_dir, cache)
    if only in (None, "D"):
        if sealed is not None:
            k1 = read_rows((sealed_k1 or sealed / "k1") / "main_table.csv", optional=True)
            labels = [t for t in TABLES if t != "tab:k1" or k1]
            complaints += check_sealed_tables(paper, package_dir, labels, cache)
        if sealed_exact is not None:
            complaints += check_exact_tables(
                paper,
                package_dir,
                sealed_exact,
                sealed=True,
                cache=cache,
                source_rows=sealed_exact_rows,
            )
        if any((sealed, sealed_predictor, sealed_visibility, sealed_exact)):
            complaints += check_sealed_prose(
                paper,
                read_rows(sealed_predictor / "predictor_metrics.csv", optional=True)
                if sealed_predictor
                else [],
                read_rows(sealed_visibility / "visibility_comparison.csv", optional=True)
                if sealed_visibility
                else [],
                read_rows(sealed_visibility / "visibility_exposure.csv", optional=True)
                if sealed_visibility
                else [],
                cache=cache,
                exact_comparison=sealed_exact_rows.get("tab:exact_visibility", []),
                exact_exposure=sealed_exact_rows.get("tab:same_copy_exposure", []),
            )
    return complaints


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--paper", type=Path, default=ROOT / "paper")
    ap.add_argument("--dev-dir", type=Path, default=ROOT / "outputs" / "dev_tables")
    ap.add_argument("--package-dir", type=Path, default=ROOT / "outputs" / "paper_tables")
    ap.add_argument("--sealed-dir", type=Path, default=None, help="the sealed run's tables")
    ap.add_argument("--sealed-k1-dir", type=Path, default=None, help="default: <sealed>/k1")
    ap.add_argument("--sealed-predictor-dir", type=Path, default=None)
    ap.add_argument("--sealed-visibility-dir", type=Path, default=None)
    ap.add_argument("--dev-exact-dir", type=Path, default=None)
    ap.add_argument("--sealed-exact-dir", type=Path, default=None)
    ap.add_argument("--only", choices=("A", "B", "C", "D"))
    args = ap.parse_args()

    complaints = run(
        args.paper,
        args.dev_dir,
        args.package_dir,
        args.only,
        args.sealed_dir,
        args.sealed_k1_dir,
        args.sealed_predictor_dir,
        args.sealed_visibility_dir,
        args.dev_exact_dir,
        args.sealed_exact_dir,
    )
    for complaint in complaints:
        print(f"   FAIL {complaint}")
    print(
        "\n"
        + (
            "the paper prints what the package produced"
            if not complaints
            else f"{len(complaints)} disagreement(s)"
        )
    )
    return 1 if complaints else 0


if __name__ == "__main__":
    raise SystemExit(main())
