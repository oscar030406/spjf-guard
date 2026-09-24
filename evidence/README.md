# evidence

The script and the log behind every number in the paper that does not come from the
package in `src/`. One directory per study. Each directory holds the scripts that were
run, the `out_*.txt` these wrote, the summary tables they produced, and a `README.md`
saying what question the study answers, which part of the paper uses it, what it needs as
input and how to rerun it.

`PATHS.md` maps every `prechecks/…` path the paper's source comments currently name onto
its path here. Machine-specific absolute paths in the copies were replaced by the two
placeholders below; no measured value was changed.

## How to read a study

Each `README.md` opens with the same four things: the question, the paper items, the
inputs, and the status. After the separator comes the study's own working notes, kept
because they record the order the scripts were run in and the traps that were hit.

Two conventions run through all of it:

- `<repo-root>` is your checkout, `<cache-dir>` is a scratch directory outside the
  repository, and `<python-root>` is the interpreter install. All three were absolute
  paths on the machine the runs were made on; set them before rerunning anything.
- **No raw data is redistributed here.** Every study reads from `data/`, and
  `data/README.md` says where each dataset comes from and under what terms. Large
  intermediates are written to `<cache-dir>`, never into this folder.

Nothing here reads sealed data. The CodeBench semesters 2023-1, 2023-2 and 2024-1, the
ACcoding submission-id block 80–100% and the OULAD 2014 presentations were not opened by
any run recorded in this folder.

## What is here

