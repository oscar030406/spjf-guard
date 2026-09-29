# Static statistical and acceptance review of the capacity sweep

## Current status: resume and acceptance issues resolved

The capacity sweep is complete. The resume defects and acceptance gaps described below
have now been corrected without changing completed cell results:

- both replicate-level and per-cell resume paths use one validator that requires the
  exact protocol and parameter object, exact policy rows, the matching NPZ, exact array
  keys, `(2001,)` shapes, and finite values before a cell can be skipped;
- certificate kernel validations are restored and enforced per overlay, including prior
  validated certificates, so a resumed run performs only the checks needed to reach two;
- reruns preserve the original `sweep_execution*.json` files and write unique
  per-invocation ledgers instead of overwriting historical timing; and
- the strengthened summarizer and independent verification script implement the ratio-availability,
  realised-maximum labelling, protocol binding, schema, policy-parameter, and certificate
  checks requested by this review.

The remaining sections preserve the original static findings as historical review
evidence. Statements that a fix "remains" or is "required" describe the code at review
time and are superseded by this status block.

## Implemented post-sweep checks

The minimum summary and verification-script corrections identified below have been implemented in
`summarize_capacity.py` and `verify_artifacts.py`, without changing the running sweep:

- ratio intervals are now emitted only when the observed ratio and all 2,000 bootstrap
  ratios are finite; explicit per-row availability flags and valid-draw counts remain;
- resampled ranges for realised `harm` and `max_excess` are named
  `resample_stability`, documented as conditional empirical diagnostics, and are not
  called confidence intervals for population maxima;
- the independent verification script now binds every cell to the exact expected protocol and
  parameter object, exact NPZ keys and shapes, fixed policy parameters, non-guard firing
  zeros, finite theorem diagnostics, and the full certified-row outcome equality that is
  recoverable from the stored artefacts; and
- certificate kernel checks are counted per overlay and acceptance requires at least
  `min(2, number of certified cells)` in each overlay. A deficient completed run will
  fail visibly; no validation flag or result is synthesized.

At review time, the JSON-only replicate resume shortcut remained in
`capacity_sweep.py` because that file was part of the running job and was deliberately
not edited. The strengthened verification script and summarizer would reject a missing, corrupt,
mixed-protocol, or wrong-schema pair. This resume shortcut was subsequently replaced by
the validator described in the current-status block above.

## Scope and verdict

This review covers `capacity_sweep.py`, `summarize_capacity.py`, and
`verify_artifacts.py`, together with the package routines they call for the week
bootstrap and per-job bound. It is a static review: no simulation, data load, or
numerical recomputation was performed.

The paired capacity comparisons and the 80-coordinate band are implemented in the
intended direction. The same deterministic week-multiplicity matrix is regenerated for
every policy, capacity and overlay; the weighted p99 routine recomputes each quantile on
the resampled empirical distribution; and the five-overlay estimand is the ratio of
differences of overlay-averaged quantiles, not an average of unstable overlay-specific
ratios. The strict `max(In) < B0` no-firing certificate is also mathematically sound.

At review time, the artefacts could not be accepted without post-sweep fixes. Two issues
could change reported inference: ratio intervals were formed after dropping undefined
draws, and ordinary percentile intervals were presented for sample maxima. The
independent verification script also accepted an internally consistent but wrong protocol and did
not verify all fields needed to substantiate `certified_identical`. The current-status
block above records the subsequent corrections.

## Findings requiring correction before acceptance

### 1. Undefined ratio draws are conditionally discarded

`summarize_capacity.py:124-128` correctly marks a ratio draw undefined when its
denominator is nonpositive. However, `_point_interval` at lines 115-121 then removes all
nonfinite draws and takes percentiles of the remainder. Lines 670-674 say invalid draws
remain missing and are not silently selected out, but that is exactly how the interval
is currently formed. Near the no-queue endpoint this selection can be material: the
reported interval is conditional on a positive denominator and is not the declared
unconditional paired-bootstrap interval.

