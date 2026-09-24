"""Replay the comparator suite under the online and the exact visibility protocols.

    uv run python scripts/run_online_visibility.py --pool primary --variants online
    uv run python scripts/run_online_visibility.py --variants exact,online --policies all

``online`` is experiment.online_replay.replay_online: the scheduler runs once and
every score is computed at the job's arrival from exactly the own-copy outcomes
completed by then, with rolling windows ordered by replay completion.  ``fixed_point``
reaches the same replay by iteration (experiment.online) and is kept as a cross-check.
``exact`` is the monotone withholding of experiment.consistent.refine_policy.  The
``original`` row of each policy is the replay on source-clock scores.  FCFS and SJF
read no score and are the references.

A policy is named as in the paper: SPJF-E, SPJF-log, Aging(600), Guard(G) and its
family rows Guard-fixed(G), Guard-age(G), Guard-queue(G), Fixed(G), Skip(G) and
Timeout(G) with theta = G - (3 - 2/k)L.  SPJF-log refines its own frozen log-target
model; every other policy refines the expected-cost model.
"""

from __future__ import annotations

import argparse
import gc
import multiprocessing as mp
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "prechecks" / "timeout_rule"))

from timeout_overlays import timeout_kernel  # noqa: E402

from build_overlays import clock_from  # noqa: E402
from consistent_cells import (  # noqa: E402
    artifact_entry,
    artifacts_valid,
    combined_hash,
    sha256_file,
    signature,
)
from run_consistent_visibility import (  # noqa: E402
    _aggregate_metrics,
    _cell_store,
    _metric_row,
    _multiplicities,
    _pack_replicates,
    _replicates,
    _source_paths,
    _trace_with_scores,
    _unpack_replicates,
    _write_csv,
    prepare_context,
)
from run_main import level_utilisation  # noqa: E402
from spjf_guard import config as cfgmod  # noqa: E402
from spjf_guard.data import sealed  # noqa: E402
from spjf_guard.data.events import static_submission_columns  # noqa: E402
from spjf_guard.experiment import grids, provenance  # noqa: E402
from spjf_guard.experiment.consistent import refine_policy  # noqa: E402
from spjf_guard.experiment.online import (  # noqa: E402
    audit_online,
    build_online_index,
    refine_policy_online,
)
from spjf_guard.experiment.online_replay import replay_online  # noqa: E402
from spjf_guard.experiment.reproduce import load_overlay  # noqa: E402
from spjf_guard.predict.forward import fit_frozen_m4_models  # noqa: E402
from spjf_guard.sim import JobResults, Trace, simulate  # noqa: E402
from spjf_guard.sim.bounds import assert_per_job_bounds  # noqa: E402
from spjf_guard.sim.policy import MICROS, Policy, aging, fcfs, sjf, spjf  # noqa: E402

ORIGINAL = "original"
VARIANTS = ("online", "fixed_point", "exact")
LOG_POLICY = "SPJF-log"
TABLES = (
    "online_cells.csv",
    "online_comparison.csv",
    "online_passes.csv",
    "online_audit.csv",
    "online_delta_manifest.csv",
    "online_costs.csv",
)

_STATE: dict[str, Any] | None = None


def comparator_suite(cfg: cfgmod.Config, servers: int) -> list[Policy]:
    """Every scored policy of the paper's comparisons, scored by the key of its model."""
    section = cfg["scheduling"]["aging_baseline"]
    suite = [
        spjf("spjf_e", "SPJF-E"),
        spjf("spjf_log", LOG_POLICY),
        aging("spjf_e", float(section["selected_credit_per_s"]), str(section["label"])),
    ]
    for policy in cfg.policies(servers, include_family_bests=True):
        if policy.name.startswith(("Guard", "Fixed", "Skip")):
            suite.append(policy)
    suite += [spjf("spjf_e", f"Timeout({g:g})") for g in cfg.promises_s]
    return suite


def _timeout_simulator(promise: float, servers: int, limit_s: float):
    theta_us = np.int64(round((promise - (3.0 - 2.0 / servers) * limit_s) * MICROS))

    def run(trace: Trace) -> JobResults:
        score = next(iter(trace.scores.values()))
        wait = timeout_kernel(trace.arrival_us, trace.service_us, score, servers, theta_us)
        start = trace.arrival_us + wait
        dispatch = np.empty(len(wait), np.int64)
        dispatch[np.argsort(start, kind="stable")] = np.arange(len(wait))
        return JobResults(
            policy=f"Timeout({promise:g})",
            servers=servers,
            wait_us=wait,
            start_us=start,
            dispatch_index=dispatch,
            n_dispatch=len(wait),
            n_forced=0,
            queue_weighted_dispatch=0,
            queue_weighted_forced=0,
        )

    return run


