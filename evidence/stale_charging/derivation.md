# Late completion charges in Algorithm 1: bound, lower bounds, mitigations

Scope: Algorithm 1 (paper/sections/05_scheduling.tex:120-147), Theorem 3
(paper/sections/06_theory.tex:242-255), proof in paper/supplementary.tex:1785-1808.
Evidence: `sim_stale.py` in this directory, output `out_sim_stale.txt` (line numbers
below refer to that file). Command, from the repository root:

    env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME NUMBA_NUM_THREADS=4 \
      OMP_NUM_THREADS=4 uv run --no-sync python -u evidence/stale_charging/sim_stale.py \
      > evidence/stale_charging/out_sim_stale.txt
    # exhaustive part alone, n <= 6 (out_sim_stale.txt stops inside the exhaustive part)
    ... python -u evidence/stale_charging/sim_stale.py 6 exhaustive \
      > evidence/stale_charging/out_sim_stale_exhaustive_n6.txt
    # head-first against guard-first union (Section 5.6)
    ... python -u evidence/stale_charging/check_union_rule.py \
      > evidence/stale_charging/out_check_union_rule.txt

Output files: `out_sim_stale.txt` holds the lower-bound and random sections of the
first run, which was stopped inside the exhaustive part (its n = 1..6 lines are there,
the summary table is not). `out_sim_stale_exhaustive.txt` is a resumed n = 1..7 run
killed by a machine restart during n = 7. `out_sim_stale_exhaustive_n6.txt` is the
complete n <= 6 run with the table. n = 7 was not finished in any run.

Verdict in one paragraph. The hand derivation is correct and, for a single shared
counter, sharp: `In_i < B_max + kL + k(L + delta)` and
`excess < B_max/k + (4 - 2/k)L + delta`. The extra `L + delta` cannot be charged
against the in-service term, because one server can hold a stale overtaker and an
in-service overtaker at the same time; a cascade instance attains the bound to within
2 time units at k = 2 (ratio 0.9987) and exceeds Theorem 3's bound by `L + delta - 2`.
Report-before-pull on a shared counter restores Theorem 3's constant exactly, for every
delta including lost reports. Per-server views with only remote charges late cost
`(1 - 1/k)(L + delta)` on the excess, sharp at k = 2. Guard OR clock, with the aged
head served first, keeps `excess < theta + (3 - 2/k)L` for every delta including
delta = infinity; the guard-first reading of the union does not (Section 5.6).

## 0. Model

0.1 k identical non-preemptive servers; `0 < C_j <= L`; jobs ranked by arrival (ties
by index); `In_i` = total service of later-ranked jobs dispatched before i (the
overtakers of i); `excess_i = W_P[i] - W_FCFS[i]`.

0.2 Late charges (model U). The charge of job c, completed at `f_c`, is added to the
shared counter `over[]` at `f_c + d_c`, with `0 <= d_c <= delta`, for every
`q < c` still waiting then (as in Algorithm 1, lines 128-131). At one instant the order
is: completions, charges due by then, arrivals, dispatches; a charge applied at t is
seen by every dispatch at t. So delta = 0 is Algorithm 1 exactly.

0.3 Work conservation is unchanged: whenever a server is free and the queue is not
empty, the server pulls at that instant (Algorithm 1, line 136).

0.4 Budgets: any rule with `0 <= budget(q, t) <= B_max`, as in Theorem 3.

0.5 Theorem 1 of the paper: `k * excess_i = In_i - Out_i + Delta_i`,
`|Delta_i| <= 2(k-1)L`, `Out_i >= 0`. Every simulated job is checked against it
(check IDENT).

## 1. Upper bound for a shared counter with late charges (model U)

Fix i with at least one overtaker. Let j be the overtaker of i dispatched last, t its
dispatch instant, s* its server.

1.1 At the dispatch of j, i is waiting and not in the fired set E(t): j was chosen,
so either E(t) is empty or j is its minimum-rank member, and i has smaller rank than
j. Hence `over[i](t) < budget(i, t) <= B_max`. This is the paper's first step
(supplementary.tex:1786-1793) and reads only the counter, so it is unchanged by late
charges.

1.2 Every charge added to `over[i]` comes from an overtaker of i. A charge for c > i
is added while i waits; c arrived at `a_c >= a_i`, completed at `f_c > a_c`, and
`f_c <= t < s_i`, so c was dispatched before i. Therefore `over[i](t)` is the total
service of the overtakers whose charge has been applied by t ("charged").

