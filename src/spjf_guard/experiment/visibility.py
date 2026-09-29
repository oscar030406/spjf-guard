"""Policy-consistent visibility diagnostics for replayed overlay traces.

The optimistic scores use user and exercise histories from the original calendar.  For
an audit, a history record in a class-term that is present in the pool is matched to the
copy of that record in the same outer overlay round.  Records outside the pool, zero-cost
submissions omitted from replay, and non-submission outcomes have no such counterpart
and are reported separately rather than silently assigned to a copy.

The conservative score does not need this convention: its user and exercise keys are
scoped to one class-term entry, and its fixed lag is checked directly as ``wait <= D``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numba import njit

from spjf_guard.sim.policy import MICROS

_KINDS = ("user", "exercise", "pair")


@dataclass(frozen=True)
class _Layout:
    """Fenwick coordinates and prefix queries for one history key."""

    local: np.ndarray
    offset: np.ndarray
    length: np.ndarray
    query: np.ndarray
    size: int


@dataclass(frozen=True)
class HistoryIndex:
    """Original-calendar histories and their matched-round replay coordinates."""

    user: _Layout
    exercise: _Layout
    pair: _Layout
    mapped_total: np.ndarray
    global_total: np.ndarray
    unreplayed: np.ndarray

    def arrays(self) -> dict[str, np.ndarray]:
        out: dict[str, np.ndarray] = {}
        for name, layout in zip(_KINDS, (self.user, self.exercise, self.pair)):
            out[f"hist_{name}_local"] = layout.local
            out[f"hist_{name}_offset"] = layout.offset
            out[f"hist_{name}_length"] = layout.length
            out[f"hist_{name}_query"] = layout.query
        out["hist_unreplayed"] = self.unreplayed
        out["hist_layout_sizes"] = np.array(
            [self.user.size, self.exercise.size, self.pair.size], np.int64
        )
        return out


@dataclass(frozen=True)
class SameCopyHistoryIndex:
    """Histories whose source and target belong to one class-term copy.

    The older :class:`HistoryIndex` deliberately matches every class-term in an outer
    overlay round.  That convention is useful for reproducing the first exposure audit,
    but it mixes independently shifted class-terms.  This index folds ``class_term``
    into every key, so a replay group can only see records from its own shifted copy.
    """

    user: _Layout
    exercise: _Layout
    pair: _Layout
    class_term: np.ndarray

    def arrays(self) -> dict[str, np.ndarray]:
        out: dict[str, np.ndarray] = {}
        for name, layout in zip(_KINDS, (self.user, self.exercise, self.pair)):
            out[f"same_{name}_local"] = layout.local
            out[f"same_{name}_offset"] = layout.offset
            out[f"same_{name}_length"] = layout.length
            out[f"same_{name}_query"] = layout.query
        out["same_layout_sizes"] = np.array(
            [self.user.size, self.exercise.size, self.pair.size], np.int64
        )
        return out


def _visible_count(sorted_availability, zero_lag_availability, target) -> np.ndarray:
    count = np.searchsorted(sorted_availability, target, side="right")
    if len(zero_lag_availability):
        count -= np.searchsorted(zero_lag_availability, target, side="right") - np.searchsorted(
            zero_lag_availability, target, side="left"
        )
    return count.astype(np.int32)


def _layout(source, key, availability, arrival) -> _Layout:
    """Group-local Fenwick positions and visible-prefix lengths for all target rows."""
    n = len(key)
    local = np.zeros(n, np.int32)
    offset = np.zeros(n, np.int32)
    length = np.zeros(n, np.int32)
    query = np.zeros(n, np.int32)
    source_rows = np.flatnonzero(source)
    zero_lag = availability[source_rows] == arrival[source_rows]
    order = source_rows[
        np.lexsort((source_rows, zero_lag, availability[source_rows], key[source_rows]))
    ]
    if not len(order):
        return _Layout(local, offset, length, query, 0)
    boundaries = np.r_[0, np.flatnonzero(key[order][1:] != key[order][:-1]) + 1, len(order)]
    targets_by_key: dict[int, np.ndarray] = {}
    target_order = np.argsort(key, kind="stable")
    target_boundaries = np.r_[
        0, np.flatnonzero(key[target_order][1:] != key[target_order][:-1]) + 1, n
    ]
    for left, right in zip(target_boundaries[:-1], target_boundaries[1:]):
        rows = target_order[left:right]
        targets_by_key[int(key[rows[0]])] = rows
    cursor = 0
    for left, right in zip(boundaries[:-1], boundaries[1:]):
        rows = order[left:right]
        width = len(rows)
        local[rows] = np.arange(1, width + 1, dtype=np.int32)
        offset[rows] = cursor
        length[rows] = width
        targets = targets_by_key.get(int(key[rows[0]]))
        if targets is not None:
            values = availability[rows]
            zero = values[availability[rows] == arrival[rows]]
            query[targets] = _visible_count(values, np.sort(zero), arrival[targets])
            offset[targets] = cursor
            length[targets] = width
        cursor += width
    return _Layout(local, offset, length, query, cursor)


def _query_only(source, key, availability, arrival) -> np.ndarray:
    return _layout(source, key, availability, arrival).query


def build_history_index(prepared, arrival, availability, pool_terms) -> HistoryIndex:
    """Index the outcome histories used by the original M4 feature set.

    Only submission outcomes enter the user and exercise aggregates measured here.
    ``prev_ev_err`` also reads non-submission outcomes; those records have no job in the
    replay and are called out in the report rather than folded into these counts.
    """
    rows = prepared.submission_rows
    semester = prepared.semester[rows]
    in_pool = np.isin(semester, list(pool_terms))
    mapped_source = in_pool & prepared.simulatable
    all_source = np.ones(len(rows), bool)
    user = prepared.user[rows].astype(np.int64)
    exercise = prepared.exercise[rows].astype(np.int64)
    pair = user * np.int64(prepared.n_exercises) + exercise
    sub_arrival = np.asarray(arrival[rows], np.float64)
    sub_availability = np.asarray(availability[rows], np.float64)
    mapped = [
        _layout(mapped_source, key, sub_availability, sub_arrival)
        for key in (user, exercise, pair)
    ]
    global_query = [
        _query_only(all_source, key, sub_availability, sub_arrival)
        for key in (user, exercise, pair)
    ]
    mapped_total = mapped[0].query + mapped[1].query - mapped[2].query
    global_total = global_query[0] + global_query[1] - global_query[2]
    return HistoryIndex(
        user=mapped[0],
        exercise=mapped[1],
        pair=mapped[2],
        mapped_total=mapped_total,
        global_total=global_total,
        unreplayed=np.maximum(global_total - mapped_total, 0).astype(np.int32),
    )


def build_same_copy_history_index(
    prepared, arrival, availability, pool_terms
) -> SameCopyHistoryIndex:
    """Index replayed submission outcomes within the same class-term.

    A replayed source must be a non-zero-service job in the named pool.  Targets are
    still indexed over every submission row because overlays address them by their
    original submission position.  Class-term is part of each key, which removes the
    independently shifted other-class artefact from this definition.
    """
    rows = prepared.submission_rows
    semester = prepared.semester[rows]
    source = np.isin(semester, list(pool_terms)) & prepared.simulatable
    class_term = prepared.class_term[rows].astype(np.int64)
    user = prepared.user[rows].astype(np.int64)
    exercise = prepared.exercise[rows].astype(np.int64)
    n_user = int(prepared.user.max()) + 1
    scoped_user = class_term * np.int64(n_user) + user
    scoped_exercise = class_term * np.int64(prepared.n_exercises) + exercise
    scoped_pair = scoped_user * np.int64(prepared.n_exercises) + exercise
    sub_arrival = np.asarray(arrival[rows], np.float64)
    sub_availability = np.asarray(availability[rows], np.float64)
    layouts = [
        _layout(source, key, sub_availability, sub_arrival)
        for key in (scoped_user, scoped_exercise, scoped_pair)
    ]
    return SameCopyHistoryIndex(layouts[0], layouts[1], layouts[2], class_term)


@njit(cache=True)
def _add(bit, base, local, width):
    if local <= 0 or width < local:
        raise AssertionError("history source is outside the indexed replay pool")
    position = local
    while position <= width:
        bit[base + position] += 1
        position += position & -position


@njit(cache=True)
def _sum(bit, base, local):
    total = 0
    position = local
    while position > 0:
        total += bit[base + position]
        position -= position & -position
    return total


@njit(cache=True)
def _premature_counts(
    arrival_us,
    service_us,
    wait_us,
    job_row,
    copy_round,
    u_local,
    u_offset,
    u_length,
    u_query,
    e_local,
    e_offset,
    e_length,
    e_query,
    p_local,
    p_offset,
    p_length,
    p_query,
    sizes,
):
    completion = arrival_us + wait_us + service_us
    completion_order = np.argsort(completion)
    rounds = int(copy_round.max()) + 1
    user_bit = np.zeros(rounds * sizes[0] + 1, np.int32)
    exercise_bit = np.zeros(rounds * sizes[1] + 1, np.int32)
    pair_bit = np.zeros(rounds * sizes[2] + 1, np.int32)
    out = np.empty(len(arrival_us), np.int32)
    cursor = 0
    for i in range(len(arrival_us)):
        now = arrival_us[i]
        while cursor < len(completion_order) and completion[completion_order[cursor]] <= now:
            done = completion_order[cursor]
            row = job_row[done]
            round_ = copy_round[done]
            _add(user_bit, round_ * sizes[0] + u_offset[row], u_local[row], u_length[row])
            _add(
                exercise_bit,
                round_ * sizes[1] + e_offset[row],
                e_local[row],
                e_length[row],
            )
            _add(pair_bit, round_ * sizes[2] + p_offset[row], p_local[row], p_length[row])
            cursor += 1
        row = job_row[i]
        round_ = copy_round[i]
        user_done = _sum(user_bit, round_ * sizes[0] + u_offset[row], u_query[row])
        exercise_done = _sum(exercise_bit, round_ * sizes[1] + e_offset[row], e_query[row])
        pair_done = _sum(pair_bit, round_ * sizes[2] + p_offset[row], p_query[row])
        mapped = u_query[row] + e_query[row] - p_query[row]
        out[i] = mapped - (user_done + exercise_done - pair_done)
    return out


def premature_counts(wait_us: np.ndarray, arrays: dict[str, np.ndarray]) -> np.ndarray:
    """Premature matched-round records per replayed job for one policy."""
    return _premature_counts(
        arrays["arrival_us"],
        arrays["service_us"],
        np.asarray(wait_us, np.int64),
        arrays["job_row"],
        arrays["copy_round"],
        arrays["hist_user_local"],
        arrays["hist_user_offset"],
        arrays["hist_user_length"],
        arrays["hist_user_query"],
        arrays["hist_exercise_local"],
        arrays["hist_exercise_offset"],
        arrays["hist_exercise_length"],
        arrays["hist_exercise_query"],
        arrays["hist_pair_local"],
        arrays["hist_pair_offset"],
        arrays["hist_pair_length"],
        arrays["hist_pair_query"],
        arrays["hist_layout_sizes"],
    )


def _copy_groups(copy_entry: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    order = np.argsort(np.asarray(copy_entry, np.int32), kind="stable")
    values = copy_entry[order]
    boundaries = np.r_[0, np.flatnonzero(values[1:] != values[:-1]) + 1, len(order)]
    return order, boundaries


def _check_copy_namespace(arrays: dict[str, np.ndarray], index: SameCopyHistoryIndex) -> None:
    """Prove that (class-term, round) is an injective name for a copy_entry."""
    if "copy_namespace_checked" in arrays:
        return
    order, boundaries = _copy_groups(arrays["copy_entry"])
    arrays["copy_order"], arrays["copy_boundaries"] = order, boundaries
    seen: set[tuple[int, int]] = set()
    for left, right in zip(boundaries[:-1], boundaries[1:]):
        jobs = order[left:right]
        classes = index.class_term[arrays["job_row"][jobs]]
        rounds = arrays["copy_round"][jobs]
        key = (int(classes[0]), int(rounds[0]))
        if np.any(classes != key[0]) or np.any(rounds != key[1]) or key in seen:
            raise AssertionError("class-term/round does not uniquely identify a shifted copy")
        seen.add(key)
    arrays["copy_namespace_checked"] = np.ones(1, bool)


def same_copy_premature_counts(
    wait_us: np.ndarray,
    arrays: dict[str, np.ndarray],
    index: SameCopyHistoryIndex,
) -> np.ndarray:
    """Premature records from the exact same shifted class-term copy per job."""
    if "copy_round" in arrays:
        # Class is already part of all three index keys. A round dimension therefore
        # denotes exactly one independently shifted copy, not other classes in a round.
        _check_copy_namespace(arrays, index)
        local = dict(arrays)
        local.update(
            {key.replace("same_", "hist_", 1): value for key, value in index.arrays().items()}
        )
        return premature_counts(wait_us, local)
    out = np.zeros(len(wait_us), np.int32)
    order, boundaries = _copy_groups(arrays["copy_entry"])
    layout = index.arrays()
    for left, right in zip(boundaries[:-1], boundaries[1:]):
        jobs = order[left:right]
        rows = arrays["job_row"][jobs]
        zeros = np.zeros(len(jobs), np.int32)
        local = {
            "arrival_us": arrays["arrival_us"][jobs],
            "service_us": arrays["service_us"][jobs],
            "job_row": rows,
            "copy_round": zeros,
            "hist_user_local": layout["same_user_local"],
            "hist_user_offset": layout["same_user_offset"],
            "hist_user_length": layout["same_user_length"],
            "hist_user_query": layout["same_user_query"],
            "hist_exercise_local": layout["same_exercise_local"],
            "hist_exercise_offset": layout["same_exercise_offset"],
            "hist_exercise_length": layout["same_exercise_length"],
            "hist_exercise_query": layout["same_exercise_query"],
            "hist_pair_local": layout["same_pair_local"],
            "hist_pair_offset": layout["same_pair_offset"],
            "hist_pair_length": layout["same_pair_length"],
            "hist_pair_query": layout["same_pair_query"],
            "hist_layout_sizes": layout["same_layout_sizes"],
        }
        out[jobs] = _premature_counts(
            local["arrival_us"],
            local["service_us"],
            np.asarray(wait_us[jobs], np.int64),
            local["job_row"],
            local["copy_round"],
            local["hist_user_local"],
            local["hist_user_offset"],
            local["hist_user_length"],
            local["hist_user_query"],
            local["hist_exercise_local"],
            local["hist_exercise_offset"],
            local["hist_exercise_length"],
            local["hist_exercise_query"],
            local["hist_pair_local"],
            local["hist_pair_offset"],
            local["hist_pair_length"],
            local["hist_pair_query"],
            local["hist_layout_sizes"],
        )
    return out


def same_copy_exposure_summary(
    wait_us: np.ndarray,
    arrays: dict[str, np.ndarray],
    index: SameCopyHistoryIndex,
) -> dict:
    """The clean queueing-only exposure definition requested by the follow-up audit."""
    counts = same_copy_premature_counts(wait_us, arrays, index)
    window = np.asarray(arrays["in_window"], bool)
    out = _count_distribution(counts, np.ones(len(counts), bool), "overall")
    out.update(_count_distribution(counts, window, "deadline"))
    return out


def _count_distribution(values: np.ndarray, mask: np.ndarray, prefix: str) -> dict:
    affected = mask & (values > 0)
    selected = values[affected]
    out = {
        f"{prefix}_jobs": int(mask.sum()),
        f"{prefix}_affected_jobs": int(affected.sum()),
        f"{prefix}_affected_share": float(affected.sum() / max(mask.sum(), 1)),
    }
    for name, quantile in (("median", 0.5), ("p90", 0.9), ("p99", 0.99)):
        out[f"{prefix}_premature_{name}"] = (
            float(np.quantile(selected, quantile)) if len(selected) else 0.0
        )
    out[f"{prefix}_premature_mean"] = float(selected.mean()) if len(selected) else 0.0
    out[f"{prefix}_premature_max"] = int(selected.max()) if len(selected) else 0
    return out


def exposure_summary(wait_us: np.ndarray, arrays: dict[str, np.ndarray]) -> dict:
    counts = premature_counts(wait_us, arrays)
    window = np.asarray(arrays["in_window"], bool)
    all_jobs = np.ones(len(counts), bool)
    out = _count_distribution(counts, all_jobs, "overall")
    out.update(_count_distribution(counts, window, "deadline"))
    unreplayed = arrays["hist_unreplayed"][arrays["job_row"]]
    out.update(_count_distribution(unreplayed, all_jobs, "unreplayed_overall"))
    out.update(_count_distribution(unreplayed, window, "unreplayed_deadline"))
    union = (counts > 0) | (unreplayed > 0)
    out["overall_any_exposure_share"] = float(union.mean())
    out["deadline_any_exposure_share"] = float(union[window].mean()) if window.any() else 0.0
    return out


def diagnostics(wait_us: np.ndarray, in_window: np.ndarray, lag_s: float) -> dict:
    """Wait distribution and fixed-lag violations for one policy in one cell."""
    wait_s = np.asarray(wait_us, np.float64) / MICROS
    window = np.asarray(in_window, bool)
    out: dict[str, float | int] = {
        "wait_mean_s": float(wait_s.mean()),
        "wait_p50_s": float(np.quantile(wait_s, 0.50)),
        "wait_p90_s": float(np.quantile(wait_s, 0.90)),
        "wait_p95_s": float(np.quantile(wait_s, 0.95)),
        "wait_p99_s": float(np.quantile(wait_s, 0.99)),
        "wait_p999_s": float(np.quantile(wait_s, 0.999)),
        "wait_max_s": float(wait_s.max()),
    }
    violation = wait_s > lag_s
    out.update(
        {
            "lag_s": lag_s,
            "lag_violations": int(violation.sum()),
            "lag_violation_share": float(violation.mean()),
            "lag_deadline_violations": int((violation & window).sum()),
            "lag_deadline_violation_share": (
                float(violation[window].mean()) if window.any() else 0.0
            ),
            "lag_max_excess_s": float(np.maximum(wait_s - lag_s, 0.0).max()),
        }
    )
    return out
