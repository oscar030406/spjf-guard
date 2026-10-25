# Backfilling baselines (reviewer 2, comment 3)

Date: 2026-10-18. Commit at run time: bce7916; this directory is untracked. No downloads.
Code: `bf_kernel.py` (numba kernel), `ref_est.py` (Python reference for per-job estimates),
`gate1_random.py`, `gate2_prefix.py`, `run_backfill.py` (one cell), `make_table.py`,
`chain_steps.json`. Outputs: `outputs/revision_r1/backfill_baselines/`.

## Design

- Model: the main-table cells (5 overlays x 3 loads, original clock, main-table k). k servers,
  width 1, non-preemptive, integer microseconds, as in `src/spjf_guard/sim/kernel.py`.
- Rules: `evidence/llm_batching/backfill/backfill.py` with M = k, w = 1. The kernel keeps its
  event order, compression, slack price, tie-break and slack candidates "now+anchor". Earliest
  fit has no upper bound. It returns backfill.py's point whenever the current place is feasible.
  With estimate L this always holds.
- Policies (8 per cell):
  - `CBF-L`, `Slack-L(G)`: every job's estimate is the limit L = 60 s. Every service time is at
    most L, so each rule keeps its own promise. CBF promises the reservation made at arrival.
    Slack promises the time scheduled at insertion + G.
  - `CBF-P`, `Slack-P(G)`: the stored SPJF-E prediction (`forward_scores.parquet`, column `spjf_e`,
    by `job_row`; the score of the main table), clipped to [1 us, L]. No guarantee. A job still
    running at its estimate gets estimate L, as in Tsafrir, Etsion and Feitelson (2007).
    CBF then re-runs its compression. Slack re-places every waiting job in ascending
    (te, index) and sets slack to max(s - delay, 0). This overrun step is my extension.
    `ref_est.py` is its reference.
  - G in {300, 600, 1200} s.
- Slack price: float64 sum. Prices within 1e-9 relative count as equal, so the exact Fraction
  ties of backfill.py are kept. Counter `C_NEARTIE` counts ties with a non-integer term; it was 0
  in every run.
- Row metrics (`run_backfill.py`) use the main-table functions from
  `spjf_guard.experiment.metrics`: deadline-window p99, harm, gap closed, mean, p99 all, max excess,
  max heavy. FCFS is recomputed with the production kernel and checked against `main_cells.csv`.
  SJF p99 is read from `main_cells.csv`. Extra columns: jobs with excess over FCFS above
  300/600/1200 s, violations of the rule's own promise, jobs that start at another time than
  under FCFS, kernel counters, wall time and peak commit.
- Table layout (`make_table.py`): the run_main aggregation, mean over overlays of p99 and gap
  closed, worst over overlays of harm, max excess and counts. The table puts the backfilling rows
  next to FCFS, SJF, SPJF-E (`main_cells.csv`) and Guard(G), Timeout(G) (`online_cells.csv`,
  variant original). Guard rows in the two files are identical, which I checked on o0 l2.

## Gates

Interpreter `<py>`: `env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME NUMBA_NUM_THREADS=2 .venv/Scripts/python.exe`
from the repository root.

### Gate 1: random small instances, PASS

`<py> -u evidence/revision_r1/backfill_baselines/gate1_random.py` (14 s, output
`gate1_random.txt`). 4,000 instances, k 1-5, D 1-8, up to 14 jobs, many simultaneous
arrivals, G in {0, D, 2D, 3D}. Every start compared.

```
after 4000: {'instances': 4000, 'jobs': 30252, 'A cbf != ref': 0, 'A cbf != backfill.py': 0,
 'A slack != ref': 0, 'A slack != backfill.py': 0, 'A cbf != FCFS': 0, 'B cbf != ref_est': 0,
 'B slack != ref_est': 0, 'B fallback differs': 0, 'ref_est(D) != backfill_ref': 0}
observed (not asserted): {'B overruns': 7583, 'B fallbacks': 0, 'A slack != FCFS': 593}
PASS: 0 mismatches [14 s]
```

A: estimate D for every job, against `backfill_ref.py` and `backfill.py`. B: per-job estimates with
overrun, against `ref_est.py`. The gate found two faults, and I fixed both before the run above:

- The arriving job sat in the waiting set during its own slack trial.
- A float price split an exact rational tie (now the 1e-9 rule).

### Gate 2: overlay 0, level 2, PASS

`<py> -u evidence/revision_r1/backfill_baselines/gate2_prefix.py` (output `gate2_prefix.txt`).
backfill.py keeps one counter per time step. So each slice is quantised: arrival floor,
duration ceil, D = L/u, G = 300 s/u. Both implementations run the same integer instance.

```
first: 20000 jobs, unit 10000 us, D 6000, G 30000; conservative: 0 starts differ
first: 20000 jobs, unit 10000 us, D 6000, G 30000; slack now+anchor: 0 starts differ
busy slice from job 64212 (largest FCFS queue in the slice 67)
busy: 20000 jobs, unit 100000 us, D 600, G 3000; conservative: 0 starts differ
busy: 20000 jobs, unit 100000 us, D 600, G 3000; slack now+anchor: 0 starts differ
PASS: 0 starts differ
```

The first 20,000 jobs carry about 1% utilisation, so I added a busy slice. In that slice slack
and conservative give different mean waits (1.832 and 1.839 units), and both match backfill.py.

### Gate 3: full cell o0 l2 (k = 4, 17,634,760 jobs), smoke

