# Audit of an original-calendar CodeBench window for a second physical run

## Scope and decision

This is a static audit of the guarded development-data path and of the input used by
the current physical experiment. It did not open, parse, or hash an event cache, and it
did not run a workload.

## Source-freeze launch failure and recovery stop

The first launch of `natural_preflight.py` stopped at its own source-freeze gate with

```text
RuntimeError: natural-window loader source changed: src/spjf_guard/config.py
```

The complete failed launch is retained in `out_natural_preflight_launch.txt`.  The
exception occurred while evaluating `SOURCE_CODE_PROOF`, before the project package was
imported and before either the event cache or score artifact was opened, parsed or
hashed.  It was therefore not a refusal by the project's sealed-data loader.  The
sealed-data guards and all data-artifact bindings remain unchanged and were not reached.

The working `src/spjf_guard/config.py` differs from Git HEAD by an added aging-policy
import and by score-selection changes.  The guarded data modules and sealed loader are
unchanged, but that semantic observation is not a substitute for the predeclared exact
source hash.  No waiver was applied.

`recover_natural_config.py` then performed three bounded, source-only recovery attempts.
It did not import the project or open a data artifact.  Attempt 1 checked the Git blob
and its CRLF checkout representation for every reachable revision.  Attempt 2 added all
ordinary combinations of LF/CRLF, present/absent terminal newline and present/absent
UTF-8 BOM.  Both reachable revisions,
`16b86b7a0dc40249cd6537bb84b7225da7c4a4a8` and
`bf320ee2fafbd9a13970768f655edad70f1e7b03`, contain the same 7,221-byte blob.  Its
SHA-256 is `3f33ec867abd83917c60b60f36221338916c0361b8a9e0a6022766b04a4d547a`
with LF endings and
`1dd4e1a3df69d6809015d6ee9cc4c8f05361b2f1455a517399339d33438eca1b`
with CRLF endings.  None of the representation variants matched the required baseline
SHA-256
`b3f13b89d146005fde6056c7c3117473803809fcaccf84c1b949c2434bbdf23c`.

Attempt 3 tested the one additional source hypothesis fixed in advance: start from the
current working-tree config, remove exactly the `aging` policy import and the complete
new `aging_section` block, and retain every other edit, including the dynamic
`score_key` selection.  The resulting candidate hashes were
`da28da20e1a0b43424e011a47fe6346cacfc5a0f778c52a04bde8ab087f9b219`
for the 7,473-byte LF form and
`8b8a51a71cdafb52c38aedd792a5dca87f12363888c4fdbb9570670d09f2a2e9`
for the 7,671-byte CRLF form.  Neither matched the required hash, so the search stopped
without trying uncontrolled combinations of edits.

The three exact results are retained in
`out_natural_source_recovery_attempt1.txt`,
`out_natural_source_recovery_attempt2.txt`, and
`out_natural_source_recovery_attempt3.txt`; the generic
`out_natural_source_recovery.txt` is the third result.  Each used one Python process and
three short Git subprocess calls.  Their recorded wall/CPU times were respectively
0.0380183/0.0, 0.0390172/0.0, and 0.0418265/0.0 seconds.  The first named log was restored
verbatim from the captured process output after the generic filename had been reused;
the second and third named logs were copied before any later reuse.

Accordingly, no `pinned_src/spjf_guard/config.py` was written, the current repository
config remained byte-identical at
`d9f1918acaa34999e001a91b3cc049bd92bb9a425c91b8402c4aa867c0abc522`, and neither
`natural_preflight.py` nor `natural_physical.py` was changed to use an unverified
substitute.  The natural preflight was not rerun and the natural physical wrapper was
not run.  This is an incomplete preflight stopped by its own source-provenance gate; it
is not a failed meaningful-candidate screen and supplies no natural-demand result.  The
remainder of this document describes the frozen protocol that would apply only after an
authoritative byte-identical config source is recovered.  Until then, the
original-calendar preflight and any dependent physical follow-up remain blocked at the
source gate.  A later continuation must supply the exact expected bytes or establish a
corrected expected hash from independent provenance; it must not weaken the hash check
or any sealed-data guard.

The current physical experiment should finish and remain in the evidence. It physically
executes jobs in real time, measures worker holding times and dispatch overhead, and can
validate FCFS, SPJF-E, and Guard job by job. Its selected 300-second interval is not an
original CodeBench calendar window, however. It is the busiest five-minute bin in a
counterfactual trace made from 44 copies of the development pool. The accurate
description is **a real-time physical replay of a five-minute interval from the paper's
44-copy shared-pool overlay**. Describing it as “one of the busiest real windows of the
development trace” would be incorrect.

