"""The original-clock exposure audit and the fixed-lag certificate."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from spjf_guard.experiment.visibility import (
    build_history_index,
    diagnostics,
    exposure_summary,
    premature_counts,
)
from spjf_guard.sim.policy import MICROS


def _history_arrays():
    prepared = SimpleNamespace(
        submission_rows=np.arange(3, dtype=np.int64),
        semester=np.array(["s", "s", "s"], dtype=object),
        simulatable=np.ones(3, bool),
        user=np.zeros(3, np.int64),
        exercise=np.zeros(3, np.int64),
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
