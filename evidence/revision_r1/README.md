# Studies for the first revision

**Question.** The three reviewers of the first submission asked for new experiments,
figures and checks. Each folder below answers one request. Reviewer and comment numbers
are those of the response letters.

**Paper items.** See the table. Section, table and figure numbers are those of the revised
manuscript and Supplementary Materials.

**Inputs.** Development data only, read through the package's loaders: the overlay traces
`data/derived/overlay_traces/primary_rep*.npz`, the stored scores in
`data/derived/package_ranking_scores/forward_scores.parquet`, and the package's own result tables in `outputs/`
(`dev_tables`, `dev_online_visibility` and others, each named in the script that reads
it). Two scripts read results on sealed data. `accoding_sealed/make_tex_table.py` rounds
the summary of the run of 3 October 2026 on ACcoding's sealed part.
`sealed_online_cluster/make_tex_table.py` rounds the class-term resampling that we ran on
the sealed terms from 23 to 25 October 2026. No script here reads sealed rows.

**Status.** Complete. Every job chain ran to its last step on 18 and 19 October 2026, and
every gate passed. Each folder's `out/` holds the tables, gate outputs and run log that
the paper cites.

| folder | what it answers | paper items | request |
| --- | --- | --- | --- |
| `noise_dose` | how the gain depends on the quality of the scores, with the bound checked on every job | Figure 4 and the last paragraph of §8.3 | Reviewer 3, Comment 4 |
| `backfill_baselines` | conservative and slack-based backfilling beside the guard on the 15 main-table cells | Table 11 and its paragraph in §8.4; Supplementary Section S13.4 | Reviewer 2, Comment 3 |
| `small_k_shapes` | which budget shape to use on one to three servers, and a default that needs no grid search | §8.6; Supplementary Section S13.1 and Table S35; the job-check count of Table 12 | Reviewer 2, Comment 5; Reviewer 3, Comment 7 |
| `report_delay` | what late completion reports cost on the real load | §8.9 and Table 14; the late-report row of Table 12 | Reviewer 1, Comment 3; Reviewer 2, Comment 4 |
| `guard_overhead` | the processor time of the per-job accounts | §8.10 and Table 15 | Reviewer 3, Comment 9 |
| `abandonment` | the numbers and the table taken from the abandonment grid of `../abandonment_loop` | the abandonment paragraph of §8.8; Supplementary Section S13.3 and Table S37 | Reviewer 2, Comment 6 |
| `accoding_sealed` | the table of the run on ACcoding's sealed part | Supplementary Section S13.2 and Table S36 | Reviewer 1, Comment 4; Reviewer 3, Comment 6 |
| `online_cluster` | intervals from resampled class-terms under the online replay | Supplementary Section S13.5 and Table S38 | Reviewer 3, Comment 7 |
| `sealed_online_cluster` | the same intervals on the sealed terms, run after their result was known; `PROTOCOL.md` was committed before any interval existed | §8.2, the Introduction; Supplementary Section S13.5 and Table S39 | Reviewer 3, Comment 7 |
| `figures` | the scripts that write Figures 4, 5 and 6 from the tables they read | Figures 4 to 6 | Reviewer 2, Comment 1; Reviewer 3, Comments 3, 4 and 8 |

Three more studies for this revision are beside this folder. `../abandonment_loop` holds
the abandonment model and its grid. `../limit_family_selection` holds the time-limit
sensitivity of Figure 5(b) and the validation-only choice of a family in §7.3. It runs the
kernels of `../skipc_block_online`.

---

## Where the results are

The scripts wrote their results to `outputs/revision_r1/<folder>/`. The root README
explains why `outputs/` is not in the repository. Four kinds of file were copied into
`<folder>/out/`:

- the text files at the top of each results folder: summary tables, the LaTeX table
  bodies, gate outputs and smoke logs;
- the gate folder of `small_k_shapes` (`out/gates/`);
- the log of each folder's job chain (`out/chain_r1_*.log`);
- the per-cell tables of `report_delay` (`out/cells/`). The source of Table 12 counts
  their guarded rows.

Other per-cell CSV and JSON files, score arrays and numba caches were not copied. The commands
below rebuild them. The paper's source comments name results by their
`outputs/revision_r1/…` paths, and `../PATHS.md` maps each one to its copy.

## How to rerun

Run from the repository root with the project interpreter (`uv sync --extra dev`).

1. The five folders with a `chain_steps.json` run as a chain. Run each step's `cmd` in
   the listed order, with `{python}` replaced by the interpreter and the step's `env` set.
   Stop at the first step that fails.
2. `abandonment`, `accoding_sealed`, `online_cluster` and `sealed_online_cluster` are single scripts. Each
   docstring gives the command, the input and the output.
3. Run the `figures` scripts last, because they read the tables of the studies above.

`backfill_baselines` checks its kernel against reference implementations that are not in
this folder. Its README says which gates can run without them.
