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
| `01_introduction.tex:35` | `prechecks/heldout_scope/heldout_scope.md` | `evidence/heldout_scope/heldout_scope.md` |
| `07_data.tex:242` | `prechecks/heldout_scope/heldout_scope.md` | `evidence/heldout_scope/heldout_scope.md` |
| `08_experiments.tex:547` | `prechecks/lpc_egee_queues/applicability.csv` | `evidence/lpc_egee_queues/applicability.csv` |
| `08_experiments.tex:553` | `prechecks/lpc_egee/applicability.csv` | `evidence/lpc_egee/applicability.csv` |
| `08_experiments.tex:585` | `prechecks/lpc_egee/capacity.json` | `evidence/lpc_egee/capacity.json` |
| `08_experiments.tex:597` | `prechecks/lpc_egee_queues/tables.md` | `evidence/lpc_egee_queues/tables.md` |
| `08_experiments.tex:659` | `prechecks/lpc_egee_queues/applicability.csv` | `evidence/lpc_egee_queues/applicability.csv` |
| `08_experiments.tex:662` | `prechecks/lpc_egee/bound_checks.csv` | `evidence/lpc_egee/bound_checks.csv` |
| `08_experiments.tex:677` | `prechecks/weakness1_attack/summary_numbers.json` | `evidence/weakness1_attack/summary_numbers.json` |
| `08_experiments.tex:687` | `prechecks/weakness1_attack/physical_numbers.json` | `evidence/weakness1_attack/physical_numbers.json` |
| `08_experiments.tex:689` | `prechecks/weakness1_attack/physical_verification.json` | `evidence/weakness1_attack/physical_verification.json` |
| `08_experiments.tex:722` | `prechecks/closed_loop/out/open_vs_closed_mean.csv` | `evidence/closed_loop/out/open_vs_closed_mean.csv` |
| `09_limitations.tex:56` | `prechecks/closed_loop/out/` | `evidence/closed_loop/out/` |
| `09_limitations.tex:185` | `prechecks/lpc_egee/validation.csv` | `evidence/lpc_egee/validation.csv` |
| `09_limitations.tex:187` | `prechecks/lpc_egee_queues/guard_dispatches.csv` | `evidence/lpc_egee_queues/guard_dispatches.csv` |
| `S_theory_additions.tex:36` | `prechecks/guard_optimality_verify/literature_check.md` | `evidence/guard_optimality_verify/literature_check.md` |
| `S_theory_additions.tex:37` | `prechecks/guard_optimality_verify/verification.md` | `evidence/guard_optimality_verify/verification.md` |
| `S_theory_additions.tex:52` | `prechecks/guard_optimality_verify/out_t1.txt` | `evidence/guard_optimality_verify/out_t1.txt` |
| `S_theory_additions.tex:53` | `prechecks/guard_optimality_verify/verification.md` | `evidence/guard_optimality_verify/verification.md` |
| `S_theory_additions.tex:91` | `prechecks/guard_optimality_verify/out_t2.txt` | `evidence/guard_optimality_verify/out_t2.txt` |
| `S_theory_additions.tex:92` | `prechecks/guard_optimality_verify/verification.md` | `evidence/guard_optimality_verify/verification.md` |
| `S_theory_additions.tex:230` | `prechecks/guard_optimality_verify/out_t3.txt` | `evidence/guard_optimality_verify/out_t3.txt` |
| `S_theory_additions.tex:231` | `prechecks/guard_optimality_verify/verification.md` | `evidence/guard_optimality_verify/verification.md` |
| `S_theory_additions.tex:293` | `prechecks/reservation_guard_verify/verification.md` | `evidence/reservation_guard_verify/verification.md` |
| `S_theory_additions.tex:340` | `prechecks/reservation_guard_verify/verification.md` | `evidence/reservation_guard_verify/verification.md` |
| `S_theory_additions.tex:360` | `prechecks/reservation_guard_verify/out_overR_eq_overC_k1.txt` | `evidence/reservation_guard_verify/out_overR_eq_overC_k1.txt` |
| `S_theory_additions.tex:401` | `prechecks/reservation_guard_verify/verification.md` | `evidence/reservation_guard_verify/verification.md` |
| `S_theory_additions.tex:410` | `prechecks/reservation_guard_verify/verification.md` | `evidence/reservation_guard_verify/verification.md` |
| `S_theory_additions.tex:427` | `prechecks/reservation_guard_verify/verification.md` | `evidence/reservation_guard_verify/verification.md` |
| `supplementary.tex:1867` | `prechecks/heldout_scope/heldout_scope.md` | `evidence/heldout_scope/heldout_scope.md` |
| `supplementary.tex:1984` | `prechecks/weakness1_attack/REPORT.md` | `evidence/weakness1_attack/REPORT.md` |
| `supplementary.tex:2013` | `prechecks/weakness1_attack/capacity_curve.csv` | `evidence/weakness1_attack/capacity_curve.csv` |
| `supplementary.tex:2014` | `prechecks/weakness1_attack/summarize_capacity.py` | `evidence/weakness1_attack/summarize_capacity.py` |
| `supplementary.tex:2036` | `prechecks/weakness1_attack/` | `evidence/weakness1_attack/` |
| `supplementary.tex:2148` | `prechecks/weakness1_attack/summary_numbers.json` | `evidence/weakness1_attack/summary_numbers.json` |
| `supplementary.tex:2149` | `prechecks/weakness1_attack/verification.json` | `evidence/weakness1_attack/verification.json` |
| `supplementary.tex:2150` | `prechecks/weakness1_attack/REPORT.md` | `evidence/weakness1_attack/REPORT.md` |
| `supplementary.tex:2164` | `prechecks/weakness1_attack/summary_numbers.json` | `evidence/weakness1_attack/summary_numbers.json` |
| `supplementary.tex:2165` | `prechecks/weakness1_attack/capacity_curve.csv` | `evidence/weakness1_attack/capacity_curve.csv` |
| `supplementary.tex:2179` | `prechecks/weakness1_attack/capacity_curve.csv` | `evidence/weakness1_attack/capacity_curve.csv` |
| `supplementary.tex:2181` | `prechecks/weakness1_attack/capacity_curve.csv` | `evidence/weakness1_attack/capacity_curve.csv` |
| `supplementary.tex:2183` | `prechecks/weakness1_attack/capacity_curve.csv` | `evidence/weakness1_attack/capacity_curve.csv` |
| `supplementary.tex:2185` | `prechecks/weakness1_attack/capacity_curve.csv` | `evidence/weakness1_attack/capacity_curve.csv` |
| `supplementary.tex:2187` | `prechecks/weakness1_attack/capacity_curve.csv` | `evidence/weakness1_attack/capacity_curve.csv` |
| `supplementary.tex:2189` | `prechecks/weakness1_attack/capacity_curve.csv` | `evidence/weakness1_attack/capacity_curve.csv` |
| `supplementary.tex:2191` | `prechecks/weakness1_attack/capacity_curve.csv` | `evidence/weakness1_attack/capacity_curve.csv` |
| `supplementary.tex:2193` | `prechecks/weakness1_attack/capacity_curve.csv` | `evidence/weakness1_attack/capacity_curve.csv` |
| `supplementary.tex:2210` | `prechecks/weakness1_attack/capacity_curve.csv` | `evidence/weakness1_attack/capacity_curve.csv` |
| `supplementary.tex:2212` | `prechecks/weakness1_attack/summary_numbers.json` | `evidence/weakness1_attack/summary_numbers.json` |
| `supplementary.tex:2222` | `prechecks/weakness1_attack/capacity_curve.csv` | `evidence/weakness1_attack/capacity_curve.csv` |
| `supplementary.tex:2224` | `prechecks/weakness1_attack/pilot.json` | `evidence/weakness1_attack/pilot.json` |
| `supplementary.tex:2237` | `prechecks/weakness1_attack/physical_numbers.json` | `evidence/weakness1_attack/physical_numbers.json` |
| `supplementary.tex:2248` | `prechecks/weakness1_attack/physical_numbers.json` | `evidence/weakness1_attack/physical_numbers.json` |
| `supplementary.tex:2249` | `prechecks/weakness1_attack/physical_verification.json` | `evidence/weakness1_attack/physical_verification.json` |
| `supplementary.tex:2261` | `prechecks/weakness1_attack/physical_numbers.json` | `evidence/weakness1_attack/physical_numbers.json` |
| `supplementary.tex:2263` | `prechecks/weakness1_attack/physical_numbers.json` | `evidence/weakness1_attack/physical_numbers.json` |
| `supplementary.tex:2265` | `prechecks/weakness1_attack/physical_numbers.json` | `evidence/weakness1_attack/physical_numbers.json` |
| `supplementary.tex:2280` | `prechecks/weakness1_attack/physical_numbers.json` | `evidence/weakness1_attack/physical_numbers.json` |
| `supplementary.tex:2292` | `prechecks/weakness1_attack/stall_bound_check.json` | `evidence/weakness1_attack/stall_bound_check.json` |
| `supplementary.tex:2294` | `prechecks/weakness1_attack/physical_verification.json` | `evidence/weakness1_attack/physical_verification.json` |
| `supplementary.tex:2318` | `prechecks/weakness1_attack/out_feedback_counterexamples.txt` | `evidence/weakness1_attack/out_feedback_counterexamples.txt` |
| `supplementary.tex:2330` | `prechecks/weakness1_attack/out_feedback_counterexamples.txt` | `evidence/weakness1_attack/out_feedback_counterexamples.txt` |
| `supplementary.tex:2344` | `prechecks/lpc_egee/applicability.csv` | `evidence/lpc_egee/applicability.csv` |
| `supplementary.tex:2345` | `prechecks/lpc_egee/capacity.json` | `evidence/lpc_egee/capacity.json` |
| `supplementary.tex:2354` | `prechecks/lpc_egee/validation.csv` | `evidence/lpc_egee/validation.csv` |
| `supplementary.tex:2366` | `prechecks/lpc_egee/pooled_policy_metrics.csv` | `evidence/lpc_egee/pooled_policy_metrics.csv` |
| `supplementary.tex:2391` | `prechecks/closed_loop/out/think_time.json` | `evidence/closed_loop/out/think_time.json` |
| `supplementary.tex:2404` | `prechecks/closed_loop/out/validation.json` | `evidence/closed_loop/out/validation.json` |
| `supplementary.tex:2405` | `prechecks/closed_loop/out/closed_cells.csv` | `evidence/closed_loop/out/closed_cells.csv` |
| `supplementary.tex:2443` | `prechecks/closed_loop/out/open_vs_closed_mean.csv` | `evidence/closed_loop/out/open_vs_closed_mean.csv` |
| `supplementary.tex:2446` | `prechecks/closed_loop/out/report_tables.md` | `evidence/closed_loop/out/report_tables.md` |
| `supplementary.tex:2447` | `prechecks/closed_loop/make_tables.py` | `evidence/closed_loop/make_tables.py` |
| `supplementary.tex:2460` | `prechecks/closed_loop/out/open_vs_closed_mean.csv` | `evidence/closed_loop/out/open_vs_closed_mean.csv` |
| `supplementary.tex:2482` | `prechecks/closed_loop/out/open_vs_closed_mean.csv` | `evidence/closed_loop/out/open_vs_closed_mean.csv` |
| `supplementary.tex:2501` | `prechecks/closed_loop/out/bootstrap.json` | `evidence/closed_loop/out/bootstrap.json` |
| `supplementary.tex:2504` | `prechecks/closed_loop/out/report_tables.md` | `evidence/closed_loop/out/report_tables.md` |
| `supplementary.tex:2534` | `prechecks/lpc_egee_queues/bound_checks.csv` | `evidence/lpc_egee_queues/bound_checks.csv` |
| `supplementary.tex:2535` | `prechecks/lpc_egee/bound_checks.csv` | `evidence/lpc_egee/bound_checks.csv` |
| `supplementary.tex:2547` | `prechecks/lpc_egee_queues/tables.md` | `evidence/lpc_egee_queues/tables.md` |
| `supplementary.tex:2579` | `prechecks/lpc_egee_queues/tables.md` | `evidence/lpc_egee_queues/tables.md` |
| `supplementary.tex:2583` | `prechecks/lpc_egee/applicability.csv` | `evidence/lpc_egee/applicability.csv` |
| `supplementary.tex:2596` | `prechecks/lpc_egee_queues/tables.md` | `evidence/lpc_egee_queues/tables.md` |
| `supplementary.tex:2627` | `prechecks/lpc_egee_queues/tables.md` | `evidence/lpc_egee_queues/tables.md` |
| `supplementary.tex:2628` | `prechecks/lpc_egee_queues/policy_metrics.csv` | `evidence/lpc_egee_queues/policy_metrics.csv` |
| `supplementary.tex:2631` | `prechecks/lpc_egee_queues/tables.md` | `evidence/lpc_egee_queues/tables.md` |
| `supplementary.tex:2643` | `prechecks/lpc_egee_queues/bound_checks.csv` | `evidence/lpc_egee_queues/bound_checks.csv` |
| `supplementary.tex:2647` | `prechecks/lpc_egee_queues/REPORT.md` | `evidence/lpc_egee_queues/REPORT.md` |
| `supplementary.tex:2666` | `prechecks/lpc_egee_queues/tables.md` | `evidence/lpc_egee_queues/tables.md` |
| `supplementary.tex:2670` | `prechecks/lpc_egee_queues/REPORT.md` | `evidence/lpc_egee_queues/REPORT.md` |
| `supplementary.tex:3398` | `prechecks/guard_optimality_verify/literature_check.md` | `evidence/guard_optimality_verify/literature_check.md` |
| `supplementary.tex:3399` | `prechecks/guard_optimality_verify/verification.md` | `evidence/guard_optimality_verify/verification.md` |

