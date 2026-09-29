"""The guard: what it may read, what it agrees with, and the two per-job bounds."""

from __future__ import annotations

import numpy as np
import pytest

from conftest import LIMIT_S, random_trace
from spjf_guard.sim import (
    MICROS,
    guard_upper_bound,
    identity_residual,
    in_out,
    simulate,
    spjf,
)
from spjf_guard.sim.bounds import identity_slack_us, in_out_quadratic
from spjf_guard.sim.policy import fcfs, fixed, guard, sjf, skip
from spjf_guard.sim.reference import CostOracle, brute_guard

SERVERS = (1, 2, 3, 4)
PROMISES = (300.0, 600.0, 1200.0)


def guarded_policies(k):
    """The reported guard family at every promise, plus the corrupted-score variants."""
    for promise in PROMISES:
        yield guard(promise, k, LIMIT_S, 120.0 * k / 4, 0.75, "good")
        yield fixed(promise, k, LIMIT_S, "good")
        yield fixed(
            promise, k, LIMIT_S, "good", b0_s=120.0 * k / 4, name=f"Fixed-admitted({promise:g})"
        )
        yield skip(promise, k, LIMIT_S, "good")
    yield guard(
        600.0, k, LIMIT_S, 30.0 * k / 4, 0.9, "reversed", name="Guard(600) on a reversed score"
    )
    yield guard(
        600.0, k, LIMIT_S, 30.0 * k / 4, 0.0, "noisy", name="Guard(600) on a random score"
    )


@pytest.mark.parametrize("k", SERVERS)
def test_both_theorem_bounds_hold_for_every_job(rng, k):
    trace = random_trace(rng, 6000, k, load=1.15)
    reference = simulate(trace, fcfs(), k).wait_us
    for policy in guarded_policies(k):
        out = simulate(trace, policy, k)
        bound = guard_upper_bound(reference, policy, k, LIMIT_S)
        excess = (out.wait_us - reference) / MICROS
        assert np.all(out.wait_us / MICROS <= bound), (
            f"{policy.name} at k={k}: worst overshoot "
            f"{float((out.wait_us / MICROS - bound).max()):.6f} s"
        )
        if policy.wrapper == "work" and policy.bmax_us > 0:
            promise = policy.bmax_us / MICROS / k + (3 - 2 / k) * LIMIT_S
            assert excess.max() <= promise + 1e-9


@pytest.mark.parametrize("k", SERVERS)
def test_the_net_overtaking_identity_holds_for_every_job(rng, k):
    trace = random_trace(rng, 4000, k, load=1.15)
    reference = simulate(trace, fcfs(), k).wait_us
    slack = identity_slack_us(k, LIMIT_S)
    policies = [
        sjf(),
        spjf("good", "SPJF-E"),
        spjf("noisy", "SPJF-random"),
        spjf("reversed", "SPJF-reversed"),
        *guarded_policies(k),
    ]
    for policy in policies:
        out = simulate(trace, policy, k)
        work_in, work_out = in_out(trace.service_us, out.dispatch_order)
        residual = identity_residual(out.wait_us, reference, work_in, work_out, k)
        assert np.abs(residual).max() <= slack, (
            f"{policy.name} at k={k}: |residual| reached "
            f"{int(np.abs(residual).max())} us against 2(k-1)L = {slack} us"
        )
        if k == 1:
            assert np.array_equal(residual, np.zeros_like(residual)), (
                f"{policy.name}: the identity is not exact at k = 1"
            )


@pytest.mark.parametrize("k", SERVERS)
def test_the_in_out_sweep_matches_its_definition(rng, k):
    trace = random_trace(rng, 220, k, load=1.2)
    out = simulate(trace, spjf("good", "SPJF-E"), k)
    fast = in_out(trace.service_us, out.dispatch_order)
    slow = in_out_quadratic(trace.service_us, out.dispatch_index)
    assert np.array_equal(fast[0], slow[0])
    assert np.array_equal(fast[1], slow[1])


@pytest.mark.parametrize("k", SERVERS)
def test_the_same_phase_sweep_matches_its_definition(rng, k):
    """The part of In contributed inside one dispatch instant, both ways.

    It is the quantity the degenerate witnesses of the identity are built from, so it is
    worth knowing it is measured and not assumed.  At k = 1 no two jobs can start at the
    same instant, so it is zero everywhere.
    """
    from spjf_guard.sim.bounds import in_same_phase, in_same_phase_quadratic

    trace = random_trace(rng, 220, k, load=1.2)
    out = simulate(trace, spjf("good", "SPJF-E"), k)
    fast, n_phases = in_same_phase(trace.service_us, out.dispatch_order, out.start_us)
    slow = in_same_phase_quadratic(trace.service_us, out.dispatch_index, out.start_us)
    assert np.array_equal(fast, slow)
    assert 0 < n_phases <= len(trace.service_us)
    assert (fast <= in_out(trace.service_us, out.dispatch_order)[0]).all()
    if k == 1:
        assert not fast.any(), "one server dispatches one job per instant"


@pytest.mark.parametrize("k", SERVERS)
def test_the_kernel_agrees_with_the_brute_force_reference(rng, k):
    """Tiny instances, every wrapper, against an O(n^2) transcription of Algorithm 1."""
    for trial in range(12):
        trace = random_trace(np.random.default_rng(700 + trial), 60, k, load=1.3)
        score = trace.score_for("good")
        for policy in guarded_policies(k):
            out = simulate(trace, policy, k)
            wait, dispatch = brute_guard(
                trace.arrival_us,
                trace.service_us,
                trace.score_for(policy.score_key),
                k,
                b0_us=policy.b0_us,
                eta_k=policy.eta_k,
                bmax_us=policy.bmax_us,
                skip_count=policy.skip_count,
            )
            assert np.array_equal(out.wait_us, wait), f"{policy.name}, trial {trial}"
            assert np.array_equal(out.dispatch_index, dispatch)
        assert score is not None


