# Predictor comparison, including the graph-network ablation ladder

**Question.** We compare several neural predictors of evaluation cost: a heterogeneous
graph network (G1), its shuffled-edge control (G2), the G0/G0U ablations, a hybrid (G3),
per-user recurrent models (R1, R1S) and a tabular MLP (N0). Do they beat the
gradient-boosting baselines on the same causal feature cache?

**Paper items.** Table 2 (Section 4.2), which is where the ablation ladder is read off,
and the paired comparisons of Section 4.3 (`out_evaluate_core.txt`, test semester 2022-2;
`boot_pairs_core_cold_ex.csv`); the cold-start and test-row figures of Sections 1 and 10;
the CodeBench column of Table S2 (Supplementary Section S1.5). Supplementary Section S5.4
names this folder in its text.

**Inputs.** The causal feature cache of `evidence/codebench_service_v2/`. The forward
prediction table `forward_neural.parquet` is derived student-log data and is not
included; regenerate it with `forward.py`. Per-run training logs are in `train_logs/`.

**Status.** Current.

Absolute paths that were written into the scripts appear as `<repo-root>` (your checkout) and `<cache-dir>` (a scratch directory outside the repository). Set both before you rerun a script. Raw data is not redistributed with this folder. `data/README.md` says where each dataset comes from.

---

## Original study notes

Neural predictors for the CodeBench evaluation-cost task -- G1 heterogeneous GNN, G2 shuffled-edge control, G0/G0U ablations, G3 hybrid, R1 per-user GRU, R1S GRU-stack, N0 tabular MLP -- built on the verified v2 causal feature cache and compared with the LightGBM baselines on 2022-2.

Run order: `build_base.py` (arrays + clock verification) -> `build_graph.py` (causal node-state timelines and sampled neighbour sets) -> `leaktest.py` (three leak tests) -> `train_neural.py` (GPU, one run per model/variant/seed) -> `stack_lgb.py` (uv env, LightGBM hybrids) -> `evaluate.py` (metrics + user-block paired bootstrap) -> `latency.py` / `latency_lgb.py` -> `forward.py` (rolling-origin predictions).

Results here: `metrics_2022-2_{core,remote}.csv`, `boot_pairs_{variant}_{all,cold_ex}.csv`, `boot_models_{variant}.csv`, `forward_neural.parquet` (keyed like the cache's `forward_ires0.parquet`), `fwdtab_neural.csv`. Every script writes its console log to `out_<stage>.txt`. Per-run training logs are in `train_logs/`. Large tensors stay in the local cache directory under `<cache-dir>/pn/`.

Added 2026-09-28: `multiway_boot.py` reruns the cold-task Spearman differences (G1-M4, G0U-M4, G1-G0U). It resamples tasks, assignments, and users x tasks instead of users only, because the new-task claim generalises over tasks. The results are in `multiway_boot.csv` and `out_multiway_boot.txt`.
