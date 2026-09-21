"""Write `protocol_lock.draft.json`: what the frozen protocol pins.

    uv run python scripts/make_protocol_lock.py [--config configs/main.yaml]

The draft carries the sha256 of every source file of the package, of the configuration
itself, and of every input artefact the configuration names, together with the choices
the plan requires to be fixed before the sealed terms are opened: the term split, the
feature list and visibility protocol, the predictor and its seeds, the ranking score, the
guard family and the selection rule, the selected parameters, the load levels and how the
integer server count is derived, the primary metric, and the bootstrap settings.

Freezing is a deliberate act and this script does not perform it: rename the draft to
`protocol_lock.json` by hand.  Until that file exists, the data loader refuses every
sealed term (src/spjf_guard/data/sealed.py).
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from spjf_guard import config as cfgmod  # noqa: E402
from spjf_guard.data import sealed  # noqa: E402

CODE_GLOBS = ("src/spjf_guard/**/*.py", "scripts/*.py", "tests/*.py")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def code_manifest(root: Path) -> list[dict]:
    files = sorted({p for glob in CODE_GLOBS for p in root.glob(glob) if p.is_file()})
    return [
        {"path": str(p.relative_to(root)).replace("\\", "/"), "sha256": sha256_file(p)}
        for p in files
    ]


def relative_to_root(path: Path, root: Path) -> str:
    """The path as the lock records it: relative to the repository, forward slashes.

    A path outside the repository is recorded as it stands, which is a signal in itself:
    the lock is meant to name inputs that a fresh clone plus `data/` can reproduce, so an
    absolute path in there says an input is sitting somewhere machine-specific.
    """
    path = Path(path)
    try:
        return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def input_manifest(cfg, root: Path) -> list[dict]:
    """sha256 of every artefact the configuration names, when it is on disk."""
    data = cfg["data"]
    candidates = []
    for key in ("events_file", "features_file", "forward_predictions_file"):
        if data.get("cache_dir") and data.get(key):
            candidates.append((key, cfg.data_path("cache_dir", data[key])))
    if data.get("score_predictions_file"):
        candidates.append(
            ("score_predictions_file", cfg.resolve(data["score_predictions_file"]))
        )
    out = []
    for key, path in candidates:
        out.append(
            {
                "key": key,
                "path": relative_to_root(path, root),
                "present": path.is_file(),
                "sha256": sha256_file(path) if path.is_file() else None,
                "bytes": path.stat().st_size if path.is_file() else None,
            }
        )
    return out


def _digest_of(entries) -> str:
    h = hashlib.sha256()
    for entry in entries:
        h.update(json.dumps(entry, sort_keys=True).encode())
    return h.hexdigest()


def grid_manifest(cfg) -> dict:
    """The three pre-stated grids, expanded to the points they stand for.

    The configuration states them as rules; the lock carries the points themselves, so
    that "the grid was pre-stated" is checkable without rerunning the expansion.
    """
    from spjf_guard.experiment.grids import grid_points

    section = cfg["scheduling"]["selection"]["grids"]
    points = grid_points(section, cfg.promises_s)
    families: dict[str, list] = {}
    for point in points:
        families.setdefault(point.family, []).append(
            [point.promise_s, point.b0_base_s, point.eta, point.gam_base_s]
        )
    return {
        "definition": section,
        "n_points": {family: len(rows) for family, rows in families.items()},
        "points": families,
        "digest": _digest_of([[f, *p] for f, rows in sorted(families.items()) for p in rows]),
    }


def cache_stage(root: Path, cfg) -> dict:
    """What builds the event cache, and which files it would read for the sealed terms.

    The sealed files are named, not hashed: hashing one means reading it, and that is
    exactly what the protection exists to prevent before the freeze.
    """
    from spjf_guard.data.cache import sealed_inputs

    raw = Path(cfg["data"].get("raw_parquet_dir", "data/codebench/parquet"))
    code = [
        root / "src" / "spjf_guard" / "data" / "cache.py",
        root / "scripts" / "build_cache.py",
    ]
    return {
        "raw_parquet_dir": str(raw).replace("\\", "/"),
        "code": [
            {"path": str(p.relative_to(root)).replace("\\", "/"), "sha256": sha256_file(p)}
            for p in code
            if p.is_file()
        ],
        "sealed_inputs": [
            relative_to_root(p, root)
            for p in sealed_inputs(
                cfg.data_path("archive_dir"),
                cfg.resolve(raw),
                cfg["overlay"]["pools"]["sealed"],
            )
        ],
        "note": "sealed inputs are named, never hashed: hashing one would read it. "
        "This is the same list the freeze hashes, so the draft a person reads describes "
        "the set that is frozen.",
    }


def build(cfg_path: Path, root: Path) -> dict:
    cfg = cfgmod.load(cfg_path)
    code = code_manifest(root)
    inputs = input_manifest(cfg, root)
    scheduling = cfg["scheduling"]
    return {
        "written_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "status": "draft",
        "config": {
            "path": str(cfg_path.relative_to(root)).replace("\\", "/"),
            "sha256": sha256_file(cfg_path),
            "document": cfgmod.load(cfg_path, expand_environment=False).raw,
        },
        "code": {"files": code, "digest": _digest_of(code)},
        "inputs": {"artefacts": inputs, "digest": _digest_of(inputs)},
        "pinned": {
            "semester_split": cfg["semesters"],
            "sealed": {
                "semesters": list(sealed.SEALED_SEMESTERS),
                "accoding_id_block": list(sealed.SEALED_ID_BLOCK),
                "oulad_year": sealed.SEALED_OULAD_YEAR,
            },
            "visibility_protocol": {
                "rule": cfg["features"]["visibility_rule"],
                "clock": cfg["clock"],
            },
            "feature_set": cfg["features"],
            "predictor": cfg["predictor"],
            "ranking_score": scheduling["ranking_score"],
            "guard_budget": scheduling["guard_budget"],
            "promises_s": scheduling["promises_s"],
            "bmax_rule": scheduling["bmax_rule"],
            "selection_rule": scheduling["selection"],
            "search_grids": grid_manifest(cfg),
            "selected_parameters": scheduling["selected"],
            "family_best": scheduling["family_best"],
            "comparators": scheduling["comparators"],
            "event_cache_stage": cache_stage(root, cfg),
            "sealed_tables": list(cfg["run"]["sealed_tables"]),
            "sealed_k1_tables": list(cfg["run"]["sealed_k1_tables"]),
            "sealed_predictor_tables": list(cfg["run"]["sealed_predictor_tables"]),
            "load": {
                "target_busy_hour_utilisation": cfg["overlay"]["target_busy_hour_utilisation"],
                "server_count_rule": cfg["overlay"]["server_count_rule"],
                "overlay_seed": cfg["overlay"]["seed"],
                "overlays": cfg["overlay"]["overlays"],
                "copies_probe": cfg["overlay"]["copies_probe"],
            },
            "primary_metric": cfg["metrics"]["primary"],
            "bootstrap": cfg["bootstrap"],
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, default=ROOT / "configs" / "main.yaml")
    ap.add_argument("--out", type=Path, default=ROOT / "protocol_lock.draft.json")
    args = ap.parse_args()
    lock = build(args.config, ROOT)
    args.out.write_text(
        json.dumps(lock, indent=2, ensure_ascii=False, sort_keys=False) + "\n", encoding="utf-8"
    )
    missing = [a["key"] for a in lock["inputs"]["artefacts"] if not a["present"]]
    print(f"wrote {args.out}")
    print(f"  code   {len(lock['code']['files'])} files, digest {lock['code']['digest']}")
    print(f"  config sha256 {lock['config']['sha256']}")
    print(
        f"  inputs digest {lock['inputs']['digest']}"
        + (f"; NOT ON DISK: {missing}" if missing else "")
    )
    print("  freeze by renaming the draft to protocol_lock.json, deliberately")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