| study | what it answers | paper items | size |
| --- | --- | --- | --- |
| `codebench` | parses the 18 CodeBench semester archives | §7 data path | 0.07 MB |
| `codebench_semantics` | what `EXECUTION TIME` and the block headers mean; where the 60 s limit comes from | §7; the constant `L` used in §6 and §8 | 0.23 MB |
| `codebench_audit` | do the parsed counts reconcile with the publisher's statistics; the cost tail | §7 sizes and per-era rows; §8 tail share; supplement field audit | 0.16 MB |
| `codebench_service_v2` | causal cost prediction and the shared evaluator pool on CodeBench | §4 CodeBench column; §7; §8 AUROC and `tab:sens`; supplement | 0.50 MB |
| `accoding_v2` | the same protocol on a second judge platform | §4 ACcoding column; §7 sizes and limits; §8 ACcoding row | 0.19 MB |
| `oulad` | the original direction, falsified | §7 OULAD header line (`out_load.txt`) only | 0.36 MB |
| `cross_domain` | does the method survive on Azure Functions and Intel Netbatch | §4 eta²; §7 spans; §8 cross-domain rows; supplement | 0.20 MB |
| `firefox_ci` | does the simulator reproduce a real recorded queue | §7 CI spans and work share; §8; supplement pools A and B | 0.31 MB |
| `firefox_ci_holdout` | does that validation survive a held-out refit | §7.3 held-out rows; §8; supplement sharpness | 0.19 MB |
| `predictor_neural` | the predictor comparison and the graph-network ablation ladder | §4 CodeBench column (`out_evaluate_core.txt`) | 0.45 MB |
| `ranking_score` | which score a prediction-driven scheduler should sort by | §8 `tab:scores`, two-class and asymmetry figures | 0.43 MB |
| `guard_variants` | the guard kernel, its per-job theorems, and the budget variants | the kernel behind §8's guard rows | 1.57 MB |
| `guard_variants_referee` | internal referee report on the per-job guard theorem | theory note revisions 1–3 | 0.15 MB |
| `guard_theory` | the theory note: a pathwise identity for FCFS-relative delay | long form of §6 and Appendix A; `A_proofs.tex` provenance; supplement | 0.51 MB |
| `guard_theory_referee` | internal referee report on the theory note (second pass) | theory note revisions 1–3 | 0.19 MB |
| `guard_theory_referee3` | internal referee report on the theory note (third pass) | theory note revisions 1–3 | 0.13 MB |
| `identity_residuals` | the identity residual measured on the real trace | §6, §8 and supplement, via `outputs/dev_tables/identity_residuals.csv` | 0.13 MB |
| `main_v3` | the main experiment: v3, v3.1 and v3.2 | §8 trace table, interval rows, sensitivity table; named in §8 body text | 4.84 MB |
| `main_v3_verify` | independent verification of v3 | §8 independent simulator figures | 0.23 MB |
| `main_v31_verify` | independent verification of v3.1 | finding G1, which is why v3.2 exists | 0.46 MB |
| `consolidation` | dedicated containers versus a shared pool | supports the shared-pool framing; no individual paper number | 0.11 MB |
| `restart_tier` | kill-and-restart tiering, examined and rejected | §9 limitations | 0.21 MB |
| `closed_loop` | does the result survive a replay in which users wait for one result before submitting the next | §8 closed-replay paragraph; §9 open-loop limitation; supplement S6.5-S6.6 | 0.26 MB |
| `lpc_egee_queues` | the same protocol on a compute farm, one pool per walltime class, where the guard's bound is nearly attained | §8 applicability; §9 forced dispatches; supplement S7.6 | 0.32 MB |
| `reservation_guard` | reservation-and-refund charging: six conjectures on the additive constant | the study behind the supplementary theory section | 0.07 MB |
| `reservation_guard_verify` | independent re-check of that rule from its written definition | supplementary theory section, decision table and witnesses | 0.08 MB |
| `weakness1_attack` | does the result depend on the capacity and on open-loop demand; the physical two-worker run and the stall-corrected certificate | §8 capacity paragraphs; supplement capacity, physical, stall-bound and feedback sections | 3.68 MB |
| `lpc_egee` | the recorded-wait grid log, pooled by partition: a real queue, a weak replay validation, and a promise too coarse to fire | §8 and §9 cross-domain rows; supplement LPC sections | 3.36 MB |
| `guard_optimality_verify` | independent re-check of the optimality note's T1, T2 and T3 | supplementary theory section | 0.10 MB |
| `heldout_scope` | what the paper promises about sealed data against what can be run | §1 and §7 sealed-scope sentences; supplement Q2 | 0.04 MB |
| `platform_testbed` | the guard run on a course platform's own two-worker back end, with an enforced per-job limit and scripted accounts that wait for each result: six cells, the enforced-limit check, the simulator comparison and the dispatch overhead | §8.5 second physical run; supplement section on the platform back end | 1.2 MB |
| `timeout_rule` | does a maximum waiting time keep the guard's promise, and what does it give up at the same promise | §6.7 `prop:clock`; §2 and §1 clock sentences; §8.4 `tab:clock`; supplement S4.11 | 0.08 MB |
| `envelope_bound` | an absolute per-job bound from the arrival log, its tightness on the traces, and how well one period's burst predicts the next | §6.8 `prop:absolute`; §8.6 absolute-bound paragraph and sigma forecast | 0.29 MB |
| `new_theory_refutation` | independent refutation of the fluid lemma, the absolute bound, the clock bound and the combined rule | §6.7-6.8 wording; supplement S4.11 counterexamples and check summary | 0.20 MB |
| `stale_charging` | what the guard promises when completion reports arrive late, and which protocol restores Theorem 3 | §6.9 `prop:late`; supplement S4.12 | 0.10 MB |
| `referee_round4` | a maximum waiting time and fixed-window ordering run as baselines beside the guard | §8.4 fixed-window (Block) paragraph | 0.06 MB |
| `cost_ratio` | L over the mean job cost, the factor by which a count of overtakes is loose | the ratio 150 in §5, §6.4, §9 and supplement S4.4 | 0.00 MB |

1,260 files, 20.6 MB.

## What is not here

Studies that no paper number rests on were left out. They are kept in the working
folder, not deleted.

