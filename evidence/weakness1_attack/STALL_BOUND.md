# A pathwise bound with dispatch stalls and delayed completion receipts

## Result and scope

The guard bound extends to the physical controller without coupling its dispatch
order to any ideal Guard or SPJF run. A conservative extension is

\[
W_P[i] < \min\left\{
 W_F[i]+G+\frac{J(d_i)}{k},\quad
 \frac{W_F[i]+B_0/k+(3-2/k)L+J(d_i)/k}{1-\eta}
\right\}+\ell_i.                                      \tag{1}
\]

Here \(d_i\) is the actual dispatch timestamp, \(\ell_i=s_i-d_i\) is
dispatch-to-physical-start delay, and \(W_P[i]=s_i-a_i\). The reference \(F\)
is an ideal, work-conserving FCFS run on the same actual enqueue times and
measured worker-holding costs. The additive promise is
\(G=B_{\max}/k+(3-2/k)L\). The second branch assumes the age-relative rule
with \(\gamma=0\), \(B_0\ge0\), and \(0\le\eta<1\).

The definition of \(J\) includes every released job that has not physically
started, including a job already dispatched but still awaiting IPC delivery or
worker startup. It accumulates lost capacity from the empty initial state,
not merely over the particular job's waiting interval. It has units of
worker-seconds; dividing it by \(k\) produces seconds.

For the selected parameters \(k=2,L=61,B_0=30,\eta=1/2,B_{\max}=356\),
equation (1) becomes

\[
W_P[i] < \min\{W_F[i]+300+J(d_i)/2,\quad
                     2W_F[i]+274+J(d_i)\}+\ell_i.       \tag{2}
\]

These are conditional mathematical bounds, not measured results. No value of
\(J\), no corrected maximum excess, and no empirical satisfaction of the
assumptions is asserted here. The original uncorrected 300-second promise does
not automatically follow for physical waiting times.

## Physical model and assumptions

Start both systems empty at a common time \(t_0\), before the first arrival.
There are finitely many jobs, all ultimately served, and \(k\) identical
workers. All timestamps share one monotone clock. For job \(i\), record:

| Symbol | Meaning | Physical log field |
|---|---|---|
| \(a_i\) | Actual arrival/enqueue | `actual_enqueue_ns` |
| \(\theta_i\) | Clock used in the guard decision | `decision_clock_ns` |
| \(d_i\) | Dispatch/assignment, at the beginning of IPC send | `dispatcher_dispatch_ns` |
| \(s_i\) | Physical holding interval begins | `worker_start_ns` |
| \(f_i\) | Physical holding interval ends | `worker_finish_ns` |
| \(r_i\) | Completion receipt processed by the dispatcher | `dispatcher_completion_receipt_ns` |
| \(C_i\) | True holding cost \(f_i-s_i\) | `worker_holding_ns` |

The assumptions are the following.

1. **Same jobs and costs.** \(a_i\le\theta_i\le d_i\le s_i<f_i\le r_i\),
   \(0<C_i\le L\), and rank is the order of actual arrivals, with a fixed tie
   rule. Actual arrivals at a common timestamp are all admitted before a
   decision at that timestamp; at every decision clock \(\theta\), all jobs
   with \(a_j\le\theta\) have already been admitted. Thus a lower-ranked
   unassigned job cannot become selectable only after a same-arrival
   higher-ranked job has been selected. This is the arrival-before-dispatch
   convention of the manuscript, applied to actual enqueues; it does not
   require instantaneous receipt of physical completions.
   Service means worker holding over \([s_i,f_i)\), not CPU time.
   FCFS uses precisely these \(a_i,C_i,k\), without dispatch or receipt costs.
   The FCFS reference is a mathematical replay, not a claim about the costs a
   second physical ordering would generate.
2. **Serial dispatch decisions.** Decisions and dispatches form one sequence;
   the next decision does not occur before the preceding dispatch. Jobs are
   removed from the selectable queue when assigned. No job starts before its
   dispatch, and holding intervals on one worker do not overlap.
3. **One outstanding assignment per worker.** A worker cannot receive its next
   assignment until the previous completion has been received and its full
   \(C_j\) entered in the guard's completed-work counter. At a decision there
   is a worker available for the selected job, so at most \(k-1\) earlier
   assignments remain uncharged. “Outstanding” includes an assignment not yet
   started, currently holding the worker, or finished but not yet received.
