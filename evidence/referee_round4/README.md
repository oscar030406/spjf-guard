# Production-style baselines: a maximum waiting time and a fixed window

**Question.** Two controls that deployed schedulers use, and that the paper discusses,
had not been run: a maximum waiting time, MaxWait(T), and ordering by predicted cost
inside fixed windows of W jobs, Block(W). How do they compare with the guard on the
development overlays, first at T = G and then at the threshold that gives the same
promise as Guard(G)?

**Paper items.** The fixed-window paragraph of Section 8.4 (Block(512) on overlay 0,
from `maxwait_overlay0.csv`). The equal-promise comparison with the clock in the same
section uses the separate kernel of `evidence/timeout_rule/`.

**Inputs.** Development overlays `data/derived/overlay_traces/primary_rep0..4.npz` and
the stored expected-cost score; the package rows of `outputs/dev_tables/main_table.csv`
are read beside the new rows, not recomputed. No sealed data.

**Status.** Done. Each run first checks its kernel as FCFS and as SPJF-E against the
package's waits. The docstring of `maxwait_baseline.py` says the maximum waiting time
carries no per-job guarantee; that was written before Proposition `prop:clock` and is
superseded by it, as `maxwait_equal_promise.py` explains.

| File | What it is |
| --- | --- |
| `maxwait_baseline.py`, `maxwait_run.log`, `maxwait_overlay0.csv`, `maxwait_manifest.json` | MaxWait(T) and Block(W) on overlay 0 at three loads |
| `maxwait_five_overlays.py`, `maxwait_five_run.log`, `maxwait_five_cells.csv`, `maxwait_five_vs_guard.csv`, `maxwait_five_manifest.json` | MaxWait(G) on all five overlays, aggregated as Table `tab:guard` is |
| `maxwait_equal_promise.py`, `maxwait_equal_promise_run.log`, `maxwait_equal_promise_cells.csv`, `maxwait_equal_promise_vs_guard.csv`, `maxwait_equal_promise_manifest.json` | MaxWait at theta = G - (3 - 2/k)L, the equal promise, with the realised maximum excess |

Commands are in each script's docstring; run them from the repository root.
