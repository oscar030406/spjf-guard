# Weakness 1: research plan

Written before new experiments on 2026-09-21. No prior files were present in this directory. Existing research elsewhere is read-only.

## Causal hypotheses

1. **Queue existence versus transportability.** Real demand on an elastic/private-container platform establishes offered work, but does not identify waiting under a pooled deployment. A physical timed-work service can establish implementation and measured queueing, not historical platform queueing or transportable service costs.
2. **Capacity selection.** Benefits may occur only at the authors' chosen capacities. An integer capacity sweep with fixed arrivals, costs, scores and guard parameters can falsify that concern within the observed demand, but cannot establish an operator's optimal capacity or a deployment cost saving.
3. **Demand feedback.** Results and delays may change subsequent submissions. The sign of a performance difference under that feedback need not follow the sign of throughput or wait improvements. Recorded-feature visibility can also change under reordering. Open-loop gains must not be called lower bounds without proof.
4. **Applicability and public queues.** A public production pool might jointly have concentrated costs, substantial recorded queueing relative to its actual maximum limit, and identifiable capacity/arrivals. Tail concentration alone is insufficient; an incomplete arrival sample or mixed-capacity queue cannot validate the simulator.
5. **Implementation fidelity.** Real dispatcher latency, completion ordering and timeout enforcement could break simulation correspondence or the guard's accounting. Per-job instrumentation is needed for any physical claim.

## Options and expected value

- **A, bounded search:** inspect the already attempted pool evidence and use a small new Mozilla pool sample only if it can measure real queue delay, cost concentration, actual maxRunTime and sample coverage. Reject before fitting if either applicability condition fails. Do not repeat broad searches or the already rejected HPC/shared-short-queue shortcut.
- **B, physical execution:** useful for the simulation-only objection, but it retains authored capacity and synthetic timed service. With two workers, thinning may substantially change burstiness and must first be compared with full replay. A defensible real-time run requires measured arrivals, starts, completions and guard interventions, and cannot be accelerated. Estimated cost: several hours for meaningful replicated windows.
- **C, capacity envelope:** highest expected value and lowest data/operational risk. Reuse guarded development loaders, cached scores and the production simulator. Sweep all relevant integer capacities from overload through disappearance of queueing, with special attention to the independently interpretable region where FCFS busy-window p99 exceeds the theorem floor. Report failures, undefined gaps, per-job harm and guarantee checks, paired week/window uncertainty and the full capacity curves. Existing consolidation evidence motivates sensitivity, not an economically identified interval.
- **D, feedback falsification:** inexpensive and logically necessary. Check the lower-bound assertion analytically with concrete reproducible counterexamples and, if development fields permit, quantify observable within-user feedback/visibility without causal overclaiming.

## Initial choice and stopping rules

Primary: C, with D as the second completed line. A receives only a bounded evidence audit and cheap falsification. B will be promoted only if the guarded-cache audit supplies a natural two-worker real-time window and it adds evidence beyond C without selection on policy benefit. This initial choice is recorded before inspecting new development statistics; amendments below will state their reason.

For C, first inspect the loader and simulator interfaces, then run a small pilot to determine data size, useful k range, state/warmup treatment and compute cost. Freeze the final sweep and bootstrap specification in this file before running it. Do not select capacity or windows by the measured policy advantage. Preserve all failed/negative cells.

## Execution boundaries

All writes, scripts, logs, temporary files and caches are confined here. No changes or hashes of sealed inputs; no sealed CodeBench terms, ACcoding final id block or OULAD 2014 are opened. Development data is obtained only through the project's guarded data loaders. Source modules are imported read-only with bytecode disabled and compiler caches redirected here. No commits, pushes or changes to the paper. At most two workers, four numerical threads, one heavy experiment at a time; no process-name termination or polling loops. Other ongoing jobs are left alone.

Every experiment has an executable script with its parameters recorded inside it and an adjacent out_*.txt log. Record wall and CPU time, exact scope and failures. Public retrievals, if needed, are unauthenticated read-only requests at <=4/s; downloaded bytes go under raw/ with provenance, size, hash and licence. Large downloads require df and >=50 GB remaining disk space.

## Deliverables and acceptance

README with reproduction, scripts/logs, machine-readable results and standalone plots, and REPORT with numerical intervals, theoretical-bound checks, exact original/replacement prose for sections 1/7/8/9, surviving objections and measured compute/wall time. No production-deployment claims, no universal capacity claim unless every eligible capacity supports it, no lower-bound claim about open-loop benefits without a valid argument. New evidence is development-only.

