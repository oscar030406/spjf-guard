"""Deliberately bad rankings, to separate the guard from the predictor.

The guarantee is a statement about the wrapper, not about the score: whatever order the
base policy proposes, no job waits more than its bound.  The way to show that is to hand
the base policy an order that is not merely imperfect but adversarial, and check the
bound still holds and the promise is still kept:

    reversed    the true cost negated: the longest job first, every time.
    random      a permutation of the true costs, so the order carries no information.
    top1short   the deployed score, except that the longest one percent of jobs are
                declared the shortest of all.  This is the failure an operator fears:
                the model is right almost everywhere and catastrophically wrong on the
                tail.

`random` draws from a named seed, so the corrupted order is a fixed function of the trace
and the configuration, not of when the run happened.
"""

from __future__ import annotations

import numpy as np

REVERSED, RANDOM, TOP1SHORT = "reversed", "random", "top1short"
KINDS = (REVERSED, RANDOM, TOP1SHORT)

TOP_FRACTION = 0.01
"""Share of the longest jobs that `top1short` mislabels."""


def adversarial_score(
    kind: str, service_s: np.ndarray, base_score: np.ndarray, seed: int
) -> np.ndarray:
    """One corrupted ranking key, as an array the simulator can sort by."""
    service_s = np.asarray(service_s, np.float64)
    if kind == REVERSED:
        return -service_s
    if kind == RANDOM:
        return np.random.default_rng(seed).permutation(service_s)
    if kind == TOP1SHORT:
        out = np.asarray(base_score, np.float64).copy()
        longest = np.argsort(-service_s, kind="stable")[
            : max(1, int(len(service_s) * TOP_FRACTION))
        ]
        out[longest] = out.min() - 1.0
        return out
    raise ValueError(f"unknown adversarial ranking {kind!r}; known: {KINDS}")


def adversarial_scores(service_s: np.ndarray, base_score: np.ndarray, seed: int) -> dict:
    return {kind: adversarial_score(kind, service_s, base_score, seed) for kind in KINDS}
