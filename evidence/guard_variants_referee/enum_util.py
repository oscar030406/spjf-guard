import sys
sys.dont_write_bytecode = True
import itertools
import numpy as np


def arrival_sets(n, amax):
    """All rank-ordered arrival vectors: non-decreasing, values in 0..amax.
    (rank = stable order by (arrival, index), so a rank-ordered input has a sorted.)"""
    return np.array(sorted(itertools.combinations_with_replacement(range(amax + 1), n)),
                    dtype=np.int64)


def service_sets(n, L):
    return np.array(list(itertools.product(range(1, L + 1), repeat=n)), dtype=np.int64)


def pred_sets(n):
    """The prediction vector enters ONLY through the strict total order induced by
    (pred[q], rank q).  Every strict total order is realised by some permutation of
    0..n-1, and conversely.  So permutations are exhaustive over all predictions,
    ties included."""
    return np.array(list(itertools.permutations(range(n))), dtype=np.int64)