def _assert_timeout_bound(outcome: JobResults, fcfs_wait: np.ndarray, promise: float) -> None:
    excess = outcome.wait_us - fcfs_wait - np.int64(round(promise * MICROS))
    if excess.max() > 0:
        raise AssertionError(f"{outcome.policy} exceeds its promise by {excess.max()} us")


def _check_bound(outcome, fcfs_wait, policy, servers, limit_s) -> None:
    if policy.name.startswith("Timeout("):
        _assert_timeout_bound(outcome, fcfs_wait, float(policy.name[8:-1]))
    elif policy.wrapper != "none":
        assert_per_job_bounds(outcome, fcfs_wait, policy, servers, limit_s)


def _frozen_log_models(cfg, args, context, pool_terms):
    prepared = context["prepared"]
    models, _, _, _ = fit_frozen_m4_models(
        prepared,
        static_submission_columns(context["events"], prepared),
        clock_from(cfg, 0.0),
        cfg["predictor"],
        cfg.limit_s,
        pool_terms,
        context["all_terms"],
        expected_scores=context["scores"]["spjf_log"].to_numpy("float64"),
        score_name="spjf_log",
    )
    return models


def _initialize(config_path: Path, args, pool_terms: list[str], run_signature: str, mult):
    global _STATE
    cfg = cfgmod.load(config_path)
    context = prepare_context(cfg, args, pool_terms)
    context["online_index"] = build_online_index(context["recomputer"])
    if LOG_POLICY in args.policy_names or args.policy_names == ["all"]:
        context["log_models"] = _frozen_log_models(cfg, args, context, pool_terms)
    _STATE = {
        "cfg": cfg,
        "args": args,
        "context": context,
        "signature": run_signature,
        "multiplicities": mult,
    }


def _theta_s(policy: Policy, servers: int, limit_s: float) -> float | None:
    if not policy.name.startswith("Timeout("):
        return None
    return float(policy.name[8:-1]) - (3.0 - 2.0 / servers) * limit_s


def _refine(variant, trace, policy, servers, cfg, arrays, context, base):
    """(original-clock outcome, refined result, pass rows) of one policy in one cell."""
    window = int(cfg["run"]["segment_tree_window_ranks"])
    models = context["log_models"] if policy.name == LOG_POLICY else context["models"]
    theta = _theta_s(policy, servers, cfg.limit_s)
    promise = None if theta is None else float(policy.name[8:-1])
    simulator = None if theta is None else _timeout_simulator(promise, servers, cfg.limit_s)
    if variant == "online":
        original = (
            simulate(trace, policy, servers, window=window)
            if simulator is None
            else simulator(trace)
        )
        result = replay_online(
            trace,
            policy,
            servers,
            window,
            arrays,
            context["online_index"],
            context["recomputer"],
            models,
            context["baseline_history"],
            base,
            timeout_s=theta,
        )
        cost = {"pauses": result.pauses, "kernel_s": result.kernel_s}
        return original, result, [cost | {"rescore_s": result.rescore_s}]
    if variant == "fixed_point":
        result = refine_policy_online(
            trace,
            policy,
            servers,
            window,
            arrays,
            context["online_index"],
            context["recomputer"],
            models,
            context["baseline_history"],
            base,
            variant,
            simulator=simulator,
        )
        return result.initial_outcome, result, [vars(item) for item in result.passes]
    if simulator is not None:
        raise ValueError(f"{policy.name} has no exact refinement: it needs its own kernel")
    result = refine_policy(
        trace,
        policy,
        servers,
        window,
        arrays,
        context["same_copy"],
        context["recomputer"],
        models,
        context["baseline_history"],
        base,
        variant,
        pool_terms=context["pool_terms"],
    )
    return result.initial_outcome, result, [vars(item) for item in result.passes]


