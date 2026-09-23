"""Run the frozen two-worker timed-sleep physical service experiment.

This file is intentionally not imported by the capacity sweep.  Its worker processes do
only blocking receive, sleep for the requested duration, and return timestamps.  The root
process is the sole dispatcher and learns measured service only from completion messages.
"""

from __future__ import annotations

import hashlib
import json
import math
import multiprocessing as mp
from multiprocessing.connection import wait as wait_connections
import os
from pathlib import Path
import sys
import time
import traceback


HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
RUNTIME_ROOT = Path(
    os.environ.get("SPJF_PHYSICAL_RUNTIME_ROOT", str(HERE / "cache"))
).resolve()
if HERE.resolve() not in (RUNTIME_ROOT, *RUNTIME_ROOT.parents):
    raise RuntimeError("physical runtime root must remain inside weakness1_attack")
for _key, _value in {
    "PYTHONDONTWRITEBYTECODE": "1",
    "NUMBA_NUM_THREADS": "1",
    "OMP_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "NUMBA_CACHE_DIR": str(RUNTIME_ROOT / "numba"),
    "TMP": str(RUNTIME_ROOT / "tmp"),
    "TEMP": str(RUNTIME_ROOT / "tmp"),
}.items():
    os.environ[_key] = _value
(RUNTIME_ROOT / "tmp").mkdir(parents=True, exist_ok=True)

K = 2
WINDOW_S = 300.0
WINDOW_NS = 300_000_000_000
FORMAL_LIMIT_S = 61.0
FORMAL_LIMIT_NS = 61_000_000_000
PROMISE_S = 300.0
B0_S = 30.0
B0_NS = 30_000_000_000
ETA = 0.5
ETA_K = ETA * K
BMAX_S = K * (PROMISE_S - (3.0 - 2.0 / K) * FORMAL_LIMIT_S)
BMAX_NS = int(round(BMAX_S * 1e9))
POLICIES = ("FCFS", "SPJF-E", "Guard(300)")
SCORE_KEY = "tweedie"
PROGRESS_S = 30.0
RECORDS = HERE / "physical_records"
INPUT_PATH = HERE / "physical_input.npz"
INPUT_METADATA = HERE / "physical_input_metadata.json"
CHECKPOINT_PATH = HERE / "physical_checkpoint.json"
SUMMARY_PATH = HERE / "physical_summary.json"
LOG_PATH = HERE / "out_physical_service.txt"

PARAMETERS = {
    "protocol_version": 2,
    "source": "primary_rep0",
    "selection": "largest offered capped-service sum in a complete calendar-aligned 300 s bin",
    "window_s": WINDOW_S,
    "workers": K,
    "policies": list(POLICIES),
    "policy_order": "sequential",
    "requested_service": "unchanged source C_cap, at most 60 s",
    "arrival_spacing": "unchanged within selected calendar bin",
    "guard": {
        "G_s": PROMISE_S,
        "formal_L_s": FORMAL_LIMIT_S,
        "B0_s": B0_S,
        "eta": ETA,
        "gamma_s": 0.0,
        "Bmax_s": BMAX_S,
    },
    "clock": "time.perf_counter_ns (system-wide monotonic QPC on Windows)",
    "service_for_guard": "worker_finish_ns - worker_start_ns, learned at completion receipt",
}
PROTOCOL = hashlib.sha256(json.dumps(PARAMETERS, sort_keys=True).encode()).hexdigest()
CLOCK_INFO = time.get_clock_info('perf_counter')
if not CLOCK_INFO.monotonic or CLOCK_INFO.adjustable or CLOCK_INFO.resolution > 1e-6:
    raise RuntimeError('physical timing requires a nonadjustable monotonic clock with <=1 us resolution')


def json_safe(value):
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    try:
        import numpy as np

        if isinstance(value, np.ndarray):
            return [json_safe(v) for v in value.tolist()]
        if isinstance(value, np.integer):
            return int(value)
        if isinstance(value, np.floating):
            value = float(value)
    except ImportError:
        pass
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def atomic_text(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="")
    tmp.replace(path)


def write_json(path: Path, value) -> None:
    atomic_text(path, json.dumps(json_safe(value), indent=2, allow_nan=False) + "\n")


def append_jsonl(handle, value) -> None:
    handle.write(json.dumps(json_safe(value), allow_nan=False, separators=(",", ":")) + "\n")
    handle.flush()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


class RunLog:
    def __init__(self, path: Path):
        self.handle = open(path, "a", encoding="utf-8", buffering=1)

    def line(self, message: str) -> None:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        text = f"[{stamp}] {message}"
        print(text, flush=True)
        self.handle.write(text + "\n")

    def close(self) -> None:
        self.handle.close()


class Fenwick:
    """Completed measured worker-holding time by immutable arrival rank."""

    def __init__(self, n: int):
        self.tree = [0] * (n + 1)

    def add(self, index: int, value: int) -> None:
        pos = index + 1
        while pos < len(self.tree):
            self.tree[pos] += value
            pos += pos & -pos

    def prefix_inclusive(self, index: int) -> int:
        pos = index + 1
        total = 0
        while pos:
            total += self.tree[pos]
            pos -= pos & -pos
        return total


def worker_main(worker_id: int, connection) -> None:
    """Persistent worker: receive one job, sleep, return actual monotonic timestamps."""
    process_cpu_origin_ns = time.process_time_ns()
    connection.send(
        {
            "type": "ready",
            "worker_id": worker_id,
            "ready_ns": time.perf_counter_ns(),
            "pid": os.getpid(),
        }
    )
    try:
        while True:
            command = connection.recv()
            received_ns = time.perf_counter_ns()
            if command["type"] == "stop":
                break
            if command["type"] != "run":
                raise RuntimeError(f"unknown worker command {command!r}")
            requested_ns = int(command["requested_service_ns"])
            cpu0 = time.process_time_ns()
            start_ns = time.perf_counter_ns()
            time.sleep(requested_ns / 1e9)
            finish_ns = time.perf_counter_ns()
            cpu1 = time.process_time_ns()
            connection.send(
                {
                    "type": "completion",
                    "worker_id": worker_id,
                    "job_id": int(command["job_id"]),
                    "command_receipt_ns": received_ns,
                    "worker_start_ns": start_ns,
                    "worker_finish_ns": finish_ns,
                    "worker_holding_ns": finish_ns - start_ns,
                    "requested_service_ns": requested_ns,
                    "worker_cpu_ns": cpu1 - cpu0,
                    "worker_cpu_cumulative_ns": cpu1 - process_cpu_origin_ns,
                }
            )
    finally:
        connection.close()


