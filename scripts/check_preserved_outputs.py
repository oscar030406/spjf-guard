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
    "selection_v4",
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


def record(source: Path) -> dict:
    with source.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh))
    return {
        "path": source.relative_to(ROOT).as_posix(),
        "sha256": digest(source),
        "bytes": source.stat().st_size,
        "rows": max(len(rows) - 1, 0),
        "columns": rows[0] if rows else [],
    }


DERIVED = ("outputs/paper_tables/numbers.csv",)
"""A snapshotted file that is not a measurement: `numbers.csv` indexes the manuscript's
figures and changes whenever `paper/` does."""

RERUN_DIRECTORY = "outputs/prefreeze/"
ORIGINAL_CONFIG = Path("configs/main_original_84932d9.yaml")
"""The pre-freeze check writes a fresh copy of the selection and the development tables
here on every run, to compare them with the ones the paper uses; its files are
replaced by design.  `--refresh` may replace their records only when the file now
matches, byte for byte, the development table of the same name."""


def _refreshable(name: str) -> bool:
    if name in DERIVED:
        return True
    if not name.startswith(RERUN_DIRECTORY):
        return False
    if name.endswith(".log.csv"):
        return True
    twin = ROOT / "outputs" / name.removeprefix(RERUN_DIRECTORY)
    return twin.is_file() and digest(twin) == digest(ROOT / name)


def refresh(path: Path, names: list[str]) -> int:
    """Replace the records of derived files after a deliberate regeneration.

    A measurement table is never refreshed this way: a changed one is the failure the
    snapshot exists to catch, and the only honest answer is to restore its bytes.
    """
    stray = [name for name in names if not _refreshable(name)]
    if stray:
        print("refusing to refresh a measurement table: " + ", ".join(stray))
        return 1
    records = json.loads(path.read_text(encoding="utf-8"))
    for entry in records:
        if entry["path"] in names:
            new = record(ROOT / entry["path"])
            print(f"{entry['path']}: {entry['sha256'][:12]} -> {new['sha256'][:12]}")
            entry.update(new)
    path.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    return 0


def snapshot(path: Path, ancillary: bool = False) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite the original snapshot {path}")
    records = [record(source) for source in _sources(ancillary)]
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


def pin_historical_config(
    snapshot_path: Path, archived: Path = ORIGINAL_CONFIG, root: Path = ROOT
) -> int:
    """Keep old run recipes honest when the live protocol acquires new experiments.

    This changes only a manifest's config path, after proving that the archived config
    is exactly the byte sequence that manifest already recorded. It neither re-signs
    table contents nor claims that an old experiment ran under the amended protocol.
    Every manifest under `outputs/` that names `configs/main.yaml` is moved.
    """
    if not check(snapshot_path, root)[0]:
        raise ValueError("existing tables changed; refusing provenance migration")
    expected = digest(root / archived)
    changed = 0
    for path in sorted((root / "outputs").rglob("manifest.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        config = document["config"]
        if config["path"] != "configs/main.yaml":
            continue
        if config["sha256"] != expected:
            raise ValueError(f"{path}: recorded config differs from {archived.as_posix()}")
        config["path"] = archived.as_posix()
        document.setdefault("notes", {})["historical_recipe"] = (
            f"The configuration this run read, preserved byte-for-byte as "
            f"{archived.as_posix()}. Only its path was relocated after configs/main.yaml "
            f"was amended; output hashes unchanged."
        )
        path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        changed += 1
    print(f"pinned {changed} manifests to {archived.as_posix()}")
    return 0


def relocate(snapshot_path: Path, old: str, new: str, root: Path = ROOT) -> int:
    """Point the records of tables that a deliberate rerun replaced at their preserved copy.

    A record moves only when its table no longer matches at `old` and the file at `new`
    is byte for byte the one it recorded, so what the snapshot guards is unchanged; the
    rerun's tables are guarded by a snapshot of their own.
    """
    records = json.loads(snapshot_path.read_text(encoding="utf-8"))
    moved = []
    for entry in records:
        here = root / entry["path"]
        if not entry["path"].startswith(old) or (
            here.is_file() and digest(here) == entry["sha256"]
        ):
            continue
        target = new + entry["path"].removeprefix(old)
        if not (root / target).is_file() or digest(root / target) != entry["sha256"]:
            raise ValueError(f"{target} is not the table {entry['path']} recorded")
        entry["relocated_from"] = entry["path"]
        entry["path"] = target
        moved.append(target)
    snapshot_path.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    print(f"relocated {len(moved)} records from {old} to {new}")
    return len(moved)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", action="store_true")
    parser.add_argument("--ancillary", action="store_true")
    parser.add_argument(
        "--pin-historical-config",
        nargs="?",
        const=ORIGINAL_CONFIG,
        type=Path,
        metavar="ARCHIVED_CONFIG",
        help="repoint manifests naming configs/main.yaml to this byte-identical copy",
    )
    parser.add_argument(
        "--file", type=Path, default=ROOT / "outputs/consistent_original_tables.json"
    )
    parser.add_argument("--refresh", nargs="+", metavar="PATH", help="derived files only")
    parser.add_argument("--relocate", nargs=2, metavar=("OLD", "NEW"))
    args = parser.parse_args()
    if args.snapshot:
        snapshot(args.file, args.ancillary)
        return 0
    if args.relocate:
        relocate(args.file, *args.relocate)
        return verify(args.file)
    if args.refresh:
        return refresh(args.file, args.refresh)
    if args.pin_historical_config:
        return pin_historical_config(args.file, args.pin_historical_config)
    return verify(args.file)


if __name__ == "__main__":
    raise SystemExit(main())
