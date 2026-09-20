"""The configuration, the selection rule, the bootstrap and the table writers."""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pytest

from spjf_guard import config as cfgmod
from spjf_guard.experiment import bootstrap as bs
from spjf_guard.experiment.metrics import gap_closed, harm, reduction_percent
from spjf_guard.experiment.report import devnum, latex_table
from spjf_guard.experiment.select import Cell, choose, summarise

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "main.yaml"


@pytest.fixture
def cfg(monkeypatch):
    monkeypatch.setenv("SPJF_CACHE_DIR", "/nonexistent/cache")
    monkeypatch.setenv("SPJF_SCORE_PRED", "/nonexistent/pred.parquet")
    return cfgmod.load(CONFIG)


def test_the_configuration_pins_the_split_the_plan_fixes(cfg):
    assert cfg["semesters"]["validation"] == ["2022-1"]
    assert cfg["semesters"]["development_test"] == ["2022-2"]
    assert cfg["semesters"]["sealed_test"] == ["2023-1", "2023-2", "2024-1"]
    assert cfg["features"]["visibility_rule"] == "done_j + delta <= a_i"
    assert cfg["metrics"]["primary"] == "deadline_window_p99_wait"
    assert cfg["bootstrap"]["resamples"] == 2000
    assert cfg.limit_s == 60.0


def test_a_missing_environment_placeholder_is_an_error(tmp_path, monkeypatch):
    """A `${NAME}` that nothing sets fails at load, rather than becoming a bad path.

    The shipped configuration uses none: every path in it is relative to the repository.
    The mechanism stays because a machine may have to point one input elsewhere, so the
    failure is checked on a copy that uses it.
    """
    monkeypatch.delenv("SPJF_NOWHERE", raising=False)
    text = CONFIG.read_text(encoding="utf-8").replace(
        "cache_dir: data/derived/codebench_cache_r4", 'cache_dir: "${SPJF_NOWHERE}"'
    )
    copy = tmp_path / "main.yaml"
    copy.write_text(text, encoding="utf-8")
    with pytest.raises(cfgmod.ConfigError, match="SPJF_NOWHERE"):
        cfgmod.load(copy)


def test_every_path_in_the_shipped_configuration_is_relative(cfg):
    """A path that is absolute, or that points into a temporary directory, would make
    the document describe one machine.  `data_path` anchors them at the repository."""
    for key in ("archive_dir", "raw_parquet_dir", "cache_dir", "overlay_dir", "score_dir"):
        value = str(cfg["data"][key])
        assert not Path(value).is_absolute(), f"data.{key} is absolute"
        assert "$" not in value, f"data.{key} still needs an environment variable"
        assert cfg.data_path(key).is_relative_to(cfg.root)


def test_the_selected_parameters_are_the_validated_ones(cfg):
    """The joint winner per promise, and the three per-family ablation points."""
    assert cfg.selected(300.0) == {
        "family": "capped",
        "b0_base_s": 60.0,
        "eta": 0.5,
        "gam_base_s": 0.0,
    }
    assert cfg.selected(600.0)["b0_base_s"] == 120.0 and cfg.selected(600.0)["eta"] == 0.75
    assert cfg.selected(1200.0)["family"] == "hybrid"
    assert cfg.selected(1200.0)["gam_base_s"] == 16.0
    for promise in (300.0, 600.0, 1200.0):
        for family in ("fixed", "capped", "hybrid"):
            assert cfg.family_best(promise, family) is not None
        assert cfg.family_best(promise, "fixed")["eta"] == 0.0


def test_the_policy_set_carries_the_promise_into_the_budget(cfg):
    policies = {p.name: p for p in cfg.policies(4)}
    assert "Guard(600)" in policies and "Fixed(600)" in policies
    guard = policies["Guard(600)"]
    assert guard.bmax_us == 4 * (600.0 - 2.5 * 60.0) * 1_000_000
    assert guard.eta_k == 0.75 * 4
    assert guard.b0_us == 120.0 * 1_000_000
    assert policies["Skip(600)"].skip_count == 34


