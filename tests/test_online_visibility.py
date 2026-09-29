"""The online fixed point equals an event-driven replay that scores each job at arrival."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from spjf_guard.experiment.online import build_online_index, refine_policy_online
from spjf_guard.experiment.online_replay import replay_online
from spjf_guard.features.refine import M4HistoryRecomputer
from spjf_guard.features.sweep import HIST_COLS, feature_frame
from spjf_guard.sim import Trace, simulate
from spjf_guard.sim.policy import MICROS, aging, fixed, guard, skip, spjf

CAP_S = 10.0
_P50 = HIST_COLS.index("ex_p50_log")
_MEAN = HIST_COLS.index("u_mean_log")


class _Reader:
    """A frozen predictor that reads an order-sensitive window and a set-level mean."""

    def predict(self, submission_rows, histories):
        histories = np.asarray(histories, np.float64)
        return (
            np.nan_to_num(histories[:, _P50], nan=1.0)
            + np.nan_to_num(histories[:, _MEAN], nan=1.0)
            + 1e-4 * np.asarray(submission_rows, np.float64)
        )


def _case(seed: int, own_span_s: float, n_external: int = 170, n_own: int = 45):
    """Class 0 is replayed on one server; class 1 is external history on its own clock.

    Costs above the cap make the replay release some outcomes earlier than the source
    log did; queueing makes others later.  Exercise 0 carries more than 120 records, so
    its rolling window is order-sensitive.
    """
    rng = np.random.default_rng(seed)
    n = n_external + n_own
    own = np.r_[np.zeros(n_external, bool), np.ones(n_own, bool)]
    arrival = np.r_[
        rng.uniform(0.0, 900.0, n_external), rng.uniform(300.0, 300.0 + own_span_s, n_own)
    ]
    cost = rng.exponential(6.0, n)
    cost[own] = np.where(rng.random(n_own) < 0.25, rng.uniform(12.0, 60.0, n_own), cost[own])
    cost[n_external] = 0.0  # a zero-cost own submission is history but not a replayed job
    order = np.argsort(arrival, kind="stable")
    arrival, cost, own = arrival[order], cost[order], own[order]
    exercise = np.where(rng.random(n) < 0.8, 0, rng.integers(1, 3, n)).astype(np.int64)
    user = np.where(own, rng.integers(0, 4, n), rng.integers(4, 9, n)).astype(np.int64)
    rows = np.arange(n, dtype=np.int64)
    prepared = SimpleNamespace(
        is_submission=np.ones(n, bool),
        submission_rows=rows,
        row_of=rows.copy(),
        exercise=exercise,
        user=user,
        class_term=(~own).astype(np.int64),
        assessment=np.zeros(n, np.int64),
        permuted_exercise=exercise.copy(),
        permuted_assessment=np.zeros(n, np.int64),
        n_exercises=3,
        n_classes=2,
        tercile_cuts=(0.5, 1.5),
        n_testcases=rng.integers(1, 5, n).astype(float),
        log_cost=np.log1p(cost),
        heavy=(cost > 20.0).astype(float),
        error=(rng.random(n) < 0.3).astype(float),
        simulatable=own & (cost > 0.0),
        semester=np.array(["s"] * n, dtype=object),
    )
    availability = arrival + cost
    jobs = np.flatnonzero(prepared.simulatable)
    trace = Trace.from_seconds(arrival[jobs], np.minimum(cost[jobs], CAP_S), limit_s=CAP_S)
    arrays = {
        "arrival_us": trace.arrival_us,
        "service_us": trace.service_us,
        "job_row": jobs,
        "copy_entry": np.zeros(len(jobs), np.int32),
        "copy_round": np.zeros(len(jobs), np.int32),
    }
    return prepared, arrival, availability, trace, arrays


def _history_at(prepared, arrival, availability, row, visible_release):
    """Full causal sweep with own outcomes placed at their replay release, or never."""
    shifted = availability.copy()
    shifted[prepared.simulatable] = 1e12
    for source, release in visible_release.items():
        shifted[source] = release
    return feature_frame(prepared, arrival, shifted)[list(HIST_COLS)].to_numpy()[row]


def _event_driven(prepared, arrival, availability, arrays, model):
    """One server, shortest score first, each score computed once at arrival.

    The toy's one copy has replay and original clocks equal, so an outcome is released
    at its completion instant.
    """
    rows = arrays["job_row"]
    arrival_us, service_us = arrays["arrival_us"], arrays["service_us"]
    n = len(rows)
    completion = np.full(n, np.iinfo(np.int64).max, np.int64)
    scores = np.zeros(n)
    free_at, admitted, queue = 0, 0, []
    while admitted < n or queue:
        if not queue and arrival_us[admitted] > free_at:
            free_at = int(arrival_us[admitted])
        while admitted < n and arrival_us[admitted] <= free_at:
            i = admitted
            visible = {
                int(rows[j]): completion[j] / MICROS
                for j in range(n)
                if completion[j] <= arrival_us[i]
            }
            history = _history_at(prepared, arrival, availability, rows[i], visible)
            scores[i] = model.predict(rows[i : i + 1], history[None, :])[0]
            queue.append(i)
            admitted += 1
        chosen = min(queue, key=lambda j: (scores[j], j))
        queue.remove(chosen)
        completion[chosen] = free_at + service_us[chosen]
        free_at = int(completion[chosen])
    return completion, scores


@pytest.mark.parametrize("seed", [3, 11, 29])
def test_fixed_point_is_the_event_driven_online_replay(seed):
    prepared, arrival, availability, trace, arrays = _case(seed, own_span_s=300.0)
    model = _Reader()
    baseline_history = feature_frame(prepared, arrival, availability)[list(HIST_COLS)].to_numpy(
        np.float32
    )
    baseline_score = model.predict(arrays["job_row"], baseline_history[arrays["job_row"]])
    recomputer = M4HistoryRecomputer(prepared, arrival, availability)
    index = build_online_index(recomputer)
    trace = Trace(trace.arrival_us, trace.service_us, {"online": baseline_score}, CAP_S)
    result = refine_policy_online(
        trace,
        spjf("online"),
        servers=1,
        window=16,
        arrays=arrays,
        index=index,
        recomputer=recomputer,
        models=model,
        baseline_history=baseline_history,
        baseline_score=baseline_score,
        score_key="online",
    )
    expected_completion, expected_score = _event_driven(
        prepared, arrival, availability, arrays, model
    )
    completion = arrays["arrival_us"] + result.outcome.wait_us + arrays["service_us"]
    np.testing.assert_array_equal(completion, expected_completion)
    used = baseline_score.copy()
    used[result.changed_jobs] = result.corrected_score
    np.testing.assert_allclose(used, expected_score, rtol=0.0, atol=1e-6)
    assert result.passes[-1].mismatched_jobs == 0
    assert len(result.changed_jobs) > 0
    frontiers = [p.frontier_s for p in result.passes if p.mismatched_jobs]
    assert all(a < b for a, b in zip(frontiers, frontiers[1:]))


def test_a_replay_on_the_source_clock_has_nothing_to_change():
    prepared, arrival, availability, trace, arrays = _case(5, own_span_s=3000.0)
    uncapped = np.rint((availability - arrival)[arrays["job_row"]] * MICROS).astype(np.int64)
    arrays = {**arrays, "service_us": uncapped}
    model = _Reader()
    baseline_history = feature_frame(prepared, arrival, availability)[list(HIST_COLS)].to_numpy(
        np.float32
    )
    baseline_score = model.predict(arrays["job_row"], baseline_history[arrays["job_row"]])
    recomputer = M4HistoryRecomputer(prepared, arrival, availability)
    trace = Trace(trace.arrival_us, uncapped, {"online": baseline_score}, 1e9)
    result = refine_policy_online(
        trace,
        spjf("online"),
        servers=len(arrays["job_row"]),
        window=16,
        arrays=arrays,
        index=build_online_index(recomputer),
        recomputer=recomputer,
        models=model,
        baseline_history=baseline_history,
        baseline_score=baseline_score,
        score_key="online",
    )
    assert [p.mismatched_jobs for p in result.passes] == [0]


def test_visible_rebuild_with_the_original_outcomes_is_the_original_row():
    prepared, arrival, availability, _, _ = _case(7, own_span_s=300.0)
    baseline = feature_frame(prepared, arrival, availability)[list(HIST_COLS)].to_numpy(
        np.float32
    )
    recomputer = M4HistoryRecomputer(prepared, arrival, availability)
    for row in np.flatnonzero(prepared.simulatable):
        own = recomputer.same_copy_sources(int(row))
        rebuilt = recomputer.recompute_visible(int(row), baseline[row], own, availability[own])
        np.testing.assert_array_equal(rebuilt, recomputer.recompute(int(row), baseline[row]))


def test_visible_rebuild_matches_the_full_sweep_on_a_shifted_clock():
    prepared, arrival, availability, _, _ = _case(13, own_span_s=300.0)
    rng = np.random.default_rng(1)
    shifted = availability.copy()
    replayed = np.flatnonzero(prepared.simulatable)
    shifted[replayed] = arrival[replayed] + rng.uniform(0.5, 40.0, len(replayed))
    swept = feature_frame(prepared, arrival, shifted)[list(HIST_COLS)].to_numpy(np.float32)
    baseline = feature_frame(prepared, arrival, availability)[list(HIST_COLS)].to_numpy(
        np.float32
    )
    recomputer = M4HistoryRecomputer(prepared, arrival, availability)
    for row in replayed:
        candidates = recomputer.own_copy_candidates(int(row))
        done = candidates[shifted[candidates] <= arrival[row]]
        rebuilt = recomputer.recompute_visible(int(row), baseline[row], done, shifted[done])
        np.testing.assert_allclose(rebuilt, swept[row], rtol=0.0, atol=1e-6, equal_nan=True)


def _prepared_case(seed: int, own_span_s: float = 300.0):
    prepared, arrival, availability, trace, arrays = _case(seed, own_span_s=own_span_s)
    model = _Reader()
    history = feature_frame(prepared, arrival, availability)[list(HIST_COLS)].to_numpy(
        np.float32
    )
    baseline = model.predict(arrays["job_row"], history[arrays["job_row"]])
    recomputer = M4HistoryRecomputer(prepared, arrival, availability)
    trace = Trace(trace.arrival_us, trace.service_us, {"online": baseline}, CAP_S)
    return prepared, arrival, availability, trace, arrays, model, history, baseline, recomputer


@pytest.mark.parametrize("seed", [3, 11, 29])
def test_event_driven_replay_is_the_brute_force_online_replay(seed):
    prepared, arrival, availability, trace, arrays, model, history, baseline, recomputer = (
        _prepared_case(seed)
    )
    result = replay_online(
        trace,
        spjf("online"),
        1,
        16,
        arrays,
        build_online_index(recomputer),
        recomputer,
        model,
        history,
        baseline,
    )
    expected_completion, expected_score = _event_driven(
        prepared, arrival, availability, arrays, model
    )
    completion = arrays["arrival_us"] + result.outcome.wait_us + arrays["service_us"]
    np.testing.assert_array_equal(completion, expected_completion)
    used = baseline.copy()
    used[result.changed_jobs] = result.corrected_score
    np.testing.assert_allclose(used, expected_score, rtol=0.0, atol=1e-6)
    assert result.pauses > 0


@pytest.mark.parametrize("seed", [3, 11, 29])
@pytest.mark.parametrize("servers", [1, 2])
def test_event_driven_and_fixed_point_replays_are_identical(seed, servers):
    _, _, _, trace, arrays, model, history, baseline, recomputer = _prepared_case(seed)
    index = build_online_index(recomputer)
    promise = 3.0 * CAP_S
    policies = [
        spjf("online"),
        guard(promise, servers, CAP_S, 2.0 * servers, 0.5, "online", name="Guard"),
        aging("online", 0.01, "Aging"),
    ]
    for policy in policies:
        direct = replay_online(
            trace, policy, servers, 16, arrays, index, recomputer, model, history, baseline
        )
        iterated = refine_policy_online(
            trace,
            policy,
            servers,
            16,
            arrays,
            index,
            recomputer,
            model,
            history,
            baseline,
            "online",
        )
        np.testing.assert_array_equal(direct.outcome.wait_us, iterated.outcome.wait_us)
        np.testing.assert_array_equal(direct.changed_jobs, iterated.changed_jobs)
        np.testing.assert_array_equal(direct.corrected_score, iterated.corrected_score)


class _Unchanged:
    """Returns every job's original score, whatever history it is shown."""

    def __init__(self, baseline, rows):
        self.by_row = dict(zip(map(int, rows), baseline))

    def predict(self, submission_rows, histories):
        return np.array([self.by_row[int(r)] for r in submission_rows])


