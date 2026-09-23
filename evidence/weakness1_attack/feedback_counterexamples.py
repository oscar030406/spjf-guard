"""Exact counterexamples to a one-sided interpretation of open-loop replay.

This file uses only the Python standard library.  It constructs finite,
single-server, non-preemptive FCFS and SJF schedules with deterministic user
think times.  The output is written next to this file as
``out_feedback_counterexamples.txt``.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction as F
import heapq
from pathlib import Path
import platform
import sys
import time
import traceback


OUTPUT_NAME = "out_feedback_counterexamples.txt"
POLICIES = ("FCFS", "SJF")
HORIZON = F(10)
DEADLINE_WINDOW_END_SECONDS = F(24)
DEADLINE_WINDOW_START_SECONDS = DEADLINE_WINDOW_END_SECONDS - F(86_400)


@dataclass(frozen=True)
class Job:
    name: str
    user: str
    step: int
    service: F
    input_order: int


@dataclass(frozen=True)
class User:
    name: str
    think: F
    jobs: tuple[Job, ...]


@dataclass(frozen=True)
class Record:
    job: Job
    arrival: F
    start: F
    completion: F
    wait: F
    dispatch: int


def f(text: str | int) -> F:
    """Parse parameters as exact rational numbers."""
    return F(str(text))


def select(ready: list[tuple[Job, F]], policy: str) -> int:
    if policy == "FCFS":
        key = lambda item: (item[1], item[0].input_order)
    elif policy == "SJF":
        key = lambda item: (item[0].service, item[1], item[0].input_order)
    else:
        raise ValueError(f"unknown policy: {policy}")
    return min(range(len(ready)), key=lambda index: key(ready[index]))


def closed_loop(users: tuple[User, ...], policy: str) -> dict[str, Record]:
    """Run a finite closed loop; successor arrival = predecessor completion + think."""
    user_by_name = {user.name: user for user in users}
    future: list[tuple[F, int, str, int]] = []
    for user in users:
        first = user.jobs[0]
        heapq.heappush(future, (F(0), first.input_order, user.name, 0))

    ready: list[tuple[Job, F]] = []
    records: dict[str, Record] = {}
    now = F(0)
    dispatch = 0
    while future or ready:
        if not ready and future[0][0] > now:
            now = future[0][0]
        while future and future[0][0] <= now:
            arrival, _, user_name, step = heapq.heappop(future)
            job = user_by_name[user_name].jobs[step]
            ready.append((job, arrival))

        chosen = select(ready, policy)
        job, arrival = ready.pop(chosen)
        start = now
        completion = start + job.service
        records[job.name] = Record(
            job=job,
            arrival=arrival,
            start=start,
            completion=completion,
            wait=start - arrival,
            dispatch=dispatch,
        )
        dispatch += 1
        now = completion

        user = user_by_name[job.user]
        next_step = job.step + 1
        if next_step < len(user.jobs):
            successor = user.jobs[next_step]
            successor_arrival = completion + user.think
            heapq.heappush(
                future,
                (successor_arrival, successor.input_order, user.name, next_step),
            )
    return records


def fixed_replay(
    jobs: tuple[Job, ...], arrivals: dict[str, F], policy: str
) -> dict[str, Record]:
    """Replay one fixed arrival vector under the requested policy."""
    future = [
        (arrivals[job.name], job.input_order, job)
        for job in jobs
    ]
    heapq.heapify(future)
    ready: list[tuple[Job, F]] = []
    records: dict[str, Record] = {}
    now = F(0)
    dispatch = 0
    while future or ready:
        if not ready and future[0][0] > now:
            now = future[0][0]
        while future and future[0][0] <= now:
            arrival, _, job = heapq.heappop(future)
            ready.append((job, arrival))
        chosen = select(ready, policy)
        job, arrival = ready.pop(chosen)
        start = now
        completion = start + job.service
        records[job.name] = Record(
            job=job,
            arrival=arrival,
            start=start,
            completion=completion,
            wait=start - arrival,
            dispatch=dispatch,
        )
        dispatch += 1
        now = completion
    return records


def ordered_jobs(users: tuple[User, ...]) -> tuple[Job, ...]:
    return tuple(
        sorted(
            (job for user in users for job in user.jobs),
            key=lambda job: job.input_order,
        )
    )


def arrival_map(records: dict[str, Record]) -> dict[str, F]:
    return {name: record.arrival for name, record in records.items()}


def cohort(records: dict[str, Record], horizon: F | None = None) -> tuple[str, ...]:
    names = [
        name
        for name, record in records.items()
        if horizon is None or record.arrival <= horizon
    ]
    return tuple(sorted(names, key=lambda name: records[name].job.input_order))


def mean_wait(records: dict[str, Record], names: tuple[str, ...] | None = None) -> F:
    selected = names if names is not None else cohort(records)
    return sum((records[name].wait for name in selected), F(0)) / len(selected)


def linear_p99(
    records: dict[str, Record], names: tuple[str, ...] | None = None
) -> F:
    """Linearly interpolated sample quantile at q=0.99, computed exactly."""
    selected = names if names is not None else cohort(records)
    waits = sorted(records[name].wait for name in selected)
    if len(waits) == 1:
        return waits[0]
    location = F(99, 100) * (len(waits) - 1)
    lower = location.numerator // location.denominator
    weight = location - lower
    return waits[lower] + weight * (waits[lower + 1] - waits[lower])


def exact(x: F) -> str:
    ratio = str(x.numerator) if x.denominator == 1 else f"{x.numerator}/{x.denominator}"
    return f"{ratio} ({float(x):.6f})"


def assert_successor_rule(users: tuple[User, ...], records: dict[str, Record]) -> None:
    for user in users:
        for predecessor, successor in zip(user.jobs, user.jobs[1:]):
            expected = records[predecessor.name].completion + user.think
            assert records[successor.name].arrival == expected


def assert_record(
    records: dict[str, Record],
    name: str,
    arrival: F,
    start: F,
    completion: F,
    wait: F,
) -> None:
    record = records[name]
    assert (record.arrival, record.start, record.completion, record.wait) == (
        arrival,
        start,
        completion,
        wait,
    )


def emit_schedule(lines: list[str], title: str, records: dict[str, Record]) -> None:
    lines.append(title)
    lines.append("dispatch job  arrival  service  start  completion  wait")
    for record in sorted(records.values(), key=lambda item: item.dispatch):
        lines.append(
            f"{record.dispatch:>8} {record.job.name:<4} "
            f"{exact(record.arrival):>18} {exact(record.job.service):>18} "
            f"{exact(record.start):>18} {exact(record.completion):>18} "
            f"{exact(record.wait):>18}"
        )
    lines.append(
        f"mean_wait={exact(mean_wait(records))}; "
        f"linear_p99_wait={exact(linear_p99(records))}; n={len(records)}"
    )
    lines.append("")


def example_open_loop_overstates(lines: list[str]) -> None:
    """Open-loop mean benefit is 3; closed-loop mean benefit is -1/6."""
    a1 = Job("A1", "A", 0, f(10), 0)
    b1 = Job("B1", "B", 0, f(1), 1)
    b2 = Job("B2", "B", 1, f(1), 2)
    users = (
        User("A", f(0), (a1,)),
        User("B", f("0.5"), (b1, b2)),
    )
    jobs = ordered_jobs(users)

    closed_fcfs = closed_loop(users, "FCFS")
    logged_arrivals = arrival_map(closed_fcfs)
    open_fcfs = fixed_replay(jobs, logged_arrivals, "FCFS")
    open_sjf = fixed_replay(jobs, logged_arrivals, "SJF")
    closed_sjf = closed_loop(users, "SJF")

    assert open_fcfs == closed_fcfs
    assert_successor_rule(users, closed_fcfs)
    assert_successor_rule(users, closed_sjf)
    assert set(open_sjf) == set(closed_sjf) == {"A1", "B1", "B2"}
    assert all(
        DEADLINE_WINDOW_START_SECONDS
        <= min(record.arrival for record in records.values())
        <= max(record.arrival for record in records.values())
        <= DEADLINE_WINDOW_END_SECONDS
        for records in (closed_fcfs, open_sjf, closed_sjf)
    )

    assert_record(closed_fcfs, "A1", f(0), f(0), f(10), f(0))
    assert_record(closed_fcfs, "B1", f(0), f(10), f(11), f(10))
    assert_record(closed_fcfs, "B2", f("11.5"), f("11.5"), f("12.5"), f(0))
    assert_record(open_sjf, "B1", f(0), f(0), f(1), f(0))
    assert_record(open_sjf, "A1", f(0), f(1), f(11), f(1))
    assert_record(open_sjf, "B2", f("11.5"), f("11.5"), f("12.5"), f(0))
    assert_record(closed_sjf, "B1", f(0), f(0), f(1), f(0))
    assert_record(closed_sjf, "A1", f(0), f(1), f(11), f(1))
    assert_record(closed_sjf, "B2", f("1.5"), f(11), f(12), f("9.5"))

    open_gain = mean_wait(open_fcfs) - mean_wait(open_sjf)
    closed_gain = mean_wait(closed_fcfs) - mean_wait(closed_sjf)
    open_p99_gain = linear_p99(open_fcfs) - linear_p99(open_sjf)
    closed_p99_gain = linear_p99(closed_fcfs) - linear_p99(closed_sjf)
    assert mean_wait(open_fcfs) == f(10) / 3
    assert mean_wait(open_sjf) == f(1) / 3
    assert mean_wait(closed_sjf) == f(7) / 2
    assert open_gain == f(3)
    assert closed_gain == -f(1) / 6
    assert open_gain > closed_gain
    assert linear_p99(open_fcfs) == f(49) / 5
    assert linear_p99(open_sjf) == f(49) / 50
    assert linear_p99(closed_sjf) == f(933) / 100
    assert open_p99_gain == f(441) / 50
    assert closed_p99_gain == f(47) / 100
    assert open_p99_gain - closed_p99_gain == f(167) / 20
    assert open_p99_gain > closed_p99_gain

    lines.append("EXAMPLE 1: OPEN-LOOP REPLAY OVERSTATES AND REVERSES THE MEAN BENEFIT")
    lines.append(
        "Parameters (seconds): one non-preemptive model server; A=[10], no successor; "
        "B=[1,1], fixed think_B=1/2 second."
    )
    lines.append("Initial rank at t=0: A1 before B1. The FCFS-induced arrivals are replayed.")
    lines.append("The identical eventual cohort {A1,B1,B2} is used for every comparison.")
    lines.append("All arrivals lie in the common 24-hour window [-86376,24] seconds.")
    lines.append("")
    emit_schedule(lines, "FCFS closed loop (also the fixed-arrival baseline)", closed_fcfs)
    emit_schedule(lines, "SJF on the fixed FCFS arrival vector", open_sjf)
    emit_schedule(lines, "SJF with endogenous successor arrival", closed_sjf)
    lines.append(f"open_loop_mean_gain = {exact(open_gain)}")
    lines.append(f"closed_loop_mean_gain = {exact(closed_gain)}")
    lines.append(f"open_minus_closed = {exact(open_gain - closed_gain)}")
    lines.append("ASSERTION: open_loop_mean_gain > closed_loop_mean_gain and the signs differ.")
    lines.append(f"open_loop_linear_p99_gain = {exact(open_p99_gain)}")
    lines.append(f"closed_loop_linear_p99_gain = {exact(closed_p99_gain)}")
    lines.append(
        f"open_minus_closed_linear_p99 = {exact(open_p99_gain - closed_p99_gain)}"
    )
    lines.append("ASSERTION: open_loop_linear_p99_gain > closed_loop_linear_p99_gain.")
    lines.append("")


def example_open_loop_understates(lines: list[str]) -> None:
    """Open-loop mean benefit is 46/5; closed-loop mean benefit is 279/25."""
    x1 = Job("X1", "X", 0, f(20), 0)
    b1 = Job("B1", "B", 0, f(1), 1)
    c1 = Job("C1", "C", 0, f(3), 2)
    a1 = Job("A1", "A", 0, f(10), 3)
    b2 = Job("B2", "B", 1, f("0.1"), 4)
    users = (
        User("X", f(0), (x1,)),
        User("B", f(2), (b1, b2)),
        User("C", f(0), (c1,)),
        User("A", f(0), (a1,)),
    )
    jobs = ordered_jobs(users)

    closed_fcfs = closed_loop(users, "FCFS")
    logged_arrivals = arrival_map(closed_fcfs)
    open_fcfs = fixed_replay(jobs, logged_arrivals, "FCFS")
    open_sjf = fixed_replay(jobs, logged_arrivals, "SJF")
    closed_sjf = closed_loop(users, "SJF")

    assert open_fcfs == closed_fcfs
    assert_successor_rule(users, closed_fcfs)
    assert_successor_rule(users, closed_sjf)
    assert set(open_sjf) == set(closed_sjf) == {"X1", "B1", "C1", "A1", "B2"}
    assert all(
        DEADLINE_WINDOW_START_SECONDS
        <= min(record.arrival for record in records.values())
        <= max(record.arrival for record in records.values())
        <= DEADLINE_WINDOW_END_SECONDS
        for records in (closed_fcfs, open_sjf, closed_sjf)
    )

    assert_record(closed_fcfs, "X1", f(0), f(0), f(20), f(0))
    assert_record(closed_fcfs, "B1", f(0), f(20), f(21), f(20))
    assert_record(closed_fcfs, "C1", f(0), f(21), f(24), f(21))
    assert_record(closed_fcfs, "A1", f(0), f(24), f(34), f(24))
    assert_record(closed_fcfs, "B2", f(23), f(34), f("34.1"), f(11))

    assert_record(open_sjf, "B1", f(0), f(0), f(1), f(0))
    assert_record(open_sjf, "C1", f(0), f(1), f(4), f(1))
    assert_record(open_sjf, "A1", f(0), f(4), f(14), f(4))
    assert_record(open_sjf, "X1", f(0), f(14), f(34), f(14))
    assert_record(open_sjf, "B2", f(23), f(34), f("34.1"), f(11))

    assert_record(closed_sjf, "B1", f(0), f(0), f(1), f(0))
    assert_record(closed_sjf, "C1", f(0), f(1), f(4), f(1))
    assert_record(closed_sjf, "B2", f(3), f(4), f("4.1"), f(1))
    assert_record(closed_sjf, "A1", f(0), f("4.1"), f("14.1"), f("4.1"))
    assert_record(closed_sjf, "X1", f(0), f("14.1"), f("34.1"), f("14.1"))

    open_gain = mean_wait(open_fcfs) - mean_wait(open_sjf)
    closed_gain = mean_wait(closed_fcfs) - mean_wait(closed_sjf)
    open_p99_gain = linear_p99(open_fcfs) - linear_p99(open_sjf)
    closed_p99_gain = linear_p99(closed_fcfs) - linear_p99(closed_sjf)
    assert mean_wait(closed_fcfs) == f(76) / 5
    assert mean_wait(open_sjf) == f(6)
    assert mean_wait(closed_sjf) == f(101) / 25
    assert open_gain == f(46) / 5
    assert closed_gain == f(279) / 25
    assert closed_gain - open_gain == f(49) / 25
    assert open_gain < closed_gain
    assert linear_p99(open_fcfs) == f(597) / 25
    assert linear_p99(open_sjf) == f(347) / 25
    assert linear_p99(closed_sjf) == f(137) / 10
    assert open_p99_gain == f(10)
    assert closed_p99_gain == f(509) / 50
    assert closed_p99_gain - open_p99_gain == f(9) / 50
    assert open_p99_gain < closed_p99_gain

    lines.append("EXAMPLE 2: OPEN-LOOP REPLAY UNDERSTATES THE MEAN BENEFIT")
    lines.append(
        "Parameters (seconds): one non-preemptive model server; initial rank X1,B1,C1,A1; "
        "services 20,1,3,10; B2 service=1/10; fixed think_B=2."
    )
    lines.append("The same five job identities are averaged under every policy.")
    lines.append("All arrivals lie in the common 24-hour window [-86376,24] seconds.")
    lines.append("")
    emit_schedule(lines, "FCFS closed loop (also the fixed-arrival baseline)", closed_fcfs)
    emit_schedule(lines, "SJF on the fixed FCFS arrival vector", open_sjf)
    emit_schedule(lines, "SJF with endogenous successor arrival", closed_sjf)
    lines.append(f"open_loop_mean_gain = {exact(open_gain)}")
    lines.append(f"closed_loop_mean_gain = {exact(closed_gain)}")
    lines.append(f"closed_minus_open = {exact(closed_gain - open_gain)}")
    lines.append("ASSERTION: open_loop_mean_gain < closed_loop_mean_gain.")
    lines.append(f"open_loop_linear_p99_gain = {exact(open_p99_gain)}")
    lines.append(f"closed_loop_linear_p99_gain = {exact(closed_p99_gain)}")
    lines.append(
        f"closed_minus_open_linear_p99 = {exact(closed_p99_gain - open_p99_gain)}"
    )
    lines.append("ASSERTION: open_loop_linear_p99_gain < closed_loop_linear_p99_gain.")
    lines.append("")

    fcfs_horizon_cohort = cohort(closed_fcfs, HORIZON)
    open_sjf_horizon_cohort = tuple(
        name for name in fcfs_horizon_cohort if open_sjf[name].arrival <= HORIZON
    )
    closed_sjf_horizon_cohort = cohort(closed_sjf, HORIZON)
    open_horizon_gain = mean_wait(open_fcfs, fcfs_horizon_cohort) - mean_wait(
        open_sjf, open_sjf_horizon_cohort
    )
    closed_horizon_gain = mean_wait(closed_fcfs, fcfs_horizon_cohort) - mean_wait(
        closed_sjf, closed_sjf_horizon_cohort
    )
    assert fcfs_horizon_cohort == ("X1", "B1", "C1", "A1")
    assert open_sjf_horizon_cohort == fcfs_horizon_cohort
    assert closed_sjf_horizon_cohort == ("X1", "B1", "C1", "A1", "B2")
    assert mean_wait(open_fcfs, fcfs_horizon_cohort) == f(65) / 4
    assert mean_wait(open_sjf, open_sjf_horizon_cohort) == f(19) / 4
    assert mean_wait(closed_sjf, closed_sjf_horizon_cohort) == f(101) / 25
    assert open_horizon_gain == f(23) / 2
    assert closed_horizon_gain == f(1221) / 100
    assert closed_horizon_gain - open_horizon_gain == f(71) / 100

    lines.append("HORIZON-COHORT VARIANT FOR EXAMPLE 2")
    lines.append(f"Arrival horizon H={exact(HORIZON)}; jobs starting after H remain observed.")
    lines.append(
        f"FCFS/open-loop cohort={fcfs_horizon_cohort}, n={len(fcfs_horizon_cohort)}; "
        f"closed-SJF cohort={closed_sjf_horizon_cohort}, n={len(closed_sjf_horizon_cohort)}."
    )
    lines.append(f"open_loop_horizon_mean_gain = {exact(open_horizon_gain)}")
    lines.append(f"closed_loop_horizon_mean_gain = {exact(closed_horizon_gain)}")
    lines.append(f"closed_minus_open = {exact(closed_horizon_gain - open_horizon_gain)}")
    lines.append(
        "CAUTION: this comparison changes the population as well as the arrival times; "
        "the policy-specific cohort sizes are therefore part of the estimand."
    )
    lines.append("")


def main() -> None:
    wall_start = time.perf_counter()
    cpu_start = time.process_time()
    lines = [
        "Feedback counterexamples: deterministic closed-loop arrivals",
        f"python={platform.python_version()}",
        f"platform={platform.platform()}",
        "policies=FCFS,SJF; servers=1; service=non-preemptive; arithmetic=Fraction",
        "event rule=release every arrival <= current completion, then dispatch",
        "SJF tie break=(service,arrival,input_order); FCFS tie break=(arrival,input_order)",
        "successor rule=predecessor completion + fixed per-user think time",
        "time_unit=second",
        "common 24-hour arrival window=seconds [-86376,24]",
        "p99 definition=linear interpolation at h=(n-1)*0.99",
        "",
    ]
    status = "PASS"
    try:
        example_open_loop_overstates(lines)
        example_open_loop_understates(lines)
        lines.append("ALL EXACT ASSERTIONS PASSED")
    except Exception:
        status = "FAIL"
        lines.append("ASSERTION FAILURE")
        lines.extend(traceback.format_exc().splitlines())
        raise
    finally:
        lines.append(f"status={status}")
        lines.append(f"wall_seconds={time.perf_counter() - wall_start:.9f}")
        lines.append(f"cpu_seconds={time.process_time() - cpu_start:.9f}")
        payload = "\n".join(lines) + "\n"
        output_path = Path(__file__).with_name(OUTPUT_NAME)
        output_path.write_text(payload, encoding="utf-8")
        sys.stdout.write(payload)


if __name__ == "__main__":
    main()
