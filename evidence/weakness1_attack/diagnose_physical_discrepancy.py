"""Diagnose physical-versus-ideal ordering from completed artifacts only.

This is post-processing, not a scheduler replay.  It never imports the simulator and
never reads the frozen NPZ.  The ideal order and waits are the fields already written
by the completed physical audit.
"""

from __future__ import annotations

from collections import Counter
import hashlib
import heapq
import json
from pathlib import Path
import sys
import time


sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
SPJF_JOBS = HERE / "physical_spjf_e_jobs.jsonl"
SPJF_DECISIONS = HERE / "physical_spjf_e_decisions.jsonl"
SPJF_AUDIT = HERE / "physical_spjf_e_audit.json"
FCFS_JOBS = HERE / "physical_fcfs_jobs.jsonl"
FCFS_AUDIT = HERE / "physical_fcfs_audit.json"
OUTPUT_JSON = HERE / "physical_discrepancy.json"
OUTPUT_LOG = HERE / "out_physical_discrepancy.txt"
TOP_JOBS = 10


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            value.update(block)
    return value.hexdigest()


def artifact(path: Path) -> dict:
    return {
        "path": path.resolve().relative_to(HERE.resolve()).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def load_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def quantile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("empty quantile")
    position = (len(ordered) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def toggle(values: set[int], item: int) -> None:
    if item in values:
        values.remove(item)
    else:
        values.add(item)


def summarize_delta(jobs: list[dict]) -> dict:
    delta = [int(row["physical_minus_production_wait_us"]) / 1e6 for row in jobs]
    absolute = [abs(value) for value in delta]
    mismatches = sum(
        int(row["dispatch_index"] != row["production_replay_dispatch_index"])
        for row in jobs
    )
    return {
        "jobs": len(jobs),
        "dispatch_index_mismatching_jobs": mismatches,
        "mean_physical_minus_ideal_wait_s": sum(delta) / len(delta),
        "max_abs_physical_minus_ideal_wait_s": max(absolute),
        "p50_abs_wait_discrepancy_s": quantile(absolute, 0.50),
        "p95_abs_wait_discrepancy_s": quantile(absolute, 0.95),
        "p99_abs_wait_discrepancy_s": quantile(absolute, 0.99),
        "counts_abs_wait_discrepancy_above_s": {
            str(threshold): sum(value > threshold for value in absolute)
            for threshold in (0.001, 0.1, 1.0, 10.0, 60.0, 300.0)
        },
    }


def main() -> None:
    wall, cpu = time.perf_counter(), time.process_time()
    spjf_audit = json.loads(SPJF_AUDIT.read_text(encoding="utf-8"))
    fcfs_audit = json.loads(FCFS_AUDIT.read_text(encoding="utf-8"))
    assert spjf_audit["policy"] == "SPJF-E"
    assert fcfs_audit["policy"] == "FCFS"
    assert spjf_audit["event_prefix_audit"]["passed"]
    assert fcfs_audit["event_prefix_audit"]["passed"]
    assert spjf_audit["input_sha256"] == fcfs_audit["input_sha256"]

    event_path = (HERE / spjf_audit["event_prefix_audit"]["event_path"]).resolve()
    assert HERE.resolve() in event_path.parents
    assert sha256(event_path) == spjf_audit["event_prefix_audit"]["event_sha256"]
    events = load_jsonl(event_path)
    starts = [row for row in events if row.get("type") == "policy_start"]
    assert len(starts) == 1
    origin_ns = int(starts[0]["origin_ns"])

    jobs = sorted(load_jsonl(SPJF_JOBS), key=lambda row: int(row["job_id"]))
    decisions = sorted(
        load_jsonl(SPJF_DECISIONS), key=lambda row: int(row["decision_index"])
    )
    fcfs_jobs = sorted(load_jsonl(FCFS_JOBS), key=lambda row: int(row["job_id"]))
    n = len(jobs)
    assert n == 2151 == len(decisions) == len(fcfs_jobs)
    assert [int(row["job_id"]) for row in jobs] == list(range(n))
    assert [int(row["decision_index"]) for row in decisions] == list(range(n))
    for rows, policy in ((jobs, "SPJF-E"), (decisions, "SPJF-E"), (fcfs_jobs, "FCFS")):
        assert all(row["policy"] == policy for row in rows)
        assert all(row["protocol"] == spjf_audit["protocol"] for row in rows)
        assert all(row["input_sha256"] == spjf_audit["input_sha256"] for row in rows)

    actual_order = [-1] * n
    ideal_order = [-1] * n
    actual_index = [-1] * n
    ideal_index = [-1] * n
    arrival_us = [0] * n
    ideal_start_us = [0] * n
    scores = [0.0] * n
    for row in jobs:
        job = int(row["job_id"])
        actual = int(row["dispatch_index"])
        ideal = int(row["production_replay_dispatch_index"])
        actual_order[actual] = job
        ideal_order[ideal] = job
        actual_index[job] = actual
        ideal_index[job] = ideal
        arrival_us[job] = int(round((int(row["actual_enqueue_ns"]) - origin_ns) / 1000))
        ideal_start_us[job] = arrival_us[job] + int(row["production_replay_wait_us"])
        scores[job] = float(row["score"])
    assert sorted(actual_order) == list(range(n))
    assert sorted(ideal_order) == list(range(n))
    assert all(arrival_us[left] <= arrival_us[left + 1] for left in range(n - 1))
    assert all(
        ideal_start_us[ideal_order[left]] <= ideal_start_us[ideal_order[left + 1]]
        for left in range(n - 1)
    )
    assert actual_order == [int(row["chosen_job"]) for row in decisions]

    ideal_waiting: set[int] = set()
    ideal_heap: list[tuple[float, int]] = []
    ideal_dispatched: set[int] = set()
    next_arrival = 0
    prefix_difference: set[int] = set()
    active_episode = None
    episodes = []
    mismatch_causes = Counter()
    physical_bad_choices = []
    ideal_bad_choices = []
    formula_conflicts = []
    first_divergence = None
    max_prefix_symmetric_difference = 0

    for position in range(n):
        ideal_choice = ideal_order[position]
        physical_choice = actual_order[position]
        ideal_time = ideal_start_us[ideal_choice]
        while next_arrival < n and arrival_us[next_arrival] <= ideal_time:
            ideal_waiting.add(next_arrival)
            heapq.heappush(ideal_heap, (scores[next_arrival], next_arrival))
            next_arrival += 1
        while ideal_heap and ideal_heap[0][1] in ideal_dispatched:
            heapq.heappop(ideal_heap)
        reconstructed_ideal_choice = ideal_heap[0][1]
        if reconstructed_ideal_choice != ideal_choice:
            ideal_bad_choices.append(
                {
                    "dispatch_index": position,
                    "stored": ideal_choice,
                    "reconstructed": reconstructed_ideal_choice,
                }
            )

        decision = decisions[position]
        physical_waiting = {int(job) for job in decision["waiting_ranks"]}
        reconstructed_physical_choice = min(
            physical_waiting, key=lambda job: (scores[job], job)
        )
        if reconstructed_physical_choice != physical_choice:
            physical_bad_choices.append(
                {
                    "dispatch_index": position,
                    "stored": physical_choice,
                    "reconstructed": reconstructed_physical_choice,
                }
            )

        if physical_choice != ideal_choice:
            physical_choice_already_ideal = ideal_index[physical_choice] < position
            ideal_choice_already_physical = actual_index[ideal_choice] < position
            if physical_choice_already_ideal or ideal_choice_already_physical:
                cause = "cascade_from_prior_order_difference"
            elif (
                physical_choice not in ideal_waiting
                and arrival_us[physical_choice] > ideal_time
                and int(jobs[physical_choice]["actual_enqueue_ns"])
                <= int(decision["decision_clock_ns"])
            ):
                cause = "later_arrival_crossed_into_physical_decision"
            elif (
                ideal_choice not in physical_waiting
                and int(jobs[ideal_choice]["actual_enqueue_ns"])
                > int(decision["decision_clock_ns"])
            ):
                cause = "later_arrival_crossed_into_ideal_decision"
            else:
                cause = "other_queue_membership_difference"
            mismatch_causes[cause] += 1
            both_available = (
                physical_choice in ideal_waiting
                and ideal_choice in ideal_waiting
                and physical_choice in physical_waiting
                and ideal_choice in physical_waiting
            )
            if both_available:
                formula_conflicts.append(position)
            physical_only = sorted(physical_waiting - ideal_waiting)
            ideal_only = sorted(ideal_waiting - physical_waiting)
            detail = {
                "dispatch_index": position,
                "physical_choice": physical_choice,
                "physical_choice_score": scores[physical_choice],
                "ideal_choice": ideal_choice,
                "ideal_choice_score": scores[ideal_choice],
                "cause": cause,
                "physical_decision_minus_mapped_ideal_epoch_ms": (
                    int(decision["decision_clock_ns"])
                    - (origin_ns + ideal_time * 1000)
                )
                / 1e6,
                "physical_choice_enqueue_minus_mapped_ideal_epoch_ms": (
                    int(jobs[physical_choice]["actual_enqueue_ns"])
                    - (origin_ns + ideal_time * 1000)
                )
                / 1e6,
                "physical_decision_minus_physical_choice_enqueue_ms": (
                    int(decision["decision_clock_ns"])
                    - int(jobs[physical_choice]["actual_enqueue_ns"])
                )
                / 1e6,
                "physical_waiting_jobs": len(physical_waiting),
                "ideal_waiting_jobs": len(ideal_waiting),
                "physical_minus_ideal_waiting_count": len(physical_waiting - ideal_waiting),
                "ideal_minus_physical_waiting_count": len(ideal_waiting - physical_waiting),
                "physical_only_waiting_job_ids": physical_only,
                "ideal_only_waiting_job_ids": ideal_only,
                "physical_choice_in_ideal_waiting": physical_choice in ideal_waiting,
                "ideal_choice_in_physical_waiting": ideal_choice in physical_waiting,
                "both_choices_available_to_both": both_available,
            }
            if first_divergence is None:
                first_divergence = detail
            if not prefix_difference:
                active_episode = {"start": position, "start_detail": detail, "mismatches": 0}
            assert active_episode is not None
            active_episode["mismatches"] += 1

        if physical_choice != ideal_choice:
            toggle(prefix_difference, physical_choice)
            toggle(prefix_difference, ideal_choice)
        max_prefix_symmetric_difference = max(
            max_prefix_symmetric_difference, len(prefix_difference)
        )
        if active_episode is not None and not prefix_difference:
            active_episode["end"] = position
            active_episode["dispatch_positions"] = position - active_episode["start"] + 1
            episodes.append(active_episode)
            active_episode = None

        ideal_waiting.remove(ideal_choice)
        ideal_dispatched.add(ideal_choice)
    assert active_episode is None and not prefix_difference
    assert not physical_bad_choices, physical_bad_choices[:1]
    assert not ideal_bad_choices, ideal_bad_choices[:1]
    assert not formula_conflicts, formula_conflicts[:5]

    dispatch_events = {
        int(row["decision_index"]): index
        for index, row in enumerate(events)
        if row.get("type") == "dispatch"
    }
    first_position = int(first_divergence["dispatch_index"])
    event_index = dispatch_events[first_position]
    prior_event_index = dispatch_events[first_position - 1] if first_position else -1
    between = events[prior_event_index + 1 : event_index]
    first_divergence["events_since_previous_physical_dispatch"] = {
        "event_type_counts": dict(Counter(str(row.get("type")) for row in between)),
        "arrival_job_ids": [
            int(row["job_id"]) for row in between if row.get("type") == "arrival_enqueued"
        ],
        "completion_job_ids": [
            int(row["job_id"]) for row in between if row.get("type") == "completion_visible"
        ],
    }

    episode_for_position = {}
    for episode_index, episode in enumerate(episodes):
        for position in range(int(episode["start"]), int(episode["end"]) + 1):
            episode_for_position[position] = episode_index

    def extreme(row: dict) -> dict:
        job = int(row["job_id"])
        actual = actual_index[job]
        ideal = ideal_index[job]
        actual_before = {other for other in range(n) if actual_index[other] < actual}
        ideal_before = {other for other in range(n) if ideal_index[other] < ideal}
        extra_actual = actual_before - ideal_before
        extra_ideal = ideal_before - actual_before

        def work(ids: set[int]) -> float:
            return sum(int(jobs[other]["worker_holding_ns"]) for other in ids) / 1e9

        mapped_ideal_start_ns = origin_ns + ideal_start_us[job] * 1000
        return {
            "job_id": job,
            "score": scores[job],
            "physical_minus_ideal_wait_s": int(row["physical_minus_production_wait_us"])
            / 1e6,
            "physical_wait_s": int(row["actual_wait_ns"]) / 1e9,
            "ideal_wait_s": int(row["production_replay_wait_us"]) / 1e6,
            "physical_dispatch_index": actual,
            "ideal_dispatch_index": ideal,
            "dispatch_index_shift": actual - ideal,
            "physical_start_minus_mapped_ideal_start_s": (
                int(row["worker_start_ns"]) - mapped_ideal_start_ns
            )
            / 1e9,
            "extra_jobs_before_physical_count": len(extra_actual),
            "extra_jobs_before_physical_measured_work_s": work(extra_actual),
            "extra_jobs_before_ideal_count": len(extra_ideal),
            "extra_jobs_before_ideal_measured_work_s": work(extra_ideal),
            "episode_at_earlier_position": episode_for_position.get(min(actual, ideal)),
        }

    top = sorted(
        jobs,
        key=lambda row: abs(int(row["physical_minus_production_wait_us"])),
        reverse=True,
    )[:TOP_JOBS]
    positive = max(jobs, key=lambda row: int(row["physical_minus_production_wait_us"]))
    negative = min(jobs, key=lambda row: int(row["physical_minus_production_wait_us"]))

    spjf_summary = summarize_delta(jobs)
    fcfs_summary = summarize_delta(fcfs_jobs)
    assert (
        spjf_summary["dispatch_index_mismatching_jobs"]
        == spjf_audit["dispatch_comparison"]["production_mismatching_jobs"]
    )
    assert (
        fcfs_summary["dispatch_index_mismatching_jobs"]
        == fcfs_audit["dispatch_comparison"]["production_mismatching_jobs"]
    )
    assert abs(
        spjf_summary["mean_physical_minus_ideal_wait_s"]
        - spjf_audit["wait_comparison"]["mean_physical_minus_production_s"]
    ) < 1e-12

    inputs = [SPJF_JOBS, SPJF_DECISIONS, SPJF_AUDIT, event_path, FCFS_JOBS, FCFS_AUDIT]
    result = {
        "status": "PASS",
        "method": (
            "artifact-only reconstruction from stored physical and production-replay fields; "
            "no scheduler simulation and no NPZ access"
        ),
        "inputs": [artifact(path) for path in inputs],
        "spjf_e": spjf_summary,
        "fcfs_control": fcfs_summary,
        "choice_checks": {
            "physical_score_choices_checked": n,
            "physical_bad_choices": len(physical_bad_choices),
            "stored_ideal_score_choices_checked": n,
            "stored_ideal_bad_choices": len(ideal_bad_choices),
            "mismatch_epochs_with_both_choices_available_to_both": len(formula_conflicts),
        },
        "first_divergence": first_divergence,
        "permutation_episodes": {
            "count": len(episodes),
            "mismatching_positions": sum(actual_order[p] != ideal_order[p] for p in range(n)),
            "longest_dispatch_positions": max(
                int(episode["dispatch_positions"]) for episode in episodes
            ),
            "max_prefix_symmetric_difference_jobs": max_prefix_symmetric_difference,
            "mismatch_epoch_causes": dict(mismatch_causes),
            "starts_by_cause": dict(
                Counter(str(episode["start_detail"]["cause"]) for episode in episodes)
            ),
            "episodes": episodes,
        },
        "extreme_jobs": {
            "largest_positive": extreme(positive),
            "largest_negative": extreme(negative),
            "top_by_absolute_discrepancy": [extreme(row) for row in top],
            "work_set_note": (
                "extra-before work is descriptive measured service, not an additive delay "
                "decomposition on two servers"
            ),
        },
        "interpretation_rule": (
            "zero bad-choice counts and zero both-available conflicts reject a score-choice "
            "formula mismatch in these artifacts; direct episode starts caused by a job "
            "arriving between the mapped ideal epoch and the later physical decision are "
            "arrival crossings, while later positions in that episode are priority cascades"
        ),
        "execution": {
            "processes": 1,
            "children": 0,
            "wall_s": time.perf_counter() - wall,
            "cpu_s": time.process_time() - cpu,
        },
    }
    text = json.dumps(result, indent=2, allow_nan=False) + "\n"
    OUTPUT_JSON.write_text(text, encoding="utf-8")
    OUTPUT_LOG.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
