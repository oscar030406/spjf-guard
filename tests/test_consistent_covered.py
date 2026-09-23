"""Vectorised withheld-edge accounting agrees with direct same-copy enumeration."""

import numpy as np

from spjf_guard.experiment.consistent import _covered_violations


def test_covered_edges_are_policy_specific_and_never_cross_copy_rounds():
    arrays = {
        "arrival_us": np.array([0, 0, 5, 5, 10, 10], np.int64),
        "job_row": np.array([0, 0, 1, 1, 2, 2], np.int64),
        "copy_round": np.array([0, 1, 0, 1, 0, 1], np.int32),
    }
    withheld = {4: {0, 1}, 5: {0, 1}}
    completion = np.array([9, 12, 18, 15, 14, 16], np.int64)
    np.testing.assert_array_equal(
        _covered_violations(completion, arrays, 3, withheld), [0, 0, 0, 0, 1, 2]
    )
    completion[:2] = [20, 9]
    np.testing.assert_array_equal(
        _covered_violations(completion, arrays, 3, withheld), [0, 0, 0, 0, 2, 1]
    )


def test_covered_counts_match_a_seeded_brute_force_reference():
    rng = np.random.default_rng(4006)
    n_rows, n_rounds = 80, 3
    rows = np.tile(np.arange(n_rows), n_rounds)
    rounds = np.repeat(np.arange(n_rounds), n_rows)
    arrival = rng.integers(0, 300, len(rows)).astype(np.int64)
    order = np.argsort(arrival, kind="stable")
    arrays = {"arrival_us": arrival[order], "job_row": rows[order], "copy_round": rounds[order]}
    completion = arrays["arrival_us"] + rng.integers(1, 100, len(rows))
    withheld = {
        int(job): set(map(int, rng.choice(n_rows, 7, replace=False)))
        for job in rng.choice(len(rows), 70, replace=False)
    }
    expected = np.zeros(len(rows), np.int32)
    for job, sources in withheld.items():
        members = (arrays["copy_round"] == arrays["copy_round"][job]) & np.isin(
            arrays["job_row"], list(sources)
        )
        expected[job] = int(np.sum(completion[members] > arrays["arrival_us"][job]))
    np.testing.assert_array_equal(
        _covered_violations(completion, arrays, n_rows, withheld), expected
    )
