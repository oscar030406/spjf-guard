"""Class-term cluster bootstrap of the online replay.

    uv run python scripts/run_online_cluster_bootstrap.py --resamples 100 --workers 3
    uv run python scripts/run_online_cluster_bootstrap.py --pool sealed --unseal \
        --resamples 100 --workers 8

The resamples are those of scripts/run_cluster_bootstrap.py: the same draws of the
primary pool's class-terms with replacement, the same seeds, copy-count probe, week set
and five overlays.  What changes is the replay: SPJF-E and Guard(G) are replayed online
(experiment.online_replay.replay_online, every score computed at the job's arrival from
the own-copy outcomes completed by then) with the frozen expected-cost weights, instead
of on source-clock scores.  FCFS and SJF read no score and are the references.

A draw can hold a class-term more than once.  The online history keys a copy by
(class-term, round), and two copies of one class-term in one round would share their
outcomes; so each occurrence gets a round of its own (`distinct_rounds`).  With no
repeated class-term, as in resample -1, the rounds are the overlay's own.

Resample -1 is the development pool and must reproduce, cell by cell, the online rows of
outputs/dev_online_visibility/online_cells.csv.  Each (resample, overlay) is written on
its own, so an interrupted run continues where it stopped.

With `--pool sealed --unseal` the draws are taken in the same way from the class-terms of
the sealed pool, after the sealed run and as an analysis of its uncertainty: the scores are
the frozen sealed scores, nothing is selected, and resample -1 must reproduce
outputs/sealed_online_visibility/online_cells.csv.  The read is refused without a frozen
protocol lock and is recorded in docs/sealed_access_log.md.
"""

from __future__ import annotations

import argparse
import csv
import json
import multiprocessing as mp
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from build_overlays import clock_from  # noqa: E402
from run_cluster_bootstrap import BOOT_SEED, _write  # noqa: E402
from run_consistent_visibility import prepare_context  # noqa: E402
from spjf_guard import config as cfgmod  # noqa: E402
from spjf_guard.data import sealed  # noqa: E402
from spjf_guard.data.events import (  # noqa: E402
    arrival_and_availability,
    static_submission_columns,
)
from spjf_guard.experiment import provenance  # noqa: E402
from spjf_guard.experiment.metrics import gap_closed, summarise  # noqa: E402
from spjf_guard.experiment.online import build_online_index  # noqa: E402
from spjf_guard.experiment.online_replay import replay_online  # noqa: E402
from spjf_guard.experiment.overlay import (  # noqa: E402
    build_overlay,
    copies_probe,
    pool_inputs,
    week_set,
)
from spjf_guard.sim import Trace, simulate  # noqa: E402
from spjf_guard.sim.bounds import assert_per_job_bounds  # noqa: E402
from spjf_guard.sim.policy import fcfs, sjf, spjf  # noqa: E402

VARIANT = "online"
_STATE: dict[str, Any] = {}