A second run on an unoverlaid interval is methodologically worthwhile only after a cheap
demand-only preflight establishes that an original-calendar interval produces a material
FCFS queue at `k=2`. The existing source and metadata do not establish that condition.
They also do not rule out a short natural burst. The preflight should therefore be run
before committing several policy-hours to another physical experiment.

## Why the current interval is constructed

`evidence/weakness1_attack/physical_service.py::select_input` calls
`common.development_overlay(0)`, groups the resulting arrivals into absolute 300-second
bins, and selects the complete bin with the largest sum of capped service. The frozen
metadata records 2,151 jobs, 4,118.215007 seconds of requested work, two workers, and
`source_copies = 44` (`physical_input_metadata.json`).

The source of that trace is explicit in `src/spjf_guard/experiment/overlay.py`:

* `overlay_entries` repeats every class-term once per copy and independently draws a
  0--11 week shift for each copy and term;
* `superpose` adds the term's base shift and the drawn whole-week shift, concatenates all
  copies, and sorts the constructed arrivals; and
* `base_shift` aligns each term's first-event week to a common reference Monday.

Thus the chosen bin is calendar-aligned on the synthetic overlay timeline. Its within-bin
arrival spacings and capped costs come from development records, but its concurrency is
created by replication and cross-term shifting. This is consistent with the overlay
module's stated purpose: one course term does not fill a judge machine, so class-terms
are superposed until the configured shared pool has the required load.

This distinction does not invalidate the physical experiment. It removes two narrower
concerns: the mechanism has run in an actual dispatcher, and the simulator can be checked
against measured physical waits and worker holding times. It does not establish that
unmodified CodeBench demand queued, and it does not remove the authors' choice of pool
capacity or counterfactual demand consolidation.

## Frozen guarded route to an unoverlaid development interval

The finalized extractor, `natural_preflight.py`, uses the same project entry path as
`scripts/build_overlays.py`, while omitting every overlay operation. The requested pool
is the exact frozen six-term primary list in `configs/main.yaml`:

```text
2020-ERE, 2020-2, 2021-1, 2021-2, 2022-1, 2022-2
```

Before either data artifact is parsed, the script requires all of the following:

1. The complete development scope assembled from `train`, `train_remote`, `validation`
   and `development_test` equals, in order, `2018-1`, `2018-2`, `2019-1`, `2019-2`,
   `2020-ERE`, `2020-1`, `2020-2`, `2021-1`, `2021-2`, `2022-1`, `2022-2`.
   `sealed.guard_semesters` is called on all 11 terms with `unseal=False`, and then on
   the requested six terms with `unseal=False`. There is no command-line override.
2. `pool_terms(cfg, "primary")` equals the six-term list above. The configured event and
   score paths, clock settings, predictor seed, training terms and deadline window equal
   the frozen values in the script.
3. `outputs/prefreeze/prefreeze.log` contains the successful development-only rebuild and
   comparison, and `outputs/prefreeze/cache_columns.csv` contains 58 equal columns,
   including `semester`, each with 2,918,799 rows and zero differences. The recorded
   manifests must also identify the cache and score artifact as development-only and
   record that the sealed 2023-1, 2023-2 and 2024-1 terms were not opened.
4. Before parsing, the event cache must have size 67,391,982 bytes and SHA-256
   `8e37c80715369880ef7652b35f24e1bc15f41d72c47ac87aa3b2c1bd81739451`;
   the stored-score file must have size 33,582,476 bytes and SHA-256
   `af90bb2d8cee4cf3e6806a3665fae356c1ea7d32cab52c724a7300706763bc92`.
   Both bindings must agree with `protocol_lock.draft.json`.
5. The current natural-loader modules must match their frozen source hashes. The replay
   imports the baseline simulator from `pinned_src` only after its package files and the
   corresponding `source_drift.json` records pass their fixed hashes; the imported
   `runner`, `kernel`, `policy` and `bounds` paths must resolve inside `pinned_src`.
   Any mismatch aborts the run.

The hashes and sizes above are recorded in `protocol_lock.draft.json`; they were not
recomputed in this audit. The existing prefreeze comparison gives independent provenance:
`outputs/prefreeze/prefreeze.log` records
`scripts/build_cache.py --pool development --compare
data/derived/codebench_cache_r4/ev.parquet`, rebuilt 11 whitelisted development terms,
and found all 58 columns equal over 2,918,799 events. The script does not accept file
metadata as a content check: it binds both complete files to the recorded hashes before
the project's loader or score reader parses either one.

