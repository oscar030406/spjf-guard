English translation of `docs/policy_consistent_visibility.md`, which is the authoritative version.

# Policy-consistent outcome visibility

This note corrects how the first M2 audit explained "queueing exposure". The figure of
about 80% in the first audit is not exposure that queueing creates within the same
class-term copy. The 95.39% figure for history outside the pool also does not mean
unusable information. We keep the old tables and do not change their numbers.

In this work, we separate the copy semantics, the history deletion, the fixed lag and the
model refitting. We also use the frozen original M4 weights to build exact visibility
certificates for each policy, each load and each overlay. All measurements use only the
development and validation pools. We did not read, parse or hash any sealed input.

## 1. What we estimate and the copy semantics

Let `H_i` be the set of history results that the original score actually uses. A result
that enters the user, exercise and pair aggregates at the same time counts only once. The
clean initial queueing-exposure set is

```text
V_i(P) = {j in H_i: copy_entry(j) = copy_entry(i),
          replay_arrival(j) + wait_P(j) + service(j) > replay_arrival(i)}.
```

`copy_entry` stands for the same class-term, the same outer round and the same shift. It
does not count the results of another independently shifted class in the same round. A
history record must also pass the visibility rule of the original feature sweep and its
order for events at the same time. The sweep releases a result with non-zero duration at
its completion, before the reads at that instant. A zero-duration event cannot leak to a
read at the same instant. We compare the replay thresholds on the integer-microsecond
clock.

We divide history into three kinds:

1. **Replayed submissions of the same copy.** The replay of the policy decides their
   completion times. This is the queue feedback that M2 asks about.
2. **History of other classes or terms.** We treat each copy of a class as an independent
   deployment instance. External history is exogenous information on the original relative
   clock. When the target instance has the shift `s_i`, we interpret an external record as
   `original_done_j + s_i`. We do not use the independent shift `s_j` of the other
   instance. We therefore keep the earlier terms, which already took place, and the
   history outside the pool. We do not claim that this equals a deployed system in which
   all copies share one student state and change each other's result clocks.
3. **Sensitivity to other classes of the same term.** For the other classes of the same
   term that are also in the pool, we separately delete their history records whole. We
   delete the outcome and also its arrival counts and time-since-arrival. We then run the
   same exact refinement on this copy. This sensitivity covers Guard(600) in all 15 cells.
   We still keep the history of earlier terms.

The earlier audit mapped the history inside the pool to the same outer round, but it let
each class shift independently. This is a reproducible **mapping-exposure statistic**, not
a rate of information leakage caused by the queue. The figure of about 80% and
`unreplayed = 95.39%` in `outputs/dev_visibility/` keep only this meaning. They cannot
prove that we must drop cross-term history or use a one-hour lag.

## 2. Exact refinement with frozen weights

For each target term, we rebuild M4 deterministically with the original training recipe.
We assert that its original scores equal the stored `spjf_e` value by value, and then we
freeze the weights. On 512 target rows chosen with a fixed seed, we also check bit by bit
that the targeted recomputation matches the original sweep.

The static code columns, the course columns and the columns known at arrival stay
unchanged. We recompute only the 22-column M4 history block of the affected targets. A
withheld outcome does not undo an arrival that already happened, and it usually leaves the
arrival counts and time-since-arrival as they are. Only the sensitivity that deletes whole
records of other classes changes these columns.

For each `(overlay, level, policy)`, we start from the scores that release each result at
its original `done_j`, and we set `S_i = empty`:

1. Simulate the policy in full. Independently count every originally visible record that
   comes from the same copy and completes only after the target arrives.
2. Subtract the records already withheld in `S_i`, which gives the new violations of this
   pass. Recompute only the targets with new violations. Rescore them with the same frozen
   model. Replace `S_i` by its union with the new records.
3. Simulate again, until a pass has no new violation. The final pass asserts that the
   number of violations still used by a score is exactly zero.

Once we withhold a record from a target, we never restore it. Each non-terminal pass adds
at least one of the finitely many `(i,j)` edges. The procedure therefore always
terminates, and it needs no artificial limit on the number of iterations.