1.3 Split the overtakers dispatched before j into
 (a) in service at t: `f_c > t`;
 (b) completed and charged: `f_c + d_c <= t`;
 (c) completed and stale: `f_c <= t < f_c + d_c`, hence `f_c` in `(t - delta, t]`.
Then `In_i = (b) + (a) + (c) + C_j` (check SUM, which recomputes this split from the
schedule).

1.4 (a): overtakers in service at t sit on distinct servers, none of them s*, which is
free at t. So (a) holds at most k - 1 jobs, each at most L (check INSERV).

1.5 (c), per server s: the stale jobs of s finish in `(t - delta, t]` and do not
overlap. Let c1 be the one that finishes first. `C_c1 <= L`. Every other stale job of
s starts at or after `f_c1 > t - delta` and finishes by t, so together they are at
most `t - f_c1 < delta`. Hence `stale_s < L + delta`; with integer times and delays,
`stale_s <= L + delta - 1` (check STALE, which uses this integer cap, and also checks
`f_c > t - delta` for every stale job).

1.6 Summing, `In_i < B_max + (k-1)L + k(L + delta) + L = B_max + kL + k(L + delta)`.
With integer data, `In_i <= (B_max - 1) + kL + k(L + delta - 1)` when `B_max` is an
integer (check IN, strict form).

1.7 Theorem 1 with `Out_i >= 0`: `k * excess_i <= In_i + 2(k-1)L`, so
`k * excess_i < B_max + (3k-2)L + k(L + delta)`, i.e.
`excess_i < B_max/k + (4 - 2/k)L + delta`. A job without an overtaker has
`excess <= (2 - 2/k)L`. This is the hand derivation, confirmed (check EXCESS).

1.8 At delta = 0 the interval `(t, t]` is empty, (c) is empty, and 1.6-1.7 are
Theorem 3. For delta > 0 the job that completed at the instant t itself is already
stale. At k = 1 that job always exists (the single server pulls j at the instant its
previous job ends), so any delta > 0, however small, raises the supremum from
`B + L` to `B + 2L + delta`: the jump is one job size, up to L.

1.9 Is the extra term smaller than `L + delta`? Per server the uncharged overtaker work
(stale plus in service, plus j on s*) lies in `[s_c1, t + L)` with
`s_c1 = f_c1 - C_c1 > t - delta - L`, so it is below `2L + delta`: `L` of Theorem 3
plus `L + delta`. Step 2 shows instances that reach this, so in model U the extra
`L + delta` per server is sharp and (c) cannot be charged against (a): in the k = 2
witness (out_sim_stale.txt, "cascade-stale U" lines) server 0 holds a stale job of
size L and an in-service overtaker of size L at the same instant.

## 2. Lower-bound instances (model U)

2.1 k = 1 (`lb_k1` in sim_stale.py). All jobs arrive at 0. Rank 0 is the victim, size
L, worst key. Then `B - 1` unit jobs with immediate charges, one job of size L with
delay delta, `delta - 1` unit jobs with delay delta, and a last overtaker of size L,
keys in that order. The units run on `[0, B-1)`, charged, so `over = B - 1`. The L job
ends at `B - 1 + L`, the stale units end at `B + L + delta - 2 = t`; each charge is due
`delta` after its completion, after t. At t, `over = B - 1 < B`, so the last
overtaker starts and the victim starts at `t + L`. FCFS starts the victim at 0, so
`excess = B + 2L + delta - 2`, which equals the integer upper bound of 1.6 at k = 1.
Measured: every listed case gives the expected value, ratio to the continuous bound
`B + 2L + delta` from 0.7500 (L = 3, B = 1, delta = 1) to 0.9987 (L = 300, B = 300,
delta = 600). Under Theorem 3 the same B allows at most `B + L - 1`; the late charges
add `L + delta - 1`.

