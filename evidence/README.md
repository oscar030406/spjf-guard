# evidence

The script and the log behind every number in the paper that does not come from the
package in `src/`. One directory per study. Each directory holds the scripts that were
run, the `out_*.txt` logs that these scripts wrote and the summary tables that they
produced. It also holds a `README.md` that says what question the study answers, which part
of the paper uses it, what it needs as input and how to rerun it.

`PATHS.md` maps every `prechecks/…` path that the paper's source comments name onto its
path here, and every `outputs/revision_r1/…` path onto its copy. In the copies, we replaced
machine-specific absolute paths with the three placeholders below. We changed no measured
value.

## How to read a study

Each `README.md` opens with the same four things: the question, the paper items, the
inputs, and the status. After the separator come the study's own working notes. We kept
them because they record the order in which the scripts were run and the traps that we hit.

Two conventions run through all of it:

- `<repo-root>` is your checkout, `<cache-dir>` is a scratch directory outside the
  repository, and `<python-root>` is the interpreter install. All three were absolute
  paths on the machine where we made the runs. Set them before you rerun anything.
- **No raw data is redistributed here.** Every study reads from `data/`, and
  `data/README.md` says where each dataset comes from and under what terms. Large
  intermediates are written to `<cache-dir>`, never into this folder.

Four scripts here read the sealed CodeBench semesters 2023-1, 2023-2 and 2024-1, for counts
and data checks. None of them computes a result on these semesters.
`codebench/parse_codebench.py` parsed all 18 archives.
`codebench/out_parse.txt:17-19, 38-40, 59-61` gives the sealed terms' sizes, users,
assessments and timestamp ranges. Their 699,668 events are part of the 4,611,325 runs of
Table 5 (`codebench_audit/out_tail_and_counts.txt:2`). `codebench/codebench_precheck.py`
loads their rows and prints per-term validation columns (`out_codebench.txt:6, 24-26`).
`codebench_audit/counts_reconcile.py` counts them against the publisher's statistics
(`out_counts_reconcile.txt`). `codebench_service/code_features.py`, run without `--only`,
streams every archive, the sealed three included. No log of its run is kept here. Every other
CodeBench script reads development semesters only. `accoding_v2/accoding_v2.py:126` reads the
ACcoding submission table whole and drops the submission-id block 80–100% on the next line.
Only the block's row count (809,330) and first id reach a log (`out_accoding_v2.txt:59-61,
91`). `oulad/audit_oulad_stats.py` reads the OULAD 2014J presentation (its items 3 and 5,
lines 69, 101 and 108) and has no log here. Every other OULAD script keeps only the 2013
presentations before it computes anything. No study here reads the outputs of the sealed run of
25 September 2026. One script reads the summary of a run on sealed data.
`revision_r1/accoding_sealed/make_tex_table.py` rounds the summary of the run of 3 October
2026 on ACcoding's sealed part for Supplementary Table S36. It reads no sealed row.

This package leaves out the development studies that the paper does not use and that no packaged script reads: `guard_theory_referee`, `guard_theory_referee3`, `guard_variants_referee`, `identity_residuals`, `restart_tier`. From the other studies it leaves out what the paper does not cite: working notes (plans, reviews, audits), development checks (smoke and gate runs) and per-run logs. Some notes below still mention them by name.

## What is here

| study | what it answers | paper items | size |
| --- | --- | --- | --- |
| `codebench` | parses the 18 CodeBench semester archives | §7 data path (the parser); the week-ahead forecast of runs per class in §7.2, RMSE 1.243, 1.159 and 1.112 (`out_codebench.txt`, P4) | 0.07 MB |
| `codebench_semantics` | what `EXECUTION TIME` and the block headers mean; where the 60 s limit comes from | no source comment names it; its findings are the stamp reading and the 60 s ceiling after 2019-08-28 in §7.1, hence `L` = 60 s in §6 and §8, and the field audit of Supplementary Section S2.1 | 0.23 MB |
| `codebench_audit` | do the parsed counts reconcile with the publisher's statistics; the cost tail | CodeBench run count of Table 5 (§7.1); CodeBench tail share of Table 13 (§8.7) and Table S3 (Supplementary Section S2.4); field audit, Supplementary Section S2.1 | 0.16 MB |
| `codebench_service` | the static code features of each run; `code_features.py` is the only file carried from the first version | §7 data path: it writes `data/codebench/parquet/code_features/<semester>.parquet`, which `scripts/build_cache.py` reads | 0.01 MB |
| `codebench_service_v2` | causal cost prediction and the shared evaluator pool on CodeBench | score-objective comparison of §5.2; 863,149 graded submissions in Table 5 (§7.1); §7.3 sealed-term exclusions; Supplementary Sections S1.3, S2.1, S3.9, S5.1 and S5.4; Table S15 (Supplementary Section S3.15); cross-check of the M1–M6 rows of Table S2 | 0.50 MB |
| `accoding_v2` | the same protocol on a second judge platform | sizes in Table 5 (§7.1); M5 − M4 on the second log in §4.3; sealed-block count in §7.3; ACcoding guard entry of Table 13 (§8.7); ACcoding column of Table S2 (Supplementary Section S1.5); Supplementary Sections S1.3, S2.4 (Table S3) and S5.4 | 0.19 MB |
| `oulad` | the original direction, falsified | all from `out_load.txt`: OULAD row of Table 5 (§7.1), the OULAD paragraph of §7.2, the development presentations of §7.3 | 0.36 MB |
| `cross_domain` | does the method survive on Azure Functions and Intel Netbatch | serverless and compute-farm rows of Table 5 (§7.1); ACcoding, Azure and Netbatch rows of Table 13 (§8.7); Table S1 and the variance share 0.867 (Supplementary Section S1.2); Table S3 rows and truncation counts (Supplementary Section S2.4); Supplementary Section S5.4 | 0.20 MB |
| `firefox_ci` | does the simulator reproduce a real recorded queue | CI rows of Table 5 (§7.1); CI rows of Table 13 and the 3.4% and 5.2% work shares (§8.7); CI rows of Tables S1 and S3 and the CI provenance paragraph (Supplementary Sections S1.2 and S2.4); Supplementary Section S5.4 | 0.31 MB |
| `firefox_ci_holdout` | does that validation survive a held-out refit | §7.2 sentence that the simulator reproduces recorded waits; Supplementary Sections S2.2 (sharpness, circularity), S2.3 (held-out refit), S5.4 and S6.7 (CI capacities) | 0.19 MB |
| `predictor_neural` | the predictor comparison and the graph-network ablation ladder | Table 2 (§4.2) and §4.3; the cold-start and test-row figures of §1 and §10; CodeBench column of Table S2 (Supplementary Section S1.5); Supplementary Section S5.4 | 0.45 MB |
| `ranking_score` | which score a prediction-driven scheduler should sort by | asymmetry figures of §8.3; Table S14 and its two-class figures (Supplementary Section S3.10), cited from §8.3; asymmetry waits in Supplementary Section S3.16; fit targets in Supplementary Section S5.1 | 0.43 MB |
| `guard_variants` | the guard kernel, its per-job theorems, and the budget variants | no printed number; its kernel is the simulator of `main_v3`, `cross_domain`, `firefox_ci` and `consolidation`. The guard rows of Tables 7–9 come from the package | 1.57 MB |
| `guard_theory` | the theory note: a pathwise identity for FCFS-relative delay | long form of §6 and of the proofs in Supplementary Sections S4 and S8 (formerly Appendix A, which the manuscript no longer has); `rev5_items.py` is the enumeration beside Proposition S22 (Supplementary Section S8.5) | 0.51 MB |
| `main_v3` | the main experiment: v3, v3.1 and v3.2 | count baseline charged at completion in §8.4; Table S4 trace and interval rows (Supplementary Section S3.1); Supplementary Sections S3.15, S3.16, S5.3, S5.4 (named in the text) and S5.6 (drop-one-cell sensitivity); Table S16 footnote rows and refit control (Supplementary Section S3.17), cited from §8.3 | 4.84 MB |
| `main_v3_verify` | independent verification of v3 | the 5.7 billion independent checks of §8.5; the job-for-job cross-check of Supplementary Section S3.16; Supplementary Section S5.4 | 0.23 MB |
| `main_v31_verify` | independent verification of v3.1 | nothing printed; its finding G1 is why v3.2 exists, whose drop-one-cell sensitivity Supplementary Section S5.6 quotes | 0.46 MB |
| `consolidation` | dedicated containers versus a shared pool | 1,636 containers at 0.12% busy against 14 servers in §7.2 and §9; Supplementary Section S2.3 | 0.11 MB |
| `closed_loop` | does the result survive a replay in which users wait for one result before submitting the next | closed-replay paragraph of §8.8; open-loop limitation of §9; Table S21 and Supplementary Section S6.5 | 0.26 MB |
| `lpc_egee_queues` | the same protocol on a compute farm, one pool per walltime class, where the guard's bound is nearly attained | Tables S22 and S23 (Supplementary Section S6.6); `test`-class row of Table S24 and its paragraph (Supplementary Section S6.7), to which the caption of Table 13 (§8.7) points | 0.32 MB |
| `reservation_guard` | reservation-and-refund charging: six conjectures on the additive constant | nothing cited directly; the study behind Supplementary Section S7.6 (Propositions S13–S15), which quotes `reservation_guard_verify` | 0.07 MB |
| `reservation_guard_verify` | independent re-check of that rule from its written definition | Supplementary Section S7.6: Propositions S13–S15, decision-table rows and witnesses; the §9 sentence that charging a cap known at arrival lowers the constant by L | 0.08 MB |
| `public_cap_guard` | is reservation charging with the service's own limit `L` as every job's cap at least as permissive as Algorithm 1 at the same promise | Supplementary Section S7.6: Proposition S16 and the exhaustive check after it; the sentence of §6.5 that `L` is such a cap; the §9 sentence on a wrapper that overrides less often at the same G | 0.01 MB |
| `general_reference` | the identity and the guard against a reference ordered by a key fixed at arrival, under server failures, and summed over all jobs or a group | Supplementary Sections S7.3 (Proposition S8 and its checks), S7.7 (Propositions S17 and S18 and their checks) and S7.8 (Proposition S19 and its checks); the sentences of §3.3 on why the reference is FCFS and of §6.9 on failures | 0.05 MB |
| `weakness1_attack` | does the result depend on the capacity and on open-loop demand; the physical two-worker run and the stall-corrected certificate | capacity and first physical run in §8.8; capacity range in §10; Tables S19 and S20 and Supplementary Sections S6.1–S6.3 (capacity, physical run, stall-corrected bound, feedback counterexamples cited from §9); Supplementary Sections S5.3 and S5.4 | 3.68 MB |
| `lpc_egee` | the recorded-wait grid log, pooled by partition: a real queue, a weak replay validation, and a promise too coarse to fire | Supplementary Sections S6.4, S6.6 (the pooled contrast) and S6.7 (chronological-test row of Table S24); the caption of Table 13 (§8.7) points there | 3.36 MB |
| `guard_optimality_verify` | independent re-check of the optimality note's T1, T2 and T3 | Supplementary Sections S7.1 (Table S26), S7.2 (Proposition S6), S7.3 (Lemma S7), S7.4 and S9.1 | 0.10 MB |
| `heldout_scope` | what the paper promises about sealed data against what can be run | §7.3 development and sealed-data paragraph (findings G1–G6); Supplementary Section S5.1 (Q2) | 0.04 MB |
| `platform_testbed` | the guard run on a course platform's own two-worker back end, with an enforced per-job limit and scripted accounts that wait for each result: six cells, the enforced-limit check, the simulator comparison and the dispatch overhead | second physical test in §8.8; Table S25 (Supplementary Section S6.9) | 1.2 MB |
| `timeout_rule` | does a maximum waiting time keep the guard's promise, and what does it give up at the same promise | Proposition 10 (§6.6); the §1 contribution list and the §2.3 sentence on maximum waiting times; Table 10 and the equal-excess comparison (§8.4); check summary, Supplementary Section S4.11; original-clock rows of Table S33 (Supplementary Section S11) | 0.08 MB |
| `envelope_bound` | an absolute per-job bound from the arrival log, its tightness on the traces, and how well one period's burst predicts the next | Proposition 11 and the rule for B_max (§6.7); the check on 304 runs, the absolute-bound paragraph and the sigma forecast (§8.5) | 0.29 MB |
| `new_theory_refutation` | independent refutation of the fluid lemma, the absolute bound, the clock bound and the combined rule | wording of Proposition 10 and the combined rule (§6.6) and of Proposition 11 (§6.7); Lemma S5, counterexamples and check summary (Supplementary Section S4.11) | 0.20 MB |
| `stale_charging` | what the guard promises when completion reports arrive late, and which protocol restores Theorem 7 | Proposition 12 (§6.8); the remark on late or lost reports at the end of §6.6; Supplementary Section S4.12 | 0.16 MB |
| `referee_round4` | a maximum waiting time and fixed-window ordering run as baselines beside the guard | the fixed-window (Block(512)) paragraph of §8.4 | 0.06 MB |
| `cost_ratio` | L over the mean job cost, the factor by which a count of overtakes is loose | the ratio 150 in §1, §6.4 and §10, and in Supplementary Sections S4.4 and S4.9 | 0.00 MB |
| `revision_r1` | the experiments, tables and figures added for the first revision: score quality, backfilling, one to three servers, late reports, the cost of the accounts, abandonment, ACcoding's sealed part and class-term intervals | Figures 4–6; Tables 11, 14 and 15 and the job-check count of Table 12; §8.3, §8.4, §8.6, §8.8, §8.9 and §8.10; Supplementary Section S13 (Tables S35–S38) | 1.36 MB |
| `abandonment_loop` | does the result survive users who give up on a long wait and may submit again | the abandonment paragraph of §8.8; Supplementary Section S13.3 and Table S37 | 0.47 MB |
| `limit_family_selection` | how close the worst excess comes to the bound at other time limits; which family a rule that sees only the validation overlays chooses | Figure 5(b); the validation-only reselection in §7.3 | 0.26 MB |
| `skipc_block_online` | Skip charged at completion and ordering within fixed blocks, under the online replay | nothing printed; its Block(W) kernel runs in `limit_family_selection` | 0.25 MB |

1,482 files, 23.0 MB.

## What is not here

We left out the studies that no paper number rests on. They are kept in the working
folder, not deleted.

| study | why |
| --- | --- |
| `accoding` (first version) | superseded by `accoding_v2`, which reruns it under the v2 protocol; no paper number comes from it. This package keeps only its `parse_sql.py`, which writes the tables that `accoding_v2` reads |
| `codebench_service` (first version) | superseded by `codebench_service_v2`. Its history features were built by submission order rather than by result-availability time, so its numbers leak and are optimistic. The rest of that first version is left out. Only its parser `code_features.py` is carried, in `codebench_service/`, because the data path still runs it |
| `guard_check` | superseded by `guard_variants`, which checks the same per-job upper bound over the whole family of budget rules |
| `upc_wifi`, `upc_wifi_gnn` | an early direction — access-point load on a campus Wi-Fi trace, and a heterogeneous graph network against hand-built neighbour features. Nothing in the paper rests on either |
| `guard_optimality` | the optimality note that `guard_optimality_verify` checks. The re-check restates every theorem that it rules on, and governs where the two disagree |
| `recorded_queue_hunt` | the search for a trace that records queue waits, which ended at LPC-EGEE. Its conclusion is carried in `weakness1_attack/AUDIT_A.md`, which also records where that conclusion was wrong |
| `llm_batching` | a separate study whose results are not published. `revision_r1/backfill_baselines` checked its kernel against the reference implementations of conservative and slack-based backfilling in it. The outputs of those checks are kept |

Some included studies still point at those directories, because that is where their own
history is:

- `accoding_v2/accoding_v2.py` at `accoding` (the SQL parse that it inherits)
- `codebench_service_v2/README.md`, `service_precheck_v2.py` and `restart_tier/notes.md`
  at `codebench_service` (what v1 did wrong, the trace that it replays, a cost figure)
- `guard_optimality_verify/README.md`, `verification.md` and `sim.py` at
  `guard_optimality` (the note under review)
- `weakness1_attack/AUDIT_A.md` at `recorded_queue_hunt` (a claim that it corrects)

The two backfilling gates and `ref_est.py` of
`revision_r1/backfill_baselines` import modules of `llm_batching`, so they do not run from
this folder. Apart from `service_precheck_v2.py`'s import of
`codebench_service/code_features.py`, those paths do not resolve inside this folder. The
text around each one says what the file was.

The studies that are here leave out these kinds of file:

- **Parse caches and derived per-job tables** (`*.parquet`, 40 files, 71 MB) — derived
  student-log data. Each study's README says which script rebuilds them.
- **Copies of the dataset publisher's web pages** (`codebench_semantics/sources/`) —
  their copyright, not ours.
- **Bytecode and numba compilation caches** (`__pycache__/`, 222 files) — build
  artefacts.
- **Simulation state and fitted models** — `closed_loop/out/chains/chain_rep*.npz` (five
  files, 2.02 GB), the per-user submission chains that `build_chains.py` rebuilds. The
  parsed per-job tables `lpc_egee_queues/jobs.csv` (20.7 MB) and `test_jobs.csv`
  (4.2 MB) are the source log in another form, and `qaudit.py` and `qvalidate.py` rebuild
  them. `qpredict.py` rebuilds the LightGBM dumps `lpc_egee_queues/model_q1..q5.txt`
  (11.3 MB).
- **Array files** (`*.npy`, `*.npz`) — predictions, per-policy wait vectors, busy masks
  and per-cell bootstrap draws; each study's README says which stage writes them.
- **Event records and figures** — the attempt-level streams of the physical run in
  `weakness1_attack` (`physical_records/`, `physical_*_jobs.jsonl`,
  `physical_*_decisions.jsonl`, 50 files, 549 MB). Also left out are the raw public-API
  responses under its `raw/taskcluster_probe/`, which carry no identified data licence,
  and the six `.png` / `.svg` figures that its summarisers redraw from the CSVs that are
  here. We dropped one machine-local recovery script with its log. It searched a
  temporary directory on one machine by a run identifier and cannot run anywhere else.
- **Per-cell results of the revision** — `revision_r1/<study>/out/` holds the files
  of `outputs/revision_r1/<study>/` that the paper cites, mostly summary tables. Each study's job
  chain rebuilds the per-cell CSV and JSON files, score arrays and numba caches there.
- **Working notes in Chinese** — the progress files of the revision studies and four
  reports written in Chinese. Each study's `README.md` restates their content in English.
- Nothing else was dropped: no file in the included studies exceeded the 5 MB limit once
  those categories were gone.

## Personal data

None of the tables here is at the level of a person. The `*.csv` files carry policy
names, load levels, semester and pool tags, model names, and measured quantities. The
identifier-like columns that exist are `trace`, `rep`, `level`, `policy`, `model`,
`target`, `pool`, `pool_tag`, `design`, `family` and `group`, and all of them name a
configuration rather than a person. No student identifier, user name, e-mail address, IP
address or line of source code written by a student appears in this folder. The scripts that read
the raw logs explicitly keep counts and flags rather than text.

## Internal documents that are cited but not distributed

Some study notes cite `docs/research_plan.md`, `docs/related_work/`,
`docs/referee_readthrough/` and the working ideas list. Those are internal working documents kept out of the
repository. Where a study depends on their content, that study reproduces it. For
example, `guard_theory/CHANGES_rev5.md` and the CHANGELOG of `guard_theory/theory.md` list
the referee items.

## Directory names

The directory names are the names by which the scripts import each other: several studies
do `sys.path.insert` into a sibling directory, and the manifests hash files by those paths.
Renaming them would have made the copies diverge from what was actually run. Therefore, we
kept them, and the table above gives the plain-English title for each.