4. **Correct rule on the observed prefix.** At decision clock \(\theta\), the
   guard charges every received completion with its true holding cost and
   chooses the smallest-rank member of the fired set; otherwise it makes any
   base-policy choice. The chosen job and every smaller-rank job still awaiting
   assignment are evaluated against the same observed prefix. The budget lies
   in \([0,B_{\max}]\). For the second branch of (1), it is exactly
   \(\min(B_0+\eta k(\theta-a_q),B_{\max})\).
5. **No hidden processing.** All holding work is represented by the logged
   intervals. Dispatch, decision, transport, receipt and startup time outside
   those intervals can take arbitrarily long, but are finite. No assumption
   of instantaneous guard reaction or work conservation is made for \(P\).

The one-outstanding-assignment property is particularly important. It is
stronger than merely saying that no two payloads overlap on a worker.
Static inspection of `physical_service.py` shows the intended discipline:
completion handling adds `holding_ns` to both counters before deleting the
busy assignment and returning the worker to `idle_workers`; dispatches are
made serially from that idle set. This still requires verification on the
completed logs, including the service cap and timestamp relations.

## The measurable capacity deficit

Let

\[
b_P(t)=\#\{j:s_j\le t<f_j\},\qquad
q_*(t)=\#\{j:a_j\le t<s_j\}.
\]

Define the nondecreasing continuous quantity

\[
J(t)=\int_{t_0}^{t}(k-b_P(u))\,\mathbf1\{q_*(u)>0\}\,du.       \tag{3}
\]

Thus an idle worker contributes whenever any already released job has yet to
start physically. Several idle workers contribute separately. Natural idle
time when every released job has already started contributes zero. A reserved
job waiting for its worker is included in \(q_*\), even if the dispatcher's
selectable queue is empty. Endpoint conventions at isolated timestamps do not
affect the integral.

This definition deliberately counts all idle workers when an unstarted job
exists, even if too few jobs are present to fill all workers. That conservative
choice is used in the waiting-time accounting below; replacing the integrand
with a smaller notion of avoidable idle capacity requires a different proof.

## Lemma 1: the workload comparison with stalls

Let \(U_P(t)\) and \(U_F(t)\) count remaining holding work of all jobs released
by \(t\), including the full cost of assigned-but-not-started jobs. Then

\[
U_P(t)-U_F(t)\le(k-1)L+J(t).                              \tag{4}
\]

