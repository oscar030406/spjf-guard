"""The class-term bootstrap summary and the table the paper prints from it."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_paper_numbers as cpn  # noqa: E402
import run_cluster_bootstrap as rcb  # noqa: E402
from spjf_guard.experiment import paper_tables as pt  # noqa: E402


def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _dev_tables(tmp_path: Path) -> Path:
    tables = tmp_path / "dev_tables"
    _write(
        tables / "main_table.csv",
        [
            {
                "level": 2,
                "policy": "Guard(600)",
                "gap_closed": 0.8,
                "gap_closed_lo": 0.76,
                "gap_closed_hi": 0.84,
            }
        ],
    )
    _write(
        tables / "paired_differences.csv",
        [
            {
                "level": 2,
                "left": "Guard(600)",
                "right": "SPJF-E",
                "difference_gap": -0.115,
                "gap_lo": -0.142,
                "gap_hi": -0.077,
            }
        ],
    )
    return tables


def _summary(point: float, contrast: float) -> list[dict]:
    return [
        {
            "level": 2,
            "quantity": "Guard(600)",
            "point": point,
            "resamples": 3,
            "lo": 0.61,
            "hi": 0.9,
            "sd": 0.07,
        },
        {
            "level": 2,
            "quantity": "Guard(600) - SPJF-E",
            "point": contrast,
            "resamples": 3,
            "lo": -0.2,
            "hi": -0.05,
            "sd": 0.04,
        },
    ]


def test_the_week_interval_joins_only_a_point_the_development_run_printed(tmp_path):
    tables = _dev_tables(tmp_path)
    rows = rcb._beside_weeks(_summary(0.8, -0.115), tables)
    assert [(r["week_lo"], r["week_hi"]) for r in rows] == [(0.76, 0.84), (-0.142, -0.077)]
    with pytest.raises(AssertionError, match="resample -1"):
        rcb._beside_weeks(_summary(0.81, -0.115), tables)


def test_the_cluster_table_prints_both_widths_and_is_checked_against_its_csv(tmp_path):
    rows = rcb._beside_weeks(_summary(0.8, -0.115), _dev_tables(tmp_path))
    source = [{k: str(v) for k, v in row.items()} for row in rows]
    text = pt.cluster_table(source)
    assert "0.080 [0.760, 0.840]" in text and "0.290 [0.610, 0.900]" in text
    package = tmp_path / "package"
    package.mkdir()
    (package / "tab_cluster.tex").write_text(text, encoding="utf-8")
    exact = tmp_path / "unused"
    assert (
        cpn.check_exact_tables(tmp_path, package, exact, source_rows={"tab:s_cluster": source})
        == []
    )
    (package / "tab_cluster.tex").write_text(text.replace("0.290", "0.291"), encoding="utf-8")
    assert (
        cpn.check_exact_tables(tmp_path, package, exact, source_rows={"tab:s_cluster": source})
        != []
    )
