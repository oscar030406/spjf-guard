# Capacity, physical queueing and feedback: investigation of weakness 1

Status: the capacity sweep, uncertainty calculation, feedback falsification, bounded
public-queue probe, physical experiment, exact stall-corrected certificate and
thinning sensitivity are complete. The optional original-calendar follow-up
stopped at an unrecovered source-version mismatch before data access. No
manuscript file has been changed.

## What question is identified

The completed evidence removes the literal claim that no queue or executing guard
has been observed: the local two-worker service physically queued, and its decisions
and stall-corrected pathwise accounting were checked from recorded events. It does
not establish a historical source-platform queue, an operator-chosen capacity or a
causal deployment benefit. The study also rejects three stronger interpretations:
positive Guard p99 gains at every queueing capacity, open-loop gains as a general
lower bound on closed-loop gains, and job-level ideal-simulator fidelity for the
two priority policies in the physical run.

The source platforms do not identify the counterfactual waiting times of a fixed pooled service. Recorded execution demand identifies an input to such a service only under assumptions about transportable service requirements, unchanged arrivals and available prediction features. An empirical benefit on that input can be sensitive to capacity even when every per-job guarantee is correct.

We separated five hypotheses before new measurement in PLAN.md: whether production queueing exists; whether the choice of capacity determines the apparent benefit; whether feedback changes the demand; whether public queue traces satisfy both applicability conditions; and whether a physical implementation matches the algorithm. We initially chose a declared capacity sweep and an exact feedback falsification. Early negative capacity cells established that this alone would not remove the unexecuted-mechanism objection, so we added a bounded real-time timed-work implementation. A small public-queue probe remains supplementary. Each amendment and its reason was recorded before inspecting the new physical window or making new API measurements.

## Development-only capacity experiment

All inputs are the five pre-existing primary development overlays under data/derived/overlay_traces. Each contains 17,634,760 jobs, of which 4,219,556 belong to its own assessment's 24-hour deadline window. All five overlays use the same six source terms---2020-ERE, 2020-2, 2021-1, 2021-2, 2022-1 and 2022-2---and the same source jobs. Each repeats the same 40 class-terms 44 times with different whole-week shifts. The five overlays are five constructions from the same demand, not independent deployments, semesters or replications from a wider population.

Before each capacity-input read, the project data guard checks the explicit development term list with unseal=False; the project's overlay loader then reads only primary_rep0.npz through primary_rep4.npz. This capacity experiment does not open the ev.parquet event cache. No sealed term, ACcoding id block, OULAD 2014 data or sealed-input hash is accessed. The declaration is bound to the documented development artefact paths and the final manifest records their hashes; it is not a semantic re-audit of every original event.

The complete common grid is every integer k=1..20, with FCFS, true-size SJF, cached expected-cost SPJF-E, and Guard with G=300, 600 and 1200 seconds. Overlay 0 continues at every integer k=21..76 with FCFS, SJF, SPJF-E and Guard(600). Only this one-overlay, one-promise extension is described as reaching disappearance of queueing. Scores are the fixed tweedie arrays embedded in the existing overlays; they are not refitted and should not be confused with a later package predictor refit. Budget shapes are the pinned paper/configuration settings, scaled only as specified by k. All policies retain the same arrivals and service costs, start at the beginning of the complete trace, preserve queue state throughout and drain every job. There is no time compression, thinning or reset at a busy window.

Define the infinite-server occupancy K_inf = max_t sum_i 1{a_i <= t < a_i+C_i}. At k >= K_inf, each arrival has a free server, so any work-conserving policy starts every job immediately. Conversely, k < K_inf cannot start every job immediately. Processing completions before arrivals at equal times gives an exact endpoint rather than a selected high-capacity cutoff. Overlay 0 has K_inf=76; the pilot verified one positive FCFS wait at k=75 and no positive wait at 76.

The two age guards sometimes admit an exact no-firing certificate. On the SPJF dispatch sequence, the project's In/Out routine computes every job's total dispatched overtaking work In_i. If In_i < the actual integer B0 for every job, then at every earlier epoch completed overtaking work is smaller than B0, and hence smaller than the guard budget. A first divergent dispatch is impossible. These cells are labelled certified_identical and are checked against the per-job bound after reusing the exact SPJF schedule. All 49 certified cells occurred on overlay 0; the first two were compared with actual guard-kernel waits and dispatch orders and had zero firing. No certified cells occurred on overlays 1--4. This shortcut is not used for the queue-length guard with B0=0.

The primary curve averages the five overlay-specific deadline-window p99 values. Ratios use the difference of those averaged quantiles, explicitly rather than averaging unstable per-overlay ratios. The bootstrap uses the stored calendar-week indices and 2,000 shared multinomial week draws (seed 20260921). Every quantile is recomputed on its weighted empirical job distribution using the package routine; the same multiplicities are used for every policy, capacity and overlay. Means are averaged over overlays; harm and maximum excess are maxima over overlays. All undefined ratio draws are counted. Pointwise intervals are distinguished from the centred standardized simultaneous bootstrap band over the 80 declared comparisons (20 capacities times four non-oracle policies).

The capacity grid and 80-coordinate comparison family were declared after the overlay-0 pilot and before the full sweep. They were not specified before any inspection of this development demand. These intervals resample already realised per-job outcomes. They do not concatenate weeks and rerun a stochastic queue. Cross-week queue state, replicated source jobs, predictor fitting, overlay selection, model mismatch and feedback are outside their coverage. Computationally exact weighted quantiles do not imply exact frequentist coverage. The estimates and intervals remain development sensitivities.

## Results

All 156 declared capacity cells are present: all five overlays at every integer $k=1,\ldots,20$, plus the overlay-0 extension through $k=76$. The guard implementation covered 356 source policy-cells: 307 were simulated and 49 used the exact no-firing certificate, with two direct kernel validations of the shortcut. All 6,277,974,560 recorded per-job bound checks passed. These are implementation checks against the proven bound on fixed traces; they do not prove the theorem, validate the trace construction or identify a deployment effect.

The main p99 results below are averages of five overlay-specific deadline-window quantiles, not a quantile after pooling all five overlays. SPJF-E and its guards in every capacity table and figure use the archived embedded Tweedie fit, distinct from the later package refit in the manuscript's headline tables. Brackets are pointwise 95% paired calendar-week bootstrap intervals. They are conditional on the five constructed overlays and their realised per-job outcomes; because all five overlays contain the same source terms and jobs, the intervals do not cover semester sampling, predictor fitting, queue-model structure, overlay design, feedback or transport to another service.

