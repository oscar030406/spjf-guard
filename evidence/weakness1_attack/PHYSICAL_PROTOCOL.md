# Timed-sleep physical-service protocol

## Purpose and evidential scope

This experiment checks whether the production scheduling rule can drive two persistent
processes whose service consists of real timed sleeps. It is implementation evidence for
one pre-specified five-minute development window. It is not a full-hour experiment, a
production deployment, a proof of exact agreement with the ideal simulator, or a source
of bootstrap confidence intervals. The capacity sweep supplies the week-level uncertainty
analysis.

The three policies run sequentially in the fixed order FCFS, SPJF-E, and Guard(300). Each
policy gets two fresh worker processes and the same job identities, target release offsets,
requested service durations, and cached prediction scores. Realised enqueue times and
sleep durations may differ between policy runs, so the separate physical FCFS run is a
diagnostic comparison rather than the theorem's same-arrival, same-service FCFS baseline.

## Frozen input selection

`physical_service.py` obtains primary development overlay replicate 0 only through
`common.development_overlay(0)`. It does not open or inspect any sealed dataset. Within
that overlay it partitions source time into calendar-aligned 300-second bins, keeps only
complete bins, and chooses the bin with the largest sum of offered capped service. An
earliest-bin rule resolves a tie. The rule uses no policy outcome, predicted gain, guard
result, or physical timing.

Every selected job is retained. Its original spacing within the bin, capped service
request, score, source rank, and evaluation-window label are retained. There is no
thinning, time compression, or scaling of the recorded capped durations. Timed sleeps
replace execution of the original submission code. Requested service must be at most 60 seconds.
The selected arrays, selection metadata, source terms, offered work, estimated work-only
drain lower bound, protocol hash, and file hash are written to `physical_input.npz` and
`physical_input_metadata.json`. A later invocation guarded-loads the development overlay
again and rejects any mismatch with the frozen input.

## Fixed model parameters

- Workers: `k = 2` persistent child processes; the root process is the only dispatcher.
- Promise: `G = 300 s`; service limit used by the theorem: `L = 61 s`.
- Guard: `B0 = 30 s`, `eta = 0.5`, `gamma = 0`.
- Budget cap: `Bmax = 2 * (300 - 2 * 61) = 356 s`.
- Score policy: SPJF-E using the cached `tweedie` prediction; ties use arrival rank.
- Clock: `time.perf_counter_ns()` for all physical event times (protocol version 2).

