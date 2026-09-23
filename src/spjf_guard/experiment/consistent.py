"""Violation-driven policy-consistent score refinement.

Scores start from the frozen original-clock predictor.  In one simulated cell, a
same-copy result is withheld from a target whenever that result was used by the score
but completes after the target arrives in the replay.  Withheld sets only grow.  The
policy is resimulated after each batch, and the terminating pass is asserted to contain
zero still-used violations.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from time import perf_counter
from typing import Protocol

import numpy as np
from numba import njit

from spjf_guard.experiment.visibility import (
    SameCopyHistoryIndex,
    same_copy_premature_counts,
)
from spjf_guard.features.refine import M4HistoryRecomputer
from spjf_guard.sim import Trace, simulate
from spjf_guard.sim.policy import MICROS, Policy
from spjf_guard.sim.runner import JobResults


class FrozenPredictor(Protocol):
    def predict(self, submission_rows: np.ndarray, histories: np.ndarray) -> np.ndarray: ...


@dataclass(frozen=True)
class ViolationPass:
    number: int
    affected_jobs: int
    offending_records: int
    cumulative_jobs: int
    cumulative_records: int
    simulation_s: float
    detection_s: float
    rescore_s: float


@dataclass(frozen=True)
class RefinementResult:
    outcome: JobResults
    initial_outcome: JobResults
    initial_jobs: np.ndarray
    initial_score_delta: np.ndarray
    initial_corrected_score: np.ndarray
    initial_withheld_counts: np.ndarray
    passes: list[ViolationPass]
    changed_jobs: np.ndarray
    score_delta: np.ndarray
    withheld_counts: np.ndarray
    corrected_score: np.ndarray


def _groups(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    order = np.argsort(np.asarray(values, np.int32), kind="stable")
    grouped = values[order]
    boundaries = np.r_[0, np.flatnonzero(grouped[1:] != grouped[:-1]) + 1, len(order)]
    return order, boundaries


def _covered_violations(
    completion: np.ndarray,
    arrays: dict[str, np.ndarray],
    n_sources: int,
    withheld: dict[int, set[int]],
) -> np.ndarray:
    """Vectorised count of still-late outcomes already withheld from each target.

    The validated (class, round) namespace gives one source job for each source row in
    a round. Subtracting these edges from the independent Fenwick count lets later
    passes enumerate only newly affected jobs, without weakening the terminal audit.
    """
    if "source_job_lookup" not in arrays:
        rounds = arrays["copy_round"]
        lookup = np.full((int(rounds.max()) + 1) * n_sources, -1, np.int32)
        positions = rounds.astype(np.int64) * n_sources + arrays["job_row"]
        lookup[positions] = np.arange(len(completion), dtype=np.int32)
        arrays["source_job_lookup"] = lookup
    targets = np.fromiter(withheld, np.int64, count=len(withheld))
    counts = np.fromiter(
        (len(rows) for rows in withheld.values()), np.int64, count=len(withheld)
    )
    jobs = np.repeat(targets, counts)
    sources = np.fromiter(
        (row for rows in withheld.values() for row in rows), np.int64, count=int(counts.sum())
    )
    positions = arrays["copy_round"][jobs].astype(np.int64) * n_sources + sources
    replay_sources = arrays["source_job_lookup"][positions]
    if np.any(replay_sources < 0):
        raise AssertionError("a withheld same-copy source has no replayed job")
    late = completion[replay_sources] > arrays["arrival_us"][jobs]
    return np.bincount(jobs, weights=late, minlength=len(completion)).astype(np.int32)


def _new_violations(
    wait_us: np.ndarray,
    arrays: dict[str, np.ndarray],
    history: SameCopyHistoryIndex,
    recomputer: M4HistoryRecomputer,
    withheld: dict[int, set[int]],
) -> tuple[dict[int, set[int]], int]:
    raw = same_copy_premature_counts(wait_us, arrays, history)
    completion = arrays["arrival_us"] + wait_us + arrays["service_us"]
    uncovered = _uncovered_counts(raw, completion, arrays, recomputer, withheld)
    affected = np.flatnonzero(uncovered > 0)
    if not len(affected):
        return {}, 0
    # Quantisation contributes at most a few microseconds to relative original time.
    lookback_s = float(wait_us.max()) / MICROS + 0.00001
    if "copy_order" not in arrays:
        arrays["copy_order"], arrays["copy_boundaries"] = _groups(arrays["copy_entry"])
    order, boundaries = arrays["copy_order"], arrays["copy_boundaries"]
    affected_mask = np.zeros(len(raw), bool)
    affected_mask[affected] = True
    lookup = np.full(len(recomputer.submission_events), -1, np.int64)
    additions: dict[int, set[int]] = {}
    checked = 0
    for left, right in zip(boundaries[:-1], boundaries[1:]):
        jobs = order[left:right]
        targets = jobs[affected_mask[jobs]]
        if not len(targets):
            continue
        source_rows = arrays["job_row"][jobs]
        lookup[source_rows] = jobs
        for target in targets:
            sources = recomputer.recent_same_copy_sources(
                int(arrays["job_row"][target]), lookback_s
            )
            replay_sources = lookup[sources]
            if np.any(replay_sources < 0):
                raise AssertionError("a same-copy history source has no replayed job")
            bad = sources[completion[replay_sources] > arrays["arrival_us"][target]]
            if len(bad) != raw[target]:
                raise AssertionError(
                    f"same-copy count mismatch at job {target}: {len(bad)} != {raw[target]}"
                )
            used = set(int(value) for value in bad) - withheld.get(int(target), set())
            if used:
                additions[int(target)] = used
                checked += len(used)
        lookup[source_rows] = -1
    return additions, checked


def _uncovered_counts(
    raw: np.ndarray,
    completion: np.ndarray,
    arrays: dict[str, np.ndarray],
    recomputer: M4HistoryRecomputer,
    withheld: dict[int, set[int]],
) -> np.ndarray:
    if not withheld or "copy_round" not in arrays:
        return raw
    covered = _covered_violations(
        completion, arrays, len(recomputer.submission_events), withheld
    )
    uncovered = raw - covered
    if np.any(uncovered < 0):
        raise AssertionError("withheld-edge count exceeds independently indexed violations")
    return uncovered


def _updated_histories(
    jobs: np.ndarray,
    job_row: np.ndarray,
    baseline_history: np.ndarray,
    recomputer: M4HistoryRecomputer,
    withheld: dict[int, set[int]],
    withhold_other_pool_classes: bool,
    pool_terms: set[str],
) -> np.ndarray:
    rows = []
    for job in jobs:
        source = int(job_row[job])
        rows.append(
            recomputer.recompute(
                source,
                baseline_history[source],
                excluded=withheld[int(job)],
                withhold_other_pool_classes=withhold_other_pool_classes,
                pool_terms=pool_terms,
            )
        )
    return np.asarray(rows, np.float32)


def _rescore(
    jobs: np.ndarray,
    job_row: np.ndarray,
    baseline_history: np.ndarray,
    recomputer: M4HistoryRecomputer,
    models: FrozenPredictor,
    withheld: dict[int, set[int]],
    withhold_other_pool_classes: bool,
    pool_terms: set[str],
) -> np.ndarray:
    keys = [
        (int(job_row[job]), withhold_other_pool_classes, tuple(sorted(withheld[int(job)])))
        for job in jobs
    ]
    missing: dict[tuple[int, bool, tuple[int, ...]], int] = {}
    for job, key in zip(jobs, keys):
        if key not in recomputer.score_cache:
            missing.setdefault(key, int(job))
    if missing:
        unique_jobs = np.array(list(missing.values()), np.int64)
        histories = _updated_histories(
            unique_jobs,
            job_row,
            baseline_history,
            recomputer,
            withheld,
            withhold_other_pool_classes,
            pool_terms,
        )
        values = models.predict(job_row[unique_jobs], histories)
        recomputer.score_cache.update(zip(missing, map(float, values)))
    out = np.array([recomputer.score_cache[key] for key in keys], np.float64)
    if len(recomputer.score_cache) > 200000:
        recomputer.score_cache.clear()
    return out


def refine_policy(
    trace: Trace,
    policy: Policy,
    servers: int,
    window: int,
    arrays: dict[str, np.ndarray],
    history: SameCopyHistoryIndex,
    recomputer: M4HistoryRecomputer,
    models: FrozenPredictor,
    baseline_history: np.ndarray,
    baseline_score: np.ndarray,
    score_key: str,
    withhold_other_pool_classes: bool = False,
    pool_terms: set[str] | None = None,
) -> RefinementResult:
    """Refine one policy/cell until a full pass finds no still-used violation."""
    pool_terms = pool_terms or set()
    scores = np.asarray(baseline_score, np.float64).copy()
    withheld: dict[int, set[int]] = {}
    passes: list[ViolationPass] = []
    initial_outcome = None
    initial_jobs = np.empty(0, np.int64)
    initial_score_delta = np.empty(0, np.float64)
    initial_corrected_score = np.empty(0, np.float64)
    initial_counts = np.empty(0, np.int32)
    pass_number = 0
    while True:
        pass_number += 1
        started = perf_counter()
        current = Trace(
            trace.arrival_us,
            trace.service_us,
            {score_key: scores},
            trace.limit_s,
        )
        outcome = simulate(current, policy, servers, window=window)
        simulated = perf_counter()
        additions, n_records = _new_violations(
            outcome.wait_us, arrays, history, recomputer, withheld
        )
        detected = perf_counter()
        for job, records in additions.items():
            withheld.setdefault(job, set()).update(records)
        passes.append(
            ViolationPass(
                number=pass_number,
                affected_jobs=len(additions),
                offending_records=n_records,
                cumulative_jobs=len(withheld),
                cumulative_records=sum(len(records) for records in withheld.values()),
                simulation_s=simulated - started,
                detection_s=detected - simulated,
                rescore_s=0.0,
            )
        )
        if not additions:
            assert n_records == 0, "the final refinement pass still has violations"
            print(f"    {policy.name} pass {pass_number}: zero violations", flush=True)
            break
        changed = np.array(sorted(additions), np.int64)
        rescored = _rescore(
            changed,
            arrays["job_row"],
            baseline_history,
            recomputer,
            models,
            withheld,
            withhold_other_pool_classes,
            pool_terms,
        )
        if pass_number == 1:
            initial_outcome = outcome
            initial_jobs = changed.copy()
            initial_score_delta = rescored - baseline_score[changed]
            initial_corrected_score = rescored.copy()
            initial_counts = np.array([len(additions[int(job)]) for job in changed], np.int32)
        scores[changed] = rescored
        passes[-1] = replace(passes[-1], rescore_s=perf_counter() - detected)
        print(
            f"    {policy.name} pass {pass_number}: {len(additions):,} jobs, "
            f"{n_records:,} new records ({perf_counter() - started:.1f} s)",
            flush=True,
        )
    changed = np.array(sorted(withheld), np.int64)
    return RefinementResult(
        outcome=outcome,
        initial_outcome=initial_outcome if initial_outcome is not None else outcome,
        initial_jobs=initial_jobs,
        initial_score_delta=initial_score_delta,
        initial_corrected_score=initial_corrected_score,
        initial_withheld_counts=initial_counts,
        passes=passes,
        changed_jobs=changed,
        score_delta=scores[changed] - baseline_score[changed],
        withheld_counts=np.array([len(withheld[int(job)]) for job in changed], np.int32),
        corrected_score=scores[changed].copy(),
    )


def one_pass_score_changes(
    wait_us: np.ndarray,
    arrays: dict[str, np.ndarray],
    history: SameCopyHistoryIndex,
    recomputer: M4HistoryRecomputer,
    models: FrozenPredictor,
    baseline_history: np.ndarray,
    baseline_score: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Withhold exactly the violations of one fixed replay, without feedback."""
    additions, _ = _new_violations(wait_us, arrays, history, recomputer, {})
    jobs = np.array(sorted(additions), np.int64)
    if not len(jobs):
        return jobs, np.empty(0), np.empty(0, np.int32), np.empty(0)
    rescored = _rescore(
        jobs,
        arrays["job_row"],
        baseline_history,
        recomputer,
        models,
        additions,
        False,
        set(),
    )
    counts = np.array([len(additions[int(job)]) for job in jobs], np.int32)
    return jobs, rescored - baseline_score[jobs], counts, rescored


