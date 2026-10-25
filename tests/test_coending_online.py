"""scripts/run_coending_online.py rebuilds only the own-copy history on the variant's jobs."""

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_coending_online as rco  # noqa: E402
from test_coending_overlays import ARRIVAL, _prepared  # noqa: E402


def test_the_history_is_rebuilt_on_the_variant_and_the_fitted_context_is_untouched(
    monkeypatch,
):
    seen = {}
    monkeypatch.setattr(
        rco, "M4HistoryRecomputer", lambda prepared, *_: seen.setdefault("recomputer", prepared)
    )
    monkeypatch.setattr(
        rco,
        "build_same_copy_history_index",
        lambda prepared, *_: seen.setdefault("same_copy", prepared),
    )
    original = _prepared()
    context = {
        "prepared": original,
        "arrival": np.r_[np.zeros(10), ARRIVAL],
        "availability": np.r_[np.zeros(10), ARRIVAL],
        "models": "frozen",
        "recomputer": "unmodified",
        "same_copy": "unmodified",
    }
    out = rco.variant_context(context, SimpleNamespace(limit_s=60.0), ["A"], "dropped")

    assert seen["recomputer"] is seen["same_copy"] is out["prepared"]
    assert out["prepared"].simulatable.tolist() == [False, False, False, True, True, True]
    assert out["models"] == "frozen"
    assert original.simulatable.tolist() == _prepared().simulatable.tolist()
    assert np.array_equal(original.cost_s, _prepared().cost_s)


def test_merged_picks_the_member_by_submission_arrival(monkeypatch):
    # The context's arrival is indexed by event row; submissions are rows 10..15, and the
    # other rows hold values that would pick a different member if they were used.
    monkeypatch.setattr(rco, "M4HistoryRecomputer", lambda prepared, *_: None)
    monkeypatch.setattr(rco, "build_same_copy_history_index", lambda prepared, *_: None)
    event_arrival = np.r_[np.arange(10.0)[::-1], ARRIVAL]
    context = {"prepared": _prepared(), "arrival": event_arrival, "availability": event_arrival}
    out = rco.variant_context(context, SimpleNamespace(limit_s=60.0), ["A"], "merged")
    assert out["prepared"].simulatable.tolist() == [False, True, False, True, True, True]
