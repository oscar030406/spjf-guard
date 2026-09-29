# Static review of physical guard semantics

## Result

The physical decision rule implements the selected `Guard(300)` instance of
Algorithm 1 correctly on the dispatcher-visible event prefix.  Its ranking,
completed-overtaker accounting, inclusive firing threshold, cap, and tie rules agree
with both the manuscript algorithm and the frozen simulator.  One manuscript metric
definition is inaccurate: the implementations count a guard **firing** whenever the
fired set is nonempty, including epochs at which the fired choice is also the base
policy's choice.  That is not always an override.

## Decision-rule comparison

| Component | Physical implementation | Frozen simulator and manuscript | Assessment |
|---|---|---|---|
| Rank and score ties | `job_id` is immutable arrival rank; the base choice minimizes `(score, job_id)` | Rank is `(arrival time, input index)` and the score heap breaks ties by rank | Match. Enqueueing preserves `job_id` order, including batches of overdue releases. |
| Completed overtaking work | `completed_work_ns - completed_by_rank.prefix_inclusive(q)` | `TC-F(q)`, where `F` includes ranks through `q` | Match. For a waiting `q`, this is exactly completed work with rank greater than `q`. |
| Cost visibility | A worker's measured holding time is added only when its completion message is received | The ideal kernel charges service only at completion, before arrivals and dispatches at the same ideal instant | Match under the physical run's explicitly logged dispatcher-visible completion semantics. A running or finished-but-unreceived job contributes zero. |
| Budget | `min(30 s + 0.5*2*age, 356 s)` | `min(B0 + eta*k*age, Bmax)` | Exact match for the frozen parameters. Here `eta*k=1`, so the physical nanosecond arithmetic introduces no rounding ambiguity. |
| Firing threshold | `over >= budget` | Algorithm 1 and both simulator channels use `>=` | Match, including equality. |
| Fired choice | Minimum `job_id` in the fired set; otherwise minimum `(score, job_id)` | Minimum rank in `E(t)`; otherwise the base policy | Match. |
| Promise arithmetic | `Bmax=2*(300-(3-2/2)*61)=356 s` | The additive and multiplicative bounds specialize to `WF+300 s` and `2*WF+274 s` | Match. |

The frozen segment-tree test is algebraically the same as the direct physical loop.
For `eta*k=en/ed`, its leaf comparison is

```
en*a_q - ed*B0 - ed*F(q) >= en*t - ed*TC,
```

which rearranges to

```
ed*(TC-F(q)) >= ed*B0 + en*(t-a_q).
```

The separate cap channel returns the queue head when its overtaking work reaches
`Bmax`.  Since overtaking work at a fixed threshold is non-increasing in rank, this is
the minimum-rank member of the capped fired set.  Taking the union of that channel and
the age-relative channel therefore implements the minimum in the budget formula.

## Metric wording mismatch

The frozen kernel sets `forced=1` whenever `E(t)` is nonempty.  It does not first ask
whether the minimum fired rank differs from the score-minimizing base choice.  The
physical implementation deliberately records both meanings:

- `guard_fired`: `E(t)` is nonempty;
- `choice_changed`: the chosen job differs from the base-policy choice.

Consequently, `n_forced`, `queue_weighted_forced`, the simulator's reported firing
rate, and the physical audit's firing counts all mean **fired-set nonempty**.  Section 5
uses this meaning when Algorithm 1 labels the `E != empty` branch “guard fires,” but
Section 3 currently defines firing rate as the share of epochs at which the guard
“overrides the base policy.” Describing the recorded statistic as an override rate
overstates changed choices whenever a fired choice also equals the base choice.

Replace that definition with:

> The \emph{firing rate} is the share of dispatch epochs at which the fired set
> $E(t)$ is non-empty, weighted by queue length; it records guard eligibility even
> when the minimum fired rank is also the base policy's choice.

If an override statistic is reported separately, it should use `choice_changed`, not
`guard_fired` or the simulator's `n_forced`.

## Physical timing boundary

The physical controller is a real-time implementation of the decision rule, not an
exact execution of the ideal queueing model.  It observes completion at dispatcher
receipt, incurs decision and pipe-send time, and dispatches two simultaneously idle
workers serially.  Time can advance and a new release can be enqueued between those
two dispatches; a worker can also finish before its completion becomes visible.  Thus
the physical system can briefly idle despite queued work and need not share the ideal
kernel's simultaneous dispatch phase.

This does not reveal a formula error in the guard.  It limits what the physical result
establishes: the event-prefix audit verifies the rule on every prefix the dispatcher
actually saw; the ideal replay verifies Algorithm 1 on the measured arrivals and
services; and the exact nanosecond comparison records whether the observed physical
waits satisfy the numerical bound against same-trace shadow FCFS.  Because the
physical controller includes OS and IPC delays outside the work-conserving model, an
observed zero-violation count is empirical implementation evidence rather than a new
application of the pathwise theorem.

Target release is likewise a workload-clock target, whereas `actual_enqueue_ns` is
the physical arrival used by the decision rule and measured-trace replay.  The input
order is preserved, so this distinction does not change rank or the guard formula; it
does mean that comparisons against frozen target offsets are nominal diagnostics,
not the same-arrival reference used for the physical bound.

## Conclusion

No blocking mismatch was found in the selected physical guard logic.  The manuscript
should correct the firing-rate definition above and keep the physical result scoped to
dispatcher-prefix conformance plus an observed same-trace bound check.
