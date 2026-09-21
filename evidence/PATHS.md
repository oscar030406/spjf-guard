# Path map: `prechecks/…` → `evidence/…`

The source comments in `paper/sections/*.tex` and `paper/supplementary.tex` name the
evidence file behind each number, under the working folder name `prechecks/`. This folder
is the published copy of that material. The mapping is one-to-one on the folder name:

    prechecks/<study>/<file>   →   evidence/<study>/<file>

File names, directory layout and log contents are unchanged, so any path in a paper
comment can be rewritten by replacing the first component. The table below lists every
path the paper currently names, with the place that names it, so the change can be made
and checked line by line.

## Paths named in paper source comments

| paper location | current path | new path |
| --- | --- | --- |
| `04_prediction.tex:184` | `prechecks/predictor_neural/out_evaluate_core.txt` | `evidence/predictor_neural/out_evaluate_core.txt` |
| `04_prediction.tex:186` | `prechecks/codebench_service_v2/out_service_v2.txt` | `evidence/codebench_service_v2/out_service_v2.txt` |
| `04_prediction.tex:187` | `prechecks/accoding_v2/out_accoding_v2.txt` | `evidence/accoding_v2/out_accoding_v2.txt` |
| `04_prediction.tex:195` | `prechecks/cross_domain/out_cross_domain_table.txt` | `evidence/cross_domain/out_cross_domain_table.txt` |
| `07_data.tex:70` | `prechecks/codebench_audit/out_tail_and_counts.txt` | `evidence/codebench_audit/out_tail_and_counts.txt` |
| `07_data.tex:71` | `prechecks/accoding_v2/out_accoding_v2.txt` | `evidence/accoding_v2/out_accoding_v2.txt` |
| `07_data.tex:73` | `prechecks/codebench_service_v2/out_service_v2.txt` | `evidence/codebench_service_v2/out_service_v2.txt` |
| `07_data.tex:74` | `prechecks/accoding_v2/out_accoding_v2.txt` | `evidence/accoding_v2/out_accoding_v2.txt` |
| `07_data.tex:75` | `prechecks/cross_domain/out_audit_azure.txt` | `evidence/cross_domain/out_audit_azure.txt` |
| `07_data.tex:76` | `prechecks/firefox_ci/out_SUMMARY.txt`, `out_simval.txt` | `evidence/firefox_ci/out_SUMMARY.txt`, `out_simval.txt` |
| `07_data.tex:77` | `prechecks/cross_domain/out_audit_netbatch.txt` | `evidence/cross_domain/out_audit_netbatch.txt` |
| `07_data.tex:78` | `prechecks/oulad/out_load.txt` | `evidence/oulad/out_load.txt` |
| `07_data.tex:191` | `prechecks/firefox_ci_holdout/out_SUMMARY.txt` | `evidence/firefox_ci_holdout/out_SUMMARY.txt` |
| `07_data.tex:262` | `prechecks/codebench_audit/out_tail_and_counts.txt` | `evidence/codebench_audit/out_tail_and_counts.txt` |
| `07_data.tex:264` | `prechecks/accoding_v2/out_accoding_v2.txt` | `evidence/accoding_v2/out_accoding_v2.txt` |
| `07_data.tex:266` | `prechecks/cross_domain/out_cross_domain_table.txt` | `evidence/cross_domain/out_cross_domain_table.txt` |
| `07_data.tex:268` | `prechecks/firefox_ci/out_SUMMARY.txt` | `evidence/firefox_ci/out_SUMMARY.txt` |
| `08_experiments.tex:52` | `prechecks/main_v3/out_main_v31.txt` | `evidence/main_v3/out_main_v31.txt` |
| `08_experiments.tex:90` | `prechecks/main_v3/out_main_v32.txt` | `evidence/main_v3/out_main_v32.txt` |
| `08_experiments.tex:158` | `prechecks/main_v3` — **body text**, not a comment | `evidence/main_v3` |
| `08_experiments.tex:171` | `prechecks/main_v3/out_main_v31.txt` | `evidence/main_v3/out_main_v31.txt` |
| `08_experiments.tex:206` | `prechecks/ranking_score/out_table_primary_5reps.txt` | `evidence/ranking_score/out_table_primary_5reps.txt` |
| `08_experiments.tex:212` | `prechecks/ranking_score/out_sim_primary_rep0_twoclass.txt` | `evidence/ranking_score/out_sim_primary_rep0_twoclass.txt` |
| `08_experiments.tex:225` | `prechecks/ranking_score/out_sim_primary_rep0_mech.txt` | `evidence/ranking_score/out_sim_primary_rep0_mech.txt` |
| `08_experiments.tex:530` | `prechecks/main_v3_verify/out_VERDICT.txt` | `evidence/main_v3_verify/out_VERDICT.txt` |
| `08_experiments.tex:531` | `prechecks/main_v3/out_main_v31.txt` | `evidence/main_v3/out_main_v31.txt` |
| `08_experiments.tex:617` | `prechecks/codebench_audit/out_tail_and_counts.txt` | `evidence/codebench_audit/out_tail_and_counts.txt` |
| `08_experiments.tex:618` | `prechecks/codebench_service_v2/out_service_v2.txt` | `evidence/codebench_service_v2/out_service_v2.txt` |
| `08_experiments.tex:621` | `prechecks/cross_domain/out_cross_domain_table.txt` | `evidence/cross_domain/out_cross_domain_table.txt` |
| `08_experiments.tex:628` | `prechecks/cross_domain/out_cross_domain_table.txt` | `evidence/cross_domain/out_cross_domain_table.txt` |
| `08_experiments.tex:631` | `prechecks/accoding_v2/out_accoding_v2.txt` | `evidence/accoding_v2/out_accoding_v2.txt` |
| `08_experiments.tex:633` | `prechecks/firefox_ci/out_SUMMARY.txt` | `evidence/firefox_ci/out_SUMMARY.txt` |
| `08_experiments.tex:640` | `prechecks/firefox_ci_holdout/out_SUMMARY.txt` | `evidence/firefox_ci_holdout/out_SUMMARY.txt` |
| `08_experiments.tex:701` | `prechecks/codebench_service_v2/out_service_v2.txt` | `evidence/codebench_service_v2/out_service_v2.txt` |
| `A_proofs.tex:449` | `prechecks/guard_theory/rev5_items.py` | `evidence/guard_theory/rev5_items.py` |
| `A_proofs.tex:450` | `prechecks/guard_theory/out_rev5_items.txt` | `evidence/guard_theory/out_rev5_items.txt` |
| `supplementary.tex:137` | `prechecks/cross_domain/out_cross_domain_table.txt` | `evidence/cross_domain/out_cross_domain_table.txt` |
| `supplementary.tex:139` | `prechecks/firefox_ci/out_SUMMARY.txt` | `evidence/firefox_ci/out_SUMMARY.txt` |
| `supplementary.tex:212` | `prechecks/codebench_audit/out_tail_and_counts.txt` | `evidence/codebench_audit/out_tail_and_counts.txt` |
| `supplementary.tex:213` | `prechecks/codebench_service_v2/out_service_v2.txt` | `evidence/codebench_service_v2/out_service_v2.txt` |
| `supplementary.tex:216` | `prechecks/firefox_ci_holdout/out_SUMMARY.txt` | `evidence/firefox_ci_holdout/out_SUMMARY.txt` |
| `supplementary.tex:531` | `prechecks/guard_theory` | `evidence/guard_theory` |

