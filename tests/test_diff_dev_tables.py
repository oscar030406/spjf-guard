"""The diff report must catch a move at the printed digit and ignore one below it.

The point of the report is what a reader of the paper would see, so a difference of
0.004 s on a figure printed to two decimals is not a difference, and 0.006 s is.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import diff_dev_tables as dd  # noqa: E402


def _ours(p99: float) -> dict:
    return {
        (2, "SPJF-E"): {
            "level": "2",
            "policy": "SPJF-E",
            "rho_target": "1.0",
            "p99_dl_s": str(p99),
            "gap_closed": "0.5000",
        }
    }


def _theirs(p99: float) -> dict:
    return {
        (2, "SPJF-tweedie"): {
            "level": "2",
            "policy": "SPJF-tweedie",
            "p99_dl_s": str(p99),
            "gap_closed": "0.5000",
        }
    }


def test_a_difference_below_the_printed_digit_is_not_reported():
    differing, compared, missing = dd.compare(_ours(62.914), _theirs(62.9125))
    assert differing == []
    assert compared == 2 and missing == []


def test_a_difference_at_the_printed_digit_is_reported():
    differing, _, _ = dd.compare(_ours(62.916), _theirs(62.9125))
    assert len(differing) == 1
    row = differing[0]
    assert row["metric"] == "p99_dl_s"
    assert (row["package_printed"], row["v31_printed"]) == ("62.92", "62.91")


def test_a_policy_v31_never_reported_is_listed_rather_than_dropped_silently():
    ours = {(0, "Guard(900)"): {"level": "0", "policy": "Guard(900)", "p99_dl_s": "1.0"}}
    differing, compared, missing = dd.compare(ours, _theirs(1.0))
    assert differing == [] and compared == 0
    assert missing == ["L0 Guard(900)"]


def test_the_firing_rate_is_compared_after_the_percent_conversion():
    ours = {(0, "SJF"): {"level": "0", "policy": "SJF", "fired_pct": "12.5"}}
    theirs = {(0, "SJF-ref"): {"level": "0", "policy": "SJF-ref", "qw_fired": "0.125"}}
    differing, compared, _ = dd.compare(ours, theirs)
    assert compared == 1 and differing == []


def test_the_labels_cover_every_policy_the_configuration_reports(tmp_path):
    from spjf_guard import config as cfgmod

    cfg = cfgmod.load(ROOT / "configs" / "main.yaml", expand_environment=False)
    names = [p.name for p in cfg.policies(4, include_log_control=True)]
    unmapped = sorted(n for n in names if n not in dd.POLICY_LABEL)
    # The ablation rows are new in this pass and have no v3.1 counterpart; every policy
    # v3.1 also reported must still map, or the diff would silently skip it.
    assert all(n.startswith("Guard-") or n == "Aging(600)" for n in unmapped), unmapped


def test_the_report_is_written_even_when_nothing_differs(tmp_path):
    table = tmp_path / "main_table.csv"
    with open(table, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["level", "policy", "rho_target", "p99_dl_s"])
        writer.writeheader()
        writer.writerow({"level": 2, "policy": "SPJF-E", "rho_target": 1.0, "p99_dl_s": 62.914})
    v31 = tmp_path / "v31.csv"
    with open(v31, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["level", "policy", "p99_dl_s"])
        writer.writeheader()
        writer.writerow({"level": 2, "policy": "SPJF-tweedie", "p99_dl_s": 62.9125})
    sys.argv = [
        "diff_dev_tables.py",
        "--table",
        str(table),
        "--v31",
        str(v31),
    ]
    assert dd.main() == 0
    out = tmp_path / "diff_vs_v31.csv"
    assert out.is_file()
    assert list(csv.DictReader(open(out, encoding="utf-8"))) == []