def test_a_promise_below_the_floor_is_refused(cfg):
    with pytest.raises(ValueError, match="floor"):
        cfg.policies(4) and __import__("spjf_guard.sim.policy", fromlist=["guard"]).guard(
            100.0, 4, 60.0, 30.0, 0.5, "s"
        )


# --- selection ----------------------------------------------------------------------- #
def _cells(gap_by_config, harm_by_config, promise=600.0, overlays=5, levels=3, family="capped"):
    """Measured cells for a handful of configurations of one family."""
    out = []
    for (b0, eta, gam), gaps in gap_by_config.items():
        for overlay in range(overlays):
            for level in range(levels):
                i = (overlay * levels + level) % len(gaps)
                out.append(
                    Cell(
                        overlay=overlay,
                        level=level,
                        family=family,
                        promise_s=promise,
                        b0_base_s=b0,
                        eta=eta,
                        gam_base_s=gam,
                        gap_closed=gaps[i],
                        harm_s=harm_by_config[(b0, eta, gam)][i],
                        realised_promise_s=promise,
                    )
                )
    return out


def test_the_rule_refuses_a_configuration_that_harms_in_any_cell():
    cells = _cells(
        {(30.0, 0.5, 0.0): [0.9], (120.0, 0.75, 0.0): [0.7]},
        {(30.0, 0.5, 0.0): [301.0], (120.0, 0.75, 0.0): [250.0]},
    )
    summary = summarise(cells)
    assert summary[("capped", 600.0, 30.0, 0.5, 0.0)]["worst_harm_s"] == 301.0
    picked = [c for c in choose(cells) if c.family == "capped"][0]
    assert (picked.b0_base_s, picked.eta) == (120.0, 0.75)
    assert picked.worst_harm_s <= picked.harm_limit_s


def test_the_rule_maximises_the_worst_cell_not_the_mean():
    cells = _cells(
        {(30.0, 0.5, 0.0): [0.95, 0.10], (120.0, 0.75, 0.0): [0.60, 0.60]},
        {(30.0, 0.5, 0.0): [10.0, 10.0], (120.0, 0.75, 0.0): [10.0, 10.0]},
    )
    picked = [c for c in choose(cells) if c.family == "capped"][0]
    assert (picked.b0_base_s, picked.eta) == (120.0, 0.75)
    assert picked.worst_gap_closed == 0.60


def test_the_joint_winner_is_the_best_of_the_three_families():
    """The paper's Guard(G): one rule over all three budget shapes."""
    cells = (
        _cells({(30.0, 0.0, 0.0): [0.40]}, {(30.0, 0.0, 0.0): [10.0]}, family="fixed")
        + _cells({(0.0, 0.0, 16.0): [0.80]}, {(0.0, 0.0, 16.0): [20.0]}, family="hybrid")
        + _cells({(120.0, 0.75, 0.0): [0.60]}, {(120.0, 0.75, 0.0): [10.0]}, family="capped")
    )
    picks = {c.family: c for c in choose(cells)}
    assert picks["fixed"].worst_gap_closed == 0.40
    assert picks["capped"].worst_gap_closed == 0.60
    assert picks["hybrid"].worst_gap_closed == 0.80
    assert picks["joint"].from_family == "hybrid"
    assert picks["joint"].gam_base_s == 16.0


def test_a_fixed_point_is_a_candidate_only_where_its_own_promise_allows():
    """A constant budget promises B0/k + (3 - 2/k)L, which can be less than G."""
    from spjf_guard.experiment.grids import ANY_PROMISE

    cells = [
        Cell(
            overlay=o,
            level=lv,
            family="fixed",
            promise_s=ANY_PROMISE,
            b0_base_s=400.0,
            eta=0.0,
            gam_base_s=0.0,
            gap_closed=0.5,
            harm_s=10.0,
            realised_promise_s=450.0,
        )
        for o in range(5)
        for lv in range(3)
    ] + _cells({(120.0, 0.75, 0.0): [0.30]}, {(120.0, 0.75, 0.0): [10.0]}, promise=300.0)
    picks = {(c.family, c.promise_s): c for c in choose(cells)}
    assert ("fixed", 300.0) not in picks  # 450 s promise is not a candidate at G = 300
    assert picks[("capped", 300.0)].b0_base_s == 120.0


