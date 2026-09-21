# CI pool: a real shared queue whose waits were recorded

**Question.** Every queue in this project is simulated. Does the k-server
non-preemptive simulator reproduce the waits of a queue that actually exists, is shared
by several teams, is non-preemptive, and records its own waits?

**Paper items.** The CI-pool spans of `paper/sections/07_data.tex`; the share of total
work carried by the top 1% in the same section and in Section 8's cross-domain table;
the CI pool A and B rows of `paper/supplementary.tex`.

**Inputs.** `data/mozilla_firefox_ci/`, collected from Mozilla's public unauthenticated
REST APIs. Mozilla publishes no licence for those APIs, so the raw slice is not
redistributed; `run_collect.sh` re-collects it.

**Status.** Current.

Absolute paths that were baked into the scripts appear as `<repo-root>` (your checkout) and `<cache-dir>` (a scratch directory outside the repository); set both before rerunning. Raw data is not redistributed with this folder — see `data/README.md` for where each dataset comes from.

---

## Original study notes

# firefox_ci — a real shared non-preemptive queue whose waits were recorded

Every queue in this project is simulated. A referee can therefore ask whether the
congestion we optimise is real. This folder answers that with a trace from a queue that
exists, that several teams share, that is non-preemptive, and that **records the wait
itself**: the hardware worker pools of Mozilla's Firefox CI (Taskcluster), read through
the public unauthenticated REST APIs. Two things are done with it: (1) our `k`-server
simulator is replayed on the recorded arrivals and services and its output is compared
with the recorded waits; (2) the predictor, SPJF and the overtake-budget guard are run
on it under the protocol of `evidence/cross_domain/`.

Pools, window and split are frozen in `fci_common.py`. Nothing outside this directory
and `data/mozilla_firefox_ci/` is written, and no education data is read.

Result in one line: the simulator reproduces the recorded wait distribution to within
about 8% at every reported quantile on both pools (per-hour mean wait correlation
0.95-0.96), the guard's per-job bound holds on every job, and the workload turns out to
sit near the edge of the method's applicability rather than inside it — read
`out_SUMMARY.txt` sections B, D, E and G.

## Why these pools

Our model needs a (near-)constant number of executors. Taskcluster's *cloud* worker
pools autoscale, so `k` is not constant there. The `releng-hardware/*` and
`proj-autophone/*` pools are physical machines: their size moves only when a machine is
reimaged or quarantined. Six candidate pools were screened (worker count, recorded
`started - scheduled`, recorded service, tasks per day); the two that were kept are the
two largest with substantial recorded wait. The screening numbers are in
`out_collect.txt` and the reasoning in `out_SUMMARY.txt`.

The pure queue wait is `started - scheduled`, not `started - created`: a Taskcluster run
becomes claimable (`scheduled`) only once the task's dependencies have resolved, so
`scheduled - created` is dependency wait and is reported separately rather than mixed in.

## Two traps that were verified, not assumed

* Treeherder's `submit_timestamp` is Taskcluster's `created`, **not** `scheduled`
  (checked task by task against `queue.status`; see `out_collect.txt`). Treeherder alone
  therefore cannot give the pure queue wait.
* Treeherder's `submit_timestamp__gte` filter is silently ignored (recorded in
  `docs/related_work/shared_queue_evidence.md` §5.1). `push_id__gte` / `push_id__lte`
  and `machine_name` do work, and every job query here is chunked on `push_id` and
  re-split whenever a page comes back full, so the server-side limit cannot drop a row
  unseen.
* Treeherder's push endpoint also ignores `push_id__gte` / `push_id__lte` — it returned
  today's pushes for a request bounded to three weeks ago. `startdate` / `enddate` work,
  and the response echoes them back as `push_timestamp__gte` / `__lt`, which is how the
  filter can be checked. The first coverage run was wasted on this.
* `queue.listTaskQueues` and per-pool task listings need credentials;
  `queue.listWorkers`, `queue.status`, `POST queue/v1/tasks/status` (500 ids per call),
  `queue.task` and all of Treeherder do not.

## Order to run

Python is always
`env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME uv run --with <pkgs> python <script>`.

