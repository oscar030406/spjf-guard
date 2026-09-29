"""The rolling-origin protocol, and what each objective estimates."""

from __future__ import annotations

import numpy as np
import pytest

from spjf_guard.predict import SCORE_SPECS, fit_rolling_origin, training_mask
from spjf_guard.predict.scores import first_arrival_by_term

TERMS = ("2020-2", "2021-1", "2021-2", "2022-1")


def toy(seed: int = 4, per_term: int = 1500):
    rng = np.random.default_rng(seed)
    n = per_term * len(TERMS)
    semester = np.repeat(np.array(TERMS), per_term)
    arrival = np.concatenate(
        [np.sort(rng.uniform(i * 1e6, i * 1e6 + 5e5, per_term)) for i in range(len(TERMS))]
    )
    heavy = rng.random(n) < 0.05
    depth = rng.integers(0, 5, n).astype(float)
    loops = rng.integers(0, 3, n).astype(float)
    cost = np.clip(
        np.where(heavy, 20.0 + 5.0 * depth, 0.2 + 0.05 * loops) * rng.lognormal(0.0, 0.3, n),
        0.01,
        60.0,
    )
    features = np.column_stack([depth, loops, heavy.astype(float) * 0 + rng.random(n)])
    availability = arrival + cost
    return features, cost, semester, availability, arrival


def test_a_forward_model_never_trains_on_its_own_term_or_later():
    _, cost, semester, availability, arrival = toy()
    first = first_arrival_by_term(semester, arrival)
    for target in TERMS[1:]:
        mask = training_mask(semester, availability, target, first)
        assert not (semester[mask] == target).any()
        later = [t for t in TERMS if first[t] > first[target]]
        assert not np.isin(semester[mask], later).any()
        assert np.all(availability[mask] < first[target])
    assert cost.shape == semester.shape


def test_a_record_whose_outcome_lands_after_the_origin_is_dropped():
    _, _, semester, availability, arrival = toy()
    first = first_arrival_by_term(semester, arrival)
    target = TERMS[2]
    moved = availability.copy()
    earlier = np.flatnonzero(semester == TERMS[0])
    moved[earlier[:10]] = first[target] + 1.0  # a run that finishes too late
    mask = training_mask(semester, moved, target, first)
    assert not mask[earlier[:10]].any()


def test_the_first_term_cannot_be_a_forward_target():
    _, cost, semester, availability, arrival = toy()
    with pytest.raises(ValueError, match="no term precedes"):
        fit_rolling_origin(
            np.zeros((len(cost), 1)),
            cost,
            semester,
            availability,
            arrival,
            [TERMS[0]],
            SCORE_SPECS["spjf_e"],
            rounds=5,
        )


@pytest.mark.slow
def test_the_expected_cost_score_ranks_at_least_as_well_as_the_log_score():
    """The Tweedie objective estimates a conditional mean; the log objective estimates a
    conditional geometric mean, which sits below it wherever the variance is large."""
    features, cost, semester, availability, arrival = toy()
    targets = list(TERMS[1:])
    scores = {}
    for name in ("spjf_e", "spjf_log"):
        scores[name] = fit_rolling_origin(
            features,
            cost,
            semester,
            availability,
            arrival,
            targets,
            SCORE_SPECS[name],
            rounds=60,
        )
    produced = np.isin(semester, targets)
    for name, value in scores.items():
        assert np.isfinite(value[produced]).all(), name
        assert np.isnan(value[~produced]).all(), name
    heavy = cost > np.quantile(cost, 0.95)
    for name in scores:
        ranked = scores[name][produced]
        assert ranked[heavy[produced]].mean() > ranked[~heavy[produced]].mean()
    mean_estimate = scores["spjf_e"][produced].mean()
    assert abs(mean_estimate - cost[produced].mean()) < cost[produced].mean()
