"""The feature sweep: one pass over a merged stream, every statistic causal.

The stream is sorted by (time, type, record), with four event types:

    0  a result becomes available, visible to arrivals at the same instant
    1  a submission arrives and READS its features
    2  any record arrives and registers that it exists, after every read at that
       instant, so records arriving together never see each other
    3  a result whose availability equals its own arrival (zero cost, zero delay):
       after the reads, so it is never seen by itself or by its contemporaries

State is keyed by the true ids.  The relational control reads a permuted exercise and
assessment while writing the true ones, which is why permuting both would change
nothing.  Quantiles come from a bounded deque of the last 120 log costs, so the feature
is a rolling quantile and not a whole-term one.
"""

from __future__ import annotations

from collections import deque
from dataclasses import replace
from math import log1p, sqrt

import numpy as np
import pandas as pd

from spjf_guard.data.events import CODE_COLUMNS

HIST_COLS = [
    "ex_n",
    "ex_mean_log",
    "ex_sd_log",
    "ex_p50_log",
    "ex_p90_log",
    "ex_max_log",
    "ex_err_rate",
    "ex_heavy_rate",
    "ex_ntc_mean",
    "u_n",
    "u_mean_log",
    "u_sd_log",
    "u_p50_log",
    "u_p90_log",
    "u_err_rate",
    "u_heavy_rate",
    "ue_n",
    "ue_last_log",
    "ue_last_err",
    "ue_log_sec_since",
    "prev_ev_err",
    "prev_ev_log_sec",
]
REL_COLS = [
    "r_ex_simuser_log",
    "r_ex_simuser_heavy",
    "r_ass_other_log",
    "r_ass_other_heavy",
    "r_ex_sameclass_log",
]
PERM_COLS = [c + "_perm" for c in REL_COLS]
CTX_COLS = [
    "a_is_exam",
    "a_weight",
    "a_nex",
    "hours_to_deadline",
    "hours_since_open",
    "hour",
    "dow",
    "is_remote",
]
AUX_COLS = ["ex_nres", "u_nres"]
FEATURE_COLUMNS = HIST_COLS + REL_COLS + PERM_COLS
DESIGN_COLUMNS = list(CODE_COLUMNS) + CTX_COLS + HIST_COLS + REL_COLS + PERM_COLS

GROUPS = {
    "M1": [c for c in HIST_COLS if c.startswith("ex_")],
    "M2": [c for c in HIST_COLS if c.startswith(("u_", "ue_", "prev_"))],
    "M3": list(CODE_COLUMNS),
    "M4": list(CODE_COLUMNS) + CTX_COLS + HIST_COLS,
    "M5": list(CODE_COLUMNS) + CTX_COLS + HIST_COLS + REL_COLS,
    "M6": list(CODE_COLUMNS) + CTX_COLS + HIST_COLS + PERM_COLS,
    "STATIC": list(CODE_COLUMNS) + CTX_COLS,
}
"""Feature groups.  M4 is the set the scheduling experiment uses."""

_ROLLING = 120
_NAN = float("nan")
_HIST_MISSING_EX = (_NAN,) * 8
_HIST_MISSING_USER = (_NAN,) * 6


def _merged_stream(prepared, arrival, availability, record_mask=None):
    """(type, record) in (time, type, record) order, as one pass of lexsort."""
    n = len(arrival)
    rows = prepared.submission_rows
    n_sub = len(rows)
    records = (
        np.arange(n, dtype=np.int64)
        if record_mask is None
        else np.flatnonzero(np.asarray(record_mask, bool))
    )
    if not np.all(availability >= arrival):
        raise AssertionError("a result became available before its own arrival")
    zero_lag = availability[records] == arrival[records]
    time = np.concatenate([availability[records], arrival[rows], arrival[records]])
    kind = np.concatenate(
        [
            np.where(zero_lag, 3, 0),
            np.ones(n_sub, np.int64),
            np.full(len(records), 2, np.int64),
        ]
    )
    record = np.concatenate([records, rows, records])
    order = np.lexsort((record, kind, time))
    return kind[order].tolist(), record[order].tolist()


