"""The three pre-stated grids: their size, their overlap, and what each point promises.

These tests are the written form of "the grids were stated before any number existed".
If a grid changes, they fail, and the protocol lock's `search_grids` digest changes with
them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from spjf_guard import config as cfgmod
from spjf_guard.experiment import grids

ROOT = Path(__file__).resolve().parents[1]
LIMIT_S = 60.0


@pytest.fixture(scope="module")
def section():
    cfg = cfgmod.load(ROOT / "configs" / "main.yaml", expand_environment=False)
    return cfg["scheduling"]["selection"]["grids"], cfg.promises_s


def test_the_grids_have_the_sizes_the_protocol_states(section):
    definition, promises = section
    points = grids.grid_points(definition, promises)
    counts: dict[str, int] = {}
    for point in points:
        counts[point.family] = counts.get(point.family, 0) + 1
    assert len(grids.fixed_bases(definition["fixed"])) == 39
    assert counts == {"fixed": 39 + len(promises), "capped": 9 * 6 * 3, "hybrid": 3 * 3 * 2 * 3}
    assert len(points) == 258


def test_every_grid_value_scales_with_the_server_count(section):
    definition, promises = section
    point = next(
        p for p in grids.grid_points(definition, promises) if p.name == "CAP-G600-B120-e0.75"
    )
    four = grids.policy_for(point, 4, LIMIT_S, "s", promises)
    eight = grids.policy_for(point, 8, LIMIT_S, "s", promises)
    assert eight.b0_us == 2 * four.b0_us
    assert eight.eta_k == 2 * four.eta_k


def test_a_constant_budget_carries_its_own_promise(section):
    """B0/k + (3 - 2/k)L, which is what decides where a fixed point may compete."""
    definition, promises = section
    point = next(p for p in grids.grid_points(definition, promises) if p.name == "FIX-B120")
    assert grids.realised_promise(point, 4, LIMIT_S) == pytest.approx(120.0 / 4 + 2.5 * 60.0)
    assert grids.realised_promise(point, 8, LIMIT_S) == pytest.approx(
        (120.0 * 8 / 4) / 8 + (3 - 2 / 8) * 60.0
    )


def test_the_families_overlap_where_they_should(section):
    """A capped point at eta = 0 is the fixed policy at the same budget, and the two are
    simulated separately so that the overlap is a check rather than an assumption."""
    definition, promises = section
    points = {p.name: p for p in grids.grid_points(definition, promises)}
    capped = points["CAP-G600-B120-e0"]
    fixed = points["FIX-B120"]
    assert grids.schedule_key(capped, 4, LIMIT_S, promises) != grids.schedule_key(
        fixed, 4, LIMIT_S, promises
    ), "the two are simulated separately: their caps differ"
    left = grids.policy_for(capped, 4, LIMIT_S, "s", promises)
    right = grids.policy_for(fixed, 4, LIMIT_S, "s", promises)
    assert left.b0_us == right.b0_us and left.eta_k == right.eta_k == 0.0


def test_a_budget_at_or_above_the_cap_is_one_schedule(section):
    """Whatever eta and gamma say, a saturated budget is the constant cap."""
    definition, promises = section
    points = {p.name: p for p in grids.grid_points(definition, promises)}
    saturated = [
        grids.schedule_key(points[name], 4, LIMIT_S, promises)
        for name in ("FIXEQ-G300", "CAP-G300-B600-e0.9", "CAP-G300-B600-e0")
    ]
    assert len(set(saturated)) == 1
    assert saturated[0][0] == "saturated"


def test_the_hybrid_grid_is_the_only_one_with_a_queue_term(section):
    definition, promises = section
    for point in grids.grid_points(definition, promises):
        assert (point.gam_base_s > 0.0) == (
            point.family == grids.HYBRID and point.gam_base_s > 0
        )
        if point.family != grids.HYBRID:
            assert point.gam_base_s == 0.0
