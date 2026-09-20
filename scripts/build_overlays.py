"""Build the overlay traces from the parsed cache, inside the package.

    uv run python scripts/build_overlays.py --pool primary --out-dir <dir> \
        [--overlays 0,1,2,3,4] [--unseal]

Pools are named in the configuration under `overlay.pools`: `primary` superposes the
development terms, `validation` leaves the development-test term out, and `sealed` is the
list the sealed run will use.  A sealed pool is refused until the protocol is frozen and
`--unseal` is given; the refusal happens before any file is opened.

Each overlay is written as one npz with the same array names the study has used
throughout, plus `job_row`, the original submission index of every job, so that any
trace can be traced back to the rows it came from.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from spjf_guard import config as cfgmod  # noqa: E402
from spjf_guard.data import sealed  # noqa: E402
from spjf_guard.data.events import (  # noqa: E402
    arrival_and_availability,
    load_events,
    prepare,
    static_submission_columns,
)
from spjf_guard.experiment.overlay import (  # noqa: E402
    REFERENCE_MONDAY_S,
    WEEK_S,
    build_overlay,
    copies_probe,
    pool_inputs,
    single_server_pool,
    superpose,
    week_set,
)


def clock_from(cfg):
    from spjf_guard.data.clock import Clock

    section = cfg["clock"]
    return Clock(
        reading=section["reading"],
        delta_s=float(section["delta_s"]),
        test_outcome_lag_s=float(section["test_block_outcome_lag_s"]),
        jitter_enabled=bool(section["jitter"]["enabled"]),
        jitter_key=section["jitter"]["key"],
    )


def pool_terms(cfg, name: str) -> list:
    pools = cfg["overlay"]["pools"]
    if name not in pools:
        raise SystemExit(f"no pool {name!r}; the configuration has {sorted(pools)}")
    return list(pools[name])


def prepare_everything(cfg, terms, unseal: bool):
    """Guard the terms, read the cache, and derive the clock and the pool inputs."""
    sealed.guard_semesters(terms, ROOT, unseal=unseal)
    events = load_events(cfg.data_path("cache_dir"), cfg["data"]["events_file"])
    prepared = prepare(
        events,
        seed=int(cfg["predictor"]["seed"]),
        limit_s=cfg.limit_s,
        train_terms=cfg["semesters"]["train"],
        zero_cost_drop_terms=cfg["clock"]["drop_zero_cost_terms"],
        jitter_key=cfg["clock"]["jitter"]["key"],
    )
    static = static_submission_columns(events, prepared)
    arrival, _ = arrival_and_availability(prepared, clock_from(cfg))
    rows = prepared.submission_rows
    header = (
        (prepared.timestamp_s + prepared.jitter_u)[rows]
        if cfg["clock"]["jitter"]["enabled"]
        else prepared.timestamp_s[rows]
    )
    inputs = pool_inputs(
        prepared,
        static,
        arrival[rows],
        header,
        terms,
        cfg.limit_s,
        float(cfg["metrics"]["deadline_window_s"]),
    )
    return prepared, inputs


def load_scores(cfg, n_rows: int) -> dict:
    """The stored ranking scores, if the configuration names a file that exists."""
    import pandas as pd

    named = cfg["data"].get("score_predictions_file")
    path = cfg.resolve(named) if named else None
    if path is None or not path.is_file():
        return {}
    frame = pd.read_parquet(path)
    wanted = {"tweedie": "tweedie", "log": "log"}
    out = {}
    for stored, name in wanted.items():
        if stored in frame.columns and len(frame) == n_rows:
            out[name] = frame[stored].to_numpy("float64")
    return out


def build_single_server(cfg, args, inputs, scores) -> int:
    """The k = 1 trace: its own selection of copies, one server, one load level."""
    section = cfg["overlay"]["single_server"]
    seed = int(cfg["overlay"]["seed"]) * 100 + int(section["seed_offset"])
    entries, rho = single_server_pool(
        inputs.pool,
        inputs.per_term,
        "arr",
        seed,
        float(section["target_utilisation"]),
        tuple(section["utilisation_window"]),
        int(section["pool_repeats"]),
    )
    print(f"single server: {len(entries)} copies, busy-hour rho = {rho:.4f}", flush=True)
    arrival, _, _, _ = superpose(entries, inputs.per_term, "arr")
    weeks = np.array(
        sorted(
            set(
                np.unique(
                    np.floor((arrival - REFERENCE_MONDAY_S) / WEEK_S).astype(np.int64)
                ).tolist()
            )
        ),
        np.int64,
    )
    del arrival
    arrays = build_overlay(
        inputs,
        inputs.pool,
        len(entries),
        0,
        seed,
        weeks,
        cfg["overlay"]["target_busy_hour_utilisation"],
        scores=scores,
        entries=entries,
        servers=[1],
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    path = args.out_dir / "k1_rep0.npz"
    np.savez(path, **arrays)
    print(
        f"  {path.name}: {len(arrays['a']):,} jobs, k = 1, "
        f"busy-hour work {float(arrays['W']):,.1f} s, {len(weeks)} weeks",
        flush=True,
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, default=ROOT / "configs" / "main.yaml")
    ap.add_argument("--pool", default="primary")
    ap.add_argument("--overlays", default=None)
    ap.add_argument(
        "--out-dir", type=Path, default=None, help="default: data.overlay_dir of the config"
    )
    ap.add_argument(
        "--single-server",
        action="store_true",
        help="build the k = 1 trace from the pool named in overlay.single_server",
    )
    ap.add_argument("--unseal", action="store_true")
    args = ap.parse_args()

    cfg = cfgmod.load(args.config)
    if args.out_dir is None:
        args.out_dir = cfg.data_path("overlay_dir")
    if args.single_server:
        args.pool = cfg["overlay"]["single_server"]["pool"]
    terms = pool_terms(cfg, args.pool)
    overlays = (
        [int(x) for x in args.overlays.split(",")]
        if args.overlays
        else list(cfg["overlay"]["overlays"])
    )
    started = time.time()
    prepared, inputs = prepare_everything(cfg, terms, args.unseal)
    print(f"pool {args.pool}: {len(inputs.pool)} class-terms, {inputs.info}", flush=True)
    if args.single_server:
        return build_single_server(
            cfg, args, inputs, load_scores(cfg, len(prepared.submission_rows))
        )

    section = cfg["overlay"]
    probe = section["copies_probe"]
    utilisations = section["target_busy_hour_utilisation"]
    seed = int(section["seed"])
    copies, _ = copies_probe(
        inputs.pool,
        inputs.per_term,
        "arr",
        tuple(cfg["overlay"]["overlays"]),
        seed,
        utilisations,
        int(probe["min_servers_at_full_load"]),
        int(probe["distinct_server_counts"]),
        int(probe["stop_after_extra_copies"]),
    )
    print(f"copies probe stops at {copies} copies ({time.time() - started:.0f} s)", flush=True)
    weeks = week_set(
        inputs.pool, inputs.per_term, "arr", copies, tuple(cfg["overlay"]["overlays"]), seed
    )
    print(f"week set: {len(weeks)} whole weeks", flush=True)

    scores = load_scores(cfg, len(prepared.submission_rows))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for overlay in overlays:
        started = time.time()
        arrays = build_overlay(
            inputs, inputs.pool, copies, overlay, seed, weeks, utilisations, scores=scores
        )
        path = args.out_dir / f"{args.pool}_rep{overlay}.npz"
        np.savez(path, **arrays)
        print(
            f"  {path.name}: {len(arrays['a']):,} jobs, k = {list(arrays['K'])}, "
            f"busy-hour work {float(arrays['W']):,.1f} s "
            f"({time.time() - started:.0f} s)",
            flush=True,
        )
        del arrays
    sealed.record_run(
        ROOT,
        "scripts/build_overlays.py",
        terms,
        f"{len(overlays)} 条叠加轨迹写到 {args.out_dir}，"
        f"每条 {copies} 份拷贝、{len(weeks)} 个整周",
        unseal=args.unseal,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
