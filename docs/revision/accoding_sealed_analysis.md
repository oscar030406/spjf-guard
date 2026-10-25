# ACcoding sealed segment: analysis of the frozen run of 2026-10-03

This note answers five questions about the sealed ACcoding evaluation for the round-1 revision.
ACcoding is the paper's second grading platform. Its sealed part is the last block of submission
ids, which was held back until the method was frozen. Reviewer 1 asks whether the results
generalize across platforms. Reviewer 3 notes that the main numbers rest on one constructed queue
from one grading platform.

To write this note, I read code, logs and output CSVs that are already on disk. I ran no
experiment and read no sealed submission rows. Paths are relative to the repository root. Times
are local (UTC-4) unless they are marked UTC.

Source abbreviations:

- `S/` is `outputs/accoding_heldout_sealed_online_v2/`, the sealed run of 2026-10-03.
- `D/` is `outputs/accoding_heldout_devtest_online_fast/`, the rehearsal of the same frozen code on the dev-test block. That block is the last block of development data before the sealed block.
- `S1/` is `outputs/accoding_heldout_sealed_online/`, the failed first sealed attempt of 2026-10-02.
- "col" names a CSV column. Every table names its source file and columns below the table.

## 0. Short answers

**1. k and load.** The config fixes k, the number of servers, at the values chosen on development
data. The harness (`scripts/run_accoding_heldout.py`) refits only the scale of the arrival gaps on
the sealed block. That refit stopped at the upper limit of its search range (scale 10). The busiest
hour then held 2.15 times the target work with poisson arrivals and 1.75 times with
deadline-shaped arrivals. So the realised load, rho_realised, is 1.78 to 2.17 times the target
load, rho_target.

The calendar map turns submission ids into calendar times. The most likely trigger is that this
map is flat over at least 23.2% of the sealed rows (Section 1.3). The frozen rule has no check on
the refit, so the capped refit did not stop the run. The arithmetic itself follows the
specification.

**2. Freeze and access.** A committed protocol lock existed before each of the two reads of the
sealed rows. The lock is the file `protocol_lock_accoding.json`, which records the hashes of the
frozen code, config and input files. The 2026-10-03 run is the second read and the first that
produced tables. Between the reads, the lock changed only for the code that scores jobs on the
online clock. On that clock, the harness scores each job only from results that completed before
the job arrived.

The run passed every gate of the frozen protocol, that is, every check that the protocol requires.
However, no gate checks the load calibration.

**3. Tables.** Section 3 gives the tables of the sealed block and of the dev-test block in the same format.

**4. Per-job check.** In a guarded run, a guard bounds how much longer each job waits than under
first-come first-served (FCFS). The harness checked that bound for every job of every guarded run:
180 runs of 807,171 jobs, which is 145,290,780 checks. It found 0 violations.

**5. Reading.** Section 5 gives the plain reading in one paragraph.

## 1. How the harness sets k and the load

### 1.1 The rule in the code

The harness sets two quantities separately: the number of servers k and the spacing of arrivals.

1. The precheck is the project's exploratory script for ACcoding. It sets a target of 14,400 s of work in the busiest clock hour (`prechecks/accoding_v2/accoding_v2.py:77`).
2. On the dev-test block, the precheck fits the scale of the arrival gaps to this target (`accoding_v2.py:1462-1467`).
3. It then sets k = round(work / 3600 / rho) and gets k = 8, 5, 4 for the three loads (`accoding_v2.py:1468`).
4. The frozen config fixes these pairs of load and k. It states that the harness never refits k on an evaluated block (`configs/accoding_heldout_20260928.yaml:47-48`). An evaluated block is the dev-test block or the sealed block.
5. Under the config, the harness refits only the gap scale on each evaluated block. It refits the scale for each arrival shape, poisson or deadline, with seed 300 and the range [1e-7, 10] (`configs/accoding_heldout_20260928.yaml:44-46`).
6. The harness does this refit in `scheduling()` (`scripts/run_accoding_heldout.py:631-646`) with the precheck function `calib_scale` (`accoding_v2.py:1395-1405`).
7. An episode is either the rows of one contest or one chunk of practice rows outside contests. The scale multiplies only the start times of the episodes, and each episode keeps the real length of its window (`apply_scale`, `accoding_v2.py:1353-1359`).
8. For each seed, the harness computes rho_realised = busiest-hour work / 3600 / k on that seed's trace (`run_accoding_heldout.py:648-650, 664`).

Thus k and the work target come from development data. The gap scale and rho_realised come from
the sealed block's own trace.

### 1.2 What the refit did on each block

