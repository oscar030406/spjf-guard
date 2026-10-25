# The one run on the sealed terms: how to run it (revised 2026-09-24; sections 4.A and 4.B added 2026-09-25)

This file covers operations only:

- what to check before the freeze
- how to freeze
- which commands make up that one run
- what goes into the ledger
- how long the run takes and how much disk it uses
- what to do if the run crashes midway

At the freeze, `scripts/freeze_protocol.py` writes the protocol lock, `protocol_lock.json`, which freezes the method before the sealed run. The ledger is the table in `docs/sealed_access_log.md`. For why the procedure is designed this way, see these decision records:

- ADR 0003, the rule for selecting parameters
- ADR 0004, the protection of sealed data
- ADR 0008, the online replay as the headline result

For the source of each artefact, see `GENERATED.md`.

Scope: **only the three sealed CodeBench terms 2023-1 / 2023-2 / 2024-1**. ACcoding ids 80%–100% and OULAD 2014 are not part of this run, because we have not moved their code into the package. The ACcoding ids 80%–100% are the last fifth of the ACcoding submissions by id. See the README sections "Data" and "The sealed semesters".

The paths need no environment variables. They all come from the `data` section of `configs/main.yaml`. The command prefix is the same as in the README:

```bash
export UV="env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME \
  NUMBA_NUM_THREADS=4 OMP_NUM_THREADS=4 uv run --no-sync"
```

## 1 Checks before the freeze (all on development data; can be run any number of times)

| # | Command | Expected |
|---|---|---|
| 0 | `$UV python scripts/parse_archive.py --semesters 2022-1 --compare` | all 40 columns of the five tables equal (about 11 seconds) |
| 0b | `$UV python scripts/build_cache.py --pool development --compare data/derived/codebench_cache_r4/ev.parquet` | all 58 columns equal |
| 1 | `$UV ruff check src tests scripts` / `$UV mypy` / `$UV python -m pytest -q` | all green |
| 2 | `$UV python scripts/check_overlays.py` | the overlays that this package produces equal those that the exploratory pipeline v3.1 stored, array by array. An overlay is one trace that superimposes copies of several class-terms, each shifted by whole weeks |
| 3 | `$UV python scripts/fit_scores.py --repeat` | two columns each for original / conservative / static, six in total. The two runs are bit-identical |
| 4 | `$UV python scripts/select_parameters.py --workers 2 --out-dir outputs/selection_v4`, and once all fifteen cells (five overlays × three load levels) are done, `--from-grid` | the nine Guard selections agree with selected/family_best in `configs/main.yaml`. Since 2026-09-24, these entries come from selection_v4. The earlier v3 selection read old overlays that embedded early predictions (see the comment in the configuration). `selection_protocol.json` records the grid, the expanded points and the candidate/feasible counts |
| 4b | `$UV python scripts/select_aging.py --workers 2` | on the 11-point grid, the same validation-only harm rule selects `credit_per_s = 0.03`. The script writes the full candidate counts. This baseline has no proven guarantee |
| 5 | `$UV python scripts/run_main.py --selection outputs/selection_v4/selected_parameters.csv --out-dir outputs/dev_tables --workers 2` | the script produces all development tables, with no `selection mismatch` at the start. Apart from the new Aging row, the existing rows and columns are unchanged bit for bit |
| 5b | `$UV python scripts/eval_scores.py --pool primary` | six target terms × six scores + six pooled rows, 42 rows in total. The heavy threshold is still 1.559043 s, and 2022-2 still has 40,844 rows and 536 heavy jobs. About 11 minutes |
| 5d | `$UV python scripts/run_visibility.py --pool primary --workers 2` | the script writes five CSVs for the fifteen cells to `outputs/dev_visibility/`. FCFS and Guard both have 0 violations of the 3600-second lag. SPJF-E is reported as measured. About 35 minutes |
| 5e | `$UV python scripts/run_consistent_visibility.py --config configs/visibility_development_20260924.yaml --pool primary --workers 2 --resume --controls data/derived/package_ranking_scores/consistent_controls_20260924.npz` | the script writes the results of the fifteen cells to `outputs/dev_consistent_visibility/`. The five frozen policies and the other-copy semantics of Guard(600) must have zero violations in the final pass of every cell. The script validates the sparse scores against the manifest |
| 5f | `$UV python scripts/assess_consistent_selection.py --config configs/visibility_development_20260922.yaml --out-dir outputs/consistent_selection_final --workers 2` | the script times 12 fixed strata of the validation pool and extrapolates the timing to a full 15-cell reselection. Do not use the timing points to select parameters |
| 5h | `$UV python scripts/run_online_visibility.py --pool primary --workers 2 --resume` | the script writes the results of fifteen cells × five frozen policies to `outputs/dev_online_visibility/`. For every policy-cell (one policy on one cell), the sampled audit `mismatches` is 0. The per-job bounds of the three Guards hold. The original rows equal the point estimates of the original rows of 5e bit for bit. `emit_paper_tables.py` checks this when it emits the tables |
| 5i | `$UV python scripts/select_online.py candidates`, then `$UV python scripts/run_online_visibility.py --pool validation --variants online --candidates outputs/online_selection/candidates.csv --out-dir outputs/online_selection/validation --workers 2 --resume`, then `$UV python scripts/select_online.py choose` | online replay of the 36 candidates on the 15 cells of the validation pool. In `online_choices.csv`, the original group must equal the nine selected points of selection_v4. The online group is only reported. The script does not write it back to the configuration |
| 5g | `$UV python scripts/check_preserved_outputs.py` | zero byte differences in the original 75 CSVs, 18,627 rows and all existing columns. Do not overwrite the snapshot |
| 5c | `$UV python scripts/build_overlays.py --pool validation --single-server --no-scores --out-dir <temp-dir>` | prints `321 copies (321 copies reused from pool primary)` and the actual busy-hour utilisation (1.0043 on the validation pool). This step rehearses the code path that reuses the number of copies. Do not write its output into `data/derived/overlay_traces/` |
| 6 | `$UV python scripts/emit_paper_tables.py` | the existing tables and `outputs/paper_tables/numbers.csv` stay byte for byte as they were |
| 6e | `$UV python scripts/emit_paper_tables.py --dev-exact-dir outputs/dev_consistent_visibility --dev-online-dir outputs/dev_online_visibility --out-dir outputs/consistent_paper_tables` | generates these files in a separate directory: copies of the existing tables, two exact tables with online rows, and a number index to which it appends the exact/online sources. It does not overwrite the old directory. It exits immediately if the original rows of the online directory disagree with those of exact |
| 7 | `$UV python scripts/check_paper_numbers.py`, then run `$UV python scripts/check_paper_numbers.py --package-dir outputs/consistent_paper_tables --dev-exact-dir outputs/dev_consistent_visibility --dev-online-dir outputs/dev_online_visibility` | the old paper tables/numbers still agree with the old package. The two exact tables in the new directory match the CSV recipe byte for byte. If they are already pasted into the paper, the copies there are identical to them value by value |
| 8 | `$UV python scripts/check_generated.py` | all seven items pass: exact certificates, preservation of the old tables, artefact lists, paper numbers, printed values in the paper, machine paths, draft |
| 9 | `$UV python scripts/run_main.py --config configs/main.yaml --dry-run-sealed` | prints the plan: ten stages, six artefact lists, the names of two cache files. The last line is `verdict REFUSED: no frozen protocol_lock.json exists` |