We compute the count and the enumeration along two independent paths and check one against
the other. In later passes, we accelerate the work with a vectorised count of the edges
already withheld. The terminal audit still recounts over all jobs. For every pass,
`exact_passes.csv` records the new targets and records, the cumulative set sizes and the
simulation/detection/rescore times. This includes the final pass with zero violations.

Here, exact means that **every same-copy outcome that the final replay still uses is really
complete**. It does not mean the maximum usable history, a unique fixed point or an online
predictor driven by completion events. Monotone deletion may keep withholdings from
earlier passes that are no longer necessary. We do not call it a minimum-deletion
solution. We also do not claim that the offline construction is directly deployable
online.

We check separately the per-job guarantee that Guard gives under any static ordering.
SPJF-E and Aging come without this guarantee.

For each cell, we write to disk only the index, the delta, the exact corrected score and
the withheld count of each affected job. We do not write a full copy of the scores for all
17.6M rows. The corrected score avoids the rounding error of a floating-point subtraction
followed by an addition. `exact_delta_manifest.csv` pins the relative path, the size and
the SHA-256 of each NPZ file. The runner can restore a completed policy/cell, keyed by the
hashes of its inputs, its implementation and its control cache. It cannot silently reuse a
stale checkpoint.

## 3. Clean initial exposure and its effect on scores

The per-cell results are in
`outputs/dev_consistent_visibility/same_copy_exposure_cells.csv`, and the summary is in
`same_copy_exposure.csv`. We first simulate each policy under the original scores. We
report the share of jobs with `|V_i(P)| > 0` and the same share inside the deadline
window. We compute the distributions of the record count and of `|delta score|` only over
the affected jobs. The score difference deletes only the violating records of the first
pass, and it does not include the later refinements.

We compute the rank displacement on **the actual queue before dispatch in the original
simulation**. All jobs affected in the first pass switch to their corrected scores at
once, and we compare their ranks in the same queue. The queue no longer holds the jobs
with an earlier dispatch in the same microsecond. We break ties in score by arrival rank.
A positive value means that the job ranks further back.

This is not the difference in dispatch sequence numbers between two simulations, nor a
rank in Guard eligibility. Aging uses the equivalent static key
`score + beta * relative_arrival`. The CSV gives the mean, p50, p90, p99 and max of both
the signed and the absolute displacement. In the FCFS rows, the rank is a counterfactual
ordering by predicted score within the actual dispatch queue of FCFS. It does not change
the service order of FCFS itself.

The per-cell results are in `same_copy_exposure_cells.csv`. The table below is the summary
of `same_copy_exposure.csv`, pooled over the five overlays. The headers are the CSV column
names, and we write only `affected_share` and `deadline_affected_share` as percentages. We
round the values to the digits that the paper uses and do not recompute them. The full
precision is in the CSV.

| level | policy | affected_share % | deadline_affected_share % | records_mean | records_p99 | abs_delta_score_p99 | abs_rank_displacement_p99 | abs_rank_displacement_max |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 0 | FCFS | 1.08 | 2.04 | 7.03 | 75.2 | 9.782 | 350.8 | 1435 |
| 0 | SPJF-E | 0.89 | 1.81 | 7.34 | 72.6 | 9.561 | 225.2 | 1248 |
| 0 | Guard(300) | 0.91 | 1.84 | 7.29 | 71.2 | 9.677 | 241.2 | 1247 |
| 0 | Guard(600) | 0.90 | 1.82 | 7.30 | 72.2 | 9.578 | 235.0 | 1354 |
| 0 | Guard(1200) | 0.90 | 1.82 | 7.32 | 72.2 | 9.642 | 226.9 | 1247 |
| 0 | Aging(600) | 0.92 | 1.85 | 7.45 | 74.2 | 9.595 | 215.8 | 1459 |
| 1 | FCFS | 2.85 | 4.74 | 7.22 | 109.4 | 10.033 | 709.9 | 5467 |
| 1 | SPJF-E | 1.92 | 3.53 | 8.39 | 99.8 | 10.154 | 299.8 | 1707 |
| 1 | Guard(300) | 2.09 | 3.74 | 8.32 | 106.0 | 10.296 | 594.4 | 3653 |
| 1 | Guard(600) | 1.99 | 3.61 | 8.21 | 98.0 | 10.153 | 391.8 | 2086 |
| 1 | Guard(1200) | 1.96 | 3.60 | 8.25 | 98.0 | 10.285 | 334.2 | 1904 |
| 1 | Aging(600) | 2.24 | 3.90 | 8.16 | 111.6 | 10.001 | 377.0 | 3455 |
| 2 | FCFS | 4.74 | 7.50 | 6.81 | 107.2 | 10.210 | 1051.4 | 8946 |
| 2 | SPJF-E | 2.69 | 4.80 | 8.35 | 110.0 | 10.807 | 324.0 | 2066 |
| 2 | Guard(300) | 3.18 | 5.41 | 8.20 | 114.6 | 10.871 | 1044.8 | 5955 |
| 2 | Guard(600) | 2.92 | 5.04 | 8.07 | 106.4 | 10.814 | 754.6 | 4377 |
| 2 | Guard(1200) | 2.85 | 5.00 | 8.12 | 107.4 | 11.008 | 535.6 | 2364 |
| 2 | Aging(600) | 3.59 | 5.82 | 7.78 | 118.4 | 10.414 | 600.6 | 4021 |

