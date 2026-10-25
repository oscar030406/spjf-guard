# Overhead of the per-job accounts

**Question.** Reviewer 3, Comment 9: what does it cost to keep a per-job overtaking
account and to share the scheduler state? The study times the production kernel on whole
runs and times the guard's operations alone, from 100 to 1,000,000 waiting jobs.

**Paper items.** §8.10 and Table 15. The corrected complexity statement in §5.4 and
Supplementary Section S5 rests on the finding in the notes below.

**Inputs.** Overlay 0 (`data/derived/overlay_traces/primary_rep0.npz`, 17,634,760 jobs),
the stored SPJF-E scores (`forward_scores.parquet`, by `job_row`), the frozen
configuration and `outputs/selection_v4/selected_parameters.csv`, and
`outputs/dev_tables/main_cells.csv` for the reproduction check.

**Status.** Complete. The measurement ran on 19 October 2026 after the machine had been
idle for 5,044 s (`out/table.md`, first lines). The kernel reproduced all 15 main-table
rows exactly before it was timed.

---

## Design

**Whole runs (`wholerun.py`).** Policies FCFS, SPJF-E and Guard(300), Guard(600) and
Guard(1200) at the three loads (k = 8, 5 and 4). The timed call is one
`simulate_kernel(...)` call of `src/spjf_guard/sim/kernel.py`, unchanged, with the same
arguments as `runner.simulate`. Metrics and the reproduction check are outside the timed
region.

- Clocks: thread CPU time (`time.thread_time_ns`) and wall time (`perf_counter_ns`).
- Each mode is compiled first on a 2,000-job prefix.
- Five repeats, looped as repeat, then load, then policy, so drift spreads over all cells.
  The table gives the median with the minimum and maximum.
- Events are counted as 3n (arrival, dispatch and completion of each job). The table also
  gives nanoseconds per job.
- The first repeat also records the peak number of waiting jobs, the mean number waiting at
  a dispatch, the window rebuilds and `max_span`.

**Operations alone (`scaling.py`).** A state with n waiting jobs, n = 10^2 to 10^6. Each
operation calls the kernel's own data-structure functions inside an `@njit` loop, so no
Python call is timed.

- Arrival: `_fen_pref` and `_st_set`, as in `_admit_arrivals`.
- Completion charge: `_fen_add` and `_st_add_suffix`, as in `_apply_completions`.
- Dispatch: the cap check `_fen_pref`, the query `_st_leftmost` and the removal
  `_st_set(NEG)`, as in `_fired_member` and `_choose`.
- Reference: the base SPJF heap, `_score_pop` and `_score_push`.

Leaf values rise with position, and each threshold is the value of a random leaf.
Therefore, every query walks a full root-to-leaf path. Two layouts are timed. In `queue`, the structures
have the size of the queue (the meaning of O(log n) in the paper). In `production`, the
Fenwick tree spans the whole trace (N = 17,634,760) and the window is 2^22, as
`simulate_kernel` allocates them for the main table. Each point is the median wall time of
five repeats, less the time of the random-number loop. Wall time is used because the
Windows thread clock moves in 15.6 ms steps.

**Idle wait (`measure.py`, `common.wait_until_idle`).** The script polls every 30 s. It
starts when, for 120 s in a row, total CPU use is below 15% and no other Python process
has a working set above 1 GB. Idle background services are excluded from that test. The
wait has no time-out. The output records every poll of the window, the CPU model, the power
plan, the numba version and the thread count. The probes use `ctypes` and `winreg`,
because starting `powershell` under load failed.

## Gates

1. The timed code is the code of the main table:
   `wholerun.py --reps 1 --out whole_gate.json` compares p99_dl_s, mean_s, p99_all_s,
   max_excess_s, harm_s, max_heavy_s, fired_fraction_queue_weighted and n_jobs of the 15
   rows with `outputs/dev_tables/main_cells.csv` by exact equality:
   `gate exact reproduction: PASS (15/15 rows)` (`out/gate_whole.log`). The first repeat
   of the full measurement repeats this check.
2. Operations alone, n ≤ 10^4: `scaling.py --exps 2,3,4 --min-seconds 0.3 --repeats 3`,
   exit 0 (`out/scaling_smoke.log`).
3. End to end with a relaxed idle test: `measure.py --poll 2 --need 4 --cpu-limit 100
   --mem-gb 1000 --reps 2 --exps 2,3 --min-seconds 0.05` and `table.py`, both exit 0
   (`out/measure_smoke.log`, `out/table_measure_smoke.md`).

The `*_smoke*` files were measured on a busy machine and are not cited.

## Finding: the kernel's cost does not depend on the queue length

The submitted manuscript said that each event costs O(log n), with n the number of waiting
jobs. `simulate_kernel` builds its Fenwick tree over the ranks of the whole trace and fixes
the window at 2^22. Therefore, each event costs O(log N + log W), whatever the queue length.
The O(log n) statement holds for structures sized to the queue. The kernel's window rebuild
(`_rebuild_window`) could provide such structures by compressing ranks. The revised manuscript
states the cost of the implementation and gives the measured times.

## Replicated schedulers (no experiment)

With R replicas of the scheduler, each job needs 2R one-way messages: R ordered arrival
messages from one sequencing point, and R completion reports, in any order. No
acknowledgement or consensus round is needed for the reports. The account over[q] depends
only on the set of reports received, and a duplicate report only raises it. Therefore, the
bound still holds. The guard's decision is the same on every replica that has the same history.
A replica whose reports lag by at most δ is a scheduler with charges δ late
(Proposition 12).

The implementation stores no account per job. over[q] = TC − F(q), one Fenwick prefix sum
for any waiting job. A job takes about 50 bytes: one Fenwick cell, one `zs` entry, one
segment-tree leaf with its share of internal nodes and lazy tags, one FIFO entry, one
`served` byte and 16 bytes in the base policy's heap.

## Files and commands

Code: `common.py`, `wholerun.py`, `scaling.py`, `measure.py`, `table.py`.
`chain_steps.json` has two steps: `guard_overhead_measure` waits for an idle machine and
writes `measure.json`, and `guard_overhead_table` writes `table.md`, `table.whole.csv`
and `table.scaling.csv`. The run log is `out/chain_r1_guard_overhead.log`. The full
measurement takes about 20 minutes after the idle wait, with a peak of about 3.5 GB and
two numba threads.
