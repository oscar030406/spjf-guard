"""Frozen-weight controls for the consistent-visibility experiment.

Every control changes history visibility while keeping the original M4 models fixed.
Only finite, simulatable submission rows in the requested pool are rescored; every
other score is copied byte-for-byte from the original score vector.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Protocol

import numpy as np
from numpy.typing import NDArray

from spjf_guard.features.refine import M4HistoryRecomputer
from spjf_guard.features.sweep import HIST_COLS, class_term_scoped, feature_frame

LAGS_S = (60.0, 300.0, 900.0, 3600.0)
CONTROL_VARIANTS = (
    "class_term_local",
    "drop_unreplayed",
    "same_copy_lag_60",
    "same_copy_lag_300",
    "same_copy_lag_900",
    "same_copy_lag_3600",
    "other_class_withheld",
    "combined_frozen",
)
CACHE_SCHEMA = "visibility-controls-v1"

FloatArray = NDArray[np.float64]
HistoryArray = NDArray[np.float32]
Progress = Callable[[str, int, int], None]


class FrozenHistoryModels(Protocol):
    """The prediction surface supplied by ``FrozenM4Models``."""

    def predict(
        self, submission_rows: NDArray[np.int64], histories: HistoryArray
    ) -> FloatArray: ...


@dataclass(frozen=True)
class ControlInputs:
    prepared: Any
    arrival: FloatArray
    availability: FloatArray
    models: FrozenHistoryModels
    baseline_history: HistoryArray
    recomputer: M4HistoryRecomputer
    base_score: FloatArray
    pool_terms: frozenset[str]


@dataclass(frozen=True)
class ControlCost:
    """Deterministic logical work used to produce one control."""

    feature_sweeps: int = 0
    recomputed_rows: int = 0
    predicted_rows: int = 0


@dataclass(frozen=True)
class ControlCacheKey:
    """Content identity of every input that can change a cached control."""

    source_sha256: str
    score_sha256: str
    config_sha256: str
    pool_sha256: str
    implementation_sha256: tuple[tuple[str, str], ...]
    schema: str = CACHE_SCHEMA

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "source_sha256": self.source_sha256,
            "score_sha256": self.score_sha256,
            "config_sha256": self.config_sha256,
            "pool_sha256": self.pool_sha256,
            "implementation_sha256": dict(self.implementation_sha256),
        }


@dataclass(frozen=True)
class ControlBuild:
    scores: dict[str, FloatArray]
    costs: dict[str, ControlCost]
    target_rows: int
    cache_hit: bool = False
    cache_key: ControlCacheKey | None = None

    @property
    def incurred_costs(self) -> dict[str, ControlCost]:
        """Actual work in this call; logical build costs remain in ``costs``."""
        if not self.cache_hit:
            return self.costs
        return {name: ControlCost() for name in self.costs}


class StaleControlCacheError(RuntimeError):
    """A cache exists but was made from different inputs or implementation."""


def _context_value(context: Mapping[str, Any] | object | None, name: str) -> Any:
    if context is None:
        return None
    if isinstance(context, Mapping):
        return context.get(name)
    return getattr(context, name, None)


def _required(value: Any, context: Mapping[str, Any] | object | None, name: str) -> Any:
    selected = value if value is not None else _context_value(context, name)
    if selected is None:
        raise TypeError(f"missing control input {name!r}")
    return selected


def _resolve_inputs(
    context: Mapping[str, Any] | object | None,
    prepared: Any | None,
    arrival: FloatArray | None,
    availability: FloatArray | None,
    models: FrozenHistoryModels | None,
    baseline_history: HistoryArray | None,
    recomputer: M4HistoryRecomputer | None,
    base_score: FloatArray | None,
    pool_terms: Iterable[str] | None,
) -> ControlInputs:
    prepared = _required(prepared, context, "prepared")
    arrival = np.asarray(_required(arrival, context, "arrival"), np.float64)
    availability = np.asarray(_required(availability, context, "availability"), np.float64)
    models = _required(models, context, "models")
    history = np.asarray(_required(baseline_history, context, "baseline_history"), np.float32)
    score = np.asarray(_required(base_score, context, "base_score"), np.float64)
    selected_terms = pool_terms
    if selected_terms is None:
        selected_terms = _required(None, context, "pool_terms")
    terms = frozenset(str(term) for term in selected_terms)
    if not terms:
        raise ValueError("pool_terms must not be empty")
    if recomputer is None:
        recomputer = _context_value(context, "recomputer")
    if recomputer is None:
        recomputer = M4HistoryRecomputer(prepared, arrival, availability)
    inputs = ControlInputs(
        prepared=prepared,
        arrival=arrival,
        availability=availability,
        models=models,
        baseline_history=history,
        recomputer=recomputer,
        base_score=score,
        pool_terms=terms,
    )
    _validate_inputs(inputs)
    return inputs


def _validate_inputs(inputs: ControlInputs) -> None:
    n_events = len(inputs.prepared.is_submission)
    n_submissions = len(inputs.prepared.submission_rows)
    if len(inputs.arrival) != n_events or len(inputs.availability) != n_events:
        raise ValueError("arrival and availability must have one value per event")
    if inputs.baseline_history.shape != (n_submissions, len(HIST_COLS)):
        raise ValueError("baseline_history has the wrong shape")
    if inputs.base_score.shape != (n_submissions,):
        raise ValueError("base_score must have one value per submission")
    if len(inputs.prepared.simulatable) != n_submissions:
        raise ValueError("simulatable must have one value per submission")


def _target_rows(inputs: ControlInputs) -> NDArray[np.int64]:
    events = inputs.prepared.submission_rows
    semesters = np.asarray(inputs.prepared.semester, dtype=object)[events]
    selected = (
        np.isfinite(inputs.base_score)
        & np.asarray(inputs.prepared.simulatable, bool)
        & np.isin(semesters, list(inputs.pool_terms))
    )
    return np.flatnonzero(selected).astype(np.int64, copy=False)


def _replay_mask(inputs: ControlInputs) -> NDArray[np.bool_]:
    prepared = inputs.prepared
    rows = np.asarray(prepared.submission_rows, np.int64)
    mask = np.zeros(len(prepared.is_submission), bool)
    eligible = np.isin(prepared.semester[rows], list(inputs.pool_terms))
    eligible &= np.asarray(prepared.simulatable, bool)
    mask[rows[eligible]] = True
    return mask


def _history(prepared: Any, inputs: ControlInputs, record_mask=None) -> HistoryArray:
    frame = feature_frame(
        prepared,
        inputs.arrival,
        inputs.availability,
        record_mask=record_mask,
    )
    return frame[list(HIST_COLS)].to_numpy(np.float32)


def _predict_batches(
    inputs: ControlInputs,
    scores: FloatArray,
    rows: NDArray[np.int64],
    histories: HistoryArray,
    batch_size: int,
) -> None:
    for start in range(0, len(rows), batch_size):
        stop = min(start + batch_size, len(rows))
        block_rows = rows[start:stop]
        scores[block_rows] = inputs.models.predict(block_rows, histories[start:stop])


def _flush_buffer(
    inputs: ControlInputs,
    scores: FloatArray,
    rows: list[int],
    histories: list[HistoryArray],
) -> int:
    if not rows:
        return 0
    indices = np.asarray(rows, np.int64)
    scores[indices] = inputs.models.predict(indices, np.asarray(histories, np.float32))
    count = len(rows)
    rows.clear()
    histories.clear()
    return count


def _append_history(
    inputs: ControlInputs,
    scores: FloatArray,
    rows: list[int],
    histories: list[HistoryArray],
    target: int,
    history: HistoryArray,
    batch_size: int,
) -> int:
    rows.append(target)
    histories.append(history)
    if len(rows) < batch_size:
        return 0
    return _flush_buffer(inputs, scores, rows, histories)


def _full_sweep_controls(
    inputs: ControlInputs,
    targets: NDArray[np.int64],
    batch_size: int,
) -> tuple[
    dict[str, FloatArray],
    dict[str, ControlCost],
    Any,
    NDArray[np.bool_],
    HistoryArray,
]:
    scores: dict[str, FloatArray] = {}
    costs: dict[str, ControlCost] = {}
    scoped = class_term_scoped(inputs.prepared)
    local_history = _history(scoped, inputs)
    scores["class_term_local"] = inputs.base_score.copy()
    _predict_batches(
        inputs, scores["class_term_local"], targets, local_history[targets], batch_size
    )
    costs["class_term_local"] = ControlCost(1, 0, len(targets))

    replay_mask = _replay_mask(inputs)
    replay_history = _history(inputs.prepared, inputs, replay_mask)
    scores["drop_unreplayed"] = inputs.base_score.copy()
    _predict_batches(
        inputs, scores["drop_unreplayed"], targets, replay_history[targets], batch_size
    )
    costs["drop_unreplayed"] = ControlCost(1, 0, len(targets))

    combined_history = _history(scoped, inputs, replay_mask)
    return scores, costs, scoped, replay_mask, combined_history


def _excluded_recent(
    inputs: ControlInputs,
    target: int,
    candidates: NDArray[np.int64],
    lag_s: float,
) -> NDArray[np.int64]:
    threshold = inputs.recomputer.sub_arrival[target] - lag_s
    available = inputs.recomputer.sub_availability[candidates]
    return candidates[available > threshold]


def _lag_and_combined_controls(
    inputs: ControlInputs,
    targets: NDArray[np.int64],
    scoped: Any,
    replay_mask: NDArray[np.bool_],
    combined_history: HistoryArray,
    batch_size: int,
    progress: Progress | None,
) -> tuple[dict[str, FloatArray], dict[str, ControlCost]]:
    names = {lag: f"same_copy_lag_{int(lag)}" for lag in LAGS_S}
    scores = {name: inputs.base_score.copy() for name in names.values()}
    scores["combined_frozen"] = inputs.base_score.copy()
    rows: dict[float, list[int]] = {lag: [] for lag in LAGS_S}
    histories: dict[float, list[HistoryArray]] = {lag: [] for lag in LAGS_S}
    recomputed = {lag: 0 for lag in LAGS_S}
    predicted = {lag: 0 for lag in LAGS_S}
    combined_rows: list[int] = []
    combined_histories: list[HistoryArray] = []
    combined_recomputed = 0
    combined_predicted = 0
    combined_recomputer = M4HistoryRecomputer(scoped, inputs.arrival, inputs.availability)
    submission_events = inputs.recomputer.submission_events
    for number, raw_target in enumerate(targets, start=1):
        target = int(raw_target)
        sources = inputs.recomputer.same_copy_sources(target)
        if len(sources):
            for lag in LAGS_S:
                history = inputs.recomputer.recompute(
                    target,
                    inputs.baseline_history[target],
                    same_copy_lag_s=lag,
                )
                recomputed[lag] += 1
                if not _history_equal(history, inputs.baseline_history[target]):
                    predicted[lag] += _append_history(
                        inputs,
                        scores[names[lag]],
                        rows[lag],
                        histories[lag],
                        target,
                        history,
                        batch_size,
                    )
        candidates = inputs.recomputer.recent_same_copy_sources(target, 3600.0)
        retained = candidates[replay_mask[submission_events[candidates]]]
        excluded = _excluded_recent(inputs, target, retained, 3600.0)
        history = combined_history[target]
        if len(excluded):
            history = combined_recomputer.recompute(
                target,
                history,
                excluded=set(map(int, excluded)),
                result_mask=replay_mask,
            )
            combined_recomputed += 1
        combined_predicted += _append_history(
            inputs,
            scores["combined_frozen"],
            combined_rows,
            combined_histories,
            target,
            history,
            batch_size,
        )
        if progress is not None and (number % 50000 == 0 or number == len(targets)):
            progress("same_copy_lags", number, len(targets))
    for lag in LAGS_S:
        predicted[lag] += _flush_buffer(inputs, scores[names[lag]], rows[lag], histories[lag])
    combined_predicted += _flush_buffer(
        inputs, scores["combined_frozen"], combined_rows, combined_histories
    )
    costs = {names[lag]: ControlCost(0, recomputed[lag], predicted[lag]) for lag in LAGS_S}
    costs["combined_frozen"] = ControlCost(1, combined_recomputed, combined_predicted)
    return scores, costs


def _history_equal(left: HistoryArray, right: HistoryArray) -> bool:
    return bool(np.array_equal(left, right, equal_nan=True))


def _other_class_control(
    inputs: ControlInputs,
    targets: NDArray[np.int64],
    batch_size: int,
    progress: Progress | None,
) -> tuple[FloatArray, ControlCost]:
    scores = inputs.base_score.copy()
    rows: list[int] = []
    histories: list[HistoryArray] = []
    predicted = 0
    for number, raw_target in enumerate(targets, start=1):
        target = int(raw_target)
        history = inputs.recomputer.recompute(
            target,
            inputs.baseline_history[target],
            withhold_other_pool_classes=True,
            pool_terms=set(inputs.pool_terms),
        )
        if not _history_equal(history, inputs.baseline_history[target]):
            predicted += _append_history(
                inputs, scores, rows, histories, target, history, batch_size
            )
        if progress is not None and (number % 50000 == 0 or number == len(targets)):
            progress("other_class_withheld", number, len(targets))
    predicted += _flush_buffer(inputs, scores, rows, histories)
    return scores, ControlCost(0, len(targets), predicted)


def build_control_set(
    context: Mapping[str, Any] | object | None = None,
    *,
    prepared: Any | None = None,
    arrival: FloatArray | None = None,
    availability: FloatArray | None = None,
    models: FrozenHistoryModels | None = None,
    baseline_history: HistoryArray | None = None,
    recomputer: M4HistoryRecomputer | None = None,
    base_score: FloatArray | None = None,
    pool_terms: Iterable[str] | None = None,
    batch_size: int = 4096,
    progress: Progress | None = None,
) -> ControlBuild:
    """Build all controls without fitting or changing a model."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    inputs = _resolve_inputs(
        context,
        prepared,
        arrival,
        availability,
        models,
        baseline_history,
        recomputer,
        base_score,
        pool_terms,
    )
    targets = _target_rows(inputs)
    scores, costs, scoped, replay_mask, combined_history = _full_sweep_controls(
        inputs, targets, batch_size
    )
    lag_scores, lag_costs = _lag_and_combined_controls(
        inputs,
        targets,
        scoped,
        replay_mask,
        combined_history,
        batch_size,
        progress,
    )
    scores.update(lag_scores)
    costs.update(lag_costs)
    other_score, other_cost = _other_class_control(inputs, targets, batch_size, progress)
    scores["other_class_withheld"] = other_score
    costs["other_class_withheld"] = other_cost
    ordered_scores = {name: scores[name] for name in CONTROL_VARIANTS}
    ordered_costs = {name: costs[name] for name in CONTROL_VARIANTS}
    return ControlBuild(ordered_scores, ordered_costs, len(targets))


