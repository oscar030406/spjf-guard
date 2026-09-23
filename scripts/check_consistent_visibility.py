"""Check coverage, monotone refinement certificates and sparse-score integrity."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from collections.abc import Set
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from spjf_guard import config as cfgmod  # noqa: E402
from spjf_guard.experiment import provenance  # noqa: E402

Row = dict[str, str]
Group = tuple[str, str, str, str]
EXACT_VARIANTS = ("original", "exact", "conservative", "static")
SENSITIVITY_VARIANT = "exact_other_class_withheld"
PASS_FIELDS = (
    "overlay",
    "level",
    "policy",
    "variant",
    "pass",
    "affected_jobs",
    "offending_records",
    "cumulative_jobs",
    "cumulative_records",
    "terminal_zero",
    "simulation_s",
    "detection_s",
    "rescore_s",
)
DELTA_FIELDS = (
    "path",
    "bytes",
    "sha256",
    "overlay",
    "level",
    "policy",
    "variant",
    "baseline_variant",
    "affected_jobs",
)


def _rows(path: Path) -> list[Row]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _required_rows(path: Path) -> tuple[list[Row], list[str]]:
    if not path.is_file():
        return [], [f"{path.name}: required table is missing"]
    try:
        rows = _rows(path)
    except (OSError, csv.Error, UnicodeError) as exc:
        return [], [f"{path.name}: cannot read table ({type(exc).__name__})"]
    return (rows, []) if rows else ([], [f"{path.name}: table is empty"])


def _text(row: Row, field: str) -> str:
    value = row.get(field, "")
    return value if isinstance(value, str) else ""


def _group(row: Row) -> Group:
    return (
        _text(row, "overlay"),
        _text(row, "level"),
        _text(row, "policy"),
        _text(row, "variant"),
    )


def expected_refinement_groups(
    policies: list[str], overlays: list[int], levels: list[int]
) -> set[Group]:
    exact = {
        (str(overlay), str(level), policy, "exact")
        for overlay in overlays
        for level in levels
        for policy in policies
    }
    sensitivity = {
        (str(overlay), str(level), "Guard(600)", SENSITIVITY_VARIANT)
        for overlay in overlays
        for level in levels
    }
    return exact | sensitivity


def _coverage_complaints(
    rows: list[Row], fields: tuple[str, ...], expected: Set[tuple[str, ...]], label: str
) -> list[str]:
    keys = [tuple(_text(row, field) for field in fields) for row in rows]
    actual = set(keys)
    duplicates = sorted(key for key, count in Counter(keys).items() if count > 1)
    complaints = []
    if duplicates:
        complaints.append(
            f"{label}: {len(duplicates)} duplicated key(s), first {duplicates[:3]}"
        )
    missing, extra = sorted(expected - actual), sorted(actual - expected)
    if missing or extra:
        complaints.append(
            f"{label}: {len(rows)} rows, {len(expected)} expected; "
            f"missing {missing[:3]}, extra {extra[:3]}"
        )
    return complaints


def _integer_columns(block: list[Row], key: Group) -> tuple[dict[str, np.ndarray], list[str]]:
    fields = (
        "pass",
        "affected_jobs",
        "offending_records",
        "cumulative_jobs",
        "cumulative_records",
    )
    try:
        values = {
            field: np.asarray([int(row[field]) for row in block], dtype=np.int64)
            for field in fields
        }
    except (KeyError, TypeError, ValueError):
        return {}, [f"{key}: pass certificate has a missing or non-integer count"]
    return values, []


def _terminal_flags(block: list[Row], key: Group) -> tuple[np.ndarray, list[str]]:
    spellings = {"true": True, "false": False}
    raw = [_text(row, "terminal_zero").lower() for row in block]
    if any(value not in spellings for value in raw):
        return np.empty(0, dtype=bool), [f"{key}: terminal_zero is not boolean"]
    return np.asarray([spellings[value] for value in raw], dtype=bool), []


def _timing_complaints(block: list[Row], key: Group) -> list[str]:
    fields = ("simulation_s", "detection_s", "rescore_s")
    try:
        values = np.asarray(
            [[float(row[field]) for field in fields] for row in block], dtype=float
        )
    except (KeyError, TypeError, ValueError):
        return [f"{key}: pass certificate has a missing or non-numeric timing"]
    if not np.isfinite(values).all() or np.any(values < 0):
        return [f"{key}: pass certificate timings are not finite non-negative values"]
    return []


def _missing_fields_complaints(
    rows: list[Row], fields: tuple[str, ...], label: str
) -> list[str]:
    missing = sorted(
        field for field in fields if any(row.get(field) in (None, "") for row in rows)
    )
    return [f"{label}: missing values for {missing}"] if missing else []


def _certificate_block_complaints(key: Group, block: list[Row]) -> list[str]:
    values, complaints = _integer_columns(block, key)
    flags, flag_complaints = _terminal_flags(block, key)
    complaints += flag_complaints + _timing_complaints(block, key)
    if complaints:
        return complaints
    order = np.argsort(values["pass"], kind="stable")
    values = {field: entries[order] for field, entries in values.items()}
    flags = flags[order]
    passes = values["pass"]
    affected = values["affected_jobs"]
    offending = values["offending_records"]
    cumulative_jobs = values["cumulative_jobs"]
    cumulative_records = values["cumulative_records"]
    if not np.array_equal(passes, np.arange(1, len(block) + 1)):
        complaints.append(f"{key}: missing or duplicate refinement passes")
    if any(np.any(values[field] < 0) for field in values if field != "pass"):
        complaints.append(f"{key}: pass certificate contains a negative count")
    actual_zero = (affected == 0) & (offending == 0)
    if not np.array_equal(flags, actual_zero):
        complaints.append(f"{key}: terminal_zero disagrees with the pass counts")
    if np.flatnonzero(actual_zero).tolist() != [len(block) - 1]:
        complaints.append(f"{key}: final pass is not the unique zero-violation pass")
    if not np.array_equal(np.diff(np.r_[0, cumulative_records]), offending):
        complaints.append(f"{key}: cumulative withheld records disagree with increments")
    job_increments = np.diff(np.r_[0, cumulative_jobs])
    if np.any(job_increments < 0) or np.any(job_increments > affected):
        complaints.append(f"{key}: cumulative affected jobs are incoherent")
    if np.any(affected > offending) or np.any(cumulative_jobs > cumulative_records):
        complaints.append(f"{key}: affected-job counts exceed their withheld records")
    return complaints


def certificate_complaints(
    rows: list[Row], expected_groups: set[Group] | None = None
) -> list[str]:
    if not rows:
        return ["exact_passes.csv: no refinement certificates"]
    groups: dict[Group, list[Row]] = defaultdict(list)
    for row in rows:
        groups[_group(row)].append(row)
    complaints = _missing_fields_complaints(rows, PASS_FIELDS, "exact_passes.csv")
    if expected_groups is not None:
        missing = sorted(expected_groups - set(groups))
        extra = sorted(set(groups) - expected_groups)
        if missing or extra:
            complaints.append(
                f"exact_passes.csv: {len(groups)} groups, {len(expected_groups)} expected; "
                f"missing {missing[:3]}, extra {extra[:3]}"
            )
    for key, block in groups.items():
        complaints += _certificate_block_complaints(key, block)
    return complaints


def _delta_manifest_lengths(row: Row, label: str) -> tuple[tuple[int, int] | None, list[str]]:
    try:
        expected_length = int(row["affected_jobs"])
        expected_bytes = int(row["bytes"])
    except (KeyError, TypeError, ValueError):
        return None, [f"{label}: manifest lengths are missing or non-integer"]
    if expected_length < 0 or expected_bytes < 0:
        return None, [f"{label}: manifest lengths are negative"]
    return (expected_length, expected_bytes), []


def _read_delta_arrays(
    path: Path, row: Row, expected_bytes: int, label: str
) -> tuple[dict[str, np.ndarray], list[str]]:
    required = {"job_index", "score_delta", "corrected_score", "withheld_count"}
    if not path.is_file():
        return {}, [f"{label}: sparse deltas are missing"]
    if provenance.sha256_file(path) != row.get("sha256"):
        return {}, [f"{label}: sparse delta checksum differs from its manifest"]
    complaints = []
    if path.stat().st_size != expected_bytes:
        complaints.append(f"{label}: byte length differs from the delta manifest")
    try:
        with np.load(path, allow_pickle=False) as data:
            if set(data.files) != required:
                return {}, [
                    f"{label}: sparse delta keys are {sorted(data.files)}, "
                    f"expected {sorted(required)}"
                ]
            arrays = {name: np.asarray(data[name]) for name in required}
    except (OSError, ValueError) as exc:
        return {}, [f"{label}: cannot read sparse deltas ({type(exc).__name__})"]
    return arrays, complaints


def _delta_value_complaints(
    arrays: dict[str, np.ndarray], expected_length: int, label: str
) -> list[str]:
    lengths = {name: len(array) if array.ndim == 1 else -1 for name, array in arrays.items()}
    if set(lengths.values()) != {expected_length}:
        return [f"{label}: sparse array lengths {lengths}, expected {expected_length}"]
    complaints = []
    jobs = arrays["job_index"]
    withheld = arrays["withheld_count"]
    if not np.issubdtype(jobs.dtype, np.integer):
        complaints.append(f"{label}: job indices are not integers")
    elif len(np.unique(jobs)) != len(jobs) or np.any(jobs < 0):
        complaints.append(f"{label}: job indices are not non-negative and unique")
    if not np.issubdtype(withheld.dtype, np.integer) or np.any(withheld <= 0):
        complaints.append(f"{label}: withheld counts are not positive integers")
    score_delta = arrays["score_delta"]
    corrected_score = arrays["corrected_score"]
    if not np.issubdtype(score_delta.dtype, np.number) or not np.isfinite(score_delta).all():
        complaints.append(f"{label}: score deltas are not finite")
    if (
        not np.issubdtype(corrected_score.dtype, np.number)
        or not np.isfinite(corrected_score).all()
    ):
        complaints.append(f"{label}: corrected scores are not finite")
    return complaints


def _delta_array_complaints(path: Path, row: Row) -> list[str]:
    label = row.get("path", str(path))
    lengths, complaints = _delta_manifest_lengths(row, label)
    if lengths is None:
        return complaints
    expected_length, expected_bytes = lengths
    arrays, read_complaints = _read_delta_arrays(path, row, expected_bytes, label)
    complaints += read_complaints
    if not arrays:
        return complaints
    return complaints + _delta_value_complaints(arrays, expected_length, label)


def _terminal_job_counts(rows: list[Row]) -> dict[Group, int]:
    output = {}
    for row in rows:
        if _text(row, "terminal_zero").lower() == "true":
            try:
                output[_group(row)] = int(row["cumulative_jobs"])
            except (KeyError, TypeError, ValueError):
                continue
    return output


def _delta_complaints(
    directory: Path,
    rows: list[Row],
    expected_groups: set[Group],
    certificate_jobs: dict[Group, int],
) -> list[str]:
    complaints = _missing_fields_complaints(rows, DELTA_FIELDS, "exact_delta_manifest.csv")
    complaints += _coverage_complaints(
        rows,
        ("overlay", "level", "policy", "variant"),
        expected_groups,
        "exact_delta_manifest.csv",
    )
    paths = [_text(row, "path") for row in rows]
    duplicated_paths = sorted(path for path, count in Counter(paths).items() if count > 1)
    if duplicated_paths:
        complaints.append(f"exact_delta_manifest.csv: duplicated paths {duplicated_paths[:3]}")
    for row in rows:
        key = _group(row)
        try:
            affected_jobs = int(row["affected_jobs"])
        except (KeyError, TypeError, ValueError):
            affected_jobs = -1
        if key not in certificate_jobs:
            complaints.append(f"{key}: delta has no valid terminal certificate")
        elif affected_jobs != certificate_jobs[key]:
            complaints.append(f"{key}: delta affected_jobs disagrees with terminal certificate")
        expected_baseline = "original" if key[3] == "exact" else "other_class_withheld"
        if row.get("baseline_variant") != expected_baseline:
            complaints.append(f"{key}: unexpected delta baseline_variant")
        relative = _text(row, "path")
        if not relative:
            complaints.append(f"{key}: sparse delta path is missing")
            continue
        path = (directory / relative).resolve()
        if not path.is_relative_to(directory.resolve()):
            complaints.append("sparse delta path escapes its output directory")
            continue
        complaints += _delta_array_complaints(path, row)
    return complaints


def coverage_complaints(
    rows: list[Row], policies: list[str], overlays: list[int], levels: list[int]
) -> list[str]:
    expected = {
        (str(o), str(level), policy, variant)
        for o in overlays
        for level in levels
        for policy in policies
        for variant in EXACT_VARIANTS
    }
    complaints = _coverage_complaints(
        rows,
        ("overlay", "level", "base_policy", "variant"),
        expected,
        "exact_cells.csv",
    )
    complaints += _composite_policy_complaints(rows, "exact_cells.csv")
    return complaints


def _composite_policy_complaints(rows: list[Row], label: str) -> list[str]:
    for row in rows:
        expected = f"{row.get('base_policy', '')}|{row.get('variant', '')}"
        if row.get("policy") != expected:
            return [f"{label}: policy/base_policy/variant disagree"]
    return []


def comparison_coverage_complaints(
    rows: list[Row], policies: list[str], levels: list[int]
) -> list[str]:
    expected = {
        (str(level), policy, variant)
        for level in levels
        for policy in policies
        for variant in EXACT_VARIANTS
    }
    return _coverage_complaints(
        rows, ("level", "base_policy", "variant"), expected, "exact_comparison.csv"
    ) + _composite_policy_complaints(rows, "exact_comparison.csv")


def sensitivity_coverage_complaints(
    rows: list[Row], overlays: list[int], levels: list[int], *, aggregate: bool = False
) -> list[str]:
    variants = ("exact", SENSITIVITY_VARIANT)
    fields: tuple[str, ...]
    expected: set[tuple[str, ...]]
    if aggregate:
        fields = ("level", "base_policy", "variant")
        expected = {
            (str(level), "Guard(600)", variant) for level in levels for variant in variants
        }
    else:
        fields = ("overlay", "level", "base_policy", "variant")
        expected = {
            (str(overlay), str(level), "Guard(600)", variant)
            for overlay in overlays
            for level in levels
            for variant in variants
        }
    label = "exact_sensitivity_comparison.csv" if aggregate else "exact_sensitivity_cells.csv"
    complaints = _coverage_complaints(rows, fields, expected, label)
    complaints += _composite_policy_complaints(rows, label)
    return complaints


def existing_anchor_complaints(
    current: list[dict[str, str]], historical: list[dict[str, str]]
) -> list[str]:
    """Replayed anchors must reproduce existing cells and aggregate intervals."""
    lookup = {
        (row.get("overlay", "pooled"), row["level"], row["base_policy"], row["variant"]): row
        for row in current
    }
    complaints = []
    for old in historical:
        if old["variant"] == "reference":
            continue
        policy = old["policy"].removesuffix("-original").removesuffix("-static")
        key = (old.get("overlay", "pooled"), old["level"], policy, old["variant"])
        if key not in lookup:
            complaints.append(f"{key}: historical anchor is missing")
            continue
        new = lookup[key]
        fields = set(old) & set(new) - {"policy"}
        changed = sorted(name for name in fields if old[name] != new[name])
        if changed:
            complaints.append(f"{key}: historical anchor differs in {changed}")
    return complaints


def _manifest_complaints(path: Path) -> tuple[dict[str, object], list[str]]:
    if not path.is_file():
        return {}, ["manifest.json: required run manifest is missing"]
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {}, [f"manifest.json: cannot read run manifest ({type(exc).__name__})"]
    if not isinstance(document, dict):
        return {}, ["manifest.json: run manifest is not a JSON object"]
    try:
        return document, provenance.verify(path)
    except (KeyError, TypeError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        return document, [f"manifest.json: malformed run manifest ({type(exc).__name__})"]


def _full_table_complaints(
    directory: Path,
    policies: list[str],
    overlays: list[int],
    levels: list[int],
) -> tuple[list[Row], list[str]]:
    exact_rows, complaints = _required_rows(directory / "exact_cells.csv")
    exact_comparison, exact_comparison_io = _required_rows(directory / "exact_comparison.csv")
    sensitivity_rows, sensitivity_io = _required_rows(directory / "exact_sensitivity_cells.csv")
    comparison_rows, comparison_io = _required_rows(
        directory / "exact_sensitivity_comparison.csv"
    )
    complaints += sensitivity_io + comparison_io + exact_comparison_io
    complaints += coverage_complaints(exact_rows, policies, overlays, levels)
    complaints += comparison_coverage_complaints(exact_comparison, policies, levels)
    complaints += sensitivity_coverage_complaints(sensitivity_rows, overlays, levels)
    complaints += sensitivity_coverage_complaints(
        comparison_rows, overlays, levels, aggregate=True
    )
    return exact_rows, complaints


def _is_primary_manifest(document: dict[str, object]) -> bool:
    arguments = document.get("arguments")
    return isinstance(arguments, dict) and arguments.get("pool") == "primary"


def _historical_complaints(directory: Path, exact_rows: list[Row]) -> list[str]:
    historical = ROOT / "outputs/dev_visibility"
    comparison, complaints = _required_rows(directory / "exact_comparison.csv")
    for table, current in (
        ("cells", exact_rows),
        ("comparison", comparison),
    ):
        path = historical / f"visibility_{table}.csv"
        if path.is_file():
            complaints += existing_anchor_complaints(current, _rows(path))
    return complaints


def check(directory: Path, cfg: cfgmod.Config, require_full: bool = True) -> list[str]:
    document, complaints = _manifest_complaints(directory / "manifest.json")
    pass_rows, pass_io = _required_rows(directory / "exact_passes.csv")
    delta_rows, delta_io = _required_rows(directory / "exact_delta_manifest.csv")
    complaints += pass_io + delta_io
    policies = list(cfg["features"]["exact_visibility"]["policies"])
    overlays = list(cfg["overlay"]["overlays"])
    levels = [0, 1, 2]
    expected_groups = (
        expected_refinement_groups(policies, overlays, levels)
        if require_full
        else {_group(row) for row in pass_rows}
    )
    complaints += certificate_complaints(pass_rows, expected_groups if require_full else None)
    complaints += _delta_complaints(
        directory, delta_rows, expected_groups, _terminal_job_counts(pass_rows)
    )
    exact_rows: list[Row] = []
    if require_full:
        exact_rows, full_complaints = _full_table_complaints(
            directory, policies, overlays, levels
        )
        complaints += full_complaints
    if _is_primary_manifest(document) and exact_rows:
        complaints += _historical_complaints(directory, exact_rows)
    return complaints


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=ROOT / "configs/main.yaml")
    parser.add_argument(
        "--directory", type=Path, default=ROOT / "outputs/dev_consistent_visibility"
    )
    parser.add_argument("--allow-subset", action="store_true")
    args = parser.parse_args()
    complaints = check(args.directory, cfgmod.load(args.config), not args.allow_subset)
    for complaint in complaints:
        print(complaint)
    if not complaints:
        print(
            "exact visibility: complete coverage, monotone zero-violation certificates, "
            "sparse deltas intact"
        )
    return int(bool(complaints))


if __name__ == "__main__":
    raise SystemExit(main())
