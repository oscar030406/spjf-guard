"""Small, validated checkpoints for the exact-visibility experiment.

Each policy/cell is independent once the frozen models and controls exist.  A completed
policy therefore writes one JSON payload immediately.  Resume accepts that payload only
when the code/config/input signature matches and every sparse delta artifact still has
the recorded hash.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def combined_hash(paths: list[Path], root: Path) -> str:
    """Hash contents under stable repository-relative path identifiers."""
    resolved_root = root.resolve()
    identified = []
    for path in paths:
        resolved = path.resolve()
        try:
            identifier = resolved.relative_to(resolved_root).as_posix()
        except ValueError as exc:
            raise ValueError(
                f"implementation path is outside {resolved_root}: {resolved}"
            ) from exc
        identified.append((identifier, resolved))
    digest = hashlib.sha256()
    for identifier, path in sorted(identified):
        digest.update(identifier.encode("utf-8"))
        digest.update(sha256_file(path).encode("ascii"))
    return digest.hexdigest()


def signature(document: dict[str, Any]) -> str:
    encoded = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def checkpoint_slug(value: str) -> str:
    return (
        value.lower()
        .replace("(", "_")
        .replace(")", "")
        .replace("|", "_")
        .replace("-", "_")
        .replace(" ", "_")
    )


def replicate_lists(replicates: dict[str, np.ndarray]) -> dict[str, list[float]]:
    return {
        name: np.asarray(values, np.float64).tolist() for name, values in replicates.items()
    }


def replicate_arrays(replicates: dict[str, list[float]]) -> dict[str, np.ndarray]:
    return {name: np.asarray(values, np.float64) for name, values in replicates.items()}


def artifact_entry(path: Path, root: Path, **fields: Any) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(root)).replace("\\", "/"),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        **fields,
    }


def artifacts_valid(entries: list[dict[str, Any]], root: Path) -> bool:
    resolved_root = root.resolve()
    for entry in entries:
        try:
            path = (resolved_root / Path(entry["path"])).resolve()
            expected_bytes = int(entry["bytes"])
            expected_sha256 = str(entry["sha256"])
        except (KeyError, TypeError, ValueError, OSError):
            return False
        if not path.is_relative_to(resolved_root) or not path.is_file():
            return False
        if path.stat().st_size != expected_bytes:
            return False
        if sha256_file(path) != expected_sha256:
            return False
    return True


@dataclass(frozen=True)
class CheckpointStore:
    root: Path
    output_root: Path
    run_signature: str
    resume: bool

    def path_for(self, name: str) -> Path:
        return self.root / f"{checkpoint_slug(name)}.json"

    def load(self, name: str) -> dict[str, Any] | None:
        path = self.path_for(name)
        if not self.resume or not path.is_file():
            return None
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if document.get("run_signature") != self.run_signature:
            return None
        artifacts = document.get("artifacts", [])
        if not isinstance(artifacts, list) or not artifacts_valid(artifacts, self.output_root):
            return None
        payload = document.get("payload")
        payload_sha256 = document.get("payload_sha256")
        if not isinstance(payload, dict) or not isinstance(payload_sha256, str):
            return None
        return payload if signature(payload) == payload_sha256 else None

    def write(
        self,
        name: str,
        payload: dict[str, Any],
        artifacts: list[dict[str, Any]] | None = None,
    ) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.path_for(name)
        temporary = path.with_suffix(".tmp")
        document = {
            "run_signature": self.run_signature,
            "artifacts": artifacts or [],
            "payload": payload,
            "payload_sha256": signature(payload),
        }
        temporary.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        temporary.replace(path)
        return path
