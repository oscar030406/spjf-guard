"""The sealed-against-development contrast, on synthetic rows.

What has to hold: the guard's change between the pools splits into SPJF-E's change and the
change in the guard's cost; the matched cells have the same number of servers even when a
cell with another server count is closer in utilisation; the all-jobs and mean ratios are
(FCFS - policy) / (FCFS - SJF); and the number check accepts a sealed contrast figure in
prose but not one that only the development pool produced.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_paper_numbers as cpn  # noqa: E402
import sealed_dev_contrast as sdc  # noqa: E402


def _main_table(fcfs: float, sjf: float) -> list[dict]:
    return [
        {"level": "2", "policy": "FCFS", "p99_all_s": fcfs, "mean_s": fcfs / 10},
        {"level": "2", "policy": "SJF", "p99_all_s": sjf, "mean_s": sjf / 10},
    ]


def _comparison(spjf_gap: float, guard_gap: float, guard_all: float) -> list[dict]:
    return [
        {
            "level": "2",
            "policy": "SPJF-E|online",
            "gap_closed": spjf_gap,
            "p99_all_s": 20.0,
            "mean_s": 2.0,
        },
        {
            "level": "2",
            "policy": "Guard(600)|online",
            "gap_closed": guard_gap,
            "p99_all_s": guard_all,
            "mean_s": guard_all / 10,
        },
    ]


def _value(rows, quantity, pool, policy="Guard(600)|online"):
    (hit,) = [
        r for r in rows if (r["quantity"], r["pool"], r["policy"]) == (quantity, pool, policy)
    ]
    return float(hit["value"])


def test_the_guard_change_splits_into_ranking_and_cost():
    rows = sdc.gap_rows("dev", _main_table(100, 0), _comparison(0.86, 0.70, 30))
    rows += sdc.gap_rows("sealed", _main_table(100, 0), _comparison(0.94, 0.89, 30))
    parts = sdc.decomposition_rows(rows)
    difference = _value(parts, "difference", "sealed-dev")
    ranking = _value(parts, "ranking_part", "sealed-dev", "SPJF-E|online")
    cost = _value(parts, "cost_part", "sealed-dev")
    assert abs(difference - 0.19) < 1e-12
    assert abs(ranking - 0.08) < 1e-12
    assert abs(cost - 0.11) < 1e-12


def test_the_ratio_on_other_metrics_is_fcfs_minus_policy_over_fcfs_minus_sjf():
    rows = sdc.gap_rows("dev", _main_table(100, 20), _comparison(0.86, 0.70, 30))
    assert abs(_value(rows, "gap_all", "dev") - 70 / 80) < 1e-12
    assert abs(_value(rows, "gap_mean", "dev") - 7 / 8) < 1e-12


def test_matched_cells_share_the_server_count_before_utilisation():
    cell = {"fcfs_p99_dl": 250.0, "span": 200.0}
    dev = {
        "0": {**cell, "servers": 4, "rho": 0.95, "guard_gap": 0.7},
        "1": {**cell, "servers": 5, "rho": 0.90, "guard_gap": 0.6},
    }
    sealed = {"0": {**cell, "servers": 4, "rho": 0.91, "guard_gap": 0.9}}
    rows = sdc.matched_rows(dev, sealed)
    assert {r["policy"] for r in rows if r["pool"] == "dev"} == {"overlay 0"}


def test_the_number_check_accepts_sealed_contrast_figures_only(tmp_path):
    paper = tmp_path / "paper"
    paper.mkdir()
    (paper / "08_experiments.tex").write_text(
        "closes \\sealednum{0.189} more and \\sealednum{0.681}\n", encoding="utf-8"
    )
    contrast = [
        {"quantity": "difference", "pool": "sealed-dev", "printed": "0.189"},
        {"quantity": "matched_guard_gap", "pool": "dev", "printed": "0.681"},
    ]
    complaints = cpn.check_sealed_prose(paper, [], [], [], contrast=contrast)
    assert len(complaints) == 1 and "0.681" in complaints[0]