Minimum fix: retain the point ratio and valid-draw count, but set `gap_closed_lo/hi` to
missing unless all 2,000 denominator draws are positive and finite. Apply the same rule
to `reduction_pct_lo/hi` unless all FCFS p99 denominator draws are positive and finite.
The plot already requires 2,000/2,000 valid Guard(600) draws; the CSV and JSON should use
the same rule. If a conditional finite-draw interval is retained for diagnosis, name it
explicitly and do not use it for a claim.

### 2. Percentile-bootstrap intervals for `max_excess` and `harm` are not valid uncertainty intervals for population maxima

`capacity_sweep.py:107-108` resamples the maximum over included week blocks, and
`summarize_capacity.py:223-224` reports the 2.5 and 97.5 percentiles as intervals. A
nonparametric bootstrap of a sample maximum is a nonregular endpoint procedure: its
upper replicate cannot exceed the observed maximum and it does not provide a calibrated
upper uncertainty bound for a larger unseen maximum. Taking the maximum across overlays
inside every draw does not repair this limitation.

Minimum fix: keep `max_excess_s` and `harm_s` as realised-trace descriptive maxima and
keep the exact per-job theorem check. Remove their `_lo/_hi` fields, or relabel them as a
week-deletion/resampling stability range rather than a 95% confidence interval. This
does not affect p99, mean, absolute-improvement, gap, reduction, or simultaneous-band
draws.

### 3. `verify_artifacts.py` does not bind the run to the expected protocol

At lines 41-53 the verification script only collects protocol strings; line 84 checks
`len(protocols) == 1`. Thus all 156 cells can carry the same wrong protocol and still
pass. Unlike `summarize_capacity.py:145-150`, the verification script defines neither the expected
parameter object nor its hash and never compares each JSON `parameters` object with it.
It also opens NPZ files with pickle enabled by default and accepts extra arrays.

Minimum fix:

1. Define the expected parameter object once, derive `EXPECTED_PROTOCOL`, and require
   both `document["protocol"] == EXPECTED_PROTOCOL` and
   `document["parameters"] == EXPECTED_PARAMETERS` for every cell.
2. Use `np.load(path, allow_pickle=False)` and require the exact expected set of array
   names, not only successful lookup of required names.
3. Independently reconstruct each row's fixed policy parameters from `(policy, k)` and
   check `floor_s`, `b0_s`, `eta`, `gamma_s`, and `bmax_s`. A correct document-level
   parameter object does not prove the rows were run with those values.
4. Require all non-guard `forced_dispatches`, `fired_fraction`, and
   `fired_queue_weighted` fields to be zero, and require every numeric ratio or bound
   diagnostic to be finite and in its mathematical range.

### 4. Resume can declare a corrupt or mixed run complete

The top-level resume test in `capacity_sweep.py:47-49` checks only that all JSON names
exist. It does not parse them, compare the protocol, or require the matching NPZ. A
partial JSON write or a missing/corrupt NPZ makes the whole replicate permanently skip.
The per-cell branch at lines 69-72 is stronger but is bypassed by the replicate-level
shortcut. JSON and NPZ writes at lines 150-152 are also not an atomic pair.

Minimum fix after the current sweep finishes: replace both resume paths with one cheap
cell validator that parses JSON, checks the exact protocol and parameters, opens NPZ
with `allow_pickle=False`, checks the exact schema and `(2001,)` finite arrays, and only
then skips. Write both products to temporary names, close and validate them, then rename
NPZ first and JSON last. Existing valid cells need no recomputation; invalid cells alone
should be rerun.

## Paired bootstrap, overlay aggregation, and the 80-coordinate family

### What is correct

- `capacity_sweep.py:55` regenerates one `2001 x 30` matrix (including the all-ones
  point row) from the same seed in every cell. This gives exact draw-index pairing over
  policy and capacity. Reusing the same draw index across overlays also implements the
  declared average-overlays-within-draw estimand.
- Deadline-window p99 uses `wait[dl]` and its stored week label; means use all jobs. The
  package quantile routine implements NumPy's default linear empirical quantile without
  materialising duplicate jobs. The explicit point check at lines 104-105 is useful.
