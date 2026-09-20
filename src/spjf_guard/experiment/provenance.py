"""A manifest beside every produced table, so a hand edit is detectable.

Re-running the experiment to check a CSV costs an hour, which is not a check anybody
runs before a commit.  What a run *can* do cheaply is record, next to the files it
wrote, the sha256 of each of them together with the configuration and the overlays they
came from.  `scripts/check_generated.py` then answers two questions in a second: has
anyone edited a generated table by hand, and was it produced from the configuration that
is on disk now.  It cannot tell whether the numbers are right; that is what
`scripts/check_reproduction.py` is for.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

MANIFEST_NAME = "manifest.json"
"""What the file is called inside the directory whose contents it describes."""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


PROJECT_ROOT = Path(__file__).resolve().parents[3]
"""The repository root, so a manifest names its files the way the repository does."""


def _relative(path: Path, root: Path | None) -> str:
    """The path relative to `root`, else to the repository, else as it stands.

    A manifest that recorded a path inside somebody's home or inside a session temporary
    directory would be describing this machine rather than this experiment, and the path
    would be gone the next day.
    """
    for base in (root, PROJECT_ROOT):
        if base is None:
            continue
        try:
            return str(Path(path).resolve().relative_to(Path(base).resolve())).replace(
                "\\", "/"
            )
        except ValueError:
            continue
    return str(path).replace("\\", "/")


def relative_path(path, root: Path | None = None) -> str:
    """How every path this package records is spelled: relative to the repository."""
    return _relative(Path(path), root)


def _entry(path: Path, root: Path | None = None) -> dict:
    name = _relative(path, root)
    present = path.is_file()
    return {
        "path": name,
        "present": present,
        "bytes": path.stat().st_size if present else None,
        "sha256": sha256_file(path) if present else None,
    }


def build(
    out_dir: Path,
    produced_by: str,
    config_path: Path,
    outputs,
    inputs=(),
    arguments: dict | None = None,
    notes: dict | None = None,
) -> dict:
    """Describe one set of produced files: what made them, from what, and their hashes."""
    return {
        "produced_by": produced_by,
        "written_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "config": _entry(Path(config_path)),
        "inputs": [_entry(Path(p)) for p in inputs],
        "outputs": [_entry(Path(p), out_dir) for p in outputs],
        "arguments": arguments or {},
        "notes": notes or {},
    }


def write(out_dir: Path, **kwargs) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / MANIFEST_NAME
    document = build(out_dir, **kwargs)
    path.write_text(json.dumps(document, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return path


def verify(manifest_path: Path) -> list[str]:
    """Complaints about the directory this manifest describes; empty means it is intact.

    A missing input is not a complaint: the overlays and the caches live under `data/`,
    which is not in the repository, and a machine that only reads the tables never has
    them.  A changed input is, because the tables no longer follow from what is on disk.
    """
    manifest_path = Path(manifest_path)
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    out_dir = manifest_path.parent
    complaints = []
    for recorded in document["outputs"]:
        current = _entry(out_dir / recorded["path"], out_dir)
        if not current["present"]:
            complaints.append(f"{recorded['path']}: recorded by the run but not on disk")
        elif current["sha256"] != recorded["sha256"]:
            complaints.append(
                f"{recorded['path']}: changed since {document['produced_by']} wrote it "
                f"({recorded['bytes']} -> {current['bytes']} bytes); regenerate it "
                f"instead of editing it"
            )
    for name, recorded in [("config", document["config"])] + [
        (f"input {i['path']}", i) for i in document["inputs"]
    ]:
        named = Path(recorded["path"])
        current = _entry(named if named.is_absolute() else PROJECT_ROOT / named)
        if not current["present"] or not recorded["present"]:
            continue
        if current["sha256"] != recorded["sha256"]:
            complaints.append(f"{name}: changed since the run; the tables are stale")
    return complaints
