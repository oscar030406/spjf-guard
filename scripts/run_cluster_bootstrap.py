"""Class-term cluster bootstrap of the development comparison.

    uv run python scripts/run_cluster_bootstrap.py --resamples 100 --workers 3

The five development overlays copy the same class-terms many times each, so the weeks
of one overlay are not independent draws of anything a reader would generalise over.
Here the resampling unit is the class-term: each resample draws the primary pool's
class-terms with replacement, reruns the copy-count probe and the week set on that
draw, builds five overlays with fresh shift draws, and simulates FCFS, SJF, SPJF-E and
Guard(G) at the three loads.  The predictor and the Guard parameters stay fixed (the
package's original-clock spjf_e scores and the configured selection); refitting and
reselecting inside every resample is outside this run.

Resample -1 is the development pool with its own seed and must reproduce
outputs/dev_tables/main_cells.csv for every policy it shares with it.
"""

from __future__ import annotations

import argparse
import csv
import json
import multiprocessing as mp
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from build_overlays import prepare_everything  # noqa: E402
from spjf_guard import config as cfgmod  # noqa: E402
from spjf_guard.data import sealed  # noqa: E402
from spjf_guard.experiment import provenance  # noqa: E402
from spjf_guard.experiment.metrics import gap_closed, summarise  # noqa: E402
from spjf_guard.experiment.overlay import build_overlay, copies_probe, week_set  # noqa: E402
from spjf_guard.sim import Trace, simulate  # noqa: E402
from spjf_guard.sim.policy import fcfs, sjf, spjf  # noqa: E402

BOOT_SEED = 20260924
_STATE: dict[str, Any] = {}


def _initialize(config_path: Path, pool_terms: list[str], scores_path: Path) -> None:
    import pandas as pd

    cfg = cfgmod.load(config_path)
    _, inputs = prepare_everything(cfg, pool_terms, unseal=False)
    frame = pd.read_parquet(scores_path)
    _STATE.update(cfg=cfg, inputs=inputs, score=frame["spjf_e"].to_numpy("float64"))


def _draw(b: int, pool: list[str]) -> tuple[list[str], int]:
    seed = int(_STATE["cfg"]["overlay"]["seed"])
    if b < 0:
        return list(pool), seed
    rng = np.random.default_rng(BOOT_SEED + b)
    return [pool[i] for i in rng.integers(0, len(pool), len(pool))], seed + 1000 * (b + 1)


def _policies(cfg, servers: int) -> list:
    out = [fcfs(), sjf(), spjf("spjf_e", "SPJF-E")]
    for promise in cfg.promises_s:
        out.append(
            cfg._guard_from(cfg.selected(promise), promise, servers, f"Guard({promise:g})")
        )
    return out


def _cell_rows(b, overlay, arrays, cfg) -> list[dict[str, Any]]:
    window = int(cfg["run"]["segment_tree_window_ranks"])
    score = _STATE["score"][arrays["job_row"]]
    trace = Trace.from_seconds(arrays["a"], arrays["svc"], {"spjf_e": score}, cfg.limit_s)
    in_window = arrays["dl"].astype(bool)
    heavy = arrays["hvt"].astype(bool)
    rows = []
    for level, servers in enumerate(int(k) for k in arrays["K"]):
        outcomes = [simulate(trace, p, servers, window=window) for p in _policies(cfg, servers)]
        base = summarise(outcomes[0], outcomes[0].wait_us, in_window, heavy).p99_dl_s
        target = summarise(outcomes[1], outcomes[0].wait_us, in_window, heavy).p99_dl_s
        for outcome in outcomes:
            stats = summarise(outcome, outcomes[0].wait_us, in_window, heavy)
            rows.append(
                {
                    "resample": b,
                    "overlay": overlay,
                    "level": level,
                    "k": servers,
                    "policy": outcome.policy,
                    "jobs": len(score),
                    "p99_dl_s": stats.p99_dl_s,
                    "harm_s": stats.as_row()["harm_s"],
                    "gap_closed": gap_closed(stats.p99_dl_s, base, target),
                }
            )
    return rows