Step 9 is a rehearsal. It prints the following items and then exits:

- the list of sealed terms
- five overlays × three load levels
- the policies
- the three static score variants
- the exact visibility protocol
- the list of online policies
- the B0 for each promise G
- **which files it would read**
- the six output lists
- the ledger path and the state of the lock

It opens no file at all, so you can run it at any time.

This package's `scripts/build_cache.py` now builds the parsed cache of the sealed terms from `data/codebench/parquet/`. We moved this script into the package in the third round. On the development terms, its cache equals the old cache in all 58 columns, column by column. This build is step 1 of the sealed run.

## 1.A The per-semester parquet files: already on disk; the sealed run does not parse them again

In the fourth round, we moved archive parsing into the package as well. Together, `scripts/parse_archive.py` and `src/spjf_guard/data/archive.py` stream-parse the five tables `assessments / events / logins / codemirror / users` from `data/codebench/archives/cb_dataset_<semester>_v1.81.tar.gz`. We verified this code by parsing the development term **2022-1** again and comparing the result column by column with the parquet on disk. **All 40 columns were equal**, and the run took 11 seconds (`scripts/parse_archive.py --semesters 2022-1 --compare`, test `tests/test_archive_parse.py`, marked `slow`).

**The sealed run does not run this step.**

Correction, found in the dry run of the freeze on 2026-09-25: on 09-18, we parsed events and assessments. However, we did not generate the `code_features` of the three sealed terms at that time. `prechecks/codebench_service/code_features.py` computes the static code features separately. During development, we computed them only for 2018-1 to 2022-2. Before the freeze, on 2026-09-25, we filled in the `code_features` of the sealed terms with the same parser. It computed only static code counts, and each term got one ledger row. Rerunning that parser on the development term 2022-1 gives a file that is identical, column by column, to the one on disk.

