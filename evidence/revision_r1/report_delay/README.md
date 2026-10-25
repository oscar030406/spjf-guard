# Late completion reports

**Question.** Reviewer 1, Comment 3, and Reviewer 2, Comment 4: Proposition 12 bounds the
guard when completion reports arrive up to δ late. What does such a delay cost on the real
load, and does every job stay within the bound?

**Paper items.** §8.9 and Table 14, from `out/summary.csv`; the late-report row of
Table 12 (§8.5).

**Inputs.** The five development overlays at the three loads of the main table, the
stored scores, the frozen configuration with `outputs/selection_v4/selected_parameters.csv`,
and `outputs/dev_tables/main_cells.csv` for gate 2. The three readings of a late report
follow `evidence/stale_charging/sim_stale.py`.

**Status.** Complete. The chain ran all 16 steps by 19 October 2026: 387 rows, 15 cells,
0 missing rows (`out/chain_r1_report_delay.log`, last lines). No job exceeded the bound
with late charges in any row.

---

`REPORT.md` gives the design, the gates and the results. Code: `delay_kernel.py` (a copy
of the package kernel with server identities and a heap of pending charges),
`check_reference.py` (gate 1), `run_delay.py` (one cell) and `summarize.py`.
`chain_steps.json` lists the steps in order.
