# User abandonment in the think-time replay

**Question.** Reviewer 2, Comment 6: users may give up on a job that waits too long and
may submit it again. Does the guard's benefit survive when the closed-loop replay of
`../closed_loop` adds abandonment and resubmission? Against which FCFS reference does the
per-job bound still hold?

**Paper items.** The abandonment paragraph of §8.8; Supplementary Section S13.3 and
Table S37. The paper's source comments name `MODEL.md`, `REPORT.md` and `out/cells.csv`.
`../revision_r1/abandonment/` prints the numbers and the table body.

**Inputs.** Development overlays only, through the package's loaders and the chain
construction of `../closed_loop` (`run_closed_loop.py`, `closed_kernel.py`), which
`run_abandon.py` imports. No sealed semester is opened.

**Status.** Complete. `MODEL.md` fixed the model and every parameter value on 1 October
2026, before the first run on an overlay. The grid has 900 rows (`out/cells.csv`). Every
guarded run kept the bound against reference R1 (450 runs, 0 violations).

---

`MODEL.md` is the model as written before the runs: patience distribution, resubmission
coin, abandonment rule, gating, policies, metrics and the two FCFS references (section 7).
`REPORT.md` gives the commands in order, the checks, the profile, the level-2 results and
the findings. The patience values are stated, not fitted, because the source platform
served every student in a dedicated container and recorded no abandonment (`MODEL.md`,
section 1).

Code: `abandon_kernel.py` (numba kernel), `run_abandon.py` (grid runner), `gated.sh` and
`run_grid.sh` (launchers), `check_reference.py` (random instances against a Python
reference), `profile_refs.py` and `make_tables.py`. Logs and results are in `out/`.