At the busiest load, 2.92 % of the jobs under Guard(600) read at least one result of the
same copy that was not yet complete (`affected_share`). In the deadline window, the share
is 5.04 % (`deadline_affected_share`). An affected job reads 8.07 such records on average
(`records_mean`). In the same cell, the `affected_share` of FCFS is 4.74 %. This is higher
than under any predicted ordering, because FCFS holds short jobs in the queue for longer.
The rank displacement in its row is counterfactual, and it does not change the service
order of FCFS itself.

The effect on scores is limited: `abs_delta_score_p99` = 10.814 seconds and
`abs_delta_score_max` = 40.641 seconds. For the rank displacement in the queue,
`abs_rank_displacement_p99` = 754.6 and `abs_rank_displacement_max` = 4377. The `jobs`
column is 17634760 in every row, which is the number of jobs in one overlay.

## 4. Attribution that changes one item at a time

All comparisons keep the original Guard(600) parameters. `class_term_local` changes only
the namespace. `drop_unreplayed` only deletes the records that did not enter the pool
replay. The four `same_copy_lag*` variants only shift the release time of the outcomes of
same-copy submissions, by 60, 300, 900 and 3600 seconds. The exogenous history and the
arrival-known columns stay unchanged.

The lag does not only filter recent results. It also reorders the retained outcomes by
their new release times. This avoids ordering errors in the rolling last-120 features.

These single-item comparisons all use the frozen original M4 and do not retrain it.
`combined_frozen` also combines the three feature restrictions of the first conservative
variant, and it still uses the original weights. Its difference from the committed
`conservative` isolates the single item of **model refitting**. We cannot add the
single-item effects: deletion, namespace, ordering and the tree model interact.

`static` and the committed `conservative` still use the models that we originally trained
for them. We did not replace them with versions that use the frozen original weights.

The table below comes from `attribution_comparison.csv`. Every entry is for Guard(600)
with the original parameters, pooled over the five overlays. Each cell gives `gap_closed`
with its `gap_closed_lo`/`gap_closed_hi`. The `exact` in the last row comes from the same
cell of `exact_comparison.csv`, and we put it here as a reference.

| variant | rho=0.5, k=7.8 | rho=0.8, k=5 | rho=1.0, k=4 |
|---|---|---|---|
| original | 0.740 [0.713, 0.760] | 0.837 [0.815, 0.851] | 0.801 [0.764, 0.842] |
| class_term_local | 0.739 [0.714, 0.759] | 0.839 [0.819, 0.852] | 0.807 [0.771, 0.845] |
| other_class_withheld | 0.739 [0.715, 0.758] | 0.837 [0.818, 0.850] | 0.806 [0.770, 0.844] |
| drop_unreplayed | 0.711 [0.680, 0.732] | 0.814 [0.785, 0.829] | 0.770 [0.724, 0.814] |
| same_copy_lag_60 | 0.639 [0.594, 0.674] | 0.679 [0.585, 0.723] | 0.573 [0.473, 0.649] |
| same_copy_lag_300 | 0.643 [0.606, 0.681] | 0.653 [0.587, 0.695] | 0.519 [0.443, 0.603] |
| same_copy_lag_900 | 0.681 [0.642, 0.722] | 0.663 [0.606, 0.706] | 0.502 [0.434, 0.595] |
| same_copy_lag_3600 | 0.680 [0.641, 0.721] | 0.675 [0.629, 0.714] | 0.518 [0.454, 0.611] |
| combined_frozen | 0.677 [0.653, 0.706] | 0.705 [0.660, 0.735] | 0.536 [0.462, 0.631] |
| conservative | 0.640 [0.604, 0.671] | 0.634 [0.560, 0.688] | 0.429 [0.357, 0.533] |
| static | 0.560 [0.519, 0.594] | 0.571 [0.504, 0.638] | 0.349 [0.281, 0.457] |
| exact | 0.724 [0.697, 0.747] | 0.785 [0.748, 0.807] | 0.672 [0.602, 0.743] |

