"""The event-cache stage: refusal without data, two caches read as one, and equality
with the existing cache.

Every test but the last works on synthetic frames or on nothing at all.  The last one is
the real comparison and is skipped unless both the per-semester parquet and an existing
`ev.parquet` are on the machine; it is marked `crosscheck` because it is the stage this
package took over from the exploratory scripts, and the only thing that makes the
takeover checkable is that the two agree column by column.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from spjf_guard.data import cache, sealed

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "codebench" / "parquet"
DEVELOPMENT = (
    "2018-1",
    "2018-2",
    "2019-1",
    "2019-2",
    "2020-ERE",
    "2020-1",
    "2020-2",
    "2021-1",
    "2021-2",
    "2022-1",
    "2022-2",
)


def _existing_cache() -> Path | None:
    directory = os.environ.get("SPJF_CACHE_DIR")
    if not directory:
        return None
    path = Path(directory) / "ev.parquet"
    return path if path.is_file() else None


def test_a_sealed_semester_is_refused_before_a_file_is_opened(tmp_path):
    with pytest.raises(sealed.SealedDataError, match="no frozen protocol_lock.json"):
        cache.build_events(
            tmp_path / "absent", ["2022-2", "2023-1"], project_root=tmp_path, unseal=True
        )
    assert not (tmp_path / "absent").exists()


def test_the_file_list_names_three_files_per_semester():
    files = cache.files_for(RAW, ["2018-1", "2018-2"])
    assert len(files) == 6
    assert [p.name for p in files].count("2018-1.parquet") == 3
    assert {p.parent.name for p in files} == {"events", "code_features", "assessments"}


def test_the_join_key_is_the_stable_record_identity():
    """The jitter key hashes the same tuple, so the two must not drift apart."""
    from spjf_guard.data.clock import JITTER_ID_COLUMNS

    assert cache.EVENT_KEY == list(JITTER_ID_COLUMNS)


def test_the_sealed_pool_writes_its_own_cache_file():
    """The one-line version of what the sealed run must never do: overwrite `ev.parquet`.

    It did, once: the development cache went from 67 MB to 13 MB and the next command
    failed inside the heavy threshold, on a training slice that no longer had any rows.
    """
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    from build_cache import cache_file_for
    from spjf_guard import config as cfgmod

    cfg = cfgmod.load(ROOT / "configs" / "main.yaml")
    development = cache_file_for(cfg, "development")
    assert development == cfg["data"]["events_file"]
    assert cache_file_for(cfg, "primary") == development
    assert cache_file_for(cfg, "sealed") != development
    cfg.raw["data"]["sealed_events_file"] = development
    with pytest.raises(SystemExit, match="own file"):
        cache_file_for(cfg, "sealed")


def _synthetic_events(terms, rows_per_term: int = 40, start: int = 1_600_000_000):
    """A minimal event frame: enough columns for the pipeline, nothing meaningful."""
    import numpy as np
    import pandas as pd

    from spjf_guard.data.events import CODE_COLUMNS

    rng = np.random.default_rng(7)
    blocks = []
    for offset, term in enumerate(terms):
        n = rows_per_term
        frame = pd.DataFrame(
            {
                "semester": term,
                "class": "c1",
                "user": [f"u{i % 5}" for i in range(n)],
                "assessment": "a1",
                "exercise": [f"e{i % 7}" for i in range(n)],
                "ts": pd.to_datetime(start + offset * 10_000_000 + np.arange(n) * 60, unit="s"),
                "kind": "submit",
                "exec_time": rng.gamma(1.0, 1.0, n).astype("float32"),
                "has_error": 0.0,
                "n_testcases": 3.0,
                "blk_i": np.arange(n, dtype="int32"),
                "a_type": "exercise",
                "a_weight": 1.0,
                "a_start": pd.to_datetime(start, unit="s"),
                "a_end": pd.to_datetime(start + 86_400, unit="s"),
                "a_nex": 7.0,
                "remote": False,
            }
        )
        for column in CODE_COLUMNS:
            frame[column] = rng.random(n).astype("float32")
        blocks.append(frame)
    return pd.concat(blocks, ignore_index=True)


def test_the_sealed_cache_is_read_beside_the_development_one_and_moves_no_row(tmp_path):
    """Adding the sealed terms must leave every development row where it was.

    The scores are stored by position, so a sealed run that shifted the development rows
    would silently score them against other jobs' costs.  The sealed terms come after
    every development term in time, so reading the two caches as one frame appends them:
    what has to be checked is that it really does, and that what `prepare` derives for a
    development row -- its cost, its heavy flag, its jittered clock -- is what it was.
    """
    import numpy as np

    from spjf_guard.data.events import load_events, prepare

    development = _synthetic_events(["2018-1", "2022-2"])
    sealed_half = _synthetic_events(["2023-1"], start=1_900_000_000)
    development.to_parquet(tmp_path / "ev.parquet", index=False)
    sealed_half.to_parquet(tmp_path / "ev_sealed.parquet", index=False)

    alone = load_events(tmp_path, "ev.parquet")
    together = load_events(tmp_path, "ev.parquet", "ev_sealed.parquet")
    assert len(together) == len(alone) + len(sealed_half)
    assert together.iloc[: len(alone)].reset_index(drop=True).equals(alone)
    assert set(together["semester"][len(alone) :]) == {"2023-1"}

    kwargs = dict(
        seed=3,
        limit_s=60.0,
        train_terms=["2018-1"],
        zero_cost_drop_terms=[],
        jitter_key="cbjitter20260919",
    )
    one, both = prepare(alone, **kwargs), prepare(together, **kwargs)
    keep = len(one.submission_rows)
    assert np.array_equal(one.submission_rows, both.submission_rows[:keep])
    assert one.heavy_threshold == both.heavy_threshold
    for field in ("cost_s", "jitter_u", "timestamp_s", "heavy", "log_cost"):
        first, second = getattr(one, field), getattr(both, field)
        assert np.array_equal(first, second[: len(first)], equal_nan=True), field

    # the design matrix is what the fit sees, so this is the equality that makes the
    # sealed run's scores for a development row the score that run already had
    first, second = _design(alone, one), _design(together, both)
    assert np.array_equal(first, second[:keep], equal_nan=True)


def _design(frame, prepared):
    """The M4 design matrix of one prepared frame, as the forward fit builds it."""
    import numpy as np

    from spjf_guard.data.clock import Clock
    from spjf_guard.data.events import arrival_and_availability, static_submission_columns
    from spjf_guard.features.sweep import GROUPS, column_index, design_matrix, feature_frame

    clock = Clock(
        reading="result",
        delta_s=0.0,
        test_outcome_lag_s=60.0,
        jitter_enabled=True,
        jitter_key="cbjitter20260919",
    )
    arrival, availability = arrival_and_availability(prepared, clock)
    static = static_submission_columns(frame, prepared)
    features = feature_frame(prepared, arrival, availability)
    matrix = design_matrix(static, features, arrival[prepared.submission_rows])
    return np.asarray(matrix[:, column_index(GROUPS["M4"])])


@pytest.mark.crosscheck
@pytest.mark.slow
def test_the_package_rebuilds_the_existing_cache_column_for_column():
    existing = _existing_cache()
    if existing is None or not (RAW / "events").is_dir():
        pytest.skip("the per-semester parquet or the existing cache is not on this machine")
    import pandas as pd

    ours, report = cache.build_events(
        RAW,
        DEVELOPMENT,
        remote_semesters=("2020-ERE", "2020-1", "2020-2", "2021-1", "2021-2"),
        project_root=ROOT,
    )
    rows = cache.compare_frames(ours, pd.read_parquet(existing), DEVELOPMENT)
    differing = [r for r in rows if r["status"] != "equal"]
    assert not differing, differing
    assert report["rows"] == len(ours)