We made the events/assessments parquet files of the eighteen terms in one parsing pass on 2026-09-18. `data/codebench/parquet/_parse_stats.csv` records the row count, byte count and time for each term. The six files of the three sealed terms have been on disk since then:

```text
data/codebench/parquet/events/2023-1.parquet        data/codebench/archives/cb_dataset_2023_1_v1.81.tar.gz
data/codebench/parquet/code_features/2023-1.parquet data/codebench/archives/cb_dataset_2023_2_v1.81.tar.gz
data/codebench/parquet/assessments/2023-1.parquet   data/codebench/archives/cb_dataset_2024_1_v1.81.tar.gz
… the same three tables for 2023-2 and 2024-1
```

That is nine parquet files plus three archives, twelve files in total. **At the freeze, `scripts/freeze_protocol.py` computes the sha256 of the bytes of these twelve files and records the hashes in the lock.** No person does this by hand. This is itself an "opening", because computing a hash reads the bytes. Therefore:

- Hashing **does not parse the content**. The script reads no table, looks at no row count and computes no statistic. It reads only the byte stream.
- Each file gets **its own row** in `docs/sealed_access_log.md`. The row states "bytes read only to compute sha256, content not parsed" and gives the file size.
- The script writes these twelve rows at the moment of the freeze, not at the moment of the run. The sealed run writes its own ledger rows separately, as usual.

The pinned hashes serve this purpose: after the sealed run, anyone can recompute these twelve sha256 values. They can then check that the run read exactly the files present at the freeze, and that nobody swapped the data in between.

## 2 The freeze

```bash
# 1 Write the draft: sha256 of the code, configuration and input artefacts, plus every choice the plan requires to be pinned
$UV python scripts/make_protocol_lock.py

# 2 A person reads the draft: term split, visibility protocol, predictor and seeds, ranking scores, guard family and selection rule,
#   exact monotone withholding and the five policies, online pause replay and the five policies, the three selected parameter sets, the three load levels and how k is chosen, the primary metric, bootstrap settings
less protocol_lock.draft.json

# 3 Commit first. The lock records the commit; the freeze is refused if the working tree is dirty or there is no commit at all
git add -A && git commit -m "..."

# 4 Dry run: checks the commit state, runs all gates, lists the twelve sealed files that would be hashed, writes nothing
$UV python scripts/freeze_protocol.py --dry-run

# 5 The real freeze. --yes is that person's decision; the script does not make it for them
$UV python scripts/freeze_protocol.py --yes

# 6 Record the fingerprint; later, "is this the same lock" is decided by it
sha256sum protocol_lock.json

# 7 Commit the lock and the ledger together. The frozen tree is already in the commit of step 3, but the lock itself is still untracked;
#   step 5 wrote one ledger row for each of the twelve sealed inputs, and those twelve rows are not committed yet either
git add protocol_lock.json docs/sealed_access_log.md
git commit -m "Freeze the protocol"
```

The `commit` that the lock records is the commit of step 3, that is, the frozen tree. Step 7 is a new commit after it. Therefore the two ids differ, and this is expected. After you commit, the following checks must still be all green. Run them once before you move on:

- `$UV python -m pytest -q`: the lock check in `tests/test_sealed_data.py` now checks `protocol_lock.json`. The two "entry point refuses the sealed pool" cases now rely on `--unseal` being absent. Before the freeze, they relied on the lock being absent. `tests/test_repo_hygiene.py` checks that git tracks every code file that the lock hashes.
- `$UV python scripts/check_generated.py --only protocol_lock`: the input hashes that the lock records match the files on disk.
- `$UV python scripts/check_paper_numbers.py` and `$UV python scripts/check_paper_numbers.py --package-dir outputs/consistent_paper_tables --dev-exact-dir outputs/dev_consistent_visibility`: the old package of numbers stays as it was. At this point, the separate exact package of numbers also comes only from development data. The sealed part exists only after run stages 4, 5, 6, 7, 9 and 10 have finished.

Step 5 does four things in a fixed order, and it stops if any of them fails:

1. The working tree must be clean and have a commit.
2. The six gates `ruff` / `ruff format --check` / `mypy` / `pytest` / `check_generated.py` / `check_paper_numbers.py` must all be green.
3. The script computes the sha256 of the bytes of each of the twelve sealed files, and it writes one ledger row for each file.
4. Then the script writes the draft, plus the commit id and these twelve hashes, as `protocol_lock.json`. It leaves the draft as it is.