Read the busiest-load column from top to bottom. When we change only the namespace, the
value is 0.807. Next, when we delete whole records of the other classes of the same term,
the value is 0.806. Neither change lowers the 0.801 of the original scores. When we delete the
history that has no replayed job, the value falls to 0.770.

The fixed lag is what really moves the result. Its values are 0.573 at 60 seconds, 0.519
at 300 seconds, 0.502 at 900 seconds and 0.518 at 3600 seconds. The three restrictions
together, still with the frozen weights, give 0.536. After the refit, the committed
conservative gives 0.429. This step alone isolates the contribution of model refitting.

The exact certificate gives 0.672, higher than any fixed-lag level: a one-hour lag deletes
far more history than the replay really requires. The lag levels are not monotone (the
result at 900 seconds is below the result at 3600 seconds). Therefore, we cannot read
these four points as a dose–response curve. We also cannot add the single-item effects.

## 5. Exact results for all development units, and the headline

Before we measured, we pinned all 5 primary overlays × 3 load levels, and we did not pick
a subset by performance. The policies are SPJF-E, Guard(300), Guard(600), Guard(1200) and
Aging(600). The four scores in the main comparison are original, exact, committed
conservative and static. Neither the parameters of the three Guards nor the Aging beta
changes because of development results.

`exact_cells.csv` holds the per-cell results, and `exact_comparison.csv` holds the summary
pooled over the five overlays. The p99dl and the gap closed keep the original aggregation.
Their intervals still come from the original paired week-block bootstrap with 2,000
resamples. The max excess and the harm use the original worst-cell aggregation. The firing
rate uses the original queue-weighted definition.

A distribution summary is the mean of the corresponding statistic over the five overlays,
and for max it is the largest value. It is not one pooled distribution that mixes all the
affected jobs.

The table below comes from `exact_comparison.csv`. It covers five primary overlays, three
load levels, five policies and four scores, with no cell missing. Look first at
`gap_closed` with its `gap_closed_lo`/`gap_closed_hi`.

