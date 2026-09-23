# LPC-EGEE, one pool per walltime class: where the guard finally bites

**Question.** On the LPC-EGEE compute farm the earlier study pooled all six queues into
the two physical partitions, so the theorem's job limit `L` had to be the pool maximum of
259,200 s, the guard never fired and the promise was vacuous. Treating every walltime
class as its own pool, with its own `L`, its own fitted effective capacity, its own
predictor and its own replay: does the guard fire, is its per-job bound tight, and does
the paper's applicability condition 1 hold on a 900-second limit class?

**Answer.** The promise becomes real and the bound is nearly attained — with `L = 900 s`
the 3.5L allowance is 3,150 s, the budget fires at 1.4 % of dispatch epochs, and the worst
realised excess is 3,129 s against that allowance, a ratio of 0.993 against 0.046 in the
pooled study. Applicability condition 1 is not rescued: it holds on the *recorded* waits
of the 900-second `test` queue by a wide margin, but the FCFS counterfactual the condition
is actually stated on passes only at the fitted capacity `k = 1`, which is a corner of the
search grid, and fails at the queue's observed concurrency ceiling. Section 9 of
`REPORT.md` ranks what a referee will attack; the corner solution is first.

**Paper items.** The applicability and cross-domain paragraphs of
`paper/sections/08_experiments.tex` (source comments name `applicability.csv` and
`tables.md`); the forced-dispatch figures of `paper/sections/09_limitations.tex`
(`guard_dispatches.csv`); supplementary Section S7.6 and Tables~\ref{tab:s_lpc_queues}
and~\ref{tab:s_lpc_replay}, whose source comments name `tables.md`, `policy_metrics.csv`,
`bound_checks.csv`, `guard_dispatches.csv` and Sections 4, 7 and 9 of `REPORT.md`.

**Inputs.** The Parallel Workloads Archive log `LPC-EGEE-2004-1.2-cln.swf.gz`
(2,718,006 bytes, SHA256 `2fc37df5cc14c355fc7a88235f72e54fdf5f0d93de09399d015383ee5c35a59d`),
read once and not redistributed here; see `data/README.md` for the download and the
archive's terms. `src/spjf_guard` is imported read-only. No sealed semester is opened.

**Status.** Current, and mixed: positive on the bound, negative on condition 1.

**Not copied here.** The parsed per-job tables `jobs.csv` (20.7 MB) and `test_jobs.csv`
(4.2 MB), which are the archive log itself in another form and are rebuilt by `qaudit.py`
and `qvalidate.py`; the fitted LightGBM dumps `model_q1..q5.txt` (11.3 MB), rebuilt by
`qpredict.py`; the array files `predictions.npz`, `policy_waits_us.npz`,
`fcfs_wait_obs.npy`, `fcfs_wait_fit.npy` and `busy.npy`; and `cache/` (14,152 files), the
uv, numba and temporary caches. Every table the paper cites is a `.csv`, `.json`, `.md` or
`out_*.txt` file and is here. Rerunning the five stages in order rebuilds all of it.

**The study it replaces** is `evidence/lpc_egee/`, which pooled the six queues into the
two physical partitions; `README.md`, `REPORT.md` and `qcommon.py` point at it.

Absolute paths that were baked into the scripts appear as `<repo-root>` (your checkout) and `<cache-dir>` (a scratch directory outside the repository); set both before rerunning. Raw data is not redistributed with this folder — see `data/README.md` for where each dataset comes from.

---

## Original study notes

# LPC-EGEE, one pool per walltime class

A follow-up to `evidence/lpc_egee/`. That study pooled all six queues of the
LPC-EGEE log into the two physical partitions, so the theorem's `L` had to be the
pool maximum 259,200 s, the guard never fired and the promise was vacuous. Here
every walltime class is treated as its own pool with its own `L`, its own fitted
effective capacity, its own predictor and its own replay.

Nothing outside this directory is written. The input is the log already in
`../lpc_egee/raw/LPC-EGEE-2004-1.2-cln.swf.gz` (2,718,006 bytes, SHA256
`2fc37df5cc14c355fc7a88235f72e54fdf5f0d93de09399d015383ee5c35a59d`), read
read-only and not downloaded again. The previous study's scripts were copied and
adapted; its own files were not edited. `src/spjf_guard` is imported read-only.

Acknowledgement, as the [archive](https://www.cs.huji.ac.il/labs/parallel/workload/l_lpc/)
asks: we thank Emmanuel Medernach for the log and its background, Dan Tsafrir for
the SWF conversion, and the Parallel Workloads Archive.

## Contents

| file | what it holds |
| --- | --- |
| `qcommon.py` | frozen protocol constants, parsing schema, shared helpers |
| `qaudit.py` | filter ledger, per-queue distributions, per-queue concurrency |
| `qvalidate.py` | per-queue effective capacity fitted on the earlier part, held-out wait validation, applicability table |
| `qpredict.py` | per-queue submission-visible LightGBM expected-cost score |
| `qreplay.py` | per-queue FCFS/SJF/SPJF-E/Guard replays, week-block bootstrap, per-job bound checks |
| `qreport.py` | renders every table in `tables.md` from the CSVs |
| `jobs.csv`, `*.csv`, `*.json`, `*.npz` | generated results |
| `out_<stage>.txt`, `timings.jsonl` | per-stage logs and measured runtime |
| `REPORT.md` | the findings, the caveats and the wording the paper could use |
| `cache/` | uv, numba and temp caches, confined here |

New files belong in this directory only, named after the stage that writes them.

## Reproduction

From the repository root, in bash, one stage at a time:

```bash
bash evidence/lpc_egee_queues/run.sh qaudit
bash evidence/lpc_egee_queues/run.sh qvalidate
bash evidence/lpc_egee_queues/run.sh qpredict
bash evidence/lpc_egee_queues/run.sh qreplay
bash evidence/lpc_egee_queues/run.sh qreport
```

`run.sh` holds the required `env -u PYTHONHOME -u PYTHONPATH -u
UV_INTERNAL__PYTHONHOME NUMBA_NUM_THREADS=4 OMP_NUM_THREADS=4 uv run --no-project`
invocation and confines every cache here. One process at a time, four threads.
All parameters live in the scripts and in `qprotocol.json`; none is selected on
the test part.
