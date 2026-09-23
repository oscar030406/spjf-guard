"""Validate timed-work artifacts and the integer-nanosecond FCFS bound."""

from __future__ import annotations

import csv
import hashlib
import heapq
import json
import math
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
import numpy as np


HERE = Path(__file__).resolve().parent
POLICIES = ("FCFS", "SPJF-E", "Guard(300)")
K = 2
L_NS = 61_000_000_000
G_NS = 300_000_000_000
# For k=2, B0=30 s, eta=1/2: (WF + B0/k + 2L)/(1-eta).
MULTIPLICATIVE_INTERCEPT_NS = 274_000_000_000
GUARD_PARAMETERS = {
    "G_s": 300.0,
    "formal_L_s": 61.0,
    "B0_s": 30.0,
    "eta": 0.5,
    "gamma_s": 0.0,
    "Bmax_s": 356.0,
}
FIXED_FIELDS = (
    "job_id",
    "source_rank",
    "target_release_offset_ns",
    "requested_service_ns",
    "score",
    "in_deadline_window",
)

OVERLAY_PROTOCOL = "27742c88b7ce6115c3942ac2c7a5654bfc18fcf784779f286e9262346bc75108"
OVERLAY_INPUT_SHA256 = "85a04f5c3a5de412310b6c066cfeed9ce09e5445eb591d01740102d1617e457d"
OVERLAY_JOBS = 2151


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            value.update(block)
    return value.hexdigest()


def load_physical_input(path: Path) -> dict[str, np.ndarray]:
    """Load the exact fixed-field schema used by the overlay physical run."""
    assert digest(path) == OVERLAY_INPUT_SHA256, "frozen overlay input hash changed"
    with np.load(path, allow_pickle=False) as store:
        if set(store.files) != set(FIXED_FIELDS):
            raise AssertionError(f"unexpected physical input schema: {sorted(store.files)}")
        data = {name: np.asarray(store[name]).copy() for name in FIXED_FIELDS}
    lengths = {name: len(value) for name, value in data.items()}
    assert len(set(lengths.values())) == 1, lengths
    return data


def _confined_path(run_dir: Path, relative: str) -> Path:
    path = (run_dir / relative).resolve()
    root = run_dir.resolve()
    assert path == root or root in path.parents, relative
    return path


def _expected_value(data: dict[str, np.ndarray], field: str, job_id: int):
    value = data[field][job_id]
    if field == "score":
        return float(value)
    if field == "in_deadline_window":
        return bool(value)
    return int(value)


def _assert_fixed_fields(
    jobs: list[dict],
    expected_fixed: dict[str, np.ndarray],
    expected_jobs: int,
) -> None:
    assert set(expected_fixed) == set(FIXED_FIELDS)
    assert {len(expected_fixed[name]) for name in FIXED_FIELDS} == {expected_jobs}
    assert np.array_equal(
        np.asarray(expected_fixed["job_id"], dtype=np.int64),
        np.arange(expected_jobs, dtype=np.int64),
    )
    for job_id, row in enumerate(jobs):
        for field in FIXED_FIELDS:
            expected = _expected_value(expected_fixed, field, job_id)
            observed = row[field]
            if field == "score":
                assert math.isfinite(expected) and observed == expected, (job_id, field)
            else:
                assert observed == expected, (job_id, field, observed, expected)


