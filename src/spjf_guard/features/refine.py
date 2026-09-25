"""Targeted M4 history recomputation for visibility refinement.

The ordinary feature sweep is the authority for the full design matrix.  This module
rebuilds only the outcome-dependent M4 fields of selected submissions.  Arrival counts
and time-since-arrival fields are copied from that authority because withholding an
outcome does not undo the fact that the record arrived.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import log1p

import numpy as np

from spjf_guard.data.events import Prepared
from spjf_guard.features.sweep import HIST_COLS

_ROLLING = 120
_NAN = float("nan")


@dataclass(frozen=True)
class _GroupedRows:
    rows: np.ndarray
    offsets: np.ndarray
    availability: np.ndarray

    def before(self, key: int, now: float, arrival: np.ndarray) -> np.ndarray:
        """Rows absorbed by the sweep before a target reads at ``now``."""
        if key < 0 or key + 1 >= len(self.offsets):
            return np.empty(0, np.int64)
        group = self.rows[self.offsets[key] : self.offsets[key + 1]]
        times = self.availability[group]
        stop = int(np.searchsorted(times, now, side="right"))
        visible = group[:stop]
        if not len(visible):
            return visible
        zero_at_read = (self.availability[visible] == now) & (arrival[visible] == now)
        return visible[~zero_at_read]


def _grouped(
    keys: np.ndarray, rows: np.ndarray, availability: np.ndarray, arrival: np.ndarray
) -> _GroupedRows:
    if not len(rows):
        return _GroupedRows(rows.copy(), np.zeros(1, np.int64), availability)
    local_keys = keys[rows]
    zero_lag = availability[rows] == arrival[rows]
    order = np.lexsort((rows, zero_lag, availability[rows], local_keys))
    ordered = rows[order].astype(np.int64, copy=False)
    counts = np.bincount(local_keys[order])
    offsets = np.r_[0, np.cumsum(counts, dtype=np.int64)]
    return _GroupedRows(ordered, offsets, availability)


def _latest(rows: np.ndarray, arrival: np.ndarray) -> int:
    """The sweep's last result uses arrival order, not completion order."""
    latest_time = arrival[rows].max()
    return int(rows[arrival[rows] == latest_time].max())


def _by_release(rows: np.ndarray, release: np.ndarray, arrival: np.ndarray) -> np.ndarray:
    """Order records as the sweep absorbs them: release, then zero lag, then row."""
    zero = release == arrival[rows]
    return rows[np.lexsort((rows, zero, release))]


def _summary(values: np.ndarray, errors: np.ndarray, heavy: np.ndarray) -> tuple[float, ...]:
    count = len(values)
    if count == 0:
        return (_NAN,) * 6
    mean = float(np.cumsum(values)[-1] / count)
    sd = float(np.sqrt(max(float(np.cumsum(np.square(values))[-1] / count) - mean * mean, 0.0)))
    ordered = np.sort(values[-_ROLLING:])
    last = len(ordered) - 1
    p50 = float(ordered[min(last, int(0.5 * last + 0.5))])
    p90 = float(ordered[min(last, int(0.9 * last + 0.5))])
    return mean, sd, p50, p90, float(errors.mean()), float(heavy.mean())


def _exercise_summary(
    values: np.ndarray,
    errors: np.ndarray,
    heavy: np.ndarray,
    testcases: np.ndarray,
) -> tuple[float, ...]:
    if not len(values):
        return (_NAN,) * 8
    common = _summary(values, errors, heavy)
    return (
        *common[:4],
        float(np.max(values[-_ROLLING:])),
        *common[4:],
        float(testcases.mean()),
    )


