"""A paired difference under the online replay is one resampled quantity, and the
cross-checks of scripts/online_paired_differences.py catch a value that was not read back."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def _script():
    spec = importlib.util.spec_from_file_location(
        "online_paired_differences_test", ROOT / "scripts/online_paired_differences.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _cells(rng, guard_shift=0.0, variant="online", overlays=5, resamples=200):
    cells = []
    for _ in range(overlays):
        fcfs = 100.0 + rng.normal(0.0, 5.0, resamples)
        sjf = 20.0 + rng.normal(0.0, 1.0, resamples)
        clock = 60.0 + rng.normal(0.0, 8.0, resamples)
        cells.append(
            {
                "FCFS": fcfs,
                "SJF": sjf,
                f"Guard(600)|{variant}": clock - guard_shift,
                f"Timeout(600)|{variant}": clock,
            }
        )
    return cells


def test_a_policy_against_itself_differs_by_zero_in_every_resample():
    oci = _script()
    [row] = oci.paired_rows(_cells(np.random.default_rng(1)), 2, [600.0], "online")
    assert row["gap_difference"] == 0.0
    assert (row["gap_difference_lo"], row["gap_difference_hi"]) == (0.0, 0.0)
    assert row["guard_gap"] == row["timeout_gap"]


def test_the_difference_is_resampled_as_one_quantity():
    """A shift common to every resample gives a difference interval of zero width, although
    the two policies' own intervals are wide."""
    oci = _script()
    [row] = oci.paired_rows(_cells(np.random.default_rng(2), 5.0), 2, [600.0], "online")
    assert np.isclose(row["gap_difference"], row["guard_gap"] - row["timeout_gap"])
    own = row["guard_gap_hi"] - row["guard_gap_lo"]
    paired = row["gap_difference_hi"] - row["gap_difference_lo"]
    assert row["gap_difference_lo"] > 0.0
    assert paired < own / 2


def _written(row, policy_name, prefix):
    return {
        "level": str(row["level"]),
        "policy": f"{policy_name}(600)|online",
        "gap_closed": repr(row[prefix]),
        "gap_closed_lo": repr(row[f"{prefix}_lo"]),
        "gap_closed_hi": repr(row[f"{prefix}_hi"]),
    }


def test_an_online_interval_that_differs_from_the_runner_in_the_last_bit_is_caught():
    oci = _script()
    [row] = oci.paired_rows(_cells(np.random.default_rng(3), 2.0), 2, [600.0], "online")
    comparison = [_written(row, "Guard", "guard_gap"), _written(row, "Timeout", "timeout_gap")]
    assert oci.online_complaints([row], comparison) == []
    comparison[1]["gap_closed_lo"] = repr(float(np.nextafter(row["timeout_gap_lo"], 1.0)))
    [complaint] = oci.online_complaints([row], comparison)
    assert "Timeout(600)|online gap_closed_lo" in complaint


def test_an_original_row_that_differs_from_the_precheck_at_six_decimals_is_caught():
    oci = _script()
    [row] = oci.paired_rows(
        _cells(np.random.default_rng(4), 2.0, "original"), 0, [600.0], "original"
    )
    reference = {"level": "0", "promise_s": "600.0"} | {
        field: repr(round(row[field], 6)) for field in oci.CLOCK_FIELDS
    }
    assert oci.clock_complaints([row], [reference]) == []
    reference["p99_diff_hi"] = repr(round(row["p99_diff_hi"], 6) + 1e-6)
    [complaint] = oci.clock_complaints([row], [reference])
    assert "p99_diff_hi" in complaint


def test_a_package_pair_is_the_left_gap_minus_the_right_one_on_its_own_clock():
    """The guard's cost is Guard(G) minus SPJF-E, negative when the guard closes less."""
    oci = _script()
    cells = _cells(np.random.default_rng(5), -3.0)
    for cell in cells:
        cell["SPJF-E|online"] = cell.pop("Timeout(600)|online")
    [row] = oci.package_rows(cells, 2, [("Guard(600)", "SPJF-E")], "online")
    assert (row["variant"], row["left"], row["right"]) == ("online", "Guard(600)", "SPJF-E")
    expected = oci._gap(cells, "Guard(600)|online") - oci._gap(cells, "SPJF-E|online")
    assert np.isclose(row["difference_gap"], expected[0])
    assert row["difference_gap"] < 0.0


def test_an_original_pair_that_differs_from_dev_tables_in_the_last_bit_is_caught():
    oci = _script()
    cells = _cells(np.random.default_rng(6), 2.0, "original")
    [row] = oci.package_rows(cells, 1, [("Guard(600)", "Timeout(600)")], "original")
    reference = {"level": "1", "left": "Guard(600)", "right": "Timeout(600)"} | {
        field: repr(float(row[field])) for field in oci.PAIR_FIELDS
    }
    assert oci.pair_complaints([row], [reference]) == []
    reference["gap_hi"] = repr(float(np.nextafter(row["gap_hi"], 0.0)))
    [complaint] = oci.pair_complaints([row], [reference])
    assert "gap_hi" in complaint


def test_a_pair_of_one_grid_point_under_two_names_prints_no_row():
    """Guard(600) and Guard-age(600) are the same point, so their difference is no result."""
    oci = _script()
    rows = []
    for variant in ("original", "online"):
        cells = _cells(np.random.default_rng(7), 2.0, variant)
        for cell in cells:
            cell[f"Guard-age(600)|{variant}"] = cell[f"Guard(600)|{variant}"]
        pairs = [("Guard(600)", "Guard-age(600)"), ("Guard(600)", "Timeout(600)")]
        rows += oci.package_rows(cells, 2, pairs, variant)
    comparison = [{"level": "2", "rho_target": "1.0"}]
    [row] = oci.pair_latex_rows(rows, comparison)
    assert "Timeout" in row and "Guard-age" not in row
