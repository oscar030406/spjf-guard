# LPC-EGEE audit

The only data input is the cleaned LPC-EGEE SWF log. The 18 columns use the same parser/schema as `evidence/cross_domain/cd_common.py`; that module was read, not imported, because its import creates its own cache. No other dataset was opened.

## Corrections to the interrupted audit

The downloaded bytes, hash, SWF parser, status treatment and raw concurrency calculation were retained. The original audit incorrectly applied outage days to `submit - min(submit)`. The original SWF epoch and the cleaned first arrival differ by **3,585,977 s (41.50 days)**. `diagnose.py` locates the long test-queue waits on raw SWF days 140–150 (not just 140–149 in the hunt). The same prespecified exclusion [138,153) now uses raw `submit` seconds. The incorrect run retained outage jobs and reported test-queue p99 939,596 s; the corrected p99 is 21,496.64 s. The old code and tables remain in `superseded_audit/`; the newest invocation in `out_audit.txt` is authoritative.

The hunt was also too categorical about requested time. It is not always the queue limit: the raw file has missing and nonstandard values. The documented CE2 short limit is 5,400 s, while old/CE1 short is 7,200 s. We use those documented queue limits for capping and retain raw requested time as a predictor. The 1,909 retained request/queue-limit mismatches include missing requests.

## Filter ledger

| filter | before | removed | after |
| --- | --- | --- | --- |
| known status 0/1/5 | 234889 | 0 | 234889 |
| positive runtime | 234889 | 20567 | 214322 |
| nonnegative wait and submit | 214322 | 0 | 214322 |
| one allocated processor | 214322 | 0 | 214322 |
| known queue/partition | 214322 | 0 | 214322 |
| arrival or observed lifetime intersects original SWF outage [138d,153d) | 214322 | 8100 | 206222 |

Raw status counts: {'1': 207825, '5': 16574, '0': 10490}. Retained status counts: {'1': 194797, '0': 9275, '5': 2150}. Failed/cancelled jobs that consumed positive service remain; only jobs without positive service are removed. Zero runtimes: 6,373; negative runtimes: 14,194; negative waits/submits: 0/0. All positive-service jobs allocate exactly one CPU.

The outage removes 8,094 arrivals in [138,153) and 6 additional jobs whose observed submit-to-completion lifetime crosses it, giving 206,222 retained jobs. This is why the total differs from the hunt's approximate 206,430; the exact reproducible count is used throughout. The remaining 741 jobs above the queue cap are **capped, not dropped**, removing 221,139 service seconds. Recorded waits and history availability keep their original values.

## Per-queue distribution over all retained arrivals

All waits and limits are seconds. `L_min/L` show queue-limit variation across partitions. `top1/top5` are capped-runtime work shares; `raw_top1` is uncapped. The longest fraction uses `round(n*fraction)` jobs, matching the existing cross-domain utility.

| queue | n | L_min | L | mean | p50 | p90 | p99 | top1 | top5 | raw_top1 | exceeds |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all | 206222 | 900 | 259200 | 550.2 | 4 | 478 | 11,917.43 | 0.4071 | 0.8354 | 0.4072 | 741 |
| 1 | 41143 | 900 | 900 | 526.3 | 3 | 5 | 21,496.64 | 0.2281 | 0.6649 | 0.2366 | 220 |
| 2 | 69446 | 5400 | 7200 | 308.6 | 4 | 507 | 4,701 | 0.224 | 0.5088 | 0.2279 | 219 |
| 3 | 30602 | 86400 | 86400 | 500.8 | 4 | 55 | 14,211 | 0.2956 | 0.6734 | 0.2969 | 185 |
| 4 | 18594 | 129600 | 129600 | 370.2 | 3 | 61 | 8,382.73 | 0.1602 | 0.5015 | 0.1602 | 61 |
| 5 | 44931 | 259200 | 259200 | 1,066.35 | 4 | 1,094 | 16,426.2 | 0.2089 | 0.5987 | 0.2089 | 55 |
| 6 | 1506 | 3600 | 3600 | 167.4 | 1 | 2 | 2,860.6 | 0.6186 | 0.947 | 0.6191 | 1 |

Queue codes: 1=test, 2=short, 3=long, 4=day, 5=infinite, 6=batch. Per-physical-pool/queue rows are in `queue_audit.csv`; requested-time counts by partition/queue are in `audit.json`.

## Topology, concurrency, utilisation and arrival concentration