The fixed clock gate is `reading=result`, `arrival_rule=t-C`, `done_rule=t`,
`delta_s=0`, `test_block_outcome_lag_s=60`, and `limit_s=60`. Jitter must be enabled with
key `cbjitter20260919` and identity columns `semester`, `class`, `user`, `assessment`,
`exercise`, `blk_i`. The fixed preparation gate uses predictor seed 3, training terms
`2018-1`, `2018-2`, `2019-1`, `2019-2`, and a deadline window of 86,400 seconds. The
script aborts if the current configuration differs; it does not silently inherit a later
`configs/main.yaml` clock or preparation change.

This precheck is necessary because the guard and loader have different scopes.
`sealed.guard_semesters` checks the term names supplied by the caller.
`data.events.load_events`, when called without a sealed-cache argument, reads all rows of
`ev.parquet` and does not filter or validate its semester values. A caller that requests
six development terms therefore does not by itself prove that a replaced cache contains
only those terms. Binding the cache bytes to the previously rebuilt development artifact,
after guarding the complete 11-term scope, closes that gap before the project's guarded
loader opens it.

After these assertions, the intended function sequence is:

```python
cfg = cfgmod.load(ROOT / "configs" / "main.yaml")
all_terms = development_terms(cfg)
terms = pool_terms(cfg, "primary")
assert all_terms == EXPECTED_ALL_DEVELOPMENT
assert terms == ["2020-ERE", "2020-2", "2021-1",
                 "2021-2", "2022-1", "2022-2"]
sealed.guard_semesters(all_terms, ROOT, unseal=False)
sealed.guard_semesters(terms, ROOT, unseal=False)
bind_data_artifacts(log)
prepared, inputs = prepare_everything(cfg, terms, False)

arrival_all, _ = arrival_and_availability(prepared, clock_from(cfg))
submission_arrival = arrival_all[prepared.submission_rows]
job_row = np.flatnonzero(inputs.keep)
order = np.argsort(submission_arrival[job_row], kind="stable")
job_row = job_row[order]

arrival = submission_arrival[job_row]
service = inputs.executed_work_s[job_row]
semester = prepared.semester[prepared.submission_rows][job_row]
scores = load_scores(cfg, len(prepared.submission_rows), path=SCORE_PATH, wanted=True)
score = scores["tweedie"][job_row]
```

`job_row` here is the position in the prepared submission arrays, matching the score
file's positional contract. The script additionally requires the finite-score mask to
equal exactly the six requested terms (402,358 target rows) before selecting the 400,790
simulatable rows. `inputs.keep` limits jobs to the six terms and removes the configured
zero-cost unsimulatable blocks. `inputs.executed_work_s` is `min(exec_time, 60 s)`. A
global stable sort by `submission_arrival` is required:
`pool_inputs.per_term` stores each class-term in header-time order, which is not guaranteed
to be arrival order after subtracting execution cost.

The extractor must not call `base_shift`, `overlay_entries`, `superpose`, `rebase`,
`build_overlay`, or `development_overlay`. It must not thin jobs, replicate a term, move
a term by whole weeks, or compress time. For policy comparability with the current
physical run, use the stored `tweedie` score from
`data/derived/ranking_score_predictions/rs_pred_ires0.parquet`. `load_scores` checks its
row count but is not itself a sealed-data guard, so it should be reached only after the
term and cache checks above and should also be bound to its recorded frozen hash before
opening.

## Which times and costs are measured

The original-calendar interval must be called an **inferred-arrival window**, not a
directly observed arrival window.

* The event header `ts` is a recorded result-written time at whole-second resolution.
* With the configured `reading: result`, submission arrival is inferred as
  `a_i = ts_i + u_i - C_i`; there is no directly recorded submission or queue-entry
  timestamp in this construction.
* `u_i` is deterministic synthetic jitter in `[0,1)` keyed by the stable record identity.
  It resolves whole-second ties and is not a measurement.
* `exec_time` is the recorded execution-cost field. The dispatched service is the modeled
  capped cost `C_cap = min(exec_time, 60 s)`, not a new measurement of original platform
  occupancy.
* In the physical experiment, the worker's actual holding time is newly measured with
  `time.perf_counter_ns`; the worker sleeps for `C_cap`, so measured holding time can
  differ slightly from the request.

These qualifications apply even when every job comes from one untouched calendar
interval. Such a run provides stronger arrival provenance than the overlay run, but it
does not turn inferred arrivals into recorded queue-entry times.

## Frozen preflight and decision rule

An earlier proposal selected the busiest bin separately within each semester and would
have continued after any positive FCFS p99 plus a Guard ordering change. That proposal is
superseded. The finalized `natural_preflight.py` and its fixed log and output names use
the following protocol:

