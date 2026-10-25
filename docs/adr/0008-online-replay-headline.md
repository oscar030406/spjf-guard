# 0008 The online replay becomes the headline result for predicted ordering; exact becomes an offline certificate

Date 2026-09-24.

## Decision

The headline result for predicted ordering now uses the **online** protocol, and the scheduler runs once. When a job arrives, the code recomputes its M4
history. It uses only the results of the same class-term copy that have **already completed** in this replay (`completion_j <= replay_arrival_i`).
The frozen original model then scores the job. A class-term is the set of submissions of one class in one academic term.

The rolling windows are ordered by the time at which each job completes in the replay. Other classes and terms still enter as exogenous
input on the original relative clock (the same as in the ADR 0007 amendment). The implementation is `src/spjf_guard/experiment/online_replay.py`. It works as follows:

- It takes the scheduling loop of the package kernel unchanged.
- At each arrival, it compares the signature of the same-copy history that is visible to that job.
- When the signature has changed, it pauses and returns to Python to rescore with `recompute_visible` and the frozen model.
- It then continues from where it paused.

We keep exact (the ADR 0007 amendment), but we demote it to an offline monotone certificate. It withholds results in a set that only grows. A result that is withheld in one pass is not put back,
even if it has completed in the final replay of exact itself. Therefore exact is a conservative solution to "no incomplete result was used".
It is not the history that the online scheduler sees at arrival time. original,
conservative and static remain the three references.

We do not reselect the parameters on account of the change of protocol, and the recorded selection is still selection_v4.
A restricted reselection under the online protocol is reported alongside the headline result as a robustness check. It covers the top four feasible points of the original protocol for each family and each promise.
These are 36 candidates in all, on 15 cells of the validation pool. It does not replace the parameters in the configuration.

## Why

ADR 0007 said that an online predictor "cannot be completed before the freeze as a change that can be audited within one day". It therefore used a fixed lag, and its amendment used a monotone certificate.
That judgement assumed that a new event engine would have to be written. In practice, it is enough to let the existing kernel pause where the signature changes, with the scheduling logic
unchanged in every line. We check correctness in three mutually independent ways:

1. On toy instances, it is identical job by job to a brute-force event-by-event simulation (`tests/test_online_visibility.py`).
2. On real cells, waits and scores are identical job by job to a Jacobi fixed-point iteration (`src/spjf_guard/experiment/online.py`). Each pass of the iteration is a full replay that rescores only the jobs whose signatures disagree,
   until none disagree.
3. With a predictor whose scores do not change, the pausing kernel is identical job by job to the package kernel and the Timeout kernel.

online answers exactly the question that the reviewers asked: what can a deployed scheduler know when a job arrives? exact answers
"there exists a set of withheld results such that every result used had completed". The two coincide when the monotone withholding happens not to withhold more than needed. In general, they do not coincide.

## Costs and limits

- The semantics are still that each class-term copy is deployed independently. We do not certify a deployment in which all copies share one student state.
- We did not fully reselect the parameters under the online protocol, because an online replay of 258 expanded points × 15 cells exceeds the budget. The restricted reselection covers only
  the points that ranked highest under the original protocol. If it selects different points, the paper reports both sets of numbers as they are, and we do not change the frozen configuration.
- The measurements below give the time, the number of pauses and the memory of online for each policy-cell. The sealed procedure therefore gains one stage (step 7),
  with the pinned output manifest `run.sealed_online_visibility_tables`.

## Measurements

**Cross-check of the two implementations** (2026-09-24, overlay 0, lightest load, `outputs/online_probe/.checkpoints/o0_l0/`
and `deltas/`). The event-driven pausing replay and the Jacobi fixed-point iteration give identical waits job by job. The set of rescored jobs and the
new scores are also identical item by item (largest difference 0.0):

| policy | rescored jobs | pauses | online time (kernel / rescoring) | fixed-point time (passes) | sampled audit mismatches |
|---|---:|---:|---|---|---:|
| SPJF-E | 143,211 | 254,788 | 234 s (78 / 140) | 1,033 s (55) | 0 / 4,000 |
| Guard(600) | 144,086 | 256,499 | 268 s (90 / 155) | 1,582 s (55) | 0 / 4,000 |
| Timeout(600) | 144,520 | 257,271 | 304 s (86 / 203) | 895 s | 0 / 4,000 |

Only the pausing kernel counts the fired column of Timeout (it counts when the timeout takes over). The original row and the fixed-point row use the precheck
Timeout kernel, which does not count takeovers, so that column is 0 there. The paper does not print this column.

