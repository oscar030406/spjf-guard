"""Targeted history recomputation agrees with the full causal sweep."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from spjf_guard.features.refine import M4HistoryRecomputer
from spjf_guard.features.sweep import HIST_COLS, feature_frame


def _prepared():
    is_submission = np.array([True, True, False, True, True, True])
    rows = np.flatnonzero(is_submission)
    row_of = np.full(len(is_submission), -1, np.int64)
    row_of[rows] = np.arange(len(rows))
    cost = np.array([1.0, 3.0, 0.0, 2.0, 4.0, 5.0])
    return SimpleNamespace(
        is_submission=is_submission,
        submission_rows=rows,
        row_of=row_of,
        exercise=np.array([0, 1, 0, 0, 1, 0], np.int64),
        user=np.array([0, 0, 0, 1, 0, 0], np.int64),
        class_term=np.array([0, 0, 0, 0, 1, 0], np.int64),
        assessment=np.zeros(6, np.int64),
        permuted_exercise=np.array([0, 1, 0, 0, 1, 0], np.int64),
        permuted_assessment=np.zeros(6, np.int64),
        n_exercises=2,
        n_classes=2,
        tercile_cuts=(0.5, 1.5),
        n_testcases=np.arange(1.0, 7.0),
        log_cost=np.log1p(cost),
        heavy=(cost > 2.5).astype(float),
        error=np.array([0.0, 1.0, 1.0, 0.0, 0.0, 1.0]),
        simulatable=np.ones(len(rows), bool),
        semester=np.array(["s", "s", "s", "s", "s", "s"], dtype=object),
    )


def test_targeted_recomputation_reproduces_every_full_sweep_row():
    prepared = _prepared()
    arrival = np.array([0.0, 2.0, 3.0, 4.0, 6.0, 8.0])
    availability = np.array([1.0, 5.0, 4.0, 6.0, 10.0, 13.0])
    baseline = feature_frame(prepared, arrival, availability)[list(HIST_COLS)].to_numpy()
    indexed = M4HistoryRecomputer(prepared, arrival, availability)
    rebuilt = np.vstack(
        [indexed.recompute(i, baseline[i]) for i in range(len(prepared.submission_rows))]
    )
    np.testing.assert_allclose(rebuilt, baseline, equal_nan=True, rtol=0.0, atol=1e-7)


def test_withholding_one_submission_changes_only_outcome_fields():
    prepared = _prepared()
    arrival = np.array([0.0, 2.0, 3.0, 4.0, 6.0, 8.0])
    availability = np.array([1.0, 5.0, 4.0, 6.0, 10.0, 13.0])
    baseline = feature_frame(prepared, arrival, availability)[list(HIST_COLS)].to_numpy()
    indexed = M4HistoryRecomputer(prepared, arrival, availability)
    changed = indexed.recompute(4, baseline[4], excluded={0})
    for field in ("ex_n", "u_n", "ue_n", "ue_log_sec_since", "prev_ev_log_sec"):
        position = HIST_COLS.index(field)
        assert changed[position] == baseline[4, position]
    assert changed[HIST_COLS.index("u_mean_log")] != baseline[4, HIST_COLS.index("u_mean_log")]


def test_other_class_sensitivity_withholds_only_same_semester_pool_classes():
    prepared = _prepared()
    arrival = np.array([0.0, 2.0, 3.0, 4.0, 6.0, 8.0])
    availability = np.array([1.0, 5.0, 4.0, 6.0, 7.0, 13.0])
    baseline = feature_frame(prepared, arrival, availability)[list(HIST_COLS)].to_numpy()
    indexed = M4HistoryRecomputer(prepared, arrival, availability)
    kept = indexed.recompute(4, baseline[4], pool_terms={"other"})
    withheld = indexed.recompute(
        4,
        baseline[4],
        withhold_other_pool_classes=True,
        pool_terms={"s"},
    )
    np.testing.assert_allclose(kept, baseline[4], equal_nan=True)
    assert withheld[HIST_COLS.index("u_n")] == baseline[4, HIST_COLS.index("u_n")] - 1
    assert withheld[HIST_COLS.index("u_mean_log")] != baseline[4, HIST_COLS.index("u_mean_log")]


def test_other_class_without_a_replayed_copy_remains_exogenous():
    prepared = _prepared()
    prepared.simulatable[3] = False
    arrival = np.array([0.0, 2.0, 3.0, 4.0, 6.0, 8.0])
    availability = np.array([1.0, 5.0, 4.0, 6.0, 7.0, 13.0])
    baseline = feature_frame(prepared, arrival, availability)[list(HIST_COLS)].to_numpy()
    indexed = M4HistoryRecomputer(prepared, arrival, availability)
    changed = indexed.recompute(
        4, baseline[4], withhold_other_pool_classes=True, pool_terms={"s"}
    )
    np.testing.assert_array_equal(changed, baseline[4])


def test_last_result_follows_arrival_not_completion_order():
    prepared = _prepared()
    prepared.exercise[:] = 0
    prepared.user[:] = 0
    arrival = np.array([0.0, 50.0, 70.0, 110.0, 120.0, 130.0])
    availability = np.array([100.0, 60.0, 75.0, 115.0, 125.0, 135.0])
    baseline = feature_frame(prepared, arrival, availability)[list(HIST_COLS)].to_numpy()
    indexed = M4HistoryRecomputer(prepared, arrival, availability)
    rebuilt = indexed.recompute(2, baseline[2])
    np.testing.assert_array_equal(rebuilt, baseline[2])
    assert rebuilt[17] == np.float32(prepared.log_cost[1])
    assert rebuilt[20] == prepared.error[2]
    without = indexed.recompute(2, baseline[2], excluded={1})
    assert without[17] == np.float32(prepared.log_cost[0])


def _random_prepared(n: int):
    rng = np.random.default_rng(701)
    prepared = _prepared()
    prepared.is_submission = rng.random(n) > 0.1
    prepared.submission_rows = np.flatnonzero(prepared.is_submission)
    prepared.row_of = np.full(n, -1, np.int64)
    prepared.row_of[prepared.submission_rows] = np.arange(len(prepared.submission_rows))
    for key in ("exercise", "user", "class_term", "assessment"):
        setattr(prepared, key, np.zeros(n, np.int64))
    prepared.permuted_exercise = prepared.exercise.copy()
    prepared.permuted_assessment = prepared.assessment.copy()
    prepared.n_testcases = rng.integers(1, 6, n).astype(float)
    prepared.log_cost = np.log1p(rng.random(n) * 10)
    prepared.heavy = (prepared.log_cost > 2.0).astype(float)
    prepared.error = (rng.random(n) < 0.3).astype(float)
    prepared.simulatable = np.ones(len(prepared.submission_rows), bool)
    prepared.semester = np.full(n, "s", object)
    arrival = rng.integers(0, 300, n).astype(float)
    available = arrival + rng.integers(0, 51, n)
    return prepared, arrival, available


def test_crossing_ties_rolling_and_withholding_match_full_sweep():
    prepared, arrival, available = _random_prepared(400)
    baseline = feature_frame(prepared, arrival, available)[list(HIST_COLS)].to_numpy()
    indexed = M4HistoryRecomputer(prepared, arrival, available)
    rebuilt = np.vstack([indexed.recompute(i, row) for i, row in enumerate(baseline)])
    np.testing.assert_array_equal(rebuilt, baseline)
    excluded = {1, 4, 12, 43, 98, 120}
    mask = np.ones(len(arrival), bool)
    mask[prepared.submission_rows[list(excluded)]] = False
    reference = feature_frame(prepared, arrival, available, record_mask=mask)[
        list(HIST_COLS)
    ].to_numpy(copy=True)
    reference[:, [0, 9, 16, 19, 21]] = baseline[:, [0, 9, 16, 19, 21]]
    changed = np.vstack(
        [indexed.recompute(i, row, excluded=excluded) for i, row in enumerate(baseline)]
    )
    np.testing.assert_array_equal(changed, reference)


def test_same_copy_lag_reorders_retained_rolling_outcomes_like_the_full_sweep():
    prepared, arrival, available = _random_prepared(400)
    prepared.class_term = np.arange(400, dtype=np.int64) % 2
    baseline = feature_frame(prepared, arrival, available)[list(HIST_COLS)].to_numpy()
    indexed = M4HistoryRecomputer(prepared, arrival, available)
    for target in (23, 71, 203, 300):
        target_class = prepared.class_term[prepared.submission_rows[target]]
        shifted = available.copy()
        own = (prepared.class_term == target_class) & prepared.is_submission
        shifted[own] += 60.0
        reference = feature_frame(prepared, arrival, shifted)[list(HIST_COLS)].to_numpy()
        changed = indexed.recompute(target, baseline[target], same_copy_lag_s=60.0)
        np.testing.assert_array_equal(changed, reference[target])


def test_other_class_complete_withholding_matches_record_mask():
    prepared, arrival, available = _random_prepared(400)
    prepared.class_term = np.arange(400, dtype=np.int64) % 2
    prepared.semester[:80] = "earlier"
    baseline = feature_frame(prepared, arrival, available)[list(HIST_COLS)].to_numpy()
    indexed = M4HistoryRecomputer(prepared, arrival, available)
    for target in (200, 300):
        event = prepared.submission_rows[target]
        mask = (prepared.class_term == prepared.class_term[event]) | (prepared.semester != "s")
        reference = feature_frame(prepared, arrival, available, record_mask=mask)[
            list(HIST_COLS)
        ].to_numpy()
        changed = indexed.recompute(
            target, baseline[target], withhold_other_pool_classes=True, pool_terms={"s"}
        )
        np.testing.assert_array_equal(changed, reference[target])
