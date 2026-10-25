"""The co-ending treatments of scripts/build_coending_overlays.py change only the job set."""

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_coending_overlays import apply_variant  # noqa: E402


def _prepared():
    # Six submissions (rows 10..15 of the event table).  Group 0: submissions 0, 1, 2 of
    # term A; group 1: submissions 4, 5 of term B, which is outside the pool; submission 3
    # is solo.  Submission 2 is not simulatable, so it is in no job set either way.
    return SimpleNamespace(
        submission_rows=np.arange(10, 16),
        semester=np.array(["x"] * 10 + ["A", "A", "A", "A", "B", "B"], dtype=object),
        co_ending=np.array([0, 0, 0, -1, 1, 1]),
        simulatable=np.array([True, True, False, True, True, True]),
        cost_s=np.r_[np.zeros(10), [5.0, 90.0, 200.0, 7.0, 3.0, 4.0]],
    )


ARRIVAL = np.array([100.0, 40.0, 10.0, 50.0, 60.0, 61.0])


def test_dropped_removes_every_pool_member_and_nothing_else():
    prepared = _prepared()
    info = apply_variant(prepared, ARRIVAL, ["A"], 60.0, "dropped")
    assert prepared.simulatable.tolist() == [False, False, False, True, True, True]
    assert info == {"groups": 1, "removed": 2}
    assert np.array_equal(prepared.cost_s, _prepared().cost_s)


def test_merged_keeps_the_earliest_member_with_the_largest_capped_cost():
    prepared = _prepared()
    info = apply_variant(prepared, ARRIVAL, ["A"], 60.0, "merged")
    # Submission 1 arrives first among the simulatable members (40 < 100); submission 2
    # arrives earlier but never ran, so it does not represent the group.
    assert prepared.simulatable.tolist() == [False, True, False, True, True, True]
    assert prepared.cost_s[11] == 60.0  # max of min(5, 60) and min(90, 60)
    untouched = np.delete(np.arange(16), 11)
    assert np.array_equal(prepared.cost_s[untouched], _prepared().cost_s[untouched])
    assert info == {"groups": 1, "members": 2, "removed": 1}
