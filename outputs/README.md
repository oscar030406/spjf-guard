# outputs

The result tables of the runs that the revised manuscript reports, as the package wrote
them. Each directory is what one command writes. Its `manifest.json` records the
command's arguments, the configuration and the SHA-256 of its inputs and outputs.
Rerunning the command (top-level README, "Instructions to replicators", and
`GENERATED.md`) overwrites the directory. To check a rerun, compare its files byte by byte
with this copy. The package keeps only summary tables, manifests and logs, with every file
that the manuscript's source names. Per-job files (compressed per-job score deltas and
resumption checkpoints) are left out. The same commands regenerate them.

The results of the separate studies added in the revision are not here: the folder
named out in each study under `evidence/revision_r1/` holds them.

Section numbers below are those of the revised manuscript. Numbers that start with S
refer to the Supplementary Materials. The table-by-table list is in the top-level README.

| Directory | Written by | Used in |
|---|---|---|
| `selection_v4/` | `scripts/select_parameters.py` (validation overlays, 258 candidates, 15 cells) | Section 8.1; Figure S1; Sections S3.11, S5.2, S5.4 |
| `selection_v3/` | `scripts/select_parameters.py`, the earlier grid run of 2026-09-21 | Table S17; Sections S3.11, S5.1, S5.2 |
| `selection_aging/` | `scripts/select_aging.py` | Table S11; Figure S1; Sections S3.8, S5.2, S5.4 |
| `dev_tables/`, `dev_tables/k1/` | `scripts/run_main.py` (five overlays × three loads; `k1/` is the single server) | Tables 9, 10, 12, S6–S10, S16, S18, S21; Figures 6, S1; Sections 1, 8.2, 8.4, 8.5, 10; S3, S5.3, S6.5, S11 |
| `dev_predictor/` | `scripts/eval_scores.py --pool primary` | Tables 13, S13, S18; Section 8.2; Sections S3.9, S5.1 |
| `dev_visibility/` | `scripts/run_visibility.py` | Tables 9, 10, S12, S18; Figure S1; Section 8.4; Sections S3.7, S5.2, S5.3 |
| `dev_consistent_visibility/` | `scripts/run_consistent_visibility.py` | Table 7; Section 8.1; Section S3.7 |
| `dev_online_visibility/` | `scripts/run_online_visibility.py --pool primary` | Tables 7, 10, S31, S38; Figure 5; Sections 1, 8.1, 8.4, 10; Sections S3.7, S11 |
| `dev_online_visibility_k1/`, `online_top1short/`, `online_top1short_k1/` | `scripts/run_online_visibility.py` on the single-server trace, and with the short-job base score (`GENERATED.md`) | Sections S3.4 (the short-job base score) and S3.6 (the single server) |
| `online_paired/` | `scripts/online_paired_differences.py` | Tables 9, 10, S32, S33, S38; Sections 8.1, 8.3, 8.4; Section S11 |
| `online_probe/` | `scripts/run_online_visibility.py`, a one-cell probe | Section S3.7 |
| `online_selection/` | `scripts/select_online.py`, then `scripts/run_online_visibility.py --pool validation` | the restricted reselection of Sections 7.3 and 8.1 |
| `cluster_bootstrap/` | `scripts/run_cluster_bootstrap.py --resamples 100` | Table S18; Section 7.2; Section S5.3 |
| `online_cluster_bootstrap/` | `scripts/run_online_cluster_bootstrap.py --resamples 100` | Sections 1, 7.2; Table S38 (Section S13.5) |
| `paper_tables/` | `scripts/emit_paper_tables.py` (table bodies, and `numbers.csv` listing every printed number with its source row and column) | Tables S4–S10, S16; Figures S2, S3 |
| `consistent_paper_tables/` | `scripts/emit_paper_tables.py --dev-exact-dir … --dev-online-dir …` | Tables 7, 8, S18, S27–S31; Sections S3.7, S5.3 |
| `sensitivity_term2019/`, `sensitivity_submit/` | `scripts/run_main.py` with `configs/sensitivity_term2019_20260926.yaml` and `configs/sensitivity_submit_20260926.yaml`, and their online runs (`online/`, `online_v2/`) | Section S3.15 |
| `sensitivity_coend_merged/`, `sensitivity_coend_dropped/` | `scripts/build_coending_overlays.py`, `scripts/run_main.py` and `scripts/run_coending_online.py` with `configs/sensitivity_coend_*_20260927.yaml` | Section S3.15 |
| `sealed_tables/` | the one run on the sealed semesters (`docs/sealed_run_procedure.md`, Section 3) | Sections 8.2, 10; Section S10; through `consistent_paper_tables/`, Tables S27–S30 |
| `sealed_online_visibility/` | the same sealed run | Sections 1, 8.2, 10 |
| `sealed_consistent_visibility/`, `sealed_predictor/` | the same sealed run | Section 8.2 |
| `sealed_dev_contrast/` | `scripts/sealed_dev_contrast.py` | Table 8; Section 8.2 |
| `accoding_heldout_sealed_online_v2/` | `scripts/run_accoding_heldout.py --block sealed`, under `protocol_lock_accoding.json` (run once, 2026-10-03) | Section 8.2; Table S36; Section S13.2 |
