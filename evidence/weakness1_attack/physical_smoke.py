"""Short, isolated physical dispatcher smoke test; it never uses project data."""

from __future__ import annotations

import hashlib
import json
import multiprocessing as mp
import os
from pathlib import Path
import sys
import time
import traceback


HERE = Path(__file__).resolve().parent
SMOKE_ROOT = HERE / "physical_smoke"
SMOKE_LOG_PATH = HERE / "out_physical_smoke.txt"
sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
os.environ["SPJF_PHYSICAL_RUNTIME_ROOT"] = str(SMOKE_ROOT / "cache")
sys.path.insert(0, str(HERE.parents[1] / "src"))
sys.path.insert(0, str(HERE / "pinned_src"))

import physical_service as physical


SMOKE_PARAMETERS = {
    "protocol": "synthetic-short-v3-qpc-occupied-workers",
    "clock": "time.perf_counter_ns",
    "source": "six fixed synthetic jobs; no project data",
    "workers": 2,
    "window_s": 0.5,
    "policies": ["FCFS", "SPJF-E", "Guard(300)"],
    "requested_service_s": [0.05, 0.05, 0.08, 0.04, 0.04, 0.04],
    "target_release_offset_s": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    "score": [0.0, 0.0, 100.0, 1.0, 2.0, 3.0],
    "guard": {
        "G_s": 0.5,
        "formal_L_s": 0.2,
        "B0_s": 0.01,
        "eta": 0.0,
        "gamma_s": 0.0,
        "Bmax_s": 0.2,
    },
    "wall_time_target_s": 30.0,
    "log_path": "out_physical_smoke.txt",
    "artifact_directory": "physical_smoke/",
    "expected_guard_behavior": (
        "the first two jobs occupy both workers; rank 2 has the worst score, and completed later-rank work exceeds the 10 ms "
        "budget and creates at least one nonempty fired set"
    ),
}
SMOKE_PROTOCOL = hashlib.sha256(
    json.dumps(SMOKE_PARAMETERS, sort_keys=True).encode()
).hexdigest()


def configure_isolated_smoke() -> None:
    """Override only this process's imported module state; formal files stay untouched."""
    physical.WINDOW_S = 0.5
    physical.WINDOW_NS = 500_000_000
    physical.FORMAL_LIMIT_S = 0.2
    physical.FORMAL_LIMIT_NS = 200_000_000
    physical.PROMISE_S = 0.5
    physical.B0_S = 0.01
    physical.B0_NS = 10_000_000
    physical.ETA = 0.0
    physical.ETA_K = 0.0
    physical.BMAX_S = 0.2
    physical.BMAX_NS = 200_000_000
    physical.PROTOCOL = SMOKE_PROTOCOL
    physical.RECORDS = SMOKE_ROOT / "records"


def synthetic_data():
    import numpy as np

    service_ns = np.array([50, 50, 80, 40, 40, 40], np.int64) * 1_000_000
    return {
        "job_id": np.arange(6, dtype=np.int64),
        "source_rank": np.arange(6, dtype=np.int64),
        "target_release_offset_ns": np.zeros(6, np.int64),
        "requested_service_ns": service_ns,
        "score": np.array([0.0, 0.0, 100.0, 1.0, 2.0, 3.0], np.float64),
        "in_deadline_window": np.ones(6, bool),
    }


