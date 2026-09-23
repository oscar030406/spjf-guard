"""Exact, standalone checks for the conditional FCFS transport bound."""

from __future__ import annotations

from fractions import Fraction
from itertools import product
import heapq
import json
from pathlib import Path
import time

import numpy as np


HERE = Path(__file__).resolve().parent
LOG_PATH = HERE / "out_transport_bound_check.txt"
K_VALUES = (1, 2, 3, 4)
ARRIVAL_EPSILON = Fraction(1, 3)
SERVICE_DELTA = Fraction(1, 7)
SJF_H = 60
SJF_EPSILONS = tuple(Fraction(1, 2**power) for power in (1, 4, 8, 12))
RANK_SWAP_ETA = Fraction(1, 1024)


def as_fraction(value: int | Fraction) -> Fraction:
    return value if isinstance(value, Fraction) else Fraction(value)


def maximum_absolute_difference(left, right) -> Fraction:
    assert len(left) == len(right)
    return max((abs(x - y) for x, y in zip(left, right)), default=Fraction(0))


def exact_mean(values) -> Fraction:
    return sum(values, Fraction(0)) / len(values)


def linear_quantile(values, probability: Fraction) -> Fraction:
    ordered = sorted(values)
    h = (len(ordered) - 1) * probability
    lower = h.numerator // h.denominator
    fraction = h - lower
    if lower == len(ordered) - 1:
        return ordered[lower]
    return ordered[lower] + fraction * (ordered[lower + 1] - ordered[lower])


def fcfs_recursion(arrivals, costs, k: int):
    """FCFS starts and waits from the sorted server-availability recursion."""
    arrivals = tuple(map(as_fraction, arrivals))
    costs = tuple(map(as_fraction, costs))
    assert len(arrivals) == len(costs) and 1 <= k
    assert all(x <= y for x, y in zip(arrivals, arrivals[1:]))
    availability = [Fraction(0)] * k
    starts, waits = [], []
    for arrival, cost in zip(arrivals, costs):
        assert cost >= 0
        start = max(arrival, availability[0])
        starts.append(start)
        waits.append(start - arrival)
        availability[0] = start + cost
        availability.sort()
    return tuple(starts), tuple(waits)


def simulate_nonpreemptive(jobs, k: int, policy: str):
    """Small exact event recursion with completions before simultaneous arrivals."""
    assert policy in {"FCFS", "SJF"}
    prepared = []
    for identity, arrival, cost, tie_rank in jobs:
        prepared.append(
            {
                "identity": identity,
                "arrival": as_fraction(arrival),
                "cost": as_fraction(cost),
                "tie_rank": int(tie_rank),
            }
        )
    arrival_order = sorted(
        range(len(prepared)),
        key=lambda index: (prepared[index]["arrival"], prepared[index]["tie_rank"]),
    )
    next_arrival = 0
    waiting = []
    running = []
    idle_servers = k
    event_serial = 0
    starts = {}

    while next_arrival < len(prepared) or waiting or running:
        next_arrival_time = (
            prepared[arrival_order[next_arrival]]["arrival"]
            if next_arrival < len(prepared)
            else None
        )
        next_completion_time = running[0][0] if running else None
        if next_arrival_time is None:
            now = next_completion_time
        elif next_completion_time is None:
            now = next_arrival_time
        else:
            now = min(next_arrival_time, next_completion_time)
        assert now is not None

        while running and running[0][0] == now:
            heapq.heappop(running)
            idle_servers += 1
        while (
            next_arrival < len(prepared)
            and prepared[arrival_order[next_arrival]]["arrival"] == now
        ):
            waiting.append(arrival_order[next_arrival])
            next_arrival += 1

        while idle_servers and waiting:
            if policy == "FCFS":
                chosen = min(
                    waiting,
                    key=lambda index: (
                        prepared[index]["arrival"],
                        prepared[index]["tie_rank"],
                    ),
                )
            else:
                chosen = min(
                    waiting,
                    key=lambda index: (
                        prepared[index]["cost"],
                        prepared[index]["tie_rank"],
                    ),
                )
            waiting.remove(chosen)
            job = prepared[chosen]
            starts[job["identity"]] = now
            event_serial += 1
            heapq.heappush(
                running, (now + job["cost"], event_serial, job["identity"])
            )
            idle_servers -= 1

    waits = {
        job["identity"]: starts[job["identity"]] - job["arrival"]
        for job in prepared
    }
    ranks = tuple(prepared[index]["identity"] for index in arrival_order)
    return starts, waits, ranks