The [archive system documentation](https://www.cs.huji.ac.il/labs/parallel/workload/l_lpc/) states two disjoint physical partitions with no load balancing: CE1 has 84 CPUs; old, renamed CE2 on 1 December 2004, has 56. These are the modelling units. The queues share capacity within a partition, and the later queue running-job ceilings are not dedicated sub-pools.

The observed concurrency lower bound is 142 globally, 85 on CE1, 58 on old/CE2, versus documented counts 140/84/56. This small discrepancy is an inconsistency of timestamps/accounting; it does not establish additional physical machines. Occupancy is measured from [submit+wait, submit+wait+raw_run), with completions before starts on ties.

| pool | k | max_concurrency | util_mean | util_p50 | util_p90 | util_max | hour_at_or_above_90pct |
| --- | --- | --- | --- | --- | --- | --- | --- |
| all | 140 | 142 | 0.2275 | 0.089 | 0.6435 | 1 | 0.02422 |
| CE1 | 84 | 85 | 0.2408 | 0.02916 | 0.858 | 1 | 0.07919 |
| old_CE2 | 56 | 58 | 0.2076 | 0.01948 | 0.822 | 1.023 | 0.04211 |

Utilisation summaries above exclude whole hourly bins overlapping the incident; `hourly_cleaned.csv` contains the full time series and an explicit validity flag. `hourly_audit.csv` retains the original pre-exclusion diagnostic. The occupancy column in `utilisation_summary.csv` additionally includes the excluded gap in its denominator and must not be confused with `util_mean`. Utilisation sometimes exceeds one because of the concurrency discrepancy.

Hourly arrival mean is 38.42, maximum 3,148, variance/mean 181.31. Calendar bins use Europe/Paris, including daylight-saving time. Exposure-normalised arrival rates peak at 15:00 versus a trough at 06:00 (2.44x); Tuesday versus Sunday is 2.24x. These are grid submission cycles, not recorded deadlines. `hour_of_day*.csv` and `day_of_week*.csv` contain counts, work and rates.

## Applicability, per queue and pooled

Condition 1 is exactly FCFS p99 > (3-2/k)L, using FCFS replay rather than recorded Maui waits. In a mixed queue physical pool, the theorem must use **L_pool=259,200 s even for a short-queue cohort**. The ratio to the cohort queue limit is also shown but does not certify a separate queue theorem. Every cohort and both physical pools fail the actual condition.

Condition 2 in the paper is qualitative cost concentration, not a formally fixed 25% cutoff or a claim of an unbounded power law. For a reproducible yes/no diagnostic, the table labels the hunt’s approximate 25% top-1% work-share proxy. Pooled, long and batch pass it; test and short are moderately concentrated but below it; day and infinite also fall below it. This proxy must not be presented as a theorem or a statistical tail-law test.

| queue | fcfs_p99 | p99_over_L_queue | p99_over_L_pool | condition1 | top1 | top5 | condition2_proxy_25pct |
| --- | --- | --- | --- | --- | --- | --- | --- |
| all | 10,576.06 | 0.0408 | 0.0408 | False | 0.4071 | 0.8354 | True |
| 1 | 26,385.8 | 29.32 | 0.1018 | False | 0.2281 | 0.6649 | False |
| 2 | 3,733.95 | 0.5186 | 0.01441 | False | 0.224 | 0.5088 | False |
| 3 | 11,067.44 | 0.1281 | 0.0427 | False | 0.2956 | 0.6734 | True |
| 4 | 4,333.28 | 0.03344 | 0.01672 | False | 0.1602 | 0.5015 | False |
| 5 | 15,457.1 | 0.05963 | 0.05963 | False | 0.2089 | 0.5987 | False |
| 6 | 1,637.55 | 0.4549 | 0.006318 | False | 0.6186 | 0.947 | True |

Held-out cohorts (same fitted pools, no capacity refit):

| queue | n | fcfs_p99 | p99_over_L_queue | p99_over_L_pool | condition1 | top1 | condition2_proxy_25pct |
| --- | --- | --- | --- | --- | --- | --- | --- |
| all | 116810 | 11,376.55 | 0.04389 | 0.04389 | False | 0.351 | True |
| 1 | 34707 | 8,405.88 | 9.34 | 0.03243 | False | 0.2134 | False |
| 2 | 19353 | 7,733.36 | 1.074 | 0.02984 | False | 0.2402 | False |
| 3 | 21235 | 17,666 | 0.2045 | 0.06816 | False | 0.274 | True |
| 4 | 18236 | 4,339.6 | 0.03348 | 0.01674 | False | 0.1609 | False |
| 5 | 21773 | 18,371.64 | 0.07088 | 0.07088 | False | 0.1803 | False |
| 6 | 1506 | 1,637.55 | 0.4549 | 0.006318 | False | 0.6186 | True |

Physical-pool totals:

| period | pool | n | fcfs_p99 | p99_over_L_pool | condition1 | top1 | top5 | condition2_proxy_25pct |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all | CE1 | 111236 | 12,768.8 | 0.04926 | False | 0.3727 | 0.7981 | True |
| all | old_CE2 | 94986 | 7,066 | 0.02726 | False | 0.4507 | 0.8834 | True |
| test | CE1 | 66538 | 11,601.41 | 0.04476 | False | 0.3205 | 0.7513 | True |
| test | old_CE2 | 50272 | 10,800.29 | 0.04167 | False | 0.3777 | 0.8451 | True |