| Block | Shape | Fitted scale | Busiest-hour work, seed 300 (s) | Work / 14,400 s | rho_realised / rho_target, 5-seed mean |
|---|---|---|---|---|---|
| dev-test | poisson | 0.01489 | 14,394.1 | 1.000 | 0.991 |
| dev-test | deadline | 0.01486 | 14,399.7 | 1.000 | 1.006 |
| sealed | poisson | 10 (range limit) | 30,922.3 | 2.147 | 2.167 |
| sealed | deadline | 10 (range limit) | 25,263.4 | 1.754 | 1.775 |

Sources: `D/trace_calibration.csv` and `S/trace_calibration.csv`, rows with anchor_rule
rows_to_block_end, cols scale and calibration_busy_work_s. `D/summary.csv` and `S/summary.csv`, col
rho_realised divided by col rho_target. This ratio is the same at all three loads.

On the sealed block, the search ended at its upper limit. `calib_scale` raises the lower end of
the range while the busiest-hour work exceeds the target (`accoding_v2.py:1401-1402`). So when no
scale up to 10 meets the target, the search converges on 10 and returns 10 without a warning. The
first sealed attempt printed the same calibration line on 2026-10-02 (`S1/run.log:25`).

### 1.3 Why the refit failed on the sealed block

A larger scale moves the episode starts further apart. However, it cannot separate jobs whose
episodes start at the same instant, because equal starts stay equal after the multiplication. The
sealed block contains a large range of ids that the calendar map sends to one instant:

- An anchor pairs the first id of a contest with a calendar time. `S/anchors.csv` ends with 15 anchors whose first ids run from 3,867,807 to 4,035,394. All 15 have calendar_s 1,637,868,600, which is the stored start_time 2021-11-25 19:30.
- The map keeps a running maximum of contest start times (`run_accoding_heldout.py:316`).
- The 14 contests after id 3,867,807 have start times no later than that maximum, so the map stays flat.
- `np.interp` gives every id after 4,035,394 the same last value (`accoding_v2.py:1312, 1323-1324`).
- `data/accoding/parquet/contests.parquet` has no contest that starts after 2021-11-27 19:00 (col start_time, maximum).
- The harness asserts that the ids in the sealed block are unique and increasing (`run_accoding_heldout.py:262`).
- Ids 3,246,174 to 3,867,806 can hold at most 621,633 rows.
- So at least 187,697 of the 809,330 sealed rows (23.2%) have ids in the flat range.

`build_trace` turns part of this range into a burst (`accoding_v2.py:1311-1325`):

- Each contest whose first id in the block falls in the flat range starts at the same instant and keeps its real window.
- Each practice chunk inside the flat range gets t1 - t0 = 0, and thus the minimum window of 600 s, at that instant.
- If a contest opened earlier in the block, its rows do not join the burst, because its episode starts at an earlier anchor.

The dev-test block has no such range. Its widest flat run of anchors spans 5,453 ids
(`D/anchors.csv`), and the refit met the target there. I did not measure how much of the 30,922 s
of busiest-hour work comes from the burst. That count needs the sealed rows. It would therefore
mean a new access, which would have to be logged.

Heavier jobs add to the effect, but they cannot cause it alone:

- Mean service time is 1.061 s on the sealed block and 0.795 s on dev-test (`tail_shares.csv`, cost_kind service, col mean_s).
- The top 1% of jobs carry 0.187 of the work on the sealed block and 0.118 on dev-test (same rows, col top1_share).
- Heavier jobs only raise the scale that meets the target.
- The search range allowed scales up to about 670 times the dev-test scale (10 / 0.0149). So heavier jobs alone cannot push the refit to the limit.

### 1.4 Classification

Three factors combine. The first factor is the likely trigger, and the other two explain why nothing stopped it:

- **Data property.** At least 23.2% of the sealed rows have no calendar anchor, because the contest metadata ends in November 2021.
- **Frozen design choice.** The protocol fixes k at its development values, moves only the episode starts, and caps the scale at 10.
- **Missing check.** `calib_scale` returns the range limit without a warning. No line of the harness and no test compares calibration_busy_work_s with the target.

The harness computes rho_realised as specified and reports it, so the CSVs show the miss openly. A
rerun with a different calibration rule would change the frozen protocol after a sealed read. It
would also be the third read of the sealed rows.

## 2. Freeze order, accesses and gates

### 2.1 Timeline