def check_same_order_fcfs():
    base_arrivals = tuple(Fraction(index) for index in range(6))
    costs = tuple(map(Fraction, (4, 1, 3, 2, 5, 1)))
    cases = 0
    tight_wait_differences = {}
    for k in K_VALUES:
        base_starts, base_waits = fcfs_recursion(base_arrivals, costs, k)
        for signs in product((-1, 1), repeat=len(base_arrivals)):
            shifted = tuple(
                arrival + sign * ARRIVAL_EPSILON
                for arrival, sign in zip(base_arrivals, signs)
            )
            assert all(x <= y for x, y in zip(shifted, shifted[1:]))
            starts, waits = fcfs_recursion(shifted, costs, k)
            assert maximum_absolute_difference(base_starts, starts) <= ARRIVAL_EPSILON
            assert maximum_absolute_difference(base_waits, waits) <= 2 * ARRIVAL_EPSILON
            assert abs(exact_mean(base_waits) - exact_mean(waits)) <= 2 * ARRIVAL_EPSILON
            assert abs(
                linear_quantile(base_waits, Fraction(99, 100))
                - linear_quantile(waits, Fraction(99, 100))
            ) <= 2 * ARRIVAL_EPSILON
            cases += 1

        tied = tuple(map(Fraction, (0, 0, 1, 1, 2, 2, 3, 3)))
        shifted_tied = tuple(
            map(Fraction, (Fraction(1, 4), Fraction(1, 4), Fraction(3, 4),
                           Fraction(3, 4), Fraction(9, 4), Fraction(9, 4),
                           Fraction(11, 4), Fraction(11, 4)))
        )
        tied_costs = tuple(map(Fraction, (5, 1, 4, 2, 3, 1, 2, 1)))
        tied_starts, tied_waits = fcfs_recursion(tied, tied_costs, k)
        shifted_starts, shifted_waits = fcfs_recursion(shifted_tied, tied_costs, k)
        tied_epsilon = maximum_absolute_difference(tied, shifted_tied)
        assert tied_epsilon == Fraction(1, 4)
        assert maximum_absolute_difference(tied_starts, shifted_starts) <= tied_epsilon
        assert maximum_absolute_difference(tied_waits, shifted_waits) <= 2 * tied_epsilon
        cases += 1

        blockers = tuple(Fraction(0) for _ in range(k - 1))
        tight_a = blockers + (Fraction(0), Fraction(1))
        tight_b = blockers + (Fraction(1, 4), Fraction(3, 4))
        tight_costs = tuple(Fraction(100) for _ in range(k - 1)) + (
            Fraction(10), Fraction(1)
        )
        _, tight_wait_a = fcfs_recursion(tight_a, tight_costs, k)
        _, tight_wait_b = fcfs_recursion(tight_b, tight_costs, k)
        tight_difference = abs(tight_wait_a[-1] - tight_wait_b[-1])
        assert tight_difference == Fraction(1, 2)
        assert tight_difference == 2 * maximum_absolute_difference(tight_a, tight_b)
        tight_wait_differences[str(k)] = str(tight_difference)
        cases += 1
    return {"cases": cases, "factor_two_tight_wait_difference_by_k": tight_wait_differences}


