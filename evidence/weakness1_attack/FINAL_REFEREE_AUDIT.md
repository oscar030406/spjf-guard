# Final hostile-referee audit

Final disposition: REPORT.md incorporates the completed-result review as well as
the earlier checkpoint below. It now includes signed-error labels, the instrumented
overhead boundary, the retrospective stall certificate, capped modeled service-cost
wording, the post-pilot declaration timing, and additional exact replacement text
for residual relevance-screen claims in Sections 1, 7, 8 and 9. The current resource
section uses the completed ledger. Historical issue descriptions below are retained
as review evidence, not unresolved instructions. The original-calendar follow-up
remains unmeasured because its own frozen source version could not be recovered.

Historical review checkpoint: the comments below refer to the report before the
final physical and follow-up checks. Items 1--5 have since been incorporated in
REPORT.md. In particular its applicability replacement omits the unsupported
claim below that the guard can never fire at any admissible budget. REPORT.md is
the authoritative replacement text; the older suggestions remain here as review
history. Final measurement and resource status is reported there.

## Scope and verdict

This audit reads the current report, capacity CSVs, coverage and verification records,
the physical protocol, the natural-window audit, the feedback and transport analyses,
and the current manuscript text. It does not inspect any NPZ or parquet file and does
not recompute a result.

The capacity numbers used in `REPORT.md` agree with `capacity_curve.csv`; the declared
156 cells and 824 policy rows pass the independent verification script, ratio intervals are absent
when all 2,000 denominators are not valid, and the negative capacity cells have been
retained. The feedback counterexamples and the conditional FCFS transport theorem are
stated with the right estimands. The remaining defects are primarily claim alignment,
not evidence that the reported capacity arithmetic is wrong.

## Must fix before using the replacement text

### 1. The manuscript's applicability conclusion now contradicts the capacity result

`REPORT.md` correctly concludes that the long-wait and concentrated-cost screens are
relevance screens, not sufficient conditions for a p99 improvement. The manuscript still
says that the two conditions “decide whether the method is worth applying,” that
CodeBench and the serverless trace are the workloads on which it “applies as designed,”
and that where both conditions hold the guard retains a stated fraction of the gap
(`08_experiments.tex`, lines 659--678). The conclusion similarly presents the two
conditions as the method's workload-level requirements (`09_limitations.tex`, lines
180--184).

The new sweep directly defeats that wording: CodeBench satisfies both screens, yet all
three guards worsen p99 at `k=1`; all three have negative point estimates at `k=2`; and
Guard(300) remains negative at `k=3`. The proposed Section 8 replacement edits only the
setup and therefore leaves the contradiction intact. Replace the applicability paragraph
and the conclusion so that applicability is capacity- and promise-specific and the two
screens are explicitly labelled heuristic relevance screens rather than a benefit
criterion. The sweep shows that they are not sufficient; it does not prove either screen
necessary for a positive p99 effect.

**Exact Section 8 replacement.** In `08_experiments.tex`, replace the paragraph beginning
“Two conditions decide whether the method is worth applying” (line 659) and ending
“at a promise of \devnum{5}$L$” (line 678) with:

> Table~\ref{tab:cross} reports two heuristic relevance screens. The first asks whether
> the per-job limit $L$ is small relative to the waits the operator cares about. The
> smallest promise in this generic guarantee family is $(3-2/k)L$, close to
> \devnum{3}$L$; when
> FCFS p99 is below that scale, the guarantee cannot express a promise finer than that
> percentile. Four of the six workloads are below this screen. Only CodeBench, at
> \devnum{4.56}, and the serverless trace, at \devnum{4.22}, are above it. The compute
> farm is the extreme: its jobs run for days, so its FCFS p99 wait is \devnum{18.7} h
> against a per-job limit of \devnum{493{,}857} s, or \devnum{5.7} days. The second
> screen is cost concentration, which
> indicates whether short-job ordering has substantial work to move. On the CI pools the
> longest \devnum{1\%} of jobs carry \devnum{3.4\%} and \devnum{5.2\%} of the work, and
> SJF makes p99 wait worse than FCFS on three of the four windows, so those windows have
> no positive p99 gap for the guard to retain. These screens describe the scale of the
> guarantee and the opportunity for reordering; neither is sufficient or proved
> necessary for a p99 benefit. In particular, CodeBench is above both screens, yet in
> the capacity sweep all three guard budgets worsen p99 at $k=1$, all have negative
> point estimates at $k=2$, and Guard(300) remains negative at $k=3$. Empirical benefit
> is therefore specific to the chosen capacity and promise. The guard rows for workloads
> below the first screen are retained as ordering results; even where ACcoding and CI
> pool~B retain most of a positive gap, they do not show that the stated guarantee is
> useful at that wait scale. At the CodeBench and serverless operating points in
> Table~\ref{tab:cross}, the guard retains
> \devnum{0.48} to \devnum{0.71} of that gap and the observed maximum excess is
> \devnum{2.5} to \devnum{3.8}$L$ at a promise of \devnum{5}$L$; these values are
> measurements at those operating points, not consequences of passing the screens.

