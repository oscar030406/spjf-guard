"""The event-cache stage: refusal without data, and equality with the existing cache.

The first three tests open no data file at all.  The last one is the real comparison and
is skipped unless both the per-semester parquet and an existing `ev.parquet` are on the
machine; it is marked `crosscheck` because it is the stage this package took over from
the exploratory scripts, and the only thing that makes the takeover checkable is that the
two agree column by column.
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
