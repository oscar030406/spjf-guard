# Gain against the quality of the scores

**Question.** Reviewer 3, Comment 4: how does the gain of prediction-driven ordering
depend on the quality of the predictions? Does the guarantee hold with poor ones? The
study degrades two scores step by step, adds random scores, and runs each score unguarded
and under the three guards on the 15 cells of Table 9.

**Paper items.** Figure 4 and the last paragraph of §8.3, from `out/noise_dose_table.csv`
(level 2 rows). `../figures/make_noise_dose.py` draws the figure.

**Inputs.** The five development overlays (`data/derived/overlay_traces/primary_rep*.npz`),
the stored SPJF-E scores (`forward_scores.parquet`, column `spjf_e`, by `job_row`),
`outputs/selection_v4/selected_parameters.csv` (the selection file of the main table, and the
run stops if it disagrees with the configuration), and
`outputs/dev_tables/main_cells.csv` for the gates.

**Status.** Complete. The chain ran all 7 steps on 18 October 2026. The final gate
compared 135 rows with `main_cells.csv`: 0 differ, and 0 bound violations over all guarded
rows (`out/chain_r1_noise_dose.log`, last lines).

---

## Design

`noise_dose.py` builds the degraded rows with the package's own code path, in the order
of `scripts/run_main.py`: `attach_adversarial`, `adversarial.adversarial_score`,
`run_cell` and `spjf_guard.experiment.parallel._run`. It imports these and copies none.

- **Scores.** For each noise seed, one standard normal Z per submission row (863,149 rows),
  indexed by `job_row`, so the copies of one submission share one error. All σ and both
  sources use the same Z.
  - `true`: service time × exp(σZ). At σ = 0 this is the order of SJF.
  - `spjf_e`: the stored SPJF-E score × exp(σZ).
  - `random`: `adversarial_score("random", ...)`, the code `run_main` uses.
- **Grid.** σ in {0, 0.25, 0.5, 1, 1.5, 2, 3}, one array per source at σ = 0. Noise seeds
  20261018, 20261019 and 20261020. Random seeds 3 (the paper's `cfg.overlay.seed`), 1003
  and 2003. This gives 41 arrays per overlay.
- **Policies.** Each array runs unguarded (SPJF) and under Guard(300), Guard(600) and
  Guard(1200) with the jointly selected parameters. Every cell also runs FCFS and SJF.
  This gives 165 simulations per cell. Every simulation goes through `parallel._run`,
  which checks the per-job bound inside the run. No bootstrap.
- **Quality.** Computed per (overlay, array), the same at every load, sampling seed
  20261021.
  - `spearman`: Spearman correlation on a fixed subsample of 2 million jobs.
  - `auroc`: concordance on 2 million fixed random pairs. Pairs with equal cost are
    dropped, and tied scores count 1/2.
  - `auroc_ratio2`: the same pairs, kept when one cost is at least twice the other.
  - `auroc_top1pct`: the AUROC with which the score ranks the longest 1% of jobs above the
    rest. Figure 4 uses this as its horizontal axis, because the global Spearman
    correlation and the pairwise AUROC do not put the two sources on one curve.

## Outputs

- `cells/rep{o}_level{l}.csv` and `quality/rep{o}.csv`, per cell and per overlay (not
  copied here).
- `out/noise_dose_by_seed.csv`: per seed, the mean over overlays of p99, gap closed, mean
  wait and quality; the maximum over overlays of excess, harm and used/allowed bound;
  violations summed.
- `out/noise_dose_table.csv`: the mean over seeds, with the minimum and maximum gap closed
  over seeds.
- `out/manifest.json`: inputs and settings of the run.

## Gates

`noise_dose.py gate` compares k, n_jobs, seven summary fields and gap_closed with
`outputs/dev_tables/main_cells.csv` by exact equality.

1. The true cost at σ = 0 and the SJF reference both equal SJF. The stored SPJF-E score at
   σ = 0 equals the SPJF-E row. Guard(300), Guard(600) and Guard(1200) on the stored scores
   equal their rows.
2. The random score with seed 3 equals the SPJF-random and Guard(600)-random rows.

On the smoke cell (overlay 0, level 2), 9 rows matched exactly. On the full grid, 135 rows
matched exactly.

## Rerun

`chain_steps.json`: one `cells` step per overlay (about one hour each with 2 workers),
then `table`, then `gate`. Score arrays go to `<cache-dir>/noise_dose/rep{o}`, 41 files of
141 MB per overlay, and are deleted at the end of each overlay. A cell whose CSV exists is
skipped, so a stopped run resumes. Peak commit was below 4.5 GB.
