# Feedback on the open-loop lower-bound claim

## Finding

The lower-bound claim is false. A faster first completion can release a successor
earlier, but this fact alone does not determine the sign of the change in mean wait,
a waiting-time quantile, or a policy-relative latency benefit. The extra work may
arrive while a long non-preemptive job is running and wait behind it, or it may arrive
just before a dispatch epoch and allow SJF to avoid starting that long job. Both
directions occur with one server, exact service times, finite user programs, and fixed
positive think times.

The constructions below are logical counterexamples to a universal bound, not
estimates of an empirical causal effect. They use seconds as the time unit and a
deterministic single-server queueing model. Every user follows a fixed finite submission script,
and each successor is submitted exactly after its user's fixed think time.
All arrivals under every compared path occur by 24 seconds. Taking the deadline at
time 24 seconds puts every arrival in the common 24-hour window
\([-86{,}376,24]\) seconds; as in the paper, jobs remain in the cohort when they
start or finish after the arrival window.

This objection is independent of prediction error and of the guard. It already holds
for exact SJF versus FCFS. It concerns the causal interpretation of policy benefit,
not the validity of the pathwise per-job guard theorem.

## What feedback does not invalidate: the pathwise theorem

The theoretical guarantee allows an arbitrary arrival sample path. It therefore also
allows a path generated adaptively by earlier completions. After a closed-loop run of
policy (P), freeze its realised jobs, arrival times, executed service times, and
scores, and replay FCFS on exactly that finite sequence. Call the result *shadow
FCFS*. The existing proof applies without a distributional or exogeneity assumption:

\[
  W_P[i;A^P,C^P]-W_{\mathrm{shadow\text{-}FCFS}}[i;A^P,C^P]
  \leq G
\]

for every job (i), whenever (P) is the guarded policy with promise (G). Shadow
FCFS is an offline or delayed conditional reference. A service cost is hidden until
its job actually completes, so exact reference starts for the unfinished prefix need
not be available online. As costs are revealed, a checker can recompute the known
prefix; after the relevant run has completed, retaining each realised enqueue instant
and executed cost is sufficient to replay the reference exactly. No model of think
time is needed for this conditional benchmark.

Shadow FCFS is not the independently operated closed-loop FCFS counterfactual. If
FCFS had actually controlled service, its different completion times would have
generated (A^F), rather than retaining (A^P). For a common job identity (i), the
policy comparison decomposes as

\[
\begin{aligned}
  W_P[i;A^P]-W_F[i;A^F]
  ={}& \underbrace{W_P[i;A^P]-W_F[i;A^P]}_{\text{pathwise term bounded by the theorem}} \\
     &+\underbrace{W_F[i;A^P]-W_F[i;A^F]}_{\text{feedback/transport term, no stated bound}}.
\end{aligned}
\]

If feedback also changes which jobs exist or their service requirements, even the
common-identity welfare comparison needs an additional estimand and coupling. The
theorem remains a valid conditional statement on each realised sequence; it does not
identify the second term or a benefit between two independently evolving systems.

## The estimands are different

Let (F) denote FCFS, (S) denote SJF, (A^P) be the arrival vector induced when
policy (P) controls completion times, and (M(P,A;C)) be mean waiting time under
policy (P), arrival vector (A), and cohort (C). Suppose, in the strongest case
for the paper's interpretation, that the logged arrivals are the FCFS-induced arrivals
(A^F), and suppose the same finite set (C) of job identities eventually appears
under both policies. The fixed-arrival replay estimates

\[
  \Delta_{\mathrm{open}}
  = M(F,A^F;C)-M(S,A^F;C),
\]

whereas the corresponding closed-loop comparison is

\[
  \Delta_{\mathrm{closed}}
  = M(F,A^F;C)-M(S,A^S;C).
\]

Therefore

\[
  \Delta_{\mathrm{closed}}-\Delta_{\mathrm{open}}
  = M(S,A^F;C)-M(S,A^S;C).
\]

The assertion that the replay is a lower bound requires
(M(S,A^F;C)\geq M(S,A^S;C)). There is no such monotonicity for a
non-preemptive queue. Counterexample 1 makes the right-hand side negative;
Counterexample 2 makes it positive. If the logged system did not run FCFS, two further
transport terms enter the comparison, so the direction is even less identified.

Lower mean latency and larger policy-relative benefit must also be kept separate. A
policy can finish one user earlier and thereby increase completed work or arrivals by
a horizon, yet have a smaller latency advantage because that induced work creates
congestion. Throughput and latency are distinct outcomes; an increase in the former
does not order the latter.

## Counterexample 1: fixed replay overstates the benefit and reverses its sign

