# Physical-versus-ideal SPJF discrepancy diagnosis

## Scope

The completed SPJF-E audit reports 1,401 of 2,151 jobs at a different dispatch
index from the ideal work-conserving replay.  Its mean physical-minus-ideal wait is
only 0.315391 s, while the largest absolute per-job difference is 392.836259 s.  The
event-prefix audit passed all 2,151 dispatches, so the physical dispatcher chose the
minimum cached score from every queue it actually observed.  These facts are
compatible: a small timing perturbation can change which jobs are available at a
dispatch, and static priority then propagates that first difference through many later
positions while positive and negative per-job wait changes cancel in the mean.

`diagnose_physical_discrepancy.py` performs a bounded artifact-only reconstruction to
separate those mechanisms.  It reads the completed SPJF-E job, decision, audit and
event files and the completed FCFS job and audit files.  It imports no simulator,
reads no NPZ, launches no child process, and creates no new schedule.  The stored
`production_replay_dispatch_index` and `production_replay_wait_us` fields are treated
as the already-completed ideal result.

The script checks every physical SPJF choice directly against the minimum
`(score, rank)` in that decision's stored `waiting_ranks`.  Independently, it walks
the stored ideal dispatch order, reconstructs the arrived and undispatched set from
the recorded actual enqueue times, and checks the same minimum.  At each differing
position it then asks whether:

1. a lower-score job arrived after the mapped ideal dispatch epoch but before the
   physical decision;
2. one schedule had already dispatched a job because of an earlier difference;
3. both candidates were available to both schedules, which would be evidence for a
   score-choice formula inconsistency; or
4. another queue-membership difference remains.

It groups mismatching positions into permutation episodes: an episode begins when two
identical dispatched prefixes first choose different jobs and ends when the sets of
jobs in the two prefixes become equal again.  An arrival crossing at an episode start
is a direct timing cause; subsequent differences before resynchronization are the
priority cascade.  For the largest positive and negative wait errors and the ten
largest absolute errors, it records dispatch-index displacement and the measured work
of jobs present before the target in only one ordering.  That work is descriptive and
is not treated as an additive delay decomposition on two servers.

FCFS is the control for interpretation.  Its completed run has zero dispatch-order
mismatches, mean physical-minus-ideal wait 0.248124 s and maximum absolute discrepancy
0.486214 s.  This provides a descriptive reference for combined timing differences in
that FCFS run, where a fixed arrival order cannot cascade.  It does not make the
separately timed FCFS run a per-job counterfactual for SPJF-E.

## Result

The diagnostic passed all assertions.  It checked all 2,151 physical choices against
the stored physical waiting sets and all 2,151 stored-replay choices against the
reconstructed replay waiting sets.  Both bad-choice counts are zero.  There are also
zero differing dispatch positions at which both schedulers had both candidates
available.  Thus the 1,401 order differences do not show that the physical and ideal
runs used different `(score, job_id)` choice formulas on a common candidate set.

The first difference is dispatch index 130.  The ideal replay chooses job 128 with
score 0.8865612342, whereas the physical dispatcher chooses lower-score job 158 with
score 0.2844021503.  Job 158 was not available at the mapped ideal dispatch epoch: it
was enqueued 1.1282 ms after that epoch.  The physical decision occurred 24.7613 ms
after the ideal epoch and 23.6331 ms after job 158's enqueue.  Its waiting set has 29
jobs and the ideal set has 28; job 158 is the sole physical-only member, while job 128
is available to both.  Between the preceding physical dispatch and this decision,
the log records one visible completion, for job 79, and eight enqueues, jobs 151--158.
This is a directly observed arrival crossing rather than a score-choice discrepancy.

The two orders form eight prefix-resynchronizing permutation episodes.  Every episode
starts with a later arrival crossing into the physical decision.  Across all differing
positions, 39 are classified as such crossings and 1,362 have at least one candidate
already dispatched by the other ordering, the signature of an order cascade.  The
longest episode runs from dispatch indices 361 through 1,761: 1,401 positions, of
which 1,363 differ.  At most six job identities separate the two dispatched-prefix
sets at once.  A prefix episode can contain additional arrival crossings after its
start, so the 1,362/39 split is a local classification at each differing epoch, not a
claim that each later displacement has one unique cause.

Job 395 is the extreme positive discrepancy.  It moves from ideal dispatch index 361
to physical index 1,761 and its wait rises from 7.353180 s to 400.189439 s, a
392.836259 s difference.  The physical ordering puts 1,400 additional jobs before it;
their measured service totals 785.013994 s.  This total is descriptive rather than an
additive wait decomposition because two workers execute service concurrently.  The
largest negative discrepancy is job 1,353, which moves from ideal index 986 to
physical index 968 and waits 2.509642 s less.  Job 1,220 has the second-largest
absolute discrepancy, waiting 16.474690 s more after moving 106 places later.

