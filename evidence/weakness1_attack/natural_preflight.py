"""Freeze and replay one original-calendar CodeBench development window.

The script is deliberately self-contained and has no command-line choices.  It first
binds the development event cache and the stored ranking scores to their documented
hashes, then uses the project's guarded loader.  It never opens the sealed cache.  The
window is chosen only by offered capped work, before any policy is simulated.

Run from the repository root with:

    env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME \
      NUMBA_NUM_THREADS=4 OMP_NUM_THREADS=4 \
      uv run --no-sync python evidence/weakness1_attack/natural_preflight.py
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.dont_write_bytecode = True

# One process, one compute thread, and every runtime write confined to this directory.
for _key, _value in {
    "PYTHONDONTWRITEBYTECODE": "1",
    "NUMBA_NUM_THREADS": "1",
    "OMP_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "NUMBA_CACHE_DIR": str(HERE / "cache" / "natural_numba"),
    "TMP": str(HERE / "cache" / "tmp"),
    "TEMP": str(HERE / "cache" / "tmp"),
}.items():
    os.environ[_key] = _value
(HERE / "cache" / "natural_numba").mkdir(parents=True, exist_ok=True)
(HERE / "cache" / "tmp").mkdir(parents=True, exist_ok=True)

PINNED_SRC = HERE / "pinned_src"
NATURAL_SOURCE_HASHES = {
    "scripts/build_overlays.py": "bdd8fed9aaff36d003207df3d58becefe9cd45da4cf36e4afd13095368c4b4c3",
    "src/spjf_guard/config.py": "b3f13b89d146005fde6056c7c3117473803809fcaccf84c1b949c2434bbdf23c",
    "src/spjf_guard/data/events.py": "ecb6976c304b3c6cf4bac01ae71200618c1e9d5cce2a6cffccb418a784ba3457",
    "src/spjf_guard/data/clock.py": "a36e794d35013de599f9e64c70fbb387cdde9304b88d0e6ea83c365929832e5b",
    "src/spjf_guard/experiment/overlay.py": "3df7d213ec69f7d261891eb9663976ec09319a177f26ca1528386d2363fad9f5",
}
PINNED_PACKAGE_HASHES = {
    "spjf_guard/__init__.py": "8182c2e4e446ae77c480e188767d2d73ba698cc76e8f4e5d8e9912e054fed0e3",
    "spjf_guard/sim/__init__.py": "b4b0aa81eb8c907f469a21ba0bd3dc67a24c8842c6d5e97afaf7634a21489fdb",
    "spjf_guard/sim/bounds.py": "6bd64b495d3eb8408d4e466ce8b189101903f144a793dcfad1095fc2533d13f9",
    "spjf_guard/sim/kernel.py": "f70ad598ff79962a1eb2a6794130f2458fa5c093269ef3d67d4a51cd91800f88",
    "spjf_guard/sim/policy.py": "54309b5fd9f7df832484dc7e26755151e7b766c874906f505cc72345882b0e60",
    "spjf_guard/sim/reference.py": "26bcdd2cece39afd792faa807be7c414f1b21b16ff1e43e8cfe261c0ae86a9bc",
    "spjf_guard/sim/runner.py": "7e061794fde171b130dfadf1f0229959cb3612bab56fcef2921e239bb5a42ad7",
    "spjf_guard/sim/tightness.py": "7583d56cd7f7573e92e52fdc807390d68e4a044f8211c233d6d29117fc91fde6",
}


def _early_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _verify_and_prefer_frozen_source() -> dict:
    """Bind loader sources and put the baseline simulator ahead of current source."""
    drift_path = HERE / "source_drift.json"
    drift = json.loads(drift_path.read_text(encoding="utf-8"))
    if drift.get("status") != "PASS":
        raise RuntimeError("source_drift.json is not a passing baseline record")
    entries = {entry["path"]: entry for entry in drift["sources"]}
    for entry in entries.values():
        snapshot = HERE / entry["snapshot"]
        if _early_sha256(snapshot) != entry["baseline_sha256"]:
            raise RuntimeError(f"baseline source snapshot changed: {entry['snapshot']}")
        if entry["path"].startswith(("src/spjf_guard/data/", "src/spjf_guard/experiment/")):
            if _early_sha256(ROOT / entry["path"]) != entry["baseline_sha256"]:
                raise RuntimeError(f"project data interface changed: {entry['path']}")
    required_sim = {
        "src/spjf_guard/sim/runner.py",
        "src/spjf_guard/sim/kernel.py",
        "src/spjf_guard/sim/policy.py",
        "src/spjf_guard/sim/bounds.py",
    }
    if not required_sim.issubset(entries):
        raise RuntimeError("source_drift.json is missing a baseline simulation module")
    for project_path in required_sim:
        pinned_path = project_path.removeprefix("src/")
        entry = entries[project_path]
        expected = PINNED_PACKAGE_HASHES[pinned_path]
        if entry["baseline_sha256"] != expected:
            raise RuntimeError(f"baseline hash record changed: {project_path}")
        if entry["snapshot"] != f"pinned_src/{pinned_path}":
            raise RuntimeError(f"baseline snapshot path changed: {project_path}")
    for relative, expected in PINNED_PACKAGE_HASHES.items():
        if _early_sha256(PINNED_SRC / relative) != expected:
            raise RuntimeError(f"pinned simulation package changed: {relative}")
    for relative, expected in NATURAL_SOURCE_HASHES.items():
        if _early_sha256(ROOT / relative) != expected:
            raise RuntimeError(f"natural-window loader source changed: {relative}")
    return {
        "drift_record": "evidence/weakness1_attack/source_drift.json",
        "baseline_simulation_modules": sorted(required_sim),
        "pinned_package_hashes": PINNED_PACKAGE_HASHES,
        "natural_loader_hashes": NATURAL_SOURCE_HASHES,
    }


SOURCE_CODE_PROOF = _verify_and_prefer_frozen_source()
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np  # noqa: E402

import build_overlays as _build_module  # noqa: E402
import spjf_guard as _spjf_guard_package  # noqa: E402
from spjf_guard import config as cfgmod  # noqa: E402
from spjf_guard.data import sealed  # noqa: E402
from spjf_guard.data import clock as _clock_module  # noqa: E402
from spjf_guard.data import events as _events_module  # noqa: E402
from spjf_guard.data.events import arrival_and_availability  # noqa: E402
from spjf_guard.experiment import overlay as _overlay_module  # noqa: E402
from build_overlays import (  # noqa: E402
    clock_from,
    load_scores,
    pool_terms,
    prepare_everything,
)

_loaded_natural = {
    "build_overlays": Path(_build_module.__file__).resolve(),
    "config": Path(cfgmod.__file__).resolve(),
    "events": Path(_events_module.__file__).resolve(),
    "clock": Path(_clock_module.__file__).resolve(),
    "overlay": Path(_overlay_module.__file__).resolve(),
}
_expected_natural = {
    "build_overlays": (ROOT / "scripts" / "build_overlays.py").resolve(),
    "config": (ROOT / "src" / "spjf_guard" / "config.py").resolve(),
    "events": (ROOT / "src" / "spjf_guard" / "data" / "events.py").resolve(),
    "clock": (ROOT / "src" / "spjf_guard" / "data" / "clock.py").resolve(),
    "overlay": (ROOT / "src" / "spjf_guard" / "experiment" / "overlay.py").resolve(),
}
if _loaded_natural != _expected_natural:
    raise RuntimeError(f"natural loader resolved from unexpected paths: {_loaded_natural}")

# Loading current config.py necessarily imports the current simulation package because
# it exposes policy constructors.  The natural loader needs only Config and score-name
# constants.  Remove those simulation modules, prepend the verified frozen simulation
# directory to the already-loaded package path, and import the simulator again.  The
# replay below therefore uses the same baseline implementation as the physical study.
for _module_name in [
    name for name in tuple(sys.modules) if name == "spjf_guard.sim" or name.startswith("spjf_guard.sim.")
]:
    del sys.modules[_module_name]
if hasattr(_spjf_guard_package, "sim"):
    delattr(_spjf_guard_package, "sim")
_spjf_guard_package.__path__.insert(0, str(PINNED_SRC / "spjf_guard"))
sys.path.insert(0, str(PINNED_SRC))

from spjf_guard.sim import MICROS, Trace, simulate  # noqa: E402
from spjf_guard.sim import bounds as _bounds_module  # noqa: E402
from spjf_guard.sim import kernel as _kernel_module  # noqa: E402
from spjf_guard.sim import policy as _policy_module  # noqa: E402
from spjf_guard.sim import runner as _runner_module  # noqa: E402
from spjf_guard.sim.bounds import (  # noqa: E402
    assert_per_job_bounds,
    guard_upper_bound,
    residual_summary,
)
from spjf_guard.sim.policy import (  # noqa: E402
    bmax_for_promise,
    fcfs,
    guard,
    seconds_to_micros,
    spjf,
)

_loaded_simulation = {
    name: str(Path(module.__file__).resolve().relative_to(HERE)).replace("\\", "/")
    for name, module in {
        "bounds": _bounds_module,
        "kernel": _kernel_module,
        "policy": _policy_module,
        "runner": _runner_module,
    }.items()
}
if not all(value.startswith("pinned_src/") for value in _loaded_simulation.values()):
    raise RuntimeError(f"baseline simulator did not take precedence: {_loaded_simulation}")
SOURCE_CODE_PROOF["loaded_baseline_simulation"] = _loaded_simulation
SOURCE_CODE_PROOF["loaded_natural_modules"] = {
    name: str(path.relative_to(ROOT)).replace("\\", "/")
    for name, path in _loaded_natural.items()
}


EXPECTED_ALL_DEVELOPMENT = (
    "2018-1",
    "2018-2",
    "2019-1",
    "2019-2",
    "2020-ERE",
    "2020-1",
    "2020-2",
    "2021-1",
    "2021-2",
    "2022-1",
    "2022-2",
)
REQUESTED_TERMS = (
    "2020-ERE",
    "2020-2",
    "2021-1",
    "2021-2",
    "2022-1",
    "2022-2",
)

EVENT_PATH = ROOT / "data" / "derived" / "codebench_cache_r4" / "ev.parquet"
EVENT_BYTES = 67_391_982
EVENT_SHA256 = "8e37c80715369880ef7652b35f24e1bc15f41d72c47ac87aa3b2c1bd81739451"
SCORE_PATH = (
    ROOT / "data" / "derived" / "ranking_score_predictions" / "rs_pred_ires0.parquet"
)
SCORE_BYTES = 33_582_476
SCORE_SHA256 = "af90bb2d8cee4cf3e6806a3665fae356c1ea7d32cab52c724a7300706763bc92"
EXPECTED_EVENT_ROWS = 2_918_799
EXPECTED_EVENT_COLUMNS = 58
EXPECTED_SUBMISSION_ROWS = 863_149
EXPECTED_TARGET_SCORE_ROWS = 402_358
EXPECTED_SIMULATABLE_JOBS = 400_790
EXPECTED_CLOCK_CONFIG = {
    "reading": "result",
    "arrival_rule": "t - C",
    "done_rule": "t",
    "delta_s": 0.0,
    "test_block_outcome_lag_s": 60.0,
    "jitter": {
        "enabled": True,
        "key": "cbjitter20260919",
        "id_columns": ["semester", "class", "user", "assessment", "exercise", "blk_i"],
    },
    "limit_s": 60.0,
    "drop_zero_cost_terms": [
        "2020-ERE",
        "2020-1",
        "2020-2",
        "2021-1",
        "2021-2",
        "2022-1",
        "2022-2",
    ],
}
EXPECTED_PREPARATION_CONFIG = {
    "predictor_seed": 3,
    "train_terms": ["2018-1", "2018-2", "2019-1", "2019-2"],
    "deadline_window_s": 86_400.0,
}

WINDOW_S = 300.0
WINDOW_US = 300 * MICROS
K = 2
FORMAL_LIMIT_S = 61.0
RECORDED_CAP_S = 60.0
PROMISE_S = 300.0
B0_S = 30.0
ETA = 0.5
GAMMA_S = 0.0
SCORE_KEY = "tweedie"

INPUT_PATH = HERE / "natural_input.npz"
INPUT_METADATA_PATH = HERE / "natural_input_metadata.json"
REPLAY_PATH = HERE / "natural_replay.npz"
ESTIMATES_PATH = HERE / "natural_estimates.json"
RESOURCES_PATH = HERE / "natural_resources.json"
LOG_PATH = HERE / "out_natural_preflight.txt"

SOURCE_PROOF = {
    "event_rebuild": {
        "path": "outputs/prefreeze/prefreeze.log",
        "section": "lines 6-67 ([0b])",
        "command": (
            "scripts/build_cache.py --pool development --compare "
            "data/derived/codebench_cache_r4/ev.parquet"
        ),
        "result": "11 terms; 2,918,799 events; 58 columns; 58 of 58 columns equal",
        "column_report": "outputs/prefreeze/cache_columns.csv",
    },
    "event_hash": {
        "path": "protocol_lock.draft.json",
        "name": "inputs.artefacts[key=events_file]",
        "sha256": EVENT_SHA256,
        "bytes": EVENT_BYTES,
    },
    "score_origin": {
        "fit_source": "evidence/ranking_score/rs_fit.py",
        "fit_logs": [
            "evidence/ranking_score/out_fit_a.txt",
            "evidence/ranking_score/out_fit_b.txt",
        ],
        "artifact_manifest": "evidence/main_v3/out_main_v31.txt lines 24-33",
        "independent_manifest_check": (
            "evidence/main_v31_verify/out_manifest.txt lines 20-28"
        ),
        "scope": "six requested development targets; all other score rows are NaN",
    },
    "score_hash": {
        "path": "protocol_lock.draft.json",
        "name": "inputs.artefacts[key=score_predictions_file]",
        "sha256": SCORE_SHA256,
        "bytes": SCORE_BYTES,
    },
}

PARAMETERS = {
    "protocol_version": 1,
    "source": "original CodeBench development event cache",
    "all_guarded_terms": list(EXPECTED_ALL_DEVELOPMENT),
    "requested_terms": list(REQUESTED_TERMS),
    "unseal": False,
    "selection": (
        "largest offered C_cap sum among absolute-UTC 300 s bins after aggregating all "
        "six primary terms; a bin must be fully covered by at least one observed semester "
        "interval and touch no semester only partially at an observed edge; earliest bin "
        "breaks an exact work tie"
    ),
    "selection_uses_policy_outcomes": False,
    "overlay": False,
    "rebase": False,
    "replication": False,
    "thinning": False,
    "clock": EXPECTED_CLOCK_CONFIG,
    "clock_interpretation": (
        "result header; inferred arrival = whole-second ts + deterministic jitter - C"
    ),
    "preparation": EXPECTED_PREPARATION_CONFIG,
    "loader_call_chain": [
        "sealed.guard_semesters(all 11 development terms, unseal=False)",
        "sealed.guard_semesters(primary six terms, unseal=False)",
        "prepare_everything -> guard_semesters(primary six) -> "
        "load_events(ev.parquet, sealed_file=None) -> prepare -> "
        "static_submission_columns -> arrival_and_availability -> pool_inputs",
        "load_scores(rs_pred_ires0.parquet, positional row-count check)",
    ],
    "loader_side_effects": (
        "in-memory preparation only; no predictor fit and no project-tree write; "
        "Numba cache and outputs are confined to evidence/weakness1_attack"
    ),
    "window_s": WINDOW_S,
    "workers": K,
    "service": "C_cap = min(recorded exec_time, 60 s); zero-cost unsimulatable blocks omitted",
    "score": SCORE_KEY,
    "policies": ["FCFS", "SPJF-E", "Guard(300)"],
    "guard": {
        "G_s": PROMISE_S,
        "formal_L_s": FORMAL_LIMIT_S,
        "B0_s": B0_S,
        "eta": ETA,
        "gamma_s": GAMMA_S,
        "Bmax_s": bmax_for_promise(PROMISE_S, K, FORMAL_LIMIT_S),
    },
    "meaningful_followup_gate": {
        "fcfs_p99_wait_at_least_s": 3.0 * FORMAL_LIMIT_S,
        "top_1pct_work_share_at_least": 0.25,
        "guard_firing": "reported separately; required only for a full mechanism audit",
    },
}
PROTOCOL = hashlib.sha256(
    json.dumps(PARAMETERS, sort_keys=True, separators=(",", ":")).encode("utf-8")
).hexdigest()


class RunLog:
    def __init__(self, path: Path):
        self.handle = path.open("w", encoding="utf-8", buffering=1)

    def line(self, message: str) -> None:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        text = f"[{stamp}] {message}"
        print(text, flush=True)
        self.handle.write(text + "\n")

    def close(self) -> None:
        self.handle.close()


def json_safe(value):
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return [json_safe(item) for item in value.tolist()]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        value = float(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def atomic_json(path: Path, value) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(json_safe(value), indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="",
    )
    tmp.replace(path)


def atomic_npz(path: Path, **arrays) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("wb") as handle:
        np.savez(handle, **arrays)
    tmp.replace(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def require_fragments(path: Path, fragments: list[str]) -> None:
    text = path.read_text(encoding="utf-8")
    missing = [fragment for fragment in fragments if fragment not in text]
    require(not missing, f"source proof {path} is missing {missing!r}")


def development_terms(cfg) -> tuple[str, ...]:
    section = cfg["semesters"]
    return tuple(
        list(section["train"])
        + list(section["train_remote"])
        + list(section["validation"])
        + list(section["development_test"])
    )


def validate_text_provenance(cfg) -> dict:
    """Validate only text and metadata; no parquet file is opened here."""
    all_terms = development_terms(cfg)
    requested = tuple(pool_terms(cfg, "primary"))
    require(all_terms == EXPECTED_ALL_DEVELOPMENT, f"development terms changed: {all_terms}")
    require(requested == REQUESTED_TERMS, f"primary terms changed: {requested}")
    require(
        cfg.data_path("cache_dir") / cfg["data"]["events_file"] == EVENT_PATH,
        "event path changed",
    )
    configured_score = cfg.resolve(cfg["data"]["score_predictions_file"])
    require(configured_score == SCORE_PATH, "stored-score path changed")
    require(cfg["clock"] == EXPECTED_CLOCK_CONFIG, f"clock configuration changed: {cfg['clock']}")
    preparation = {
        "predictor_seed": int(cfg["predictor"]["seed"]),
        "train_terms": list(cfg["semesters"]["train"]),
        "deadline_window_s": float(cfg["metrics"]["deadline_window_s"]),
    }
    require(
        preparation == EXPECTED_PREPARATION_CONFIG,
        f"natural preparation configuration changed: {preparation}",
    )

    # Both guards run before either data artifact is hashed or parsed.  The first binds
    # the full cache scope; the second binds the requested natural pool.
    sealed.guard_semesters(all_terms, ROOT, unseal=False)
    sealed.guard_semesters(requested, ROOT, unseal=False)

    prefreeze = ROOT / "outputs" / "prefreeze" / "prefreeze.log"
    require_fragments(
        prefreeze,
        [
            "scripts/build_cache.py --pool development --compare "
            "data/derived/codebench_cache_r4/ev.parquet",
            "pool development: 11 terms, 2,918,799 events, 58 columns",
            "58 of 58 columns equal",
            "=== [0b] exit 0",
        ],
    )
    column_report = ROOT / "outputs" / "prefreeze" / "cache_columns.csv"
    with column_report.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    require(len(rows) == EXPECTED_EVENT_COLUMNS, "cache comparison does not list 58 columns")
    require(
        all(
            int(row["rows"]) == EXPECTED_EVENT_ROWS
            and row["status"] == "equal"
            and int(row["differing"]) == 0
            for row in rows
        ),
        "cache comparison contains a non-equal column or an unexpected row count",
    )
    require(any(row["column"] == "semester" for row in rows), "semester column was not compared")

    main_report = ROOT / "prechecks" / "main_v3" / "out_main_v31.txt"
    require_fragments(
        main_report,
        [
            f"cb_v2_cache_r4/ev.parquet                      {EVENT_SHA256}",
            f"rank_score/rs_pred_ires0.parquet               {SCORE_SHA256}",
            "DATA.  CodeBench development semesters only.",
            "2023-1, 2023-2 and 2024-1 were not opened.",
        ],
    )
    manifest_check = ROOT / "prechecks" / "main_v31_verify" / "out_manifest.txt"
    require_fragments(
        manifest_check,
        [
            "rank_score/rs_pred_ires0.parquet       af90bb2d8cee4cf3... report_match=True",
            "data artefact hash mismatches: 0",
        ],
    )
    fit_source = ROOT / "prechecks" / "ranking_score" / "rs_fit.py"
    require_fragments(
        fit_source,
        [
            "Targets: the six overlay-pool semesters POOL60.",
            "2023-1 / 2023-2 / 2024-1 are never read.",
            'out = {k: np.full(len(sidx), np.nan) for k in SCORES}',
        ],
    )
    require_fragments(
        ROOT / "prechecks" / "ranking_score" / "out_fit_a.txt",
        [
            "targets ['2020-ERE', '2020-2', '2021-1']",
            "2020-ERE   404578    147380",
            "2020-2   608171     49550",
            "2021-1   657721     57080",
        ],
    )
    require_fragments(
        ROOT / "prechecks" / "ranking_score" / "out_fit_b.txt",
        [
            "targets ['2021-2', '2022-1', '2022-2']",
            "2021-2   714801     55957",
            "2022-1   770758     51547",
            "2022-2   822305     40844",
        ],
    )

    lock = json.loads((ROOT / "protocol_lock.draft.json").read_text(encoding="utf-8"))
    artifacts = {row["key"]: row for row in lock["inputs"]["artefacts"]}
    expected = {
        "events_file": (EVENT_PATH, EVENT_BYTES, EVENT_SHA256),
        "score_predictions_file": (SCORE_PATH, SCORE_BYTES, SCORE_SHA256),
    }
    for key, (path, size, digest) in expected.items():
        row = artifacts.get(key)
        require(row is not None, f"protocol draft has no {key} artifact")
        require((ROOT / row["path"]).resolve() == path.resolve(), f"{key} path changed")
        require(row["bytes"] == size, f"{key} documented size changed")
        require(row["sha256"] == digest, f"{key} documented hash changed")

    return {
        "all_development_terms": list(all_terms),
        "requested_terms": list(requested),
        "prefreeze_column_rows": len(rows),
        "prefreeze_event_rows": EXPECTED_EVENT_ROWS,
        "clock": EXPECTED_CLOCK_CONFIG,
        "preparation": EXPECTED_PREPARATION_CONFIG,
        "source_proof": SOURCE_PROOF,
        "source_code_proof": SOURCE_CODE_PROOF,
    }


def bind_data_artifacts(log: RunLog) -> dict:
    """Hash the two documented development artifacts before either is parsed."""
    out = {}
    for name, path, size, expected_hash in (
        ("events_file", EVENT_PATH, EVENT_BYTES, EVENT_SHA256),
        ("score_predictions_file", SCORE_PATH, SCORE_BYTES, SCORE_SHA256),
    ):
        require(path.is_file(), f"missing {name}: {path}")
        require(path.stat().st_size == size, f"{name} size changed; refusing to parse")
        started = time.perf_counter()
        digest = sha256_file(path)
        require(digest == expected_hash, f"{name} hash changed; refusing to parse")
        out[name] = {
            "path": str(path.relative_to(ROOT)).replace("\\", "/"),
            "bytes": size,
            "sha256": digest,
            "hash_wall_s": time.perf_counter() - started,
        }
        log.line(f"bound {name}: {size} bytes sha256={digest}")
    return out


def utc_from_us(value: int) -> str:
    return datetime.fromtimestamp(value / MICROS, tz=timezone.utc).isoformat()


def freeze_natural_window(cfg, prepared, inputs, score_all: np.ndarray) -> tuple[dict, dict]:
    rows = prepared.submission_rows
    require(len(rows) == EXPECTED_SUBMISSION_ROWS, "prepared submission row count changed")
    submission_semester = np.asarray(prepared.semester[rows], dtype=str)
    target_score_mask = np.isin(submission_semester, REQUESTED_TERMS)
    finite_score = np.isfinite(score_all)
    require(
        np.array_equal(finite_score, target_score_mask),
        "finite Tweedie rows are not exactly the six requested development terms",
    )
    require(int(finite_score.sum()) == EXPECTED_TARGET_SCORE_ROWS, "target score count changed")
    require(np.all(score_all[finite_score] > 0), "a target Tweedie score is not positive")

    arrival_all, _ = arrival_and_availability(prepared, clock_from(cfg))
    submission_arrival = arrival_all[rows]
    job_row = np.flatnonzero(inputs.keep)
    require(len(job_row) == EXPECTED_SIMULATABLE_JOBS, "simulatable primary job count changed")
    require(
        set(submission_semester[job_row].tolist()) == set(REQUESTED_TERMS),
        "natural job rows contain an unexpected semester",
    )
    order = np.argsort(submission_arrival[job_row], kind="stable")
    job_row = job_row[order]
    arrival_us = np.rint(submission_arrival[job_row] * MICROS).astype(np.int64)
    service_us = np.rint(inputs.executed_work_s[job_row] * MICROS).astype(np.int64)
    score = np.asarray(score_all[job_row], np.float64)
    semester = submission_semester[job_row]
    class_term = np.asarray(prepared.class_term[rows][job_row], np.int64)

    require(np.all(np.diff(arrival_us) >= 0), "natural arrivals are not stably sorted")
    require(np.all(service_us > 0), "a simulatable job rounded to non-positive service")
    require(
        int(service_us.max()) <= seconds_to_micros(RECORDED_CAP_S),
        "a natural job exceeds the recorded 60 s cap",
    )
    require(np.isfinite(score).all(), "selected-pool score is missing or non-finite")

    coverage = []
    for term in REQUESTED_TERMS:
        index = np.flatnonzero(semester == term)
        require(index.size > 0, f"{term} has no simulatable jobs")
        coverage.append(
            {
                "semester": term,
                "first_arrival_us": int(arrival_us[index[0]]),
                "last_arrival_us": int(arrival_us[index[-1]]),
                "jobs": int(index.size),
            }
        )

    # Aggregate all six terms on their actual absolute calendar before choosing a bin.
    # A bin is complete when at least one term's observed interval covers it and no term
    # touches it only partially at an archive edge.  Every primary job in the winning
    # interval is retained, including jobs from overlapping semester labels.
    bin_id, inverse = np.unique(arrival_us // WINDOW_US, return_inverse=True)
    work = np.zeros(len(bin_id), np.int64)
    np.add.at(work, inverse, service_us)
    count = np.bincount(inverse)
    bin_start = bin_id * WINDOW_US
    full_coverage_count = np.zeros(len(bin_id), np.int16)
    partial_edge_count = np.zeros(len(bin_id), np.int16)
    for record in coverage:
        first = record["first_arrival_us"]
        last = record["last_arrival_us"]
        full = (bin_start >= first) & (bin_start + WINDOW_US <= last)
        overlaps = (bin_start <= last) & (bin_start + WINDOW_US > first)
        full_coverage_count += full
        partial_edge_count += overlaps & ~full
    complete = (full_coverage_count > 0) & (partial_edge_count == 0)
    require(complete.any(), "the six-term natural trace has no complete 300 s bin")
    eligible = np.flatnonzero(complete)
    best = int(eligible[np.argmax(work[eligible])])
    winner = {
        "bin_id": int(bin_id[best]),
        "start_us": int(bin_start[best]),
        "stop_us": int(bin_start[best] + WINDOW_US),
        "work_us": int(work[best]),
        "jobs": int(count[best]),
        "complete_bins": int(complete.sum()),
        "full_coverage_semesters": int(full_coverage_count[best]),
        "partial_edge_semesters": int(partial_edge_count[best]),
    }
    chosen = (arrival_us >= winner["start_us"]) & (arrival_us < winner["stop_us"])
    selected = np.flatnonzero(chosen)
    require(len(selected) == winner["jobs"], "selected job count disagrees with bin aggregate")
    require(
        int(service_us[selected].sum()) == winner["work_us"],
        "selected work disagrees with bin aggregate",
    )
    selected_terms = [term for term in REQUESTED_TERMS if np.any(semester[selected] == term)]
    selected_term_counts = {
        term: int((semester[selected] == term).sum()) for term in selected_terms
    }
    require(sum(selected_term_counts.values()) == len(selected), "selected term counts disagree")

    data = {
        "arrival_us": np.ascontiguousarray(arrival_us[selected]),
        "target_offset_us": np.ascontiguousarray(arrival_us[selected] - winner["start_us"]),
        "service_us": np.ascontiguousarray(service_us[selected]),
        "score": np.ascontiguousarray(score[selected]),
        "job_row": np.ascontiguousarray(job_row[selected], dtype=np.int64),
        "class_term": np.ascontiguousarray(class_term[selected], dtype=np.int64),
    }
    selection = {
        **winner,
        "start_utc": utc_from_us(winner["start_us"]),
        "stop_utc": utc_from_us(winner["stop_us"]),
        "first_arrival_offset_s": float(data["target_offset_us"][0] / MICROS),
        "last_arrival_offset_s": float(data["target_offset_us"][-1] / MICROS),
        "work_s": float(winner["work_us"] / MICROS),
        "work_per_worker_s": float(winner["work_us"] / (MICROS * K)),
        "work_over_window_capacity": float(winner["work_us"] / (WINDOW_US * K)),
        "work_only_drain_lower_bound_s": max(
            0.0, float(winner["work_us"] / (MICROS * K) - WINDOW_S)
        ),
        "class_terms": int(np.unique(data["class_term"]).size),
        "semesters": selected_terms,
        "semester_job_counts": selected_term_counts,
        "source_semester_coverage": coverage,
    }
    return data, selection


def max_waiting(arrival_us: np.ndarray, start_us: np.ndarray, wait_us: np.ndarray) -> int:
    """Maximum open intervals [arrival,start) among jobs that wait strictly positively."""
    positive = wait_us > 0
    if not positive.any():
        return 0
    event_time = np.concatenate([arrival_us[positive], start_us[positive]])
    event_delta = np.concatenate(
        [np.ones(int(positive.sum()), np.int64), -np.ones(int(positive.sum()), np.int64)]
    )
    order = np.lexsort((event_delta, event_time))  # departures (-1) before arrivals (+1)
    active = np.cumsum(event_delta[order])
    return int(active.max())


def wait_summary(result, arrival_us: np.ndarray, service_us: np.ndarray, bin_start_us: int) -> dict:
    wait_s = result.wait_us / MICROS
    completion_us = result.start_us + service_us
    return {
        "jobs": int(len(wait_s)),
        "mean_wait_s": float(wait_s.mean()),
        "p50_wait_s": float(np.quantile(wait_s, 0.50)),
        "p90_wait_s": float(np.quantile(wait_s, 0.90)),
        "p99_wait_s": float(np.quantile(wait_s, 0.99)),
        "max_wait_s": float(wait_s.max()),
        "positive_wait_jobs": int((result.wait_us > 0).sum()),
        "positive_wait_share": float((result.wait_us > 0).mean()),
        "max_waiting_open_intervals": max_waiting(arrival_us, result.start_us, result.wait_us),
        "nominal_completion_from_window_start_s": float(
            (completion_us.max() - bin_start_us) / MICROS
        ),
        "nominal_drain_after_release_window_s": max(
            0.0, float((completion_us.max() - bin_start_us) / MICROS - WINDOW_S)
        ),
    }


def run_replays(data: dict, selection: dict, log: RunLog) -> tuple[dict, dict]:
    trace = Trace(
        arrival_us=data["arrival_us"],
        service_us=data["service_us"],
        scores={SCORE_KEY: data["score"]},
        limit_s=FORMAL_LIMIT_S,
    )
    policies = (
        fcfs(),
        spjf(SCORE_KEY, name="SPJF-E"),
        guard(
            promise_s=PROMISE_S,
            k=K,
            limit_s=FORMAL_LIMIT_S,
            b0_s=B0_S,
            eta=ETA,
            score_key=SCORE_KEY,
            name="Guard(300)",
            gam_s=GAMMA_S,
        ),
    )
    results = {}
    policy_resources = {}
    for policy in policies:
        wall0, cpu0 = time.perf_counter(), time.process_time()
        result = simulate(trace, policy, K)
        results[policy.name] = result
        policy_resources[policy.name] = {
            "wall_s": time.perf_counter() - wall0,
            "cpu_s": time.process_time() - cpu0,
        }
        log.line(
            f"replayed {policy.name}: jobs={len(trace)} "
            f"p99={np.quantile(result.wait_us / MICROS, 0.99):.6f}s"
        )

    fcfs_result = results["FCFS"]
    spjf_result = results["SPJF-E"]
    guard_result = results["Guard(300)"]
    guard_policy = policies[2]
    checked = assert_per_job_bounds(
        guard_result,
        fcfs_result.wait_us,
        guard_policy,
        K,
        FORMAL_LIMIT_S,
        tolerance_s=0.0,
    )
    bound_s = guard_upper_bound(fcfs_result.wait_us, guard_policy, K, FORMAL_LIMIT_S)
    violation_s = guard_result.wait_us / MICROS - bound_s
    excess_us = guard_result.wait_us - fcfs_result.wait_us
    require(
        int(excess_us.max()) <= seconds_to_micros(PROMISE_S),
        "Guard exceeded its 300 s per-job excess-wait promise",
    )
    bound = {
        "jobs_checked": int(checked),
        "checked_even_if_no_guard_epoch_fired": True,
        "guard_firing_epochs": int(guard_result.n_forced),
        "guard_fired": bool(guard_result.n_forced > 0),
        "violations": int((violation_s > 0).sum()),
        "max_violation_s": float(violation_s.max()),
        "max_excess_over_fcfs_s": float(excess_us.max() / MICROS),
        "promise_s": PROMISE_S,
        "bound_formula": (
            "min((W_FCFS + B0/k + (3-2/k)L)/(1-eta), "
            "W_FCFS + Bmax/k + (3-2/k)L)"
        ),
        "identity": residual_summary(
            guard_result.wait_us,
            fcfs_result.wait_us,
            data["service_us"],
            guard_result.dispatch_order,
            K,
            FORMAL_LIMIT_S,
            start_us=guard_result.start_us,
        ),
    }
    require(bound["violations"] == 0, "per-job guard bound has a violation")

    summaries = {
        name: wait_summary(
            result, data["arrival_us"], data["service_us"], selection["start_us"]
        )
        for name, result in results.items()
    }
    for name, result in results.items():
        summaries[name]["dispatches"] = int(result.n_dispatch)
        summaries[name]["guard_firing_epochs"] = (
            int(result.n_forced) if name == "Guard(300)" else None
        )
        summaries[name]["guard_firing_fraction"] = (
            float(result.fired_fraction) if name == "Guard(300)" else None
        )

    n = len(data["service_us"])
    descending = np.sort(data["service_us"])[::-1]
    top1 = max(1, int(math.ceil(n * 0.01)))
    top5 = max(1, int(math.ceil(n * 0.05)))
    total_work = int(descending.sum())
    top1_share = float(descending[:top1].sum() / total_work)
    top5_share = float(descending[:top5].sum() / total_work)
    fcfs_p99 = summaries["FCFS"]["p99_wait_s"]
    meaningful_candidate = bool(
        fcfs_p99 >= 3.0 * FORMAL_LIMIT_S and top1_share >= 0.25
    )
    estimates = {
        "protocol": PROTOCOL,
        "parameters": PARAMETERS,
        "selection": selection,
        "cost_concentration": {
            "top_1pct_jobs": top1,
            "top_1pct_work_share": top1_share,
            "top_5pct_jobs": top5,
            "top_5pct_work_share": top5_share,
        },
        "policies": summaries,
        "guard_bound": bound,
        "followup_screens": {
            "fcfs_p99_positive": bool(fcfs_p99 > 0.0),
            "fcfs_p99_at_least_3L": bool(fcfs_p99 >= 3.0 * FORMAL_LIMIT_S),
            "top_1pct_work_share_at_least_0_25": bool(top1_share >= 0.25),
            "guard_fired": bool(guard_result.n_forced > 0),
            "meaningful_candidate": meaningful_candidate,
            "full_mechanism_audit_candidate": bool(
                meaningful_candidate and guard_result.n_forced > 0
            ),
            "gate_note": (
                "The meaningful-candidate gate uses only FCFS congestion and true-cost "
                "concentration after the demand-only window is frozen. Guard firing is a "
                "secondary requirement for a full mechanism audit; no SPJF or Guard benefit "
                "selects the window."
            ),
        },
    }
    replay = {
        "fcfs_wait_us": fcfs_result.wait_us,
        "fcfs_start_us": fcfs_result.start_us,
        "fcfs_dispatch_index": fcfs_result.dispatch_index,
        "spjf_wait_us": spjf_result.wait_us,
        "spjf_start_us": spjf_result.start_us,
        "spjf_dispatch_index": spjf_result.dispatch_index,
        "guard_wait_us": guard_result.wait_us,
        "guard_start_us": guard_result.start_us,
        "guard_dispatch_index": guard_result.dispatch_index,
        "guard_bound_s": np.asarray(bound_s, np.float64),
    }
    return estimates, {"arrays": replay, "resources": policy_resources}


def main() -> int:
    if len(sys.argv) != 1:
        raise SystemExit("this frozen preflight accepts no command-line arguments")
    started_wall, started_cpu = time.perf_counter(), time.process_time()
    log = RunLog(LOG_PATH)
    resources = {
        "protocol": PROTOCOL,
        "status": "running",
        "processes": 1,
        "children": 0,
        "configured_compute_threads": 1,
        "phases": {},
    }
    try:
        log.line(f"natural preflight protocol={PROTOCOL}")
        cfg = cfgmod.load(ROOT / "configs" / "main.yaml")

        wall0, cpu0 = time.perf_counter(), time.process_time()
        proof = validate_text_provenance(cfg)
        resources["phases"]["text_provenance"] = {
            "wall_s": time.perf_counter() - wall0,
            "cpu_s": time.process_time() - cpu0,
        }
        log.line("text provenance and both development-term guards passed")

        wall0, cpu0 = time.perf_counter(), time.process_time()
        artifacts = bind_data_artifacts(log)
        resources["phases"]["hash_binding"] = {
            "wall_s": time.perf_counter() - wall0,
            "cpu_s": time.process_time() - cpu0,
        }

        # prepare_everything passes sealed_file=None because unseal is literally False.
        # It performs no predictor fit and writes nothing.  Its overlay-ready per-term
        # base shifts are not used below; selection uses only the direct natural arrival,
        # keep mask and capped service arrays.
        wall0, cpu0 = time.perf_counter(), time.process_time()
        prepared, inputs = prepare_everything(cfg, list(REQUESTED_TERMS), False)
        scores = load_scores(cfg, len(prepared.submission_rows), path=SCORE_PATH, wanted=True)
        require(SCORE_KEY in scores, f"stored scores have no {SCORE_KEY!r} column")
        data, selection = freeze_natural_window(cfg, prepared, inputs, scores[SCORE_KEY])
        resources["phases"]["guarded_load_and_selection"] = {
            "wall_s": time.perf_counter() - wall0,
            "cpu_s": time.process_time() - cpu0,
        }
        log.line(
            f"selected terms={selection['semesters']} {selection['start_utc']} "
            f"jobs={selection['jobs']} work={selection['work_s']:.6f}s"
        )

        atomic_npz(INPUT_PATH, **data)
        input_sha256 = sha256_file(INPUT_PATH)

        wall0, cpu0 = time.perf_counter(), time.process_time()
        estimates, replay_run = run_replays(data, selection, log)
        resources["phases"]["three_policy_replay_and_bounds"] = {
            "wall_s": time.perf_counter() - wall0,
            "cpu_s": time.process_time() - cpu0,
        }
        resources["policy_replays"] = replay_run["resources"]
        atomic_npz(REPLAY_PATH, **replay_run["arrays"])
        replay_sha256 = sha256_file(REPLAY_PATH)

        metadata = {
            "protocol": PROTOCOL,
            "parameters": PARAMETERS,
            "source_proof": proof,
            "bound_artifacts": artifacts,
            "selection": selection,
            "input": {
                "path": INPUT_PATH.name,
                "bytes": INPUT_PATH.stat().st_size,
                "sha256": input_sha256,
                "arrays": sorted(data),
            },
            "replay": {
                "path": REPLAY_PATH.name,
                "bytes": REPLAY_PATH.stat().st_size,
                "sha256": replay_sha256,
                "arrays": sorted(replay_run["arrays"]),
            },
            "scope": (
                "one demand-selected original-calendar inferred-arrival window; no overlay, "
                "time shift, rebase, replication, thinning, or time compression"
            ),
        }
        atomic_json(INPUT_METADATA_PATH, metadata)
        atomic_json(ESTIMATES_PATH, estimates)

        policy_completion = {
            name: row["nominal_completion_from_window_start_s"]
            for name, row in estimates["policies"].items()
        }
        resources.update(
            {
                "status": "PASS",
                "wall_s": time.perf_counter() - started_wall,
                "cpu_s": time.process_time() - started_cpu,
                "nominal_physical_policy_wall_estimates_s": policy_completion,
                "nominal_sequential_physical_wall_estimate_s": float(
                    sum(policy_completion.values())
                ),
                "artifacts": {
                    path.name: {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
                    for path in (INPUT_PATH, INPUT_METADATA_PATH, REPLAY_PATH, ESTIMATES_PATH)
                },
            }
        )
        atomic_json(RESOURCES_PATH, resources)
        log.line(
            f"PASS wall={resources['wall_s']:.3f}s cpu={resources['cpu_s']:.3f}s "
            f"meaningful={estimates['followup_screens']['meaningful_candidate']} "
            f"full_mechanism="
            f"{estimates['followup_screens']['full_mechanism_audit_candidate']}"
        )
        return 0
    except BaseException as exc:
        resources.update(
            {
                "status": "FAILED",
                "wall_s": time.perf_counter() - started_wall,
                "cpu_s": time.process_time() - started_cpu,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
        )
        atomic_json(RESOURCES_PATH, resources)
        log.line(f"FAILED {type(exc).__name__}: {exc}")
        raise
    finally:
        log.close()


if __name__ == "__main__":
    raise SystemExit(main())
