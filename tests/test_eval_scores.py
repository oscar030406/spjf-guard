"""The sealed terms' predictor metrics, on arrays small enough to check by hand.

Everything here is synthetic: no test opens a data file, so the entry point's refusal of
the sealed pool can be tested on a machine that does not have the sealed terms, exactly
as `test_sealed_data.py` tests the loader's.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from spjf_guard.experiment import bootstrap as bs
from spjf_guard.experiment import predictor_metrics as pm

ROOT = Path(__file__).resolve().parents[1]


def _sample(score, heavy, truth=None, prediction=None):
    score = np.asarray(score, np.float64)
    truth = np.zeros(len(score)) if truth is None else np.asarray(truth, np.float64)
    prediction = score if prediction is None else np.asarray(prediction, np.float64)
    return pm.sample(score, np.asarray(heavy, bool), truth, prediction)


def _ones(n: int) -> np.ndarray:
    return np.ones(n, np.float64)


def test_a_perfect_ranking_scores_one_and_a_reversed_one_scores_zero():
    score = [0.1, 0.2, 0.3, 0.4]
    heavy = [False, False, True, True]
    assert pm.auroc(_sample(score, heavy), _ones(4)) == pytest.approx(1.0)
    assert pm.auroc(_sample(score[::-1], heavy), _ones(4)) == pytest.approx(0.0)


def test_auroc_counts_a_tied_pair_as_half():
    # scores 1, 2, 2, 3 with the heavy jobs second and fourth: of the four heavy-light
    # pairs, three are won outright and the fourth, the two twos, is a tie.
    value = pm.auroc(_sample([1.0, 2.0, 2.0, 3.0], [False, True, False, True]), _ones(4))
    assert value == pytest.approx((3.0 + 0.5) / 4.0)


def test_a_constant_score_is_one_big_tie_and_scores_a_half():
    s = _sample([7.0] * 6, [True, False, False, True, False, False])
    assert pm.auroc(s, _ones(6)) == pytest.approx(0.5)
    assert pm.average_precision(s, _ones(6)) == pytest.approx(2.0 / 6.0)
    assert np.isnan(pm.spearman(s, _ones(6)))


def test_auroc_is_undefined_when_one_class_is_missing():
    assert np.isnan(pm.auroc(_sample([1.0, 2.0, 3.0], [False] * 3), _ones(3)))
    assert np.isnan(pm.average_precision(_sample([1.0, 2.0], [False, False]), _ones(2)))


def test_average_precision_of_a_perfect_ranking_is_one():
    s = _sample([0.1, 0.2, 0.9, 1.0], [False, False, True, True])
    assert pm.average_precision(s, _ones(4)) == pytest.approx(1.0)


def test_average_precision_of_a_ranking_with_one_light_job_on_top():
    # order from the top: light, heavy, heavy, light.  Recall 0.5 at precision 1/2,
    # recall 1.0 at precision 2/3.
    s = _sample([0.4, 0.3, 0.2, 0.1], [False, True, True, False])
    assert pm.average_precision(s, _ones(4)) == pytest.approx(0.5 * 0.5 + 0.5 * (2 / 3))


def test_rmse_is_taken_on_the_vectors_it_is_given():
    s = _sample(
        [1.0, 2.0, 3.0], [False, True, False], truth=[1.0, 2.0, 3.0], prediction=[2.0, 2.0, 5.0]
    )
    assert pm.rmse(s, _ones(3)) == pytest.approx(np.sqrt((1.0 + 0.0 + 4.0) / 3.0))


def test_spearman_is_one_on_a_monotone_pair_and_minus_one_on_a_reversed_one():
    truth = [1.0, 2.0, 3.0, 9.0]
    assert pm.spearman(_sample([1.0, 5.0, 6.0, 7.0], [False] * 4, truth), _ones(4)) == (
        pytest.approx(1.0)
    )
    assert pm.spearman(_sample([7.0, 6.0, 5.0, 1.0], [False] * 4, truth), _ones(4)) == (
        pytest.approx(-1.0)
    )


def test_spearman_averages_tied_ranks():
    # the two middle scores tie, so both carry rank 1.5 and the correlation is the
    # Pearson correlation of (0, 1.5, 1.5, 3) against (0, 1, 2, 3)
    x, y = np.array([0.0, 1.5, 1.5, 3.0]), np.array([0.0, 1.0, 2.0, 3.0])
    expected = float(np.corrcoef(x, y)[0, 1])
    s = _sample([1.0, 2.0, 2.0, 3.0], [False] * 4, truth=[1.0, 2.0, 3.0, 4.0])
    assert pm.spearman(s, _ones(4)) == pytest.approx(expected)


def test_a_weight_of_two_is_the_row_counted_twice():
    score = [0.1, 0.2, 0.3, 0.4]
    heavy = [False, True, False, True]
    doubled = _sample(score + score, heavy + heavy, truth=[1.0, 2.0, 3.0, 4.0] * 2)
    once = _sample(score, heavy, truth=[1.0, 2.0, 3.0, 4.0])
    for metric in ("auroc", "average_precision", "rmse_log1p", "spearman"):
        assert pm.evaluate(once, 2.0 * _ones(4))[metric] == pytest.approx(
            pm.evaluate(doubled, _ones(8))[metric]
        )


def test_the_first_replicate_is_the_sample_itself():
    rng = np.random.default_rng(3)
    score = rng.random(40)
    heavy = rng.random(40) < 0.3
    s = _sample(score, heavy, truth=rng.random(40))
    block = np.repeat(np.arange(8), 5)
    draws = bs.with_point_estimate(bs.block_multiplicities(8, resamples=16, seed=11))
    drawn = pm.replicates(s, block, draws)
    for metric, values in drawn.items():
        assert len(values) == 17
        assert values[0] == pytest.approx(pm.evaluate(s, _ones(40))[metric], nan_ok=True)


def test_the_block_draw_is_the_one_the_week_block_bootstrap_uses():
    """One draw, two names: the predictor metrics block by user, the queueing metrics by
    week, and neither invents a second random number stream."""
    assert np.array_equal(
        bs.block_multiplicities(6, resamples=5, seed=7),
        bs.week_multiplicities(6, resamples=5, seed=7),
    )


def test_the_sealed_pool_is_refused_without_a_frozen_lock(tmp_path):
    """The entry point refuses before it opens anything: no cache, no score file."""
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "eval_scores.py"),
            "--pool",
            "sealed",
            "--scores",
            str(tmp_path / "absent_scores.parquet"),
            "--out-dir",
            str(tmp_path / "absent_out"),
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )
    assert result.returncode != 0
    assert "SealedDataError" in result.stderr
    assert "no frozen protocol_lock.json" in result.stderr
    assert not (tmp_path / "absent_out").exists()


def test_the_pinned_output_list_is_its_own_list():
    """`run.sealed_predictor_tables` is checked on its own, never merged into the tables
    of the main run: a merged list would make both commands fail the exact-set check."""
    from spjf_guard import config as cfgmod
    from spjf_guard.experiment import provenance

    cfg = cfgmod.load(ROOT / "configs" / "main.yaml")
    pinned = cfg["run"]["sealed_predictor_tables"]
    assert set(pinned) == {"predictor_metrics.csv", provenance.MANIFEST_NAME}
    assert not set(pinned) & set(cfg["run"]["sealed_tables"]) - {provenance.MANIFEST_NAME}
    assert provenance.pinned_outputs_complaint(pinned, [Path("x/predictor_metrics.csv")]) == ""
    assert provenance.pinned_outputs_complaint(pinned, []) != ""
    assert (
        provenance.pinned_outputs_complaint(
            pinned, [Path("x/predictor_metrics.csv"), Path("x/extra.csv")]
        )
        != ""
    )


def test_visibility_outputs_have_a_separate_exact_pinned_list():
    from spjf_guard import config as cfgmod
    from spjf_guard.experiment import provenance

    cfg = cfgmod.load(ROOT / "configs" / "main.yaml")
    pinned = cfg["run"]["sealed_visibility_tables"]
    expected = {
        "visibility_cells.csv",
        "visibility_comparison.csv",
        "visibility_paired_differences.csv",
        "visibility_exposure.csv",
        "visibility_waits_and_lag.csv",
        provenance.MANIFEST_NAME,
    }
    assert set(pinned) == expected
    produced = [
        Path("sealed_visibility") / name for name in expected if name != "manifest.json"
    ]
    assert provenance.pinned_outputs_complaint(pinned, produced) == ""
    assert provenance.pinned_outputs_complaint(pinned, produced[:-1]) != ""