def verify_run(
    *,
    run_dir: Path,
    profile: str,
    expected_protocol: str,
    expected_input_sha256: str,
    expected_jobs: int,
    input_path: Path,
    expected_fixed: dict[str, np.ndarray],
    expected_protocol_version: int,
    expected_upstream: dict | None = None,
    exact_bound_name: str = "physical_exact_bound.csv",
    verification_name: str = "physical_verification.json",
    log_name: str = "out_verify_physical.txt",
) -> dict:
    """Verify one completed profile against independently supplied frozen input."""
    wall, cpu = time.perf_counter(), time.process_time()
    run_dir = Path(run_dir).resolve()
    input_path = Path(input_path).resolve()
    summary = json.loads((run_dir / "physical_summary.json").read_text(encoding="utf-8"))
    checkpoint = json.loads((run_dir / "physical_checkpoint.json").read_text(encoding="utf-8"))

    assert summary["completed_policies"] == list(POLICIES)
    assert set(summary["audits"]) == set(POLICIES)
    assert set(checkpoint["completed"]) == set(POLICIES)
    assert summary["protocol"] == checkpoint["protocol"] == expected_protocol
    assert summary["parameters"]["protocol_version"] == expected_protocol_version
    assert summary["parameters"]["workers"] == K
    assert summary["parameters"]["guard"] == GUARD_PARAMETERS
    assert summary["input"]["jobs"] == expected_jobs
    if expected_upstream is not None:
        assert summary["upstream_preflight"] == expected_upstream

    input_hash = digest(input_path)
    assert input_hash == expected_input_sha256
    assert input_hash == checkpoint["input_sha256"] == summary["input"]["input_sha256"]

    results: dict[str, dict] = {}
    for policy in POLICIES:
        slug = policy.lower().replace("(", "_").replace(")", "").replace("-", "_")
        expected_paths = {
            "jobs": run_dir / f"physical_{slug}_jobs.jsonl",
            "decisions": run_dir / f"physical_{slug}_decisions.jsonl",
            "audit": run_dir / f"physical_{slug}_audit.json",
        }
        entry = checkpoint["completed"][policy]
        assert entry["policy"] == policy
        assert entry["input_sha256"] == input_hash
        artifact_paths = {}
        for key, canonical in expected_paths.items():
            artifact = _confined_path(run_dir, entry[key]["path"])
            assert artifact == canonical.resolve()
            assert artifact.is_file()
            assert artifact.stat().st_size == entry[key]["bytes"]
            assert digest(artifact) == entry[key]["sha256"]
            artifact_paths[key] = artifact

        jobs = [
            json.loads(line)
            for line in artifact_paths["jobs"].read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        jobs.sort(key=lambda row: row["job_id"])
        assert [row["job_id"] for row in jobs] == list(range(expected_jobs))
        assert sorted(row["dispatch_index"] for row in jobs) == list(range(expected_jobs))
        _assert_fixed_fields(jobs, expected_fixed, expected_jobs)
        for row in jobs:
            assert row["protocol"] == expected_protocol
            assert row["input_sha256"] == input_hash
            assert row["policy"] == policy
            assert row["rank"] == row["job_id"]

        artifact_audit = json.loads(artifact_paths["audit"].read_text(encoding="utf-8"))
        audit = summary["audits"][policy]
        assert audit == artifact_audit
        assert audit["protocol"] == expected_protocol
        assert audit["input_sha256"] == input_hash
        assert audit["policy"] == policy and audit["jobs"] == expected_jobs
        prefix = audit["event_prefix_audit"]
        assert prefix["passed"] and prefix["error_count"] == 0
        assert prefix["dispatches_checked"] == expected_jobs
        event_path = _confined_path(run_dir, prefix["event_path"])
        assert event_path.is_file() and digest(event_path) == prefix["event_sha256"]
        assert not audit["model_assumption_failed"] and audit["jobs_exceeding_L"] == 0
        assert audit["wait_comparison"]["per_job_compared"] == expected_jobs

        last_arrival = -1
        worker_ids = set()
        origin_ns = jobs[0]["target_release_ns"] - jobs[0]["target_release_offset_ns"]
        for row in jobs:
            assert (
                last_arrival
                <= row["actual_enqueue_ns"]
                <= row["decision_clock_ns"]
                <= row["dispatcher_dispatch_ns"]
                <= row["worker_start_ns"]
                <= row["worker_finish_ns"]
                <= row["dispatcher_completion_receipt_ns"]
            )
            assert row["target_release_ns"] <= row["actual_enqueue_ns"]
            assert row["target_release_ns"] - row["target_release_offset_ns"] == origin_ns
            assert row["release_lateness_ns"] == (
                row["actual_enqueue_ns"] - row["target_release_ns"]
            )
            # Pipe send-return and worker receipt are both after dispatch, but their
            # mutual order is not assumed.
            assert row["dispatcher_dispatch_ns"] <= row["command_receipt_ns"]
            assert row["command_receipt_ns"] <= row["worker_start_ns"]
            assert row["dispatcher_dispatch_ns"] <= row["dispatch_send_return_ns"]
            last_arrival = row["actual_enqueue_ns"]
            assert 0 < row["worker_holding_ns"] <= L_NS
            assert row["worker_holding_ns"] == (
                row["worker_finish_ns"] - row["worker_start_ns"]
            )
            assert row["actual_wait_ns"] == row["worker_start_ns"] - row["actual_enqueue_ns"]
            worker = row["worker_id"]
            assert type(worker) is int and 0 <= worker < K
            worker_ids.add(worker)
        assert worker_ids == set(range(K))
        for worker in range(K):
            ordered = sorted(
                (row for row in jobs if row["worker_id"] == worker),
                key=lambda row: row["worker_start_ns"],
            )
            assert all(
                left["worker_finish_ns"] <= right["worker_start_ns"]
                for left, right in zip(ordered, ordered[1:])
            )

        results[policy] = {
            "jobs": len(jobs),
            "input_fixed_fields_match": True,
            "artifact_audit_equals_summary_audit": True,
            "exact_clock_order_passed": True,
            "positive_measured_services": True,
            "valid_worker_ids": True,
            "worker_intervals_do_not_overlap": True,
        }
        if policy != "Guard(300)":
            continue

        assert audit["ideal_guard_epoch_audit"]["passed"]
        assert audit["ideal_guard_epoch_audit"]["dispatches_checked"] == len(jobs)
        assert audit["guard_bound"]["production_replay_assertion"]["passed"]
        assert (
            audit["guard_bound"]["production_replay_assertion"]["checked_jobs"]
            == len(jobs)
        )
        assert (
            audit["guard_bound"][
                "physical_violations_against_same_measured_trace_shadow_fcfs"
            ]
            == 0
        )
        availability = [jobs[0]["actual_enqueue_ns"]] * K
        rows = []
        for job in jobs:
            start = max(job["actual_enqueue_ns"], availability[0])
            heapq.heapreplace(availability, start + job["worker_holding_ns"])
            shadow_wait = start - job["actual_enqueue_ns"]
            bound = min(
                shadow_wait + G_NS,
                2 * shadow_wait + MULTIPLICATIVE_INTERCEPT_NS,
            )
            excess = job["actual_wait_ns"] - shadow_wait
            rows.append(
                {
                    "job_id": job["job_id"],
                    "actual_wait_ns": job["actual_wait_ns"],
                    "exact_shadow_fcfs_wait_ns": shadow_wait,
                    "exact_guard_upper_bound_ns": bound,
                    "exact_excess_ns": excess,
                    "bound_slack_ns": bound - job["actual_wait_ns"],
                    "production_shadow_rounding_error_ns": (
                        job["same_measured_trace_shadow_fcfs_wait_us"] * 1000
                        - shadow_wait
                    ),
                }
            )
        with (run_dir / exact_bound_name).open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        violations = sum(row["bound_slack_ns"] < 0 for row in rows)
        results[policy].update(
            exact_nanosecond_bound_checks=len(rows),
            exact_nanosecond_violations=violations,
            max_exact_excess_s=max(row["exact_excess_ns"] for row in rows) / 1e9,
            minimum_bound_slack_s=min(row["bound_slack_ns"] for row in rows) / 1e9,
            max_abs_production_shadow_rounding_error_s=max(
                abs(row["production_shadow_rounding_error_ns"]) for row in rows
            )
            / 1e9,
        )
        assert violations == 0, results[policy]

    assert digest(input_path) == input_hash
    result = {
        "status": "PASS",
        "profile": profile,
        "protocol": expected_protocol,
        "input_path": str(input_path),
        "input_sha256": input_hash,
        "jobs": expected_jobs,
        "scope": (
            "all physical jobs and an independent integer-nanosecond shadow-FCFS check; "
            "observed-run audit, not a future real-time guarantee"
        ),
        "policies": results,
        "execution": {
            "wall_s": time.perf_counter() - wall,
            "cpu_s": time.process_time() - cpu,
        },
    }
    text = json.dumps(result, indent=2) + "\n"
    (run_dir / verification_name).write_text(text, encoding="utf-8")
    (run_dir / log_name).write_text(text, encoding="utf-8")
    print(text, end="")
    return result


def main() -> None:
    verify_run(
        run_dir=HERE,
        profile="development_overlay",
        expected_protocol=OVERLAY_PROTOCOL,
        expected_input_sha256=OVERLAY_INPUT_SHA256,
        expected_jobs=OVERLAY_JOBS,
        input_path=HERE / "physical_input.npz",
        expected_fixed=load_physical_input(HERE / "physical_input.npz"),
        expected_protocol_version=2,
    )


if __name__ == "__main__":
    main()