| Time (UTC-4) | Event | Evidence |
|---|---|---|
| 2026-09-19 | The precheck reads only the sealed row count (809,330) and the first sealed id (3,246,174). | `docs/sealed_access_log.md:10` |
| 2026-10-02 12:40:35 | Commit a8a27f1 adds lock 1, frozen at 44fb137, after 29 tests and an online-clock rehearsal on the dev-test block. | commit a8a27f1 |
| 2026-10-02, up to 13:04:23 | The first sealed attempt reads the sealed rows, fits the predictors, writes anchors.csv and prints the first calibration. | `S1/` file times, `S1/run.log` |
| 2026-10-02, after 13:04 | The first attempt stops with `AssertionError: SPJF-E: no online fixed point in 200 iterations`. It writes no table. | `docs/sealed_access_log.md:92` |
| 2026-10-02 | The local job queue retries the attempt. The retry stops with `FileExistsError` at `run_accoding_heldout.py:853-854`, before `evaluate()` at line 859 reads data. | `docs/sealed_access_log.md:93`, `outputs/HANDOFF_log_2026-10-01.md:406` |
| 2026-10-02 14:39:31 | Commit b500fcd adds the rows of both attempts to the ledger of sealed reads. | commit b500fcd |
| 2026-10-03 00:32:40 | The harness now computes the online-clock scores in one causal pass. The fixed-point loop starts from these scores and reschedules and rescores until they stop changing. | commit 453e3b0 |
| 2026-10-03 01:04:44 | The one-pass scores use single-row LightGBM scoring. | commit 084399c |
| 2026-10-03 07:26 | The rehearsal of the new code on the dev-test block ends. | `D/` file times |
| 2026-10-03 07:32:15 | Commit b101bd4 removes lock 1 and states the reason. | commit b101bd4 |
| 2026-10-03 07:32:50 | Commit 78da399 adds lock 2, frozen at b101bd4, with 52 files and 36 tests. | commit 78da399 |
| 2026-10-03 07:33:26 | The second sealed read starts. | `outputs/accoding_sealed_online_v2.log:1` |
| 2026-10-03 11:32:03 | The run ends with exit 0 after "Completed all cells and per-job assertions". | `outputs/accoding_sealed_online_v2.log`, `S/run.log` |
| 2026-10-03 11:33:09 | Commit 71e7f00 adds the ledger row. It calls the run the "second access to the ACcoding sealed block". | commit 71e7f00, `docs/sealed_access_log.md:94` |

The ledger in `docs/sealed_access_log.md` holds four ACcoding rows. The first row records a read
that only counted rows. The second and third rows belong to the failed attempt and its retry. The
fourth row belongs to this run. Only the failed attempt and this run read sealed rows. The handoff
note at `HANDOFF.md:235` asks that the paper call this run the second access.

The lock changed between the two reads. The change touched only the scoring on the online clock:

- `scripts/accoding_online.py` is new in lock 2 (sha256 0134999128fe...).
- `scripts/run_accoding_heldout.py` changed from 33e6e8e411a7... to 60d6d57e4f3e....
- `tests/test_accoding_heldout.py` changed from 9bcb0b6d0875... to a06e8bcb2173....
- Both locks hold the same config values, guard parameters, runtime versions and output list.

I read lock 1 with `git show a8a27f1:protocol_lock_accoding.json` and compared the two locks key
by key. The new rehearsal `D/` equals the lock-1 rehearsal `outputs/accoding_heldout_devtest_online/`
in all 9 CSVs and every column, except online_iterations. That column counts the rounds of the
fixed-point loop. It is 1 in `D/` and 3 to 57 in the lock-1 rehearsal.

The first attempt printed the predictor scores on the sealed rows and the capped calibration
(`S1/run.log:5-25`). The first 25 lines of `S1/run.log` equal `S/run.log:1-25`, apart from
elapsed seconds. On 2026-10-02, the operator recorded "scale 10" and "30,922 s" in a note
(`outputs/HANDOFF_log_2026-10-01.md:406`). The trace rules did not change after that note.

### 2.2 Lock and manifest hashes

