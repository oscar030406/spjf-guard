# Overtake-budget guard: the kernel, its per-job theorems, and the variants

**Question.** Which budget rule should the FCFS-relative guard use, and does each
candidate actually hold a per-job bound? `guardkern.py` is the simulator kernel used by
the main experiment, the cross-domain studies and the identity-residual measurement; its
docstring states and proves the two per-job theorems.

**Paper items.** Indirect but load-bearing: the kernel behind the guard rows of
Section 8, and `pareto_tables.txt` is the cross-check that
`evidence/consolidation/` uses to confirm it replays the same trace.

**Inputs.** The primary overlay rebuilt through `evidence/codebench_service_v2/`
(`build_inputs.py`); the arrays it writes go to the cache directory, not here.

**Status.** Current. It supersedes an earlier single-script bound check, which is not
included here.

Absolute paths that were baked into the scripts appear as `<repo-root>` (your checkout) and `<cache-dir>` (a scratch directory outside the repository); set both before rerunning. Raw data is not redistributed with this folder — see `data/README.md` for where each dataset comes from.

---

## Original study notes

Overtake-budget guard variants for the k-server non-preemptive queue: one simulator kernel
(`guardkern.py`, whose docstring states and proves the two per-job theorems), adversarial
verification (`brute.py`, `search_tight.py`), and runs on the real primary trace
(`build_inputs.py` -> `run_grid.py` -> `pareto.py`).

Run order (each command carries its own parameters; prefix every run with
`env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME uv run --with numpy --with numba ...`):

1. `brute.py` — kernel vs two independent reference implementations vs the project
   simulator, per-job bound asserted on ~16k small instances; counterexamples for the
   designs that have no bound.  -> `out_brute.txt`, `brute_results.csv`
2. `search_tight.py` — simulated annealing that tries to break the theorems and measures
   how much of the allowed excess an adversary reaches.  -> `out_search_tight.txt`,
   `search_tight.csv`
3. `build_inputs.py` — rebuilds the primary overlay (rep0, rep1) and the k=1
   configuration through `evidence/codebench_service_v2` (read-only import).
   -> `out_build_inputs.txt`; arrays go to `<cache-dir>/gv_inputs/*.npz`, not here.
4. `probe_speed.py` — one-off timing / window-size check.  -> `out_probe*.txt` if kept.
5. `run_grid.py <rep0|rep1|k1rep0> <level 0|1|2> <predictor> <groups>` — one row per
   policy, asserting the per-job bound on every job.  -> `results/grid_*.csv`,
   `out_grid_*.txt`
6. `pareto.py` — collects `results/` into the tables.  -> `all_runs.csv`,
   `pareto_main.csv`, `pareto_adv.csv`, `pareto_tables.txt`

Everything written by these scripts stays in this directory (plus the npz inputs in the
cache directory); no other project file is touched.
