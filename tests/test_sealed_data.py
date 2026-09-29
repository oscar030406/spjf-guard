"""The sealed terms cannot be read before the freeze.

None of these tests opens a data file: the refusal has to happen at the path level,
before any read, which is what makes it testable without the sealed data present.
"""

from __future__ import annotations

import json

import pytest

from spjf_guard.data import sealed


def test_the_sealed_terms_are_the_ones_the_plan_names():
    assert sealed.SEALED_SEMESTERS == ("2023-1", "2023-2", "2024-1")
    assert sealed.SEALED_ID_BLOCK == (0.80, 1.00)
    assert sealed.SEALED_OULAD_YEAR == "2014"
    for term in sealed.SEALED_SEMESTERS:
        assert term not in sealed.DEVELOPMENT_SEMESTERS


@pytest.mark.parametrize("term", sealed.SEALED_SEMESTERS)
def test_a_sealed_term_is_refused_without_a_frozen_lock(tmp_path, term):
    with pytest.raises(sealed.SealedDataError, match="no frozen protocol_lock.json"):
        sealed.guard_semesters(["2022-2", term], tmp_path, unseal=True)


@pytest.mark.parametrize("term", sealed.SEALED_SEMESTERS)
def test_a_draft_lock_does_not_release_a_sealed_term(tmp_path, term):
    (tmp_path / "protocol_lock.draft.json").write_text("{}", encoding="utf-8")
    with pytest.raises(sealed.SealedDataError, match="no frozen protocol_lock.json"):
        sealed.guard_semesters([term], tmp_path, unseal=True)


@pytest.mark.parametrize("term", sealed.SEALED_SEMESTERS)
def test_a_frozen_lock_alone_does_not_release_a_sealed_term(tmp_path, term):
    (tmp_path / "protocol_lock.json").write_text(json.dumps({"frozen": True}), encoding="utf-8")
    with pytest.raises(sealed.SealedDataError, match="--unseal flag was not given"):
        sealed.guard_semesters([term], tmp_path, unseal=False)


@pytest.mark.parametrize("term", sealed.SEALED_SEMESTERS)
def test_both_conditions_together_release_a_sealed_term(tmp_path, term):
    _frozen_tree(tmp_path)
    sealed.guard_semesters([term], tmp_path, unseal=True)


def test_development_terms_pass_without_a_lock(tmp_path):
    sealed.guard_semesters(list(sealed.DEVELOPMENT_SEMESTERS), tmp_path, unseal=False)


def test_a_term_outside_the_whitelist_is_refused(tmp_path):
    with pytest.raises(sealed.SealedDataError, match="development whitelist"):
        sealed.guard_semesters(["2017-2"], tmp_path, unseal=False)


def test_the_sealed_accoding_block_is_refused(tmp_path):
    with pytest.raises(sealed.SealedDataError, match="id block"):
        sealed.guard_id_block(0.64, 1.00, tmp_path, unseal=True)
    sealed.guard_id_block(0.00, 0.80, tmp_path, unseal=False)


def test_the_sealed_oulad_year_is_refused(tmp_path):
    with pytest.raises(sealed.SealedDataError, match="OULAD year"):
        sealed.guard_oulad_year("2014", tmp_path, unseal=True)
    sealed.guard_oulad_year("2013", tmp_path, unseal=False)


def test_the_ledger_must_exist_before_a_sealed_read_can_be_recorded(tmp_path):
    with pytest.raises(FileNotFoundError):
        sealed.record_access(tmp_path, "scripts/run_main.py", "x", "y", "z")


def test_the_projects_ledger_is_where_the_protection_expects_it():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    ledger = root / sealed.LOG_RELATIVE_PATH
    assert ledger.is_file(), f"{ledger} is missing"
    header = ledger.read_text(encoding="utf-8").splitlines()
    assert any(line.startswith("| 日期 |") for line in header)