@njit(cache=True)
def _bit_add(bit, position, delta):
    position += 1
    while position < len(bit):
        bit[position] += delta
        position += position & -position


@njit(cache=True)
def _bit_prefix(bit, stop):
    total = 0
    position = stop
    while position > 0:
        total += bit[position]
        position -= position & -position
    return total


@njit(cache=True)
def _queue_ranks(arrival, start, order, coordinate, new_coordinate, affected):
    n = len(arrival)
    bit = np.zeros(n + 1, np.int32)
    new_bit = np.zeros(n + 1, np.int32)
    old_rank = np.zeros(n, np.int32)
    new_rank = np.zeros(n, np.int32)
    arrival_cursor = 0
    for job in order:
        now = start[job]
        while arrival_cursor < n and arrival[arrival_cursor] <= now:
            _bit_add(bit, coordinate[arrival_cursor], 1)
            _bit_add(new_bit, new_coordinate[arrival_cursor], 1)
            arrival_cursor += 1
        if affected[job]:
            old_rank[job] = _bit_prefix(bit, coordinate[job]) + 1
            new_rank[job] = _bit_prefix(new_bit, new_coordinate[job]) + 1
        _bit_add(bit, coordinate[job], -1)
        _bit_add(new_bit, new_coordinate[job], -1)
    return old_rank, new_rank