def class_term_scoped(prepared):
    """Give each class-term an independent user and exercise namespace.

    An overlay entry is one shifted copy of one class-term.  Scoping the history before
    fitting means that a copied score depends only on records with a unique counterpart
    inside that same entry; independently shifted class-terms cannot supply one another
    with outcomes from the original calendar.
    """
    exercise, exercise_uniques = pd.factorize(
        pd.MultiIndex.from_arrays([prepared.class_term, prepared.exercise])
    )
    user, _ = pd.factorize(pd.MultiIndex.from_arrays([prepared.class_term, prepared.user]))
    scoped_exercise = exercise.astype(np.int64)
    return replace(
        prepared,
        exercise=scoped_exercise,
        user=user.astype(np.int64),
        n_exercises=len(exercise_uniques),
        permuted_exercise=scoped_exercise.copy(),
    )


class _State:
    """Every running aggregate the sweep keeps, keyed by the true ids."""

    __slots__ = (
        "exercise",
        "user",
        "ex_count",
        "user_count",
        "pair_arrival",
        "pair_last",
        "user_last_arrival",
        "user_last_result",
        "assessment",
        "assessment_exercise",
        "exercise_tercile",
        "exercise_class",
    )

    def __init__(self):
        self.exercise: dict = {}
        self.user: dict = {}
        self.ex_count: dict = {}
        self.user_count: dict = {}
        self.pair_arrival: dict = {}
        self.pair_last: dict = {}
        self.user_last_arrival: dict = {}
        self.user_last_result: dict = {}
        self.assessment: dict = {}
        self.assessment_exercise: dict = {}
        self.exercise_tercile: dict = {}
        self.exercise_class: dict = {}


def _quantile(sorted_values, p):
    last = len(sorted_values) - 1
    return sorted_values[min(last, int(p * last + 0.5))]


def _exercise_block(entry):
    if entry is None:
        return _HIST_MISSING_EX, 0
    count, total, total_sq, errors, heavy, testcases, window = entry
    mean = total / count
    ordered = sorted(window)
    return (
        (
            mean,
            sqrt(max(total_sq / count - mean * mean, 0.0)),
            _quantile(ordered, 0.5),
            _quantile(ordered, 0.9),
            ordered[-1],
            errors / count,
            heavy / count,
            testcases / count,
        ),
        count,
    )


def _user_block(entry, low, high):
    if entry is None:
        return _HIST_MISSING_USER, 0, 1
    count, total, total_sq, errors, heavy, window = entry
    mean = total / count
    ordered = sorted(window)
    stats = (
        mean,
        sqrt(max(total_sq / count - mean * mean, 0.0)),
        _quantile(ordered, 0.5),
        _quantile(ordered, 0.9),
        errors / count,
        heavy / count,
    )
    return stats, count, (0 if mean < low else (1 if mean < high else 2))


def _relational(state, exercise_key, assessment_key, class_key, sizes, tercile):
    """The five relational aggregates, read at a possibly permuted exercise/assessment."""
    n_exercises, n_classes = sizes
    entry = state.exercise_tercile.get(exercise_key * 3 + tercile)
    same_user_log, same_user_heavy = (
        (entry[1] / entry[0], entry[2] / entry[0]) if entry is not None else (_NAN, _NAN)
    )
    other_log = other_heavy = _NAN
    assessment = state.assessment.get(assessment_key)
    if assessment is not None:
        pair = state.assessment_exercise.get(assessment_key * n_exercises + exercise_key)
        seen, log_sum, heavy_sum = pair if pair is not None else (0, 0.0, 0.0)
        rest = assessment[0] - seen
        if rest > 0:
            other_log = (assessment[1] - log_sum) / rest
            other_heavy = (assessment[2] - heavy_sum) / rest
    same_class = state.exercise_class.get(exercise_key * n_classes + class_key)
    class_log = same_class[1] / same_class[0] if same_class is not None else _NAN
    return (same_user_log, same_user_heavy, other_log, other_heavy, class_log)


