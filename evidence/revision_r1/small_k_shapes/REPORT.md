# Small-k budget shapes and a no-grid default (reviewer 2, comment 5)

Purpose: the operator wants a budget setting that needs no grid search. The key variable
is how much gap the constant shape at B_max/2 gives up against the best grid-selected shape
at k = 1, 2, 3. This experiment measures that shortfall and the harm that goes with it.

## 1. Pre-registered default (written 2026-10-18T15:42Z, before any run)

Rule, from Corollary cor:params (paper/sections/06_theory.tex) and Section "Setting the
Guard" (paper/sections/05_scheduling.tex):

- B_max = k (G - (3 - 2/k) L), with L = 60 s.
- Default: constant shape, eta = 0, gamma = 0, B0 = B_max / 2.
- Built in code as `fixed(G, k, L, "spjf_e", b0_s=B_max/2, name="Guard-default(G)")`,
  not through `Config._guard_from`, which would scale B0 by k/4.

| k | floor (3-2/k)L | B_max at G = 300 / 600 / 1200 | B0 = B_max/2 at G = 300 / 600 / 1200 |
|---|---|---|---|
| 1 | 60 s  | 240 / 540 / 1140 s  | 120 / 270 / 570 s  |
| 2 | 120 s | 360 / 960 / 2160 s  | 180 / 480 / 1080 s |
| 3 | 140 s | 480 / 1380 / 3180 s | 240 / 690 / 1590 s |

The default keeps the promise G because B0 <= B_max. With eta = 0 the multiplicative bound
also applies, so its excess bound is B0/k + floor = (G + floor)/2 (k = 1: 180/330/630 s,
k = 2: 210/360/660 s, k = 3: 220/370/670 s).

### What the final step computes (fixed now, no threshold tuned later)

Per (k, G, load) group of 5 overlays:

1. best shape = the family winner (Guard-fixed, Guard-age, Guard-queue) with the highest
   mean gap closed over the 5 overlays.