def queue_rank_displacement(
    arrival_us: np.ndarray,
    start_us: np.ndarray,
    score: np.ndarray,
    jobs: np.ndarray,
    score_delta: np.ndarray,
    dispatch_order: np.ndarray | None = None,
    *,
    corrected_score: np.ndarray | None = None,
) -> np.ndarray:
    """Signed score-rank movement in the queue just before the dispatch instant.

    Earlier dispatches at the same microsecond have already left the queue.  Score ties
    follow the simulator's smaller-arrival-rank rule. All affected jobs receive their
    one-pass corrected scores simultaneously on the fixed original dispatch queues.
    """
    if corrected_score is not None and len(corrected_score) != len(jobs):
        raise ValueError("absolute corrected scores must align with affected jobs")
    if not len(jobs):
        return np.empty(0, np.int64)
    n = len(score)
    indices = np.arange(n, dtype=np.int64)
    key_order = np.lexsort((indices, score))
    coordinate = np.empty(n, np.int32)
    coordinate[key_order] = np.arange(n, dtype=np.int32)
    corrected = score.copy()
    if corrected_score is None:
        corrected[jobs] += score_delta
    else:
        corrected[jobs] = corrected_score
    new_order = np.lexsort((indices, corrected))
    new_coordinate = np.empty(n, np.int32)
    new_coordinate[new_order] = np.arange(n, dtype=np.int32)
    affected = np.zeros(n, bool)
    affected[jobs] = True
    old_rank, new_rank = _queue_ranks(
        np.asarray(arrival_us, np.int64),
        np.asarray(start_us, np.int64),
        np.argsort(start_us, kind="stable") if dispatch_order is None else dispatch_order,
        coordinate,
        new_coordinate,
        affected,
    )
    return new_rank[jobs].astype(np.int64) - old_rank[jobs]


def distribution(values: np.ndarray, prefix: str, absolute: bool = False) -> dict:
    sample = np.abs(values) if absolute else np.asarray(values)
    if not len(sample):
        return {
            f"{prefix}_mean": 0.0,
            f"{prefix}_p50": 0.0,
            f"{prefix}_p90": 0.0,
            f"{prefix}_p99": 0.0,
            f"{prefix}_max": 0.0,
        }
    return {
        f"{prefix}_mean": float(sample.mean()),
        f"{prefix}_p50": float(np.quantile(sample, 0.50)),
        f"{prefix}_p90": float(np.quantile(sample, 0.90)),
        f"{prefix}_p99": float(np.quantile(sample, 0.99)),
        f"{prefix}_max": float(sample.max()),
    }


def effective_score(policy: Policy, trace: Trace, score: np.ndarray) -> np.ndarray:
    """Static priority key used by the simulator, including Aging's transform."""
    if policy.age_credit_per_s == 0.0:
        return score
    arrival_s = (trace.arrival_us - trace.arrival_us[0]) / MICROS
    return score + policy.age_credit_per_s * arrival_s
