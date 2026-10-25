"""Evaluate frozen parameters on ACcoding, with an explicitly gated sealed entry point."""

from __future__ import annotations

import argparse
import ast
import contextlib
import hashlib
import json
import os
import platform
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_REL = "configs/accoding_heldout_20260928.yaml"
SCRIPT_REL = "scripts/run_accoding_heldout.py"
PRECHECK_REL = "prechecks/accoding_v2/accoding_v2.py"
LOCK_REL = "protocol_lock_accoding.json"
SEALED_FIRST_ID = 3246174
METADATA_FILES = [
    "data/accoding/parquet/problems.parquet",
    "data/accoding/parquet/contests.parquet",
    "data/accoding/parquet/problem_tags.parquet",
]
READ_COLUMNS = [
    "id",
    "problem_id",
    "creator_id",
    "contest_id",
    "lang",
    "code_length",
    "time_cost",
    "memory_cost",
    "result",
]

sys.dont_write_bytecode = True
for variable in (
    "NUMBA_NUM_THREADS",
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
):
    os.environ[variable] = "4"
os.environ.setdefault("NUMBA_CACHE_DIR", str(Path(tempfile.gettempdir()) / "accoding_numba"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import lightgbm as lgb  # noqa: E402
import numba  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pyarrow as pa  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402
import yaml  # noqa: E402
from prechecks.accoding_v2 import accoding_v2 as pre  # noqa: E402
from scripts import accoding_online  # noqa: E402

from spjf_guard.data import sealed  # noqa: E402
from spjf_guard.experiment import provenance  # noqa: E402
from spjf_guard.sim import MICROS, Trace, simulate  # noqa: E402
from spjf_guard.sim.bounds import assert_per_job_bounds  # noqa: E402
from spjf_guard.sim.policy import fcfs, guard, sjf, spjf  # noqa: E402

pa.set_cpu_count(4)
pa.set_io_thread_count(1)


class Log:
    def __init__(self, path):
        self.file = Path(path).open("x", encoding="utf-8")

    def p(self, message):
        print(message, flush=True)
        self.file.write(str(message) + "\n")
        self.file.flush()

    def close(self):
        self.file.close()


def read_config(root=ROOT):
    with (root / CONFIG_REL).open(encoding="utf-8") as stream:
        config = yaml.safe_load(stream)
    assert config["data"]["sealed_first_id"] == SEALED_FIRST_ID
    assert config["resources"]["threads"] == pre.N_THREADS == 4
    assert config["trace"]["svc_fixed_s"] == pre.SVC_FIXED
    assert config["trace"]["episode_cap_h"] == pre.EPISODE_CAP_H
    assert config["trace"]["practice_chunk"] == pre.PRACTICE_CHUNK
    assert config["trace"]["busy_work_target_s"] == pre.BUSY_WORK_TARGET
    settings = config["predictor"]
    for seed in settings["seeds"]:
        params = pre.lgb_params("regression", seed, settings["num_leaves"])
        assert all(params[key] == value for key, value in settings["lgb_fixed"].items())
        assert all(
            params[key] == seed + offset for key, offset in settings["lgb_seed_offsets"].items()
        )
    return config


def load_development(config, root=ROOT):
    """Push the development predicate into Arrow before any pandas materialisation."""
    table = pq.read_table(
        root / config["data"]["submissions"],
        columns=READ_COLUMNS,
        filters=[("id", "<", SEALED_FIRST_ID)],
        use_threads=False,
    )
    df = table.to_pandas(use_threads=False)
    assert int(df["id"].max()) < SEALED_FIRST_ID
    assert (np.diff(df["id"].to_numpy(np.int64)) > 0).all()
    bounds = config["data"]["row_bounds"]
    assert len(df) == bounds[3]
    assert int(df.iloc[bounds[2]]["id"]) == config["data"]["devtest_first_id"]
    df["blk"] = np.zeros(len(df), dtype=np.int8)
    df.loc[bounds[1] : bounds[2] - 1, "blk"] = 1
    df.loc[bounds[2] :, "blk"] = 2
    return df


def load_devtest(config, root=ROOT):
    df = load_development(config, root)
    return df.loc[df["blk"] == 2].reset_index(drop=True)


def script_dependencies(root, entrypoints):
    """Collect local script imports recursively, without executing their code."""
    pending = list(entrypoints)
    found = set()
    while pending:
        relative = pending.pop()
        if relative in found:
            continue
        found.add(relative)
        tree = ast.parse((root / relative).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module, *[node.module + "." + a.name for a in node.names]]
            for name in names:
                candidate = "scripts/" + name.removeprefix("scripts.").replace(".", "/") + ".py"
                if (root / candidate).is_file():
                    pending.append(candidate)
    return found


def required_files(root, config):
    files = script_dependencies(root, [SCRIPT_REL, "scripts/freeze_accoding.py"])
    files.update([CONFIG_REL, PRECHECK_REL, "tests/test_accoding_heldout.py"])
    files.update(["pyproject.toml", "uv.lock", *METADATA_FILES])
    files.update(config["guard"]["params_files"])
    files.update(
        p.relative_to(root).as_posix() for p in (root / "src/spjf_guard").rglob("*.py")
    )
    return sorted(files)


def runtime_versions():
    return {
        "python": sys.version,
        "platform": platform.system(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "lightgbm": lgb.__version__,
        "pyarrow": pa.__version__,
        "numba": numba.__version__,
        "pyyaml": yaml.__version__,
    }


def output_names(block):
    names = [
        "metrics.csv",
        "summary.csv",
        "predictor_metrics.csv",
        "tail_shares.csv",
        "trace_calibration.csv",
        "anchors.csv",
        "run.log",
        "manifest.json",
    ]
    if block == "devtest":
        names += [
            "anchor_comparison.csv",
            "precheck_reference_metrics.csv",
            "precheck_reference_summary.csv",
            "reproduction.csv",
        ]
    return sorted(names)


def validate_lock(config, params_path, unseal, root=ROOT):
    if not unseal:
        raise sealed.SealedDataError("sealed ACcoding requires --unseal")
    path = root / LOCK_REL
    if not path.is_file():
        raise sealed.SealedDataError(f"sealed ACcoding requires {LOCK_REL}")
    lock = json.loads(path.read_text(encoding="utf-8"))
    if lock["status"] != "frozen" or lock["config_values"] != config:
        raise sealed.SealedDataError("ACcoding lock status or pinned config does not match")
    expected = required_files(root, config)
    if set(lock["sha256"]) != set(expected):
        raise sealed.SealedDataError("ACcoding lock file list does not match current imports")
    for name in expected:
        if provenance.sha256_file(root / name) != lock["sha256"][name]:
            raise sealed.SealedDataError(f"ACcoding lock sha256 mismatch: {name}")
    if lock["runtime_versions"] != runtime_versions():
        raise sealed.SealedDataError("ACcoding runtime versions differ from the freeze")
    relative_params = params_path.resolve().relative_to(root.resolve()).as_posix()
    if relative_params not in lock["params_files"]:
        raise sealed.SealedDataError(f"unlocked params CSV: {relative_params}")
    if lock["outputs"] != output_names("sealed"):
        raise sealed.SealedDataError("ACcoding lock output list does not match")
    return lock


def authorize_sealed(config, params_path, unseal, root=ROOT):
    lock = validate_lock(config, params_path, unseal, root)
    sealed.guard_id_block(0.80, 1.00, root, unseal=True)
    return lock


@contextlib.contextmanager
def recording_accoding(root=ROOT):
    """The package recorder accepts term names; explicitly record this id-block label."""
    with (root / sealed.LOG_RELATIVE_PATH).open("r+", encoding="utf-8"):
        pass
    with sealed.recording(root, SCRIPT_REL, ["accoding-sealed-id-block"], True) as outcome:
        try:
            yield outcome
        except BaseException as exc:
            outcome.at(f"{type(exc).__name__}: {exc}")
            raise
        finally:
            sealed.record_access(
                root,
                SCRIPT_REL,
                "accoding-sealed-id-block [0.80, 1.00]",
                outcome.produced,
                "运行者",
                "否",
            )


def _append_authorized_sealed(development, config, params_path, unseal, root=ROOT):
    """Future author-only read: require both locks before the sealed predicate is used."""
    authorize_sealed(config, params_path, unseal, root)
    table = pq.read_table(
        root / config["data"]["submissions"],
        columns=READ_COLUMNS,
        filters=[("id", ">=", SEALED_FIRST_ID)],
        use_threads=False,
    )
    block = table.to_pandas(use_threads=False)
    assert int(block["id"].min()) == SEALED_FIRST_ID
    assert (np.diff(block["id"].to_numpy(np.int64)) > 0).all()
    bounds = config["data"]["row_bounds"]
    assert len(block) == bounds[4] - bounds[3]
    block["blk"] = np.full(len(block), 3, dtype=np.int8)
    return pd.concat([development, block], ignore_index=True)


def read_parameters(path, config):
    frame = pd.read_csv(path)
    columns = ["family", "promise_s", "b0_base_s", "eta", "gam_base_s"]
    joint = frame.loc[frame.family == config["guard"]["family"], columns]
    expected = sorted(config["guard"]["promises_cb_s"])
    if sorted(joint.promise_s.tolist()) != expected:
        raise ValueError(f"params must contain exactly one joint row for each G in {expected}")
    return joint.sort_values("promise_s").to_dict("records")


def scaled_guard(entry, k, config):
    limit = config["trace"]["service_cap_s"]
    scale = limit / config["guard"]["codebench_limit_s"]
    return guard(
        promise_s=entry["promise_s"] * scale,
        k=k,
        limit_s=limit,
        b0_s=entry["b0_base_s"] * scale * k / 4,
        eta=entry["eta"],
        gam_s=entry["gam_base_s"] * scale * k / 4,
        score_key=config["predictor"]["score_key"],
        name=f"Guard({entry['promise_s']:g})",
    )


def block_anchors(rows, contests):
    """Each contest's first id among `rows` with its start_time, in id order.

    `rows` are all rows loaded up to the evaluated block's end, not the block alone: a
    contest that opened in an earlier block would otherwise be anchored at its first id
    inside the block, which moves every id after it to a later clock.  On the dev-test
    block this gives the precheck's anchors (`id_time_anchors` of the development rows).
    """
    first = rows.loc[rows.contest_id >= 0].groupby("contest_id")["id"].min()
    first = (
        first.rename("first_id")
        .reset_index()
        .merge(
            contests[["id", "start_time"]],
            left_on="contest_id",
            right_on="id",
            how="inner",
        )
    )
    first = first.dropna(subset=["start_time"]).sort_values("first_id")
    ids = first.first_id.to_numpy(np.float64)
    times = np.array([t.value / 1e9 for t in first.start_time])
    return ids, np.maximum.accumulate(times)


def compare_anchors(block, own, legacy):
    ids = block["id"].to_numpy()
    ours = np.interp(ids, *own)
    old = np.interp(ids, *legacy)
    difference = ours - old
    return pd.DataFrame(
        [
            {
                "block_anchor_count": len(own[0]),
                "precheck_anchor_count": len(legacy[0]),
                "anchor_arrays_equal": all(np.array_equal(a, b) for a, b in zip(own, legacy)),
                "jobs_with_different_mapped_time": int(np.count_nonzero(difference)),
                "max_absolute_time_difference_s": float(np.abs(difference).max()),
                "mean_absolute_time_difference_s": float(np.abs(difference).mean()),
                "first_job_block_time_s": ours[0],
                "first_job_precheck_time_s": old[0],
            }
        ]
    )


def filtered_fingerprint(frame):
    hashed = pd.util.hash_pandas_object(frame, index=False).to_numpy(np.uint64)
    return hashlib.sha256(hashed.tobytes()).hexdigest()


def make_features(df, prob, ptag, block_number, config, log):
    threshold = pre.heavy_threshold(df)
    assert threshold == config["data"]["heavy_threshold_reference_ms"]
    judged = pre.modelling_mask(df).to_numpy()
    blocks = df["blk"].to_numpy()
    rng = np.random.default_rng(config["predictor"]["train_sample_seed"])
    training = np.flatnonzero(judged & (blocks == 0))
    training = np.sort(
        rng.choice(training, config["predictor"]["train_sample_rows"], replace=False)
    )
    keep = judged & ((blocks == 1) | (blocks == block_number))
    keep[training] = True
    features, indices = pre.compute_features(df, prob, ptag, 0, keep, threshold, log)
    targets = np.log1p(np.maximum(df.time_cost.to_numpy()[indices], 0) / 1000).astype(
        np.float32
    )
    heavy = (df.time_cost.to_numpy()[indices] > threshold).astype(np.int8)
    feature_blocks = blocks[indices]
    log.p(
        f"Features: {len(training)} train, {sum(feature_blocks == 1)} valid, "
        f"{sum(feature_blocks == block_number)} evaluated; heavy threshold {threshold} ms"
    )
    return features, indices, targets, heavy, feature_blocks, threshold


def prediction_rows(model, seed, scores, heavy_scores, y, heavy, groups):
    rows = []
    for name, mask in groups.items():
        rows.append(
            {
                "model": model,
                "seed": str(seed),
                "group": name,
                "n_jobs": int(mask.sum()),
                "auroc": pre.roc_auc(heavy[mask], heavy_scores[mask]),
                "ap": pre.avg_prec(heavy[mask], heavy_scores[mask]),
                "rmse_log1p_s": float(np.sqrt(np.mean((scores[mask] - y[mask]) ** 2))),
            }
        )
    return rows


def fit_predict(features, targets, heavy, blocks, block_number, config, log):
    tr, te = blocks == 0, blocks == block_number
    evaluated = features[te]
    groups = {
        "all": np.ones(te.sum(), bool),
        "cold-problem(<5 visible)": evaluated[:, pre.FIDX["p_n"]] < 5,
        "cold-user(<5 visible)": evaluated[:, pre.FIDX["u_n"]] < 5,
    }
    groups["cold-both"] = groups["cold-problem(<5 visible)"] & groups["cold-user(<5 visible)"]
    settings = config["predictor"]
    rows, predictions, boosters = [], {}, []
    for model in settings["models"]:
        columns = [pre.FIDX[name] for name in pre.MODELS[model]]
        xtrain = np.ascontiguousarray(features[tr][:, columns])
        xtest = np.ascontiguousarray(evaluated[:, columns])
        regressions, classifications = [], []
        for seed in settings["seeds"]:
            scores = []
            for objective, target in [
                (settings["regression_objective"], targets),
                (settings["heavy_objective"], heavy),
            ]:
                model_fit = lgb.train(
                    pre.lgb_params(objective, seed, settings["num_leaves"]),
                    lgb.Dataset(xtrain, label=target[tr], feature_name=pre.MODELS[model]),
                    num_boost_round=settings["rounds"],
                )
                scores.append(model_fit.predict(xtest, num_threads=4).astype(np.float32))
                if model == settings["score_model"] and objective == settings["regression_objective"]:
                    boosters.append(model_fit)
            regressions.append(scores[0])
            classifications.append(scores[1])
            rows.extend(prediction_rows(model, seed, *scores, targets[te], heavy[te], groups))
            log.p(f"Fitted {model}, seed {seed}, training block only")
        pr, pc = np.mean(regressions, axis=0), np.mean(classifications, axis=0)
        rows.extend(prediction_rows(model, "ensemble", pr, pc, targets[te], heavy[te], groups))
        predictions[model] = pr
        log.p(
            f"{model} ensemble AUROC={pre.roc_auc(heavy[te], pc):.8f}, "
            f"AP={pre.avg_prec(heavy[te], pc):.8f}"
        )
    return pd.DataFrame(rows), predictions[settings["score_model"]], boosters


def tail_row(values, population, cost_kind, fractions):
    descending = np.sort(values)[::-1]
    row = {
        "population": population,
        "cost_kind": cost_kind,
        "n_jobs": len(values),
        "total_s": float(values.sum()),
        "mean_s": float(values.mean()),
    }
    for fraction in fractions:
        n_tail = max(1, int(len(values) * fraction))
        row[f"top{100 * fraction:g}_share"] = float(
            descending[:n_tail].sum() / descending.sum()
        )
    return row


def tail_rows(df, name, config):
    costs = df.loc[pre.modelling_mask(df), "time_cost"].to_numpy(np.float64) / 1000
    service = np.minimum(
        costs + config["trace"]["svc_fixed_s"], config["trace"]["service_cap_s"]
    )
    fractions = config["metrics"]["tail_fractions"]
    return [
        tail_row(costs[costs > 0], name, "measured_positive", fractions),
        tail_row(service, name, "service", fractions),
    ]


def gap_closed(fcfs_value, policy_value, sjf_value):
    denominator = fcfs_value - sjf_value
    return (fcfs_value - policy_value) / denominator if denominator != 0 else float("nan")


def result_row(result, baseline, heavy, context, config, policy, checked):
    excess = (result.wait_us - baseline.wait_us) / MICROS
    immediate = baseline.wait_us <= round(config["metrics"]["harm_fcfs_max_s"] * MICROS)
    metrics = pre.sim_metrics(result.wait_s, heavy, result.policy)
    del metrics["p99_dl"], metrics["mean_dl"]
    return {
        **context,
        **metrics,
        "max_excess_s": float(excess.max()),
        "harm_s": float(excess[immediate].max()),
        "fired_fraction": result.fired_fraction if policy.wrapper == "work" else 0.0,
        "bounds_checked": checked,
        "b0_s": policy.b0_us / MICROS,
        "eta": policy.eta_k / context["k"],
        "gamma_s": policy.gam_us / MICROS,
        "bmax_s": policy.bmax_us / MICROS,
        "score_definition": (
            f"{config['predictor']['score_model']}; "
            f"{config['predictor']['regression_objective']}; "
            f"{config['predictor']['regression_target']}"
            if policy.score_key == config["predictor"]["score_key"]
            else policy.name
        ),
    }


def run_cell(trace, heavy, context, entries, config):
    policies = [
        fcfs(),
        sjf(),
        spjf(config["predictor"]["score_key"], config["predictor"]["policy_label"]),
    ]
    policies += [scaled_guard(entry, context["k"], config) for entry in entries]
    baseline = simulate(trace, policies[0], context["k"])
    rows = []
    for policy, entry in zip(policies, [None, None, None, *entries]):
        result = baseline if policy.name == "FCFS" else simulate(trace, policy, context["k"])
        checked = 0
        if policy.wrapper == "work":
            checked = assert_per_job_bounds(
                result,
                baseline.wait_us,
                policy,
                context["k"],
                trace.limit_s,
            )
        row = result_row(result, baseline, heavy, context, config, policy, checked)
        row["promise_cb_s"] = entry["promise_s"] if entry else float("nan")
        row["promise_acc_s"] = (
            entry["promise_s"] * trace.limit_s / config["guard"]["codebench_limit_s"]
            if entry
            else float("nan")
        )
        rows.append(row)
    for row in rows:
        for metric in ["mean", "p99"]:
            row[f"gap_closed_{metric}"] = gap_closed(
                rows[0][metric], row[metric], rows[1][metric]
            )
    return rows


def score_columns(config):
    return [pre.FIDX[name] for name in pre.MODELS[config["predictor"]["score_model"]]]


def score_model_predict(boosters, features, config):
    """The score model's ensemble on feature rows, as fit_predict computes it."""
    x = np.ascontiguousarray(features[:, score_columns(config)])
    return np.mean([b.predict(x, num_threads=4).astype(np.float32) for b in boosters], axis=0)


def online_fixed_point(trace, policy, k, online, order, config, start=None):
    """(result, iterations) of `policy` under the online clock.

    A job's score is computed at its arrival from the evaluated block's results that have
    completed by then (online_block_features), everything before the block being visible.
    Starting from `start` (default: the original-clock scores), schedule and scores are
    recomputed until the scores repeat exactly; the schedule up to a time depends only on
    the scores of jobs that arrived before it, so the iteration settles on the online
    replay, and from the one-pass scores of accoding_online it settles at once."""
    key = config["predictor"]["score_key"]
    scores = trace.scores[key] if start is None else start
    arrival = np.empty(len(order), np.int64)
    arrival[order] = trace.arrival_us
    completion = np.empty(len(order), np.int64)
    for iteration in range(1, config["online"]["max_iterations"] + 1):
        current = Trace(trace.arrival_us, trace.service_us, {key: scores}, trace.limit_s)
        result = simulate(current, policy, k)
        completion[order] = trace.arrival_us + result.wait_us + trace.service_us
        features = pre.online_block_features(
            online["A"], online["state"], online["rows"], arrival, completion
        )
        rescored = score_model_predict(online["boosters"], features, config)[order]
        if np.array_equal(rescored, scores):
            return result, iteration
        scores = rescored
    raise AssertionError(f"{policy.name}: no online fixed point in {iteration} iterations")


def run_cell_online(trace, heavy, context, entries, config, online, order, reference):
    """The scored policies of run_cell under the online clock; FCFS and SJF read no score,
    so their rows (`reference`) are shared with the original clock."""
    policies = [spjf(config["predictor"]["score_key"], config["predictor"]["policy_label"])]
    policies += [scaled_guard(entry, context["k"], config) for entry in entries]
    baseline = simulate(trace, fcfs(), context["k"])
    rows = []
    for policy, entry in zip(policies, [None, *entries]):
        score_rows, close = accoding_online.single_row_scorer(
            online["boosters"], score_columns(config)
        )
        start = accoding_online.online_scores(
            trace, policy, context["k"], online, order, score_rows
        )
        close()
        result, iterations = online_fixed_point(
            trace, policy, context["k"], online, order, config, start
        )
        checked = 0
        if policy.wrapper == "work":
            checked = assert_per_job_bounds(
                result, baseline.wait_us, policy, context["k"], trace.limit_s
            )
        row = result_row(result, baseline, heavy, context, config, policy, checked)
        row["score_definition"] += "; online"
        row["online_iterations"] = iterations
        row["promise_cb_s"] = entry["promise_s"] if entry else float("nan")
        row["promise_acc_s"] = (
            entry["promise_s"] * trace.limit_s / config["guard"]["codebench_limit_s"]
            if entry
            else float("nan")
        )
        for metric in ["mean", "p99"]:
            row[f"gap_closed_{metric}"] = gap_closed(
                reference[0][metric], row[metric], reference[1][metric]
            )
        rows.append(row)
    return rows


def make_trace(jobs, contests, anchors, shape, seed, config):
    settings = config["trace"]
    start, offset, _, _ = pre.build_trace(
        jobs,
        contests,
        shape,
        seed,
        settings["gamma"],
        settings["tau_h"],
        anchors,
        cap_h=settings["episode_cap_h"],
    )
    return start, offset


def scheduling(
    jobs, contests, anchors, scores, threshold, entries, config, anchor_name, log, online=None
):
    settings = config["trace"]
    service = np.minimum(
        jobs.time_cost.to_numpy(np.float64) / 1000 + settings["svc_fixed_s"],
        settings["service_cap_s"],
    )
    heavy = jobs.time_cost.to_numpy() > threshold
    tails = tail_row(service, "evaluated", "service", config["metrics"]["tail_fractions"])
    rows, calibrations = [], []
    for shape in settings["shapes"]:
        start, offset = make_trace(
            jobs, contests, anchors, shape, settings["calibration_seed"], config
        )
        scale = pre.calib_scale(start, offset, service, settings["busy_work_target_s"])
        work, _, _ = pre.busy_hour_work(pre.apply_scale(start, offset, scale), service)
        calibrations.append(
            {
                "anchor_rule": anchor_name,
                "shape": shape,
                "scale": scale,
                "calibration_busy_work_s": work,
                "calibration_seed": 300,
            }
        )
        log.p(f"Trace {anchor_name}/{shape}: scale={scale:.17g}, busy work={work:.6f} s")
        for seed in settings["seeds"]:
            start, offset = make_trace(jobs, contests, anchors, shape, seed, config)
            arrivals = pre.apply_scale(start, offset, scale)
            busy, _, _ = pre.busy_hour_work(arrivals, service)
            order = np.argsort(np.rint(arrivals * MICROS), kind="mergesort")
            trace = Trace.from_seconds(
                arrivals[order],
                service[order],
                {config["predictor"]["score_key"]: scores[order]},
                limit_s=settings["service_cap_s"],
            )
            for load in settings["loads"]:
                context = {
                    "anchor_rule": anchor_name,
                    "shape": shape,
                    "seed": seed,
                    "rho_target": load["rho"],
                    "rho_realised": busy / 3600 / load["k"],
                    "k": load["k"],
                    "scale": scale,
                    "n_jobs": len(jobs),
                    "top1_share": tails["top1_share"],
                    "top5_share": tails["top5_share"],
                }
                cell = run_cell(trace, heavy[order], context, entries, config)
                rows.extend(cell)
                if online is not None:
                    rows.extend(
                        run_cell_online(
                            trace, heavy[order], context, entries, config, online, order, cell
                        )
                    )
            log.p(f"Completed {anchor_name}/{shape}/seed={seed}, all loads and bounds")
    return pd.DataFrame(rows), pd.DataFrame(calibrations)


def summarise(metrics):
    keys = ["anchor_rule", "shape", "rho_target", "k", "policy", "score_definition"]
    summary = metrics.groupby(keys, sort=False).mean(numeric_only=True).reset_index()
    maxima = metrics.groupby(keys, sort=False)[["max_excess_s", "harm_s"]].max().reset_index()
    summary = summary.drop(columns=["max_excess_s", "harm_s"]).merge(maxima, on=keys)
    for _, indices in summary.groupby(keys[:4], sort=False).groups.items():
        part = summary.loc[indices].set_index("policy")
        for metric in ["mean", "p99"]:
            summary.loc[indices, f"gap_closed_{metric}"] = [
                gap_closed(part.loc["FCFS", metric], value, part.loc["SJF", metric])
                for value in summary.loc[indices, metric]
            ]
    return summary


def reproduction_rows(predictors, tails, reference):
    rows = []
    model_refs = {
        "M1": (0.8990, 0.4313),
        "M2": (0.7855, 0.2923),
        "M3": (0.7884, 0.1651),
        "M4": (0.9266, 0.5267),
        "M5": (0.9264, 0.5271),
    }
    for model, values in model_refs.items():
        current = predictors[
            (predictors.model == model)
            & (predictors.seed == "ensemble")
            & (predictors.group == "all")
        ].iloc[0]
        for metric, expected in zip(["auroc", "ap"], values):
            rows.append(
                {
                    "quantity": f"{model}_{metric}",
                    "precheck": expected,
                    "rehearsal": current[metric],
                    "source_decimals": 4,
                }
            )
    for kind, expected_values in [
        ("service", (0.122, 0.290)),
        ("measured_positive", (0.275, 0.628)),
    ]:
        current = tails[(tails.population == "development") & (tails.cost_kind == kind)].iloc[0]
        for metric, expected in zip(["top1_share", "top5_share"], expected_values):
            rows.append(
                {
                    "quantity": f"development_{kind}_{metric}",
                    "precheck": expected,
                    "rehearsal": current[metric],
                    "source_decimals": 3,
                }
            )
    subset = reference[(reference["shape"] == "poisson") & (reference.rho_target == 0.8)]
    for policy, metric, expected in [
        ("FCFS", "p99", 1.531),
        ("SJF", "p99", 0.623),
        ("SPJF-E", "p99", 0.641),
        ("SPJF-E", "gap_closed_p99", 0.980),
    ]:
        actual = subset[subset.policy == policy].iloc[0][metric]
        rows.append(
            {
                "quantity": f"poisson_rho0.8_{policy}_{metric}",
                "precheck": expected,
                "rehearsal": actual,
                "source_decimals": 3,
            }
        )
    frame = pd.DataFrame(rows)
    frame["difference"] = frame.rehearsal - frame.precheck
    frame["matches_printed_precision"] = [
        round(row.rehearsal, row.source_decimals) == row.precheck for row in frame.itertuples()
    ]
    return frame


def evaluate(block, params_path, out_dir, config, log, unseal, root=ROOT):
    development = load_development(config, root)
    tails = tail_rows(development, "development", config)
    df = development
    if block == "sealed":
        df = _append_authorized_sealed(development, config, params_path, unseal, root)
    block_number = 2 if block == "devtest" else 3
    selected = df.loc[df.blk == block_number]
    jobs = selected.loc[pre.modelling_mask(selected)].reset_index(drop=True)
    tails.extend(tail_rows(jobs, block, config))
    metadata = root / "data/accoding/parquet"
    prob = pd.read_parquet(metadata / "problems.parquet")
    contests = pd.read_parquet(metadata / "contests.parquet")
    ptag = pd.read_parquet(metadata / "problem_tags.parquet")
    features, indices, targets, heavy, blocks, threshold = make_features(
        df,
        prob,
        ptag,
        block_number,
        config,
        log,
    )
    assert np.array_equal(df.id.to_numpy()[indices[blocks == block_number]], jobs.id.to_numpy())
    predictors, scores, boosters = fit_predict(
        features, targets, heavy, blocks, block_number, config, log
    )
    del features, indices, targets, heavy, blocks
    history = pre.history_arrays(df, prob, ptag, threshold)
    in_block = df.blk.to_numpy() == block_number
    rows = np.flatnonzero(in_block & pre.modelling_mask(df).to_numpy())
    online = {
        "A": history,
        "state": pre.history_before(history, int(np.flatnonzero(in_block)[0])),
        "rows": rows,
        "boosters": boosters,
    }
    assert np.array_equal(df.id.to_numpy()[rows], jobs.id.to_numpy())
    anchors = block_anchors(df, contests)
    pd.DataFrame({"first_id": anchors[0], "calendar_s": anchors[1]}).to_csv(
        out_dir / "anchors.csv", index=False
    )
    entries = read_parameters(params_path, config)
    metrics, calibrations = scheduling(
        jobs, contests, anchors, scores, threshold, entries, config, "rows_to_block_end", log,
        online,
    )
    metrics.to_csv(out_dir / "metrics.csv", index=False)
    summarise(metrics).to_csv(out_dir / "summary.csv", index=False)
    tail_frame = pd.DataFrame(tails)
    if block == "devtest":
        legacy = pre.id_time_anchors(development, contests)
        comparison = compare_anchors(jobs, anchors, legacy)
        comparison.to_csv(out_dir / "anchor_comparison.csv", index=False)
        log.p(f"Anchor comparison: {comparison.to_dict('records')[0]}")
        reference, ref_cal = scheduling(
            jobs, contests, legacy, scores, threshold, [], config, "precheck_development", log
        )
        reference.to_csv(out_dir / "precheck_reference_metrics.csv", index=False)
        reference_summary = summarise(reference)
        reference_summary.to_csv(out_dir / "precheck_reference_summary.csv", index=False)
        reproduction_rows(predictors, tail_frame, reference_summary).to_csv(
            out_dir / "reproduction.csv", index=False
        )
        calibrations = pd.concat([calibrations, ref_cal], ignore_index=True)
    predictors.to_csv(out_dir / "predictor_metrics.csv", index=False)
    tail_frame.to_csv(out_dir / "tail_shares.csv", index=False)
    calibrations.to_csv(out_dir / "trace_calibration.csv", index=False)
    return {
        "evaluated_rows": len(selected),
        "evaluated_judged_rows": len(jobs),
        "development_max_id": int(development.id.max()),
        "heavy_threshold_ms": threshold,
        "development_filtered_sha256": filtered_fingerprint(development),
        "evaluated_filtered_sha256": filtered_fingerprint(selected),
        "submissions_read": "Arrow id predicate; whole submissions file never hashed",
        "predictor": config["predictor"],
        "trace_rules": config["trace"],
        "parameters": entries,
        "bound_job_checks": int(metrics.bounds_checked.sum()),
        "versions": runtime_versions(),
    }


def check_outputs(out_dir, promised):
    actual = sorted(
        path.relative_to(out_dir).as_posix() for path in out_dir.rglob("*") if path.is_file()
    )
    if actual != promised:
        raise RuntimeError(f"output list mismatch: expected {promised}, wrote {actual}")


def execute(args, config, root=ROOT):
    out_dir = args.out_dir.resolve()
    if out_dir.exists() and any(out_dir.iterdir()):
        raise FileExistsError(f"output directory is not empty: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)
    log = Log(out_dir / "run.log")
    try:
        log.p(f"ACcoding {args.block}; synthetic arrivals; historical M4 log1p score")
        notes = evaluate(args.block, args.params, out_dir, config, log, args.unseal, root)
        log.p("Completed all cells and per-job assertions")
    finally:
        log.close()
    inputs = [root / name for name in required_files(root, config)]
    inputs += [
        args.params,
        *[
            root / "data/accoding/parquet" / name
            for name in ["problems.parquet", "contests.parquet", "problem_tags.parquet"]
        ],
    ]
    names = output_names(args.block)
    if args.block == "sealed":
        inputs.append(root / LOCK_REL)
    provenance.write(
        out_dir,
        produced_by=SCRIPT_REL,
        config_path=root / CONFIG_REL,
        outputs=[out_dir / name for name in names if name != "manifest.json"],
        inputs=sorted(set(inputs)),
        arguments={
            "block": args.block,
            "params": provenance.relative_path(args.params),
            "out_dir": provenance.relative_path(out_dir),
            "unseal": args.unseal,
        },
        notes=notes,
    )
    check_outputs(out_dir, names)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--block", choices=["devtest", "sealed"], required=True)
    parser.add_argument("--params", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--unseal", action="store_true")
    args = parser.parse_args(argv)
    config = read_config()
    read_parameters(args.params, config)
    if args.block == "sealed":
        lock = authorize_sealed(config, args.params, args.unseal)
        with recording_accoding() as outcome:
            execute(args, config)
            check_outputs(args.out_dir, lock["outputs"])
            outcome.done(f"{args.out_dir.as_posix()}: {', '.join(lock['outputs'])}")
    else:
        execute(args, config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