**Proof.** Write \(h=(k-1)L\) and \(D=U_P-U_F\). Common arrival jumps cancel,
so \(D\) is continuous and absolutely continuous between the finitely many
events. Away from event instants,
\(D'=b_F-b_P\), with \(b_F\le k\).

If \(U_P>h\), at least \(k\) unfinished jobs must be present because each has
remaining work at most \(L\). If \(b_P<k\), at least one of these jobs has
not started, so \(J'=k-b_P\). If \(b_P=k\), \(D'\le0=J'\). Therefore
\(D'\le J'\) whenever \(U_P>h\).

Set \(Z=D-J\). Whenever \(Z>h\), nonnegativity of \(U_F,J\) implies
\(U_P>h\), and hence \(Z'\le0\). The continuous function \(Z\), initially
zero, cannot have an upward excursion above \(h\): throughout any such
excursion it is nonincreasing. This proves (4), including \(k=1\).
No statement about common dispatch orders has been used. \(\square\)

## Lemma 2: dispatch-time accounting

Use the physical **dispatch sequence**, not the physical start sequence, to
define the manuscript's \(\mathrm{In}_i\) and \(\mathrm{Out}_i\). Let
\(W_D[i]=d_i-a_i\). Let \(R_i^P\) be remaining work of lower-ranked jobs at
\(a_i\). Let \(\rho_i^P\) be the remaining work at \(d_i\) of jobs assigned
strictly before \(i\) in the dispatch sequence. This last quantity includes
full costs of previous assignments not yet physically started, and zero for
finished-but-unreceived assignments. Then the exact identity is

\[
kW_D[i]=R_i^P+\mathrm{In}_i-\mathrm{Out}_i-\rho_i^P
                  +J(d_i)-J(a_i).                        \tag{5}
\]

**Proof.** Throughout \([a_i,d_i)\), job \(i\) has not started, so
\(q_*>0\). Exactly
\(kW_D[i]-[J(d_i)-J(a_i)]\) holding work is executed during that interval.
Every job executing there was assigned before \(i\). Splitting its work by
rank gives the same partition as in the manuscript: higher-ranked work is
\(\mathrm{In}_i\) minus its unfinished part at \(d_i\); lower-ranked work is
\(R_i^P-\mathrm{Out}_i\) minus its unfinished part. Assignments made at
\(d_i\) before \(i\) contribute their whole cost to both the appropriate
work sum and the residual, and execute zero before the endpoint. This proves
(5). The argument does not require physical starts to have dispatch order.
\(\square\)

For FCFS, ordinary work-conserving accounting gives
\(kW_F[i]=R_i^F-\rho_i^F\), with \(0\le\rho_i^F\le(k-1)L\).
At \(a_i\), rank \(i\) and all higher ranks have executed zero work in both
systems, including equal-arrival ties. Consequently
\(R_i^P-R_i^F=U_P(a_i)-U_F(a_i)\). Subtracting the FCFS identity from (5)
therefore gives the exact extension

\[
k(W_D[i]-W_F[i])=\mathrm{In}_i-\mathrm{Out}_i
 +(R_i^P-R_i^F)-\rho_i^P+\rho_i^F+J(d_i)-J(a_i).          \tag{6}
\]

Combining (4), \(\rho_i^P\ge0\), and the bound on \(\rho_i^F\) yields

\[
k(W_D[i]-W_F[i])
 \le \mathrm{In}_i-\mathrm{Out}_i+2(k-1)L+J(d_i).         \tag{7}
\]

The prefix \(J(a_i)\) in the workload discrepancy and the waiting-window
increment \(J(d_i)-J(a_i)\) add to exactly one \(J(d_i)\). They must not be
counted twice, and the prefix cannot simply be discarded.

## Lemma 3: delayed receipts still leave at most k uncharged overtakers

Suppose \(i\) has an overtaker, and let \(j\) be the last overtaker in the
dispatch sequence. At its decision \(\theta_j\), job \(i\) remains selectable
and has smaller rank. Choosing \(j\) therefore implies that \(i\) does not
fire, even if another job fires. Its received overtaking work \(O_i\) satisfies

\[
O_i<\mathrm{budget}(i,\theta_j)\le B_{\max}.
\]

Every overtaker assigned before \(j\) lies in exactly one of two disjoint
sets: its completion has been received and its full cost appears in \(O_i\),
or its assignment is still outstanding. At most \(k-1\) assignments of the
second kind exist, since a worker is available for \(j\). Each has full
cost at most \(L\), regardless of whether its physical execution has not
begun, is in progress, or has already finished. Adding \(j\) gives

\[
\mathrm{In}_i<B_{\max}+kL.                              \tag{8}
\]

This is the original \(kL\) accounting term, with outstanding assignments
replacing only-currently-running jobs. An arbitrarily delayed receipt does
not permit repeated uncharged overtaking on that worker: the slot remains
unavailable until the receipt has been charged. The resulting physical idle
time is recorded by (3) whenever an unstarted job exists.

There is no duplicate work in (8): received and outstanding sets are
disjoint. Likewise, (3) integrates time outside holding intervals, whereas
\(C_j\) measures time inside them. A finished-but-unreceived job has zero
remaining work in (5), though its full cost may still need the conservative
uncharged allowance in (8). These are different quantities with different
roles.

For the age-relative rule, serial decisions imply
\(\theta_j\le d_j\le d_i\), so the same argument also gives

\[
\mathrm{In}_i<B_0+\eta kW_D[i]+kL.                      \tag{9}
\]

Neither argument requires immediate recognition of physical completion or
continuous reevaluation of the fired set. It uses the rule only at the actual
decision prefix. The completed work can remain invisible between decisions.

## Proof of the result

Insert (8) in (7) and discard \(-\mathrm{Out}_i\le0\). This gives

\[
W_D[i]<W_F[i]+B_{\max}/k+(3-2/k)L+J(d_i)/k.
\]

Insert (9) instead, move \(\eta W_D[i]\) to the left, and divide by
\(1-\eta>0\). This gives

\[
W_D[i]<\frac{W_F[i]+B_0/k+(3-2/k)L+J(d_i)/k}{1-\eta}.
\]

If \(i\) has no overtaker, (7) with \(\mathrm{In}_i=0\) gives both bounds
strictly because the displayed right-hand sides retain an extra \(L>0\).
Finally \(W_P[i]=W_D[i]+\ell_i\); taking the smaller valid bound proves (1).

The correction is an ex post pathwise certificate unless the deployment also
enforces deterministic upper bounds on \(J(d_i)\) and \(\ell_i\). Finiteness
alone gives a finite bound on a finished trace, not a fixed advance promise.

## Counterexamples to tempting shorter corrections

**1. Dividing all startup delay by k is false for physical start times.**
Let \(k=2,L=1,B_{\max}=0\). At zero, release a rank-first victim and ten
unit jobs. Dispatch the victim immediately to worker 0, but let its physical
start be delayed until time 10. Worker 1 starts the ten other jobs consecutively
on \([0,1),\ldots,[9,10)\), with immediate receipts. All choices obey the
zero-budget guard on the selectable queue; the victim has already left that
queue. Then \(W_P[i]=10\), \(W_F[i]=0\), and \(J(s_i)=10\). The proposed
bound \(W_P[i]\le W_F[i]+G+J(s_i)/k\) would say \(10\le2+5\), which is
false. The separate \(\ell_i\) in (1) handles this situation. Here
\(d_i=0,J(d_i)=0,\ell_i=10\). Repeating more jobs makes the failure
arbitrarily large. No ideal/physical ordering comparison is involved.

**2. Counting idle time only during the victim's wait misses inherited backlog.**
Let \(k=1,L=1,B_{\max}=0\). Release \(M>1\) unit jobs at zero, but let the
physical dispatcher do nothing until \(T>M\). Release the rank-last victim
at \(T\), and from \(T\) onward serve jobs FCFS with no further idle time or
startup delay. The reference has cleared all \(M\) earlier jobs before \(T\),
so \(W_F[i]=0\). The victim waits \(M\), though
\(J(d_i)-J(a_i)=0\). An original-bound-plus-local-idle formula would give
only \(1\). The prefix deficit \(J(a_i)=T\) is essential in (4).

**3. The selectable queue is insufficient to measure the prefix deficit.**
Take \(k=2,L=1,B_{\max}=0\). At zero, release two unit jobs and dispatch
both, but delay both physical starts until \(T\). For \(0<t<T\), the
selectable queue is empty, so a queue-only idle integral remains zero; the
correct \(J(T)=2T\). With \(T>1\), just before \(T\) the ideal reference
is empty and \(U_P-U_F=2>(k-1)L=1\). Thus the workload lemma with the
queue-only integral is false. The two jobs are outstanding, unstarted work.

**4. Physical nonoverlap alone does not control stale completion accounting.**
Let \(k=1,L=1,B_{\max}=1/2\), with a victim and \(M\) later unit jobs
released at zero. If a worker may be reused before old completion costs are
charged, dispatch all \(M\) later jobs consecutively and withhold all their
receipts until after the victim is selected. The observed overtaking counter
stays zero and the base policy can keep selecting later jobs; \(J=0\), but
the victim waits \(M\), exceeding \(B_{\max}+L=1.5\). This violates the
one-outstanding-assignment assumption, not the decision-prefix rule.

If that assumption is absent, a measurable generalization is possible but
requires another term. At the last overtaker decision, let \(A_i\) be the
full work of prior overtakers not yet charged. Then
\(\mathrm{In}_i<\mathrm{budget}(i,\theta_j)+A_i+L\).
Replacing the right side of (1)'s additive branch by an additional
\([A_i-(k-1)L]_+/k\) is conservative; the corresponding multiplicative
branch adds this work divided by \(k(1-\eta)\). This term is zero under the
current reservation discipline. It must not be silently assumed zero for a
controller that pipelines multiple assignments per worker.

**5. A rank tie cannot override the admission-before-decision convention.**
Let \(k=1,L=1,B_{\max}=B_0=0\). Give a victim and a later-ranked unit job the
same recorded arrival time zero, but make the later-ranked job selectable and
dispatch it before admitting the victim. It runs on \([0,1)\), and the victim
starts at one. Then \(J=\ell_i=W_F[i]=0\), while \(W_P[i]=1\); the claimed
strict bound would require \(1<1\). The last-overtaker step fails because
the victim was not selectable when the overtaker was chosen. The explicit
arrival-before-decision premise excludes this inconsistent event ordering.
Postprocessing must reject it if found, even when nominal arrival ranks look
correct.

## What to verify from the completed physical logs

An exact-integer postprocessing pass can check the assumptions and (1) without
replaying any physical policy or changing the running controller.

1. **Validate the schedule and observed decisions.** Join jobs, decisions and
   events by job ID. Check unique arrivals/assignments/completions, monotone
   rank, admission of every actual arrival at or before each decision clock
   (including all equal-time ties), all timestamp inequalities,
   \(C_i=f_i-s_i\le L\), physical worker
   nonoverlap, and for successive assignments to one worker verify that the
   prior cost was charged before the next decision. Reuse the observed-prefix
   firing/choice audit. The current limit-failure count must be zero to claim
   (2); a failed service cap cannot be repaired merely by adding \(J\).
2. **Integrate J from event endpoints.** Sort the union of \(a_i,s_i,f_i,d_i\).
   At each distinct timestamp apply all changes to \(q_*\) and \(b_P\), then
   accumulate \((t_{next}-t)(k-b_P)\) if \(q_*>0\). Insert dispatch timestamps
   as query points so every \(J(d_i)\) is exact. Check \(q_*\ge0\) and
   \(0\le b_P\le k\). Use the common empty origin \(t_0\), not the start
   of a per-job window. Nanoseconds times worker count remain exact integers.
3. **Build the correct FCFS reference.** Use actual enqueue nanoseconds and
   actual \(C_i\), with the manuscript's rank and simultaneous-event rules.
   Do not substitute target releases, requested sleep durations, receipt-based
   slot occupancy, or costs measured in a different physical run. The existing
   measured-trace FCFS replay can supply this reference if those inputs match.
4. **Check identities before the bound.** Reconstruct dispatch-sequence
   \(\mathrm{In},\mathrm{Out}\), actual remaining work at arrivals and
   dispatches, and FCFS residuals. Check (6) exactly, then (4), (7), (8) and
   (9) with their stated cases. These checks locate timestamp, ordering or
   accounting mistakes that a single final excess comparison would conceal.
5. **Report separate quantities.** Report the uncorrected observed excess,
   the jobwise corrections \(J(d_i)/k\) and \(\ell_i\), both branch margins,
   and corrected violations. A bound violation check should use exact scaled
   integers. For the additive branch test
   \(k(W_P-W_F-\ell_i)<B_{\max}+(3k-2)L+J(d_i)\).
   For \(\eta=p/q\), test
   \((q-p)k(W_P-\ell_i)<qkW_F+qB_0+q(3k-2)L+qJ(d_i)\).
   Report assumption failures separately from bound violations.

Sums of decision CPU time, pipe-send time, or completion latency are not a
substitute for (3): those intervals may overlap useful holding work, and they
need not cover every empty-worker interval. The event integral measures the
specific quantity the proof uses. It may accumulate over a long run and give a
loose correction; that is a limitation of this conservative certificate.

## Sources and verification status

The derivation extends the workload comparison and busy-period accounting in
`paper/sections/06_theory.tex`, the conventions in
`paper/sections/03_problem_model.tex`, and the guard in
`paper/sections/05_scheduling.tex`. The deferred workload proof in
`paper/sections/A_proofs.tex` and the timing boundary in
`PHYSICAL_SEMANTICS_REVIEW.md` were also inspected. The current physical source
was read to establish the intended receipt-before-reuse discipline and identify
the required log fields.

The proof and five counterexamples above were checked algebraically. No Python,
physical rerun, event-log integration, empirical bound check, or sealed-data
access was performed for this note. No existing controller or report was modified.

`check_stall_bound.py` implements the exact-nanosecond audit above. It requires
the completed shared `physical_verification.json` to report PASS and binds the
frozen input, checkpoint artifacts and event file by hash. Decisions are read
one record at a time. Once the timed physical service and shared verification
have finished, the command is `python check_stall_bound.py --physical-complete`.
It writes `stall_bound_check.json`, `stall_bound_jobs.csv`, and
`out_stall_bound_check.txt`. Writing the checker does not establish its outcome;
the files it produces must be inspected after an authorized run.
