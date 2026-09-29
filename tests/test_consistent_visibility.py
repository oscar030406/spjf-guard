"""The violation-driven refinement is monotone and ends on a zero pass."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from spjf_guard.experiment.consistent import queue_rank_displacement, refine_policy
from spjf_guard.experiment.visibility import build_same_copy_history_index
from spjf_guard.features.refine import M4HistoryRecomputer
from spjf_guard.features.sweep import HIST_COLS, feature_frame
from spjf_guard.sim import Trace
from spjf_guard.sim.policy import MICROS, spjf


class _Frozen:
    def predict(self, submission_rows, histories):
        return np.full(len(submission_rows), 9.0)


def _case():
    is_submission = np.ones(3, bool)
    rows = np.arange(3, dtype=np.int64)
    prepared = SimpleNamespace(
        is_submission=is_submission,
        submission_rows=rows,
        row_of=rows.copy(),
        exercise=np.array([1, 0, 0], np.int64),
        user=np.array([1, 0, 0], np.int64),
        class_term=np.zeros(3, np.int64),
        assessment=np.zeros(3, np.int64),
        permuted_exercise=np.array([1, 0, 0], np.int64),
        permuted_assessment=np.zeros(3, np.int64),
        n_exercises=2,
        n_classes=1,
        tercile_cuts=(0.5, 1.5),
        n_testcases=np.ones(3),
        log_cost=np.log1p(np.array([20.0, 5.0, 5.0])),
        heavy=np.array([1.0, 0.0, 0.0]),
        error=np.zeros(3),
        simulatable=np.ones(3, bool),
        semester=np.array(["s", "s", "s"], dtype=object),
    )
    original_arrival = np.array([0.0, 0.0, 10.0])
    original_done = np.array([5.0, 5.0, 15.0])
    baseline_history = feature_frame(prepared, original_arrival, original_done)[
        list(HIST_COLS)
    ].to_numpy(np.float32)
    recomputer = M4HistoryRecomputer(prepared, original_arrival, original_done)
    index = build_same_copy_history_index(prepared, original_arrival, original_done, ["s"])
    trace = Trace.from_seconds(
        [0.0, 0.0, 10.0],
        [20.0, 5.0, 5.0],
        scores={"exact": np.array([0.0, 1.0, 2.0])},
    )
    arrays = {
        "arrival_us": trace.arrival_us,
        "service_us": trace.service_us,
        "job_row": rows,
        "copy_entry": np.zeros(3, np.int32),
    }
    return trace, arrays, index, recomputer, baseline_history


def _two_pass_case():
    """A first withdrawal delays its target and exposes a second target."""
    rows = np.arange(4, dtype=np.int64)
    original_arrival = np.array([0.0, 1.0, 6.0, 12.0])
    service = np.array([10.0, 5.0, 1.0, 1.0])
    prepared = SimpleNamespace(
        is_submission=np.ones(4, bool),
        submission_rows=rows,
        row_of=rows.copy(),
        exercise=np.array([2, 0, 1, 1], np.int64),
        user=np.array([2, 0, 0, 1], np.int64),
        class_term=np.zeros(4, np.int64),
        assessment=np.zeros(4, np.int64),
        permuted_exercise=np.array([2, 0, 1, 1], np.int64),
        permuted_assessment=np.zeros(4, np.int64),
        n_exercises=3,
        n_classes=1,
        tercile_cuts=(0.5, 1.5),
        n_testcases=np.ones(4),
        log_cost=np.log1p(service),
        heavy=(service > 4.0).astype(float),
        error=np.zeros(4),
        simulatable=np.ones(4, bool),
        semester=np.array(["s"] * 4, dtype=object),
    )
    original_done = original_arrival + service
    baseline_history = feature_frame(prepared, original_arrival, original_done)[
        list(HIST_COLS)
    ].to_numpy(np.float32)
    recomputer = M4HistoryRecomputer(prepared, original_arrival, original_done)
    index = build_same_copy_history_index(prepared, original_arrival, original_done, ["s"])
    trace = Trace.from_seconds(
        original_arrival,
        service,
        scores={"exact": np.array([0.0, 2.0, 1.0, 3.0])},
    )
    arrays = {
        "arrival_us": trace.arrival_us,
        "service_us": trace.service_us,
        "job_row": rows,
        "copy_entry": np.zeros(4, np.int32),
    }
    return trace, arrays, index, recomputer, baseline_history


def test_refinement_records_the_terminal_zero_violation_pass():
    trace, arrays, index, recomputer, baseline_history = _case()
    result = refine_policy(
        trace,
        spjf("exact"),
        servers=1,
        window=16,
        arrays=arrays,
        history=index,
        recomputer=recomputer,
        models=_Frozen(),
        baseline_history=baseline_history,
        baseline_score=np.array([0.0, 1.0, 2.0]),
        score_key="exact",
    )
    assert [(p.affected_jobs, p.offending_records) for p in result.passes] == [(1, 1), (0, 0)]
    np.testing.assert_array_equal(result.changed_jobs, [2])
    np.testing.assert_array_equal(result.withheld_counts, [1])
    np.testing.assert_array_equal(result.score_delta, [7.0])
    np.testing.assert_array_equal(result.initial_jobs, [2])
    np.testing.assert_array_equal(result.initial_score_delta, [7.0])
    np.testing.assert_array_equal(result.initial_corrected_score, [9.0])


def test_refinement_is_monotone_when_a_withdrawal_creates_a_later_violation():
    trace, arrays, index, recomputer, baseline_history = _two_pass_case()
    baseline_score = trace.scores["exact"]
    result = refine_policy(
        trace,
        spjf("exact"),
        servers=1,
        window=16,
        arrays=arrays,
        history=index,
        recomputer=recomputer,
        models=_Frozen(),
        baseline_history=baseline_history,
        baseline_score=baseline_score,
        score_key="exact",
    )

    assert [(p.affected_jobs, p.offending_records) for p in result.passes] == [
        (1, 1),
        (1, 1),
        (0, 0),
    ]
    cumulative_jobs = [p.cumulative_jobs for p in result.passes]
    cumulative_records = [p.cumulative_records for p in result.passes]
    assert cumulative_jobs == sorted(cumulative_jobs) == [1, 2, 2]
    assert cumulative_records == sorted(cumulative_records) == [1, 2, 2]
    np.testing.assert_array_equal(result.changed_jobs, [2, 3])
    np.testing.assert_array_equal(result.withheld_counts, [1, 1])
    np.testing.assert_array_equal(result.score_delta, [8.0, 6.0])
    assert result.passes[-1].affected_jobs == 0
    assert result.passes[-1].offending_records == 0

    fast_arrays = {**arrays, "copy_round": np.zeros(len(trace), np.int32)}
    fast = refine_policy(
        trace,
        spjf("exact"),
        servers=1,
        window=16,
        arrays=fast_arrays,
        history=index,
        recomputer=recomputer,
        models=_Frozen(),
        baseline_history=baseline_history,
        baseline_score=baseline_score,
        score_key="exact",
    )
    assert [p.cumulative_records for p in fast.passes] == cumulative_records
    np.testing.assert_array_equal(fast.outcome.wait_us, result.outcome.wait_us)
    np.testing.assert_array_equal(fast.changed_jobs, result.changed_jobs)
    np.testing.assert_array_equal(fast.corrected_score, result.corrected_score)


def test_rank_displacement_uses_the_dispatch_queue_not_the_whole_trace():
    arrival = np.array([0, 0, 10], np.int64) * MICROS
    start = np.array([0, 30, 25], np.int64) * MICROS
    score = np.array([0.0, 1.0, 2.0])
    moved = queue_rank_displacement(arrival, start, score, np.array([2]), np.array([-2.0]))
    np.testing.assert_array_equal(moved, [-1])


def test_rank_uses_absolute_corrected_score_without_delta_round_trip():
    arrival = np.array([0, 1], np.int64)
    start = np.array([2, 3], np.int64)
    score = np.array([2.0, np.nextafter(0.0001, -np.inf)])
    jobs = np.array([0], np.int64)
    corrected = np.array([0.0001])
    delta = corrected - score[jobs]

    legacy = queue_rank_displacement(
        arrival, start, score, jobs, delta, dispatch_order=np.array([0, 1])
    )
    exact = queue_rank_displacement(
        arrival,
        start,
        score,
        jobs,
        delta,
        dispatch_order=np.array([0, 1]),
        corrected_score=corrected,
    )

    np.testing.assert_array_equal(legacy, [-1])
    np.testing.assert_array_equal(exact, [0])


def test_rank_applies_all_changes_and_respects_same_time_dispatch_order():
    arrival = np.zeros(3, np.int64)
    start = np.zeros(3, np.int64)
    score = np.array([1.0, 2.0, 3.0])
    moved = queue_rank_displacement(
        arrival,
        start,
        score,
        np.array([0, 1]),
        np.array([2.0, -2.0]),
        dispatch_order=np.array([1, 0, 2]),
    )
    # Job 1 moves to the front at its dispatch. By job 0's dispatch it has left.
    np.testing.assert_array_equal(moved, [0, -1])


def test_rank_matches_a_brute_queue_snapshot_with_score_ties():
    arrival = np.array([0, 0, 0, 5, 5, 9], np.int64) * MICROS
    start = np.array([0, 0, 5, 5, 12, 9], np.int64) * MICROS
    dispatch_order = np.array([1, 0, 3, 2, 5, 4], np.int64)
    score = np.array([1.0, 1.0, 2.0, 2.0, 3.0, 3.0])
    jobs = np.array([0, 1, 2, 3, 4, 5], np.int64)
    delta = np.array([1.0, 0.0, 1.0, -1.0, 0.0, -2.0])

    corrected = score + delta
    active: set[int] = set()
    cursor = 0
    old_rank = np.zeros(len(score), np.int64)
    new_rank = np.zeros(len(score), np.int64)
    for job in dispatch_order:
        now = start[job]
        while cursor < len(arrival) and arrival[cursor] <= now:
            active.add(cursor)
            cursor += 1
        old = sorted(active, key=lambda item: (score[item], item))
        new = sorted(active, key=lambda item: (corrected[item], item))
        old_rank[job] = old.index(int(job)) + 1
        new_rank[job] = new.index(int(job)) + 1
        active.remove(int(job))

    actual = queue_rank_displacement(
        arrival,
        start,
        score,
        jobs,
        delta,
        dispatch_order=dispatch_order,
    )
    np.testing.assert_array_equal(actual, new_rank[jobs] - old_rank[jobs])
