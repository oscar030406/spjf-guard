"""What the simulator must satisfy whatever the policy: research plan 7.2, first group."""

from __future__ import annotations

import numpy as np
import pytest

from conftest import LIMIT_S, random_trace
from spjf_guard.sim import Policy, guard, simulate, spjf
from spjf_guard.sim.policy import fcfs, sjf
from spjf_guard.sim.reference import kiefer_wolfowitz, lindley

SERVERS = (1, 2, 3, 4, 7)


@pytest.mark.parametrize("k", SERVERS)
def test_no_negative_waits_and_monotone_clock(rng, k):
    trace = random_trace(rng, 4000, k, load=1.1)
    for policy in (fcfs(), sjf(), spjf("good", "SPJF-E")):
        out = simulate(trace, policy, k)
        assert out.wait_us.min() >= 0, f"{policy.name} produced a negative wait"
        starts = out.start_us[out.dispatch_order]
        assert np.all(np.diff(starts) >= 0), f"{policy.name} ran its clock backwards"
        assert np.array_equal(
            np.sort(out.dispatch_index), np.arange(len(trace), dtype=np.int64)
        )


def test_fcfs_equals_the_lindley_recursion_at_one_server(rng):
    trace = random_trace(rng, 5000, 1, load=0.9)
    out = simulate(trace, fcfs(), 1)
    assert np.array_equal(out.wait_us, lindley(trace.arrival_us, trace.service_us))


@pytest.mark.parametrize("k", (2, 3, 4, 7))
def test_fcfs_equals_the_kiefer_wolfowitz_recursion(rng, k):
    trace = random_trace(rng, 5000, k, load=1.05)
    out = simulate(trace, fcfs(), k)
    assert np.array_equal(out.wait_us, kiefer_wolfowitz(trace.arrival_us, trace.service_us, k))


@pytest.mark.parametrize("k", SERVERS)
def test_zero_budget_is_fcfs_job_for_job(rng, k):
    """B = 0 recovers FCFS: the head always fires, so the base policy never decides."""
    trace = random_trace(rng, 4000, k, load=1.1)
    zero = Policy(
        name="Guard(0)",
        base="score",
        wrapper="work",
        score_key="reversed",
        b0_us=0,
        eta_k=0.0,
        bmax_us=0,
    )
    out = simulate(trace, zero, k)
    reference = simulate(trace, fcfs(), k)
    assert np.array_equal(out.wait_us, reference.wait_us)
    assert np.array_equal(out.dispatch_index, reference.dispatch_index)


@pytest.mark.parametrize("k", (1, 2, 4))
def test_work_is_conserved(rng, k):
    """No server idles while a job waits: every job starts at an instant at which either
    it has just arrived or a server has just freed."""
    trace = random_trace(rng, 2000, k, load=1.2)
    out = simulate(trace, guard(600.0, k, LIMIT_S, 120.0 * k / 4, 0.75, "good"), k)
    completions = set((out.start_us + trace.service_us).tolist())
    arrivals = set(trace.arrival_us.tolist())
    for job in range(len(trace)):
        start = int(out.start_us[job])
        assert start in arrivals or start in completions or start == int(trace.arrival_us[job])


@pytest.mark.parametrize("k", (1, 2, 4))
def test_every_service_time_is_within_the_limit(rng, k):
    trace = random_trace(rng, 500, k)
    assert trace.service_us.max() <= LIMIT_S * 1_000_000