def lock_complaints(root) -> list[str]:
    """Why the protocol lock on disk does not describe this tree; empty means it does.

    One rule, right on both sides of the freeze.  Before it there is no
    `protocol_lock.json`, and what has to hold is that the draft carries the code and the
    configuration as they stand: a draft that lags the tree would freeze a method nobody
    ran.  After it the frozen lock's digests still have to be the tree's, which is the
    freeze's own promise -- nothing under the locked paths moved once the sealed terms
    could be opened -- and the ledger has to carry the row the freeze wrote for each
    sealed input it hashed.

    The input artefacts are left out: they live under `data/`, which is not in the
    repository, so comparing them would make a clone fail a check about the method.  They
    are `scripts/check_generated.py --only protocol_lock`'s business.
    """
    import sys

    sys.path.insert(0, str(root / "scripts"))
    from make_protocol_lock import (
        _digest_of,
        code_manifest,
        config_snapshot_manifest,
        sha256_file,
    )

    lock = sealed.frozen_lock(root)
    path = lock or root / "protocol_lock.draft.json"
    if not path.is_file():
        return [f"{path.name} is missing; write it with scripts/make_protocol_lock.py"]
    document = json.loads(path.read_text(encoding="utf-8"))
    out = []
    tree = code_manifest(root)
    if lock is None and document["code"]["digest"] != _digest_of(tree):
        out.append(f"{path.name} does not describe the code in src/, scripts/ and tests/")
    if lock is not None:
        undeclared = _undeclared_changes(root, document["code"]["files"], tree)
        if undeclared:
            out.append(
                "a locked file has changed since the freeze without a matching entry in "
                f"{POST_RUN_CHANGES}: " + ", ".join(undeclared)
            )
    if document["config"]["sha256"] != sha256_file(root / "configs" / "main.yaml"):
        out.append(f"{path.name} was written for another configs/main.yaml")
    if document.get("config_snapshots") != config_snapshot_manifest(root):
        out.append(f"{path.name} was written for other archived configurations")
    if lock is None:
        return out + ([] if document["status"] == "draft" else ["the draft says frozen"])
    if not document.get("commit"):
        out.append("a frozen lock names the commit it froze")
    ledger = (root / sealed.LOG_RELATIVE_PATH).read_text(encoding="utf-8")
    rows = [r for r in ledger.splitlines() if "scripts/freeze_protocol.py" in r]
    # A second freeze writes the same rows again, so the rule is that every hashed input
    # has a row, not that the two counts match.
    if any(
        not any(entry["path"] in row for row in rows)
        for entry in document.get("sealed_input_hashes", [])
    ):
        out.append("the ledger has no row for every sealed input the freeze hashed")
    return out


POST_RUN_CHANGES = "docs/post_run_changes.json"
"""Locked files changed after the sealed run finished, each with the bytes it now has and
why.  A change that is not listed, or whose file no longer has the listed bytes, still
breaks the lock: the declaration pins the new bytes as the freeze pinned the old ones."""


def _undeclared_changes(root, locked: list[dict], tree: list[dict]) -> list[str]:
    """Locked source files whose bytes differ from the lock and from the declaration."""
    before = {entry["path"]: entry["sha256"] for entry in locked}
    now = {entry["path"]: entry["sha256"] for entry in tree}
    declaration = root / POST_RUN_CHANGES
    declared = (
        {
            entry["path"]: entry["sha256"]
            for entry in json.loads(declaration.read_text(encoding="utf-8"))["files"]
        }
        if declaration.is_file()
        else {}
    )
    changed = sorted(p for p in before.keys() | now.keys() if before.get(p) != now.get(p))
    return [p for p in changed if declared.get(p) != now.get(p)]


def test_the_protocol_lock_describes_the_tree_it_belongs_to():
    """The draft before the freeze, the frozen lock after it: one check, both states."""
    from pathlib import Path

    assert lock_complaints(Path(__file__).resolve().parents[1]) == []


