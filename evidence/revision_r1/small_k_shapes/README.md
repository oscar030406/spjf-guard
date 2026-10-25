# Budget shapes on one to three servers

**Question.** Reviewer 2, Comment 5, and Reviewer 3, Comment 7: on few servers, which
budget shape should an operator use? How much does a default that needs no grid search
give up?

**Paper items.** §8.6 (`out/guidance.csv`, `out/guidance.txt`, `out/shape_table.csv`);
Supplementary Section S13.1 and Table S35 (`out/tab_s_small_k_body.tex`); the job-check
count of Table 12 in §8.5 (`out/bound_summary.csv`).

**Inputs.** Development overlay traces at k = 1, 2 and 3, five repetitions at three
loads. The k = 1 traces are read from `outputs/steady_online_g18b/overlays/`.
`build_traces.py` rebuilds them with the package's overlay builder and checks them array by
array (gate 3), then builds the k = 2 and k = 3 traces the same way. The trace k1u80_rep0
equals `data/derived/overlay_traces/k1_rep0.npz`. Scores: the stored SPJF-E scores
(`forward_scores.parquet`, by `job_row`). Shape parameters:
`outputs/selection_v4/selected_parameters.csv`, not reselected. Gates 1 and 2 compare with
`outputs/dev_tables/k1` and `outputs/dev_tables/main_cells.csv`.

**Status.** Complete. The default rule was written before any run (`REPORT.md`, section 1).
The chain ran all 63 steps on 18 October 2026. All 56 cells report 0 bound violations, over
4,723,993,155 job checks in total (`out/chain_r1_small_k.log`, `out/bound_summary.csv`). The
output of gate 2 is in `out/gates/`.

---

`REPORT.md` gives the pre-registered default and criterion, the gates, the cost and the
results. Code: `build_traces.py`, `run_cells.py`, `gate_compare.py`, `final_table.py`,
`make_tex_table.py` and `common.py`. `chain_steps.json` lists the steps in order.