`<py> -u evidence/revision_r1/backfill_baselines/run_backfill.py --rep 0 --level 2 --out-dir outputs/revision_r1/backfill_baselines/smoke`
(log `smoke_o0_l2.log`, rows `smoke/o0_l2_*.json`). BelowNormal priority, one serial kernel, all
8 policies (one cell, not the grid). Load + FCFS took 8 s.

| policy | wall (s) | peak commit (GB) | p99 wait (s) | gap closed | harm (s) | max excess (s) | jobs excess > 300/600/1200 s | starts != FCFS | own-promise violations |
|---|---|---|---|---|---|---|---|---|---|
| FCFS | - | - | 263.120 | 0 | 0 | 0 | - | - | - |
| Guard(300) | - | - | 156.169 | 0.4856 | 103.3 | 219.6 | - | - | - |
| Timeout(300) | - | - | 254.199 | 0.0405 | 182.3 | 188.5 | - | - | - |
| Guard(600) | - | - | 87.541 | 0.7972 | 259.3 | 512.3 | - | - | - |
| Timeout(600) | - | - | 172.172 | 0.4130 | 449.5 | 462.1 | - | - | - |
| Guard(1200) | - | - | 77.363 | 0.8434 | 103.3 | 1110.4 | - | - | - |
| Timeout(1200) | - | - | 82.842 | 0.8186 | 462.7 | 1058.8 | - | - | - |
| CBF-L | 228 | 2.22 | 263.120 | 0 | 0 | 0 | 0/0/0 | 0 | 0 |
| Slack-L(300) | 282 | 2.80 | 263.120 | 0 | 0.2 | 0.35 | 0/0/0 | 587 | 0 |
| Slack-L(600) | 292 | 2.80 | 263.120 | 0 | 0.2 | 0.35 | 0/0/0 | 587 | 0 |
| Slack-L(1200) | 292 | 3.19 | 263.120 | 0 | 0.2 | 0.35 | 0/0/0 | 587 | 0 |
| CBF-P | 927 | 2.80 | 260.701 | 0.0110 | 56.9 | 117.7 | 0/0/0 | 2,185,162 | 2,406,645 |
| Slack-P(300) | 200 | 3.19 | 117.692 | 0.6603 | 957.8 | 5369.9 | 5673/2337/819 | 2,911,280 | 8,264 |
| Slack-P(600) | 199 | 3.19 | 117.692 | 0.6603 | 957.8 | 5369.9 | 5673/2337/819 | 2,911,280 | 3,573 |
| Slack-P(1200) | 201 | 3.19 | 117.692 | 0.6603 | 957.8 | 5369.9 | 5673/2337/819 | 2,911,280 | 1,269 |

Peak commit is the process peak and includes earlier policies of the same process. The full
table with SJF and SPJF-E is `outputs/revision_r1/backfill_baselines/backfill_table.md`
(`make_table.py --cells .../smoke`).

## What the smoke cell shows

- With the guarantee-bearing estimate L, both backfilling rules act as FCFS. CBF-L starts all
  17,634,760 jobs at their FCFS times. This also held in all 4,000 random instances of gate 1.
  - Reason: every job has width 1 and the same estimate L. Then every reservation is L long.
    The planned usage never rises again after it falls. A later job never finds a hole of
    length L before an earlier job's reservation. So backfilling has nothing to fill.
  - Slack-L starts 587 jobs at other times than FCFS. The largest delay over FCFS is 0.35 s.
    These jobs arrive in the same microsecond as a freed server and take it ahead of a queued job.
  - Gap closed is 0 at every G.
  - Proof status: gate 1 and the full cell verify the CBF-L = FCFS claim. I did not write a proof.
- With SPJF-E predictions (no guarantee):
  - CBF-P closes 1.1% of the gap. Predictions run short for 7,316,496 jobs, and each of those
    estimates jumps to L.
  - Slack-P closes 66.0%, less than Guard(600) (79.7%) and Guard(1200) (84.3%). It has a max
    excess of 5,370 s and 819 jobs more than 1,200 s past FCFS. Harm is 958 s.
  - The waits of Slack-P do not depend on G. Each job's slack rises when compression moves it
    earlier, so the slack limit never binds. G changes only the count of own-promise violations.
- Load-Balancing Guardrails is not implemented (main-thread decision).

## Full grid: cost and how to run it

- Cost model: run time follows the FCFS queue length summed over arrivals (sumW).
  - o0: 6.1e7, 3.7e8, 9.0e8 for levels 0, 1, 2.
  - o4: 9.9e7, 3.4e8, 8.5e8 for levels 0, 1, 2.
- Per cell at level 2: 8 policies take about 2,630 s (44 min).
- Estimate: about 44, 18 and 6 min per overlay for levels 2, 1, 0, so about 68 min per overlay.
  That is about 5.7 h for the 15 cells, serial, one process, peak commit about 3.2 GB.
- If `smoke/o0_l2_*.json` are copied into `cells/`, the o0 l2 step is skipped (same code), and
  the total is about 5 h. The single longest run is CBF-P at level 2 (about 15 min).
- `chain_steps.json`: 18 restartable steps, same format as `local_tools/revision/chains.json`:
  gate 1, gate 2, one step per cell (`run_backfill.py --rep R --level L`), then `make_table.py`.
  A cell step skips each policy whose JSON exists. Each step sets 2 numba/OMP threads. The
  runner sets BelowNormal priority itself.

## Limits of this comparison

- Slack uses the "now+anchor" candidate set, not the paper's full loop over every slot. The
  full loop costs O(W^3) per event, and the FCFS queue reaches 10,020 jobs on o0 l2. See the
  header of `evidence/llm_batching/backfill/trace_backfill.py`.
- The overrun step for predicted estimates is my rule (see Design).
