"""Rolling-origin scores, with the feature cut-offs refit per target.

For each target term, train only on the terms whose first arrival precedes the target's,
and drop every training record whose result would not have been readable by then.  The
heavy cut-off and the user-slowness terciles live *inside* the features (the heavy-rate
and similar-user columns), so when the fixed development cut-offs would have been
computed partly from the target's own rows, they are refit on the target's training rows
and every feature is rebuilt with them.  The heavy label used for evaluation stays the
fixed development p95.

Only the induced order of a score reaches the scheduler, never its level.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from spjf_guard.data.events import arrival_and_availability, heavy_threshold_and_cuts
from spjf_guard.features.sweep import GROUPS, column_index, design_matrix, feature_frame
from spjf_guard.predict.scores import SCORE_SPECS, ScoreSpec

FIXED_CUTOFFS = "development terms"
REFIT_CUTOFFS = "this target's training rows"


@dataclass(frozen=True)
class ForwardRun:
    """What one rolling-origin pass produced, and what decided each target."""

    scores: dict[str, np.ndarray]
    log: list[dict]


def lgb_parameters(cfg_predictor: dict, spec: ScoreSpec) -> dict:
    """Everything LightGBM is given, with determinism pinned.

    `deterministic` plus `force_row_wise` plus a fixed thread count is what makes two
    runs on one machine produce identical trees; without the thread count fixed, the
    histogram reduction order changes and the last digits move.
    """
    params = {
        "objective": spec.objective,
        "n_estimators": int(cfg_predictor.get("n_estimators", 300)),
        "learning_rate": float(cfg_predictor.get("learning_rate", 0.06)),
        "num_leaves": int(cfg_predictor.get("num_leaves", 63)),
        "min_child_samples": int(cfg_predictor.get("min_child_samples", 50)),
        "colsample_bytree": float(cfg_predictor.get("colsample_bytree", 1.0)),
        "subsample": float(cfg_predictor.get("subsample", 0.8)),
        "subsample_freq": int(cfg_predictor.get("subsample_freq", 1)),
        "seed": int(cfg_predictor["seed"]),
        "random_state": int(cfg_predictor["seed"]),
        "num_threads": int(cfg_predictor["num_threads"]),
        "deterministic": True,
        "force_row_wise": True,
        "verbose": -1,
    }
    params.update(spec.params)
    return params


def _fit_predict(params: dict, train_x, train_y, test_x):
    import lightgbm as lgb

    settings = dict(params)
    rounds = settings.pop("n_estimators")
    model = lgb.train(settings, lgb.Dataset(train_x, label=train_y), num_boost_round=rounds)
    return model.predict(test_x)


def term_order(semester: np.ndarray, arrival_s: np.ndarray, terms) -> tuple[dict, list]:
    """First arrival per term, and the terms in calendar order of that first arrival."""
    first = {t: float(arrival_s[semester == t].min()) for t in terms}
    return first, sorted(terms, key=lambda t: first[t])


def _design_for_target(
    base, prepared, static, clock, arrival, train_mask, events, fixed_cutoffs, limit_s
):
    """The design matrix a target must use, rebuilding the features when the cut-offs
    have to be refit."""
    core = np.isin(prepared.semester[prepared.submission_rows], fixed_cutoffs["terms"])
    if train_mask[core].all():
        return base, fixed_cutoffs["threshold"], fixed_cutoffs["cuts"], FIXED_CUTOFFS
    cost32 = events["exec_time"].to_numpy()[prepared.submission_rows][train_mask]
    threshold, cuts = heavy_threshold_and_cuts(cost32, limit_s)
    refitted = prepared.with_cutoffs(threshold, cuts)
    new_arrival, new_availability = arrival_and_availability(refitted, clock)
    frame = feature_frame(refitted, new_arrival, new_availability)
    rows = prepared.submission_rows
    return (design_matrix(static, frame, arrival[rows]), threshold, cuts, REFIT_CUTOFFS)


def fit_forward(
    prepared,
    static,
    events,
    clock,
    cfg_predictor: dict,
    limit_s: float,
    targets,
    all_terms,
    score_names=("spjf_e", "spjf_log"),
    progress=None,
) -> ForwardRun:
    """One frozen model per (score, target term).  Returns a score per submission row."""
    arrival, availability = arrival_and_availability(prepared, clock)
    rows = prepared.submission_rows
    semester = prepared.semester[rows]
    executed = np.minimum(prepared.cost_s[rows], limit_s)
    base_features = feature_frame(prepared, arrival, availability)
    base_design = design_matrix(static, base_features, arrival[rows])
    columns = column_index(GROUPS["M4"])
    first, order = term_order(prepared.semester, arrival, all_terms)
    available = availability[rows]
    fixed = {
        "terms": list(cfg_predictor["fixed_cutoff_terms"]),
        "threshold": prepared.heavy_threshold,
        "cuts": prepared.tercile_cuts,
    }
    out = {name: np.full(len(rows), np.nan) for name in score_names}
    log = []
    for target in [t for t in order if t in targets]:
        prior = [t for t in order if first[t] < first[target]]
        if not prior:
            raise ValueError(f"no term precedes {target!r}; it cannot be a forward target")
        train = np.isin(semester, prior) & (available < first[target])
        test = semester == target
        design, threshold, cuts, source = _design_for_target(
            base_design, prepared, static, clock, arrival, train, events, fixed, limit_s
        )
        train_x = design[np.ix_(train, columns)]
        test_x = design[np.ix_(test, columns)]
        for name in score_names:
            spec = SCORE_SPECS[name]
            label = spec.target_of(executed)
            out[name][test] = _fit_predict(
                lgb_parameters(cfg_predictor, spec), train_x, label[train], test_x
            )
        log.append(
            {
                "target": target,
                "train_terms": f"{prior[0]}..{prior[-1]}",
                "n_train": int(train.sum()),
                "n_target": int(test.sum()),
                "cutoff_source": source,
                "heavy_threshold_s": round(threshold, 6),
                "tercile_low": round(cuts[0], 6),
                "tercile_high": round(cuts[1], 6),
            }
        )
        if progress is not None:
            progress(log[-1])
        del design, train_x, test_x
    return ForwardRun(scores=out, log=log)


def to_frame(run: ForwardRun) -> pd.DataFrame:
    return pd.DataFrame(run.scores)