def _frozen_tree(tmp_path, inputs: int = 2):
    """A miniature repository that has been frozen: lock, configuration, ledger."""
    import hashlib

    (tmp_path / "configs").mkdir()
    (tmp_path / "configs" / "main.yaml").write_text("name: tiny\n", encoding="utf-8")
    empty = hashlib.sha256().hexdigest()
    config = hashlib.sha256((tmp_path / "configs" / "main.yaml").read_bytes()).hexdigest()
    (tmp_path / "protocol_lock.json").write_text(
        json.dumps(
            {
                "status": "frozen",
                "commit": "0" * 40,
                "code": {"files": [], "digest": empty},
                "config": {"path": "configs/main.yaml", "sha256": config},
                "config_snapshots": [
                    {"path": str(path).replace("\\", "/"), "present": False, "sha256": None}
                    for path in sealed.CONFIG_SNAPSHOT_PATHS
                ],
                "sealed_input_hashes": [
                    {
                        "path": f"data/{i}.parquet",
                        "sha256": f"{i:064x}",
                        "bytes": i,
                    }
                    for i in range(inputs)
                ],
            }
        ),
        encoding="utf-8",
    )
    ledger = _ledger(tmp_path)
    for i in range(inputs):
        sealed.record_access(
            tmp_path,
            "scripts/freeze_protocol.py",
            "封存学期",
            f"只读取字节求 sha256：data/{i}.parquet",
            "冻结脚本",
        )
    return ledger


def test_a_frozen_lock_that_still_describes_its_tree_passes(tmp_path):
    _frozen_tree(tmp_path)
    assert lock_complaints(tmp_path) == []


def test_a_locked_file_that_changed_after_the_freeze_is_caught(tmp_path):
    _frozen_tree(tmp_path)
    (tmp_path / "scripts").mkdir(exist_ok=True)
    (tmp_path / "scripts" / "afterwards.py").write_text("x = 1\n", encoding="utf-8")
    assert any("changed since the freeze" in c for c in lock_complaints(tmp_path))


def _declare(root, relative: str, reason: str = "reporting fix after the sealed run") -> None:
    import hashlib

    digest = hashlib.sha256((root / relative).read_bytes()).hexdigest()
    (root / "docs").mkdir(exist_ok=True)
    (root / POST_RUN_CHANGES).write_text(
        json.dumps({"files": [{"path": relative, "sha256": digest, "why": reason}]}),
        encoding="utf-8",
    )


def test_a_change_declared_with_its_bytes_after_the_run_passes(tmp_path):
    _frozen_tree(tmp_path)
    (tmp_path / "scripts").mkdir(exist_ok=True)
    (tmp_path / "scripts" / "afterwards.py").write_text("x = 1\n", encoding="utf-8")
    _declare(tmp_path, "scripts/afterwards.py")
    assert lock_complaints(tmp_path) == []


def test_a_declared_file_edited_again_is_caught(tmp_path):
    _frozen_tree(tmp_path)
    (tmp_path / "scripts").mkdir(exist_ok=True)
    changed = tmp_path / "scripts" / "afterwards.py"
    changed.write_text("x = 1\n", encoding="utf-8")
    _declare(tmp_path, "scripts/afterwards.py")
    changed.write_text("x = 2\n", encoding="utf-8")
    assert any("scripts/afterwards.py" in c for c in lock_complaints(tmp_path))


def test_a_second_freeze_that_wrote_its_rows_again_still_has_a_row_per_input(tmp_path):
    _frozen_tree(tmp_path)
    for i in range(2):
        sealed.record_access(
            tmp_path,
            "scripts/freeze_protocol.py",
            "封存学期",
            f"只读取字节求 sha256：data/{i}.parquet",
            "冻结脚本",
        )
    assert lock_complaints(tmp_path) == []


def test_a_freeze_the_ledger_does_not_record_is_caught(tmp_path):
    _frozen_tree(tmp_path, inputs=1)
    assert lock_complaints(tmp_path) == []
    path = tmp_path / "protocol_lock.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["sealed_input_hashes"].append(
        {"path": "data/extra.parquet", "sha256": "f" * 64, "bytes": 1}
    )
    path.write_text(json.dumps(document), encoding="utf-8")
    assert any("ledger" in c for c in lock_complaints(tmp_path))


