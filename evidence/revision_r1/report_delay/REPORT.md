# Late completion reports on the development overlays: report

Reviewer 2, comment 4: Proposition prop:late bounds the guard when completion reports
reach it up to delta late, but no trace-driven run shows what delta costs. This
experiment replays the 15 primary development cells (overlays 0-4, levels 0-2, k = 8, 5,
4 as in the main table) with late charges and measures p99, gap closed, harm, max excess
over FCFS, and the per-job bounds as delta grows.

## Design

- Models, exactly as in `evidence/stale_charging/sim_stale.py`:
  - U: one shared counter. The charge of job c, completed at f_c, is applied at f_c + d_c.
  - A1: U, and a server applies its own last completion just before it pulls its next job.
  - A2: each server dispatches from its own view. Its own completions enter that view at
    once. Another server's completion c enters it at f_c + d_c.
  - Order at one instant: completions, charges due by t, arrivals, dispatches. A free
    server is the lowest-index one.
- Kernel: `delay_kernel.py`, a copy of `src/spjf_guard/sim/kernel.py`. The segment tree,
  the Fenwick tree and the heaps are verbatim. The event loop adds server identities and
  a pending-charge heap. A2 keeps one segment tree and one Fenwick tree per server. Every
  charge goes through the heap, so delta = 0 runs the same code path.
- delta in {0, 0.1, 1, 5, 30, 60, 300} s. Two laws: constant d_c = delta, and uniform
  d_c = floor(u_c (delta + 1)) us with u_c = default_rng(20261018 + overlay).random(n).
  Every policy, model and delta of an overlay uses the same u.
- Policies: Guard(300), Guard(600), Guard(1200) built from
  `configs/main_frozen_1289aa2.yaml` and `outputs/selection_v4/selected_parameters.csv`
  through `cfg.policies`. Each run asserts the parameters against
  `outputs/dev_tables/policy_parameters.csv`. Scores: the stored `tweedie` array. It
  equals `forward_scores.parquet` column `spjf_e` indexed by `job_row`, the input of the
  main table (checked on overlay 0: equal, max |diff| 0).
- References: FCFS, SJF and SPJF-E from the production `spjf_guard.sim.simulate`. delta
  does not change them. SJF is run because gap closed needs it.
