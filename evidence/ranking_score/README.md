# Ranking score: what should a prediction-driven scheduler sort by?

**Question.** When job costs are extremely heavy-tailed, which score should a
non-preemptive scheduler sort by — a forward predictor of the mean, a quantile, the
probability of a heavy job, or a two-part model?

**Paper items.** Table `tab:scores` of `paper/sections/08_experiments.tex`
(`out_table_primary_5reps.txt`); the two-class figures quoted in the same section
(`out_sim_primary_rep0_twoclass.txt`); the asymmetry figures
(`out_sim_primary_rep0_mech.txt`).

**Inputs.** The verified simulator and feature cache of
`evidence/codebench_service_v2/`, imported read-only.

**Status.** Current.

Absolute paths that were baked into the scripts appear as `<repo-root>` (your checkout) and `<cache-dir>` (a scratch directory outside the repository); set both before rerunning. Raw data is not redistributed with this folder — see `data/README.md` for where each dataset comes from.

---

## Original study notes

Ranking-score study: which score a prediction-driven non-preemptive scheduler should sort by when job costs are extremely heavy-tailed — forward predictors of E[C_cap], quantiles, P(heavy) and a two-part model on the M4 feature set, each run through the verified simulator of `../codebench_service_v2` (imported read-only).

Files: `rs_common.py` (shared setup and study parameters) -> `rs_fit.py` (rolling-origin predictors) -> `rs_calib.py` (calibration per target semester) -> `rs_sim.py` (scheduling runs) -> `rs_gain.py` (gains + week-block bootstrap CIs) -> `rs_summary.py` (result tables) -> `rs_mech.py` (misranking decomposition); `rs_smoke.py` and `rs_check_threads.py` verify that our training loop reproduces the pipeline's. `out_*.txt` are run logs; `calib_*.csv`, `gain*.csv`, `table_*.csv`, `mech_*.csv` the tables. Predictions and per-trace arrays stay in the local cache directory (`rank_score/`), not here. New files of this study go in this directory; nothing outside it is written.