This wording preserves the table's descriptive cross-domain comparisons while removing
the unsupported decision rule and the categorical claim that two workloads “apply as
designed.” It also avoids treating either screen as mathematically necessary for an
improvement.

**Optional conclusion consistency replacement.** In `09_limitations.tex`, replace the
sentence beginning “The method needs a time limit” (line 182) and ending “fail the first
of those” (line 184) with:

> A time limit small relative to the waits of interest and a concentrated cost
> distribution are heuristic relevance screens: the former determines whether the
> guarantee can be stated on a useful scale, and the latter indicates whether cost-based
> reordering has substantial work to move. Neither screen is sufficient or proved
> necessary for a p99 benefit. The capacity sweep shows that the sign and magnitude of
> the empirical effect also depend on the chosen capacity and promise.

This is an optional consistency edit in addition to the requested Section 8 replacement;
it does not change the theoretical pathwise guarantee.

### 2. The capacity study is not complete through queue disappearance on all overlays

`REPORT.md` line 9 calls the work a “complete capacity sensitivity.” All five overlays
are covered only for `k=1..20`; only overlay 0 and only Guard(600), FCFS, SJF and SPJF-E
continue through the exact no-wait endpoint at `k=76`. Queue-disappearance capacities
for overlays 1--4 and the two other guards above `k=20` were not evaluated. This is
already described accurately elsewhere in the report, so “complete” should be replaced
by “the declared capacity sweep.” The result supports a full common-grid sensitivity and
one endpoint extension, not the design-free statement “for every pool size at which this
demand queues” across all five constructions.

The simultaneous family was fixed after a pilot on overlay 0 had revealed p99 values at
several capacities and one Guard(600) result. “Predeclared” should therefore mean
“declared after the pilot and before the full sweep,” not a confirmatory family specified
before looking at this development demand.

### 3. The proposed edits leave two strong Section 7 overclaims in place

The current overlay paragraph says week resampling “covers time” (`07_data.tex`, lines
218--220). The capacity analysis instead reweights already realised job outcomes; it does
not rerun queue state, and the same source jobs are replicated across week blocks. The
report explicitly excludes cross-week queue state and replicated-source dependence from
coverage. Retaining “covers time” after inserting the proposed Section 7 text would undo
that qualification. Replace it with the exact conditional outcome-resampling scope.

The current consolidation paragraph says “Pooling is worth two orders of magnitude” and
“the scheduler is worth one server” (`07_data.tex`, lines 142--155). Those are stronger
than the report's own finding that container lifetimes are reconstructed, containers also
serve editing, the p99 targets are illustrative, and no operator objective, prices or
economic capacity interval are identified. Replace the two “worth” claims with a purely
descriptive statement about the authored overlay and chosen p99 targets. The existing
qualification after those claims does not neutralise their economic wording.

### 4. Keep the archived score fit distinct from the paper's current SPJF-E fit

The capacity sweep uses the `tweedie` arrays embedded in the old overlays, while the
current paper tables use a later package refit. The report acknowledges this, but its
replacement text later calls the capacity curve simply “SPJF-E.” The artifacts visibly
differ: at `k=4` the capacity curve reports 62.9186 seconds, while the current headline
table reports 62.79 seconds. Label the sensitivity policy and its guards as using the
stored Tweedie fit in the table, caption and prose; do not splice its intervals into the
package-refit tables. The Section 1 replacement should likewise describe ACcoding's
recorded `time_cost` field rather than an unqualified “real job cost,” because executor
occupancy and the added fixed service term are model assumptions.

### 5. Narrow the certificate and theorem-verification language