def build_controls(
    context: Mapping[str, Any] | object | None = None,
    *,
    prepared: Any | None = None,
    arrival: FloatArray | None = None,
    availability: FloatArray | None = None,
    models: FrozenHistoryModels | None = None,
    baseline_history: HistoryArray | None = None,
    recomputer: M4HistoryRecomputer | None = None,
    base_score: FloatArray | None = None,
    pool_terms: Iterable[str] | None = None,
    batch_size: int = 4096,
    progress: Progress | None = None,
) -> dict[str, FloatArray]:
    """Return the eight frozen-weight score arrays.

    Inputs may be supplied in a runner context (mapping or attribute object), or as
    explicit keyword arguments.  Explicit values take precedence over context values.

    ``class_term_local`` changes only the history namespace. ``drop_unreplayed`` uses
    the replay-eligibility mask for the whole history stream. The four lag controls
    shift only same-class simulatable outcome releases, preserving arrival-known fields
    and release ordering. ``other_class_withheld`` removes both arrivals and outcomes
    of other classes in the target's pool semester. ``combined_frozen`` applies the
    class-term namespace, replay mask, and 3600-second release lag together.
    """
    return build_control_set(
        context,
        prepared=prepared,
        arrival=arrival,
        availability=availability,
        models=models,
        baseline_history=baseline_history,
        recomputer=recomputer,
        base_score=base_score,
        pool_terms=pool_terms,
        batch_size=batch_size,
        progress=progress,
    ).scores


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_json(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _implementation_paths() -> tuple[Path, ...]:
    package = Path(__file__).resolve().parents[1]
    return (
        Path(__file__).resolve(),
        package / "features" / "refine.py",
        package / "features" / "sweep.py",
        package / "predict" / "forward.py",
    )


def cache_key_from_files(
    source_paths: Iterable[Path],
    score_path: Path,
    config_path: Path,
    pool_terms: Iterable[str],
    *,
    implementation_paths: Iterable[Path] | None = None,
) -> ControlCacheKey:
    """Hash allowed development inputs and all score-producing implementation files."""
    terms = sorted({str(term) for term in pool_terms})
    source_hashes = [_sha256_file(Path(path)) for path in source_paths]
    if not source_hashes:
        raise ValueError("source_paths must not be empty")
    paths = tuple(implementation_paths or _implementation_paths())
    package = Path(__file__).resolve().parents[1]
    implementation = []
    for path in paths:
        resolved = Path(path).resolve()
        try:
            name = resolved.relative_to(package).as_posix()
        except ValueError:
            name = resolved.name
        implementation.append((name, _sha256_file(resolved)))
    return ControlCacheKey(
        source_sha256=_sha256_json(source_hashes),
        score_sha256=_sha256_file(Path(score_path)),
        config_sha256=_sha256_file(Path(config_path)),
        pool_sha256=_sha256_json(terms),
        implementation_sha256=tuple(sorted(implementation)),
    )


def _costs_to_json(costs: Mapping[str, ControlCost]) -> dict[str, dict[str, int]]:
    return {
        name: {
            "feature_sweeps": cost.feature_sweeps,
            "recomputed_rows": cost.recomputed_rows,
            "predicted_rows": cost.predicted_rows,
        }
        for name, cost in costs.items()
    }


def _costs_from_json(document: Mapping[str, Mapping[str, int]]) -> dict[str, ControlCost]:
    return {
        name: ControlCost(
            feature_sweeps=int(cost["feature_sweeps"]),
            recomputed_rows=int(cost["recomputed_rows"]),
            predicted_rows=int(cost["predicted_rows"]),
        )
        for name, cost in document.items()
    }


def _score_rows(scores: Mapping[str, FloatArray]) -> int:
    if set(scores) != set(CONTROL_VARIANTS):
        raise ValueError("a control cache must contain exactly the declared variants")
    shapes = {np.asarray(score).shape for score in scores.values()}
    if len(shapes) != 1:
        raise ValueError("control score arrays must all have the same shape")
    shape = next(iter(shapes))
    if len(shape) != 1:
        raise ValueError("each control score must be one-dimensional")
    return int(shape[0])


def save_control_cache(path: Path, key: ControlCacheKey, build: ControlBuild) -> Path:
    """Atomically store arrays with their full content key and logical cost ledger."""
    score_rows = _score_rows(build.scores)
    if set(build.costs) != set(CONTROL_VARIANTS):
        raise ValueError("a control cache needs one cost entry per variant")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "key": key.as_dict(),
        "target_rows": build.target_rows,
        "score_rows": score_rows,
        "costs": _costs_to_json(build.costs),
    }
    temporary = tempfile.NamedTemporaryFile(
        mode="wb", prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, delete=False
    )
    temporary_path = Path(temporary.name)
    try:
        with temporary:
            payload: dict[str, Any] = dict(build.scores)
            payload["__metadata__"] = np.asarray(json.dumps(metadata, sort_keys=True))
            np.savez_compressed(temporary, **payload)
        os.replace(temporary_path, path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise
    return path


def _read_metadata(store: Any, path: Path) -> dict[str, Any]:
    if "__metadata__" not in store.files:
        raise StaleControlCacheError(f"{path} has no visibility-control metadata")
    try:
        return json.loads(str(store["__metadata__"].item()))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise StaleControlCacheError(f"{path} has invalid metadata") from exc


def load_control_cache(path: Path, key: ControlCacheKey) -> ControlBuild | None:
    """Load an exact-key cache; return ``None`` only when no cache exists."""
    path = Path(path)
    if not path.is_file():
        return None
    with np.load(path, allow_pickle=False) as store:
        metadata = _read_metadata(store, path)
        if metadata.get("key") != key.as_dict():
            raise StaleControlCacheError(f"{path} was built from a different cache key")
        missing = [name for name in CONTROL_VARIANTS if name not in store.files]
        if missing:
            raise StaleControlCacheError(f"{path} is missing controls {missing}")
        scores = {name: np.asarray(store[name], np.float64).copy() for name in CONTROL_VARIANTS}
    try:
        score_rows = _score_rows(scores)
        costs = _costs_from_json(metadata["costs"])
    except (KeyError, TypeError, ValueError) as exc:
        raise StaleControlCacheError(f"{path} has invalid cache contents") from exc
    if score_rows != int(metadata.get("score_rows", -1)):
        raise StaleControlCacheError(f"{path} has the wrong score-array length")
    if set(costs) != set(CONTROL_VARIANTS):
        raise StaleControlCacheError(f"{path} has an incomplete cost ledger")
    return ControlBuild(
        scores=scores,
        costs=costs,
        target_rows=int(metadata["target_rows"]),
        cache_hit=True,
        cache_key=key,
    )


def load_or_build_controls(
    path: Path,
    key: ControlCacheKey,
    builder: Callable[[], ControlBuild],
    *,
    rebuild_stale: bool = False,
) -> ControlBuild:
    """Reuse an exact cache or build it; stale reuse is never permitted."""
    try:
        cached = load_control_cache(path, key)
    except StaleControlCacheError:
        if not rebuild_stale:
            raise
        cached = None
    if cached is not None:
        return cached
    build = replace(builder(), cache_hit=False, cache_key=key)
    save_control_cache(path, key, build)
    return build
