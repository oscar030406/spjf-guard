# Time-limit sensitivity and a validation-only choice of family

Two studies share this folder, its code tag and its runner helpers.

**Question.**

- `limit/`: Reviewer 3, Comment 3. How close does the worst observed excess come to the
  guaranteed bound when the service's time limit L is 45, 60, 90 or 120 s?
- `family/`: Reviewer 1, Comment 5. The guard family and a coarse grid were explored on the
  primary pool before the selection rule existed. Suppose that the rule chooses among all
  families at once and sees only the validation overlays. Which family does it choose, and
  how does that choice do on the primary pool?

**Paper items.** Figure 5(b), from `limit/limit_summary.csv` (drawn by
`../revision_r1/figures/make_bound_observed.py`). The paragraph on the validation-only
reselection in §7.3, from `family/select_families.py` (the rule), `family/choices.csv`,
`family/evaluation.csv` and `family/gates.txt`.

**Inputs.** Development overlays only, under the online replay of the package
(`scripts/run_online_visibility.py`, imported as `rov` and not changed). The time-limit
study reads the primary pool. The family choice reads the validation pool, and its
evaluation reads the primary pool. The package's tables `outputs/dev_online_visibility`
and `outputs/online_selection` give the reference rows and the grid of the three guard
shapes. No sealed semester is opened.

**Status.** Complete. Both job sets were complete by 5 October 2026: 46 time-limit jobs and
45 validation jobs. `limit/limit_summary.csv` has 168 rows, 0 missing. `family/choices.csv`
has 60 rows, `family/evaluation.csv` 27 rows, and no primary-pool run was missing. All
gates passed.

---

## Shared code

- `_setup.py`: paths, and the code tag. Output folders must carry the tag, the first
  eight hex digits of the sha256 of the runner files. Final tags: `871d6845` (time limit)
  and `41e70726` (family). The family tag includes `../skipc_block_online/block_kernel.py`.
- `fixed_point.py`: after the online replay, feeds the final scores back into the static
  simulator and requires the same waits, starts and (except for Timeout) dispatch order.
  `fixed_point_selftest.py` checks it on small samples of the package
  (`fixed_point_selftest.txt`: all checks passed).
- `memcheck.ps1`, `memready.ps1`: Windows memory probes used to decide when a job could
  start (free physical memory and commit).

## Time limit (`limit/`)

- **Configurations.** `make_configs.py` copies `configs/main.yaml` byte for byte and changes
  only `clock.limit_s` (`main_L45.yaml` to `main_L120.yaml`). `main_L60.yaml` equals
  `main.yaml`.
- **What changes with L.** `run_limit.py` replaces five names of `rov` in the parent and in
  every worker.
  - The predictors, features and heavy labels stay those of the frozen pipeline at
    L = 60 s. The archived models were trained on min(C, 60 s), and runs longer than 60 s
    exist before 2019-08-28. Therefore, a refit at another L would fail the package's check
    that the refit reproduces the archived scores.
  - The stored service times, already min(C, 60 s), are cut at L. They do not change for
    L ≥ 60 s.
  - The policies are built at the given L: B_max = k(G − (3 − 2/k)L) and
    N = floor(Gk/L − (2k − 2)). A policy without a budget, G ≤ (3 − 2/k)L or N < 1, is FCFS.
    It is reported with status FCFS and not replayed. At L = 120 s this applies to
    Guard(300) and Fixed(300) (`check_suite.txt`).
  - Every run checks the per-job bound at the given L, and `fixed_point.py` checks the final
    scores.
- **Policies.** SPJF-E, Guard(G), Fixed(G) and Skip(G) for G in {300, 600, 1200} s, on the
  online clock, with the original clock as reference.
- **At L = 45 s.** The arrival instants and the server counts stay those of the stored
  trace. FCFS and SJF are recomputed on the cut trace, so gap closed at L = 45 s is
  normalised by another reference.
- **Gates.**
  1. At L = 60 s, the cell overlay 0, level 2 equals `outputs/dev_online_visibility/
     online_cells.csv` in all 20 rows and 20 columns. `gate1.txt` is the run under the
     code before the fixed-point check (tag 841db3a1), and `gate1_871d6845.txt` is the
     run under the final code, compared on 20 October 2026. The online audit found 0
     mismatches for each of the 10 policies.
  2. Every guarded run checks the bound on every job (for example Guard(300), k = 4,
     L = 60 s: largest W − W_FCFS 223.3 s over 17,634,760 jobs; `logs/gate_L60_o0_l2.log`).
  3. `fixed_point_selftest.py`: 24 feed-back checks equal; the cut at L = 45 s gives
     [1, 44.5, 45, 45, 45] s on the test input.
- **Jobs and summary.** `jobs_proposed.txt` (46 jobs: the gate cell again, a smoke cell at
  L = 45 s, and L = 45, 90 and 120 s on the 15 primary cells; SPJF-E is not rerun at 90
  and 120 s). `summarize.py` writes `limit_summary.csv` (`summarize_run.log`).

## Family choice (`family/`)

- **The rule** is the docstring of `select_families.py`, written before any result of a new
  family was seen. Before we wrote it, we had seen three sets of primary-pool
  values. The first is the header of `outputs/dev_online_visibility/online_cells.csv` and
  its two SPJF-E rows of overlay 0, level 0. The second is the fired column of some
  Fixed(1200) rows of the same file. The third is one unlabelled column of
  `outputs/online_selection/evaluation/online_cells.csv`. The last two
  were read with a wrong column number.
- **Families and grids.** The three guard shapes (258 points of the existing grid, with
  Fixed(G)); Skip(G) and Skip(n = m) with N = floor(m·k/4), m in {4, 8, 16, 32, 64};
  Timeout(G) and Timeout with θ in {15, 30, 60, 120, 240, 480, 960} s; linear aging with the
  configuration's 11 credits; ordering by score within fixed blocks of W arrivals,
  W in {8, 32, 128, 512}. Aging and blocks carry no promise.
- **Choice.** For each G in {300, 600, 1200} s, on the 15 validation cells, on the online
  clock with the original clock as reference: worst gap closed, worst harm and worst
  realised promise. A point labelled with G is a candidate at G. An unlabelled point is a
  candidate when its worst promise is at most G. Aging and Block points are candidates at
  every G. A candidate is feasible when its worst harm is at most G/2. Within a family: largest worst gap, then smaller harm, then smaller
  parameter. Across families: the three guard shapes jointly by the package's joint rule,
  then the best of Guard, Skip, Timeout, Aging and Block.
- **Evaluation.** `evaluate.py` reports the primary-pool rows of each choice beside the
  paper's Guard(G). Nothing feeds back into the choice. Command:
  `evaluate.py --choices family/choices.csv`. Run from this copy on 20 October 2026, it
  rewrote `evaluation.csv` and `jobs_primary.txt` byte for byte.
- **Gates** (`select_families.py gates`, `gates.txt`: 0 gate failures).
  1. The same selection code, run on the existing grid of the three guard shapes, gives
     the 24 rows of `online_choices_all.csv` in all 14 columns.
  2. For aging, the rule picks the credit that the package's `select_aging._choose` picks,
     0.1, on both clocks.
- **Runs.** `rov` runs Skip(G), Timeout(G) and Timeout(θ) itself. `run_family.py` adds
  Skip(n = m), Aging and Block(W) to it. Block(W) uses the kernel of
  `../skipc_block_online`. `make_jobs.py` wrote `jobs_proposed.txt` (45
  validation jobs). `choose_run.log` and `evaluate_run.log` are the final runs.