Line numbers are as of the state of `paper/` when this folder was assembled; the path
strings are what to search for.

## Paths named elsewhere in the repository

These are not paper comments, but they name the same material and will break in the same
way if only the paper is updated.

| location | current path | new path |
| --- | --- | --- |
| `GENERATED.md` (reproduction row, diff row) | `prechecks/main_v3/v31/table_main_primary.csv` | `evidence/main_v3/v31/table_main_primary.csv` |
| `GENERATED.md` (single-server row) | `prechecks/main_v3/v31/table_main_k1.csv` | `evidence/main_v3/v31/table_main_k1.csv` |
| `GENERATED.md` (inputs table) | `prechecks/codebench_service_v2/` | `evidence/codebench_service_v2/` |
| `GENERATED.md` (inputs table) | `prechecks/ranking_score/rs_fit.py` | `evidence/ranking_score/rs_fit.py` |
| `GENERATED.md` (inputs table) | `prechecks/main_v3/v31/primary_rep*.npz` | **no new path** — see below |
| `README.md` (contents, steps 2 and 5, conclusions) | `prechecks/` | `evidence/` |

`prechecks/main_v3/v31/primary_rep*.npz` is the one row that does not map. Those overlay
traces are rebuilt into the cache directory by `v31_build.py` and are not on disk under
that path; `scripts/check_overlays.py` needs them rebuilt before it can compare against
them. The row in `GENERATED.md` should say so.

## Inside the copied files

`.md` and `.py` files in this folder had their own `prechecks/…` cross-references
rewritten to `evidence/…`, so the studies point at each other correctly. The `out_*.txt`
run logs were **not** touched — they are run output and still print `prechecks/<study>/`.
Read those as `evidence/<study>/`.