## Frozen capacity protocol after the pilot

The pilot used primary overlay 0 (17,634,760 jobs; 4,219,556 deadline-window jobs) and found exact infinite-server peak occupancy 76. FCFS deadline p99 was 110,194 s at k=1, 263.12 s at k=4, 22.17 s at k=8 and 0.2225 s at k=16. These values select coverage, not winning capacities. One Guard(600) pilot at k=4 passed all 17,634,760 bounds. Total pilot runtime was 96.94 s. The pilot's start-anchored hourly work is not the paper's calendar-hour work; the final experiment uses stored W and stored week indices, which preserve the original calendar alignment.

Final scope: all five existing primary development overlays at every integer k=1..20, six policies (FCFS, true-size SJF, cached expected-cost SPJF-E, Guard(300), Guard(600), Guard(1200)); overlay 0 additionally at every k=21..76 with FCFS, SJF, SPJF-E and Guard(600). At and above 76 on overlay 0, infinite-server occupancy proves every work-conserving policy has zero wait. Every run starts at the trace beginning and drains all jobs; there are no busy-window resets, arrival thinning, time compression or recomputed predictors. Original cached tweedie scores are used unchanged, distinguished from later package refits. Guard shapes are copied from configs/main.yaml: (B0/k, eta, gamma/k)=(15,.5,0), (30,.75,0), (0,0,4), with their respective G caps. No parameter is selected here.

Each cell records primary p99, all-job mean/p99, FCFS-to-SJF gap (undefined for nonpositive denominator), absolute/relative improvement, harm among FCFS wait <=1 s, maximum excess, firing rate, wait probability and busy-hour offered work/(3600 k). The theorem floor (3-2/k)L, actual G and FCFS primary p99 are reported separately: floor eligibility does not imply that a particular G is operationally tight.

Intervals use 2,000 paired resamples of the existing 30 week indices (seed 20260921), identical multiplicities across policies, capacities and overlays. Each resampled p99 is recomputed from its full weighted job distribution using the package implementation; overlay estimates are averaged as in the paper. Replicates are not independent datasets. Pointwise percentile intervals are labelled as such. Undefined ratio draws remain missing and their counts are reported. Capacity-wide positive-benefit claims additionally require a simultaneous centred bootstrap band for absolute p99 differences over the declared k=1..20 family; the band covers all three guards and SPJF-E, and does not claim structural/model uncertainty. A minimum over a selected subrange is descriptive unless separately covered by that band.

Existing consolidation k=8..14 is an illustrative service-target range from prior work, not an identified economic capacity interval: private containers also serve editing and no price or SLO is observed. The sweep may falsify a universal benefit claim, which will be retained in the report. B is not promoted: changing the load by thinning and physically sleeping would add implementation evidence but would not identify demand feedback or operator capacity. Two completed lines C and D address those causes more directly within this study.

Execution refinement, with scope and statistics unchanged: the initial serial invocation is preserved and its completed cells reused. It was stopped by its verified process id (other jobs untouched); its process CPU time is in initial_execution.json. The resumed command has exactly two computational workers. An exact shortcut is permitted for age guards only: if the imported In/Out sweep on SPJF shows In_i < the policy's actual integer B0 for every job, then the completed overtaking work at any earlier waiting epoch is also below B0 and the fired set is empty. First-divergence induction proves that the guarded and unguarded dispatch sequences coincide. Such cells are marked certified_identical, still checked job by job against the bound, and the first two certificates per overlay are compared against actual guard-kernel waits, dispatch orders and zero firing. The strict inequality is essential. The shortcut is not applied to the queue-length guard with B0=0.

## Physical execution added after the early capacity falsification

The first complete k=2 cell falsified a stronger universal-benefit reading: SPJF-E materially improves deadline-window p99, but each pinned guard slightly worsens it. At k=3, Guard(300) also worsens that percentile. The capacity study is retained in full to describe the boundary, but it cannot on its own remove the unexecuted-mechanism objection. We therefore promote B to a concrete, bounded third component while retaining D as an inexpensive exact logical check.

Before inspecting a physical input window, fix its selection as the complete 300-second calendar bin with the largest total offered capped service on primary overlay 0. Retain every arrival and its original spacing and cost; do not thin, compress time, choose by policy benefit or claim a scaled replica of k=4. Execute this same demand on k=2 actual worker processes under FCFS, SPJF-E and Guard(300), sequentially, starting a new empty service for each policy and draining all jobs. The service is a controlled timed-work experiment, not a historical queue or a reconstruction of the full trace's inherited backlog. Its nominal costs are capped at 60 s; predeclare L=61 s to allow timer/IPC variation, and mark any observed service exceeding 61 s as a model-assumption failure rather than increasing the limit afterwards. Guard parameters are B0=30 s, eta=.5, gamma=0 and Bmax=356 s. There is no claim that an ordinary operating system enforces a hard real-time 61-second bound on future executions.

