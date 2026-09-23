# Conditional natural-calendar physical follow-up

## Purpose and status

`natural_physical.py` is a thin, gated configuration layer over the reviewed
two-worker implementation in `physical_service.py`. It is prepared for a possible
second physical run on `natural_input.npz`; it has not been executed. The follow-up
is permitted only when the original-calendar preflight passes both workload screens:
nominal two-worker FCFS p99 wait is at least (3L=183) seconds and the longest one
percent of jobs supply at least 25% of capped work. No empirical policy advantage
selects the window.

The additional `full_mechanism_audit_candidate` flag is recorded but is not a second
admission gate. It indicates whether nominal Guard also fired. If it is false, the
physical run may still test timing and fixed-demand scheduling, but it cannot be
reported as an exercised guard-intervention mechanism.

## Refusal and provenance checks

Before creating `natural_physical/`, importing `physical_service`, or starting a
worker, the wrapper requires all of the following:

1. `natural_resources.json` reports `PASS`, one process and no children.
2. The resources file binds the byte size and SHA-256 of `natural_input.npz`,
   `natural_input_metadata.json`, `natural_replay.npz` and
   `natural_estimates.json`; all four current files must match.
3. Metadata, estimates and resources carry the same preflight protocol; metadata and
   estimates contain identical parameters and selected-window records.
4. The preflight records the six declared development terms, an original-calendar
   source, no overlay, rebase, replication or thinning, the frozen two-worker policy
   family and the exact Guard(300) parameters.
5. The recorded event-cache and score-file hashes, pinned simulation hashes and
   natural-loader hashes equal the reviewed constants. The current
   `natural_preflight.py`, `physical_service.py` and pinned simulation files must also
   retain their reviewed hashes.
6. The two workload-screen booleans are recomputed from the reported FCFS p99 and
   top-one-percent work share, agree with `meaningful_candidate`, and are true.
7. The frozen NPZ has exactly the six declared arrays, one common positive length,
   sorted arrivals and offsets, offsets equal to absolute arrival minus the selected
   bin start, releases inside the 300-second half-open bin, services in `(0,60 s]`,
   finite positive scores, unique source rows and the recorded work sum.

Any failure raises before the dedicated output directory is created. The wrapper does
not reopen the event parquet or score parquet, rebuild the natural input, or infer a
missing gate value.

## Exact input adaptation

The scheduler receives only this deterministic schema conversion:

| Natural preflight array | Timed-service field |
|---|---|
| array position | `job_id`, the immutable arrival rank |
| `job_row` | `source_rank`, used as an original submission-row identity in output |
| `target_offset_us` | `target_release_offset_ns = 1000 * target_offset_us` |
| `service_us` | `requested_service_ns = 1000 * service_us` |
| `score` | `score`, converted only to contiguous float64 storage |
| no corresponding field | `in_deadline_window = false` for every job |

The last field exists only for compatibility with the shared physical implementation.
A cross-semester natural bin has no single assessment deadline window, so no natural
result may use the original physical summarizer's deadline subset.

The new physical protocol hash binds the upstream preflight protocol, frozen input and
metadata hashes, the exact conversion, gate role, two-worker policies, timing model and
Guard parameters. Checkpoints bind that protocol and the upstream natural-input hash.

## Output isolation and Windows spawning

All new outputs are under `evidence/weakness1_attack/natural_physical/`:

- `records/` for attempt event streams and failure records;
- `physical_checkpoint.json` and `physical_summary.json`;
- per-policy `physical_*_jobs.jsonl`, `physical_*_decisions.jsonl` and
  `physical_*_audit.json` files;
- `out_natural_physical.txt` and a dedicated `cache/` runtime tree.

The original `physical_input*`, checkpoint, summary, canonical policy files, log and
`physical_records/` are never selected as output paths. The natural preflight files
remain read-only.

