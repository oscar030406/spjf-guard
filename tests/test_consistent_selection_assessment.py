"""The timing sample is fixed, balanced by candidate family, and never selects parameters."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from spjf_guard import config

ROOT = Path(__file__).resolve().parents[1]


def _script():
    spec = importlib.util.spec_from_file_location(
        "assess_consistent_selection", ROOT / "scripts/assess_consistent_selection.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_timing_sample_is_deterministic_and_covers_every_grid_point_in_its_weights():
    script = _script()
    cfg = config.load(ROOT / "configs/main.yaml")
    first = script.timing_plan(cfg)
    assert first == script.timing_plan(cfg)
    assert len(first) == 12
    assert sum(row["stratum_size"] for row in first) == 258 + 11
    assert {row["point"]["family"] for row in first} == {"fixed", "capped", "hybrid", "aging"}
    assert all(0 <= row["overlay"] < 5 and 0 <= row["level"] < 3 for row in first)


def test_cost_projection_does_not_change_or_select_parameters():
    script = _script()
    cfg = config.load(ROOT / "configs/main.yaml")
    rows = [
        {**row, "family": row["point"]["family"], "seconds": 120.0}
        for row in script.timing_plan(cfg)
    ]
    result = script._projection(cfg, rows)
    assert result["optimistic_deduplicated_two_worker_hours"] == 63.5
    assert not result["parameters_changed_by_this_assessment"]
    assert not result["full_reselection_fits"]


def test_the_declared_seed_and_budget_are_read_from_the_config():
    script = _script()
    cfg = config.load(ROOT / "configs/main.yaml")
    original = script.timing_plan(cfg)
    settings = cfg.raw["features"]["exact_visibility"]
    settings["selection_cost_seed"] = 4001
    assert script.timing_plan(cfg) != original
    settings["reselection_budget_hours"] = 2.0
    rows = [{**row, "family": row["point"]["family"], "seconds": 120.0} for row in original]
    assert script._projection(cfg, rows)["budget_hours"] == 2.0
