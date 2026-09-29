# The closed-loop (think-time-preserving) replay model

Written before the simulator was run. It fixes the arrival rule, the rank rule, the
deadline rule and the two edge treatments; nothing below was changed after seeing a
result.

## 1. Why this model and not another

The paper replays recorded demand into a shared pool at the recorded instants: an
**open** workload model, in which arrivals are independent of completions. The standard
objection (Schroeder, Wierman & Harchol-Balter, *Open versus closed: a cautionary tale*,
NSDI 2006) is that the two models behave very differently, and the standard remedy for a
recorded trace is to replay the *dependency structure* rather than the timestamps: Zakay
& Feitelson, *Preserving user behavior characteristics in trace-based simulation of
parallel job scheduling*, MASCOTS 2014, extract per-user sessions and the think time
between the termination of one batch and the submission of the next, and re-issue each
job relative to the simulated completion of its predecessor. Shmueli & Feitelson, *On
simulation and design of parallel-systems schedulers: are we doing the right thing?*,
IEEE TPDS 20(7), 2009, make the same argument for site-level simulation driven by user
models.

What our trace supports is the Zakay–Feitelson construction with a session of one job:
each submission's predecessor is the same student's previous submission, and the recorded
offset between the previous *result* and the next submission is the think time. It does
not support an abandonment model or a job-content model, so those stay out (§6).

## 2. The recorded chain

A job of the overlay is a `(copy, row)` pair. Copies of a class-term are independent
users, so a user is the pair `(copy_entry, user id of job_row)`. Within one such user the
jobs are ordered by their recorded arrival $a$ (the overlay array is already in that
order, so the ordering needs no extra sort).

- **predecessor** $\mathrm{pred}(i)$: that user's previous submission in the trace, any
  exercise and any assessment. A job whose user has no earlier submission is a **first
  submission**.
- The source platform gave each student a dedicated container and served immediately, so
  the recorded completion of the predecessor is
  $\mathrm{done}_{\mathrm{pred}} = a_{\mathrm{pred}} + C_{\mathrm{pred}}$, which under the
  paper's header reading ($a = t - C$) is exactly the recorded result stamp
  $t_{\mathrm{pred}}$.
- **recorded offset (think time)** $\delta_i = a_i - \mathrm{done}_{\mathrm{pred}}$.
- **recorded inter-submission gap** $o_i = a_i - a_{\mathrm{pred}}$.

Both are computed in exact integer microseconds from the quantised arrays the simulator
uses, so the sign of $\delta_i$ is decided the same way in every run.

## 3. The replay rule

Write $a'$ for a realised arrival in the replay, $W'$ for the realised wait and
$\mathrm{done}' = a' + W' + C$ for the realised completion.

1. **First submission**: $a'_i = a_i$. It keeps its recorded arrival.
2. **Result-gated** ($\delta_i \ge 0$): the student saw the previous result before
   submitting again, so the next submission is released $\delta_i$ after the previous
   job's completion *in the replay*:
   $$a'_i = \mathrm{done}'_{\mathrm{pred}} + \delta_i .$$
3. **Submission-gated** ($\delta_i < 0$): the student submitted before the previous
   result was available, so the submission cannot have been triggered by it and the
   recorded gap between the two submissions is preserved:
   $$a'_i = a'_{\mathrm{pred}} + o_i .$$

Both rules give $a'_i \ge a'_{\mathrm{pred}}$, so a user's chain keeps its recorded order,
and in both cases $a'_i$ is known at an instant no later than $a'_i$ itself
(at $\mathrm{done}'_{\mathrm{pred}}$ in case 2, at $a'_{\mathrm{pred}}$ in case 3). Ranks
can therefore be assigned online.

**Rank.** Jobs are ranked by $(a', \text{input index})$ — realised arrival, ties to the
earlier position in the recorded trace. This is the package's own convention with $a$
replaced by $a'$. Every guard quantity (the completed-work prefix sums, the budget
$\min(B_0 + \gamma w_q + \eta k (t - a'_q), B_{\max})$, the min-rank fired job) is
computed on that rank and on $a'$.

**Per policy.** Arrivals depend on completions, so each policy generates its own arrival
sequence. FCFS, SJF, SPJF-E and Guard(600) are each replayed against their own realised
stream; nothing is shared between them but the recorded chain.

**Deadline windows stay on the calendar.** An assignment's end $a^{\mathrm{end}}$ is a
date. Each copy is a rigid whole-week shift of a class-term, so the deadline of a job on
the overlay's clock is $a^{\mathrm{end}}$ plus that copy's shift; it does not move when
the replay moves the job. Two window memberships are therefore reported:

- `p99_dl_s` uses the **recorded** membership (the `dl` flag of the overlay), so the job
  set is identical to the paper's open-loop table and the two are directly comparable;
- `p99_dl_realised_window_s` uses $a'$ against the same calendar window.

## 4. The two edge treatments

A submission whose realised arrival lands after its own assignment's end is an artefact
the model cannot settle from the data. Both readings are run and both are reported.

- **(i) late submissions kept** (`late_submissions = kept`). Every recorded submission is
  still submitted; the offered work is exactly the open-loop offered work, and only its
  placement in time changes.
- **(ii) late submissions dropped** (`late_submissions = dropped`). A submission with
  $a'_i > a^{\mathrm{end}}_i$ never enters the pool. Offered work falls; the run reports
  by how much (`n_dropped`, `offered_work_s`). A dropped submission still releases its
  successor, by the submission-gated rule $a'_{\mathrm{succ}} = a'_i + o_{\mathrm{succ}}$
  — there is no result to wait for, and cutting the chain there would silently delete the
  rest of that student's term.

## 5. What is measured against what

- **Primary**: 99th percentile of the wait among jobs in a deadline window; mean, p99 over
  all jobs, max, worst heavy-job wait; firing rate (queue-weighted and per dispatch).
- **Gap closed**: $(\mathrm{FCFS} - P)/(\mathrm{FCFS} - \mathrm{SJF})$ on `p99_dl_s`,
  with FCFS and SJF themselves replayed closed-loop, each on its own arrival sequence.
- **Harm and max excess**: against FCFS run **open-loop on the policy's own realised
  arrival sequence**. That is the counterfactual the per-job theorem is stated against —
  "the wait the same job would have had under FCFS on the same arrival stream" — and under
  gating the arrival stream is policy-specific, so FCFS's own closed-loop run is a
  different stream and is not the right comparator.
- **Guarantee**: the additive guard bound
  $W \le W_{\mathrm{FCFS}} + B_{\max}/k + (3 - 2/k)L$ evaluated per job against that same
  reference; the run reports the worst ratio to the bound and the number of violations.
- **Load**: offered work, busy-hour work and the realised busy-hour utilisation, the span
  of the trace, arrivals per hour inside deadline windows, and the drift $a' - a$.

## 6. What the model does not contain

- **No abandonment.** A student who waits never gives up, so the model cannot show a
  policy being punished by lost work. Dropping late submissions (treatment ii) is a
  calendar rule, not a patience rule.
- **No content feedback.** The service time of a job is the recorded one; a student who
  saw a result later does not submit different code.
- **The think times are recorded under near-zero wait.** The source platform served each
  student in a dedicated container, so $\delta$ is a think time measured at zero queueing
  delay. The replay assumes it is invariant to the wait; that assumption is the model, and
  it is not testable on this trace.
- **Replicated users.** A class-term is superposed 44 times, so the 68,640 chains are 44
  copies of 1,560 real student-terms. Think times are correlated across copies in a way
  real independent users would not be.
