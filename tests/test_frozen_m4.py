"""Targeted rescoring changes history columns, not frozen model weights or other inputs."""

import numpy as np
import pandas as pd
import pytest

from spjf_guard.data.clock import Clock
from spjf_guard.data.events import CODE_COLUMNS, Prepared, heavy_threshold_and_cuts
from spjf_guard.features.refine import M4HistoryRecomputer
from spjf_guard.features.sweep import HIST_COLS, feature_frame
from spjf_guard.predict.forward import (
    FIXED_CUTOFFS,
    REFIT_CUTOFFS,
    FrozenM4Models,
    fit_forward,
    fit_frozen_m4_models,
)


class _Model:
    def __init__(self, scale: float):
        self.scale = scale
        self.blocks: list[np.ndarray] = []

    def predict(self, matrix: np.ndarray) -> np.ndarray:
        self.blocks.append(matrix.copy())
        return self.scale * np.nan_to_num(matrix).sum(axis=1)


def test_frozen_rescore_keeps_static_design_and_returns_original_requested_order():
    width = len(HIST_COLS)
    design = np.arange(4 * (width + 2), dtype=np.float32).reshape(4, width + 2)
    models = {"a": _Model(1.0), "b": _Model(2.0)}
    frozen = FrozenM4Models(models, design, np.array(["a", "b", "a", "b"]))
    rows = np.array([3, 0, 2], np.int64)
    histories = np.ones((3, width), np.float32)
    original = design.copy()
    prediction = frozen.predict(rows, histories)
    expected = (design[rows, :2].sum(axis=1) + width) * np.array([2.0, 1.0, 1.0])
    np.testing.assert_array_equal(prediction, expected)
    np.testing.assert_array_equal(design, original)
    np.testing.assert_array_equal(models["b"].blocks[0][:, :2], design[[3], :2])
    np.testing.assert_array_equal(models["a"].blocks[0][:, 2:], histories[[1, 2]])
    assert models["a"].scale == 1.0 and models["b"].scale == 2.0


def test_frozen_rescore_rejects_misaligned_history_rows():
    frozen = FrozenM4Models({}, np.zeros((1, len(HIST_COLS) + 2)), np.array(["a"]))
    with pytest.raises(ValueError, match="differ in length"):
        frozen.predict(np.array([0]), np.empty((0, len(HIST_COLS))))


TERMS = ["t0", "t1", "t2", "t3"]
LIMIT_S = 60.0
PREDICTOR = {
    "n_estimators": 40,
    "learning_rate": 0.1,
    "num_leaves": 15,
    "min_child_samples": 5,
    "seed": 3,
    "num_threads": 1,
    "fixed_cutoff_terms": ["t0", "t1"],
}


def _four_terms(per_term: int = 300):
    """Four terms in calendar order, the fixed cut-offs taken on t0 and t1.  t1 runs longer
    jobs than t0, so the p95 of t0 alone, which t1's forward fit has to use, is lower.  A
    few users submit most of the long jobs and the code and assessment columns carry
    nothing, so the later models split on the heavy rates."""
    rng = np.random.default_rng(17)
    n = per_term * len(TERMS)
    term = np.repeat(np.arange(len(TERMS)), per_term)
    timestamp = np.sort(rng.uniform(1e3, 9e5, n)) + term * 1e6
    user = rng.integers(0, 20, n)
    long_job = rng.random(n) < np.where(user < 4, 0.5, 0.02)
    cost = np.where(long_job, rng.uniform(2.0, 50.0, n), rng.gamma(0.5, 0.5, n))
    cost32 = (cost * np.where(term == 1, 3.0, 1.0)).astype(np.float32)
    cost = cost32.astype(np.float64)
    exercise = rng.integers(0, 10, n)
    assessment = rng.integers(0, 3, n)
    threshold, cuts = heavy_threshold_and_cuts(cost32[term < 2], LIMIT_S)
    prepared = Prepared(
        is_submission=np.ones(n, bool),
        submission_rows=np.arange(n),
        row_of=np.arange(n),
        timestamp_s=timestamp,
        jitter_u=np.zeros(n),
        cost_s=cost,
        semester=np.array(TERMS, object)[term],
        exercise=exercise,
        user=user,
        class_term=term.astype(np.int64),
        assessment=assessment,
        n_exercises=10,
        n_classes=len(TERMS),
        error=(rng.random(n) < 0.3).astype(float),
        n_testcases=rng.integers(1, 6, n).astype(float),
        log_cost=np.log1p(cost),
        heavy_threshold=threshold,
        tercile_cuts=cuts,
        permuted_exercise=exercise.copy(),
        permuted_assessment=assessment.copy(),
        heavy=(cost > threshold).astype(float),
        simulatable=np.ones(n, bool),
    )
    static = {
        "code": np.zeros((n, len(CODE_COLUMNS)), np.float32),
        "a_is_exam": np.zeros(n, np.float32),
        "a_weight": np.ones(n, np.float32),
        "a_nex": np.full(n, 3.0, np.float32),
        "is_remote": np.zeros(n, np.float32),
        "a_end": np.full(n, np.nan),
        "a_start": np.full(n, np.nan),
    }
    return prepared, static, pd.DataFrame({"exec_time": cost32}), Clock(jitter_enabled=False)


def test_a_target_with_refit_cut_offs_is_frozen_on_the_design_its_forward_fit_used():
    prepared, static, events, clock = _four_terms()
    targets = TERMS[1:]
    run = fit_forward(
        prepared, static, events, clock, PREDICTOR, LIMIT_S, targets, TERMS, ("spjf_e",)
    )
    assert [entry["cutoff_source"] for entry in run.log] == [
        REFIT_CUTOFFS,
        FIXED_CUTOFFS,
        FIXED_CUTOFFS,
    ]
    expected = run.scores["spjf_e"]
    frozen, history, arrival, availability = fit_frozen_m4_models(
        prepared,
        static,
        clock,
        PREDICTOR,
        LIMIT_S,
        targets,
        TERMS,
        expected_scores=expected,
        events=events,
    )
    t0 = events["exec_time"].to_numpy()[prepared.semester == "t0"]
    refit = prepared.with_cutoffs(*heavy_threshold_and_cuts(t0, LIMIT_S))
    assert list(frozen.refit_heavy) == ["t1"]
    np.testing.assert_array_equal(frozen.refit_heavy["t1"], refit.heavy)
    in_t1 = prepared.semester == "t1"
    fixed_rows = feature_frame(prepared, arrival, availability)[list(HIST_COLS)]
    refit_rows = feature_frame(refit, arrival, availability)[list(HIST_COLS)]
    fixed_rows, refit_rows = fixed_rows.to_numpy(np.float32), refit_rows.to_numpy(np.float32)
    assert not np.array_equal(fixed_rows[in_t1], refit_rows[in_t1])
    np.testing.assert_array_equal(history, np.where(in_t1[:, None], refit_rows, fixed_rows))
    recomputer = M4HistoryRecomputer(prepared, arrival, availability, frozen.refit_heavy)
    rows = np.flatnonzero(np.isin(prepared.semester, targets))
    rebuilt = np.vstack([recomputer.recompute(int(row), history[row]) for row in rows])
    np.testing.assert_array_equal(rebuilt, history[rows])
    np.testing.assert_array_equal(frozen.predict(rows, rebuilt), expected[rows])
