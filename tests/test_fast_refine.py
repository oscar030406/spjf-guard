"""scripts/fast_refine.py keeps the reference's float bits in the two places where a
compiled rewrite most easily drifts: numpy's pairwise mean and the rolling summary."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import fast_refine as fr  # noqa: E402
from spjf_guard.features import refine  # noqa: E402


def _bits(x):
    return np.asarray(x, np.float64).view(np.uint64)


def test_the_mean_is_numpys_pairwise_sum_bit_for_bit():
    rng = np.random.default_rng(7)
    for n in [*range(1, 140), 255, 256, 257, 4634, 13868]:
        for scale in (1e-3, 1.0, 1e3):
            a = rng.standard_normal(n) * scale + 5.0
            assert _bits(fr._mean(a)) == _bits(a.mean()), n


def test_the_summary_matches_the_reference_on_awkward_histories():
    rng = np.random.default_rng(11)
    cases = [np.empty(0), np.full(7, 2.5), np.zeros(130), np.array([-0.0, 0.0, -0.0])]
    cases += [np.round(rng.gamma(2.0, 1.0, n), 3) for n in (1, 119, 120, 121, 500, 4634)]
    for values in cases:
        errors = (rng.random(len(values)) < 0.3).astype(np.float64)
        heavy = (rng.random(len(values)) < 0.1).astype(np.float64)
        want = refine._summary(values, errors, heavy)
        out = np.zeros(8)
        fr._summary(values, errors, heavy, out, 1)
        assert np.array_equal(_bits(out[1:7]), _bits(want)), len(values)
