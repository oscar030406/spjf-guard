# Figure scripts for the revision

**Question.** Reviewer 2, Comment 1, and Reviewer 3, Comments 3, 4 and 8 asked for
figures: the bound against the worst observed excess, the gain against the quality of the
scores, and where the guard pays as the load changes.

**Paper items.** Figure 4 (`make_noise_dose.py`), Figure 5 (`make_bound_observed.py`) and
Figure 6 (`make_operating_region.py`).

**Inputs.** Each script reads only the result tables named in its docstring and records
their sha256 in the block that it writes: `../noise_dose/out/noise_dose_table.csv` (from
`outputs/revision_r1/noise_dose/`), `../../limit_family_selection/limit/limit_summary.csv`,
`../../weakness1_attack/capacity_curve.csv`, `outputs/dev_tables/main_table.csv` and
`outputs/dev_online_visibility/online_comparison.csv`.

**Status.** Complete. The scripts compute every plotted number. The figure files only draw
them.

---

`make_<label>.py` writes the marked generated block of `paper/figures/fig_<label>.tex`.
Shared helpers are in `figgen.py`. `export_figures.py` compiles every figure alone into
`paper/figures/export/` for the separate figure files. Run the scripts from the
repository root, after the studies whose tables they read.