class M4HistoryRecomputer:
    """Indexed original-clock histories used to rebuild selected M4 rows."""

    def __init__(self, prepared: Prepared, arrival: np.ndarray, availability: np.ndarray):
        self.prepared = prepared
        self.arrival = np.asarray(arrival, np.float64)
        self.availability = np.asarray(availability, np.float64)
        self.submission_events = prepared.submission_rows.astype(np.int64)
        self.has_replayed_job = np.zeros(prepared.n_classes, bool)
        copied_events = self.submission_events[prepared.simulatable]
        self.has_replayed_job[prepared.class_term[copied_events]] = True
        self.sub_arrival = self.arrival[self.submission_events]
        self.sub_availability = self.availability[self.submission_events]
        n_sub = len(self.submission_events)
        sub_rows = np.arange(n_sub, dtype=np.int64)
        self.sub_exercise = prepared.exercise[self.submission_events].astype(np.int64)
        self.sub_user = prepared.user[self.submission_events].astype(np.int64)
        pair = self.sub_user * np.int64(prepared.n_exercises) + self.sub_exercise
        pair_values, self.sub_pair = np.unique(pair, return_inverse=True)
        self.pair_values = pair_values
        self.exercise = _grouped(
            self.sub_exercise, sub_rows, self.sub_availability, self.sub_arrival
        )
        self.user = _grouped(self.sub_user, sub_rows, self.sub_availability, self.sub_arrival)
        self.pair = _grouped(self.sub_pair, sub_rows, self.sub_availability, self.sub_arrival)
        event_rows = np.arange(len(self.arrival), dtype=np.int64)
        self.event_user = _grouped(
            prepared.user.astype(np.int64), event_rows, self.availability, self.arrival
        )
        self.arrival_exercise = _grouped(
            self.sub_exercise, sub_rows, self.sub_arrival, self.sub_arrival
        )
        self.arrival_user = _grouped(
            self.sub_user, sub_rows, self.sub_arrival, self.sub_arrival
        )
        self.arrival_pair = _grouped(
            self.sub_pair, sub_rows, self.sub_arrival, self.sub_arrival
        )
        self.arrival_events = _grouped(
            prepared.user.astype(np.int64), event_rows, self.arrival, self.arrival
        )
        self.source_cache: dict[int, np.ndarray] = {}
        self.score_cache: dict[tuple[int, bool, tuple[int, ...]], float] = {}
        self._scoped: tuple[tuple[np.ndarray, _GroupedRows], ...] | None = None

    def _pair_code(self, target: int) -> int:
        value = (
            np.int64(self.sub_user[target]) * np.int64(self.prepared.n_exercises)
            + self.sub_exercise[target]
        )
        code = int(np.searchsorted(self.pair_values, value))
        if code == len(self.pair_values) or self.pair_values[code] != value:
            return -1
        return code

    def _allowed(
        self,
        sub_rows: np.ndarray,
        target: int,
        excluded: set[int],
        result_mask: np.ndarray | None,
        withhold_other_pool_classes: bool,
        pool_terms: set[str],
    ) -> np.ndarray:
        if not len(sub_rows):
            return sub_rows
        keep = np.ones(len(sub_rows), bool)
        events = self.submission_events[sub_rows]
        if result_mask is not None:
            keep &= result_mask[events]
        if excluded:
            blocked = np.fromiter(excluded, dtype=np.int64, count=len(excluded))
            keep &= ~np.isin(sub_rows, blocked)
        if withhold_other_pool_classes:
            prepared = self.prepared
            target_event = self.submission_events[target]
            target_term = str(prepared.semester[target_event])
            if target_term in pool_terms:
                same_term = prepared.semester[events] == target_term
                other_class = prepared.class_term[events] != prepared.class_term[target_event]
                copied = self.has_replayed_job[prepared.class_term[events]]
                keep &= ~(same_term & other_class & copied)
        return sub_rows[keep]

    def _allowed_events(
        self,
        events: np.ndarray,
        target: int,
        excluded: set[int],
        result_mask: np.ndarray | None,
        withhold_other_pool_classes: bool,
        pool_terms: set[str],
    ) -> np.ndarray:
        if not len(events):
            return events
        keep = np.ones(len(events), bool)
        if result_mask is not None:
            keep &= result_mask[events]
        if excluded:
            sub_rows = self.prepared.row_of[events]
            blocked = np.fromiter(excluded, dtype=np.int64, count=len(excluded))
            keep &= (sub_rows < 0) | ~np.isin(sub_rows, blocked)
        if withhold_other_pool_classes:
            prepared = self.prepared
            target_event = self.submission_events[target]
            target_term = str(prepared.semester[target_event])
            if target_term in pool_terms:
                same_term = prepared.semester[events] == target_term
                other_class = prepared.class_term[events] != prepared.class_term[target_event]
                copied = self.has_replayed_job[prepared.class_term[events]]
                keep &= ~(same_term & other_class & copied)
        return events[keep]

    def same_copy_sources(self, target: int) -> np.ndarray:
        """Replayed same-class outcomes read by the original score of ``target``."""
        cached = self.source_cache.get(target)
        if cached is not None:
            return cached
        event = self.submission_events[target]
        now = self.sub_arrival[target]
        exercise = self.exercise.before(int(self.sub_exercise[target]), now, self.sub_arrival)
        user = self.user.before(int(self.sub_user[target]), now, self.sub_arrival)
        candidates = np.union1d(exercise, user)
        source_events = self.submission_events[candidates]
        same_class = self.prepared.class_term[source_events] == self.prepared.class_term[event]
        result = candidates[same_class & self.prepared.simulatable[candidates]]
        # Bound caching independently of how many cells or policies are requested.
        if len(self.source_cache) < 20000:
            self.source_cache[target] = result
        return result

    def lagged_same_copy_sources(self, target: int, lag_s: float) -> np.ndarray:
        """Same-copy sources removed by applying ``lag_s`` only to those sources."""
        sources = self.same_copy_sources(target)
        threshold = self.sub_arrival[target] - float(lag_s)
        return sources[self.sub_availability[sources] > threshold]

    def recent_same_copy_sources(self, target: int, lookback_s: float) -> np.ndarray:
        """A time-bounded candidate superset for detecting replay violations."""
        now = self.sub_arrival[target]
        parts = []
        for grouped, key in (
            (self.exercise, self.sub_exercise[target]),
            (self.user, self.sub_user[target]),
        ):
            group = grouped.rows[grouped.offsets[key] : grouped.offsets[key + 1]]
            times = self.sub_availability[group]
            left = np.searchsorted(times, now - lookback_s, side="left")
            right = np.searchsorted(times, now, side="right")
            parts.append(group[left:right])
        candidates = np.union1d(*parts)
        source_events = self.submission_events[candidates]
        event = self.submission_events[target]
        same_class = self.prepared.class_term[source_events] == self.prepared.class_term[event]
        nonzero_at_read = ~(
            (self.sub_availability[candidates] == now) & (self.sub_arrival[candidates] == now)
        )
        return candidates[same_class & nonzero_at_read & self.prepared.simulatable[candidates]]

    def recompute(
        self,
        target: int,
        baseline: np.ndarray,
        excluded: set[int] | None = None,
        result_mask: np.ndarray | None = None,
        withhold_other_pool_classes: bool = False,
        pool_terms: set[str] | None = None,
        same_copy_lag_s: float = 0.0,
    ) -> np.ndarray:
        """Withhold outcomes; the whole-other-class sensitivity also removes arrivals."""
        excluded = excluded or set()
        pool_terms = pool_terms or set()
        now = self.sub_arrival[target]
        ex_rows = self.exercise.before(int(self.sub_exercise[target]), now, self.sub_arrival)
        user_rows = self.user.before(int(self.sub_user[target]), now, self.sub_arrival)
        pair_rows = self.pair.before(self._pair_code(target), now, self.sub_arrival)
        event_rows = self.event_user.before(int(self.sub_user[target]), now, self.arrival)
        args = (
            target,
            excluded,
            result_mask,
            withhold_other_pool_classes,
            pool_terms,
        )
        ex_rows = self._allowed(ex_rows, *args)
        user_rows = self._allowed(user_rows, *args)
        pair_rows = self._allowed(pair_rows, *args)
        event_rows = self._allowed_events(event_rows, *args)
        if same_copy_lag_s:
            ex_rows = self._released(ex_rows, target, same_copy_lag_s, True)
            user_rows = self._released(user_rows, target, same_copy_lag_s, True)
            pair_rows = self._released(pair_rows, target, same_copy_lag_s, True)
            event_rows = self._released(event_rows, target, same_copy_lag_s, False)
        out = self._outcome_fields(baseline, ex_rows, user_rows, pair_rows, event_rows)
        if withhold_other_pool_classes:
            self._other_class_arrivals(target, out, pool_terms)
        if len(out) != len(HIST_COLS):
            raise AssertionError("the targeted M4 row has the wrong width")
        return out

    def _own_copy(self, events: np.ndarray, target: int) -> np.ndarray:
        """Replayed records of the target's own class-term, in event space."""
        sub_rows = self.prepared.row_of[events]
        replayed = sub_rows >= 0
        replayed[replayed] &= self.prepared.simulatable[sub_rows[replayed]]
        class_term = self.prepared.class_term[self.submission_events[target]]
        return replayed & (self.prepared.class_term[events] == class_term)

    def own_copy_candidates(self, target: int) -> np.ndarray:
        """Own-copy submissions sharing the target's user or exercise, arrived earlier."""
        if self._scoped is None:
            self._scoped = self._scoped_arrival_groups()
        now = self.sub_arrival[target]
        class_term = np.int64(self.prepared.class_term[self.submission_events[target]])
        width = np.int64(max(int(self.prepared.n_exercises), int(self.sub_user.max()) + 1))
        parts = []
        for (keys, grouped), value in zip(
            self._scoped, (self.sub_exercise[target], self.sub_user[target])
        ):
            scoped = class_term * width + np.int64(value)
            key = int(np.searchsorted(keys, scoped))
            if keys[key] != scoped:
                raise AssertionError("an online target is not a replayed submission")
            parts.append(grouped.before(key, now, self.sub_arrival))
        return np.union1d(*parts)

    def _scoped_arrival_groups(self) -> tuple[tuple[np.ndarray, _GroupedRows], ...]:
        """Replayed submissions keyed by (class-term, exercise) and (class-term, user)."""
        rows = np.flatnonzero(self.prepared.simulatable).astype(np.int64)
        class_term = self.prepared.class_term[self.submission_events[rows]].astype(np.int64)
        width = np.int64(max(int(self.prepared.n_exercises), int(self.sub_user.max()) + 1))
        out = []
        for values in (self.sub_exercise, self.sub_user):
            keys, codes = np.unique(class_term * width + values[rows], return_inverse=True)
            full = np.full(len(self.sub_arrival), -1, np.int64)
            full[rows] = codes
            out.append((keys, _grouped(full, rows, self.sub_arrival, self.sub_arrival)))
        return tuple(out)

    def recompute_visible(
        self,
        target: int,
        baseline: np.ndarray,
        own_rows: np.ndarray,
        own_release: np.ndarray,
    ) -> np.ndarray:
        """Rebuild the M4 row when the target's own-copy outcomes are exactly ``own_rows``.

        This is the online replay's reading: an own-copy outcome is visible when it has
        completed in the replay, and it enters the history at its replay release instant
        ``own_release`` (original clock), which orders the rolling windows.  Every other
        record keeps its original availability.  Which outcomes are visible is decided by
        the caller on the replay clock; on the original clock a release can sit a few
        microseconds after ``now`` through quantisation, and it only orders the windows.
        """
        now = self.sub_arrival[target]
        own_rows = np.asarray(own_rows, np.int64)
        own_release = np.asarray(own_release, np.float64)
        pair_code = self._pair_code(target)
        pieces = []
        for grouped, key, keys in (
            (self.exercise, int(self.sub_exercise[target]), self.sub_exercise),
            (self.user, int(self.sub_user[target]), self.sub_user),
            (self.pair, pair_code, self.sub_pair),
        ):
            original = grouped.before(key, now, self.sub_arrival)
            external = original[~self._own_copy(self.submission_events[original], target)]
            mine = keys[own_rows] == key
            pieces.append(
                _by_release(
                    np.r_[external, own_rows[mine]],
                    np.r_[self.sub_availability[external], own_release[mine]],
                    self.sub_arrival,
                )
            )
        events = self.event_user.before(int(self.sub_user[target]), now, self.arrival)
        external = events[~self._own_copy(events, target)]
        mine = self.sub_user[own_rows] == self.sub_user[target]
        event_rows = _by_release(
            np.r_[external, self.submission_events[own_rows[mine]]],
            np.r_[self.availability[external], own_release[mine]],
            self.arrival,
        )
        return self._outcome_fields(baseline, *pieces, event_rows)  # type: ignore[call-arg]

    def _outcome_fields(
        self,
        baseline: np.ndarray,
        ex_rows: np.ndarray,
        user_rows: np.ndarray,
        pair_rows: np.ndarray,
        event_rows: np.ndarray,
    ) -> np.ndarray:
        ex_events = self.submission_events[ex_rows]
        user_events = self.submission_events[user_rows]
        out = np.asarray(baseline, np.float32).copy()
        out[1:9] = _exercise_summary(
            self.prepared.log_cost[ex_events],
            self.prepared.error[ex_events],
            self.prepared.heavy[ex_events],
            self.prepared.n_testcases[ex_events],
        )
        out[10:16] = _summary(
            self.prepared.log_cost[user_events],
            self.prepared.error[user_events],
            self.prepared.heavy[user_events],
        )
        if len(pair_rows):
            pair_event = self.submission_events[_latest(pair_rows, self.sub_arrival)]
            out[17] = self.prepared.log_cost[pair_event]
            out[18] = self.prepared.error[pair_event]
        else:
            out[17:19] = _NAN
        out[20] = (
            self.prepared.error[_latest(event_rows, self.arrival)] if len(event_rows) else _NAN
        )
        return out

    def _released(
        self, rows: np.ndarray, target: int, lag_s: float, submission_space: bool
    ) -> np.ndarray:
        """Reorder retained outcomes by their genuinely shifted release instants."""
        events = self.submission_events[rows] if submission_space else rows
        sub_rows = self.prepared.row_of[events]
        replayed = sub_rows >= 0
        replayed[replayed] &= self.prepared.simulatable[sub_rows[replayed]]
        target_event = self.submission_events[target]
        own_copy = replayed & (
            self.prepared.class_term[events] == self.prepared.class_term[target_event]
        )
        release = self.availability[events].copy()
        release[own_copy] += lag_s
        now = self.sub_arrival[target]
        zero = release == self.arrival[events]
        keep = (release <= now) & ~((release == now) & zero)
        order = np.lexsort((events[keep], zero[keep], release[keep]))
        return rows[keep][order]

    def _other_class_arrivals(self, target: int, out: np.ndarray, pool_terms: set[str]) -> None:
        now = self.sub_arrival[target]
        groups = (
            (self.arrival_exercise, int(self.sub_exercise[target]), 0),
            (self.arrival_user, int(self.sub_user[target]), 9),
            (self.arrival_pair, self._pair_code(target), 16),
        )
        for group, key, column in groups:
            rows = group.before(key, now, self.sub_arrival)
            kept = self._allowed(rows, target, set(), None, True, pool_terms)
            out[column] = len(kept)
            if column == 16:
                out[19] = log1p(now - self.sub_arrival[kept].max()) if len(kept) else _NAN
        events = self.arrival_events.before(int(self.sub_user[target]), now, self.arrival)
        events = self._allowed_events(events, target, set(), None, True, pool_terms)
        out[21] = log1p(now - self.arrival[events].max()) if len(events) else _NAN
