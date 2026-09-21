# Cross-domain check: does the method survive outside education?

**Question.** Do prediction-driven scheduling and the overtake-budget guard still work
on public non-education workloads with real arrival times and real per-job costs — the
Azure Functions 2021 invocation trace and the Intel Netbatch 2012 compute-farm log?

**Paper items.** The eta-squared column of `paper/sections/04_prediction.tex`; the
serverless and compute-farm rows and spans of `paper/sections/07_data.tex`; the
serverless, compute-farm and overlay rows of Section 8's cross-domain table; the
serverless invocation and compute-farm rows of `paper/supplementary.tex`.

**Inputs.** `data/azure_functions_2021/` and `data/intel_netbatch_2012/`; neither is
redistributed here.

**Status.** Current.

Absolute paths that were baked into the scripts appear as `<repo-root>` (your checkout) and `<cache-dir>` (a scratch directory outside the repository); set both before rerunning. Raw data is not redistributed with this folder — see `data/README.md` for where each dataset comes from.

---

## Original study notes

Cross-domain generality check: does SPJF + the overtake-budget guard still work on public NON-education workloads with real arrival times and real per-job costs — the Azure Functions 2021 invocation trace and the Intel Netbatch 2012 compute-farm log (`data/azure_functions_2021/`, `data/intel_netbatch_2012/`)?

Order: `cd_common.py` (paths, loaders, seed) -> `cd_audit.py` (fields, units, caps, tail, burstiness, entities) -> `cd_flurry.py` (which apps make the Azure load, and the trace-shaping decision) -> `cd_build.py` (leak-free features + two leak tests) -> `cd_predict.py` (LightGBM log-L2 / Tweedie on three feature sets, entity-block bootstrap) -> `cd_kernel.py` (the k-server simulator with the guard) + `cd_verify.py` (kernel vs a brute-force reference) -> `cd_sim.py` (policies on the real arrival times, per-job theorem check) -> `cd_table.py` (the comparison against the education results). Run each with `uv run --with pandas --with numpy --with scipy --with pyarrow --with lightgbm --with numba python <script>.py [azure|netbatch]`. `out_*.txt` are the run logs, `pred_*.csv` / `sim_*.csv` / `meta_*.csv` the tables; feature matrices and per-job predictions stay in the local cache directory. Nothing outside this directory is written and no education data is read.
