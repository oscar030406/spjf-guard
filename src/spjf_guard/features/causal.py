"""Historical features built under the result-availability rule.

Every statistic a job carries is recomputed from the records whose outcome was readable
at that job's arrival,

    record j may enter x_i  <=>  done_j + delta <= a_i ,

rather than assembled once over the whole term and masked afterwards.  The sweep walks
one merged stream: records become visible in availability order, jobs read in arrival
order, and a record that becomes visible at exactly a job's arrival is read by it.

Two properties follow, and both are tested rather than asserted.  Deleting every record
that completes after a job's arrival leaves that job's features unchanged, and perturbing
the outcome of a record still unfinished at that arrival leaves them unchanged.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = (
    "semester",
    "class",
    "user",
    "assessment",
    "exercise",
    "ts",
    "exec_time",
    "has_error",
)
"""Columns the builder refuses to run without."""

FEATURE_COLUMNS = (
    "ex_n",
    "ex_log_cost_mean",
    "ex_error_rate",
    "user_n",
    "user_log_cost_mean",
    "user_error_rate",
    "prior_n",
    "prior_last_log_cost",
    "prior_seconds_since",
    "hours_to_deadline",
    "hour_of_day",
    "day_of_week",
)

_UNSEEN = -1.0
"""Value a statistic takes when nothing about that key is visible yet."""


class MissingColumnError(KeyError):
    """The event frame does not carry a column the feature builder needs."""


def check_columns(frame: pd.DataFrame) -> None:
    missing = [c for c in REQUIRED_COLUMNS if c not in frame.columns]
    if missing:
        raise MissingColumnError(
            f"the event frame is missing the required column(s) {missing}; "
            f"it has {sorted(frame.columns)}"
        )


def visible_mask(availability_s: np.ndarray, arrival_s: float) -> np.ndarray:
    """Which records are readable at one instant.  The rule, written once."""
    return np.asarray(availability_s, np.float64) <= float(arrival_s)


class _RunningStats:
    """Count, sum of log costs and error count per key, updated in visibility order."""

    def __init__(self, n_keys: int):
        self.count = np.zeros(n_keys, np.float64)
        self.log_cost = np.zeros(n_keys, np.float64)
        self.errors = np.zeros(n_keys, np.float64)

    def add(self, key: int, log_cost: float, error: float) -> None:
        self.count[key] += 1.0
        self.log_cost[key] += log_cost
        self.errors[key] += error

    def read(self, key: int) -> tuple[float, float, float]:
        n = self.count[key]
        if n == 0.0:
            return 0.0, _UNSEEN, _UNSEEN
        return n, self.log_cost[key] / n, self.errors[key] / n


def _context(arrival_s: np.ndarray, deadline_s: np.ndarray | None) -> np.ndarray:
    hour = np.floor(np.mod(arrival_s, 86400.0) / 3600.0)
    day = np.mod(np.floor(arrival_s / 86400.0) + 3.0, 7.0)  # 1970-01-01 was a Thursday
    to_deadline = (
        np.full_like(arrival_s, _UNSEEN)
        if deadline_s is None
        else (np.asarray(deadline_s, np.float64) - arrival_s) / 3600.0
    )
    return np.column_stack([to_deadline, hour, day])


def _sweep(
    order_by_availability,
    availability,
    arrival,
    exercise,
    user,
    pair,
    log_cost,
    error,
    n_exercise,
    n_user,
    n_pair,
):
    """One pass: absorb every record readable at a job's arrival, then read."""
    ex_stats = _RunningStats(n_exercise)
    user_stats = _RunningStats(n_user)
    pair_count = np.zeros(n_pair, np.float64)
    pair_last_cost = np.full(n_pair, _UNSEEN, np.float64)
    pair_last_done = np.full(n_pair, np.nan, np.float64)
    out = np.empty((len(arrival), 9), np.float64)
    cursor = 0
    for i in np.argsort(arrival, kind="stable"):
        limit = arrival[i]
        while cursor < len(order_by_availability):
            j = order_by_availability[cursor]
            if availability[j] > limit:
                break
            ex_stats.add(exercise[j], log_cost[j], error[j])
            user_stats.add(user[j], log_cost[j], error[j])
            pair_count[pair[j]] += 1.0
            pair_last_cost[pair[j]] = log_cost[j]
            pair_last_done[pair[j]] = availability[j]
            cursor += 1
        since = (
            _UNSEEN if np.isnan(pair_last_done[pair[i]]) else limit - pair_last_done[pair[i]]
        )
        out[i] = (
            *ex_stats.read(exercise[i]),
            *user_stats.read(user[i]),
            pair_count[pair[i]],
            pair_last_cost[pair[i]],
            since,
        )
    return out


def build_features(
    frame: pd.DataFrame,
    arrival_s: np.ndarray,
    availability_s: np.ndarray,
    deadline_s: np.ndarray | None = None,
    limit_s: float = 60.0,
) -> pd.DataFrame:
    """Per-record features, every one of them causal.

    `arrival_s` and `availability_s` come from `data.clock`; the builder never derives
    them itself, so a run cannot silently use a different reading from the one the
    configuration pins.
    """
    check_columns(frame)
    n = len(frame)
    if not (len(arrival_s) == len(availability_s) == n):
        raise ValueError("arrival, availability and the frame differ in length")
    exercise, n_exercise = _codes(frame["exercise"])
    user, n_user = _codes(frame["user"])
    pair, n_pair = _codes(frame["user"].astype(str) + "|" + frame["exercise"].astype(str))
    cost = np.minimum(np.nan_to_num(frame["exec_time"].to_numpy(np.float64)), limit_s)
    log_cost = np.log1p(cost)
    error = frame["has_error"].to_numpy(np.float64)
    arrival = np.asarray(arrival_s, np.float64)
    availability = np.asarray(availability_s, np.float64)
    order = np.argsort(availability, kind="stable")
    history = _sweep(
        order,
        availability,
        arrival,
        exercise,
        user,
        pair,
        log_cost,
        error,
        n_exercise,
        n_user,
        n_pair,
    )
    values = np.column_stack([history, _context(arrival, deadline_s)])
    return pd.DataFrame(values, columns=list(FEATURE_COLUMNS), index=frame.index)


def _codes(series: pd.Series) -> tuple[np.ndarray, int]:
    codes, uniques = pd.factorize(series)
    return codes.astype(np.int64), len(uniques)
