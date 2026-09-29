"""The wiring the sealed pool's single-server run needs, without any sealed data.

Three things have to hold for `--pool sealed --single-server` to be a run at all: the
two k = 1 traces cannot share a file name, a trace built without stored scores has to
survive a run that attaches its own, and a score file that belongs to another cache has
to be refused instead of dropped.  All three are checked here on synthetic files.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_overlays as bo  # noqa: E402
import run_main as rm  # noqa: E402
from spjf_guard import config as cfgmod  # noqa: E402
from spjf_guard.experiment.reproduce import load_overlay  # noqa: E402

CONFIG = ROOT / "configs" / "main.yaml"


def _config():
    return cfgmod.load(CONFIG)


def _overlay(path: Path, n: int = 64, scores: bool = True) -> Path:
    rng = np.random.default_rng(4)
    service = np.clip(rng.gamma(0.5, 1.0, n), 1e-3, 60.0)
    arrival = np.cumsum(rng.exponential(1.0, n))
    arrays = {
        "a": arrival,
        "svc": service,
        "dl": rng.random(n) < 0.3,
        "exam": rng.random(n) < 0.1,
        "hvt": service > 1.0,
        "wk": np.zeros(n, np.int64),
        "weeks": np.zeros(1, np.int64),
        "job_row": np.arange(n, dtype=np.int64),
        "K": np.array([1], np.int64),
        "W": np.float64(service.sum()),
    }
    if scores:
        arrays["tweedie"] = service + rng.normal(0.0, 0.1, n)
    np.savez(path, **arrays)
    return path


def test_the_two_single_server_traces_do_not_share_a_file_name():
    cfg = _config()
    selection_pool = cfg["overlay"]["single_server"]["pool"]
    assert bo.single_server_prefix(cfg, selection_pool) == "k1"
    assert bo.single_server_prefix(cfg, "sealed") == "sealed_k1"
    assert bo.single_server_prefix(cfg, "validation") == "validation_k1"


def test_the_single_server_run_is_checked_against_its_own_pinned_list():
    assert rm.sealed_table_key(None) == "sealed_tables"
    assert rm.sealed_table_key("sealed") == "sealed_tables"
    assert rm.sealed_table_key("k1") == "sealed_k1_tables"
    assert rm.sealed_table_key("sealed_k1") == "sealed_k1_tables"
    cfg = _config()
    for key in ("sealed_tables", "sealed_k1_tables"):
        rm.check_sealed_tables(cfg, "primary", None, [])  # a development run is free
        with pytest.raises(SystemExit):
            rm.check_sealed_tables(cfg, "sealed", "k1" if "k1" in key else None, [])


def test_a_trace_without_stored_scores_loads_when_the_run_brings_its_own(tmp_path):
    """The sealed overlays carry no scores -- they are fitted after the overlays are
    built -- so an empty score map has to mean none, not the default one."""
    path = _overlay(tmp_path / "sealed_k1_rep0.npz", scores=False)
    trace, servers, labels = load_overlay(path, 0, {}, 60.0)
    assert trace.scores == {}
    assert servers == 1
    assert set(labels) == {"in_window", "is_heavy"}
    with pytest.raises(KeyError):
        load_overlay(path, 0, None, 60.0)
    stored, _, _ = load_overlay(_overlay(tmp_path / "with_rep0.npz"), 0, None, 60.0)
    assert set(stored.scores) == {"tweedie"}


def test_scores_fitted_on_another_cache_are_refused_rather_than_dropped(tmp_path):
    import pandas as pd

    cfg = _config()
    path = tmp_path / "scores.parquet"
    pd.DataFrame({"tweedie": np.arange(5.0), "log": np.arange(5.0)}).to_parquet(path)
    assert set(bo.load_scores(cfg, 5, path)) == {"tweedie", "log"}
    with pytest.raises(SystemExit, match="read by position"):
        bo.load_scores(cfg, 6, path)
    assert bo.load_scores(cfg, 6, path, wanted=False) == {}


def test_this_packages_own_score_columns_are_read_too(tmp_path):
    import pandas as pd

    path = tmp_path / "forward_scores.parquet"
    pd.DataFrame(
        {cfgmod.SCORE_KEY: np.arange(3.0), cfgmod.LOG_SCORE_KEY: np.arange(3.0)}
    ).to_parquet(path)
    assert set(bo.load_scores(_config(), 3, path)) == {"tweedie", "log"}
    other = tmp_path / "unrelated.parquet"
    pd.DataFrame({"something": np.arange(3.0)}).to_parquet(other)
    with pytest.raises(SystemExit, match="none of the score columns"):
        bo.load_scores(_config(), 3, other)


def test_a_sealed_run_marks_its_numbers_as_sealed_and_a_development_run_does_not():
    """Which of the paper's two marks a run's LaTeX table is typeset with."""
    assert rm.table_macro("sealed") == "sealednum"
    for pool in ("primary", "validation", "dev8"):
        assert rm.table_macro(pool) == "devnum"