| $k$ | FCFS p99, s [95% interval] | SPJF-E p99, s [95% interval] | Guard(600) p99, s [95% interval] |
|---:|---:|---:|---:|
| 1 | 108,345.3 [92,267.4, 114,125.4] | 130,231.1 [65,565.9, 155,632.2] | 108,839.1 [92,739.3, 114,582.3] |
| 2 | 10,362.6 [7,565.1, 11,503.5] | 1,844.2 [766.70, 3,990.4] | 10,618.1 [7,820.3, 11,755.2] |
| 3 | 1,056.4 [688.91, 1,273.0] | 138.86 [105.79, 169.05] | 934.68 [452.24, 1,253.7] |
| 4 | 273.50 [197.09, 352.10] | 62.92 [53.69, 72.13] | 89.61 [65.94, 114.14] |
| 5 | 119.35 [92.91, 143.43] | 43.39 [37.94, 47.54] | 47.44 [40.46, 53.39] |
| 8 | 24.43 [18.46, 29.58] | 13.21 [9.58, 15.80] | 13.36 [9.67, 16.05] |
| 14 | 0.8360 [0.4536, 1.50] | 0.4687 [0.2978, 0.7283] | 0.4687 [0.2978, 0.7283] |
| 20 | 0.0000 [0.0000, 0.0392] | 0.0000 [0.0000, 0.0254] | 0.0000 [0.0000, 0.0254] |

The single centred, coordinate-standardised 95% simultaneous band covers 80 absolute p99 differences declared after the pilot and before the full sweep: four non-oracle policies at $k=1,\ldots,20$. Positive support is capacity-dependent. SPJF-E has a positive simultaneous lower bound at $k=2,\ldots,12$; Guard(300) and Guard(600) do so at $k=4,\ldots,12$; Guard(1200) does so at $k=3,\ldots,12$. These are statements about this fixed-demand sensitivity, not universal invariance to pooling or capacity. At $k=1$, the FCFS-minus-Guard p99 differences are -208.61, -493.79 and -1,071.72 seconds for the 300, 600 and 1200-second promises, respectively; the simultaneous bands are wholly negative for each. At $k=2$, every guard also has a negative point estimate, and Guard(1200)'s band remains wholly negative. At $k=14$, all three guard point estimates are about 0.37 seconds but all simultaneous bands cross zero; at $k=20$, the point differences are zero. The sweep therefore falsifies a universal positive-benefit claim across capacities at which some queueing can exist.

Aggregate tail improvement does not mean every job improves. For Guard(600), the observed maximum excess wait over same-input FCFS is 515.84 seconds at $k=4$ and 124.38 seconds at $k=20$; among jobs whose FCFS wait is at most one second, the corresponding maximum harms are 339.06 and 37.37 seconds. These are finite-trace maxima, not population confidence bounds. At $k=4$, Guard(600) closes 0.8000 of the FCFS-to-SJF p99 gap, with pointwise interval [0.7620, 0.8388]; at $k=20$ the gap ratio is undefined because its denominator is not positive. Full pointwise and simultaneous tables are in report_capacity_tables.md.

The theorem floor and an operationally restrictive chosen promise are different
screens. Every overlay has FCFS deadline p99 above $(3-2/k)L$ at $k=1,2,3,4$;
none does at $k\geq5$ in the common grid. For Guard(600), the mean FCFS p99 divided
by the chosen promise is 180.58, 17.27, 1.76, 0.456 and 0.199 at $k=1,2,3,4,5$.
At $k=8$ the ratio is only 0.0407. Thus much of the positive-benefit range has a
promise large relative to typical tail waits, while very congested cells can satisfy
both a concentrated-cost screen (the top 1% account for 37.54% of capped work) and
a long-wait screen and still worsen p99. The two applicability screens identify
potential relevance; they are not sufficient conditions for a p99 improvement.
The figures mark the mean-FCFS theorem-floor screen, and the CSV also records the
number of individual overlays passing it. No shading is presented as an operational
service-level guarantee or a benefit theorem.

![Capacity envelope, gaps, harm and the zero-wait endpoint](capacity_envelope.png)

![Absolute p99 improvements with the declared simultaneous band](capacity_improvement_bands.png)

The largest observed wait is 412,270.29 seconds. Adding one 60-second service limit
gives 0.682 week lengths. This indicates material potential dependence across week
boundaries even though queue state is retained in every replay. The outcome-resampling
intervals should not be read as a stochastic queue-process bootstrap.

On overlay 0 alone, the extension retains FCFS, SJF, SPJF-E and Guard(600). FCFS still has one positive wait at $k=75$ and every policy has zero wait at the exact infinite-server endpoint $k=76$. This endpoint does not establish the same threshold for the other overlays or for an unseen demand process.

## Physical implementation and its estimand

All three physical policies completed and their independent artifact, timestamp,
observed-prefix and service-limit audits passed. Each executed all 2,151 jobs in the
same selected five-minute release window and drained its own empty-start service.
The window contains 4,118.215007 seconds of requested work, or 6.864 times its
two-worker release-window capacity. Its longest 1% of jobs carry 24.60% of requested
work, just below the separate 25% heuristic used for public and natural-window
triage. This window was selected by offered work, not by that screen or policy gain.

| Policy | Physical mean wait, s | Physical p99, s | Jobs waiting >1 s | Mean signed physical-minus-ideal error, s | Maximum absolute per-job error, s |
|---|---:|---:|---:|---:|---:|
| FCFS | 1,337.046139 | 1,763.304883 | 2,096 | +0.248124 | 0.486214 |
| SPJF-E | 142.793482 | 1,687.474329 | 1,468 | +0.315391 | 392.836259 |
| Guard(300) | 480.390671 | 1,783.648373 | 1,754 | +5.368542 | 1,354.102033 |

The last two columns compare each physical run with the ideal policy replay using
that run's own measured arrivals and holding costs; signed error is physical wait
minus ideal wait. Comparisons between physical
policies are descriptive because actual enqueue and holding times differ across
runs. In particular, Guard's measured p99 exceeds the separate physical FCFS p99
by 20.343490 seconds; this physical window does not establish a Guard p99 gain.
There is one selected window, so no confidence interval over windows is reported.

All 6,453 physical decisions pass the independent observed-prefix choice audit.
The physical Guard has 322 nonempty-fired-set decisions, all of which change the
base choice. The ideal measured-input Guard has 372, and 52 jobs have differing
firing indicators. An independent ideal-epoch audit checks all 2,151 dispatches
and 1,241,424 waiting-job budgets against the production kernel. The independent
physical audit in the stall checker reconstructs 1,127,815 waiting-job evaluations.
These establish rule conformance separately on the two event sequences, not
agreement of their firing epochs. Their dispatch positions differ for 1,753 jobs.

