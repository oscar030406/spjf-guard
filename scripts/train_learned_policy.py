"""A base scheduling policy trained for the schedule, not for the prediction.

    uv run python scripts/train_learned_policy.py features --out-dir <dir>
    uv run python scripts/train_learned_policy.py train --out-dir <dir> --workers 20

The guard's bound holds for any base order.  SPJF-E is a score trained for prediction
accuracy; this script trains a score for the scheduling objective itself.  The policy
serves the smallest

    score(job) = log spjf_e(job) + w . phi(job),

where phi are quantities known when the job arrives (FEATURES, standardised over the
validation pool's jobs).  The coefficient of log spjf_e is fixed at one because an order
does not change under positive scaling.  w is found by the cross-entropy method, a
direct policy search: sample weight vectors, simulate each one's schedules, refit the
sampling distribution to the best.  The return of a weight vector is the mean over the
15 validation cells (five validation overlays, three loads) of the fraction of the
deadline-window p99 gap closed, unguarded, on source-clock scores -- the cells and the
metric the Guard parameters were selected on.  Nothing here reads the primary pool's
last term or a sealed term.

`features` writes phi for every prepared submission (phi.npz); `train` writes the
search history (history.csv) and the final weights with the standardisation
(policy.json).
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

from spjf_guard import config as cfgmod  # noqa: E402
from spjf_guard.data import sealed  # noqa: E402
from spjf_guard.experiment import provenance  # noqa: E402
from spjf_guard.experiment.metrics import gap_closed, summarise  # noqa: E402
from spjf_guard.sim import Trace, simulate  # noqa: E402
from spjf_guard.sim.policy import fcfs, sjf, spjf  # noqa: E402

FEATURES = (
    "in_deadline_window",
    "log_hours_to_deadline",
    "in_exam",
    "remote",
    "log_chars",
    "log_loops",
    "log_defs",
)
SEARCH = {
    "seed": 20260927,
    "population": 24,
    "elite": 6,
    "iterations": 25,
    "initial_sd": 1.0,
    "smoothing": 0.7,
    "min_sd": 0.02,
}
"""Fixed before any search result was seen."""

POOL = "validation"
_STATE: dict[str, Any] = {}


def row_features(cfg) -> np.ndarray:
    """phi for every prepared submission, unstandardised, NaN where undefined."""
    from build_overlays import clock_from
    from fit_scores import load_prepared
    from spjf_guard.data.events import (
        CODE_COLUMNS,
        arrival_and_availability,
        static_submission_columns,
    )

    events, prepared, _ = load_prepared(cfg, False)
    static = static_submission_columns(events, prepared)
    arrival, _ = arrival_and_availability(prepared, clock_from(cfg))
    arrival = arrival[prepared.submission_rows]
    to_deadline = static["a_end"] - arrival
    window = float(cfg["metrics"]["deadline_window_s"])
    code = static["code"].astype(np.float64)
    column = {name: i for i, name in enumerate(CODE_COLUMNS)}
    exam = (
        (static["a_is_exam"] == 1)
        & (arrival >= static["a_start"])
        & (arrival <= static["a_end"])
    )
    phi = np.column_stack(
        [
            ((to_deadline <= window) & (to_deadline >= 0)).astype(np.float64),
            np.log1p(np.clip(to_deadline, 0.0, None) / 3600.0),
            exam.astype(np.float64),
            static["is_remote"].astype(np.float64),
            np.log1p(code[:, column["chars"]]),
            np.log1p(code[:, column["n_while"]] + code[:, column["n_for"]]),
            np.log1p(code[:, column["n_def"]]),
        ]
    )
    assert phi.shape[1] == len(FEATURES)
    return phi


def standardised(phi: np.ndarray, rows: np.ndarray) -> tuple[np.ndarray, dict]:
    """phi scaled by the mean and sd over `rows`; an undefined value becomes the mean."""
    mean = np.nanmean(phi[rows], axis=0)
    sd = np.nanstd(phi[rows], axis=0)
    if np.any(sd == 0):
        raise ValueError(f"constant feature over the pool: {np.array(FEATURES)[sd == 0]}")
    out = np.nan_to_num((phi - mean) / sd, nan=0.0)
    return out, {"mean": mean.tolist(), "sd": sd.tolist()}


def learned_score(
    spjf_e: np.ndarray, phi_std: np.ndarray, job_row: np.ndarray, weights: np.ndarray
) -> np.ndarray:
    """The policy's score of each job; `phi_std` is per submission, `job_row` per job."""
    return np.log(spjf_e) + (phi_std @ weights)[job_row]


def _overlay_path(cfg, overlay: int) -> Path:
    return cfg.data_path("overlay_dir") / f"{POOL}_rep{overlay}.npz"


def _initialize(config_path: Path, phi_path: Path) -> None:
    cfg = cfgmod.load(config_path)
    window = int(cfg["run"]["segment_tree_window_ranks"])
    with np.load(phi_path) as z:
        phi_std = z["phi_std"]
    cells = []
    for overlay in cfg["overlay"]["overlays"]:
        with np.load(_overlay_path(cfg, overlay)) as z:
            job_row = z["job_row"].astype(np.int64)
            trace = Trace.from_seconds(z["a"], z["svc"], {}, cfg.limit_s)
            labels = (z["dl"].astype(bool), z["hvt"].astype(bool))
            spjf_e, servers = z["tweedie"].astype(np.float64), [int(k) for k in z["K"]]
        for level, k in enumerate(servers):
            first = simulate(trace, fcfs(), k, window=window)
            reference = summarise(first, first.wait_us, *labels).p99_dl_s
            target = summarise(
                simulate(trace, sjf(), k, window=window), first.wait_us, *labels
            ).p99_dl_s
            cells.append((overlay, level, k, first.wait_us, reference, target))
        _STATE.setdefault("overlays", {})[overlay] = (trace, labels, spjf_e, job_row)
    _STATE.update(cfg=cfg, window=window, cells=cells, phi_std=phi_std)


