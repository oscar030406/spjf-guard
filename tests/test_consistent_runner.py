"""The exact runner keeps bounded workers ordered and reuses their model context."""

from __future__ import annotations

import argparse
import copy
import importlib
import importlib.util
import multiprocessing as mp
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]


def _script():
    spec = importlib.util.spec_from_file_location(
        "run_consistent_visibility_test", ROOT / "scripts/run_consistent_visibility.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeExecutor:
    created: dict[str, Any] = {}

    def __init__(self, *, max_workers, mp_context, initializer, initargs):
        self.created.update(
            max_workers=max_workers,
            start_method=mp_context.get_start_method(),
            initializer=initializer,
            initargs=initargs,
        )

    def __enter__(self):
        return self

    def __exit__(self, *_error):
        return False

    def map(self, function, tasks, *, chunksize):
        self.created.update(function=function, tasks=list(tasks), chunksize=chunksize)
        return [{"task": task} for task in self.created["tasks"]]


def _parallel_arguments():
    args = argparse.Namespace(config=ROOT / "configs" / "main.yaml", workers=2)
    terms = ["2019-1"]
    controls = {"control": np.array([1.0])}
    multiplicities = np.ones((2, 1), np.int64)
    tasks = [(1, 2), (3, 4)]
    return args, terms, controls, multiplicities, tasks


def test_parallel_cells_wires_two_workers_and_preserves_task_order(monkeypatch):
    script = _script()
    _FakeExecutor.created.clear()
    monkeypatch.setattr(script, "ProcessPoolExecutor", _FakeExecutor)
    args, terms, controls, multiplicities, tasks = _parallel_arguments()

    cells, elapsed = script._parallel_cells(
        args, terms, controls, "signature", multiplicities, tasks
    )

    assert [cell["task"] for cell in cells] == tasks
    assert elapsed >= 0.0
    assert _FakeExecutor.created["max_workers"] == 2
    assert _FakeExecutor.created["start_method"] == "spawn"
    assert _FakeExecutor.created["initializer"] is script._initialize_cell_worker
    assert _FakeExecutor.created["function"] is script._worker_cell
    assert _FakeExecutor.created["chunksize"] == 1
    assert _FakeExecutor.created["initargs"][2:] == (
        terms,
        controls,
        "signature",
        multiplicities,
    )


def test_worker_initializer_builds_once_and_reuses_context(monkeypatch):
    script = _script()
    prepared_context = {"marker": object()}
    loaded_config = object()
    prepares = []
    observed_contexts = []
    monkeypatch.setattr(script.cfgmod, "load", lambda path: loaded_config)

    def fake_prepare(cfg, args, terms):
        prepares.append((cfg, args, terms))
        return prepared_context

    def fake_cell(cfg, args, context, controls, overlay, level, multiplicities, signature):
        observed_contexts.append(context)
        return {"costs": [], "task": (overlay, level)}

    monkeypatch.setattr(script, "prepare_context", fake_prepare)
    monkeypatch.setattr(script, "_cell", fake_cell)
    args, terms, controls, multiplicities, _ = _parallel_arguments()
    script._initialize_cell_worker(
        args.config, args, terms, controls, "signature", multiplicities
    )

    first = script._worker_cell((0, 0))
    second = script._worker_cell((0, 1))

    assert len(prepares) == 1
    assert observed_contexts == [prepared_context, prepared_context]
    assert [row["stage"] for row in first["costs"]] == ["worker_frozen_models"]
    assert second["costs"] == []


def test_parallel_cells_propagates_worker_failure(monkeypatch):
    script = _script()

    class FailingExecutor(_FakeExecutor):
        def map(self, function, tasks, *, chunksize):
            raise RuntimeError("worker failed")

    monkeypatch.setattr(script, "ProcessPoolExecutor", FailingExecutor)
    args, terms, controls, multiplicities, tasks = _parallel_arguments()
    with pytest.raises(RuntimeError, match="worker failed"):
        script._parallel_cells(args, terms, controls, "signature", multiplicities, tasks)


def test_spawned_worker_is_importable_and_propagates_initialization_error():
    scripts = str(ROOT / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    script = importlib.import_module("run_consistent_visibility")
    with ProcessPoolExecutor(max_workers=2, mp_context=mp.get_context("spawn")) as executor:
        future = executor.submit(script._worker_cell, (0, 0))
        with pytest.raises(RuntimeError, match="cell worker was not initialized"):
            future.result(timeout=20)


@pytest.mark.parametrize(
    "field",
    [
        "own_class_term_copy_outcome_rule",
        "external_history_clock",
        "same_semester_other_class_history",
        "alternative_sensitivity",
    ],
)
def test_protocol_config_rejects_a_changed_visibility_semantic(field):
    script = _script()
    cfg = script.cfgmod.load(ROOT / "configs" / "main.yaml")
    raw = copy.deepcopy(cfg.raw)
    raw["features"]["exact_visibility"][field] = "changed"
    changed = script.cfgmod.Config(cfg.path, raw)
    with pytest.raises(ValueError, match=field):
        script._assert_protocol_config(changed)


def test_aging_corrected_key_is_built_from_the_absolute_score():
    script = _script()
    trace = script.Trace.from_seconds(
        np.array([10.0, 12.0]),
        np.ones(2),
        scores={"score": np.array([2.0, 4.0])},
    )
    policy = script.aging("score", 0.25)
    actual = script._corrected_effective_score(
        policy,
        trace,
        np.array([1], np.int64),
        np.array([0.0001]),
    )
    np.testing.assert_array_equal(actual, [0.5001])