def _run_policy(cell: dict[str, Any], policy: Policy, variant: str) -> dict[str, Any]:
    cfg, args, context = _STATE["cfg"], _STATE["args"], _STATE["context"]
    overlay, level, servers = cell["overlay"], cell["level"], cell["servers"]
    name = f"o{overlay}_l{level}_{variant}_{policy.name}"
    cached = cell["store"].load(name)
    if cached is not None:
        return cached
    started = time.perf_counter()
    score_name = "spjf_log" if policy.name == LOG_POLICY else "spjf_e"
    base = context["scores"][score_name].to_numpy("float64")[cell["arrays"]["job_row"]]
    trace = Trace(
        cell["trace"].arrival_us, cell["trace"].service_us, {variant: base}, cfg.limit_s
    )
    refined = replace(policy, score_key=variant)
    original, result, costs = _refine(
        variant, trace, refined, servers, cfg, cell["arrays"], context, base
    )
    rows, replicates = [], {}
    for label, outcome in ((ORIGINAL, original), (variant, result.outcome)):
        outcome = replace(outcome, policy=policy.name)
        _check_bound(outcome, cell["fcfs"].wait_us, policy, servers, cfg.limit_s)
        rows.append(
            _metric_row(
                outcome,
                cell["fcfs"].wait_us,
                cell["labels"],
                overlay,
                level,
                cell["work_s"],
                cell["rho"],
                label,
                cell["base_p99"],
                cell["target_p99"],
            )
        )
        replicates[f"{policy.name}|{label}"] = _replicates(
            outcome, cell["labels"], _STATE["multiplicities"]
        )
    audit = {"overlay": overlay, "level": level, "policy": policy.name, "variant": variant}
    if variant in ("online", "fixed_point") and args.audit:
        sample = np.random.default_rng(overlay * 100 + level).choice(
            len(base), args.audit, replace=False
        )
        sample = np.union1d(sample, result.changed_jobs[: args.audit])
        audit["sampled_jobs"] = len(sample)
        audit["mismatches"] = audit_online(
            result,
            sample,
            cell["arrays"],
            context["online_index"],
            context["recomputer"],
            context["log_models"] if policy.name == LOG_POLICY else context["models"],
            context["baseline_history"],
            base,
        )
        if audit["mismatches"]:
            print(
                f"    AUDIT {name}: {audit['mismatches']} of {len(sample)} differ", flush=True
            )
    path = args.out_dir / "deltas" / f"{name.replace('(', '_').replace(')', '')}.npz"
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        job_index=result.changed_jobs,
        score_delta=result.score_delta,
        corrected_score=result.corrected_score,
    )
    delta = artifact_entry(
        path,
        args.out_dir,
        overlay=overlay,
        level=level,
        policy=policy.name,
        variant=variant,
        affected_jobs=len(result.changed_jobs),
    )
    payload = {
        "metric_rows": rows,
        "pass_rows": [
            {"overlay": overlay, "level": level, "policy": policy.name, "variant": variant}
            | row
            for row in costs
        ],
        "replicates": _pack_replicates(replicates),
        "audit": audit,
        "delta": delta,
        "elapsed_s": time.perf_counter() - started,
    }
    cell["store"].write(name, payload, [delta])
    return payload


def _load_cell(overlay: int, level: int) -> dict[str, Any]:
    cfg, args = _STATE["cfg"], _STATE["args"]
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
    window = int(cfg["run"]["segment_tree_window_ranks"])
    trace = _trace_with_scores(trace, {}, job_row)
    fcfs_out = simulate(trace, fcfs(), servers, window=window)
    sjf_out = simulate(trace, sjf(), servers, window=window)
    from spjf_guard.experiment.metrics import summarise

    base_p99 = summarise(fcfs_out, fcfs_out.wait_us, labels["in_window"], labels["is_heavy"])
    target_p99 = summarise(sjf_out, fcfs_out.wait_us, labels["in_window"], labels["is_heavy"])
    return {
        "overlay": overlay,
        "level": level,
        "servers": servers,
        "trace": trace,
        "labels": labels,
        "arrays": arrays,
        "work_s": work_s,
        "rho": rho,
        "fcfs": fcfs_out,
        "base_p99": base_p99.p99_dl_s,
        "target_p99": target_p99.p99_dl_s,
        "references": {
            "FCFS": _replicates(fcfs_out, labels, _STATE["multiplicities"]),
            "SJF": _replicates(sjf_out, labels, _STATE["multiplicities"]),
        },
        "store": _cell_store(args, _STATE["signature"], overlay, level, path),
    }


