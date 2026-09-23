"""Predeclared stratified timing sample for a full exact-score validation selection.

Each grid stratum supplies one uniformly sampled candidate and one independently
uniformly sampled validation cell. The timing estimator expands each measured complete
refinement by its stratum size and all 15 cells. Dividing by two is an optimistic
two-worker wall-time projection, excluding loading, references and model fitting.
No timing-sample result selects a scheduling parameter.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from run_consistent_visibility import prepare_context  # noqa: E402
from spjf_guard import config as cfgmod  # noqa: E402
from spjf_guard.experiment import grids, provenance  # noqa: E402
from spjf_guard.experiment.consistent import refine_policy  # noqa: E402
from spjf_guard.experiment.metrics import summarise  # noqa: E402
from spjf_guard.experiment.report import write_csv  # noqa: E402
from spjf_guard.experiment.reproduce import load_overlay  # noqa: E402
from spjf_guard.sim import Trace, simulate  # noqa: E402
from spjf_guard.sim.bounds import assert_per_job_bounds  # noqa: E402
from spjf_guard.sim.policy import Policy, aging, fcfs  # noqa: E402

def timing_plan(cfg: cfgmod.Config) -> list[dict[str, Any]]:
    """Twelve uniformly sampled points, stratified before looking at any new outcome."""
    points = grids.grid_points(cfg["scheduling"]["selection"]["grids"], cfg.promises_s)
    strata: dict[str, list[dict[str, Any]]] = {}
    fixed = [asdict(point) for point in points if point.family == grids.FIXED]
    for number, indices in enumerate(np.array_split(np.arange(len(fixed)), 3)):
        strata[f"fixed_{number}"] = [fixed[index] for index in indices]
    for family in (grids.CAPPED, grids.HYBRID):
        for promise in cfg.promises_s:
            strata[f"{family}_{promise:g}"] = [
                asdict(point)
                for point in points
                if point.family == family and point.promise_s == promise
            ]
    credits = cfg["scheduling"]["aging_baseline"]["credit_per_s_grid"]
    for number, indices in enumerate(np.array_split(np.arange(len(credits)), 3)):
        strata[f"aging_{number}"] = [
            {
                "family": "aging",
                "credit": float(credits[index]),
                "name": f"aging-{credits[index]:g}",
            }
            for index in indices
        ]
    settings = cfg["features"]["exact_visibility"]
    rng = np.random.default_rng(int(settings["selection_cost_seed"]))
    return [
        {
            "stratum": name,
            "stratum_size": len(candidates),
            "point": candidates[int(rng.integers(len(candidates)))],
            "overlay": int(rng.integers(5)),
            "level": int(rng.integers(3)),
        }
        for name, candidates in strata.items()
    ]


def _policy(cfg: cfgmod.Config, point: dict[str, Any], servers: int) -> Policy:
    if point["family"] == "aging":
        return aging("exact", point["credit"], point["name"])
    return grids.policy_for(
        grids.GridPoint(**point), servers, cfg.limit_s, "exact", cfg.promises_s
    )


def _measure(
    cfg: cfgmod.Config, args: argparse.Namespace, context: dict, item: dict[str, Any]
) -> tuple[dict, list[dict]]:
    path = args.overlay_dir / f"validation_rep{item['overlay']}.npz"
    trace, servers, labels = load_overlay(path, item["level"], {}, cfg.limit_s)
    with np.load(path) as data:
        arrays = {
            "arrival_us": trace.arrival_us,
            "service_us": trace.service_us,
            "job_row": data["job_row"].astype(np.int64),
            "copy_entry": data["copy_entry"].astype(np.int32),
            "copy_round": data["copy_round"].astype(np.int32),
        }
    scores = context["base_score"][arrays["job_row"]]
    trace = Trace(trace.arrival_us, trace.service_us, {"exact": scores}, trace.limit_s)
    window = int(cfg["run"]["segment_tree_window_ranks"])
    reference = simulate(trace, fcfs(), servers, window=window)
    policy = _policy(cfg, item["point"], servers)
    started = perf_counter()
    result = refine_policy(
        trace,
        policy,
        servers,
        window,
        arrays,
        context["same_copy"],
        context["recomputer"],
        context["models"],
        context["baseline_history"],
        scores,
        "exact",
        pool_terms=context["pool_terms"],
    )
    elapsed = perf_counter() - started
    if policy.wrapper != "none":
        assert_per_job_bounds(result.outcome, reference.wait_us, policy, servers, cfg.limit_s)
    stats = summarise(
        result.outcome, reference.wait_us, labels["in_window"], labels["is_heavy"]
    )
    row = {key: value for key, value in item.items() if key != "point"}
    row.update(
        policy=policy.name,
        family=item["point"]["family"],
        k=servers,
        jobs=len(trace),
        passes=len(result.passes),
        seconds=elapsed,
        affected_share=len(result.changed_jobs) / len(trace),
        terminal_violations=0,
        p99_dl_s=stats.p99_dl_s,
        harm_s=stats.harm_s,
    )
    passes = [{"stratum": item["stratum"], **asdict(value)} for value in result.passes]
    return row, passes


def _projection(cfg: cfgmod.Config, rows: list[dict]) -> dict:
    points = grids.grid_points(cfg["scheduling"]["selection"]["grids"], cfg.promises_s)
    # Expanded-grid weighting is transparent; also report the known schedule-dedup
    # saving as a separate optimistic estimate, never as a measured run time.
    distinct = len({grids.schedule_key(p, 4, cfg.limit_s, cfg.promises_s) for p in points})
    guard = sum(
        row["stratum_size"] * row["seconds"] for row in rows if row["family"] != "aging"
    )
    aging_s = sum(
        row["stratum_size"] * row["seconds"] for row in rows if row["family"] == "aging"
    )
    optimistic_s = 15 * (guard * distinct / len(points) + aging_s) / 2
    budget_hours = float(cfg["features"]["exact_visibility"]["reselection_budget_hours"])
    return {
        "expanded_guard_candidates": len(points),
        "distinct_guard_schedules_k4": distinct,
        "aging_candidates": len(cfg["scheduling"]["aging_baseline"]["credit_per_s_grid"]),
        "validation_cells": 15,
        "workers": 2,
        "sample_refinements": len(rows),
        "measured_refinement_seconds": sum(row["seconds"] for row in rows),
        "expanded_grid_serial_seconds": 15 * (guard + aging_s),
        "optimistic_deduplicated_two_worker_hours": optimistic_s / 3600,
        "budget_hours": budget_hours,
        "full_reselection_fits": optimistic_s <= budget_hours * 3600,
        "parameters_changed_by_this_assessment": False,
        "caveat": "Stratified runtime estimate, not a confidence bound; assumes ideal "
        "two-worker speedup and excludes loading, fitting and reference overhead.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=ROOT / "configs/main.yaml")
    parser.add_argument(
        "--out-dir", type=Path, default=ROOT / "outputs/consistent_selection_assessment"
    )
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args()
    if args.workers != 2:
        parser.error("the timing assessment pins --workers 2")
    cfg = cfgmod.load(args.config)
    seed = int(cfg["features"]["exact_visibility"]["selection_cost_seed"])
    args.scores = cfg.data_path("score_dir", "forward_scores.parquet")
    args.overlay_dir = cfg.data_path("overlay_dir")
    args.unseal = False
    plan: dict[str, Any] = {
        "seed": seed,
        "purpose": "timing only; no parameter selection",
        "sampling": "one uniform candidate and independent uniform cell per stratum",
        "sample": timing_plan(cfg),
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    plan_path = args.out_dir / "timing_plan.json"
    if plan_path.exists() and json.loads(plan_path.read_text(encoding="utf-8")) != plan:
        raise ValueError("refusing to overwrite a different predeclared timing plan")
    plan_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    if args.plan_only:
        print(json.dumps(plan, indent=2))
        return 0
    context = prepare_context(cfg, args, list(cfg["overlay"]["pools"]["validation"]))
    implementation = {
        name: provenance.sha256_file(ROOT / name)
        for name in (
            "src/spjf_guard/experiment/consistent.py",
            "src/spjf_guard/experiment/visibility.py",
            "src/spjf_guard/features/refine.py",
            "src/spjf_guard/predict/forward.py",
        )
    }
    rows, passes = [], []
    started = perf_counter()
    for item in plan["sample"]:
        row, detail = _measure(cfg, args, context, item)
        rows.append(row)
        passes.extend(detail)
        write_csv(rows, args.out_dir / "timing_cells.csv")
        write_csv(passes, args.out_dir / "timing_passes.csv")
        print(f"{row['stratum']}: {row['passes']} passes, {row['seconds']:.1f} s", flush=True)
    projection = _projection(cfg, rows)
    projection["assessment_seconds_excluding_fit"] = perf_counter() - started
    projection["implementation_sha256"] = implementation
    projected_path = args.out_dir / "cost_projection.json"
    projected_path.write_text(json.dumps(projection, indent=2) + "\n", encoding="utf-8")
    provenance.write(
        args.out_dir,
        produced_by="scripts/assess_consistent_selection.py",
        config_path=args.config,
        outputs=[
            plan_path,
            args.out_dir / "timing_cells.csv",
            args.out_dir / "timing_passes.csv",
            projected_path,
        ],
        inputs=[args.scores],
        arguments={"workers": 2, "seed": seed},
    )
    print(json.dumps(projection, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