The physical run begins only after the two-worker capacity sweep has stopped. Record scheduled and actual enqueue times, worker starts/completions, measured service, dispatcher and completion-receipt delay, every decision and guard intervention. Audit Algorithm 1 independently on every realised event prefix; compare measured per-job waits with the production simulator under the same measured arrivals and service for that policy; check the simulated and measured guard waits against same-input shadow FCFS and disclose overhead-related model discrepancy or violations. Comparing to a separately executed physical FCFS run is descriptive because measured service durations can differ slightly across runs. Measure dispatcher CPU/wall overhead. Do not manufacture a confidence interval over demand from one window; the capacity study supplies paired-week intervals, while this component is an instrumented implementation validation on one deterministically selected window.

Thinning is deliberately not used. Equal scaling of offered work and k preserves a first-moment utilisation ratio but need not preserve burst multiplicity, integer capacity, residual service or a tail quantile. Running the unthinned window at k=2 makes the changed capacity explicit and avoids interpreting a reduced stream as an equivalent full-size deployment.

## Reporting corrections from static statistical review

Before the aggregate summaries were run, a separate review tightened two inferential labels. A ratio interval will be reported only when all 2,000 bootstrap denominators are positive; the number of undefined draws remains visible, and absolute p99 differences retain their intervals. This avoids presenting an interval conditional on a selectively defined subset of draws. The observed maximum excess and harm remain exact finite-trace maxima. Percentiles of their empirical week reweightings are labelled resample stability ranges, not confidence limits for a future or population maximum. No queue simulation, random draw, policy setting, point estimate or simultaneous-comparison family changes. The artefact verification script additionally binds the exact frozen protocol and row parameters and audits certificate spot-check coverage by overlay.

## Concurrent source and input changes: resolved before physical execution

Another ongoing project run changed the simulator's optional age-credit extension,
configuration, and development overlay files while this study was running. All five
capacity inputs had been loaded by 09:18:59 local time, before their first overwrite at
09:24:35. The completed cells retain the original arrays and cached scores. Validation
first rejected changed source hashes, then changed input hashes; neither mismatch was
ignored. The additive-cache reconstruction attempt failed its original SHA-256 check
and remains a rejected diagnostic. Re-serialising its retained members reproduced that
same rejected candidate, so it was not adopted.

The original simulator source was recovered from the repository revision and matched
against the source hashes recorded before computation. An AST comparison identifies
the only runner/policy change as a default-zero age-credit extension, unused by all
studied policies. Future reproduction uses the matched snapshot under `pinned_src/`;
the unchanged project data guard and loader still govern development reads. Five
original local backup overlays were copied only into `raw/recovered_development/`.
All five sizes and SHA-256 hashes match the earlier development manifest exactly,
including the embedded scores. `recovered_development_inputs.json` records provenance.
`verify_artifacts.py` then passed all 156 cells, 824 policy rows, 6,277,974,560 per-job
checks, source snapshots and five input hashes. No concurrent project work was reverted.

The physical input selection completed at 10:00 local time on the recovered original
replicate: 2,151 jobs and 4,118.215007 seconds of requested work. Nominal makespans are
about 2,061--2,064 seconds per policy, or an estimated 103 minutes for three sequential
real-time runs. This resource estimate was obtained after the fixed demand-only
selection and did not change it. The full service started at 10:02. It uses the stored
44-copy overlay offsets, not an unmodified historical platform arrival window.

## Physical clock correction before accepting measurements

The first partial physical run exposed coarse timestamp quantisation. A direct clock
probe established that this Python 3.12.13 build maps `monotonic_ns` to GetTickCount64
(15.625 ms resolution), which can assign zero holding time to a short job. At 10:08:41
we stopped only the verified experimental root and its two children. Version-1 code,
input metadata, smoke artefacts and partial events remain available. This is rejected
measurement, not a completed policy run.