| Item | Value | Source |
|---|---|---|
| Lock 2 file | a226ea5ab9ae383c0ec2286e613b7e62dc61c5d06052d4d61e8aa7afb21a7cab | sha256 of `protocol_lock_accoding.json` on disk, of the blob in 78da399, and in `S/manifest.json` inputs |
| Lock 2 commit field | b101bd43a762daca6a06afa75248208ab443ef03 | `protocol_lock_accoding.json`, key commit |
| Lock 1 commit field | 44fb13731864a5b09e7e04f769c895e49bc3e5e6 | lock 1, key commit |
| Harness | 60d6d57e4f3e1a76b2e65cfa10e01140b870d6b5b11ba3a09cd9d00820c8ad0b | lock 2 key sha256, equal in `S/manifest.json` |
| Online scorer | 0134999128fecdfffb8f945632421f9569ce1741f0d031abafc2dc1b629aba74 | same |
| Config | bbf8c74daa59da41c32fec17e2ed4fc88b9a2358d8a72879d3cd5113930eae68 | same |
| Precheck | 06e0e350c5fc230fd57acec39302fbcd09cb1fa7c78a7f6334692b158c2e2af4 | same |
| Tests | a06e8bcb21739e85b343c13b4cd3aeaadfadaee571eddab07d946654d2c6dba4 | same |
| Guard parameters (`outputs/selection_v4/selected_parameters.csv`) | 060a6b59b15c2fe1a43c175478d79973547274595d23b9646732ea3af5bea83a | same |
| Development rows fingerprint | 320f5772c58d800dca849ccebc306441063c7b0f842ca52f675c8d87fddfde68 | `S/manifest.json`, notes.development_filtered_sha256 |
| Sealed rows fingerprint | 3e4d639ae1885249b69ccb0dc07398033dcb9b853cbb81c6ce0b6cfb2ce14450 | `S/manifest.json`, notes.evaluated_filtered_sha256 |

All 52 file hashes in lock 2 equal the input hashes that the two runs wrote to their manifests, `S/manifest.json` and `D/manifest.json`.

### 2.3 Gates and results

| Gate | Code | Result |
|---|---|---|
| Clean tree, tests pass, no file change during the tests | `scripts/freeze_accoding.py:18-34, 69-76` | Passed. Lock 2 exists, and commit 78da399 reports 36 tests. |
| Rehearsal: online_iterations = 1 in every online row | `HANDOFF.md:235` | Passed. 120 of 120 rows, `D/metrics.csv`. |
| Rehearsal: every other column equals the lock-1 rehearsal | `HANDOFF.md:235` | Passed. 9 of 9 CSVs (my comparison). |
| Rehearsal: precheck numbers reproduced at printed precision | `run_accoding_heldout.py:698-757` | Passed. 18 of 18 rows, `D/reproduction.csv`, col matches_printed_precision. |
| Rehearsal: anchors equal the precheck anchors | `run_accoding_heldout.py:319-337` | Passed. `D/anchor_comparison.csv`, anchor_arrays_equal True, 0 jobs moved. |
| Lock check before the read: status, config, 52 hashes, versions, parameters, outputs | `run_accoding_heldout.py:198-226` | Passed. The run read data. |
| Sealed block: first id, increasing ids, row count | `run_accoding_heldout.py:261-264` | Passed. |
| Heavy threshold equals the development value of 1,314 ms | `run_accoding_heldout.py:347` | Passed. `S/run.log:4`. |
| Online fixed point within 200 iterations | `run_accoding_heldout.py:551-562` | Passed. online_iterations = 1 in 120 of 120 rows, `S/metrics.csv`. |
| Per-job guard bound | `run_accoding_heldout.py:503-510, 583-587` | Passed. 145,290,780 checks (Section 4). |
| Output list equals the lock list | `run_accoding_heldout.py:843-848, 888, 904` | Passed. 8 files. |

No gate compares calibration_busy_work_s with the 14,400 s target. Section 1 shows the effect.

## 3. Results tables

### 3.1 Definitions

- Both runs use one anchor rule, rows_to_block_end. Under it, each contest's anchor is its first id among all rows up to the end of the evaluated block. On the dev-test block, the precheck anchors give the same numbers as these anchors (`D/precheck_reference_summary.csv`, FCFS, SJF and SPJF-E rows).
- p99 is the 99th percentile of the waiting time over all evaluated jobs, with no deadline window (config line 74). The harness drops p99_dl, the p99 inside the deadline window (`run_accoding_heldout.py:469`).
- Each table value is the mean over the arrival seeds 300 to 304 (`run_accoding_heldout.py:685`).
- Gap closed is (FCFS - policy) / (FCFS - SJF) on the 5-seed means (`run_accoding_heldout.py:460-462, 688-694`). SJF orders jobs by their true service times. The value n/d means FCFS = SJF, so the gap is not defined.
- Max excess is the largest W_policy - W_FCFS over all jobs and all 5 seeds, where W is a job's waiting time (`run_accoding_heldout.py:466, 473, 686`).
- The bound is G_acc = G x 30.5 / 60, col promise_acc_s (`run_accoding_heldout.py:513-517`). Here 30.5 / 60 is the limit L used for ACcoding divided by that used for CodeBench, the platform of the paper's main experiment. Section 4 shows that G_acc is the per-job bound for every job here.
- On the online clock, the harness computes a job's features only from results that completed before the job arrived (config line 89). On the original clock, it uses the recorded results of all submissions with smaller ids.
- Note of 2026-10-26: the harness labels this policy SPJF-E, but its score is the log1p model of `run_accoding_heldout.py:358`. The paper therefore calls it SPJF-log.
- SPJF-E orders jobs by the predictor's score and has no guard. Guard(G) adds the guard to SPJF-E and takes its parameters for G from CodeBench. The harness scales G and the guard's parameters b0 and gamma by 30.5 / 60. It also scales b0 and gamma by k / 4 (`run_accoding_heldout.py:279-291`).