We tested the script itself in a temporary clone, together with a fake sealed directory. On a clean tree, it writes the lock and twelve ledger rows. It refuses a dirty tree. If you run it again on a repository that is already frozen, it reports straight away that the repository is already frozen.

The same test must pass both before and after the freeze: `tests/test_sealed_data.py::test_the_protocol_lock_describes_the_tree_it_belongs_to`. Before the freeze, it checks that the draft's code digest and configuration hash are those of the current working tree. If the draft lagged behind the code, the frozen method would be one that nobody has run. After the freeze, it checks the same two items in `protocol_lock.json`, that is, "the locked paths have not changed by a single byte since the freeze". It also checks that every sealed input that `scripts/freeze_protocol.py` hashed has its own row in the ledger. **It is not the old `test_no_frozen_lock_exists_yet`.** That test would necessarily turn red on the day of the freeze, so we deleted it.

After the freeze, **do not** change `src/`, `scripts/` or `configs/main.yaml` any more. A change makes it a different method, and the sha256 values in the lock will no longer match.

## 3 The run

Ten commands, in order, each with `--unseal`:

```bash
# 1 Parsed cache: the event tables of the three sealed terms, built from the parquet files already on disk (the archives are not parsed again).
#   It writes ev_sealed.parquet and leaves the development ev.parquet untouched; every later step reads both:
#   the development cache is the training half for each rolling origin, and if it were overwritten the sealed run would have no training rows
$UV python scripts/build_cache.py --pool sealed --unseal

# 2 Overlay traces of the sealed pool: the same function as for primary, only the term list is replaced by pools.sealed.
#   --no-scores because the scores are fitted only in step 3 and attached by job_row in step 4
$UV python scripts/build_overlays.py --pool sealed --no-scores --unseal

# 3 Ranking scores for the sealed terms: the training set is still only the terms before them; the rolling origins are unchanged
$UV python scripts/fit_scores.py --pool sealed \
    --out data/derived/package_ranking_scores/sealed_scores.parquet --unseal

# 4 Main run: the policy set and all parameters come from the frozen configuration; no reselection
$UV python scripts/run_main.py --config configs/main.yaml --pool sealed \
    --score-parquet data/derived/package_ranking_scores/sealed_scores.parquet \
    --out-dir outputs/sealed_tables --workers 2 --unseal

# 5 committed conservative/static references and the old-mapping exposure audit: parameters are not reselected; writes the number of 3600-second violations.
$UV python scripts/run_visibility.py --config configs/main.yaml --pool sealed \
    --scores data/derived/package_ranking_scores/sealed_scores.parquet \
    --out-dir outputs/sealed_visibility --workers 2 --unseal

# 6 exact policy-specific visibility: frozen original model weights and parameters; --workers 2 is the resource cap.
#   At most two cells run at the same time, and each worker refines sequentially; results are aggregated in a fixed cell order.
#   --resume only accepts checkpoints whose input, code and artefact hashes match.
$UV python scripts/run_consistent_visibility.py --config configs/main.yaml --pool sealed \
    --scores data/derived/package_ranking_scores/sealed_scores.parquet \
    --out-dir outputs/sealed_consistent_visibility --workers 2 --resume --unseal

# 7 online replay (ADR 0008): the policies, variants and audit sample size can only be the set pinned in the configuration,
#   and anything else given on the command line is refused; --resume only accepts checkpoints with a matching signature.
$UV python scripts/run_online_visibility.py --config configs/main.yaml --pool sealed \
    --scores data/derived/package_ranking_scores/sealed_scores.parquet \
    --out-dir outputs/sealed_online_visibility --workers 2 --resume --unseal

# 8 Single-server trace: the number of copies is the 321 selected on the development pool; the utilisation is reported as measured (ADR 0006).
#   The file is called sealed_k1_rep0.npz and does not overwrite the development k1_rep0.npz
$UV python scripts/build_overlays.py --pool sealed --single-server --no-scores --unseal

# 9 Tables for the single-server run: the artefact list is run.sealed_k1_tables, checked separately from that of step 4
$UV python scripts/run_main.py --config configs/main.yaml --pool sealed \
    --prefix sealed_k1 --reps 0 --levels 0 \
    --score-parquet data/derived/package_ranking_scores/sealed_scores.parquet \
    --out-dir outputs/sealed_tables/k1 --workers 2 --unseal

# 10 Predictor metrics on the sealed terms: per term and pooled, four metrics with intervals for each of the six scores
$UV python scripts/eval_scores.py --pool sealed \
    --scores data/derived/package_ranking_scores/sealed_scores.parquet \
    --out-dir outputs/sealed_predictor --unseal
```