All 49 `certified_identical` cells occur on overlay 0, and only two were run through the
guard kernel as certificate spot checks. `REPORT.md` says “the first two certificates in
each overlay,” which can be read as ten checks. State the observed distribution directly:
49 certificates on overlay 0, two kernel spot checks there, and no certificates to check
on overlays 1--4. The analytical certificate argument is still sound.

The 6,277,974,560 per-job checks found no violation on these fixed traces. They do not
“confirm the theorem”; the proof establishes the theorem, while these checks test the
implementation and recorded cells for consistency with it. Use “found no violation” or
“validated the implementation against the bound on these traces.”

### 6. Do not merge pending physical or natural-window work into a result claim

The physical section is correctly marked pending. Until all three checkpoints, the
service-limit premise, event-prefix choice audit, measured-trace simulator comparison and
shadow-FCFS bound audit pass, no success sentence belongs in the paper. If it passes, the
input must remain described as the busiest five-minute bin of the 44-copy overlay, with
stored overlay release spacing and an empty start. It is not an original CodeBench window
and not an estimate of the full trace with inherited backlog.

`NATURAL_WINDOW_AUDIT.md` now records its earlier per-semester proposal as superseded and
matches `natural_preflight.py`: the frozen script aggregates all six terms on the absolute
calendar, applies explicit observed-edge completeness, retains every primary job in the
winning bin, and defines a meaningful candidate as FCFS p99 at least `3L` **and**
top-1%-job work share at least 0.25. Guard firing is a separate full-mechanism condition.
No natural result exists yet.

### 7. Reconcile resource accounting in the final report

The report gives 3.85 seconds wall and 3.27 seconds CPU for “the summary pass,” which are
the initial summary values. The final `coverage.json`, `summary_numbers.json` and
`out_summarize_capacity.txt` give 3.284885 seconds wall and 2.9375 seconds CPU. More
substantively, the report does not yet give the requested total compute and wall time.
The retained capacity records alone contain 4,062.97 seconds of resumed wall time,
7,897.61 seconds of resumed worker CPU, and 242.23 seconds of initial serial CPU, before
the physical run and smaller checks. Use the completed resource ledger after the physical
run; distinguish elapsed project time, summed sequential experiment wall time, parallel
worker CPU, excluded partial runs and missing instrumentation.

## Statistical scope that must remain explicit

The pointwise intervals and the 80-coordinate band are empirical week-reweighting
summaries conditional on one replicated development construction and fixed scores. The
same 40 class-terms and jobs are copied 44 times, and waits can cross week boundaries.
There is no independent-week or independent-overlay sampling frame that turns these
bands into population coverage for semesters, demand, capacity design or deployment.
The safe claim is that the simultaneous *resampling* lower bound is positive for the
listed coordinates under the declared reweighting scheme. It is not a generalisation
probability or production significance test. The report mostly states this correctly;
the narrower label must survive into captions and conclusions.

The capacity curve also averages five overlay-specific p99 values. It is not the p99 of
the pooled jobs, and the gap is a ratio of differences of those averaged quantiles. Harm
and maximum excess use the worst overlay instead. These differing aggregation scopes are
legitimate but must remain named wherever values are joined in one table or figure.

## Research limitations that survive all current checks

1. There is still no complete-arrival, heavy-tailed, capacity-bound production trace on
   which this simulator is validated and these policies are replayed. The Taskcluster
   probe is correctly only a truncated negative triage sample.
2. The pool size, 44-copy demand consolidation and service-cost transport are authored.
   One overlay's exact zero-wait endpoint and a timed-sleep dispatcher do not identify an
   operator's capacity, service objective, isolation cost or economic saving.
3. Endogenous arrivals, policy-dependent feature visibility and changed service costs are
   not identified. The feedback examples prove the bias can have either sign. The FCFS
   transport result needs common identities, costs, rank, initial state and a bounded
   arrival shift; the logs supply neither those counterfactual premises nor epsilon.
4. A successful physical run would validate process-level dispatch and timing on one
   selected empty-start window. Sleeping holds a worker slot but does not test submitted
   code, container start-up, resource contention, grading correctness, dynamic capacity
   or repeated demand windows.
5. Every capacity result is development-only and informed by the same source demand used
   in the pilot and earlier method development. The guard guarantee remains pathwise and
   predictor-independent; empirical benefit and transport do not.

## Claims that survive hostile review

- The capacity sweep decisively rejects a universal positive-p99-benefit claim: the
  retained negative cells are large and the exact scopes are recoverable.
