# 0007 Conservative 3600-second visibility within a class-term as the headline result for predicted ordering

Date 2026-09-21.

## Decision

From now on the headline result for predicted ordering uses `spjf_e_conservative`: the M4 user, exercise and user–exercise histories are all restricted to the same
class-term, only absorb the results of submissions that become scheduled jobs, and require the result clock to satisfy
`done_j + 3600 <= a_i`. One class-term copy in an overlay therefore reads only the history that has a unique corresponding job within that copy; all copies of the same
original job still share one frozen score, but they no longer borrow results from another class-term or results that never entered the pool.

The 3600 seconds were fixed before looking at the sealed terms. Over the five development overlays and three load levels, the largest FCFS wait is
1544.602708 seconds. For the largest promise in this package, 1200 seconds, the theorem gives for every guarded policy
`W^P <= W^FCFS + G <= 2744.602708` seconds; 3600 seconds leaves 855.397292 seconds of margin, i.e. 31.2%.
The sealed run still counts `W > 3600` in every cell: a single one under FCFS or any of the three Guards means the development-phase derivation does not cover
the new pool, and the run must not continue silently; SPJF-E, which has no proof, is reported the same way and cannot be counted towards the certificate.

The old global, `delta = 0` score is kept as a clearly labelled optimistic reference; the `STATIC` score, which uses only the code and the course/clock
columns known at submission time, is the lower anchor. All comparisons keep the Guard parameters already selected on the validation pool; nothing is reselected with the new score.

## Why

The old score reads a result as soon as `done_j` is reached on the original platform, but in the replay that result is only complete at `a_j + W_j^P + C_j`. The development audit shows that,
when replay counterparts for the history are found within the same outer round, about 80% of jobs read at least one result that was not yet complete at their own arrival;
95.39% also read at least one submission result that is not in the same replay pool at all. This exposure does not affect the Guard's worst-case wait guarantee for any static
ordering score, but it means the gain from predicted ordering is not a gain under a deployable clock.

Online exact release is the more direct definition, but it is not a local change to the current kernel. The current Numba scheduling kernel takes one pre-
sorted static score; the exact version would have to update the rolling user, exercise and user–exercise state at every completion event of every policy, then
evaluate the frozen 300 LightGBM trees, and the cross-class history of the original overlay has no unique replayed counterpart. That is a new event engine and
prediction executor, and it cannot be completed before the freeze as a change that can be audited within one day. The fixed-lag scheme instead keeps the static kernel and turns the sufficient condition
into `W <= D`, which can be verified job by job after the run.

## Cost

The conservative result is not close to the old one. At the busiest load, with the original parameters, Guard(600)'s gap closed falls from 0.801
`[0.764, 0.842]` to 0.429 `[0.357, 0.533]`; the static lower anchor is 0.349
`[0.281, 0.457]`. This shows that the old clock inflated the prediction gain at high load, and the paper can no longer treat it as the main effect. The conservative result is still
significantly better than the static lower anchor, so what can be stated is "there is a deployable gain from history, but smaller than originally reported", not "the sensitivity analysis does not affect
the conclusion".

Restricting to the class-term also deliberately gives up a deployable cross-class prior. If a deployed system has a separate prior store written to disk before the window starts and
clearly defined across copies, it can be added later as a fourth variant; this freeze does not pass off the current global original-calendar history as such a prior.

## Amendment — 2026-09-23

The text above is kept as the record of the 2026-09-21 decision; this section corrects its explanation of the exposure, its judgement of the feasibility of the exact computation, and the final reporting basis.
This amendment uses only the development and validation pools, does not access sealed data, and does not create a formal lock.

### Problems corrected

The old statistic of about 80% mixed histories of different classes that were shifted independently within the same outer round, and cannot be called a leakage rate caused by same-copy queueing.
The 95.39% of unreplayed history is also not unusable information: completed records of earlier terms have a legitimate original clock. The original
conservative variant differs from original at once in namespace, history support set, fixed release lag and model training; therefore
0.801 → 0.429 by itself cannot identify the effect of queueing delay. The strong attribution in the text above, that "the old clock inflated the gain", is withdrawn
and replaced by a frozen-weight comparison that changes one item at a time.

