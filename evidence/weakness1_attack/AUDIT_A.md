# Option A audit: another public queue trace

Audit date: 2026-09-21. This is a read-only audit of existing results. No Mozilla data
API request, download, data parse, simulation, or new measurement was made for this note.

## Decision

Do not start a full continuous-window Mozilla collection before the cheap triage result.
The earlier 132-run sample makes that collection a low-priority bet, but it did not
retain the arm64 pool's wait p99. One bounded recency probe is therefore prepared in
`probe_taskcluster.py` to fill that missing statistic after the current heavy job
finishes; it has not been run, so this audit gives no new empirical conclusion about
the arm64 wait condition. Even after it runs, its last-20-per-current-worker slice is a
triage result rather than evidence that no public system can satisfy the two
applicability conditions.

The only remaining Mozilla pool that looked materially better than the two published
pools was `releng-hardware/gecko-3-b-osx-arm64`. The existing screen found seven current
workers and 132 completed runs. The longest 1% carried 12.7% of service work. With only
132 observations, that statistic is controlled by roughly one or two runs and is not a
stable tail estimate; even its point estimate is about half of the survey's approximate
25% screening threshold. Tasks on the same pool used `maxRunTime` values 2,700, 7,200,
and 15,000 seconds. Because those task classes share workers, the applicable pool-wide
bound is at least 15,000 seconds: a recorded p99 wait would have to reach about 45,000
seconds before the requested `p99 >= 3 L` screen passed. The existing note did not
record that pool's p99 wait, so it is not legitimate to claim that the wait condition
failed. It is also not legitimate to use 2,700 seconds for a selected task class while
omitting the longer tasks that consume the same capacity.

## What the existing attempts establish

| system or pool | real recorded queue evidence | cost concentration | wait/limit screen | audit verdict |
| --- | --- | --- | --- | --- |
| Firefox CI `gecko-t-osx-1500-m4` | 191,970 services; recorded wait p99 20,675.4 s | top 1% = 3.4%; service CV 0.610 | actual maximum `maxRunTime` 10,800 s, so recorded p99 is 1.91 times the actual maximum, below 3 | validates the simulator, but fails the tail screen and the stronger actual-limit wait screen |
| Firefox CI `gecko-t-linux-talos-2404` | 30,702 services; recorded wait p99 9,881.6 s | top 1% = 5.2%; service CV 0.869 | actual maximum `maxRunTime` 7,200 s, so recorded p99 is 1.37 times the actual maximum | same conclusion |
| Other Firefox hardware pools | 31 `releng-hardware` worker types were enumerable; the best documented build-pool sample was the seven-worker arm64 pool above | arm64 top 1% = 12.7% on 132 runs; it was the heaviest documented sample | mixed actual limits up to 15,000 s; no p99 was retained in the audit note | insufficient to rule the pool out, but too weak to justify a full collection |
| Firefox and community cloud pools | public inventory found 415 Firefox worker-manager pools and 165 community pools | not material after the capacity failure | not material after the capacity failure | every worker-manager pool inspected had `minCapacity: 0`; `maxCapacity` is an autoscaling cap rather than observed fixed capacity |
| LPC-EGEE | 206,222 retained jobs with recorded waits | top 1% = 40.71% of capped work | the shared physical pool has `L=259,200` s; held-out FCFS p99/L is 0.04389 and every cohort fails the actual pool condition | heavy, but queue mixing makes the guarantee vacuous and held-out wait fidelity is weak (hourly correlations 0.44 and 0.40) |
| openSUSE OBS | enqueue, start, end, and one-job-per-slot worker IDs are public | top 1% = 41.3%; CV 6.12 | p99 wait 2,670 s versus an approximately 8 h no-output kill, about 0.09 times that operational cap | only about 0.1% of arrivals to the measured servers are visible, so simulator validation is not identified |
| ICPC event feeds | real contest submission and judgement times | corrected top 1% = 12.3--13.7% | endgame p99 = 5.1 times median problem limit | queues, but the service tail is too light |
| Chromium Swarming | exact bots for dimension-filtered pools and recorded times | top 1% = 4.5--10.1% across six samples | best documented p99 wait 2,892 s, about 0.27 times `L` | sharding flattens service costs by design |
| Apache Jenkins | real executor waits and countable labelled executors | instance top 1% = 28.4%, but the sub-pool that queues is 12.1% | documented ratios 0.3--2.8 | the heavy aggregate and the congested sub-pool are not the same queue |

