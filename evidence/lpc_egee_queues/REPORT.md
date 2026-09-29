# LPC-EGEE per queue: a 900-second limit class where the guard finally bites, on a fit that does not hold up

**Verdict.** Splitting the log by walltime class changes the picture in one direction and refuses to
change it in another. It changes the promise: with `L = 900 s` the guard's 3.5L promise is 3,150 s
instead of the pooled study's 907,200 s, the work budget fires (1.4 % of dispatch epochs), and the
per-job bound is nearly attained — the worst realised excess is **3,129 s against an allowance of
3,150 s, a ratio of 0.993**, where the pooled study's ratio was 0.046. It does not rescue
applicability condition 1 as the paper defines it. Condition 1 holds on the *recorded* waits of the
900-second `test` queue by a wide margin (held-out p99 = 7.6L on CE1, 18.7L on CE2), but the FCFS
counterfactual the condition is actually stated on passes only at the fitted capacity `k = 1`, which
is a corner of the search grid, and fails outright at the queue's observed concurrency ceiling. The
hypothesis as posed — "condition 1 is a property of the limit class a pool serves" — survives only
in the weak, recorded-wait form. Everything below is a replay on a model we impose, because the six
queues demonstrably shared the same machines.

## 1. What is different from `evidence/lpc_egee/`

Same input file, same filter ledger, same retained count (**206,222**, asserted against the previous
study before anything else runs), same chronological split (2005-01-12T22:38:29Z, day 120 after the
first cleaned arrival), same excluded incident (original SWF days [138, 153), i.e. cleaned days
96.50–111.50). Three things are new.

**One pool per (partition, queue), with that class's own L.** The theorem constant is 900 s for the
`test` queue, not the 259,200 s pool maximum.

**Three partitions, not two.** The SWF header names `clrglop195`, `clrce01`, `clrce02`. The previous
study merged `clrglop195` (partition 1) into "old_CE2". They are different machines in different
periods: partition 1 stops on cleaned day 76.76 (2004-11-30) and owns **no** held-out arrival, while
CE2 starts on day 77.63. The merge is also what produced the previous audit's unexplained
"observed 58 against a documented 56": the 58 is partition 1's own maximum. **CE2 alone maxes out at
exactly 56 simultaneous jobs**, matching its documentation. Partition 1 is audited here and then
excluded from every fit and replay; 170,249 of the 206,222 retained jobs are replayed, the rest
being partition 1 and the `batch` queue (see section 3).

| part | machine | n | first day | last day | held-out arrivals | max concurrent |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | clrglop195 | 34,467 | 0 | 76.76 | 0 | 58 |
| 2 | clrce01 (CE1, 84 CPUs) | 111,236 | 1.54 | 238.64 | 66,538 | 85 |
| 3 | clrce02 (CE2, 56 CPUs) | 60,519 | 77.63 | 238.65 | 50,272 | 56 |