def check_cost_prefix_bound():
    arrivals = tuple(map(Fraction, (0, 1, 2, 3, 4, 5, 6, 7)))
    shifted_arrivals = tuple(
        arrival + (Fraction(1, 4) if index % 2 == 0 else Fraction(-1, 4))
        for index, arrival in enumerate(arrivals)
    )
    assert all(x <= y for x, y in zip(shifted_arrivals, shifted_arrivals[1:]))
    epsilon = maximum_absolute_difference(arrivals, shifted_arrivals)
    costs = tuple(map(Fraction, (7, 1, 5, 2, 4, 3, 6, 1)))
    cost_changes = tuple(
        SERVICE_DELTA if index % 3 != 1 else -SERVICE_DELTA
        for index in range(len(costs))
    )
    shifted_costs = tuple(cost + change for cost, change in zip(costs, cost_changes))
    d = tuple(abs(change) for change in cost_changes)
    cases = 0
    accumulation = {}
    for k in K_VALUES:
        starts, waits = fcfs_recursion(arrivals, costs, k)
        shifted_starts, shifted_waits = fcfs_recursion(
            shifted_arrivals, shifted_costs, k
        )
        prefix = Fraction(0)
        for index in range(len(arrivals)):
            assert abs(starts[index] - shifted_starts[index]) <= epsilon + prefix
            assert abs(waits[index] - shifted_waits[index]) <= 2 * epsilon + prefix
            prefix += d[index]
        cases += 1

        chain_length = 7
        chain_arrivals = tuple(Fraction(0) for _ in range(k - 1 + chain_length))
        blockers = tuple(Fraction(1000) for _ in range(k - 1))
        chain_costs = blockers + tuple(Fraction(1) for _ in range(chain_length))
        changed_chain_costs = blockers + tuple(
            Fraction(1) + SERVICE_DELTA for _ in range(chain_length)
        )
        chain_starts, _ = fcfs_recursion(chain_arrivals, chain_costs, k)
        changed_chain_starts, _ = fcfs_recursion(
            chain_arrivals, changed_chain_costs, k
        )
        final_difference = abs(chain_starts[-1] - changed_chain_starts[-1])
        assert final_difference == (chain_length - 1) * SERVICE_DELTA
        accumulation[str(k)] = str(final_difference)
        cases += 1
    return {
        "cases": cases,
        "epsilon": str(epsilon),
        "per_service_delta": str(SERVICE_DELTA),
        "six_predecessor_accumulation_by_k": accumulation,
    }


def sjf_jobs(k: int, epsilon: Fraction, early: bool):
    jobs = [
        (f"blocker_{index}", Fraction(0), Fraction(1000), index)
        for index in range(k - 1)
    ]
    jobs.extend(
        [
            ("trigger", Fraction(1), Fraction(1), 100),
            ("long", Fraction(1), Fraction(SJF_H), 101),
            (
                "later_short",
                Fraction(2) - epsilon / 2 if early else Fraction(2) + epsilon / 2,
                Fraction(1),
                102,
            ),
        ]
    )
    return jobs


def check_sjf_discontinuity():
    results = {}
    cases = 0
    for k in K_VALUES:
        gaps = []
        for epsilon in SJF_EPSILONS:
            early_jobs = sjf_jobs(k, epsilon, True)
            late_jobs = sjf_jobs(k, epsilon, False)
            _, early_waits, early_rank = simulate_nonpreemptive(early_jobs, k, "SJF")
            _, late_waits, late_rank = simulate_nonpreemptive(late_jobs, k, "SJF")
            assert early_rank == late_rank
            identity_order = tuple(job[0] for job in early_jobs)
            early_vector = tuple(early_waits[identity] for identity in identity_order)
            late_vector = tuple(late_waits[identity] for identity in identity_order)
            mean_gap = abs(exact_mean(early_vector) - exact_mean(late_vector))
            assert mean_gap == Fraction(SJF_H - 1, k + 2) - epsilon / (k + 2)
            assert abs(
                early_waits["later_short"] - late_waits["later_short"]
            ) == SJF_H - epsilon
            gaps.append(
                {
                    "epsilon": str(epsilon),
                    "mean_wait_gap": str(mean_gap),
                    "later_short_wait_gap": str(SJF_H - epsilon),
                }
            )
            cases += 1
        assert all(
            as_fraction(gaps[index]["mean_wait_gap"])
            < as_fraction(gaps[index + 1]["mean_wait_gap"])
            for index in range(len(gaps) - 1)
        )
        results[str(k)] = gaps
    return {"cases": cases, "H": SJF_H, "by_k": results}