@pytest.mark.parametrize("k", (1, 2, 4))
def test_the_guard_reads_a_true_cost_only_at_a_completion(rng, k):
    """The reference scheduler asks an oracle that records every read against the clock;
    a read before the job completed would make the wrapper unimplementable."""
    trace = random_trace(rng, 300, k, load=1.2)
    policy = guard(600.0, k, LIMIT_S, 120.0 * k / 4, 0.75, "good")
    oracle = CostOracle(trace.service_us)
    brute_guard(
        trace.arrival_us,
        trace.service_us,
        trace.score_for("good"),
        k,
        b0_us=policy.b0_us,
        eta_k=policy.eta_k,
        bmax_us=policy.bmax_us,
        oracle=oracle,
    )
    assert oracle.reads, "the guard charged nothing at all"
    assert oracle.illegal_reads == [], (
        f"{len(oracle.illegal_reads)} service times were read before their job completed"
    )


@pytest.mark.parametrize("k", (2, 4))
def test_a_budget_above_the_base_policys_overtaking_never_fires(rng, k):
    """Consistency: a budget larger than any In_i leaves the base policy untouched."""
    trace = random_trace(rng, 1500, k, load=0.8)
    base = simulate(trace, spjf("good", "SPJF-E"), k)
    work_in, _ = in_out(trace.service_us, base.dispatch_order)
    huge = int(work_in.max()) + 1
    wide = guard(1e9, k, LIMIT_S, huge / MICROS, 0.0, "good", name="Guard(wide)")
    out = simulate(trace, wide, k)
    assert np.array_equal(out.wait_us, base.wait_us)
    assert out.n_forced == 0


QUEUE_TERMS = (1.0, 4.0, 16.0)


@pytest.mark.parametrize("k", SERVERS)
def test_the_queue_length_term_keeps_the_same_per_job_bound(rng, k):
    """The third shape of the budget: B0 + gam * (waiting at arrival) + eta k (t - a_q).

    The guarantee rests on the cap alone, so adding the queue-length term must not move
    the bound: what is asserted here is the same per-job inequality, at the same G.
    """
    trace = random_trace(rng, 6000, k, load=1.15)
    reference = simulate(trace, fcfs(), k).wait_us
    for gam in QUEUE_TERMS:
        for eta in (0.0, 0.9):
            policy = guard(
                600.0,
                k,
                LIMIT_S,
                0.0,
                eta,
                "good",
                name=f"Guard-queue(600) gam={gam:g}",
                gam_s=gam * k / 4,
            )
            out = simulate(trace, policy, k)
            bound = guard_upper_bound(reference, policy, k, LIMIT_S)
            assert np.all(out.wait_us / MICROS <= bound), (
                f"gam={gam} eta={eta} k={k}: worst overshoot "
                f"{float((out.wait_us / MICROS - bound).max()):.6f} s"
            )
            excess = (out.wait_us - reference) / MICROS
            assert excess.max() <= policy.bmax_us / MICROS / k + (3 - 2 / k) * LIMIT_S + 1e-9


@pytest.mark.parametrize("k", SERVERS)
def test_a_zero_queue_term_is_the_capped_relative_policy(rng, k):
    """gam = 0 must leave the schedule exactly as it was, job for job."""
    trace = random_trace(rng, 4000, k, load=1.1)
    without = simulate(trace, guard(600.0, k, LIMIT_S, 30.0 * k / 4, 0.5, "good"), k)
    with_zero = simulate(
        trace, guard(600.0, k, LIMIT_S, 30.0 * k / 4, 0.5, "good", gam_s=0.0), k
    )
    assert np.array_equal(without.wait_us, with_zero.wait_us)
    assert np.array_equal(without.dispatch_order, with_zero.dispatch_order)


@pytest.mark.parametrize("k", (1, 4))
def test_a_queue_term_above_the_cap_is_the_constant_cap_policy(rng, k):
    """Once B0 + gam w reaches the cap the budget is the cap, whatever gamma is.

    This is what makes clipping the constant part inside the kernel safe, and it is the
    boundary the bound assertion relies on: the budget never exceeds B_max.
    """
    from spjf_guard.sim.policy import bmax_for_promise

    trace = random_trace(rng, 4000, k, load=1.1)
    cap = bmax_for_promise(600.0, k, LIMIT_S)
    saturated = simulate(trace, fixed(600.0, k, LIMIT_S, "good"), k)
    huge = simulate(
        trace,
        guard(600.0, k, LIMIT_S, cap, 0.0, "good", name="Guard-queue huge", gam_s=1e6),
        k,
    )
    assert np.array_equal(saturated.wait_us, huge.wait_us)


def test_a_negative_queue_term_is_refused():
    """A negative budget is outside the theorem, so the constructor refuses it."""
    with pytest.raises(ValueError, match=">= 0"):
        from spjf_guard.sim.policy import Policy

        Policy(name="bad", base="score", wrapper="work", b0_us=10, gam_us=-1, bmax_us=100)
    with pytest.raises(ValueError, match="above the cap"):
        from spjf_guard.sim.policy import Policy

        Policy(name="bad", base="score", wrapper="work", b0_us=200, bmax_us=100)
