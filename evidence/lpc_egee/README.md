# LPC-EGEE, pooled by partition: a real recorded queue, and a weak replay validation

**Question.** Every wait in the main experiment is simulated. Is there a trace that
records queue waits and concentrated execution costs in the same system, and does the
method hold on it?

**Answer.** The LPC-EGEE grid log supplies both. It does not establish that the guard
improves the real system. At capacities fitted before the test period, expected-cost
ordering improves the simulated mean and overall p99, while the busy-hour p99 improvement
is unresolved. The work-budget guards never intervene: pooling all six queues into the
two physical partitions forces the job limit `L` to be the pool maximum of 259,200 s, so
the promise is far coarser than the observed waits. That failure is what
`evidence/lpc_egee_queues/` was built to answer, by giving each walltime class its own
pool and its own `L`.

**Paper items.** Three locations in `paper/sections/08_experiments.tex`, one in
`paper/sections/09_limitations.tex` and six in `paper/supplementary.tex`, whose source
comments name `applicability.csv`, `validation.csv`, `capacity.json`, `bound_checks.csv`
and `pooled_policy_metrics.csv`.

**Inputs.** The Parallel Workloads Archive log `LPC-EGEE-2004-1.2-cln.swf.gz`
(2,718,006 bytes, SHA256
`2fc37df5cc14c355fc7a88235f72e54fdf5f0d93de09399d015383ee5c35a59d`), downloaded once on
2026-09-21 and not redistributed here; see `data/README.md` for the download and the
archive's terms, which ask for acknowledgement of Emmanuel Medernach, Dan Tsafrir and the
archive. No project dataset and no sealed semester is read.

**Status.** Superseded on the guard question by `evidence/lpc_egee_queues/`, current as
the pooled reading the paper contrasts against it. `superseded_audit/` holds the earlier
audit that item 1 replaced after a wrong outage clock and CE2 queue limit were repaired.

**Not copied here.** 14,223 files and 405 MB became 63 files and 3.35 MB.

- `raw/LPC-EGEE-2004-1.2-cln.swf.gz` (2.72 MB) — the archive log itself, which is not
  redistributed; download it from the link in `data/README.md`.
- `jobs.csv` (20.9 MB) and `test_jobs.csv` (4.45 MB) — the parsed per-job tables, which
  are that log in another form; `audit.py` and `validate.py` rebuild them.
- `model_spjf_e.txt`, `model_spjf_log.txt`, `model_static_e.txt` (7.2 MB) — LightGBM
  dumps, rebuilt by `predict.py`.
- `predictions.npz`, `policy_waits_us.npz`, `fcfs_wait.npy` (3.7 MB) and `timings.jsonl`.
- `cache/` (14,150 files, 719 MB) — uv, numba and temporary caches.

Every table the paper cites is a `.csv`, `.json`, `.md` or `out_*.txt` file and is here.

Absolute paths that were baked into the scripts appear as `<repo-root>` (your checkout), `<cache-dir>` (a scratch directory outside the repository) and `<python-root>` (the interpreter install); set them before rerunning. Raw data is not redistributed with this folder — see `data/README.md` for where each dataset comes from.

---

## Original study notes

# LPC-EGEE recorded-wait study

This directory contains the sole input trace in `raw/`, its download record,
SWF audit, chronological capacity validation, submission-visible predictors,
policy replays, paired week-block intervals, and `REPORT.md`. All generated
files and caches stay here. No project dataset is used. The working copy of this directory is
excluded by the repository's existing `prechecks/` ignore rule.

Input: [LPC-EGEE-2004-1.2-cln.swf.gz](https://www.cs.huji.ac.il/labs/parallel/workload/l_lpc/LPC-EGEE-2004-1.2-cln.swf.gz).
Downloaded 2026-09-21 at 11:32:21.6910836 UTC, **2,718,006 bytes**.
SHA256: `2fc37df5cc14c355fc7a88235f72e54fdf5f0d93de09399d015383ee5c35a59d`.
The file was retained and its size/hash verified; it was not downloaded again.

Acknowledgement wording from the [archive](https://www.cs.huji.ac.il/labs/parallel/workload/l_lpc/):
“Emmanuel Medernach (medernac AT clermont.in2p3.fr), the author of [medernach05],
who also helped with background information and interpretation.”
We gratefully acknowledge Emmanuel Medernach for providing this log and its
background information, Dan Tsafrir for SWF conversion, and the Parallel
Workloads Archive for making it available. The archive requests a similar
acknowledgement when the log is used; it supplies no longer mandatory formula.

Run from the repository root in bash, sequentially:

```bash
bash evidence/lpc_egee/run.sh diagnose
bash evidence/lpc_egee/run.sh audit
bash evidence/lpc_egee/run.sh validate
bash evidence/lpc_egee/run.sh predict
bash evidence/lpc_egee/run.sh replay
bash evidence/lpc_egee/run.sh supplement
bash evidence/lpc_egee/run.sh report
```

`run.sh` contains the required `env -u ... uv run --no-project ... python`
invocation and confines uv/Numba/temp caches here. One process at a time,
four threads maximum; no multiprocessing. Parameters live in the scripts
and `protocol.json`; each script writes `out_<stage>.txt` and records runtime.
`timings.jsonl` includes completed invocations of the interrupted run.

The inherited audit's raw download, parsing, status filter and concurrency
calculation were sound. `superseded_audit/` preserves its code and audit tables.
Its outage filter used days after the first *cleaned* arrival in place of
original SWF days, leaving the actual outage in the sample. The corrected
audit also uses the documented 5,400-second CE2 short-queue limit. Thus item 1
was rerun for identified defects before proceeding to item 2.

The split remains the inherited day 120 after the first cleaned arrival;
the outage remains original SWF days [138,153). These are different clocks.
The main study keeps the documented disjoint 84/56-CPU physical pools and
fits one effective capacity per pool using only pre-split observations.
Queues have concurrency ceilings, not dedicated machines. No smaller pool
is selected to manufacture congestion.

`AUDIT.md` gives the filter ledger, per-queue distributions, utilisation and
applicability tables; `REPORT.md` gives the held-out verdict and proposed paper
wording. CSV/NPZ files contain the complete numerical results. `manifest.json`
records input, implementation and result hashes plus library versions.
The history features obey visibility in the recorded source log; their
counterfactual availability is separately measured in
`history_counterfactual_diagnostic.csv`. This distinction limits deployment claims.
