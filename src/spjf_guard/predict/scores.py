"""The ranking score, fitted forward.

Service is non-preemptive, so a dispatched job holds its server for its whole service
time and the delay it imposes on the queue behind it is `C_i` itself, not a monotone
transform of it.  Waiting times add in the units service is measured in, so the score has
to estimate the conditional mean E[C | x].  Squared error on log(1+C) estimates a
conditional geometric mean instead, and the two differ by a term that grows with the
conditional variance, which is exactly where the few heavy jobs sit.  SPJF-E therefore
changes the objective and nothing else: same features, same model size, same protocol,
target in raw seconds under a Tweedie loss of power 1.5.

Rolling origin: for each target term, train only on the terms whose first arrival
precedes the target's, and drop every training record whose outcome would not have been
readable by then.  Only the induced order of the score is used, never its level.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

LOG_SCORE = "spjf_log"
EXPECTED_COST_SCORE = "spjf_e"


@dataclass(frozen=True)
class ScoreSpec:
    """One objective, and what it is fitted on."""

    name: str
    objective: str
    target: str  # "c_cap_seconds" or "log1p_c_cap"
    params: dict = field(default_factory=dict)

    def target_of(self, cost_s: np.ndarray) -> np.ndarray:
        if self.target == "c_cap_seconds":
            return cost_s
        if self.target == "log1p_c_cap":
            return np.log1p(cost_s)
        raise ValueError(f"unknown target {self.target!r}")


SCORE_SPECS = {
    EXPECTED_COST_SCORE: ScoreSpec(
        EXPECTED_COST_SCORE, "tweedie", "c_cap_seconds", {"tweedie_variance_power": 1.5}
    ),
    LOG_SCORE: ScoreSpec(LOG_SCORE, "regression", "log1p_c_cap", {}),
}

DEFAULT_LGB_PARAMS = {
    "learning_rate": 0.05,
    "num_leaves": 63,
    "min_data_in_leaf": 50,
    "feature_fraction": 0.9,
    "bagging_fraction": 0.9,
    "bagging_freq": 1,
    "verbose": -1,
}
DEFAULT_ROUNDS = 400


def first_arrival_by_term(semester: np.ndarray, arrival_s: np.ndarray) -> dict:
    """The instant each term's first job arrives; the rolling origin orders terms by it."""
    out: dict[str, float] = {}
    for term in np.unique(semester):
        out[str(term)] = float(arrival_s[semester == term].min())
    return out


def training_mask(
    semester: np.ndarray, availability_s: np.ndarray, target: str, first_arrival: dict
) -> np.ndarray:
    """Rows a forward model for `target` may train on.

    A row qualifies when its term starts before the target's and its own outcome was
    readable before the target's first job arrived.  Both conditions are needed: the
    second is what stops a long run in an earlier term from leaking across the boundary.
    """
    if target not in first_arrival:
        raise KeyError(f"{target!r} has no first arrival; it is not in the data")
    origin = first_arrival[target]
    earlier = np.isin(semester, [t for t, s in first_arrival.items() if s < origin])
    return earlier & (np.asarray(availability_s, np.float64) < origin)


def fit_rolling_origin(
    features: np.ndarray,
    cost_s: np.ndarray,
    semester: np.ndarray,
    availability_s: np.ndarray,
    arrival_s: np.ndarray,
    targets,
    spec: ScoreSpec,
    seed: int = 3,
    num_threads: int = 4,
    params: dict | None = None,
    rounds: int = DEFAULT_ROUNDS,
    progress=None,
) -> np.ndarray:
    """One frozen model per target term; returns the score for every row of a target.

    Rows outside every target term keep `nan`, so a caller cannot use a score that was
    never produced forward.
    """
    import lightgbm as lgb

    first_arrival = first_arrival_by_term(semester, arrival_s)
    out = np.full(len(cost_s), np.nan, np.float64)
    settings: dict = dict(DEFAULT_LGB_PARAMS)
    settings.update(params or {})
    settings.update(spec.params)
    settings.update(
        {
            "objective": spec.objective,
            "seed": seed,
            "random_state": seed,
            "num_threads": num_threads,
            "deterministic": True,
            "force_row_wise": True,
        }
    )
    label = spec.target_of(cost_s)
    for target in targets:
        train = training_mask(semester, availability_s, target, first_arrival)
        test = semester == target
        if not train.any():
            raise ValueError(f"no term precedes {target!r}; it cannot be a forward target")
        model = lgb.train(
            settings, lgb.Dataset(features[train], label=label[train]), num_boost_round=rounds
        )
        out[test] = model.predict(features[test])
        if progress is not None:
            progress(target, int(train.sum()), int(test.sum()))
    return out