Protocol version 2 replaces event timestamps with `perf_counter_ns`, the system-wide
monotonic QueryPerformanceCounter with observed 100 ns increments, and rejects a
clock worse than one microsecond at startup. The job arrays, selection, requested
costs and policy parameters are identical. The revised smoke fixture initially exposed
that serial enqueue timestamps differ from simultaneous target releases: an ideal
empty server can start the first enqueued job before the physical batch decision.
Its failed assertion is retained. A six-job fixture with the first two jobs occupying
the workers then passed all physical and ideal audits, including nonempty guard firing
and changed choice. The full version-2 service began at 10:11:03. Its final acceptance
will additionally use an independent exact-nanosecond FCFS recurrence and per-job bound
comparison so that microsecond rounding is not the basis of the physical promise check.

## Two bounded checks fixed while the physical run is in progress

The physical input is a constructed overlay window, so it cannot establish that the
same queue arose on the source calendar. A text-only provenance audit now identifies
a safe original-calendar development cache: the documented development-only rebuild
compared all 58 columns, including semester, with the existing event cache and found
them equal; the protocol lock binds its size and hash. The stored score file has an
independent matching development manifest. `NATURAL_WINDOW_AUDIT.md` records these
sources. Neither parquet file has yet been opened in this investigation.

After the running service stops, `natural_preflight.py` will first check those text
proofs and both project semester guards, then bind the documented development hashes
and call the project's guarded event-loading chain. Any refusal or mismatch stops
the check. It aggregates the six primary terms on their original absolute calendar,
selects the complete 300-second bin with the largest capped offered work, and keeps
every primary job in that bin. It uses reconstructed candidate arrivals (result
timestamp plus the declared deterministic jitter minus recorded cost), not recorded
enqueue timestamps. No overlay, replication, thinning, time compression or score fit
is permitted. The original simulator snapshot and exact clock configuration are
checked before the nominal FCFS, SPJF-E and Guard(300) replays.

The demand-only selection and follow-up gate are fixed before measurement. A second
physical window is justified by both FCFS p99 wait of at least 183 seconds (three
predeclared 61-second limits) and a top-1% capped-work share of at least 25%. Guard
firing is reported separately and is required for a full intervention audit. If the
screen fails, retain the result and stop this line; do not select a different window
by its policy advantage. A passing follow-up must use separate output paths and all
the timing, event-prefix, simulator and exact per-job bound checks of the first run.

`thinning_check.py` separately tests the proposed reduced-replica interpretation on
the already frozen 2,151-job physical input. The full k=4 replay is the reference;
100 independent Bernoulli-half samples, with seeds 20260921 through 20261020, retain
their original offsets, costs and scores and run at k=2. An unthinned k=2 result is
also retained. FCFS, SPJF-E and Guard(300) are all checked, with every guard job tested
against its same-input bound. Across-thinning central ranges describe Monte Carlo
sensitivity of this one window, not confidence intervals over demand. Neither the
window nor a thinning seed will be selected for a favourable policy result. This
small simulation begins only after both physical worker processes have stopped.

## Dispatch discontinuity and a measurable stall correction

The completed physical SPJF-E run passed every observed-prefix choice check but
did not match the ideal measured-input replay job by job: the maximum absolute
waiting-time difference was about 393 seconds despite a mean difference of about
0.32 seconds. This is a failed high-fidelity claim, not a reason to change the
window, timestamps or ideal replay. A bounded, read-only postprocessing script
will locate the first differing decision and trace the recorded permutation of
jobs, without constructing another scheduling run.

The physical dispatcher is not instantaneously work-conserving. Before integrating
its completed Guard logs, we state and prove a candidate extension in STALL_BOUND.md.
It adds the cumulative idle worker-time while any released job has not physically
started, divided by k, and the particular job's dispatch-to-start delay. Completed
costs must be charged before a worker can receive another assignment. The analysis
uses the actual dispatch sequence, not an assumed coupling to an ideal policy run.
An exact-integer check will reconstruct the accounting identities, these premises,
both bound branches and their margins. The correction is an ex post certificate;
without advance bounds on dispatch stalls it is not a fixed operational promise.

## Original-calendar preflight: source drift before data access

The first natural-window invocation stopped at its source-code binding gate before
importing the guarded loader or reading/hashing either parquet input. The concurrently
edited config.py no longer matches the frozen source hash. This is not a sealed-data
loader refusal and supplies no evidence about natural-window load or tail behaviour.
The failed launcher log is retained. We will attempt byte-exact recovery of the
already declared configuration module into this directory, bind the recovered file
to the original expected SHA-256, and leave the current repository file unchanged.
Only that frozen configuration import may change; the project's current, hash-bound
data guards/loaders and every development-data provenance gate remain mandatory.
If exact source recovery fails, this follow-up stops. No window, score, policy,
capacity, relevance threshold or data guard is changed by this amendment.
