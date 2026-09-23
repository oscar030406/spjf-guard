# Live server survey (read-only), 2026-09-23

Host 118.196.52.57 (2 vCPU / 3 GB, up 14 days; `jizhi-web` and `jizhi-engine` both active).
Source: `journalctl -u jizhi-engine` from 2026-08-04, 8,660 completed-request lines with
`path`, `status`, `durationMs`. No key file, env file or content payload was read. The
nginx access log for this site is off (`access_log off`); `/xp/wwwlogs/www.ylsc.com.log`
belongs to a different application on the same host and is irrelevant.

## Model-backed endpoints: count and service time (s)

| path | n | median | p90 | max |
|---|---|---|---|---|
| personalize/blueprint | 492 | 8.24 | 13.56 | 44.13 |
| personalize/tutor | 66 | 6.62 | 20.33 | 45.24 |
| personalize/skill-map | 204 | 0.004 (cache hits) | 38.55 | 60.31 |
| personalize/quiz-decision | 18 | 5.50 | 7.37 | 21.71 |
| personalize/verify-content | 177 | 0.017 | 0.032 | 1.62 |
| practice-scout/ai/guide (real generations) | 3 | 135.3 / 157.8 / 228.1 | | |
| practice-scout/ai/guide/chat | 5 | 2.7–50.5 | | |
| practice-scout/ai/guide/tasks (one real) | 1 | 40.0 | | |

Other guide-path lines (14–35 ms) are lookups, not generations.

## Arrivals

Blueprint calls per day: 2026-08-23 128, 08-24 61, 08-31 90, 09-02 45, 09-03 26,
09-04 64, 09-06 18, 09-07 36; every other day 0–4; after 09-08 two calls in total.
These are development-team bursts before the 09-05 competition deadline, not learner
demand. The recorded demand on the live site is therefore no better than the local
inventory (109 jobs, 3 owners) for the purposes of the paper.

## Two facts that matter for the experiment design

1. One practice-guide generation completed on the engine after 228.1 s, above the
   170 s timeout the web route applies. So the timeout is applied by the caller, and it
   is not established that the engine job is cancelled when the caller gives up. Whether
   the cap ℓ_j = 170 s is *enforced* (job killed, server freed) or only *observed* (caller
   stops waiting, server stays busy) decides whether the reservation-and-refund guard's
   assumption holds on this stack; the build must check `practice-scout/ai/guide` on
   the engine side and, if the job is not cancelled, enforce the cap in the dispatch
   module or treat the server as busy until the engine finishes.
2. Service times of the model calls are genuinely variable (blueprint max/median 5.4,
   tutor 6.8, skill-map bimodal on cache hits), which is the property the earlier
   timed-work run could not supply.

Command used (read-only): `ssh root@118.196.52.57 'journalctl -u jizhi-engine --no-pager | grep 请求完成 | ...'`.
