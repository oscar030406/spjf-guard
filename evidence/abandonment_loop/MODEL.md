# Closed-loop replay with abandonment and resubmission: the model

Written on 2026-10-01 before the simulator was run on any overlay. Every parameter value
is fixed here; nothing below was changed after seeing a result. Development overlays only.

## 1. What this adds and why it is a sensitivity, not a measurement

`evidence/closed_loop/MODEL.md` replays the development overlays closed-loop in the
Zakay-Feitelson form (each submission is issued its recorded think time after the
simulated completion of the same user's previous submission) and states in its section 6
that the trace does not support an abandonment model: the source platform served every
student in a dedicated container, so no recorded job was ever abandoned and no patience
can be estimated. This study adds abandonment anyway, as a parametrised sensitivity. The
patience distribution and the resubmission probability are stated, not fitted; the grid
spans a minute to half an hour of mean patience and the three corner behaviours of a user
who gives up (always walks away, coin flip, always resubmits).

Everything in `evidence/closed_loop/MODEL.md` sections 2 and 3 (the chain, the gating
rules, the rank rule, the calendar deadline windows) is kept unchanged, with the
additions below.

## 2. Patience and the resubmission coin

A job is an input row `j` of the overlay. Its attempts are numbered `m = 0, 1, 2, 3`
(attempt 0 is the original submission; at most **3 resubmissions**).

- **Seed.** `seed = 20261001 + overlay`, so the five overlays draw independently.
- **Uniforms.** `u(seed, j, m, stream)` is a counter-based hash with the splitmix64
  finaliser `mix`: `h = mix(mix(mix(seed) ^ j) ^ (4 m + stream))` in uint64,
  `u = ((h >> 11) + 0.5) / 2^53`, so `0 < u < 1`. Stream 0 is the patience, stream 1 the
  resubmission coin. The draw depends on nothing but `(overlay, j, m)`: FCFS and every
  policy see the same patience and the same coin for the same attempt of the same job,
  and the three patience means share the same uniforms (common random numbers).
- **Patience** of attempt `m` of job `j`, in integer microseconds:
  `theta = floor(-mean_us * ln u) + 1`, an exponential with mean `mean_us` floored at
  1 microsecond, so a job never abandons at its own arrival instant.
- **Coin.** When attempt `m` abandons, the user resubmits iff `m < 3` and
  `u(seed, j, m, 1) < p_resubmit`; otherwise the job is **withdrawn** and never runs.
- One jitted function computes both draws; the kernel and the pure-Python reference call
  that same function, so a check failure cannot come from two `log` implementations.

**Grid.** mean patience in {60 s, 300 s, 1800 s}, `p_resubmit` in {0, 0.5, 1}: nine
combinations. A tenth, infinite patience, is the closed-loop replay of
`evidence/closed_loop` itself and is run as the baseline row of every cell.

## 3. The abandonment rule

Write `a'` for the realised arrival of an attempt. An attempt that is still waiting at
the instant `a' + theta` abandons at that instant:

- **resubmit**: the attempt leaves the queue and the same job re-enters as attempt
  `m + 1` at that same instant: a new arrival, a new rank, the same service time and the
  same score, a new patience draw `theta(j, m + 1)`;
- **withdraw**: the attempt leaves the queue and the job never runs.

**Event order at an instant t** (the closed-loop kernel's order with one pass added):
completions at or before t (releasing result-gated successors) -> abandonments due at or
before t -> arrivals at or before t (in `(instant, input index)` order) -> one dispatch ->
repeat all passes at the same t. A job whose patience expires at the instant a server
frees therefore abandons; it is served only if it starts strictly before `a' + theta`.

**Rank.** An attempt is ranked by `(a' of that attempt, input index of the job)`, the
closed-loop rule applied per attempt. A resubmitted attempt gets a fresh rank at the back
of the arrival order; every guard quantity (completed-work prefix sums, the budget
`min(B0 + gam w_q + eta k (t - a'_q), B_max)`, the min-rank fired job) is computed on that
rank and that `a'`. The waiting count `w_q` counts every attempt waiting at `a'_q`.

**Removal.** An abandoning attempt is removed lazily, exactly as the kernel removes a
dispatched one: its rank is marked in the `served` byte array (so the FIFO head, the score
heap and the window rebuild skip it), its segment-tree leaf is set to `NEG` in guard mode,
and the waiting count drops by one.

## 4. Gating with abandonment

- **Result-gated successor** (`delta >= 0`): released `delta` after the predecessor's
  completion **or withdrawal**, whichever ends the job. A resubmission does not release
  it: the user is still waiting on that job.
- **Submission-gated successor** (`delta < 0`): released at `a'_pred + o` where `a'_pred`
  is the arrival of the predecessor's **first** attempt; it is released once and never
  again on a resubmission.
- First submissions keep their recorded arrival.
- **Late submissions are kept** (closed_loop's treatment i). closed_loop found the two
  treatments within 1.3 % of the p99 everywhere, so the second treatment is not repeated.

## 5. Policies

From `cfg = spjf_guard.config.load('configs/main.yaml')`: FCFS, SJF (oracle, true
service time), SPJF-E, and Guard(G) for G in {300, 600, 1200} built as
`cfg._guard_from(cfg.selected(G), G, k, f"Guard({G})")` (capped 60/0.5, capped 120/0.75,
hybrid 120/0/16 per four servers). The configuration's ranking score key is `spjf_e`; the
overlay files carry no array of that name, and closed_loop ranks SPJF-E and Guard on the
stored `tweedie` array (the original-clock expected-cost score). This study does the same,
so the infinite-patience rows reproduce closed_loop's.

## 6. Metrics, per (overlay, level, patience, p_resubmit, policy)

All on the recorded deadline-window membership (`dl` flag), as closed_loop's primary.

- `p99_dl_s` (**primary**): 99th percentile of the wait of the served attempt
  (start minus that attempt's arrival) over served deadline-window jobs. This is the
  quantity the scheduler controls and the one the guard bound covers.
- `p99_dl_user_s`: the same with start minus the job's **first** submission, i.e. the
  delay the user saw including abandoned attempts.
- **Read with the withdrawn fraction.** Abandonment censors the wait distribution: the
  longest waits are the ones that end in a withdrawal, so a p99 over served jobs falls as
  more jobs leave. A policy is not better because its p99 fell while its withdrawn
  fraction rose; the two columns are reported side by side for that reason.
- `gap_closed` = (FCFS - P)/(FCFS - SJF) on `p99_dl_s`, FCFS and SJF replayed under the
  same patience and coin, each on its own realised stream; `gap_closed_user` likewise on
  `p99_dl_user_s`.
- `frac_withdrawn` (withdrawn jobs / jobs), `n_resubmissions` (resubmission events),
  `n_abandon_events`, `n_dl_withdrawn` and `frac_dl_withdrawn` (deadline-window jobs
  withdrawn).
- `max_excess_s` against reference R1 (section 7), and for guards the worst ratio to the
  bound and the violation count.
- descriptive only: `max_excess_vs_fcfs_abandon_s` and, for guards,
  `n_over_bound_vs_fcfs_abandon` against reference R2.

## 7. Which reference the guarantee is stated against

The paper's per-job bound `W <= W_FCFS + B_max/k + (3 - 2/k) L` is a sample-path statement
for any non-preemptive work-conserving k-server schedule of a given set of jobs, against
FCFS on the same arrival sequence of that set.

**R1 (asserted).** FCFS run open-loop, without abandonment, on the **served attempts**:
each served job enters at the realised arrival of the attempt that was served, with its
service time; abandoned attempts and withdrawn jobs are absent. The abandonment run,
restricted to its served attempts, is a schedule of that job set of the kind the theorem
covers:

1. withdrawn and abandoned attempts never occupy a server, so the servers process served
   attempts only;
2. it is work-conserving on that set: whenever a served attempt waits, every server is
   busy (a free server would have taken it);
3. the guard's charge on an attempt q is the completed work of later-ranked attempts,
   which are all served attempts; the rank order of served attempts is their realised
   arrival order;
4. the fired job dispatched is the min-rank fired attempt among all waiting; an abandoning
   attempt that is fired and of lower rank than q would have been dispatched, hence
   served, so on the served set the rule is the guard's rule;
5. the budget's queue-length term counts abandoning attempts too, but every budget is
   at most `B_max`, and the additive bound rests on `B_max` alone.

So the run asserts zero violations of `guard_upper_bound(W_FCFS^R1, policy, k, L)` for
every served attempt of every guarded run, exactly as `run_closed_loop.py` does against
its open-loop FCFS reference; a violation stops the run. `max_excess_s` for every non-FCFS
policy is also measured against R1 (closed_loop's convention).

**R2 (descriptive, not asserted).** FCFS with the same patience and coin, open-loop, on the
policy's realised **first-attempt** arrivals. This is not covered: under FCFS a different
set of attempts abandons, the capacity they free shortens other FCFS waits, and a job's
R2 wait can be smaller than anything the guarded run could have given it without any
defect in the guard. The excess against R2 is measured on user-perceived delay (start
minus first submission) over jobs served in both runs, and reported with the count of jobs
above the additive bound computed from that delay; it is not asserted. The random-instance
harness (check b) records how often R2 is exceeded on small instances, as the evidence for
this paragraph; R1 must hold on every instance there too.

## 8. Cells and the cost rule

Target: the 15 primary cells (overlays 0-4, levels 0-2), ten patience/coin combinations,
six policies. One level-2 combination (six policies plus their reference runs) is
profiled first; if it takes more than 90 s after the hot spot is removed, the grid runs
on levels 1-2 of all five overlays only, and REPORT.md says so.

## 9. What the model does not contain

- Patience is independent of the job, the user, the deadline and the attempt number;
  real patience before a deadline is plausibly shorter and correlated across a user's
  attempts. A user does not learn from earlier abandonments.
- A resubmission is the same job: same service, same score. A user who gives up does not
  change the code.
- Everything in closed_loop MODEL.md section 6 still holds (think times recorded at
  near-zero wait, replicated users, no content feedback).
