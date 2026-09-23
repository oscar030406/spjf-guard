"""Run the decomposition and policy-specific exact-visibility experiment.

    uv run python scripts/run_consistent_visibility.py --pool primary --workers 2

The frozen original M4 model is refined independently in each overlay/load/policy
cell. Completed policies are checkpointed with content hashes, so an interrupted run
can resume without accepting stale scores or sparse deltas.
"""

from __future__ import annotations

import argparse
import csv
import gc
import multiprocessing as mp
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from build_overlays import clock_from  # noqa: E402
from consistent_cells import (  # noqa: E402
    CheckpointStore,
    artifact_entry,
    artifacts_valid,
    combined_hash,
    replicate_arrays,
    replicate_lists,
    sha256_file,
    signature,
)
from fit_scores import load_prepared  # noqa: E402
from run_main import aggregate, level_utilisation, paired_intervals  # noqa: E402
from spjf_guard import config as cfgmod  # noqa: E402
from spjf_guard.data import sealed  # noqa: E402
from spjf_guard.data.events import static_submission_columns  # noqa: E402
from spjf_guard.experiment import bootstrap as bs  # noqa: E402
from spjf_guard.experiment import parallel, provenance  # noqa: E402
from spjf_guard.experiment.consistent import (  # noqa: E402
    RefinementResult,
    distribution,
    effective_score,
    one_pass_score_changes,
    queue_rank_displacement,
    refine_policy,
)
from spjf_guard.experiment.metrics import (  # noqa: E402
    gap_closed,
    reduction_percent,
    summarise,
)
from spjf_guard.experiment.reproduce import load_overlay  # noqa: E402
from spjf_guard.experiment.visibility import build_same_copy_history_index  # noqa: E402
from spjf_guard.experiment.visibility_controls import (  # noqa: E402
    CONTROL_VARIANTS,
    LAGS_S,
    ControlBuild,
    build_control_set,
    cache_key_from_files,
    load_or_build_controls,
)
from spjf_guard.features.refine import M4HistoryRecomputer  # noqa: E402
from spjf_guard.predict.forward import fit_frozen_m4_models  # noqa: E402
from spjf_guard.sim import JobResults, Trace, simulate  # noqa: E402
from spjf_guard.sim.bounds import assert_per_job_bounds  # noqa: E402
from spjf_guard.sim.policy import MICROS, Policy, aging, fcfs, sjf, spjf  # noqa: E402

ORIGINAL = "original"
EXACT = "exact"
CONSERVATIVE = "conservative"
STATIC = "static"
OTHER_CLASS_EXACT = "exact_other_class_withheld"
HEADLINE_VARIANTS = (ORIGINAL, EXACT, CONSERVATIVE, STATIC)
TABLE_NAMES = (
    "exact_cells.csv",
    "exact_comparison.csv",
    "exact_passes.csv",
    "same_copy_exposure_cells.csv",
    "same_copy_exposure.csv",
    "attribution_cells.csv",
    "attribution_comparison.csv",
    "exact_delta_manifest.csv",
    "exact_costs.csv",
    "exact_sensitivity_cells.csv",
    "exact_sensitivity_comparison.csv",
)

_WORKER_STATE: dict[str, Any] | None = None
_WORKER_MODEL_SECONDS = 0.0
_WORKER_MODEL_REPORTED = False


def _guard(cfg: cfgmod.Config, promise: float, servers: int, score_key: str) -> Policy:
    policy = cfg._guard_from(cfg.selected(promise), promise, servers, f"Guard({promise:g})")
    return replace(policy, score_key=score_key)


def exact_policies(cfg: cfgmod.Config, servers: int, score_key: str) -> list[Policy]:
    section = cfg["scheduling"]["aging_baseline"]
    return [
        spjf(score_key, "SPJF-E"),
        *[_guard(cfg, promise, servers, score_key) for promise in cfg.promises_s],
        aging(score_key, float(section["selected_credit_per_s"]), str(section["label"])),
    ]


def _assert_protocol_config(cfg: cfgmod.Config) -> None:
    section = cfg["features"]["exact_visibility"]
    expected_settings = {
        "algorithm": "monotone_per_job_withholding",
        "base_score": "spjf_e",
        "model_weights": "frozen",
        "own_class_term_copy_outcome_rule": "completion_j <= replay_arrival_i",
        "external_history_clock": "original_relative",
        "same_semester_other_class_history": "exogenous",
        "alternative_sensitivity": "drop_same_semester_other_class_records",
        "terminal_assertion": "no_new_violation",
    }
    for key, expected_value in expected_settings.items():
        if section[key] != expected_value:
            raise ValueError(f"exact visibility {key} {section[key]!r} != {expected_value!r}")
    expected = [policy.name for policy in exact_policies(cfg, 1, EXACT)]
    if list(section["policies"]) != expected:
        raise ValueError(
            f"exact policy config {section['policies']} != implementation {expected}"
        )
    configured_lags = tuple(float(value) for value in section["fixed_lags_s"])
    if configured_lags != tuple(LAGS_S):
        raise ValueError(f"exact lag config {configured_lags} != implementation {LAGS_S}")
    if list(section["sensitivity_policies"]) != ["Guard(600)"]:
        raise ValueError("exact visibility sensitivity is pinned to Guard(600)")


def _score_frame(path: Path, n_rows: int) -> pd.DataFrame:
    frame = pd.read_parquet(path)
    if len(frame) != n_rows:
        raise SystemExit(f"{path} has {len(frame):,} rows; expected {n_rows:,}")
    needed = {"spjf_e", "spjf_e_conservative", "spjf_e_static"}
    missing = sorted(needed - set(frame))
    if missing:
        raise SystemExit(f"{path} is missing {missing}")
    return frame


