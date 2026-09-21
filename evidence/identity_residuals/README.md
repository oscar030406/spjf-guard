# Identity residual measured on the real trace

**Question.** Theorem 1 of the theory note had been checked exhaustively on small
synthetic instances and never measured on the trace the paper runs on. How large is the
residual of the net-overtake identity there, and how much of the per-job excess over
FCFS does it explain?

**Paper items.** The measurement behind `outputs/dev_tables/identity_residuals.csv`,
which is what `paper/sections/06_theory.tex`, `paper/sections/08_experiments.tex` and
`paper/supplementary.tex` quote; the identity residual on all nine cells reported in the
supplement.

**Inputs.** The overlay trace `<cache-dir>/mv31/traces/primary_rep0.npz` and the loaders
and selected parameters of `evidence/main_v3/v31/`; rebuild the trace with
`evidence/main_v3/v31/v31_build.py --traces primary --reps 0` if the cache is gone.

**Status.** Current.

Absolute paths that were baked into the scripts appear as `<repo-root>` (your checkout) and `<cache-dir>` (a scratch directory outside the repository); set both before rerunning. Raw data is not redistributed with this folder — see `data/README.md` for where each dataset comes from.

---

## Original study notes

Residual of the net-overtake identity (Theorem 1) measured on the real trace.

The theorem — `../guard_theory/theory.md` §3 Theorem 1, and the paper's
`paper/sections/06_theory.tex` — says that for any non-preemptive work-conserving
k-server policy P and any job i,

```
D_i := k * ( W_P[i] - W_FCFS[i] ) - ( In_i - Out_i ),       |D_i| <= 2(k-1) L
In_i  = total service of jobs that arrived after i and were dispatched before i
Out_i = total service of jobs that arrived before i and were dispatched after i
```

with the §1.1 conventions (rank = (arrival, input index); at an instant, completions,
then arrivals, then dispatches one at a time; `In`/`Out` are read off the dispatch
**sequence**, not the clock, so a job dispatched in i's own phase before i still counts
its whole service in `In_i`). It had been checked exhaustively and at random on small
synthetic instances and never measured on the trace the paper runs on. `out_SUMMARY.txt`
is that measurement.

**Result in one line.** Over 9 cells × 17,634,760 jobs the theorem holds on every job;
the residual reaches 0.485–0.521 of the bound 2(k−1)L (worst absolute 6.79 L at k = 8,
bound 14 L), is exactly 0 on 81–96% of jobs, and (In_i − Out_i)/k explains R² = 0.983 to
0.9996 of the variance of the per-job excess over FCFS.

## What is inside

| file | what |
| --- | --- |
| `ir_common.py` | paths, the microsecond convention, the three policies, the manifest, `run_policy` |
| `ir_kern.py` | **copy** of `../guard_variants/guardkern.py` (sha256 `e8b8578d…`) with the dispatch sequence and the dispatch instant recorded; the four added lines are marked `# [ir]`, nothing else differs |
| `ir_refsim.py` | **copy** of `../guard_variants_referee/refsim.py` (sha256 `1195a898…`) with the dispatch sequence recorded, same style of edit |
| `ir_overtake.py` | `In_i`, `Out_i` and the same-phase part of `In_i` by one Fenwick sweep over the dispatch sequence (O(n log n)), plus the O(n²) definition they are checked against |
| `ir_validate.py` | stage 1: proves the three tools (see below) → `out_validate.txt` |
| `ir_run.py` | stage 2: one load level per invocation → `cells.csv`, `out_run.txt` |
| `ir_report.py` | stage 3: formats `out_SUMMARY.txt`; computes nothing |
| `cells.csv` | one row per (load level, policy): 9 cells, every reported quantity |
| `out_validate.txt`, `out_run.txt` | stage logs, appended to, each invocation stamped with the code manifest |
| `out_SUMMARY.txt` | the report |

## Why a copy of the kernel

`guardkern.run` returns waits, not the dispatch sequence, and `In`/`Out` are defined by
that sequence — two jobs dispatched at the same instant are ordered by it, and which of
them overtook the other is exactly what the identity accounts for. Rather than write a
second simulator and hope it schedules identically, `ir_kern.py` is the project kernel
with two arrays filled in and returned; no branch, comparison or state update is touched.
Every run then checks the claim rather than asserting it: `ir_common.run_policy` executes
`guardkern.run` beside it on the same input and requires the two wait vectors to be equal
element for element, on all 17.6 M jobs of every cell.