| Policy | Selection mean / p99 / max, ms | Decision-to-dispatch p99, ms | Maximum enqueue lateness, ms |
|---|---:|---:|---:|
| FCFS | 0.03276 / 0.08280 / 0.12990 | 0.12320 | 26.2313 |
| SPJF-E | 0.04448 / 0.11385 / 0.21460 | 0.13610 | 27.9367 |
| Guard(300) | 0.57363 / 1.13185 / 1.54630 | 1.14465 | 25.8120 |

![Measured waits, ideal discrepancies and instrumented selection overhead](physical_validation.png)

The physical experiment is a separate test of implementation and timing. Its selection rule was fixed before inspecting a new physical window: choose the complete calendar-aligned 300-second bin with the greatest total offered capped work in development overlay 0, breaking ties by earliest time. All jobs in that bin keep their source costs, scores and order; target release offsets preserve their inter-arrival spacing. Actual enqueue lateness is measured separately rather than assumed to be zero. Each policy starts with a new empty two-worker service and drains the entire window. This discards inherited full-trace backlog, so the result is not another estimate of the capacity sweep's full-trace percentile.

Under the frozen protocol, each worker occupies its slot by a timed sleep, and FCFS, SPJF-E and Guard(300) run sequentially. The nominal 60-second payload cap and the measured-service premise L=61 seconds are fixed in advance, as are B0=30 seconds, eta=0.5, gamma=0 and Bmax=356 seconds. An execution exceeding L is a failed premise, not a value to clip or a reason to increase L retrospectively. No hard real-time guarantee is claimed for an ordinary operating system.

The dispatcher learns realised holding cost only when it receives a completion message. The event log records target and actual enqueue, choice, dispatch, worker start and finish, and completion receipt separately. All accepted cross-process timestamps use the system-wide high-resolution performance counter. An initial attempt using the coarse Windows monotonic clock was stopped and retained as rejected measurement; PHYSICAL_PROTOCOL.md documents the probe, correction and successful synthetic checks. The choice audit reconstructs visible event prefixes independently; guard firing denotes a nonempty fired set, and an actual change from the base choice is counted separately. Measured service excludes dispatcher and communication delay. Consequently a simulator using measured arrivals and service is an ideal work-conserving comparator, and any physical discrepancy is retained. Checking the realised physical waits against the numerical bound is an observed-trace audit. The additional stall-corrected certificate below does not bound future idle-capacity loss or dispatch-to-start delay, and does not restore a fixed uncorrected 300-second promise.

The physical guard's theorem reference is shadow FCFS on that guard run's measured arrivals and costs. A separately executed physical FCFS run has different timing noise and is a descriptive comparison. We do not bootstrap jobs from one selected window to manufacture uncertainty over demand windows. The capacity experiment supplies conditional paired-week intervals; the completed physical experiment supplies per-job implementation and timing checks.

No reduced replica is claimed. Scaling arrival count and worker count by the same factor preserves a utilisation ratio but can change simultaneous arrivals, residual service and tail waiting times. The physical run retains the entire selected demand stream and explicitly uses a different capacity. Its input remains a window of the constructed 44-fold development overlay, not a historical source-platform queue. Timed sleeps do not establish portability of submitted-program execution costs.

### A failed job-level equivalence claim

Selection wall time includes the instrumented waiting-set scan and construction of
per-job guard evaluations. It excludes later JSON serialization and logging, IPC
send, and worker startup; the separate decision-to-dispatch, dispatch-to-start and
completion-receipt measurements distinguish these boundaries. It is an overhead
measurement for this auditable controller, not a benchmark of an optimized
production implementation. Per-decision process CPU readings are quantized on
this platform; zero readings do not imply free computation.

The completed FCFS run has the same dispatch sequence as its measured-input ideal
replay, with a maximum absolute per-job wait difference of 0.486214 seconds. SPJF-E
does not: its mean wait difference is only 0.315391 seconds, but one job differs by
392.836259 seconds. The absolute discrepancy has median 0.110207 seconds, p95
0.429925 seconds and p99 0.642782 seconds; ten of 2,151 jobs exceed one second,
two exceed ten seconds and one exceeds 300 seconds. Aggregate agreement would
conceal this failure of job-level trajectory fidelity.

Guard's disagreement is more extensive: median absolute wait error is 58.423388
seconds and p99 absolute error is 1,171.599374 seconds. Its small signed mean error
results from cancellation of positive and negative discrepancies. The SPJF-specific
arrival-crossing diagnosis below was not repeated for Guard and does not identify
the cause of each Guard discrepancy; differing firing histories are also present.

`diagnose_physical_discrepancy.py` reconstructs the waiting sets of both stored
sequences without running another simulator. At the first differing dispatch,
index 130, ideal SPJF selects job 128 whereas the physical service selects job 158,
whose score is smaller. Job 158 is enqueued 1.1282 milliseconds after the mapped
ideal epoch; the physical decision occurs 24.7613 milliseconds after that epoch,
when the new job has already waited 23.6331 milliseconds. The waiting sets differ
only by that new job. All eight starts of differing-prefix episodes are arrival
crossings; 39 mismatching positions involve a newly available arrival and 1,362
inherit earlier order divergence. Both stored sequences make the minimum-score
choice on their own waiting sets at every step. These checks support an
arrival-crossing and priority-cascade explanation, not a different base-choice
formula. They do not decompose the sources of the initial timing delay or provide
an independent audit of the stored ideal replay.

The extreme job is dispatched at ideal position 361 and physical position 1,761;
its wait changes from 7.353180 to 400.189439 seconds. This is consistent with the
non-continuity examples in TRANSPORT_BOUND.md: small timing perturbations need
not produce small SPJF waiting-time perturbations. It prevents a blanket claim
that the ideal simulator reproduces every physical job, even when the observed
decision-prefix audit passes.

### A guard certificate allowing dispatch stalls

Ideal trajectory agreement is not required for the observed-trace pathwise certificate.
STALL_BOUND.md extends the workload and overtaking accounting to the actual serial
dispatch sequence. Write d_i for dispatch, s_i for physical start, ell_i=s_i-d_i,
and J(t) for cumulative idle worker-time from the empty initial state whenever
at least one released job has not physically started. Assigned jobs awaiting
startup count in this last condition. Under the common-clock, finite-job and
non-preemptive assumptions in that proof, every job with actual enqueue time
a_j<=theta must be admitted before a decision at theta, including all equal-time
ties. Decisions and dispatches are serial, the guard follows the correct rule on
each observed prefix, 0<C_i<=L, and a worker slot cannot be reused until its preceding
holding cost has been received and charged. For gamma=0 the physical wait satisfies

