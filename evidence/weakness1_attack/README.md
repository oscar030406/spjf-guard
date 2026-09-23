# Weakness 1: does the pooled-scheduler result depend on the capacity, and on open-loop demand?

**Question.** The manuscript replays one server count on an open-loop trace. Three
objections follow. Does the guard's benefit survive at every capacity, or only at the one
chosen? Are open-loop gains a lower bound on what a closed loop would give? And has a
real queue with an executing guard ever been observed at all, rather than only simulated?

**Answer.** The capacity sweep gives a curve, not a point, and the benefit is not positive
everywhere; the open-loop-as-lower-bound reading is falsified by exact rational
counterexamples, including on the primary p99 metric; and a real two-worker timed-work
service did physically queue, with its decisions and its stall-corrected pathwise
accounting checked from recorded events. Three stronger readings are rejected: positive
guard p99 gains at every queueing capacity, open-loop gains as a general lower bound, and
job-level ideal/physical equivalence for the two priority policies in the physical run.
`REPORT.md` is the findings, `PLAN.md` the hypotheses and the frozen protocol.

**Paper items.** Three locations in `paper/sections/08_experiments.tex` and 32 in
`paper/supplementary.tex` — the capacity sweep and its curve (`capacity_curve.csv`,
`summarize_capacity.py`, `summary_numbers.json`, `verification.json`), the physical
experiment (`physical_numbers.json`, `physical_verification.json`), the stall-corrected
certificate (`stall_bound_check.json`, `STALL_BOUND.md`), the feedback counterexamples
(`out_feedback_counterexamples.txt`, `FEEDBACK.md`), the initial falsification
(`pilot.json`) and `REPORT.md`. One supplement sentence names the folder in **body text**,
not in a comment.

**Inputs.** Development overlays only, through the package's guarded loaders with
`unseal=False`. No sealed semester is opened. `pinned_src/` and `source_snapshot/` hold
the byte-matched package source the runs used, so the provenance survives a later rebuild.

**Status.** Current. One follow-up is incomplete and says so: the original-calendar
window stopped at an unrecovered source-version mismatch before any data access, which is
not a demand-screen result.

**Not copied here.** 5,432 files and 5.9 GB became 323 files and 3.7 MB.

- `raw/recovered_development/` (7 files, 5.56 GB) — the development overlay arrays,
  recovered from a local backup; rebuilt by `scripts/build_overlays.py --pool primary`.
- `raw/taskcluster_probe/` (11 files, 1.2 MB) — raw public-API responses with no
  identified data licence, kept locally and deliberately not redistributed; the probe's
  own summary, `probe_taskcluster_summary.json`, is here.
- `physical_records/` (8 files, 271 MB) and the per-job and per-decision streams
  `physical_*_jobs.jsonl` and `physical_*_decisions.jsonl` (42 files, 278 MB) — the
  attempt-level event records of the physical run. The measured quantities derived from
  them are in `physical_numbers.json`, `physical_summary.json` and
  `physical_verification.json`.
- `cells/*.npz` (156 files) and the other array files (158 files, 53.8 MB) — the per-cell
  bootstrap draws of the capacity sweep; each cell's `*.json` is here, and
  `capacity_sweep.py` rebuilds the arrays.
- `cache/`, `.uv-cache/`, `.uv_cache_transport/` (4,873 files, 208 MB) — numba,
  matplotlib, uv and temporary caches.
- The figures `capacity_envelope`, `capacity_improvement_bands` and `physical_validation`
  (`.png` and `.svg`, 6 files, 3.6 MB), which `summarize_capacity.py` and
  `summarize_physical.py` redraw from the CSVs that are here.
- `stall_bound_jobs.csv` (0.71 MB), the per-job record behind `stall_bound_check.json`.
- The one-off local recovery script `recover_original_backups.py` with its log and
  `recovered_development_inputs.json`. It searched a temporary directory on one machine by
  a run identifier and cannot run anywhere else; `INPUT_DRIFT_AUDIT.md` records what it
  found and why. `README.md` below still lists it.