def _read(state, prepared, record, now, sizes, low, high):
    """The features of one submission at its own arrival instant."""
    n_exercises = sizes[0]
    exercise = prepared.exercise[record]
    user = prepared.user[record]
    pair = user * n_exercises + exercise
    ex_stats, ex_results = _exercise_block(state.exercise.get(exercise))
    user_stats, user_results, tercile = _user_block(state.user.get(user), low, high)
    prior = state.pair_arrival.get(pair)
    pair_n = prior[0] if prior is not None else 0
    pair_since = log1p(max(now - prior[1], 0.0)) if prior is not None else _NAN
    last = state.pair_last.get(pair)
    pair_last_log, pair_last_err = (last[2], last[3]) if last is not None else (_NAN, _NAN)
    last_arrival = state.user_last_arrival.get(user)
    prev_since = log1p(max(now - last_arrival, 0.0)) if last_arrival is not None else _NAN
    last_result = state.user_last_result.get(user)
    prev_err = last_result[2] if last_result is not None else _NAN
    history = (
        (state.ex_count.get(exercise, 0),)
        + ex_stats
        + (state.user_count.get(user, 0),)
        + user_stats
        + (pair_n, pair_last_log, pair_last_err, pair_since, prev_err, prev_since)
    )
    class_key = prepared.class_term[record]
    true_side = _relational(
        state, exercise, prepared.assessment[record], class_key, sizes, tercile
    )
    permuted_side = _relational(
        state,
        prepared.permuted_exercise[record],
        prepared.permuted_assessment[record],
        class_key,
        sizes,
        tercile,
    )
    return history, true_side, permuted_side, (ex_results, user_results)


def _register(state, prepared, record, arrival):
    """A record arrives: it exists, but its outcome is not readable yet."""
    user = prepared.user[record]
    state.user_last_arrival[user] = arrival
    if not prepared.is_submission[record]:
        return
    exercise = prepared.exercise[record]
    state.ex_count[exercise] = state.ex_count.get(exercise, 0) + 1
    state.user_count[user] = state.user_count.get(user, 0) + 1
    pair = user * prepared.n_exercises + exercise
    prior = state.pair_arrival.get(pair)
    state.pair_arrival[pair] = ((prior[0] if prior is not None else 0) + 1, arrival)


def _absorb(state, prepared, record, when, sizes):
    """A result becomes readable: every aggregate may now count it."""
    n_exercises, n_classes = sizes
    user = prepared.user[record]
    latest = state.user_last_result.get(user)
    if latest is None or when > latest[0] or (when == latest[0] and record > latest[1]):
        state.user_last_result[user] = (when, record, prepared.error[record])
    if not prepared.is_submission[record]:
        return
    exercise = prepared.exercise[record]
    log_cost = prepared.log_cost[record]
    heavy = prepared.heavy[record]
    error = prepared.error[record]
    entry = state.exercise.get(exercise)
    if entry is None:
        state.exercise[exercise] = [
            1,
            log_cost,
            log_cost * log_cost,
            error,
            heavy,
            prepared.n_testcases[record],
            deque([log_cost], maxlen=_ROLLING),
        ]
    else:
        entry[0] += 1
        entry[1] += log_cost
        entry[2] += log_cost * log_cost
        entry[3] += error
        entry[4] += heavy
        entry[5] += prepared.n_testcases[record]
        entry[6].append(log_cost)
    person = state.user.get(user)
    if person is None:
        person = state.user[user] = [
            1,
            log_cost,
            log_cost * log_cost,
            error,
            heavy,
            deque([log_cost], maxlen=_ROLLING),
        ]
    else:
        person[0] += 1
        person[1] += log_cost
        person[2] += log_cost * log_cost
        person[3] += error
        person[4] += heavy
        person[5].append(log_cost)
    low, high = prepared.tercile_cuts
    mean = person[1] / person[0]
    tercile = 0 if mean < low else (1 if mean < high else 2)
    pair = user * n_exercises + exercise
    last = state.pair_last.get(pair)
    if last is None or when > last[0] or (when == last[0] and record > last[1]):
        state.pair_last[pair] = (when, record, log_cost, error)
    assessment = prepared.assessment[record]
    for table, key in (
        (state.assessment, assessment),
        (state.assessment_exercise, assessment * n_exercises + exercise),
        (state.exercise_tercile, exercise * 3 + tercile),
        (state.exercise_class, exercise * n_classes + prepared.class_term[record]),
    ):
        entry = table.get(key)
        if entry is None:
            table[key] = [1, log_cost, heavy]
        else:
            entry[0] += 1
            entry[1] += log_cost
            entry[2] += heavy


