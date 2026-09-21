v3.1 of the consolidated main experiment: the same pipeline as `../mv3_*.py`, re-run under
its own manifest with the three changes the independent verifier asked for in
`../../main_v3_verify/out_VERDICT.txt`. The v3 report `../out_main_v3.txt` and its stage
logs are untouched; v3.1 writes `../out_main_v31.txt`. This directory is a separate
manifest, which is why it is a subdirectory: `../mv3_report.py`'s refusal rule scans
`../out_*.txt` and must not see logs from other code.

What changed, and only this:

- **F8, selection.** Guard parameters are chosen worst-case over **five** validation
  overlays as well as the three load levels (15 cells): feasible = harm ≤ G/2 in every
  cell, objective = the deadline-window p99 gap closed in the worst cell. The identical
  rule is applied to the fixed-budget family (`FIXSEL`), so "capped beats fixed at equal
  promise" is decided against the best *feasible* fixed budget rather than against
  B0 = Bmax, which the rule rejects at every G.
- **F4, the baseline.** The finite-skip baseline is charged at **dispatch** —
  `v31_skipkern.py`, whose docstring proves `W ≤ W_FCFS + (N + 2k − 2)L/k` — and gets the
  largest N that still promises G (34 instead of 30 at k = 4, G = 600 s). v3's
  completion-charged variant stays beside it as `SKIPC`.
- **F1, the manifest.** The manifest hashes the imported modules (`guardkern.py`, the v2.1
  pipeline, the referee simulator, `rs_fit.py`) as well as this study's scripts; the data
  artefacts are hashed too and logged by the build stage.

Run order (prefix: `env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME uv run
--with pandas --with numpy --with scipy --with pyarrow --with lightgbm --with numba
python`):

```
v31_build.py  --traces primary --reps 0,1,2      ~20 s   overlay traces -> scratch
v31_build.py  --traces primary --reps 3,4        ~15 s
v31_build.py  --traces valid   --reps 0,1,2,3,4  ~35 s   five validation overlays
v31_build.py  --traces t222,k1 --reps 0          ~10 s
v31_run.py --trace valid --rep {0..4} --level {0,1,2} --set grid   ~70 s each (15 cells)
v31_select.py                                     ~1 s   -> selected_params.csv
v31_run.py --trace primary --rep {0..4} --level {0,1,2} --set main ~40 s each (15 cells)
v31_run.py --trace k1 --rep 0 --level 0 --set main                 ~10 s
v31_gain.py --trace primary --reps 0,1,2,3,4      ~5 s
v31_gain.py --trace k1 --reps 0 --levels 0        ~3 s
v31_xcheck.py --small 3000 --trace primary --rep 0 --level 2  ~1 min
v31_report.py                                     ~5 s   -> ../out_main_v31.txt
```

Caches: as in `../README.md` (`<cache-dir>/cb_v2_cache_r4`,
`<cache-dir>/rank_score/rs_pred_ires0.parquet`, `<cache-dir>/mv3/r1s_forward.parquet`);
this study's own traces and bootstrap replicates go to `<cache-dir>/mv31/`.

Regenerate: source = the caches above; artefact = `../out_main_v31.txt` and the `*.csv`
here; command = the run order above; check = `v31_report.py` exits non-zero and writes
nothing if any stage log's manifest differs from the current scripts *or* from the
imported modules.

Files: `v31_common.py` (paths, parameters, guard algebra, trace/score loaders),
`v31_skipkern.py` (dispatch-charged finite skip, its bound and a literal reference),
`v31_build.py`, `v31_run.py`, `v31_select.py`, `v31_gain.py`, `v31_xcheck.py`,
`v31_report.py`; tables `trace_summary.csv`, `copies_probe_*.csv`, `select_grid.csv`,
`select_worst.csv`, `selected_params.csv`, `gain_*.csv`, `gaindiff_*.csv`,
`table_main_*.csv`, `report_*.csv`; logs `out_*.txt`.
