# E-SC1: class-term resampling of the sealed terms under the online replay

Written 2026-10-23, before the run. This file does not change after the run starts.

## Claim it tests

Section 8.2 reports that Guard(600) closes 0.894 [0.862, 0.912] of the gap on the three
sealed terms at the busiest load, online protocol. The interval resamples weeks. Two
internal reviews of 2026-10-23 (items F9 and AB7 in
`docs/referee_readthrough/review_r1_20261023/verified.md`) ask what that interval covers.
On the development terms, resampling whole class-terms widens the same interval to
[-0.043, 0.894] (Supplementary Table S38). This run gives the class-term interval on the
sealed terms, so that Section 8.2 and the response to Reviewer 3, comment 7, can report it.

## Status

Post hoc. The sealed result is known (2026-09-25 run, online replay of 2026-10-01). This
run is an analysis of the uncertainty of that result. It selects nothing, and it cannot
change the method, its parameters or the point estimate, which is resample -1.

## Design

    uv run python scripts/run_online_cluster_bootstrap.py --pool sealed --unseal \
        --resamples 100 --workers 7

- Unit resampled: the class-term of the sealed pool (terms 2023-1, 2023-2, 2024-1), drawn
  with replacement, as `scripts/run_cluster_bootstrap.py` draws the development pool.
- Same seeds (`BOOT_SEED + b`), copy-count probe, week set and five overlays as the
  development run of `outputs/online_cluster_bootstrap/`.
- Replayed online: SPJF-E and Guard(300), Guard(600), Guard(1200) with the selected
  parameters. FCFS and SJF are the references of the gap.
- Fixed: `configs/main.yaml` (sha256 ecd7b34b...), the frozen sealed scores
  `data/derived/package_ranking_scores/sealed_scores.parquet` (sha256 104b2905...), the
  predictor weights and the guard selection.
- No scientific factor varies. The run measures sampling variation over class-terms only.

## Completion criteria (checked by machine)

1. Resample -1 reproduces each online cell of
   `outputs/sealed_online_visibility/online_cells.csv`: p99_dl_s equal as floats, for
   5 overlays x 3 levels x 4 policies = 60 rows. The script asserts this before it writes
   any interval.
2. All 101 x 5 part files exist, and `bootstrap_summary.csv` has 3 levels x 7 quantities.
3. Every guarded replay passes `assert_per_job_bounds`.
4. `docs/sealed_access_log.md` has the row of this run.

## Reporting rule

Each quantity is reported as the point of resample -1 with the 2.5% and 97.5% quantiles
over the 100 resamples, as in Supplementary Table S38. The interval is reported whether or
not it contains zero, in Section 8.2, a supplementary table and the response letter.