def _evaluate(weights: list[float]) -> list[float]:
    """Gap closed in each validation cell under the score with these weights."""
    w = np.asarray(weights)
    out = []
    scored = {}
    for overlay, (trace, labels, spjf_e, job_row) in _STATE["overlays"].items():
        scored[overlay] = Trace(
            trace.arrival_us,
            trace.service_us,
            {"learned": learned_score(spjf_e, _STATE["phi_std"], job_row, w)},
            trace.limit_s,
        )
    for overlay, level, k, fcfs_wait, reference, target in _STATE["cells"]:
        labels = _STATE["overlays"][overlay][1]
        outcome = simulate(scored[overlay], spjf("learned"), k, window=_STATE["window"])
        p99 = summarise(outcome, fcfs_wait, *labels).p99_dl_s
        out.append(gap_closed(p99, reference, target))
    return out


def train(args, cfg) -> int:
    phi_path = args.out_dir / "phi.npz"
    rng = np.random.default_rng(SEARCH["seed"])
    d = len(FEATURES)
    mean, sd = np.zeros(d), np.full(d, SEARCH["initial_sd"])
    history = []
    with ProcessPoolExecutor(
        max_workers=args.workers,
        mp_context=mp.get_context("spawn"),
        initializer=_initialize,
        initargs=(args.config, phi_path),
    ) as executor:
        baseline = executor.submit(_evaluate, [0.0] * d).result()
        history.append(
            {"iteration": -1, "candidate": 0, "objective": np.mean(baseline)}
            | dict(zip(FEATURES, [0.0] * d))
        )
        print(f"SPJF-E (w = 0): {np.mean(baseline):.4f}", flush=True)
        for iteration in range(SEARCH["iterations"]):
            started = time.perf_counter()
            draws = mean + sd * rng.standard_normal((SEARCH["population"], d))
            gaps = list(executor.map(_evaluate, draws.tolist()))
            objective = np.array([np.mean(g) for g in gaps])
            for i, (w, value) in enumerate(zip(draws, objective)):
                history.append(
                    {"iteration": iteration, "candidate": i, "objective": value}
                    | dict(zip(FEATURES, w.tolist()))
                )
            elite = draws[np.argsort(-objective, kind="stable")[: SEARCH["elite"]]]
            a = SEARCH["smoothing"]
            mean = a * elite.mean(axis=0) + (1 - a) * mean
            sd = np.maximum(a * elite.std(axis=0) + (1 - a) * sd, SEARCH["min_sd"])
            print(
                f"iteration {iteration}: best {objective.max():.4f}, "
                f"elite mean {np.sort(objective)[-SEARCH['elite'] :].mean():.4f} "
                f"({time.perf_counter() - started:.0f} s)",
                flush=True,
            )
        final = executor.submit(_evaluate, mean.tolist()).result()
    with np.load(phi_path) as z:
        stats = {"mean": z["mean"].tolist(), "sd": z["sd"].tolist()}
    policy = {
        "features": list(FEATURES),
        "weights": mean.tolist(),
        "standardisation": stats,
        "search": SEARCH,
        "validation_gap_closed_mean": float(np.mean(final)),
        "validation_gap_closed_worst": float(np.min(final)),
        "spjf_e_validation_gap_closed_mean": float(np.mean(baseline)),
        "spjf_e_validation_gap_closed_worst": float(np.min(baseline)),
    }
    written = [
        _write_csv(history, args.out_dir / "history.csv"),
        _write_json(policy, args.out_dir / "policy.json"),
    ]
    provenance.write(
        args.out_dir,
        produced_by="scripts/train_learned_policy.py",
        config_path=args.config,
        outputs=written,
        inputs=[phi_path, *[_overlay_path(cfg, o) for o in cfg["overlay"]["overlays"]]],
        arguments={"action": "train", "workers": args.workers},
        notes={"objective": "mean gap closed over the 15 validation cells, unguarded"},
    )
    print(f"final weights {np.round(mean, 4).tolist()}: {np.mean(final):.4f}", flush=True)
    return 0


def features(args, cfg) -> int:
    phi = row_features(cfg)
    rows = np.unique(
        np.concatenate(
            [
                np.load(_overlay_path(cfg, o))["job_row"].astype(np.int64)
                for o in cfg["overlay"]["overlays"]
            ]
        )
    )
    phi_std, stats = standardised(phi, rows)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    path = args.out_dir / "phi.npz"
    np.savez(path, phi_std=phi_std, mean=np.array(stats["mean"]), sd=np.array(stats["sd"]))
    print(f"phi for {len(phi):,} submissions; standardised over {len(rows):,}", flush=True)
    return 0


def _write_csv(rows: list[dict], path: Path) -> Path:
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def _write_json(document: dict, path: Path) -> Path:
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")
    return path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=("features", "train"))
    ap.add_argument("--config", type=Path, default=ROOT / "configs" / "main.yaml")
    ap.add_argument("--out-dir", type=Path, default=ROOT / "outputs" / "learned_policy")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    cfg = cfgmod.load(args.config)
    terms = list(cfg["overlay"]["pools"][POOL])
    sealed.guard_semesters(terms, ROOT, unseal=False)
    script = "scripts/train_learned_policy.py"
    with sealed.recording(ROOT, script, terms, False) as outcome:
        code = features(args, cfg) if args.action == "features" else train(args, cfg)
        outcome.done(f"learned policy: {args.action}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