- `summarize_capacity.py:191-205` averages p99 and mean across the five fixed overlays
  within each draw. Lines 211-213 then form
  `(mean Q_FCFS - mean Q_P)/(mean Q_FCFS - mean Q_SJF)`. This is internally coherent and
  matches the wording now in `REPORT.md`; it must continue to be described as a ratio of
  averaged quantiles. It is not the mean of five per-overlay ratios.
- `simultaneous_band` constructs exactly 20 capacities times four non-oracle policies,
  and the shared week draws preserve dependence among all 80 coordinates. A two-sided
  max-absolute-deviation band is conservative for a one-sided positive-benefit claim.
  Requiring every relevant lower endpoint to exceed zero is a valid familywise decision
  rule, conditional on the stated outcome-resampling model.

### Checks and wording still needed

`common.py` returns integer week labels and only the number of stored weeks. The sweep
asserts `n_weeks == 30` but does not assert that labels cover exactly `0..29`, nor record
the stored `weeks` axis. Before calling the across-overlay draws paired calendar-week
draws, record a hash or explicit equality check for the five stored week axes and assert
the label domain. If the axes are not identical, use overlay-specific draw matrices or
describe the pairing as index pairing rather than calendar pairing.

The band implementation at `summarize_capacity.py:341-353` follows the predeclared
single-bootstrap standardized max-deviation construction: it subtracts the observed
estimate and divides by the coordinate's bootstrap standard deviation. It does not
compute a replicate-specific standard error, so `centered, coordinate-standardized
single-bootstrap max-|t| band` is more precise than `studentized` at line 361. The
existing coverage qualification at lines 369-372 is essential: this is conditional
week-outcome inference, not a queue-process bootstrap and not uncertainty over source
jobs, overlay construction, predictor fitting, feedback, or the pool design.

The same source jobs can move between week blocks across the five constructed overlays.
Shared multiplicities do not make those overlays independent, and they may not reproduce
all dependence created by duplicated source jobs. The code correctly treats the five
overlays as fixed constructions and averages them; no effective sample size of five or
five-independent-deployments claim is justified.

## `certified_identical` and per-job guarantees

The certificate condition in `capacity_sweep.py:80-85` is sufficient. On the unguarded
SPJF dispatch order, `In_i` is all higher-rank work dispatched before job `i`. With
`gamma=0`, nonnegative age growth, and strict `max_i In_i < B0`, completed overtaking
work cannot reach the guard budget before a first divergent dispatch. Therefore a first
divergence is impossible. Comparing against the actual integer `p.b0_us` correctly
handles any cap clipping, and strict inequality matches the kernel's `>=` firing test.
The copied result is then passed through `assert_per_job_bounds` for every job.

The acceptance evidence is weaker than the report wording:

- `capacity_sweep.py:86-92` checks only the first two certified cells in each invocation
  of `main`. A fresh two-worker run normally invokes `main` once per overlay and resets
  the counter, but resumed/skipped work can change which cells are checked.
- `verify_artifacts.py:86` requires only two checked certificates in the entire study.
  It does not establish the current statement that the first two certificates in every
  overlay were checked, and the first two can both belong to the same guard setting.
- The verification script proves equality only for the four stored draw arrays. It does not compare
  `p99_all_s`, `max_wait_s`, or `positive_wait_jobs` with SPJF-E, and a validation flag
  is not required to occur only on a certified row.

Minimum fix without blanket reruns: inspect the stored flags, report their exact
`(rep,k,policy)` coverage, require at least two per overlay if that is the retained text,
and require at least one actual-kernel check for each guard policy that uses the
certificate. If those conditions are absent, either run only the missing boundary
checks or weaken the text to the exact observed coverage. The verification script should also
compare every stored outcome field with SPJF-E for certified rows and assert that a true
kernel-validation flag implies `execution == "certified_identical"`. An actual
validation should check `queue_weighted_forced == 0`; equality of waits already implies
equality of starts for common arrivals.