The existing static scheduling kernel does not need to be turned into an online prediction engine to compute the required final visibility certificate: each policy/cell starts from the original score,
and after simulating, the same-copy results that are still incomplete are added to a per-job withheld set; M4 is recomputed only for targets with new violations, scored with
the original frozen weights, and simulated again. The set only grows, and the finite number of records guarantees termination; the last pass must assert zero violations still in use.
The per-pass counts, timings, sparse scores and content hashes are all written out. This is an offline monotone availability certificate, not a unique,
minimum-deletion or maximum-history online solution.

Each class-term copy is treated as an independent instance, and the history of other classes and terms enters as exogenous input on that instance's original relative clock. This
keeps real past information and does not borrow fictitious future completion times from another independently shifted instance. For all 15 primary cells,
Guard(600) also gets an exact sensitivity analysis that deletes outright the history of the other replicated classes in the same term; the meaning and limits of this choice must be
reported together with the result, and cannot be generalised to a platform-wide intervention model with shared student state.

### Measurements and the headline decision

2026-09-23: the exact run on the development and validation pools finished, with output in `outputs/dev_consistent_visibility/`.
The coverage, pinned before measurement, is 5 primary overlays × 3 load levels × 5 policies, 75 refinement units in all; no cell is missing,
and no subset was picked according to results. In `exact_passes.csv` every unit's final pass has `terminal_zero` equal to `True` and
`offending_records` equal to `0`; refinement converged in 10–18 passes (including the final pass), 1,033 passes in total. A further 15
`exact_other_class_withheld` units also all ended with zero violations. The per-job bounds of the three Guards
still hold under the exact scores. The consistent visibility item of `scripts/check_generated.py` reports
`1 run(s) have complete monotone, terminal-zero certificates`.

**Decision: exact becomes the headline result for predicted ordering; conservative and original are demoted to two references.**