The local Python 3.12.13 `monotonic` clock uses GetTickCount64 with 15.625 ms
resolution, despite returning integer nanoseconds. This was detected in the initial
smoke records and confirmed by `clock_resolution.py`. Its first unfinished FCFS run
was stopped at about 397 seconds and retained as rejected measurement, together with
version-1 source and input metadata. Version 2 uses QueryPerformanceCounter: the local
clock reports 100 ns resolution, monotonic and nonadjustable. Python documents this
counter as system-wide on Windows since Python 3.10, so dispatcher and workers share
the clock ([Python 3.12 time documentation](https://docs.python.org/3.12/library/time.html#time.perf_counter)).
Startup rejects a clock with resolution worse than one microsecond. This instrumentation
correction changes no job, window selection, service request, capacity, score, or guard
parameter. Original raw timestamps remain separate from the simulator's microsecond
representation; rounded microsecond comparisons are explicitly labelled.

The 61-second limit consists of the pre-fixed 60-second payload limit and one second of
timing headroom. It is a model premise, not a future hard-real-time guarantee. If any
measured worker holding time exceeds 61 seconds, the job and run are marked as premise
failures. The script does not raise, reselect the window, or increase `L` after observing
the result.

## Physical event loop

Workers block on `Connection.recv()`. On a run command a worker records command receipt,
records its start, calls `time.sleep()` once for the requested duration, records finish,
and sends the timestamps to the dispatcher. A worker never ranks jobs or exposes service
to the scheduler before completion. The ready handshake and one-second launch lead start
both workers without a CPU-intensive warm-up.

The dispatcher blocks in `multiprocessing.connection.wait()`, with the next target release
as its timeout when applicable. It does not poll or busy-wait. At each visible event prefix
it applies Algorithm 1 in this order:

1. Receive available completion messages and charge each measured worker holding time.
2. Enqueue every target release that is due.
3. Dispatch while an idle worker and a waiting job both exist.

Thus a completion becomes schedulable evidence when the dispatcher receives its message,
not at the worker's earlier finish timestamp. Both timestamps are preserved. A completion
that arrives while the dispatcher is processing another event is visible at the next
`connection.wait()` return. This is the implemented observable-event semantics.

For every waiting job `i`, Guard(300) computes completed overtaking work from only charged
completion messages and computes age from the dispatcher's actual enqueue time. Its budget
is `min(B0 + eta*k*age, Bmax)`. `guard_fired` means the fired set `E(t)` is nonempty. The
dispatcher chooses its minimum arrival rank. `choice_changed` separately records whether
that choice differs from the SPJF-E base candidate; a guard-controlled dispatch need not
change the selected job. For FCFS and SPJF-E, guard firing and choice change are false.

## Recorded clocks and audit trail

The event log preserves target release, actual enqueue, dispatcher decision, dispatcher
dispatch, worker command receipt, worker start, worker finish, and dispatcher completion
receipt. The primary physical definitions are:

- wait: `worker_start - actual_enqueue`;
- service `C`: `worker_finish - worker_start`;
- visible completion: dispatcher completion receipt;
- dispatcher slot occupancy diagnostic: `completion_receipt - dispatch`.

Every decision records the complete waiting ranks, each waiting job's score, age inputs,
charged completed overtaking work, budget, fired status, fired set, minimum fired rank,
base candidate, chosen job, visible completion and enqueue counts, and decision CPU and
wall overhead. Per-job diagnostics also retain dispatch-to-start delay, finish-to-receipt
IPC lag, requested-versus-measured sleep overshoot, and worker idle gaps. These quantities
expose dispatcher and IPC non-work-conservation rather than folding it into service.

Progress records contain substantive event counts and target an interval of 30 seconds.
The progress deadline is an additional blocking-wait timeout, so it does not create a
polling or busy loop; operating-system scheduling can delay a record. Dispatcher CPU,
worker CPU, full wall time from the common origin, offered-work drain estimate, and actual
drain after the 300-second release window are reported.

## Simulator and bound audits

After a physical policy finishes, both workers are shut down before any simulator audit.
The production simulator is replayed on that policy run's actual enqueue times and measured
worker holding times, rounded to its microsecond representation. Physical per-job waits, dispatch indices, and Guard firing count are
compared with this replay. Agreement is not asserted: the simulator is ideal and
work-conserving, whereas the physical dispatcher has measured process and IPC overhead.
An additional nominal replay uses frozen target releases and requested service.

For Guard(300), production `assert_per_job_bounds` runs against ideal FCFS on the same
microsecond-rounded measured arrival and service trace. The physical Guard waits are also compared per job with
the bound formed from that same measured-trace shadow FCFS and the fixed `L = 61 s`.
Physical violations, production assertion failures, and service-limit premise failures are
all retained. The independent physical FCFS wait comparison is labelled separately because
its realised enqueue and service times are not identical to Guard(300)'s.

The final `verify_physical.py` audit additionally reconstructs shadow FCFS directly in
integer nanoseconds from the measured job records. For every Guard job it checks
`W_physical <= min(W_shadow + 300 s, 2 W_shadow + 274 s)` without a rounding tolerance.
It retains the difference from the production simulator's rounded shadow wait, verifies
every fixed job field against the frozen NPZ, and checks all timestamp orderings and
non-overlapping worker intervals. This observed-run check does not impose a future
real-time service or dispatch bound on the operating system.

Production `n_forced` is interpreted as the number of Guard dispatches with nonempty
`E(t)`. The FCFS kernel's internal FIFO counter is not interpreted as guard firing.

## Files, restart behaviour, and completion rule

Attempt event and decision JSONL files are written under `physical_records/`. An interrupted
attempt remains there for diagnosis; no partial physical state is resumed. The next run
starts that policy again with fresh workers. A policy enters `physical_checkpoint.json`
only after its canonical per-job JSONL, decision JSONL, and audit JSON are complete and
hashed. Completed policies are verified and skipped on restart.

`physical_summary.json` is written only after all three policy checkpoints exist.
`out_physical_service.txt` is the progress and resource log. All caches and experiment
outputs remain within `evidence/weakness1_attack/`.