| policy | variant | rho=0.5, k=7.8 | rho=0.8, k=5 | rho=1.0, k=4 |
|---|---|---|---|---|
| SPJF-E | exact | 0.740 [0.711, 0.765] | 0.849 [0.817, 0.867] | 0.848 [0.802, 0.878] |
| SPJF-E | original | 0.754 [0.725, 0.776] | 0.885 [0.862, 0.899] | 0.916 [0.892, 0.930] |
| SPJF-E | conservative | 0.662 [0.629, 0.691] | 0.735 [0.682, 0.766] | 0.670 [0.599, 0.733] |
| SPJF-E | static | 0.565 [0.524, 0.599] | 0.627 [0.578, 0.680] | 0.525 [0.461, 0.604] |
| Guard(300) | exact | 0.677 [0.644, 0.703] | 0.645 [0.574, 0.694] | 0.356 [0.268, 0.474] |
| Guard(300) | original | 0.705 [0.678, 0.724] | 0.738 [0.697, 0.761] | 0.478 [0.387, 0.602] |
| Guard(300) | conservative | 0.576 [0.527, 0.616] | 0.473 [0.391, 0.556] | 0.217 [0.143, 0.326] |
| Guard(300) | static | 0.514 [0.464, 0.555] | 0.387 [0.317, 0.478] | 0.202 [0.136, 0.288] |
| Guard(600) | exact | 0.724 [0.697, 0.747] | 0.785 [0.748, 0.807] | 0.672 [0.602, 0.743] |
| Guard(600) | original | 0.740 [0.713, 0.760] | 0.837 [0.815, 0.851] | 0.801 [0.764, 0.842] |
| Guard(600) | conservative | 0.640 [0.604, 0.671] | 0.634 [0.560, 0.688] | 0.429 [0.357, 0.533] |
| Guard(600) | static | 0.560 [0.519, 0.594] | 0.571 [0.504, 0.638] | 0.349 [0.281, 0.457] |
| Guard(1200) | exact | 0.733 [0.707, 0.755] | 0.789 [0.757, 0.810] | 0.708 [0.656, 0.759] |
| Guard(1200) | original | 0.746 [0.719, 0.768] | 0.844 [0.823, 0.857] | 0.830 [0.801, 0.857] |
| Guard(1200) | conservative | 0.642 [0.610, 0.672] | 0.649 [0.591, 0.690] | 0.516 [0.448, 0.593] |
| Guard(1200) | static | 0.559 [0.518, 0.592] | 0.588 [0.537, 0.647] | 0.443 [0.378, 0.531] |
| Aging(600) | exact | 0.615 [0.542, 0.654] | 0.529 [0.425, 0.622] | 0.256 [0.218, 0.329] |
| Aging(600) | original | 0.613 [0.548, 0.653] | 0.608 [0.505, 0.677] | 0.313 [0.276, 0.404] |
| Aging(600) | conservative | 0.228 [0.180, 0.271] | 0.111 [0.082, 0.161] | 0.051 [0.035, 0.074] |
| Aging(600) | static | 0.128 [0.095, 0.168] | 0.052 [0.035, 0.088] | 0.029 [0.018, 0.038] |

The other columns of the exact variant come from the same file, and the headers are the
column names:

| policy | level | p99_dl_s | max_excess_s | harm_s | fired_pct | reduction_pct |
|---|---|---:|---:|---:|---:|---:|
| SPJF-E | 0 | 14.94 | 1237.454 | 248.057 | 0.00 | 45.87 |
| SPJF-E | 1 | 46.42 | 3025.763 | 705.892 | 0.00 | 60.96 |
| SPJF-E | 2 | 78.46 | 5830.092 | 1324.288 | 0.00 | 71.24 |
| Guard(300) | 0 | 16.14 | 200.095 | 116.024 | 2.09 | 41.98 |
| Guard(300) | 1 | 63.84 | 206.011 | 127.906 | 12.96 | 46.35 |
| Guard(300) | 2 | 191.52 | 223.629 | 146.319 | 28.94 | 29.90 |
| Guard(600) | 0 | 15.25 | 498.598 | 248.057 | 0.45 | 44.88 |
| Guard(600) | 1 | 51.90 | 508.984 | 215.642 | 2.64 | 56.35 |
| Guard(600) | 2 | 118.94 | 519.871 | 332.841 | 7.82 | 56.43 |
| Guard(1200) | 0 | 15.07 | 833.467 | 94.537 | 21.78 | 45.43 |
| Guard(1200) | 1 | 51.60 | 1101.439 | 127.828 | 9.44 | 56.64 |
| Guard(1200) | 2 | 110.49 | 1118.731 | 212.556 | 6.37 | 59.51 |
| Aging(600) | 0 | 17.16 | 888.508 | 244.561 | 0.00 | 38.11 |
| Aging(600) | 1 | 74.05 | 1453.994 | 358.088 | 0.00 | 37.97 |
| Aging(600) | 2 | 214.89 | 1837.105 | 454.676 | 0.00 | 21.47 |

The headline reading is at the busiest load. For Guard(600) exact, `gap_closed` =
0.6715344319171953 with the interval [0.6024522980795439, 0.742715180786423], and
`p99_dl_s` = 118.93693605000044 seconds. In the same cell, original is 0.8013141740724661,
conservative is 0.42907950876102036 and static is 0.34876069519470415. In the same cell,
unguarded SPJF-E gives exact 0.8478892898214522, conservative 0.670404820033541 and
original 0.916436739323007.