| study | why |
| --- | --- |
| `accoding` (first version) | superseded by `accoding_v2`, which reruns it under the v2 protocol; no paper number comes from it |
| `codebench_service` (first version) | superseded by `codebench_service_v2`. Its history features were built by submission order rather than by result-availability time, so its numbers leak and are optimistic; the directory says so itself |
| `guard_check` | superseded by `guard_variants`, which checks the same per-job upper bound over the whole family of budget rules |
| `upc_wifi`, `upc_wifi_gnn` | an early direction — access-point load on a campus Wi-Fi trace, and a heterogeneous graph network against hand-built neighbour features. Nothing in the paper rests on either |
| `guard_optimality` | the optimality note that `guard_optimality_verify` checks. The re-check restates every theorem it rules on, and governs where the two disagree |
| `recorded_queue_hunt` | the search for a trace that records queue waits, which ended at LPC-EGEE. Its conclusion is carried in `weakness1_attack/AUDIT_A.md`, which also records where that conclusion was wrong |

Some included studies still point at those directories, because that is where their own
history is: `accoding_v2/accoding_v2.py` at `accoding` (the SQL parse it inherits),
`codebench_service_v2/README.md`, `service_precheck_v2.py` and `restart_tier/notes.md`
at `codebench_service` (what v1 did wrong, the trace it replays, a cost figure),
`guard_optimality_verify/README.md`, `verification.md` and `sim.py` at
`guard_optimality` (the note under review), and `weakness1_attack/AUDIT_A.md` at
`recorded_queue_hunt` (a claim it corrects). Those paths do not resolve inside this
folder; the text around each one says what the file was.

Seven kinds of file were left out of the studies that are here:

- **Parse caches and derived per-job tables** (`*.parquet`, 40 files, 71 MB) — derived
  student-log data. Each study's README says which script rebuilds them.
- **Copies of the dataset publisher's web pages** (`codebench_semantics/sources/`) —
  their copyright, not ours.
- **Bytecode and numba compilation caches** (`__pycache__/`, 222 files) — build
  artefacts.
- **Simulation state and fitted models** — `closed_loop/out/chains/chain_rep*.npz` (five
  files, 2.02 GB), the per-user submission chains rebuilt by `build_chains.py`; the
  parsed per-job tables `lpc_egee_queues/jobs.csv` (20.7 MB) and `test_jobs.csv`
  (4.2 MB), which are the source log in another form and are rebuilt by `qaudit.py` and
  `qvalidate.py`; and the LightGBM dumps `lpc_egee_queues/model_q1..q5.txt` (11.3 MB),
  rebuilt by `qpredict.py`.
- **Array files** (`*.npy`, `*.npz`) — predictions, per-policy wait vectors, busy masks
  and per-cell bootstrap draws; each study's README says which stage writes them.
- **Event records and figures** — the attempt-level streams of the physical run in
  `weakness1_attack` (`physical_records/`, `physical_*_jobs.jsonl`,
  `physical_*_decisions.jsonl`, 50 files, 549 MB), the raw public-API responses under
  its `raw/taskcluster_probe/`, which carry no identified data licence, and the six
  `.png` / `.svg` figures its summarisers redraw from the CSVs that are here. One
  machine-local recovery script was dropped with its log: it searched a temporary
  directory on one machine by a run identifier and cannot run anywhere else.
- Nothing else was dropped: no file in the included studies exceeded the 5 MB limit once
  those categories were gone.

## Personal data

None of the tables here is at the level of a person. The `*.csv` files carry policy
names, load levels, semester and pool tags, model names, and measured quantities; the
identifier-like columns that exist are `trace`, `rep`, `level`, `policy`, `model`,
`target`, `pool`, `pool_tag`, `design`, `family` and `group`, all of which name a
configuration rather than a person. No student identifier, user name, e-mail address, IP
address or line of student source code appears in this folder, and the scripts that read
the raw logs are explicit about keeping counts and flags rather than text.

## Internal documents that are cited but not distributed

Some study notes cite `docs/research_plan.md`, `docs/related_work/`,
`docs/referee_readthrough/` and the working ideas list. Those are internal working documents kept out of the
repository. Where their content is load-bearing it is reproduced in the study that uses
it — the referee items, for example, are listed in `guard_theory/CHANGES_rev5.md` and in
the CHANGELOG of `guard_theory/theory.md`.

## Directory names

The directory names are the ones the scripts import each other by: several studies do
`sys.path.insert` into a sibling directory, and the manifests hash files by those paths.
Renaming them would have made the copies diverge from what was actually run, so they are
kept and the table above supplies the plain-English title for each.
