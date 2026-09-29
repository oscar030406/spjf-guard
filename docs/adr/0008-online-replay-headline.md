# 0008 The online replay becomes the headline result for predicted ordering; exact becomes an offline certificate

Date 2026-09-24.

## Decision

The headline result for predicted ordering now uses the **online** protocol: the scheduler runs once, and each job, at the moment it arrives, recomputes the M4
history from the results of the same class-term copy that have **already completed** in this replay (`completion_j <= replay_arrival_i`), and is scored by the frozen original model;
the rolling windows are ordered by replay completion time, and other classes and terms still enter as exogenous
input on the original relative clock (the same as in the ADR 0007 amendment). The implementation is `src/spjf_guard/experiment/online_replay.py`: it takes the scheduling loop of the package kernel
unchanged, compares at each arrival the signature of the same-copy history visible to that job, pauses when the signature has changed, returns to Python to
rescore with `recompute_visible` and the frozen model, and continues from where it paused.

exact (the ADR 0007 amendment) is kept, demoted to an offline monotone certificate: it withholds results in a set that only grows, and a result withheld in one pass is not put back
even if it has completed in exact's own final replay, so exact is a conservative solution to "no incomplete result was used",
not the history the online scheduler sees at arrival time. original,
conservative and static remain the three references. The parameters are not reselected because the protocol changed: the recorded selection is still selection_v4;
a restricted reselection under the online protocol (the top four feasible points of the original protocol for each family and each promise, 36 candidates in all, 15 cells of the validation pool) is
reported alongside the headline result as a robustness check and does not replace the parameters in the configuration.

## Why

The ADR 0007 amendment said an online predictor "cannot be completed before the freeze as a change that can be audited within one day", so a monotone certificate was used instead.
That judgement assumed a new event engine would have to be written; in practice it is enough to let the existing kernel pause where the signature changes, with the scheduling logic
unchanged in every line. Correctness is checked in three mutually independent ways:

1. On toy instances it is identical job by job to a brute-force event-by-event simulation (`tests/test_online_visibility.py`);
2. On real cells, waits and scores are identical job by job to a Jacobi fixed-point iteration (`src/spjf_guard/experiment/online.py`: each pass is a full replay that rescores only the jobs whose signatures disagree,
   until none disagree);
3. With a predictor whose scores do not change, the pausing kernel is identical job by job to the package kernel and the Timeout kernel.

online answers exactly the question the reviewers asked: what can a deployed scheduler know when a job arrives. exact answers
"there exists a set of withheld results such that every result used had completed". The two coincide when the monotone withholding happens not to withhold more than needed, and in general they do not.

## Costs and limits

- The semantics are still that each class-term copy is deployed independently; a deployment in which all copies share one student state is not certified.
- The parameters were not fully reselected under the online protocol (an online replay of 258 expanded points × 15 cells exceeds the budget); the restricted reselection covers only
  the points ranked highest under the original protocol. If it selects different points, the paper reports both sets of numbers as they are, and the frozen configuration is not changed.
- The time, number of pauses and memory of online per policy-cell are in the measurements below; the sealed procedure therefore gains one stage (step 7),
  with the pinned output manifest `run.sealed_online_visibility_tables`.

## Measurements

**Cross-check of the two implementations** (2026-09-24, overlay 0, lightest load, `outputs/online_probe/.checkpoints/o0_l0/`
and `deltas/`). The event-driven pausing replay and the Jacobi fixed-point iteration give identical waits job by job, and the set of rescored jobs and the
corrected scores are identical item by item (largest difference 0.0):

| policy | rescored jobs | pauses | online time (kernel / rescoring) | fixed-point time (passes) | sampled audit mismatches |
|---|---:|---:|---|---|---:|
| SPJF-E | 143,211 | 254,788 | 234 s (78 / 140) | 1,033 s (55) | 0 / 4,000 |
| Guard(600) | 144,086 | 256,499 | 268 s (90 / 155) | 1,582 s (55) | 0 / 4,000 |
| Timeout(600) | 144,520 | 257,271 | 304 s (86 / 203) | 895 s | 0 / 4,000 |

Timeout's fired column is counted only by the pausing kernel (it counts when the timeout takes over); the original row and the fixed-point row use the precheck
Timeout kernel, which does not count takeovers, so that column is 0 there. The paper does not print this column.