def _suite(cfg: cfgmod.Config, args, servers: int) -> list[Policy]:
    """The named comparators, or every grid point listed in ``--candidates``."""
    if args.candidates is None:
        wanted = args.policy_names
        return [
            policy
            for policy in comparator_suite(cfg, servers)
            if wanted == ["all"] or policy.name in wanted
        ]
    from select_online import _rows, grid_point

    points = [grid_point(row) for row in _rows(args.candidates)]
    return [
        grids.policy_for(point, servers, cfg.limit_s, "spjf_e", cfg.promises_s)
        for point in points
    ]


def _worker(task: tuple[int, int]) -> dict[str, Any]:
    overlay, level = task
    cell = _load_cell(overlay, level)
    suite = _suite(_STATE["cfg"], _STATE["args"], cell["servers"])
    out = {"rows": [], "passes": [], "audit": [], "deltas": [], "costs": [], "replicates": {}}
    out["replicates"].update(cell["references"])
    for policy in suite:
        for variant in _STATE["args"].variant_names:
            if variant == "exact" and policy.name.startswith("Timeout("):
                continue
            payload = _run_policy(cell, policy, variant)
            out["rows"] += [
                row
                for row in payload["metric_rows"]
                if row["variant"] != ORIGINAL or variant == _STATE["args"].variant_names[0]
            ]
            out["passes"] += payload["pass_rows"]
            out["audit"].append(payload["audit"])
            out["deltas"].append(payload["delta"])
            out["costs"].append(
                {
                    "overlay": overlay,
                    "level": level,
                    "policy": policy.name,
                    "variant": variant,
                    "seconds": payload["elapsed_s"],
                }
            )
            out["replicates"].update(_unpack_replicates(payload["replicates"]))
    del cell
    gc.collect()
    print(f"overlay {overlay} level {level} complete", flush=True)
    return out


PRESENTATION = ("experiment/paper_tables.py",)
"""Package files that format results for the paper and compute none.  Editing one leaves
the checkpoints of a run valid, so the paper can be revised while a long run resumes."""


def _run_signature(cfg, args, pool_terms) -> tuple[str, str]:
    package = ROOT / "src" / "spjf_guard"
    scripts = ("run_consistent_visibility.py", "consistent_cells.py", "build_overlays.py")
    paths = [Path(__file__).resolve()]
    paths += [ROOT / "scripts" / name for name in (*scripts, "run_main.py", "select_online.py")]
    paths += sorted(
        path
        for path in package.rglob("*.py")
        if path.relative_to(package).as_posix() not in PRESENTATION
    )
    paths.append(ROOT / "prechecks" / "timeout_rule" / "timeout_overlays.py")
    implementation = combined_hash(paths, ROOT)
    document = {
        "implementation_sha256": implementation,
        "config_sha256": sha256_file(args.config),
        "score_sha256": sha256_file(args.scores),
        "source_sha256": [sha256_file(path) for path in _source_paths(cfg, args.unseal)],
        "pool": args.pool,
        "pool_terms": list(pool_terms),
        "audit": args.audit,
    }
    return signature(document), implementation


