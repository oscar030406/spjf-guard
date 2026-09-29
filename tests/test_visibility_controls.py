"""Frozen visibility controls agree with per-target causal sweeps."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from spjf_guard.data.events import Prepared
from spjf_guard.experiment.visibility_controls import (
    CONTROL_VARIANTS,
    ControlBuild,
    ControlCost,
    StaleControlCacheError,
    build_control_set,
    cache_key_from_files,
    load_control_cache,
    save_control_cache,
)
from spjf_guard.features.refine import M4HistoryRecomputer
from spjf_guard.features.sweep import HIST_COLS, class_term_scoped, feature_frame


class _Frozen:
    def __init__(self):
        self.weights = np.linspace(0.5, 2.5, len(HIST_COLS))
        self.max_batch = 0
        self.predicted: list[int] = []

    def score(self, histories):
        return np.nan_to_num(histories, nan=0.0) @ self.weights

    def predict(self, submission_rows, histories):
        rows = np.asarray(submission_rows, np.int64)
        self.max_batch = max(self.max_batch, len(rows))
        self.predicted.extend(map(int, rows))
        return self.score(np.asarray(histories, np.float32))


class _CountingRecomputer(M4HistoryRecomputer):
    def __init__(self, prepared, arrival, availability):
        super().__init__(prepared, arrival, availability)
        self.recent_calls = 0
        self.source_calls = 0

    def same_copy_sources(self, target):
        self.source_calls += 1
        return super().same_copy_sources(target)

    def recent_same_copy_sources(self, target, lookback_s):
        self.recent_calls += 1
        return super().recent_same_copy_sources(target, lookback_s)


def _prepared() -> Prepared:
    is_submission = np.array([True, True, True, True, True, True, True, False, True, True])
    rows = np.flatnonzero(is_submission)
    row_of = np.full(len(is_submission), -1, np.int64)
    row_of[rows] = np.arange(len(rows))
    semester = np.array(["s0", "s1", "s1", "s1", "s1", "s1", "s1", "s1", "s1", "s1"])
    class_term = np.array([0, 1, 2, 1, 1, 1, 1, 2, 1, 2], np.int64)
    cost = np.arange(1.0, 11.0)
    prepared = Prepared(
        is_submission=is_submission,
        submission_rows=rows,
        row_of=row_of,
        timestamp_s=np.arange(10.0),
        jitter_u=np.zeros(10),
        cost_s=cost,
        semester=semester,
        exercise=np.zeros(10, np.int64),
        user=np.zeros(10, np.int64),
        class_term=class_term,
        assessment=class_term.copy(),
        n_exercises=1,
        n_classes=3,
        error=(np.arange(10) % 2).astype(float),
        n_testcases=np.arange(1.0, 11.0),
        log_cost=np.log1p(cost),
        heavy_threshold=7.0,
        tercile_cuts=(1.0, 2.0),
        permuted_exercise=np.zeros(10, np.int64),
        permuted_assessment=class_term.copy(),
        heavy=(cost > 7.0).astype(float),
    )
    prepared.simulatable = np.array(
        [True, True, True, True, True, True, False, True, True], bool
    )
    prepared.event_id = np.arange(10, dtype=np.int64)
    return prepared


def _clock():
    arrival = np.array(
        [0.0, 100.0, 300.0, 3500.0, 4500.0, 4800.0, 4900.0, 4700.0, 5000.0, 5200.0]
    )
    availability = np.array(
        [10.0, 200.0, 400.0, 4100.0, 4750.0, 4970.0, 4990.0, 4800.0, 5100.0, 5300.0]
    )
    return arrival, availability


def _target_rows(prepared, base):
    terms = prepared.semester[prepared.submission_rows]
    return np.flatnonzero(np.isfinite(base) & prepared.simulatable & np.isin(terms, ["s1"]))


def _replay_mask(prepared):
    mask = np.zeros(len(prepared.is_submission), bool)
    rows = prepared.submission_rows
    keep = (prepared.semester[rows] == "s1") & prepared.simulatable
    mask[rows[keep]] = True
    return mask


def _lagged_availability(prepared, availability, target, lag_s):
    changed = availability.copy()
    rows = prepared.submission_rows
    event = rows[target]
    source_events = rows[
        (prepared.class_term[rows] == prepared.class_term[event]) & prepared.simulatable
    ]
    changed[source_events] += lag_s
    return changed


def _history(prepared, arrival, availability, record_mask=None):
    return feature_frame(prepared, arrival, availability, record_mask=record_mask)[
        list(HIST_COLS)
    ].to_numpy(np.float32)


def _brute_force_scores(prepared, arrival, availability, frozen, base):
    targets = _target_rows(prepared, base)
    expected = {name: base.copy() for name in CONTROL_VARIANTS}
    scoped = class_term_scoped(prepared)
    replay_mask = _replay_mask(prepared)
    expected["class_term_local"][targets] = frozen.score(
        _history(scoped, arrival, availability)[targets]
    )
    expected["drop_unreplayed"][targets] = frozen.score(
        _history(prepared, arrival, availability, replay_mask)[targets]
    )
    for raw_target in targets:
        target = int(raw_target)
        for lag_s in (60.0, 300.0, 900.0, 3600.0):
            perturbed = _lagged_availability(prepared, availability, target, lag_s)
            history = _history(prepared, arrival, perturbed)[target]
            expected[f"same_copy_lag_{int(lag_s)}"][target] = frozen.score(history)
        event = prepared.submission_rows[target]
        same_semester_other_class = (prepared.semester == prepared.semester[event]) & (
            prepared.class_term != prepared.class_term[event]
        )
        history = _history(
            prepared,
            arrival,
            availability,
            record_mask=~same_semester_other_class,
        )[target]
        expected["other_class_withheld"][target] = frozen.score(history)
        perturbed = _lagged_availability(prepared, availability, target, 3600.0)
        history = _history(scoped, arrival, perturbed, replay_mask)[target]
        expected["combined_frozen"][target] = frozen.score(history)
    return expected


def test_controls_match_brute_force_per_target_sweeps_and_bound_batches():
    prepared = _prepared()
    arrival, availability = _clock()
    baseline = _history(prepared, arrival, availability)
    frozen = _Frozen()
    base = frozen.score(baseline)
    recomputer = _CountingRecomputer(prepared, arrival, availability)
    build = build_control_set(
        prepared=prepared,
        arrival=arrival,
        availability=availability,
        models=frozen,
        baseline_history=baseline,
        recomputer=recomputer,
        base_score=base,
        pool_terms={"s1"},
        batch_size=2,
    )
    expected = _brute_force_scores(prepared, arrival, availability, frozen, base)
    for name in CONTROL_VARIANTS:
        np.testing.assert_allclose(
            build.scores[name], expected[name], equal_nan=True, rtol=0.0, atol=1e-6
        )
    targets = _target_rows(prepared, base)
    assert recomputer.recent_calls == len(targets)
    assert recomputer.source_calls == len(targets)
    assert frozen.max_batch <= 2
    assert set(frozen.predicted) <= set(map(int, targets))
    assert build.costs["combined_frozen"].predicted_rows == len(targets)


def _rolling_case():
    n_sources = 122
    n = n_sources + 1
    rows = np.arange(n, dtype=np.int64)
    class_term = np.ones(n, np.int64)
    class_term[[0, -1]] = 0
    cost = np.arange(1.0, n + 1.0)
    cost[0] = 1000.0
    prepared = Prepared(
        is_submission=np.ones(n, bool),
        submission_rows=rows,
        row_of=rows.copy(),
        timestamp_s=np.arange(n, dtype=float),
        jitter_u=np.zeros(n),
        cost_s=cost,
        semester=np.full(n, "s1", dtype=object),
        exercise=np.zeros(n, np.int64),
        user=np.zeros(n, np.int64),
        class_term=class_term,
        assessment=class_term.copy(),
        n_exercises=1,
        n_classes=2,
        error=(rows % 2).astype(float),
        n_testcases=np.ones(n),
        log_cost=np.log1p(cost),
        heavy_threshold=100.0,
        tercile_cuts=(2.0, 4.0),
        permuted_exercise=np.zeros(n, np.int64),
        permuted_assessment=class_term.copy(),
        heavy=(cost > 100.0).astype(float),
    )
    prepared.simulatable = np.ones(n, bool)
    prepared.event_id = rows.copy()
    arrival = np.r_[np.arange(n_sources, dtype=float), 5000.0]
    availability = np.r_[1000.0, 1100.0 + 25.0 * np.arange(n_sources - 1), 5100.0]
    return prepared, arrival, availability


def test_lag_reorders_retained_results_at_the_rolling_window_boundary():
    prepared, arrival, availability = _rolling_case()
    baseline = _history(prepared, arrival, availability)
    target = len(prepared.submission_rows) - 1
    frozen = _Frozen()
    base = np.full(len(prepared.submission_rows), np.nan)
    base[target] = frozen.score(baseline[target])
    build = build_control_set(
        prepared=prepared,
        arrival=arrival,
        availability=availability,
        models=frozen,
        baseline_history=baseline,
        base_score=base,
        pool_terms={"s1"},
        batch_size=4,
    )
    shifted = availability.copy()
    shifted[0] += 3600.0
    expected = frozen.score(_history(prepared, arrival, shifted)[target])
    actual = build.scores["same_copy_lag_3600"][target]
    np.testing.assert_allclose(actual, expected, rtol=0.0, atol=1e-6)
    assert actual != base[target]


def _write(path: Path, value: str) -> Path:
    path.write_text(value, encoding="utf-8")
    return path


def test_cache_rejects_stale_inputs_and_preserves_the_cost_ledger(tmp_path):
    source = _write(tmp_path / "source.bin", "development events")
    source_extra = _write(tmp_path / "source-extra.bin", "additional events")
    score = _write(tmp_path / "score.bin", "development scores")
    config = _write(tmp_path / "config.yaml", "seed: 1")
    implementation = _write(tmp_path / "implementation.py", "VERSION = 1")
    key = cache_key_from_files(
        [source, source_extra],
        score,
        config,
        ["s1"],
        implementation_paths=[implementation],
    )
    scores = {name: np.arange(3.0) for name in CONTROL_VARIANTS}
    costs = {name: ControlCost(1, 2, 3) for name in CONTROL_VARIANTS}
    cache = tmp_path / "controls.npz"
    save_control_cache(cache, key, ControlBuild(scores, costs, target_rows=3))
    loaded = load_control_cache(cache, key)
    assert loaded is not None and loaded.cache_hit
    assert loaded.costs == costs
    assert all(cost == ControlCost() for cost in loaded.incurred_costs.values())
    _write(source_extra, "changed additional events")
    changed_key = cache_key_from_files(
        [source, source_extra],
        score,
        config,
        ["s1"],
        implementation_paths=[implementation],
    )
    with pytest.raises(StaleControlCacheError, match="different cache key"):
        load_control_cache(cache, changed_key)