| # | source | command | artifact |
|---|---|---|---|
| 0 | `evidence/guard_variants/guardkern.py` | copied once, read-only | `guardkern_snapshot.py` |
| 1 | public APIs | `bash run_collect.sh <stage>` for `workers`, `repos`, `jobs`, `status`, `runtime`, `coverage`, `assemble` | `data/mozilla_firefox_ci/raw/**`, `data/mozilla_firefox_ci/runs_<tag>.parquet`, `out_collect.txt` |
| 1b | raw pages | `fci_scrub.py` (only after a killed run) | `out_scrub.txt` |
| 2 | the parquet | `fci_audit.py` | `out_audit.txt` |
| 3 | — | `fci_verify.py` | `out_verify.txt` |
| 4 | the parquet | `fci_simval.py [tag ...]` | `out_simval.txt`, `simval.csv`, `keff_<tag>.csv` |
| 5 | the parquet + `keff_<tag>.csv` | `fci_build.py <tag>` | `out_leaktest_<tag>.txt`, `meta_<tag>.csv`, features in the cache directory |
| 6 | features | `fci_predict.py <tag>` | `out_predict_<tag>.txt`, `pred_<tag>.csv`, predictions in the cache directory |
| 7 | predictions + `keff_<tag>.csv` | `fci_sim.py <tag>` | `out_sim_<tag>.txt`, `sim_<tag>.csv` |
| 8 | all of the above | `fci_table.py` | `out_SUMMARY.txt` |

`<tag>` is the `taskQueueId` with `/` replaced by `__`, e.g.
`releng-hardware__gecko-t-osx-1500-m4`. Step 4 must run before step 5: it fits the
effective capacity and the setup/teardown time that steps 5 and 7 then use.

Packages: `requests` for stage 1; `pandas numpy pyarrow numba requests` for 2-5, 7, 8;
plus `scipy lightgbm` for 6.

`run_collect.sh` exists because a python process doing these API calls degrades on this
host from ~0.7 s to 15-40 s per call after a few hundred requests, while a process
started at that moment is fast again. Every stage is resumable — pages are written
atomically and a page already on disk is skipped — so the driver simply restarts the
stage. The process also retires itself after `FCI_REQ_LIMIT` (default 150) requests,
because `timeout(1)` kills the `env`/`uv` wrapper while the python grandchild survives.

Politeness: one process, one request at a time, at most ~3.8 requests/second, a
descriptive `User-Agent`, exponential backoff on 429/5xx.

**Download budget: this run overran it.** The intended cap was 400 MB and the realised
total was about 730 MB. `MAX_WIRE_BYTES` in `fci_common.py` is enforced per process, not
cumulatively across the stages, and the Taskcluster bulk-status endpoint returns about
1 kB per task uncompressed (844 pages x 0.52 MB = 436 MB on its own). About 140 MB was
avoidable waste: talos status pages fetched against an id list that was then narrowed,
and coverage pages for pushes that turned out to be outside the window. Anyone rerunning
this should make the cap cumulative (persist the counter to disk) before starting.

The second pool's window is narrowed to 7 days (`POOL_WINDOW` in `fci_common.py`) for
the same budget reason; the first pool keeps the full 21 days and 255k tasks.

## `guardkern_snapshot.py`

A byte-identical copy of `evidence/guard_variants/guardkern.py` as it stood when this
study started, taken because the original was being revised in parallel. Do not edit it here.

    sha256(evidence/guard_variants/guardkern.py at copy time, 2026-09-19)
      = 5579cbb61837a07e218fc7ed85da8b34191676b12e689e254af3354d40114c12
    sha256(evidence/firefox_ci/guardkern_snapshot.py)
      = 5579cbb61837a07e218fc7ed85da8b34191676b12e689e254af3354d40114c12
    sha256(evidence/guard_variants/guardkern.py when this study finished)
      = e8b8578d5b53874440d2f37f285bc422c127512595b544fe5427b5a3acdd1c58

The original changed while this study ran, in parallel work on the guard kernel. Every number in
`out_SUMMARY.txt` comes from the snapshot, so before quoting them in the paper, diff the
two files and rerun steps 4-8 if the kernel's behaviour changed.

`fci_simval.py` carries a second, independent simulator (the one that supports a
time-varying `k(t)`); `fci_verify.py` checks it against the snapshot job by job on random
instances before any result is read, and `fci_simval.py` repeats that check on the real
trace.

## What is in `out_SUMMARY.txt`

Pool, window, run counts, `k`, the coverage estimate, how close the simulator gets to the
recorded waits and what explains the residual, the prediction table, the scheduling
table in the format of `evidence/cross_domain/out_cross_domain_table.txt`, the
applicability ratio `FCFS p99 wait / L'`, and the list of what may and may not be
claimed in the paper.

## Data

`data/mozilla_firefox_ci/` holds the raw API pages and the assembled parquet. Mozilla
publishes no licence for these APIs, so the raw slice is not redistributed; see the row
in `data/README.md`.