\[
W_P[i] < \min\left\{W_F[i]+G+J(d_i)/k,\;
\frac{W_F[i]+B_0/k+(3-2/k)L+J(d_i)/k}{1-\eta}\right\}+\ell_i.
\]

Here F is shadow FCFS constructed from this Guard run's own actual enqueue times
and measured worker-holding costs f_i-s_i, not the separately timed physical FCFS
run. The proof
allows arbitrary finite dispatch and completion-receipt delays and does not assume
the physical and ideal dispatch orders agree. For this experiment the two branches
are W_F+300+J/2 and 2W_F+274+J, followed by ell_i. J is measured in worker-seconds;
the resulting correction is in seconds. This is an ex post certificate until a
deployment also enforces advance bounds on J and startup delay. It does not convert
an ordinary operating system into a hard real-time executor or establish that the
uncorrected 300-second promise always holds there.

`check_stall_bound.py` verifies the assumptions, the exact workload identity and
both corrected branches for every Guard job, with zero numerical tolerance and
zero failures. It also checks the workload comparison at all 10,756 linear
endpoints. Maximum J(d_i) is 2.2526348 worker-seconds; maximum dispatch-to-start
delay is 0.4508 milliseconds. The largest actual additive correction J(d_i)/2+ell_i
is 1.1265093 seconds. The minimum combined corrected-bound margin is 78.76975885
seconds. The original uncorrected numerical bound also happens to hold on every
job: maximum excess is 222.2075511 seconds and minimum margin is 77.7924489
seconds. That last observation is not an advance promise for unbounded stalls.
The independent exact-nanosecond FCFS check differs from the production
microsecond-rounded shadow by at most 6.7 microseconds.

### Reduced replicas are a sensitivity, not an invariance

The predeclared thinning check retains each frozen job independently with probability
one half and halves capacity from four to two workers, preserving retained offsets,
costs and scores. Its 100 fixed seeds are not selected by outcome. The mean retained
work fraction is 0.501987, with central 95% Monte Carlo range [0.424867, 0.570736].

| Policy | Full k=4 p99, s | Half-thinned k=2 median p99, s | Central 95% Monte Carlo range, s |
|---|---:|---:|---:|
| FCFS | 760.161467 | 770.360117 | [611.392392, 908.282128] |
| SPJF-E | 796.253177 | 802.541935 | [654.479368, 917.028797] |
| Guard(300) | 812.893696 | 819.724824 | [674.531988, 966.663349] |

Mean p99 values across thinnings are within 1% of their full-reference values,
but the central relative ranges are about -19.6% to +19.5% for FCFS, -17.8% to
+15.2% for SPJF-E, and -17.0% to +18.9% for Guard. Thus a single reduced replica
cannot be treated as the full queue merely because expected work per worker is
preserved. The exact four-simultaneous-job counterexample in THINNING_PROTOCOL.md
also disproves general invariance. These are across-thinning sensitivity ranges,
not demand confidence intervals. All 107,526 retained Guard jobs and 4,302 jobs
in the two full-input references pass their same-trace production bound checks.

### Original-calendar follow-up stopped before measurement

The additional natural-window preflight did not produce a demand result. It
stopped before importing the guarded loading chain or reading/hashing either
event or score parquet, because the concurrently edited configuration module no
longer matched the recorded source hash. A source-only recovery searched the
reachable configuration history and line-ending/encoding variants but did not
recover that exact version. The fixed source gate was retained and the follow-up
was stopped; the separately prepared natural physical wrapper was not run.

This is a provenance limitation, not a failed heavy-tail or queue-wait screen.
No conclusion about original-calendar applicability follows. The completed
physical result remains a window of the constructed development overlay.
NATURAL_WINDOW_AUDIT.md and the retained preflight/recovery logs document the
failure and distinguish it from the untouched project sealed-data guards.

## Feedback: a theorem that survives and a benefit claim that does not


The statement in section 9 that open-loop policy gains are a lower bound is false without an additional assumption. FEEDBACK.md and feedback_counterexamples.py give exact finite examples with non-preemptive service, fixed positive user think times and the same eventual job identities under both policies. The first has jobs of lengths 10 and 1 arriving together, and the short job's user submits one more unit job half a second after completion. Replaying the FCFS-induced arrival vector makes SJF look better by 3 seconds of mean wait; allowing each policy to generate its own successor time makes SJF worse by 1/6 second. With standard linear interpolation, the same example gives an open-loop p99 benefit of 8.82 seconds but a closed-loop benefit of only 0.47 seconds. Earlier feedback places the successor behind the already running long job. A second example reverses the bias direction: its open- and closed-loop mean benefits are 9.2 and 11.16 seconds, and its p99 benefits are 10.00 and 10.18 seconds. No uncertainty interval is appropriate for these exact counterexamples: they refute a general implication, not estimate the feedback effect in CodeBench.

Endogenous arrivals do not invalidate the arbitrary-sample-path guard theorem. Given a guarded policy's realised arrivals and executed costs, shadow FCFS can be replayed on that same finite sequence and the per-job bound applies. Independently running FCFS in a closed loop would generally generate a different arrival vector. The difference between those two FCFS references is a feedback transport term for which the paper has no bound. This distinction preserves the guarantee while limiting the causal interpretation of replay benefit. Shadow FCFS is a retrospective benchmark after realised costs are known; no online access to future service costs is assumed.

## Conditional transport criterion

An additional analytical result in TRANSPORT_BOUND.md states what would make a
transport claim checkable. If two systems have the same job identities, service costs,
initial capacity state and FCFS arrival rank, and each identity's arrival changes by
at most epsilon, FCFS start times change by at most epsilon and waits by at most
2 epsilon. The same bound holds for a common-cohort mean or linearly interpolated
p99. It can transport a policy-trace shadow-FCFS reference to an independently
generated FCFS reference under those premises. The proof follows the sorted server
availability recursion. Rank changes and policy dispatch discontinuities invalidate
the analogous general claim for SPJF; cost changes add a cumulative perturbation term.
The present logs identify neither the counterfactual arrival vector nor epsilon, so
this is a conditional audit criterion rather than an empirical correction or a bound
on the reported open-loop benefit.

`transport_bound_check.py` checks 292 small exact integer or rational constructions:
264 same-rank FCFS cases, eight service-perturbation cases, 16 SJF dispatch
discontinuities at a fixed 60-second cost, and four FCFS rank swaps. All assertions
pass. These checks supplement the analytical proof and do not estimate epsilon.

## Public production queue audit