**Two capacities per cell, both fixed before the held-out part.** `fit` is the inherited grid
objective (|log mean ratio| + |log p90 ratio| over arrivals that had submitted *and* completed before
the cutoff, every integer k up to the partition's CPU count). `obs` is the largest number of that
cell's own jobs observed running at once before the cutoff — the structural reading of a queue
concurrency ceiling. `fit` is primary; `obs` exists so that a corner solution cannot hide.

## 2. Did the queues share machines? Yes, and it is measurable

If each queue had owned nodes, the per-queue running maxima could not sum past the partition's CPU
count. On CE1 they sum to **337 against 84 CPUs**; on CE2 to **203 against 56**. The archive's own
page dates per-queue running-job ceilings to 7 March 2005, inside the held-out period, and the SWF
header says only that "queues enforce a runtime limit". So a per-queue pool is **our model**, on the
same footing as the paper's other constructed pools; the recorded waits of a queue validate that
sub-pool model only, never the real multi-queue Maui schedule.

## 3. Per-queue audit

All retained arrivals; waits and limits in seconds; `top1`/`top5` are shares of capped executed work
inside that queue; `concurrent p99` is time-weighted over the log outside the incident.

| queue | L | n | held-out n | wait p50 | wait p90 | wait p99 | recorded p99 / L | top1 | top5 | mean service | max concurrent | concurrent p99 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| test | 900 | 41,143 | 34,707 | 3 | 5 | 21,496.6 | **23.89** | 0.228 | 0.665 | 31.6 | 30 | 2 |
| batch | 3,600 | 1,506 | 1,506 | 1 | 2 | 2,860.6 | 0.79 | 0.619 | 0.947 | 39.5 | 4 | 0 |
| short | 7,200 | 69,446 | 19,353 | 4 | 507 | 4,701.0 | 0.65 | 0.224 | 0.509 | 166.1 | 86 | 11 |
| long | 86,400 | 30,602 | 21,235 | 4 | 55 | 14,211.0 | 0.16 | 0.296 | 0.673 | 2,624.3 | 83 | 42 |
| day | 129,600 | 18,594 | 18,236 | 3 | 61 | 8,382.7 | 0.06 | 0.160 | 0.501 | 6,437.1 | 81 | 60 |
| infinite | 259,200 | 44,931 | 21,773 | 4 | 1,094 | 16,426.2 | 0.06 | 0.209 | 0.599 | 8,953.9 | 140 | 115 |
| pooled | 259,200 | 206,222 | 116,810 | 4 | 478 | 11,917.4 | 0.05 | 0.407 | 0.835 | 2,983.2 | 142 | 134 |

Two facts decide the rest of the study. The `test` queue's recorded p99 wait is **23.9 times its own
limit** (27.5 on CE1, 16.7 on CE2), which no other queue approaches. And cost concentration
**inside** a capped class is far weaker than pooled: 16–36 % of the class's work sits in its top 1 %
of jobs, against 40.7 % pooled. Pooling queues with different limits is itself a large part of the
pooled heavy tail — a point the previous report suspected and this measures.

Two queues drop out before any replay. **`batch`** has no arrival that both submitted and completed
before the cutoff (all 1,506 of its jobs are held-out), so no capacity can be fitted without using
the test part; it is audited and dropped. **`day`** has 67 and 270 visible fit rows on CE1 and CE2,
below the pre-set `MIN_FIT_ROWS = 500`, and the resulting capacities give a simulated offered load of
1.097 on CE1 — an unstable queue whose p99 of 4.0 million seconds is an artefact of a diverging
simulation, not congestion. Its numbers stay in the tables, flagged, and support nothing.

## 4. The capacity fit is a corner solution on the queue that matters

The `test` queue did not exist for most of the fit window: its first arrival is day 90.77
(2004-12-14) on CE2 and day 112.36 (2005-01-05) on CE1. CE1's `test` queue therefore has **7.6 days**
of fitting data, beginning nine hours after the excluded incident ends, and roughly 40 % of those
1,927 rows fall on days 112–115, which carry the recovery congestion the prespecified window does not
cover. The fit-part recorded mean wait is 4,970 s; the best k in 1..84 is **k = 1**, and it produces
a mean of 6.6 s. The objective is minimised at the grid boundary because even a single server
under-predicts by a factor of 753. CE2's `test` queue is better placed (14.2 days, 4,509 rows,
recorded fit mean 215 s) and also lands on k = 1, under-predicting by a factor of 25.

Held-out wait profiles at the primary capacity, in seconds:

| cell | L | k | offered load | recorded mean | sim mean | recorded p99 | sim p99 | hourly r |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CE1 test | 900 | 1 | 0.096 | 238.9 | 697.2 | 6,815.4 | 16,710.7 | -0.027 |
| CE2 test | 900 | 1 | 0.025 | 419.7 | 57.4 | 16,807.6 | 2,202.9 | -0.008 |
| CE1 short | 7,200 | 67 | 0.003 | 519.9 | 0.0 | 14,289.0 | 0.0 | — |
| CE2 short | 5,400 | 46 | 0.005 | 117.7 | 0.0 | 726.4 | 0.0 | — |
| CE1 long | 86,400 | 38 | 0.131 | 648.2 | 724.7 | 22,860.1 | 29,091.5 | 0.226 |
| CE2 long | 86,400 | 20 | 0.063 | 418.5 | 189.1 | 20,547.8 | 8,265.4 | 0.283 |
| CE1 infinite | 259,200 | 83 | 0.185 | 891.9 | 382.9 | 12,405.8 | 10,899.9 | 0.123 |
| CE2 infinite | 259,200 | 43 | 0.162 | 2,025.4 | 2,203.6 | 83,621.7 | 81,279.0 | 0.364 |

