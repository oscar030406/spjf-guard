"""The corrupted rankings, and the claim they exist to support.

What has to hold is not that the corrupted orders are bad — they are — but that the
guard's per-job bound survives them unchanged, because the bound is a statement about the
wrapper and not about the score.
"""

from __future__ import annotations

import numpy as np
import pytest

from conftest import LIMIT_S, random_trace
from spjf_guard.experiment.adversarial import KINDS, TOP1SHORT, adversarial_scores
from spjf_guard.sim import MICROS, guard_upper_bound, simulate
from spjf_guard.sim.policy import fcfs, guard


def test_the_reversed_ranking_puts_the_longest_job_first():
    service = np.array([1.0, 5.0, 2.0])
    scores = adversarial_scores(service, np.zeros(3), seed=1)
    assert list(np.argsort(scores["reversed"])) == [1, 2, 0]


def test_the_random_ranking_is_a_permutation_of_the_costs_and_is_seeded():
    service = np.linspace(0.1, 10.0, 50)
    first = adversarial_scores(service, np.zeros(50), seed=7)["random"]
    again = adversarial_scores(service, np.zeros(50), seed=7)["random"]
    assert np.array_equal(first, again)
    assert np.array_equal(np.sort(first), np.sort(service))


def test_top1short_calls_exactly_the_longest_one_percent_the_shortest():
    service = np.arange(1000.0)
    base = np.full(1000, 5.0)
    corrupted = adversarial_scores(service, base, seed=3)[TOP1SHORT]
    mislabelled = np.flatnonzero(corrupted < 5.0)
    assert len(mislabelled) == 10
    assert set(mislabelled) == set(range(990, 1000))


@pytest.mark.parametrize("k", (1, 4))
def test_the_guard_keeps_its_bound_under_every_corrupted_ranking(rng, k):
    trace = random_trace(rng, 5000, k, load=1.15)
    service_s = trace.service_us / MICROS
    reference = simulate(trace, fcfs(), k).wait_us
    base = trace.score_for("good")
    scores = adversarial_scores(service_s, base, seed=11)
    from spjf_guard.sim import Trace

    for kind in KINDS:
        corrupted = Trace(
            trace.arrival_us, trace.service_us, {kind: scores[kind]}, trace.limit_s
        )
        policy = guard(600.0, k, LIMIT_S, 120.0 * k / 4, 0.75, kind, name=f"Guard(600) {kind}")
        out = simulate(corrupted, policy, k)
        bound = guard_upper_bound(reference, policy, k, LIMIT_S)
        assert np.all(out.wait_us / MICROS <= bound), kind
