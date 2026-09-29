"""What the repository must be true of before a stranger clones it.

Three properties, all easy to lose by accident and impossible to see by reading a diff.
No file the repository carries may name a path that exists only on this machine: a clone
of it would carry a path its reader never had, and a path under a session temporary
directory is gone the next day.  Every file the protocol lock hashes has to be a file git
can see, or the lock freezes code that no clone contains.  And freezing must refuse a
tree that is not committed, because a frozen lock names a commit.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_generated  # noqa: E402
import freeze_protocol  # noqa: E402
from make_protocol_lock import CODE_GLOBS  # noqa: E402


def _git(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ("git",) + args, cwd=ROOT, input=stdin, capture_output=True, text=True, timeout=60
    )


def _code_files() -> list[str]:
    """Every file the protocol lock would hash, spelled as git spells a path."""
    return sorted(
        str(p.relative_to(ROOT)).replace("\\", "/")
        for glob in CODE_GLOBS
        for p in ROOT.glob(glob)
        if p.is_file()
    )


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


def test_git_can_see_every_file_the_protocol_lock_hashes():
    """A file the lock hashes but git ignores is code that is in no clone.

    That happened: `.gitignore` carried an unanchored `data/`, which matched
    `src/spjf_guard/data/` as well as the data directory, so six modules -- the sealed
    guard among them -- were hashed into the lock, linted by nobody and carried by no
    clone.  An ignored file is invisible to `git status`, so the freeze's own "the tree
    is committed" check cannot see it either; this is the check that can.

    A file that is only untracked is a different state: git reports it, the freeze
    refuses the dirty tree, and a person decides whether it belongs in the repository.
    So the requirement is that git sees the file, tracked or not, never that it is
    already committed -- which would make this check fail on every file being written.
    """
    if _git("rev-parse", "--git-dir").returncode != 0:
        pytest.skip("not a git repository, or git is not available")
    files = _code_files()
    ignored = _git("check-ignore", "--stdin", stdin="\n".join(files))
    if ignored.returncode not in (0, 1):
        pytest.skip(f"git check-ignore is unavailable: {ignored.stderr.strip()}")
    named = [line.strip() for line in ignored.stdout.splitlines() if line.strip()]
    assert named == [], (
        f"{named} would be hashed into the protocol lock but .gitignore hides them; "
        "anchor the rule that matches them, as /data/ is anchored"
    )
    seen = set(_git("ls-files").stdout.splitlines())
    seen |= {
        line[3:].strip('"')
        for line in _git("status", "--porcelain", "--untracked-files=all").stdout.splitlines()
    }
    unseen = [f for f in files if f not in seen]
    assert unseen == [], f"git reports nothing at all about {unseen}"


def test_freezing_refuses_a_tree_that_is_not_committed(tmp_path):
    """The refusal is exercised on a repository of our own, not on this one.

    The live tree is clean exactly when someone is about to freeze, which is when this
    check matters most, so a test that asserts the live tree is dirty is a test that
    fails on the one day it is read.
    """
    monkey = tmp_path / "repo"
    monkey.mkdir()
    for args in (("init", "-q"), ("config", "user.email", "t@t"), ("config", "user.name", "t")):
        subprocess.run(("git",) + args, cwd=monkey, capture_output=True, text=True, timeout=60)
    (monkey / "a.txt").write_text("one\n", encoding="utf-8")

    def state():
        original = freeze_protocol.ROOT
        freeze_protocol.ROOT = monkey
        try:
            return freeze_protocol.commit_state()
        finally:
            freeze_protocol.ROOT = original

    commit, complaints = state()
    assert commit is None and complaints, "a repository with no commit has to be refused"
    subprocess.run(("git", "add", "-A"), cwd=monkey, capture_output=True, timeout=60)
    subprocess.run(("git", "commit", "-qm", "one"), cwd=monkey, capture_output=True, timeout=60)
    commit, complaints = state()
    assert commit and not complaints, "a clean committed tree has to be accepted"
    (monkey / "a.txt").write_text("two\n", encoding="utf-8")
    commit, complaints = state()
    assert commit and complaints, "an uncommitted change has to be refused"


def test_the_gates_the_freeze_script_runs_are_the_ones_we_have():
    names = [name for name, _ in freeze_protocol.GATES]
    assert {"ruff", "mypy", "pytest", "generated artefacts", "paper numbers"} <= set(names)
    for _, command in freeze_protocol.GATES:
        script = next((part for part in command if part.endswith(".py")), None)
        if script:
            assert (ROOT / script).is_file(), f"{script} is named by a gate but is missing"