Absolute paths that were baked into the scripts appear as `<repo-root>` (your checkout), `<cache-dir>` (a scratch directory outside the repository) and `<python-root>` (the interpreter install); set them before rerunning. Raw data is not redistributed with this folder — see `data/README.md` for where each dataset comes from.

---

## Original study notes

# Weakness 1 investigation

This directory contains the research plan, reproducible development-only experiments, execution logs and final report for testing whether pooled-scheduler conclusions depend on the chosen capacity and on open-loop demand. The rest of the repository is read-only.

Read REPORT.md for findings and manuscript replacement text; PLAN.md records the hypotheses and the frozen protocol. Each executable experiment includes its parameters and records an adjacent out_*.txt log. Temporary and compiler caches stay inside this directory. No sealed dataset is used.

## Contents

- `capacity_sweep.py`, `common.py`, `cells/`: exact full-trace replay, paired week draws and resumable per-capacity checkpoints. `pilot.py` and `pilot.json` retain the initial falsification and exact no-wait endpoint.
- `summarize_capacity.py`: curve tables, pointwise intervals, simultaneous bands and standalone scientific figures. `verify_artifacts.py` independently checks the complete output, per-job-check counts, promises and hashes of the approved development inputs.
- `feedback_counterexamples.py`, `FEEDBACK.md`: exact rational closed-loop counterexamples, including the primary p99 metric and the distinct shadow-FCFS guarantee.
- `transport_bound_check.py`, `TRANSPORT_BOUND.md`: a conditional FCFS arrival-perturbation theorem, exact-arithmetic checks of its assumptions, and counterexamples to extending it to general rank changes or predicted-size dispatch.
- `physical_service.py`, `PHYSICAL_PROTOCOL.md`, `physical_smoke.py`: a real-time two-worker timed-work service, frozen selection and instrumentation protocol, and short synthetic implementation checks. `physical_records/` preserves attempt-level events; the canonical per-policy files contain every measured job and decision. `summarize_physical.py` produces descriptive tables and standalone validation plots.
- `diagnose_physical_discrepancy.py`, `PHYSICAL_DISCREPANCY.md`: stored-sequence checks locating the first SPJF-E arrival crossing and subsequent priority-order cascade. This diagnoses a failed job-level ideal/physical equivalence claim without another scheduling run.
- `STALL_BOUND.md`, `check_stall_bound.py`: an extension of the pathwise guard bound with cumulative idle-capacity and dispatch-to-start terms, together with an exact-integer check of the logged accounting identities and assumptions. The correction is an ex post certificate unless stalls are bounded in advance.
- `thinning_check.py`, `THINNING_PROTOCOL.md`: a fixed-seed Monte Carlo sensitivity check comparing the full frozen window at `k=4` with independent half-thinnings at `k=2`; its empirical ranges are not demand confidence intervals.
- `natural_preflight.py`, `NATURAL_WINDOW_AUDIT.md`: text-provenance and guarded-loader checks for an original-calendar development window, followed by a fixed demand-only selection and nominal relevance screen. The current preflight stopped before data access because its exact baseline config bytes could not be recovered; this is not a demand-screen result. `recover_natural_config.py` and the three named recovery logs record the bounded source-only attempts. `natural_physical.py` was not run; it is a separate-run wrapper that refuses an incomplete or failed screen, and its verification and summary entry points reuse the common physical checks.
- `AUDIT_A.md`, `probe_taskcluster.py`, `raw/taskcluster_probe/`: existing public-queue evidence and a bounded new recency probe. Raw API responses have no identified data licence and are retained locally, with provenance; do not treat this as a licensed redistribution package.
- `DESIGN_REVIEW.md`, `source_baseline.json`, execution and verification JSON, and adjacent `out_*.txt` logs: design qualifications, provenance and measured timings. `out_capacity_sweep_initial.txt` preserves the serial attempt; completed cells were retained when moving to two workers.
- `pinned_src/`, `source_snapshot/`, `source_drift.json`, `raw/recovered_development/`: byte-matched source and development inputs used before a concurrent project rebuild. `recover_original_backups.py` and `INPUT_DRIFT_AUDIT.md` document their provenance. The rejected additive ZIP reconstruction is retained separately and is never used by `common.py`.

## Rerun from the repository root