@pytest.mark.parametrize("servers", [1, 2, 3])
def test_pausing_kernel_schedules_exactly_as_the_package_kernel(servers):
    _, _, _, trace, arrays, _, history, baseline, recomputer = _prepared_case(
        17, own_span_s=120.0
    )
    model = _Unchanged(baseline, arrays["job_row"])
    index = build_online_index(recomputer)
    promise = 3.0 * CAP_S
    policies = [
        spjf("online"),
        guard(promise, servers, CAP_S, 1.0 * servers, 0.25, "online", name="Guard"),
        guard(promise, servers, CAP_S, 0.0, 0.0, "online", name="Queue", gam_s=0.5),
        fixed(promise, servers, CAP_S, "online"),
        skip(promise, servers, CAP_S, "online"),
        aging("online", 0.05, "Aging"),
    ]
    paused = 0
    for policy in policies:
        direct = replay_online(
            trace, policy, servers, 4096, arrays, index, recomputer, model, history, baseline
        )
        package = simulate(trace, policy, servers, window=4096)
        np.testing.assert_array_equal(direct.outcome.wait_us, package.wait_us)
        np.testing.assert_array_equal(direct.outcome.dispatch_index, package.dispatch_index)
        assert direct.outcome.n_forced == package.n_forced
        assert len(direct.changed_jobs) == 0
        paused += direct.pauses
    assert paused > 0


@pytest.mark.parametrize("servers", [1, 2, 3])
def test_pausing_timeout_schedules_exactly_as_the_reference_timeout_kernel(servers):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "prechecks" / "timeout_rule"))
    from timeout_overlays import timeout_kernel

    _, _, _, trace, arrays, _, history, baseline, recomputer = _prepared_case(
        17, own_span_s=120.0
    )
    model = _Unchanged(baseline, arrays["job_row"])
    index = build_online_index(recomputer)
    for theta_s in (0.0, 5.0, 20.0, 1e6):
        direct = replay_online(
            trace,
            spjf("online", "Timeout"),
            servers,
            4096,
            arrays,
            index,
            recomputer,
            model,
            history,
            baseline,
            timeout_s=theta_s,
        )
        reference = timeout_kernel(
            trace.arrival_us,
            trace.service_us,
            baseline,
            servers,
            np.int64(round(theta_s * 1e6)),
        )
        np.testing.assert_array_equal(direct.outcome.wait_us, reference)
