"""Acceptance check: reproduce the v3.1 development result on the primary overlays.

    uv run python scripts/check_reproduction.py --overlay-dir <dir with primary_rep*.npz> \
        [--reps 0,1,2,3,4] [--levels 0,1,2] [--out outputs/reproduction.csv]

Two things are checked.  First, per-job: for every policy the 17.6 M waits this package
produces must equal, job for job, the waits the exploratory kernels produce on the same
trace.  Second, in summary: aggregated over the overlays exactly as v3.1's report
aggregates them (mean for the waits, the firing rate and k, worst-over-overlays for the
excess, the harm and the worst heavy wait), the numbers must match
prechecks/main_v3/v31/table_main_primary.csv to the precision that file prints.

Exit status is non-zero when any wait differs or any summary number moves.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import tempfile
from pathlib import Path

# numba reads NUMBA_CACHE_DIR once, when it is imported, so it has to be redirected
# before anything pulls numba in; otherwise the compiled caches of the read-only kernels
# under prechecks/ land next to their sources.
os.environ.setdefault("NUMBA_CACHE_DIR", tempfile.mkdtemp(prefix="numba_repro_"))
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.dont_write_bytecode = True

import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from spjf_guard.experiment.reproduce import (  # noqa: E402
    POLICY_COLUMN,
    compare_level,
    load_overlay,
    read_v31_table,
)

MEAN_OVER_OVERLAYS = {
    "p99_dl_s": "p99_dl_s",
    "mean_s": "mean_s",
    "p99_all_s": "p99_all_s",
    "fired_fraction_queue_weighted": "qw_fired",
}
WORST_OVER_OVERLAYS = {
    "max_excess_s": "max_excess_s",
    "harm_s": "harm_wf1s_s",
    "max_heavy_s": "max_heavy_s",
}
TOLERANCE = {
    "p99_dl_s": 5e-7,
    "mean_s": 5e-7,
    "p99_all_s": 5e-7,
    "fired_fraction_queue_weighted": 5e-5,
    "max_excess_s": 5e-7,
    "harm_s": 5e-7,
    "max_heavy_s": 5e-7,
    "gap_closed": 5e-5,
}


def _per_cell(args, table):
    """One row per (overlay, level, policy), both measured and read from v3.1."""
    rows = []
    for rep in (int(x) for x in args.reps.split(",")):
        path = args.overlay_dir / f"primary_rep{rep}.npz"
        for level in (int(x) for x in args.levels.split(",")):
            trace, servers, labels = load_overlay(path, level)
            print(f"rep{rep} level{level}: k = {servers}, {len(trace):,} jobs", flush=True)
            for c in compare_level(
                trace,
                servers,
                labels,
                level,
                table,
                ROOT / "prechecks",
                args.b0_base,
                args.eta,
                args.promise,
            ):
                rows.append(
                    {
                        "rep": rep,
                        "level": level,
                        "k": servers,
                        "policy": c.policy,
                        "jobs_differing": c.jobs_differing,
                        "worst_difference_us": c.worst_difference_us,
                        "gap_closed": c.gap_closed,
                        **c.ours.as_row(),
                    }
                )
                print(
                    f"  {c.policy:12s} differing={c.jobs_differing:>10,} "
                    f"p99dl={c.ours.p99_dl_s:.6f} gap={c.gap_closed:.4f}",
                    flush=True,
                )
            del trace, labels
    return rows


def _aggregate(rows, table):
    """Mean and worst over the overlays, as v3.1's report aggregates them."""
    out = []
    for level in sorted({r["level"] for r in rows}):
        for policy in POLICY_COLUMN:
            cells = [r for r in rows if r["level"] == level and r["policy"] == policy]
            if not cells:
                continue
            theirs = table[(level, POLICY_COLUMN[policy])]
            agg = {
                "level": level,
                "policy": policy,
                "n_overlays": len(cells),
                "k": float(np.mean([c["k"] for c in cells])),
                "jobs_differing": int(sum(c["jobs_differing"] for c in cells)),
                "gap_closed": float(np.mean([c["gap_closed"] for c in cells])),
                "gap_closed_v31": theirs["gap_closed"],
            }
            for field, column in MEAN_OVER_OVERLAYS.items():
                agg[field] = float(np.mean([c[field] for c in cells]))
                agg[field + "_v31"] = theirs[column]
            for field, column in WORST_OVER_OVERLAYS.items():
                agg[field] = float(np.max([c[field] for c in cells]))
                agg[field + "_v31"] = theirs[column]
            out.append(agg)
    return out


def _verdict(agg_rows):
    failures = []
    for row in agg_rows:
        if row["jobs_differing"]:
            failures.append(
                f"{row['policy']} L{row['level']}: {row['jobs_differing']:,} waits differ"
            )
        for field, tol in TOLERANCE.items():
            mine, theirs = row[field], row[field + "_v31"]
            if not np.isfinite(theirs):
                continue
            if abs(mine - theirs) > tol:
                failures.append(
                    f"{row['policy']} L{row['level']} {field}: "
                    f"{mine:.6f} against v3.1's {theirs:.6f}"
                )
    return failures


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--overlay-dir", required=True, type=Path)
    ap.add_argument("--reps", default="0,1,2,3,4")
    ap.add_argument("--levels", default="0,1,2")
    ap.add_argument("--b0-base", type=float, default=120.0)
    ap.add_argument("--eta", type=float, default=0.75)
    ap.add_argument("--promise", type=float, default=600.0)
    ap.add_argument(
        "--table", type=Path, default=ROOT / "prechecks/main_v3/v31/table_main_primary.csv"
    )
    ap.add_argument("--out", type=Path, default=ROOT / "outputs/reproduction.csv")
    args = ap.parse_args()

    table = read_v31_table(args.table)
    rows = _per_cell(args, table)
    agg = _aggregate(rows, table)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    for name, data in (("cells", rows), ("", agg)):
        path = (
            args.out
            if not name
            else args.out.with_name(args.out.stem + "_cells" + args.out.suffix)
        )
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(data[0]))
            writer.writeheader()
            writer.writerows(data)
        print(f"wrote {path}")
    failures = _verdict(agg)
    print(
        "\n".join(failures)
        if failures
        else "\nevery per-job wait and every summary number matches v3.1"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
