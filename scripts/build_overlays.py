"""Build the overlay traces from the parsed cache, inside the package.

    uv run python scripts/build_overlays.py --pool primary --out-dir <dir> \
        [--overlays 0,1,2,3,4] [--single-server] [--score-parquet <parquet>] \
        [--no-scores] [--unseal]

Pools are named in the configuration under `overlay.pools`: `primary` superposes the
development terms, `validation` leaves the development-test term out, and `sealed` is the
list the sealed run will use.  A sealed pool is refused until the protocol is frozen and
`--unseal` is given; the refusal happens before any file is opened.

`--single-server` builds the k = 1 trace, from `--pool` when one is given and otherwise
from the pool named in `overlay.single_server`.  It writes `k1_rep0.npz` for that pool
and `<pool>_k1_rep0.npz` for any other, so the two never overwrite each other.

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
from spjf_guard.experiment import provenance  # noqa: E402
from spjf_guard.experiment.overlay import (  # noqa: E402
    REFERENCE_MONDAY_S,
    WEEK_S,
    build_overlay,
    copies_probe,
    pool_inputs,
    single_server_copies,
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
    events = load_events(
        cfg.data_path("cache_dir"),
        cfg["data"]["events_file"],
        cfg["data"]["sealed_events_file"] if unseal else None,
    )
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


STORED_SCORES = {
    "tweedie": ("tweedie", cfgmod.SCORE_KEY),
    "log": ("log", cfgmod.LOG_SCORE_KEY),
}
"""Array name in the trace -> the column spellings a score file may carry: the pre-check's
(`tweedie`, `log`) and this package's own (`spjf_e`, `spjf_log`)."""


def load_scores(cfg, n_rows: int, path: Path | None = None, wanted: bool = True) -> dict:
    """The ranking scores stored inside the trace, one value per prepared submission.

    Stored scores are a convenience: `scripts/run_main.py --score-parquet` attaches the
    package's own by `job_row` and overrides whatever the trace carries.  They are read
    by position, so a file whose length is not this cache's number of prepared
    submissions belongs to another cache.  That used to be dropped without a word, which
    left the trace with no ranking at all and a run that quietly reported the policies
    that need none; it is refused now.  A pool whose scores do not exist yet -- the
    sealed pool, whose scores are fitted after its overlays are built -- says so with
    `--no-scores`.
    """
    import pandas as pd

    if not wanted:
        print("no stored scores: the run attaches its own by job_row", flush=True)
        return {}
    if path is None:
        named = cfg["data"].get("score_predictions_file")
        path = cfg.resolve(named) if named else None
    if path is None or not path.is_file():
        print(f"no stored scores: {path} is not on disk", flush=True)
        return {}
    frame = pd.read_parquet(path)
    if len(frame) != n_rows:
        raise SystemExit(
            f"{path} has {len(frame):,} rows and this pool's cache has {n_rows:,} prepared "
            "submissions; the scores are read by position, so they were fitted on another "
            "cache. Give --score-parquet the file fitted on this one, or --no-scores to "
            "build a trace that scripts/run_main.py attaches its scores to."
        )
    out = {}
    for array, columns in STORED_SCORES.items():
        found = next((c for c in columns if c in frame.columns), None)
        if found is not None:
            out[array] = frame[found].to_numpy("float64")
    if not out:
        raise SystemExit(f"{path} carries none of the score columns {sorted(STORED_SCORES)}")
    return out


def single_server_prefix(cfg, pool: str) -> str:
    """What the k = 1 trace of a pool is called: `k1` for the pool the selection was made
    on, `<pool>_k1` for any other, so that a second pool's trace never overwrites it."""
    return "k1" if pool == cfg["overlay"]["single_server"]["pool"] else f"{pool}_k1"


def single_server_entries(cfg, pool: str, inputs, seed: int):
    """The copies the k = 1 trace superposes, and the busy hour they reach.

    On the pool the selection was made on, the probe runs as it always has and its count
    is compared with the pinned one.  On any other pool the pinned count is reused and
    the utilisation is reported as it comes, because choosing copies by the utilisation
    they produce is a design decision and would be taken on that pool's data.  ADR 0006.
    """
    section = cfg["overlay"]["single_server"]
    pinned = int(section["copies"])
    if pool != section["pool"]:
        entries, rho = single_server_copies(
            inputs.pool, inputs.per_term, "arr", seed, pinned, int(section["pool_repeats"])
        )
        return entries, rho, f"{pinned} copies reused from pool {section['pool']}"
    entries, rho = single_server_pool(
        inputs.pool,
        inputs.per_term,
        "arr",
        seed,
        float(section["target_utilisation"]),
        tuple(section["utilisation_window"]),
        int(section["pool_repeats"]),
    )
    if len(entries) != pinned:
        print(
            f"  copies mismatch: the probe selected {len(entries)}, the configuration "
            f"pins {pinned}; the pinned number is what another pool would reuse",
            flush=True,
        )
    return entries, rho, "selected by the probe on its own pool"


