# Skip charged at completion and fixed-block ordering under the online replay

**Question.** Two baselines of §8.4 were first run on the original clock: a count of
overtakes charged when an overtaker completes (SKIPC) and ordering by score within fixed
blocks of W arrivals (Block(W)). Do they behave the same under the online replay? The
family choice of `../limit_family_selection` also needs Block(W) on that replay.

**Paper items.** No number in the paper comes from this folder. The §8.4 sentences on
charging at completion and on Block(512) cite the original-clock runs
(`../main_v3/v31/report_diff.csv`, `../referee_round4/maxwait_overlay0.csv`). The
Block(W) kernel here is the one that `../limit_family_selection/family/run_family.py` runs.

**Inputs.** Development overlays only, under the package's online replay
(`scripts/run_online_visibility.py`, imported as `rov` and not changed), and the archived
scores of the original-clock runs for gate 2.

**Status.** Complete. The 55 jobs were complete by 5 October 2026, and `summarize.py` ran
on that day (`summarize_run.log`, exit 0). All gates and the summary's own checks passed.

---

## Kernels

Both kernels copy the loop of the package kernel and change only the dispatch rule.

- `skipc_kernel.py`: one switch sets when a skip is charged. Charging at dispatch is the
  package's Skip. Charging at completion is SKIPC, with N = floor(Gk/L − (3k − 2)).
- `block_kernel.py`: the heap orders jobs by (rank // W, score, rank).

`skipc_block_online.py` runs them on the online clock: in each worker it replaces `rov`'s
`_suite` and `_refine` and goes through the fixed-point check with a simulator callback.
`rov`'s checkpoint signature does not cover the code here. Therefore, the output folder name
carries a code tag (`8450d220`, from the sha256 of four files), and the runner refuses an
`--out-dir` without it.

## Gates

1. **Degenerate cases against the package kernel** (`gate1.py`, overlay 0, level 2,
   `out/gate1.csv`). In dispatch-charging mode the kernel equals the package's Skip(300),
   Skip(600) and Skip(1200) (N = 14, 34, 74): 0 differences in the wait, start and
   dispatch arrays. Block(1) equals FCFS, and Block(n) equals SPJF-E. `check_small.py`
   compares 400 random instances with integer seconds, job by job, with the package kernel
   and two earlier SKIPC implementations (`out/check_small.txt`).
2. **Original clock reproduced.**
   - Block(W) (`gate2_block.py`): the scores stored in the overlay equal the package's
     `spjf_e` on all 17,634,760 jobs. The 21 rows of
     `../referee_round4/maxwait_overlay0.csv` (12 Block
     rows, 9 reference rows) are equal in every field, and every start time equals the
     earlier `simulate_rule` (`out/gate2_block.txt`).
   - SKIPC (`gate2_skipc.py`, 15 cells): with the earlier code, the nine SKIP − SKIPC rows
     of `../main_v3/v31/gaindiff_primary.csv` and the SKIP and SKIPC rows of
     `../main_v3/v31/table_main_primary.csv` are equal at full precision. With the new kernel on integer microseconds, the nine
     printed strings of `../main_v3/v31/report_diff.csv` are the same. Job by job, 1,368 SKIPC starts
     differ from the earlier kernel on the same microsecond inputs, about 0.0002% of
     some 790 million comparisons. All come from boundary comparisons that the earlier
     floating-point clock flipped (`out/gate2_skipc.txt`).
3. **Online fixed point.** In the smoke run, each of the three policies fed its final scores
   back into the static kernel and got the same waits, starts and dispatch order. The audit
   of 4,000 jobs per policy found 0 mismatches.
4. **Bound.** SKIPC asserts k(W − W_FCFS) ≤ (N + 3k − 2)L on every job in integers:
   793,564,200 job results in gate 2 and 35,269,520 per policy in the smoke run, 0
   violations. `rov` asserts the package's bound for Skip. Block(W) has no promise.

The smoke run's Skip(300) row equals the Skip(300) row of
`outputs/dev_online_visibility` in every field on both clocks (`out/summary_controls.csv`).

## Jobs and summary

`jobs_proposed.txt` has 55 jobs, one per policy and cell: 44 for SKIPC (three G on 15
cells, less the smoke cell) and 11 for Block(W) (four windows on overlay 0 at three loads,
less the smoke cell). `summarize.py --run outputs/skipc_block_online_8450d220` writes
`out/summary.txt`, `summary_g4.csv` (SKIPC), `summary_g4_cells.csv`, `summary_g5.csv`
(Block(W)) and `summary_controls.csv`. It checks that the reference rows equal
`dev_online_visibility` on both clocks, that the SKIPC and Block rows equal their
re-simulations, and that the original-clock Block rows equal
`../referee_round4/maxwait_overlay0.csv`.

Gate 2 and the summary report different intervals. Gate 2 follows the earlier rule
(resamples without row 0), and `summarize.py` follows
`scripts/online_paired_differences.py` (with row 0).