def refusal_for(root) -> tuple[list[str], str]:
    """The refusal a sealed pool must produce, in whichever state the repository is in.

    Entry-point tests never supply the release flag. Before freezing, the missing lock
    is the first refusal; afterwards, the absent flag is the remaining refusal. The
    lock-plus-flag combinations are tested separately with synthetic temporary roots.
    """
    if sealed.frozen_lock(root) is None:
        return [], "no frozen protocol_lock.json"
    return [], "the --unseal flag was not given"


@pytest.mark.parametrize(
    "entrypoint", ["run_main.py", "run_visibility.py", "run_consistent_visibility.py"]
)
def test_the_run_script_refuses_a_sealed_pool_it_may_not_open(
    tmp_path, monkeypatch, entrypoint
):
    """The protection is wired into the entry point, not only into the module."""
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    flags, message = refusal_for(root)
    monkeypatch.setenv("SPJF_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("SPJF_SCORE_PRED", str(tmp_path / "pred.parquet"))
    result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / entrypoint),
            "--pool",
            "sealed",
            "--overlay-dir",
            str(tmp_path),
            "--reps",
            "0",
            "--levels",
            "0",
            *flags,
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=root,
    )
    assert result.returncode != 0
    assert "SealedDataError" in result.stderr
    assert message in result.stderr


def test_the_dry_run_prints_the_plan_and_opens_nothing(tmp_path, monkeypatch):
    """`--dry-run-sealed` is the rehearsal: it names every file and reads none of them.

    The overlay directory it is given does not exist and the ledger is compared byte for
    byte before and after, so a read or an append would show up here.
    """
    import hashlib
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    ledger = root / sealed.LOG_RELATIVE_PATH
    before = hashlib.sha256(ledger.read_bytes()).hexdigest() if ledger.is_file() else None
    monkeypatch.setenv("SPJF_CACHE_DIR", str(tmp_path / "absent_cache"))
    monkeypatch.setenv("SPJF_SCORE_PRED", str(tmp_path / "absent_pred.parquet"))
    result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "run_main.py"),
            "--config",
            str(root / "configs" / "main.yaml"),
            "--overlay-dir",
            str(tmp_path / "absent_overlays"),
            "--dry-run-sealed",
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=root,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    out = result.stdout
    for term in sealed.SEALED_SEMESTERS:
        assert term in out
    assert "would read" in out
    assert "sealed_rep0.npz" in out
    assert "[5 visibility" in out
    assert "[6 exact" in out
    assert "[7 online" in out
    assert "[10 predictor" in out
    assert "visibility_waits_and_lag.csv" in out
    assert str(sealed.LOG_RELATIVE_PATH) in out.replace("/", "\\")
    assert ("NOT FROZEN" in out) == (not (root / "protocol_lock.json").is_file())
    assert not (tmp_path / "absent_overlays").exists()
    after = hashlib.sha256(ledger.read_bytes()).hexdigest() if ledger.is_file() else None
    assert after == before