Writing the probe's table failed because the passes rows of the two variants have different fields (fixed in 15dfb36); the numbers above are taken directly from the checkpoint JSON
and the delta NPZ. The same commit narrowed the runner's checkpoint signature to the files that take part in the computation, so changing the paper table code no longer invalidates
policy-cells that have already been computed.

**Headline result on the primary pool** (2026-09-24, `outputs/dev_online_visibility/`, five frozen policies × 15 cells). The sampled audits of all 75
policy-cells have 0 mismatches (in each cell 2,000 random jobs plus up to 2,000 rescored jobs, recomputed directly from their visible
history). Computation took 33,479 seconds in total, 240–728 seconds per policy-cell. Gap closed with 95% intervals:

| load | policy | original | online |
|---|---|---|---|
| ρ = 0.5 | Guard(600) | 0.740 [0.713, 0.760] | 0.725 [0.696, 0.746] |
| ρ = 0.8 | Guard(600) | 0.837 [0.815, 0.851] | 0.800 [0.772, 0.819] |
| ρ = 1.0 | Guard(600) | 0.801 [0.764, 0.842] | 0.705 [0.648, 0.768] |
| ρ = 1.0 | SPJF-E | 0.916 [0.892, 0.930] | 0.864 [0.827, 0.890] |
| ρ = 1.0 | Guard(1200) | 0.844 [0.817, 0.870] | 0.754 [0.711, 0.799] |
| ρ = 1.0 | Guard(300) | 0.478 [0.387, 0.602] | 0.367 [0.278, 0.485] |
| ρ = 1.0 | Aging(600) | 0.313 [0.276, 0.404] | 0.258 [0.222, 0.339] |

At the busiest load, Guard(600)'s online value lies between exact (0.672, from the 09-23 exact run) and original.

**Full comparison set** (2026-09-26, same directory, `--policies all --resume`, 24 policies × 15 cells = 360 policy-cells).
All 360 audit rows have 0 mismatches; the rows of the five main policies are identical field by field to those of the run with only five policies. No policy with a promise exceeds its promise; the largest
excess is 0.945 of the promise (Guard-age(1200), ρ = 1.0). At the two higher loads the gap closed of all 24 policies is below original,
and at the lightest load 22 are. The paired differences are read back from the checkpoints by `scripts/online_paired_differences.py` (the original half is bit-for-bit equal to
`outputs/dev_tables/paired_differences.csv`): every difference whose interval excludes 0 under original keeps its sign under online;
4 of them are no longer significant, and 3 others become significant (all at the lightest load);
the cost of the guarantee grows (at ρ = 1.0, G = 600 s, Guard(600) − SPJF-E goes from −0.115 to −0.158); the sign of guard versus timeout is unchanged in all nine
cells (+0.423 [+0.204, +0.664] at ρ = 1.0, G = 600 s). The only conclusion that changes concerns the two orderings: under online, SPJF-E − SPJF-log
is −0.022 [−0.039, −0.009], +0.006 [−0.004, 0.015] and +0.009 [−0.000, 0.015] at the three loads, so the original-protocol conclusion that the expected-cost
ordering leads at the two higher loads no longer holds. Supplementary Section S11 (Tables S31–S33) and Sections 8.3 and 8.4 of the main text are written accordingly.

Restricted reselection (finished 2026-09-27): the same rule on the 15 validation cells under the online protocol, over the top 4 feasible points per family per promise
(36 candidates, `outputs/online_selection/candidates.csv`), audit mismatches 0. The original group of `online_choices.csv` equals selection_v4 in all 12 rows. Under
online the joint choice moves at every promise: G = 300 s to capped B0 = 15k/4 s, eta = 0.5; G = 600 s to hybrid B0 = 120k/4 s, eta = 0, gam = 16k/4 s, which is the
Guard-queue(600) of S11 (0.692 [0.641, 0.753] online at rho = 1.0, harm 128.6 s, against 0.705 and 333.2 s for Guard(600)); G = 1200 s to capped B0 = 480k/4 s,
eta = 0.75. The recorded parameters stay selection_v4; Section 8.1 reports the reselection.
