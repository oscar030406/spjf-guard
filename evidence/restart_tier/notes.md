# Kill-and-restart tiering: does a short first-attempt cap move the `Omega(L)` barrier?

Self-contained study. Everything below was produced by the scripts in this directory;
no other project file was modified. The verdict is in `out_SUMMARY.txt`.

**Short answer: no, and the idea costs more than it buys.** Tiering does not move the
additive constant of the per-job guarantee from `L` to `tau` (§4), it destroys the
FCFS-relative guarantee outright (§3), and on the development trace every tiered design
is dominated by the plain guard at the same worst case (§6). The one design family that
wins anything (§7) wins only at half load, only by giving up work conservation, and
therefore has no guarantee at all.

---

## 1. Model

The base model is the one of `../guard_theory/theory.md` §1 and is used verbatim:
`k` identical unit-speed servers, non-preemptive, work conserving, jobs numbered in
**rank** order `(arrival, input index)`, `W_P[i]` the waiting time of job `i` under `P`,
`FCFS` the same-input policy that always dispatches the minimum-rank waiting job,
`L = 60 s` the per-job service cap, `excess_P[i] = W_P[i] - W_FCFS[i]`.

**Tiering.** Fix a tier-1 cap `tau < L` and a kill predicate `kill(j)` that depends only
on job `j`'s own attributes (its capped service `C_j` and its prediction `pred_j`), never
on the schedule. A job with `kill(j)` false runs once, for `C_j`, and completes.
A job with `kill(j)` true is first run for `tau`, **killed** (those `tau` seconds are
wasted; the job is not advanced at all — the jobs are idempotent, so a kill is legal, but
it is preemptive-**repeat**, not preemptive-resume), and returns to the waiting set at
that instant as a *tier-2* job keeping its original rank; its tier-2 run takes `C_j` and
completes it. A prediction-driven **skip** (`pred_j >= tau` sends `j` straight to tier 2)
is a legal kill predicate. The whole schedule is therefore a sequence of **pieces**, each
of length at most `L`, and the per-job quantities are defined on the job:

    W[i] = (start of the run that COMPLETES i) - a_i      so  flow(i) = W[i] + C_i

in both the tiered and the plain system, which makes the two directly comparable.

**Guard.** The guard of §4.3 of the research plan, with the constant budget `B` and
applied at piece level: `over[q]` is the total **executed** work (a killed tier-1 piece
contributes its `tau`) of jobs of rank `> q` completed while `q` waits; the fired set is
`{waiting q : over[q] >= B}`; when it is non-empty the minimum-rank member is dispatched.
With a constant budget `over[.]` is non-increasing in rank, so that member is the FCFS
head and one Fenwick query per decision suffices — `tierkern.py` has no segment tree.

**Reference schedules.** Three, and the difference matters:

| name | meaning |
|---|---|
| `FCFS` | plain first-come-first-served, **no tiering**. The reference of every guarantee in the paper, and the system the operator runs today. |
| `TFCFS` | the same tiering (`tau`, same kill predicate), dispatched by rank. |
| `SJF-ref` | true shortest-job-first, not deployable; the denominator of "gap closed". Not an optimality ceiling (research plan §4.4, S2). |

---

## 2. Why the existing theorem does not simply carry over

The natural hope is a relabelling: replace each job by its pieces and apply Theorem A of
`theory.md` to the piece set. **That does not work.** Theorem A is proved for a fixed job
set with fixed release times, and a tier-2 piece's release time is its kill time, which
depends on the schedule — two policies on the same input produce different piece release
times. Proposition 11(b) of `theory.md` already shows that release times which differ
from the ranking key break Theorem 1 (the net-overtake identity), and here they differ
*between the two schedules being compared*, which is worse.

Two consequences, both settled below by construction and by search rather than by
assertion: the bound against plain FCFS is false (§3), and the bound against `TFCFS`
survives every attack I could mount but is *not proved* (§5).

---

## 3. Proposition K — kill-and-restart admits no additive FCFS-relative guarantee

**Statement.** Fix `k >= 1`, `0 < tau < L` and any `G`. Let `P` be *any* policy that runs
every job in tier 1 first (i.e. `kill(j)` is true for every `j` with `C_j > tau`). There
is an input on which some job `i` has `W_P[i] >= W_FCFS[i] + G`.