2.2 k >= 2 (`lb_cascade_stale`). The paper's cascade (Lemma S8.1, m rounds,
`L = k^m`), then at `T = mL` the victim with the paper's sync and pre jobs (charged),
then on every server one stale job of size L and `delta - 1` stale units, then k
finals; `B = f + L + 1` with the paper's f. Measured excess is exactly
`f + 3L + delta - 1` in every case. At k = 2, m = 8 (L = 256) the ratio to
`B/k + (4 - 2/k)L + delta` is 0.9980 (delta = 1), 0.9983 (128), 0.9984 (256),
0.9987 (512). Theorem 3's bound at the same B is 768; the victim waits 1023 to 1534
beyond FCFS, that is `L + delta - 2` more than Theorem 3 allows. k = 3 (m = 5) gives
0.9765 and 0.9812; k = 4 (m = 4) gives 0.9383 and 0.9508, the same gap to 1 the
paper's own cascade shows at those m (0.9538 at k = 3, m = 4; 0.8895 at k = 4, m = 3,
reproduced with delta = 0).

## 3. Mitigation A1: report-before-pull on a shared counter

3.1 Rule: when a server frees and pulls, its own completion report is applied to the
shared counter before the pull's selection is made (one step, e.g. the report rides
on the pull request). All other charges may still travel late, with any delta,
including never.

3.2 Claim: `In_i < B_max + kL` and `excess_i < B_max/k + (3 - 2/k)L`, Theorem 3's
constants, for every delay.

3.3 Proof. Take t, j, s* as in 1.1-1.3; 1.1, 1.2 and 1.4 hold unchanged. Let c be a
stale overtaker, on server s. Every earlier pull of s applied s's then-last
completion, so c is s's last completion and s has not pulled since `f_c`. The victim
waits throughout `[a_i, t]` and `a_i < f_c <= t`. If `f_c < t`: at the dispatch phase
of instant `f_c`, s is free and the queue holds i; the phase runs while a server is
free and the queue is non-empty (0.3), and i is still waiting after it, so every
server is busy after it and s pulled at `f_c`, which applied c. Contradiction. So
`f_c = t` and s has not yet pulled in the phase at t: s is free when j is dispatched,
so s is not s* (s* applied its own last completion before pulling j) and s holds no
in-service overtaker. Hence, per server `s != s*`, (a) + (c) is one job of size at
most L, and on s* both are zero. `In_i < B_max + (k-1)L + L = B_max + kL`; Theorem 1
gives the excess bound.

3.4 Consequence: with report-before-pull the late channel is never needed while any
job waits, so the promise holds with reports on it late or lost. Measured: A1 has 0
violations of Theorem 3's bound in the random and exhaustive runs; on the model-U
witnesses of 2.1 and 2.2 it gives exactly Theorem 3's values (`B - 1 + L` at k = 1;
`f + 2L` at k = 2, 3).

## 4. Mitigation A2: per-server views, only other servers' charges late

4.1 Rule: each server keeps its own copy of `over[]` and selects from it; its own
completions enter its copy at once (report-before-pull locally), completions of other
servers enter it at `f_c + d_c`, `d_c <= delta`.

4.2 Claim: `In_i < B_max + kL + (k-1)(L + delta)`, hence
`excess_i < B_max/k + (3 - 2/k)L + (1 - 1/k)(L + delta)`.

4.3 Proof. 1.1 holds in s*'s view: `over_{s*}[i](t) < B_max`. 1.2 holds per view. In
s*'s view the stale jobs are on servers `s != s*` only; 1.4 and 1.5 bound them per
server by L (in service) and `L + delta` (stale). Sum and apply Theorem 1.

4.4 Refinement (check A2REF). If `s != s*` holds an in-service overtaker pulled at
`t_s <= t`, its stale jobs finished before `t_s`, are in s's own view at `t_s`, and s
pulled an overtaker of i then, so they total less than `over_s[i](t_s) < B_max`. Per
such server the extra is below `min(L + delta, B_max)`; a server without one has
stale work below `L + delta` and nothing in service. So the extra per remote server is
at most `max(delta, min(L + delta, B_max))`: never smaller than delta.

4.5 Answer to "does it return to Theorem 3 when all charges are current at each
dispatch": yes, trivially, at delta = 0 every model is Algorithm 1. With per-server
views and delta > 0 it does not: the cascade witness with `B = f + 2L + delta`
(`lb_cascade_stale(..., "A2")`) gives excess `f + 3L + delta - 1`, ratio 0.9985 to
0.9990 at k = 2, m = 8, i.e. `(1 - 1/k)(L + delta)` above Theorem 3 up to rounding. At
k = 1 there is no remote server and A2 is Theorem 3 (measured on 2.1's instance:
`B - 1 + L`).

## 5. Mitigation P-union: guard OR clock

