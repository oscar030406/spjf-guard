"""Stage zero: the archive parser against the parquet that is already on disk.

The five per-semester tables are the root of everything the paper reports, and until this
pass they were produced outside the package.  The check is the strongest one available
without a second implementation: parse one development semester's archive again, and
compare every column of every table with the parquet the study has been using.  One
semester takes about ten seconds and reads its archive as a stream.

Sealed semesters are never parsed here.  The archive of a sealed term is sealed data, and
the parser refuses it for the same reason every other stage does.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from spjf_guard import config as cfgmod  # noqa: E402
from spjf_guard.data.archive import TABLES, archive_name, semester_of  # noqa: E402

SEMESTER = "2022-1"
"""A development term: its archive and its parquet are both on disk and not sealed."""


@pytest.fixture(scope="module")
def paths():
    cfg = cfgmod.load(ROOT / "configs" / "main.yaml", expand_environment=False)
    archive = cfg.data_path("archive_dir", archive_name(SEMESTER))
    parquet = cfg.data_path("raw_parquet_dir")
    if not archive.is_file():
        pytest.skip(f"{archive.name} is not on this machine")
    if not (parquet / "events" / f"{SEMESTER}.parquet").is_file():
        pytest.skip("the per-semester parquet is not on this machine")
    return archive, parquet


def test_the_archive_name_and_the_semester_tag_are_inverse():
    assert semester_of(archive_name("2022-1")) == "2022-1"
    assert semester_of(archive_name("2020-ERE")) == "2020-ERE"


@pytest.mark.slow
def test_every_column_of_every_table_matches_the_parquet_on_disk(paths):
    from parse_archive import compare_tables
    from spjf_guard.data.archive import parse_archive

    archive, parquet = paths
    tables, stats = parse_archive(archive)
    assert stats["semester"] == SEMESTER
    assert set(tables) == set(TABLES)
    rows = compare_tables(tables, parquet, SEMESTER)
    differing = [r for r in rows if r["status"] != "equal"]
    assert not differing, differing[:5]
    assert len(rows) > 30, "the comparison should cover every column of all five tables"