def main() -> int:
    configure_isolated_smoke()
    SMOKE_ROOT.mkdir(parents=True, exist_ok=True)
    physical.write_json(
        SMOKE_ROOT / "smoke_parameters.json",
        {"protocol_hash": SMOKE_PROTOCOL, **SMOKE_PARAMETERS},
    )
    log = physical.RunLog(SMOKE_LOG_PATH)
    wall0 = time.perf_counter()
    cpu0 = time.process_time()
    audits = {}
    fcfs_jobs_path = SMOKE_ROOT / "physical_fcfs_jobs.jsonl"
    try:
        data = synthetic_data()
        for policy in SMOKE_PARAMETERS["policies"]:
            log.line(f"smoke start {policy}")
            run = physical.run_physical_policy(policy, data, SMOKE_PROTOCOL, log)
            audit, jobs = physical.audit_policy(
                policy,
                run,
                data,
                SMOKE_PROTOCOL,
                independent_fcfs_jobs_path=fcfs_jobs_path,
            )
            slug = physical.policy_slug(policy)
            jobs_path = SMOKE_ROOT / f"physical_{slug}_jobs.jsonl"
            decisions_path = SMOKE_ROOT / f"physical_{slug}_decisions.jsonl"
            audit_path = SMOKE_ROOT / f"physical_{slug}_audit.json"
            physical.write_jsonl(jobs_path, jobs)
            physical.write_jsonl(decisions_path, run["decisions"])
            physical.write_json(audit_path, audit)
            if not audit["event_prefix_audit"]["passed"]:
                raise AssertionError(f"{policy}: event-prefix audit failed")
            if audit["model_assumption_failed"] or audit["jobs_exceeding_L"] != 0:
                raise AssertionError(f"{policy}: synthetic service exceeded fixed L")
            if policy == "Guard(300)":
                if not audit["ideal_guard_epoch_audit"]["passed"]:
                    raise AssertionError("Guard: ideal dispatch-epoch audit failed")
                if audit["firing_comparison"]["physical_visible_prefix_count"] < 1:
                    raise AssertionError("Guard: synthetic trace did not fire physically")
                if audit["firing_comparison"]["physical_choice_changed_count"] < 1:
                    raise AssertionError("Guard: firing never changed the base choice")
                if audit["firing_comparison"]["production_replay_count"] < 1:
                    raise AssertionError("Guard: synthetic production replay did not fire")
                bound = audit["guard_bound"]
                if bound["production_replay_assertion"]["passed"] is not True:
                    raise AssertionError("Guard: production per-job bound assertion failed")
                if bound["production_replay_assertion"]["checked_jobs"] != len(data["job_id"]):
                    raise AssertionError("Guard: production bound did not check every job")
                if bound["physical_violations_against_same_measured_trace_shadow_fcfs"] != 0:
                    raise AssertionError("Guard: synthetic physical waits violated the bound")
            elif audit["firing_comparison"]["physical_visible_prefix_count"] != 0:
                raise AssertionError(f"{policy}: non-Guard policy reported guard firing")
            audits[policy] = audit
            log.line(
                f"smoke complete {policy}: prefix_errors="
                f"{audit['event_prefix_audit']['error_count']}"
            )

        elapsed = time.perf_counter() - wall0
        summary = {
            "protocol_hash": SMOKE_PROTOCOL,
            "parameters": SMOKE_PARAMETERS,
            "passed": True,
            "wall_s": elapsed,
            "root_cpu_s": time.process_time() - cpu0,
            "wall_time_target_met": elapsed < SMOKE_PARAMETERS["wall_time_target_s"],
            "coverage": {
                "real_two_worker_dispatcher": True,
                "workers_stopped_before_each_audit": True,
                "fcfs_prefix": audits["FCFS"]["event_prefix_audit"],
                "spjf_prefix": audits["SPJF-E"]["event_prefix_audit"],
                "guard_prefix": audits["Guard(300)"]["event_prefix_audit"],
                "guard_ideal_epochs": audits["Guard(300)"]["ideal_guard_epoch_audit"],
                "guard_physical_firing_count": audits["Guard(300)"][
                    "firing_comparison"
                ]["physical_visible_prefix_count"],
                "all_model_premises_hold": all(
                    not audit["model_assumption_failed"] for audit in audits.values()
                ),
                "guard_production_bound": audits["Guard(300)"]["guard_bound"][
                    "production_replay_assertion"
                ],
                "guard_physical_bound_violation_count": audits["Guard(300)"][
                    "guard_bound"
                ]["physical_violations_against_same_measured_trace_shadow_fcfs"],
            },
        }
        physical.write_json(SMOKE_ROOT / "summary.json", summary)
        log.line(f"PHYSICAL_SMOKE_COMPLETE wall={elapsed:.3f}s")
        return 0
    except BaseException as exc:
        failure = {
            "protocol_hash": SMOKE_PROTOCOL,
            "passed": False,
            "wall_s": time.perf_counter() - wall0,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }
        physical.write_json(SMOKE_ROOT / "summary.json", failure)
        log.line(f"PHYSICAL_SMOKE_FAILED {type(exc).__name__}: {exc}")
        raise
    finally:
        log.close()


if __name__ == "__main__":
    mp.freeze_support()
    raise SystemExit(main())
