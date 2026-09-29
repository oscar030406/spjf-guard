"""Generated exact outputs cannot omit certificates, deltas, or protocol cells."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]


def _script():
    spec = importlib.util.spec_from_file_location(
        "check_consistent_visibility", ROOT / "scripts/check_consistent_visibility.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _passes():
    return [
        {
            "overlay": "0",
            "level": "0",
            "policy": "SPJF-E",
            "variant": "exact",
            "pass": str(index),
            "affected_jobs": str(affected),
            "offending_records": str(records),
            "cumulative_jobs": "2",
            "cumulative_records": str(total),
            "terminal_zero": str(affected == 0 and records == 0).lower(),
            "simulation_s": "0.1",
            "detection_s": "0.2",
            "rescore_s": "0.3",
        }
        for index, affected, records, total in (
            (1, 2, 5, 5),
            (2, 1, 2, 7),
            (3, 0, 0, 7),
        )
    ]


def _write_delta(path: Path, **replacements: np.ndarray) -> dict[str, str]:
    arrays = {
        "job_index": np.asarray([4, 9], dtype=np.int64),
        "score_delta": np.asarray([-0.3, -0.1]),
        "corrected_score": np.asarray([1.2, 2.4]),
        "withheld_count": np.asarray([3, 1], dtype=np.int64),
    }
    arrays.update(replacements)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **arrays)
    script = _script()
    return {
        "path": path.name,
        "bytes": str(path.stat().st_size),
        "sha256": script.provenance.sha256_file(path),
        "overlay": "0",
        "level": "0",
        "policy": "SPJF-E",
        "variant": "exact",
        "baseline_variant": "original",
        "affected_jobs": "2",
    }


def _sensitivity_rows():
    variants = ("exact", "exact_other_class_withheld")
    return [
        {
            "overlay": "0",
            "level": "0",
            "policy": f"Guard(600)|{variant}",
            "base_policy": "Guard(600)",
            "variant": variant,
        }
        for variant in variants
    ]


def test_monotone_certificate_requires_a_terminal_zero_pass():
    script = _script()
    assert script.certificate_complaints(_passes()) == []
    assert script.certificate_complaints(_passes()[:-1])


def test_certificate_rejects_record_readmission_and_missing_pass():
    script = _script()
    rows = _passes()
    rows[-1]["cumulative_records"] = "6"
    assert script.certificate_complaints(rows)
    assert script.certificate_complaints([rows[0], rows[-1]])


def test_certificate_rejects_empty_duplicate_and_incoherent_terminal_rows():
    script = _script()
    assert script.certificate_complaints([])
    rows = _passes()
    rows.append(dict(rows[-1]))
    assert script.certificate_complaints(rows)
    rows = _passes()
    rows[-1]["terminal_zero"] = "false"
    assert script.certificate_complaints(rows)


def test_full_refinement_coverage_is_75_exact_plus_15_sensitivity_groups():
    script = _script()
    policies = ["SPJF-E", "Guard(300)", "Guard(600)", "Guard(1200)", "Aging(600)"]
    groups = script.expected_refinement_groups(policies, list(range(5)), [0, 1, 2])
    assert len(groups) == 90
    assert sum(group[3] == "exact" for group in groups) == 75
    assert sum(group[3] == "exact_other_class_withheld" for group in groups) == 15
    assert script.certificate_complaints(_passes(), groups)


def test_coverage_requires_all_four_score_variants_for_every_policy_cell():
    script = _script()
    rows = [
        {
            "overlay": "0",
            "level": "0",
            "policy": f"SPJF-E|{variant}",
            "base_policy": "SPJF-E",
            "variant": variant,
        }
        for variant in ("original", "exact", "conservative", "static")
    ]
    assert script.coverage_complaints(rows, ["SPJF-E"], [0], [0]) == []
    assert script.coverage_complaints(rows[:-1], ["SPJF-E"], [0], [0])


def test_historical_anchor_check_includes_aggregate_confidence_limits():
    script = _script()
    old = {
        "level": "2",
        "policy": "Guard(600)-original",
        "variant": "original",
        "gap_closed": "0.801",
        "gap_closed_lo": "0.764",
    }
    current = {**old, "base_policy": "Guard(600)", "policy": "Guard(600)|original"}
    assert script.existing_anchor_complaints([current], [old]) == []
    current["gap_closed_lo"] = "0.765"
    assert script.existing_anchor_complaints([current], [old])


def test_aggregate_coverage_rejects_a_missing_aging_anchor():
    script = _script()
    rows = [
        {
            "level": "0",
            "policy": f"Aging(600)|{variant}",
            "base_policy": "Aging(600)",
            "variant": variant,
        }
        for variant in script.EXACT_VARIANTS
    ]
    assert script.comparison_coverage_complaints(rows, ["Aging(600)"], [0]) == []
    assert script.comparison_coverage_complaints(rows[:-1], ["Aging(600)"], [0])
    old = {"level": "0", "policy": "Aging(600)", "variant": "conservative"}
    assert script.existing_anchor_complaints([], [old])
    reference = {"level": "0", "policy": "FCFS", "variant": "reference"}
    assert script.existing_anchor_complaints([], [reference]) == []


def test_sensitivity_coverage_requires_both_variants_and_composite_policy():
    script = _script()
    rows = _sensitivity_rows()
    assert script.sensitivity_coverage_complaints(rows, [0], [0]) == []
    assert script.sensitivity_coverage_complaints(rows[:-1], [0], [0])
    rows[0]["policy"] = "Guard(600)"
    assert script.sensitivity_coverage_complaints(rows, [0], [0])


def test_sparse_delta_matches_certificate_and_has_all_equal_length_arrays(tmp_path):
    script = _script()
    row = _write_delta(tmp_path / "delta.npz")
    key = ("0", "0", "SPJF-E", "exact")
    assert script._delta_complaints(tmp_path, [row], {key}, {key: 2}) == []


@pytest.mark.parametrize("field", ["corrected_score", "withheld_count"])
def test_sparse_delta_rejects_truncated_corrected_or_withheld_arrays(tmp_path, field):
    script = _script()
    dtype = np.int64 if field == "withheld_count" else float
    row = _write_delta(tmp_path / "delta.npz", **{field: np.asarray([1], dtype=dtype)})
    key = ("0", "0", "SPJF-E", "exact")
    complaints = script._delta_complaints(tmp_path, [row], {key}, {key: 2})
    assert any("array lengths" in complaint for complaint in complaints)


def test_delta_manifest_rejects_missing_and_duplicate_group_coverage(tmp_path):
    script = _script()
    row = _write_delta(tmp_path / "delta.npz")
    key = ("0", "0", "SPJF-E", "exact")
    assert script._delta_complaints(tmp_path, [], {key}, {key: 2})
    assert script._delta_complaints(tmp_path, [row, dict(row)], {key}, {key: 2})


def test_required_certificate_table_rejects_missing_and_header_only_files(tmp_path):
    script = _script()
    path = tmp_path / "exact_passes.csv"
    assert script._required_rows(path)[1]
    path.write_text("overlay,level,policy\n", encoding="utf-8")
    assert script._required_rows(path)[1]