There is one non-preemptive model server, and one time unit is one second. At
$t=0$, jobs $A_1$ and $B_1$ arrive in that FCFS order, with service times 10
seconds and 1 second. User A has no successor. User B follows a fixed two-submission
script: $B_2$, also of service time 1 second, is submitted after the fixed think
time $z_B=1/2$ second:

\[
  a(B_2)=d(B_1)+\tfrac12,
\]

where $d$ is completion time. The eventual cohort is identically
$C=\{A_1,B_1,B_2\}$ under every policy, and all three job identities are averaged.

FCFS generates the logged arrival vector:

| Policy/path | Job | Arrival | Start | Completion | Wait |
|---|---:|---:|---:|---:|---:|
| FCFS closed | (A_1) | 0 | 0 | 10 | 0 |
|  | (B_1) | 0 | 10 | 11 | 10 |
|  | (B_2) | (23/2) | (23/2) | (25/2) | 0 |

Thus (M(F,A^F;C)=10/3). Replaying those arrivals under SJF gives
(B_1:[0,1]), (A_1:[1,11]), and (B_2:[23/2,25/2]), with waits
((0,1,0)). Hence

\[
  M(S,A^F;C)=\tfrac13,
  \qquad
  \Delta_{\mathrm{open}}=\tfrac{10}{3}-\tfrac13=3.
\]

In the closed SJF system, however, completing (B_1) at time 1 releases (B_2) at
(3/2). SJF has already started non-preemptive (A_1) at time 1, so (B_2) waits
until time 11:

| Policy/path | Job | Arrival | Start | Completion | Wait |
|---|---:|---:|---:|---:|---:|
| SJF closed | (B_1) | 0 | 0 | 1 | 0 |
|  | (A_1) | 0 | 1 | 11 | 1 |
|  | (B_2) | (3/2) | 11 | 12 | (19/2) |

Consequently

\[
  M(S,A^S;C)=\tfrac72,
  \qquad
  \Delta_{\mathrm{closed}}
  =\tfrac{10}{3}-\tfrac72=-\tfrac16.
\]

The open-loop contrast exceeds the closed-loop contrast by (19/6) and even reports an
improvement where the closed-loop comparison is a deterioration. The mechanism is
exactly the one cited in the paper: the faster response returns work earlier. Its
effect on latency has the opposite sign from the claimed lower-bound argument.

For direct alignment with the paper's primary waiting-time quantile, define the sample
p99 by standard linear interpolation: for sorted waits
$x_{(0)}\leq\cdots\leq x_{(n-1)}$, set $h=(n-1)0.99$ and interpolate between
$x_{(\lfloor h\rfloor)}$ and the next observation. The FCFS, fixed-arrival SJF,
and closed-SJF p99 values are respectively $49/5$, $49/50$, and $933/100$.
Because the identical cohort fits inside one deadline window, these are also the
corresponding p99$_{\mathrm{dl}}$ values for that window.
Therefore

\[
  \Delta^{p99}_{\mathrm{open}}=\tfrac{441}{50}=8.82,
  \qquad
  \Delta^{p99}_{\mathrm{closed}}=\tfrac{47}{100}=0.47.
\]

Thus fixed replay also overstates the p99 benefit, by $167/20=8.35$. A sign
reversal is unnecessary for the falsification: a claimed lower bound cannot exceed
the target quantity.

## Counterexample 2: fixed replay understates the benefit

Again use one non-preemptive model server and seconds as the time unit. Four jobs
arrive at time 0 in FCFS rank order $X_1,B_1,C_1,A_1$, with service times
$20,1,3,10$. User B has successor $B_2$ of service $1/10$ and fixed think
time $z_B=2$. The identical eventual set of five job identities is averaged under
every policy.

FCFS dispatches

\[
  X_1:[0,20],\quad B_1:[20,21],\quad C_1:[21,24],\quad
  A_1:[24,34],\quad B_2:[34,341/10].
\]

Because (B_2) arrives at (21+2=23), the waits in input order are
((0,20,21,24,11)), and (M(F,A^F;C)=76/5).

On the fixed FCFS arrival vector, SJF dispatches

\[
  B_1:[0,1],\quad C_1:[1,4],\quad A_1:[4,14],\quad
  X_1:[14,34],\quad B_2:[34,341/10].
\]

Its waits are ((0,1,4,14,11)) in dispatch order, so

\[
  M(S,A^F;C)=6,
  \qquad
  \Delta_{\mathrm{open}}=\tfrac{76}{5}-6=\tfrac{46}{5}=9.2.
\]

