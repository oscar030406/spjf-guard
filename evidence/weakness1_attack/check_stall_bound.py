"""Check the completed Guard(300) trace against STALL_BOUND.md in exact ns.

Run only after the physical service and verify_physical.py have finished:
    python check_stall_bound.py --physical-complete
No physical payloads, worker processes, or policy-order coupling are used.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import heapq
import json
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
import verify_physical as shared


HERE = Path(__file__).resolve().parent
POLICY = "Guard(300)"
K = shared.K
L = shared.L_NS
B0 = 30_000_000_000
BMAX = 356_000_000_000
G = shared.G_NS
N = shared.OVERLAY_JOBS
JSON_PATH = HERE / "stall_bound_check.json"
CSV_PATH = HERE / "stall_bound_jobs.csv"
LOG_PATH = HERE / "out_stall_bound_check.txt"


def need(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def json_file(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def json_lines(path: Path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def bound_path(relative: str) -> Path:
    path = (HERE / relative).resolve()
    need(HERE == path.parent or HERE in path.parents, f"unconfined path: {relative}")
    return path


class Checks:
    def __init__(self):
        self.counts = defaultdict(lambda: {"checked": 0, "failed": 0})
        self.failures = []

    def test(self, name, condition, context=None):
        self.counts[name]["checked"] += 1
        if not condition:
            self.counts[name]["failed"] += 1
            if len(self.failures) < 20:
                self.failures.append({"check": name, "context": context})

    def gate(self, stage):
        need(not self.failures, f"{stage}: {self.failures[0] if self.failures else ''}")


def load_bound_artifacts():
    need(K == 2 and L == 61_000_000_000 and G == 300_000_000_000,
         "this checker specializes the k=2, L=61 s, G=300 s theorem")
    verification_path = HERE / "physical_verification.json"
    verification = json_file(verification_path)
    checkpoint_path = HERE / "physical_checkpoint.json"
    summary_path = HERE / "physical_summary.json"
    checkpoint, summary = json_file(checkpoint_path), json_file(summary_path)
    protocol, input_hash = shared.OVERLAY_PROTOCOL, shared.OVERLAY_INPUT_SHA256
    need(verification["status"] == "PASS", "shared physical verification is not PASS")
    need(verification["profile"] == "development_overlay", "wrong verification profile")
    need(verification["jobs"] == N, "wrong verified job count")
    need(verification["protocol"] == checkpoint["protocol"] == summary["protocol"] == protocol,
         "protocol binding mismatch")
    need(verification["input_sha256"] == checkpoint["input_sha256"]
         == summary["input"]["input_sha256"] == input_hash, "input binding mismatch")
    need(set(checkpoint["completed"]) == set(shared.POLICIES), "physical policies incomplete")
    need(summary["completed_policies"] == list(shared.POLICIES), "summary is incomplete")
    need(set(verification["policies"]) == set(shared.POLICIES), "verification is incomplete")
    need(summary["parameters"]["guard"] == shared.GUARD_PARAMETERS, "guard parameters changed")
    need(summary["parameters"]["workers"] == K, "worker count changed")
    need(summary["parameters"]["protocol_version"] == 2, "wrong protocol version")
    source_paths = {"verification": verification_path, "checkpoint": checkpoint_path,
                    "summary": summary_path, "input": HERE / "physical_input.npz",
                    "shared_verifier": HERE / "verify_physical.py",
                    "proof": HERE / "STALL_BOUND.md"}
    entry = checkpoint["completed"][POLICY]
    need(entry["policy"] == POLICY and entry["input_sha256"] == input_hash,
         "wrong completed Guard binding")
    paths = {}
    for kind, suffix in (("jobs", "jobs.jsonl"), ("decisions", "decisions.jsonl"),
                         ("audit", "audit.json")):
        path = bound_path(entry[kind]["path"])
        need(path == HERE / f"physical_guard_300_{suffix}", f"wrong {kind} path")
        need(path.stat().st_size == entry[kind]["bytes"], f"{kind} size mismatch")
        need(shared.digest(path) == entry[kind]["sha256"], f"{kind} hash mismatch")
        paths[kind] = path
        source_paths[kind] = path
    audit = json_file(paths["audit"])
    need(audit == summary["audits"][POLICY], "artifact/summary audit mismatch")
    need(audit["policy"] == POLICY and audit["jobs"] == N, "wrong audit scope")
    need(audit["protocol"] == protocol and audit["input_sha256"] == input_hash,
         "wrong audit binding")
    prefix = audit["event_prefix_audit"]
    need(prefix["passed"] is True and prefix["error_count"] == 0
         and prefix["dispatches_checked"] == N, "observed-prefix audit is not PASS")
    need(not audit["model_assumption_failed"] and audit["jobs_exceeding_L"] == 0,
         "shared audit reports a failed service cap")
    paths["events"] = bound_path(prefix["event_path"])
    need(shared.digest(paths["events"]) == prefix["event_sha256"], "event hash mismatch")
    source_paths["events"] = paths["events"]
    jobs = sorted(json_lines(paths["jobs"]), key=lambda row: row["job_id"])
    need([row["job_id"] for row in jobs] == list(range(N)), "wrong job IDs")
    fixed = shared.load_physical_input(HERE / "physical_input.npz")
    shared._assert_fixed_fields(jobs, fixed, N)
    sources = {name: {"path": str(path.relative_to(HERE)), "sha256": shared.digest(path),
                      "bytes": path.stat().st_size} for name, path in source_paths.items()}
    return jobs, paths, sources


def audit_schedule(jobs, paths, checks):
    clock_fields = ("actual_enqueue_ns", "decision_clock_ns", "dispatcher_dispatch_ns",
                    "worker_start_ns", "worker_finish_ns", "dispatcher_completion_receipt_ns")
    origin = jobs[0]["target_release_ns"] - jobs[0]["target_release_offset_ns"]
    for i, row in enumerate(jobs):
        checks.test("integer_clock_fields", all(type(row[f]) is int for f in clock_fields), i)
        checks.test("timestamp_order", all(row[x] <= row[y] for x, y in
                    zip(clock_fields, clock_fields[1:])), i)
        checks.test("job_binding", row["policy"] == POLICY and row["rank"] == i
                    and row["protocol"] == shared.OVERLAY_PROTOCOL
                    and row["input_sha256"] == shared.OVERLAY_INPUT_SHA256, i)
        checks.test("rank_arrivals", i == 0 or jobs[i-1]["actual_enqueue_ns"]
                    <= row["actual_enqueue_ns"], i)
        checks.test("empty_common_origin", origin <= row["actual_enqueue_ns"]
                    and row["target_release_ns"] - row["target_release_offset_ns"] == origin, i)
        checks.test("holding_cost_and_cap", type(row["worker_holding_ns"]) is int
                    and 0 < row["worker_holding_ns"] <= L
                    and row["worker_holding_ns"] == row["worker_finish_ns"]-row["worker_start_ns"], i)
        checks.test("wait_and_launch_fields", row["actual_wait_ns"]
                    == row["worker_start_ns"]-row["actual_enqueue_ns"]
                    and row["dispatch_to_worker_start_ns"]
                    == row["worker_start_ns"]-row["dispatcher_dispatch_ns"], i)
        checks.test("worker_id", type(row["worker_id"]) is int and 0 <= row["worker_id"] < K, i)
    order = sorted(jobs, key=lambda row: row["dispatch_index"])
    checks.test("dispatch_indices", [row["dispatch_index"] for row in order] == list(range(N)))
    for left, right in zip(order, order[1:]):
        checks.test("serial_decisions", left["dispatcher_dispatch_ns"] <= right["decision_clock_ns"],
                    [left["job_id"], right["job_id"]])
    for worker in range(K):
        sequence = [r for r in order if r["worker_id"] == worker]
        for left, right in zip(sequence, sequence[1:]):
            checks.test("receipt_before_next_decision", left["dispatcher_completion_receipt_ns"]
                        <= right["decision_clock_ns"], [left["job_id"], right["job_id"]])
            checks.test("physical_nonoverlap", left["worker_finish_ns"] <= right["worker_start_ns"],
                        [left["job_id"], right["job_id"]])
    checks.gate("job schedule assumptions")

    waiting, arrived, received, assigned = set(), set(), set(), set()
    outstanding = {}
    receipt_pos, dispatch_pos = [-1]*N, [-1]*N
    decision_iter = iter(json_lines(paths["decisions"]))
    dispatch_count = complete_count = start_count = 0
    latest_clock = origin
    for pos, event in enumerate(json_lines(paths["events"])):
        kind = event["type"]
        if kind == "policy_start":
            start_count += 1
            checks.test("event_empty_start", event["origin_ns"] == origin and not assigned
                        and event["policy"] == POLICY and event["jobs"] == N, pos)
            continue
        if kind == "arrival_enqueued":
            i = event["job_id"]
            checks.test("event_unique_ranked_arrival", i not in arrived and i == len(arrived), pos)
            checks.test("event_arrival_matches", event["actual_enqueue_ns"]
                        == jobs[i]["actual_enqueue_ns"], i)
            latest_clock = event_clock(checks, latest_clock, event["actual_enqueue_ns"], pos)
            arrived.add(i)
            waiting.add(i)
        elif kind == "completion_visible":
            i, worker = event["job_id"], event["worker_id"]
            row = jobs[i]
            checks.test("event_unique_reserved_completion", i not in received
                        and outstanding.get(worker) == i, pos)
            pairs = {"worker_start_ns": "worker_start_ns", "worker_finish_ns": "worker_finish_ns",
                     "dispatcher_completion_receipt_ns": "dispatcher_completion_receipt_ns",
                     "charged_worker_holding_ns": "worker_holding_ns"}
            checks.test("event_completion_matches", all(event[x] == row[y] for x, y in pairs.items()), i)
            latest_clock = event_clock(checks, latest_clock, event["dispatcher_completion_receipt_ns"], pos)
            received.add(i)
            receipt_pos[i] = pos
            outstanding.pop(worker, None)
        elif kind == "dispatch":
            decision = next(decision_iter, None)
            need(decision is not None, "missing decision record")
            i, worker = event["job_id"], event["worker_id"]
            row, theta = jobs[i], decision["decision_clock_ns"]
            checks.test("event_dispatch_binding", decision["protocol"] == shared.OVERLAY_PROTOCOL
                        and decision["input_sha256"] == shared.OVERLAY_INPUT_SHA256
                        and decision["policy"] == POLICY and decision["chosen_job"] == i
                        and decision["decision_index"] == event["decision_index"]
                        == row["dispatch_index"] == dispatch_count
                        and decision["worker_id"] == row["worker_id"] == worker
                        and decision["dispatcher_dispatch_ns"] == event["dispatcher_dispatch_ns"]
                        == row["dispatcher_dispatch_ns"] and theta == row["decision_clock_ns"], i)
            checks.test("event_available_slot", i in waiting and i not in assigned
                        and worker not in outstanding and len(outstanding) <= K-1, i)
            checks.test("event_decision_clock", latest_clock <= theta, i)
            latest_clock = event_clock(checks, latest_clock, event["dispatcher_dispatch_ns"], pos)
            checks.test("event_waiting_prefix", decision["waiting_ranks"] == sorted(waiting)
                        and decision["dispatcher_enqueued_count"] == len(arrived)
                        and decision["dispatcher_visible_completion_count"] == len(received), i)
            checks.test("all_actual_arrivals_before_decision_including_ties",
                        arrived == {q for q in range(N) if jobs[q]["actual_enqueue_ns"] <= theta}, i)
            suffix = [0]*(N+1)
            for q in range(N-1, -1, -1):
                suffix[q] = suffix[q+1] + (jobs[q]["worker_holding_ns"] if q in received else 0)
            checks.test("event_completed_counter", decision["visible_completed_work_ns"] == suffix[0]
                        and row["visible_completed_work_ns_at_dispatch"] == suffix[0], i)
            evaluations = decision["waiting_evaluation"]
            checks.test("event_evaluation_ranks", [e["job_id"] for e in evaluations] == sorted(waiting), i)
            fired = []
            for evaluation in evaluations:
                q = evaluation["job_id"]
                age = theta-jobs[q]["actual_enqueue_ns"]
                # eta*k = (1/2)*2 = 1 exactly; no rounding or ceiling is needed.
                budget = min(B0+age, BMAX)
                over = suffix[q+1]
                is_fired = over >= budget
                if is_fired:
                    fired.append(q)
                checks.test("event_exact_budget_and_charge", age >= 0
                            and evaluation["age_ns"] == age
                            and evaluation["budget_ns"] == budget
                            and evaluation["over_completed_worker_holding_ns"] == over
                            and evaluation["fired"] == is_fired, [i, q])
            base = min(waiting, key=lambda q: (jobs[q]["score"], q))
            expected = min(fired) if fired else base
            checks.test("event_guard_choice", decision["fired_set"] == fired
                        and decision["base_choice"] == base and expected == i
                        and decision["guard_fired"] == bool(fired)
                        and event["guard_fired"] == bool(fired)
                        and decision["choice_changed"] == (i != base), i)
            outstanding[worker] = i
            waiting.discard(i)
            assigned.add(i)
            dispatch_pos[i] = pos
            dispatch_count += 1
        elif kind == "policy_complete":
            complete_count += 1
            checks.test("event_complete_state", not outstanding and not waiting and len(received) == N, pos)
    checks.test("event_all_records_complete", start_count == complete_count == 1
                and len(arrived) == len(received) == len(assigned) == dispatch_count == N
                and next(decision_iter, None) is None)
    checks.gate("independent observed-prefix audit")
    return origin, receipt_pos, dispatch_pos


def event_clock(checks, previous, current, pos):
    checks.test("event_monotone_clock", previous <= current, pos)
    return max(previous, current)


def sweep(jobs, origin, checks):
    availability = [(origin, worker) for worker in range(K)]
    heapq.heapify(availability)
    fs, ff = [], []
    for row in jobs:
        available, worker = availability[0]
        start = max(row["actual_enqueue_ns"], available)
        finish = start+row["worker_holding_ns"]
        heapq.heapreplace(availability, (finish, worker))
        fs.append(start)
        ff.append(finish)
    # Each endpoint carries changes to unstarted count, physical busy count,
    # reference busy count, and total arriving work, in that order.
    events = defaultdict(lambda: [0, 0, 0, 0])
    events[origin]
    for i, row in enumerate(jobs):
        a, s, f, d = (row[x] for x in ("actual_enqueue_ns", "worker_start_ns",
                                      "worker_finish_ns", "dispatcher_dispatch_ns"))
        events[a][0] += 1
        events[a][3] += row["worker_holding_ns"]
        events[s][0] -= 1
        events[s][1] += 1
        events[f][1] -= 1
        events[fs[i]][2] += 1
        events[ff[i]][2] -= 1
        events[d]
    q = bp = bf = up = uf = deficit = 0
    previous = origin
    deficits, gaps = {}, {}
    minimum_gap_margin = None
    for timestamp in sorted(events):
        dt = timestamp-previous
        up -= bp*dt
        uf -= bf*dt
        if q > 0:
            deficit += (K-bp)*dt
        dq, dbp, dbf, incoming = events[timestamp]
        up += incoming
        uf += incoming
        q += dq
        bp += dbp
        bf += dbf
        checks.test("sweep_capacity_and_work", q >= 0 and 0 <= bp <= K
                    and 0 <= bf <= K and up >= 0 and uf >= 0, timestamp)
        margin = (K-1)*L+deficit-(up-uf)
        checks.test("lemma4_all_linear_endpoints", margin >= 0, {"t_ns": timestamp, "margin": margin})
        minimum_gap_margin = margin if minimum_gap_margin is None else min(minimum_gap_margin, margin)
        deficits[timestamp], gaps[timestamp] = deficit, up-uf
        previous = timestamp
    checks.test("sweep_empty_end", q == bp == bf == up == uf == 0)
    checks.gate("capacity integral and workload comparison")
    return fs, ff, deficits, gaps, {
        "linear_endpoints_checked": len(events), "J_end_worker_ns": deficit,
        "minimum_lemma4_margin_work_ns": minimum_gap_margin,
    }


def remaining(cost, start, timestamp):
    return cost-min(cost, max(0, timestamp-start))


def check_jobs(jobs, fs, deficits, gaps, receipt_pos, dispatch_pos, checks):
    rows = []
    costs = [r["worker_holding_ns"] for r in jobs]
    starts = [r["worker_start_ns"] for r in jobs]
    indices = [r["dispatch_index"] for r in jobs]
    for i, row in enumerate(jobs):
        a, d, s = row["actual_enqueue_ns"], row["dispatcher_dispatch_ns"], row["worker_start_ns"]
        wd, wf, launch = d-a, fs[i]-a, s-d
        overtakers = [j for j in range(i+1, N) if indices[j] < indices[i]]
        in_work = sum(costs[j] for j in overtakers)
        out_work = sum(costs[j] for j in range(i) if indices[j] > indices[i])
        rp = sum(remaining(costs[j], starts[j], a) for j in range(i))
        rf = sum(remaining(costs[j], fs[j], a) for j in range(i))
        rho_p = sum(remaining(costs[j], starts[j], d) for j in range(N) if indices[j] < indices[i])
        rho_f = sum(remaining(costs[j], fs[j], fs[i]) for j in range(i))
        jd, ja = deficits[d], deficits[a]
        checks.test("arrival_gap_partition", rp-rf == gaps[a], i)
        checks.test("residual_ranges", 0 <= rho_p <= (K-1)*L and 0 <= rho_f <= (K-1)*L, i)
        checks.test("reference_busy_identity", K*wf == rf-rho_f, i)
        rhs = in_work-out_work+(rp-rf)-rho_p+rho_f+jd-ja
        identity_error = K*(wd-wf)-rhs
        checks.test("eq6_exact_identity", identity_error == 0, {"job": i, "error_ns": identity_error})
        lemma7_margin = in_work-out_work+2*(K-1)*L+jd-K*(wd-wf)
        checks.test("lemma7", lemma7_margin >= 0, i)
        last = None
        observed = uncharged = 0
        last_budget = None
        if overtakers:
            last = max(overtakers, key=lambda j: indices[j])
            cutoff = dispatch_pos[last]
            observed = sum(costs[j] for j in range(i+1, N) if receipt_pos[j] < cutoff)
            outstanding = [j for j in range(N) if indices[j] < indices[last] and receipt_pos[j] > cutoff]
            uncharged = sum(costs[j] for j in overtakers if indices[j] < indices[last]
                            and receipt_pos[j] > cutoff)
            theta = jobs[last]["decision_clock_ns"]
            last_budget = min(B0+theta-a, BMAX)
            checks.test("last_overtaker_prefix", a <= theta <= d and len(outstanding) <= K-1
                        and observed < last_budget, i)
            checks.test("last_overtaker_partition", in_work == observed+uncharged+costs[last]
                        and uncharged <= (K-1)*L, i)
            checks.test("lemma8_guard_work_cap", in_work < BMAX+K*L, i)
            checks.test("lemma9_guard_age_work", in_work < B0+wd+K*L, i)
        additive_margin = BMAX+(3*K-2)*L+jd-K*(wd-wf)
        # eta = 1/2: multiply the multiplicative inequality by 2*k.
        multiplicative_margin = 2*K*wf+2*B0+2*(3*K-2)*L+2*jd-K*wd
        checks.test("corrected_additive_strict_bound", additive_margin > 0, i)
        checks.test("corrected_multiplicative_strict_bound", multiplicative_margin > 0, i)
        corrected_twice = min(2*(wf+G)+jd, 4*wf+548_000_000_000+2*jd)+2*launch
        corrected_margin_twice = corrected_twice-2*(s-a)
        checks.test("eq2_corrected_physical_bound", corrected_margin_twice > 0, i)
        rows.append({
            "job_id": i, "dispatch_index": indices[i], "actual_enqueue_ns": a,
            "dispatcher_dispatch_ns": d, "worker_start_ns": s,
            "actual_wait_ns": s-a, "dispatch_wait_ns": wd, "exact_shadow_fcfs_wait_ns": wf,
            "dispatch_to_start_ns": launch, "J_arrival_worker_ns": ja,
            "J_dispatch_worker_ns": jd, "J_wait_window_worker_ns": jd-ja,
            "In_work_ns": in_work, "Out_work_ns": out_work, "R_physical_work_ns": rp,
            "R_fcfs_work_ns": rf, "rho_physical_work_ns": rho_p, "rho_fcfs_work_ns": rho_f,
            "eq6_error_work_ns": identity_error, "lemma7_margin_work_ns": lemma7_margin,
            "last_overtaker_job_id": last, "last_observed_over_work_ns": observed,
            "last_uncharged_prior_over_work_ns": uncharged, "last_budget_work_ns": last_budget,
            "additive_margin_work_ns": additive_margin,
            "multiplicative_scaled_margin_work_ns": multiplicative_margin,
            "corrected_bound_twice_ns": corrected_twice,
            "corrected_bound_margin_twice_ns": corrected_margin_twice,
            "uncorrected_excess_ns": s-a-wf,
            "uncorrected_bound_margin_ns": min(wf+G, 2*wf+274_000_000_000)-(s-a),
        })
    return rows


def run(checks):
    jobs, paths, sources = load_bound_artifacts()
    origin, receipt_pos, dispatch_pos = audit_schedule(jobs, paths, checks)
    fs, ff, deficits, gaps, sweep_summary = sweep(jobs, origin, checks)
    rows = check_jobs(jobs, fs, deficits, gaps, receipt_pos, dispatch_pos, checks)
    # A second hash pass prevents a successful result from describing changing inputs.
    for source in sources.values():
        need(shared.digest(HERE / source["path"]) == source["sha256"], "source changed during check")
    with CSV_PATH.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "status": "PASS" if not checks.failures else "FAIL",
        "profile": "development_overlay", "policy": POLICY, "jobs": len(rows),
        "protocol": shared.OVERLAY_PROTOCOL, "input_sha256": shared.OVERLAY_INPUT_SHA256,
        "units": "All time/work checks are exact integer nanoseconds; work sums are worker-nanoseconds.",
        "parameters": {"k": K, "L_ns": L, "B0_ns": B0, "Bmax_ns": BMAX,
                       "eta_numerator": 1, "eta_denominator": 2, "gamma_ns": 0, "G_ns": G},
        "scope": "Measured-trace conditional pathwise certificate; no fixed future real-time promise.",
        "sources": sources, "sweep": sweep_summary,
        "metrics": {
            "corrected_violations": sum(r["corrected_bound_margin_twice_ns"] <= 0 for r in rows),
            "uncorrected_nonstrict_violations": sum(r["uncorrected_bound_margin_ns"] < 0 for r in rows),
            "maximum_uncorrected_excess_ns": max(r["uncorrected_excess_ns"] for r in rows),
            "minimum_uncorrected_margin_ns": min(r["uncorrected_bound_margin_ns"] for r in rows),
            "minimum_corrected_margin_twice_ns": min(r["corrected_bound_margin_twice_ns"] for r in rows),
            "maximum_J_dispatch_worker_ns": max(r["J_dispatch_worker_ns"] for r in rows),
            "maximum_dispatch_to_start_ns": max(r["dispatch_to_start_ns"] for r in rows),
            "sum_dispatch_to_start_ns": sum(r["dispatch_to_start_ns"] for r in rows),
            "maximum_additive_correction_twice_ns": max(r["J_dispatch_worker_ns"]
                                                        + 2*r["dispatch_to_start_ns"] for r in rows),
        },
        "job_table": {"path": CSV_PATH.name, "sha256": shared.digest(CSV_PATH), "rows": len(rows)},
    }
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--physical-complete", action="store_true",
                        help="Confirm the timed physical service and shared verification have finished.")
    args = parser.parse_args()
    if not args.physical_complete:
        parser.error("Run only after physical completion, with --physical-complete.")
    wall0, cpu0 = time.perf_counter_ns(), time.process_time_ns()
    checks = Checks()
    try:
        result = run(checks)
    except Exception as exc:
        result = {"status": "FAIL", "error_type": type(exc).__name__, "error": str(exc),
                  "job_table": None, "scope": "No successful certificate was produced."}
    result["checks"] = dict(checks.counts)
    result["first_failures"] = checks.failures
    result["execution"] = {"wall_ns": time.perf_counter_ns()-wall0,
                           "cpu_ns": time.process_time_ns()-cpu0,
                           "new_worker_processes": 0, "numeric_tolerances": 0,
                           "decision_records_streamed": True}
    result["checker_sha256"] = shared.digest(Path(__file__))
    text = json.dumps(result, indent=2, ensure_ascii=False)+"\n"
    JSON_PATH.write_text(text, encoding="utf-8")
    LOG_PATH.write_text(text, encoding="utf-8")
    print(text, end="")
    raise SystemExit(0 if result["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
