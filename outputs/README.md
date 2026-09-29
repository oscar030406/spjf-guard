# outputs

The result tables of the runs the submitted manuscript reports, as the package wrote
them before the submission. Each directory is what one command writes; its
`manifest.json` records the command's arguments, the configuration and the SHA-256 of
its inputs and outputs. Rerunning the command (top-level README, "Instructions to
replicators") overwrites the directory, and a byte comparison with this copy is the
check. Only summary tables, manifests and logs are kept. Per-job files (compressed
per-job score deltas and resumption checkpoints, 3.5 GB in all) are left out; the same
commands regenerate them.

Section numbers below are those of the manuscript; S-numbers are the Supplementary
Materials. The table-by-table list is in the top-level README.

| Directory | Written by | Used in |
|---|---|---|
| `selection_v4/` | `scripts/select_parameters.py` (validation overlays, 258 candidates, 15 cells) | Section 8.1; Figure S1; Sections S3.11, S5.2, S5.4 |
| `selection_v3/` | `scripts/select_parameters.py`, the earlier grid run of 2026-09-21 | Table S17; Sections S3.11, S5.1, S5.2 |
| `selection_aging/` | `scripts/select_aging.py` | Table S11; Figure S1; Sections S3.8, S5.2, S5.4 |
| `dev_tables/`, `dev_tables/k1/` | `scripts/run_main.py` (five overlays × three loads; `k1/` is the single server) | Tables 7, 8, S6–S10, S16, S18, S21; Figure S1; Sections 1, 8.2, 8.4, 8.5, 10; S3, S5.3, S6.5, S11 |
| `dev_predictor/` | `scripts/eval_scores.py --pool primary` | Tables 9, S13, S18; Section 8.2; Sections S3.9, S5.1 |
| `dev_visibility/` | `scripts/run_visibility.py` | Tables 7, 8, S12, S18; Figure S1; Section 8.4; Sections S3.7, S5.2, S5.3 |
| `dev_consistent_visibility/` | `scripts/run_consistent_visibility.py` | Table 5; Section 8.1; Section S3.7 |
| `dev_online_visibility/` | `scripts/run_online_visibility.py --pool primary` | Tables 5, 8, S31; Sections 1, 8.1, 8.4, 10; Sections S3.7, S11 |
| `online_paired/` | `scripts/online_paired_differences.py` | Tables 7, 8, S32, S33; Sections 8.1, 8.3, 8.4; Section S11 |
| `online_probe/` | `scripts/run_online_visibility.py`, a one-cell probe | Section S3.7 |
| `online_selection/` | `scripts/select_online.py`, then `scripts/run_online_visibility.py --pool validation` | the restricted reselection of Section 8.1 |
| `cluster_bootstrap/` | `scripts/run_cluster_bootstrap.py --resamples 100` | Table S18; Section 7.2; Section S5.3 |
| `paper_tables/` | `scripts/emit_paper_tables.py` (table bodies, and `numbers.csv` listing every printed number with its source row and column) | Tables S4–S10, S16; Figures S2, S3 |
| `consistent_paper_tables/` | `scripts/emit_paper_tables.py --dev-exact-dir … --dev-online-dir …` | Tables 5, 6, S18, S27–S31; Sections S3.7, S5.3 |
| `sensitivity_term2019/`, `sensitivity_submit/` | `scripts/run_main.py` with `configs/sensitivity_term2019_20260926.yaml` and `configs/sensitivity_submit_20260926.yaml` | Section S3.15 |
| `sealed_tables/` | the one run on the sealed semesters (`docs/sealed_run_procedure.md`, Section 3) | Sections 8.2, 10; Section S10; through `consistent_paper_tables/`, Tables S27–S30 |
| `sealed_online_visibility/` | the same sealed run | Sections 1, 8.2, 10 |
| `sealed_consistent_visibility/`, `sealed_predictor/` | the same sealed run | Section 8.2 |
| `sealed_dev_contrast/` | `scripts/sealed_dev_contrast.py` | Table 6; Section 8.2 |
