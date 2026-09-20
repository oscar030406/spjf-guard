"""Causality of the features, tested by deletion and by perturbation.

Research plan 7.2: for a sampled job, deleting every record that completes after that
job's arrival must leave its features unchanged, and perturbing the outcome of a
predecessor still unfinished at that arrival must leave them unchanged too.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from spjf_guard.data.clock import Clock, co_ending_groups, executed_work, jitter
from spjf_guard.features.causal import (
    FEATURE_COLUMNS,
    MissingColumnError,
    build_features,
    check_columns,
)

LIMIT_S = 60.0


def synthetic_events(seed: int = 11, n: int = 900) -> pd.DataFrame:
    """A frame with the columns the builder needs and heavy overlap between runs."""
    rng = np.random.default_rng(seed)
    users = [f"u{i}" for i in range(25)]
    exercises = [f"e{i}" for i in range(12)]
    cost = np.clip(rng.gamma(0.5, 3.0, size=n), 0.05, 400.0)
    base = np.sort(rng.integers(1_600_000_000, 1_600_200_000, size=n)).astype(np.float64)
    frame = pd.DataFrame(
        {
            "semester": "2022-1",
            "class": rng.choice(["c1", "c2"], size=n),
            "user": rng.choice(users, size=n),
            "assessment": rng.choice(["a1", "a2", "a3"], size=n),
            "exercise": rng.choice(exercises, size=n),
            "ts": base,
            "exec_time": cost,
            "has_error": (rng.random(n) < 0.3).astype(float),
        }
    )
    frame["blk_i"] = frame.groupby(
        ["semester", "class", "user", "assessment", "exercise"]
    ).cumcount()
    return frame


def timings(frame: pd.DataFrame, delta_s: float = 0.0):
    clock = Clock(delta_s=delta_s)
    is_submission = np.ones(len(frame), bool)
    cost = executed_work(frame["exec_time"].to_numpy(), LIMIT_S)
    return clock.arrival_and_availability(frame, frame["ts"].to_numpy(), cost, is_submission)


@pytest.mark.parametrize("delta_s", (0.0, 60.0, 600.0, 3600.0))
def test_deleting_everything_that_completes_later_changes_nothing(delta_s):
    frame = synthetic_events()
    arrival, availability = timings(frame, delta_s)
    full = build_features(frame, arrival, availability, limit_s=LIMIT_S)
    rng = np.random.default_rng(5)
    for row in rng.choice(len(frame), size=25, replace=False):
        keep = (availability <= arrival[row]) | (np.arange(len(frame)) == row)
        cut = frame[keep].copy()
        cut_arrival, cut_availability = arrival[keep], availability[keep]
        trimmed = build_features(cut, cut_arrival, cut_availability, limit_s=LIMIT_S)
        position = int(np.flatnonzero(np.flatnonzero(keep) == row)[0])
        before = full.iloc[row][list(FEATURE_COLUMNS)].to_numpy()
        after = trimmed.iloc[position][list(FEATURE_COLUMNS)].to_numpy()
        np.testing.assert_array_equal(after, before)


def test_perturbing_an_unfinished_predecessor_changes_nothing():
    frame = synthetic_events()
    arrival, availability = timings(frame)
    full = build_features(frame, arrival, availability, limit_s=LIMIT_S)
    candidates = [
        i
        for i in range(len(frame))
        if np.any((arrival < arrival[i]) & (availability > arrival[i]))
    ]
    assert candidates, "the instance has no job with a predecessor still running"
    row = candidates[len(candidates) // 2]
    unfinished = np.flatnonzero((arrival < arrival[row]) & (availability > arrival[row]))
    perturbed = frame.copy()
    perturbed.loc[perturbed.index[unfinished], "has_error"] = (
        1.0 - perturbed.loc[perturbed.index[unfinished], "has_error"]
    )
    moved = build_features(perturbed, arrival, availability, limit_s=LIMIT_S)
    np.testing.assert_array_equal(moved.iloc[row].to_numpy(), full.iloc[row].to_numpy())


def test_a_record_readable_exactly_at_the_arrival_is_visible():
    """The rule is `done_j + delta <= a_i`, inclusive, and the sweep implements it."""
    frame = pd.DataFrame(
        {
            "semester": ["s", "s"],
            "class": ["c", "c"],
            "user": ["u", "u"],
            "assessment": ["a", "a"],
            "exercise": ["e", "e"],
            "ts": [10.0, 30.0],
            "exec_time": [5.0, 1.0],
            "has_error": [1.0, 0.0],
            "blk_i": [0, 1],
        }
    )
    arrival = np.array([5.0, 10.0])
    availability = np.array([10.0, 30.0])
    features = build_features(frame, arrival, availability, limit_s=LIMIT_S)
    assert features.iloc[0]["prior_n"] == 0.0
    assert features.iloc[1]["prior_n"] == 1.0
    assert features.iloc[1]["prior_seconds_since"] == 0.0


def test_a_missing_required_column_is_an_error():
    frame = synthetic_events().drop(columns=["exec_time"])
    with pytest.raises(MissingColumnError, match="exec_time"):
        check_columns(frame)


def test_the_jitter_is_a_function_of_the_id_and_the_key_alone():
    frame = synthetic_events()
    first = jitter(frame)
    shuffled = frame.sample(frac=1.0, random_state=2)
    np.testing.assert_array_equal(jitter(shuffled), first[shuffled.index])
    assert np.all((first >= 0.0) & (first < 1.0))
    assert not np.array_equal(jitter(frame, key="cbjitter00000001"), first)


def test_executed_work_is_capped_at_the_limit():
    cost = np.array([0.1, 59.9, 60.0, 400.0])
    np.testing.assert_array_equal(
        executed_work(cost, LIMIT_S), np.array([0.1, 59.9, 60.0, 60.0])
    )


def test_co_ending_groups_are_maximal_and_solo_runs_are_marked():
    semester = np.array(["s"] * 5)
    user = np.array(["u", "u", "u", "v", "v"])
    second = np.array([100, 100, 200, 100, 300])
    groups = co_ending_groups(semester, user, second)
    assert groups[0] == groups[1] >= 0
    assert groups[2] == -1 and groups[3] == -1 and groups[4] == -1


def test_the_two_readings_move_the_arrival_in_opposite_directions():
    frame = synthetic_events(n=50)
    cost = executed_work(frame["exec_time"].to_numpy(), LIMIT_S)
    submission = np.ones(len(frame), bool)
    result = Clock(reading="result").arrival_and_availability(
        frame, frame["ts"].to_numpy(), cost, submission
    )
    submit = Clock(reading="submit").arrival_and_availability(
        frame, frame["ts"].to_numpy(), cost, submission
    )
    assert np.all(result[0] <= submit[0])
    assert np.all(result[1] <= submit[1])
