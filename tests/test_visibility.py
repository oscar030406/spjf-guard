"""The original-clock exposure audit and the fixed-lag certificate."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from spjf_guard.experiment.visibility import (
    build_history_index,
    build_same_copy_history_index,
    diagnostics,
    exposure_summary,
    premature_counts,
    same_copy_premature_counts,
)
from spjf_guard.sim.policy import MICROS


def _history_arrays():
    prepared = SimpleNamespace(
        submission_rows=np.arange(3, dtype=np.int64),
        semester=np.array(["s", "s", "s"], dtype=object),
        simulatable=np.ones(3, bool),
        user=np.zeros(3, np.int64),
        exercise=np.zeros(3, np.int64),
        class_term=np.zeros(3, np.int64),
        n_exercises=1,
    )
    arrival = np.array([0.0, 10.0, 20.0])
    availability = np.array([5.0, 15.0, 25.0])
    index = build_history_index(prepared, arrival, availability, ["s"])
    return {
        "arrival_us": np.array([0, 10, 20], np.int64) * MICROS,
        "service_us": np.full(3, 5 * MICROS, np.int64),
        "job_row": np.arange(3, dtype=np.int64),
        "copy_round": np.zeros(3, np.int32),
        "copy_entry": np.zeros(3, np.int32),
        "in_window": np.array([False, True, True]),
        **index.arrays(),
    }


def test_premature_records_are_counted_at_each_replayed_arrival():
    arrays = _history_arrays()
    wait = np.array([20, 0, 0], np.int64) * MICROS
    np.testing.assert_array_equal(premature_counts(wait, arrays), [0, 1, 1])
    summary = exposure_summary(wait, arrays)
    assert summary["overall_affected_jobs"] == 2
    assert summary["overall_affected_share"] == 2 / 3
    assert summary["deadline_affected_share"] == 1.0
    assert summary["unreplayed_overall_affected_jobs"] == 0


def test_lag_violations_are_reported_overall_and_in_deadline_windows():
    wait = np.array([0.0, 9.0, 11.0]) * MICROS
    out = diagnostics(wait.astype(np.int64), np.array([False, True, True]), lag_s=10.0)
    assert out["lag_violations"] == 1
    assert out["lag_violation_share"] == 1 / 3
    assert out["lag_deadline_violation_share"] == 0.5
    assert out["lag_max_excess_s"] == 1.0


def test_same_copy_excludes_an_independently_shifted_class_term():
    prepared = SimpleNamespace(
        submission_rows=np.arange(4, dtype=np.int64),
        semester=np.array(["s", "s", "s", "s"], dtype=object),
        simulatable=np.ones(4, bool),
        user=np.zeros(4, np.int64),
        exercise=np.zeros(4, np.int64),
        class_term=np.array([0, 1, 0, 1], np.int64),
        n_exercises=1,
    )
    original_arrival = np.array([0.0, 0.0, 10.0, 10.0])
    original_done = np.array([5.0, 5.0, 15.0, 15.0])
    index = build_same_copy_history_index(prepared, original_arrival, original_done, ["s"])
    arrays = {
        "arrival_us": np.array([0, 0, 10, 10], np.int64) * MICROS,
        "service_us": np.full(4, 5 * MICROS, np.int64),
        "job_row": np.arange(4, dtype=np.int64),
        "copy_entry": np.array([0, 1, 0, 1], np.int32),
    }
    wait = np.array([20, 20, 0, 0], np.int64) * MICROS
    np.testing.assert_array_equal(same_copy_premature_counts(wait, arrays, index), [0, 0, 1, 1])


def test_same_copy_round_fast_path_matches_per_entry_reference():
    prepared = SimpleNamespace(
        submission_rows=np.arange(6, dtype=np.int64),
        semester=np.array(["a", "a", "a", "b", "b", "b"], dtype=object),
        simulatable=np.ones(6, bool),
        user=np.array([0, 0, 1, 0, 0, 1], np.int64),
        exercise=np.array([0, 1, 0, 0, 1, 0], np.int64),
        class_term=np.array([0, 0, 0, 1, 1, 1], np.int64),
        n_exercises=2,
    )
    original_arrival = np.array([0.0, 4.0, 9.0, 1.0, 6.0, 11.0])
    original_done = original_arrival + np.array([2.0, 3.0, 2.0, 4.0, 2.0, 3.0])
    index = build_same_copy_history_index(prepared, original_arrival, original_done, ["a", "b"])

    rng = np.random.default_rng(20260922)
    arrivals = []
    services = []
    job_rows = []
    copy_entries = []
    copy_rounds = []
    for round_ in range(3):
        for term_index, term_rows in enumerate((np.arange(3), np.arange(3, 6))):
            entry = round_ * 2 + term_index
            shift = float(rng.integers(0, 8))
            arrivals.append(original_arrival[term_rows] + shift)
            services.append(original_done[term_rows] - original_arrival[term_rows])
            job_rows.append(term_rows)
            copy_entries.append(np.full(3, entry, np.int32))
            copy_rounds.append(np.full(3, round_, np.int32))
    arrival_s = np.concatenate(arrivals)
    order = np.argsort(arrival_s, kind="stable")
    fast = {
        "arrival_us": np.rint(arrival_s[order] * MICROS).astype(np.int64),
        "service_us": np.rint(np.concatenate(services)[order] * MICROS).astype(np.int64),
        "job_row": np.concatenate(job_rows)[order],
        "copy_entry": np.concatenate(copy_entries)[order],
        "copy_round": np.concatenate(copy_rounds)[order],
    }
    wait = rng.integers(0, 12 * MICROS, len(order), dtype=np.int64)
    reference = {key: value for key, value in fast.items() if key != "copy_round"}

    np.testing.assert_array_equal(
        same_copy_premature_counts(wait, fast, index),
        same_copy_premature_counts(wait, reference, index),
    )