The Mozilla result remains valuable for a different claim. When effective capacity and
setup are fitted on one chronological part and frozen on another, simulated/recorded
mean wait is 0.90--1.14, hourly mean-wait Pearson is 0.936--0.981, per-job Spearman is
0.940--0.963, and p90 is 0.81--1.21. This supports fidelity of the queue approximation
on these two light-tailed pools. It does not supply a pool on which the proposed policy
has both substantial cost concentration and non-vacuous protection.

The final claim in `prechecks/recorded_queue_hunt/candidates.md` that the LPC-EGEE test
queue satisfies the wait condition is superseded by `evidence/lpc_egee/REPORT.md` and
`AUDIT.md`. The short queue does not own its processors. Longer-limit queues share both
physical pools, so the theorem must use the pool maximum of 259,200 seconds rather than
the test queue's 900-second limit. The same rule applies to any proposed Mozilla
sub-population sharing a worker type.

## Why a cheap Mozilla repeat cannot answer the question

The public `queue.getWorker` response retains only the last 20 tasks for each worker.
The seven-worker arm64 screen is therefore capped at about 140 recent task references
before duplicates, incomplete runs, and filtering. Workers with different service
rates cover different time spans, so concatenating their last 20 tasks does not define
one continuous arrival window. It can cheaply falsify an obviously light tail; it
cannot establish arrival coverage, reconstruct the load offered while all seven
workers were available, or validate a replay against recorded waits.

A defensible collection has no one-call "tasks by pool" query. The existing collector
had to use this public chain:

1. `GET https://firefox-ci-tc.services.mozilla.com/api/queue/v1/provisioners/releng-hardware/worker-types`
   to enumerate hardware worker types.
2. `GET https://firefox-ci-tc.services.mozilla.com/api/queue/v1/provisioners/releng-hardware/worker-types/{workerType}/workers?limit=500`
   with continuation tokens to enumerate the current workers.
3. `GET https://treeherder.mozilla.org/api/project/{repo}/jobs/?machine_name={workerId}&push_id__gte={lo}&push_id__lte={hi}&count=2000&return_type=list`
   for every current worker and every feeding repository, recursively splitting a push
   range whenever 2,000 rows are returned.
4. `POST https://firefox-ci-tc.services.mozilla.com/api/queue/v1/tasks/status` in batches
   of at most 500 task IDs to obtain `taskQueueId` and every run's `scheduled`, `started`,
   `resolved`, and `workerId`.
5. `GET https://firefox-ci-tc.services.mozilla.com/api/queue/v1/task/{taskId}` to obtain
   the actual `payload.maxRunTime`; the established collector found that a label can be
   non-single-valued, so one task per label is not a proof of the maximum.

This chain is recorded here as a reproducible reopening path, not as a recommendation
to execute it now. In the previous two-pool study it required about 730 MB of API
responses, including 436 MB from bulk status alone, and the budget guard was mistakenly
per process rather than cumulative. A small seven-worker pool would be cheaper, but a
valid negative or positive result still needs a continuous window large enough to
estimate a p99 and a top-1% share, not another 132-run recency sample.

The prepared probe is deliberately narrower. It performs one `listWorkers` GET, one
`getWorker` GET per current worker, and two unauthenticated read-only batch lookups:
`POST /tasks/status` for true `scheduled`, `started`, and `resolved`, and `POST /tasks`
for every sampled task's actual `payload.maxRunTime`. With the previously observed seven
workers this is ten network requests; the hard cap is 25. The POSTs do not change
external state, but they are necessary because a GET-only budget of 25 requests could
retrieve at most about eight task status/definition pairs after enumerating workers and
therefore cannot estimate even a recency-sample p99. If either batch lookup is unavailable,
the script stops rather than substitute Treeherder's `submit_timestamp`: that timestamp
is Taskcluster `created`, not `scheduled`, and would mix dependency delay into queue wait.

Every response is cached without re-downloading under `raw/taskcluster_probe/`. The
manifest records method, URL, retrieval time, byte size, SHA-256, request-body hash and
the fact that no API-data licence statement was found. The request interval is 0.26 s,
the User-Agent contains no personal information, and there is no retry or polling loop.
The output explicitly describes the last-20-per-current-worker sample as triage rather
than a continuous-window p99. It reports the wait and tail screens separately: recorded
p99 must reach three times the pool-wide limit, and the longest `ceil(0.01 n)` completed
runs must carry at least 25% of sampled service. A joint pass is reported only when both
are true and every sampled task has a finite, positive `maxRunTime`. Rerun command, from
this directory:

```sh
env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME NUMBA_NUM_THREADS=4 OMP_NUM_THREADS=4 uv run --no-project --with requests python probe_taskcluster.py
```

## Arrival coverage and capacity pitfalls

1. **Current workers are not historical workers.** Treeherder enumeration by the
   current `workerId` list misses tasks run by machines retired during the window. It
   also cannot see tasks that never acquired a machine. Whole-push enumeration in the
   opposite direction is required for each new pool. The established osx study measured
   347/356, or 97.5%, coverage on three whole pushes and found 1.7% never started; that
   estimate cannot be transferred to another pool.
2. **Treeherder's apparent time filters are unsafe.** The existing study measured that
   `submit_timestamp__gte` is silently ignored. Push IDs must first be bounded with the
   push endpoint's working `startdate`/`enddate` filters. Conversely, the push endpoint's
   own `push_id__gte`/`push_id__lte` filters were ignored. A page that reaches the 2,000
   row limit must be split rather than treated as complete.
3. **Nominal worker count is not effective capacity.** The established windows saw 173
   osx workers and 105 talos workers, but held-out fits selected 155--157 and 92--96.
   Using nominal counts underestimated mean wait by factors of 1.3--2.6. For a
   seven-worker pool, one unavailable machine changes capacity by 14.3%, so a current
   worker listing is particularly weak evidence about historical `k(t)`.
4. **Task state and service accounting matter.** Pure queue wait is
   `started-scheduled`; `scheduled-created` is dependency wait. Task status contains
   retries as separate runs. Worker reuse also has a gap: the established pools needed
   median setup/teardown terms of 54 s and 127 s. A new replay must preserve priority
   then FIFO for fidelity before comparing an FCFS counterfactual.
5. **A sub-population does not acquire its own capacity bound.** A label, repository,
   architecture, or short-`maxRunTime` cohort may be analysed only while all other tasks
   sharing those workers remain in the offered load. Otherwise both arrival coverage
   and the applicable maximum service bound are understated. This is exactly the error
   corrected in the LPC-EGEE follow-up.

## Completed bounded probe on 2026-09-21

The script completed with 10 read-only requests in 6.60 seconds (0.11 seconds process
CPU). It enumerated seven current workers and their 140 recent task/run claims;
133 had completed service observations. All sampled task definitions supplied a
positive `maxRunTime`, and no measured sampled service exceeded its own limit.
Recorded queue wait had p99 11,291.53 seconds and maximum 11,530.58 seconds. Against
the 15,000-second pool limit used by the screen, p99/L was 0.753, below the required
three. The longest two completed runs (ceil(1% of 133)) contributed 7.89% of work,
below the predeclared 25% screen. Neither screen passed. We therefore stopped before
collecting a full window, fitting capacity or comparing scheduling policies.

These are measurements of a truncated recency sample, not estimates of the whole
pool's arrival stream or proof that every public queue fails. The raw response
manifest and `probe_taskcluster_summary.json` retain task/run identities, timestamps,
limits and the exact separate screen decisions.

## Reopening condition

Reopen this line only if one of two things changes: a public server-side task-by-pool
history becomes available, or enough prospectively polled data accumulates for a
continuous fixed-hardware window. Before any predictor or policy work, require all of
the following on that window: independently audited arrival coverage; historical
capacity or a frozen held-out effective-capacity fit; pool-wide actual `maxRunTime`;
recorded p99 wait at least approximately three times that limit; and a stable
cost-concentration estimate near the paper's stated heavy-tail regime. Failure of either
last two screens is a stop.

## Source files used

- `docs/related_work/shared_queue_evidence.md`, especially sections 1, 2, 3.4, and 5.1.
- `evidence/firefox_ci/README.md`, `out_collect.txt`, `out_SUMMARY.txt`,
  `fci_common.py`, and `fci_collect.py`.
- `evidence/firefox_ci_holdout/README.md` and `out_SUMMARY.txt`.
- `prechecks/recorded_queue_hunt/candidates.md`, especially sections 2.2, 3.1--3.5,
  and 4.
- `evidence/lpc_egee/REPORT.md` and `AUDIT.md` for the corrected shared-pool limit and
  validation result.
- Taskcluster's public Queue source,
  `https://github.com/taskcluster/taskcluster/blob/main/services/queue/src/api.js`, for
  the current `listWorkers`, `getWorker`, batched task and batched status routes.
- Taskcluster's worker-response schema,
  `https://github.com/taskcluster/taskcluster/blob/main/services/queue/schemas/v1/worker-response.yml`,
  for the documented 20-task recency limit.