Step 5 prints the status of the fixed-lag certificate and writes it into the manifest. If conservative has an observed `W > 3600`, that anchor must
be labelled `legacy conservative certificate invalid`. It can then no longer be called a certified visibility scheme. When the headline result is
online (ADR 0008), this warning does not block the later steps. However, if the headline result is conservative, this case is a hard stop.

A failure of any of these checks is always a hard stop:

- the final-pass zero-violation assertion of step 6
- the per-job Guard bounds in either step
- the sparse delta check

A mismatch in the sampled audit of step 7 becomes a hard stop at the step that emits the tables. The runner only prints the number of mismatches. However, `emit_paper_tables.py` and `check_paper_numbers.py` read `online_audit.csv`. They refuse to emit tables if the file is missing or if any row has a non-zero `mismatches`.

After the run, emit the tables and check them. These commands read only `outputs/`, not the sealed data, so they do not need `--unseal`:

```bash
$UV python scripts/emit_paper_tables.py --out-dir outputs/consistent_paper_tables \
    --dev-exact-dir outputs/dev_consistent_visibility \
    --dev-online-dir outputs/dev_online_visibility \
    --sealed-dir outputs/sealed_tables \
    --sealed-predictor-dir outputs/sealed_predictor \
    --sealed-visibility-dir outputs/sealed_visibility \
    --sealed-exact-dir outputs/sealed_consistent_visibility \
    --sealed-online-dir outputs/sealed_online_visibility
$UV python scripts/check_paper_numbers.py --package-dir outputs/consistent_paper_tables \
    --dev-exact-dir outputs/dev_consistent_visibility \
    --dev-online-dir outputs/dev_online_visibility \
    --sealed-dir outputs/sealed_tables \
    --sealed-predictor-dir outputs/sealed_predictor \
    --sealed-visibility-dir outputs/sealed_visibility \
    --sealed-exact-dir outputs/sealed_consistent_visibility \
    --sealed-online-dir outputs/sealed_online_visibility
$UV python scripts/check_generated.py     # includes the sealed part automatically once it sees outputs/sealed_tables
```

`emit_paper_tables.py` writes `outputs/consistent_paper_tables/tab_*_sealed.tex`. In these files, it adds the `_sealed` suffix to the labels of nine tables. These are the five original result tables, the two visibility tables and the two exact tables (with online rows).

The script wraps every number in `\sealednum{}` instead of `\devnum{}`. `\devnum` means "this number comes from development data,
not from the sealed terms", so sealed numbers must not use it. The `main_table.tex` that steps 4 and 9 write themselves also uses `\sealednum{}`.

**Before you paste these tables into the paper, define `\sealednum` in the paper.** Use this definition: `\newcommand{\sealednum}[1]{#1}`.
Place it next to the existing `\newcommand{\devnum}[1]{#1}` in all three files:
`paper/main.tex`, `paper/main_article.tex` and `paper/supplementary.tex`. The check scripts recognise exactly this macro.

When each of the ten commands finishes, it appends one row to `docs/sealed_access_log.md` itself. The row uses the six-column format that the table already has:

```text
| 2026-09-24 | `scripts/run_main.py` | 封存学期 2023-1, 2023-2, 2024-1 | <what was produced> | 运行者 | 否 |
```

The column `是否影响设计` ("influenced the design") defaults to `否` ("no"). If you really change the method after you see this result, change that row to `是` ("yes") and explain the change in the paper. That is why the ledger exists.

The artefacts are the **six** lists that the configuration lock pins. Each list must match exactly, with nothing extra and nothing missing. The runs check each list separately:

