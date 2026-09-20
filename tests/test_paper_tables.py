"""The emitted tables and the map of the paper's numbers.

Two things have to hold.  Every number in an emitted table body is wrapped in
`\\devnum{}`, so a development figure can never be mistaken for a sealed one in the
typeset paper.  And every `\\devnum{}` the paper carries appears in `numbers.csv` with
either a producing artefact or a stated reason why this package does not produce it —
the list is what stops a number from quietly having no source at all.
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from spjf_guard.experiment import paper_tables as pt  # noqa: E402

DIGITS = re.compile(r"\d")
DEVNUM = re.compile(r"\\devnum\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}")


def _table_rows():
    return [
        {
            "level": 0,
            "k": 8,
            "rho_target": 0.5,
            "policy": name,
            "p99_dl_s": value,
            "mean_s": 0.5,
            "gap_closed": 0.7,
            "gap_closed_lo": 0.6,
            "gap_closed_hi": 0.8,
            "reduction_pct": 40.0,
            "max_excess_s": 100.0,
            "harm_s": 50.0,
            "fired_pct": 1.5,
        }
        for name, value in (
            ("FCFS", 27.64),
            ("SJF", 10.59),
            ("SPJF-E", 14.73),
            ("SPJF-log", 14.8),
            ("Guard(600)", 14.98),
            ("SPJF-reversed", 42.72),
            ("Guard(600)-reversed", 43.39),
        )
    ]


def _body(text: str) -> list[str]:
    """The rows between the header rule and the bottom rule."""
    lines = text.splitlines()
    start = lines.index(r"\midrule") + 1
    return lines[start : lines.index(r"\bottomrule")]


def _undecorated_digits(text: str) -> list[str]:
    """Every body row with a digit outside a `\\devnum{}`.

    Two exceptions, both of which the paper also leaves bare: the column count of a
    `\\multicolumn` and the skip count `$N=...$`, which is a policy's name, not a result.
    """
    bad = []
    for line in _body(text):
        stripped = DEVNUM.sub("", line)
        stripped = re.sub(r"\\multicolumn\{\d+\}\{[a-z]\}", "", stripped)
        stripped = re.sub(r"\$N=\d+\$", "", stripped)
        stripped = stripped.replace("p99", "")
        if DIGITS.search(stripped):
            bad.append(line)
    return bad


def test_every_number_of_the_rank_table_is_wrapped():
    assert _undecorated_digits(pt.rank_table(_table_rows())) == []


def test_every_number_of_the_guard_table_is_wrapped():
    parameters = {
        (0, "Guard(600)"): {"promise_s": 600.0, "skip_count": 0.0},
    }
    text = pt.guard_table(_table_rows(), parameters, ["Guard(600)"])
    assert _undecorated_digits(text) == []
    assert r"\label{tab:guard}" in text


def test_the_adversarial_table_pairs_each_ranking_with_its_guarded_twin():
    text = pt.adversarial_table(_table_rows())
    assert "reversed" in text
    body = [line for line in text.splitlines() if line.strip().endswith(r"\\")]
    assert any("42.72" in line and "43.39" in line for line in body)


def test_the_residual_table_prints_the_share_as_a_percentage():
    rows = [
        {
            "level": 0,
            "k": 8,
            "rho_target": 0.5,
            "policy": "SPJF-E",
            "max_abs_residual_L": 6.786,
            "ratio_to_bound": 0.485,
            "share_residual_zero": 0.956,
            "samephase_share_sum_in": 0.0036,
            "r2_net_over_k": 0.985,
            "max_abs_error_s": 50.9,
        }
    ]
    text = pt.residual_table(rows, ["SPJF-E"])
    assert r"\devnum{95.6\%}" in text
    assert r"\devnum{0.36\%}" in text, "the same-phase share is printed to two decimals"
    assert _undecorated_digits(text) == []


@pytest.mark.skipif(
    not (ROOT / "outputs" / "paper_tables" / "numbers.csv").is_file(),
    reason="the numbers map has not been emitted on this machine",
)
def test_every_paper_number_has_a_source_or_a_stated_reason():
    path = ROOT / "outputs" / "paper_tables" / "numbers.csv"
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    assert rows
    orphans = [r for r in rows if not r["produced_by"] and not r["not_produced"]]
    assert not orphans, orphans[:5]


def test_a_paired_difference_is_indexed_in_both_spellings_the_paper_uses():
    """The paper quotes a difference and its interval as one `\\devnum{}`, sometimes in
    math mode and sometimes bare; both have to find the row that produced them."""
    import emit_paper_tables as emit

    out: dict = {}
    emit.difference_values(
        [
            {
                "left": "Guard(600)",
                "right": "SPJF-E",
                "difference_gap": -0.116,
                "gap_lo": -0.143,
                "gap_hi": -0.077,
                "difference_s": 26.45,
                "lo": 20.1,
                "hi": 32.9,
            }
        ],
        out,
    )
    where = "dev_tables/paired_differences.csv[Guard(600) - SPJF-E]"
    assert out["-0.116 [-0.143, -0.077]"] == where
    assert out["$-0.116$ $[-0.143, -0.077]$"] == where
    assert out["-0.116"] == where


def test_a_number_the_package_should_produce_is_never_called_external():
    """The classification has to separate three states, not two.

    A number in the experiment section that this package prints differently is a change
    to report, not a number from somewhere else; a number in a section this package never
    touches carries that section's reason; a number in neither gets no reason at all, and
    the generated-artefact check fails on it.
    """
    import emit_paper_tables as emit

    assert emit.classify("p99 was 14.98 s", "08_experiments", "tab:rank") == emit.DIFFERS
    assert emit.classify("the excess reached 1.2 s", "fig_excess", "") == emit.DIFFERS
    spearman = emit.classify("Spearman 0.41", "08_experiments", "tab:rank")
    assert spearman == "predictor-comparison"
    assert emit.classify("six terms", "07_data", "") == "data-description"
    assert emit.classify("whatever", "11_future_work", "") == ""


def test_the_paper_is_never_written_to():
    """The emitter's own source must not open anything under paper/ for writing."""
    source = (ROOT / "scripts" / "emit_paper_tables.py").read_text(encoding="utf-8")
    assert "write_text" not in source.split("def paper_numbers")[0].split("args.paper")[-1]
    assert "args.paper" in source
