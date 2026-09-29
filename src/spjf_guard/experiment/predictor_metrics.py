"""What a ranking score is worth as a predictor, on one set of rows.

Four figures, the ones section 4 of the paper reports: AUROC and average precision for
the heavy class, RMSE on the `log1p` scale and Spearman correlation.  Every one of them
is written against a weight per row, so a single implementation serves both the point
estimate, where every weight is one, and a bootstrap resample, where a row's weight is
how often its block was drawn.  Nothing here decides what a block is; the caller does.

The two expensive steps -- sorting the score and ranking both vectors -- do not depend on
the weights, so `Sample` does them once and a resample is a weighted scan.  Ties are
counted the way the pre-checks counted them: AUROC gives a tied pair half a point, and
average precision takes one step per block of equal scores.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

METRICS = ("auroc", "average_precision", "rmse_log1p", "spearman")
"""The four figures, in the order the tables print them."""


def midrank(values: np.ndarray) -> np.ndarray:
    """Ranks with ties averaged, which is the rank Spearman's correlation is defined on."""
    order = np.argsort(values, kind="mergesort")
    sorted_values = values[order]
    starts = np.flatnonzero(np.r_[True, sorted_values[1:] != sorted_values[:-1]])
    ends = np.r_[starts[1:], len(values)]
    block = np.repeat(np.arange(len(starts)), ends - starts)
    out = np.empty(len(values), np.float64)
    out[order] = (0.5 * (starts + ends - 1))[block]
    return out


@dataclass(frozen=True)
class Sample:
    """One set of rows to score, arranged so that a resample is a scan.

    `order` sorts the score ascending and `group` numbers its blocks of equal values;
    `heavy` is the label in that same order.  The two log-scale vectors and their
    midranks stay in the rows' own order, where the weights are.
    """

    order: np.ndarray
    heavy: np.ndarray
    group: np.ndarray
    n_groups: int
    truth: np.ndarray
    prediction: np.ndarray
    truth_rank: np.ndarray
    prediction_rank: np.ndarray


def sample(score: np.ndarray, heavy: np.ndarray, truth: np.ndarray, prediction) -> Sample:
    """Prepare the rows once: `score` orders them, `truth` and `prediction` are log1p."""
    order = np.argsort(score, kind="mergesort")
    ordered = np.asarray(score, np.float64)[order]
    group = np.cumsum(np.r_[True, ordered[1:] != ordered[:-1]]) - 1
    return Sample(
        order=order,
        heavy=np.asarray(heavy, bool)[order],
        group=group,
        n_groups=int(group[-1]) + 1 if len(group) else 0,
        truth=np.asarray(truth, np.float64),
        prediction=np.asarray(prediction, np.float64),
        truth_rank=midrank(np.asarray(truth, np.float64)),
        prediction_rank=midrank(np.asarray(score, np.float64)),
    )


def _by_group(s: Sample, weights: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Weight of the heavy jobs and of all jobs, per block of equal scores."""
    ordered = weights[s.order]
    heavy = np.bincount(s.group, weights=np.where(s.heavy, ordered, 0.0), minlength=s.n_groups)
    return heavy, np.bincount(s.group, weights=ordered, minlength=s.n_groups)


def auroc(s: Sample, weights: np.ndarray) -> float:
    """The chance a heavy job is ranked above a light one, a tie counting for half."""
    heavy, total = _by_group(s, weights)
    light = total - heavy
    below = np.cumsum(light) - light
    pairs = heavy.sum() * light.sum()
    if pairs <= 0.0:
        return float("nan")
    return float((heavy * (below + 0.5 * light)).sum() / pairs)


def average_precision(s: Sample, weights: np.ndarray) -> float:
    """Precision averaged over recall, one step per block of equal scores."""
    heavy, total = _by_group(s, weights)
    heavy_above = np.cumsum(heavy[::-1])[::-1]
    all_above = np.cumsum(total[::-1])[::-1]
    if not len(heavy_above) or heavy_above[0] <= 0.0:
        return float("nan")
    precision = heavy_above / np.maximum(all_above, 1e-12)
    recall = heavy_above / heavy_above[0]
    return float(np.sum(np.diff(np.r_[0.0, recall[::-1]]) * precision[::-1]))


def rmse(s: Sample, weights: np.ndarray) -> float:
    """Root mean squared error on the log1p scale, where both scores are comparable."""
    residual = s.truth - s.prediction
    return float(np.sqrt(float((weights * residual * residual).sum()) / weights.sum()))


def spearman(s: Sample, weights: np.ndarray) -> float:
    """Correlation of the two midrank vectors.

    The ranks are the ones this set of rows has, not the ones a resample would have: a
    resample reweights the pairs, it does not re-rank them.  That is how the pre-check's
    user-block bootstrap of the same figure was computed, and it keeps the point estimate
    equal to the ordinary Spearman correlation.
    """
    total = weights.sum()
    x, y = s.prediction_rank, s.truth_rank
    mean_x, mean_y = float((weights * x).sum()) / total, float((weights * y).sum()) / total
    dx, dy = x - mean_x, y - mean_y
    spread = np.sqrt(float((weights * dx * dx).sum()) * float((weights * dy * dy).sum()))
    if spread <= 0.0:
        return float("nan")
    return float((weights * dx * dy).sum() / spread)


def evaluate(s: Sample, weights: np.ndarray) -> dict[str, float]:
    """All four figures under one weighting."""
    return {
        "auroc": auroc(s, weights),
        "average_precision": average_precision(s, weights),
        "rmse_log1p": rmse(s, weights),
        "spearman": spearman(s, weights),
    }


def replicates(s: Sample, block: np.ndarray, multiplicities: np.ndarray) -> dict:
    """Each figure over every resample, the first row being the sample itself.

    `block[i]` is the block row `i` belongs to and `multiplicities[b, j]` is how often
    block `j` was drawn in resample `b`, so the weights of a resample are one lookup.
    """
    drawn = [
        evaluate(s, multiplicities[b][block].astype(np.float64))
        for b in range(len(multiplicities))
    ]
    return {name: np.array([d[name] for d in drawn]) for name in METRICS}
