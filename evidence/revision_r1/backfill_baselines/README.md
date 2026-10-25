# Backfilling baselines

**Question.** Reviewer 2, Comment 3: how do conservative backfilling (CBF) and
slack-based backfilling compare with the guard under the same promise, on the 15 cells of
the main table?

**Paper items.** Table 11 and its paragraph in §8.4 (`out/backfill_cells.csv`,
`out/backfill_table.csv`, `out/tab_backfill_body.tex`); Supplementary Section S13.4, the
rules and their checks (`out/gate1_random.txt`, `out/gate2_prefix.txt`).

**Inputs.** The five development overlays at the three loads of the main table, the stored
SPJF-E scores (`forward_scores.parquet`, by `job_row`), `outputs/dev_tables/main_cells.csv`
(FCFS check, SJF and SPJF-E rows) and `outputs/dev_online_visibility/online_cells.csv`
(Guard and Timeout rows, variant original).

**Status.** Complete. The chain ran all 18 steps on 18 October 2026
(`out/chain_r1_backfill.log`). Gates 1 and 2 found 0 differing starts.

---

`REPORT.md` gives the design, the gates and the results. Code: `bf_kernel.py` (numba
kernel), `run_backfill.py` (one cell), `make_table.py`, `make_tex_table.py`, and the gates
`gate1_random.py` and `gate2_prefix.py` with `ref_est.py`. `chain_steps.json` lists the
steps in order.

## What runs from this folder

The kernel, the cell runner and the tables need only the package in `src/`. Gates 1 and 2
and `ref_est.py` also import modules of a separate study that is not distributed here.
These modules are the reference implementations of the two rules (`backfill.py` and
`backfill_ref.py`, under `evidence/llm_batching/backfill/` in the scripts' paths) and two
helpers of that study (`check_overtaking_cost.fcfs_list`, and `check_prefix_refund.run` and
`Observer`). These
gates therefore do not run from this folder. Their outputs are kept in `out/`.
