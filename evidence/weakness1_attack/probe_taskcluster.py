"""Cheap, read-only recency probe for one Firefox CI hardware worker pool.

Run from this directory after the other heavy command has finished:

env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME NUMBA_NUM_THREADS=4 OMP_NUM_THREADS=4 uv run --no-project --with requests python probe_taskcluster.py

The probe uses the Queue API's last 20 task claims per current worker. It therefore
does not define a continuous arrival window and cannot establish pool-wide p99 or
arrival coverage. It can cheaply decide whether a full collection is worth attempting.
All parameters are frozen below. Every response is cached under raw/taskcluster_probe/.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests


HERE = Path(__file__).resolve().parent
RAW = HERE / "raw" / "taskcluster_probe"
LOG_PATH = HERE / "out_probe_taskcluster.txt"
SUMMARY_PATH = HERE / "probe_taskcluster_summary.json"
MANIFEST_PATH = RAW / "manifest.json"

ROOT_URL = "https://firefox-ci-tc.services.mozilla.com"
QUEUE = ROOT_URL + "/api/queue/v1"
PROVISIONER = "releng-hardware"
WORKER_TYPE = "gecko-3-b-osx-arm64"
POOL = PROVISIONER + "/" + WORKER_TYPE

# Existing evidence found maxRunTime values 2,700, 7,200 and 15,000 seconds in this
# pool. A recency sample may omit the 15,000-second class, so it may never lower L.
KNOWN_POOL_L_FLOOR_S = 15_000.0
TARGET_MULTIPLE = 3.0
TAIL_TOP1_SHARE_MIN = 0.25
MAX_CURRENT_WORKERS = 8
MAX_RECENT_TASKS_PER_WORKER = 20
MAX_NETWORK_REQUESTS = 25
MIN_REQUEST_INTERVAL_S = 0.26  # <= 3.85 requests/s
TIMEOUT_S = (10, 45)

USER_AGENT = (
    "spjf-guard-queue-study/1.0 "
    "(public academic read-only queue probe; no contact information)"
)
LICENCE_NOTE = (
    "No data-licence statement was found for the Mozilla API responses; "
    "public unauthenticated API, attribution intended, raw responses not for redistribution."
)


class ProbeError(RuntimeError):
    pass


RAW.mkdir(parents=True, exist_ok=True)
sys.dont_write_bytecode = True

_network_requests = 0
_last_request = 0.0
_log_handle = None


def log(message: str) -> None:
    print(message, flush=True)
    if _log_handle is not None:
        _log_handle.write(message + "\n")
        _log_handle.flush()


def atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        return {"source": "Mozilla Firefox CI Taskcluster public API", "files": {}}
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def save_manifest(manifest: dict) -> None:
    atomic_write(
        MANIFEST_PATH,
        (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )


def cached_json_request(
    session: requests.Session,
    method: str,
    url: str,
    cache_name: str,
    body: dict | None = None,
) -> dict:
    global _network_requests, _last_request

    path = RAW / cache_name
    if path.exists():
        raw = path.read_bytes()
        manifest = load_manifest()
        if cache_name not in manifest["files"]:
            manifest["files"][cache_name] = {
                "method": method,
                "url": url,
                "retrieved_utc": None,
                "local_mtime_utc": datetime.fromtimestamp(
                    path.stat().st_mtime, timezone.utc
                ).isoformat(),
                "size_bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "licence": LICENCE_NOTE,
                "request_body_sha256": (
                    hashlib.sha256(
                        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
                    ).hexdigest()
                    if body is not None
                    else None
                ),
                "note": "Recovered metadata for a pre-existing cache file; retrieval time unknown.",
            }
            save_manifest(manifest)
        log(f"cache hit {cache_name}: {len(raw)} bytes")
        return json.loads(raw)

    if _network_requests >= MAX_NETWORK_REQUESTS:
        raise ProbeError(f"network request cap {MAX_NETWORK_REQUESTS} reached")
    delay = MIN_REQUEST_INTERVAL_S - (time.monotonic() - _last_request)
    if delay > 0:
        time.sleep(delay)

    if method == "GET":
        response = session.get(url, timeout=TIMEOUT_S)
    elif method == "POST":
        # These two Queue endpoints are read-only batch lookups. POST is required
        # because the task-id list is the request body; no external state is changed.
        response = session.post(url, json=body, timeout=TIMEOUT_S)
    else:
        raise ProbeError(f"unsupported method {method}")
    _last_request = time.monotonic()
    _network_requests += 1
    log(f"request {_network_requests}/{MAX_NETWORK_REQUESTS}: {method} {url} -> {response.status_code}")
    if response.status_code != 200:
        raise ProbeError(
            f"{method} {url} returned HTTP {response.status_code}: {response.text[:300]}"
        )

    raw = response.content
    atomic_write(path, raw)
    manifest = load_manifest()
    manifest["files"][cache_name] = {
        "method": method,
        "url": url,
        "retrieved_utc": datetime.now(timezone.utc).isoformat(),
        "size_bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "licence": LICENCE_NOTE,
        "request_body_sha256": (
            hashlib.sha256(
                json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            if body is not None
            else None
        ),
        "response_content_length_header": response.headers.get("content-length"),
    }
    save_manifest(manifest)
    return response.json()


def parse_time(value: str | None) -> float:
    if not value:
        return math.nan
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def quantile(values: list[float], q: float) -> float:
    if not values:
        return math.nan
    xs = sorted(values)
    h = (len(xs) - 1) * q
    lo = math.floor(h)
    hi = math.ceil(h)
    if lo == hi:
        return xs[lo]
    return xs[lo] + (h - lo) * (xs[hi] - xs[lo])


def safe_segment(value: str) -> str:
    return quote(value, safe="")


def main() -> None:
    wall0 = time.perf_counter()
    cpu0 = time.process_time()
    session = requests.Session()
    session.headers.update(
        {"User-Agent": USER_AGENT, "Accept": "application/json", "Accept-Encoding": "gzip"}
    )

    workers_url = (
        f"{QUEUE}/provisioners/{safe_segment(PROVISIONER)}/worker-types/"
        f"{safe_segment(WORKER_TYPE)}/workers?limit=500"
    )
    workers_page = cached_json_request(
        session, "GET", workers_url, "01_list_workers.json"
    )
    if workers_page.get("continuationToken"):
        raise ProbeError(
            "listWorkers returned a continuation token; this script deliberately refuses "
            "to sample an incomplete worker list"
        )
    workers = sorted(
        workers_page.get("workers", []),
        key=lambda x: (x.get("workerGroup", ""), x.get("workerId", "")),
    )
    if not workers:
        raise ProbeError("listWorkers returned no current workers")
    if len(workers) > MAX_CURRENT_WORKERS:
        raise ProbeError(
            f"pool now lists {len(workers)} workers, above frozen cap {MAX_CURRENT_WORKERS}; "
            "review the sampling plan before running more requests"
        )
    log(f"current workers: {len(workers)}")

    claims: dict[tuple[str, int], set[tuple[str, str]]] = {}
    worker_metadata = []
    for index, worker in enumerate(workers, start=1):
        group = worker["workerGroup"]
        worker_id = worker["workerId"]
        worker_url = (
            f"{QUEUE}/provisioners/{safe_segment(PROVISIONER)}/worker-types/"
            f"{safe_segment(WORKER_TYPE)}/workers/{safe_segment(group)}/"
            f"{safe_segment(worker_id)}"
        )
        detail = cached_json_request(
            session,
            "GET",
            worker_url,
            f"02_worker_{index:02d}_{safe_segment(group)}_{safe_segment(worker_id)}.json",
        )
        recent = detail.get("recentTasks", [])
        if len(recent) > MAX_RECENT_TASKS_PER_WORKER:
            raise ProbeError(
                f"worker {group}/{worker_id} returned {len(recent)} recent tasks, "
                f"above documented cap {MAX_RECENT_TASKS_PER_WORKER}"
            )
        for item in recent:
            if "taskId" not in item or "runId" not in item:
                raise ProbeError("getWorker recentTasks item lacks taskId or runId")
            key = (str(item["taskId"]), int(item["runId"]))
            claims.setdefault(key, set()).add((group, worker_id))
        worker_metadata.append(
            {
                "workerGroup": group,
                "workerId": worker_id,
                "firstClaim": detail.get("firstClaim"),
                "lastDateActive": detail.get("lastDateActive"),
                "quarantineUntil": detail.get("quarantineUntil"),
                "recentTaskCount": len(recent),
            }
        )

    if not claims:
        raise ProbeError("getWorker returned no recent task claims")
    task_ids = sorted({task_id for task_id, _ in claims})
    if len(task_ids) > 500:
        raise ProbeError(f"unexpectedly found {len(task_ids)} task ids; batch cap is 500")
    log(
        f"recent claim references: {sum(x['recentTaskCount'] for x in worker_metadata)}; "
        f"unique task/run pairs: {len(claims)}; unique tasks: {len(task_ids)}"
    )

    body = {"taskIds": task_ids}
    body_key = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]
    statuses_page = cached_json_request(
        session,
        "POST",
        f"{QUEUE}/tasks/status",
        f"03_statuses_{body_key}.json",
        body,
    )
    definitions_page = cached_json_request(
        session,
        "POST",
        f"{QUEUE}/tasks",
        f"04_definitions_{body_key}.json",
        body,
    )
    if statuses_page.get("continuationToken") or definitions_page.get("continuationToken"):
        raise ProbeError(
            "a batch endpoint returned a continuation token; no partial result will be reported"
        )

    statuses = {}
    for item in statuses_page.get("statuses", []):
        status = item.get("status", {})
        task_id = item.get("taskId") or status.get("taskId")
        if task_id:
            statuses[str(task_id)] = status
    definitions = {}
    for item in definitions_page.get("tasks", []):
        task_id = item.get("taskId")
        if task_id:
            definitions[str(task_id)] = item.get("task", {})

    task_max_run_time = {}
    invalid_max_run_time_task_ids = []
    for task_id in task_ids:
        definition = definitions.get(task_id)
        value = definition.get("payload", {}).get("maxRunTime") if definition else None
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            parsed = math.nan
        if not math.isfinite(parsed) or parsed <= 0:
            invalid_max_run_time_task_ids.append(task_id)
        else:
            task_max_run_time[task_id] = parsed

    rows = []
    missing_status = 0
    malformed_run = 0
    pool_mismatch = 0
    claim_worker_mismatch = 0
    for (task_id, run_id), claimed_workers in sorted(claims.items()):
        status = statuses.get(task_id)
        if status is None:
            missing_status += 1
            continue
        if status.get("taskQueueId") != POOL:
            pool_mismatch += 1
            continue
        run = next((r for r in status.get("runs", []) if int(r.get("runId", -1)) == run_id), None)
        if run is None:
            malformed_run += 1
            continue
        scheduled = parse_time(run.get("scheduled"))
        started = parse_time(run.get("started"))
        resolved = parse_time(run.get("resolved"))
        if not all(math.isfinite(x) for x in (scheduled, started, resolved)):
            malformed_run += 1
            continue
        if not (scheduled <= started <= resolved):
            malformed_run += 1
            continue
        observed_worker = (str(run.get("workerGroup", "")), str(run.get("workerId", "")))
        if observed_worker not in claimed_workers:
            claim_worker_mismatch += 1

        max_run_time = task_max_run_time.get(task_id)
        rows.append(
            {
                "taskId": task_id,
                "runId": run_id,
                "workerGroup": run.get("workerGroup"),
                "workerId": run.get("workerId"),
                "scheduled": run.get("scheduled"),
                "started": run.get("started"),
                "resolved": run.get("resolved"),
                "wait_s": started - scheduled,
                "service_s": resolved - started,
                "maxRunTime_s": max_run_time,
            }
        )

    if not rows:
        raise ProbeError("no completed recent runs had true scheduled/started/resolved timestamps")
    waits = [row["wait_s"] for row in rows]
    services = [row["service_s"] for row in rows]
    service_total = sum(services)
    if not math.isfinite(service_total) or service_total <= 0:
        raise ProbeError(f"non-positive or non-finite total service: {service_total}")
    max_run_times = list(task_max_run_time.values())
    p99_wait = quantile(waits, 0.99)
    sample_l = max(max_run_times) if max_run_times else math.nan
    l_used = max(KNOWN_POOL_L_FLOOR_S, sample_l if math.isfinite(sample_l) else 0.0)
    threshold = TARGET_MULTIPLE * l_used
    # The empirical top-1% set is the longest ceil(0.01*n) runs. This definition is
    # explicit because at n <= 140 the difference between one and two runs is material.
    top_count = max(1, math.ceil(len(services) * 0.01))
    top_share = sum(sorted(services, reverse=True)[:top_count]) / service_total
    complete_definitions = len(invalid_max_run_time_task_ids) == 0

    service_limit_pairs = [
        (row["service_s"], row["maxRunTime_s"])
        for row in rows
        if row["maxRunTime_s"] is not None
    ]
    service_over_limit_count = sum(
        1 for service, max_run_time in service_limit_pairs if service > max_run_time
    )
    service_over_limit_share = (
        service_over_limit_count / len(service_limit_pairs) if service_limit_pairs else None
    )

    wait_condition_on_used_limit = p99_wait >= threshold
    tail_condition = top_share >= TAIL_TOP1_SHARE_MIN
    if not wait_condition_on_used_limit:
        wait_result = "fail in the truncated recency sample"
    elif complete_definitions:
        wait_result = "pass in the truncated recency sample"
    else:
        wait_result = (
            "inconclusive: p99 exceeds 3 times the known/sample limit, but missing or "
            "invalid task limits could make the true pool maximum larger"
        )
    tail_result = (
        "pass in the truncated recency sample"
        if tail_condition
        else "fail in the truncated recency sample"
    )
    if not tail_condition or not wait_condition_on_used_limit:
        joint_result = (
            "the two numerical screens do not both pass in this truncated recency sample; "
            "this is triage, not a pool-wide conclusion"
        )
    elif not complete_definitions:
        joint_result = (
            "inconclusive because the wait screen lacks complete, valid maxRunTime coverage"
        )
    else:
        joint_result = (
            "both numerical screens pass in this truncated recency sample only; a continuous "
            "trace and coverage audit are still required"
        )

    summary = {
        "written_utc": datetime.now(timezone.utc).isoformat(),
        "pool": POOL,
        "scope": "last 20 task claims per current worker; not a continuous arrival window",
        "network_requests_this_run": _network_requests,
        "network_request_cap": MAX_NETWORK_REQUESTS,
        "workers": worker_metadata,
        "counts": {
            "current_workers": len(workers),
            "recent_claim_references": sum(x["recentTaskCount"] for x in worker_metadata),
            "unique_task_run_pairs": len(claims),
            "unique_task_ids": len(task_ids),
            "completed_runs_with_true_wait": len(rows),
            "missing_status": missing_status,
            "missing_or_invalid_maxRunTime_task_ids": len(invalid_max_run_time_task_ids),
            "malformed_or_incomplete_run": malformed_run,
            "pool_mismatch": pool_mismatch,
            "claim_worker_mismatch": claim_worker_mismatch,
        },
        "metrics": {
            "recorded_wait_p50_s": quantile(waits, 0.50),
            "recorded_wait_p90_s": quantile(waits, 0.90),
            "recorded_wait_p99_s": p99_wait,
            "recorded_wait_max_s": max(waits),
            "service_top1_share": top_share,
            "service_top1_job_count": top_count,
            "service_top1_definition": "longest ceil(0.01*n) completed sampled runs",
            "service_total_s": service_total,
            "service_over_maxRunTime_count": service_over_limit_count,
            "service_with_valid_maxRunTime_count": len(service_limit_pairs),
            "service_over_maxRunTime_share": service_over_limit_share,
            "sample_maxRunTime_max_s": sample_l if math.isfinite(sample_l) else None,
            "known_pool_maxRunTime_floor_s": KNOWN_POOL_L_FLOOR_S,
            "limit_used_s": l_used,
            "three_times_limit_s": threshold,
            "p99_over_limit": p99_wait / l_used,
        },
        "screens": {
            "wait_threshold_multiple": TARGET_MULTIPLE,
            "wait_condition_on_used_limit": wait_condition_on_used_limit,
            "wait_maxRunTime_coverage_complete": complete_definitions,
            "wait_result": wait_result,
            "tail_top1_share_min": TAIL_TOP1_SHARE_MIN,
            "tail_condition": tail_condition,
            "tail_result": tail_result,
            "both_conditions_supported": (
                wait_condition_on_used_limit and complete_definitions and tail_condition
            ),
            "joint_result": joint_result,
        },
        "invalid_maxRunTime_task_ids": invalid_max_run_time_task_ids,
        "limitations": [
            "The worker API retains only the 20 most recent claims per current worker.",
            "Different workers' recency slices span different times; this is not a common window.",
            "Retired workers and tasks that never claimed a worker are absent.",
            "A sample p99 based on at most about 140 claims is unstable and cannot validate replay coverage.",
            "True queue wait is available here only because the read-only batch status response contains scheduled and started.",
            "The API data licence is not stated; raw responses are retained locally and should not be redistributed.",
        ],
        "runs": rows,
        "timing": {
            "wall_seconds": time.perf_counter() - wall0,
            "process_cpu_seconds": time.process_time() - cpu0,
        },
    }
    atomic_write(
        SUMMARY_PATH,
        (json.dumps(summary, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    log(f"completed runs with true wait: {len(rows)}")
    log(
        f"wait p99={p99_wait:.1f}s; L used={l_used:.1f}s; "
        f"p99/L={p99_wait/l_used:.3f}; 3L={threshold:.1f}s"
    )
    log(
        f"tail: top {top_count}/{len(services)} service share={top_share:.4f}; "
        f"condition >= {TAIL_TOP1_SHARE_MIN:.2f}: {tail_condition}"
    )
    log(
        f"wait condition p99 >= {TARGET_MULTIPLE:.1f}L: {wait_condition_on_used_limit}; "
        f"maxRunTime coverage complete: {complete_definitions}"
    )
    log(
        f"service > task maxRunTime: {service_over_limit_count}/{len(service_limit_pairs)} "
        "among runs with a valid limit; services are reported as recorded and are not capped"
    )
    log(f"joint screen: {joint_result}")
    log(
        "scope warning: last-20 claims per current worker are not a continuous arrival "
        "window and cannot establish pool-wide p99 or arrival coverage"
    )
    log(f"summary: {SUMMARY_PATH.name}")


if __name__ == "__main__":
    started_utc = datetime.now(timezone.utc).isoformat()
    invocation_wall, invocation_cpu = time.perf_counter(), time.process_time()
    with LOG_PATH.open("w", encoding="utf-8") as handle:
        _log_handle = handle
        log(f"started_utc: {started_utc}")
        log(f"pool: {POOL}")
        log(f"request cap: {MAX_NETWORK_REQUESTS}; minimum interval: {MIN_REQUEST_INTERVAL_S}s")
        try:
            main()
        except Exception as exc:
            log(f"ERROR: {type(exc).__name__}: {exc}")
            failure = {
                "status": "incomplete_probe",
                "pool": POOL,
                "started_utc": started_utc,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "network_requests": _network_requests,
                "interpretation": "No pool-wide applicability conclusion follows from an incomplete or refused retrieval.",
                "timing": {
                    "wall_seconds": time.perf_counter() - invocation_wall,
                    "process_cpu_seconds": time.process_time() - invocation_cpu,
                },
            }
            atomic_write(SUMMARY_PATH, (json.dumps(failure, indent=2) + "\n").encode("utf-8"))
            raise
