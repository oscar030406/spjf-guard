# Platform test bed: results of the six full runs

2026-09-23. Run on the local machine; nothing was pushed, nothing was deployed, and the live site was not touched.
This file reports the results; the build notes of the test bed are not part of the repository.

- Six cells, 100 jobs each, k = 2, promise G = 400 s, per-job execution limit
  L = 170 s (study plan, "practice guide") / 25 s (learner report, "blueprint"), budget shape B0 = 30 s, η = 0.5, γ = 0.
- 20 test accounts (`loadtest_u001`…`u020`). The sequence of job classes is identical in all six runs
  (the cycle `guide,guide,blueprint×6`), and think times are drawn per seat with the same seed,
  so differences in demand between runs come only from the rule itself and from feedback.
- Total wall-clock time 3 h 27 min; 571 model calls were recorded, **429.5 thousand input + 402.6 thousand output tokens**.
- All records are in `records/`. Summary in `records/summary.json`, simulator comparison in
  `records/simulator_replay.json`, per-dispatch decisions in `records/decisions-full-<cell>.jsonl`.

---

## 1. The six cells

| cell | policy / demand rule | n | ρ | span | mean wait | p90 wait | max excess | excess / G | guard firings | simulator max per-job deviation |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | fcfs / closed loop (ii) | 100 | 1.000 | 1955 s | 308.8 s | 479.4 s | 0.17 s | 0.0004 | 0 | 167.8 ms |
| 2 | spjf / closed loop (ii) | 100 | 0.971 | 2104 s | 227.4 s | 1083.3 s | **1869.9 s** | **4.67** | 0 | 125.3 ms |
| 3 | guard, completed-work charging / closed loop (ii) | 100 | 0.994 | 1777 s | 235.2 s | 680.2 s | 151.7 s | 0.379 | 24 | 138.8 ms |
| 4 | guard, reservation charging / closed loop (ii) | 100 | 0.976 | 1868 s | 206.7 s | 896.8 s | 205.5 s | 0.514 | 20 | not comparable (see §6) |
| 5 | guard, completed-work charging / open loop (i) | 100 | 0.695 | 2753 s | 70.3 s | 177.3 s | 184.0 s | 0.460 | 5 | 115.5 ms |
| 6 | guard, completed-work charging / closed loop (iii) | 100 | 0.993 | 1906 s | 205.7 s | 433.8 s | 184.8 s | 0.462 | 21 | 132.8 ms |

How `excess` is computed: take **this run's own** arrival sequence and **this run's own measured** executed work
`min(C_i, ℓ_i)`, replay first-come first-served offline once, compute `measured wait − replayed wait` for each job, and take the maximum.
Each run's counterfactual is its own, not another run's: under the closed loop the arrival sequences of the runs differ in the first place (§4).

**ρ is measured, not set**: `ρ = Σ min(C_i, ℓ_i) / (k × span)`. The four closed-loop guard/fcfs
runs are all at 0.97–1.00, i.e. the two workers were almost never idle; the open-loop run is at 0.695, below the 0.85
targeted when thinning with E[C] = 41 s, because the measured E[C] was 38.3 s and the tail has to drain.

### Bound check

**Jobs beyond the promise: 0 in each of cells 1 / 3 / 4 / 5 / 6, 7 in cell 2.**

The cell 2 entry is not a failure; it is what this experiment is meant to measure: `spjf` is the base policy without the guard,
and it promises nothing. With the same input and the same k, it made the worst-off job wait
1869.9 s longer than first-come first-served, 4.67 times the promise G. Putting the guard on the same base policy (cell 3) brought the worst-off job down to
151.7 s, 0.379 times G.

## 2. Measured service times