def prepare_context(
    cfg: cfgmod.Config, args: argparse.Namespace, pool_terms: list[str]
) -> dict[str, Any]:
    events, prepared, all_terms = load_prepared(cfg, args.unseal)
    scores = _score_frame(args.scores, len(prepared.submission_rows))
    static = static_submission_columns(events, prepared)
    models, baseline_history, arrival, availability = fit_frozen_m4_models(
        prepared,
        static,
        clock_from(cfg, 0.0),
        cfg["predictor"],
        cfg.limit_s,
        pool_terms,
        all_terms,
        expected_scores=scores["spjf_e"].to_numpy("float64"),
    )
    recomputer = M4HistoryRecomputer(prepared, arrival, availability)
    targets = np.flatnonzero(np.isin(prepared.semester[prepared.submission_rows], pool_terms))
    sample = np.random.default_rng(20260922).choice(
        targets, min(512, len(targets)), replace=False
    )
    rebuilt = np.vstack(
        [recomputer.recompute(int(row), baseline_history[row]) for row in sample]
    )
    np.testing.assert_array_equal(rebuilt, baseline_history[sample])
    predicted = models.predict(sample, rebuilt)
    expected = scores["spjf_e"].to_numpy("float64")[sample]
    np.testing.assert_array_equal(predicted, expected)
    print(
        f"  targeted M4 baseline audit: {len(sample)} feature and score rows exactly equal",
        flush=True,
    )
    return {
        "events": events,
        "prepared": prepared,
        "scores": scores,
        "models": models,
        "baseline_history": baseline_history,
        "arrival": arrival,
        "availability": availability,
        "recomputer": recomputer,
        "same_copy": build_same_copy_history_index(prepared, arrival, availability, pool_terms),
        "base_score": scores["spjf_e"].to_numpy("float64"),
        "pool_terms": set(str(term) for term in pool_terms),
    }


def _source_paths(cfg: cfgmod.Config, unseal: bool) -> list[Path]:
    paths = [cfg.data_path("cache_dir", cfg["data"]["events_file"])]
    sealed_name = cfg["data"].get("sealed_events_file")
    if unseal and sealed_name:
        paths.append(cfg.data_path("cache_dir", sealed_name))
    return paths


def _control_build(
    cfg: cfgmod.Config,
    args: argparse.Namespace,
    context: dict[str, Any],
    pool_terms: list[str],
) -> ControlBuild:
    key = cache_key_from_files(
        _source_paths(cfg, args.unseal), args.scores, args.config, pool_terms
    )

    def progress(stage: str, complete: int, total: int) -> None:
        print(f"  {stage}: {complete:,}/{total:,}", flush=True)

    return load_or_build_controls(
        args.controls,
        key,
        lambda: build_control_set(context, progress=progress),
        rebuild_stale=args.rebuild_controls,
    )


def _trace_with_scores(
    trace: Trace, scores: dict[str, np.ndarray], job_row: np.ndarray
) -> Trace:
    return Trace(
        trace.arrival_us,
        trace.service_us,
        {name: values[job_row] for name, values in scores.items()},
        trace.limit_s,
    )


def _metric_row(
    outcome: JobResults,
    fcfs_wait: np.ndarray,
    labels: dict[str, np.ndarray],
    overlay: int,
    level: int,
    work_s: float,
    rho: float,
    variant: str,
    base_p99: float,
    target_p99: float,
) -> dict[str, Any]:
    stats = summarise(outcome, fcfs_wait, labels["in_window"], labels["is_heavy"])
    return {
        "overlay": overlay,
        "level": level,
        "k": outcome.servers,
        "rho_target": rho,
        "rho_realised": round(work_s / (3600.0 * outcome.servers), 6),
        "base_policy": outcome.policy,
        "variant": variant,
        **stats.as_row(),
        "policy": f"{outcome.policy}|{variant}",
        "fired_pct": 100.0 * stats.fired_fraction_queue_weighted,
        "gap_closed": gap_closed(stats.p99_dl_s, base_p99, target_p99),
        "reduction_pct": reduction_percent(stats.p99_dl_s, base_p99),
    }


def _replicates(
    outcome: JobResults,
    labels: dict[str, np.ndarray],
    multiplicities: np.ndarray,
) -> dict[str, np.ndarray]:
    return parallel._bootstrap(
        outcome.wait_us, labels["week"], multiplicities, labels["in_window"]
    )


def _pack_replicates(values: dict[str, dict[str, np.ndarray]]) -> dict[str, Any]:
    return {name: replicate_lists(replicates) for name, replicates in values.items()}


def _unpack_replicates(values: dict[str, Any]) -> dict[str, dict[str, np.ndarray]]:
    return {name: replicate_arrays(replicates) for name, replicates in values.items()}


def _corrected_effective_score(
    policy: Policy,
    trace: Trace,
    jobs: np.ndarray,
    corrected_score: np.ndarray,
) -> np.ndarray:
    """Return absolute corrected priority keys without reconstructing from deltas."""
    corrected = np.asarray(corrected_score, np.float64)
    if policy.age_credit_per_s == 0.0:
        return corrected
    arrival_s = (trace.arrival_us[jobs] - trace.arrival_us[0]) / MICROS
    return corrected + policy.age_credit_per_s * arrival_s


