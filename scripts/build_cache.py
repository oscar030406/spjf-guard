"""Build the parsed-event cache from the per-semester parquet, inside the package.

    uv run python scripts/build_cache.py --raw-dir data/codebench/parquet \
        [--out $SPJF_CACHE_DIR] [--pool development] [--compare <existing ev.parquet>] \
        [--unseal]

`--pool development` reads the development terms of the configuration; `--pool sealed`
reads the sealed ones and is refused until the protocol is frozen and `--unseal` is
given, before any file is opened.  `--compare` writes nothing and instead prints a
column-by-column comparison against an existing cache.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from spjf_guard import config as cfgmod  # noqa: E402
from spjf_guard.data import sealed  # noqa: E402
from spjf_guard.data.cache import build_events, compare_frames, write_events  # noqa: E402


def pool_terms(cfg, pool: str) -> list[str]:
    terms = cfg["semesters"]
    if pool == "sealed":
        return list(terms["sealed_test"])
    if pool == "development":
        return (
            list(terms["train"])
            + list(terms["train_remote"])
            + list(terms["validation"])
            + list(terms["development_test"])
        )
    pools = cfg["overlay"]["pools"]
    if pool in pools:
        return list(pools[pool])
    raise SystemExit(f"no pool {pool!r}: use development, sealed, or one of {sorted(pools)}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, default=ROOT / "configs" / "main.yaml")
    ap.add_argument("--raw-dir", type=Path, default=ROOT / "data" / "codebench" / "parquet")
    ap.add_argument("--pool", default="development")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--compare", type=Path, default=None)
    ap.add_argument("--report", type=Path, default=None)
    ap.add_argument("--unseal", action="store_true")
    args = ap.parse_args()

    cfg = cfgmod.load(args.config)
    terms = pool_terms(cfg, args.pool)
    sealed.guard_semesters(terms, ROOT, unseal=args.unseal)
    started = time.time()
    frame, report = build_events(
        args.raw_dir,
        terms,
        remote_semesters=cfg["semesters"]["train_remote"],
        project_root=ROOT,
        unseal=args.unseal,
    )
    print(
        f"pool {args.pool}: {len(terms)} terms, {report['rows']:,} events, "
        f"{report['columns']} columns, code features matched on "
        f"{report['code_feature_match']:.5f} of rows ({time.time() - started:.0f} s)",
        flush=True,
    )
    if args.compare is not None:
        import pandas as pd

        theirs = pd.read_parquet(args.compare)
        rows = compare_frames(frame, theirs, terms)
        bad = [r for r in rows if r["status"] != "equal"]
        for row in rows:
            print(f"  {row['column']:24s} {row['status']}")
        if args.report is not None:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            with open(args.report, "w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            print(f"wrote {args.report}")
        print(f"{len(rows) - len(bad)} of {len(rows)} columns equal")
        return 1 if bad else 0

    out = args.out or cfg.data_path("cache_dir")
    path = write_events(frame, out, cfg["data"]["events_file"])
    print(f"wrote {path}")
    sealed.record_run(
        ROOT,
        "scripts/build_cache.py",
        terms,
        f"{report['rows']:,} 行事件表写到 {path}",
        unseal=args.unseal,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
