"""The result-availability clock, the deterministic jitter, and the cost variable.

Under the reading the field-semantics check settled on, a submission's event header is the
instant its result was written, so

    arrival_i = t_i - C_i        the instant the work reached the platform
    done_j    = t_j              the instant its outcome became readable

and a past record may enter a job's features only when `done_j + delta <= a_i`.  The old
reading, arrival at the header and done at the header plus the cost, is kept as a
sensitivity; the two are never mixed inside one run.

Headers are recorded to whole seconds, so many records share a second.  A deterministic
sub-second jitter, keyed by the record's stable id, breaks those ties the same way in
every run and on every machine.

Executed work is `C_cap = min(C, L)`: the platform stops a run at its time limit, and a
run stopped there contributes exactly L.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

JITTER_KEY = "cbjitter20260919"
"""The fixed key; changing it changes every arrival and is a protocol change."""

JITTER_ID_COLUMNS = ("semester", "class", "user", "assessment", "exercise", "blk_i")
"""The record's stable id: `blk_i` is its position among the blocks of its key."""

READING_RESULT = "result"
READING_SUBMIT = "submit"


def jitter(frame: pd.DataFrame, key: str = JITTER_KEY) -> np.ndarray:
    """u in [0,1) per record, a deterministic function of its id and the key.

    The top 53 bits of a keyed hash of the id columns, times 2^-53.  Independent of the
    row order of `frame`, so a reordering of the input cannot move an arrival.
    """
    missing = [c for c in JITTER_ID_COLUMNS if c != "blk_i" and c not in frame.columns]
    if missing:
        raise KeyError(f"the jitter id needs the column(s) {missing}")
    ident = frame.reindex(columns=[c for c in JITTER_ID_COLUMNS if c != "blk_i"]).astype(str)
    if "blk_i" in frame.columns:
        ident["blk_i"] = frame["blk_i"].to_numpy().astype(np.int64)
    else:
        ident["blk_i"] = (
            ident.groupby(list(ident.columns), sort=False)
            .cumcount()
            .to_numpy()
            .astype(np.int64)
        )
    hashed = pd.util.hash_pandas_object(ident, index=False, hash_key=key).to_numpy()
    return (hashed >> np.uint64(11)).astype(np.float64) * 2.0**-53


def executed_work(cost_s: np.ndarray, limit_s: float) -> np.ndarray:
    """C_cap = min(C, L); a run stopped at the limit contributes exactly L."""
    return np.minimum(np.asarray(cost_s, np.float64), float(limit_s))


@dataclass(frozen=True)
class Clock:
    """One reading of the event header, with its result-availability delay."""

    reading: str = READING_RESULT
    delta_s: float = 0.0
    test_outcome_lag_s: float = 60.0
    jitter_enabled: bool = True
    jitter_key: str = JITTER_KEY

    def header(self, frame: pd.DataFrame, timestamp_s: np.ndarray) -> np.ndarray:
        """The header instant on the jittered clock."""
        if not self.jitter_enabled:
            return np.asarray(timestamp_s, np.float64)
        return np.asarray(timestamp_s, np.float64) + jitter(frame, self.jitter_key)

    def arrival_and_availability(
        self,
        frame: pd.DataFrame,
        timestamp_s: np.ndarray,
        cost_s: np.ndarray,
        is_submission: np.ndarray,
    ):
        """(arrival, availability) for every record, availability including delta.

        A test block carries no execution time: it arrives at its header and its outcome
        becomes readable one lag later.
        """
        header = self.header(frame, timestamp_s)
        cost = np.where(is_submission, np.nan_to_num(np.asarray(cost_s, np.float64)), 0.0)
        if self.reading == READING_RESULT:
            arrival, done = header - cost, header.copy()
        elif self.reading == READING_SUBMIT:
            arrival, done = header.copy(), header + cost
        else:
            raise ValueError(f"unknown header reading {self.reading!r}")
        done = np.where(is_submission, done, header + self.test_outcome_lag_s)
        return arrival, done + self.delta_s


def co_ending_groups(
    semester: np.ndarray, user: np.ndarray, header_second: np.ndarray
) -> np.ndarray:
    """Group id per record, -1 when solo.

    A group is a maximal set of submission blocks of one user in one term sharing a
    header second, of size at least two.  These runs lengthened each other, which is why
    merging or dropping them is a sensitivity rather than the main analysis.
    """
    frame = pd.DataFrame({"semester": semester, "user": user, "second": header_second})
    code = frame.groupby(["semester", "user", "second"], sort=False).ngroup().to_numpy()
    size = np.bincount(code)[code]
    return np.where(size >= 2, code, -1).astype(np.int64)
