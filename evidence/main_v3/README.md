# Main experiment on CodeBench development data

**Question.** With the ranking score, the capped relative overtake-budget guard whose
parameters are chosen on validation overlays only, and the per-job bound asserted on
every simulated job — how much of the FCFS-to-SJF gap does the guarded policy close, and
at what cost?

**Paper items.** `out_main_v31.txt` sections 2, 4 and 5 (the trace table and the
interval rows of `paper/sections/08_experiments.tex`, rows SPJF-M4refit and SPJF-r1s, and
the finite-skip row cross-checked in section 10); `out_main_v32.txt` section 4 (the
drop-one-cell sensitivity table). Section 8 of the manuscript also names this directory
in the text, as the earlier version that used a floating-point clock and a stored copy of
the trace. `v31/table_main_primary.csv` and `v31/table_main_k1.csv` are read by
`scripts/check_reproduction.py` and `scripts/diff_dev_tables.py` in the released package.

**Read v32/ first.** `out_main_v32.txt` is the current result and supersedes both
`out_main_v31.txt` and `out_main_v3.txt`. All three are kept exactly as reported, each
under its own manifest: v3 in this directory, v3.1 in `v31/`, v3.2 in `v32/`.

**Status.** v3.2 current; v3 and v3.1 kept because the paper cites them and because each
records what the next version changed.

Absolute paths that were baked into the scripts appear as `<repo-root>` (your checkout) and `<cache-dir>` (a scratch directory outside the repository); set both before rerunning. Raw data is not redistributed with this folder — see `data/README.md` for where each dataset comes from.

---

## Original study notes

Consolidated main experiment on CodeBench development data: the Tweedie ranking score, the
capped relative overtake-budget guard whose parameters are chosen on validation semesters
only, and the k-server per-job bound asserted on every simulated job.

**Read `v32/` first. `out_main_v32.txt` is the current result; it supersedes both
`out_main_v31.txt` and `out_main_v3.txt`.** All three are kept exactly as they were
reported and verified, each under its own manifest and in its own directory:

- v3 — `mv3_*.py`, `out_main_v3.txt`, the `*.csv` in this directory.
- v3.1 — `v31/`, report `out_main_v31.txt`. Same pipeline, three changes the independent
  verifier asked for in `../main_v3_verify/out_VERDICT.txt`: selection worst-case over
  five validation overlays (F8), a fairly counted finite-skip baseline (F4), and a
  manifest that also hashes the imported modules (F1).
- v3.2 — `v32/`, report `out_main_v32.txt`. Fixes the one finding against v3.1
  (`../main_v31_verify/out_VERDICT.txt`, G1): the fixed and capped budget families are now
  searched on pre-stated grids of comparable density, a hybrid family is searched
  alongside them, and the selection's sensitivity and feasible frontier are reported.

Where they disagree, v3.2 is the current result. The main claim is weaker than v3.1's: on
an equal search the capped budget's margin over the best feasible fixed budget is about
half what v3.1 reported, and it is not resolved at the lightest load.

The rest of this file describes v3.

Everything outside this directory is imported read-only with byte compilation off
(`sys.dont_write_bytecode = True`, `NUMBA_CACHE_DIR` pointed at our own scratch):
`../codebench_service_v2/service_precheck_v2.py` (features, forward models, overlay
builder, `level_ks`, week-block bootstrap, `k1_select`, its own simulator),
`../guard_variants/guardkern.py` (the guard kernel and its per-job bound),
`../guard_variants_referee/refsim.py` (independent reference simulator),
`../ranking_score/` predictions, `../predictor_neural/` forward GRU states.
Sealed semesters 2023-1, 2023-2 and 2024-1 are never opened.

Run order (prefix every command with
`env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME uv run --with pandas --with
numpy --with scipy --with pyarrow --with lightgbm --with numba python`):

```
mv3_r1s.py    --targets 2020-ERE,2020-2                  ~30 s   forward R1S-Tweedie score
mv3_r1s.py    --targets 2021-1,2021-2,2022-1,2022-2      ~60 s
mv3_build.py  --traces primary --reps 0,1,2               ~20 s  overlay traces -> scratch
mv3_build.py  --traces primary --reps 3,4                 ~20 s
mv3_build.py  --traces valid   --reps 0,1                 ~20 s  validation trace
mv3_build.py  --traces t222,k1 --reps 0                   ~20 s  2022-2 probe, k = 1 trace
mv3_run.py --trace valid --rep 0 --level {0,1,2} --set grid  ~70 s each  selection grid
mv3_select.py                                              ~1 s  -> selected_params.csv
mv3_run.py --trace primary --rep {0..4} --level {0,1,2} --set main  ~40 s each (15 cells)
mv3_run.py --trace k1 --rep 0 --level 0 --set main         ~20 s
mv3_gain.py --trace primary --reps 0,1,2,3,4               ~10 s  gains, CIs, differences
mv3_gain.py --trace k1 --reps 0 --levels 0                  ~5 s
mv3_xcheck.py --small 2000 --trace primary --rep 0 --level 2  ~3 min  simulator agreement
mv3_report.py                                               ~5 s  -> out_main_v3.txt
```

Cache: the verified v2.1 feature/forward cache is
`<cache-dir>/cb_v2_cache_r4`, the Tweedie predictions are
`<cache-dir>/rank_score/rs_pred_ires0.parquet`, the forward GRU states are
`<cache-dir>/pn/fwdemb_R1_<semester>.npz`, where `<cache-dir>` is
`<cache-dir>`.
This study's own large artefacts (overlay traces, per-policy bootstrap replicates, the R1S
predictions) go to `<cache-dir>/mv3/`, never into the project tree. If the cache directory has
been cleaned, regenerate `cb_v2_cache_r4` with `../codebench_service_v2/README.md`'s run
order and `rs_pred_ires0.parquet` with `../ranking_score/rs_fit.py` before anything here.

Reproducibility: every stage appends to `out_<stage>.txt`, and each invocation's first
line carries one sha256 over all `mv3_*.py` except `mv3_report.py`. `mv3_report.py`
recomputes that hash and refuses to write `out_main_v3.txt` if any stage log carries a
different one, so a reported number can never come from code that has since changed.

Regenerate: source = `data/codebench/parquet/` 2018-1..2022-2 through the caches above;
artefact = `out_main_v3.txt` and the `*.csv` tables here; command = the run order above
from `mv3_r1s.py` to `mv3_report.py`; check = `mv3_report.py` exits non-zero and writes
nothing if any stage log's manifest differs from the current scripts.

Files: `mv3_common.py` (paths, parameters, guard algebra, trace/score loaders),
`mv3_r1s.py`, `mv3_build.py`, `mv3_run.py`, `mv3_select.py`, `mv3_gain.py`,
`mv3_xcheck.py`, `mv3_report.py`; tables `trace_summary.csv`, `copies_probe_*.csv`,
`select_grid.csv`, `selected_params.csv`, `r1s_targets.csv`, `gain_*.csv`,
`gaindiff_*.csv`, `table_main_*.csv`, `report_*.csv`; logs `out_*.txt`; report
`out_main_v3.txt`. New files of this study go here and nothing outside is written.