def _ledger(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    header = "| 日期 | 脚本 | 读取内容 | 输出 | 谁看过 | 是否影响设计 |"
    (docs / "sealed_access_log.md").write_text(
        header + "\n|---|---|---|---|---|---|\n", encoding="utf-8"
    )
    return docs / "sealed_access_log.md"


def test_a_development_run_writes_no_ledger_row(tmp_path):
    ledger = _ledger(tmp_path)
    before = ledger.read_text(encoding="utf-8")
    assert (
        sealed.record_run(tmp_path, "scripts/run_main.py", ["2022-2"], "tables", True) is None
    )
    assert (
        sealed.record_run(tmp_path, "scripts/run_main.py", ["2023-1"], "tables", False) is None
    )
    assert ledger.read_text(encoding="utf-8") == before


def test_a_sealed_run_writes_one_row_naming_the_terms(tmp_path):
    ledger = _ledger(tmp_path)
    path = sealed.record_run(
        tmp_path,
        "scripts/run_main.py",
        ["2022-2", "2023-1", "2024-1"],
        "outputs/sealed_tables/main_table.csv",
        unseal=True,
    )
    assert path == ledger
    rows = [r for r in ledger.read_text(encoding="utf-8").splitlines() if r.startswith("| 2")]
    assert len(rows) == 1
    assert "2023-1, 2024-1" in rows[0]
    assert "2022-2" not in rows[0]
    assert "outputs/sealed_tables/main_table.csv" in rows[0]
    assert rows[0].rstrip().endswith("| 否 |")


def _rows(ledger) -> list[str]:
    return [r for r in ledger.read_text(encoding="utf-8").splitlines() if r.startswith("| 2")]


def test_a_row_lands_in_the_table_not_under_the_closing_sentence(tmp_path):
    """The ledger ends in prose, and a row appended to the file would land below it."""
    ledger = _ledger(tmp_path)
    closing = "没有对任何封存学期计算过调度结果。"
    ledger.write_text(
        ledger.read_text(encoding="utf-8") + "\n" + closing + "\n", encoding="utf-8"
    )
    sealed.record_access(tmp_path, "scripts/run_main.py", "封存学期 2023-1", "表", "运行者")
    lines = [line for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert lines[-1] == closing
    assert lines[-2].startswith("| 2")


def test_an_interrupted_run_still_leaves_a_row_saying_where_it_stopped(tmp_path):
    """A command that read a sealed term and then died has read it, row or no row."""
    ledger = _ledger(tmp_path)
    with pytest.raises(RuntimeError):
        with sealed.recording(tmp_path, "scripts/run_main.py", ["2023-1"], True) as outcome:
            outcome.at("第 3 格")
            raise RuntimeError("out of memory")
    rows = _rows(ledger)
    assert len(rows) == 1
    assert "中断于第 3 格" in rows[0]
    assert "RuntimeError" in rows[0]


def test_a_second_run_adds_a_row_and_rewrites_none(tmp_path):
    ledger = _ledger(tmp_path)
    for text in ("第一次的表", "第二次的表"):
        with sealed.recording(tmp_path, "scripts/run_main.py", ["2023-1"], True) as outcome:
            outcome.done(text)
    rows = _rows(ledger)
    assert len(rows) == 2
    assert "第一次的表" in rows[0]
    assert "第二次的表" in rows[1]


def test_a_refused_read_writes_no_row(tmp_path):
    """The guard raises before anything is opened; a row would say the opposite."""
    ledger = _ledger(tmp_path)
    before = ledger.read_text(encoding="utf-8")
    with pytest.raises(sealed.SealedDataError):
        with sealed.recording(tmp_path, "scripts/build_overlays.py", ["2023-1"], True):
            sealed.guard_semesters(["2023-1"], tmp_path, unseal=True)
    assert ledger.read_text(encoding="utf-8") == before


@pytest.mark.parametrize(
    "script,extra",
    [
        ("build_overlays.py", ["--out-dir", "absent_overlays"]),
        ("fit_scores.py", ["--out", "absent_scores.parquet"]),
    ],
)
def test_the_sealed_pool_is_refused_in_every_entry_point(tmp_path, monkeypatch, script, extra):
    """The pool name is the same knob for every stage, and every stage refuses it."""
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    flags, message = refusal_for(root)
    monkeypatch.setenv("SPJF_CACHE_DIR", str(tmp_path / "absent_cache"))
    monkeypatch.setenv("SPJF_SCORE_PRED", str(tmp_path / "absent_pred.parquet"))
    args = [str(tmp_path / a) if a.startswith("absent") else a for a in extra]
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / script), "--pool", "sealed", *args, *flags],
        capture_output=True,
        text=True,
        check=False,
        cwd=root,
    )
    assert result.returncode != 0
    assert "SealedDataError" in result.stderr
    assert message in result.stderr
    assert not (tmp_path / "absent_overlays").exists()
    assert not (tmp_path / "absent_scores.parquet").exists()