On Windows, `run_physical_policy` spawns `physical_service.worker_main` by module name.
The child imports an unmodified `physical_service` module rather than inheriting the
parent's reassigned output globals. This is safe because `worker_main` uses no protocol,
input, path, policy or guard global: it only receives a job id and requested duration,
sleeps, timestamps and returns the completion. The dedicated runtime-root environment
is inherited. All input conversion, scheduling, policy construction, event logging and
audits remain in the configured parent process. A future change that makes
`worker_main` consult module configuration invalidates this reasoning and must update
the reviewed source hash.

## Algorithm and estimand

After the gate, the wrapper delegates unchanged to `physical_service.main`. It keeps
the same sequential FCFS, SPJF-E and Guard(300) runs, two persistent workers per run,
actual enqueue semantics, completion-only service visibility, event-prefix audit,
ideal measured-trace replay, same-(a,C) shadow FCFS and service-limit premise. Every
job from the frozen natural window is retained with no thinning or time compression.
Each policy begins empty, so the result does not include backlog from before the
selected window.

The gate is part of the follow-up design and uses nominal FCFS congestion plus cost
concentration. The resulting physical window is therefore demand-selected and
gate-selected, not a random or representative window. One run supplies no confidence
interval and does not identify historical CodeBench queueing, closed-loop feedback or
execution-cost transport to a real pooled judge.

## Minimal adaptation of the verification script

The existing `verify_physical.py` should be parameterised rather than copied. A shared
`verify_run(run_dir, source_profile)` entry point can preserve its clock, worker-overlap,
audit-hash and exact nanosecond bound checks while replacing three hard-coded facts:

1. Read expected job count from `summary["input"]["jobs"]` rather than requiring 2,151.
2. Independently recompute the profile's protocol and input SHA. The natural-run verification script
   can import the wrapper's side-effect-free `physical_parameters` and
   `physical_protocol` functions after its read-only preflight validation, rather than
   trust the protocol copied into the result. Require protocol version 3 and
   `checkpoint.input_sha256 ==
   summary.input.source_input_sha256 == summary.upstream_preflight.input_sha256`, and
   recompute the SHA-256 of the parent `natural_input.npz`.
3. Load the actual frozen input and reconstruct the expected physical fields, reusing
   the wrapper's read-only `load_and_transform_input` function. For every
   `job_id`, compare `source_rank` with `job_row`, `target_release_offset_ns` with
   `1000*target_offset_us`, `requested_service_ns` with `1000*service_us`, and `score`
   with the frozen score. Also require the compatibility deadline flag to be false.

The third check is necessary for both profiles in spirit: comparing frozen fields only
among policy outputs proves cross-policy consistency but does not bind those fields to
the input NPZ. The original profile should likewise reconstruct its expected fields
from `physical_input.npz` instead of relying only on the fixed job count.

The verification script should write its CSV, JSON and log inside `run_dir`. Its existing exact
formula remains unchanged for this protocol:

\[
  \min\{W_F+300\text{ s},\;2W_F+274\text{ s}\}.
\]

The reusable clock check should include target release before actual enqueue, exact
release lateness, dispatch before worker command receipt, command receipt before worker
start, worker finish before dispatcher receipt, and non-overlapping intervals per
worker.

## Minimal summarizer adaptation

`summarize_physical.py` should similarly expose a shared
`summarize_run(run_dir, title, include_deadline)` function. The natural invocation uses
the dedicated directory, an “original-calendar inferred-arrival window” title and
`include_deadline=False`; it omits `deadline_wait_s` instead of describing an empty
compatibility field. All other wait, replay-discrepancy, service, release-lateness and
dispatcher-overhead calculations can remain shared. Figures and numerical JSON must be
written under the selected run directory.

These parameterisations avoid a second implementation of the theorem bound, event
checks or plotting statistics. They should be made only after the currently running
original physical experiment has finished.

## Intended invocation after the gate

From the repository root, using the existing project environment without synchronising
it:

```sh
env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME \
  NUMBA_NUM_THREADS=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  uv run --no-sync python evidence/weakness1_attack/natural_physical.py
```

The wrapper accepts no command-line choices. This command is intentionally not run by
the protocol preparation step.
