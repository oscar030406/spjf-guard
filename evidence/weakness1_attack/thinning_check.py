"""Check whether Bernoulli demand thinning preserves the nominal k=4 result at k=2.

This is a finite-window Monte Carlo sensitivity check.  It consumes only the already
frozen physical input and uses the production simulator pinned by ``common``.  It does
not load an overlay, refit a score, choose a window, or launch a physical-service run.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True

from common import HERE, TERMS, np
from spjf_guard.sim import Trace, simulate
from spjf_guard.sim.bounds import assert_per_job_bounds
from spjf_guard.sim.policy import fcfs, guard, spjf


INPUT = HERE / "physical_input.npz"
METADATA = HERE / "physical_input_metadata.json"
CSV_PATH = HERE / "thinning_check_runs.csv"
JSON_PATH = HERE / "thinning_check.json"
LOG_PATH = HERE / "out_thinning_check.txt"
FIGURE_STEM = HERE / "thinning_check"

EXPECTED_INPUT_SHA256 = "85a04f5c3a5de412310b6c066cfeed9ce09e5445eb591d01740102d1617e457d"
EXPECTED_PHYSICAL_PROTOCOL = "27742c88b7ce6115c3942ac2c7a5654bfc18fcf784779f286e9262346bc75108"
EXPECTED_SCHEMA = {
    "job_id",
    "source_rank",
    "target_release_offset_ns",
    "requested_service_ns",
    "score",
    "in_deadline_window",
}
EXPECTED_JOBS = 2151
WINDOW_S = 300.0
FORMAL_LIMIT_S = 61.0
PROMISE_S = 300.0
KEEP_PROBABILITY = 0.5
FULL_K = 4
THIN_K = 2
REPLICATES = 100
FIRST_SEED = 20260921
SCORE_KEY = "tweedie"
POLICY_NAMES = ("FCFS", "SPJF-E", "Guard(300)")

PARAMETERS = {
    "purpose": "first-moment scaling sensitivity for the frozen physical window",
    "input_sha256": EXPECTED_INPUT_SHA256,
    "physical_protocol": EXPECTED_PHYSICAL_PROTOCOL,
    "source_terms": list(TERMS),
    "window_s": WINDOW_S,
    "full_jobs": EXPECTED_JOBS,
    "full_workers": FULL_K,
    "thinned_workers": THIN_K,
    "thinning": "independent Bernoulli per job",
    "keep_probability": KEEP_PROBABILITY,
    "replicates": REPLICATES,
    "seeds": [FIRST_SEED + index for index in range(REPLICATES)],
    "arrival_transform": "retain frozen offsets from common calendar-bin origin 0",
    "service_transform": "none",
    "score_transform": "none; frozen score is subset without refit",
    "policies": list(POLICY_NAMES),
    "guard": {
        "G_s": PROMISE_S,
        "formal_L_s": FORMAL_LIMIT_S,
        "B0_s": "15*k",
        "eta": 0.5,
        "gamma_s": 0.0,
    },
}
PROTOCOL = hashlib.sha256(json.dumps(PARAMETERS, sort_keys=True).encode()).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_text(path: Path, value: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8", newline="")
    temporary.replace(path)


def json_safe(value):
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return [json_safe(item) for item in value.tolist()]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        value = float(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def write_json(path: Path, value) -> None:
    atomic_text(path, json.dumps(json_safe(value), indent=2, allow_nan=False) + "\n")


def load_frozen_input() -> tuple[dict[str, np.ndarray], dict, str]:
    if not INPUT.is_file() or not METADATA.is_file():
        raise RuntimeError("frozen physical input and metadata must both exist")
    digest = sha256_file(INPUT)
    if digest != EXPECTED_INPUT_SHA256:
        raise RuntimeError(f"physical input SHA-256 changed: {digest}")
    metadata = json.loads(METADATA.read_text(encoding="utf-8"))
    if metadata.get("input_sha256") != digest:
        raise RuntimeError("physical metadata does not bind the frozen NPZ SHA-256")
    if metadata.get("protocol") != EXPECTED_PHYSICAL_PROTOCOL:
        raise RuntimeError("physical metadata has a different protocol hash")
    parameters = metadata.get("parameters", {})
    if parameters.get("protocol_version") != 2:
        raise RuntimeError("physical input is not protocol version 2")
    if metadata.get("source_terms") != list(TERMS):
        raise RuntimeError("physical input does not name the six development terms")
    if metadata.get("source_rep") != 0 or parameters.get("source") != "primary_rep0":
        raise RuntimeError("physical input is not frozen development overlay rep 0")
    if metadata.get("jobs") != EXPECTED_JOBS or metadata.get("window_s") != WINDOW_S:
        raise RuntimeError("physical input job count or window length changed")
    if metadata.get("selection_used_policy_outcomes") is not False:
        raise RuntimeError("physical window selection must be independent of policy outcomes")
    if parameters.get("requested_service") != "unchanged source C_cap, at most 60 s":
        raise RuntimeError("physical requested-service definition changed")
    if parameters.get("arrival_spacing") != "unchanged within selected calendar bin":
        raise RuntimeError("physical arrival-spacing definition changed")

    with np.load(INPUT, allow_pickle=False) as store:
        if set(store.files) != EXPECTED_SCHEMA:
            raise RuntimeError(f"physical input schema changed: {sorted(store.files)}")
        data = {name: np.array(store[name], copy=True) for name in store.files}
    if any(array.shape != (EXPECTED_JOBS,) for array in data.values()):
        raise RuntimeError("physical input arrays do not all have the frozen job count")
    if not np.array_equal(data["job_id"], np.arange(EXPECTED_JOBS, dtype=np.int64)):
        raise RuntimeError("physical input job IDs are not contiguous arrival ranks")
    arrival_ns = data["target_release_offset_ns"]
    service_ns = data["requested_service_ns"]
    score = data["score"]
    if arrival_ns.dtype != np.int64 or service_ns.dtype != np.int64:
        raise RuntimeError("physical input time arrays are not int64 nanoseconds")
    if np.any(np.diff(arrival_ns) < 0) or int(arrival_ns[0]) < 0:
        raise RuntimeError("physical input arrivals are not ordered offsets from zero")
    if int(arrival_ns[-1]) >= int(WINDOW_S * 1e9):
        raise RuntimeError("physical input contains an arrival outside the 300 s window")
    if np.any(service_ns <= 0) or int(service_ns.max()) > 60_000_000_000:
        raise RuntimeError("physical input service is outside (0, 60 s]")
    if np.any(arrival_ns % 1000) or np.any(service_ns % 1000):
        raise RuntimeError("physical nanoseconds do not convert exactly to simulator microseconds")
    if not np.isfinite(score).all():
        raise RuntimeError("physical input score contains a nonfinite value")
    recorded_work_s = float(metadata["offered_requested_work_s"])
    actual_work_s = float(service_ns.sum() / 1e9)
    if not math.isclose(recorded_work_s, actual_work_s, rel_tol=0.0, abs_tol=5e-10):
        raise RuntimeError("physical metadata offered work differs from its NPZ")
    return data, metadata, digest


def make_trace(data: dict[str, np.ndarray], indices: np.ndarray) -> Trace:
    indices = np.ascontiguousarray(indices, dtype=np.int64)
    arrival_us = np.ascontiguousarray(
        data["target_release_offset_ns"][indices] // 1000, dtype=np.int64
    )
    service_us = np.ascontiguousarray(
        data["requested_service_ns"][indices] // 1000, dtype=np.int64
    )
    scores = np.ascontiguousarray(data["score"][indices], dtype=np.float64)
    # In particular, do not subtract the first retained arrival after thinning.
    return Trace(arrival_us, service_us, {SCORE_KEY: scores}, limit_s=FORMAL_LIMIT_S)


def policy_objects(k: int):
    return (
        fcfs(),
        spjf(SCORE_KEY, "SPJF-E"),
        guard(
            PROMISE_S,
            k,
            FORMAL_LIMIT_S,
            15.0 * k,
            0.5,
            SCORE_KEY,
            name="Guard(300)",
            gam_s=0.0,
        ),
    )


def simulate_scenario(
    scenario: str,
    replicate: int | None,
    seed: int | None,
    k: int,
    indices: np.ndarray,
    data: dict[str, np.ndarray],
    full_work_us: int,
) -> list[dict]:
    trace = make_trace(data, indices)
    policies = policy_objects(k)
    baseline = simulate(trace, policies[0], k)
    work_us = int(trace.service_us.sum())
    common = {
        "scenario": scenario,
        "replicate": replicate,
        "seed": seed,
        "keep_probability": KEEP_PROBABILITY if replicate is not None else None,
        "k": k,
        "source_jobs": EXPECTED_JOBS,
        "jobs": len(trace),
        "job_fraction": len(trace) / EXPECTED_JOBS,
        "offered_work_s": work_us / 1e6,
        "work_fraction": work_us / full_work_us,
        "offered_work_over_300k": work_us / 1e6 / (WINDOW_S * k),
        "first_arrival_offset_s": float(trace.arrival_us[0] / 1e6),
        "last_arrival_offset_s": float(trace.arrival_us[-1] / 1e6),
    }
    rows = []
    for policy in policies:
        result = baseline if policy.name == "FCFS" else simulate(trace, policy, k)
        checks = 0
        if policy.name == "Guard(300)":
            checks = assert_per_job_bounds(
                result, baseline.wait_us, policy, k, FORMAL_LIMIT_S
            )
            if checks != len(trace):
                raise AssertionError("production guard bound did not check every job")
        wait_s = result.wait_us / 1e6
        excess_s = (result.wait_us - baseline.wait_us) / 1e6
        rows.append(
            {
                **common,
                "policy": policy.name,
                "mean_wait_s": float(wait_s.mean()),
                "p99_wait_s": float(np.quantile(wait_s, 0.99)),
                "max_wait_s": float(wait_s.max()),
                "max_excess_s": float(excess_s.max()),
                # n_forced has FIFO-kernel semantics for FCFS; it is a guard event only here.
                "guard_firings": int(result.n_forced)
                if policy.name == "Guard(300)"
                else 0,
                "guard_bound_checks": int(checks),
            }
        )
    return rows


def distribution(values) -> dict:
    array = np.asarray(values, dtype=np.float64)
    if array.shape != (REPLICATES,) or not np.isfinite(array).all():
        raise RuntimeError("Monte Carlo summary requires 100 finite values")
    q025, q50, q975 = np.quantile(array, [0.025, 0.5, 0.975])
    return {
        "n_random_thinnings": REPLICATES,
        "mean": float(array.mean()),
        "sample_sd": float(array.std(ddof=1)),
        "min": float(array.min()),
        "mc_p025": float(q025),
        "mc_median": float(q50),
        "mc_p975": float(q975),
        "max": float(array.max()),
        "range_interpretation": (
            "empirical central 95% range across the 100 fixed Bernoulli thinnings; "
            "not a confidence interval for a demand population"
        ),
    }


def write_csv(rows: list[dict]) -> None:
    fields = list(rows[0])
    if any(list(row) != fields for row in rows):
        raise AssertionError("thinning CSV rows have inconsistent fields")
    temporary = CSV_PATH.with_suffix(".csv.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(CSV_PATH)


def make_chart(rows: list[dict], references: dict[str, dict]) -> list[str]:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return []
    thin = [row for row in rows if row["scenario"] == "bernoulli_half_k2"]
    figure, axes = plt.subplots(1, 3, figsize=(12.0, 3.6), sharex=True)
    for axis, policy in zip(axes, POLICY_NAMES):
        selected = [row for row in thin if row["policy"] == policy]
        axis.scatter(
            [row["offered_work_over_300k"] for row in selected],
            [row["relative_p99_deviation_from_full_k4"] for row in selected],
            s=13,
            alpha=0.65,
            linewidths=0,
        )
        axis.axhline(0.0, color="black", linewidth=0.9)
        axis.axhline(
            references[policy]["full_k2_relative_p99_deviation_from_full_k4"],
            color="#b24a3a",
            linewidth=1.0,
            linestyle="--",
            label="unthinned k=2",
        )
        axis.set_title(policy)
        axis.set_xlabel("offered work / (300 k)")
        axis.grid(alpha=0.2)
    axes[0].set_ylabel("relative p99 deviation from full k=4")
    axes[-1].legend(frameon=False, fontsize=8)
    figure.suptitle("Frozen 300 s development window: random half-thinning to k=2")
    figure.text(
        0.5,
        0.01,
        "100 fixed Bernoulli replicas; scatter is a Monte Carlo sensitivity distribution, not a demand CI",
        ha="center",
        fontsize=8,
    )
    figure.tight_layout(rect=(0, 0.06, 1, 0.94))
    outputs = []
    for suffix in (".svg", ".png"):
        path = FIGURE_STEM.with_suffix(suffix)
        figure.savefig(path, dpi=180, bbox_inches="tight")
        outputs.append(path.name)
    plt.close(figure)
    return outputs


def main() -> None:
    started_wall = time.perf_counter()
    started_cpu = time.process_time()
    data, metadata, digest = load_frozen_input()
    full_indices = np.arange(EXPECTED_JOBS, dtype=np.int64)
    full_work_us = int((data["requested_service_ns"] // 1000).sum())

    rows = []
    rows.extend(
        simulate_scenario("full_k4_reference", None, None, FULL_K, full_indices, data, full_work_us)
    )
    rows.extend(
        simulate_scenario("full_k2_nominal", None, None, THIN_K, full_indices, data, full_work_us)
    )
    full_k4 = {
        row["policy"]: row for row in rows if row["scenario"] == "full_k4_reference"
    }
    if set(full_k4) != set(POLICY_NAMES):
        raise AssertionError("full k=4 reference is incomplete")

    retained_source_jobs = []
    for replicate in range(REPLICATES):
        seed = FIRST_SEED + replicate
        keep = np.random.default_rng(seed).random(EXPECTED_JOBS) < KEEP_PROBABILITY
        indices = np.flatnonzero(keep).astype(np.int64)
        if not len(indices):
            raise RuntimeError(f"seed {seed} retained no jobs")
        retained_source_jobs.append(data["job_id"][indices].astype(np.int64))
        rows.extend(
            simulate_scenario(
                "bernoulli_half_k2",
                replicate,
                seed,
                THIN_K,
                indices,
                data,
                full_work_us,
            )
        )

    for row in rows:
        denominator = full_k4[row["policy"]]["p99_wait_s"]
        row["relative_p99_deviation_from_full_k4"] = (
            (row["p99_wait_s"] - denominator) / denominator if denominator > 0 else None
        )

    thin_rows = [row for row in rows if row["scenario"] == "bernoulli_half_k2"]
    if len(thin_rows) != REPLICATES * len(POLICY_NAMES):
        raise AssertionError("random-thinning result matrix is incomplete")
    if sum(row["guard_bound_checks"] for row in thin_rows) != sum(
        len(indices) for indices in retained_source_jobs
    ):
        raise AssertionError("not every thinned Guard job received a production bound check")

    references = {}
    for policy in POLICY_NAMES:
        ref4 = next(
            row for row in rows
            if row["scenario"] == "full_k4_reference" and row["policy"] == policy
        )
        ref2 = next(
            row for row in rows
            if row["scenario"] == "full_k2_nominal" and row["policy"] == policy
        )
        references[policy] = {
            "full_k4": ref4,
            "full_k2_nominal": ref2,
            "full_k2_relative_p99_deviation_from_full_k4": ref2[
                "relative_p99_deviation_from_full_k4"
            ],
        }

    common_random = [
        row for row in thin_rows if row["policy"] == POLICY_NAMES[0]
    ]
    random_input_distribution = {
        metric: distribution([row[metric] for row in common_random])
        for metric in (
            "jobs",
            "job_fraction",
            "offered_work_s",
            "work_fraction",
            "offered_work_over_300k",
        )
    }
    random_policy_distribution = {}
    for policy in POLICY_NAMES:
        selected = [row for row in thin_rows if row["policy"] == policy]
        random_policy_distribution[policy] = {
            metric: distribution([row[metric] for row in selected])
            for metric in (
                "mean_wait_s",
                "p99_wait_s",
                "max_excess_s",
                "relative_p99_deviation_from_full_k4",
                "guard_firings",
            )
        }

    figures = make_chart(rows, references)
    execution = {
        "wall_s": time.perf_counter() - started_wall,
        "cpu_s": time.process_time() - started_cpu,
    }
    report = {
        "protocol": PROTOCOL,
        "parameters": PARAMETERS,
        "input_verification": {
            "path": INPUT.name,
            "sha256": digest,
            "metadata_path": METADATA.name,
            "physical_protocol_version": metadata["parameters"]["protocol_version"],
            "source_terms": metadata["source_terms"],
            "jobs": metadata["jobs"],
            "window_s": metadata["window_s"],
            "maximum_requested_service_s": float(
                data["requested_service_ns"].max() / 1e9
            ),
        },
        "scope": (
            "single preselected 300 s development window; evaluates first-moment scaling only; "
            "does not represent the full dataset, select a physical window or seed by benefit, "
            "or trigger another physical run"
        ),
        "gap_metric": (
            "omitted by the frozen design because no true-size SJF policy is simulated; "
            "all reported policy comparisons use FCFS on the identical retained jobs"
        ),
        "random_range_interpretation": (
            "the Monte Carlo ranges describe variability across the 100 fixed random half-thinnings "
            "of this one window; they are not confidence intervals for demand"
        ),
        "references": references,
        "random_input_distribution": random_input_distribution,
        "random_policy_distribution": random_policy_distribution,
        "production_guard_bound_checks": {
            "full_k4_jobs": next(
                row["guard_bound_checks"] for row in rows
                if row["scenario"] == "full_k4_reference" and row["policy"] == "Guard(300)"
            ),
            "full_k2_jobs": next(
                row["guard_bound_checks"] for row in rows
                if row["scenario"] == "full_k2_nominal" and row["policy"] == "Guard(300)"
            ),
            "random_thinned_jobs": sum(
                row["guard_bound_checks"] for row in thin_rows
            ),
            "all_assertions_passed": True,
        },
        "outputs": {
            "runs_csv": CSV_PATH.name,
            "summary_json": JSON_PATH.name,
            "log": LOG_PATH.name,
            "figures": figures,
        },
        "execution": execution,
    }
    write_csv(rows)
    write_json(JSON_PATH, report)
    log_lines = [
        "thinning check complete",
        f"protocol={PROTOCOL}",
        f"input_sha256={digest}",
        f"random_replicates={REPLICATES}",
        f"guard_jobs_checked={report['production_guard_bound_checks']['random_thinned_jobs']}",
        "random_ranges=Monte Carlo distribution across fixed thinnings; not demand confidence intervals",
        f"wall_s={execution['wall_s']:.9f}",
        f"cpu_s={execution['cpu_s']:.9f}",
        json.dumps(json_safe(report), allow_nan=False, separators=(",", ":")),
    ]
    atomic_text(LOG_PATH, "\n".join(log_lines) + "\n")
    print("\n".join(log_lines[:-1]), flush=True)


if __name__ == "__main__":
    main()