The basis is this sentence from earlier in this section: "The existing static scheduling kernel does not need to be turned into an online prediction engine to compute the required final visibility certificate …
the last pass must assert zero violations still in use." That sentence defines exact as **the required** final visibility certificate and writes the condition under which it can be
published as a decidable assertion. That assertion now holds, so exact is the direct answer to the question in M2. Conversely,
this section has already withdrawn the reason for conservative as the headline result: "The original conservative variant differs from original at once in
namespace, history support set, fixed release lag and model training; therefore 0.801 → 0.429 by itself cannot identify the effect of queueing delay."
A comparison that its own decision record judges unidentifiable cannot remain the headline result.
The two-branch wording of step 5 of `docs/sealed_run_procedure.md` ("when the headline is exact, this warning does not block step 6;
if the headline is still conservative, this case is a hard stop") also falls into the first branch under this decision.

All numbers are from `outputs/dev_consistent_visibility/exact_comparison.csv`, pooled over five overlays,
with parameters unchanged (Guard(600) = capped B0=120, eta=.75). At the busiest load (level 2, rho=1.0, k=4):

| policy | variant | gap_closed [lo, hi] | p99_dl_s | max_excess_s | harm_s | fired_pct |
|---|---|---|---:|---:|---:|---:|
| Guard(600) | exact | 0.672 [0.602, 0.743] | 118.94 | 519.871 | 332.841 | 7.82 |
| Guard(600) | original | 0.801 [0.764, 0.842] | 89.24 | 523.668 | 339.882 | 7.15 |
| Guard(600) | conservative | 0.429 [0.357, 0.533] | 174.71 | 527.753 | 303.519 | 7.71 |
| Guard(600) | static | 0.349 [0.281, 0.457] | 193.11 | 528.132 | 316.119 | 11.18 |
| SPJF-E | exact | 0.848 [0.802, 0.878] | 78.46 | 5830.092 | 1324.288 | 0.00 |
| SPJF-E | conservative | 0.670 [0.599, 0.733] | 119.20 | 6069.684 | 891.634 | 0.00 |
| SPJF-E | original | 0.916 [0.892, 0.930] | 62.79 | 5904.525 | 708.755 | 0.00 |

At the other two load levels Guard(600) exact is 0.724 [0.697, 0.747] (level 0) and 0.785 [0.748, 0.807]
(level 1), against 0.740 and 0.837 for original and 0.640 and 0.634 for conservative.

What each of the two references is, in one sentence each: **original** keeps the result clock of the original platform, which makes a result visible before the replayed job that produces it
has completed, so it is an optimistic reference; **conservative** is stricter than availability itself: it at once restricts history to the same
class-term copy, delays every result by 3600 seconds, and refits the model, so it is a stricter reference and not a clean control.
`attribution_comparison.csv` separates these three things at the busiest load: changing only the namespace gives 0.807, deleting the history that has no replayed
job gives 0.770, and the fixed lag is the item that moves the result (0.573/0.519/0.502/0.518 for 60/300/900/3600 seconds
respectively); the three together with frozen weights give 0.536, and only after refitting is it 0.429.

The limits are reported together with this headline and cannot be left out: this is an **offline monotone availability certificate**, not a unique solution,
not a minimum deletion, and not an online predictor driven by completion events; each class-term copy is treated as an independent deployment instance, and other classes and terms
enter as exogenous input on that instance's original relative clock, so it does not certify a deployment in which "all copies share one student state".
`exact_sensitivity_comparison.csv` gives the sensitivity of this semantics: after deleting outright the history of the other replicated classes in the same term,
the gap at the busiest load goes from 0.672 [0.602, 0.743] to 0.655 [0.583, 0.732] and the p99 from 118.94 seconds to 122.69 seconds,
in the same direction and smaller in size than the difference between original and exact. The parameters are still the set selected under original; no exact reselection is done this time
(the cost estimate in the next section gives the reason), so no claim is made that these parameters are optimal under exact.

The publication gate follows the last section of this ADR: a failure of exact's final-pass zero violations or of a Guard bound is always a hard stop; since the headline is exact,
a failure of conservative's fixed-lag certificate no longer blocks publication, but it is still printed as usual and written into the manifest.

### Selection protocol

The original validation pool, per-cell harm constraint and worst-cell rule are unchanged. An exact reselection must refine each candidate policy independently;
one candidate's exact scores cannot be reused for other candidates. Timing on a 12-stratum validation pool with the pre-fixed seed 20260922 is
used to estimate the cost for all 15 cells, 258 Guard expanded points (243 distinct schedules) and 11 Aging points, and is not used for selection.

All 12 pre-declared timing points finished; refinement took 8–17 passes and every one ended with zero violations, 3,329.65 seconds of refinement in total. Extrapolating by stratum
weights, removing known duplicate schedules and assuming an ideal two-worker speed-up, a full reselection would still need about 164.26 hours; this optimistic estimate
does not yet include fitting, disk reads and references, and is far beyond the budget of about 8 hours. So the full grid is not run, and the original selected points are not changed:
Guard(300) is capped B0=60, eta=.5; Guard(600) is capped B0=120, eta=.75; Guard(1200)
is hybrid B0=0, eta=0, gamma=16; Aging beta=.03. The Guard points come from the original validation under original, and Aging
from the committed conservative validation. The cost sample only estimates the cost and takes no part in selection.

This amendment supports a comparison of information protocols at fixed parameters. It does not prove that these four points are still optimal on the exact validation pool or satisfy the original harm
screen, and it does not provide an exact reselection result that does not exist. If a full reselection is done in future, a new validation run must be frozen first,
the current parameter set must be kept at the same time and the corresponding development comparison regenerated; a different parameter label cannot be put on the current tables.

### Freezing and preservation

The experiment recipe snapshot is `configs/visibility_development_20260922.yaml`; the final decision is written into `configs/main.yaml`.
The old table manifests only change their pointer to the byte-identical `configs/main_original_84932d9.yaml`; the old configuration hash and output hashes are unchanged.
The original 75 CSVs, 18,627 rows and all original columns are protected by an independent byte-snapshot gate. `run_main.py` continues to write the historical reference rows;
the exact results come from an independent runner and output directory, and the change of headline is not used as a reason to overwrite old numbers.

The sealed procedure gains an independent exact stage and becomes nine stages with five pinned output manifests; the fixed exact manifest includes 11 CSVs and the
manifest, and the dynamic sparse NPZ files are managed by a delta manifest. It supports checkpoint recovery with content signatures, the final-pass zero-violation check, an independent
emitter/checker for the tables derived for the paper, and a read-only sealed dry run. The main text and the evidence directory are outside the scope of this change; accurate statements the paper can use,
the full numbers and the measured resource budget are in `docs/policy_consistent_visibility.md`.

The status of the old fixed-lag certificate is printed separately and recorded in the manifest; if the conservative waits on the new pool exceed 3600 seconds, that anchor is
explicitly marked as having failed the certificate. The exact headline does not depend on this sufficient condition, so it still runs its own zero-violation certificate; if the
headline were conservative, a fixed-lag failure would block publication. Any failure of exact zero violations or of a Guard bound
always blocks publication. Renaming the draft is not a formal freeze; the sealed entry point only accepts a lock in the formal frozen format together with the explicit opening argument.