Under closed SJF, (B_1) completes at 1 and releases (B_2) at time 3. When (C_1)
completes at time 4, (B_2) is already waiting. SJF can therefore select (B_2)
before either long job:

\[
  B_1:[0,1],\quad C_1:[1,4],\quad B_2:[4,41/10],\quad
  A_1:[41/10,141/10],\quad X_1:[141/10,341/10].
\]

The waits are (0,1,1,41/10,141/10), giving

\[
  M(S,A^S;C)=\tfrac{101}{25},
  \qquad
  \Delta_{\mathrm{closed}}
  =\tfrac{76}{5}-\tfrac{101}{25}
  =\tfrac{279}{25}=11.16.
\]

Here the fixed replay understates the closed-loop benefit by (49/25=1.96). Earlier
feedback moves the short successor across a dispatch epoch; serving it first saves its
11-unit fixed-replay wait at the cost of only (1/10) additional wait to each long
job.

The corresponding linearly interpolated p99 values are $597/25$ for FCFS,
$347/25$ for fixed-arrival SJF, and $137/10$ for closed SJF. Hence

\[
  \Delta^{p99}_{\mathrm{open}}=10,
  \qquad
  \Delta^{p99}_{\mathrm{closed}}=\tfrac{509}{50}=10.18.
\]

The fixed replay understates the p99 benefit by $9/50=0.18$, establishing the
opposite bias direction for the paper's primary type of latency statistic on the same
five job identities.

## Arrival-window cohorts change the question again

The paper's deadline-window metric selects jobs by arrival time. With endogenous
arrivals, that makes cohort membership policy-dependent. In Counterexample 2, use the
arrival horizon (H=10) and retain the paper's convention that a job arriving by the
horizon remains observed even if it starts later. The FCFS/fixed-arrival cohort is
({X_1,B_1,C_1,A_1}), with four jobs, because (B_2) arrives at 23. The closed-SJF
cohort has five jobs because (B_2) arrives at 3. Exact per-policy cohort means give

\[
  \Delta_{\mathrm{open},H}
  =\tfrac{65}{4}-\tfrac{19}{4}=\tfrac{23}{2}=11.5,
\]

but

\[
  \Delta_{\mathrm{closed},H}
  =\tfrac{65}{4}-\tfrac{101}{25}
  =\tfrac{1221}{100}=12.21.
\]

That is a well-defined comparison of policy-specific arrival cohorts, but it mixes
scheduling, throughput, and population composition. The denominator changes from four
to five. The same problem is sharper for p99: the order statistic can change because
of both waiting times and the number and identity of jobs admitted to the cohort.

A feedback analysis must pre-specify one of three different targets:

1. A common finite set of user-attempt identities, as in the two main counterexamples.
2. Policy-specific jobs arriving by a common wall-clock horizon, with job counts and
   completed work reported as outcomes alongside latency.
3. A fixed initial cohort only, which preserves comparability but deliberately omits
   the induced successors.

None is numerically bounded by the fixed-arrival replay without additional structural
assumptions on user behavior, service requirements, censoring, and the queueing policy.

## Required prose correction

Exact original sentence:

> We cannot restore that feedback, our logs carrying no session boundaries, no think times and no resubmission semantics, but its direction is known: a closed loop returns work to a service that answers quickly, so the omission suppresses the benefit of the policies that shorten waits, and our reported gains are a lower bound.

Exact replacement sentence:

> We cannot restore that feedback because our logs carry no session boundaries, think times, or resubmission semantics; its direction is not identified, since completion-dependent arrivals can either increase or decrease a policy's measured latency advantage, so the fixed-arrival replay estimates performance conditional on the recorded arrivals rather than a lower or upper bound under endogenous demand, while the pathwise guard guarantee still holds on each realised arrival and service sequence against shadow FCFS replayed on that same sequence.

The next sentence about replay being established practice may remain, but it supports
the use of fixed-arrival replay as a conditional experiment, not the discarded
one-sided bound.

## Reproduction and checks

Run from the repository root in Git Bash, with the local cache environment from README.md:

```text
env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME NUMBA_NUM_THREADS=4 OMP_NUM_THREADS=4 uv run --no-project --with numpy python evidence/weakness1_attack/feedback_counterexamples.py
```

The script uses only the standard library, exact rational arithmetic, and fixed
parameters embedded in the file. It writes `out_feedback_counterexamples.txt`, prints
every dispatch recursion, records wall and CPU time, and asserts every arrival, start,
completion, wait, mean, effect direction, and cohort membership reported above. It
also asserts every linearly interpolated p99 value and p99 effect direction. It
does not read any dataset or import the project simulator. No guard is used, so a
guard-bound check is inapplicable.