- delta = 0 is one run per guard (model `all`, law `all`). Every model is Algorithm 1 there.
- Metrics per row: `summarise`, `gap_closed` and `reduction_percent` from
  `spjf_guard.experiment.metrics`, the code of the main table. Bound checks, in int64 us:
  - `viol_late`: jobs with k * excess >= Bmax + (3k-2)L + X. X = k(L + delta) for U,
    (k-1)(L + delta) for A2, 0 for A1 and at delta = 0 (the header of sim_stale.py).
    For U this is eq. (late) of the paper.
  - `viol_orig`: jobs above `guard_upper_bound` (Theorem 3, the main table's assertion).
  - `worst_ratio_late`, `worst_ratio_orig`, and the worst job's index and waits.

Rules fixed before the overlay runs:
- `viol_late > 0` in any row is a finding against prop:late and is reported as such.
- For U and A2 at delta > 0, `viol_orig > 0` is expected: Theorem 3 is not claimed there.
- For A1, `viol_orig > 0` with `viol_late == 0` would show that the multiplicative form of
  Theorem 3 breaks under A1. The paper says Theorem 3 holds unchanged for A1.

## Gates (repository root; `PY` = `env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME .venv/Scripts/python.exe`)

1. `$PY -u evidence/revision_r1/report_delay/check_reference.py 30000 20261018`
   ```
   U: {'instances': 9928, 'delta_pos': 7911, 'compared': 20127, 'skipped_err': 9657, 'with_rebuild': 369, 'mismatch': 0, 'charges_compared': 276472}
   A1: {'instances': 10087, 'delta_pos': 8025, 'compared': 20431, 'skipped_err': 9830, 'with_rebuild': 502, 'mismatch': 0, 'charges_compared': 327655}
   A2: {'instances': 9985, 'delta_pos': 7927, 'compared': 20213, 'skipped_err': 9742, 'with_rebuild': 482, 'mismatch': 0, 'charges_compared': 743142}
   delta=0 vs production kernel: {'compared': 3043, 'mismatch': 0}
   GATE1 instances 30000 total_mismatches 0 (2.5 s)
   ```
   Per job: start, server, dispatch position, and the dispatch count at which each charge
   entered each view (appg and app2 in sim_stale.py). Windows of 64, 16 and 8 ranks;
   err = 1 runs (window too small) are skipped. Server orders 0 and 1 both covered.
   Mutation tests on scratch copies (1500 instances each): charge due at t applied one
   event late, 1878 mismatches. A1 report-before-pull removed, 836. A2 dispatching from
   the shared view, 82. Output: `outputs/revision_r1/report_delay/gate1_check_reference.json`.
2. `$PY -u evidence/revision_r1/report_delay/run_delay.py gate2`
   ```
   GATE2 mismatches 0 wall 711.2 s peak commit 4.64 GB
   ```
   Overlay 0, levels 0-2, each guard, each model at delta = 0: waits equal to the
   production `simulate` (max |diff| 0 us), dispatch order and forced counts equal, and
   p99_dl_s, gap_closed, max_excess_s, harm_s, mean_s equal to `main_cells.csv` as
   floats. FCFS, SJF and SPJF-E rows also equal. Example line:
   `L0 k8 Guard(300) A2: wait diff 0 us, order equal True, p99 12.76878855000015 gap 0.6783084612833095 exc 189.287731, main_cells diffs none (58.7 s)`.
   Output: `gate2_delta0.json`, `gate2.log`.
3. Smoke: `$PY -u evidence/revision_r1/report_delay/run_delay.py run --overlay 0 --level 2 --models U --resume`
   ```
   rep0 L2: done {'overlay': 0, 'level': 2, 'k': 4, 'rows': 42, 'wall_s': 295.2, 'peak_commit_gb': 2.66}
   ```
   42 rows (3 references, 3 delta = 0, 36 U rows) in 295 s wall, peak commit 2.66 GB.
   Loading and the references take 24 s. One U run takes 5-7 s. The smoke wrote into
   `cells/`, so the full-grid step for rep0_L2 resumes it and adds only A1 and A2.
   Timing rows, same file:
   `run --overlay 0 --level 2 --models A1,A2 --laws const --deltas 30,300 --policies "Guard(600)" --resume`:
   A1 5.9 s per run, A2 24.6-25.5 s per run, peak commit 3.24 GB.

## Smoke numbers (overlay 0, level 2, k = 4; FCFS p99 263.120 s, SJF 42.881 s, SPJF-E 61.811 s)

| policy | model, law | delta (s) | p99 (s) | gap | max excess (s) | viol_late | viol_orig |
|---|---|---|---|---|---|---|---|
| Guard(300) | delta 0 | 0 | 156.169 | 0.4856 | 219.6 | 0 | 0 |
| Guard(300) | U const | 60 | 142.246 | 0.5488 | 291.1 | 0 | 0 |
| Guard(300) | U const | 300 | 106.280 | 0.7121 | 520.6 | 0 | 12969 |
| Guard(300) | U unif | 300 | 124.697 | 0.6285 | 380.9 | 0 | 1002 |
| Guard(600) | delta 0 | 0 | 87.541 | 0.7972 | 512.3 | 0 | 0 |
| Guard(600) | U const | 60 | 85.627 | 0.8059 | 589.8 | 0 | 0 |
| Guard(600) | U const | 300 | 81.955 | 0.8226 | 801.8 | 0 | 4674 |
| Guard(600) | A1 const | 300 | 87.541 | 0.7972 | 512.3 | 0 | 0 |
| Guard(600) | A2 const | 300 | 82.719 | 0.8191 | 733.1 | 0 | 2554 |
| Guard(1200) | delta 0 | 0 | 77.363 | 0.8434 | 1110.4 | 0 | 0 |
| Guard(1200) | U const | 300 | 74.326 | 0.8572 | 1373.0 | 0 | 770 |

Read on one cell only:
- Late charges make the guard fire less, so the schedule moves toward SPJF-E. The p99
  falls and the gap closed rises with delta. The cost shows in the worst case: the max
  excess over FCFS grows by about delta for U (Guard(600): 512 s at 0, 802 s at 300 s).
- Up to delta = 60 s, no U job exceeds Theorem 3. At 300 s, 770 to 12,969 jobs do, all
  within the late bound (`viol_late` 0).
- A1 at delta = 30 and 300 s gives the delta = 0 numbers on this cell. The A1 branch is
  live: gate 1 checks it job by job, and removing report-before-pull gave 836 mismatches.
  Expected mechanism (not measured, wait arrays not compared): when jobs wait, every
  server is busy, so the next pull comes from a server that applies its own completion
  first. A1 can differ from delta = 0 only when a server pulls while an idle server's
  completion is still unreported, which needs events at the same microsecond.
- `harm_s` and the other columns are in `cells/rep0_L2.csv`.

## Full grid

`chain_steps.json`: 15 steps `run_delay.py run --overlay o --level l --resume` (level 2
first), then `summarize.py`. Each step skips the rows already in
`outputs/revision_r1/report_delay/cells/rep<o>_L<l>.csv` and rewrites that file after
every row. No step needs the network. Rows per cell: 3 references + per guard 1 + 6
deltas x 2 laws x 3 models = 114 guard rows.

Cost estimate from the measured run times (U and A1 about 6 s; A2 about 27 s at k = 4,
37 s at k = 5, 60 s at k = 8; about 30 s per cell for loading and references):
- level 2 (k = 4): 3 x (25 x 6 + 12 x 27) s = about 24 min per cell.
- level 1 (k = 5): 3 x (150 + 12 x 37) s = about 30 min per cell.
- level 0 (k = 8): 3 x (150 + 12 x 60) s = about 44 min per cell.
- Total: about 8.2 h for 15 cells, one process at a time. A2 is 70 % of it.
- Peak commit: 4.64 GB at k = 8 with A2 (gate 2), under the 12 GB limit.

Note: `rep<o>_L<l>.log.json` describes the last invocation only. The chain's resumed
rep0_L2 run overwrites the smoke values; they stay in `smoke_rep0_L2_U.log` and above.

Outputs: `cells/rep<o>_L<l>.csv` and `.log.json` (wall, peak commit), then
`summary.csv` and `summary.md` (mean over overlays of p99 and gap, change from delta = 0,
worst max excess, harm and ratios, summed violations, missing cells listed).

## Open issues

- A2 costs k segment trees per event. A faster A2 is possible but not built: the
  estimate above is affordable.
- Only server order 0 (lowest free index) runs on the overlays. Gate 1 covers both orders.
- The uniform law uses one draw of u per overlay, so the laws differ only through delta.
- delta = 0 rows are one run labelled `all`; summarize.py copies them into every series.