The per-job bound of Guard still holds under exact. In this cell, the `max_excess_s` of
the three Guards is 223.629, 519.871 and 1118.731 seconds. These are below their promises
of 300, 600 and 1200 seconds respectively. Aging(600) has no such guarantee, and under
exact its `max_excess_s` = 1837.105 seconds, which we report as it is. Under exact, harm
does not fall in general: the `harm_s` of Guard(600) at the three load levels is 248.057,
215.642 and 332.841.

`exact_sensitivity_comparison.csv` compares two versions of Guard(600). The first keeps
the exogenous history of other classes. The second deletes that history whole and then
runs the exact refinement. This tests the copy semantics, not the same-copy queueing
delay.

The table below comes from `exact_sensitivity_comparison.csv` and covers Guard(600) in all
15 cells.

| level | variant | p99_dl_s | gap_closed [lo, hi] | max_excess_s | harm_s | fired_pct |
|---|---|---:|---|---:|---:|---:|
| 0 | exact | 15.25 | 0.724 [0.697, 0.747] | 498.598 | 248.057 | 0.45 |
| 0 | exact_other_class_withheld | 15.32 | 0.722 [0.694, 0.743] | 500.418 | 153.893 | 0.38 |
| 1 | exact | 51.90 | 0.785 [0.748, 0.807] | 508.984 | 215.642 | 2.64 |
| 1 | exact_other_class_withheld | 52.65 | 0.777 [0.736, 0.798] | 507.739 | 344.166 | 2.60 |
| 2 | exact | 118.94 | 0.672 [0.602, 0.743] | 519.871 | 332.841 | 7.82 |
| 2 | exact_other_class_withheld | 122.69 | 0.655 [0.583, 0.732] | 519.811 | 320.159 | 7.75 |

At the busiest load, `gap_closed` falls from 0.6715344319171953 to 0.6552768465857393. Its
interval moves from [0.602, 0.743] to [0.583, 0.732], and `p99_dl_s` goes from 118.94
seconds to 122.69 seconds. At all three load levels, the direction is the same and the
size is smaller than the difference between original and exact. This shows that the copy
semantics is not the dominant term.

This sensitivity deletes only the other replicated classes of the same term. We keep the
history of earlier terms under both readings.

The headline decision and its limits are in the 2026-09-23 Amendment of ADR 0007. We keep
the old decision and the original tables as history. The original scores are the
optimistic reference. The conservative and static scores are reference anchors with less
history information, not mathematical upper or lower bounds on performance.

The original pooled AUROC of 0.9360, the conservative 0.9116 and the static 0.8371 belong
to the original predictor comparison. The exact scores change with the policy and the
cell. We cannot attribute the fall in the old pooled AUROC to queueing. We also cannot use
it in place of this policy-specific experiment.

## 6. Cost and limits of reselection on the validation pool

We fixed the validation pool, the per-cell harm constraint and the rule that maximises the
worst-cell gap before this work. A reselection by the exact scores would need a separate
refinement for each candidate policy. It could not share the exact scores of the finally
selected policy and then sweep all the parameters.

Before we looked at the new results, we split the fixed, capped, hybrid and aging grids
into 12 strata for the timing plan. From each stratum, we drew one candidate uniformly at
random and, independently, one validation cell uniformly at random, with seed 20260922.
The 42 fixed points form three strata. We stratified the capped and hybrid grids by the
three values of G. The 11 aging points form three strata.

We first wrote the plan to `outputs/consistent_selection_final/timing_plan.json`.
`timing_cells.csv`, `timing_passes.csv` and `cost_projection.json` hold the full
measurements and the extrapolation.

We extrapolated to all 15 cells with each stratum weighted by its size. We also applied
the saving from the reduction of 258 Guard expanded points to 243 distinct schedules. We
then divided by two for an ideal two-worker speed-up. We did not count fitting, disk reads
or the FCFS/SJF reference. The result is therefore an optimistic time estimate, not a
statistical lower confidence bound. The scheduling metrics of the timing sample take no
part in parameter selection.