5.1 Rule (head first when aged). Let `E(t) = {q : over[q] >= budget(q,t)}` (the guard's
fired set) and `A(t) = {q waiting : t - a_q >= theta}` (the aged set). Serve the
minimum-rank member of `E(t) ∪ A(t)` if the union is non-empty, else the base policy's
choice. Ranks follow arrival, so A(t) is a prefix of the waiting set: it is empty or
contains the head (the minimum-rank waiting job). The rule therefore reads "serve the
head if it has waited theta, otherwise run Algorithm 1". The counter may be late by
delta, or never updated (delta = infinity, all reports lost).

5.2 Guard half. Let j be served while a job i of smaller rank waits. Either the union is
empty and the base chose j, or j is the minimum-rank member of the union; in both cases
i is in neither set, in particular not in E(t). That is 1.1, and for finite delta all
of Section 1 follows: the model-U bounds survive adding the clock.

5.3 Clock half. For every dispatch at an instant `t' >= a_i + theta` before `s_i`,
i is in A(t'), so the minimum-rank member of the union, which is served, has rank at
most i's; no overtaker of i is dispatched
at or after `a_i + theta`. Every overtaker starts in `[a_i, a_i + theta)` (it arrives
no earlier than `a_i`). On one server the overtakers do not overlap, start at or after
`a_i`, and the last one starts before `a_i + theta` and ends before
`a_i + theta + L`; so they total less than `theta + L`, and
`In_i < k(theta + L)` (check CLKIN). This step reads no counter and no report.

5.4 Theorem 1: `k * excess_i < k(theta + L) + 2(k-1)L`, so
`excess_i < theta + (3 - 2/k)L` for every delta, including delta = infinity (check
CLOCK). With a finite delta both bounds hold:
`excess_i < min(theta + (3-2/k)L, B_max/k + (4-2/k)L + delta)`.
With `k W_i <= V_i^- + (k-1)L + In_i` (P-abs; check FLUID, every model):
`W_i < V_i^-/k + theta + (2 - 1/k)L`.

5.5 Lower bounds. Flat instance (`lb_clock_flat`), all reports lost: at 0 the victim
(rank 0) and, per server, `theta - 1` units then one job of size L, all preferred by
the base policy. Excess is `theta + L - 1` at every k, which attains the integer
maximum of `In_i <= k(theta + L - 1)`. At k = 1 the ratio to `theta + L` is 0.8333
(theta = L = 3), 0.9833 (theta = L = 30), 0.9997 (theta = 3000, L = 30). For k >= 2
this instance has `Delta = 0`, so it leaves `(2 - 2/k)L + 1` of the bound unused
(ratio 0.9899 at k = 2 and 0.9850 at k = 4 only because theta = 100L). On the paper's
S8.3 cascade, with theta one above the victim's age at its last overtaker, the clock
leaves the victim's overtakers unchanged and the ratio is 0.7461 to 0.7490 (k = 2) and
0.6820 (k = 3). Whether `(3 - 2/k)L` is the exact additive supremum for the clock at
k >= 2 is not settled here.

5.6 The dispatch order inside the union matters. Guard-first (serve the minimum-rank
member of E(t) if E is non-empty, else the head if aged, else the base) fails the clock
half as soon as budgets differ between jobs (gamma > 0 or eta > 0): E can hold a job
younger than an aged head that is not in E, and 5.3 then breaks. This was found by the
independent refuter (evidence/new_theory_refutation/refutation.md, section P-union)
and reproduced here with `check_union_rule.py` (model UG in sim_stale.py). Its witness 1
(k = 1, L = 3, budget `min(3 n_q, 5)`; theta = 4 instead of 3.5 because time is integer
here) gives excess 7 against the clock bound 7 under guard-first and 4 under the rule of
5.1. Its witness 2 (k = 1, theta = 0, budget `min(k age/4, 6)`, base SJF) gives 3 against
3 under guard-first and 0 under 5.1. For constant budgets over[q] is non-increasing in
rank (every charge that reaches a waiting q2 also reaches every waiting q1 < q2, late or
not), E(t) is a prefix too, and the two readings coincide.

## 6. Simulation (sim_stale.py)

6.1 Independent of the package: integer event loop, FCFS by the Kiefer-Wolfowitz
recursion, base policy "smallest key first" with adversarial keys, both server orders
(lowest or highest free index), models U, A1, A2, UN, and UG (guard-first union, used
only in 6.5).

6.2 Checks per job, each a numbered claim above: EXCESS (1.7 / 3.2 / 4.2), IN (1.6),
IDENT (0.5), GUARD (1.1), SUM (1.3), STALE (1.5, 3.3), INSERV (1.4), A2REF (4.4),
CLOCK (5.4), CLKIN (5.3), FLUID (5.4).

6.3 Exhaustive: k in {1, 2}, n <= 6 (the task asks n <= 7; see the note on output
files at the top), sizes in {1,2,3}, L = 3, arrivals in 0..4
(first at 0), B in {1,2,3}, delta in {0,1,2} (plus infinity for UN), theta in
{0,1,2,4,6} for UN. All key orders for n <= 5; for n = 6, 7 the 4n + 4
victim-last key families (every size vector and arrival vector still enumerated).
All delay vectors in `{0..delta}^n` for n <= 4; for n >= 5 two patterns (all delays
equal delta; a hashed per-job delay).

6.4 Random: 200,000 runs, seed 20260923, k in 1..4, n in 2..40, L in {3,4,6,10},
delta in 0..2L, constant or shaped budgets (B0 + gamma n_q + eta k age, capped),
theta in 0..3L for UN with delta = infinity in a quarter of UN runs.

6.5 Union rule (`check_union_rule.py`): the refuter's two witnesses under both readings,
then 200,000 random instances (seed 20260924), each run under UN (head-first, 5.1) and
UG (guard-first, 5.6); budget shapes constant, gamma, eta and mixed; delta 0, 1..2L or
infinity, one third each; theta in 0..3L.

6.6 Results: see Section 7.

## 7. Results

7.1 Statements, with where each is proved and checked. "Violations 0" means every job of
every run passed every check of 6.2 that applies to the model.

| # | Statement | Proof | Status |
|---|---|---|---|
| S1 | Shared counter, charges up to delta late (U): `In_i < B_max + kL + k(L + delta)`, `excess_i < B_max/k + (4 - 2/k)L + delta` | 1.1-1.7 | proved; 0 violations; sharp at k = 1 and k = 2 (7.3) |
| S2 | The extra `L + delta` per server cannot be charged against the in-service term | 1.9, 2.2 | shown by instance: one server holds a stale job of size L and an in-service overtaker at once |
| S3 | At k = 1 any delta > 0 adds up to L + delta to Theorem 3's excess | 1.8, 2.1 | proved; attained to the integer maximum |
| S4 | Report-before-pull on a shared counter (A1): Theorem 3's constants for every delta, lost reports included | 3.3 | proved; 0 violations; U's witnesses fall back to Theorem 3's values |
| S5 | Per-server views, only remote charges late (A2): `excess_i < B_max/k + (3 - 2/k)L + (1 - 1/k)(L + delta)` | 4.3 | proved; 0 violations; sharp at k = 2 |
| S6 | Guard OR clock, aged head first (UN): `In_i < k(theta + L)`, `excess_i < theta + (3 - 2/k)L`, `W_i < V_i^-/k + theta + (2 - 1/k)L` for every delta including infinity; S1 as well for finite delta | 5.2-5.4 | proved; 0 violations for all four budget shapes |
| S7 | Guard-first union (UG) keeps the clock bound | 5.6 | false for gamma > 0 or eta > 0 (refuter's witnesses reproduced) |

7.2 Lower-bound instances (`out_sim_stale.txt`, lines 10-85): every construction gives
its predicted excess exactly (no MISMATCH line), 0 violations (line 85).

7.3 Worst ratio to the bound, from the constructions:
- S1, k = 1 (`lb_k1`): excess `B + 2L + delta - 2`, the integer maximum of 1.6; ratio
  0.9987 at L = 300, B = 300, delta = 600 (line 23). Under Theorem 3 the same B allows
  `B + L - 1`.
- S1, k = 2 (`lb_cascade_stale`, m = 8, L = 256): excess 1023, 1150, 1278, 1534 for
  delta = 1, 128, 256, 512; ratio 0.9980 to 0.9987 (lines 37-40). Theorem 3's bound at
  that B is 768 (line 49). k = 3 (m = 5): 0.9765, 0.9812; k = 4 (m = 4): 0.9383, 0.9508
  (lines 43-46), the same shortfall as the paper's cascade at those m (0.9538 at k = 3,
  m = 4; 0.8895 at k = 4, m = 3; lines 13-14).
- S4: the same k = 1 instances under A1 (and A2, which has no remote server at k = 1)
  give 59 and 599 (lines 25-28); the k = 2, 3 instances under A1 give 191, 767, 697
  (lines 48-50). All are Theorem 3's values.
- S5, k = 2, m = 8: ratio 0.9985 to 0.9990 (lines 60-63); k = 3: 0.9768, 0.9815; k = 4:
  0.9385, 0.9510 (lines 64-67).
- S6 flat instance, all reports lost: excess `theta + L - 1` at every k; ratio 0.9997 at
  k = 1 (theta = 3000, L = 30), 0.9899 at k = 2 and 0.9850 at k = 4 (lines 70-76). On the
  paper's cascade with the clock just late enough: 0.7461, 0.7490 (k = 2), 0.6820 (k = 3).
  The additive constant `(3 - 2/k)L` of S6 is attained at k = 1; at k >= 2 the flat
  instance leaves `(2 - 2/k)L + 1` of it unused, and whether it is sharp there is open.

7.4 Random, 200,000 runs, seed 20260923 (`out_sim_stale.txt`, lines 87-108): 0
violations. Worst ratio per model and k = 1, 2, 3, 4: U 0.9828, 0.8571, 0.7941, 0.7529;
A1 0.9855, 0.8791, 0.8108, 0.7947; A2 0.9853, 0.8696, 0.7606, 0.7179; UN (clock bound)
0.9744, 0.7551, 0.7031, 0.6818.

7.5 Exhaustive, n <= 6 (`out_sim_stale_exhaustive_n6.txt`): 2,273,660,361 runs, 0
violations (line 36). Worst ratio per k, model and delta (lines 14-35): k = 1: U 0.8333,
0.8000, 0.8182 (delta 0, 1, 2); A1 and A2 0.8333; UN 0.8000, 0.8889, 0.8889, 0.8889
(delta 0, 1, 2, infinity). k = 2: U 0.6667, 0.5714, 0.5217; A1 0.6667; A2 0.5263, 0.5000;
UN 0.5000, 0.6000, 0.6000, 0.6000. With L = 3 and B <= 3 these instances are too small to
approach the constants, which need L and B large (7.3); they test the inequalities, not
their sharpness. n = 7 was not completed (see the note on output files).

7.6 Union rule (`out_check_union_rule.txt`). Witnesses (lines 4-8): head-first gives
excess 4 and 0, guard-first 7 and 3 against clock bounds 7 and 3, each a violation of
CLOCK and CLKIN. Random pairs (lines 13-47): UN 0 violations in 200,000 runs across the
constant, gamma, eta and mixed shapes and delta in {0, 1..2L, infinity}; UG 2,265
violations, all in the eta shape (k = 1: CLOCK 988, CLKIN 1001, worst ratio 4.3333;
k = 2: CLOCK 1, CLKIN 191; k = 3, 4: CLKIN 52, 32). The random draw hit no gamma-shape
violation; witness 1 is one. For the constant shape UN and UG have identical worst
ratios in every k, as 5.6 predicts.

7.7 Scope of the evidence. The base policy in the searches is a static priority order
(adversarial keys); dynamic base policies enter the proofs, which do not read the base
policy, but not the searches. Time and delays are integers, so strict bounds are checked
in their integer form (1.5, 1.6).

## 8. Notes for the paper

8.1 What a deployment must guarantee for Theorem 3 to hold as stated is the event order
of 0.2: a completion's charge is applied before any dispatch at the same instant.
Report-before-pull (Section 3) is a protocol that guarantees it with a shared
counter.

8.2 The draft proof of L1 (draft_clock_and_envelope_proofs.tex:20-22) says "some job
waits, since at most k-1 jobs in service hold at most (k-1)L". `U > (k-1)L` can hold
with k jobs in service and none waiting; the conclusion (all k servers busy) still
follows, because an idle server under work conservation means an empty queue and at
most k - 1 jobs in service. Suggested wording: "then all k servers are busy, since
otherwise the queue is empty and at most k - 1 jobs in service hold at most (k-1)L".
The FLUID check (the consequence `kW <= V^- + (k-1)L + In`) had 0 violations in every
run here; Wolff (1987) concerns other published bounds and was not re-derived here.
