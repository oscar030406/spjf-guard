# Cross-domain check: does the method survive outside education?

**Question.** Do prediction-driven scheduling and the overtake-budget guard still work
on public workloads outside education, with real arrival times and real per-job costs? The
two workloads are the Azure Functions 2021 invocation trace and the Intel Netbatch 2012
compute-farm log.

**Paper items.** The serverless and compute-farm rows of Table 5 (Section 7.1); the
ACcoding, Azure Functions and Netbatch rows of Table 13 (Section 8.7); Table S1 and the
variance share 0.867 of Supplementary Section S1.2; the serverless and compute-farm rows
of Table S3 and the truncation counts of Supplementary Section S2.4. Supplementary Section
S5.4 names this folder in its text.

**Inputs.** `data/azure_functions_2021/` and `data/intel_netbatch_2012/`. Neither is
redistributed here.

**Status.** Current.

Absolute paths that were written into the scripts appear as `<repo-root>` (your checkout) and `<cache-dir>` (a scratch directory outside the repository). Set both before you rerun a script. Raw data is not redistributed with this folder. `data/README.md` says where each dataset comes from.

---

## Original study notes

Cross-domain generality check: does SPJF + the overtake-budget guard still work on public NON-education workloads with real arrival times and real per-job costs — the Azure Functions 2021 invocation trace and the Intel Netbatch 2012 compute-farm log (`data/azure_functions_2021/`, `data/intel_netbatch_2012/`)?

Order: `cd_common.py` (paths, loaders, seed) -> `cd_audit.py` (fields, units, caps, tail, burstiness, entities) -> `cd_flurry.py` (which apps make the Azure load, and the trace-shaping decision) -> `cd_build.py` (leak-free features + two leak tests) -> `cd_predict.py` (LightGBM log-L2 / Tweedie on three feature sets, entity-block bootstrap) -> `cd_kernel.py` (the k-server simulator with the guard) + `cd_verify.py` (kernel vs a brute-force reference) -> `cd_sim.py` (policies on the real arrival times, per-job theorem check) -> `cd_table.py` (the comparison against the education results). Run each with `uv run --with pandas --with numpy --with scipy --with pyarrow --with lightgbm --with numba python <script>.py [azure|netbatch]`. `out_*.txt` are the run logs, `pred_*.csv` / `sim_*.csv` / `meta_*.csv` the tables. Feature matrices and per-job predictions stay in the local cache directory. Nothing outside this directory is written and no education data is read.
