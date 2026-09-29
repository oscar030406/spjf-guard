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

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from spjf_guard.data.clock import Clock
from spjf_guard.data.events import Prepared, arrival_and_availability, heavy_threshold_and_cuts
from spjf_guard.features.sweep import (
    GROUPS,
    HIST_COLS,
    class_term_scoped,
    column_index,
    design_matrix,
    feature_frame,
    static_design_matrix,
)
from spjf_guard.predict.scores import SCORE_SPECS, ScoreSpec

FIXED_CUTOFFS = "development terms"
REFIT_CUTOFFS = "this target's training rows"


@dataclass(frozen=True)
class ForwardRun:
    """What one rolling-origin pass produced, and what decided each target."""

    scores: dict[str, np.ndarray]
    log: list[dict]


@dataclass
class FrozenM4Models:
    """Original-score models and design rows used by exact visibility refinement."""

    models: dict[str, Any]
    design: np.ndarray
    semester: np.ndarray

    def predict(self, submission_rows: np.ndarray, histories: np.ndarray) -> np.ndarray:
        indices = np.asarray(submission_rows, np.int64)
        if len(indices) != len(histories):
            raise ValueError("submission rows and replacement histories differ in length")
        block = self.design[indices].copy()
        history_start = block.shape[1] - len(HIST_COLS)
        block[:, history_start:] = np.asarray(histories, np.float32)
        out = np.empty(len(indices), np.float64)
        terms = self.semester[indices]
        for term in np.unique(terms):
            selected = np.flatnonzero(terms == term)
            out[selected] = self.models[str(term)].predict(block[selected])
        return out


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
    model = _fit_model(params, train_x, train_y)
    return model.predict(test_x)


def _fit_model(params: dict, train_x, train_y):
    import lightgbm as lgb

    settings = dict(params)
    rounds = settings.pop("n_estimators")
    return lgb.train(settings, lgb.Dataset(train_x, label=train_y), num_boost_round=rounds)


def fit_frozen_m4_models(
    prepared: Prepared,
    static: pd.DataFrame,
    clock: Clock,
    cfg_predictor: dict,
    limit_s: float,
    targets: Sequence[str],
    all_terms: Sequence[str],
    expected_scores: np.ndarray | None = None,
    score_name: str = "spjf_e",
) -> tuple[FrozenM4Models, np.ndarray, np.ndarray, np.ndarray]:
    """Refit the original M4 weights once and verify their stored predictions.

    Returns the frozen models, the authoritative M4 history rows, and the original
    arrival/availability arrays.  The current protocol uses fixed cut-offs for all
    development targets; refusing a target-specific cut-off here prevents refinement
    from silently scoring with a different design than the fitted model.
    """
    arrival, availability = arrival_and_availability(prepared, clock)
    features = feature_frame(prepared, arrival, availability)
    rows = prepared.submission_rows
    design = design_matrix(static, features, arrival[rows])
    columns = column_index(GROUPS["M4"])
    selected_design = np.ascontiguousarray(design[:, columns], np.float32)
    semester = prepared.semester[rows]
    first, order = term_order(prepared.semester, arrival, all_terms)
    available = availability[rows]
    executed = np.minimum(prepared.cost_s[rows], limit_s)
    spec = SCORE_SPECS[score_name]
    label = spec.target_of(executed)
    settings = lgb_parameters(cfg_predictor, spec)
    models: dict[str, Any] = {}
    reproduced = np.full(len(rows), np.nan, np.float64)
    fixed_terms = list(cfg_predictor["fixed_cutoff_terms"])
    core = np.isin(semester, fixed_terms)
    for target in [str(term) for term in order if term in targets]:
        prior = [term for term in order if first[term] < first[target]]
        train = np.isin(semester, prior) & (available < first[target])
        if not train[core].all():
            raise ValueError(
                f"{target} needs target-specific cut-offs; exact refinement requires "
                "the matching frozen target design"
            )
        test = semester == target
        model = _fit_model(settings, selected_design[train], label[train])
        models[target] = model
        reproduced[test] = model.predict(selected_design[test])
        if expected_scores is not None:
            np.testing.assert_array_equal(reproduced[test], expected_scores[test])
        print(f"  frozen M4 {target}: {int(test.sum()):,} scores reproduced", flush=True)
    target_rows = np.isin(semester, list(targets))
    if expected_scores is not None and not np.array_equal(
        reproduced[target_rows],
        np.asarray(expected_scores, np.float64)[target_rows],
        equal_nan=True,
    ):
        delta = np.abs(reproduced[target_rows] - expected_scores[target_rows])
        raise AssertionError(
            "refitted frozen M4 weights do not reproduce the stored original scores; "
            f"{int((delta > 0).sum()):,} rows differ, worst {float(delta.max()):.3e}"
        )
    history = features[list(HIST_COLS)].to_numpy(np.float32)
    return (
        FrozenM4Models(models=models, design=selected_design, semester=semester),
        history,
        arrival,
        availability,
    )


