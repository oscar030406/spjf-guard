"""Run the timed-work service on a gate-passing frozen natural-calendar input.

This is a thin configuration layer over physical_service.py.  It performs no source
data reconstruction and refuses to create a run directory unless the completed
natural preflight is internally bound and its meaningful-candidate gate is true.
"""

from __future__ import annotations

import hashlib
import json
import multiprocessing as mp
import os
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
RUN_DIR = HERE / "natural_physical"
PINNED_SRC = HERE / "pinned_src"
NATURAL_INPUT = HERE / "natural_input.npz"
NATURAL_METADATA = HERE / "natural_input_metadata.json"
NATURAL_ESTIMATES = HERE / "natural_estimates.json"
NATURAL_REPLAY = HERE / "natural_replay.npz"
NATURAL_RESOURCES = HERE / "natural_resources.json"
sys.dont_write_bytecode = True

EXPECTED_PHYSICAL_SERVICE_SHA256 = (
    "a69d2f25ad344219a5d5d60bb2d556ebd8ab63d69d9b6690b6e32fb3e06a02e1"
)
EXPECTED_NATURAL_PREFLIGHT_SHA256 = (
    "de88ce4494db6b3c8a9f221c3711240cf8b390b316436f032bc4867a0e5672f0"
)
EXPECTED_REQUESTED_TERMS = [
    "2020-ERE",
    "2020-2",
    "2021-1",
    "2021-2",
    "2022-1",
    "2022-2",
]
EXPECTED_INPUT_ARRAYS = {
    "arrival_us",
    "target_offset_us",
    "service_us",
    "score",
    "job_row",
    "class_term",
}
EXPECTED_DATA_ARTIFACTS = {
    "events_file": {
        "bytes": 67_391_982,
        "sha256": "8e37c80715369880ef7652b35f24e1bc15f41d72c47ac87aa3b2c1bd81739451",
    },
    "score_predictions_file": {
        "bytes": 33_582_476,
        "sha256": "af90bb2d8cee4cf3e6806a3665fae356c1ea7d32cab52c724a7300706763bc92",
    },
}
EXPECTED_PINNED_PACKAGE_HASHES = {
    "spjf_guard/__init__.py": "8182c2e4e446ae77c480e188767d2d73ba698cc76e8f4e5d8e9912e054fed0e3",
    "spjf_guard/sim/__init__.py": "b4b0aa81eb8c907f469a21ba0bd3dc67a24c8842c6d5e97afaf7634a21489fdb",
    "spjf_guard/sim/reference.py": "26bcdd2cece39afd792faa807be7c414f1b21b16ff1e43e8cfe261c0ae86a9bc",
    "spjf_guard/sim/tightness.py": "7583d56cd7f7573e92e52fdc807390d68e4a044f8211c233d6d29117fc91fde6",
}
EXPECTED_BASELINE_SIM_HASHES = {
    "spjf_guard/sim/runner.py": "b1921178d8afaae8da95cdf9518c8aaef23fe0faeae9151cb8c5aa9393aa5df9",
    "spjf_guard/sim/kernel.py": "f70ad598ff79962a1eb2a6794130f2458fa5c093269ef3d67d4a51cd91800f88",
    "spjf_guard/sim/policy.py": "54309b5fd9f7df832484dc7e26755151e7b766c874906f505cc72345882b0e60",
    "spjf_guard/sim/bounds.py": "6bd64b495d3eb8408d4e466ce8b189101903f144a793dcfad1095fc2533d13f9",
}
EXPECTED_NATURAL_LOADER_HASHES = {
    "scripts/build_overlays.py": "bdd8fed9aaff36d003207df3d58becefe9cd45da4cf36e4afd13095368c4b4c3",
    "src/spjf_guard/config.py": "b3f13b89d146005fde6056c7c3117473803809fcaccf84c1b949c2434bbdf23c",
    "src/spjf_guard/data/events.py": "ecb6976c304b3c6cf4bac01ae71200618c1e9d5cce2a6cffccb418a784ba3457",
    "src/spjf_guard/data/clock.py": "a36e794d35013de599f9e64c70fbb387cdde9304b88d0e6ea83c365929832e5b",
    "src/spjf_guard/experiment/overlay.py": "3df7d213ec69f7d261891eb9663976ec09319a177f26ca1528386d2363fad9f5",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    require(path.is_file(), f"missing required preflight artifact: {path.name}")
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{path.name} is not a JSON object")
    return value


def validate_sources(metadata: dict) -> None:
    require(
        sha256_file(HERE / "physical_service.py") == EXPECTED_PHYSICAL_SERVICE_SHA256,
        "physical_service.py changed after wrapper review",
    )
    require(
        sha256_file(HERE / "natural_preflight.py") == EXPECTED_NATURAL_PREFLIGHT_SHA256,
        "natural_preflight.py changed after wrapper review",
    )
    proof = metadata["source_proof"]["source_code_proof"]
    require(
        proof["pinned_package_hashes"] == EXPECTED_PINNED_PACKAGE_HASHES,
        "preflight pinned-package metadata changed",
    )
    require(
        proof["natural_loader_hashes"] == EXPECTED_NATURAL_LOADER_HASHES,
        "preflight natural-loader metadata changed",
    )
    loaded = proof["loaded_baseline_simulation"]
    require(
        set(loaded) == {"bounds", "kernel", "policy", "runner"}
        and all(value.startswith("pinned_src/") for value in loaded.values()),
        "preflight did not record the frozen simulator as loaded",
    )
    require(
        proof["baseline_simulation_modules"]
        == sorted(
            [
                "src/spjf_guard/sim/runner.py",
                "src/spjf_guard/sim/kernel.py",
                "src/spjf_guard/sim/policy.py",
                "src/spjf_guard/sim/bounds.py",
            ]
        ),
        "preflight baseline simulator module set changed",
    )
    for relative, expected in {
        **EXPECTED_PINNED_PACKAGE_HASHES,
        **EXPECTED_BASELINE_SIM_HASHES,
    }.items():
        path = PINNED_SRC / relative
        require(path.is_file(), f"missing pinned source: {relative}")
        require(sha256_file(path) == expected, f"pinned source changed: {relative}")


def validate_preflight() -> dict:
    """Read-only gate and provenance validation; creates no output directory."""
    resources = read_json(NATURAL_RESOURCES)
    require(resources.get("status") == "PASS", "natural preflight did not pass")
    require(resources.get("processes") == 1, "natural preflight process count changed")
    require(resources.get("children") == 0, "natural preflight unexpectedly used children")

    paths = {
        NATURAL_INPUT.name: NATURAL_INPUT,
        NATURAL_METADATA.name: NATURAL_METADATA,
        NATURAL_REPLAY.name: NATURAL_REPLAY,
        NATURAL_ESTIMATES.name: NATURAL_ESTIMATES,
    }
    artifact_rows = resources.get("artifacts", {})
    artifact_hashes = {}
    for name, path in paths.items():
        require(path.is_file(), f"missing natural preflight artifact: {name}")
        row = artifact_rows.get(name)
        require(isinstance(row, dict), f"natural resources do not bind {name}")
        require(path.stat().st_size == row.get("bytes"), f"{name} size changed")
        digest = sha256_file(path)
        require(digest == row.get("sha256"), f"{name} hash changed")
        artifact_hashes[name] = digest

    metadata = read_json(NATURAL_METADATA)
    estimates = read_json(NATURAL_ESTIMATES)
    protocol = metadata.get("protocol")
    require(isinstance(protocol, str) and len(protocol) == 64, "invalid preflight protocol")
    require(resources.get("protocol") == protocol, "resource/preflight protocol mismatch")
    require(estimates.get("protocol") == protocol, "estimate/preflight protocol mismatch")
    require(
        estimates.get("parameters") == metadata.get("parameters"),
        "metadata and estimates use different parameters",
    )
    require(
        estimates.get("selection") == metadata.get("selection"),
        "metadata and estimates bind different selected windows",
    )

    parameters = metadata["parameters"]
    require(parameters.get("protocol_version") == 1, "unexpected preflight version")
    require(
        parameters.get("source") == "original CodeBench development event cache",
        "preflight source is not the original-calendar development cache",
    )
    require(parameters.get("requested_terms") == EXPECTED_REQUESTED_TERMS, "term set changed")
    for key in ("overlay", "rebase", "replication", "thinning"):
        require(parameters.get(key) is False, f"natural preflight unexpectedly sets {key}")
    require(parameters.get("selection_uses_policy_outcomes") is False, "policy-selected window")
    require(parameters.get("window_s") == 300.0, "natural window is not 300 seconds")
    require(parameters.get("workers") == 2, "natural preflight is not a two-worker design")
    require(
        parameters.get("policies") == ["FCFS", "SPJF-E", "Guard(300)"],
        "natural preflight policy family changed",
    )
    require(
        parameters.get("guard")
        == {
            "G_s": 300.0,
            "formal_L_s": 61.0,
            "B0_s": 30.0,
            "eta": 0.5,
            "gamma_s": 0.0,
            "Bmax_s": 356.0,
        },
        "natural preflight guard parameters changed",
    )

    require(
        metadata["input"].get("path") == NATURAL_INPUT.name,
        "natural metadata names another input",
    )
    require(
        metadata["input"].get("sha256") == artifact_hashes[NATURAL_INPUT.name],
        "natural metadata/input hash mismatch",
    )
    require(
        metadata["input"].get("bytes") == NATURAL_INPUT.stat().st_size,
        "natural metadata/input size mismatch",
    )
    require(
        set(metadata["input"].get("arrays", [])) == EXPECTED_INPUT_ARRAYS,
        "natural input schema changed",
    )
    for name, expected in EXPECTED_DATA_ARTIFACTS.items():
        observed = metadata["bound_artifacts"].get(name)
        require(isinstance(observed, dict), f"preflight did not bind {name}")
        require(observed.get("bytes") == expected["bytes"], f"{name} size metadata changed")
        require(
            observed.get("sha256") == expected["sha256"],
            f"{name} hash metadata changed",
        )

    screens = estimates["followup_screens"]
    fcfs_p99 = float(estimates["policies"]["FCFS"]["p99_wait_s"])
    top1_share = float(estimates["cost_concentration"]["top_1pct_work_share"])
    expected_gate = bool(fcfs_p99 >= 3.0 * 61.0 and top1_share >= 0.25)
    require(
        bool(screens.get("fcfs_p99_at_least_3L")) == (fcfs_p99 >= 183.0),
        "FCFS p99 screen is internally inconsistent",
    )
    require(
        bool(screens.get("top_1pct_work_share_at_least_0_25"))
        == (top1_share >= 0.25),
        "work-concentration screen is internally inconsistent",
    )
    require(
        bool(screens.get("meaningful_candidate")) == expected_gate,
        "meaningful-candidate gate is internally inconsistent",
    )
    require(expected_gate, "natural original-calendar workload gate did not pass")

    validate_sources(metadata)
    return {
        "resources": resources,
        "metadata": metadata,
        "estimates": estimates,
        "artifact_hashes": artifact_hashes,
        "gate": {
            "fcfs_p99_wait_s": fcfs_p99,
            "fcfs_p99_threshold_s": 183.0,
            "top_1pct_work_share": top1_share,
            "top_1pct_work_share_threshold": 0.25,
            "meaningful_candidate": True,
            "guard_fired_in_nominal_replay": bool(screens.get("guard_fired")),
            "full_mechanism_audit_candidate": bool(
                screens.get("full_mechanism_audit_candidate")
            ),
        },
    }


def load_and_transform_input(bundle: dict) -> dict:
    """Validate the frozen arrays, then apply only exact microsecond-to-ns conversion."""
    import numpy as np

    with np.load(NATURAL_INPUT, allow_pickle=False) as store:
        require(set(store.files) == EXPECTED_INPUT_ARRAYS, "natural NPZ schema changed")
        source = {name: np.asarray(store[name]).copy() for name in store.files}
    require(
        sha256_file(NATURAL_INPUT) == bundle["artifact_hashes"][NATURAL_INPUT.name],
        "natural input changed while it was being loaded",
    )
    lengths = {name: len(value) for name, value in source.items()}
    require(len(set(lengths.values())) == 1, f"natural arrays have different lengths: {lengths}")
    jobs = next(iter(lengths.values()))
    selection = bundle["metadata"]["selection"]
    require(jobs == int(selection["jobs"]) and jobs > 0, "natural job count mismatch")
    for name in ("arrival_us", "target_offset_us", "service_us", "job_row", "class_term"):
        require(np.issubdtype(source[name].dtype, np.integer), f"{name} is not integer")
    require(np.issubdtype(source["score"].dtype, np.floating), "score is not floating point")
    arrival_us = source["arrival_us"].astype(np.int64, copy=False)
    offset_us = source["target_offset_us"].astype(np.int64, copy=False)
    service_us = source["service_us"].astype(np.int64, copy=False)
    require(np.all(np.diff(arrival_us) >= 0), "natural arrivals are not rank ordered")
    require(np.all(np.diff(offset_us) >= 0), "natural offsets are not rank ordered")
    require(
        np.array_equal(arrival_us - int(selection["start_us"]), offset_us),
        "natural target offsets do not match absolute arrivals",
    )
    require(int(offset_us.min()) >= 0 and int(offset_us.max()) < 300_000_000,
            "natural release lies outside the selected 300-second bin")
    require(np.all(service_us > 0) and int(service_us.max()) <= 60_000_000,
            "natural service is outside (0, 60 s]")
    require(np.isfinite(source["score"]).all() and np.all(source["score"] > 0),
            "natural scores are not finite and positive")
    require(len(np.unique(source["job_row"])) == jobs, "natural source rows are not unique")
    require(int(service_us.sum()) == int(selection["work_us"]), "natural work sum changed")

    return {
        "job_id": np.arange(jobs, dtype=np.int64),
        # source_rank stores the immutable original submission-row identity.  The
        # scheduler's arrival rank remains job_id, exactly as in physical_service.py.
        "source_rank": np.ascontiguousarray(source["job_row"], dtype=np.int64),
        "target_release_offset_ns": np.ascontiguousarray(offset_us * 1000, dtype=np.int64),
        "requested_service_ns": np.ascontiguousarray(service_us * 1000, dtype=np.int64),
        "score": np.ascontiguousarray(source["score"], dtype=np.float64),
        # A cross-semester natural bin has no single assessment deadline window.
        "in_deadline_window": np.zeros(jobs, dtype=bool),
    }


def physical_parameters(bundle: dict) -> dict:
    """Return the independently recomputable natural-physical protocol parameters."""
    return {
        "protocol_version": 3,
        "source": "frozen original-calendar natural_input.npz",
        "upstream_preflight_protocol": bundle["metadata"]["protocol"],
        "upstream_input_sha256": bundle["artifact_hashes"][NATURAL_INPUT.name],
        "upstream_metadata_sha256": bundle["artifact_hashes"][NATURAL_METADATA.name],
        "selection": bundle["metadata"]["parameters"]["selection"],
        "selection_uses_policy_outcomes": False,
        "followup_gate_uses_nominal_fcfs_and_cost_concentration": True,
        "window_s": 300.0,
        "workers": 2,
        "policies": ["FCFS", "SPJF-E", "Guard(300)"],
        "policy_order": "sequential",
        "requested_service": "frozen natural C_cap, exact us-to-ns conversion, at most 60 s",
        "arrival_spacing": "frozen natural target_offset_us, exact us-to-ns conversion",
        "guard": {
            "G_s": 300.0,
            "formal_L_s": 61.0,
            "B0_s": 30.0,
            "eta": 0.5,
            "gamma_s": 0.0,
            "Bmax_s": 356.0,
        },
        "clock": "time.perf_counter_ns (system-wide monotonic QPC on Windows)",
        "service_for_guard": "worker_finish_ns - worker_start_ns, learned at completion receipt",
        "compatibility_deadline_field": "all false; no common deadline window is defined",
    }


def physical_protocol(bundle: dict) -> str:
    return hashlib.sha256(
        json.dumps(physical_parameters(bundle), sort_keys=True).encode("utf-8")
    ).hexdigest()


def configure_and_run(bundle: dict, data: dict) -> int:
    """Configure parent-process globals, then delegate scheduling and audits unchanged."""
    expected_runtime = (RUN_DIR / "cache").resolve()
    configured_runtime = os.environ.get("SPJF_PHYSICAL_RUNTIME_ROOT")
    if configured_runtime is not None:
        require(
            Path(configured_runtime).resolve() == expected_runtime,
            "SPJF_PHYSICAL_RUNTIME_ROOT points outside the dedicated natural run",
        )
    os.environ["SPJF_PHYSICAL_RUNTIME_ROOT"] = str(expected_runtime)
    sys.path.insert(0, str(HERE))
    sys.path.insert(0, str(PINNED_SRC))

    import physical_service as physical

    RUN_DIR.mkdir(parents=False, exist_ok=True)
    parameters = physical_parameters(bundle)
    protocol = physical_protocol(bundle)
    selection = bundle["metadata"]["selection"]
    offered_work_s = sum(int(value) for value in data["requested_service_ns"]) / 1e9
    run_metadata = {
        "protocol": protocol,
        "parameters": parameters,
        "source_preflight_protocol": bundle["metadata"]["protocol"],
        "source_input_path": NATURAL_INPUT.name,
        "source_input_sha256": bundle["artifact_hashes"][NATURAL_INPUT.name],
        "source_metadata_sha256": bundle["artifact_hashes"][NATURAL_METADATA.name],
        "source_scope": bundle["metadata"]["scope"],
        "source_terms": EXPECTED_REQUESTED_TERMS,
        "selection_used_policy_outcomes": False,
        "followup_gate": bundle["gate"],
        "source_selection": selection,
        "calendar_bin_id": int(selection["bin_id"]),
        "source_window_start_ns": int(selection["start_us"]) * 1000,
        "source_window_stop_ns": int(selection["stop_us"]) * 1000,
        "window_s": 300.0,
        "jobs": len(data["job_id"]),
        "offered_requested_work_s": offered_work_s,
        "offered_work_per_worker_s": offered_work_s / 2.0,
        "work_only_drain_lower_bound_s": max(0.0, offered_work_s / 2.0 - 300.0),
        "first_target_offset_s": int(data["target_release_offset_ns"][0]) / 1e9,
        "last_target_offset_s": int(data["target_release_offset_ns"][-1]) / 1e9,
        "source_rank_semantics": "original submission-row identity; job_id is arrival rank",
        "in_deadline_window_semantics": "undefined for this cross-semester natural bin; all false",
        "input_sha256": bundle["artifact_hashes"][NATURAL_INPUT.name],
    }

    physical.HERE = RUN_DIR
    physical.RECORDS = RUN_DIR / "records"
    physical.INPUT_PATH = NATURAL_INPUT
    physical.INPUT_METADATA = NATURAL_METADATA
    physical.CHECKPOINT_PATH = RUN_DIR / "physical_checkpoint.json"
    physical.SUMMARY_PATH = RUN_DIR / "physical_summary.json"
    physical.LOG_PATH = RUN_DIR / "out_natural_physical.txt"
    physical.PARAMETERS = parameters
    physical.PROTOCOL = protocol

    def frozen_prepare_input():
        return data, run_metadata, bundle["artifact_hashes"][NATURAL_INPUT.name]

    physical.prepare_input = frozen_prepare_input
    result = int(physical.main())
    if result == 0:
        summary = read_json(physical.SUMMARY_PATH)
        require(summary.get("protocol") == protocol, "natural physical summary protocol mismatch")
        summary["scope"] = (
            "one demand-selected original-calendar inferred-arrival window; physical "
            "timed-sleep implementation evidence, not a production deployment or confidence interval"
        )
        summary["upstream_preflight"] = {
            "protocol": bundle["metadata"]["protocol"],
            "input_sha256": bundle["artifact_hashes"][NATURAL_INPUT.name],
            "metadata_sha256": bundle["artifact_hashes"][NATURAL_METADATA.name],
            "gate": bundle["gate"],
        }
        physical.write_json(physical.SUMMARY_PATH, summary)
    return result


def main() -> int:
    if len(sys.argv) != 1:
        raise SystemExit("this frozen natural physical wrapper accepts no arguments")
    bundle = validate_preflight()
    data = load_and_transform_input(bundle)
    return configure_and_run(bundle, data)


if __name__ == "__main__":
    mp.freeze_support()
    raise SystemExit(main())