1. Load the six requested terms by the guarded route above, stably sort every simulatable
   job by its inferred absolute arrival, and aggregate all six terms together into
   absolute-UTC 300-second bins. This is one global calendar selection, not six separate
   semester searches.
2. For each semester, record its first and last eligible arrival. A candidate bin is
   complete only if at least one semester's observed interval covers the whole bin and no
   semester overlaps the bin only partly at an observed edge. Terms with no temporal
   overlap with that bin do not disqualify it. Retain every requested-term job in the
   winning interval, including jobs with another semester label if terms overlap there.
3. Among complete bins, select the one with the largest sum of `C_cap`, with the earliest
   absolute bin winning an exact work tie. Selection uses no predicted score, simulated
   wait, policy outcome, or guard firing.
4. Report UTC bounds, all represented semesters and their job counts, job and class-term
   counts, work, first and last arrival offsets, coverage-edge counts, and
   `work / (300 * 2)`. Work above 600 seconds proves a positive work-conservation drain
   lower bound for two workers, but work at or below 600 seconds does not rule out a queue
   caused by burst timing.
5. Only after freezing that bin, replay FCFS, SPJF-E and Guard(300) at `k=2`, with formal
   `L=61` s, `B0=30` s, `eta=0.5` and zero gamma. Report the wait distribution, maximum
   queue size, drain time, Guard firing count, and per-job bound checks. Do not choose a
   different interval after seeing these results.

The fixed **meaningful-candidate** gate is the conjunction of FCFS p99 wait at least
`3L = 183` seconds and a top-1%-job work share of at least 0.25, where the top count is
`ceil(0.01 n)`. These are heuristic relevance screens, not sufficient or proved
necessary conditions for a p99 benefit. Guard firing is reported independently. A
candidate supports a full physical mechanism audit only when the joint
meaningful-candidate gate passes and Guard(300) has at least one forced dispatch. Neither
SPJF-E nor Guard benefit is used to select the window or to define the
meaningful-candidate gate.

If the joint gate fails, the result should be retained as evidence that the busiest
predeclared complete five-minute natural interval did not meet the fixed relevance
screen at two workers. If the joint gate passes but the guard never fires, the interval
may document congestion and cost concentration but cannot exercise the guard's override
mechanism in a follow-up physical run.

Using `k=1` after a `k=2` failure is still possible, but it is a new capacity choice and
must be labelled as such. Widening the demand-only selection to a predeclared one-hour
window is cleaner if the purpose is to preserve a natural backlog, but it requires about
one real hour per policy plus drain. Replicating or shifting the failed natural interval
would return to the current counterfactual design and must not be described as a natural
window.

## Recommended statement after the current run

Until the natural preflight supplies new evidence, the strongest accurate statement is:

> We implemented the three dispatch policies in a two-worker execution service and
> replayed, without time compression, the busiest five-minute interval of the same
> 44-copy counterfactual shared-pool trace used in the simulation. Jobs occupied workers
> for their capped recorded costs, while the service measured dispatch times, waits, and
> worker holding times with a monotonic clock. This experiment checks the simulator and
> the guard implementation against a physical dispatcher; it does not show that the
> source CodeBench deployment itself queued or that its unmodified arrival stream would
> saturate two workers.

If the joint gate passes, the guard fires, and a second run agrees with simulation, a
separate sentence may state that the same implementation was also tested on the busiest
predeclared complete original-calendar **inferred-arrival** window. The pool size would
remain an experimental choice, and that limitation should remain explicit.

## Static sources inspected

* `evidence/weakness1_attack/physical_service.py`
* `evidence/weakness1_attack/physical_input_metadata.json`
* `evidence/weakness1_attack/common.py`
* `scripts/build_overlays.py`
* `scripts/build_cache.py`
* `src/spjf_guard/data/sealed.py`
* `src/spjf_guard/data/events.py`
* `src/spjf_guard/data/clock.py`
* `src/spjf_guard/experiment/overlay.py`
* `configs/main.yaml`
* `outputs/prefreeze/prefreeze.log`
* `outputs/prefreeze/cache_columns.csv`
* `protocol_lock.draft.json`
* `evidence/weakness1_attack/source_drift.json`
* `evidence/weakness1_attack/pinned_src/spjf_guard/sim/`
* `evidence/main_v3/out_main_v31.txt`
* `evidence/main_v31_verify/out_manifest.txt`
* `evidence/ranking_score/rs_fit.py`
* `evidence/ranking_score/out_fit_a.txt`
* `evidence/ranking_score/out_fit_b.txt`
