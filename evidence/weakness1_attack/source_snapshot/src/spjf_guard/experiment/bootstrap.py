"""Paired week-block bootstrap of the queueing metrics.

Class-terms sharing a pool of servers are not independent samples, so intervals come from
resampling whole weeks of the overlay timeline with replacement.  One draw of week
multiplicities is used for every policy, every load level and every overlay, which is
what makes differences paired.

The quantile of a pooled resample is computed exactly rather than by materialising the
resample: the values are sorted once and cut into position blocks, block counts per
resample locate the block holding the order statistic wanted, and a weighted scan inside
that block finds it.  numpy's default 'linear' interpolation is reproduced exactly.
"""

from __future__ import annotations

import numpy as np

DEFAULT_RESAMPLES = 2000
DEFAULT_SEED = 20260919
_BLOCKS = 4000


def block_multiplicities(
    n_blocks: int, resamples: int = DEFAULT_RESAMPLES, seed: int = DEFAULT_SEED
) -> np.ndarray:
    """M[b, j] = how often block j appears in resample b, for whatever a block is.

    A whole week of the overlay timeline for the queueing metrics, a user for the
    predictor metrics: the unit differs because what is not independent differs, the
    draw does not.
    """
    rng = np.random.default_rng(seed)
    return rng.multinomial(n_blocks, np.full(n_blocks, 1.0 / n_blocks), size=resamples)


def week_multiplicities(
    n_weeks: int, resamples: int = DEFAULT_RESAMPLES, seed: int = DEFAULT_SEED
) -> np.ndarray:
    """M[b, w] = how often week w appears in resample b.  The same draw for every policy."""
    return block_multiplicities(n_weeks, resamples, seed)


def with_point_estimate(multiplicities: np.ndarray) -> np.ndarray:
    """Row 0 reproduces the observed sample, so the point estimate is checked in place."""
    ones = np.ones((1, multiplicities.shape[1]), np.int64)
    return np.vstack([ones, multiplicities])


def resampled_mean(values: np.ndarray, week: np.ndarray, multiplicities: np.ndarray):
    """Mean of the pooled resample, per resample."""
    n_weeks = multiplicities.shape[1]
    total = np.bincount(week, weights=values, minlength=n_weeks)
    count = np.bincount(week, minlength=n_weeks).astype(float)
    return (multiplicities @ total) / (multiplicities @ count)


def _lerp(a, b, t):
    """numpy's quantile interpolation, reproduced."""
    d = b - a
    return b - d * (1.0 - t) if t >= 0.5 else a + d * t


def _order_statistic(sorted_values, sorted_week, edges, cumulative, weights, rank):
    block = int(np.searchsorted(cumulative, rank, side="right"))
    before = cumulative[block - 1] if block > 0 else 0.0
    lo, hi = edges[block], edges[block + 1]
    inside = np.cumsum(weights[sorted_week[lo:hi]])
    return sorted_values[lo + int(np.searchsorted(inside, rank - before, side="right"))]


def resampled_quantile(
    values: np.ndarray,
    week: np.ndarray,
    multiplicities: np.ndarray,
    q: float,
    blocks: int = _BLOCKS,
) -> np.ndarray:
    """q-quantile of each pooled resample, exactly, without materialising it."""
    n_resamples, n_weeks = multiplicities.shape
    order = np.argsort(values, kind="stable")
    sorted_values, sorted_week = values[order], week[order]
    n = len(sorted_values)
    edges = np.unique(np.linspace(0, n, min(blocks, n) + 1).astype(np.int64))
    n_blocks = len(edges) - 1
    block_of = np.repeat(np.arange(n_blocks), np.diff(edges))
    per_week = np.bincount(
        sorted_week * n_blocks + block_of, minlength=n_weeks * n_blocks
    ).reshape(n_weeks, n_blocks)
    cumulative = np.cumsum(multiplicities.astype(float) @ per_week.astype(float), axis=1)
    sizes = cumulative[:, -1]
    out = np.full(n_resamples, np.nan)
    for b in range(n_resamples):
        size = int(sizes[b])
        if size == 0:
            continue
        virtual = (size - 1) * q
        lower = min(max(int(np.floor(virtual)), 0), size - 1)
        upper = min(lower + 1, size - 1)
        left = _order_statistic(
            sorted_values, sorted_week, edges, cumulative[b], multiplicities[b], lower
        )
        right = _order_statistic(
            sorted_values, sorted_week, edges, cumulative[b], multiplicities[b], upper
        )
        out[b] = _lerp(left, right, virtual - lower)
    return out


def interval(replicates: np.ndarray, level: float = 0.95) -> tuple[float, float]:
    """Percentile interval over the finite replicates."""
    finite = replicates[np.isfinite(replicates)]
    if finite.size == 0:
        return float("nan"), float("nan")
    tail = 100.0 * (1.0 - level) / 2.0
    return float(np.percentile(finite, tail)), float(np.percentile(finite, 100.0 - tail))