The discrepancy is therefore sparse in the tail despite the large order change.  The
absolute wait discrepancy has median 0.110207 s, p95 0.429925 s and p99 0.642782 s;
10 jobs exceed 1 s, two exceed 10 s and one exceeds 300 s.  Its signed mean remains
0.315391 s because earlier and later jobs partly cancel.  Standard linear
interpolation is used for these quantiles.

The separately timed FCFS control has no dispatch-order mismatch.  Its
physical-minus-own-ideal-replay wait difference has mean 0.248124 s, maximum absolute
value 0.486214 s and p99 absolute value 0.479359 s.  This is consistent with small
accumulated timing overhead when FCFS's fixed arrival order cannot create a priority
cascade.  It does not identify what the SPJF-E waits would have been in the FCFS
process, because the two physical runs have different clock traces.

## Limits of the diagnosis

This is an internal-consistency diagnosis of completed artifacts.  It takes the
stored production replay order and waits as the ideal result and reconstructs its
candidate sets from the stored actual enqueue times using the same microsecond
rounding recorded for that replay.  It does not independently recompute the simulator
or validate upstream scores, service measurements, enqueue records, or the replay
implementation.  The zero-conflict result therefore rules out a different base
choice on the candidate sets represented in these files; it is not a proof that every
upstream field is correct.

The arrival-crossing evidence identifies the immediate queue-membership mechanism.
It does not apportion the 24.7613 ms first-epoch lag among OS wake-up, completion IPC,
dispatcher work, and worker handoff, nor does it establish a general perturbation
bound for static-priority scheduling.  The 392.836259 s outlier shows why the observed
mean timing delta alone cannot certify per-job fidelity to an ideal work-conserving
replay.

The machine-readable result is `physical_discrepancy.json`; the adjacent complete log
is `out_physical_discrepancy.txt`.  The run used one process, launched no children,
and consumed 0.197062 s wall time and 0.187500 s CPU time.  It read no NPZ and created
no new schedule.  Both outputs bind all six input artifacts by SHA-256, including the
SPJF-E event log named and hashed by the completed audit.

## Guard(300) qualification

The completed Guard(300) run provides a separate, stronger warning against physical
trajectory equivalence.  Relative to its own ideal production replay on the Guard
run's actual enqueue times and measured holding costs, 1,753 of 2,151 jobs have a
different dispatch index.  The signed mean physical-minus-ideal wait is 5.368542 s,
and the largest absolute per-job difference is 1,354.102033 s.  The physical run has
322 fired-set-nonempty epochs, compared with 372 in the ideal replay; the stored
per-job firing indicators disagree for 52 job identities.

Both sides nevertheless pass their respective semantic audits.  The physical
event-prefix audit checks all 2,151 decisions against the arrivals and completion
receipts visible to the dispatcher.  The independent ideal-epoch audit checks all
2,151 ideal decisions, 1,241,424 waiting-job budget evaluations and all 372
reconstructed firing epochs against the ideal kernel.  Thus these differences do not
by themselves show an implementation error.  They show that physical timing changes
not only candidate availability but also the completed-work and age state read by the
guard.

The SPJF-E arrival-crossing diagnostic above was not rerun for Guard(300), and its
static-score decision rule does not apply at fired epochs.  No claim is made that the
Guard dispatch differences or its extreme wait discrepancy have the same cause as the
SPJF-E episodes.  Establishing such a decomposition would require a separate
Guard-aware analysis of candidate sets, receipt-visible completed work, budgets and
firing decisions.

The exact stall-bound checker passes with no numerical tolerance.  For all 2,151 jobs
it verifies the common-clock and equal-arrival admission conditions, serial dispatch,
receipt-before-worker-reuse discipline, measured holding cap, observed-prefix guard
rule, workload comparison, dispatch identity, overtaker bounds, both corrected strict
branches, and their combined physical-wait formula.  It reports zero corrected
violations.  The realized trace also has zero violations of the uncorrected same-trace
numerical bound, with maximum physical excess over shadow FCFS of 222.2075511 s.  This
last result is empirical for the completed trace; the theorem still supplies no fixed
future bound without advance controls on cumulative capacity deficit and
dispatch-to-start delay.

The all-job physical p99 is 1,783.64837 s for Guard(300), higher than the separately
executed physical FCFS value of 1,763.30488 s.  This is a negative descriptive p99
comparison for the selected window.  The sequential runs have different physical
clock traces and do not have identical realized holding costs, so that comparison is
not the theorem's same-arrival, same-cost shadow-FCFS contrast and is not a causal
policy effect.
