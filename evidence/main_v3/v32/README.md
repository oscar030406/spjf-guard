v3.2 of the consolidated main experiment: the same pipeline as v3.1, re-run under its own
manifest, fixing the one CRITICAL finding against v3.1
(`../../main_v31_verify/out_VERDICT.txt`, G1). v3 and v3.1 are untouched; v3.2 writes
`../out_main_v32.txt`. Separate subfolder because it is a separate manifest.

What changed:

- **G1, the fairness fix.** v3.1 picked "the best feasible fixed budget" from four
  budgets while searching the capped family over fifteen, so the harm constraint was
  slack at the fixed point and the reported margin was an artefact of the unequal
  search. v3.2 gives both families pre-stated grids of comparable density — fixed: 39
  log-spaced constant budgets from 15·k/4 to the equal-promise budget k(G−(3−2/k)L), of
  which 27–41 are admissible per promise; capped: 9 B0 × 6 eta = 54 — plus an 18-point
  **hybrid** (a queue-length term inside the capped budget) that the rule is allowed to
  prefer. The grids are written down in `v32_common.py`'s docstring, which was frozen
  before any v3.2 number existed. Where the two families overlap (capped at eta = 0 is
  the fixed policy at the same B0) they are simulated separately and checked against
  each other: 345 pairs agree, and the worst-disagreeing pair is re-simulated and shown
  to be bit-identical job for job.
- **G3, the labels.** Every table prints B0, Bmax, Ncap and the realised promise **per
  overlay**, because overlays 0–3 run k = 8/5/4 and overlay 4 runs k = 7/5/4, and every
  budget scales with k/4.
- **G4, the sensitivity.** The report gives the selection with the single validation
  cell that decided v3.1's G = 600 choice (overlay 1, level 2) dropped, plus the whole
  feasible frontier per promise, so a reader can see how flat the choice is.
- **Requirement 5.** The report's first section is the honest conclusion, generated from
  the data rather than written in advance, including the measured excess distribution
  for the jobs FCFS already makes wait more than 60 s under both budget shapes.

Run order (prefix: `env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME uv run
--no-project --with pandas --with numpy --with scipy --with pyarrow --with lightgbm
--with numba python`; `--no-project` keeps uv from binding to the `.venv` in the project
root):

```
v32_build.py --traces primary --reps 0,1,2 | --reps 3,4 | --traces valid,k1  ~20 s each
v32_run.py --trace valid --rep {0..4} --level {0,1,2} --set grid --part {1,2} --nparts 2
                                                  ~160 s per part, 15 cells x 2 parts
v32_select.py                                     ~12 s  -> selected_params.csv
v32_run.py --trace primary --rep {0..4} --level {0,1,2} --set main   ~37 s each
v32_run.py --trace k1 --rep 0 --level 0 --set main                   ~8 s
v32_gain.py --trace primary --reps 0,1,2,3,4 ; --trace k1 --reps 0 --levels 0
v32_xcheck.py --small 3000 --trace primary --rep 0 --level 2         ~54 s
v32_report.py                                     -> ../out_main_v32.txt
```

A grid cell is ~250 simulations and does not fit in one run, so `v32_run.py`
takes `--part i --nparts n`: results are appended and already-computed policies are
skipped, so parts can run in any order and a part can be repeated without changing
anything.

Caches: as in `../README.md`; this study's traces and bootstrap replicates go to
`<cache-dir>/mv32/`. `v31_skipkern.py` is imported from `../v31` rather than copied and
is hashed into this manifest as an external module, together with `guardkern.py`, the
v2.1 pipeline, the referee simulator and `rs_fit.py`.

Regenerate: source = the caches above; artefact = `../out_main_v32.txt` and the `*.csv`
here; command = the run order above; check = `v32_report.py` exits non-zero and writes
nothing if any stage log's manifest differs from the current scripts or imported modules.

Files: `v32_common.py` (paths, the pre-stated grids, guard algebra, loaders),
`v32_build.py`, `v32_run.py`, `v32_select.py`, `v32_gain.py`, `v32_xcheck.py`,
`v32_report.py`; tables `trace_summary.csv`, `select_cells.csv`, `select_worst.csv`,
`frontier.csv`, `selected_params.csv`, `select_sensitivity.csv`, `gain_*.csv`,
`gaindiff_*.csv`, `table_main_*.csv`, `report_*.csv`; logs `out_*.txt`.
