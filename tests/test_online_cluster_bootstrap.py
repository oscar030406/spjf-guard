"""The online bootstrap names every copy of a resampled pool by (class-term, round)."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from run_online_cluster_bootstrap import distinct_rounds  # noqa: E402


def _entries(pool, copies):
    # copy_entry as overlay.superpose numbers the copies: copy-major, in pool order.
    return np.arange(copies * len(pool), dtype=np.int32)


def test_a_pool_without_repeats_keeps_the_overlay_rounds():
    pool = ["a", "b", "c"]
    entry = _entries(pool, 4)
    assert np.array_equal(distinct_rounds(entry, pool), entry // len(pool))


def test_repeated_class_terms_get_a_round_of_their_own():
    pool = ["a", "b", "a", "c", "a"]
    entry = _entries(pool, 3)
    rounds = distinct_rounds(entry, pool)
    names = {(pool[e % len(pool)], int(r)) for e, r in zip(entry, rounds)}
    assert len(names) == len(entry)