### 3.2 Compact comparison for the paper (online clock)

The table uses the online clock, as the paper's sealed CodeBench result does. FCFS has no online
variant.

| Shape | rho target | k | rho realized, dev / sealed | FCFS p99 s, dev / sealed | SPJF-E gap, dev / sealed | Guard(600) gap, dev / sealed | Guard(600) max excess s (bound 305), dev / sealed |
|---|---|---|---|---|---|---|---|
| poisson | 0.5 | 8 | 0.496 / 1.084 | 0 / 2,470.5 | n/d / -1.026 | n/d / -0.172 | 8.3 / 236.6 |
| poisson | 0.8 | 5 | 0.793 / 1.734 | 1.53 / 7,813.1 | 0.983 / -2.297 | 0.983 / -0.070 | 201.0 / 251.4 |
| poisson | 1 | 4 | 0.991 / 2.167 | 44.38 / 11,444.4 | 0.995 / -0.871 | 0.979 / -0.021 | 237.7 / 251.3 |
| deadline | 0.5 | 8 | 0.503 / 0.888 | 0 / 1,776.4 | n/d / 0.022 | n/d / -0.086 | 7.7 / 238.8 |
| deadline | 0.8 | 5 | 0.804 / 1.420 | 3.27 / 6,395.5 | 0.989 / -0.909 | 0.982 / -0.001 | 233.5 / 254.7 |
| deadline | 1 | 4 | 1.006 / 1.775 | 71.57 / 9,722.4 | 0.993 / -1.216 | 0.970 / 0.009 | 239.0 / 257.2 |

Sources: `D/summary.csv` and `S/summary.csv`. The SPJF-E and Guard(600) rows are those whose col
score_definition ends with the word online. Cols k, rho_realised, p99, gap_closed_p99 and
max_excess_s. Bound from col promise_acc_s. Bound violations: 0 in both runs (Section 4).

### 3.3 Sealed block, original clock

n jobs = 807,171 in every cell. Values in brackets are gap closed at the p99.

| Shape | rho target | k | rho realized: mean (min-max) | n jobs | FCFS p99 s | SJF p99 s | SPJF-E p99 s [gap] | Guard(300) p99 s [gap] | Guard(600) p99 s [gap] | Guard(1200) p99 s [gap] |
|---|---|---|---|---|---|---|---|---|---|---|
| poisson | 0.5 | 8 | 1.084 (1.074-1.091) | 807,171 | 2,470.5 | 1,630.8 | 2,546.2 [-0.090] | 2,516.8 [-0.055] | 2,613.2 [-0.170] | 2,838.2 [-0.438] |
| poisson | 0.8 | 5 | 1.734 (1.718-1.746) | 807,171 | 7,813.1 | 7,085.1 | 8,604.4 [-1.087] | 7,842.8 [-0.041] | 7,863.7 [-0.069] | 7,907.7 [-0.130] |
| poisson | 1 | 4 | 2.167 (2.147-2.182) | 807,171 | 11,444.4 | 9,494.7 | 11,533.0 [-0.045] | 11,483.8 [-0.020] | 11,510.9 [-0.034] | 11,546.5 [-0.052] |
| deadline | 0.5 | 8 | 0.888 (0.877-0.906) | 807,171 | 1,776.4 | 815.2 | 1,246.3 [0.551] | 1,796.3 [-0.021] | 1,854.8 [-0.082] | 1,976.6 [-0.208] |
| deadline | 0.8 | 5 | 1.420 (1.404-1.450) | 807,171 | 6,395.5 | 4,386.7 | 7,742.1 [-0.670] | 6,381.0 [0.007] | 6,379.8 [0.008] | 6,359.5 [0.018] |
| deadline | 1 | 4 | 1.775 (1.754-1.813) | 807,171 | 9,722.4 | 8,610.0 | 10,344.4 [-0.559] | 9,714.3 [0.007] | 9,704.5 [0.016] | 9,690.3 [0.029] |

Sources: `S/summary.csv`, rows whose col score_definition does not end with online. Cols k,
rho_realised, n_jobs, p99 and gap_closed_p99. The min-max range comes from `S/metrics.csv`, col
rho_realised over the 5 seeds.