def _decomposition_row(
    policy: Policy,
    outcome: JobResults,
    jobs: np.ndarray,
    delta: np.ndarray,
    corrected_score: np.ndarray,
    counts: np.ndarray,
    trace: Trace,
    labels: dict[str, np.ndarray],
    overlay: int,
    level: int,
    score: np.ndarray,
) -> dict[str, Any]:
    window_jobs = labels["in_window"][jobs]
    rank = (
        np.empty(0, np.int64)
        if not len(jobs)
        else queue_rank_displacement(
            trace.arrival_us,
            outcome.start_us,
            effective_score(policy, trace, score),
            jobs,
            delta,
            dispatch_order=outcome.dispatch_order,
            corrected_score=_corrected_effective_score(policy, trace, jobs, corrected_score),
        )
    )
    row = {
        "overlay": overlay,
        "level": level,
        "k": outcome.servers,
        "policy": policy.name,
        "jobs": len(trace),
        "affected_jobs": len(jobs),
        "affected_share": len(jobs) / len(trace),
        "deadline_jobs": int(labels["in_window"].sum()),
        "deadline_affected_jobs": int(window_jobs.sum()),
        "deadline_affected_share": float(window_jobs.sum() / max(labels["in_window"].sum(), 1)),
    }
    row.update(distribution(counts, "records"))
    row.update(distribution(delta, "abs_delta_score", absolute=True))
    row.update(distribution(rank, "rank_displacement"))
    row.update(distribution(rank, "abs_rank_displacement", absolute=True))
    return row


def _delta_path(out_dir: Path, overlay: int, level: int, policy: str, variant: str) -> Path:
    from consistent_cells import checkpoint_slug

    return out_dir / "deltas" / f"o{overlay}_l{level}_{checkpoint_slug(policy)}_{variant}.npz"


def _save_delta(
    out_dir: Path,
    overlay: int,
    level: int,
    policy: str,
    variant: str,
    baseline_variant: str,
    result: RefinementResult,
) -> dict[str, Any]:
    path = _delta_path(out_dir, overlay, level, policy, variant)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        job_index=result.changed_jobs,
        score_delta=result.score_delta,
        corrected_score=result.corrected_score,
        withheld_count=result.withheld_counts,
    )
    return artifact_entry(
        path,
        out_dir,
        overlay=overlay,
        level=level,
        policy=policy,
        variant=variant,
        baseline_variant=baseline_variant,
        affected_jobs=len(result.changed_jobs),
    )


def _pass_rows(
    overlay: int,
    level: int,
    policy: str,
    variant: str,
    result: RefinementResult,
) -> list[dict[str, Any]]:
    return [
        {
            "overlay": overlay,
            "level": level,
            "policy": policy,
            "variant": variant,
            "pass": item.number,
            "affected_jobs": item.affected_jobs,
            "offending_records": item.offending_records,
            "cumulative_jobs": item.cumulative_jobs,
            "cumulative_records": item.cumulative_records,
            "terminal_zero": item.affected_jobs == 0 and item.offending_records == 0,
            "simulation_s": item.simulation_s,
            "detection_s": item.detection_s,
            "rescore_s": item.rescore_s,
        }
        for item in result.passes
    ]


def _assert_bound(
    outcome: JobResults,
    fcfs_wait: np.ndarray,
    policy: Policy,
    servers: int,
    limit_s: float,
) -> None:
    if policy.wrapper != "none":
        assert_per_job_bounds(outcome, fcfs_wait, policy, servers, limit_s)


def _cost_row(
    stage: str,
    seconds: float,
    *,
    overlay: int | str = "",
    level: int | str = "",
    policy: str = "",
    variant: str = "",
    status: str = "computed",
    detail: str = "",
) -> dict[str, Any]:
    return {
        "stage": stage,
        "overlay": overlay,
        "level": level,
        "policy": policy,
        "variant": variant,
        "seconds": seconds,
        "status": status,
        "detail": detail,
    }


def _run_exact_policy(
    cfg: cfgmod.Config,
    args: argparse.Namespace,
    store: CheckpointStore,
    trace: Trace,
    arrays: dict[str, np.ndarray],
    context: dict[str, Any],
    labels: dict[str, np.ndarray],
    multiplicities: np.ndarray,
    fcfs_out: JobResults,
    base_p99: float,
    target_p99: float,
    work_s: float,
    rho: float,
    overlay: int,
    level: int,
    policy: Policy,
) -> tuple[dict[str, Any], dict[str, Any]]:
    name = f"o{overlay}_l{level}_exact_{policy.name}"
    cached = store.load(name)
    if cached is not None:
        return cached, _cost_row(
            "exact_policy",
            cached["elapsed_s"],
            overlay=overlay,
            level=level,
            policy=policy.name,
            status="resumed",
        )
    started = time.perf_counter()
    result = refine_policy(
        trace,
        policy,
        fcfs_out.servers,
        int(cfg["run"]["segment_tree_window_ranks"]),
        arrays,
        context["same_copy"],
        context["recomputer"],
        context["models"],
        context["baseline_history"],
        trace.scores[ORIGINAL],
        EXACT,
        pool_terms=context["pool_terms"],
    )
    outcomes = {ORIGINAL: result.initial_outcome, EXACT: result.outcome}
    for variant in (CONSERVATIVE, STATIC):
        outcomes[variant] = simulate(
            trace,
            replace(policy, score_key=variant),
            fcfs_out.servers,
            window=int(cfg["run"]["segment_tree_window_ranks"]),
        )
    rows = []
    replicates = {}
    for variant in HEADLINE_VARIANTS:
        policy_outcome = outcomes[variant]
        _assert_bound(policy_outcome, fcfs_out.wait_us, policy, fcfs_out.servers, cfg.limit_s)
        rows.append(
            _metric_row(
                policy_outcome,
                fcfs_out.wait_us,
                labels,
                overlay,
                level,
                work_s,
                rho,
                variant,
                base_p99,
                target_p99,
            )
        )
        replicates[f"{policy.name}|{variant}"] = _replicates(
            policy_outcome, labels, multiplicities
        )
    decomposition = _decomposition_row(
        replace(policy, score_key=ORIGINAL),
        result.initial_outcome,
        result.initial_jobs,
        result.initial_score_delta,
        result.initial_corrected_score,
        result.initial_withheld_counts,
        trace,
        labels,
        overlay,
        level,
        trace.scores[ORIGINAL],
    )
    delta = _save_delta(args.out_dir, overlay, level, policy.name, EXACT, ORIGINAL, result)
    elapsed = time.perf_counter() - started
    payload = {
        "metric_rows": rows,
        "decomposition": decomposition,
        "pass_rows": _pass_rows(overlay, level, policy.name, EXACT, result),
        "replicates": _pack_replicates(replicates),
        "delta": delta,
        "elapsed_s": elapsed,
    }
    store.write(name, payload, [delta])
    return payload, _cost_row(
        "exact_policy", elapsed, overlay=overlay, level=level, policy=policy.name
    )


