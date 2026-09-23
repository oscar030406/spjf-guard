# Closed-loop replay: what survives when users react to the scheduler

**Question.** The paper replays the trace open-loop: arrivals come from the log at their
recorded instants and do not react to the scheduler. A referee objected that the result
therefore cannot be read as what a scheduler would achieve against users who wait for one
result before submitting again. Does the fraction of the FCFS-to-SJF gap that the guard
closes survive a replay in which each submission is released only after its predecessor
returns, with the recorded think time preserved?

**Answer.** It does, on this trace and under this behavioural model. Every wait falls,
because a queue that builds up holds back the submissions that would have deepened it,
but the ordering of the policies and the fraction of the gap closed are intact: 0.734,
0.827 and 0.800 at the three loads open-loop against 0.825, 0.809 and 0.810 under gating.
The per-job guarantee holds on all 17.6 million jobs of each run. Section 7 of `REPORT.md`
lists what a sceptic would still attack, starting with the fact that the recorded think
times were produced on a platform that served each student immediately.

**Paper items.** The open-loop limitation paragraph and the think-time figures of
`paper/sections/09_limitations.tex`; the closed-replay sensitivity paragraph of
`paper/sections/08_experiments.tex`; supplementary Sections S6.5 and S6.6, including
Table~\ref{tab:s_closed} and the bootstrap table, whose source comments name
`out/open_vs_closed_mean.csv`, `out/think_time.json`, `out/validation.json`,
`out/closed_cells.csv`, `out/bootstrap.json` and `out/report_tables.md`.

**Inputs.** Development overlays only, read through the package's guarded loaders with
`unseal=False`: `data/derived/overlay_traces/primary_rep*.npz` and the development event
cache. No sealed semester is opened.

**Status.** Current.

**Not copied here.** `out/chains/chain_rep*.npz` (five files, 2.02 GB) — the per-user
submission chains, rebuilt by `build_chains.py`, which must run before
`run_closed_loop.py`. The numba and bytecode caches under `__pycache__/` were dropped as
build artefacts.

Absolute paths that were baked into the scripts appear as `<repo-root>` (your checkout) and `<cache-dir>` (a scratch directory outside the repository); set both before rerunning. Raw data is not redistributed with this folder — see `data/README.md` for where each dataset comes from.

---

## Original study notes

# evidence/closed_loop — closed-loop (think-time-preserving) replay

An empirical study on the **development** overlays only. It answers the referee objection
that the paper's replay is open-loop: arrivals come from the log at their recorded
instants and do not react to the scheduler, so the paper cannot claim its result is a
lower bound on what a scheduler would achieve against reacting users.

Nothing here is part of the paper's pipeline. The working copy of this directory is git-excluded and writes
only inside itself. Every sealed term (CodeBench 2023-1/2023-2/2024-1, the ACcoding id
block 80-100 %, OULAD 2014) is untouched: the scripts go through the package's guarded
loaders with `unseal=False` and read only `data/derived/overlay_traces/primary_rep*.npz`
and the development event cache.

## What is inside

| file | what it is |
| --- | --- |
| `MODEL.md` | the closed-loop model, written before the simulator was run: the chain, the gating rules, the rank rule, the deadline rule, the two edge treatments, and what the model deliberately leaves out |
| `REPORT.md` | the findings: open vs closed side by side, the mechanism, the sentences the paper could state, and what a sceptic would still attack |
| `build_chains.py` | per-user submission chains and the recorded think time $\delta$; writes `out/chains/chain_rep*.npz`, `out/think_time.json`, `out/delta_vs_cpred.csv` |
| `closed_kernel.py` | the event-driven k-server kernel with gating: a port of `spjf_guard.sim.kernel` in which arrivals are released by the chain instead of read from a sorted array |
| `run_closed_loop.py` | `validate` (gating off must reproduce the package job for job) and `run` (the experiment); writes `out/validation.json` and `out/closed_cells.csv` |
| `make_tables.py` | the side-by-side tables and the bootstrap; writes `out/open_vs_closed.csv` and `out/bootstrap.json` |
| `out/` | every result, plus the run logs |

## How to rerun

From the repository root, single process, four threads, one script at a time:

```sh
env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME \
    NUMBA_NUM_THREADS=4 OMP_NUM_THREADS=4 \
    uv run --no-sync python evidence/closed_loop/build_chains.py

env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME \
    NUMBA_NUM_THREADS=4 OMP_NUM_THREADS=4 \
    uv run --no-sync python evidence/closed_loop/run_closed_loop.py validate

env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME \
    NUMBA_NUM_THREADS=4 OMP_NUM_THREADS=4 \
    uv run --no-sync python -u evidence/closed_loop/run_closed_loop.py run \
        --reps 0,1,2 --levels 0,1,2 --keep-late 0,1

env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME \
    NUMBA_NUM_THREADS=4 OMP_NUM_THREADS=4 \
    uv run --no-sync python evidence/closed_loop/make_tables.py
```

`build_chains.py` must run first: `run_closed_loop.py` reads `out/chains/`.
`run_closed_loop.py run` rewrites `out/closed_cells.csv` after every policy, so an
interrupted run leaves a readable partial file.

## Where new files go

Results, logs and intermediate arrays go under `out/` and nowhere else; `out/chains/`
holds the per-overlay chain arrays, everything else sits directly in `out/`. A new
measurement gets its own script at this level and its own CSV or JSON in `out/`.