Line numbers are as of the state of `paper/` when this folder was assembled, and the
manuscript was being edited at the time; the path strings are what to search for, not the
line numbers.

## Studies the paper names that are not published here

Two working directories are still named from inside this folder and have no copy of their
own: `prechecks/guard_optimality`, the optimality note that `guard_optimality_verify`
checks, and `prechecks/recorded_queue_hunt`, the trace search whose conclusion
`weakness1_attack/AUDIT_A.md` carries and corrects. Neither is named in a paper source
comment. `evidence/README.md` says why each was left out.

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
| `08_experiments.tex` (second physical run, source comment) | `prechecks/platform_testbed/records/summary.json`, `simulator_replay.json` | `evidence/platform_testbed/records/summary.json`, `simulator_replay.json` |
| `supplementary.tex` (platform back-end section, source comments) | `prechecks/platform_testbed/records/summary.json`, `simulator_replay.json`, `results.md` | `evidence/platform_testbed/records/summary.json`, `simulator_replay.json`, `results.md` |

`prechecks/main_v3/v31/primary_rep*.npz` is the one row that does not map. Those overlay
traces are rebuilt into the cache directory by `v31_build.py` and are not on disk under
that path; `scripts/check_overlays.py` needs them rebuilt before it can compare against
them. The row in `GENERATED.md` should say so.

## Inside the copied files

`.md`, `.py`, `.sh` and `.ps1` files in this folder had their own `prechecks/…`
cross-references rewritten to `evidence/…`, so the studies point at each other correctly. The `out_*.txt`
run logs were **not** touched — they are run output and still print `prechecks/<study>/`.
Read those as `evidence/<study>/`.