AUDIT_A.md distinguishes older measurements from any new retrieval. The two existing Mozilla pools validate parts of the queue approximation but have top-1% work shares of only 3.4% and 5.2%. Relative to their actual maximum maxRunTime, their recorded p99 waits are only 1.91 and 1.37 times L. The arm64 build pool is a narrower unresolved candidate: the earlier 132-run recency sample had top-1% share 12.7%, shared limits up to at least 15,000 seconds, and no retained p99 wait. Missing p99 is not evidence of failure. The short LPC-EGEE queue cannot borrow a 900-second theorem limit while sharing processors with queues capped at 259,200 seconds. No full collection or policy fit is justified solely by a heavy aggregate tail.

The bounded new probe made 10 read-only requests, below its cap of 25, to `releng-hardware/gecko-3-b-osx-arm64`. It recovered 140 distinct recent claim references from the last 20 claims of each of seven current workers; 133 runs had complete scheduled, started and resolved timestamps and valid task-specific `maxRunTime`. Their recorded wait p99 was 11,291.53 seconds and their maximum wait was 11,530.58 seconds. The largest observed task limit was 15,000 seconds, so p99 wait was 0.753 times the limit rather than the pre-specified three-limit screen. The longest two runs, the ceiling of 1% of 133, contributed 7.89% of service rather than the 25% tail-concentration screen. Neither condition passed.

This negative probe is only triage. Last-20-task histories from current workers are not a continuous or common arrival window, and they omit retired workers and tasks that never claimed a worker. The sample cannot establish historical capacity, complete arrivals or replay fidelity, and its p99 is unstable at this size. It therefore does not show that the pool lacks queueing, or that no public production system can satisfy the applicability conditions; it supports the stopping decision not to fit a policy to this truncated sample.

## Exact manuscript replacements

These are proposed replacements, not edits to the manuscript. The capacity sensitivity uses the explicitly identified cached predictor. Its numbers belong in a separate table/figure rather than silently replacing the existing package-refit tables. The physical wording below reports the completed audits and the failed priority-policy trajectory-equivalence claims.

### Section 1, final paragraph before the development-data qualification

Replace the two sentences beginning “The demand in every trace is real, recorded traffic.” and ending “what it does not.” (the complete source spans, including TeX references, are reproduced in REPLACEMENTS_REVIEW.md):

> The execution records are real, but not every arrival instant is recorded: CodeBench candidate arrivals are reconstructed as the recorded result timestamp, with the declared sub-second jitter, minus the recorded execution cost, while ACcoding retains its recorded \texttt{time\_cost} field and within-group submission-id order but draws every arrival instant. Interpreting ACcoding's reported runtime as executor occupancy, including the added fixed service term in that sensitivity, is a service-model assumption. The shared judging pools and their capacities are counterfactual designs rather than measurements of either source platform; Section~\ref{sec:data} states how the workloads and capacities are constructed and what those constructions can support. The fixed-demand comparisons and capacity sensitivity do not identify the effect of migrating either source platform to a shared pool.

### Section 7, “Building the Shared Pool”

Replace the sentence “The three load levels share that trace and differ only in the pool size.”:

> Within each overlay, the three headline load levels use the same reconstructed arrivals, capped recorded execution costs treated as modeled service requirements, and stored expected-cost scores and differ only in pool size. A separate capacity sensitivity reuses the stored \texttt{tweedie} score array in each existing development overlay without refitting, and retains the promises and capacity-scaled guard formulas declared after the overlay-0 pilot and before the full sweep, without re-selection. It evaluates every integer capacity from $k=1$ to $20$ on all five overlays; on overlay~0 alone, FCFS, SJF, SPJF-E and Guard(600) continue through the exact zero-wait endpoint at $k=76$. The five overlays contain the same source terms and jobs under different week shifts, so agreement across them is not evidence of invariance across semesters, deployments or demand processes. The extension is a sensitivity to authored capacity, not an estimate of an operator's optimal capacity or resource cost.

Retain the following sentences that specify the original 8/5/4 and 7/5/4 anchor capacities and their realised busy-hour loads. The new sweep does not alter those original measurements.

Replace the sentence beginning “Five overlays are week-shifts of the same terms” and ending “leaves the choice of terms uncovered.”:

> The five overlays reuse the same source terms and jobs under different whole-week shifts, so they do not constitute five independent platforms or demand samples. Our paired-week intervals reweight the realised per-job outcomes within these fixed constructions; they do not regenerate arrivals, propagate a new queue across resampled blocks, or cover selection of source terms, replicated-source dependence, predictor fitting, capacity design or transport to another deployment.

In “The Original Platform Has No Shared Queue”, replace the paragraph beginning “The second is a measurement on the same demand.” and ending “nor that any of it is a cost saving.”:

> The second comparison is an architectural sensitivity on the constructed overlay of Section~\ref{sec:overlay}. A 30-minute activity-based session proxy gives a p99 of \devnum{1{,}636} simultaneous containers and an execution fraction of \devnum{0.12\%}; neither quantity is directly observed container occupancy on the original calendar. Only \devnum{11\%} to \devnum{35\%} of logins have a subsequent recorded logout, and six session reconstructions give p99 counts of \devnum{1{,}003} to \devnum{2{,}525} and execution fractions of \devnum{0.07\%} to \devnum{0.17\%}. In the separate pooled replay, illustrative deadline-window p99 targets of \devnum{1}, \devnum{5} and \devnum{30} seconds require \devnum{14}, \devnum{11} and \devnum{8} FCFS servers, respectively, compared with \devnum{13}, \devnum{10} and \devnum{7} under the predictor-ordered policy used in that comparison. These are conditional simulation results for chosen service targets. Editing containers and judging executors serve different functions, and neither operator targets nor resource prices are observed, so the comparison identifies neither an economic capacity interval nor a cost saving or historical queue.

In the same section, replace the two sentences beginning “We use the log as a demand trace: arrival instants and per-job costs are real;” and ending “slowed down before a deadline.”:

> We use the log to reconstruct a candidate demand trace: the recorded execution cost is retained, and the candidate arrival is computed as the recorded result timestamp, with the declared sub-second jitter, minus that cost. The server pool, queue and order are our design. Nothing in this paper claims that the original platform slowed down before a deadline.

### Section 8, opening of “Setup”

Replace the first two sentences, from “All scheduling runs replay the overlaid CodeBench pool built in Section…” through “…so the comparison is pathwise.”:

> The principal scheduling comparisons replay the complete overlaid CodeBench workload with common reconstructed arrivals and capped recorded execution costs treated as modeled service requirements across policies, so those comparisons are pathwise conditional on the constructed workload. The separate capacity sensitivity uses the archived embedded \texttt{tweedie} fit, distinct from the later package refit in the headline tables, and the capacity-scaled guard formulas and ranges declared after the overlay-0 pilot and before the full sweep, as stated in Section~\ref{sec:overlay}; neither scores nor guard shapes are re-selected by capacity. We report absolute deadline-window p99 differences alongside gap closed, mark ratios with nonpositive reference denominators as undefined, retain negative and zero cells, and distinguish pointwise paired-week intervals from a simultaneous resampling band over the capacity--policy family declared after the pilot and before the full sweep. These intervals condition on five overlays constructed from the same source terms and jobs and do not cover semester, predictor-fit, queue-model or feedback uncertainty. In the $k=1,\ldots,20$ sensitivity with this archived fit, SPJF-E has a positive simultaneous resampling lower bound on its absolute p99 improvement at $k=2,\ldots,12$; the corresponding ranges are $k=4,\ldots,12$ for Guard(300) and Guard(600), and $k=3,\ldots,12$ for Guard(1200). At $k=1$ every guard has a negative point estimate and simultaneous upper bound, so the sweep does not support a positive benefit at every capacity at which queueing can occur.

Include the following second paragraph in that Setup replacement:

> We separately implemented FCFS, SPJF-E and Guard(300) on two local worker processes using timed payloads. A demand-only rule selected the complete five-minute bin with the most capped work in development overlay~0; all 2,151 jobs retained their target release offsets, without thinning or time compression, and each policy started empty and drained its queue. Every physical decision conformed to Algorithm~1 on its observed event prefix, and no measured holding time exceeded the predeclared 61-second limit. The ideal measured-input simulator reproduced FCFS waits within 0.487 seconds per job, but maximum absolute errors for SPJF-E and Guard were 392.84 and 1,354.10 seconds; physical and ideal Guard firing counts were 322 and 372. Thus this test establishes process-level rule conformance and real queueing on an authored pool, but not job-level trajectory fidelity for the priority policies. The physical Guard's maximum excess over shadow FCFS on its own measured arrivals and holding costs was 222.21 seconds, with no observed violation of the numerical 300-second bound. A separate pathwise derivation includes cumulative idle-capacity loss and dispatch-to-start delay; its largest additive correction on this run was 1.127 seconds and every job passed the corrected bound. This is a conditional retrospective certificate, not a fixed operating-system timing promise. Guard p99 was 1,783.65 seconds versus 1,763.30 seconds in the separately timed FCFS run, so the selected window does not establish a Guard p99 gain. The p99 instrumented selection-wall times are 0.08280, 0.11385 and 1.13185 milliseconds for FCFS, SPJF-E and Guard, respectively; these scans include guard-evaluation instrumentation but exclude later serialization, logging, IPC send and worker startup. One window provides no interval over demand windows, and timed payloads do not establish submitted-program performance or source-platform waiting.

### Section 8, interpretation of Table `tab:cross`

Replace the paragraph beginning “Two conditions decide whether the method is worth applying” and ending “at a promise of \devnum{5}$L$”:

> Table~\ref{tab:cross} reports two heuristic relevance screens. The first asks whether the per-job limit $L$ is small relative to the waits of interest. The smallest promise in this generic guarantee family is $(3-2/k)L$, close to \devnum{3}$L$; when FCFS p99 is below that scale, this bound cannot express a promise finer than that percentile. Four of the six workloads are below this screen. CodeBench, at \devnum{4.56}, and the serverless trace, at \devnum{4.22}, are above it. The compute farm is an extreme case: its FCFS p99 wait is \devnum{18.7} h against a per-job limit of \devnum{493{,}857} s, or \devnum{5.7} days. The second screen is cost concentration, which indicates the opportunity for short-job ordering. On the CI pools, the longest \devnum{1\%} of jobs carry \devnum{3.4\%} and \devnum{5.2\%} of the work; SJF worsens p99 relative to FCFS on three of the four windows, leaving no positive p99 gap there for the guard to retain. These screens describe the scale of the bound and the opportunity for reordering; neither is sufficient or proved necessary for a p99 benefit. In particular, the capacity sensitivity with archived Tweedie scores retains the same concentrated CodeBench costs, yet all three guard budgets worsen p99 at $k=1$, all have negative point estimates at $k=2$, and Guard(300) remains negative at $k=3$. Empirical benefit is specific to the chosen capacity, promise and predictor. The guard rows below the first screen remain ordering results; retaining a positive gap there does not show that the stated guarantee is useful at that wait scale. At the CodeBench and serverless operating points in Table~\ref{tab:cross}, the guard retains \devnum{0.48} to \devnum{0.71} of the gap, with observed maximum excess \devnum{2.5} to \devnum{3.8}$L$ at a promise of \devnum{5}$L$. These are measurements at those operating points, not consequences of passing the screens.

### Section 9, “The shared pool is our design”

Replace the block beginning “We use its logs as a demand trace: the arrival instants and the per-job costs are recorded;” and ending “waiting on the real platform, the pooled side being simulated throughout.” Retain the two existing deployment citations with the corresponding claim:

> We use its logs to reconstruct a candidate demand trace: each arrival is computed as the recorded result timestamp, with the declared sub-second jitter, minus the recorded execution cost, while the server pool, queue and scheduler are ours. Section~\ref{sec:data} explains that a fixed pool of judge hosts on one queue is a standard deployment \cite{domjudge_manual,peveler2019sandbox} and reports the container-to-pool comparison on the constructed demand \cite{smith1981pooling}. The fixed-demand capacity sensitivity cannot establish historical waiting on CodeBench. The timed-sleep protocol is limited to dispatch, process timing and completion accounting on one selected overlay window; it does not execute submitted programs or establish that recorded execution costs transfer unchanged to a different resource-isolation regime.

Retain the sentences qualifying the 44-fold overlay and the distinction between an editing container and a judging executor.

### Section 9, “Open-loop replay”

Replace the complete opening block from “Arrivals come from the log at their recorded instants…” through “…our reported gains are a lower bound.”:

> The replay holds arrivals fixed: CodeBench candidate arrivals are reconstructed from logged result timestamps, declared sub-second jitter and costs, while ACcoding arrival instants are drawn. Feitelson states the objection at its strongest, that ``logged workloads actually contain a `signature' of the logged system'' \cite{feitelson2021resampling}; a trace-driven simulation issues requests irrespective of system state, so a scheduler is neither rewarded with the work it would attract nor punished by the users it would drive away \cite{shmueli2009simulation}. The available records do not identify how arrivals would respond to changed completion times. Faster responses can release subsequent work either into a blocking interval or before a favourable dispatch opportunity, so open-loop replay can overstate or understate both mean-wait and p99 improvements; the reported gains are not a lower bound on a closed-loop deployment effect. The per-job theorem still applies to any realised arrival sequence, including one generated by feedback, when shadow FCFS is retrospectively replayed on that same sequence and the same executed costs; it does not compare two independently evolving closed-loop systems. The replay also freezes historical scores and recorded execution costs, although reordering can change when prior outcomes become visible to the predictor and a different contention or isolation regime can change wall-clock service requirements.

### Section 9, “Not studied”

Replace “Capacity is fixed throughout, so this is not a capacity-planning study.”:

> Capacity is fixed within each run and varied only over the sensitivity ranges declared after the overlay-0 pilot and before the full sweep; this is a sensitivity to authored capacity, not an estimate of an operator's optimal capacity, service objective or cost.

Replace the adjacent block beginning “The reported runs compare policies at a common set of enqueue instants” and ending “Nothing here was deployed.”:

> The fixed-demand runs compare policies at common reconstructed candidate arrivals and freeze the stored scores and capped recorded execution costs treated as modeled service requirements. Section~\ref{sec:prediction} measures feature-construction and prediction latency and charges it in a sensitivity, where it moves the closed gap by less than \devnum{0.001} at every load; that result does not supply a live feature store or account for policy-dependent result visibility. The separately pre-specified timed-sleep protocol uses cached scores and timed payloads and is limited to process-level dispatcher behaviour; it is not an operational judge and does not test program isolation, grading correctness, container start-up or application contention. The prototype executed locally; no policy was deployed on either source platform, and no economic or production effect is identified.

Retain the original cross-reference to the prediction section. REPLACEMENTS_REVIEW.md provides every full source span for an exact edit.

### Section 9, conclusion consistency

Replace the sentence beginning “The method needs a time limit” and ending “fail the first of those”:

> A time limit small relative to the waits of interest and a concentrated cost distribution are heuristic relevance screens: the former determines whether this generic bound can be stated on a useful scale, and the latter indicates the opportunity for cost-based reordering. Neither screen is sufficient or proved necessary for a p99 benefit. The capacity sensitivity shows that the sign and magnitude of the empirical effect also depend on the chosen capacity, promise and predictor.

### Remaining relevance-screen wording in Sections 1, 7, 8 and 9

The replacements above also require the following local consistency edits. These
edit anchors are in the current manuscript; they do not change the cross-workload
table's recorded values.

In Section 1's fourth contribution, replace the whole item beginning “An evaluation
on real logs from two programming-assignment judging platforms” with:

> An evaluation using execution records from two programming-assignment judging platforms and a serverless invocation trace, with every simulated guarded job checked against the theoretical bound. Cross-workload measurements report two heuristic relevance screens: the scale of the generic guarantee relative to the waits of interest, and the concentration of service work. Four of six workloads are below the wait-scale screen, and the two continuous-integration pools have low cost concentration. A separate development capacity sensitivity shows that these screens do not imply a p99 benefit, while a local timed-work implementation tests the decision rule and an observed-trace bound that accounts for dispatcher stalls.

Retain the original CodeBench, ACcoding, serverless, Netbatch and CI citations with
their corresponding dataset clauses. This item describes the new evidence without
classifying the screens as necessary or sufficient conditions for benefit.

In Section 7's data-overview table, replace the serverless role “method applies
outside education” with “cross-domain scheduling trace”, and the compute-farm
role “non-applicable case” with “recorded-queue long-limit case”. Replace the
sentence beginning “Costs are heavy-tailed on every workload except the CI pools”
with:

> Table~\ref{tab:tails} reports how much executed work is concentrated in the longest jobs. The CI pools have lower top-1% work shares than the principal CodeBench and serverless traces; this describes the opportunity for cost-based reordering, not a sufficient or necessary condition for a p99 benefit.

Replace the three-line sentence beginning “The per-job limit in the last column”
and ending “the method applies to.” with:

> The per-job limit in the last column sets the unit of the guarantee in Section~\ref{sec:theory}. Section~\ref{sec:exp_cross} compares that bound scale with the waits in each replay and reports cost concentration as a separate relevance screen; neither comparison identifies an operator's service objective or decides whether p99 must improve.

In Section 8's opening roadmap, replace “and where the method applies
(Sections...” with “and the cross-workload relevance screens (Sections...”,
retaining its two existing section references. Replace the entire caption of
Table~\ref{tab:cross} with:

> The same method on six workloads. Tail share is the fraction of executed work carried by the longest 1% of jobs; AUROC is for the heavy class from arrival-time information; excesses are in units of the per-job limit L used in that replay. The wait-scale screen asks whether FCFS p99 exceeds the generic floor (3-2/k)L, close to 3L. Four of the six workloads are below it, so this guarantee family cannot state a promise finer than that percentile there. The screen describes the scale of the bound, not whether ordering can improve p99.

In the same table header, replace the two stacked entries “Cond.” / “1?” with
“Wait-scale” / “screen?”.

In Section 9, replace the complete paragraph headed “Two applicability conditions,
each with traces that fail it.”, through the sentence ending “gives both conditions
in numbers.”, with the heading “Two heuristic relevance screens.” and:

> The first screen concerns whether this generic bound is informative at the observed wait scale. Using the per-job limits of the cross-workload replays, FCFS p99 divided by L is 0.021 on ACcoding, 0.136 on the compute farm, 0.373 on CI pool B and 1.78 on pool A. In each case FCFS p99 is below the generic floor (3-2/k)L, close to 3L. On the Intel Netbatch compute farm, the replay's 5.7-day service cap gives a smallest expressible promise of about 17 days, compared with an 18.7-hour FCFS p99 in the worst constructed window; predicted-cost ordering also worsens p99 there under sustained overload. A large bound relative to p99 does not imply that the guard cannot fire or that its mathematical guarantee is invalid; it limits what that guarantee says at the chosen wait scale. The second screen concerns the opportunity for cost-based ordering. On the two Firefox CI hardware pools, the longest 1% of jobs carry 3.4% and 5.2% of the work, with coefficients of variation 0.61 and 0.87, and true-size ordering worsens p99 on three of four measured windows. Neither screen is sufficient or proved necessary for a p99 benefit. The development capacity sensitivity retains the same concentrated costs yet shows negative Guard p99 effects at low capacities; capacity, promise and predictor must be stated with the empirical effect.

Retain the original Netbatch and Taskcluster/Treeherder citations with those
measurements. In particular the universal sentence that the guard “never fires
at any admissible budget” is removed; the inclusive zero-budget rule can fire.

### Additional metric-definition correction in Section 3


The requested Sections 1, 7, 8 and 9 changes above also require consistency with the
definition of firing rate. `PHYSICAL_SEMANTICS_REVIEW.md` verifies that both the frozen
kernel and the physical service count a firing whenever the fired set is nonempty;
the selected job can still equal the base choice. Replace the firing-rate definition
that uses “overrides the base policy” with:

> The \emph{firing rate} is the queue-length-weighted share of dispatch decisions at which the fired set $E(t)$ is non-empty. It records guard eligibility even when the minimum fired rank is also the base policy's choice; a changed-choice rate is a distinct statistic.

## What remains of the objection

The pool and the 44-fold demand overlay are still authored constructions. The study does not recover CodeBench's historical queue, demonstrate a production benefit, identify an economic consolidation decision, or show that original wall-clock execution costs remain invariant after changing resource isolation. Frozen historical features may cease to be available at the same arrival times after reordering. The timed-payload protocol can test occupied execution slots and scheduling logic, but not program isolation, grading correctness, container startup or application resource contention. The completed capacity and feedback results delimit fixed-demand sensitivity and identification; the successful event-prefix and bound audits do not turn a conditional replay into a causal deployment experiment. The ideal priority-policy replay also fails to reproduce every physical job or guard firing epoch, so rule conformance must not be presented as trajectory validation.

The earlier container comparison is a useful architecture illustration but cannot identify a plausible capacity interval from concurrency alone. Containers also serve editing and interaction, their lifetimes are only partly observed, and neither an operator's service objective nor prices are recorded. The old k=8..14 range corresponds to illustrative FCFS p99 targets between 30 and 1 second on one overlay; it is not a cost-optimal interval and it need not satisfy the guard's applicability condition. No ratio of container counts to executors is interpreted as a monetary saving.

In particular, the often quoted 1,636-container p99 belongs to the 30-minute activity
proxy after the same 44-copy overlay construction, rather than directly measured
simultaneous containers on the original calendar. Alternative session definitions
give 1,003--2,525 in that earlier overlay calculation; this is definition sensitivity,
not a confidence interval. Consequently those numbers cannot independently identify
the shared-pool capacity interval. The original per-semester and overlaid results
are distinguished in `evidence/consolidation/out_SUMMARY.txt`.

A sceptical referee can still ask for a real heavy-tailed, capacity-bound deployment with complete arrivals, actual service limits, historical capacity and a prospective policy comparison; for a model of resubmission feedback and dynamic feature visibility; for unoverlaid independent demand; and for uncertainty covering the design and transport assumptions. This report narrows what the replay supports instead of treating more simulation as evidence that the source platform queued.

## Verification, resources and reproduction

The structural capacity audit finds all 156 expected JSON and NPZ cell pairs, the complete declared policy/capacity scopes, 2,000 bootstrap draws, all 80 simultaneous-band coordinates and no guard-bound violation. The no-op resume validates every completed cell's protocol, parameters, policy rows and NPZ schema, shape and finite values, skips all five input loads and preserves the original execution ledgers. A final caption-only summary takes 3.198 seconds wall and 2.859 seconds CPU; both numerical curve CSVs remain byte-identical, as recorded in caption_rerun_audit.json. The two capacity figures and the physical validation figure were visually checked for labels, clipping and consistency with the reported estimands. The bounded Taskcluster probe uses 10 network requests and takes 6.60 seconds wall and 0.11 seconds CPU. The exact feedback constructions are checked against every reported recursion, mean and linearly interpolated p99 value.

The completed physical service, including its ideal and event-prefix audits, takes
6,212.054 seconds wall (103.53 minutes) and 25.3125 seconds of recorded root-plus-worker
CPU. The independent physical artifact check takes 0.258 seconds wall; the exact
stall accounting and bound check takes 4.697 seconds wall and 4.641 seconds CPU.
The thinning sensitivity takes 2.857 seconds wall and 2.797 seconds CPU. The artifact,
stall and thinning checks use single-process postprocessing after the physical workers
stop; no heavy experiment
overlaps another, and the only numerical/physical worker count used is at most two.

resource_ledger.json is the single source for aggregate timing. The recorded experiment
CPU total is 8,310.640625 seconds (2.30851 core-hours), and summed instrumented experiment
wall time is 10,696.044707 seconds (2.97112 hours). These sums include retained failed
or superseded measurements where their timers exist, without adding per-policy or
per-cell timers twice. The stopped coarse-clock attempt contributes a further
399.678354 seconds of wall time estimated from log timestamps, excluded from the
instrumented wall sum; its measured root CPU is included, while its worker CPU is
unknown. Other uninstrumented failed preparation/provenance attempts, interpreter
startup, Git subprocess CPU, read-only inspection and writing are listed as unknown
or excluded rather than assigned zero. Thus the CPU sum is recorded usage, not an
exact machine-wide total. Elapsed investigation time from PLAN.md creation is
reported separately: at the final ledger timestamp, 2026-09-21 16:11:32 UTC,
13,738.844482 seconds had elapsed (3 hours 48 minutes 58.84 seconds). This includes
analysis and writing between experiments; the earlier mandatory pre-reads and
subsequent final presentation checks are outside that clock.

Input and source provenance passed final verification. Another project run rebuilt the source-path overlays after all five sweep inputs had been loaded into memory. We retained that concurrent work and recovered the original five local backups only into this directory. Every restored file is 793,567,608 bytes and matches its pre-run development-manifest hash exactly. The simulator snapshot also matches the original recorded source hashes; unchanged project data guards and loaders remain in use. `verification.json` reports PASS for the full numerical and provenance audit, and `INPUT_DRIFT_AUDIT.md` records the failed candidate reconstruction and the exact recovery.

| Original development input | Verified SHA-256 |
|---|---|
| primary_rep0.npz | `4f5a6c84a59d1e60342593d26a81e92a38cb76a2b730c69a6babaffc983d4971` |
| primary_rep1.npz | `f300b3195d03bad713951bcf7051610ae6b7eb99753c61e85465299b9737b720` |
| primary_rep2.npz | `053b24fa860f2595ea2c0427945d107dabab1e65abf2e46a264678834dd3d981` |
| primary_rep3.npz | `84e95b15b9da99a4d6d6a9606c835db7396b552448995312bc238e2a3b4191e4` |
| primary_rep4.npz | `5581859bdf016c22f105563b43711543e4db908d3874ac1549d6a0adb454c1aa` |

Scripts, logs, checkpoints, tables and figures are retained in this directory, and README.md gives the reproduction commands. No commit or push was made.