## What stage 1 proves before any number is reported

On 3,000 random instances (n ≤ 40, k ≤ 6, arrival ties and equal predictions included),
drawn on a 1/64 s grid so that the float64 clock, the kernel's `round(x·1e6)` metering and
an exact-integer reference simulator all agree bit for bit — so each check below is an
equality, not a tolerance:

* **A** `ir_kern` waits == `guardkern.run` waits, every job;
* **B** the recorded dispatch sequence and start times == those of `ir_refsim.py`, the
  independently written pure-python reference simulator, every job;
* **C** the Fenwick sweep == the O(n²) definition, for `In`, `Out` and the same-phase part;
* **D** Theorem 1 holds exactly on every job (worst observed 0.879·(k−1)L);
* **E** FCFS's dispatch sequence is rank order, so `In = Out = 0` on every job.

**C** is repeated on a real slice: the densest 5,000 consecutive jobs of the primary trace
(ranks 6,690,498–6,695,497, 511 s of arrivals), at all three k and all three policies.

## Units

`In` and `Out` are exact int64 microseconds — a service time is metered as
`round(x · 1e6)`, which is how `guardkern` charges a completed overtaker, so the identity
is measured in the currency the guard itself meters. Waits are
`round(start · 1e6) − round(a · 1e6)` off the project's float64 clock, so each `D_i` can
differ from the residual of the exact float64 schedule by at most 2k µs. `ir_run.py`
computes `D` a second time entirely in float64 seconds and reports the largest difference:
it is ≤ 8 µs = 1.3e-7 L in every cell, against residuals of order L.

## How to rerun

Prefix every command with
`env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME PYTHONDONTWRITEBYTECODE=1
NUMBA_NUM_THREADS=4 OMP_NUM_THREADS=4 uv run --with numpy --with pandas --with pyarrow
--with numba --with scipy --with lightgbm python`, from this directory
(`PYTHONDONTWRITEBYTECODE=1` only keeps a one-file `__pycache__` from appearing beside
these scripts — the modules set it themselves, but too late for the first import):

```
ir_validate.py --instances 3000 --slice 5000    ~10 s   -> out_validate.txt
ir_run.py --level 0                             ~30 s   -> cells.csv, out_run.txt
ir_run.py --level 1                             ~30 s
ir_run.py --level 2                             ~30 s
ir_report.py                                    ~1 s    -> out_SUMMARY.txt
```

Inputs, all read-only and none of them rebuilt here: the overlay trace
`<cache-dir>/mv31/traces/primary_rep0.npz` and the loaders, guard algebra and selected
parameters of `../main_v3/v31/` (`v31_common.py`, `selected_params.csv`), which this
directory imports. `<cache-dir>` is
`<cache-dir>`;
if it has been cleaned, rebuild the trace with `../main_v3/v31/v31_build.py --traces
primary --reps 0` first. Numba's cache goes to `<cache-dir>/nb` — deliberately short,
because the natural `<cache-dir>/ident_res/numba_cache/...` path overruns Windows' 260
character limit and numba then fails with `FileNotFoundError`.

Generated artefacts: source = the trace above; artefacts = `cells.csv` and
`out_SUMMARY.txt`; regenerate = the run order above; check = `ir_report.py` exits
non-zero and writes nothing if any stage log carries a manifest other than the current
hash over `ir_*.py` (except `ir_report.py`, which only formats) plus `guardkern.py`,
`refsim.py`, `v31_common.py` and `selected_params.csv`.

New files of this study go in this directory; nothing outside it is written. Sealed data
(CodeBench 2023-1, 2023-2, 2024-1; the ACcoding id block 80–100%; OULAD 2014) is never
opened.

## Two things to know before quoting a number

* This overlay's load levels are **k = 8/5/4**, not 7/5/4: 7/5/4 is the k vector of
  primary overlay rep 4 and of validation overlays 0 and 3. `../main_v3/v31/trace_summary.csv`
  lists them all.
* Nothing here is held out. The trace is development data and the guard parameters were
  selected on validation overlays in `../main_v3/v31/`. The residual is a property of one
  schedule, not a sampled statistic, so no confidence interval is reported — but the
  numbers are one overlay's.
