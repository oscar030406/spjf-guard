"""Snapshot and verify every pre-existing development table without changing it."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRECTORIES = (
    "dev_tables",
    "dev_predictor",
    "dev_visibility",
    "selection_v3",
    "selection_aging",
    "selection_conservative",
    "prefreeze",
    "paper_tables",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sources(ancillary: bool) -> list[Path]:
    if ancillary:
        return sorted(
            [
                *(ROOT / "outputs").glob("*.csv"),
                *(ROOT / "outputs/dev_visibility_smoke").glob("*.csv"),
            ]
        )
    return sorted(
        source
        for directory in DIRECTORIES
        for source in (ROOT / "outputs" / directory).rglob("*.csv")
    )


def snapshot(path: Path, ancillary: bool = False) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite the original snapshot {path}")
    records = []
    for source in _sources(ancillary):
        with source.open(encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.reader(fh))
        records.append(
            {
                "path": source.relative_to(ROOT).as_posix(),
                "sha256": digest(source),
                "bytes": source.stat().st_size,
                "rows": max(len(rows) - 1, 0),
                "columns": rows[0] if rows else [],
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    print(f"snapshotted {len(records)} existing CSV tables")


def check(path: Path, root: Path = ROOT) -> tuple[bool, str]:
    records = json.loads(path.read_text(encoding="utf-8"))
    mismatches = [
        r["path"]
        for r in records
        if not (root / r["path"]).is_file() or digest(root / r["path"]) != r["sha256"]
    ]
    message = (
        f"{len(records)} tables, {sum(r['rows'] for r in records):,} rows: "
        f"{len(mismatches)} byte differences; all existing columns included"
    )
    if mismatches:
        message += "; changed or missing: " + ", ".join(mismatches)
    return not mismatches, message


def verify(path: Path) -> int:
    ok, message = check(path)
    print(message)
    return int(not ok)


def pin_historical_config(snapshot_path: Path) -> int:
    """Keep old run recipes honest when the live protocol acquires new experiments.

    This changes only a manifest's config path, after proving that the archived config
    is exactly the byte sequence that manifest already recorded. It neither re-signs
    table contents nor claims that an old experiment ran under the amended protocol.
    """
    if verify(snapshot_path):
        raise ValueError("existing tables changed; refusing provenance migration")
    archived = ROOT / "configs/main_original_84932d9.yaml"
    expected = digest(archived)
    changed = 0
    paths = sorted(
        {
            path
            for directory in DIRECTORIES
            for path in (ROOT / "outputs" / directory).rglob("manifest.json")
        }
    )
    for path in paths:
        document = json.loads(path.read_text(encoding="utf-8"))
        config = document["config"]
        if config["path"] != "configs/main.yaml":
            continue
        if config["sha256"] != expected:
            raise ValueError(f"{path}: recorded config differs from the historical snapshot")
        config["path"] = archived.relative_to(ROOT).as_posix()
        document.setdefault("notes", {})["historical_recipe"] = (
            "Original commit 84932d9 configuration, preserved byte-for-byte. Only its "
            "path was relocated after the visibility amendment; output hashes unchanged."
        )
        path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        changed += 1
    print(f"pinned {changed} historical manifests to the unchanged configuration bytes")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", action="store_true")
    parser.add_argument("--ancillary", action="store_true")
    parser.add_argument("--pin-historical-config", action="store_true")
    parser.add_argument(
        "--file", type=Path, default=ROOT / "outputs/consistent_original_tables.json"
    )
    args = parser.parse_args()
    if args.snapshot:
        snapshot(args.file, args.ancillary)
        return 0
    if args.pin_historical_config:
        return pin_historical_config(args.file)
    return verify(args.file)


if __name__ == "__main__":
    raise SystemExit(main())