### 3.4 Sealed block, online clock

FCFS and SJF read no score, so their rows in 3.3 also serve the online clock.

| Shape | rho target | k | rho realized: mean (min-max) | n jobs | SPJF-E p99 s [gap] | Guard(300) p99 s [gap] | Guard(600) p99 s [gap] | Guard(1200) p99 s [gap] | online iterations (max) |
|---|---|---|---|---|---|---|---|---|---|
| poisson | 0.5 | 8 | 1.084 (1.074-1.091) | 807,171 | 3,332.0 [-1.026] | 2,516.7 [-0.055] | 2,614.9 [-0.172] | 2,843.5 [-0.444] | 1 |
| poisson | 0.8 | 5 | 1.734 (1.718-1.746) | 807,171 | 9,485.7 [-2.297] | 7,835.7 [-0.031] | 7,863.9 [-0.070] | 7,926.8 [-0.156] | 1 |
| poisson | 1 | 4 | 2.167 (2.147-2.182) | 807,171 | 13,142.9 [-0.871] | 11,475.9 [-0.016] | 11,486.3 [-0.021] | 11,580.0 [-0.070] | 1 |
| deadline | 0.5 | 8 | 0.888 (0.877-0.906) | 807,171 | 1,754.7 [0.022] | 1,797.8 [-0.022] | 1,858.8 [-0.086] | 1,991.5 [-0.224] | 1 |
| deadline | 0.8 | 5 | 1.420 (1.404-1.450) | 807,171 | 8,221.4 [-0.909] | 6,385.9 [0.005] | 6,397.1 [-0.001] | 6,397.5 [-0.001] | 1 |
| deadline | 1 | 4 | 1.775 (1.754-1.813) | 807,171 | 11,075.2 [-1.216] | 9,723.2 [-0.001] | 9,712.8 [0.009] | 9,741.3 [-0.017] | 1 |

Sources: `S/summary.csv`, rows whose col score_definition ends with online. Cols p99 and
gap_closed_p99. The last col is the maximum of col online_iterations in `S/metrics.csv`.

### 3.5 Sealed block, guarantee

Each cell gives the max excess over FCFS for the original clock, then the online clock.

| Shape | rho target | k | Guard(300): max excess s, original / online (bound 152.5 s) | Guard(600): max excess s, original / online (bound 305 s) | Guard(1200): max excess s, original / online (bound 610 s) | jobs checked | violations |
|---|---|---|---|---|---|---|---|
| poisson | 0.5 | 8 | 79.5 / 82.9 | 233.4 / 236.6 | 545.1 / 543.9 | 24,215,130 (30 runs x 807,171) | 0 |
| poisson | 0.8 | 5 | 91.9 / 97.5 | 247.9 / 251.4 | 550.9 / 550.1 | 24,215,130 (30 runs x 807,171) | 0 |
| poisson | 1 | 4 | 98.3 / 94.1 | 249.6 / 251.3 | 561.1 / 557.0 | 24,215,130 (30 runs x 807,171) | 0 |
| deadline | 0.5 | 8 | 82.0 / 84.2 | 238.1 / 238.8 | 537.2 / 538.9 | 24,215,130 (30 runs x 807,171) | 0 |
| deadline | 0.8 | 5 | 95.3 / 95.1 | 247.3 / 254.7 | 553.1 / 558.8 | 24,215,130 (30 runs x 807,171) | 0 |
| deadline | 1 | 4 | 104.9 / 101.7 | 255.8 / 257.2 | 561.5 / 561.1 | 24,215,130 (30 runs x 807,171) | 0 |

Total jobs checked: 145,290,780. Sources: `S/summary.csv`, cols max_excess_s and promise_acc_s.
`S/metrics.csv`, col bounds_checked summed over the 30 guarded runs of each row. Violations: 0,
because any violation stops the run (Section 4).

### 3.6 Dev-test block, original clock

