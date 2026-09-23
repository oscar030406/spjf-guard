# LPC-EGEE: a real queue with a heavy tail, but a weak replay validation

**Verdict.** This trace supplies recorded queue waits and concentrated execution costs in the same system. It does **not** establish that Guard improves the real system. At the capacities fitted before the test period, expected-cost ordering improves the simulated mean and overall p99, but the busy-hour p99 improvement is unresolved. The work-budget guards never intervene, because the maximum queue limit makes their guarantees much coarser than the observed waits.

## 1. Audit and frozen protocol

The retained sample contains **206,222** jobs; longest 1%/5% account for **40.71%/83.54%** of capped work. The held-out sample has **116,810** jobs, with 1%/5% shares **35.1%/78.8%**. Full filter counts, all six queue distributions, utilisation, calendar cycles and applicability decisions are in [AUDIT.md](AUDIT.md). The only rerun of item 1 repaired a wrong outage clock and the CE2 short-queue limit; the input was retained and verified.

The inherited chronological split is **2005-01-12T22:38:29+00:00**, 120 days after the first cleaned arrival. Models use 89,356 pre-split rows whose recorded results are already available; 56 earlier arrivals are excluded from training because they finish too late. Capacities are selected on the same visibility rule, separately per physical pool, over every integer 1..84 or 1..56, minimising |log((simulated mean+1)/(recorded mean+1))| + |log((simulated p90+1)/(recorded p90+1))|. Fitted capacities are **83 and 56**. No test-driven capacity, load, model, window or guard selection is made.

Simulations reset only across the excluded incident, preserve idle gaps, and carry state through the train/test boundary. All replay policies use an FCFS prefix; pre-split jobs pending at the switch retain precedence. Before the split no fitted or true-size scores are used. Each segment runs until its last job starts, so jobs waiting beyond the final arrival are included. Arrivals and service are fixed across policies; service is min(raw run, documented partition/queue limit), while the bound uses the pool maximum 259,200 s.

A busy window is an arrival-hour with at least the fit-part 90th-percentile count, computed over all non-outage hours: **30 arrivals/h on CE1, 33 on old/CE2**. These frozen thresholds select **74,267** held-out arrivals. They are arrival-burst windows, not deadlines or bins selected for having long test waits.

## 2. Out-of-sample simulator validation

The production integer-microsecond simulator is imported read-only, with bytecode disabled and caches redirected here. Its FCFS output agrees exactly with the independent fitting recursion for all 206,222 jobs. There is also exact wait agreement on 120 small instances, plus dispatch-order agreement on the 100 non-FCFS cases, covering six policies, k=1/2/4/7 and same-instant events. This validates implementation, **not fidelity to Maui**.

| pool | k | recorded_mean | sim_mean | recorded_p50 | sim_p50 | recorded_p90 | sim_p90 | recorded_p99 | sim_p99 | hourly_pearson |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CE1 | 83 | 534.6 | 405 | 4 | 0 | 56 | 0 | 12,229.04 | 11,601.41 | 0.4398 |
| old_CE2 | 56 | 606.4 | 372.3 | 1 | 0 | 3 | 0 | 16,817.19 | 10,800.29 | 0.398 |

Units are seconds; hourly correlation is Pearson correlation of the two mean waits within each nonempty **arrival-hour cohort**, not a correlation with empty hours filled by zero. CE1 mean is 0.758 of recorded and old/CE2 0.614; CE1 p99 is 0.949, old/CE2 0.642. Both simulated medians/p90s are zero. The nominal-capacity and uncapped-service sensitivities in `validation.csv` do not resolve the discrepancy; no setup time is fitted.