def causal_sweep(
    prepared,
    arrival: np.ndarray,
    availability: np.ndarray,
    record_mask: np.ndarray | None = None,
):
    """(history, relational, permuted relational, available-result counts), in
    submission order."""
    kinds, records = _merged_stream(prepared, arrival, availability, record_mask)
    n_sub = len(prepared.submission_rows)
    sizes = (prepared.n_exercises, prepared.n_classes)
    low, high = prepared.tercile_cuts
    state = _State()
    history = [None] * n_sub
    relational = [None] * n_sub
    permuted = [None] * n_sub
    aux = [None] * n_sub
    arrival_list = arrival.tolist()
    row_of = prepared.row_of.tolist()
    for kind, record in zip(kinds, records):
        if kind == 1:
            row = row_of[record]
            (history[row], relational[row], permuted[row], aux[row]) = _read(
                state, prepared, record, arrival_list[record], sizes, low, high
            )
        elif kind == 2:
            _register(state, prepared, record, arrival_list[record])
        else:
            _absorb(state, prepared, record, arrival_list[record], sizes)
    return (
        np.array(history, np.float32).reshape(n_sub, len(HIST_COLS)),
        np.array(relational, np.float32).reshape(n_sub, len(REL_COLS)),
        np.array(permuted, np.float32).reshape(n_sub, len(REL_COLS)),
        np.array(aux, np.int64).reshape(n_sub, 2),
    )


def feature_frame(prepared, arrival, availability, record_mask=None) -> pd.DataFrame:
    """The sweep's output as the frame the cache stores."""
    history, relational, permuted, aux = causal_sweep(
        prepared, arrival, availability, record_mask
    )
    frame = pd.DataFrame(np.hstack([history, relational, permuted]), columns=FEATURE_COLUMNS)
    frame["ex_nres"], frame["u_nres"] = aux[:, 0], aux[:, 1]
    return frame


def context_block(static: dict, arrival_s: np.ndarray) -> np.ndarray:
    hour = np.floor(np.mod(arrival_s, 86400.0) / 3600.0)
    day = np.mod(np.floor(arrival_s / 86400.0) + 3.0, 7.0)  # 1970-01-01 was a Thursday
    return np.column_stack(
        [
            static["a_is_exam"],
            static["a_weight"],
            static["a_nex"],
            (static["a_end"] - arrival_s) / 3600.0,
            (arrival_s - static["a_start"]) / 3600.0,
            hour,
            day,
            static["is_remote"],
        ]
    ).astype("float32")


def design_matrix(static: dict, features: pd.DataFrame, arrival_s: np.ndarray) -> np.ndarray:
    """The full float32 design matrix in `DESIGN_COLUMNS` order."""
    n_code = len(CODE_COLUMNS)
    out = np.empty((len(arrival_s), len(DESIGN_COLUMNS)), np.float32)
    out[:, :n_code] = static["code"]
    out[:, n_code : n_code + len(CTX_COLS)] = context_block(static, arrival_s)
    out[:, n_code + len(CTX_COLS) :] = features[FEATURE_COLUMNS].to_numpy()
    return out


def static_design_matrix(static: dict, arrival_s: np.ndarray) -> np.ndarray:
    """Code and schedule columns only: no outcome released inside the target window."""
    return np.column_stack([static["code"], context_block(static, arrival_s)]).astype("float32")


def column_index(names) -> list[int]:
    lookup = {c: i for i, c in enumerate(DESIGN_COLUMNS)}
    return [lookup[c] for c in names]