def select_input() -> tuple[dict, dict]:
    """Guarded-load rep 0 and deterministically select the busiest complete five minutes."""
    import numpy as np

    from common import TERMS, development_overlay

    trace, labels = development_overlay(0)
    arrival_ns = np.asarray(trace.arrival_us, np.int64) * 1000
    service_ns = np.asarray(trace.service_us, np.int64) * 1000
    score = np.asarray(trace.score_for(SCORE_KEY), np.float64)
    bin_id, inverse = np.unique(arrival_ns // WINDOW_NS, return_inverse=True)
    work_ns = np.zeros(len(bin_id), np.int64)
    np.add.at(work_ns, inverse, service_ns)
    bin_start = bin_id * WINDOW_NS
    complete = (bin_start >= arrival_ns[0]) & (bin_start + WINDOW_NS <= arrival_ns[-1])
    if not complete.any():
        raise RuntimeError("the overlay contains no complete calendar-aligned 300 s bin")
    candidates = np.flatnonzero(complete)
    winner = int(candidates[np.argmax(work_ns[candidates])])
    start_ns = int(bin_start[winner])
    stop_ns = start_ns + WINDOW_NS
    selected = np.flatnonzero((arrival_ns >= start_ns) & (arrival_ns < stop_ns))
    if not len(selected):
        raise RuntimeError("selected busy window is empty")
    data = {
        "job_id": np.arange(len(selected), dtype=np.int64),
        "source_rank": selected.astype(np.int64),
        "target_release_offset_ns": (arrival_ns[selected] - start_ns).astype(np.int64),
        "requested_service_ns": service_ns[selected].astype(np.int64),
        "score": score[selected].astype(np.float64),
        "in_deadline_window": np.asarray(labels["in_window"])[selected].astype(bool),
    }
    if np.any(np.diff(data["target_release_offset_ns"]) < 0):
        raise AssertionError("selected arrivals are not in rank order")
    if int(data["requested_service_ns"].max()) > 60_000_000_000:
        raise AssertionError("requested payload exceeds the frozen 60 s cap")
    metadata = {
        "protocol": PROTOCOL,
        "parameters": PARAMETERS,
        "source_terms": list(TERMS),
        "source_rep": 0,
        "selection_used_policy_outcomes": False,
        "calendar_bin_id": int(bin_id[winner]),
        "source_window_start_ns": start_ns,
        "source_window_stop_ns": stop_ns,
        "window_s": WINDOW_S,
        "jobs": int(len(selected)),
        "offered_requested_work_s": float(data["requested_service_ns"].sum() / 1e9),
        "offered_work_per_worker_s": float(data["requested_service_ns"].sum() / (K * 1e9)),
        "work_only_drain_lower_bound_s": max(
            0.0, float(data["requested_service_ns"].sum() / (K * 1e9) - WINDOW_S)
        ),
        "first_target_offset_s": float(data["target_release_offset_ns"][0] / 1e9),
        "last_target_offset_s": float(data["target_release_offset_ns"][-1] / 1e9),
        "source_busy_hour_work_s": float(labels["busy_hour_work_s"]),
        "source_copies": int(labels["copies"]),
    }
    return data, metadata


def prepare_input() -> tuple[dict, dict, str]:
    """Create or verify the frozen input; every invocation uses the guarded dev loader."""
    import numpy as np

    selected, metadata = select_input()
    if INPUT_PATH.exists() != INPUT_METADATA.exists():
        raise RuntimeError("physical input is partial: NPZ and metadata must exist together")
    if INPUT_PATH.exists():
        recorded = json.loads(INPUT_METADATA.read_text(encoding="utf-8"))
        if recorded.get("protocol") != PROTOCOL:
            raise RuntimeError("existing physical input belongs to another protocol")
        with np.load(INPUT_PATH, allow_pickle=False) as store:
            if set(store.files) != set(selected):
                raise RuntimeError("existing physical input array schema differs")
            for name, expected in selected.items():
                if not np.array_equal(store[name], expected, equal_nan=True):
                    raise RuntimeError(f"existing physical input differs at array {name}")
        digest = sha256_file(INPUT_PATH)
        if digest != recorded.get("input_sha256"):
            raise RuntimeError("existing physical input hash differs from its metadata")
        return selected, recorded, digest
    tmp = HERE / "physical_input.tmp.npz"
    np.savez(tmp, **selected)
    tmp.replace(INPUT_PATH)
    digest = sha256_file(INPUT_PATH)
    metadata["input_sha256"] = digest
    metadata["written_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    write_json(INPUT_METADATA, metadata)
    return selected, metadata, digest


def policy_slug(policy: str) -> str:
    return policy.lower().replace("(", "_").replace(")", "").replace("-", "_")


def policy_object(name: str):
    from spjf_guard.sim.policy import fcfs, guard, spjf

    if name == "FCFS":
        return fcfs()
    if name == "SPJF-E":
        return spjf(SCORE_KEY, "SPJF-E")
    if name == "Guard(300)":
        return guard(PROMISE_S, K, FORMAL_LIMIT_S, B0_S, ETA, SCORE_KEY)
    raise ValueError(name)


def base_choice(policy: str, waiting: list[int], score) -> int:
    if policy == "FCFS":
        return min(waiting)
    return min(waiting, key=lambda job: (float(score[job]), job))


def choose_job(
    policy: str,
    waiting: list[int],
    score,
    enqueue_ns: list[int],
    waiting_at_arrival: list[int],
    completed_work_ns: int,
    completed_by_rank: Fenwick,
    decision_ns: int,
) -> tuple[int, dict]:
    """Algorithm 1 choice from only dispatcher-visible completions and enqueues."""
    cpu0, wall0 = time.process_time_ns(), time.perf_counter_ns()
    base = base_choice(policy, waiting, score)
    evaluations = []
    fired = []
    if policy == "Guard(300)":
        for job in sorted(waiting):
            over_ns = completed_work_ns - completed_by_rank.prefix_inclusive(job)
            age_ns = max(0, decision_ns - enqueue_ns[job])
            constant_ns = B0_NS  # gamma = 0; retained explicitly in the audit row
            budget_ns = min(constant_ns + int(round(ETA_K * age_ns)), BMAX_NS)
            is_fired = over_ns >= budget_ns
            if is_fired:
                fired.append(job)
            evaluations.append(
                {
                    "job_id": job,
                    "rank": job,
                    "score": float(score[job]),
                    "enqueue_ns": enqueue_ns[job],
                    "age_ns": age_ns,
                    "waiting_at_arrival": waiting_at_arrival[job],
                    "over_completed_worker_holding_ns": over_ns,
                    "budget_ns": budget_ns,
                    "fired": is_fired,
                }
            )
    chosen = min(fired) if fired else base
    wall1, cpu1 = time.perf_counter_ns(), time.process_time_ns()
    decision = {
        "decision_clock_ns": decision_ns,
        "policy": policy,
        "waiting_ranks": sorted(waiting),
        "waiting_evaluation": evaluations,
        "fired_set": fired,
        "minimum_fired_rank": min(fired) if fired else None,
        "base_choice": base,
        "chosen_job": chosen,
        "guard_fired": bool(fired),
        "choice_changed": chosen != base,
        "choice_reason": "minimum_fired_rank" if fired else "base_policy",
        "visible_completed_work_ns": completed_work_ns,
        "decision_wall_overhead_ns": wall1 - wall0,
        "decision_cpu_overhead_ns": cpu1 - cpu0,
    }
    return chosen, decision


def load_checkpoint(input_sha256: str) -> dict:
    if not CHECKPOINT_PATH.exists():
        return {"protocol": PROTOCOL, "input_sha256": input_sha256, "completed": {}}
    checkpoint = json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
    if checkpoint.get("protocol") != PROTOCOL or checkpoint.get("input_sha256") != input_sha256:
        raise RuntimeError("physical checkpoint belongs to another protocol or input")
    for policy, entry in checkpoint.get("completed", {}).items():
        for key in ("jobs", "decisions", "audit"):
            path = HERE / entry[key]["path"]
            if not path.is_file() or sha256_file(path) != entry[key]["sha256"]:
                raise RuntimeError(f"completed checkpoint for {policy} has stale {key}")
    return checkpoint


def stop_workers(processes, parent_connections) -> None:
    for connection in parent_connections:
        try:
            connection.send({"type": "stop"})
        except (BrokenPipeError, EOFError, OSError):
            pass
    for process in processes:
        if process.pid is None:
            continue
        process.join(timeout=10.0)
        if process.is_alive():
            process.terminate()
            process.join(timeout=5.0)
    for connection in parent_connections:
        connection.close()


def write_jsonl(path: Path, rows: list[dict]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as handle:
        for row in rows:
            append_jsonl(handle, row)
    tmp.replace(path)


def audit_event_prefix(policy: str, run: dict, data: dict, jobs: list[dict]) -> dict:
    """Independently rebuild every dispatcher-visible prefix from the event JSONL."""
    event_path = HERE / run["attempt_event_path"]
    events = [
        json.loads(line)
        for line in event_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    decisions = {int(row["decision_index"]): row for row in run["decisions"]}
    jobs_by_id = {int(row["job_id"]): row for row in jobs}
    waiting: set[int] = set()
    enqueued: dict[int, int] = {}
    enqueue_order: list[int] = []
    completed_cost: dict[int, int] = {}
    running_by_worker: dict[int, int] = {}
    dispatched: set[int] = set()
    dispatch_order: list[int] = []
    origin_ns = None
    counts: dict[str, int] = {}
    first_error = None
    last_visible_clock_ns = None
    decisions_with_target_due_unenqueued = 0
    target_due_unenqueued_occurrences = 0
    max_target_due_unenqueued_lateness_ns = 0
    first_target_due_unenqueued = None

    def check(condition: bool, kind: str, expected, actual, context: dict) -> None:
        nonlocal first_error
        if condition:
            return
        counts[kind] = counts.get(kind, 0) + 1
        if first_error is None:
            first_error = {
                "kind": kind,
                "expected": json_safe(expected),
                "actual": json_safe(actual),
                "context": json_safe(context),
            }

    def check_clock(clock_ns, event_index: int, event_type: str) -> None:
        nonlocal last_visible_clock_ns
        if clock_ns is None:
            return
        clock_ns = int(clock_ns)
        if last_visible_clock_ns is not None:
            check(
                clock_ns >= last_visible_clock_ns,
                "visible_event_clock_regression",
                f">={last_visible_clock_ns}",
                clock_ns,
                {"event_index": event_index, "event_type": event_type},
            )
        last_visible_clock_ns = max(clock_ns, last_visible_clock_ns or clock_ns)

    for event_index, event in enumerate(events):
        event_type = event.get("type")
        context = {"event_index": event_index, "event_type": event_type}
        if event_type == "policy_start":
            origin_ns = int(event["origin_ns"])
            check_clock(origin_ns, event_index, event_type)
        elif event_type == "arrival_enqueued":
            job = int(event["job_id"])
            actual_ns = int(event["actual_enqueue_ns"])
            waiting_before = len(waiting)
            check_clock(actual_ns, event_index, event_type)
            check(job not in enqueued, "duplicate_enqueue", "not previously enqueued", job, context)
            check(job not in dispatched, "enqueue_after_dispatch", False, True, context)
            check(
                actual_ns >= int(event["target_release_ns"]),
                "enqueue_before_target",
                f">={event['target_release_ns']}",
                actual_ns,
                context,
            )
            check(
                int(event["waiting_at_arrival"]) == waiting_before,
                "event_waiting_at_arrival",
                waiting_before,
                int(event["waiting_at_arrival"]),
                context,
            )
            check(
                int(jobs_by_id[job]["waiting_at_arrival"]) == waiting_before,
                "job_waiting_at_arrival",
                waiting_before,
                int(jobs_by_id[job]["waiting_at_arrival"]),
                context,
            )
            enqueued[job] = actual_ns
            waiting.add(job)
            enqueue_order.append(job)
        elif event_type == "completion_visible":
            job = int(event["job_id"])
            worker = int(event["worker_id"])
            receipt_ns = int(event["dispatcher_completion_receipt_ns"])
            check_clock(receipt_ns, event_index, event_type)
            check(
                running_by_worker.get(worker) == job,
                "completion_worker_assignment",
                running_by_worker.get(worker),
                job,
                context,
            )
            check(job not in completed_cost, "duplicate_completion", False, True, context)
            row = jobs_by_id[job]
            check(
                int(event["worker_start_ns"]) == int(row["worker_start_ns"]),
                "event_worker_start",
                int(row["worker_start_ns"]),
                int(event["worker_start_ns"]),
                context,
            )
            check(
                int(event["worker_finish_ns"]) == int(row["worker_finish_ns"]),
                "event_worker_finish",
                int(row["worker_finish_ns"]),
                int(event["worker_finish_ns"]),
                context,
            )
            check(
                int(event["charged_worker_holding_ns"]) == int(row["worker_holding_ns"]),
                "completion_charge",
                int(row["worker_holding_ns"]),
                int(event["charged_worker_holding_ns"]),
                context,
            )
            completed_cost[job] = int(event["charged_worker_holding_ns"])
            check(
                int(event["visible_completed_work_ns"]) == sum(completed_cost.values()),
                "event_visible_completed_work",
                sum(completed_cost.values()),
                int(event["visible_completed_work_ns"]),
                context,
            )
            running_by_worker.pop(worker, None)
        elif event_type == "dispatch":
            index = int(event["decision_index"])
            actual_job = int(event["job_id"])
            worker = int(event["worker_id"])
            dispatch_ns = int(event["dispatcher_dispatch_ns"])
            check_clock(dispatch_ns, event_index, event_type)
            check(index == len(dispatch_order), "dispatch_index_sequence", len(dispatch_order), index, context)
            check(actual_job in waiting, "dispatch_not_waiting", True, actual_job in waiting, context)
            check(worker not in running_by_worker, "dispatch_to_busy_worker", False, True, context)
            decision = decisions.get(index)
            check(decision is not None, "missing_decision_row", True, False, context)
            if decision is None:
                if actual_job in waiting:
                    waiting.remove(actual_job)
                dispatched.add(actual_job)
                running_by_worker[worker] = actual_job
                dispatch_order.append(actual_job)
                continue
            decision_clock_ns = int(decision["decision_clock_ns"])
            check(
                decision_clock_ns <= dispatch_ns,
                "decision_after_dispatch",
                f"<={dispatch_ns}",
                decision_clock_ns,
                context,
            )
            check(
                int(decision["dispatcher_visible_completion_count"])
                == len(completed_cost),
                "decision_completion_count",
                len(completed_cost),
                int(decision["dispatcher_visible_completion_count"]),
                context,
            )
            check(
                int(decision["dispatcher_enqueued_count"]) == len(enqueued),
                "decision_enqueue_count",
                len(enqueued),
                int(decision["dispatcher_enqueued_count"]),
                context,
            )
            waiting_ranks = sorted(waiting)
            check(
                list(decision["waiting_ranks"]) == waiting_ranks,
                "decision_waiting_set",
                waiting_ranks,
                decision["waiting_ranks"],
                context,
            )
            if origin_ns is not None:
                due = {
                    job
                    for job in range(len(jobs))
                    if origin_ns + int(data["target_release_offset_ns"][job])
                    <= decision_clock_ns
                }
                due_unenqueued = sorted(due.difference(enqueued))
                if due_unenqueued:
                    decisions_with_target_due_unenqueued += 1
                    target_due_unenqueued_occurrences += len(due_unenqueued)
                    lateness = max(
                        decision_clock_ns
                        - (origin_ns + int(data["target_release_offset_ns"][job]))
                        for job in due_unenqueued
                    )
                    max_target_due_unenqueued_lateness_ns = max(
                        max_target_due_unenqueued_lateness_ns, lateness
                    )
                    if first_target_due_unenqueued is None:
                        first_target_due_unenqueued = {
                            "decision_index": index,
                            "decision_clock_ns": decision_clock_ns,
                            "job_ids": due_unenqueued,
                            "max_lateness_ns": lateness,
                        }
            for job, actual_enqueue_ns in enqueued.items():
                check(
                    actual_enqueue_ns <= decision_clock_ns,
                    "observed_enqueue_after_decision",
                    f"<={decision_clock_ns}",
                    actual_enqueue_ns,
                    {**context, "job_id": job},
                )
            expected_base = (
                min(waiting_ranks)
                if policy == "FCFS"
                else min(waiting_ranks, key=lambda job: (float(data["score"][job]), job))
            )
            expected_evaluations = []
            expected_fired = []
            if policy == "Guard(300)":
                completed_suffix_ns = [0] * (len(jobs) + 1)
                for completed_job, cost in completed_cost.items():
                    completed_suffix_ns[completed_job] += cost
                for rank in range(len(jobs) - 1, -1, -1):
                    completed_suffix_ns[rank] += completed_suffix_ns[rank + 1]
                for job in waiting_ranks:
                    over_ns = completed_suffix_ns[job + 1]
                    age_ns = max(0, decision_clock_ns - enqueued[job])
                    budget_ns = min(B0_NS + int(round(ETA_K * age_ns)), BMAX_NS)
                    fired = over_ns >= budget_ns
                    if fired:
                        expected_fired.append(job)
                    expected_evaluations.append(
                        {
                            "job_id": job,
                            "rank": job,
                            "score": float(data["score"][job]),
                            "enqueue_ns": enqueued[job],
                            "waiting_at_arrival": int(
                                jobs_by_id[job]["waiting_at_arrival"]
                            ),
                            "age_ns": age_ns,
                            "over_completed_worker_holding_ns": over_ns,
                            "budget_ns": budget_ns,
                            "fired": fired,
                        }
                    )
            expected_choice = min(expected_fired) if expected_fired else expected_base
            actual_eval = {int(row["job_id"]): row for row in decision["waiting_evaluation"]}
            check(
                set(actual_eval) == {row["job_id"] for row in expected_evaluations},
                "evaluation_job_set",
                [row["job_id"] for row in expected_evaluations],
                sorted(actual_eval),
                context,
            )
            for expected in expected_evaluations:
                actual = actual_eval.get(expected["job_id"], {})
                for field in (
                    "rank",
                    "score",
                    "enqueue_ns",
                    "waiting_at_arrival",
                    "age_ns",
                    "over_completed_worker_holding_ns",
                    "budget_ns",
                    "fired",
                ):
                    check(
                        actual.get(field) == expected[field],
                        f"evaluation_{field}",
                        expected[field],
                        actual.get(field),
                        {**context, "job_id": expected["job_id"]},
                    )
            expected_guard_fired = bool(expected_fired)
            expected_changed = expected_choice != expected_base
            checks = {
                "base_choice": expected_base,
                "fired_set": expected_fired,
                "minimum_fired_rank": min(expected_fired) if expected_fired else None,
                "chosen_job": expected_choice,
                "guard_fired": expected_guard_fired,
                "choice_changed": expected_changed,
                "visible_completed_work_ns": sum(completed_cost.values()),
            }
            for field, expected in checks.items():
                check(
                    decision.get(field) == expected,
                    f"decision_{field}",
                    expected,
                    decision.get(field),
                    context,
                )
            for field, expected in (
                ("decision_index", index),
                ("worker_id", worker),
                ("dispatcher_dispatch_ns", dispatch_ns),
                ("policy", policy),
            ):
                check(
                    decision.get(field) == expected,
                    f"decision_{field}",
                    expected,
                    decision.get(field),
                    context,
                )
            check(actual_job == expected_choice, "event_dispatch_choice", expected_choice, actual_job, context)
            check(
                bool(event["guard_fired"]) == expected_guard_fired,
                "event_guard_fired",
                expected_guard_fired,
                bool(event["guard_fired"]),
                context,
            )
            check(
                bool(event["choice_changed"]) == expected_changed,
                "event_choice_changed",
                expected_changed,
                bool(event["choice_changed"]),
                context,
            )
            row = jobs_by_id[actual_job]
            for field, expected in (
                ("dispatch_index", index),
                ("worker_id", worker),
                ("dispatcher_dispatch_ns", dispatch_ns),
                ("guard_fired", expected_guard_fired),
                ("choice_changed", expected_changed),
            ):
                check(
                    row.get(field) == expected,
                    f"job_{field}",
                    expected,
                    row.get(field),
                    context,
                )
            if actual_job in waiting:
                waiting.remove(actual_job)
            dispatched.add(actual_job)
            running_by_worker[worker] = actual_job
            dispatch_order.append(actual_job)
        elif event_type == "policy_complete":
            check_clock(event["finish_ns"], event_index, event_type)

    check(len(dispatch_order) == len(jobs), "dispatch_count", len(jobs), len(dispatch_order), {})
    check(
        enqueue_order == list(range(len(jobs))),
        "enqueue_rank_order",
        list(range(len(jobs))),
        enqueue_order,
        {},
    )
    check(len(completed_cost) == len(jobs), "completion_count", len(jobs), len(completed_cost), {})
    check(not waiting, "waiting_not_empty_at_end", [], sorted(waiting), {})
    check(not running_by_worker, "workers_busy_at_end", {}, running_by_worker, {})
    check(len(decisions) == len(jobs), "decision_count", len(jobs), len(decisions), {})
    return {
        "passed": not counts,
        "error_count": int(sum(counts.values())),
        "error_counts": counts,
        "first_error": first_error,
        "event_rows": len(events),
        "dispatches_checked": len(dispatch_order),
        "event_path": run["attempt_event_path"],
        "event_sha256": sha256_file(event_path),
        "target_release_diagnostic": {
            "decisions_with_target_due_unenqueued": decisions_with_target_due_unenqueued,
            "decision_target_due_unenqueued_count": target_due_unenqueued_occurrences,
            "max_target_due_unenqueued_lateness_ns": max_target_due_unenqueued_lateness_ns,
            "first_target_due_unenqueued": first_target_due_unenqueued,
            "interpretation": (
                "target release can pass between the final enqueue scan and the decision "
                "clock; scheduling is audited against actual observed enqueue events"
            ),
        },
    }


def run_physical_policy(policy: str, data: dict, input_sha256: str, log: RunLog) -> dict:
    """Run one fresh physical policy; an interrupted attempt is never resumed in place."""
    RECORDS.mkdir(parents=True, exist_ok=True)
    attempt = f"{policy_slug(policy)}_attempt_{time.strftime('%Y%m%dT%H%M%S')}_{time.perf_counter_ns()}"
    event_path = RECORDS / f"{attempt}_events.jsonl"
    decision_attempt_path = RECORDS / f"{attempt}_decisions.jsonl"
    ctx = mp.get_context("spawn")
    pairs = [ctx.Pipe(duplex=True) for _ in range(K)]
    parent_connections = [pair[0] for pair in pairs]
    child_connections = [pair[1] for pair in pairs]
    processes = [
        ctx.Process(target=worker_main, args=(worker, child_connections[worker]))
        for worker in range(K)
    ]
    policy_wall0, policy_cpu0 = time.perf_counter_ns(), time.process_time_ns()
    worker_cpu_ns = 0
    worker_cpu_cumulative_ns = [0] * K
    jobs = [
        {
            "protocol": PROTOCOL,
            "input_sha256": input_sha256,
            "policy": policy,
            "job_id": int(job),
            "source_rank": int(data["source_rank"][job]),
            "rank": int(job),
            "target_release_offset_ns": int(data["target_release_offset_ns"][job]),
            "requested_service_ns": int(data["requested_service_ns"][job]),
            "score": float(data["score"][job]),
            "in_deadline_window": bool(data["in_deadline_window"][job]),
        }
        for job in range(len(data["job_id"]))
    ]
    decisions = []
    enqueue_ns = [0] * len(jobs)
    waiting_at_arrival = [0] * len(jobs)
    waiting: list[int] = []
    completed_by_rank = Fenwick(len(jobs))
    completed_work_ns = 0
    dispatch_sequence = 0
    next_arrival = 0
    completed = 0
    idle_workers = set(range(K))
    busy_by_connection = {}
    connection_by_worker = {worker: parent_connections[worker] for worker in range(K)}
    worker_by_connection = {connection: worker for worker, connection in connection_by_worker.items()}
    ready_messages = []
    origin_ns = None
    last_progress_ns = time.perf_counter_ns()
    model_limit_failures = 0
    event_handle = open(event_path, "w", encoding="utf-8", newline="", buffering=1)
    decision_handle = open(
        decision_attempt_path, "w", encoding="utf-8", newline="", buffering=1
    )

    def enqueue_due(now_ns: int) -> None:
        nonlocal next_arrival
        while (
            next_arrival < len(jobs)
            and origin_ns + int(data["target_release_offset_ns"][next_arrival])
            <= now_ns
        ):
            job = next_arrival
            actual_ns = time.perf_counter_ns()
            enqueue_ns[job] = actual_ns
            waiting_at_arrival[job] = len(waiting)
            jobs[job].update(
                {
                    "target_release_ns": origin_ns
                    + int(data["target_release_offset_ns"][job]),
                    "actual_enqueue_ns": actual_ns,
                    "release_lateness_ns": actual_ns
                    - (origin_ns + int(data["target_release_offset_ns"][job])),
                    "waiting_at_arrival": len(waiting),
                }
            )
            waiting.append(job)
            append_jsonl(
                event_handle,
                {
                    "type": "arrival_enqueued",
                    "policy": policy,
                    "job_id": job,
                    "target_release_ns": jobs[job]["target_release_ns"],
                    "actual_enqueue_ns": actual_ns,
                    "waiting_at_arrival": waiting_at_arrival[job],
                },
            )
            next_arrival += 1

    try:
        for process in processes:
            process.start()
        for connection in child_connections:
            connection.close()
        pending_ready = set(parent_connections)
        while pending_ready:
            available = wait_connections(list(pending_ready) + [p.sentinel for p in processes])
            for item in available:
                if item in pending_ready:
                    message = item.recv()
                    if message.get("type") != "ready":
                        raise RuntimeError(f"worker did not announce ready: {message}")
                    pending_ready.remove(item)
                    append_jsonl(event_handle, message)
                else:
                    raise RuntimeError("worker exited during startup")
        origin_ns = time.perf_counter_ns() + 1_000_000_000
        window_end_ns = origin_ns + WINDOW_NS
        append_jsonl(
            event_handle,
            {
                "type": "policy_start",
                "policy": policy,
                "origin_ns": origin_ns,
                "window_end_ns": window_end_ns,
                "jobs": len(jobs),
            },
        )
        log.line(f"physical {policy} started: {len(jobs)} jobs, two fresh workers")

        while True:
            # These are the completion messages returned by the preceding blocking wait.
            # They are the completions visible to the dispatcher at this event prefix.
            for item in ready_messages:
                if item not in worker_by_connection:
                    raise RuntimeError("worker exited before completing its assigned job")
                message = item.recv()
                receipt_ns = time.perf_counter_ns()
                if message.get("type") != "completion":
                    raise RuntimeError(f"unexpected worker message {message}")
                worker = worker_by_connection[item]
                job = int(message["job_id"])
                if busy_by_connection.get(item) != job:
                    raise RuntimeError("completion does not match the worker assignment")
                holding_ns = int(message["worker_holding_ns"])
                worker_cpu_ns += int(message["worker_cpu_ns"])
                worker_cpu_cumulative_ns[worker] = int(
                    message["worker_cpu_cumulative_ns"]
                )
                completed_work_ns += holding_ns
                completed_by_rank.add(job, holding_ns)
                model_failed = holding_ns > FORMAL_LIMIT_NS
                model_limit_failures += int(model_failed)
                jobs[job].update(message)
                jobs[job].update(
                    {
                        "dispatcher_completion_receipt_ns": receipt_ns,
                        "dispatcher_slot_occupancy_ns": receipt_ns - jobs[job]["dispatcher_dispatch_ns"],
                        "completion_ipc_lag_ns": receipt_ns - int(message["worker_finish_ns"]),
                        "actual_wait_ns": int(message["worker_start_ns"]) - jobs[job]["actual_enqueue_ns"],
                        "dispatch_to_worker_start_ns": int(message["worker_start_ns"])
                        - jobs[job]["dispatcher_dispatch_ns"],
                        "formal_L61_assumption_failed": model_failed,
                    }
                )
                append_jsonl(
                    event_handle,
                    {
                        "type": "completion_visible",
                        "policy": policy,
                        "job_id": job,
                        "worker_id": worker,
                        "worker_command_receipt_ns": int(message["command_receipt_ns"]),
                        "worker_start_ns": int(message["worker_start_ns"]),
                        "worker_finish_ns": int(message["worker_finish_ns"]),
                        "dispatcher_completion_receipt_ns": receipt_ns,
                        "requested_service_ns": int(message["requested_service_ns"]),
                        "charged_worker_holding_ns": holding_ns,
                        "visible_completed_work_ns": completed_work_ns,
                        "formal_L61_assumption_failed": model_failed,
                    },
                )
                del busy_by_connection[item]
                idle_workers.add(worker)
                completed += 1
            ready_messages = []

            now_ns = time.perf_counter_ns()
            enqueue_due(now_ns)

            while idle_workers and waiting:
                # Logging and IPC for the preceding dispatch take real time.  Admit
                # releases that became due before making the next physical decision.
                enqueue_due(time.perf_counter_ns())
                worker = min(idle_workers)
                decision_clock_ns = time.perf_counter_ns()
                chosen, decision = choose_job(
                    policy,
                    waiting,
                    data["score"],
                    enqueue_ns,
                    waiting_at_arrival,
                    completed_work_ns,
                    completed_by_rank,
                    decision_clock_ns,
                )
                decision.update(
                    {
                        "protocol": PROTOCOL,
                        "input_sha256": input_sha256,
                        "decision_index": dispatch_sequence,
                        "worker_id": worker,
                        "dispatcher_visible_completion_count": completed,
                        "dispatcher_enqueued_count": next_arrival,
                    }
                )
                # The scheduler never uses requested cost.  It is placed on the wire only
                # after the choice is fixed; dispatch time is the start of that IPC send.
                connection = connection_by_worker[worker]
                dispatch_ns = time.perf_counter_ns()
                send_cpu0 = time.process_time_ns()
                connection.send(
                    {
                        "type": "run",
                        "job_id": chosen,
                        "requested_service_ns": int(data["requested_service_ns"][chosen]),
                    }
                )
                send_return_ns = time.perf_counter_ns()
                send_cpu_ns = time.process_time_ns() - send_cpu0
                decision["dispatcher_dispatch_ns"] = dispatch_ns
                decision["decision_to_dispatch_ns"] = dispatch_ns - decision_clock_ns
                decision["dispatch_send_return_ns"] = send_return_ns
                decision["dispatch_send_wall_ns"] = send_return_ns - dispatch_ns
                decision["dispatch_send_cpu_ns"] = send_cpu_ns
                jobs[chosen].update(
                    {
                        "dispatch_index": dispatch_sequence,
                        "worker_id": worker,
                        "decision_clock_ns": decision_clock_ns,
                        "dispatcher_dispatch_ns": dispatch_ns,
                        "dispatch_send_return_ns": send_return_ns,
                        "dispatch_send_wall_ns": send_return_ns - dispatch_ns,
                        "dispatch_send_cpu_ns": send_cpu_ns,
                        "guard_fired": decision["guard_fired"],
                        "choice_changed": decision["choice_changed"],
                        "choice_reason": decision["choice_reason"],
                        "visible_completed_work_ns_at_dispatch": completed_work_ns,
                        "decision_wall_overhead_ns": decision["decision_wall_overhead_ns"],
                        "decision_cpu_overhead_ns": decision["decision_cpu_overhead_ns"],
                    }
                )
                append_jsonl(decision_handle, decision)
                decisions.append(decision)
                append_jsonl(
                    event_handle,
                    {
                        "type": "dispatch",
                        "policy": policy,
                        "decision_index": dispatch_sequence,
                        "job_id": chosen,
                        "worker_id": worker,
                        "dispatcher_dispatch_ns": dispatch_ns,
                        "guard_fired": decision["guard_fired"],
                        "choice_changed": decision["choice_changed"],
                        "choice_reason": decision["choice_reason"],
                    },
                )
                busy_by_connection[connection] = chosen
                waiting.remove(chosen)
                idle_workers.remove(worker)
                dispatch_sequence += 1

            now_ns = time.perf_counter_ns()
            if now_ns - last_progress_ns >= int(PROGRESS_S * 1e9):
                progress = {
                    "type": "progress",
                    "policy": policy,
                    "elapsed_s": (now_ns - origin_ns) / 1e9,
                    "arrived": next_arrival,
                    "dispatched": dispatch_sequence,
                    "completed": completed,
                    "waiting": len(waiting),
                    "running": len(busy_by_connection),
                }
                append_jsonl(event_handle, progress)
                log.line(
                    f"{policy} progress elapsed={progress['elapsed_s']:.1f}s "
                    f"arrived={next_arrival} dispatched={dispatch_sequence} "
                    f"completed={completed} waiting={len(waiting)}"
                )
                last_progress_ns = now_ns

            if completed == len(jobs) and now_ns >= window_end_ns:
                break
            next_release_ns = (
                origin_ns + int(data["target_release_offset_ns"][next_arrival])
                if next_arrival < len(jobs)
                else window_end_ns if now_ns < window_end_ns else None
            )
            progress_deadline_ns = last_progress_ns + int(PROGRESS_S * 1e9)
            next_wake_ns = (
                progress_deadline_ns
                if next_release_ns is None
                else min(next_release_ns, progress_deadline_ns)
            )
            timeout = (
                max(0.0, (next_wake_ns - time.perf_counter_ns()) / 1e9)
            )
            watched = parent_connections + [process.sentinel for process in processes]
            ready_messages = wait_connections(watched, timeout=timeout)

        finish_ns = time.perf_counter_ns()
        append_jsonl(
            event_handle,
            {
                "type": "policy_complete",
                "policy": policy,
                "finish_ns": finish_ns,
                "wall_s_from_origin": (finish_ns - origin_ns) / 1e9,
                "release_window_s": WINDOW_S,
                "actual_drain_after_release_window_s": max(
                    0.0, (finish_ns - window_end_ns) / 1e9
                ),
                "model_limit_failures": model_limit_failures,
            },
        )
    except BaseException as exc:
        append_jsonl(
            event_handle,
            {
                "type": "interrupted",
                "policy": policy,
                "when_ns": time.perf_counter_ns(),
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            },
        )
        log.line(
            f"physical {policy} interrupted; attempt records preserved at {event_path.name}"
        )
        raise
    finally:
        event_handle.close()
        decision_handle.close()
        stop_workers(processes, parent_connections)

    policy_wall1, policy_cpu1 = time.perf_counter_ns(), time.process_time_ns()
    result = {
        "policy": policy,
        "attempt": attempt,
        "origin_ns": origin_ns,
        "window_end_ns": origin_ns + WINDOW_NS,
        "finish_ns": finish_ns,
        "wall_s_from_origin": (finish_ns - origin_ns) / 1e9,
        "actual_drain_s": max(0.0, (finish_ns - (origin_ns + WINDOW_NS)) / 1e9),
        "jobs": jobs,
        "decisions": decisions,
        "attempt_event_path": str(event_path.relative_to(HERE)).replace("\\", "/"),
        "attempt_decision_path": str(decision_attempt_path.relative_to(HERE)).replace("\\", "/"),
        "policy_wall_s": (policy_wall1 - policy_wall0) / 1e9,
        "dispatcher_cpu_s": (policy_cpu1 - policy_cpu0) / 1e9,
        "worker_service_interval_cpu_s": worker_cpu_ns / 1e9,
        "worker_cpu_through_last_finish_s": sum(worker_cpu_cumulative_ns) / 1e9,
        "total_measured_cpu_through_last_finish_s": (
            policy_cpu1 - policy_cpu0 + sum(worker_cpu_cumulative_ns)
        ) / 1e9,
        "model_limit_failures": model_limit_failures,
    }
    return result


def audit_ideal_guard_replay(trace, replay, policy_spec, scores) -> tuple[dict, dict[int, dict]]:
    """Rebuild ideal Guard dispatch epochs without calling the scheduler implementation."""
    from fractions import Fraction

    n = len(trace.arrival_us)
    order = sorted(range(n), key=lambda job: int(replay.dispatch_index[job]))
    dispatched: set[int] = set()
    records: dict[int, dict] = {}
    errors = []
    eta = Fraction(str(policy_spec.eta_k)).limit_denominator(720720)
    en, ed = eta.numerator, eta.denominator
    fired_epochs = 0
    waiting_evaluations_checked = 0
    for dispatch_index, actual_choice in enumerate(order):
        t_us = int(replay.start_us[actual_choice])
        completed = {
            job
            for job in dispatched
            if int(replay.start_us[job]) + int(trace.service_us[job]) <= t_us
        }
        waiting = [
            job
            for job in range(n)
            if job not in dispatched and int(trace.arrival_us[job]) <= t_us
        ]
        base = min(waiting, key=lambda job: (float(scores[job]), job))
        fired = []
        waiting_evaluations_checked += len(waiting)
        completed_suffix_us = [0] * (n + 1)
        for completed_job in completed:
            completed_suffix_us[completed_job] += int(trace.service_us[completed_job])
        for rank in range(n - 1, -1, -1):
            completed_suffix_us[rank] += completed_suffix_us[rank + 1]
        for job in waiting:
            over_us = completed_suffix_us[job + 1]
            age_us = t_us - int(trace.arrival_us[job])
            budget_num = ed * int(policy_spec.b0_us) + en * age_us
            if policy_spec.bmax_us > 0:
                budget_num = min(budget_num, ed * int(policy_spec.bmax_us))
            is_fired = ed * over_us >= budget_num
            if is_fired:
                fired.append(job)
        expected_choice = min(fired) if fired else base
        if expected_choice != actual_choice:
            errors.append(
                {
                    "dispatch_index": dispatch_index,
                    "start_epoch_us": t_us,
                    "expected_choice": expected_choice,
                    "replay_choice": actual_choice,
                    "base_choice": base,
                    "fired_set": fired,
                }
            )
        guard_fired = bool(fired)
        fired_epochs += int(guard_fired)
        records[actual_choice] = {
            "ideal_start_epoch_us": t_us,
            "ideal_guard_fired": guard_fired,
            "ideal_choice_changed": actual_choice != base,
            "ideal_base_choice": base,
            "ideal_fired_set": fired,
            "ideal_fired_count": len(fired),
        }
        dispatched.add(actual_choice)
    if fired_epochs != int(replay.n_forced):
        errors.append(
            {
                "kind": "kernel_firing_count",
                "reconstructed": fired_epochs,
                "kernel_n_forced": int(replay.n_forced),
            }
        )
    return (
        {
            "passed": not errors,
            "error_count": len(errors),
            "first_error": errors[0] if errors else None,
            "dispatches_checked": n,
            "waiting_budget_evaluations_checked": waiting_evaluations_checked,
            "reconstructed_firing_epochs": fired_epochs,
            "kernel_n_forced": int(replay.n_forced),
        },
        records,
    )


def audit_policy(
    policy: str,
    run: dict,
    data: dict,
    input_sha256: str,
    independent_fcfs_jobs_path: Path | None = None,
) -> tuple[dict, list[dict]]:
    """Replay ideal production schedules and retain every physical-model discrepancy."""
    import numpy as np

    from spjf_guard.sim import Trace, simulate
    from spjf_guard.sim.bounds import assert_per_job_bounds, guard_upper_bound
    from spjf_guard.sim.policy import fcfs

    jobs = sorted(run["jobs"], key=lambda row: row["job_id"])
    enqueue_us = np.array(
        [int(round((row["actual_enqueue_ns"] - run["origin_ns"]) / 1000)) for row in jobs],
        np.int64,
    )
    holding_us = np.array(
        [max(1, int(round(row["worker_holding_ns"] / 1000))) for row in jobs], np.int64
    )
    holding_ns = np.array([row["worker_holding_ns"] for row in jobs], np.int64)
    scores = np.array([row["score"] for row in jobs], np.float64)
    measured = Trace(enqueue_us, holding_us, {SCORE_KEY: scores}, limit_s=FORMAL_LIMIT_S)
    policy_spec = policy_object(policy)
    replay = simulate(measured, policy_spec, K)
    shadow_fcfs = simulate(measured, fcfs(), K)

    nominal_arrival_us = np.array(
        [int(round(row["target_release_offset_ns"] / 1000)) for row in jobs], np.int64
    )
    nominal_service_us = np.array(
        [max(1, int(round(row["requested_service_ns"] / 1000))) for row in jobs], np.int64
    )
    nominal = Trace(
        nominal_arrival_us,
        nominal_service_us,
        {SCORE_KEY: scores},
        limit_s=FORMAL_LIMIT_S,
    )
    nominal_policy = policy_object(policy)
    nominal_replay = simulate(nominal, nominal_policy, K)

    physical_dispatch_index = np.array([row["dispatch_index"] for row in jobs], np.int64)
    physical_wait_us = np.array(
        [int(round(row["actual_wait_ns"] / 1000)) for row in jobs], np.int64
    )
    wait_difference_us = physical_wait_us - replay.wait_us
    nominal_wait_difference_us = physical_wait_us - nominal_replay.wait_us
    dispatch_mismatch = physical_dispatch_index != replay.dispatch_index
    nominal_dispatch_mismatch = physical_dispatch_index != nominal_replay.dispatch_index
    physical_fired = sum(bool(row["guard_fired"]) for row in jobs) if policy == "Guard(300)" else 0
    physical_choice_changed = (
        sum(bool(row["choice_changed"]) for row in jobs) if policy == "Guard(300)" else 0
    )
    replay_fired = replay.n_forced if policy == "Guard(300)" else 0
    event_prefix_audit = audit_event_prefix(policy, run, data, jobs)
    ideal_guard_epoch_audit = None
    ideal_guard_records = {}
    physical_ideal_firing_mismatches = []
    if policy == "Guard(300)":
        ideal_guard_epoch_audit, ideal_guard_records = audit_ideal_guard_replay(
            measured, replay, policy_spec, scores
        )
        for row in jobs:
            ideal = ideal_guard_records[row["job_id"]]
            row.update(ideal)
            mismatch = bool(row["guard_fired"]) != bool(ideal["ideal_guard_fired"])
            row["physical_vs_ideal_guard_fired_mismatch"] = mismatch
            if mismatch:
                physical_ideal_firing_mismatches.append(row["job_id"])

    model_assumption_failed = bool(np.any(holding_ns > FORMAL_LIMIT_NS))
    production_bound_assertion = {
        "attempted": policy == "Guard(300)",
        "passed": None,
        "checked_jobs": 0,
        "error": None,
    }
    physical_bound_violations = 0
    physical_max_bound_violation_s = 0.0
    if policy == "Guard(300)":
        bounds_s = guard_upper_bound(
            shadow_fcfs.wait_us, policy_spec, K, FORMAL_LIMIT_S
        )
        physical_wait_s = physical_wait_us / 1e6
        violation_s = np.maximum(physical_wait_s - bounds_s, 0.0)
        physical_bound_violations = int((violation_s > 0.0).sum())
        physical_max_bound_violation_s = float(violation_s.max())
        for row, bound_s, amount_s in zip(jobs, bounds_s, violation_s):
            row["same_measured_trace_shadow_fcfs_wait_us"] = int(
                shadow_fcfs.wait_us[row["job_id"]]
            )
            row["physical_guard_bound_s"] = float(bound_s)
            row["physical_guard_bound_violation_s"] = float(amount_s)
        try:
            checked = assert_per_job_bounds(
                replay, shadow_fcfs.wait_us, policy_spec, K, FORMAL_LIMIT_S
            )
            production_bound_assertion.update(passed=True, checked_jobs=int(checked))
        except AssertionError as exc:
            production_bound_assertion.update(passed=False, error=str(exc))

    independent_fcfs_comparison = None
    fcfs_jobs_path = (
        independent_fcfs_jobs_path
        if independent_fcfs_jobs_path is not None
        else HERE / "physical_fcfs_jobs.jsonl"
    )
    if policy == "Guard(300)" and fcfs_jobs_path.is_file():
        fcfs_jobs = [
            json.loads(line)
            for line in fcfs_jobs_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        fcfs_jobs.sort(key=lambda row: row["job_id"])
        if len(fcfs_jobs) != len(jobs):
            raise RuntimeError("independent physical FCFS run has a different job count")
        differences = []
        service_differences = []
        for row, fcfs_row in zip(jobs, fcfs_jobs):
            if row["job_id"] != fcfs_row["job_id"]:
                raise RuntimeError("independent physical FCFS job identities differ")
            delta_wait = int(row["actual_wait_ns"] - fcfs_row["actual_wait_ns"])
            delta_service = int(row["worker_holding_ns"] - fcfs_row["worker_holding_ns"])
            row["independent_physical_fcfs_wait_ns"] = int(fcfs_row["actual_wait_ns"])
            row["guard_minus_independent_physical_fcfs_wait_ns"] = delta_wait
            row["independent_physical_fcfs_worker_holding_ns"] = int(
                fcfs_row["worker_holding_ns"]
            )
            row["guard_minus_independent_fcfs_worker_holding_ns"] = delta_service
            differences.append(delta_wait)
            service_differences.append(delta_service)
        independent_fcfs_comparison = {
            "same_requested_jobs": True,
            "same_realised_service_times": False,
            "theorem_baseline": False,
            "mean_wait_difference_s": float(np.mean(differences) / 1e9),
            "max_wait_difference_s": float(np.max(differences) / 1e9),
            "min_wait_difference_s": float(np.min(differences) / 1e9),
            "max_abs_worker_holding_difference_s": float(
                np.max(np.abs(service_differences)) / 1e9
            ),
            "interpretation": (
                "diagnostic comparison with a separate physical FCFS execution; it is not "
                "the theorem's same-a/same-C shadow FCFS baseline"
            ),
        }

    for job, row in enumerate(jobs):
        row.update(
            {
                "production_replay_wait_us": int(replay.wait_us[job]),
                "physical_minus_production_wait_us": int(wait_difference_us[job]),
                "production_replay_dispatch_index": int(replay.dispatch_index[job]),
                "production_dispatch_mismatch": bool(dispatch_mismatch[job]),
                "nominal_replay_wait_us": int(nominal_replay.wait_us[job]),
                "physical_minus_nominal_wait_us": int(nominal_wait_difference_us[job]),
                "nominal_replay_dispatch_index": int(nominal_replay.dispatch_index[job]),
                "nominal_dispatch_mismatch": bool(nominal_dispatch_mismatch[job]),
            }
        )

    dispatch_to_start = np.array(
        [row["dispatch_to_worker_start_ns"] for row in jobs], np.int64
    )
    completion_lag = np.array([row["completion_ipc_lag_ns"] for row in jobs], np.int64)
    slot_overhead = np.array(
        [row["dispatcher_slot_occupancy_ns"] - row["worker_holding_ns"] for row in jobs],
        np.int64,
    )
    sleep_overshoot = np.array(
        [row["worker_holding_ns"] - row["requested_service_ns"] for row in jobs],
        np.int64,
    )
    worker_idle_gaps = []
    visible_idle_gaps = []
    for worker_id in range(K):
        worker_jobs = sorted(
            (row for row in jobs if row["worker_id"] == worker_id),
            key=lambda row: row["worker_start_ns"],
        )
        previous = None
        for row in worker_jobs:
            if previous is None:
                row["worker_idle_gap_from_prior_finish_ns"] = None
                row["dispatcher_visible_idle_gap_ns"] = None
            else:
                worker_gap = int(row["worker_start_ns"] - previous["worker_finish_ns"])
                visible_gap = int(
                    row["worker_start_ns"] - previous["dispatcher_completion_receipt_ns"]
                )
                row["worker_idle_gap_from_prior_finish_ns"] = worker_gap
                row["dispatcher_visible_idle_gap_ns"] = visible_gap
                worker_idle_gaps.append(worker_gap)
                visible_idle_gaps.append(visible_gap)
            previous = row

    def distribution_ms(values) -> dict:
        values = np.asarray(values, np.float64) / 1e6
        return {
            "count": int(values.size),
            "mean_ms": float(values.mean()),
            "p50_ms": float(np.percentile(values, 50)),
            "p95_ms": float(np.percentile(values, 95)),
            "p99_ms": float(np.percentile(values, 99)),
            "max_ms": float(values.max()),
        }

    actual_wait_ns = np.array([row["actual_wait_ns"] for row in jobs], np.int64)
    release_lateness_ns = np.array([row["release_lateness_ns"] for row in jobs], np.int64)
    decision_wall_ns = np.array(
        [row["decision_wall_overhead_ns"] for row in jobs], np.int64
    )
    decision_cpu_ns = np.array(
        [row["decision_cpu_overhead_ns"] for row in jobs], np.int64
    )
    audit = {
        "protocol": PROTOCOL,
        "input_sha256": input_sha256,
        "policy": policy,
        "jobs": len(jobs),
        "physical_time_definition": {
            "arrival": "dispatcher actual_enqueue_ns",
            "wait": "worker_start_ns - actual_enqueue_ns",
            "service_C": "worker_finish_ns - worker_start_ns",
            "visible_completion": "dispatcher_completion_receipt_ns",
            "slot_occupancy_diagnostic": "dispatcher_completion_receipt_ns - dispatcher_dispatch_ns",
        },
        "prefix_audit_scope": (
            "each decision uses only completion messages already received and jobs already "
            "enqueued by the dispatcher; worker finish and completion receipt are both logged"
        ),
        "production_replay_service": (
            "actual enqueue times and measured worker holding C; it excludes dispatcher/IPC "
            "overhead and is therefore an ideal work-conserving comparison, not an exact replica"
        ),
        "event_prefix_audit": event_prefix_audit,
        "ideal_guard_epoch_audit": ideal_guard_epoch_audit,
        "model_L_s": FORMAL_LIMIT_S,
        "model_assumption_failed": model_assumption_failed,
        "jobs_exceeding_L": int((holding_ns > FORMAL_LIMIT_NS).sum()),
        "max_measured_worker_holding_s": float(holding_ns.max() / 1e9),
        "wait_comparison": {
            "mean_physical_minus_production_s": float(wait_difference_us.mean() / 1e6),
            "max_abs_physical_minus_production_s": float(
                np.abs(wait_difference_us).max() / 1e6
            ),
            "per_job_compared": len(jobs),
        },
        "physical_wait": {
            "mean_s": float(actual_wait_ns.mean() / 1e9),
            "p99_s": float(np.percentile(actual_wait_ns, 99) / 1e9),
            "max_s": float(actual_wait_ns.max() / 1e9),
            "positive_wait_job_count": int((actual_wait_ns > 0).sum()),
        },
        "release_lateness": distribution_ms(release_lateness_ns),
        "dispatch_comparison": {
            "production_mismatching_jobs": int(dispatch_mismatch.sum()),
            "nominal_mismatching_jobs": int(nominal_dispatch_mismatch.sum()),
        },
        "firing_comparison": {
            "physical_visible_prefix_count": int(physical_fired),
            "production_replay_count": int(replay_fired),
            "difference": int(physical_fired - replay_fired),
            "physical_choice_changed_count": int(physical_choice_changed),
            "physical_vs_ideal_per_job_mismatch_count": len(
                physical_ideal_firing_mismatches
            ),
            "physical_vs_ideal_mismatch_jobs": physical_ideal_firing_mismatches,
            "physical_vs_ideal_first_mismatch_job": (
                physical_ideal_firing_mismatches[0]
                if physical_ideal_firing_mismatches
                else None
            ),
            "semantics": (
                "guard firing means E(t) is nonempty; choice_changed separately means the "
                "minimum fired rank differs from the base-policy candidate"
            ),
        },
        "dispatcher_overhead": {
            "decision_wall_distribution": distribution_ms(decision_wall_ns),
            "decision_cpu_distribution": distribution_ms(decision_cpu_ns),
            "decision_wall_ns_sum": int(
                sum(row["decision_wall_overhead_ns"] for row in jobs)
            ),
            "decision_cpu_ns_sum": int(sum(row["decision_cpu_overhead_ns"] for row in jobs)),
            "dispatch_send_wall_ns_sum": int(sum(row["dispatch_send_wall_ns"] for row in jobs)),
            "dispatch_send_cpu_ns_sum": int(sum(row["dispatch_send_cpu_ns"] for row in jobs)),
            "dispatch_to_start_mean_ms": float(dispatch_to_start.mean() / 1e6),
            "dispatch_to_start_max_ms": float(dispatch_to_start.max() / 1e6),
            "completion_receipt_lag_mean_ms": float(completion_lag.mean() / 1e6),
            "completion_receipt_lag_max_ms": float(completion_lag.max() / 1e6),
            "slot_overhead_mean_ms": float(slot_overhead.mean() / 1e6),
            "slot_overhead_max_ms": float(slot_overhead.max() / 1e6),
            "worker_idle_gap_from_prior_finish_mean_ms": (
                float(np.mean(worker_idle_gaps) / 1e6) if worker_idle_gaps else None
            ),
            "worker_idle_gap_from_prior_finish_max_ms": (
                float(np.max(worker_idle_gaps) / 1e6) if worker_idle_gaps else None
            ),
            "dispatcher_visible_idle_gap_mean_ms": (
                float(np.mean(visible_idle_gaps) / 1e6) if visible_idle_gaps else None
            ),
            "dispatcher_visible_idle_gap_max_ms": (
                float(np.max(visible_idle_gaps) / 1e6) if visible_idle_gaps else None
            ),
            "sleep_overshoot_mean_ms": float(sleep_overshoot.mean() / 1e6),
            "sleep_overshoot_max_ms": float(sleep_overshoot.max() / 1e6),
        },
        "guard_bound": {
            "physical_violations_against_same_measured_trace_shadow_fcfs": physical_bound_violations,
            "physical_max_violation_s": physical_max_bound_violation_s,
            "production_replay_assertion": production_bound_assertion,
            "model_premise_failed": model_assumption_failed,
        },
        "independent_physical_fcfs": independent_fcfs_comparison,
        "nominal_replay": {
            "arrival": "frozen target offsets",
            "service": "frozen requested C_cap",
            "mean_physical_minus_nominal_wait_s": float(
                nominal_wait_difference_us.mean() / 1e6
            ),
            "max_abs_physical_minus_nominal_wait_s": float(
                np.abs(nominal_wait_difference_us).max() / 1e6
            ),
        },
        "run_resources": {
            "wall_s": run["policy_wall_s"],
            "physical_wall_s_from_origin": run["wall_s_from_origin"],
            "release_window_s": WINDOW_S,
            "actual_drain_after_release_window_s": run["actual_drain_s"],
            "dispatcher_cpu_s": run["dispatcher_cpu_s"],
            "worker_service_interval_cpu_s": run["worker_service_interval_cpu_s"],
            "worker_cpu_through_last_finish_s": run["worker_cpu_through_last_finish_s"],
            "total_measured_cpu_through_last_finish_s": run[
                "total_measured_cpu_through_last_finish_s"
            ],
            "worker_cpu_scope": (
                "worker_main entry through each worker's last finish; interpreter startup "
                "and the final completion send are outside this measurement"
            ),
        },
        "no_exact_correspondence_claimed": True,
    }
    return audit, jobs


def completed_entry(policy: str, input_sha256: str) -> dict:
    slug = policy_slug(policy)
    paths = {
        "jobs": HERE / f"physical_{slug}_jobs.jsonl",
        "decisions": HERE / f"physical_{slug}_decisions.jsonl",
        "audit": HERE / f"physical_{slug}_audit.json",
    }
    return {
        "policy": policy,
        "input_sha256": input_sha256,
        **{
            key: {
                "path": str(path.relative_to(HERE)).replace("\\", "/"),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for key, path in paths.items()
        },
    }


def main() -> int:
    RECORDS.mkdir(parents=True, exist_ok=True)
    log = RunLog(LOG_PATH)
    started_wall, started_cpu = time.perf_counter(), time.process_time()
    try:
        log.line(f"physical protocol {PROTOCOL}; no sealed input; no thinning")
        data, metadata, input_sha256 = prepare_input()
        log.line(
            f"selected fixed window jobs={metadata['jobs']} "
            f"offered_work_s={metadata['offered_requested_work_s']:.6f} "
            f"work-only drain lower bound={metadata['work_only_drain_lower_bound_s']:.6f}s"
        )
        checkpoint = load_checkpoint(input_sha256)
        for policy in POLICIES:
            if policy in checkpoint["completed"]:
                log.line(f"skip completed physical policy {policy}")
                continue
            run = run_physical_policy(policy, data, input_sha256, log)
            # Workers have been shut down before either production replay begins.
            audit, jobs = audit_policy(policy, run, data, input_sha256)
            slug = policy_slug(policy)
            jobs_path = HERE / f"physical_{slug}_jobs.jsonl"
            decisions_path = HERE / f"physical_{slug}_decisions.jsonl"
            audit_path = HERE / f"physical_{slug}_audit.json"
            write_jsonl(jobs_path, jobs)
            write_jsonl(decisions_path, run["decisions"])
            write_json(audit_path, audit)
            if not audit["event_prefix_audit"]["passed"]:
                raise RuntimeError(
                    f"{policy} independent event-prefix audit failed; see {audit_path.name}"
                )
            if (
                audit["ideal_guard_epoch_audit"] is not None
                and not audit["ideal_guard_epoch_audit"]["passed"]
            ):
                raise RuntimeError(
                    f"{policy} independent ideal-epoch audit failed; see {audit_path.name}"
                )
            checkpoint["completed"][policy] = completed_entry(policy, input_sha256)
            checkpoint["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            write_json(CHECKPOINT_PATH, checkpoint)
            log.line(
                f"completed {policy}: wall={run['policy_wall_s']:.3f}s "
                f"drain={run['actual_drain_s']:.3f}s "
                f"cpu_through_finish={run['total_measured_cpu_through_last_finish_s']:.3f}s "
                f"L61_failures={run['model_limit_failures']}"
            )

        audits = {}
        for policy in POLICIES:
            slug = policy_slug(policy)
            audits[policy] = json.loads(
                (HERE / f"physical_{slug}_audit.json").read_text(encoding="utf-8")
            )
        summary = {
            "protocol": PROTOCOL,
            "parameters": PARAMETERS,
            "input": metadata,
            "completed_policies": list(POLICIES),
            "audits": audits,
            "total_invocation_wall_s": time.perf_counter() - started_wall,
            "root_invocation_cpu_s": time.process_time() - started_cpu,
            "physical_policy_measured_cpu_through_last_finish_s": sum(
                audit["run_resources"]["total_measured_cpu_through_last_finish_s"]
                for audit in audits.values()
            ),
            "scope": (
                "one selected five-minute development-overlay window; physical timed-sleep "
                "implementation evidence, not a production deployment or confidence interval"
            ),
        }
        write_json(SUMMARY_PATH, summary)
        log.line(
            f"PHYSICAL_COMPLETE wall={summary['total_invocation_wall_s']:.3f}s "
            f"root_cpu={summary['root_invocation_cpu_s']:.3f}s"
        )
        return 0
    finally:
        log.close()


if __name__ == "__main__":
    mp.freeze_support()
    raise SystemExit(main())
