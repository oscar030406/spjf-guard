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
    order = source_rows[np.lexsort((source_rows, availability[source_rows], key[source_rows]))]
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


@njit(cache=True)
def _add(bit, base, local, width):
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
