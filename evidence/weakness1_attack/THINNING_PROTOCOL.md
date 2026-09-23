# Frozen protocol: first-moment scaling by random thinning

## Question and scope

This check asks whether replacing the full frozen demand at four servers by an
independent half-sample at two servers approximately preserves nominal queueing
outcomes. It evaluates the legitimacy of this particular first-moment scaling device.
It is not a second physical-service experiment, a full-data analysis, or evidence that
thinning preserves burst structure or tail dependence.

A simple exact counterexample already rules out general invariance. Four equal jobs
arriving together at four idle servers have zero waiting. Retaining each independently
with probability one half and using two servers preserves expected work per server,
but at least three jobs survive with probability `(4+1)/16 = 5/16`; those samples
have positive waiting. The nominal replay below measures the size of the discrepancy
for this study's chosen window instead of assuming that this counterexample determines
its empirical magnitude.

The source is the already frozen `physical_input.npz`: 2,151 jobs in the preselected
300 s development window from `primary_rep0`. The script verifies the file's fixed
SHA-256, protocol-v2 metadata, six development terms, input schema, job count, time
units, and 60 s requested-service cap before parsing it. It does not invoke the overlay
loader, inspect any other data file, refit the score, or reselect the window.

## Predeclared transformation

The full reference retains all 2,151 jobs and uses `k=4`. For replicate index
`r = 0,...,99`, NumPy's `default_rng(20260921 + r)` independently retains each job with
probability `1/2`, and the retained trace uses `k=2`. A separate full-input `k=2` run is
included as the current nominal comparator.

Thinning only removes jobs. Every retained job keeps its frozen arrival offset,
requested service, score, and order. In particular, the script does not subtract the
first retained arrival: time zero remains the common start of the original calendar
bin. Seeds, the window, and the retention rule are fixed without reference to any
policy result.

## Simulator and policies

All schedules use the production simulator imported through `common.py`, which checks
the pinned simulator snapshot. Each trace is simulated under:

- `FCFS`;
- `SPJF-E`, using the frozen `tweedie` score without refitting; and
- `Guard(300)`, with formal `L=61 s`, `G=300 s`, `B0=15k s`, `eta=0.5`, and
  `gamma=0`.

For every random thinning, and for both full-input references, the script calls the
production per-job bound assertion for every Guard job against FCFS on the identical
trace. FCFS's internal FIFO kernel flag is not reported as a guard firing.

## Outputs and interpretation

`thinning_check_runs.csv` contains one row per scenario and policy: retained job and
work fractions, offered work divided by `300k`, mean/p99/maximum wait, maximum wait
excess over same-trace FCFS, Guard firings, bound-check count, and relative p99 deviation
from the full `k=4` result for the same policy. `thinning_check.json` records the frozen
parameters, input validation, full `k=4` and full `k=2` references, all bound counts,
and empirical distributions over the 100 random thinnings. `out_thinning_check.txt`
records execution timing and the same structured summary. If Matplotlib is available,
the script also exports `thinning_check.svg` and `thinning_check.png`.

The 2.5th and 97.5th percentiles are an empirical central range over the 100 fixed
Bernoulli thinnings. They are a Monte Carlo sensitivity distribution for this one
window, not a confidence interval for an underlying demand population. A gap-closed
ratio is omitted because the frozen policy set does not include the undeployable
true-size SJF reference; adding it only to manufacture a denominator would expand the
predeclared comparison.