**Construction (family A).** `n` jobs, all of work `L`, all arriving at `t = 0`, nothing
else. Every tiered schedule must execute `n(L + tau)` of work. At the instant the last
job is dispatched, at most `k` runs are outstanding, so at least `n(L+tau) - kL` has been
executed on `k` servers and that instant is at time `>= (n(L+tau) - kL)/k`. Under FCFS the
largest waiting time is `(ceil(n/k) - 1)L <= (n/k)L`. Hence

    max_i excess_P[i]  >=  n*tau/k - L,

unbounded in `n`. ∎

**Measured** (`out_brute.txt`, family A, `L = 8`, `tau = 1`): the worst excess is exactly
`n*tau/k` at `k = 1, 2` for every `n` in `{2,4,8,16,32}`, and `11.0` vs a predicted
`>= 2.67` at `k = 3, n = 32`. The same table runs the *non-tiered* `SPJF+guard` on the
same instances: its worst excess is `0.000` throughout.

**What this kills.** The guard controls the *order* of execution; it cannot control the
*amount* of work executed. The excess here is not overtaking — `In_i = 0` for the victim —
it is the wasted `tau` of every heavy job ahead of it. No wrapper, no budget and no base
policy can remove it. Two apparent escapes and why neither works:

* *Use the predictions to skip the kill for predicted-heavy jobs.* Under an adversarial
  predictor every heavy job is predicted light, every heavy job is killed, and family A
  returns unchanged. The paper's guarantee is explicitly prediction-quality-free
  (research plan §5, §4.3); a guarantee conditional on prediction quality is a different
  and much weaker product.
* *Make the kill predicate adaptive* (kill only when the queue is long, say). Then the
  inflated-demand argument of §5 breaks too, and the kill predicate is no longer
  schedule-independent, so nothing at all is left. Family A's queue is long anyway.

**Random search.** `out_brute.txt`, 3,000,000 random instances (`n <= 7`, `k <= 3`,
`tau = 1`, `L = 8`, four budgets, three base orders): Theorem A's slack `B/k + (3-2/k)L`
is violated on **25,768** instances, worst violation `+5.00 = +0.63 L` beyond the slack.
The control — the same guard with tiering switched off — has **0** violations, worst
margin `-0.25`, so the harness is sound.

---

## 4. The `Omega(L)` barrier is not moved — this is the central negative result

The motivating hope was: inside tier 1 every service is `<= tau`, so a **light** job
(`C_i <= tau`, 98.7% of the trace at `tau = 1 s`) should get a per-job bound with an
additive term in units of `tau`. It does not, because a tier-2 piece is a full-length
non-preemptive block: a light job that arrives while `k` tier-2 blocks are running waits
for one of them to finish, and the guard cannot preempt a running job. The guard's own
budget is what puts those blocks at an adversarial instant: holding a heavy job back by
`over_i` up to `B` moves its tier-2 block to a moment at which plain FCFS is running a
short job.

**Measured** (`out_brute.txt`, family B). `tau` fixed at `1.0`, the largest service `L`
varied, the same random search each time; the table reports the two natural light-job
constants with the `B/k` (resp. `(B + waste)/k`) term removed:

| `L/tau` | max light excess over `TFCFS`, minus `B/k` | max light excess over `FCFS`, minus `(B+waste)/k` |
|---:|---:|---:|
| 2 | 2.50 | 1.00 |
| 4 | 4.50 | 3.00 |
| 8 | 10.00 | 8.00 |
| 16 | 18.00 | 15.50 |
| 32 | 35.00 | 33.00 |

Both grow linearly in `L` — about `1.1 L`, indistinguishable in slope from the untiered
case — and are flat in `tau`. If tiering had moved the barrier these columns would be
constant. **It does not.** With `L = 60 s`, a `tau = 1 s` tier-1 pass leaves the light
jobs' additive constant at roughly `60 s`, exactly where it was.

The same search reports the hypothesis counts over 3,000,000 instances:
`W_P[i] <= W_FCFS[i] + (B+waste)/k + 3 tau` for light `i` — **8,606 violations**, worst
`+5.5`; `W_P[i] <= W_TFCFS[i] + B/k + 3 tau` for light `i` — **11,793 violations**, worst
`+7.0`. The worst instance for each is printed job by job in `out_brute.txt`.