def _uniform(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rows of the passes table under one header: an online replay records pauses and a
    fixed-point pass records a frontier, so each leaves the other's columns empty."""
    fields = list(dict.fromkeys(key for row in rows for key in row))
    return [{key: row.get(key, "") for key in fields} for row in rows]


def run(cfg, args, pool_terms, outcome) -> int:
    started = time.perf_counter()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    run_signature, implementation = _run_signature(cfg, args, pool_terms)
    overlays = [int(v) for v in args.reps.split(",")]
    levels = [int(v) for v in args.levels.split(",")]
    mult = _multiplicities(cfg, args.overlay_dir / f"{args.pool}_rep{overlays[0]}.npz")
    tasks = [(o, lv) for o in overlays for lv in levels]
    with ProcessPoolExecutor(
        max_workers=args.workers,
        mp_context=mp.get_context("spawn"),
        initializer=_initialize,
        initargs=(args.config, args, pool_terms, run_signature, mult),
    ) as executor:
        cells = list(executor.map(_worker, tasks, chunksize=1))
    rows = [row for cell in cells for row in cell["rows"]]
    replicate_cells = [
        {"overlay": o, "level": lv, "replicates": cell["replicates"]}
        for (o, lv), cell in zip(tasks, cells, strict=True)
    ]
    deltas = sorted(
        (d for cell in cells for d in cell["deltas"]),
        key=lambda d: (d["overlay"], d["level"], d["policy"], d["variant"]),
    )
    if not artifacts_valid(deltas, args.out_dir):
        raise AssertionError("an online score delta is missing or has the wrong hash")
    tables = {
        "online_cells.csv": rows,
        "online_comparison.csv": _aggregate_metrics(rows, replicate_cells),
        "online_passes.csv": _uniform([r for cell in cells for r in cell["passes"]]),
        "online_audit.csv": [r for cell in cells for r in cell["audit"]],
        "online_delta_manifest.csv": deltas,
        "online_costs.csv": [r for cell in cells for r in cell["costs"]],
    }
    written = [_write_csv(tables[name], args.out_dir / name, ("policy",)) for name in TABLES]
    if args.pool == "sealed":
        complaint = provenance.pinned_outputs_complaint(
            cfg["run"]["sealed_online_visibility_tables"], written
        )
        if complaint:
            raise SystemExit(complaint)
    provenance.write(
        args.out_dir,
        produced_by="scripts/run_online_visibility.py",
        config_path=args.config,
        outputs=written,
        inputs=[
            *_source_paths(cfg, args.unseal),
            args.scores,
            *[args.overlay_dir / f"{args.pool}_rep{o}.npz" for o in overlays],
        ],
        arguments={
            "pool": args.pool,
            "reps": args.reps,
            "levels": args.levels,
            "policies": args.policies,
            "candidates": None if args.candidates is None else str(args.candidates),
            "variants": args.variants,
            "audit": args.audit,
            "workers": args.workers,
            "unseal": args.unseal,
        },
        notes={
            "implementation_sha256": implementation,
            "online": "every score computed at arrival from own-copy outcomes completed by "
            "then; rolling windows ordered by replay completion; terminal pass has zero "
            "mismatched jobs",
            "exact": "monotone per-job withholding (run_consistent_visibility protocol)",
            "other_class_terms": "exogenous on their original relative clock",
        },
    )
    outcome.done(f"online replay written in {time.perf_counter() - started:.0f} s")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "main.yaml")
    parser.add_argument("--pool", default="primary")
    parser.add_argument("--overlay-dir", type=Path, default=None)
    parser.add_argument("--scores", type=Path, default=None)
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--reps", default="0,1,2,3,4")
    parser.add_argument("--levels", default="0,1,2")
    parser.add_argument("--policies", default=None, help="default: the configured list")
    parser.add_argument("--candidates", type=Path, default=None)
    parser.add_argument("--variants", default=None, help="default: the configured list")
    parser.add_argument("--audit", type=int, default=None)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--unseal", action="store_true")
    args = parser.parse_args()
    cfg = cfgmod.load(args.config)
    section = cfg["features"]["online_visibility"]
    pinned = (",".join(section["policies"]), ",".join(section["variants"]))
    args.policies = args.policies or pinned[0]
    args.variants = args.variants or pinned[1]
    args.audit = int(section["audit_sample"]) if args.audit is None else args.audit
    args.policy_names = args.policies.split(",")
    args.variant_names = args.variants.split(",")
    if not set(args.variant_names) <= set(VARIANTS):
        parser.error(f"variants are {VARIANTS}")
    chosen = (args.policies, args.variants, args.audit, args.candidates)
    if args.pool == "sealed" and chosen != (*pinned, int(section["audit_sample"]), None):
        parser.error("the sealed run replays exactly the configured policies and variants")
    pool_terms = list(cfg["overlay"]["pools"][args.pool])
    sealed.guard_semesters(pool_terms, ROOT, unseal=args.unseal)
    args.overlay_dir = args.overlay_dir or cfg.data_path("overlay_dir")
    score_name = "sealed_scores.parquet" if args.pool == "sealed" else "forward_scores.parquet"
    args.scores = args.scores or cfg.data_path("score_dir", score_name)
    prefix = "dev" if args.pool == "primary" else args.pool
    args.out_dir = args.out_dir or ROOT / "outputs" / f"{prefix}_online_visibility"
    args.skip_controls = True
    with sealed.recording(
        ROOT, "scripts/run_online_visibility.py", pool_terms, args.unseal
    ) as outcome:
        return run(cfg, args, pool_terms, outcome)


if __name__ == "__main__":
    raise SystemExit(main())