def _run_fcfs_decomposition(
    args: argparse.Namespace,
    store: CheckpointStore,
    trace: Trace,
    arrays: dict[str, np.ndarray],
    context: dict[str, Any],
    labels: dict[str, np.ndarray],
    fcfs_out: JobResults,
    overlay: int,
    level: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    name = f"o{overlay}_l{level}_fcfs_decomposition"
    cached = store.load(name)
    if cached is not None:
        return cached["row"], _cost_row(
            "fcfs_decomposition",
            cached["elapsed_s"],
            overlay=overlay,
            level=level,
            policy="FCFS",
            status="resumed",
        )
    started = time.perf_counter()
    jobs, delta, counts, corrected_score = one_pass_score_changes(
        fcfs_out.wait_us,
        arrays,
        context["same_copy"],
        context["recomputer"],
        context["models"],
        context["baseline_history"],
        trace.scores[ORIGINAL],
    )
    row = _decomposition_row(
        fcfs(),
        fcfs_out,
        jobs,
        delta,
        corrected_score,
        counts,
        trace,
        labels,
        overlay,
        level,
        trace.scores[ORIGINAL],
    )
    elapsed = time.perf_counter() - started
    store.write(name, {"row": row, "elapsed_s": elapsed})
    return row, _cost_row(
        "fcfs_decomposition", elapsed, overlay=overlay, level=level, policy="FCFS"
    )


def _run_attribution_variant(
    cfg: cfgmod.Config,
    store: CheckpointStore,
    trace: Trace,
    labels: dict[str, np.ndarray],
    multiplicities: np.ndarray,
    fcfs_out: JobResults,
    base_p99: float,
    target_p99: float,
    work_s: float,
    rho: float,
    overlay: int,
    level: int,
    variant: str,
) -> tuple[dict[str, Any], dict[str, np.ndarray], dict[str, Any]]:
    name = f"o{overlay}_l{level}_attribution_{variant}"
    cached = store.load(name)
    if cached is not None:
        return (
            cached["row"],
            replicate_arrays(cached["replicates"]),
            _cost_row(
                "attribution",
                cached["elapsed_s"],
                overlay=overlay,
                level=level,
                policy="Guard(600)",
                variant=variant,
                status="resumed",
            ),
        )
    started = time.perf_counter()
    policy = _guard(cfg, 600.0, fcfs_out.servers, variant)
    policy_outcome = simulate(
        trace,
        policy,
        fcfs_out.servers,
        window=int(cfg["run"]["segment_tree_window_ranks"]),
    )
    _assert_bound(policy_outcome, fcfs_out.wait_us, policy, fcfs_out.servers, cfg.limit_s)
    row = _metric_row(
        policy_outcome,
        fcfs_out.wait_us,
        labels,
        overlay,
        level,
        work_s,
        rho,
        variant,
        base_p99,
        target_p99,
    )
    replicates = _replicates(policy_outcome, labels, multiplicities)
    elapsed = time.perf_counter() - started
    store.write(
        name,
        {"row": row, "replicates": replicate_lists(replicates), "elapsed_s": elapsed},
    )
    return (
        row,
        replicates,
        _cost_row(
            "attribution",
            elapsed,
            overlay=overlay,
            level=level,
            policy="Guard(600)",
            variant=variant,
        ),
    )


def _run_sensitivity(
    cfg: cfgmod.Config,
    args: argparse.Namespace,
    store: CheckpointStore,
    trace: Trace,
    arrays: dict[str, np.ndarray],
    context: dict[str, Any],
    labels: dict[str, np.ndarray],
    multiplicities: np.ndarray,
    fcfs_out: JobResults,
    base_p99: float,
    target_p99: float,
    work_s: float,
    rho: float,
    overlay: int,
    level: int,
) -> tuple[
    dict[str, Any],
    dict[str, np.ndarray],
    list[dict[str, Any]],
    dict[str, Any],
    dict[str, Any],
]:
    name = f"o{overlay}_l{level}_sensitivity_guard600"
    cached = store.load(name)
    if cached is not None:
        return (
            cached["row"],
            replicate_arrays(cached["replicates"]),
            cached["pass_rows"],
            cached["delta"],
            _cost_row(
                "exact_sensitivity",
                cached["elapsed_s"],
                overlay=overlay,
                level=level,
                policy="Guard(600)",
                variant=OTHER_CLASS_EXACT,
                status="resumed",
            ),
        )
    started = time.perf_counter()
    policy = _guard(cfg, 600.0, fcfs_out.servers, "exact_sensitivity")
    result = refine_policy(
        trace,
        policy,
        fcfs_out.servers,
        int(cfg["run"]["segment_tree_window_ranks"]),
        arrays,
        context["same_copy"],
        context["recomputer"],
        context["models"],
        context["baseline_history"],
        trace.scores["other_class_withheld"],
        "exact_sensitivity",
        withhold_other_pool_classes=True,
        pool_terms=context["pool_terms"],
    )
    _assert_bound(result.outcome, fcfs_out.wait_us, policy, fcfs_out.servers, cfg.limit_s)
    row = _metric_row(
        result.outcome,
        fcfs_out.wait_us,
        labels,
        overlay,
        level,
        work_s,
        rho,
        OTHER_CLASS_EXACT,
        base_p99,
        target_p99,
    )
    replicates = _replicates(result.outcome, labels, multiplicities)
    pass_rows = _pass_rows(overlay, level, "Guard(600)", OTHER_CLASS_EXACT, result)
    delta = _save_delta(
        args.out_dir,
        overlay,
        level,
        "Guard(600)",
        OTHER_CLASS_EXACT,
        "other_class_withheld",
        result,
    )
    elapsed = time.perf_counter() - started
    payload = {
        "row": row,
        "replicates": replicate_lists(replicates),
        "pass_rows": pass_rows,
        "delta": delta,
        "elapsed_s": elapsed,
    }
    store.write(name, payload, [delta])
    return (
        row,
        replicates,
        pass_rows,
        delta,
        _cost_row(
            "exact_sensitivity",
            elapsed,
            overlay=overlay,
            level=level,
            policy="Guard(600)",
            variant=OTHER_CLASS_EXACT,
        ),
    )


def _cell_store(
    args: argparse.Namespace, run_signature: str, overlay: int, level: int, path: Path
) -> CheckpointStore:
    cell_signature = signature(
        {
            "run": run_signature,
            "overlay": overlay,
            "level": level,
            "overlay_sha256": sha256_file(path),
        }
    )
    return CheckpointStore(
        args.out_dir / ".checkpoints" / f"o{overlay}_l{level}",
        args.out_dir,
        cell_signature,
        args.resume,
    )


def _cell(
    cfg: cfgmod.Config,
    args: argparse.Namespace,
    context: dict[str, Any],
    controls: dict[str, np.ndarray],
    overlay: int,
    level: int,
    multiplicities: np.ndarray,
    run_signature: str,
) -> dict[str, Any]:
    cell_started = time.perf_counter()
    path = args.overlay_dir / f"{args.pool}_rep{overlay}.npz"
    trace, servers, labels = load_overlay(path, level, {}, cfg.limit_s)
    with np.load(path) as source:
        job_row = source["job_row"].astype(np.int64)
        labels["week"] = source["wk"].astype(np.int64)
        arrays = {
            "arrival_us": trace.arrival_us,
            "service_us": trace.service_us,
            "job_row": job_row,
            "copy_entry": source["copy_entry"].astype(np.int32),
            "copy_round": source["copy_round"].astype(np.int32),
        }
        work_s = float(source["W"])
        rho = level_utilisation(cfg, level, servers, work_s, len(source["K"]))
    attached = {
        ORIGINAL: context["base_score"],
        CONSERVATIVE: context["scores"]["spjf_e_conservative"].to_numpy("float64"),
        STATIC: context["scores"]["spjf_e_static"].to_numpy("float64"),
        **controls,
    }
    trace = _trace_with_scores(trace, attached, job_row)
    fcfs_out = simulate(
        trace, fcfs(), servers, window=int(cfg["run"]["segment_tree_window_ranks"])
    )
    sjf_out = simulate(
        trace, sjf(), servers, window=int(cfg["run"]["segment_tree_window_ranks"])
    )
    base_p99 = summarise(
        fcfs_out, fcfs_out.wait_us, labels["in_window"], labels["is_heavy"]
    ).p99_dl_s
    target_p99 = summarise(
        sjf_out, fcfs_out.wait_us, labels["in_window"], labels["is_heavy"]
    ).p99_dl_s
    references = {
        "FCFS": _replicates(fcfs_out, labels, multiplicities),
        "SJF": _replicates(sjf_out, labels, multiplicities),
    }
    store = _cell_store(args, run_signature, overlay, level, path)
    exact_rows: list[dict] = []
    passes: list[dict] = []
    decomposition: list[dict] = []
    exact_replicates = dict(references)
    deltas: list[dict] = []
    costs = [
        _cost_row(
            "cell_baselines",
            time.perf_counter() - cell_started,
            overlay=overlay,
            level=level,
            detail=f"jobs={len(trace)}",
        )
    ]
    fcfs_row, cost = _run_fcfs_decomposition(
        args, store, trace, arrays, context, labels, fcfs_out, overlay, level
    )
    decomposition.append(fcfs_row)
    costs.append(cost)
    policies = exact_policies(cfg, servers, EXACT)
    if args.policy:
        wanted = set(args.policy.split(","))
        policies = [policy for policy in policies if policy.name in wanted]
    guard_exact_row = None
    guard_exact_replicates = None
    for policy in policies:
        payload, cost = _run_exact_policy(
            cfg,
            args,
            store,
            trace,
            arrays,
            context,
            labels,
            multiplicities,
            fcfs_out,
            base_p99,
            target_p99,
            work_s,
            rho,
            overlay,
            level,
            policy,
        )
        exact_rows.extend(payload["metric_rows"])
        decomposition.append(payload["decomposition"])
        passes.extend(payload["pass_rows"])
        restored = _unpack_replicates(payload["replicates"])
        exact_replicates.update(restored)
        deltas.append(payload["delta"])
        costs.append(cost)
        if policy.name == "Guard(600)":
            guard_exact_row = next(
                row for row in payload["metric_rows"] if row["variant"] == EXACT
            )
            guard_exact_replicates = restored["Guard(600)|exact"]
    attribution_rows: list[dict] = []
    attribution_replicates = dict(references)
    sensitivity_rows: list[dict] = []
    sensitivity_replicates = dict(references)
    if not args.skip_controls:
        for variant in (ORIGINAL, *CONTROL_VARIANTS, CONSERVATIVE, STATIC):
            row, reps, cost = _run_attribution_variant(
                cfg,
                store,
                trace,
                labels,
                multiplicities,
                fcfs_out,
                base_p99,
                target_p99,
                work_s,
                rho,
                overlay,
                level,
                variant,
            )
            attribution_rows.append(row)
            attribution_replicates[f"Guard(600)|{variant}"] = reps
            costs.append(cost)
        if guard_exact_row is not None and guard_exact_replicates is not None:
            row, reps, extra_passes, delta, cost = _run_sensitivity(
                cfg,
                args,
                store,
                trace,
                arrays,
                context,
                labels,
                multiplicities,
                fcfs_out,
                base_p99,
                target_p99,
                work_s,
                rho,
                overlay,
                level,
            )
            sensitivity_rows.extend([guard_exact_row, row])
            sensitivity_replicates["Guard(600)|exact"] = guard_exact_replicates
            sensitivity_replicates[f"Guard(600)|{OTHER_CLASS_EXACT}"] = reps
            passes.extend(extra_passes)
            deltas.append(delta)
            costs.append(cost)
    print(f"overlay {overlay} level {level} complete", flush=True)
    return {
        "exact_rows": exact_rows,
        "passes": passes,
        "decomposition": decomposition,
        "attribution_rows": attribution_rows,
        "sensitivity_rows": sensitivity_rows,
        "exact_replicates": exact_replicates,
        "attribution_replicates": attribution_replicates,
        "sensitivity_replicates": sensitivity_replicates,
        "deltas": deltas,
        "costs": costs,
    }


def _initialize_cell_worker(
    config_path: Path,
    args: argparse.Namespace,
    pool_terms: list[str],
    controls: dict[str, np.ndarray],
    run_signature: str,
    multiplicities: np.ndarray,
) -> None:
    """Prepare one frozen model context for all cells assigned to this worker."""
    global _WORKER_MODEL_REPORTED, _WORKER_MODEL_SECONDS, _WORKER_STATE
    started = time.perf_counter()
    cfg = cfgmod.load(config_path)
    context = prepare_context(cfg, args, pool_terms)
    _WORKER_STATE = {
        "cfg": cfg,
        "args": args,
        "context": context,
        "controls": controls,
        "multiplicities": multiplicities,
        "run_signature": run_signature,
    }
    _WORKER_MODEL_SECONDS = time.perf_counter() - started
    _WORKER_MODEL_REPORTED = False


def _worker_cell(task: tuple[int, int]) -> dict[str, Any]:
    """Run one independent cell using this process's persistent frozen context."""
    global _WORKER_MODEL_REPORTED
    if _WORKER_STATE is None:
        raise RuntimeError("cell worker was not initialized")
    overlay, level = task
    cell = _cell(
        _WORKER_STATE["cfg"],
        _WORKER_STATE["args"],
        _WORKER_STATE["context"],
        _WORKER_STATE["controls"],
        overlay,
        level,
        _WORKER_STATE["multiplicities"],
        _WORKER_STATE["run_signature"],
    )
    if not _WORKER_MODEL_REPORTED:
        cell["costs"].insert(
            0,
            _cost_row(
                "worker_frozen_models",
                _WORKER_MODEL_SECONDS,
                overlay=overlay,
                level=level,
                detail="one fit reused by this persistent cell worker",
            ),
        )
        _WORKER_MODEL_REPORTED = True
    return cell


def _parallel_cells(
    args: argparse.Namespace,
    pool_terms: list[str],
    controls: dict[str, np.ndarray],
    run_signature: str,
    multiplicities: np.ndarray,
    tasks: list[tuple[int, int]],
) -> tuple[list[dict[str, Any]], float]:
    """Run distinct cells in bounded workers and retain task order in the result."""
    started = time.perf_counter()
    with ProcessPoolExecutor(
        max_workers=args.workers,
        mp_context=mp.get_context("spawn"),
        initializer=_initialize_cell_worker,
        initargs=(
            args.config,
            args,
            pool_terms,
            controls,
            run_signature,
            multiplicities,
        ),
    ) as executor:
        cells = list(executor.map(_worker_cell, tasks, chunksize=1))
    return cells, time.perf_counter() - started


def _aggregate_decomposition(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    output = []
    for level in sorted({row["level"] for row in rows}):
        policies = dict.fromkeys(row["policy"] for row in rows if row["level"] == level)
        for policy in policies:
            block = [row for row in rows if row["level"] == level and row["policy"] == policy]
            result = {"level": level, "policy": policy, "n_overlays": len(block)}
            for field in block[0]:
                if field in {"overlay", "level", "policy", "k"}:
                    continue
                values = [row[field] for row in block]
                result[field] = float(
                    np.max(values) if field.endswith("_max") else np.mean(values)
                )
            result["k"] = float(np.mean([row["k"] for row in block]))
            output.append(result)
    return output


def _aggregate_metrics(
    rows: list[dict[str, Any]], replicate_cells: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if not rows:
        return []
    policies = list(dict.fromkeys(row["policy"] for row in rows))
    levels = sorted({int(row["level"]) for row in rows})
    result = aggregate(rows, paired_intervals(replicate_cells, policies, levels))
    for row in result:
        row["base_policy"], row["variant"] = row["policy"].split("|", 1)
        row.setdefault("gap_closed_lo", float("nan"))
        row.setdefault("gap_closed_hi", float("nan"))
        row.setdefault("reduction_pct_lo", float("nan"))
        row.setdefault("reduction_pct_hi", float("nan"))
    return result


def _write_csv(rows: list[dict[str, Any]], path: Path, empty_fields: tuple[str, ...]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else list(empty_fields)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _write_outputs(args: argparse.Namespace, collections: dict[str, Any]) -> list[Path]:
    exact_comparison = _aggregate_metrics(
        collections["exact_rows"], collections["exact_replicate_cells"]
    )
    attribution_comparison = _aggregate_metrics(
        collections["attribution_rows"], collections["attribution_replicate_cells"]
    )
    sensitivity_comparison = _aggregate_metrics(
        collections["sensitivity_rows"], collections["sensitivity_replicate_cells"]
    )
    tables = {
        "exact_cells.csv": (collections["exact_rows"], ("overlay", "level", "policy")),
        "exact_comparison.csv": (exact_comparison, ("level", "policy")),
        "exact_passes.csv": (collections["passes"], ("overlay", "level", "policy")),
        "same_copy_exposure_cells.csv": (
            collections["decomposition"],
            ("overlay", "level", "policy"),
        ),
        "same_copy_exposure.csv": (
            _aggregate_decomposition(collections["decomposition"]),
            ("level", "policy"),
        ),
        "attribution_cells.csv": (
            collections["attribution_rows"],
            ("overlay", "level", "policy"),
        ),
        "attribution_comparison.csv": (
            attribution_comparison,
            ("level", "policy"),
        ),
        "exact_delta_manifest.csv": (
            collections["deltas"],
            ("path", "bytes", "sha256", "overlay", "level", "policy", "variant"),
        ),
        "exact_costs.csv": (collections["costs"], ("stage", "seconds", "status")),
        "exact_sensitivity_cells.csv": (
            collections["sensitivity_rows"],
            ("overlay", "level", "policy"),
        ),
        "exact_sensitivity_comparison.csv": (
            sensitivity_comparison,
            ("level", "policy"),
        ),
    }
    return [
        _write_csv(tables[name][0], args.out_dir / name, tables[name][1])
        for name in TABLE_NAMES
    ]


def _implementation_paths() -> list[Path]:
    scripts = [
        Path(__file__).resolve(),
        ROOT / "scripts" / "consistent_cells.py",
        ROOT / "scripts" / "build_overlays.py",
        ROOT / "scripts" / "fit_scores.py",
        ROOT / "scripts" / "run_main.py",
    ]
    package = sorted((ROOT / "src" / "spjf_guard").rglob("*.py"))
    return scripts + package


def _run_signature(
    cfg: cfgmod.Config,
    args: argparse.Namespace,
    pool_terms: list[str],
    controls_path: Path | None,
) -> tuple[str, str]:
    implementation = combined_hash(_implementation_paths(), ROOT)
    document = {
        "implementation_sha256": implementation,
        "config_sha256": sha256_file(args.config),
        "score_sha256": sha256_file(args.scores),
        "source_sha256": [sha256_file(path) for path in _source_paths(cfg, args.unseal)],
        "control_sha256": (
            sha256_file(controls_path)
            if controls_path is not None and controls_path.is_file()
            else None
        ),
        "pool": args.pool,
        "pool_terms": list(pool_terms),
    }
    return signature(document), implementation


def _empty_collections() -> dict[str, list[Any]]:
    return {
        "exact_rows": [],
        "passes": [],
        "decomposition": [],
        "attribution_rows": [],
        "sensitivity_rows": [],
        "exact_replicate_cells": [],
        "attribution_replicate_cells": [],
        "sensitivity_replicate_cells": [],
        "deltas": [],
        "costs": [],
    }


def _extend_collections(
    collections: dict[str, list[Any]],
    cell: dict[str, Any],
    overlay: int,
    level: int,
) -> None:
    fields = (
        "exact_rows",
        "passes",
        "decomposition",
        "attribution_rows",
        "sensitivity_rows",
        "deltas",
        "costs",
    )
    for field in fields:
        collections[field].extend(cell[field])
    for prefix in ("exact", "attribution", "sensitivity"):
        collections[f"{prefix}_replicate_cells"].append(
            {
                "overlay": overlay,
                "level": level,
                "replicates": cell[f"{prefix}_replicates"],
            }
        )


def _multiplicities(cfg: cfgmod.Config, overlay_path: Path) -> np.ndarray:
    with np.load(overlay_path) as source:
        n_weeks = len(source["weeks"])
    return bs.with_point_estimate(
        bs.week_multiplicities(
            n_weeks,
            int(cfg["bootstrap"]["resamples"]),
            int(cfg["bootstrap"]["seed"]),
        )
    )


def run(
    cfg: cfgmod.Config,
    args: argparse.Namespace,
    pool_terms: list[str],
    outcome: sealed.RunOutcome,
) -> int:
    started = time.perf_counter()
    _assert_protocol_config(cfg)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    print("fitting and verifying frozen original M4 models", flush=True)
    stage = time.perf_counter()
    context = prepare_context(cfg, args, pool_terms)
    collections = _empty_collections()
    collections["costs"].append(_cost_row("frozen_models", time.perf_counter() - stage))
    controls: dict[str, np.ndarray] = {}
    control_path = None
    if not args.skip_controls:
        stage = time.perf_counter()
        control_build = _control_build(cfg, args, context, pool_terms)
        controls = control_build.scores
        control_path = args.controls
        collections["costs"].append(
            _cost_row(
                "score_controls",
                time.perf_counter() - stage,
                status="cache_hit" if control_build.cache_hit else "computed",
                detail=f"target_rows={control_build.target_rows}",
            )
        )
        for name, cost in control_build.costs.items():
            detail = (
                f"feature_sweeps={cost.feature_sweeps};"
                f"recomputed_rows={cost.recomputed_rows};"
                f"predicted_rows={cost.predicted_rows}"
            )
            collections["costs"].append(
                _cost_row("score_control_work", 0.0, variant=name, detail=detail)
            )
    if args.build_controls_only:
        outcome.done(f"score controls ready in {time.perf_counter() - started:.0f} s")
        return 0
    run_signature, implementation_hash = _run_signature(cfg, args, pool_terms, control_path)
    overlays = [int(value) for value in args.reps.split(",")]
    levels = [int(value) for value in args.levels.split(",")]
    multiplicities = _multiplicities(
        cfg, args.overlay_dir / f"{args.pool}_rep{overlays[0]}.npz"
    )
    tasks = [(overlay, level) for overlay in overlays for level in levels]
    del context
    gc.collect()
    cells, parallel_wall = _parallel_cells(
        args,
        pool_terms,
        controls,
        run_signature,
        multiplicities,
        tasks,
    )
    for (overlay, level), cell in zip(tasks, cells, strict=True):
        _extend_collections(collections, cell, overlay, level)
    collections["costs"].append(
        _cost_row(
            "parallel_cells_wall",
            parallel_wall,
            detail=(
                f"max_workers={args.workers}; worker_model_fits={args.workers}; "
                "parent model fit built controls and was released before worker launch"
            ),
        )
    )
    if not artifacts_valid(collections["deltas"], args.out_dir):
        raise AssertionError("a sparse exact-score delta is missing or has the wrong hash")
    collections["deltas"].sort(
        key=lambda row: (row["overlay"], row["level"], row["policy"], row["variant"])
    )
    collections["costs"].append(
        _cost_row(
            "total_compute",
            time.perf_counter() - started,
            detail="before table writes",
        )
    )
    written = _write_outputs(args, collections)
    if args.pool == "sealed":
        complaint = provenance.pinned_outputs_complaint(
            cfg["run"]["sealed_consistent_visibility_tables"], written
        )
        if complaint:
            raise SystemExit(complaint)
    provenance.write(
        args.out_dir,
        produced_by="scripts/run_consistent_visibility.py",
        config_path=args.config,
        outputs=written,
        inputs=[
            *_source_paths(cfg, args.unseal),
            args.scores,
            *[args.overlay_dir / f"{args.pool}_rep{overlay}.npz" for overlay in overlays],
            *([control_path] if control_path is not None else []),
        ],
        arguments={
            "pool": args.pool,
            "reps": args.reps,
            "levels": args.levels,
            "workers": args.workers,
            "policy": args.policy,
            "skip_controls": args.skip_controls,
            "resume": args.resume,
            "unseal": args.unseal,
        },
        notes={
            "implementation_sha256": implementation_hash,
            "model_weights": "frozen original M4 rolling-origin LightGBM",
            "other_class_terms": "exogenous on their original relative clock",
            "other_class_sensitivity": "same-semester other-class history withheld",
            "terminal_assertion": "every exact policy/cell ends with zero new violation",
            "dense_policy_scores_written": False,
            "delta_integrity": "NPZ files are explicitly hashed by exact_delta_manifest.csv",
        },
    )
    outcome.done(
        f"exact visibility outputs written to {provenance.relative_path(args.out_dir)} "
        f"in {time.perf_counter() - started:.0f} s"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "main.yaml")
    parser.add_argument("--pool", default="primary")
    parser.add_argument("--overlay-dir", type=Path, default=None)
    parser.add_argument("--scores", type=Path, default=None)
    parser.add_argument("--controls", type=Path, default=None)
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--reps", default=None)
    parser.add_argument("--levels", default=None)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--policy", default=None)
    parser.add_argument("--skip-controls", action="store_true")
    parser.add_argument("--rebuild-controls", action="store_true")
    parser.add_argument("--build-controls-only", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--unseal", action="store_true")
    args = parser.parse_args()
    if args.workers != 2:
        parser.error("this protocol pins --workers 2")
    cfg = cfgmod.load(args.config)
    exact_section = cfg["features"]["exact_visibility"]
    args.reps = args.reps or ",".join(
        str(value) for value in exact_section["development_overlays"]
    )
    args.levels = args.levels or ",".join(
        str(value) for value in exact_section["development_levels"]
    )
    if args.pool not in cfg["overlay"]["pools"]:
        parser.error(f"unknown pool {args.pool!r}")
    pool_terms = list(cfg["overlay"]["pools"][args.pool])
    sealed.guard_semesters(pool_terms, ROOT, unseal=args.unseal)
    args.overlay_dir = args.overlay_dir or cfg.data_path("overlay_dir")
    score_name = "sealed_scores.parquet" if args.pool == "sealed" else "forward_scores.parquet"
    args.scores = args.scores or cfg.data_path("score_dir", score_name)
    if args.pool == "sealed":
        control_name = "sealed_consistent_controls.npz"
    elif args.pool == "primary":
        control_name = "consistent_controls.npz"
    else:
        control_name = f"{args.pool}_consistent_controls.npz"
    args.controls = args.controls or cfg.data_path("score_dir", control_name)
    if args.pool == "sealed":
        out_name = "sealed_consistent_visibility"
    elif args.pool == "primary":
        out_name = "dev_consistent_visibility"
    else:
        out_name = f"{args.pool}_consistent_visibility"
    args.out_dir = args.out_dir or ROOT / "outputs" / out_name
    with sealed.recording(
        ROOT, "scripts/run_consistent_visibility.py", pool_terms, args.unseal
    ) as outcome:
        return run(cfg, args, pool_terms, outcome)


if __name__ == "__main__":
    raise SystemExit(main())