**The only way out, and why it is closed.** To keep a light job from waiting behind an
`L`-long block, some server must be kept free of tier-2 work: either a partition
(design (a) of the task) or a cap of `m < k` tier-2 jobs in service (design (b)). Both
make the policy **non work conserving** — a server idles while tier-2 jobs wait — and
Proposition 10 of `../guard_theory/theory.md` shows that work conservation is the one
assumption that cannot be dropped: with unbounded forced idling there is no guarantee at
all. This is not a formality; it is measured in §7, where `Proposition W` is violated on
up to 0.42% of the 17.6 M jobs by the capped designs. Design (c) ("dispatch tier 2 only
when no tier-1 job waits") *is* work conserving, and is the `t1rank`/`t1pred` family run
throughout below — but it leaves the barrier exactly where §4 found it, because nothing
stops all `k` servers from being on tier-2 blocks when no tier-1 job happens to be
waiting.

---

## 5. Proposition W — what does survive, and the price of it

**Statement (proof sketch; the gaps are flagged).** With the tiering of §1 (kill
predicate schedule-independent) and the constant-budget guard at piece level, for every
job `i`

    W_P[i]  <=  W_FCFS[i] + (B + Delta_i)/k + (3 - 2/k) L

where `Delta_i = tau * #{ j : kill(j), t0_i < a_j <= a_i }` and `t0_i` is the last time
before `a_i` at which the tiered system's unfinished demand was `<= (k-1)L`.

*Proof sketch.* Give the tiered system inflated demands `C_j + tau*1{kill(j)}`; because
`kill` does not depend on the schedule this is well defined at arrival, and the tiered
system is then an ordinary non-preemptive work-conserving `k`-server system on those
demands. Lemma 1 of `theory.md` is re-run on `D = U_P - U_F`: arrivals now add `tau` more
to `U_P` than to `U_F` at each killed job, and `D` is still non-increasing wherever
`U_P > (k-1)L`, so `D(t) <= (k-1)L + (inflation arriving in (t0,t])`. Steps (1)-(5) of
Theorem 4's proof then go through unchanged — in particular step (3), the overtaker
bound `E_new < B + kL`, is untouched because `over[.]` counts executed work including the
wasted `tau`, and every piece in service is at most `L`. ∎

*Gaps, stated plainly.* (i) I re-ran the argument, I did not re-derive the `(3-2/k)L`
constant for the tiered case, and I make no tightness claim for it. (ii) `t0_i` is
measured in the kernel by the sufficient condition "at most `k-1` jobs present", which
is stronger than `U_P <= (k-1)L`, so the reported `Delta` is conservative (larger than
needed) — good for an upper bound, useless for a lower one. (iii) The statement is
verified, not proved to the standard of `theory.md`: **0 violations** in 3,000,000 random
small instances and **0 violations** on every job of every work-conserving tiered run on
the real trace (12 runs x 17,634,760 jobs, asserted in `run_iso.py`).

**And this is the price.** `Delta_i` is not a constant the operator can be told in
advance: family A makes it grow without bound, and on the real trace it is large. At
`k = 4`, `tau = 1 s`, the measured `Delta_max` is **1,605 s**, so a design that claims the
paper's `G = 300 s` service level actually guarantees

    (B + Delta_max)/k + (3-2/k)L  =  (600 + 1605)/4 + 150  =  701 s,

i.e. **2.3x worse than the promise it was configured for**, and at `tau = 10 s` it is
`(600 + 5910)/4 + 150 = 1,777 s`. A guarantee whose constant has to be measured on the
trace after the fact is not the product the paper is selling.

**Theorem A against a tiered reference — a conjecture, not a result.** `W_P[i] <=
W_TFCFS[i] + B/k + (3-2/k)L` survived all 3,000,000 random instances with 0 violations
(worst margin `-0.25`). I did **not** prove it — §2 explains why the obvious relabelling
fails — and I would not put it in a paper without a proof. It is also the wrong
statement to sell: `TFCFS` is a system that already burns 3.4-12.1% of its capacity on
work it throws away, and the operator who runs plain FCFS today has agreed to no such
thing. Any guarantee relative to `TFCFS` must be labelled as relative to a *different and
worse* baseline.

---

## 6. The development trace

`rep0` overlay, 17,634,760 jobs, 7,048,761 s of work, deadline-window p99 wait as in
`../guard_variants/`; three load levels `k = 8 / 5 / 4` (busy-hour `rho` 0.53 / 0.85 /
1.06). Raw logs: `out_trace_L2.txt`, `out_iso_L{0,1,2}.txt`, `results_L2.csv`,
`iso_L*.csv`.

**Cost of the wasted work.**

| `tau` | jobs with `C > tau` | their share of the work | **wasted share of total work** |
|---:|---:|---:|---:|
| 1 s | 237,292 (1.35%) | 38.7% | **3.37%** |
| 2 s | 160,380 (0.91%) | 37.1% | **4.55%** |
| 5 s | 114,708 (0.65%) | 35.1% | **8.14%** |
| 10 s | 85,404 (0.48%) | 32.1% | **12.12%** |

At the busy-hour load (`k = 4`, `rho = 1.0589`) a 3.4% capacity loss moves `rho` to 1.095.
That shows up immediately: **tiering on its own, with FCFS order (`TFCFS`), is worse than
plain FCFS**, deadline-window p99 `356.3 s` vs `263.1 s` at `tau = 1` (gap `-0.42`),
`377.6 s` at `tau = 2`, `576.1 s` at `tau = 10` (gap `-1.42`), with worst-job excesses of
`367 / 387 / 1,234 s` over plain FCFS.

**Headline comparison at `k = 4`, `rho = 1.06`** (FCFS p99_dl `263.12 s`, true-SJF
`42.88 s`; `G = 300 s = 5L`, `B = k(G - (3-2/k)L) = 600`):

| policy | honest guarantee | measured max excess | p99_dl | gap closed | gap (mean) |
|---|---:|---:|---:|---:|---:|
| `SPJF` (no guard) | none | 5,882.9 | 66.57 | 0.892 | 0.924 |
| **`SPJF+guard` G=300** | **300** | 215.4 | 168.67 | 0.429 | 0.530 |
| `SPJF+guard` G=500 | 500 | 413.0 | 99.15 | 0.745 | 0.676 |
| `SPJF+guard` G=700 | 700 | 608.7 | 84.50 | 0.811 | 0.758 |
| `TFCFS` tau=1 (no guard needed: rank order) | 551 | 367.1 | 356.28 | -0.423 | -0.270 |
| `TIER-blind` tau=1 +guard | 701 | 481.5 | 220.64 | 0.193 | 0.431 |
| `TIER-pred` tau=1 +guard | 701 | 481.5 | 139.87 | 0.560 | 0.539 |
| `TIER-skip` tau=1 +guard | 573 | 378.6 | 123.69 | 0.633 | 0.587 |
| `TIER-pred` tau=2 +guard | 694 | 537.2 | 131.33 | 0.598 | 0.479 |
| `TIER-skip` tau=2 +guard | 664 | 506.7 | 128.46 | 0.611 | 0.493 |

Read at face value the tiered rows beat `SPJF+guard` (0.63 vs 0.43) — **and that reading
is wrong**, because they are not keeping the same promise. Placed on an honest axis:

**Iso-comparison** (`out_iso_L2.txt`): `dgap` = tiered design's gap minus what plain
`SPJF+guard` achieves at the *same* honest guarantee / at the *same* measured worst-case
excess, read off the `SPJF+guard` budget curve on the same trace.

| design | `k=8`, rho 0.53 | `k=5`, rho 0.85 | `k=4`, rho 1.06 |
|---|---:|---:|---:|
| `TIER-blind` tau=1 | -0.089 / -0.097 | +0.004 / -0.006 | **-0.575 / -0.618** |
| `TIER-pred` tau=1 | -0.140 / -0.155 | +0.014 / +0.004 | **-0.208 / -0.252** |
| `TIER-skip` tau=1 | -0.136 / -0.158 | +0.043 / +0.011 | **-0.086 / -0.136** |
| `TIER-pred` tau=2 | -0.007 / -0.016 | +0.044 / +0.030 | **-0.188 / -0.211** |
| `TIER-skip` tau=2 | -0.005 / -0.014 | +0.050 / +0.033 | **-0.165 / -0.187** |

(each cell: iso-measured-excess / iso-guarantee.) Tiering is a **loss at both ends of the
load range and at best a rounding-error gain in the middle**. At the load that motivates
the whole paper it is a loss of 0.09 to 0.62 of the gap. `tau = 5` and `tau = 10` are
worse still (`k = 8`, `tau = 5`: `-0.026 / -0.034`; `k = 4`, `tau = 10`: gap goes
negative). Predictions help the tiered design a lot (`blind` -> `pred` is +0.37 of the gap
at `k = 4`), and the `skip` rule recovers part of the waste (3.37% -> 2.34% at `tau = 1`),
but neither closes the deficit.

**What a wrong prediction costs, in each direction** (`tau = 1 s`, `k = 4`): a heavy job
predicted light is killed and costs `tau` of wasted capacity plus one requeue, and it is
this direction that both inflates `Delta_i` and is the direction the predictor is already
known to get wrong (research plan §4.2: the costly errors are exactly the underestimates).
A light job predicted heavy skips tier 1 and is dispatched at tier-2 priority, i.e. only
when no tier-1 job waits — it wastes nothing but can wait a long time; at `k = 4` the
`skip` design's worst light-job excess is `378.6 s` against `481.5 s` without the skip, so
on this trace the skip is a net improvement on both axes. Neither direction is protected
by anything except the guard, and the guard's budget is what §4 showed is also the lever
the adversary uses.

---

## 7. The reserved-server designs (task items (a) and (b))

`m2` = at most this many tier-2 pieces in service at once (`m2 = k` is design (c), no
reservation; `m2 < k` reserves `k - m2` servers for tier-1 work). A partition (design (a))
is the same thing with the tier-1 jobs also confined, i.e. strictly worse, and was not
run separately. These designs are **not work conserving**, so nothing is guaranteed:

* At `k = 4`, `rho = 1.06`, `tau = 1`: `m2 = 1` gives p99_dl `951.7 s` (gap `-3.13`), worst
  excess `22,544 s`, and violates Proposition W on **61,934 jobs (0.35%)**. `m2 = 2`
  violates it on 4,696 jobs. `m2 = 3` closes gap 0.602 against `SPJF+guard`'s 0.811 at the
  same guarantee. **Every reservation loses at the busy-hour load.**
* This is exactly the objection that was already recorded against the two-queue design
  ("重任务走专用执行机"的双队列, research plan §1.4): predicted-heavy jobs carry ~88% of the
  work (`../codebench_service/out_service.txt`), so reserving servers for them is
  unaffordable. Kill-restart does not change that arithmetic — at `tau = 2` the jobs that
  reach tier 2 still carry **37.1%** of the work, so at `k = 4`, `rho = 1.06` tier 2 needs
  `0.371 * 1.06 * 4 = 1.57` servers of long-run capacity and any cap below 2 is unstable.
* **The one place it wins, and it wins clearly.** Reserving a quarter of the fleet from
  tier-2 work, at `tau = 2 s`:

  | level | design | p99_dl | gap | gap (mean) | measured max excess | `SPJF+guard` at that excess |
  |---|---|---:|---:|---:|---:|---:|
  | `k=8`, rho 0.53 | `m2 = 6` | 5.01 s | **1.238** | 0.985 | 276.6 s | 0.715 (mean 0.82) |
  | `k=5`, rho 0.85 | `m2 = 4` | 34.92 s | **0.990** | 0.809 | 371.8 s | 0.797 (mean 0.79) |
  | `k=4`, rho 1.06 | `m2 = 3` | 124.57 s | 0.629 | 0.607 | 582.9 s | **0.802** (mean 0.76) |

  A gap above 1 means it beats true-SJF on deadline-window p99, which is possible because
  that denominator is not a ceiling (research plan §4.4) — such configurations are to be
  flagged, not celebrated. This is the least-attained-service effect: capping the first
  attempt at 2 s stops short jobs queueing behind long ones. It is real at
  `rho <= 0.85` (+0.19 to +0.52 of the gap on p99, and at `k = 8` on the mean too), and it
  **fails at the busy-hour load** (-0.17), which is the load the paper exists for. It has
  **no guarantee of any kind** — it is not work conserving, and neighbouring caps in the
  same family (`m2 = 1..3` at `k = 8`, `m2 <= 3` at `k = 5`, `m2 <= 2` at `k = 4`) violate
  Proposition W on up to 0.42% of the 17.6 M jobs and reach worst-case excesses above
  20,000 s. It also idles a quarter of the fleet. A curiosity worth one line in the
  discussion, not a method.

---

## 8. Prior art

Prior art searched and read for this study (depth of reading noted per item).
Nothing below was taken on trust from a snippet where the claim is load-bearing.

**The mechanism is TAGS, and it is 24 years old.** Harchol-Balter, *Task Assignment with
Unknown Duration*, JACM 49(2):260-288, 2002,
[10.1145/506147.506154](https://doi.org/10.1145/506147.506154), full text at
<https://www.cs.cmu.edu/~harchol/Papers/tags.pdf> (read in full). §4: all arrivals go to
host 1; a job that has used `s_1` of CPU "is killed ... put at the end of the queue at
Host 2, where it must be restarted from scratch". Exactly this idea, with **one dedicated
host per cutoff level**. Model: Poisson arrivals, bounded-Pareto sizes; objective mean
slowdown / mean waiting time / equal *expected* slowdown; analysis steady-state M/G/1 per
host with cutoffs solved numerically. **No worst-case analysis, no per-job bound, no
FCFS-relative statement anywhere.** The paper explicitly distinguishes itself from
multi-level feedback queueing, which transfers a job "(not killed and restarted)".

**And the TAGS line has a stability theorem that this study should heed.** Bachmat,
Doncel, Sarfati, *Analysis of the TAGS policy*, Performance Evaluation 2020,
[10.1016/j.peva.2020.102098](https://doi.org/10.1016/j.peva.2020.102098) (read in full,
Thms 4.1-4.2): the maximum load a TAGS system can carry is `<= ln(r) + 1` in the job-size
range `r`, **independently of the number of hosts**. Their own recommendation is "small
systems with relatively low utilization". The newest descendant, Li, Harchol-Balter,
Scheller-Wolf, *SPLIT*, arXiv [2605.13749](https://arxiv.org/abs/2605.13749) (2026), has
abandoned the kill and moved over-threshold jobs "in a preempt-resume manner (no work is
lost)". The field walked away from this mechanism.

**The competitive-analysis line owns the worst case and has already generalised the
design.** Jäger, Sagnol, Schmidt genannt Waldschmidt, Warode, *Competitive Kill-and-Restart
and Preemptive Strategies for Non-Clairvoyant Scheduling*, IPCO 2023 / Math. Programming
210:457-509 (2025), [10.1007/s10107-024-02118-8](https://doi.org/10.1007/s10107-024-02118-8),
arXiv [2211.02044](https://arxiv.org/abs/2211.02044) (intro, contributions, related work
read). Their `D_b` probes each job at a *geometric ladder* of cutoffs — a two-tier
`(tau, L)` is its two-level special case — and they prove tight ratios
(`1+3*sqrt(3) ~ 6.196` deterministic, `< 3.032` randomized for `1||sum w_j C_j`;
`5+2*sqrt(6) ~ 9.899` for `P||sum C_j`; `~9.915` for `1|r_j|sum w_j C_j`). Earlier
restart results: Shmoys-Wein-Williamson SIAM J. Comput. 24(6):1313-1331 (1995), introduced
the model (**secondhand, via Jäger's related work — not read**); van den Akker-Hoogeveen-
Vakhania J. Scheduling 3(6):333-341 (2000), 1.5 with restarts vs 1.618 without
(abstract only); van Stee-La Poutré ESA 2002 / J. Algorithms 57(2):95-129, 3/2 for
`sum C_j` (abstract only). **Every one of these is a ratio against OPT on an aggregate
objective; none gives a per-job bound and none compares to FCFS.**

**The prediction-driven skip is published.** Shahout & Mitzenmacher, *SkipPredict*,
NeurIPS 2024, arXiv [2402.03564](https://arxiv.org/abs/2402.03564) (intro read): a cheap
one-bit prediction routes predicted-long jobs past the cheap tier. Nothing is run and
killed there. `SPJF` itself is named and analysed in Mitzenmacher, *Scheduling with
Predictions and the Price of Misprediction*, ITCS 2020,
[10.4230/LIPIcs.ITCS.2020.14](https://doi.org/10.4230/LIPIcs.ITCS.2020.14).

**What is genuinely open — and it is not tiering.** The learning-augmented literature
defines consistency, robustness and smoothness exclusively as ratios against `OPT(I)`
(survey arXiv [2609.04787](https://arxiv.org/abs/2609.04787), §3.2); Nudge (Grosof, Yang,
Scully, Harchol-Balter, PACM MACS 5(2) art. 21, 2021,
[10.1145/3460088](https://doi.org/10.1145/3460088), read in full) has an overtake budget
of exactly 1 but states only a *stochastic* M/G/1 improvement and never the deterministic
per-job consequence; Mitzenmacher & Shahout, Stochastic Systems 2025,
[10.1287/stsy.2025.0106](https://doi.org/10.1287/stsy.2025.0106), list multi-server +
predictions as open. **The per-job FCFS-relative deterministic bound is the unoccupied
cell — which is the paper's existing contribution, not this idea.**

**Two references the paper should cite regardless of this study's verdict.**
(i) Parekh & Gallager, IEEE/ACM ToN 1(3):344-357, 1993,
<https://pbg.cs.illinois.edu/courses/cs598fa09/readings/pg93.pdf> (Theorem 1 read
verbatim): `F̂_p - F_p <= L_max/r` — a per-job, deterministic, any-input additive bound
relative to a baseline schedule, with the slack in units of the maximum service unit.
That is the paper's bound *shape*, 33 years old, in the fair-queueing setting; the
classical way to shrink `L_max` there is packet fragmentation, which **preserves** work.
Kill-and-restart is the same move performed by **destroying** work, and §3-§4 of this
note are the price. (ii) Anggraito, Razumchik, Marin, *Kill Smart, Run Fast*, ICPE '26,
[10.1145/3777884.3796995](https://doi.org/10.1145/3777884.3796995) (read): kill-and-restart
with a per-job kill budget of 1 plus a bounded-deferral rule, motivated by fairness —
the closest existing thing to a guard inside a kill-and-restart system, analysed by
simulation and fairness index, with no per-job worst-case bound.

**Nothing new is left in the combination.** Kill-and-restart tiering: TAGS 2002, with the
worst case done by Jäger et al. 2023. Predicted-heavy bypass: SkipPredict 2024. The only
novelty would be attaching the per-job FCFS-relative guarantee to it — and §3 shows the
guarantee does not survive contact with the mechanism.

---

## 9. What was checked, and what was not

| claim | status | evidence |
|---|---|---|
| simulator reproduces the project's verified kernel | **verified** | `out_verify.txt`: 400 random instances x 6 configurations and 3,000,000 real-trace jobs at `k = 4, 8`, max difference `0.000e+00`; 19,200 tiered cases against an independent pure-python simulator, 0 mismatches |
| Proposition K (no additive FCFS-relative guarantee) | **proved + measured** | §3; `out_brute.txt` family A, exact at `k = 1, 2` |
| Theorem A fails for the tiered system vs plain FCFS | **disproved by counterexample** | 25,768 / 3,000,000 instances, worst `+0.63 L` |
| light-job constant scales with `L`, not `tau` | **measured, not proved** | `out_brute.txt` family B, five values of `L/tau`, slope `~1.1 L` |
| Proposition W (waste-corrected bound) | **proof sketch + verified** | §5; 0 violations in 3,000,000 instances and in 12 x 17.6 M job-level assertions |
| Theorem A vs a *tiered* FCFS reference | **conjecture** | 0 violations in 3,000,000 instances; §2 says why the obvious proof fails |
| reserved-server designs void the guarantee | **measured** | §7; up to 0.42% of jobs violate Proposition W |
| tiering is dominated at equal worst case | **measured** | §6, three load levels, `iso_L*.csv` |
| `(3-2/k)L` is the right constant for the tiered case | **not checked** | inherited from `theory.md` Theorem 4; no tightness claim made here |
| behaviour on `rep1`, on other predictors, on Azure | **not run** | one replicate only, by instruction |

The "inherent price" question (an upper bound on what *any* non-preemptive policy with a
guarantee `G` can gain) is not pursued here: Theorem 16 of `../guard_theory/theory.md`
already owns it, and that file belongs to the theory note. What this study adds to it is an
empirical floor on the same trace: the `SPJF+guard` budget curve in `iso_L*.csv` is a
measured lower bound on the achievable gain at each `G`, and every tiered design sits
below it.
