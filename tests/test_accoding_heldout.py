"""The ACcoding held-out runner keeps sealed rows gated and its protocol pinned."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from spjf_guard.data import sealed
from spjf_guard.sim import MICROS, Trace, simulate
from spjf_guard.sim.bounds import assert_per_job_bounds
from spjf_guard.sim.policy import fcfs, guard, spjf

ROOT = Path(__file__).resolve().parents[1]


def _load_script():
    spec = importlib.util.spec_from_file_location(
        "run_accoding_heldout_test", ROOT / "scripts/run_accoding_heldout.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


script = _load_script()


def _load_freeze_script():
    spec = importlib.util.spec_from_file_location(
        "freeze_accoding_test", ROOT / "scripts/freeze_accoding.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _loader_config(row_bounds, submissions="synthetic.parquet", devtest_first_id=3):
    return {
        "data": {
            "submissions": submissions,
            "row_bounds": row_bounds,
            "devtest_first_id": devtest_first_id,
        }
    }


def _submissions(ids):
    n = len(ids)
    return pd.DataFrame(
        {
            "id": np.asarray(ids, dtype=np.int64),
            "problem_id": np.full(n, 10, dtype=np.int64),
            "creator_id": np.full(n, 20, dtype=np.int64),
            "contest_id": np.full(n, 30, dtype=np.int64),
            "lang": np.zeros(n, dtype=np.int64),
            "code_length": np.full(n, 100, dtype=np.int64),
            "time_cost": np.arange(1, n + 1, dtype=np.int64),
            "memory_cost": np.full(n, 1024, dtype=np.int64),
            "result": np.full(n, 2, dtype=np.int64),
        }
    )


@pytest.mark.parametrize(
    ("loader_name", "expected_ids"),
    [("load_development", [1, 2, 3]), ("load_devtest", [3])],
)
def test_arrow_predicate_is_passed_before_pandas_materialisation(
    monkeypatch, tmp_path, loader_name, expected_ids
):
    frame = _submissions([1, 2, 3])
    observed = {}

    class SpyTable:
        def to_pandas(self, **kwargs):
            assert observed["filters"] == [("id", "<", script.SEALED_FIRST_ID)]
            assert observed["columns"] == script.READ_COLUMNS
            assert observed["use_threads"] is False
            assert kwargs == {"use_threads": False}
            observed["materialised"] = True
            return frame.copy()

    def read_table(path, **kwargs):
        observed.update(kwargs)
        observed["path"] = path
        assert "materialised" not in observed
        return SpyTable()

    monkeypatch.setattr(script.pq, "read_table", read_table)
    config = _loader_config([0, 1, 2, 3, 4])

    loaded = getattr(script, loader_name)(config, tmp_path)

    assert loaded.id.tolist() == expected_ids
    assert observed["path"] == tmp_path / "synthetic.parquet"
    assert observed["materialised"] is True


def test_real_arrow_filter_excludes_the_boundary_and_later_ids(tmp_path):
    ids = [
        script.SEALED_FIRST_ID - 2,
        script.SEALED_FIRST_ID - 1,
        script.SEALED_FIRST_ID,
        script.SEALED_FIRST_ID + 1,
    ]
    path = tmp_path / "synthetic.parquet"
    pq.write_table(pa.Table.from_pandas(_submissions(ids), preserve_index=False), path)
    config = _loader_config([0, 1, 1, 2, 4], devtest_first_id=script.SEALED_FIRST_ID - 1)

    development = script.load_development(config, tmp_path)
    devtest = script.load_devtest(config, tmp_path)

    assert development.id.tolist() == ids[:2]
    assert devtest.id.tolist() == [script.SEALED_FIRST_ID - 1]
    assert development.id.max() < script.SEALED_FIRST_ID


@pytest.mark.parametrize("refusal", ["no-unseal", "missing-lock", "wrong-hash"])
def test_sealed_refusals_happen_before_arrow_reads(monkeypatch, tmp_path, refusal):
    config = _loader_config([0, 1, 2, 3, 4])
    params = tmp_path / "params.csv"
    params.write_text("family,promise_s\n", encoding="utf-8")
    marker = tmp_path / "marker.txt"
    marker.write_text("locked bytes", encoding="utf-8")
    monkeypatch.setattr(script, "required_files", lambda _root, _config: ["marker.txt"])

    if refusal == "wrong-hash":
        lock = {
            "status": "frozen",
            "config_values": config,
            "sha256": {"marker.txt": "0" * 64},
            "params_files": ["params.csv"],
            "outputs": script.output_names("sealed"),
        }
        (tmp_path / script.LOCK_REL).write_text(json.dumps(lock), encoding="utf-8")

    def forbidden_read(*_args, **_kwargs):
        raise AssertionError("a sealed parquet read was attempted")

    monkeypatch.setattr(script.pq, "read_table", forbidden_read)
    unseal = refusal != "no-unseal"

    with pytest.raises(sealed.SealedDataError):
        script._append_authorized_sealed(
            pd.DataFrame(), config, params, unseal=unseal, root=tmp_path
        )


def _guard_config():
    return {
        "trace": {"service_cap_s": 30.5},
        "guard": {"codebench_limit_s": 60.0},
        "predictor": {"score_key": "score"},
    }


JOINT = [
    {"promise_s": 300.0, "b0_base_s": 60.0, "eta": 0.5, "gam_base_s": 0.0},
    {"promise_s": 600.0, "b0_base_s": 120.0, "eta": 0.75, "gam_base_s": 0.0},
    {"promise_s": 1200.0, "b0_base_s": 120.0, "eta": 0.0, "gam_base_s": 16.0},
]


@pytest.mark.parametrize("k", [1, 4, 8])
@pytest.mark.parametrize("entry", JOINT)
def test_guard_scaling_changes_seconds_and_capacity_but_not_eta(k, entry):
    policy = script.scaled_guard(entry, k, _guard_config())
    ratio = 30.5 / 60.0
    scaled_promise = entry["promise_s"] * ratio
    bmax_s = k * (scaled_promise - (3 - 2 / k) * 30.5)
    b0_s = entry["b0_base_s"] * ratio * k / 4
    gamma_s = entry["gam_base_s"] * ratio * k / 4

    assert policy.bmax_us == round(bmax_s * MICROS)
    assert policy.b0_us == round(min(b0_s, bmax_s) * MICROS)
    assert policy.gam_us == round(gamma_s * MICROS)
    assert policy.eta_k / k == entry["eta"]


def test_each_joint_guard_satisfies_the_package_bound_on_an_adversarial_queue():
    n_jobs, k = 96, 4
    trace = Trace.from_seconds(
        np.zeros(n_jobs),
        np.where(np.arange(n_jobs) % 3 == 0, 30.5, 0.5),
        {"score": np.arange(n_jobs, 0, -1, dtype=np.float64)},
        limit_s=30.5,
    )
    baseline = simulate(trace, fcfs(), k)
    forced = []

    for entry in JOINT:
        policy = script.scaled_guard(entry, k, _guard_config())
        result = simulate(trace, policy, k)
        assert assert_per_job_bounds(result, baseline.wait_us, policy, k, 30.5) == n_jobs
        forced.append(result.n_forced)

    assert max(forced) > 0


def test_a_contest_opened_before_the_block_keeps_its_earlier_anchor():
    earlier = pd.DataFrame({"id": [5], "contest_id": [10]})
    block = pd.DataFrame({"id": [100, 101, 200], "contest_id": [10, 10, 20]})
    contests = pd.DataFrame(
        {
            "id": [10, 20],
            "start_time": [pd.Timestamp("2025-01-02"), pd.Timestamp("2025-01-01")],
        }
    )

    ids, times = script.block_anchors(pd.concat([earlier, block]), contests)

    np.testing.assert_array_equal(ids, [5.0, 200.0])
    assert times[0] == pd.Timestamp("2025-01-02").value / 1e9
    assert times[1] == times[0]


def _feature_inputs():
    df = pd.DataFrame(
        {
            "id": [1, 2, 3, 4],
            "problem_id": [7, 7, 7, 7],
            "creator_id": [9, 9, 9, 9],
            "contest_id": [11, 11, 11, 11],
            "lang": [0, 0, 0, 0],
            "code_length": [100, 100, 100, 100],
            "time_cost": [1000, 2000, 9000, 5000],
            "memory_cost": [100, 200, 300, 400],
            "result": [2, 2, 2, 2],
        }
    )
    problems = pd.DataFrame(
        {
            "id": [7],
            "n_tests": [3],
            "time_limit": [1000],
            "memory_limit": [65536],
            "difficulty": [2],
            "n_supported_langs": [1],
            "has_special_judge": [False],
            "partial_score": [False],
        }
    )
    tags = pd.DataFrame(columns=["problem_id", "tag_id", "weight"])
    return df, problems, tags


def test_lag_zero_features_use_strict_prefix_and_ignore_own_and_future_outcomes():
    df, problems, tags = _feature_inputs()
    keep = np.array([False, True, False, False])
    original, indices = script.pre.compute_features(
        df, problems, tags, 0, keep, heavy_thr=4000, log=None, every=0
    )
    changed = df.copy()
    changed.loc[1:, ["time_cost", "memory_cost", "result"]] = [30000, 999999, 9]
    after_future_change, changed_indices = script.pre.compute_features(
        changed, problems, tags, 0, keep, heavy_thr=4000, log=None, every=0
    )

    np.testing.assert_array_equal(indices, [1])
    np.testing.assert_array_equal(changed_indices, indices)
    np.testing.assert_allclose(after_future_change, original, equal_nan=True)
    assert original[0, script.pre.FIDX["p_n"]] == 1
    assert original[0, script.pre.FIDX["p_last_lg"]] == pytest.approx(np.log1p(1.0))

    changed.loc[0, "time_cost"] = 8000
    after_prefix_change, _ = script.pre.compute_features(
        changed, problems, tags, 0, keep, heavy_thr=4000, log=None, every=0
    )
    assert after_prefix_change[0, script.pre.FIDX["p_last_lg"]] == pytest.approx(np.log1p(8.0))


def _ledger(root):
    path = root / sealed.LOG_RELATIVE_PATH
    path.parent.mkdir(parents=True)
    path.write_text(
        "| 日期 | 脚本 | 读取内容 | 产出 | 查看者 | 影响设计 |\n|---|---|---|---|---|---|\n",
        encoding="utf-8",
    )
    return path


def _accoding_rows(path):
    return [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if "`scripts/run_accoding_heldout.py`" in line
    ]


def test_recording_accoding_writes_one_explicit_row_on_success_and_failure(tmp_path):
    success_root = tmp_path / "success"
    success = _ledger(success_root)
    with script.recording_accoding(success_root) as outcome:
        outcome.done("metrics.csv")
    success_rows = _accoding_rows(success)
    assert len(success_rows) == 1
    assert "accoding-sealed-id-block [0.80, 1.00]" in success_rows[0]
    assert "metrics.csv" in success_rows[0]

    failure_root = tmp_path / "failure"
    failure = _ledger(failure_root)
    with pytest.raises(RuntimeError, match="stopped"):
        with script.recording_accoding(failure_root):
            raise RuntimeError("stopped")
    failure_rows = _accoding_rows(failure)
    assert len(failure_rows) == 1
    assert "运行中断" in failure_rows[0]


def test_check_outputs_rejects_both_missing_and_extra_files(tmp_path):
    promised = script.output_names("sealed")
    for name in promised:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(name, encoding="utf-8")
    script.check_outputs(tmp_path, promised)

    missing = tmp_path / promised[0]
    missing.unlink()
    with pytest.raises(RuntimeError, match="output list mismatch"):
        script.check_outputs(tmp_path, promised)

    missing.write_text("restored", encoding="utf-8")
    (tmp_path / "unexpected.csv").write_text("extra", encoding="utf-8")
    with pytest.raises(RuntimeError, match="output list mismatch"):
        script.check_outputs(tmp_path, promised)


def test_freeze_refuses_an_existing_lock_before_inspecting_git(monkeypatch, tmp_path):
    freezer = _load_freeze_script()
    target = tmp_path / freezer.heldout.LOCK_REL
    target.write_text("existing", encoding="utf-8")

    def forbidden_clean(_root):
        raise AssertionError("git was inspected despite the existing lock")

    monkeypatch.setattr(freezer, "clean_commit", forbidden_clean)
    with pytest.raises(FileExistsError, match="already exists"):
        freezer.freeze(root=tmp_path)
    assert target.read_text(encoding="utf-8") == "existing"


def test_freeze_refuses_a_dirty_tree_before_tests_or_lock_write(monkeypatch, tmp_path):
    freezer = _load_freeze_script()
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        if command[:2] == ["git", "status"]:
            return SimpleNamespace(stdout=" M tests/test_accoding_heldout.py\n")
        raise AssertionError(f"unexpected command after dirty status: {command}")

    monkeypatch.setattr(freezer.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="dirty git tree"):
        freezer.freeze(root=tmp_path)

    assert calls == [["git", "status", "--porcelain", "--untracked-files=all"]]
    assert not (tmp_path / freezer.heldout.LOCK_REL).exists()


def test_freeze_dry_run_hashes_exact_bytes_and_pins_outputs(monkeypatch, tmp_path, capsys):
    freezer = _load_freeze_script()
    marker = tmp_path / "marker.bin"
    marker.write_bytes(b"protocol bytes\x00\xff")
    params = tmp_path / "params.csv"
    params.write_text(
        "family,promise_s,b0_base_s,eta,gam_base_s\n"
        "joint,300,60,0.5,0\n"
        "joint,600,120,0.75,0\n"
        "joint,1200,120,0,16\n",
        encoding="utf-8",
    )
    config = {
        "data": {"row_bounds": [0, 1, 2, 3, 7]},
        "guard": {
            "family": "joint",
            "promises_cb_s": [300, 600, 1200],
            "params_files": ["params.csv"],
        },
    }
    test_commands = []

    monkeypatch.setattr(freezer, "clean_commit", lambda _root: "a" * 40)
    monkeypatch.setattr(freezer.heldout, "read_config", lambda _root: config)
    monkeypatch.setattr(
        freezer.heldout,
        "required_files",
        lambda _root, _config: ["marker.bin", "params.csv"],
    )

    def pass_tests(command, **kwargs):
        test_commands.append((command, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(freezer.subprocess, "run", pass_tests)
    lock = freezer.freeze(yes=False, root=tmp_path)

    assert lock["sha256"]["marker.bin"] == hashlib.sha256(marker.read_bytes()).hexdigest()
    assert lock["sha256"]["params.csv"] == hashlib.sha256(params.read_bytes()).hexdigest()
    assert lock["outputs"] == freezer.heldout.output_names("sealed")
    assert lock["sealed_block"] == {
        "quantiles": [0.80, 1.00],
        "first_id": freezer.heldout.SEALED_FIRST_ID,
        "rows": 4,
    }
    assert len(test_commands) == 1
    assert test_commands[0][0][-2:] == ["-q", "tests/test_accoding_heldout.py"]
    assert test_commands[0][1]["check"] is True
    assert not (tmp_path / freezer.heldout.LOCK_REL).exists()
    assert "Dry run passed" in capsys.readouterr().out


def test_lock_tracks_transitive_local_script_imports(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "entry.py").write_text("import helper\n", encoding="utf-8")
    (scripts / "helper.py").write_text("from scripts import nested\n", encoding="utf-8")
    (scripts / "nested.py").write_text("import json\n", encoding="utf-8")
    assert script.script_dependencies(tmp_path, ["scripts/entry.py"]) == {
        "scripts/entry.py",
        "scripts/helper.py",
        "scripts/nested.py",
    }


def test_matching_accoding_lock_still_calls_the_package_gate(monkeypatch, tmp_path):
    config = {"data": {"row_bounds": [0, 1, 2, 3, 4]}}
    params = tmp_path / "params.csv"
    params.write_text("pinned parameters", encoding="utf-8")
    monkeypatch.setattr(script, "required_files", lambda _root, _config: ["params.csv"])
    lock = {
        "status": "frozen",
        "config_values": config,
        "runtime_versions": script.runtime_versions(),
        "sha256": {"params.csv": hashlib.sha256(params.read_bytes()).hexdigest()},
        "params_files": ["params.csv"],
        "outputs": script.output_names("sealed"),
    }
    (tmp_path / script.LOCK_REL).write_text(json.dumps(lock), encoding="utf-8")
    called = []
    monkeypatch.setattr(
        script.sealed,
        "guard_id_block",
        lambda lo, hi, root, unseal: called.append((lo, hi, root, unseal)),
    )
    assert script.authorize_sealed(config, params, True, tmp_path) == lock
    assert called == [(0.80, 1.00, tmp_path, True)]
    lock["outputs"] = ["unregistered.csv"]
    (tmp_path / script.LOCK_REL).write_text(json.dumps(lock), encoding="utf-8")
    with pytest.raises(sealed.SealedDataError, match="output list"):
        script.authorize_sealed(config, params, True, tmp_path)
    assert len(called) == 1
    lock["outputs"] = script.output_names("sealed")
    lock["runtime_versions"]["lightgbm"] = "changed-after-freeze"
    (tmp_path / script.LOCK_REL).write_text(json.dumps(lock), encoding="utf-8")
    with pytest.raises(sealed.SealedDataError, match="runtime versions"):
        script.authorize_sealed(config, params, True, tmp_path)
    assert len(called) == 1


def test_missing_ledger_refuses_before_entering_the_sealed_work(tmp_path):
    entered = False
    with pytest.raises(FileNotFoundError):
        with script.recording_accoding(tmp_path):
            entered = True
    assert not entered


def test_id_version_with_the_wrong_devtest_boundary_is_rejected(tmp_path):
    pq.write_table(
        pa.Table.from_pandas(_submissions([1, 2, 4]), preserve_index=False),
        tmp_path / "synthetic.parquet",
    )
    with pytest.raises(AssertionError):
        script.load_development(_loader_config([0, 1, 2, 3, 4]), tmp_path)


def test_fcfs_dispatch_count_is_not_reported_as_a_guard_trigger():
    config = script.read_config()
    trace = Trace.from_seconds([0, 0, 0], [0.5, 2, 1], limit_s=30.5)
    policy = fcfs()
    result = simulate(trace, policy, 1)
    assert result.n_forced == result.n_dispatch
    row = script.result_row(
        result,
        result,
        np.array([False, True, False]),
        {"k": 1},
        config,
        policy,
        0,
    )
    assert row["fired_fraction"] == 0


def test_online_features_are_lag_zero_in_row_order_and_hide_unfinished_results():
    df, problems, tags = _feature_inputs()
    keep = np.array([False, True, True, True])
    lag_zero, rows = script.pre.compute_features(
        df, problems, tags, 0, keep, heavy_thr=4000, log=None, every=0
    )
    history = script.pre.history_arrays(df, problems, tags, 4000)
    state = script.pre.history_before(history, 1)
    arrival = rows.astype(float)
    in_order = script.pre.online_block_features(history, state, rows, arrival, arrival + 0.5)
    np.testing.assert_array_equal(in_order.view(np.uint32), lag_zero.view(np.uint32))
    # row 1 still running when rows 2 and 3 arrive: only row 0 is visible to them
    late = script.pre.online_block_features(
        history, state, rows, arrival, np.array([9.0, 2.5, 3.5])
    )
    assert late[1, script.pre.FIDX["p_n"]] == 1 and late[2, script.pre.FIDX["p_n"]] == 2
    assert late[2, script.pre.FIDX["p_last_lg"]] == pytest.approx(np.log1p(9.0))
    assert state["P"][7][0] == 1  # the shared state is not consumed


def _online_case(seed, n=360, first=120):
    """A random submission history whose last n - first rows are the replayed block, with
    tied arrivals and tied completions, and two small boosters as the score model."""
    rng = np.random.default_rng(seed)
    df = pd.DataFrame(
        {
            "id": np.arange(1, n + 1),
            "problem_id": rng.integers(1, 6, n),
            "creator_id": rng.integers(1, 10, n),
            "contest_id": rng.integers(1, 4, n),
            "lang": rng.integers(0, 2, n),
            "code_length": rng.integers(50, 500, n),
            "time_cost": rng.choice([0, 0, 40, 400, 900, 2500, 4000], n),
            "memory_cost": rng.integers(100, 9000, n),
            "result": rng.choice([2, 2, 6, 9, 4], n),
        }
    )
    problems = pd.DataFrame(
        {
            "id": np.arange(1, 6),
            "n_tests": rng.integers(1, 9, 5),
            "time_limit": [1000] * 5,
            "memory_limit": [65536] * 5,
            "difficulty": rng.integers(1, 5, 5),
            "n_supported_langs": [2] * 5,
            "has_special_judge": [False] * 5,
            "partial_score": [False] * 5,
        }
    )
    tags = pd.DataFrame({"problem_id": [1, 1, 3], "tag_id": [4, 5, 4], "weight": [1.0, 2.0, 1.0]})
    history = script.pre.history_arrays(df, problems, tags, 2000)
    rows = np.arange(first, n)
    columns = [script.pre.FIDX[name] for name in script.pre.MODELS["M4"]]
    x = rng.normal(size=(400, len(columns))).astype(np.float32)
    boosters = [
        script.lgb.train(
            {"num_leaves": 7, "verbose": -1, "seed": s, "min_data_in_leaf": 5},
            script.lgb.Dataset(x, x[:, s] + rng.normal(size=400)),
            num_boost_round=20,
        )
        for s in (0, 1)
    ]
    online = {
        "A": history,
        "state": script.pre.history_before(history, first),
        "rows": rows,
        "boosters": boosters,
    }
    arrivals = np.sort(rng.integers(0, 40, len(rows))).astype(float)  # many ties
    service = rng.choice([0.5, 1.0, 1.0, 2.0, 3.0, 5.0], len(rows))
    order = np.argsort(np.rint(arrivals * MICROS), kind="mergesort")
    original = rng.normal(size=len(rows)).astype(np.float32)
    trace = Trace.from_seconds(arrivals[order], service[order], {"s": original[order]}, 5.0)
    config = {"predictor": {"score_model": "M4", "score_key": "s"}, "online": {"max_iterations": 400}}
    return trace, online, order, config


@pytest.mark.parametrize("seed", [0, 1, 2])
@pytest.mark.parametrize("wrapped", [False, True])
def test_one_pass_online_scores_are_the_fixed_point(seed, wrapped):
    trace, online, order, config = _online_case(seed)
    if wrapped:
        policy = guard(12.0, 2, 5.0, 1.0, 0.5, "s", name="Guard(12)")
    else:
        policy = spjf("s", "SPJF")
    iterated, rounds = script.online_fixed_point(trace, policy, 2, online, order, config)
    assert rounds > 1  # the original-clock scores are not already the online ones
    score_rows, close = script.accoding_online.single_row_scorer(
        online["boosters"], script.score_columns(config)
    )
    start = script.accoding_online.online_scores(trace, policy, 2, online, order, score_rows)
    close()
    settled, first_round = script.online_fixed_point(
        trace, policy, 2, online, order, config, start
    )
    assert first_round == 1
    np.testing.assert_array_equal(settled.wait_us, iterated.wait_us)
    np.testing.assert_array_equal(settled.dispatch_index, iterated.dispatch_index)
    assert settled.n_forced > 0 if wrapped else settled.n_forced == 0


def test_single_row_scorer_equals_the_batch_ensemble():
    """online_scores scores through LightGBM's single-row API and the warm-started fixed point
    rescores through score_model_predict's batch call, so the two must agree bit for bit,
    with and without missing features, for boosters fitted with and without them."""
    rng = np.random.default_rng(7)
    config = {"predictor": {"score_model": "M4"}}
    columns = script.score_columns(config)
    x = rng.normal(size=(2000, len(columns))).astype(np.float32)
    x[rng.random(x.shape) < 0.2] = np.nan
    y = np.nan_to_num(x[:, 0]) + rng.normal(size=len(x))
    boosters = [
        script.lgb.train(
            {"num_leaves": 31, "verbose": -1, "seed": s},
            script.lgb.Dataset(x if s else np.nan_to_num(x), y),
            num_boost_round=60,
        )
        for s in (0, 1, 2)
    ]
    features = np.full((500, len(script.pre.ALLF)), np.nan, np.float32)
    features[:, columns] = x[:500]
    score_rows, close = script.accoding_online.single_row_scorer(boosters, columns)
    np.testing.assert_array_equal(
        score_rows(features), script.score_model_predict(boosters, features, config)
    )
    close()