def test_a_configuration_measured_in_fewer_cells_is_an_error():
    cells = _cells({(30.0, 0.5, 0.0): [0.9]}, {(30.0, 0.5, 0.0): [10.0]})
    cells.append(
        Cell(
            overlay=9,
            level=9,
            family="capped",
            promise_s=600.0,
            b0_base_s=120.0,
            eta=0.75,
            gam_base_s=0.0,
            gap_closed=0.5,
            harm_s=10.0,
            realised_promise_s=600.0,
        )
    )
    with pytest.raises(ValueError, match="different numbers of cells"):
        summarise(cells)


def test_the_first_replicate_reproduces_the_observed_sample():
    rng = np.random.default_rng(1)
    values = rng.gamma(2.0, 1.0, size=5000)
    week = rng.integers(0, 30, size=5000)
    multiplicities = bs.with_point_estimate(bs.week_multiplicities(30, resamples=8))
    assert np.isclose(bs.resampled_mean(values, week, multiplicities)[0], values.mean())
    assert np.isclose(
        bs.resampled_quantile(values, week, multiplicities, 0.99)[0], np.quantile(values, 0.99)
    )


def test_the_same_draw_is_reused_so_differences_are_paired():
    first = bs.week_multiplicities(30)
    second = bs.week_multiplicities(30)
    assert np.array_equal(first, second)
    assert first.shape == (bs.DEFAULT_RESAMPLES, 30)
    assert np.all(first.sum(axis=1) == 30)


def test_an_interval_brackets_the_point_estimate():
    rng = np.random.default_rng(3)
    values = rng.gamma(2.0, 1.0, size=20000)
    week = rng.integers(0, 30, size=20000)
    multiplicities = bs.week_multiplicities(30, resamples=200)
    lo, hi = bs.interval(bs.resampled_mean(values, week, multiplicities))
    assert lo < values.mean() < hi


# --- metrics and the table writer ------------------------------------------------------ #
def test_harm_is_measured_among_the_jobs_fcfs_would_not_delay():
    excess = np.array([5.0, 100.0, 2.0])
    fcfs_wait = np.array([0.0, 30.0, 0.5])
    assert harm(excess, fcfs_wait) == 5.0


def test_gap_closed_is_not_a_percentage_reduction():
    assert gap_closed(50.0, 100.0, 25.0) == pytest.approx(2.0 / 3.0)
    assert reduction_percent(50.0, 100.0) == 50.0
    assert np.isnan(gap_closed(50.0, 100.0, 100.0))


def test_every_number_in_a_latex_row_is_wrapped():
    rows = [
        {
            "level": 2,
            "rho_target": 1.0,
            "k": 4.0,
            "policy": "FCFS",
            "p99_dl_s": 273.497387,
            "gap_closed": 0.0,
            "gap_closed_lo": 0.0,
            "gap_closed_hi": 0.0,
            "reduction_pct": 0.0,
            "mean_s": 10.27,
            "max_excess_s": 0.0,
            "harm_s": 0.0,
            "fired_pct": 100.0,
        }
    ]
    text = latex_table(rows, "caption", "tab:x")
    assert r"\devnum{273.50}" in text
    body = [ln for ln in text.splitlines() if ln.startswith(" & ")]
    assert body, "the table has no body rows"
    for line in body:
        free = re.sub(r"\\devnum\{[^}]*\}", "", line)
        assert not re.search(r"\d", free), f"an unwrapped number survives in {free!r}"
    assert devnum(float("nan")) == r"\devnum{---}"