The original “Torque/Maui, therefore non-FCFS” description is too blunt. The [archive documentation](https://www.cs.huji.ac.il/labs/parallel/workload/l_lpc/) names OpenPBS/Maui and says the serial-job scheduling order was plain FCFS before 1 June 2005; queue bonuses and group fair share began after this log ended. It also dates **queue concurrency ceilings to 7 March 2005**, within the test period. Those ceilings, periodic polling and middleware effects are absent from our work-conserving pool. We therefore do not equate recorded waits with theoretical FCFS waits. The page’s “plain FCFS” summary does not erase its own queue-ceiling qualification.

A documentation-dated diagnostic, without refitting, gives CE1 mean ratio 1.068, p99 ratio 1.043 and hourly correlation 0.888 before 7 March; afterwards hourly correlation falls to 0.281. Old/CE2 is weak even before then (correlation 0.394). This supports a structural mismatch explanation, not a post hoc rescue of the full held-out validation. Even perfect agreement of these summaries would support an aggregate queue approximation, not identify the real scheduler or validate policy counterfactuals.

## 3. Predictability and submission visibility

Features are user, group, queue, partition, requested time and queue limit, plus only that user’s completed-job count, mean cost, mean/std log cost, last cost, last-five mean and time since latest completion. Executable is uniformly -1 and omitted; status, run time and recorded wait are not submission features. Histories are swept by recorded submit+wait+raw_run <= arrival, including ties. Categorical levels and the heavy threshold use training rows only; unknown identities map to missing. Independent from-scratch recomputation matches all seven history columns on 290 sampled/boundary rows.

Heavy means capped cost > training p95 = **4,567.5 s**, with test prevalence 8.82%. The models are frozen at the split. `src/spjf_guard/predict/scores.py` supplies Tweedie power 1.5 on raw capped seconds versus squared error on log(1+C), 400 rounds, 63 leaves, learning rate .05, min leaf 50, feature/bag fractions .9, bag frequency 1. Both use seed 3, deterministic row-wise construction and four threads.

| pool | score | auroc | average_precision | log_rmse | spearman |
| --- | --- | --- | --- | --- | --- |
| all | spjf_e | 0.8922 | 0.482 | 1.888 | 0.7572 |
| CE1 | spjf_e | 0.8773 | 0.4555 | 1.835 | 0.7888 |
| old_CE2 | spjf_e | 0.9 | 0.5285 | 1.956 | 0.7005 |
| all | spjf_log | 0.8741 | 0.4636 | 1.928 | 0.7277 |
| CE1 | spjf_log | 0.8487 | 0.413 | 1.829 | 0.7842 |
| old_CE2 | spjf_log | 0.8867 | 0.5668 | 2.051 | 0.6416 |

The log-score policy has a slightly lower busy-hour p99 (10,219 versus 10,511 s), despite lower AUROC. The paired log-minus-E interval is [-1,851, 931] s; this study does not establish expected-cost ranking superiority.

**Visibility qualification:** histories are causal in the **recorded log**. Reordering changes completion times: 2,906 test arrivals (2.5%) would have at least one historical outcome unavailable under the replayed SPJF-E schedule. Thus this is a frozen, open-loop recorded-feature replay, not an operationally closed-loop predictor/scheduler experiment. The submission-only ablation avoids that feedback dependency, has AUROC 0.675, and increases busy p99 by 1.13% (interval includes zero). The direction of the open-loop bias is unknown; no lower-bound claim is justified.

## 4. Policy results, uncertainty and bounds

For G/L in {3.5,5,10}, Bmax=k(G-(3-2/k)L). Constant uses B0=Bmax, eta=0. Age-relative uses (B0/kL,eta)=(1/4,.5) at 3.5L and 5L and (1/2,.75) at 10L; gamma=0. The 5L/10L settings are transferred from the paper’s development selection (Section 8, Table `tab:setup`); 3.5L reuses the 5L setting without selection. Skip uses floor(Gk/L)-(2k-2), charged at dispatch. Exact per-pool parameters are in `policy_parameters.csv`; none were fitted here. These are constant/age ablations, not a newly selected joint winner.

| policy | mean | p99 | p99_busy | busy reduction [95% CI] | p99_busy_gap | max_excess | harm |
| --- | --- | --- | --- | --- | --- | --- | --- |
| FCFS | 391 | 11,376.55 | 10,969.34 | 0.0% [0.0%, 0.0%] | 0 | 0 | 0 |
| SJF | 245.5 | 7,315.56 | 8,596.06 | 21.6% [3.6%, 61.4%] | 1 | 80,219 | 23,384 |
| SPJF-E | 307.1 | 9,359 | 10,511 | 4.2% [-11.2%, 46.0%] | 0.1931 | 42,084 | 11,355 |
| SPJF-log | 305.5 | 9,439.12 | 10,219.02 | 6.8% [-14.0%, 39.3%] | 0.3162 | 80,266 | 16,226 |
| SPJF-static | 355.8 | 10,479.58 | 11,093 | -1.1% [-28.2%, 14.6%] | -0.05211 | 64,178 | 4,898 |
| Constant-3.5L | 307.1 | 9,359 | 10,511 | 4.2% [-11.2%, 46.0%] | 0.1931 | 42,084 | 11,355 |
| Age-3.5L | 307.1 | 9,359 | 10,511 | 4.2% [-11.2%, 46.0%] | 0.1931 | 42,084 | 11,355 |
| Skip-3.5L | 307.6 | 9,111 | 10,458.74 | 4.7% [-8.0%, 42.1%] | 0.2151 | 42,008 | 11,355 |
| Constant-5L | 307.1 | 9,359 | 10,511 | 4.2% [-11.2%, 46.0%] | 0.1931 | 42,084 | 11,355 |
| Age-5L | 307.1 | 9,359 | 10,511 | 4.2% [-11.2%, 46.0%] | 0.1931 | 42,084 | 11,355 |
| Skip-5L | 307.1 | 9,359 | 10,524.34 | 4.1% [-11.9%, 46.0%] | 0.1875 | 42,084 | 11,355 |
| Constant-10L | 307.1 | 9,359 | 10,511 | 4.2% [-11.2%, 46.0%] | 0.1931 | 42,084 | 11,355 |
| Age-10L | 307.1 | 9,359 | 10,511 | 4.2% [-11.2%, 46.0%] | 0.1931 | 42,084 | 11,355 |
| Skip-10L | 307.1 | 9,359 | 10,511 | 4.2% [-11.2%, 46.0%] | 0.1931 | 42,084 | 11,355 |

For SPJF-E (and every constant/age guard): mean reduction **21.4% [13.2%, 38.2%]**, overall p99 reduction **17.7% [4.3%, 60.1%]**, busy p99 reduction **4.2% [-11.2%, 46.0%]**. The corresponding FCFS-to-SJF gaps closed are 0.576 [0.447, 0.759], 0.497 [0.219, 0.902], and 0.193 [-0.865, 0.859]. Gap closed is not percentage wait reduction. SJF is an oracle comparator, not a general p99 optimum. Maximum excess is 42,084 s; harm is 11,355 s, defined over FCFS waits <=1 s.

Intervals use 2,000 paired bootstrap resamples of the same 17 arrival-week blocks (seed 20260921), with the same week multiplicities for both physical pools and every policy. Quantiles are recomputed from the expanded empirical distribution, not averaged across weekly quantiles. They condition on the fitted capacity, model and trace and do not cover model-selection, capacity or structural error, job dependence across weeks, or counterfactual feedback. In 1/2,000 draws FCFS p99 is zero; in 8/2,000 busy draws the FCFS-to-SJF denominator is nonpositive. Undefined quantities remain missing: p99-reduction intervals use 1,999 draws, mean-reduction intervals use all 2,000, and busy gap intervals use 1,992. The conditional gap interval is especially unstable. All per-pool intervals are in `policy_metrics.csv`.

Every job was checked against the imported additive/multiplicative bound: **1,855,998 job-policy checks, 1,051,290 on test jobs, zero violations**. Worst positive excess/allowed excess = **0.046389**. The instance-dependent check uses Bmax/k + Lambda(start) + (2-2/k)Lambda(arrival), and the corresponding age-relative bound, with Lambda(t)=max capped service among arrivals by t: zero violations, worst ratio **0.046389**. Identity-residual checks also pass. Prefix maxima already reach the global cap before the scored period, so the instance version adds no useful tightening.

All six constant/age guards fire **zero times**, and their per-job waits equal SPJF-E. This is why a small worst-bound ratio is not evidence of an effective safeguard here. The theorem floor is 768,343–771,354 s (about 8.9 days), compared with overall FCFS p99 11,376.55 s (0.04389L) and busy p99 10,969.34 s (0.04232L). Condition 1 fails even though pooled cost concentration satisfies condition 2. Using the test queue’s 900-second L would falsely shrink the theorem constant while longer queues share its machines.

## 5. What a referee should accept or reject

The strongest objections are substantive: (i) held-out wait profiles are poorly reproduced, so policy benefits remain conditional simulations; (ii) heterogeneous queue limits make the guarantee operationally uninformative; (iii) grid bags, remote assignment, polling and incomplete middleware state influence both arrivals and waits; (iv) completion-history feedback is frozen and demonstrably inconsistent for 2.49% of test arrivals; and (v) this is one 2004–2005 Pentium-IV grid site, not a modern judging or cloud deployment. The pooled tail also partly reflects mixing queues with different limits. Neither bootstrap intervals nor serial-job status remove these problems.

**Exact sentences supported for the paper:**

> “The public LPC-EGEE trace supplies recorded queue waits and concentrated execution costs together: after a prespecified outage exclusion and documented queue-limit capping, the longest 1% of 206,222 jobs accounts for 40.7% of executed work.”

> “An FCFS approximation with effective capacities fitted on the first chronological part underestimates held-out mean waits by 24% and 39% on the two physical partitions, with hourly correlations of 0.44 and 0.40; we therefore treat policy replays on this trace as conditional counterfactuals rather than validated estimates of deployment benefit.”

> “On those held-out counterfactuals, SPJF-E reduces mean wait by 21.4% [13.2%, 38.2%], while its 4.2% reduction in busy-hour p99 is unresolved [−11.2%, 46.0%]; at promises of 3.5, 5 and 10 times the 259,200-second pool limit, neither constant nor age-relative work-budget guards intervene.”

**Candidate Table `tab:cross` row (all values from the held-out part):**

```latex
LPC-EGEE, held-out FCFS counterfactual (83+56 disjoint servers) & 0.351 & 0.892 & 0.042 & no & 0.193 & 0.162L & 0.193 / 0.162L \\
```

Required footnote: “LPC-EGEE pools remain disjoint; capacities are fitted on the earlier part, and full held-out wait-profile validation is weak. L is the largest queue limit; the p99 and gaps use frozen-threshold busy hours, not deadlines. History features use recorded completion times. The work-budget guard never fires. Thus this row is a conditional replay and not evidence of real-scheduler improvement.” Tail share 0.351 is held-out, not the all-period 0.407 headline.

**Not supported:** a claim that this completes end-to-end real-queue validation; a causal reduction of recorded Maui waits; a statistically resolved busy-p99 benefit; a useful guard/benefit trade-off; superiority of expected over log scores; per-queue 900-second guarantees in the shared physical pool; heavy-tail power-law claims; or generalisation to modern production systems.

Reproduction: [README.md](README.md). Data provenance and hashes: `download.json`, `manifest.json`. All writes are confined to this git-excluded directory; no project datasets were read, and no paper/code/configuration files were changed.

Measured computation across all completed script invocations (including the interrupted run’s initial audit and this run’s correction): **31.03 wall seconds, 42.16 process CPU seconds**. This excludes interpreter/import/startup overhead, the earlier download, and reading/writing review time. No timing for unrecorded work is inferred. One computational process at a time, at most four threads.