def rank_swap_jobs(k: int, long_first: bool):
    jobs = [
        (f"blocker_{index}", Fraction(0), Fraction(1000), index)
        for index in range(k - 1)
    ]
    if long_first:
        long_arrival, short_arrival = Fraction(1), Fraction(1) + RANK_SWAP_ETA
    else:
        long_arrival, short_arrival = Fraction(1) + RANK_SWAP_ETA, Fraction(1)
    jobs.extend(
        [
            ("long", long_arrival, Fraction(SJF_H), 100),
            ("short", short_arrival, Fraction(1), 101),
        ]
    )
    return jobs


def check_arrival_rank_counterexample():
    results = {}
    for k in K_VALUES:
        jobs_long_first = rank_swap_jobs(k, True)
        jobs_short_first = rank_swap_jobs(k, False)
        _, waits_long_first, rank_long_first = simulate_nonpreemptive(
            jobs_long_first, k, "FCFS"
        )
        _, waits_short_first, rank_short_first = simulate_nonpreemptive(
            jobs_short_first, k, "FCFS"
        )
        assert rank_long_first != rank_short_first
        identity_order = tuple(job[0] for job in jobs_long_first)
        long_first_vector = tuple(waits_long_first[name] for name in identity_order)
        short_first_vector = tuple(waits_short_first[name] for name in identity_order)
        short_wait_gap = abs(waits_long_first["short"] - waits_short_first["short"])
        mean_gap = abs(exact_mean(long_first_vector) - exact_mean(short_first_vector))
        p99_gap = abs(
            linear_quantile(long_first_vector, Fraction(99, 100))
            - linear_quantile(short_first_vector, Fraction(99, 100))
        )
        assert short_wait_gap == SJF_H - RANK_SWAP_ETA
        assert short_wait_gap > 2 * RANK_SWAP_ETA
        assert mean_gap == Fraction(SJF_H - 1, k + 1)
        assert p99_gap > 50
        results[str(k)] = {
            "epsilon": str(RANK_SWAP_ETA),
            "short_wait_gap": str(short_wait_gap),
            "mean_wait_gap": str(mean_gap),
            "p99_gap": str(p99_gap),
        }
    return {"cases": len(K_VALUES), "by_k": results}


def main():
    wall_start = time.perf_counter()
    cpu_start = time.process_time()
    lines = []

    def log(message):
        lines.append(str(message))
        print(message, flush=True)

    status = "FAIL"
    error = None
    checks = {}
    try:
        log("transport-bound exact arithmetic verification")
        log(
            json.dumps(
                {
                    "k_values": K_VALUES,
                    "arrival_epsilon": str(ARRIVAL_EPSILON),
                    "service_delta": str(SERVICE_DELTA),
                    "sjf_H": SJF_H,
                    "sjf_epsilons": [str(value) for value in SJF_EPSILONS],
                    "rank_swap_eta": str(RANK_SWAP_ETA),
                    "arithmetic": "fractions.Fraction and integer event times",
                    "numpy_version_environment_only": np.__version__,
                    "scope": "analytical checks only; no empirical epsilon is estimated",
                },
                indent=2,
            )
        )
        checks["same_order_fcfs"] = check_same_order_fcfs()
        checks["cost_prefix_bound"] = check_cost_prefix_bound()
        checks["sjf_same_rank_discontinuity"] = check_sjf_discontinuity()
        checks["fcfs_rank_swap_counterexample"] = check_arrival_rank_counterexample()
        status = "PASS"
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        result = {
            "status": status,
            "checks": checks,
            "error": error,
            "timing": {
                "wall_s": time.perf_counter() - wall_start,
                "cpu_s": time.process_time() - cpu_start,
            },
        }
        log(json.dumps(result, indent=2))
        LOG_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
