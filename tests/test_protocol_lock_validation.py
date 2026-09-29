"""Only a structurally complete frozen lock may release sealed paths."""

from __future__ import annotations

import copy
import json

import pytest

from spjf_guard.data import sealed


def _valid_lock() -> dict:
    return {
        "status": "frozen",
        "commit": "a" * 40,
        "code": {"files": [], "digest": "b" * 64},
        "config": {"path": "configs/main.yaml", "sha256": "c" * 64},
        "config_snapshots": [
            {
                "path": str(path).replace("\\", "/"),
                "present": False,
                "sha256": None,
            }
            for path in sealed.CONFIG_SNAPSHOT_PATHS
        ],
        "sealed_input_hashes": [
            {"path": "data/sealed-do-not-open.parquet", "sha256": "d" * 64, "bytes": 1}
        ],
    }


def _write_lock(root, document: dict) -> None:
    (root / "protocol_lock.json").write_text(json.dumps(document), encoding="utf-8")


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (lambda lock: lock.update(status="draft"), "status=frozen"),
        (lambda lock: lock.pop("commit"), "frozen commit"),
        (lambda lock: lock.pop("sealed_input_hashes"), "sealed input hashes"),
        (lambda lock: lock.pop("code"), "code manifest"),
        (lambda lock: lock.pop("config_snapshots"), "archived-configuration manifest"),
    ],
)
def test_renamed_or_incomplete_draft_cannot_release_sealed_data(tmp_path, mutation, reason):
    document = copy.deepcopy(_valid_lock())
    mutation(document)
    _write_lock(tmp_path, document)

    decision = sealed.decide(tmp_path, unseal=True)

    assert not decision.permitted
    assert reason in decision.reason


def test_complete_frozen_lock_releases_without_opening_named_sealed_input(tmp_path):
    document = _valid_lock()
    _write_lock(tmp_path, document)

    decision = sealed.decide(tmp_path, unseal=True)

    assert decision.permitted
    assert not (tmp_path / document["sealed_input_hashes"][0]["path"]).exists()


def test_release_flag_is_still_required_before_lock_validation(tmp_path):
    _write_lock(tmp_path, {"status": "draft"})

    decision = sealed.decide(tmp_path, unseal=False)

    assert not decision.permitted
    assert "--unseal flag" in decision.reason
