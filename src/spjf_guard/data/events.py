"""Reading the parsed event cache and deriving everything a run needs from it.

The cache is the five tables the archive parser produces, already joined: one row per
logged event, with the static code features, the assessment window and the term.  This
module turns that frame into the integer keys, the clock and the labels the feature
sweep and the overlay builder work from.  It never reparses an archive, and it refuses
any term that is not on the configuration's whitelist (see `sealed.py`).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from spjf_guard.data.cache import SORT_COLUMN
from spjf_guard.data.clock import Clock, co_ending_groups, jitter

REQUIRED_EVENT_COLUMNS = (
    "semester",
    "class",
    "user",
    "assessment",
    "exercise",
    "ts",
    "kind",
    "exec_time",
    "has_error",
    "n_testcases",
    "blk_i",
    "a_type",
    "a_weight",
    "a_start",
    "a_end",
    "a_nex",
    "remote",
)

CODE_COLUMNS = (
    "chars",
    "lines",
    "nonblank_lines",
    "max_line_len",
    "n_comment_lines",
    "n_while",
    "n_for",
    "n_input",
    "n_def",
    "n_if",
    "n_print",
    "n_range",
    "n_try",
    "n_class",
    "n_return",
    "n_lambda",
    "n_len",
    "n_append",
    "n_import",
    "imp_math",
    "imp_random",
    "imp_time",
    "imp_sys",
    "imp_os",
    "imp_numpy",
    "imp_itertools",
    "imp_string",
    "imp_other",
    "max_indent",
    "nest_loop_depth",
    "has_while_true",
    "has_recursion",
    "max_num_digits",
    "max_range_digits",
    "has_sleep",
    "has_evalexec",
    "has_open",
)

DUPLICATE_KEY = (
    "semester",
    "class",
    "user",
    "assessment",
    "exercise",
    "ts",
    "exec_time",
    "grade",
    "has_error",
    "error_type",
    "n_testcases",
    "code_len",
    "code_lines",
    *CODE_COLUMNS,
)
"""The closest the kept columns get to a byte-identical resubmission of the same block."""


class MissingEventColumnError(KeyError):
    """The event frame does not carry a column the pipeline needs."""


def _read_cache(path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(
            f"the parsed event cache {path} is missing; build it with the archive "
            "parser and point data.cache_dir at it"
        )
    frame = pd.read_parquet(path)
    check_event_columns(frame)
    return frame


def load_events(
    cache_dir, events_file: str = "ev.parquet", sealed_file: str | None = None
) -> pd.DataFrame:
    """The parsed event cache, with the sealed terms' own cache added when asked for.

    The sealed terms are a second file and never a rewrite of the first.  Every forward
    fit trains on the terms that precede its target, so a sealed run whose cache held the
    sealed terms alone would have nothing to train on at all -- it would not fail at the
    fit either, but at the heavy threshold, on an empty slice of training rows.  Read
    together the two are one frame in one timestamp order, which is what keeps a row's
    position meaning the same thing in a development run and in the sealed one: the
    sealed terms follow every development term in time, so they are appended to the order
    rather than shuffled into it, and no development row moves.
    """
    from pathlib import Path

    frame = _read_cache(Path(cache_dir) / events_file)
    if sealed_file is None:
        return frame
    both = pd.concat([frame, _read_cache(Path(cache_dir) / sealed_file)], ignore_index=True)
    return both.sort_values(SORT_COLUMN, kind="mergesort").reset_index(drop=True)


def check_event_columns(frame: pd.DataFrame) -> None:
    missing = [c for c in REQUIRED_EVENT_COLUMNS + CODE_COLUMNS if c not in frame.columns]
    if missing:
        raise MissingEventColumnError(
            f"the event frame is missing the required column(s) {missing}"
        )


def _seconds(series: pd.Series) -> np.ndarray:
    return (series - pd.Timestamp("1970-01-01")).dt.total_seconds().to_numpy("float64")


@dataclass
class Prepared:
    """Integer keys, the jittered clock and the labels, for one event frame."""

    is_submission: np.ndarray
    submission_rows: np.ndarray  # positions of the submissions inside the frame
    row_of: np.ndarray  # frame position -> submission index, or -1
    timestamp_s: np.ndarray
    jitter_u: np.ndarray
    cost_s: np.ndarray
    semester: np.ndarray
    exercise: np.ndarray
    user: np.ndarray
    class_term: np.ndarray
    assessment: np.ndarray
    n_exercises: int
    n_classes: int
    error: np.ndarray
    n_testcases: np.ndarray
    log_cost: np.ndarray
    heavy_threshold: float
    tercile_cuts: tuple[float, float]
    permuted_exercise: np.ndarray
    permuted_assessment: np.ndarray
    heavy: np.ndarray
    duplicate: np.ndarray = field(default_factory=lambda: np.zeros(0, bool))
    simulatable: np.ndarray = field(default_factory=lambda: np.zeros(0, bool))
    co_ending: np.ndarray = field(default_factory=lambda: np.zeros(0, np.int64))

    def with_cutoffs(self, heavy_threshold: float, cuts: tuple[float, float]) -> Prepared:
        """A copy whose heavy flag and tercile cuts are refit, for a rolling-origin target."""
        from dataclasses import replace

        cost = np.nan_to_num(self.cost_s)
        return replace(
            self,
            heavy_threshold=heavy_threshold,
            tercile_cuts=cuts,
            heavy=(cost > heavy_threshold).astype("float64"),
        )


def _factorise(values) -> tuple[np.ndarray, np.ndarray]:
    codes, uniques = pd.factorize(values)
    return codes.astype(np.int64), np.asarray(uniques)


def _permutation(
    frame: pd.DataFrame,
    assessment_strings,
    exercise_uniques,
    assessment_uniques,
    exercise_code,
    assessment_code,
    seed: int,
):
    """The relational control: read a different exercise's neighbourhood, keep the state
    keyed by the true ids.  Permuting read and write keys together would relabel nothing."""
    rng = np.random.default_rng(seed)
    all_exercises = np.asarray(frame["exercise"].unique(), dtype=object)
    all_assessments = np.unique(assessment_strings).astype(object)
    exercise_map = dict(zip(all_exercises, rng.permutation(all_exercises)))
    assessment_map = dict(zip(all_assessments, rng.permutation(all_assessments)))
    exercise_index = {s: i for i, s in enumerate(exercise_uniques)}
    assessment_index = {s: i for i, s in enumerate(assessment_uniques)}
    permuted_exercise = np.array(
        [exercise_index[exercise_map[s]] for s in exercise_uniques], np.int64
    )
    permuted_assessment = np.array(
        [assessment_index[assessment_map[s]] for s in assessment_uniques], np.int64
    )
    return permuted_exercise[exercise_code], permuted_assessment[assessment_code]


HEAVY_QUANTILE = 0.95
CLASS_CUT_QUANTILES = (1 / 3, 2 / 3)
"""The heavy label's quantile and the class terciles.  `configs/main.yaml` carries the
same values under `features.heavy_quantile` and `features.class_cut_quantiles`, and
`config.load` refuses a file that disagrees, so the lock's hash of the configuration
covers them without the code reading them at run time."""


def heavy_threshold_and_cuts(cost_float32: np.ndarray, limit_s: float):
    """p95 of the executed work, and the terciles of its log, on the given rows."""
    capped = np.minimum(cost_float32, limit_s)
    log_capped = np.log1p(capped)
    low, high = CLASS_CUT_QUANTILES
    return (
        float(np.quantile(capped, HEAVY_QUANTILE)),
        (float(np.quantile(log_capped, low)), float(np.quantile(log_capped, high))),
    )


def prepare(
    frame: pd.DataFrame,
    seed: int,
    limit_s: float,
    train_terms,
    zero_cost_drop_terms,
    jitter_key: str,
) -> Prepared:
    """Integer keys, the jittered clock, the heavy label and the simulation mask."""
    check_event_columns(frame)
    is_submission = (frame["kind"].astype(str).to_numpy() == "submit") & frame[
        "exec_time"
    ].notna().to_numpy()
    rows = np.flatnonzero(is_submission)
    row_of = np.full(len(frame), -1, np.int64)
    row_of[rows] = np.arange(len(rows))
    semester = np.asarray(frame["semester"].astype(str), dtype=object)
    exercise, exercise_uniques = _factorise(frame["exercise"])
    user, _ = _factorise(frame["user"])
    class_string = frame["semester"].astype(str) + "|" + frame["class"].astype(str)
    class_term, _ = _factorise(class_string)
    assessment_strings = (class_string + "|" + frame["assessment"].astype(str)).to_numpy()
    assessment, assessment_uniques = _factorise(assessment_strings)
    cost = frame["exec_time"].to_numpy("float64")
    cost_float32 = frame["exec_time"].to_numpy()  # float32, as the cache stores it
    train = np.isin(semester[rows], list(train_terms))
    threshold, cuts = heavy_threshold_and_cuts(cost_float32[rows][train], limit_s)
    permuted_exercise, permuted_assessment = _permutation(
        frame,
        assessment_strings,
        exercise_uniques,
        assessment_uniques,
        exercise,
        assessment,
        seed,
    )
    prepared = Prepared(
        is_submission=is_submission,
        submission_rows=rows,
        row_of=row_of,
        timestamp_s=frame["ts"].to_numpy("datetime64[s]").astype("int64").astype("float64"),
        jitter_u=jitter(frame, jitter_key),
        cost_s=cost,
        semester=semester,
        exercise=exercise,
        user=user,
        class_term=class_term,
        assessment=assessment,
        n_exercises=int(exercise.max()) + 1,
        n_classes=int(class_term.max()) + 1,
        error=frame["has_error"].to_numpy("float64"),
        n_testcases=frame["n_testcases"].to_numpy("float64"),
        log_cost=np.log1p(np.nan_to_num(cost)),
        heavy_threshold=threshold,
        tercile_cuts=cuts,
        permuted_exercise=permuted_exercise,
        permuted_assessment=permuted_assessment,
        heavy=(np.nan_to_num(cost) > threshold).astype("float64"),
    )
    prepared.duplicate = _duplicate_mask(frame, rows)
    prepared.simulatable = ~(
        (cost[rows] == 0.0) & np.isin(semester[rows], list(zero_cost_drop_terms))
    )
    keep = prepared.simulatable
    groups = co_ending_groups(
        semester[rows][keep], user[rows][keep], prepared.timestamp_s[rows][keep]
    )
    prepared.co_ending = np.full(len(rows), -1, np.int64)
    prepared.co_ending[keep] = groups
    return prepared


def _duplicate_mask(frame: pd.DataFrame, rows: np.ndarray) -> np.ndarray:
    columns = [c for c in DUPLICATE_KEY if c in frame.columns]
    block = frame.iloc[rows][columns].copy()
    if "error_type" in block.columns:
        block["error_type"] = block["error_type"].astype(str)
    out = np.zeros(len(frame), bool)
    out[rows] = block.duplicated(keep="first").to_numpy()
    return out


def static_submission_columns(frame: pd.DataFrame, prepared: Prepared) -> dict:
    """Per-submission columns that do not depend on how the header is read."""
    rows = frame.iloc[prepared.submission_rows]
    return {
        "code": np.column_stack([rows[c].to_numpy("float32") for c in CODE_COLUMNS]),
        "a_is_exam": (rows["a_type"].astype(str).to_numpy() == "exam").astype("float32"),
        "a_weight": pd.to_numeric(rows["a_weight"], errors="coerce").to_numpy("float32"),
        "a_nex": pd.to_numeric(rows["a_nex"], errors="coerce").to_numpy("float32"),
        "is_remote": rows["remote"].to_numpy("float32"),
        "a_end": _seconds(rows["a_end"]),
        "a_start": _seconds(rows["a_start"]),
        "class_term": np.asarray(
            rows["semester"].astype(str) + "|" + rows["class"].astype(str), dtype=object
        ),
        "user": np.asarray(rows["user"].astype(str), dtype=object),
    }


def arrival_and_availability(prepared: Prepared, clock: Clock):
    """(arrival, availability) for every event, on the clock the configuration pins."""
    header = (
        prepared.timestamp_s + prepared.jitter_u
        if clock.jitter_enabled
        else prepared.timestamp_s
    )
    cost = np.where(prepared.is_submission, np.nan_to_num(prepared.cost_s), 0.0)
    if clock.reading == "result":
        arrival, done = header - cost, header.copy()
    elif clock.reading == "submit":
        arrival, done = header.copy(), header + cost
    else:
        raise ValueError(f"unknown header reading {clock.reading!r}")
    done = np.where(prepared.is_submission, done, header + clock.test_outcome_lag_s)
    return arrival, done + clock.delta_s
