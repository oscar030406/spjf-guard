"""What the repository must be true of before a stranger clones it.

Two properties, both of which are easy to lose by accident and impossible to see by
reading a diff.  First, no file the repository carries may name a path that exists only
on this machine: a clone of it would carry a path its reader never had, and a path under
a session temporary directory is gone the next day.  Second, freezing the protocol must
refuse a tree that is not committed, because a frozen lock names a commit.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_generated  # noqa: E402
import freeze_protocol  # noqa: E402


def test_no_tracked_file_names_a_path_from_this_machine():
    ok, message = check_generated.check_paths()
    assert ok, message


def test_the_path_check_would_notice_a_machine_path(tmp_path, monkeypatch):
    """The gate has to be able to fail, or it is decoration."""
    planted = tmp_path / "configs"
    planted.mkdir()
    (planted / "main.yaml").write_text(
        "cache_dir: " + "C:/Use" + "rs/someone/cache\n", encoding="utf-8"
    )
    monkeypatch.setattr(check_generated, "ROOT", tmp_path)
    monkeypatch.setattr(check_generated, "SCANNED", ("configs/*.yaml",))
    ok, message = check_generated.check_paths()
    assert not ok and "configs/main.yaml" in message


def test_every_documented_path_exception_still_exists():
    """An exception that outlives the file it excuses is an exception nobody reviews."""
    for relative in check_generated.PATH_EXCEPTIONS:
        assert (ROOT / relative).is_file(), f"{relative} is gone; drop its exception"


def test_freezing_refuses_a_tree_that_is_not_committed():
    """This repository has no commit while the package is being built, which is exactly
    the state the freeze script must refuse."""
    commit, complaints = freeze_protocol.commit_state()
    assert commit is None or complaints, (
        "the tree is committed and clean; the refusal path cannot be exercised here"
    )


def test_the_gates_the_freeze_script_runs_are_the_ones_we_have():
    names = [name for name, _ in freeze_protocol.GATES]
    assert {"ruff", "mypy", "pytest", "generated artefacts", "paper numbers"} <= set(names)
    for _, command in freeze_protocol.GATES:
        script = next((part for part in command if part.endswith(".py")), None)
        if script:
            assert (ROOT / script).is_file(), f"{script} is named by a gate but is missing"