Use the existing project environment without synchronising it. In Git Bash:

```sh
export PYTHONDONTWRITEBYTECODE=1
export NUMBA_CACHE_DIR="$PWD/evidence/weakness1_attack/cache/numba"
export MPLCONFIGDIR="$PWD/evidence/weakness1_attack/cache/matplotlib"
export UV_CACHE_DIR="$PWD/evidence/weakness1_attack/cache/uv"
export TMP="$PWD/evidence/weakness1_attack/cache/tmp"
export TEMP="$TMP"
env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME NUMBA_NUM_THREADS=4 OMP_NUM_THREADS=4 uv run --no-sync python evidence/weakness1_attack/capacity_sweep.py >> evidence/weakness1_attack/out_capacity_sweep.txt 2>&1
env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME NUMBA_NUM_THREADS=4 OMP_NUM_THREADS=4 uv run --no-project --with numpy --with matplotlib python evidence/weakness1_attack/summarize_capacity.py
env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME NUMBA_NUM_THREADS=4 OMP_NUM_THREADS=4 uv run --no-sync python evidence/weakness1_attack/verify_artifacts.py > evidence/weakness1_attack/out_verify_artifacts.txt 2>&1
env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME NUMBA_NUM_THREADS=4 OMP_NUM_THREADS=4 uv run --no-project --with numpy python evidence/weakness1_attack/feedback_counterexamples.py
env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME NUMBA_NUM_THREADS=4 OMP_NUM_THREADS=4 uv run --no-project --with numpy python evidence/weakness1_attack/transport_bound_check.py
env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME NUMBA_NUM_THREADS=4 OMP_NUM_THREADS=4 uv run --no-project --with requests python evidence/weakness1_attack/probe_taskcluster.py
env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME NUMBA_NUM_THREADS=4 OMP_NUM_THREADS=4 uv run --no-sync python evidence/weakness1_attack/physical_smoke.py
env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME NUMBA_NUM_THREADS=4 OMP_NUM_THREADS=4 uv run --no-sync python evidence/weakness1_attack/prepare_physical_input.py > evidence/weakness1_attack/out_prepare_physical_input.txt 2>&1
env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME NUMBA_NUM_THREADS=4 OMP_NUM_THREADS=4 uv run --no-sync python evidence/weakness1_attack/physical_service.py
env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME NUMBA_NUM_THREADS=4 OMP_NUM_THREADS=4 uv run --no-project --with numpy python evidence/weakness1_attack/verify_physical.py
env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME NUMBA_NUM_THREADS=4 OMP_NUM_THREADS=4 uv run --no-sync python evidence/weakness1_attack/diagnose_physical_discrepancy.py
env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME NUMBA_NUM_THREADS=4 OMP_NUM_THREADS=4 uv run --no-sync python evidence/weakness1_attack/check_stall_bound.py --physical-complete
env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME NUMBA_NUM_THREADS=4 OMP_NUM_THREADS=4 uv run --no-project --with numpy --with matplotlib python evidence/weakness1_attack/summarize_physical.py
env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME NUMBA_NUM_THREADS=4 OMP_NUM_THREADS=4 uv run --no-sync python evidence/weakness1_attack/thinning_check.py
env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME NUMBA_NUM_THREADS=4 OMP_NUM_THREADS=4 uv run --no-project --with numpy python evidence/weakness1_attack/resource_ledger.py
```

Run commands sequentially. The sweep uses at most two worker processes; there is only one heavy command at a time. Logs from self-logging scripts are written beside the scripts. A completed sweep resumes by validating and reusing its existing cells. For a completely fresh numerical rerun, first preserve `cells/` and existing logs under different names inside this directory; no source-data rebuild is needed. The public probe reuses every cached response and stops on an incomplete sample or endpoint error. It performs read-only batch retrievals by POST where the public API requires a JSON list of task ids; no task or external resource is created or modified.

