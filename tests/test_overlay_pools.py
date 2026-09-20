"""The pool constructions, on a synthetic set of class-terms.

Array equality with v3.1's stored overlays is checked by `scripts/check_overlays.py`,
which needs the real cache; what is testable without data is the shape of the two
constructions: the drawn copies are copy-major and a prefix of the next count, and the
single-server selection lands inside its utilisation window and is a prefix of its own
additions.
"""

from __future__ import annotations

import numpy as np
import pytest

from spjf_guard.experiment import overlay as ov

WINDOW = (0.78, 0.82)
TARGET = 0.80


def _per_term(n_terms: int = 6, per_term: int = 400, seed: int = 5) -> dict:
    """Class-terms whose arrivals sit in one week, each with its own base shift."""
    rng = np.random.default_rng(seed)
    out = {}
    for t in range(n_terms):
        arrival = np.sort(rng.uniform(0.0, 5 * 86400.0, per_term))
        out[f"T{t}"] = {
            "arr": arrival,
            "svc": rng.gamma(1.5, 4.0, per_term),
            "base": np.float64(ov.REFERENCE_MONDAY_S + t * 3600.0),
            "idx": np.arange(t * per_term, (t + 1) * per_term),
        }
    return out


def test_the_drawn_copies_are_copy_major_and_a_prefix_of_the_next_count():
    pool = ["A", "B", "C"]
    three = ov.overlay_entries(pool, 3, overlay=2, seed=7)
    four = ov.overlay_entries(pool, 4, overlay=2, seed=7)
    assert four[: len(three)] == three
    assert [term for term, _ in three] == pool * 3


def test_the_single_server_selection_lands_inside_its_window():
    per_term = _per_term()
    entries, rho = ov.single_server_pool(
        sorted(per_term),
        per_term,
        "arr",
        seed=20260919 * 100 + 50,
        target=TARGET,
        window=WINDOW,
    )
    assert WINDOW[0] <= rho <= WINDOW[1]
    assert entries
    arrival, service, rows, _ = ov.superpose(entries, per_term, "arr")
    assert ov.busy_hour_work(arrival, service) / 3600.0 == pytest.approx(rho, abs=1e-9)


def test_the_single_server_selection_is_deterministic_for_one_seed():
    per_term = _per_term()
    first = ov.single_server_pool(sorted(per_term), per_term, "arr", 1234, TARGET, WINDOW)
    second = ov.single_server_pool(sorted(per_term), per_term, "arr", 1234, TARGET, WINDOW)
    assert first == second


def test_a_pool_that_cannot_reach_the_window_is_an_error():
    """When no addition raises the busiest hour, the selection stops and says so.

    It does not quietly return a trace whose load is not the one the table claims.
    """
    per_term = _per_term(n_terms=2, per_term=4)
    for group in per_term.values():
        group["svc"] = np.zeros_like(group["svc"])
    with pytest.raises(RuntimeError, match="outside"):
        ov.single_server_pool(sorted(per_term), per_term, "arr", 11, TARGET, WINDOW)