| cell | class | n | median | p90 | max | CV | hit limit | max over limit |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | blueprint | 74 | 6.41 s | 14.47 s | 25.01 s | 0.683 | 6 | 10.3 ms |
| 1 | practice-guide | 26 | 124.54 s | 170.01 s | 170.01 s | 0.216 | 4 | 13.1 ms |
| 2 | blueprint | 74 | 6.24 s | 13.30 s | 18.67 s | 0.493 | 0 | 0 |
| 2 | practice-guide | 26 | 136.36 s | 170.00 s | 170.01 s | 0.225 | 6 | 11.4 ms |
| 3 | blueprint | 74 | 5.63 s | 8.60 s | 25.00 s | 0.511 | 1 | 1.9 ms |
| 3 | practice-guide | 26 | 111.57 s | 170.00 s | 170.01 s | 0.268 | 4 | 13.6 ms |
| 4 | blueprint | 74 | 6.10 s | 7.69 s | 10.73 s | 0.224 | 0 | 0 |
| 4 | practice-guide | 26 | 124.47 s | 151.87 s | 170.01 s | 0.197 | 1 | 6.0 ms |
| 5 | blueprint | 74 | 7.58 s | 10.74 s | 16.10 s | 0.272 | 0 | 0 |
| 5 | practice-guide | 26 | 123.32 s | 168.77 s | 170.02 s | 0.235 | 3 | 16.1 ms |
| 6 | blueprint | 74 | 9.12 s | 14.75 s | 21.37 s | 0.330 | 0 | 0 |
| 6 | practice-guide | 26 | 111.32 s | 170.01 s | 170.01 s | 0.270 | 4 | 14.5 ms |

- **Neither class is heavy-tailed on its own**: the CV of each class is between 0.20 and 0.69. The CV of the mixture of the two classes is above 1,
  but that is **a mixture of two job classes**, and the paper must say it in exactly those terms; it must not say "job durations on the platform are heavy-tailed".
- **The limit is real**: **29 of the 600 jobs reached their own ℓ** (22 study plans, 7 learner reports),
  and the largest amount by which a measured service time exceeded its ℓ is **16.1 ms**. The engine log explicitly records
  "execution limit used up" 26 times; in the other 3 cases the caller's abort and the engine's deadline
  fell due at the same moment, the abort landed first, and the engine did not get to write that line. A slot stays occupied until the executing call actually returns,
  so the executed work of these 29 jobs is ℓ itself, not a number that was merely observed.

## 3. Who pays

| cell | jobs worse off than under first-come first-served | mean extra wait of those jobs | mean wait, study plan | mean wait, learner report | guard firing rate |
|---|---:|---:|---:|---:|---:|
| 1 fcfs | 98 | 0.1 s | 306.5 s | 309.7 s | 0/100 |
| 2 spjf | 20 | **460.2 s** | 788.7 s | 30.2 s | 0/100 |
| 3 guard, completed-work charging | 32 | 57.8 s | 516.0 s | 136.5 s | 24/100 |
| 4 guard, reservation charging | 29 | 102.6 s | 718.2 s | 26.9 s | 20/100 |
| 5 guard, open loop | 23 | 45.4 s | 127.3 s | 50.3 s | 5/100 |
| 6 guard, closed loop (iii) | 29 | 65.3 s | 372.8 s | 146.9 s | 21/100 |

Unguarded `spjf` puts the cost on a few jobs: 20 jobs are sacrificed, each waiting 460 s longer on average,
and long jobs (study plans) wait 789 s on average while short ones wait 30 s. With the guard, more jobs are affected
(32), but the cost to each is much smaller (58 s), and the ratio between the long and short classes shrinks from 26 times to 3.8 times.
The 98 "worse off" jobs of cell 1 wait only 0.1 s longer on average: first-come first-served and its own replay should be equal,
so this row is a self-check of the replay code.

## 4. Open and closed loop: demand did react to waiting

This is the one capability this platform adds over the earlier timed-work physical experiment, and the result is positive.

**The same replayed first-come first-served counterfactual gives six different numbers in the six cells**:

| cell | mean / max wait of the replayed first-come first-served run |
|---|---|
| 1 fcfs | 308.8 / 533.2 s |
| 2 spjf | 725.2 / 1203.2 s |
| 3 guard, completed-work charging | 483.7 / 807.8 s |
| 4 guard, reservation charging | 652.6 / 1082.7 s |
| 5 guard, open loop | 141.9 / 321.1 s |
| 6 guard, closed loop (iii) | 346.7 / 632.8 s |

Under the closed loop the arrival sequence is a function of the policy: `spjf` returns short jobs within seconds, users send their next request sooner,
and so more work is packed into the same window; **its own** first-come first-served counterfactual is therefore more than twice as heavy as that of the `fcfs` run
(725 s against 309 s). **So the measured waits of different cells cannot be compared with each other directly**;
only the comparison of each run with its own replay is a clean control. This must be written into the method.

The effect of rule (iii) (the longer the wait, the longer the think time, slope = 0.5) relative to rule (ii):
both with guard and completed-work charging, cell 6 has mean wait 205.7 s and p90 433.8 s,
cell 3 has 235.2 s and p90 680.2 s; cell 6's replayed counterfactual (346.7 s) is also lighter than cell 3's (483.7 s).
**When demand slows down, the queue gets shorter**: the negative feedback exists and can be measured.

The open-loop run (cell 5) is the only one with ρ clearly below 1: arrivals are sent on a timetable,
independent of results, so the system can drain, and the mean wait is only 70.3 s.
**In the closed loop ρ is an outcome, not a parameter**; the only way to pin ρ is the open loop.

## 5. The two charging rules

| | cell 3, completed-work charging | cell 4, reservation and refund (rule R) |
|---|---|---|
| budget cap | `B_max = k(G − (3−2/k)L) = 120 s` | `Z_max = k(G − (2−2/k)L) = 460 s` |
| mean wait | 235.2 s | 206.7 s |
| p90 wait | 680.2 s | 896.8 s |
| max excess | 151.7 s (0.379 G) | 205.5 s (0.514 G) |
| jobs beyond the promise | 0 | 0 |
| firings | 24 | 20 |
| mean extra wait of sacrificed jobs | 57.8 s | 102.6 s |

The reservation rule's threshold is one L lower, so under the same promise its allowance is much larger (460 s against 120 s);
it lets more overtaking through and keeps more of the base policy's benefit (lower mean wait, short jobs wait only 26.9 s),
at the price of a longer extra wait for the sacrificed jobs (102.6 s against 57.8 s). Neither side exceeded the promise.

**This is not a controlled comparison**: the allowances of the two runs differ (that is determined by the rules themselves),
and under the closed loop the demand realisations of the two runs also differ. What it shows is that "both charging rules run on this stack,
both keep the promise, and both fall in the expected direction", not "which one is better".

## 6. Simulator check (G3)

Each run's `(a_i, C_i, score_i, k)` is fed to the paper package's simulator, and the waits are compared job by job:

| cell | policy in the simulator | jobs | measured mean / max wait | simulated mean / max wait | max per-job deviation | jobs with deviation > 1 s |
|---|---|---:|---|---|---:|---:|
| 1 | FCFS | 100 | 308.84 / 533.29 s | 308.76 / 533.24 s | 167.8 ms | 0 |
| 2 | SPJF-E | 100 | 227.41 / 1933.61 s | 227.34 / 1933.56 s | 125.3 ms | 0 |
| 3 | Guard(400) | 100 | 235.19 / 789.72 s | 235.12 / 789.67 s | 138.8 ms | 0 |
| 5 | Guard(400) | 100 | 70.33 / 324.42 s | 70.28 / 324.38 s | 115.5 ms | 0 |
| 6 | Guard(400) | 100 | 205.72 / 433.83 s | 205.66 / 433.78 s | 132.8 ms | 0 |

