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
    (tmp_path / "protocol_lock.json").write_text(json.dumps({"frozen": True}), encoding="utf-8")
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


def test_no_frozen_lock_exists_yet():
    """The development repository must not carry a frozen lock by accident."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    assert sealed.frozen_lock(root) is None, (
        "protocol_lock.json exists: the protocol is frozen, which is a deliberate act"
    )


def test_the_run_script_refuses_unseal_without_a_frozen_lock(tmp_path, monkeypatch):
    """The protection is wired into the entry point, not only into the module."""
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("SPJF_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("SPJF_SCORE_PRED", str(tmp_path / "pred.parquet"))
    result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "run_main.py"),
            "--overlay-dir",
            str(tmp_path),
            "--reps",
            "0",
            "--levels",
            "0",
            "--unseal",
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=root,
    )
    assert result.returncode != 0
    assert "SealedDataError" in result.stderr
    assert "no frozen protocol_lock.json" in result.stderr


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
    monkeypatch.setenv("SPJF_CACHE_DIR", str(tmp_path / "absent_cache"))
    monkeypatch.setenv("SPJF_SCORE_PRED", str(tmp_path / "absent_pred.parquet"))
    args = [str(tmp_path / a) if a.startswith("absent") else a for a in extra]
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / script), "--pool", "sealed", *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=root,
    )
    assert result.returncode != 0
    assert "SealedDataError" in result.stderr
    assert "no frozen protocol_lock.json" in result.stderr
    assert not (tmp_path / "absent_overlays").exists()
    assert not (tmp_path / "absent_scores.parquet").exists()