def _resample(task: tuple[int, Path]) -> Path:
    b, out_dir = task
    path = out_dir / "resamples" / f"b{b}.json"
    if path.is_file():
        return path
    started = time.perf_counter()
    cfg, inputs = _STATE["cfg"], _STATE["inputs"]
    section = cfg["overlay"]
    probe = section["copies_probe"]
    overlays = tuple(section["overlays"])
    utilisations = section["target_busy_hour_utilisation"]
    pool, seed = _draw(b, inputs.pool)
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
        arrays = build_overlay(inputs, pool, copies, overlay, seed, weeks, utilisations)
        rows += _cell_rows(b, overlay, arrays, cfg)
        del arrays
    document = {"resample": b, "pool": pool, "seed": seed, "copies": copies, "rows": rows}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(document), encoding="utf-8")
    tmp.replace(path)
    print(f"resample {b}: {copies} copies, {time.perf_counter() - started:.0f} s", flush=True)
    return path


def _overlay_means(rows: list[dict[str, Any]]) -> dict[tuple[int, int, str], float]:
    """(resample, level, policy) -> mean over overlays of gap closed."""
    sums: dict[tuple[int, int, str], list[float]] = {}
    for row in rows:
        sums.setdefault((row["resample"], row["level"], row["policy"]), []).append(
            row["gap_closed"]
        )
    return {key: float(np.mean(values)) for key, values in sums.items()}


def _summary(rows: list[dict[str, Any]], promises: list[float]) -> list[dict[str, Any]]:
    means = _overlay_means(rows)
    resamples = sorted({b for b, _, _ in means if b >= 0})
    out = []
    contrasts = [(p, None) for p in ["SPJF-E"] + [f"Guard({g:g})" for g in promises]]
    contrasts += [(f"Guard({g:g})", "SPJF-E") for g in promises]
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


def _check_identity(rows: list[dict[str, Any]], dev_cells: Path) -> int:
    with open(dev_cells, encoding="utf-8", newline="") as handle:
        dev = {
            (int(r["overlay"]), int(r["level"]), r["policy"]): float(r["p99_dl_s"])
            for r in csv.DictReader(handle)
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


def _write(rows: list[dict[str, Any]], path: Path) -> Path:
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, default=ROOT / "configs" / "main.yaml")
    ap.add_argument("--resamples", type=int, default=100)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--out-dir", type=Path, default=ROOT / "outputs" / "cluster_bootstrap")
    ap.add_argument(
        "--dev-cells", type=Path, default=ROOT / "outputs" / "dev_tables" / "main_cells.csv"
    )
    args = ap.parse_args()
    cfg = cfgmod.load(args.config)
    terms = list(cfg["overlay"]["pools"]["primary"])
    sealed.guard_semesters(terms, ROOT, unseal=False)
    scores = cfg.data_path("score_dir", "forward_scores.parquet")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    tasks = [(b, args.out_dir) for b in range(-1, args.resamples)]
    with sealed.recording(ROOT, "scripts/run_cluster_bootstrap.py", terms, False) as outcome:
        with ProcessPoolExecutor(
            max_workers=args.workers,
            mp_context=mp.get_context("spawn"),
            initializer=_initialize,
            initargs=(args.config, terms, scores),
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
            produced_by="scripts/run_cluster_bootstrap.py",
            config_path=args.config,
            outputs=written,
            inputs=[scores, args.dev_cells],
            arguments={"resamples": args.resamples, "workers": args.workers},
            notes={
                "unit": "class-term of the primary pool, drawn with replacement",
                "held_fixed": "predictor weights (spjf_e) and the configured Guard selection",
                "identity_rows_checked": checked,
            },
        )
        outcome.done(f"{args.resamples} class-term resamples; {checked} identity rows equal")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