All 12 timing points finished, and every terminal pass had zero violations. The refinement
itself took 3,329.65 seconds in total. The timing loop, including disk reads and the
references, took 3,427.29 seconds. The whole command, including the reproduction of the
frozen models, took about 58.1 minutes. The samples are below, with each cell written as
overlay/level:

| stratum | grid weight | drawn policy | cell | passes (including the zero pass) | refinement seconds |
|---|---:|---|---|---:|---:|
| fixed low | 14 | FIX-B60 | 4/2 | 14 | 300.84 |
| fixed middle | 14 | FIX-B568.726 | 4/1 | 17 | 333.68 |
| fixed high | 14 | FIX-B2919.9 | 3/2 | 15 | 331.96 |
| capped 300 | 54 | B240, eta=.75 | 3/2 | 15 | 353.37 |
| capped 600 | 54 | B30, eta=.9 | 3/2 | 15 | 349.59 |
| capped 1200 | 54 | B120, eta=.25 | 4/1 | 13 | 279.34 |
| hybrid 300 | 18 | B0, gamma=4, eta=.9 | 1/2 | 14 | 321.38 |
| hybrid 600 | 18 | B120, gamma=4, eta=0 | 2/0 | 12 | 207.71 |
| hybrid 1200 | 18 | B30, gamma=4, eta=0 | 4/1 | 15 | 300.57 |
| aging low | 4 | beta=.00003 | 0/1 | 14 | 192.77 |
| aging middle | 4 | beta=.001 | 2/2 | 15 | 227.84 |
| aging high | 3 | beta=.1 | 2/2 | 8 | 130.60 |

The optimistic full-grid extrapolation, deduplicated and with two workers, is **164.26
hours**. This exceeds the budget of about 8 hours by a factor of about 20.5. The serial
extrapolation without deduplication is 348.26 hours. We therefore did not run the exact
full-grid reselection, and there is no second set of selected parameters.

What we actually completed is the pre-declared cost assessment above and the full
development comparison with the original parameters fixed. From this, readers can compare
the results of the same decision rule under different information protocols. They cannot
use it to claim the optimal parameters under exact or the feasibility on the validation
pool. Nor can they use it to claim the development performance after a change of
parameters.

The timing manifest records the SHA of the four core implementation files. After the
timing, we added two things. The first keeps the absolute scores of the first pass in
memory, for exact tie handling of the queue rank. The second is the sensitivity boundary
"keep another class if it has no replayed job". Neither changes the violation detection
used for the timing, the scheduling or the semantics of the main refinement. We also did
not enable the second addition in the timing sample.

The cost extrapolation does not include a separate re-measurement of these two items. We
do not treat it as a promise of precise wall-clock time.

The retained parameters are below. The frozen-score sensitivity changes the information
protocol, not the rule that selects the parameters.

| policy | family | B0 base (s) | eta | gamma base (s) | beta |
|---|---|---:|---:|---:|---:|
| Guard(300) | capped | 60 | .5 | 0 | — |
| Guard(600) | capped | 120 | .75 | 0 | — |
| Guard(1200) | hybrid | 0 | 0 | 16 | — |
| Aging(600) | linear aging | — | — | — | .03 |

We originally selected the Guard points under original, and the .03 of Aging under
conservative. A comparison at fixed parameters can isolate the effect of the information
protocol. However, it is not the result of optimal tuning under exact. It does not prove
that exact still meets the feasibility condition of the original validation-pool
selection. Nor can we call the full grid that we did not run a reselection. Development
results do not flow back into the choice of any candidate.

`Aging(600)` keeps its original comparison label. The 600 is the target of the original
validation protocol. It is not a per-job upper bound that still holds after the scores
change. We must report its max excess and harm under exact as they are.

## 7. Reproduction, preservation of the old tables and run cost

The measurement uses the immutable `configs/visibility_development_20260922.yaml`. We
wrote the final decision back to `configs/main.yaml`, not to the measurement
configuration. The old output manifests point to the byte-identical
`configs/main_original_84932d9.yaml`. They keep the original configuration and output
hashes. We do not claim that we reran the old tables under the new configuration.

