from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from consistent_cells import CheckpointStore, combined_hash, sha256_file  # noqa: E402


def _implementation_tree(root: Path) -> list[Path]:
    paths = [root / "scripts" / "runner.py", root / "src" / "engine.py"]
    for path, contents in zip(paths, ("runner\n", "engine\n")):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")
    return paths


def test_combined_hash_uses_repository_relative_path_identifiers(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "relocated" / "second"
    assert combined_hash(_implementation_tree(first), first) == combined_hash(
        _implementation_tree(second), second
    )


def test_checkpoint_rejects_a_tampered_metric_payload(tmp_path: Path) -> None:
    store = CheckpointStore(tmp_path / "checkpoints", tmp_path, "run", True)
    path = store.write("cell", {"metric": 1.25})
    assert store.load("cell") == {"metric": 1.25}

    document = json.loads(path.read_text(encoding="utf-8"))
    document["payload"]["metric"] = 9.5
    path.write_text(json.dumps(document), encoding="utf-8")
    assert store.load("cell") is None


def test_checkpoint_refuses_an_artifact_path_outside_output_root(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    outside = tmp_path / "outside.npz"
    outside.write_bytes(b"not an output artifact")
    artifact = {
        "path": "../outside.npz",
        "bytes": outside.stat().st_size,
        "sha256": sha256_file(outside),
    }
    store = CheckpointStore(output_root / "checkpoints", output_root, "run", True)
    store.write("cell", {"metric": 1.25}, [artifact])
    assert store.load("cell") is None
