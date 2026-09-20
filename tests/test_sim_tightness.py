"""The tightness families reproduce the values published for them.

Reference outputs: prechecks/guard_theory/out_sharp_family.txt (identity) and
out_wrapper_tight.txt (wrapper).  One unit of the construction is one microsecond here,
so the simulator runs them exactly.
"""

from __future__ import annotations

from fractions import Fraction

import numpy as np
import pytest

from spjf_guard.sim import Policy, Trace, identity_residual, in_out, simulate
from spjf_guard.sim.policy import fcfs
from spjf_guard.sim.tightness import identity_family, wrapper_family

UNIT_S = 1e-6  # one construction unit is one microsecond
PRIORITY = "priority"


def _trace(instance) -> Trace:
    return Trace(
        instance.arrival,
        instance.service,
        {PRIORITY: instance.priority},
        limit_s=float(instance.service.max()) * UNIT_S,
    )


def _residual_at_victim(instance, k):
    trace = _trace(instance)
    base = Policy(name="static priority", base="score", wrapper="none", score_key=PRIORITY)
    out = simulate(trace, base, k)
    reference = simulate(trace, fcfs(), k)
    work_in, work_out = in_out(trace.service_us, out.dispatch_order)
    residual = identity_residual(out.wait_us, reference.wait_us, work_in, work_out, k)
    return int(residual[instance.victim])


@pytest.mark.parametrize(
    ("k", "limit", "rounds", "direction", "jobs", "expected"),
    [
        (2, 64, 6, "upper", 649, Fraction(127, 64)),
        (2, 64, 6, "lower", 393, Fraction(-127, 64)),
        (2, 64, 5, "upper", 584, Fraction(125, 64)),
        (3, 81, 4, "upper", 822, Fraction(290, 81)),
        (3, 81, 4, "lower", 336, Fraction(-292, 81)),
        (4, 64, 3, "upper", 718, Fraction(303, 64)),
        (4, 64, 3, "lower", 206, Fraction(-303, 64)),
    ],
)
def test_the_identity_family_reaches_its_published_value(
    k, limit, rounds, direction, jobs, expected
):
    instance = identity_family(k, limit, rounds, direction)
    assert len(instance) == jobs
    residual = _residual_at_victim(instance, k)
    assert Fraction(residual, limit) == expected
    assert abs(residual) < 2 * (k - 1) * limit, "the supremum must not be attained"


@pytest.mark.parametrize(
    ("k", "limit", "rounds", "jobs", "budget", "excess", "work_in", "expected"),
    [
        (2, 64, 6, 396, 128, 191, 255, Fraction(127, 32)),
        (2, 128, 7, 909, 256, 383, 511, Fraction(255, 64)),
        (3, 81, 4, 340, 147, 227, 389, Fraction(178, 27)),
        (4, 64, 3, 211, 102, 165, 357, Fraction(279, 32)),
    ],
)
def test_the_wrapper_family_reaches_its_published_constant(
    k, limit, rounds, jobs, budget, excess, work_in, expected
):
    instance = wrapper_family(k, limit, rounds)
    assert len(instance) == jobs
    assert instance.budget == budget
    trace = _trace(instance)
    wrapped = Policy(
        name=f"Guard(B={budget})",
        base="score",
        wrapper="work",
        score_key=PRIORITY,
        b0_us=budget,
        eta_k=0.0,
        bmax_us=0,
    )
    out = simulate(trace, wrapped, k)
    reference = simulate(trace, fcfs(), k)
    victim = instance.victim
    assert int(reference.wait_us[victim]) == 0
    measured = int(out.wait_us[victim] - reference.wait_us[victim])
    assert measured == excess
    assert Fraction(k * measured - budget, limit) == expected
    assert expected < 3 * k - 2, "the supremum must not be attained"
    sweep_in, _ = in_out(trace.service_us, out.dispatch_order)
    assert int(sweep_in[victim]) == work_in
    assert work_in < budget + k * limit, "In_i must stay below budget + kL"


def test_the_wrapper_witness_saturates_both_slacks_together(rng=None):
    """At k = 2, L = 64, m = 6 the identity residual and the kL term are each one unit
    short of their ceilings on the same instance."""
    k, limit, rounds = 2, 64, 6
    instance = wrapper_family(k, limit, rounds)
    trace = _trace(instance)
    wrapped = Policy(
        name="Guard",
        base="score",
        wrapper="work",
        score_key=PRIORITY,
        b0_us=instance.budget,
        eta_k=0.0,
        bmax_us=0,
    )
    out = simulate(trace, wrapped, k)
    reference = simulate(trace, fcfs(), k)
    work_in, work_out = in_out(trace.service_us, out.dispatch_order)
    residual = identity_residual(out.wait_us, reference.wait_us, work_in, work_out, k)
    victim = instance.victim
    assert int(work_out[victim]) == 0
    assert int(residual[victim]) == 2 * (k - 1) * limit - 1
    assert int(work_in[victim]) == instance.budget + k * limit - 1
    assert np.abs(residual).max() <= 2 * (k - 1) * limit
