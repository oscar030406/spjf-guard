"""Parse CodeBench semester archives into the per-semester parquet the package reads.

    uv run python scripts/parse_archive.py --semesters 2022-1 [--archive-dir ...] \
        [--out data/codebench/parquet] [--compare] [--unseal]

This is stage zero: the only step whose input is not already a table.  With `--compare`
nothing is written and each of the five tables is checked column by column against the
parquet already on disk, which is how the port was verified against the exploratory
parser (`prechecks/codebench/parse_codebench.py`).

A sealed semester's archive is sealed data like any other, so the same guard applies:
without `--unseal` and a frozen protocol the archive is never opened, and a run that does
open one writes its own row in the access ledger.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from spjf_guard import config as cfgmod  # noqa: E402
from spjf_guard.data import sealed  # noqa: E402
from spjf_guard.data.archive import (  # noqa: E402
    TABLES,
    archive_name,
    parse_archive,
    write_tables,
)


def compare_tables(tables: dict, out_dir: Path, semester: str) -> list[dict]:
    """Each freshly parsed table against the one on disk, column by column."""
    import pandas as pd

    rows = []
    for name in TABLES:
        path = Path(out_dir) / name / f"{semester}.parquet"
        ours = tables[name]
        if not path.is_file():
            rows.append({"table": name, "column": "", "status": "no parquet on disk"})
            continue
        theirs = pd.read_parquet(path)
        if len(ours) != len(theirs):
            rows.append(
                {
                    "table": name,
                    "column": "",
                    "status": f"row counts differ: {len(ours)} against {len(theirs)}",
                }
            )
            continue
        for column in sorted(set(ours.columns) | set(theirs.columns)):
            row = {"table": name, "column": column, "status": "equal"}
            if column not in ours.columns or column not in theirs.columns:
                row["status"] = (
                    "only in ours" if column in ours.columns else "only in the parquet"
                )
            else:
                left, right = ours[column], theirs[column]
                if left.dtype.kind == "f" and right.dtype.kind == "f":
                    same = ((left - right).abs() <= 1e-9) | (left.isna() & right.isna())
                else:
                    same = (left.astype(str) == right.astype(str)) | (
                        left.isna() & right.isna()
                    )
                differing = int((~same).sum())
                if differing:
                    row["status"] = f"{differing} of {len(ours)} rows differ"
            rows.append(row)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, default=ROOT / "configs" / "main.yaml")
    ap.add_argument("--semesters", required=True, help="comma separated, e.g. 2022-1,2022-2")
    ap.add_argument("--archive-dir", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument(
        "--compare",
        action="store_true",
        help="write nothing; compare against the parquet already on disk",
    )
    ap.add_argument("--unseal", action="store_true")
    args = ap.parse_args()

    cfg = cfgmod.load(args.config)
    semesters = [s.strip() for s in args.semesters.split(",") if s.strip()]
    sealed.guard_semesters(semesters, ROOT, unseal=args.unseal)
    archives = args.archive_dir or cfg.data_path("archive_dir")
    out_dir = args.out or cfg.data_path("raw_parquet_dir")

    failures = 0
    for semester in semesters:
        path = Path(archives) / archive_name(semester)
        if not path.is_file():
            raise SystemExit(f"{path} is not on disk")
        started = time.time()
        tables, stats = parse_archive(path)
        if stats["semester"] != semester:
            raise SystemExit(
                f"{path.name} holds semester {stats['semester']!r}, not {semester!r}"
            )
        print(
            f"{semester}: {stats['n_events']:,} events, {stats['n_users']} users, "
            f"{stats['n_assessments']} assessments, {stats['n_logins']:,} logins, "
            f"{stats['n_cm_rows']:,} editor minutes, {stats['uncompressed_mb']:.0f} MB read "
            f"in {time.time() - started:.0f} s",
            flush=True,
        )
        if args.compare:
            rows = compare_tables(tables, out_dir, semester)
            bad = [r for r in rows if r["status"] != "equal"]
            for row in bad:
                print(f"   {row['table']:12s} {row['column']:16s} {row['status']}")
            print(f"   {len(rows) - len(bad)} of {len(rows)} columns equal")
            failures += len(bad)
            continue
        written = write_tables(tables, out_dir, semester)
        print("   wrote " + ", ".join(str(p.relative_to(ROOT)) for p in written))
        sealed.record_run(
            ROOT,
            "scripts/parse_archive.py",
            [semester],
            f"{stats['n_events']:,} 行事件解析进 {out_dir.name}/",
            unseal=args.unseal,
        )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