**Five runs, 500 jobs, max per-job deviation 167.8 ms; no job differs by more than 1 second.**

**Cell 4 is not part of this conclusion.** The paper package's simulator carries only the completed-work wrapper
and has no implementation of reservation and refund, so running cell 4 through it would mean checking a rule R trace against Algorithm 1:
in `simulator_replay.json` this row has `comparable` set to `false`, and the 982 s deviation measures
**the difference between the two mechanisms**, not fidelity. To add this comparison,
rule R from `evidence/reservation_guard/rguard.py` would have to be connected to `spjf_guard.sim`.

## 7. Dispatcher overhead

| cell | mean per dispatch epoch | max |
|---|---:|---:|
| 1 | 10.0 µs | 58 µs |
| 2 | 12.1 µs | 75 µs |
| 3 | 12.2 µs | 67 µs |
| 4 | 11.2 µs | 57 µs |
| 5 | 11.1 µs | 61 µs |
| 6 | 12.1 µs | 57 µs |

The measured queue depth is between 11 and 18 (`decisions-*.jsonl`). Algorithm 1 scans the waiting set at every epoch,
which at this depth takes on the order of 10 µs; service times are 10⁰–10² seconds. **They differ by 5 to 7 orders of magnitude.**
This number can only be obtained from a real deployment.

## 8. Tokens and wall-clock time

| cell | model calls recorded | input | output | stops in the engine log | wall-clock |
|---|---:|---:|---:|---:|---:|
| 1 fcfs / closed loop (ii) | 90 | 68,778 | 65,748 | 10 | 1955 s |
| 2 spjf / closed loop (ii) | 94 | 65,598 | 61,940 | 5 | 2104 s |
| 3 guard, completed-work charging / closed loop (ii) | 95 | 71,294 | 64,581 | 5 | 1777 s |
| 4 guard, reservation charging / closed loop (ii) | 99 | 78,711 | 76,856 | 1 | 1868 s |
| 5 guard, open loop (i) | 97 | 74,059 | 68,880 | 2 | 2769 s |
| 6 guard, closed loop (iii) | 96 | 71,086 | 64,578 | 3 | 1906 s |
| **Total** | **571** | **429,526** | **402,583** | **26** | **12,379 s (generator) / 3 h 27 min (including restarts)** |

Measured cost per call:

| call | n | mean input | mean output |
|---|---:|---:|---:|
| learner report (LearnerDiagnosisAgent) | 437 | 212 | 259 |
| study plan (ResourceGenerationAgent) | 134 | 2514 | 2158 |

Only 571 calls were recorded for 600 jobs: for the jobs stopped at the limit, the stream was cut before the usage block arrived,
and the output tokens they used were not recorded. So **832 thousand tokens is a lower bound**;
estimated from the share of stopped jobs, the true value is about 3–5% higher.