def term_order(semester: np.ndarray, arrival_s: np.ndarray, terms) -> tuple[dict, list]:
    """First arrival per term, and the terms in calendar order of that first arrival."""
    first = {t: float(arrival_s[semester == t].min()) for t in terms}
    return first, sorted(terms, key=lambda t: first[t])


def _history_prepared(prepared, scope: str):
    if scope == "global":
        return prepared
    if scope == "class_term":
        return class_term_scoped(prepared)
    raise ValueError(f"unknown history scope {scope!r}")


def _result_mask(prepared, eligible_only: bool) -> np.ndarray | None:
    if not eligible_only:
        return None
    mask = np.zeros(len(prepared.is_submission), bool)
    mask[prepared.submission_rows] = prepared.simulatable
    return mask


def _feature_design(prepared, static, arrival, availability, group, eligible_only):
    rows = prepared.submission_rows
    if group == "STATIC":
        return static_design_matrix(static, arrival[rows])
    frame = feature_frame(
        prepared,
        arrival,
        availability,
        record_mask=_result_mask(prepared, eligible_only),
    )
    return design_matrix(static, frame, arrival[rows])


def _design_for_target(
    base,
    prepared,
    static,
    clock,
    arrival,
    train_mask,
    events,
    fixed_cutoffs,
    limit_s,
    group,
    history_scope,
    eligible_only,
):
    """The design matrix a target must use, rebuilding the features when the cut-offs
    have to be refit."""
    core = np.isin(prepared.semester[prepared.submission_rows], fixed_cutoffs["terms"])
    if group == "STATIC" or train_mask[core].all():
        return base, fixed_cutoffs["threshold"], fixed_cutoffs["cuts"], FIXED_CUTOFFS
    cost32 = events["exec_time"].to_numpy()[prepared.submission_rows][train_mask]
    threshold, cuts = heavy_threshold_and_cuts(cost32, limit_s)
    refitted = _history_prepared(prepared.with_cutoffs(threshold, cuts), history_scope)
    new_arrival, new_availability = arrival_and_availability(refitted, clock)
    return (
        _feature_design(
            refitted,
            static,
            new_arrival,
            new_availability,
            group,
            eligible_only,
        ),
        threshold,
        cuts,
        REFIT_CUTOFFS,
    )


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
    feature_group="M4",
    history_scope="global",
    eligible_results_only=False,
    progress=None,
) -> ForwardRun:
    """One frozen model per (score, target term).  Returns a score per submission row."""
    history_prepared = _history_prepared(prepared, history_scope)
    arrival, availability = arrival_and_availability(history_prepared, clock)
    rows = prepared.submission_rows
    semester = prepared.semester[rows]
    executed = np.minimum(prepared.cost_s[rows], limit_s)
    base_design = _feature_design(
        history_prepared,
        static,
        arrival,
        availability,
        feature_group,
        eligible_results_only,
    )
    columns = column_index(GROUPS[feature_group])
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
            base_design,
            prepared,
            static,
            clock,
            arrival,
            train,
            events,
            fixed,
            limit_s,
            feature_group,
            history_scope,
            eligible_results_only,
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
                "feature_group": feature_group,
                "history_scope": history_scope,
                "eligible_results_only": eligible_results_only,
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