For every guarded cell, the in-run call to `assert_per_job_bounds` is the strongest
current check: a violating cell is not written. The verification script's total
`6,277,974,560` bound checks is consistent with 356 guarded policy cells times
17,634,760 jobs. In addition, the verification script recovers the integer maximum excess from the
NPZ-backed point value and checks it against `G`; this direct promise check should be
kept. For clarity, assert `0 <= max_fraction_of_allowed_excess <= 1 + tolerance` rather
than only its upper side, and compare all expected guard parameters before interpreting
that fraction.

## Formula and field audit

- `gap_closed` and `reduction_pct` use the right numerators and denominators. The only
  inferential defect is the finite-draw filtering described above.
- `max_fraction_of_allowed_excess` at `capacity_sweep.py:120` takes the per-job ratio of
  positive excess to the policy-specific allowed excess and then the maximum; operator
  precedence gives the intended calculation.
- `harm` uses the repository's declared formula: the maximum signed excess among jobs
  with FCFS wait at most one second. `max_excess` likewise uses the maximum signed
  excess. These match `src/spjf_guard/experiment/metrics.py`; they should not be silently
  clipped in this study. If prose intends a nonnegative loss, define the positive part
  explicitly and change it consistently in the paper and package.
- For p99 and mean, five-overlay aggregation is an arithmetic mean. For `harm` and
  `max_excess`, it is the worst overlay. The mixed scope is intentional but the generic
  scope label `five_overlay_mean_or_worst` should be retained wherever rows are joined or
  plotted.
- `floor_eligible_fcfs_p99_gt_floor` is based on the mean of five overlay p99 values.
  Rename it to expose that fact, or add the number/range of individual overlays above
  the floor. Otherwise plot shading can be mistaken for an all-overlay applicability
  statement.
- The simulator kernel marks every raw FCFS choice as `forced`, but
  `capacity_sweep.py:125-127` correctly serialises all non-guard firing fields as zero.
  Normalise the FCFS `JobResults` counters immediately after simulation in future runs,
  or keep all downstream reads behind the wrapper test. This bookkeeping issue does not
  alter waits or the existing serialised capacity cells.

## Minimal acceptance sequence after the sweep

1. Patch the resume validator and the independent expected-protocol/parameter checks;
   validate every existing JSON/NPZ pair without recomputing valid cells.
2. Change ratio intervals to missing unless all declared draws are valid; remove or
   relabel intervals for realised maxima. Regenerate summaries only.
3. Audit certificate flags by overlay and policy, fill only missing kernel spot checks if
   the stronger wording is retained, and strengthen certified-row field equality checks.
4. Record/check the stored week axes, keep the conditional-inference limitations, and
   name the ratio-of-averaged-quantiles estimand in every table caption that reports it.
5. Compute total CPU time by summing the completed cell timings, including cells produced
   before a resumed launcher run; a final `sweep_execution.json` from a resume does not
   by itself measure total historical compute.

Acceptance should require the strengthened verification script to pass, all 156 exact-protocol
JSON/NPZ pairs to load, all primitive draws to be finite, every guarded policy cell to
account for all jobs, zero per-job violations, the direct integer promise checks, the
declared certificate-validation coverage, and explicit invalid-draw counts for every
reported ratio.

## Implementation notes following the review

The initial serial invocation's three retained cells (overlay 0, k=1,2,3) copied the
production FCFS kernel's FIFO-selection flag into the raw firing fields. Their waits
and all bootstrap arrays are unaffected. The final verification script accepts exactly this
documented legacy case (all dispatches FIFO, and no execution metadata); it requires
zero firing for every other unguarded row. All summaries define non-guard firing as
zero and retain the original raw cells unchanged.

Resource accounting uses the recorded CPU of the interrupted initial invocation plus
the resumed workers' complete process-CPU totals. This includes partial interrupted
work and input/bootstrap overhead and avoids adding cell timers a second time. The
initial and resumed invocation records are both preserved. A fresh resume must not
overwrite these historical execution records with a near-zero skip-only duration.