- On the fixed traces, every recorded per-job guard check passes, and the verification script binds
  the accepted cells to the frozen inputs, parameters and simulator snapshot.
- The open-loop lower-bound assertion is false in general; the exact counterexamples
  establish both possible bias directions without relying on CodeBench data.
- The per-job theorem remains meaningful on any realised arrival/service sample path
  against shadow FCFS on that same path. This is a conditional guarantee, not a causal
  comparison with an independently evolving deployment.

## Completed-run addendum

This addendum audits the completed physical, stall-bound and thinning sections of the
report as they stood after the earlier pending-run audit. It supersedes only the earlier
status statements that called the physical and natural-window work pending. The original-
calendar preflight stopped before data access because its exact loader-source version
could not be recovered; it produced no demand result.

### Artifact-to-report cross-check

The completed physical numbers in `REPORT.md` agree with the small retained records:

- `physical_numbers.json` gives the reported mean waits, p99 waits, jobs waiting more
  than one second, signed physical-minus-ideal mean errors, maximum absolute errors,
  selection times and enqueue lateness for all three policies.
- The three policy audits cover 2,151 jobs each. The Guard audit records 322 physical
  nonempty-fired-set decisions, 372 ideal measured-input firings, 52 per-job firing-
  indicator mismatches, 1,753 dispatch-position mismatches, 2,151 ideal epochs and
  1,241,424 ideal waiting-job budget evaluations, as reported.
- `physical_verification.json` is `PASS` and records zero exact-nanosecond violations,
  maximum same-trace excess 222.2075511 seconds, minimum uncorrected slack 77.7924489
  seconds and at most 6.7 microseconds of production-shadow rounding difference.
- `stall_bound_check.json` is `PASS`. Its 10,756 endpoint checks, 2.2526348
  worker-seconds maximum $J(d_i)$, 0.4508 ms maximum dispatch-to-start delay,
  1.1265093 s maximum additive correction and 78.76975885 s minimum corrected margin
  agree with the report.
- The full-$k=4$ and half-thinned-$k=2$ p99 values, 100-replicate central ranges,
  107,526 thinned Guard checks and 4,302 full-reference checks agree with
  `thinning_check.json`. That record correctly labels its ranges as Monte Carlo
  sensitivity across fixed thinnings, not demand confidence intervals.

No numerical mismatch was found in those completed-result passages. The large priority-
policy discrepancies are retained rather than averaged away: SPJF-E has a 392.836259 s
maximum absolute per-job error and Guard has 1,354.102033 s, while the physical and ideal
Guard histories differ. This supports rule-conformance and observed-trace certificate
claims, not job-level simulator reproduction for those policies.

### Remaining must-fix claim alignment

1. **Old applicability language remains outside the proposed paragraph replacements.**
   Replacing only the Table~`tab:cross` interpretation and conclusion leaves several
   categorical claims that contradict the new capacity result. The following source
   spans need the same heuristic-screen terminology:

   - `01_introduction.tex:26`: change “the two applicability conditions” to “two
     heuristic relevance screens.”
   - `07_data.tex:42` and `:56`: replace the table roles “method applies outside
     education” and “non-applicable case” with descriptive roles such as “cross-domain
     scheduling trace” and “recorded-queue long-limit case.” At lines 237--238, replace
     “the method's second applicability condition” with “the cost-concentration
     relevance screen.” At lines 271--274, say that Section~`sec:exp_cross` compares the
     bound scale with the waits of interest; it does not decide which workloads the
     method applies to.
   - `08_experiments.tex:12`: replace “where the method applies” with “the cross-workload
     relevance screens.” In the Table~`tab:cross` caption and header at lines 588--598,
     replace “applicability condition” and “Cond. 1?” with “wait-scale relevance screen”
     and “Wait-scale screen?”.
   - Replace the complete paragraph `09_limitations.tex:66--85`, headed “Two
     applicability conditions,” with a paragraph headed “Two heuristic relevance
     screens.” It should retain the six workload measurements, state that the first
     screen concerns whether this generic bound is informative at the observed wait
     scale and the second concerns the opportunity for cost-based ordering, and state
     that neither screen is sufficient or proved necessary for p99 benefit. Delete “the
     guard never fires at any admissible budget”; that is not a literal universal claim.

   The same terminology should be used in `REPORT.md` where its study plan and public
   probe still say “applicability conditions.”