The probe failed to write its table, because the passes rows of the two variants have different fields (fixed in 15dfb36). We therefore took the numbers above directly from the checkpoint JSON
and the delta NPZ. The same commit narrowed the checkpoint signature of the runner to the files that take part in the computation. As a result, a change to the code of the paper tables no longer invalidates
policy-cells that have already been computed.

**Headline result on the primary pool** (2026-09-24, `outputs/dev_online_visibility/`, five frozen policies × 15 cells). The sampled audits of all 75
policy-cells have 0 mismatches. In each cell, the audit recomputes 2,000 random jobs plus up to 2,000 rescored jobs directly from their visible
history. Computation took 33,479 seconds in total, 240–728 seconds per policy-cell.

Gap closed (Section 3.4 of the paper) uses the p99 wait of the jobs that arrive in the 24 hours before a deadline. It is the share of the gap between first-come first-served and shortest-job-first by true cost that a policy closes.
The table gives it with 95% intervals:

| load | policy | original | online |
|---|---|---|---|
| ρ = 0.5 | Guard(600) | 0.740 [0.713, 0.760] | 0.725 [0.696, 0.746] |
| ρ = 0.8 | Guard(600) | 0.837 [0.815, 0.851] | 0.800 [0.772, 0.819] |
| ρ = 1.0 | Guard(600) | 0.801 [0.764, 0.842] | 0.705 [0.648, 0.768] |
| ρ = 1.0 | SPJF-E | 0.916 [0.892, 0.930] | 0.864 [0.827, 0.890] |
| ρ = 1.0 | Guard(1200) | 0.844 [0.817, 0.870] | 0.754 [0.711, 0.799] |
| ρ = 1.0 | Guard(300) | 0.478 [0.387, 0.602] | 0.367 [0.278, 0.485] |
| ρ = 1.0 | Aging(600) | 0.313 [0.276, 0.404] | 0.258 [0.222, 0.339] |

At the busiest load, the online value of Guard(600) falls between exact (0.672, from the 09-23 exact run) and original.

**Full comparison set** (2026-09-26, same directory, `--policies all --resume`, 24 policies × 15 cells = 360 policy-cells).
All 360 audit rows have 0 mismatches. The rows of the five main policies are identical field by field to those of the run with only five policies. No policy with a promise exceeds its promise, and the largest
excess is 0.945 of the promise (Guard-age(1200), ρ = 1.0).

At the two higher loads, the gap closed of all 24 policies is below original.
At the lightest load, 22 are below original. `scripts/online_paired_differences.py` reads the paired differences back from the checkpoints (the original half is bit-for-bit equal to
`outputs/dev_tables/paired_differences.csv`). The results are:

- Every difference whose interval excludes 0 under original keeps its sign under online.
- 4 of them are no longer significant, and 3 others become significant (all at the lightest load).
- The cost of the guarantee grows (at ρ = 1.0, G = 600 s, Guard(600) − SPJF-E goes from −0.115 to −0.158).
- The sign of guard versus timeout is unchanged in all nine
  cells (+0.423 [+0.204, +0.664] at ρ = 1.0, G = 600 s).

The only conclusion that changes concerns the two orderings. SPJF-E orders jobs by predicted expected cost, and SPJF-log orders them by a prediction fitted on the log scale. Under online, SPJF-E − SPJF-log
is −0.022 [−0.039, −0.009], +0.006 [−0.004, 0.015] and +0.009 [−0.000, 0.015] at the three loads. The original-protocol conclusion, that the expected-cost
ordering leads at the two higher loads, therefore no longer holds. We wrote Supplementary Section S11 (Tables S31–S33) and Sections 8.3 and 8.4 of the main text accordingly.

Restricted reselection (finished 2026-09-27): we ran the same rule on the 15 validation cells under the online protocol. It covered the top 4 feasible points per family per promise
(36 candidates, `outputs/online_selection/candidates.csv`). The audit found 0 mismatches. The original group of `online_choices.csv` equals selection_v4 in all 12 rows. Under
online, the joint choice moves at every promise:

- G = 300 s: capped B0 = 15k/4 s, eta = 0.5.
- G = 600 s: hybrid B0 = 120k/4 s, eta = 0, gam = 16k/4 s. This is the
  Guard-queue(600) of S11 (0.692 [0.641, 0.753] online at rho = 1.0, harm 128.6 s, against 0.705 and 333.2 s for Guard(600)).
- G = 1200 s: capped B0 = 480k/4 s,
  eta = 0.75.

The recorded parameters stay selection_v4, and Section 8.1 reports the reselection.