| Command | List | Content |
|---|---|---|
| Step 4 → `outputs/sealed_tables/` | `run.sealed_tables` | `main_cells.csv` (per cell), `main_table.csv` (aggregated over overlays), `main_table.tex`, `paired_differences.csv` (paired differences and intervals), `bound_checks.csv` (how many jobs the per-job assertion checked, and the largest used fraction of the allowance), `identity_residuals.csv` (identity residuals on the first overlay), `policy_parameters.csv` (the B0, η, γ, cap and N that each policy actually used in each cell), `manifest.json` |
| Step 5 → `outputs/sealed_visibility/` | `run.sealed_visibility_tables` | `visibility_cells.csv`, `visibility_comparison.csv`, `visibility_paired_differences.csv`, `visibility_exposure.csv`, `visibility_waits_and_lag.csv`, `manifest.json` |
| Step 6 → `outputs/sealed_consistent_visibility/` | `run.sealed_consistent_visibility_tables` | eleven fixed CSVs: `exact_cells`, `exact_comparison`, `exact_passes`, `same_copy_exposure_cells`, `same_copy_exposure`, `attribution_cells`, `attribution_comparison`, `exact_delta_manifest`, `exact_costs`, `exact_sensitivity_cells`, `exact_sensitivity_comparison`, plus `manifest.json`. Only `exact_delta_manifest.csv` records the data-dependent `deltas/*.npz`, one by one (path, byte count and sha256). These files are not in the fixed list |
| Step 7 → `outputs/sealed_online_visibility/` | `run.sealed_online_visibility_tables` | six fixed CSVs: `online_cells`, `online_comparison`, `online_passes` (the number of pauses and the kernel and rescoring times of each policy-cell), `online_audit`, `online_delta_manifest`, `online_costs`, plus `manifest.json`. The delta manifest records `deltas/*.npz`. These files are not in the fixed list |
| Step 9 → `outputs/sealed_tables/k1/` | `run.sealed_k1_tables` | the same eight file names as above, written in the subdirectory |
| Step 10 → `outputs/sealed_predictor/` | `run.sealed_predictor_tables` | `predictor_metrics.csv`, `manifest.json` |

"Nothing extra and nothing missing" is not a verbal agreement. A `--pool sealed` run writes its outputs and then compares the set of fixed file names that it wrote with the corresponding list. It exits with an error if they differ. The six lists cannot be merged into one, because then every command would fail to match. The development tables are in `outputs/dev_tables/`, `outputs/dev_visibility/`, `outputs/dev_consistent_visibility/`, `outputs/dev_online_visibility/` and `outputs/dev_predictor/`. Neither side overwrites the other.

Reporting: give the utilisation actually reached on the sealed terms as measured. **Do not adjust k afterwards to hit the target value.** `main_cells.csv` and `main_table.csv` have an extra column `rho_realised` next to `rho_target`. `rho_target` is the load level that the cell was built for, and it is the number that the paper prints. `rho_realised` is the utilisation that this overlay actually reached in the busy hour at this k (busy-hour work ÷ 3600k). The difference between the two comes from rounding k. Only `rho_realised` shows how full a system was when a number was measured on it. The promise G and the selected (B0, η) are frozen. Do not reselect them because of the results on the sealed terms.

The number of copies and k are a different matter. On the sealed pool, step 2 reruns the copy-count probe, which determines the number of copies. `server_count_rule` computes k for each overlay. The lock freezes the rule, not the numbers that the rule produces on new data. The number of copies at which the probe stops appears only on screen and in that ledger row. When you write the paper, state clearly that this number was derived from the busy-hour work of the sealed pool. The k = 1 trace is the exception: its number of copies is the 321 of the development pool (ADR 0006).

None of the sealed commands passes `--selection`. Therefore `read_selection` falls back to the default path. This repository keeps its selection results in `outputs/selection_v4/`, so the default path has no selection file. As a result, `selection` is empty, and all parameters come from the frozen configuration. This is the intended effect.

One consequence is that the `selection mismatch` check at the start never fires in the sealed run. **Do not treat this check as a protection of the sealed run.** It protects the development run of step 5 in section 1.

## 4 How long it takes and how much disk it uses

Measured on this machine (2 worker processes, LightGBM fixed at 4 threads):