def distinct_rounds(copy_entry: np.ndarray, pool: list[str]) -> np.ndarray:
    """A round per copy such that (class-term, round) names exactly one copy.

    `copy_entry` is round * len(pool) + position; a class-term's j-th occurrence in the
    pool goes to round * m + j, m being the largest number of occurrences.
    """
    occurrence = np.zeros(len(pool), np.int64)
    seen: dict[str, int] = {}
    for position, term in enumerate(pool):
        occurrence[position] = seen.get(term, 0)
        seen[term] = occurrence[position] + 1
    m = max(seen.values())
    entry = copy_entry.astype(np.int64)
    return (entry // len(pool) * m + occurrence[entry % len(pool)]).astype(np.int32)


def _initialize(
    config_path: Path, pool_terms: list[str], scores_path: Path, unseal: bool
) -> None:
    cfg = cfgmod.load(config_path)
    context = prepare_context(
        cfg, SimpleNamespace(unseal=unseal, scores=scores_path), pool_terms
    )
    context["online_index"] = build_online_index(context["recomputer"])
    # The pool inputs as build_overlays.prepare_everything derives them, from the same
    # prepared rows the replay reads.
    prepared = context["prepared"]
    rows = prepared.submission_rows
    arrival, _ = arrival_and_availability(prepared, clock_from(cfg))
    header = (
        (prepared.timestamp_s + prepared.jitter_u)[rows]
        if cfg["clock"]["jitter"]["enabled"]
        else prepared.timestamp_s[rows]
    )
    inputs = pool_inputs(
        prepared,
        static_submission_columns(context["events"], prepared),
        arrival[rows],
        header,
        pool_terms,
        cfg.limit_s,
        float(cfg["metrics"]["deadline_window_s"]),
    )
    _STATE.update(cfg=cfg, context=context, inputs=inputs)


def _draw(b: int, pool: list[str], seed: int) -> tuple[list[str], int]:
    """run_cluster_bootstrap._draw, with the configured seed passed in."""
    if b < 0:
        return list(pool), seed
    rng = np.random.default_rng(BOOT_SEED + b)
    return [pool[i] for i in rng.integers(0, len(pool), len(pool))], seed + 1000 * (b + 1)


def _policies(cfg, servers: int) -> list:
    out = [spjf("spjf_e", "SPJF-E")]
    for promise in cfg.promises_s:
        out.append(
            cfg._guard_from(cfg.selected(promise), promise, servers, f"Guard({promise:g})")
        )
    return out


def _saved_rows(checkpoint: Path | None) -> dict:
    """Rows a stopped job already wrote to its checkpoint, by (level, policy)."""
    if checkpoint is None or not checkpoint.is_file():
        return {}
    saved = json.loads(checkpoint.read_text(encoding="utf-8"))["rows"]
    return {(row["level"], row["policy"]): row for row in saved}


def _policy_row(job: dict, level: int, servers: int, policy, first, reference, target) -> dict:
    cfg, context = _STATE["cfg"], _STATE["context"]
    result = replay_online(
        job["trace"],
        replace(policy, score_key=VARIANT),
        servers,
        job["window"],
        job["replay_arrays"],
        context["online_index"],
        context["recomputer"],
        context["models"],
        context["baseline_history"],
        job["base"],
    )
    outcome = replace(result.outcome, policy=policy.name)
    if policy.wrapper != "none":
        assert_per_job_bounds(outcome, first.wait_us, policy, servers, cfg.limit_s)
    stats = summarise(outcome, first.wait_us, job["in_window"], job["heavy"])
    return {
        "resample": job["b"],
        "overlay": job["overlay"],
        "level": level,
        "k": servers,
        "policy": f"{policy.name}|{VARIANT}",
        "jobs": len(job["base"]),
        "p99_dl_s": stats.p99_dl_s,
        "harm_s": stats.as_row()["harm_s"],
        "gap_closed": gap_closed(stats.p99_dl_s, reference, target),
        "pauses": result.pauses,
    }


def _overlay_rows(
    b: int, overlay: int, arrays: dict, pool: list[str], checkpoint: Path | None = None
) -> list[dict]:
    """With `checkpoint`, the rows so far are rewritten there after each (level, policy) and
    the rows found there are reused, so a job stopped with its machine resumes at that row
    (each row is computed from the trace alone, not from the rows before it)."""
    cfg = _STATE["cfg"]
    done = _saved_rows(checkpoint)
    window = int(cfg["run"]["segment_tree_window_ranks"])
    job_row = arrays["job_row"].astype(np.int64)
    base = _STATE["context"]["base_score"][job_row]
    trace = Trace.from_seconds(arrays["a"], arrays["svc"], {VARIANT: base}, cfg.limit_s)
    replay_arrays = {
        "arrival_us": trace.arrival_us,
        "service_us": trace.service_us,
        "job_row": job_row,
        "copy_entry": arrays["copy_entry"].astype(np.int32),
        "copy_round": distinct_rounds(arrays["copy_entry"], pool),
    }
    in_window, heavy = arrays["dl"].astype(bool), arrays["hvt"].astype(bool)
    job = {"b": b, "overlay": overlay, "trace": trace, "window": window, "base": base,
           "replay_arrays": replay_arrays, "in_window": in_window, "heavy": heavy}
    rows = []
    for level, servers in enumerate(int(k) for k in arrays["K"]):
        policies = _policies(cfg, servers)
        keys = [(level, f"{policy.name}|{VARIANT}") for policy in policies]
        if all(key in done for key in keys):
            rows += [done[key] for key in keys]
            continue
        first = simulate(trace, fcfs(), servers, window=window)
        target = summarise(
            simulate(trace, sjf(), servers, window=window), first.wait_us, in_window, heavy
        ).p99_dl_s
        reference = summarise(first, first.wait_us, in_window, heavy).p99_dl_s
        for policy, key in zip(policies, keys):
            if key in done:
                rows.append(done[key])
                continue
            rows.append(_policy_row(job, level, servers, policy, first, reference, target))
            if checkpoint is not None:
                _atomic(checkpoint, {"rows": rows})
    return rows


def _resample(task: tuple[int, Path]) -> Path:
    b, out_dir = task
    path = out_dir / "resamples" / f"b{b}.json"
    if path.is_file():
        return path
    cfg, inputs = _STATE["cfg"], _STATE["inputs"]
    section = cfg["overlay"]
    probe = section["copies_probe"]
    overlays = tuple(section["overlays"])
    utilisations = section["target_busy_hour_utilisation"]
    pool, seed = _draw(b, inputs.pool, int(section["seed"]))
    copies, _ = copies_probe(
        pool,
        inputs.per_term,
        "arr",
        overlays,
        seed,
        utilisations,
        int(probe["min_servers_at_full_load"]),
        int(probe["distinct_server_counts"]),
        int(probe["stop_after_extra_copies"]),
    )
    weeks = week_set(pool, inputs.per_term, "arr", copies, overlays, seed)
    rows = []
    for overlay in overlays:
        part = out_dir / "resamples" / f"b{b}_o{overlay}.json"
        if not part.is_file():
            started = time.perf_counter()
            arrays = build_overlay(inputs, pool, copies, overlay, seed, weeks, utilisations)
            _atomic(part, {"rows": _overlay_rows(b, overlay, arrays, pool)})
            del arrays
            print(
                f"resample {b} overlay {overlay}: {time.perf_counter() - started:.0f} s",
                flush=True,
            )
        rows += json.loads(part.read_text(encoding="utf-8"))["rows"]
    _atomic(path, {"resample": b, "pool": pool, "seed": seed, "copies": copies, "rows": rows})
    return path


def _atomic(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(document), encoding="utf-8")
    tmp.replace(path)


def _check_identity(rows: list[dict[str, Any]], dev_cells: Path) -> int:
    with open(dev_cells, encoding="utf-8", newline="") as handle:
        dev = {
            (int(r["overlay"]), int(r["level"]), r["policy"]): float(r["p99_dl_s"])
            for r in csv.DictReader(handle)
            if r["variant"] == VARIANT
        }
    checked = 0
    for row in rows:
        if row["resample"] != -1:
            continue
        expected = dev[(row["overlay"], row["level"], row["policy"])]
        if expected != row["p99_dl_s"]:
            raise AssertionError(f"resample -1 {row} does not reproduce {expected}")
        checked += 1
    return checked


def _summary(rows: list[dict[str, Any]], promises: list[float]) -> list[dict[str, Any]]:
    """Per level: each policy's gap closed and each Guard minus SPJF-E, as the mean over
    the overlays of a resample; the point is resample -1, the interval the resamples'."""
    sums: dict[tuple[int, int, str], list[float]] = {}
    for row in rows:
        sums.setdefault((row["resample"], row["level"], row["policy"]), []).append(
            row["gap_closed"]
        )
    means = {key: float(np.mean(values)) for key, values in sums.items()}
    resamples = sorted({b for b, _, _ in means if b >= 0})
    spjf_name = f"SPJF-E|{VARIANT}"
    guards = [f"Guard({g:g})|{VARIANT}" for g in promises]
    contrasts = [(p, None) for p in [spjf_name, *guards]] + [(g, spjf_name) for g in guards]
    out = []
    for level in sorted({lv for _, lv, _ in means}):
        for policy, minus in contrasts:

            def value(b, policy=policy, minus=minus, level=level):
                gap = means[(b, level, policy)]
                return gap - means[(b, level, minus)] if minus else gap

            draws = np.array([value(b) for b in resamples])
            out.append(
                {
                    "level": level,
                    "quantity": f"{policy} - {minus}" if minus else policy,
                    "point": value(-1),
                    "resamples": len(draws),
                    "lo": float(np.quantile(draws, 0.025)),
                    "hi": float(np.quantile(draws, 0.975)),
                    "sd": float(draws.std(ddof=1)),
                }
            )
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, default=ROOT / "configs" / "main.yaml")
    ap.add_argument("--resamples", type=int, default=100)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--pool", choices=("primary", "sealed"), default="primary")
    ap.add_argument("--unseal", action="store_true")
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument(
        "--dev-cells",
        type=Path,
        default=None,
        help="online cells that resample -1 must reproduce; default: the pool's own",
    )
    args = ap.parse_args()
    cfg = cfgmod.load(args.config)
    terms = list(cfg["overlay"]["pools"][args.pool])
    sealed.guard_semesters(terms, ROOT, unseal=args.unseal)
    is_sealed = args.pool == "sealed"
    scores = cfg.data_path(
        "score_dir", "sealed_scores.parquet" if is_sealed else "forward_scores.parquet"
    )
    args.out_dir = args.out_dir or ROOT / "outputs" / (
        "sealed_online_cluster_bootstrap" if is_sealed else "online_cluster_bootstrap"
    )
    args.dev_cells = args.dev_cells or ROOT / "outputs" / (
        "sealed_online_visibility" if is_sealed else "dev_online_visibility"
    ) / "online_cells.csv"
    args.out_dir.mkdir(parents=True, exist_ok=True)
    tasks = [(b, args.out_dir) for b in range(-1, args.resamples)]
    script = "scripts/run_online_cluster_bootstrap.py"
    with sealed.recording(ROOT, script, terms, args.unseal) as outcome:
        with ProcessPoolExecutor(
            max_workers=args.workers,
            mp_context=mp.get_context("spawn"),
            initializer=_initialize,
            initargs=(args.config, terms, scores, args.unseal),
        ) as executor:
            paths = list(executor.map(_resample, tasks, chunksize=1))
        documents = [json.loads(p.read_text(encoding="utf-8")) for p in paths]
        rows = [row for d in documents for row in d["rows"]]
        checked = _check_identity(rows, args.dev_cells)
        written = [
            _write(rows, args.out_dir / "bootstrap_cells.csv"),
            _write(_summary(rows, cfg.promises_s), args.out_dir / "bootstrap_summary.csv"),
            _write(
                [
                    {"resample": d["resample"], "copies": d["copies"], "seed": d["seed"]}
                    | {"pool": " ".join(d["pool"])}
                    for d in documents
                ],
                args.out_dir / "bootstrap_draws.csv",
            ),
        ]
        provenance.write(
            args.out_dir,
            produced_by=script,
            config_path=args.config,
            outputs=written,
            inputs=[scores, args.dev_cells],
            arguments={
                "resamples": args.resamples,
                "workers": args.workers,
                "pool": args.pool,
                "unseal": args.unseal,
            },
            notes={
                "unit": f"class-term of the {args.pool} pool, drawn with replacement",
                "replay": "online (replay_online), frozen expected-cost weights",
                "held_fixed": "predictor weights and the configured Guard selection",
                "identity_rows_checked": checked,
            },
        )
        outcome.done(f"{args.resamples} online class-term resamples; {checked} identity rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