The per-queue simulator is **not** a better model of the recorded waits than the pooled one. On the
`test` queue it misses in opposite directions on the two partitions (2.9x high on CE1, 7.3x low on
CE2) and hourly correlation is indistinguishable from zero. The `short` queue is worse still: at the
fitted capacity its held-out FCFS wait is identically zero while the recorded p99 is 14,289 s on CE1.
A queue treated as its own pool cannot produce those waits, because the jobs that caused them were
not in that queue. This is the mechanism, stated plainly: **the recorded wait of a short-limit job at
this site is mostly time spent behind other queues' long jobs on shared machines.** Splitting by
class removes exactly the load that created the wait.

## 5. Applicability, per class, held-out part

`condition 1` is the paper's: FCFS p99 > (3 - 2/k)L, with the FCFS replay, not the recorded wait.
`>= 3L` is the rule-of-thumb form; at k = 1 the exact floor collapses to L, so both are shown.
`condition 2` uses the same reproducible 25 % top-1 % proxy as the previous audit.

| cell | L | k(fit) | FCFS p99 | /L | busy /L | cond 1 floor | cond 1 >=3L | recorded p99 /L | recorded >=3L | top1 | cond 2 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CE1 test | 900 | 1 | 16,710.7 | 18.57 | 18.57 | yes | **yes** | 7.57 | yes | 0.167 | no |
| CE2 test | 900 | 1 | 2,202.9 | 2.45 | 2.84 | yes | no | 18.68 | yes | 0.350 | **yes** |
| test pooled | 900 | 1 | 12,386.7 | 13.76 | 14.30 | yes | **yes** | 11.95 | yes | 0.213 | no |
| CE1 short | 7,200 | 67 | 0.0 | 0.00 | 0.00 | no | no | 1.99 | no | 0.280 | yes |
| CE2 short | 5,400 | 46 | 0.0 | 0.00 | 0.00 | no | no | 0.14 | no | 0.193 | no |
| CE1 long | 86,400 | 38 | 29,091.5 | 0.34 | 0.34 | no | no | 0.27 | no | 0.243 | no |
| CE2 long | 86,400 | 20 | 8,265.4 | 0.10 | 0.10 | no | no | 0.24 | no | 0.319 | yes |
| CE1 infinite | 259,200 | 83 | 10,899.9 | 0.04 | 0.04 | no | no | 0.05 | no | 0.162 | no |
| CE2 infinite | 259,200 | 43 | 81,279.0 | 0.31 | 0.31 | no | no | 0.32 | no | 0.220 | no |
| CE1 day (dagger) | 129,600 | 7 | 4,035,464 | 31.14 | 31.14 | yes | yes | 0.09 | no | 0.151 | no |
| CE2 day (dagger) | 129,600 | 12 | 565,956 | 4.37 | 4.37 | yes | yes | 0.04 | no | 0.169 | no |

(dagger) unstable simulation on a thin fit; the FCFS p99 is a divergence, not a wait.

At the observed concurrency ceiling (`obs`) the `test` queue's fitted pool becomes k = 10 on CE1 and
k = 6 on CE2 and its **held-out FCFS p99 is exactly zero on both**; `short` and `long` are likewise
zero. Under that reading condition 1 fails everywhere except the unstable `day` cell. The whole of
condition 1 on this trace therefore rests on which capacity a queue-pool is given, and the capacity
that passes is the boundary value of the search.

So the honest answer to the hypothesis:

- **Recorded waits**: condition 1 holds on the 900-second class on both partitions, by 7.6x and 18.7x
  on the held-out part. This *is* the first workload in this project with recorded per-job waits
  where a documented queue limit is that small relative to the observed p99.
- **FCFS counterfactual**, which is the condition the theorem needs: holds pooled and on CE1 at
  k = 1, fails on CE2 at the 3L form, fails on both at the observed ceiling. Not robust.
- **Condition 2 inside a capped class**: 0.213 pooled on the held-out `test` queue, 0.167 on CE1,
  0.350 on CE2. Measured, moderate, below the 25 % proxy except on CE2. Capping service at 900 s
  mechanically limits how concentrated the work inside that class can be.
- Therefore **both conditions hold together, under the paper's own definitions, on one cell only**
  (CE2's `test` queue passes condition 2 and the exact floor but not the 3L form; CE1's passes
  condition 1 both ways but not condition 2). No cell passes both in their strict forms.

## 6. Predictor, per class, submission visibility

Features: user, group, partition, requested time, queue limit, plus that user's own completion
history readable at the arrival instant (count, mean cost, mean and sd of log cost, last cost,
last-five mean, time since the last completion). Package defaults from
`src/spjf_guard/predict/scores.py`: Tweedie power 1.5 on capped seconds, 400 rounds, 63 leaves,
learning rate 0.05, min leaf 50, feature/bagging 0.9, seed 3, deterministic, four threads. Levels,
the heavy threshold (that class's training p95) and the trees are all fixed at the cutoff. An
independent from-scratch recomputation of the history columns matched on 160 sampled rows per
variant.

| class | heavy threshold | held-out heavy rate | n train | n test | AUROC | AP | Spearman |
| --- | --- | --- | --- | --- | --- | --- | --- |
| test | 16 s | 0.212 | 6,436 | 34,707 | **0.746** | 0.497 | 0.501 |
| short | 1,004 s | 0.093 | 50,093 | 19,353 | 0.846 | 0.278 | 0.551 |
| long | 3,494 s | 0.111 | 9,361 | 21,235 | 0.737 | 0.285 | 0.643 |
| day | 3,486 s | 0.197 | 337 | 18,236 | 0.715 | 0.395 | 0.389 |
| infinite | 38,060 s | 0.076 | 23,129 | 21,773 | 0.792 | 0.264 | 0.638 |

Restricting the history to the same queue costs the `test` class accuracy (AUROC 0.674) and helps the
`short` class (0.899): within a class the useful signal about a user's next job partly comes from
what that user ran elsewhere. The primary models use the full own-user stream, which is what a
submission-time scorer really sees. The held-out heavy rate of 21 % against a 5 % training definition
shows how far the `test` class drifts after the cutoff — its training p95 is 16 seconds.

As in the previous study the history stream is the **recorded** one and is not recomputed under the
counterfactual schedules, so this is an open-loop replay.

## 7. Replay: the guard fires, and its bound is nearly attained

Per class, at that class's own L and fitted k, both partitions pooled, held-out arrivals only
(115,304 replayed test-part jobs). `B_max = k(G - (3 - 2/k)L)`; constant shape `B0 = B_max, eta = 0`;
age-relative shape `B0 = kL/4, eta = 0.5` at 3.5L and 5L and `B0 = kL/2, eta = 0.75` at 10L,
transferred unchanged from the paper's development selection. Busy windows are arrival-hours at or
above that cell's own fit-part 90th percentile of hourly arrivals, counted only over hours after the
cell's first arrival. Intervals are 2,000 paired resamples of the same 17 arrival-week blocks, seed
20260921.

**`test` queue (L = 900 s, k = 1 on both partitions), 34,707 held-out jobs, 16,813 in busy hours:**

| policy | mean | mean gap closed [95 %] | p99 | busy p99 | busy p99 gap [95 %] | max excess | harm | firing |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| FCFS | 410.2 | 0 | 12,386.7 | 13,412.8 | 0 | 0 | 0 | — |
| SJF (oracle) | 245.7 | 1 | 3,766.0 | 8,340.6 | 1 | 112,805 | 1,539 | — |
| SPJF-E | 298.7 | 0.678 [0.622, 0.757] | 5,264.8 | 9,967.5 | 0.679 [-3.11, 0.92] | **77,467** | 25 | — |
| Constant-3.5L | 316.6 | 0.569 [0.534, 0.630] | 9,849.9 | 13,933.4 | -0.103 [-0.54, 0.56] | **3,129** | 25 | 1.42 % |
| Age-3.5L | 314.9 | 0.579 [0.548, 0.641] | 9,849.9 | 13,933.4 | -0.103 [-0.54, 0.57] | 3,082 | 25 | 1.64 % |
| Constant-5L | 310.3 | 0.607 [0.577, 0.664] | 9,974.9 | 13,478.6 | -0.013 [-0.59, 0.55] | 4,444 | 25 | 1.04 % |
| Age-5L | 311.1 | 0.602 [0.575, 0.647] | 9,973.6 | 13,478.6 | -0.013 [-0.58, 0.57] | 4,338 | 25 | 1.46 % |
| Constant-10L | 304.6 | 0.642 [0.591, 0.710] | 10,477.6 | 13,965.2 | -0.109 [-2.81, 0.62] | 8,726 | 25 | 0.67 % |
| Age-10L | 304.1 | 0.645 [0.598, 0.711] | 10,317.5 | 13,940.2 | -0.104 [-2.51, 0.62] | 8,765 | 25 | 0.77 % |

Mean-wait reduction against FCFS is resolved: SPJF-E 27.2 % [19.8 %, 43.2 %], Constant-3.5L 22.8 %
[18.1 %, 32.6 %]. The busy-hour p99 is not: every interval spans zero, and the guarded policies sit
at or slightly above the FCFS busy p99 while cutting the mean. The trade-off the paper wants to show
is visible in one line: **the guard gives up 0.11 of the mean gap SPJF-E closes and cuts the worst
excess over FCFS from 77,467 s to 3,129 s, a factor of 24.8.**

The per-job bounds hold everywhere — **1,021,494 job-policy checks, 691,824 of them on held-out jobs,
zero violations** — and for the first time in this project they are nearly tight: worst
excess / allowance is **0.9933** (Constant-3.5L), 0.9876 (5L), 0.9696 (10L), against 0.046 pooled.
At k = 1 the additive identity slack 2(k-1)L is zero, so the identity residual must vanish exactly,
and it does; on the k > 1 classes the worst identity ratio is 0.446.

The other classes behave as the pooled study did. On `short` every policy's held-out wait is
identically zero, so nothing can be improved or harmed. On `long` and `infinite` the guards never
fire and their waits equal SPJF-E's (busy p99 gap 0.746 and 1.023, max excess 43,505 s and 84,213 s).
On `day` the simulation diverges and the numbers are meaningless. Only the 900-second class produces
a firing guard.

## 8. What the paper could state

> "The LPC-EGEE site ran six queues with documented walltime limits of 900 to 259,200 seconds on two
> disjoint partitions. Treating each walltime class as its own pool, the 900-second `test` class has
> a recorded p99 queue wait of 23.9 times its own limit over the whole log, and 7.6 and 18.7 times on
> the two partitions over the held-out period; pooled over all six classes the same ratio is 0.05.
> The ratio that decides applicability is therefore a property of the limit class, not of the site."

> "Inside a capped class, cost concentration is much weaker than it is pooled: the longest 1 % of the
> 900-second class hold 21.3 % of its executed work on the held-out part (16.7 % and 35.0 % by
> partition), against 40.7 % when the six classes are pooled. Part of the heavy tail of a mixed pool
> is the mixing of walltime limits."

> "On the 900-second class, at capacities fitted on the earlier part, the work-budget guard
> intervenes at 1.4 % of dispatch epochs and its per-job bound is nearly attained: the largest excess
> over the FCFS wait is 3,129 s against an allowed 3,150 s, a ratio of 0.993 over 691,824 held-out
> job-policy checks with no violation. Relative to the unguarded score it gives up 0.11 of the mean
> gap to the oracle and reduces the worst excess by a factor of 24.8."

> "We do not claim a validated wait model for this trace. An FCFS pool per walltime class, fitted on
> the earlier part, misses the held-out mean of the 900-second class by 2.9x on one partition and
> 7.3x on the other, with hourly correlations near zero, and produces identically zero waits for the
> 7,200-second class whose recorded p99 is 14,289 s. Queues at this site shared their partition's
> machines — the per-queue running maxima sum to 337 against 84 CPUs — so a short-limit job's
> recorded wait is largely time behind other classes' long jobs, which a per-class pool removes by
> construction."

Candidate `tab:cross` row, held-out part, 900-second class, both partitions:

```latex
LPC-EGEE \texttt{test} class, held-out FCFS counterfactual ($L=900$\,s, $k=1{+}1$) & 0.213 & 0.746 & 13.76 & yes & 0.679 & 3.48L & 0.569 / 3.48L \\
```

Required footnote: "The class is a pool we impose: the six queues shared their partition's machines,
and the capacity fitted for this class is the boundary value k = 1 of the search grid, chosen on 7.6
and 14.2 days of pre-cutoff data. Held-out wait-profile agreement is poor. Condition 1 holds on the
recorded waits on both partitions and on the FCFS counterfactual pooled, but fails on CE2 at the 3L
form and on both partitions at the observed concurrency ceiling. The 0.679 is the busy-hour p99 gap
closed by the unguarded score, whose interval spans zero; the guard's own busy-hour gap is -0.103 and
its resolved improvement is in the mean, 0.569 [0.534, 0.630]."

**Not supported:** that a per-queue reading makes condition 1 robustly true on this trace; that the
900-second class's FCFS counterfactual is validated; a resolved busy-hour p99 improvement of any
policy; anything at all from the `day` class; or a claim that farms "already partition by class" in
the sense the theorem needs — this farm partitioned *limits*, not *machines*.

## 9. What a referee will attack, in order of force

1. **The capacity is a corner solution, and the fit window is the worst possible one.** The
   900-second class appears on CE1 nine hours after the excluded incident ends; 40 % of its 1,927
   fitting rows are recovery days with a recorded mean wait of 4,970 s that no k in 1..84 can
   reproduce. k = 1 is the grid boundary, not an estimate. Moving to the queue's observed
   concurrency ceiling erases every held-out wait. A referee is entitled to say the applicability
   verdict on this cell is an artefact of the capacity search.
2. **Queues shared machines, so the per-class pool deletes the cause of the waits it is fitted to.**
   Measured, not assumed: 337 versus 84, 203 versus 56. The per-class model reproduces neither the
   `test` nor the `short` class's held-out waits.
3. **Non-FCFS real scheduler.** OpenPBS/Maui with per-queue running-job ceilings dated inside the
   held-out period; recorded waits are multi-queue waits and are used here only as a target and a
   descriptive statistic.
4. **2004-2005 grid middleware.** Pilot-style submission bursts, remote assignment and polling drive
   both arrivals and waits; nothing here transfers to a modern autoscaled system without argument.
5. **Open-loop features.** Completion history is taken from the recorded schedule, not recomputed
   under each counterfactual.
6. **Multiplicity.** Eleven cells, two capacity variants, three promises and two budget shapes were
   examined; one cell shows a firing guard. The intervals are conditional on the trace, the fitted
   capacity and the frozen model, and do not cover this search.

## 10. Reproduction and cost

Scripts, protocol and every table: [README.md](README.md), `qprotocol.json`, `tables.md`, and the
CSV/NPZ files beside them. Nothing outside this directory was written; the previous study's files
were read, never edited; no project dataset and no sealed data were touched.

Measured computation over the five stages: **24.86 wall seconds, 42.17 process CPU seconds**
(`compute_time.json`), plus 2.38 wall seconds for the final table-rendering pass that produced the
numbers above. One process at a time, four threads, no multiprocessing. Interpreter startup, package
resolution and reading time are excluded.