| Step | Time | Disk |
|---|---|---|
| Parsed cache (step 1) | about 5 minutes for the 11 development terms. Faster for the three terms of the sealed pool | development cache `ev.parquet` about 67 MB. `ev_sealed.parquet` in proportion to the number of terms, about 15 MB |
| Overlay traces (5) | copy-count probe 6 s + about 3 s each. About 2 minutes including reading the cache and writing to disk | about 790 MB each, about 4.0 GB for 5 |
| Ranking scores | six target terms and six columns on the development pool: about 3.5 minutes. `--repeat` about 7 minutes. The sealed pool has only 3 target terms | about 90 MB |
| Main run, 15 cells | 29 policies, 2,000 paired bootstrap draws, 2 worker processes: about 48 minutes on the development pool | tables < 5 MB. About 750 MB of temporary files per cell, deleted when done |
| Visibility comparison (step 5) | 15 cells, 14 compared policies, plus the per-job exposure scan of the old history: about 35 minutes on the development pool | five CSVs + manifest < 20 MB. Temporary peak similar to the main run |
| exact policy-specific visibility (step 6) | development pool, 15 cells, 2 worker processes: 16,690 seconds of compute in total, 15,593 seconds of wall clock (about 4.3 hours, measured 2026-09-23) | the fixed CSVs are small. The 90 compressed affected-job deltas total 211 MB (development pool) |
| online replay (step 7) | development pool, 15 cells × five frozen policies = 75 policy-cells: 33,479 seconds of compute in total, 240–728 seconds each (measured 2026-09-24). At 2 worker processes, this corresponds to about 4.7 hours of wall clock. We resumed this run in two parts, so there is no continuous wall-clock time | six CSVs + manifest are small. Compressed affected-job deltas about 170 MB (development pool). About 7.3 GB of committed memory per worker process |
| Single-server trace (step 8) | 3 minutes measured on the development pool (321 copies, 3.2 million jobs) | about 145 MB |
| Single-server run (step 9) | about 60 s for one cell (2 worker processes) | tables < 1 MB |
| Predictor metrics (step 10) | about 11 minutes measured for the 42 rows of the development pool. About half that for the three target terms of the sealed pool | < 1 MB |
| Total | about 11 hours at development-pool scale, of which the exact and online steps take about 9 hours. Less for the three terms of the sealed pool | the ten commands run sequentially, so their footprints do not add up. The peak for a single step is about 18 GB of committed memory (exact, two worker processes at about 8.5 GB each) |

These values come from the development pool (17.6 M jobs per overlay). The size of the sealed pool is unknown. Therefore this section gives only pre-freeze estimates of magnitude, which are not calibrated on sealed data. We completed both the selection on the original Guard grid and the aging selection before the freeze. Neither selection is part of the sealed run.

By default, the scripts write temporary files to the system temporary directory (`spjf_main_*` / `spjf_visibility_*`), about 750 MB per cell. They delete these files when done, but only on normal completion. Therefore each crash leaves one copy behind. For those of the ten commands that support `--scratch`, point it at a directory that you can clean yourself. Before a rerun, check and clean the corresponding leftovers. `--workers` is fixed at 2.

## 4.A The first freeze and the revision (2026-09-25)

The sealed run under the first freeze (1289aa2) failed in step 4 while it was loading the overlay traces. `clock.drop_zero_cost_terms` listed only the development terms. Therefore blocks with a cost of exactly 0 in the sealed terms stayed in the traces. After rounding, these blocks had a service time of 0. We handled this according to the rule in section 5, "a bug that really must be fixed makes it a new method". We took these steps:

- We stopped the whole run. We stopped step 6 by hand while it was fitting the frozen model, and we wrote a ledger row by hand.
- We added the three sealed terms to that list (ADR 0009).
- We archived the old lock as `docs/archive/protocol_lock_1289aa2.json`.
- We saved the old configuration byte for byte as `configs/main_frozen_1289aa2.yaml`.
- After refreezing, we reran the ten commands from step 1.

No command produced a summary table under the first freeze, and nobody saw any sealed result.

## 4.B After the sealed run (2026-09-25)

All ten commands under lock f6c1b3af finished. The run started at 19:22 and ended at 22:34 Beijing time. The laptop clock is on US Eastern time, so the log shows 07:22–10:34.

Steps 4, 6 and 7 ran in parallel. A local shell script ran steps 1–3 sequentially and then four chains: 4→5, 6, 7 and 8→9→10. The repository does not keep this script. Each command wrote one ledger row.

In step 7, the number of sampled-audit mismatches was 0 for all 75 policy-cells. In step 5, the conservative certificate was valid on the sealed cells. In step 6, every cell had zero violations in its final pass.
The per-job bound checks had 0 violations for all 315 items of the main run and all 21 items of the single-server run.

Emitting and checking used three commands. Two of them are the emit and the check with `--out-dir outputs/consistent_paper_tables` at the end of section 3.
The third is one emit into the default output directory, because the old-emit round of `check_generated.py` looks for the sealed tables in `outputs/paper_tables/`:

```bash
$UV python scripts/emit_paper_tables.py --sealed-dir outputs/sealed_tables \
    --sealed-predictor-dir outputs/sealed_predictor --sealed-visibility-dir outputs/sealed_visibility
$UV python scripts/check_preserved_outputs.py --refresh outputs/paper_tables/numbers.csv
$UV python scripts/check_preserved_outputs.py --file outputs/selection_v4_tables.json \
    --refresh outputs/paper_tables/numbers.csv
```