A monetary cost cannot be derived: the usage ledger has no unit-price field (the platform repository's `scripts/usage-ledger.py` itself states that it "therefore does not output amounts").

## 9. What this run supports

1. **Algorithm 1 kept the per-job promise on a production-grade stack.** Over the four guard runs, 400 jobs in all,
   the number of jobs beyond the promise is 0, and the max excess lies between 0.379 and 0.514 times G. The same base policy
   without the guard (cell 2), under the same k and the same promise, had 7 jobs beyond the bound, the worst by 4.67 times.
2. **The guard did not eat up the base policy's benefit.** Against each run's own replayed counterfactual: `spjf` cut the mean wait from 725.2 s
   to 227.4 s (−69%), `guard` from 483.7 s to 235.2 s (−51%).
   The cost moved from "20 jobs wait 460 s longer on average" to "32 jobs wait 58 s longer on average".
3. **The per-job limit is enforced on the server side, not merely observed.** 29 of the 600 jobs reached the limit,
   and the largest amount by which a measured service time exceeded its ℓ is 16.1 ms; the engine log explicitly records its own stop 26 times.
   This is the premise of rule R, and it holds on this stack.
4. **Demand reacts to waiting, measurably.** The same replayed counterfactual ranges from 141.9 s
   to 725.2 s over the six runs; closed-loop ρ is 0.97–1.00 and open-loop ρ is 0.695; rule (iii) lowers the mean wait from 235.2 s
   to 205.7 s. The earlier timed-work experiment could not do this.
5. **The paper's simulator matches the real service.** Five runs, 500 jobs, max per-job deviation 167.8 ms.
6. **Dispatch overhead is negligible**: 10–12 µs per epoch at a queue depth of 11–18, 5–7 orders of magnitude below the service times.

## 10. What this run does not support

- **No real people.** Demand was generated by scripted users on the local machine. This must be written verbatim into §7/§9:
  arrivals are scripted replays driven by synthetic accounts on a local deployment;
  no human learner was in the loop.
- **Not a p99 result.** With 100 jobs per run there is no credible p99; the local set-up also has no "assessment
  deadline" object, and the shape of the open-loop arrivals is borrowed from the paper's trace, not from this platform's calendar.
- **Measured waits of different cells cannot be compared with each other directly** (§4). Under the closed loop the arrival sequence is a function of the policy,
  and the only clean control is each run against its own replayed first-come first-served run.
- **Cell 3 and cell 4 are not a controlled comparison** (§5): the allowances differ, and so do the demand realisations.
- **Not heavy-tailed** (§2). The cross-class CV > 1 comes from mixing two job classes, and must be stated honestly as a construction.
- **The budget shape was not selected.** B0 = 30 s, η = 0.5 is a setting used in the paper's earlier physical experiment,
  and it was not reselected on a validation set this time. The relation between the promise G and the cap B_max is unaffected:
  the theorem reads the budget only through the cap.
- **The size proxy is not calibrated**, and it is not unbiased: it is used only for ordering, and the paper's guarantee holds for any score.
  The `inverted` (deliberately negated) and `random` settings were again not run this time.
- **One machine, one process.** The counters live on one event loop; no conclusion about distributed dispatch is supported.
- **The simulator's 168 ms is not a fidelity result.** In the 2151-job timed-work experiment of `weakness1_attack`,
  Guard's max per-job deviation was 1354.1 s, and 1753 jobs were dispatched at different positions.
  100 jobs with about 20 firings do not reach that regime. The two results must be written side by side.
- **The course-building job class was not connected** (about 0.6 M tokens per call); the two job classes in this run take minutes and seconds.

## 11. Files

| content | path |
|---|---|
| this file | `evidence/platform_testbed/results.md` |
| per-cell summary | `evidence/platform_testbed/records/summary.json` |
| simulator comparison | `evidence/platform_testbed/records/simulator_replay.json` |
| per-job records | `evidence/platform_testbed/records/jobs-full-*.jsonl` |
| per-dispatch decisions | `evidence/platform_testbed/records/decisions-full-*.jsonl` |
| client records | `evidence/platform_testbed/records/client-full-*.jsonl` |
| per-run parameters | `evidence/platform_testbed/records/manifest-full-*.json` |
| per-run tokens and stops | `evidence/platform_testbed/records/usage-full-*.log` |
| open-loop arrival timetable | `evidence/platform_testbed/records/arrivals_deadline_burst_100.csv` |
| table generation script | `evidence/platform_testbed/results_tables.py` |
| simulator comparison script | `evidence/platform_testbed/replay_simulator.py` |
| arrival table cutting script | `evidence/platform_testbed/make_arrivals.py` |

Platform side (`<platform-repo>`, branch `sched-experiment`):
dispatcher `apps/classroom/lib/server/classroom-dispatch.ts`,
engine-side execution limit `apps/agent-engine/backend/services/call_deadline.py`,
experiment scripts `experiments/scheduling/`, change and rollback notes `docs/调度实验改动说明.md`.