def build_single_server(cfg, args, inputs, scores, outcome) -> int:
    """The k = 1 trace: its own selection of copies, one server, one load level."""
    section = cfg["overlay"]["single_server"]
    seed = int(cfg["overlay"]["seed"]) * 100 + int(section["seed_offset"])
    entries, rho, how = single_server_entries(cfg, args.pool, inputs, seed)
    print(
        f"single server: {len(entries)} copies ({how}), busy-hour rho = {rho:.4f}",
        flush=True,
    )
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
    path = args.out_dir / f"{single_server_prefix(cfg, args.pool)}_rep0.npz"
    np.savez(path, **arrays)
    print(
        f"  {path.name}: {len(arrays['a']):,} jobs, k = 1, "
        f"busy-hour work {float(arrays['W']):,.1f} s, {len(weeks)} weeks",
        flush=True,
    )
    outcome.done(
        f"k = 1 叠加轨迹 {path.name} 写到 {provenance.relative_path(args.out_dir)}，"
        f"{len(entries)} 份拷贝（{how}），实际忙时利用率 {rho:.4f}"
    )
    return 0


def build(cfg, args, terms, overlays, outcome) -> int:
    """Prepare the pool and write its traces, under the ledger row of this reading."""
    started = time.time()
    outcome.at("读取事件缓存")
    prepared, inputs = prepare_everything(cfg, terms, args.unseal)
    print(f"pool {args.pool}: {len(inputs.pool)} class-terms, {inputs.info}", flush=True)
    rows = len(prepared.submission_rows)
    if args.single_server:
        scores = load_scores(cfg, rows, args.score_parquet, not args.no_scores)
        return build_single_server(cfg, args, inputs, scores, outcome)

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

    scores = load_scores(cfg, rows, args.score_parquet, not args.no_scores)
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
    outcome.done(
        f"{len(overlays)} 条叠加轨迹写到 {provenance.relative_path(args.out_dir)}，"
        f"每条 {copies} 份拷贝、{len(weeks)} 个整周"
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, default=ROOT / "configs" / "main.yaml")
    ap.add_argument(
        "--pool",
        default=None,
        help="default: primary, or the pool named in "
        "overlay.single_server when --single-server is given",
    )
    ap.add_argument("--overlays", default=None)
    ap.add_argument(
        "--out-dir", type=Path, default=None, help="default: data.overlay_dir of the config"
    )
    ap.add_argument(
        "--single-server",
        action="store_true",
        help="build the k = 1 trace, from --pool when one is given",
    )
    ap.add_argument(
        "--score-parquet",
        type=Path,
        default=None,
        help="scores to store in the trace, one row per prepared submission; "
        "default: data.score_predictions_file of the config",
    )
    ap.add_argument(
        "--no-scores",
        action="store_true",
        help="store no scores: the run attaches its own by job_row, which is how the "
        "sealed pool is built, its scores being fitted after its overlays",
    )
    ap.add_argument("--unseal", action="store_true")
    args = ap.parse_args()

    cfg = cfgmod.load(args.config)
    if args.out_dir is None:
        args.out_dir = cfg.data_path("overlay_dir")
    if args.pool is None:
        args.pool = cfg["overlay"]["single_server"]["pool"] if args.single_server else "primary"
    terms = pool_terms(cfg, args.pool)
    # Before the ledger row, not inside it: a refused read is not a read, and the row
    # would say the opposite.
    sealed.guard_semesters(terms, ROOT, unseal=args.unseal)
    overlays = (
        [int(x) for x in args.overlays.split(",")]
        if args.overlays
        else list(cfg["overlay"]["overlays"])
    )
    with sealed.recording(ROOT, "scripts/build_overlays.py", terms, args.unseal) as outcome:
        return build(cfg, args, terms, overlays, outcome)


if __name__ == "__main__":
    raise SystemExit(main())
