"""Check the package's feature sweep against the cached one, column by column.

    uv run python scripts/check_features.py [--config configs/main.yaml]

Integer and count columns must be exactly equal; float columns must agree to 1e-9 after
both are taken to float64.  Any column that differs is printed with how far and on how
many rows, so a disagreement is described rather than tolerated.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from spjf_guard import config as cfgmod  # noqa: E402
from spjf_guard.data import sealed  # noqa: E402
from spjf_guard.data.clock import Clock  # noqa: E402
from spjf_guard.data.events import arrival_and_availability, load_events, prepare  # noqa: E402
from spjf_guard.features.sweep import AUX_COLS, FEATURE_COLUMNS, feature_frame  # noqa: E402

EXACT_COLUMNS = ("ex_n", "u_n", "ue_n", *AUX_COLS)
"""Counts: these are integers and must match exactly."""

TOLERANCE = 1e-9


def clock_from(cfg) -> Clock:
    section = cfg["clock"]
    return Clock(
        reading=section["reading"],
        delta_s=float(section["delta_s"]),
        test_outcome_lag_s=float(section["test_block_outcome_lag_s"]),
        jitter_enabled=bool(section["jitter"]["enabled"]),
        jitter_key=section["jitter"]["key"],
    )


def compare(ours: pd.DataFrame, theirs: pd.DataFrame) -> list[dict]:
    rows = []
    for column in list(FEATURE_COLUMNS) + list(AUX_COLS):
        mine = ours[column].to_numpy("float64")
        other = theirs[column].to_numpy("float64")
        both_nan = np.isnan(mine) & np.isnan(other)
        nan_only_mine = np.isnan(mine) & ~np.isnan(other)
        nan_only_theirs = ~np.isnan(mine) & np.isnan(other)
        finite = ~np.isnan(mine) & ~np.isnan(other)
        delta = np.abs(mine[finite] - other[finite])
        worst = float(delta.max()) if delta.size else 0.0
        exact = column in EXACT_COLUMNS
        differing = int((delta > 0).sum()) if exact else int((delta > TOLERANCE).sum())
        rows.append(
            {
                "column": column,
                "exact_required": exact,
                "rows_differing": differing
                + int(nan_only_mine.sum())
                + int(nan_only_theirs.sum()),
                "worst_abs_difference": worst,
                "both_nan": int(both_nan.sum()),
                "nan_only_ours": int(nan_only_mine.sum()),
                "nan_only_cached": int(nan_only_theirs.sum()),
                "ok": (
                    differing == 0 and nan_only_mine.sum() == 0 and nan_only_theirs.sum() == 0
                ),
            }
        )
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, default=ROOT / "configs" / "main.yaml")
    ap.add_argument("--out", type=Path, default=ROOT / "outputs" / "feature_check.csv")
    args = ap.parse_args()

    cfg = cfgmod.load(args.config)
    terms = cfg["semesters"]
    whitelist = (
        list(terms["train"])
        + list(terms["train_remote"])
        + list(terms["validation"])
        + list(terms["development_test"])
    )
    sealed.guard_semesters(whitelist, ROOT, unseal=False)

    started = time.time()
    events = load_events(cfg.data_path("cache_dir"), cfg["data"]["events_file"])
    print(f"events {len(events):,} in {time.time() - started:.0f} s", flush=True)
    prepared = prepare(
        events,
        seed=int(cfg["predictor"]["seed"]),
        limit_s=cfg.limit_s,
        train_terms=terms["train"],
        zero_cost_drop_terms=cfg["clock"]["drop_zero_cost_terms"],
        jitter_key=cfg["clock"]["jitter"]["key"],
    )
    print(
        f"heavy threshold {prepared.heavy_threshold:.6f} s, tercile cuts "
        f"{prepared.tercile_cuts[0]:.6f} / {prepared.tercile_cuts[1]:.6f}",
        flush=True,
    )
    arrival, availability = arrival_and_availability(prepared, clock_from(cfg))
    started = time.time()
    ours = feature_frame(prepared, arrival, availability)
    print(f"sweep {time.time() - started:.0f} s, {len(ours):,} submissions", flush=True)

    cached = pd.read_parquet(cfg.data_path("cache_dir", cfg["data"]["features_file"]))
    if len(cached) != len(ours):
        print(f"row counts differ: ours {len(ours):,}, cached {len(cached):,}")
        return 1
    rows = compare(ours, cached)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    bad = [r for r in rows if not r["ok"]]
    for row in rows:
        mark = "ok  " if row["ok"] else "DIFF"
        print(
            f"{mark} {row['column']:22s} differing={row['rows_differing']:>8,} "
            f"worst={row['worst_abs_difference']:.3e}"
        )
    print(f"\nwrote {args.out}; {len(bad)} of {len(rows)} columns differ")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