These results went into the paper:

- §8.2 of the main text and table `tab:visibility_sealed`
- `tab:rank_sealed`, `tab:guard_sealed`, `tab:adv_sealed` and `tab:k1_sealed` in Supplementary S10
- one sentence each in the abstract, the introduction, §7.3 and §9

We left `tab:resid_sealed` out. The emitter prints all three load levels of that table as
`\rho = 0`. The development table is rewritten through `RESPELT`, while the D1 check of the sealed table does not rewrite it. Therefore copying the table would mislead readers.
The development versions of `tab:exact_visibility_sealed`, `tab:same_copy_exposure_sealed` and `tab:visibility_audit_sealed` are not in the paper either.

While writing the paper, we found three defects in the checks and tests. We changed five locked files and declared each of them in `docs/post_run_changes.json`. ADR 0010 gives the reasons.
We did not change `protocol_lock.json`.

After the sealed run, we completed two more tasks on the development pool (2026-09-26). Both tasks read only development data.

The first task was the full comparison set of step 5h of section 1. We ran it in the same directory with
`--policies all --resume`. The five headline policies hit the existing checkpoints directly, and the script computed the other nineteen anew. In total, this gives 24 policies × 15 cells = 360 policy-cells.
In the six CSVs, the rows of the five headline policies are identical field by field to those of the five-policy run.

The second task was `scripts/online_paired_differences.py`. It gives the paired differences from the checkpoints of this run (Tables S32 and S33 of Supplementary S11). An appended section of ADR 0010 declares the new script and tests.
Neither task reads the sealed terms, and neither changes any sealed artefact.

## 5 What to do if it crashes midway

The rule is "the method is not changed after the results are seen", not "a file may be opened only once". So technical reruns are allowed, under three conditions:

1. **The lock has not changed.** Before a rerun, check that `sha256sum protocol_lock.json` matches the fingerprint from step 6 of section 2. If it does not match, the method is not the same. Stop.
2. **The code and configuration have not changed.** After a crash, do not "quickly fix something and rerun". If you really find a bug that must be fixed, the fix makes it a new method. In that case, explain the situation, refreeze, and state clearly in the ledger what the previous attempt read.
3. **Every attempt is recorded in the ledger.** The crashed attempt also gets a row, because all ten commands write the ledger in `finally`. In that row, the output column reads "运行中断于<哪一步>，未产出汇总表" ("run interrupted at <step>, no summary table produced") plus the exception type. A rerun adds another row, and the old rows stay unchanged.

   In only one case must you write a row by hand. When the process is killed outright (out of memory, power loss), Python has no chance to write the row. In that case, add the row in the six-column format above. In its output column, state which step the run reached.

How to rerun in practice:

- **The overlay or score step crashed**: rerun the whole command unchanged. These steps are deterministic, so the rerun overwrites the output with the same content.
- **The parsed-cache step crashed**: rerun it unchanged. It writes `ev_sealed.parquet` and does not touch `ev.parquet`, so a rerun
  cannot damage the development cache. If you find that the size or row count of `ev.parquet` has changed, stop at once. The change means that someone ran an old version
  of `build_cache.py`. That version overwrites the development cache in place, and every later rolling origin would then have no training rows.
- **The main run crashed midway**: rerun the whole command unchanged. Unlike parameter selection, the main run does not save results per cell. Therefore it runs all 15 cells again from the start, which takes about 48 minutes (section 4). This is simpler than filling in cells. If you really need to fill in a few cells, specify them with `--reps` / `--levels` and merge the two `main_cells.csv` files. However, you then have to check the row count of the resulting table yourself.
- **The exact step crashed**: if the lock and code are unchanged, rerun it unchanged with `--resume`. The script reuses a completed policy/cell when the hashes of the code, configuration, overlay, scores, control cache and deltas match. It refines an unfinished item from the start. Do not change policies, lag, withholding or assessment after seeing partial results. The final `exact_delta_manifest.csv` defines `deltas/`. The script does not splice together checkpoints from different inputs.
- **The machine ran out of memory and the process was killed** (the process disappears with no traceback): lower `--workers` and rerun. The commands above use 2, and 1 halves the memory. This happened once during this round of development. Another heavy job was running at the same time. When parameter selection reached the 3rd cell, the process was killed with no error message. An unchanged rerun passed.

Not allowed: changing the method after seeing part of the results, and then running again. Here the method means the promise G, (B0, η), the policy set, the metrics and the aggregation. That is not a rerun. It is a reselection.