| Shape | rho target | k | rho realized: mean (min-max) | n jobs | FCFS p99 s | SJF p99 s | SPJF-E p99 s [gap] | Guard(300) p99 s [gap] | Guard(600) p99 s [gap] | Guard(1200) p99 s [gap] |
|---|---|---|---|---|---|---|---|---|---|---|
| poisson | 0.5 | 8 | 0.496 (0.490-0.501) | 647,465 | 0 | 0 | 0 [n/d] | 0 [n/d] | 0 [n/d] | 0 [n/d] |
| poisson | 0.8 | 5 | 0.793 (0.784-0.801) | 647,465 | 1.53 | 0.623 | 0.641 [0.980] | 0.657 [0.963] | 0.640 [0.981] | 0.645 [0.975] |
| poisson | 1 | 4 | 0.991 (0.980-1.002) | 647,465 | 44.38 | 2.41 | 2.60 [0.996] | 8.08 [0.865] | 3.20 [0.981] | 3.16 [0.982] |
| deadline | 0.5 | 8 | 0.503 (0.500-0.509) | 647,465 | 0 | 0 | 0 [n/d] | 0 [n/d] | 0 [n/d] | 0 [n/d] |
| deadline | 0.8 | 5 | 0.804 (0.800-0.814) | 647,465 | 3.27 | 0.763 | 0.785 [0.991] | 0.916 [0.939] | 0.808 [0.982] | 0.815 [0.979] |
| deadline | 1 | 4 | 1.006 (1.000-1.017) | 647,465 | 71.57 | 2.78 | 3.19 [0.994] | 20.81 [0.738] | 4.77 [0.971] | 4.24 [0.979] |

Sources: `D/summary.csv`, same rows and cols as 3.3. The range comes from `D/metrics.csv`, col
rho_realised. The older run `outputs/accoding_heldout_devtest/`
dates from 2026-09-27. Its original-clock rows equal these rows in cols p99, mean, rho_realised,
gap_closed_p99 and max_excess_s.

### 3.7 Dev-test block, online clock

| Shape | rho target | k | rho realized: mean (min-max) | n jobs | SPJF-E p99 s [gap] | Guard(300) p99 s [gap] | Guard(600) p99 s [gap] | Guard(1200) p99 s [gap] | online iterations (max) |
|---|---|---|---|---|---|---|---|---|---|
| poisson | 0.5 | 8 | 0.496 (0.490-0.501) | 647,465 | 0 [n/d] | 0 [n/d] | 0 [n/d] | 0 [n/d] | 1 |
| poisson | 0.8 | 5 | 0.793 (0.784-0.801) | 647,465 | 0.638 [0.983] | 0.652 [0.968] | 0.638 [0.983] | 0.643 [0.978] | 1 |
| poisson | 1 | 4 | 0.991 (0.980-1.002) | 647,465 | 2.63 [0.995] | 8.17 [0.863] | 3.28 [0.979] | 3.21 [0.981] | 1 |
| deadline | 0.5 | 8 | 0.503 (0.500-0.509) | 647,465 | 0 [n/d] | 0 [n/d] | 0 [n/d] | 0 [n/d] | 1 |
| deadline | 0.8 | 5 | 0.804 (0.800-0.814) | 647,465 | 0.789 [0.989] | 0.913 [0.940] | 0.809 [0.982] | 0.814 [0.979] | 1 |
| deadline | 1 | 4 | 1.006 (1.000-1.017) | 647,465 | 3.23 [0.993] | 21.91 [0.722] | 4.87 [0.970] | 4.33 [0.977] | 1 |

Sources: `D/summary.csv` and `D/metrics.csv`, same rows and cols as 3.4.

### 3.8 Dev-test block, guarantee

| Shape | rho target | k | Guard(300): max excess s, original / online (bound 152.5 s) | Guard(600): max excess s, original / online (bound 305 s) | Guard(1200): max excess s, original / online (bound 610 s) | jobs checked | violations |
|---|---|---|---|---|---|---|---|
| poisson | 0.5 | 8 | 6.6 / 8.3 | 6.6 / 8.3 | 6.6 / 8.3 | 19,423,950 (30 runs x 647,465) | 0 |
| poisson | 0.8 | 5 | 61.7 / 61.1 | 201.9 / 201.0 | 164.4 / 164.3 | 19,423,950 (30 runs x 647,465) | 0 |
| poisson | 1 | 4 | 83.7 / 84.5 | 237.3 / 237.7 | 543.0 / 543.6 | 19,423,950 (30 runs x 647,465) | 0 |
| deadline | 0.5 | 8 | 8.5 / 7.7 | 8.5 / 7.7 | 8.5 / 7.7 | 19,423,950 (30 runs x 647,465) | 0 |
| deadline | 0.8 | 5 | 80.6 / 81.1 | 232.5 / 233.5 | 342.8 / 349.0 | 19,423,950 (30 runs x 647,465) | 0 |
| deadline | 1 | 4 | 85.4 / 89.0 | 238.0 / 239.0 | 547.4 / 543.8 | 19,423,950 (30 runs x 647,465) | 0 |

Total jobs checked: 116,543,700. Sources: `D/summary.csv` and `D/metrics.csv`, same cols as 3.5.
At rho 0.5 the guards never fire, that is, they never override the order of SPJF-E. So all three guards equal SPJF-E.

### 3.9 Other numbers used in this note