2. **The service input still needs its model qualifier in three proposed replacements.**
   The Section 7, Section 8 Setup and Section 9 Not-studied snippets call the values
   “service costs” or “recorded service costs.” The source field is recorded execution
   cost, capped and treated as a service requirement in the replay. Use “common capped
   recorded execution costs, treated as modeled service requirements.” This keeps those
   snippets consistent with the Section 1 and Section 9 transport qualifications.

   Those snippets also call promises, formulas or sensitivity ranges “pre-specified.”
   The exact scope was fixed after the overlay-0 pilot and before the full sweep. Use that
   timing explicitly wherever the shorter term could imply specification before the
   pilot.

3. **Keep the physical result retrospective in every short formulation.** The detailed
   report does this well, and the proposed Section 8 physical paragraph calls the result
   a conditional retrospective certificate. One sentence at `REPORT.md:169` still says
   “a pathwise physical guarantee”; replace that phrase with “the observed-trace
   pathwise certificate.” The uncorrected 300-second inequality happened to hold for all
   jobs on this run. A future guarantee would require advance bounds on cumulative idle
   worker-time $J$ and dispatch-to-start delay $\ell$, which this experiment does not
   enforce.

   In the physical results table, rename “Ideal-comparator mean error” to “Mean signed
   physical-minus-ideal error” because the Guard value is small partly through
   cancellation. The Section 8 physical insertion should also retain the measured
   overhead requested by the protocol: selection-wall p99 is 0.08280 ms for FCFS,
   0.11385 ms for SPJF-E and 1.13185 ms for Guard(300). State that these scans exclude
   later serialization, logging, IPC send and worker startup.

4. **The resource section remains incomplete and stale.** `REPORT.md` still gives 3.85 s
   wall and 3.27 s CPU for the summary pass; those are the initial-summary values, while
   the final caption rerun records 3.1981476 s and 2.859375 s. The completed
   `resource_ledger.json` sums 10,696.0447073 s of instrumented experiment wall time and
   8,310.640625 s of known CPU. Its physical-service row is 6,212.0544331 s wall and
   25.3125 s CPU: 24.3125 s root-invocation CPU plus 1.0 s worker CPU through last
   finish. The separate 9.0 s physical-policy measurement includes dispatcher CPU that
   is already part of the root total and must not be added again. The final report should
   also retain the ledger's 399.678354 s estimated partial-run wall time outside the
   instrumented sum, list the rows with missing timing, and distinguish the changing
   elapsed time since `PLAN.md` creation from the summed experiment time.

### Replacement-anchor verification

All requested replacement anchors resolve uniquely in the current manuscript. The
source line spans below are pre-edit locations; line wrapping means some quoted anchors
are not one literal contiguous line, but their opening and closing text are unambiguous.

| Section | Current source span | Result |
|---|---|---|
| 1, final qualification | `01_introduction.tex:29` | Exact two-sentence paragraph found. |
| 7, load-level sentence | `07_data.tex:211--212` | Exact sentence found across a TeX line wrap. |
| 7, overlay/interval sentence | `07_data.tex:218--220` | Exact opening and closing text found. |
| 7, consolidation paragraph | `07_data.tex:142--155` | Exact paragraph endpoints found. |
| 7, reconstructed demand | `07_data.tex:119--121` | Exact two-sentence span found. |
| 8, Setup opening | `08_experiments.tex:17--20` | Exact first two sentences found. The physical paragraph is an insertion after this replacement and before the existing Table~`tab:setup` lead-in. |
| 8, Table~`tab:cross` interpretation | `08_experiments.tex:659--678` | Exact paragraph endpoints found. |
| 9, shared-pool block | `09_limitations.tex:9--16` | Exact endpoints found; retain lines 17--19 as directed. |
| 9, open-loop opening | `09_limitations.tex:22--32` | Exact endpoints found. |
| 9, fixed-capacity sentence | `09_limitations.tex:151--152` | Exact sentence found across a line wrap. |
| 9, end-to-end block | `09_limitations.tex:152--157` | Exact endpoints found. |
| 9, conclusion sentence | `09_limitations.tex:182--184` | Exact endpoints found. |

The original-calendar work remains unresolved for provenance reasons, not because its
queue or tail screens failed. It must not be described as a negative natural-demand
result. The completed physical experiment remains one empty-start timed-payload window
from the 44-copy overlay; it removes the claims that the mechanism was never executed or
that all queue waits were simulated, while leaving the source-platform queue and
transport objections intact.
