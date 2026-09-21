"""Run the frozen policy-consistent visibility comparison and exposure audit.

    uv run python scripts/run_visibility.py --pool primary \
        --scores data/derived/package_ranking_scores/forward_scores.parquet \
        --out-dir outputs/dev_visibility --workers 2

The three score regimes see identical offered jobs and use the already selected guard
parameters.  ``original`` reproduces the original result clock, ``conservative`` uses
the pinned class-term-copy namespace and fixed lag, and ``static`` has no outcome-history
columns.  No parameter is selected here.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from build_overlays import clock_from  # noqa: E402
from fit_scores import load_prepared  # noqa: E402
from run_main import (  # noqa: E402
    REFERENCE,
    TARGET,
    aggregate,
    cell_rows,
    level_utilisation,
    paired_differences,
    paired_intervals,
)
from spjf_guard import config as cfgmod  # noqa: E402
from spjf_guard.data import sealed  # noqa: E402
from spjf_guard.data.events import arrival_and_availability  # noqa: E402
from spjf_guard.experiment import bootstrap as bs  # noqa: E402
from spjf_guard.experiment import parallel, provenance, visibility  # noqa: E402
from spjf_guard.experiment.metrics import summarise  # noqa: E402
from spjf_guard.experiment.report import write_csv  # noqa: E402
from spjf_guard.experiment.reproduce import load_overlay  # noqa: E402
from spjf_guard.sim import simulate  # noqa: E402
from spjf_guard.sim.policy import aging, fcfs, sjf, spjf  # noqa: E402

VARIANTS = ("original", "conservative", "static")
EXPECTED = "spjf_e"


def read_scores(path: Path, n_rows: int) -> dict[str, np.ndarray]:
    frame = pd.read_parquet(path)
    if len(frame) != n_rows:
        raise SystemExit(
            f"{path} has {len(frame):,} rows, but the prepared cache has {n_rows:,}"
        )
    wanted = {
        "original": EXPECTED,
        "conservative": f"{EXPECTED}_conservative",
        "static": f"{EXPECTED}_static",
    }
    missing = [column for column in wanted.values() if column not in frame]
    if missing:
        raise SystemExit(f"{path} is missing the visibility score column(s) {missing}")
    return {variant: frame[column].to_numpy("float64") for variant, column in wanted.items()}


def _guard(cfg, promise: float, servers: int, score: str, name: str):
    policy = cfg._guard_from(cfg.selected(promise), promise, servers, name)
    return replace(policy, score_key=score)


def policies(cfg, servers: int) -> list[tuple[str, object]]:
    """The unchanged selected method under each information regime."""
    out: list[tuple[str, object]] = [("reference", sjf())]
    for variant in VARIANTS:
        score = f"visibility_{variant}"
        suffix = "" if variant == "conservative" else f"-{variant}"
        out.append((variant, spjf(score, f"SPJF-E{suffix}")))
        for promise in cfg.promises_s:
            out.append(
                (
                    variant,
                    _guard(
                        cfg,
                        promise,
                        servers,
                        score,
                        f"Guard({promise:g}){suffix}",
                    ),
                )
            )
    section = cfg["scheduling"]["aging_baseline"]
    out.append(
        (
            "conservative",
            aging(
                "visibility_conservative",
                float(section["selected_credit_per_s"]),
                str(section["label"]),
            ),
        )
    )
    return out


def _tasks(cfg, servers, multiplicities) -> tuple[list[dict], dict[str, str]]:
    tasks = []
    variant_of = {REFERENCE: "reference", TARGET: "reference"}
    original_names = {"SPJF-E-original", *[f"Guard({g:g})-original" for g in cfg.promises_s]}
    for variant, policy in policies(cfg, servers):
        variant_of[policy.name] = variant
        tasks.append(
            {
                "tag": policy.name,
                "policy": policy,
                "servers": servers,
                "window": int(cfg["run"]["segment_tree_window_ranks"]),
                "limit_s": cfg.limit_s,
                "assert_bounds": bool(cfg["run"]["assert_per_job_bounds"]),
                "bootstrap": multiplicities,
                "diagnostics": True,
                "visibility_lag_s": conservative_lag(cfg),
                "exposure": policy.name in original_names,
            }
        )
    tasks.append(
        {
            "tag": "FCFS-exposure",
            "policy": fcfs(),
            "servers": servers,
            "window": int(cfg["run"]["segment_tree_window_ranks"]),
            "limit_s": cfg.limit_s,
            "assert_bounds": False,
            "exposure": True,
        }
    )
    return tasks, variant_of


def conservative_lag(cfg) -> float:
    return float(cfg["features"]["visibility_variants"]["conservative"]["delta_s"])


def _extra_arrays(store, history: visibility.HistoryIndex) -> dict[str, np.ndarray]:
    if "copy_round" not in store:
        raise SystemExit("overlay has no copy_round; rebuild it with scripts/build_overlays.py")
    rounds = store["copy_round"].astype(np.int32)
    if np.any(rounds < 0):
        raise SystemExit("the visibility audit requires the ordinary copy-major overlay")
    return {
        "job_row": store["job_row"].astype(np.int64),
        "copy_round": rounds,
        **history.arrays(),
    }


def _reference_payload(reference, labels, multiplicities):
    payload = {
        "summary": summarise(
            reference, reference.wait_us, labels["in_window"], labels["is_heavy"]
        ),
        "diagnostics": visibility.diagnostics(
            reference.wait_us, labels["in_window"], float("inf")
        ),
    }
    if multiplicities is not None:
        payload["replicates"] = parallel._bootstrap(
            reference.wait_us, labels["week"], multiplicities, labels["in_window"]
        )
    return payload


def _exposure_name(tag: str) -> str:
    return tag.removesuffix("-original").removesuffix("-exposure")


def _one_cell(cfg, args, history, overlay, level, multiplicities, scratch):
    path = args.overlay_dir / f"{args.pool}_rep{overlay}.npz"
    trace, servers, labels = load_overlay(path, level, {}, cfg.limit_s)
    scores = read_scores(args.scores, args.n_score_rows)
    with np.load(path) as store:
        labels["week"] = store["wk"].astype(np.int64)
        work_s = float(store["W"])
        rho_target = level_utilisation(cfg, level, servers, work_s, len(store["K"]))
        job_row = store["job_row"].astype(np.int64)
        extra = _extra_arrays(store, history)
    from spjf_guard.sim import Trace

    trace = Trace(
        trace.arrival_us,
        trace.service_us,
        {f"visibility_{name}": values[job_row] for name, values in scores.items()},
        trace.limit_s,
    )
    reference = simulate(
        trace,
        fcfs(),
        servers,
        window=int(cfg["run"]["segment_tree_window_ranks"]),
    )
    results = {REFERENCE: _reference_payload(reference, labels, multiplicities)}
    cell_dir = parallel.write_cell(
        scratch / f"cell_{overlay}_{level}",
        trace,
        labels,
        reference.wait_us,
        trace.scores,
        extra,
    )
    tasks, variant_of = _tasks(cfg, servers, multiplicities)
    exposure_rows, diagnostic_rows = [], []
    for tag, payload in parallel.map_policies(
        cell_dir, tasks, cfg.limit_s, tuple(trace.scores), args.workers
    ):
        if tag != "FCFS-exposure":
            results[tag] = payload
            diagnostic_rows.append(
                {
                    "overlay": overlay,
                    "level": level,
                    "k": servers,
                    "policy": tag,
                    "variant": variant_of[tag],
                    **payload["diagnostics"],
                }
            )
        if "exposure" in payload:
            exposure_rows.append(
                {
                    "overlay": overlay,
                    "level": level,
                    "k": servers,
                    "policy": _exposure_name(tag),
                    "variant": "original",
                    **payload["exposure"],
                }
            )
    shutil.rmtree(cell_dir, ignore_errors=True)
    diagnostic_rows.append(
        {
            "overlay": overlay,
            "level": level,
            "k": servers,
            "policy": REFERENCE,
            "variant": "reference",
            **visibility.diagnostics(
                reference.wait_us, labels["in_window"], conservative_lag(cfg)
            ),
        }
    )
    rows = cell_rows(cfg, results, overlay, level, servers, rho_target, work_s)
    for row in rows:
        row["variant"] = variant_of.get(row["policy"], "reference")
    replicates = {
        key: value.get("replicates") for key, value in results.items() if "replicates" in value
    }
    cell = {"overlay": overlay, "level": level, "replicates": replicates}
    return rows, cell, exposure_rows, diagnostic_rows


def _variant_pairs(cfg) -> list[tuple[str, str]]:
    bases = ["SPJF-E", *[f"Guard({g:g})" for g in cfg.promises_s]]
    return [(base, f"{base}-original") for base in bases] + [
        (base, f"{base}-static") for base in bases
    ]


def _write_outputs(cfg, args, rows, replicate_cells, exposure, diagnostics) -> list[Path]:
    policies = list(dict.fromkeys(row["policy"] for row in rows))
    levels = sorted({int(row["level"]) for row in rows})
    intervals = paired_intervals(replicate_cells, policies, levels)
    table = aggregate(rows, intervals)
    for row in table:
        source = next(item for item in rows if item["policy"] == row["policy"])
        row["variant"] = source["variant"]
    differences = paired_differences(replicate_cells, _variant_pairs(cfg), levels)
    written = [
        write_csv(rows, args.out_dir / "visibility_cells.csv"),
        write_csv(table, args.out_dir / "visibility_comparison.csv"),
        write_csv(differences, args.out_dir / "visibility_paired_differences.csv"),
        write_csv(exposure, args.out_dir / "visibility_exposure.csv"),
        write_csv(diagnostics, args.out_dir / "visibility_waits_and_lag.csv"),
    ]
    provenance.write(
        args.out_dir,
        produced_by="scripts/run_visibility.py",
        config_path=args.config,
        outputs=written,
        inputs=[
            *[
                args.overlay_dir / f"{args.pool}_rep{o}.npz"
                for o in (int(value) for value in args.reps.split(","))
            ],
            args.scores,
        ],
        arguments={
            "pool": args.pool,
            "reps": args.reps,
            "levels": args.levels,
            "scores": provenance.relative_path(args.scores),
            "workers": args.workers,
            "unseal": args.unseal,
        },
        notes={
            "headline_variant": cfg["features"]["headline_variant"],
            "conservative_lag_s": conservative_lag(cfg),
            "selected_parameters_unchanged": cfg["scheduling"]["selected"],
            "exposure_mapping": "same outer overlay round; unreplayed histories separate",
        },
    )
    return written


def produce(cfg, args, terms, outcome) -> int:
    started = time.time()
    events, prepared, _ = load_prepared(cfg, args.unseal)
    args.n_score_rows = len(prepared.submission_rows)
    arrival, availability = arrival_and_availability(prepared, clock_from(cfg, 0.0))
    history = visibility.build_history_index(prepared, arrival, availability, terms)
    del events, arrival, availability
    scratch = args.scratch or Path(tempfile.mkdtemp(prefix="spjf_visibility_"))
    rows: list[dict] = []
    replicate_cells: list[dict] = []
    exposure: list[dict] = []
    diagnostics: list[dict] = []
    multiplicities = None
    for overlay in (int(value) for value in args.reps.split(",")):
        for level in (int(value) for value in args.levels.split(",")):
            path = args.overlay_dir / f"{args.pool}_rep{overlay}.npz"
            with np.load(path) as store:
                n_weeks = len(store["weeks"])
            if multiplicities is None:
                multiplicities = bs.with_point_estimate(
                    bs.week_multiplicities(
                        n_weeks,
                        int(cfg["bootstrap"]["resamples"]),
                        int(cfg["bootstrap"]["seed"]),
                    )
                )
            cell = _one_cell(cfg, args, history, overlay, level, multiplicities, scratch)
            rows.extend(cell[0])
            replicate_cells.append(cell[1])
            exposure.extend(cell[2])
            diagnostics.extend(cell[3])
            print(
                f"overlay {overlay} level {level}: visibility comparison complete",
                flush=True,
            )
    if args.scratch is None:
        shutil.rmtree(scratch, ignore_errors=True)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    written = _write_outputs(cfg, args, rows, replicate_cells, exposure, diagnostics)
    outcome.done(
        f"策略一致可见性比较写到 {provenance.relative_path(args.out_dir)}，"
        f"耗时 {time.time() - started:.0f} 秒"
    )
    if args.pool == "sealed":
        complaint = provenance.pinned_outputs_complaint(
            cfg["run"]["sealed_visibility_tables"], written
        )
        if complaint:
            raise SystemExit(complaint)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, default=ROOT / "configs" / "main.yaml")
    ap.add_argument("--pool", default="primary")
    ap.add_argument("--overlay-dir", type=Path, default=None)
    ap.add_argument("--scores", type=Path, default=None)
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--reps", default="0,1,2,3,4")
    ap.add_argument("--levels", default="0,1,2")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--scratch", type=Path, default=None)
    ap.add_argument("--unseal", action="store_true")
    args = ap.parse_args()
    cfg = cfgmod.load(args.config)
    if args.pool not in cfg["overlay"]["pools"]:
        ap.error(f"unknown pool {args.pool!r}")
    terms = list(cfg["overlay"]["pools"][args.pool])
    sealed.guard_semesters(terms, ROOT, unseal=args.unseal)
    args.overlay_dir = args.overlay_dir or cfg.data_path("overlay_dir")
    default_score = (
        "sealed_scores.parquet" if args.pool == "sealed" else "forward_scores.parquet"
    )
    args.scores = args.scores or cfg.data_path("score_dir", default_score)
    default_out = "sealed_visibility" if args.pool == "sealed" else "dev_visibility"
    args.out_dir = args.out_dir or ROOT / "outputs" / default_out
    with sealed.recording(ROOT, "scripts/run_visibility.py", terms, args.unseal) as outcome:
        return produce(cfg, args, terms, outcome)


if __name__ == "__main__":
    raise SystemExit(main())