```sh
env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME \
  NUMBA_NUM_THREADS=4 OMP_NUM_THREADS=4 uv run --no-sync python \
  scripts/assess_consistent_selection.py \
  --config configs/visibility_development_20260922.yaml \
  --out-dir outputs/consistent_selection_final --workers 2

env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME \
  NUMBA_NUM_THREADS=4 OMP_NUM_THREADS=4 uv run --no-sync python \
  scripts/run_consistent_visibility.py \
  --config configs/visibility_development_20260922.yaml \
  --pool primary --out-dir outputs/dev_consistent_visibility --workers 2 --resume
```

The exact runner runs at most two cells at the same time. Each worker refines the policies
in order and reuses its own frozen models and cache. The main process builds the control
scores and then releases the full context. Each of the two persistent workers rebuilds the
same model recipe and checks it value by value. The workers share no mutable history
state.

Aggregation follows a cell order fixed in advance, not the order of completion, so that
the floating-point aggregation order stays the same. Only one heavy command runs at a
time, with `--workers 2` and with 4 threads each for Numba and OpenMP.

The `stage` and `seconds` columns of `exact_costs.csv`, summed by stage, with the number
of rows in the second column:

| stage | rows | total seconds |
|---|---:|---:|
| frozen_models | 1 | 63.89 |
| score_controls | 1 | 1033.36 |
| worker_frozen_models | 2 | 131.81 |
| cell_baselines | 15 | 253.29 |
| fcfs_decomposition | 15 | 655.47 |
| attribution | 165 | 2375.15 |
| exact_policy | 75 | 20615.30 |
| exact_sensitivity | 15 | 5538.27 |
| parallel_cells_wall | 1 | 15592.54 |
| total_compute | 1 | 16690.42 |

`total_compute` is a single row of 16690.42 seconds, and its detail reads
`before table writes`. `parallel_cells_wall` is also a single row, of 15592.54 seconds,
and its detail reads
`max_workers=2; worker_model_fits=2; parent model fit built controls and was released before worker launch`.
Per policy, `exact_policy` takes 123.15 seconds at the shortest and 405.79 seconds at the
longest.

We group `exact_passes.csv` by `overlay`/`level`/`policy`/`variant`. `variant=exact` has
75 units (5 policies × 15 cells), with 10–18 passes each (including the final pass with
zero violations) and 1033 passes in total. In the final pass of every unit,
`terminal_zero` is `True` and `offending_records` is `0`. In
the final state, `cumulative_jobs` lies between 145,463 and 681,325, and
`cumulative_records` lies between 1,171,095 and 6,526,252. Each cell has 17,634,760 jobs.

`variant=exact_other_class_withheld` has 15 units (Guard(600) × 15 cells), with 11–17
passes each and 214 passes in total. Their final passes also all have zero violations.
Look at the convergence in one cell. At the busiest load, Guard(600) takes 15, 15, 16, 14
and 14 passes on the five overlays. The final numbers of withheld jobs are 570,586,
576,095, 580,679, 566,237 and 568,459.

The `notes` of `manifest.json` record the semantics of this run:

- `model_weights` = frozen original M4 rolling-origin LightGBM
- `other_class_terms` = exogenous on their original relative clock
- `other_class_sensitivity` = same-semester other-class history withheld
- `terminal_assertion` = every exact policy/cell ends with zero new violation
- `dense_policy_scores_written` = false

`exact_delta_manifest.csv` pins the completeness of the sparse deltas. The consistent
visibility item of `scripts/check_generated.py` reads this manifest and all the CSVs, and
it reports `1 run(s) have complete monotone, terminal-zero certificates`.

`scripts/check_preserved_outputs.py` checks the 18,627 rows and all the original columns
of the original 75 CSVs byte for byte. A further 10 existing check/smoke CSVs with 308
rows, which we never reran or rewrote, enter an auxiliary snapshot check.
`scripts/check_consistent_visibility.py` checks the full coverage, the monotone
certificates and the sparse deltas. It also checks the replayed
original/conservative/static anchors against the old per-cell tables.

We write the new tables derived for the paper to the separate
`outputs/consistent_paper_tables/`, and we do not overwrite `outputs/paper_tables/`. The
commands, the order of the sealed run and the disk budget are in `GENERATED.md` and
`docs/sealed_run_procedure.md`. Here we update only the draft and do not create a formal
lock.

## 8. Statements the paper can use

<!-- PAPER_SENTENCES -->