| Quantity | Sealed | Dev-test | Source |
|---|---|---|---|
| M4 ensemble AUROC, all jobs | 0.936 | 0.927 | `predictor_metrics.csv`, model M4, seed ensemble, group all, col auroc |
| M4 ensemble AP, all jobs | 0.685 | 0.527 | same row, col ap |
| M4 ensemble RMSE of log1p(s) | 0.317 | 0.271 | same row, col rmse_log1p_s |
| Mean service time (s) | 1.061 | 0.795 | `tail_shares.csv`, cost_kind service, col mean_s |
| Work share of the top 1% of jobs | 0.187 | 0.118 | same row, col top1_share |
| Guard(600) fired fraction, both clocks | 0.067 to 0.101 | 0 to 0.0024 | `summary.csv`, col fired_fraction |
| All guards fired fraction, both clocks | 0.044 to 0.112 | 0 to 0.0080 | same col |
| SPJF-E gap closed in mean wait, original / online | 0.798 to 0.872 / 0.619 to 0.727 | 0.766 to 0.892 / 0.772 to 0.900 | `summary.csv`, col gap_closed_mean |
| Guard(600) gap closed in mean wait, original / online | 0.057 to 0.154 / 0.052 to 0.144 | 0.580 to 0.868 / 0.564 to 0.860 | same col |
| SPJF-E max excess over FCFS (s), original clock | 8,954.0 to 23,717.5 | 6.6 to 2,175.9 | `summary.csv`, col max_excess_s |
| FCFS p99 / L, L = 30.5 s | 58.2 to 375.2 | 0 to 2.35 | `summary.csv`, col p99 of FCFS rows, divided by 30.5 |

## 4. Per-job guarantee check

The check covered every job of every guarded run on the sealed block, and it found no violation:

- The harness checks the guard bound for each job, inside the run, on both clocks (`run_accoding_heldout.py:503-510` and `583-587`).
- `assert_per_job_bounds` computes each job's bound from the same job's FCFS wait in the same trace (`src/spjf_guard/sim/bounds.py:166-213`).
- It compares values from integer microseconds with zero tolerance, and any violation raises `AssertionError` (`bounds.py:214-221`).
- There are 180 guarded runs: 3 guards, 3 loads, 2 shapes, 5 seeds and 2 clocks.
- In each of the 180 rows, bounds_checked equals n_jobs = 807,171 (`S/metrics.csv`).
- The sum is 145,290,780, equal to notes.bound_job_checks in `S/manifest.json`.
- The run ended with exit 0 after "Completed all cells and per-job assertions" (`outputs/accoding_sealed_online_v2.log`).

For these parameters, the binding bound is W_FCFS + G_acc for every job. Guard(1200) has a
term that grows with the queue length, so only the additive form applies (`bounds.py:188-193`). For Guard(300) and
Guard(600), the multiplicative form exceeds the additive form by at least 15.25 s for every job.
So max_excess_s at or below promise_acc_s restates the per-job check. The largest ratios of max
excess to bound are 0.688 for Guard(300), 0.843 for Guard(600) and 0.921 for Guard(1200).

The check is not trivial, because the guards overrode the base order on 4.4% to 11.2% of
dispatches (Section 3.9). The rehearsal on the dev-test block has the same coverage: 180 runs of
647,465 jobs, which is 116,543,700 checks, with 0 violations.

## 5. Plain reading

On the sealed ACcoding segment, the guarantee held for every job: 145,290,780 per-job checks found
no violation. Guard(600) used at most 257.2 s of its 305 s bound, although it overrode the base
order on 7% to 10% of dispatches. However, the benefit did not transfer: SPJF-E gave a worse p99 than FCFS in
5 of 6 cells, and Guard(600) stayed near FCFS. These cells did not run at the designed loads, because
the refit of the arrival gaps stopped at the end of its search range. Their busiest hour held 1.78 to 2.17
times the target work, and the FCFS p99 was 1,776 to 11,444 s. The dev-test cells had an FCFS p99 of
at most 72 s, so this run cannot separate a platform effect from overload.

Limits of this reading:

- ACcoding has no recorded arrival times, so both runs draw them at random. The runs thus test ordering on real job sizes, not on real waiting (`paper/sections/09_limitations.tex:67`).
- The guard parameters come from CodeBench and are rescaled to ACcoding, so the guard side is a cross-platform transfer.
- The harness trains the predictor on a 1,000,000-row sample of ACcoding ids 1 to 1,951,042 (`run_accoding_heldout.py:350-354`).
- So the predictor side is a hold-out from a later period of the same platform.
- I did not read the sealed rows. So I can only infer what share of the busiest-hour work comes from the burst in the flat range.
