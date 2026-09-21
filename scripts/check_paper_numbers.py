"""Does the paper print what this package produced?

    uv run python scripts/check_paper_numbers.py [--paper paper] \
        [--dev-dir outputs/dev_tables] [--package-dir outputs/paper_tables] [--only A]

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

   Nothing here is keyed by a line number: a table is found by its label and a figure by
   the file that has to contain it, so moving a float or lifting an appendix into the
   supplement does not make this script stale.

B. **Running text, captions and plot coordinates.**  Figures the paper quotes from this
   package are recomputed here from `outputs/dev_tables/*.csv` and looked for in the file
   that should carry them, or in either of two when the sentence may sit in the manuscript
   or in the supplement.  This is the check that catches a number rounded by hand, or a
   number that was right before a rerun and was not updated after it.

C. **The sourced rows of `numbers.csv`.**  Every row in the "has a source" state must
   still be printed in the section it was found in; one that is not is either a leftover
   or a coincidence match, and the coincidences are listed with their reasons.

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
multiset: a row that was moved is still printed, a row that was dropped is not."""

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
"""Which file a `numbers.csv` row is looked for in.  A file missing from the paper -- the
supplement before it existed, an appendix after it is folded in -- is skipped rather than
reported, because check C asks whether a number is still printed, not where it lives."""


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


def read_rows(path: Path) -> list[dict]:
    if not path.is_file():
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


def _paper_bodies(paper: Path, cache: dict, label: str) -> tuple[str, list[str]]:
    """The tabulars the paper carries a package table's rows in, and where they are."""
    bodies, where = [], []
    for relative, paper_label in PAPER_TABLES[label]:
        text = cache.setdefault(relative, (paper / relative).read_text(encoding="utf-8"))
        bodies.append(table_body(text, paper_label))
        where.append(f"{paper_label} in {relative}")
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


def check_subsets(paper: Path, cache: dict) -> list[str]:
    """Every cell of a shortened copy of a table is a cell of the full one."""
    complaints = []
    for (short_file, short_label), (long_file, long_label), why in SUBSETS:
        short_text = cache.setdefault(
            short_file, (paper / short_file).read_text(encoding="utf-8")
        )
        long_text = cache.setdefault(long_file, (paper / long_file).read_text(encoding="utf-8"))
        short_body, long_body = (
            table_body(short_text, short_label),
            table_body(long_text, long_label),
        )
        labels = _load_labels(short_body) | _load_labels(long_body)
        short = Counter(normalise(v) for v in DEVNUM.findall(short_body))
        long = Counter(normalise(v) for v in DEVNUM.findall(long_body))
        data = Counter({v: c for v, c in short.items() if v not in labels})
        extra = +(data - long)
        stray = _load_labels(short_body) - _load_labels(long_body)
        print(
            f"   {short_label:11s} {sum(short.values()):4d} values, all of them in"
            f" {long_label}  ->  {'ok' if not extra and not stray else 'MISMATCH'}"
            f"   ({why})"
        )
        if extra:
            complaints.append(f"{short_label}: {long_label} does not print {dict(extra)}")
        if stray:
            complaints.append(f"{short_label}: {long_label} has no block headed {stray}")
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
            thousands(sum(int(r["n_jobs"]) for r in t.residuals)),
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


def check_recomputed(paper: Path, want: list[tuple], cache: dict) -> list[str]:
    """B: every recomputed figure is present in a file that may carry it.

    A figure may be quoted in either of two files when the sentence around it can sit in
    the manuscript or in the supplement; the expectation then names both, and finding it in
    one is enough.  Naming both is what keeps the check from going stale the next time a
    section is moved.
    """
    complaints = []
    for where, what, value in want:
        files = (where,) if isinstance(where, str) else where
        texts = [
            cache.setdefault(name, (paper / name).read_text(encoding="utf-8")) for name in files
        ]
        if not any(_printed(text, value) for text in texts):
            complaints.append(f"{' or '.join(files)}: {what} = {value} is not printed there")
    print(
        f"\nB. running text, captions and plot coordinates recomputed from the CSVs\n"
        f"   {len(want) - len(complaints)} of {len(want)} found where they belong"
    )
    return complaints


def check_sourced(paper: Path, package_dir: Path, cache: dict) -> list[str]:
    """C: the rows of `numbers.csv` that name a package source are still printed."""
    rows = [r for r in read_rows(package_dir / "numbers.csv") if r["produced_by"]]
    gone, dropped = [], []
    for row in rows:
        relative = SECTION_FILE.get(row["section"])
        if relative is None or not (paper / relative).is_file():
            continue
        text = cache.setdefault(relative, (paper / relative).read_text(encoding="utf-8"))
        if "\\devnum{" + row["value"] + "}" in text:
            continue
        (dropped if row["key"] in COINCIDENCE else gone).append(row)
    print(
        f"\nC. the {len(rows)} numbers.csv rows with a package source\n"
        f"   {len(rows) - len(gone) - len(dropped)} still printed unchanged, "
        f"{len(dropped)} dropped as coincidence matches"
    )
    for row in dropped:
        print(f"   dropped  {row['key']}: {row['value']} -- {COINCIDENCE[row['key']]}")
    return [
        f"{r['key']}: \\devnum{{{r['value']}}} (package source {r['produced_by']})"
        for r in gone
    ]


def run(paper: Path, dev: Path, package_dir: Path, only: str | None = None) -> list[str]:
    """Every check that `only` allows; returns the complaints, empty when the paper agrees."""
    cache: dict = {}
    complaints: list[str] = []
    residuals = resid_table_rows(read_rows(dev / "identity_residuals.csv"))
    if only in (None, "A"):
        complaints += check_tables(paper, package_dir, residuals, cache)
    if only in (None, "B"):
        complaints += check_recomputed(paper, expectations(dev), cache)
    if only in (None, "C"):
        complaints += check_sourced(paper, package_dir, cache)
    return complaints


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--paper", type=Path, default=ROOT / "paper")
    ap.add_argument("--dev-dir", type=Path, default=ROOT / "outputs" / "dev_tables")
    ap.add_argument("--package-dir", type=Path, default=ROOT / "outputs" / "paper_tables")
    ap.add_argument("--only", choices=("A", "B", "C"))
    args = ap.parse_args()

    complaints = run(args.paper, args.dev_dir, args.package_dir, args.only)
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