The physical service runs the three policies sequentially. Each uses the same full five-minute release window and drains its backlog in real time; drain can take longer than five minutes. Completed policy artefacts are verified and reused. Interrupted attempts remain available for inspection, and only the unfinished policy restarts from an empty service. The fixed input, source indices and input hash identify exactly what was executed. These timed payloads exercise occupied workers and dispatcher accounting; they do not execute judge submissions or reconstruct a historical queue. The smoke check is synthetic and is kept separate from research measurements.

Before resuming an interrupted terminal session, inspect the existing physical log,
checkpoint and exact process command lines. Do not start a second service while the
first service still owns its two workers. A missing final summary alone does not mean
the process stopped. The original coarse-clock attempt and rejected smoke fixture
are retained under `physical_v1_coarse_clock/` and
`physical_smoke_v2_arrival_fixture/`; accepted measurements use protocol version 2
and `perf_counter_ns` throughout.

If matplotlib or requests is absent, run only the affected standalone script with `uv run --no-project --with numpy --with matplotlib python ...` or `uv run --no-project --with requests python ...`, retaining the same `env -u ...` prefix and local `UV_CACHE_DIR`. Nothing is installed system-wide. The numerical replay itself uses `uv run --no-sync python` because it imports `spjf_guard`.

The simulator, predictor arrays and manuscript are read-only. The capacity sweep and overlay physical experiment do not open the event cache. The separate natural preflight requires documented development-only rebuild equivalence, fixed source hashes and the project's development guards before reading its approved event and score caches. It refuses changed provenance or configuration. The development-only term guard precedes each explicitly named primary-overlay read. `verification.json` binds those five files to the approved hashes from the earlier development manifest; no sealed input is hashed. The reported intervals condition on the observed replicated demand and frozen models, not production transportability.

The optional original-calendar preflight is incomplete: it currently refuses the
unrecovered configuration source version before data access. Its diagnostic rerun
command is `env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME NUMBA_NUM_THREADS=4 OMP_NUM_THREADS=4 uv run --no-sync python evidence/weakness1_attack/natural_preflight.py`.
It is not required to reproduce the completed results above. Do not waive its source
or data guards to obtain a window.

Only if `natural_estimates.json` reports that the frozen joint follow-up gate passed,
the original-calendar physical profile can run in its own `natural_physical/` directory:

```sh
env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME NUMBA_NUM_THREADS=4 OMP_NUM_THREADS=4 uv run --no-sync python evidence/weakness1_attack/natural_physical.py
env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME NUMBA_NUM_THREADS=4 OMP_NUM_THREADS=4 uv run --no-project --with numpy python evidence/weakness1_attack/verify_natural_physical.py
env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME NUMBA_NUM_THREADS=4 OMP_NUM_THREADS=4 uv run --no-project --with numpy --with matplotlib python evidence/weakness1_attack/summarize_natural_physical.py
env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME NUMBA_NUM_THREADS=4 OMP_NUM_THREADS=4 uv run --no-project --with numpy python evidence/weakness1_attack/resource_ledger.py
```

A measured failure of the relevance screen is a completed negative result, not a
reason to change the window or parameters. A source/provenance mismatch or loader
refusal instead stops the check without a demand result. The natural wrapper cannot
overwrite the original overlay run.

## Input and source version isolation

The original repository inputs were rebuilt concurrently after all five sweep inputs
had been loaded. Reproduction therefore reads the five verified local copies under
`raw/recovered_development/`, not whatever currently occupies the original paths.
`common.py` checks every input against `development_inputs.json` before parsing, invokes
the unchanged project semester guard with `unseal=False`, and uses the project overlay
loader. Each restored file matches its original SHA-256 and 793,567,608-byte size.
The original simulation source is also matched to its pre-run hash and imported from
`pinned_src/`; project data interfaces remain read-only and hash-checked. These snapshots
are part of the reproducible experiment and must be retained with its results.

If the local recovered copies are missing, `recover_original_backups.py` can locate the
documented original development backup and restore only these five allowlisted files
inside this directory. It refuses any hash mismatch. Run it with the same project
`env -u ... uv run --no-sync python` prefix and redirect output to
`out_recover_original_backups.txt`. No source-data file is rebuilt or replaced.
`recover_development_inputs.py` and `check_recovered_container.py` document the rejected
reconstruction diagnostic; they are not required reproduction steps.
