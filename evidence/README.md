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

- `<repo-root>` is your checkout and `<cache-dir>` is a scratch directory outside the
  repository. Both were absolute paths on the machine the runs were made on; set them
  before rerunning anything.
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

633 files, 11.8 MB.

## What is not here

Five studies were left out. They are kept in the working folder, not deleted.

| study | why |
| --- | --- |
| `accoding` (first version) | superseded by `accoding_v2`, which reruns it under the v2 protocol; no paper number comes from it |
| `codebench_service` (first version) | superseded by `codebench_service_v2`. Its history features were built by submission order rather than by result-availability time, so its numbers leak and are optimistic; the directory says so itself |
| `guard_check` | superseded by `guard_variants`, which checks the same per-job upper bound over the whole family of budget rules |
| `upc_wifi`, `upc_wifi_gnn` | an early direction — access-point load on a campus Wi-Fi trace, and a heterogeneous graph network against hand-built neighbour features. Nothing in the paper rests on either |

Six places inside the included studies still point at those five directories, because
that is where their own history is: `accoding_v2/accoding_v2.py` (the SQL parse it
inherits), `codebench_service_v2/README.md` and `service_precheck_v2.py` (what v1 did
wrong, and the trace it replays), and `restart_tier/notes.md` (a cost figure). Those
paths do not resolve inside this folder; the text around each one says what the file was.

Four kinds of file were left out of the studies that are here:

- **Parse caches and derived per-job tables** (`*.parquet`, 40 files, 71 MB) — derived
  student-log data. Each study's README says which script rebuilds them.
- **Copies of the dataset publisher's web pages** (`codebench_semantics/sources/`) —
  their copyright, not ours.
- **Bytecode and numba compilation caches** (`__pycache__/`, 222 files) — build
  artefacts.
- Nothing else was dropped: no file in the included studies exceeded the 5 MB limit once
  those three categories were gone.

## Personal data

None of the tables here is at the level of a person. The `*.csv` files carry policy
names, load levels, semester and pool tags, model names, and measured quantities; the
identifier-like columns that exist are `trace`, `rep`, `level`, `policy`, `model`,
`target`, `pool`, `pool_tag`, `design`, `family` and `group`, all of which name a
configuration rather than a person. No student identifier, user name, e-mail address, IP
address or line of student source code appears in this folder, and the scripts that read
the raw logs are explicit about keeping counts and flags rather than text.

## Internal documents that are cited but not distributed

Some study notes cite `docs/research_plan.md`, `docs/related_work/` and
`docs/referee_readthrough/`. Those are internal working documents kept out of the
repository. Where their content is load-bearing it is reproduced in the study that uses
it — the referee items, for example, are listed in `guard_theory/CHANGES_rev5.md` and in
the CHANGELOG of `guard_theory/theory.md`.

## Directory names

The directory names are the ones the scripts import each other by: several studies do
`sys.path.insert` into a sibling directory, and the manifests hash files by those paths.
Renaming them would have made the copies diverge from what was actually run, so they are
kept and the table above supplies the plain-English title for each.