2. shortfall = mean gap closed of the best shape minus that of Guard-default(G), with a
   paired week-block bootstrap interval (2000 resamples, the configuration's seed).
3. harm of Guard-default(G) and of the best shape, worst over the 5 overlays.

The default counts as adequate in a group when both hold:

- shortfall <= 0.05 of the gap (point estimate), and
- worst-overlay harm of the default <= G/2, the harm limit of the selection rule
  (`harm_fraction` 0.5 in the configuration).

The guidance reports, per k and per G, the number of adequate groups out of 3 loads, and
the largest and the median shortfall. It also reports the same numbers for the constant
grid winner (Guard-fixed) and for Fixed(G) (B0 = B_max), against the same best shape.

## 2. Design

- k in {1, 2, 3}. G in {300, 600, 1200} s. Busy-hour per-server load 0.50, 0.80, 0.95
  (the loads of the existing G18 B k = 1 grid). 5 repetitions, seeds 350 + rep.
- k = 1 traces: `outputs/steady_online_g18b/overlays/k1u{50,80,95}_rep{0..4}.npz`, read only.
  k1u80_rep0 equals `data/derived/overlay_traces/k1_rep0.npz` on all 13 trace arrays (G18 B gate).
- k = 2, 3 traces: same pipeline (`single_server_pool`, then `build_overlay(..., servers=[k])`),
  target and window multiplied by k (busiest-hour work / 3600 near k x load). The pool is
  listed 16k times instead of 8, so that the random phase reaches the target without the
  greedy phase. The builder asserts this, and it re-derives k1u80_rep0 with the k = 1
  settings and checks it against k1_rep0.npz.
- Scores: SPJF-E (`spjf_e`) from `data/derived/package_ranking_scores/forward_scores.parquet`,
  attached by `job_row` (as the k = 1 table and the main table did).
- Shape points: `outputs/selection_v4/selected_parameters.csv` (the selection the k = 1 and
  main tables read), not reselected. The joint winner Guard(G) equals Guard-age(G) at
  G = 300, 600 and Guard-queue(G) at G = 1200, so it is not simulated twice.
- Policies per cell: FCFS, SJF, SPJF-E, and per G: Guard-fixed, Guard-age, Guard-queue,
  Fixed(G), Guard-default(G): 17 simulated policies, 18 rows with FCFS.
- Config: `configs/main_frozen_1289aa2.yaml`. Every guarded run asserts its per-job bound.

## 3. Gates

Python is `env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME .venv/Scripts/python.exe`,
run from the repo root. Logs are in `outputs/revision_r1/small_k_shapes/logs/`.

Gate 1, the k = 1 table (`outputs/dev_tables/k1`), PASS:

```
run_cells.py --trace outputs/steady_online_g18b/overlays/k1u80_rep0.npz --overlay 0     --out-dir outputs/revision_r1/small_k_shapes/cells
  k1u80_rep0_l0: k = 1, 3,209,347 jobs, 18 policies, bound violations 0, 57.2 s, peak commit 0.96 GB
gate_compare.py outputs/revision_r1/small_k_shapes/cells/k1u80_rep0_l0 outputs/dev_tables/k1
  main_cells.csv: 15/15 shared rows equal on 18 columns (12 guarded)
  bound_checks.csv: 12/12 shared rows equal on 9 columns (12 guarded)
  policy_parameters.csv: 12/12 shared rows equal on 10 columns (12 guarded)
  gate: PASS
```

The trace k1u80_rep0 equals k1_rep0.npz on the 13 trace arrays (G18 B gate), so this cell
is also the full run's k1u80_rep0 cell. Rows compare as text: every field is the same string.

Gate 2, one main-k guard row (`outputs/dev_tables/main_cells.csv`, overlay 0, level 0, k = 8), PASS:

```
run_cells.py --trace data/derived/overlay_traces/primary_rep0.npz --overlay 0 --levels 0     --policies "FCFS,SJF,Guard-age(600),Guard-fixed(600)" --no-bootstrap     --out-dir outputs/revision_r1/small_k_shapes/gates/gate2
  primary_rep0_l0: k = 8, 17,634,760 jobs, 4 policies, bound violations 0, 45.0 s, peak commit 2.43 GB
gate_compare.py outputs/revision_r1/small_k_shapes/gates/gate2/primary_rep0_l0 outputs/dev_tables
  main_cells.csv: 4/4 shared rows equal on 18 columns (2 guarded)
  bound_checks.csv: 2/2 shared rows equal on 9 columns (2 guarded)
  policy_parameters.csv: 2/2 shared rows equal on 10 columns (2 guarded)
  gate: PASS
```

Guard-age(600) is the joint winner Guard(600); its row equals the main table's Guard-age(600) row.

Gate 3, the generalised builder at k = 1: `build_traces.py` first rebuilds the 15 G18 B
k = 1 traces with 8 listings and checks each against its file (and k1u80_rep0 against
k1_rep0.npz). PASS (`logs/smoke_build.log`): all 15 traces equal their G18 B files on all
13 arrays, k1u80_rep0 included.

A one-cell dry run of `final_table.py --allow-partial` (k1u80_rep0 only) is parked in
`outputs/revision_r1/small_k_shapes/dryrun_1cell/`; it only checks that the script runs.

## 4. Smoke (k = 2, overlay 0, all three loads, all 18 policies, bootstrap on, 1 worker)

```
build_traces.py --ks 2 --reps 0        # gate 3 + 3 traces, 23 s wall, peak commit 2.67 GB
run_cells.py --trace outputs/revision_r1/small_k_shapes/overlays/k2u{50,80,95}_rep0.npz     --overlay 0 --out-dir outputs/revision_r1/small_k_shapes/cells
  k2u50_rep0_l0: 3,335,329 jobs, bound violations 0,  56.7 s, peak commit 0.97 GB
  k2u80_rep0_l0: 6,027,279 jobs, bound violations 0,  98.4 s, peak commit 1.26 GB
  k2u95_rep0_l0: 7,505,035 jobs, bound violations 0, 119.8 s, peak commit 1.42 GB
```

The k = 2 traces: 330 / 613 / 746 copies, per-server busy-hour load 0.5000 / 0.7999 / 0.9500,
30 weeks each; the random phase reached the target in all three (asserted).
Peak commit is the job-object peak of the runner and its pool worker together.

Smoke values, gap closed (overlay 0 only, not a result):

| load | G | Guard-fixed | Guard-age | Guard-queue | Fixed(G) | Guard-default |
|---|---|---|---|---|---|---|
| 0.50 | 300 | 0.688 | 0.690 | 0.644 | 0.726 | 0.698 |
| 0.80 | 300 | 0.607 | 0.771 | 0.685 | 0.811 | 0.651 |
| 0.95 | 300 | 0.370 | 0.650 | 0.551 | 0.680 | 0.400 |
| 0.95 | 600 | 0.757 | 0.853 | 0.796 | 0.856 | 0.749 |
| 0.95 | 1200 | 0.862 | 0.892 | 0.821 | 0.895 | 0.866 |

The early sign: at a tight promise and high load, a constant budget (grid winner or
B_max/2) trails the age-relative shape by up to 0.25 of the gap. The adequacy test of
section 1 decides on the 5-overlay means after the full run.

### Design asymmetry to state in the paper

The k = 1 traces are the G18 B files unchanged. With 8 listings their random phase ran out,
so u80 and u95 at k = 1 hold about the same 320 copies and differ in the busy hour that the
greedy phase built. At k = 2, 3 (16k listings) the random phase reaches each target, so the
load levels differ in volume as well. This keeps gate 1 exact and the k = 1 cells equal to
the published k = 1 table.

## 5. Full-run cost (estimate, not run)

Cell time is about 16-18 s per million jobs with 18 policies and 1 worker (smoke and gate 1).

| part | jobs | estimate |
|---|---|---|
| build the 24 traces left + gate 3 | - | about 2 min, peak commit 2.9 GB (k = 3 rep 0 build: 15 s) |
| k = 1, 14 cells left (1 done) | about 36 M | about 11 min |
| k = 2, 12 cells left (3 done) | about 68 M | about 19 min |
| k = 3, 15 cells | about 145 M (rep 0 measured: 6.2 / 10.8 / 12.4 M) | about 40 min |
| final_table | - | under 1 min |

Total about 75 min wall at BelowNormal, one process at a time. Largest cell (k = 3, load
0.95, 12.4 M jobs at rep 0): peak commit about 2 GB (extrapolated from the smoke). Disk: about 7.5 GB of traces in
`outputs/revision_r1/small_k_shapes/overlays` (the 3 k = 2 smoke traces take 0.6 GB).

Run it as the steps of `chain_steps.json` (47 steps: build_traces, 45 cells, final_table).
Every step skips work that is already on disk.

The k = 3 rep 0 traces are built already (`logs/k3_rep0_build.log`): 597 / 1049 / 1197 copies,
per-server load 0.4997 / 0.7995 / 0.9511, and the random-phase assertion held at load 0.95.

## 6. k = 1 sensitivity traces (added on 2026-10-18)

The k = 1 / k >= 2 construction asymmetry (section 4) does not touch the within-cell shape
comparison, but it confounds the trend across k. So a second k = 1 family is added:

- `build_traces.py --ks 1 --listings 16` writes `k1L16u{50,80,95}_rep{0..4}.npz`; names
  cannot collide with the published k = 1 traces (`k1u..`). Cells are `k1L16u.._rep._l0.*`.
- The original k = 1 cells stay, for the exact match to the published k = 1 table (gate 1).
- `final_table.py` now groups by series (k1, k1L16, k2, k3), expects 60 cells, and writes
  `trend.csv`: the shortfall of each candidate at k1L16 -> k2 -> k3, with k1 beside it.

Check (`logs/k1L16_rep0_build.log`):

```
build_traces.py --ks 1 --listings 16 --reps 0
  gate k = 1 k1u80_rep0.npz: 321 copies, 3,209,347 jobs: all 13 arrays equal   (15/15 equal)
  k1L16u50_rep0: 147 copies, load 0.4999, 1,419,761 jobs
  k1L16u80_rep0: 250 copies, load 0.8007, 2,497,947 jobs
  k1L16u95_rep0: 397 copies, load 0.9498, 4,014,130 jobs   (random phase held at all three)
  peak commit 2.63 GB, 19 s
```

The gate line checks k1u80_rep0 against both its G18 B file and `k1_rep0.npz`.
Extra cost: about 40 M jobs, about 11 min; the full chain becomes about 86 min, 63 steps.

## 7. Blockers

None. Nothing was downloaded or installed. psutil is not in .venv, so `common.py` reads the
peak commit through a Windows job object with ctypes.
