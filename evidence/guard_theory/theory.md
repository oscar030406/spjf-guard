# A pathwise identity for FCFS-relative delay in non-preemptive multiserver scheduling

This note turns the per-job bound of `evidence/guard_variants/guardkern.py`
(Theorem A there) into a two-sided structural statement that holds for *every*
non-preemptive work-conserving policy, and then reads the guard off as a
corollary. Everything is on the sample path: no stationarity, no distributional
assumption, no assumption on the quality of predictions.

This is revision 5. Its changes answer the fourth referee report
(`docs/referee_readthrough/`), which read the *paper* and found five places
where §6 and Appendix A of the manuscript are wrong or unproved. Two of the five
(the Impossibility quantifier, the scope of the count remark) are degradations
introduced when this note was compressed into the paper and are already correct
here; the other three, and one further item the referee raised against the
paper's Remark 1, are gaps in this note as well. What moved:

* **Lemma 1s** now carries `k >= 2` in its statement, not only inside its proof.
  At `k = 1` the bound `(k-1)L = 0` is *attained* at every instant, so the
  strict form is false there (referee item RR-7).
* **Remark 1.3's** stated reason for keeping the dispatch-sequence convention
  was false: completed work lower-bounds the executed-work currency too. The
  two real reasons (an exactly determined constant, symmetric sides) are kept
  and the false one is replaced by the proof that both are metered (RR-8).
* **Proposition 8** claimed `Λpref(a_i)` for "Corollary 1.2 and the wrapper
  bound". It is enough for Corollary 1.2 and *not* for the wrapper: the `kL`
  term of Theorem 4 charges overtakers, which arrive after `a_i`. The correct
  placement is `Λpref(s^P_i)`, with an explicit counterexample (RR-1).
* **Proposition 14** is restated with the hypothesis its proof actually uses ---
  a budget positive at the first dispatch epoch --- together with the two facts
  that fix the boundary of the statement: rules that are zero at the first epoch
  but positive later fall to the same instance behind a saturating prefix, and
  the rules that escape are exactly those that reproduce FCFS (RR-2).
* **§7** promotes the `k = 1` achievable fraction from a numerical observation
  to **Proposition 17**, with a proof --- and the exact value is
  `min(1, floor(G/s)/n)`, not `min(1, G/(n s))` (RR-4). The implied
  constant of `eps` in Theorem 16 is written out, and it carries a factor `k`
  the referee's version dropped (RR-26).

Everything in this revision is re-measured in `rev5_items.py` /
`out_rev5_items.txt`, which uses `sim_core.py` only.

Revision 4's change was in §4: the paper draft now states the wrapper
theorem for **any** budget rule that respects a cap, `0 <= budget_q(t) <= Bmax`,
and that statement is correct — the proof of revision 3's Theorem 4 never reads
the rule except through the cap, so it holds verbatim for rules that decrease
with time, differ between jobs, are redrawn at every dispatch epoch, or are
chosen by an adversary who knows the input. Theorem 4 is restated for the whole
class, the five things the proof does *not* use and the two it does are written
out, and the scope of the multiplicative bound is settled: it needs the job's
*own* constant `B0_i`, and with a common `B0` and the queue-length shape
`B0_q = B0 + gam * n_q`, `gam > 0`, it is false by an unbounded margin
(Proposition 4B', explicit witness). §4.2 is a new numerical attack over six
budget rules, including adversarial per-(job, epoch) budgets. Nothing outside §4
changes: Theorem 4C's family uses a constant budget and is inside the general
class, and it was replayed through the new kernel to confirm it.

Revisions 1-3 answer three adversarial referee reports
(`evidence/guard_variants_referee/`, `evidence/guard_theory_referee/`,
`evidence/guard_theory_referee3/`); every item is listed in the CHANGELOG at
the end. Revision 2's main change was §6.1: the constant `2(k-1)L` of Theorem 1
is proved optimal. Revision 3's main change is §6.4, and it goes the other way:
revision 2 conjectured there that the wrapper's additive constant on the wait is
flat in `k` at about `1.75 L`. **That conjecture is false.** The third referee
built a family that saturates Theorem 1 and the wrapper's `In < B + kL`
*simultaneously*, which revision 2 believed impossible, and it drives the
wrapper constant to the proved ceiling. The conjecture is withdrawn, replaced by
Theorem 4C, and open problem 8.1 of revision 2 is settled and deleted.

Every statement is marked **proved** or **disproved** in the table below, and
the table matches the body exactly. Revision 2 had one **conjecture**, in §6.4;
it is disproved here, and no conjecture is left in the note. Every
one of them was attacked numerically with exact integer arithmetic. Three
independent simulators are used: `sim_core.py` (pure Python), `sharp_kernel.py`
(numba) and, for the general budget class of revision 4, `gen_budget.py`'s own
kernel (numba, the budget rule a parameter rather than a constant); all three
were written for this note by its author, none shares any code with
`guardkern.py`, and `run_sharp.py agree`
cross-checks the first two against each other (20,000 instances, 0 mismatches).
Revision 4's kernel is checked against the second by replaying Theorem 4C's
family through it (§4.2). The three
referee directories contain three further simulators, written by other people,
which agree with these. The third referee's central claim was re-derived here
from its prose and re-measured with `sharp_kernel.py` before being accepted
(`wrapper_tight.py`, `out_wrapper_tight.txt`); its other findings were re-run
the same way (`rev3_items.py`, `out_rev3_items.txt`), and one of them did not
survive verbatim — see R3-3 in the CHANGELOG.

---

## 0. Status

| # | statement | status |
|---|---|---|
| Lem 1 | `\|U_A(t) - U_B(t)\| <= (k-1)L` for any two work-conserving policies | proved |
| Lem 1s | the inequality of Lemma 1 is **strict**: `\|U_A - U_B\| < (k-1)L` whenever `L > 0` **and `k >= 2`**; at `k = 1` both sides are `0` and the bound is attained | proved (rev. 3; the `k >= 2` hypothesis made explicit in rev. 5) |
| Lem 1' | local form: the constant is `(k-1)` times the largest job present at the start of the current all-busy epoch, **read at the left limit** | proved (rev. 2's form is false; counterexample) |
| Lem 1'' | `(k-1)L` in Lemma 1 is a supremum: approached (explicit family), never attained (Lemma 1s) | proved |
| **Thm 1** | `\|k(W_P-W_FCFS) - (In-Out)\| <= 2(k-1)L`, every policy, every input, every job | proved |
| **Thm 3** | `2(k-1)L` is the **exact supremum** of that quantity, both directions; the inequality is strict | proved (explicit family + Lemma 1s) |
| — | the two directions of Thm 3 are **not** alike: upward the excess is real, downward it is half a convention | §6.2, measured |
| Cor 1.1 | `k=1`: `W_P - W_FCFS = In - Out` exactly | proved |
| Cor 1.2 | `In - Out <= Z` implies `excess <= Z/k + (2-2/k)L` | proved |
| Rem 1.3 | the executed-work convention obeys the same bound, with the same supremum upward; completed work lower-bounds **both** currencies, so the choice is not about implementability | proved upward; downward open (§8, item 2); the false "not on `Ine`" clause removed in rev. 5 |
| Lem 2 | a `G`-guarantee **on `i` and on the jobs of `Out_i`** forces `Out_i <= k(G - excess_i + L)` | proved |
| Thm 2 | a `G`-guarantee forces `In_i <= kG + (3k-2)L` | proved |
| Cor 2.1 | the two containments `Budg(Z) ⊆ Guar(...)` and `Guar(G) ⊆ Budg(...)` | proved |
| — | the guard is the *unique* least restrictive rule in `Budg` | **not proved** (open, §8, item 1) |
| Prop 3 | count budgets: no guarantee without `L`; loose by `L/xbar`; not necessary | proved (families given in rev. 3) |
| **Thm 4** | wrapper bound for **any** budget rule with `0 <= budget_q(t) <= Bmax` and an arbitrary base policy: `In_i < Bmax + kL`, `excess <= Bmax/k + (3-2/k)L` | proved (generalised in rev. 4) |
| — | the rule may decrease in time, differ per job, be redrawn every dispatch epoch, or be chosen adversarially with knowledge of the future; `budget == 0` is FCFS exactly | proved (rev. 4) |
| — | the **minimum-rank** tie-break inside `E(t)` is load-bearing: serving another member breaks both bounds | counterexamples measured (rev. 4) |
| **Thm 4B** | multiplicative bound for the age-relative shape `min(B0_q + eta k (t-a_q), Bmax)`, with **`B0_q` a constant of `q`** and the bound stated in `B0_i` | proved |
| **Prop 4B'** | the same bound stated with a **common** `B0` is **false** for `gam > 0` (queue-length shape) and for a per-job `B0_q`, for every `eta`, by an unbounded margin | disproved (explicit witness) |
| Thm 5(a) | `max_q over_q < B` in the base run **implies** the guard is invisible | proved (one direction only) |
| — | the converse of Thm 5(a) | **disproved** (counterexample) |
| Thm 5(b,c) | sufficient conditions in terms of `In^A` and of `A`'s own robustness | proved |
| Prop 6 | no multiplicative consistency w.r.t. the base: the ratio is `(2L+m-1)/(m+1)` | disproved (counterexample, with the ratio now computed) |
| Prop 7 | the guard fires only on a saturated constraint | proved (weakened from revision 1) |
| Prop 8 | `L` -> prefix maximum, at `a_i` for the identity's upward direction and Cor 1.2, at **`s^P_i` for Theorem 4's two wrapper bounds**, at `max(s^P_i,s^F_i)` downward, at `s^F_i+G` in Thm 2 | proved + counterexample (the wrapper placement corrected in rev. 5) |
| Prop 9 | heterogeneous speeds: `B/k -> B/V`, independent of the server-selection rule | proved |
| Prop 10 | pauses/vacations: identity holds with an idleness term; nothing holds without one | partly disproved |
| Prop 11a | timeout kill at `L`: holds verbatim, with `In`, `Out`, `over` read in **executed** work | proved |
| Prop 11b | release times with rank by arrival | disproved; fixed by ranking on release |
| Prop 12 | batch arrivals, zero-length jobs | proved |
| Prop 13 | the `B/k` term of Theorem 4 is attained: the excess is `ceil(B/k)` on an explicit family | proved (family + proof in rev. 3) |
| Prop 14 | **every wrapper whose budget is positive at the first dispatch epoch** admits instances with excess `>= L`; rules that are zero there but positive later fall to the same instance behind a saturating prefix; the rules that escape reproduce FCFS. At `k=1` the wrapper bound `B+L` is a **supremum**, approached (explicit family), never attained | proved (hypothesis and boundary written out in rev. 5) |
| **Thm 4C** | Theorem 4 is **tight for every `k`**: `sup (k*excess - B)/L = 3k-2`, never attained, so the wait-additive `(3-2/k)L` is exact | proved (explicit family; rev. 2's `1.75 L` conjecture is **disproved**) |
| Lem 15 | inversion sums; exact mean-wait identity at `k=1` | proved; the `k>1` clause is weak |
| Thm 16 | price of FCFS-fairness on the two-class family, with the implied constant of `eps` written out | proved (constant added in rev. 5) |
| **Prop 17** | at `k = 1` the achievable fraction is **exactly** `min(1, floor(G/s)/n)` --- not `min(1, G/(n s))`, which revision 4 recorded as a measurement and the paper draft asserted as fact (the paper writes `sigma` for this note's `s`, after the rename of referee item RR-13) | proved (rev. 5; exhaustive check on 1,161 settings) |

---

## 1. Model and notation

*Servers.* `k` identical unit-speed servers, non-preemptive: once a job is
dispatched to a server it occupies it for its full service requirement.

*Jobs.* A finite job set. Job `j` has arrival time `a_j >= 0` and service time
`x_j >= 0` (the paper draft writes `C_j` for this quantity). Jobs are numbered
`1..N` in **rank** order, where rank is the total order induced by
`(a_j, input index)`; `j < i` means "`j` has smaller rank", which implies
`a_j <= a_i`. Zero-length jobs are allowed.

*Policy.* A policy `P` is any rule that, at every instant at which some server
is free and at least one job waits, picks a waiting job and dispatches it. It
may use randomness, predictions of any quality, deadlines, priorities, learned
scores, or knowledge of the future; the upper bounds below never restrict it.
One lower bound — Proposition 14, and only that one — uses the (realistic)
restriction that `P` does not observe `x_j` before `j` completes. Revision 2
attributed that restriction to "the lower bounds of §6" as a class, which is
wrong: the policies of Theorem 3 and Theorem 4C are static priorities defined by
size, and no other lower bound here needs the restriction. (Theorem 3's policy
does not really need size information either: inside a cascade round the unit
jobs always carry the higher ranks, so "units before bigs" is LIFO by rank.)

*Work conservation.* No server idles at an instant at which some job waits.

### 1.1 Tie conventions (referee items O9, G3)

`k >= 2` forces an explicit event order, and the extremal instances of every
statement below live exactly on these ties. At each instant `t`:

1. **completions** are processed first (a server that frees at `t` is free at
   `t`);
2. then **arrivals** (a job with `a_j = t` is waiting at `t`);
3. then **dispatches**, one at a time.

*Dispatch sequence.* The dispatches form a single sequence; several dispatches
may share an instant, and the order inside that instant is the order in which
the policy performs them. Write `j -< i` for "`j` precedes `i` in that
sequence" and call the maximal run of dispatches at one instant a **phase**.

*The quantities are defined by the sequence, not by the clock.*

    W_P[i]  = s^P_i - a_i                                  waiting time
    excess_P[i] = W_P[i] - W_FCFS[i]                       (on the same input)
    In_i    = sum{ x_j : j > i and j -< i }                work that jumped ahead of i
    Out_i   = sum{ x_j : j < i and i -< j }                work that i jumped ahead of
    R^Q_i   = remaining work at time a_i, under Q, of the jobs of rank < i,
              read AFTER the arrivals at a_i have been processed
    rho^Q_i = remaining work at s^Q_i of the jobs dispatched STRICTLY before i
              in Q's sequence that are still in service at s^Q_i

Three consequences of the conventions that the proofs use and that the referees
found missing from revision 1:

* **A job dispatched in the same phase as `i` executes no work in
  `[a_i, s^P_i)`** — that interval ends at the instant of the phase. So a
  same-phase overtaker contributes its whole `x_j` to `In_i` and its whole `x_j`
  to `rho^P_i`, and the two cancel in the identity of Theorem 1.
* `R^Q_i` is read *after* the arrivals at `a_i`. With `R` read before them,
  step (1) of Theorem 1 is false whenever a rank `< i` job arrives at exactly
  `a_i` (the first referee's G3: 44,223 failures out of 199,756 job-checks for
  the pre-arrival reading, 0 for the post-arrival reading).
* `rho` counts only jobs dispatched **strictly** before `i`; `i` itself is never
  counted.

*FCFS* is the policy that always dispatches the minimum-rank waiting job, and,
when several servers free simultaneously, dispatches in increasing rank.

*Other notation.* `L = max_j x_j` (finite in §2-§5; §5.1 removes it).
`U_Q(t)` is the total unfinished work at time `t` under `Q`, counting jobs with
`a_j <= t`; `N_Q(t)` is the number of jobs present (arrived, not completed).
The wrapper of §4 uses `over_q(t)`, `E(t)`, `B0`, `B0_q`, `gam`, `n_q`, `eta`,
`Bmax` and `G`, defined there, with the same meaning as in the paper draft
(where they are written `\mathrm{over}[q](t)`, `E(t)`, `B_0`, `B_{0,q}`,
`\gamma`, `n_q`, `\eta`, `B_{\max}`, `G`) and in `guardkern.py`. The service
time `x_j` of this note is the paper's `C_j`.

All of this is exactly the setting of `guardkern.py`, except that `x_j > 0` is
relaxed to `x_j >= 0` and the guard is no longer part of the model.

---

## 2. Preliminaries

### Lemma 1 (workload comparison) — proved

For any two non-preemptive work-conserving `k`-server policies `A`, `B` on the
same input, `|U_A(t) - U_B(t)| <= (k-1) L` for all `t`.

*Proof (referee item O12/G1: via the left limit at the last crossing).*
Arrivals add the same amount to both, so `D = U_A - U_B` changes only between
arrivals, at rate `-(min(N_A,k) - min(N_B,k))`. If `U_A(u) > (k-1)L` then more
than `k-1` jobs are present under `A` (each carries at most `L`), so all `k`
servers are busy and `min(N_A,k) = k >= min(N_B,k)`: `D` is non-increasing at
`u`.

Fix `t` and let `S = { u <= t : U_A(u) <= (k-1)L }`. `S` is never empty:
`U_A = 0` before the first arrival. (Revision 2 opened with a branch "if `S` is
empty then `D(t) <= U_A(t) <= (k-1)L` directly", which is dead and also
self-contradictory — `S` empty would mean `U_A(t) > (k-1)L`, contradicting the
`U_A(t) <= (k-1)L` the branch then displays. The branch is deleted.) Put
`t0 = sup S <= t`. Revision 1 said "let `t0` be the last time `<= t` with
`U_A(t0) <= (k-1)L`", which presumes the supremum is attained; it need not be,
because `U_A` jumps up at arrivals. Take instead the **left limit**
`U_A(t0^-) = lim_{u ↑ t0} U_A(u)`. By definition of the supremum there are
`u_n ↑ t0` with `U_A(u_n) <= (k-1)L`, so `U_A(t0^-) <= (k-1)L`, and `U_A - U_B`
is left-continuous with `D(t0^-) <= U_A(t0^-) <= (k-1)L`. On `(t0, t]` we have
`U_A > (k-1)L`, so `D` is non-increasing there, and `D` does not jump at `t0`
(arrivals add equally to both). Hence
`D(t) <= D(t0^-) <= (k-1)L`. Swap `A` and `B`. ∎

### Lemma 1s (Lemma 1 is strict) — proved *(new in revision 3)*

If `k >= 2` and `L > 0` then `|U_A(t) - U_B(t)| < (k-1)L` for all `t`: the bound
of Lemma 1 is never attained. (If `L = 0` every job is zero-length, both sides
are `0`, and the statement degenerates.)

**`k >= 2` is needed, and revision 3 left it inside the proof only** (referee
item RR-7). At `k = 1` the right-hand side is `0`, and the bound is attained at
every instant: one server executes work at rate `1` whenever any job is present,
so `U_A ≡ U_B` for any two work-conserving policies. Both steps of the proof
below that need `k >= 2` are marked. The consequence for Theorem 1 is only that
its `|D_i| <= 2(k-1)L` is strict for `k >= 2` and an equality `0 = 0` at `k = 1`;
nothing downstream changes, Theorem 3 being stated for `k >= 2` already.
Measured: `max |U_A - U_B|` over 300 random `k=1` instances is `0`
(`out_rev5_items.txt`, RR-7).

Revision 2 asserted non-attainment in Lemma 1'' and used it for the strictness
of Theorem 3, but proved only that *one particular family* does not attain the
bound, which leaves open that some other instance does. The third referee
supplied the missing argument (item R3-2); here it is.

*Proof.* `D = U_A - U_B` is continuous — arrivals add the same jump to both — and
piecewise linear with finitely many pieces, since the breakpoints are the
finitely many arrival and completion instants of the two runs. Suppose
`D(t) = (k-1)L` for some `t`, and let `t1` be the smallest such `t`; the set
`{ D = (k-1)L }` is closed and bounded below by `0` (where `D(0) = 0 < (k-1)L`,
**which needs `k >= 2`**), so `t1` exists and `t1 > 0`.

Let `I` be the linear piece immediately to the left of `t1`; it has positive
length. Its slope is strictly positive: a negative slope would put
`D > (k-1)L` on `I`, and a zero slope would put `D = (k-1)L` on `I`, and either
contradicts the minimality of `t1`. The slope of `D` is
`-(min(N_A,k) - min(N_B,k))`, so on `I` we have `min(N_A,k) < min(N_B,k)`, hence
`min(N_A,k) <= k-1` and therefore `N_A <= k-1` on `I`.

`A` is work-conserving, so with at most `k-1` jobs present none of them waits:
all `N_A` of them are in service, and `U_A` falls at rate `N_A` on `I`. Also
`U_A <= (k-1)L` on `I`, each of the at most `k-1` present jobs carrying at most
`L`. Taking the left limit at `t1` and using continuity of `D`,

    U_A(t1^-) - U_B(t1^-) = D(t1) = (k-1)L,   U_A(t1^-) <= (k-1)L,   U_B >= 0,

which forces `U_B(t1^-) = 0` and `U_A(t1^-) = (k-1)L`. But `U_B(t1^-) = 0` with
`min(N_B,k) > min(N_A,k) >= 0` gives `N_B >= 1` on `I`, so `U_A(t1^-)` is
reached by a strictly decreasing `U_A` on `I` — i.e. `N_A >= 1` there, since
`N_A = 0` would give `U_A(t1^-) = 0 = (k-1)L`, impossible for `k >= 2, L > 0`.
A strictly decreasing `U_A` bounded above by `(k-1)L` on `I` has
`U_A(t1^-) < U_A(\inf I) <= (k-1)L`, contradicting `U_A(t1^-) = (k-1)L`. Hence
`D` never reaches `(k-1)L`; swap `A` and `B` for the other direction. ∎

The consequence used later: in step (4) of Theorem 1, `|R^P_i - R^F_i|` is
*strictly* below `(k-1)L`, so `|D_i| < 2(k-1)L` strictly, which is what
Theorem 3 needs and what revision 2 left unproved.

### Lemma 1' (local form) — proved, in the repaired form

**Revision 2's form is false** and its own extremal family is the counterexample;
see the end of this subsection. The correct statement reads the reference time at
its left limit, exactly the repair revision 2 already applied to Lemma 1.

Let `t` be any time and let

    u = max{ b <= t : fewer than k of A's servers are busy at b^- } ,

which exists because no server is busy before the first arrival. Then

    U_A(t) - U_B(t)  <=  U_A(u^-)  <=  (k-1) * max{ x_j : j present at u^- } .

*Proof.* Because `A` is work-conserving, "fewer than `k` servers busy" forces
"every present job is in service", so at `u^-` at most `k-1` jobs are present,
each carrying at most its own work: `U_A(u^-) <= (k-1) max{x_j : j at u^-}`. By
maximality of `u`, all `k` of `A`'s servers are busy at `v^-` for every
`v in (u, t]`, so `min(N_A,k) = k >= min(N_B,k)` there and `D = U_A - U_B` is
non-increasing on `(u,t]`. `D` is continuous, so `D(t) <= D(u^-) <= U_A(u^-)`
(using `U_B >= 0`). ∎

In particular the constant can always be taken as `(k-1) * Λpref(t)` with
`Λpref(t) = max{ x_j : a_j <= t }`, a prefix maximum: the jobs present at `u^-`
arrived strictly before `u <= t`. **No global size bound is needed** for
Lemma 1.

**What was wrong with revision 2's form** (referee item R3-3). It read: "Let
`u <= t` be any time with `N_A(u) <= k-1` and `N_A >= k` throughout `(u, t]`.
Then `U_A(t) - U_B(t) <= (k-1) max{x_j : j present at u}`. If no such `u` exists,
`U_A(t) <= U_B(t)`." The displayed inequality is correct; the fallback clause is
not, because an admissible `u` can fail to exist while the gap is positive. The
count `N_A(u)` is read *after* the arrivals at `u`, so at an instant where `N_A`
jumps from `k-1` to `k` there is no admissible reference time at all: every
`u` before the jump has `N_A < k` somewhere in `(u,t]`, and `u` at or after the
jump has `N_A(u) >= k`.

*Smallest counterexample* (`rev3_items.py`, `out_rev3_items.txt`). `k = 2`,

    a = (0,0,0,0,0,4,4),   x = (4,1,1,1,1,10,10),

`P` = "unit jobs before the big job", a legal static-priority work-conserving
policy. Then `P` starts the jobs at `(2,0,0,1,1,4,6)` and FCFS at
`(0,0,1,2,3,4,4)`. At `t = 4` and at `t = 5` the admissible set is empty — the
search is exact, over the constancy decomposition of the time line, not over a
grid — while `U_P - U_FCFS = 2 > 0`. The fallback clause asserts `20 <= 18`.
The repaired form takes `u = 4`, where `U_P(4^-) = 2` and one job of size `4` is
present, and gives `2 <= (k-1)*4 = 4`.

The note's own extremal family fails the same clause at `t = T_m`, where `N_P`
is `k-1` just before `T_m` and jumps to `>= k` at `T_m`: at
`(k,L,m) = (2,64,3), (3,81,2), (4,64,2)` the admissible set is empty and the gap
is `rho_m = 56, 90, 84`. One correction to the referee's wording: on the cascade
*without* its finale the clause is not refuted, because there `N_P(T_m) = k-1`
and the trivial choice `u = t` is admissible and gives the correct bound
`(k-1)L`. The refutation needs arrivals at `T_m`.

Proposition 8 depends on Lemma 1' only through "the jobs present at the
reference time arrived no later than `a_i`", which the repaired form still
supplies: `u <= a_i` and the jobs present at `u^-` arrived strictly before `u`.

### Lemma 1'' (Lemma 1 is tight) — proved

For every `k >= 2` and every `m >= 1` there is an input with `L = k^m`, and a
work-conserving policy `P`, such that at time `T_m = mL`

    U_P(T_m) - U_FCFS(T_m)  =  (k-1) L ( 1 - ((k-1)/k)^m )  ,

FCFS is empty and idle at `T_m`, and `P` holds exactly `k-1` jobs in service,
each with remaining work `L(1 - ((k-1)/k)^m)`. Hence
`sup (U_A - U_B) = (k-1)L`; by Lemma 1s it is never attained.

*Proof (the cascade).* Fix `k` and `L = k^m`. The input is built from `m`
identical rounds; round `j` occupies `[T_j, T_{j+1}) = [jL, (j+1)L)`. At time
`T_j` inject, in index order:

* `k-1` **big** jobs of work `L`, and then
* `L` **unit** jobs of work `1`

(so the bigs have the lower ranks). Let `P` be the static-priority policy that
always dispatches a waiting unit job if one exists, and a big job otherwise;
this is a legal work-conserving policy.

*Induction hypothesis at `T_j`:* FCFS has completed every job and all `k` of
its servers are idle; `P` has exactly `k-1` jobs in service, each with remaining
`rho_j/(k-1)`, where `rho_0 = 0`.

*FCFS in round `j`.* All `k` servers are free at `T_j`, so FCFS dispatches the
`k-1` bigs and one unit. Its remaining server then takes the `L` unit jobs back
to back, finishing at `T_j + L`; the bigs also finish at `T_j + L`. So FCFS has
all `k` servers busy on `(T_j, T_{j+1})` and is again empty and idle at
`T_{j+1}`.

*`P` in round `j`.* At `T_j`, `P` has one free server, which takes a unit. Its
`k-1` old jobs all complete at `T_j + rho_j/(k-1)`, and their servers take units
as well; `P` never touches a big while a unit waits. So `P` has all `k` servers
busy from `T_j` until the units run out, which happens at `T_j + tau_j` where
`k tau_j = rho_j + L`, i.e. `tau_j = (rho_j + L)/k`. (`P` is indeed busy
throughout: the old jobs end at `rho_j/(k-1) <= tau_j`, which is
`k rho_j <= (k-1)(rho_j + L)`, i.e. `rho_j <= (k-1)L`, true by induction.)
At `T_j + tau_j`, `P` holds only the `k-1` bigs; it dispatches them and leaves
one server idle.

*The gain.* On `(T_j + tau_j, T_{j+1}]`, FCFS has `k` busy servers and `P` has
`k-1`, so `U_P - U_FCFS` grows at rate `1` over a window of length `L - tau_j`.
At `T_{j+1}` FCFS is empty, and `P`'s `k-1` bigs have each run for `L - tau_j`,
so each has `tau_j` left. The hypothesis is reproduced with

    rho_{j+1} = (k-1) tau_j = (k-1)(rho_j + L)/k ,

whose solution with `rho_0 = 0` is `rho_j = (k-1)L(1 - ((k-1)/k)^j)`. Because
FCFS is empty at `T_j`, `U_P(T_j) - U_FCFS(T_j) = rho_j`. With `L = k^m` every
`rho_j` and `tau_j` with `j <= m` is an integer. Since `rho_m -> (k-1)L` as
`m -> infinity`, the supremum over all instances is at least `(k-1)L`, and
Lemma 1 makes it at most `(k-1)L`. ∎

Revision 2 closed this proof with "since `rho_j < (k-1)L` for every finite `j`
… the bound is a supremum that is never attained", which does not follow: it
shows only that *this* family misses the bound, not that every instance does.
Non-attainment is Lemma 1s, proved above.

Checked exactly (`family_tight.py`, `out_sharp_family.txt`): the measured gap is
`(k-1)L(1 - ((k-1)/k)^m)` to the last digit — e.g. `63/64 L` at `k=2, m=6`,
`130/81 L` at `k=3, m=4`, `111/64 L` at `k=4, m=3` — simulated by `sim_core.py`,
which knows nothing about the construction.

---

## 3. G1 — the net-overtake identity

### Theorem 1 (the net-overtake identity) — **proved**

For every non-preemptive work-conserving `k`-server policy `P`, every input, and
every job `i`:

    -2(k-1)L  <=  k * ( W_P[i] - W_FCFS[i] )  -  ( In_i - Out_i )  <=  2(k-1)L

More precisely, writing `D_i` for the middle expression,

    D_i = (R^P_i - R^F_i) - rho^P_i + rho^F_i,
    |R^P_i - R^F_i| <= (k-1)L,   0 <= rho^P_i, rho^F_i <= (k-1)L.

So `c(k) = 2 - 2/k` in the normalised form

    | W_P[i] - W_FCFS[i] - (In_i - Out_i)/k |  <=  (2 - 2/k) L.

*Proof.*

**(1) Busy-period identity.** Job `i` waits throughout `[a_i, s^P_i)`, so by
work conservation every server is busy on that interval and exactly `k*W_P[i]`
units of work are executed there, none of it on `i`. (If `s^P_i = a_i` the
interval is empty and both sides are `0`.)

Split the executed work by rank.

*Rank `> i`.* Such a job `j` has `a_j >= a_i`, so it can be executed inside the
window only if it is dispatched inside the window, i.e. only if `j -< i`.
Conversely every `j > i` with `j -< i` is dispatched at or before `s^P_i`.
Hence the work executed on rank `> i` jobs equals `In_i - rho_new`, where
`rho_new` is the total remaining work at time `s^P_i` of those overtakers that
have not finished by then. By §1.1 a same-phase overtaker contributes `x_j` to
both `In_i` and `rho_new`, and so contributes `0` to the executed work, as it
must.

*Rank `< i`.* All such jobs are present at `a_i` (their arrival is `<= a_i`),
with total remaining `R^P_i` — read after the arrivals at `a_i`, so a rank `< i`
job arriving at exactly `a_i` counts with its full `x_j`. At `s^P_i` their total
remaining is `Out_i` (those not dispatched before `i`, each with full work — this
includes those dispatched in `i`'s own phase after `i`) plus `rho_old` (those
dispatched strictly before `i` and unfinished). So the executed work on them is
`R^P_i - Out_i - rho_old`.

Therefore

    k * W_P[i] = R^P_i + In_i - Out_i - rho^P_i,   rho^P_i := rho_old + rho_new. (1)

**(2) Bounding `rho`.** `rho^P_i` is the total remaining work, at `s^P_i`, of
the jobs dispatched strictly before `i` that are still in service then. Each of
them occupies a distinct server, and none of them occupies the server that takes
`i`, so there are at most `k-1` of them and each has remaining work `<= L`.
Hence `0 <= rho^P_i <= (k-1)L`.

**(3) FCFS.** Under FCFS, `In^F_i = 0`: a rank `> i` job dispatched before `i`
would have to be dispatched at an instant at which `i` waits, but FCFS
dispatches the minimum-rank waiting job there, and inside a phase it dispatches
in increasing rank. And `Out^F_i = 0`: at `s^F_i` every rank `< i` job has
already been dispatched, else FCFS would have taken it instead of `i`. So (1)
applied to FCFS reads

    k * W_FCFS[i] = R^F_i - rho^F_i,        0 <= rho^F_i <= (k-1)L.             (2)

**(4) Comparison of the two remaining-work terms.** At time `a_i`, after the
arrivals at `a_i` are processed, the two systems contain exactly the same jobs.
The jobs of rank `>= i` present at `a_i` (the ones with `a_j = a_i`) are
untouched in both. Hence `U_P(a_i) - U_F(a_i) = R^P_i - R^F_i`, and Lemma 1
gives `|R^P_i - R^F_i| <= (k-1)L`.

**(5)** Subtract (2) from (1). Each direction uses only two of the three
ranges — the upper direction uses `R^P - R^F <= (k-1)L` and `rho^F <= (k-1)L`
with `rho^P >= 0`, the lower direction the mirror image — so the slack is
`2(k-1)L` and not `3(k-1)L`. ∎

**Remark 1.0 (where the extremal instances live).** At `k = 1` all three terms
vanish and the identity is exact (Corollary 1.1). At `k >= 2` the easiest
instances to find are degenerate: the referee's `k=4` witness is four jobs of
work `L` arriving together, with `P` dispatching the victim last **in the same
phase**, so every wait is `0`, the actual excess is `0`, and `D = -(k-1)L` is
pure same-phase bookkeeping. Those instances are not the worst ones — §6 builds
instances with genuine waits and `|D| -> 2(k-1)L` — but they explain why a
random or small-`n` exhaustive search stops at `(k-1)L` (see §6.3).

**Numerical attack** (`run_identity.py`/`out_identity.txt` from revision 1, and
`run_sharp.py` with `out_sharp_agree.txt`, `out_sharp_exh.txt`,
`out_sharp_rand.txt` for this revision):

* simulator self-test: `k=1` FCFS reproduces the Lindley recursion on 20,000
  instances; the busy-period identity `k*W[i] = ` work executed in `[a_i, s_i)`
  holds on 90,188 further job-checks; the numba kernel and `sim_core.py` agree
  on schedules, FCFS, `In`, `Out` and `D` on 20,000 instances (0 mismatches).
* exhaustive: **every** work-conserving schedule of 4,820,505 small instances —
  45,304,641 schedules, `k = 1..4`, `n <= 6`, `L in {2,3,4,6}`, ties and
  zero-length jobs included — no violation.
* random: 10,800,000 instances / 108,000,000 job-checks, `k in 1..6`,
  `L in {2,5,9}`, `n in {6,10,14}`, free-choice tapes (every work-conserving
  schedule is reachable) — no violation, in either convention.
* the second referee's independent sweep: 1,130,777 exhaustive schedules and
  300,000,000 random instances / 2,249,983,356 job-checks — no violation; and a
  per-step audit of the five proof steps above on 268,188 job-checks, 0
  failures.

### Corollary 1.1 (single server: the identity is exact) — **proved**

For `k = 1`, for every work-conserving non-preemptive policy, every input and
every job:

    W_P[i] - W_FCFS[i]  =  In_i - Out_i         (exactly, no error term)

Verified exactly on 100% of the enumerated schedules and on every random
instance with `k=1`: the observed slack is identically `0` (all four `k=1` rows
of `out_sharp_rand.txt` and `out_sharp_exh.txt`).

### Corollary 1.2 (work budgets are sufficient) — **proved**

If a policy keeps `In_i - Out_i <= Z` for every job (in particular if it keeps
`In_i <= Z`, since `Out_i >= 0`), then

    W_P[i] <= W_FCFS[i] + Z/k + (2 - 2/k) L   for every job.

### Remark 1.3 (the executed-work convention) — proved upward, open downward

Referee item O9 asks whether defining the two currencies in *executed* work
gives a smaller constant. Put

    Ine_i = work of rank > i jobs EXECUTED during [a_i, s^P_i)   ( = In_i - rho_new )
    Out_i = remaining work at s^P_i of the rank < i jobs not yet dispatched
            ( this is already the definition above -- Out needs no change )

and `De_i = k(W_P[i] - W_F[i]) - (Ine_i - Out_i)`. Then (1) becomes
`k W_P[i] = R^P_i + Ine_i - Out_i - rho_old`, so

    De_i = (R^P_i - R^F_i) - rho_old^P_i + rho^F_i,   0 <= rho_old^P_i <= (k-1)L,

and **the same bound `|De_i| <= 2(k-1)L` holds, with the same proof**. The
convention does kill the degenerate witnesses of Remark 1.0 (a same-phase
overtaker now contributes nothing, so `De = 0` there). It does **not** give a
smaller constant upward: at the victim of the family of Theorem 3,
`rho_old = 0` and `rho_new <= k-1 = o(L)`, so `De = D + rho_new >= D` and `De`
is driven to `2(k-1)L` as well (`out_sharp_family.txt`, column `De`: `127/64 L`
at `k=2, m=6`). Revision 2 said "`rho_new = 0` at the victim"; that is true only
when the last unit jobs happen to complete exactly at `s^P_i`. Measured
(`out_rev3_items.txt`): `rho_new = 0` at `(k,m) = (2,6)` and `(4,3)`, `1` at
`(2,3)`, `2` at `(3,4)`. The conclusion is unaffected. Downward the mirror
family only reaches
`(k-1)L` for `De`, while hill-climbing finds `1.625 L` at `k=2`, so the true
downward constant for `De` is somewhere in `((k-1)L, 2(k-1)L]` and is open.

*Which is the main theorem.* The **sequence** convention (`In_i`) stays the main
statement, for two reasons: its constant is exactly determined in both
directions (Theorem 3), whereas the downward constant for `De` is open; and its
two sides are symmetric. `De` is recorded here as a remark because it is the
cleaner *accounting* (no zero-wait witnesses), and every numerical run in this
directory reports both.

**A third reason was given here and in the paper draft, and it is false**
(referee item RR-8). Revisions 1–4 said that completed work "is a lower bound on
`In_i` but not on `Ine_i`", so that only the sequence convention is meterable.
Both are metered. Let `j` have rank above `q` and complete at some
`t <= s^P_q`. Then `a_j >= a_q`, so `j` is dispatched at `s^P_j >= a_j >= a_q`
and finishes by `t <= s^P_q`: the whole of `x_j` is executed inside
`[a_q, s^P_q)` and is counted in full by `Ine_q`. Hence

    over_q(t)  <=  Ine_q  <=  In_q     for every t <= s^P_q,

so the guard's charge lower-bounds both currencies and the wrapper is
implementable under either. Checked on 1,000 instances at `k = 1..4`, 18,688
`(q,t)` pairs, 0 violations of either inequality (`out_rev5_items.txt`, RR-8).

### Lemma 2 (a guarantee bounds `Out` automatically) — **proved**, strengthened

Let `i` be a job and suppose `excess_P[i] <= G` and `excess_P[j] <= G` for every
`j` counted in `Out_i` (i.e. every rank `< i` job that `i` overtook). Then

    Out_i <= k ( G - excess_P[i] + L ).

*Proof.* Every job `j < i` counted in `Out_i` is dispatched at or after `s^P_i`,
and at `s^P_j <= s^F_j + G <= s^F_i + G` because FCFS dispatches every rank `< i`
job before `i`. So all of them start inside a window of length
`Δ = (s^F_i + G) - s^P_i = G - excess_P[i] >= 0`. Fix a server: of the jobs it
starts inside a window of length `Δ`, all but the last complete inside the
window, so their total work is `<= Δ`, and the last one adds `<= L`. Summing
over `k` servers gives `Out_i <= k(Δ + L)`. ∎

Revision 1 assumed the guarantee for *every* job of the input; the proof only
ever uses it for `i` and for the jobs of `Out_i`, which is the free
strengthening the second referee pointed out.

Both halves of the hypothesis are needed, and the witness should be exhibited
rather than counted, because the second referee's evidence for the second half
used a "guarantee" `G` set to the maximum excess among the jobs *outside*
`Out_i`, which can be negative — and a negative `G` is not a guarantee (referee
item R3-12). A witness with `G = 0`: `k = 1`, five unit jobs all arriving at
`t = 0`, dispatch sequence `3, 4, 2, 0, 1`, victim `i = 2`. The per-job excesses
are `(3, 3, 0, -3, -3)`, so `excess_2 = 0 <= G = 0`, yet
`Out_2 = 2 > k(G - excess_2 + L) = 1`. The jobs of `Out_2` are `0` and `1`, both
with excess `3 > G` — exactly the half of the hypothesis that has been dropped.
Verified in `out_rev3_items.txt`.

Checked on 2,400,760 job-instances (`out_consistency.txt`): 0 failures. The
third referee adds 1,440,990 hypothesis-checks restricted to `G >= 0`: 0
violations of the strengthened form, 86,103 violations when the hypothesis on
`i` itself is dropped, 364 when it is kept on `i` but not on the jobs of
`Out_i`.

### Theorem 2 (work budgets are necessary) — **proved**

If `P` satisfies `excess_P[j] <= G` for every job on some input, then for every
`i`

    In_i  <=  k G + (3k - 2) L.

*Proof.* Theorem 1 gives `In_i - Out_i <= k*excess_P[i] + 2(k-1)L`. Add Lemma 2
(whose hypothesis holds, since the guarantee is assumed for every job):

    In_i <= k*excess_P[i] + 2(k-1)L + k(G - excess_P[i] + L) = kG + (3k-2)L,

and the `excess_P[i]` terms cancel, so the bound is uniform. ∎

Checked on 2,400,760 job-instances: 0 failures.

### Corollary 2.1 (work budgets are the right currency) — **proved**, restated

Write `Guar(G)` for the class of policies with per-job excess `<= G` on every
input, and `Budg(Z)` for the class that keeps `In_i <= Z` on every input. Then

    Budg(Z)  ⊆  Guar( Z/k + (2 - 2/k) L )          (Corollary 1.2)
    Guar(G)  ⊆  Budg( kG + (3k-2) L )              (Theorem 2)

so the two families coincide up to an additive `O(kL)` in the budget: **a work
budget on the overtaken work is both necessary and sufficient for an
FCFS-relative per-job guarantee.**

Revision 1 continued "…and it is the *only* such currency" and called the guard
"the least restrictive" member of `Budg`. Neither claim is proved by the two
containments, and the second referee was right to flag it (item O8). The two
containments are exactly what is proved; uniqueness and minimality are open
(§8, item 1).

### Proposition 3 (count and position budgets) — **proved**

Let a policy bound the *number* of jobs allowed to overtake any given job by `N`
(the Nudge-K / finite-skip currency).

(a) *Without a size bound there is no guarantee at all* — **proved**. Fix any
`k >= 1` and any `X > 0`. At `t = 0` let there arrive, in rank order: `k-1` jobs
of work `X`, then the victim `i` of work `1`, then one further job of work `X`.
All `k` servers are free. FCFS dispatches the `k-1` jobs of rank `< i` and then
`i`, all in the phase at `t = 0`, so `W_FCFS[i] = 0`. The policy `P` dispatches
the same `k-1` jobs and then the *last* job instead of `i`; this is
work-conserving, and it fills all `k` servers, so `i` waits until the first
completion at `t = X`. Hence `excess_P[i] = X` with exactly **one** overtaker,
so every count budget `N >= 1` admits `P` while the excess is unbounded in `X`.
∎ (Measured for `k = 1,2,3` and `X = 10, 100, 1000` in `out_rev3_items.txt`:
`In_i = X`, overtaker count `1`, excess `X` in every row.) Revision 2 gave the
one-line sentence "one overtaker of work `X` costs `excess = X/k`", which is
also loose — on this family the cost is `X`, not `X/k`.

(b) *With sizes `<= L`*, `In_i <= N L` and Corollary 1.2 gives
`excess <= N L / k + (2-2/k)L`, and this is attained when every overtaker has
size exactly `L`. Compare a work budget at the same guarantee `G`: the work
budget is `B ≈ kG`, which admits `B / xbar` overtakes when the typical size is
`xbar`, while the count budget admitting the same guarantee is `N = kG/L`, i.e.
`B/L` overtakes. **The count budget is loose by exactly the factor `L / xbar`.**
Measured (`out_tightness.txt`, G4.5(b)): at `k=2` and guarantee `G=100`, a count
budget must be `N = 2` when `L = 100`, while a work budget `B = kG = 200` admits
200 overtakes at `xbar = 1`, 20 at `xbar = 10`, and 2 at `xbar = 100`. For this
project's workload (`L` = the 60 s per-submission cap, `xbar` on the order of a
second) the factor is one to two orders of magnitude.

(c) *A count budget is not necessary either* — **proved**. Fix `k = 1` and any
`M >= 1`, and set `L = 2M`. At `t = 0` let there arrive, in rank order, the
victim `i` of work `L` and then `M` jobs of work `1`. `P` dispatches the `M`
small jobs first, so `W_P[i] = M` and `W_FCFS[i] = 0`: `excess_P[i] = M = L/2`,
and every small job finishes earlier under `P` than under FCFS, so no job has
excess above `L/2`. `P` therefore meets the guarantee `G = L/2` for every `M`,
with `In_i = M = kG` — inside the work budget `kG` that Corollary 1.2 asks for —
while its overtaker count is `M`, which exceeds every fixed `N` once `M > N`. So
no finite count budget is necessary for the guarantee `L/2`. ∎ (Measured for
`M = 4, 16, 64, 256` in `out_rev3_items.txt`: excess `= L/2` in every row.)

---

## 4. G2 — the guard as a black-box wrapper

### 4.1 The wrapper

Fix an arbitrary **base policy** `A` (any rule that picks a waiting job;
randomised, learned, prediction-driven, EDF, class-priority, anything). For a
waiting job `q` and time `t` let

    over_q(t) = total true service of jobs of rank > q that have COMPLETED by t

(they necessarily completed while `q` waited, since a job of rank `> q` arrives
at or after `a_q`). Given a **budget function** `budget_q(t)`, the fired set is

    E(t) = { q waiting at t : over_q(t) >= budget_q(t) }.

At each dispatch: if `E(t)` is non-empty, dispatch its **minimum-rank** member;
otherwise dispatch whatever `A` chooses.

Only completed work is charged, because a scheduler that learns `x_j` at
completion cannot charge work in progress. That is the whole reason for the
extra `kL` below.

Serving the minimum-rank member of `E(t)` is what makes the per-job argument
work when the budget is not the same for every job: job `i` is overtaken only at
instants at which its own budget is unspent. For a constant budget, `over_q(t)`
is non-increasing in rank, so `E(t)` is non-empty iff the head of the waiting
queue is in it — the rule then degenerates to the head check of the project's
original guard.

The **budget class** is everything the cap admits:

    any function budget_q(t) with  0 <= budget_q(t) <= Bmax                (Thm 4)

and one shape inside it carries a second bound:

    age-relative:  budget_q(t) = min( B0_q + eta * k * (t - a_q), Bmax )
                   with 0 <= eta < 1 and B0_q a constant of q             (Thm 4B)

`guard(A, B)` denotes the constant rule `budget_q(t) = B`. The paper's
one-line family `budget_q(t) = min(B0 + gam * n_q + eta * k * (t - a_q), Bmax)`,
with `n_q` the number of jobs waiting when `q` arrives, sits inside the class for
every `B0, gam >= 0` and `eta in [0,1)`; it is the age-relative shape exactly
when `gam = 0`, and has `B0_q = B0 + gam * n_q` otherwise.

Revision 3 stated Theorem 4 for the constant rule and Theorem 4B for the
age-relative one. Revision 4 states Theorem 4 for the whole class, because the
proof never reads the rule except through the cap, and separates out what the
multiplicative bound really needs (Theorem 4B and Proposition 4B').

### Theorem 4 (the additive bound, arbitrary base policy, arbitrary budget rule) — **proved**

Fix any base policy `A`, any cap `Bmax >= 0` and **any** budget rule with
`0 <= budget_q(t) <= Bmax` for every waiting `q` and every dispatch epoch. Then
for every input and every job `i`:

    In_i  <  Bmax + k L      (whenever i has at least one overtaker)         (3)
    W_guard[i]  <=  W_FCFS[i] + Bmax/k + (3 - 2/k) L                         (4)

and (4) is strict unless `Bmax = L = 0`.

*Proof of (3).* Among the overtakers of `i`, consider the one dispatched last in
the dispatch sequence, say `j`, and let `t` be its dispatch epoch. Because
dispatches are sequential and `i` is dispatched after `j`, **job `i` is waiting
at the moment `j` is dispatched**, including the case `t = s^P_i`, in which `j`
is dispatched in `i`'s own phase, just before `i` (referee item G2 — revision 1
said "dispatched while `i` waits", which reads as `t < s^P_i` and leaves that
case unhandled). Job `i` has arrived by then, since `a_i <= a_j <= t`.

Since `j` is dispatched, either `E(t)` is empty or `min E(t) = j`; in both cases
`i ∉ E(t)` (its rank is smaller than `j`'s), so
`over_i(t) < budget_i(t) <= Bmax`. The overtakers of `i` dispatched strictly
before `j` split into those completed by `t`, whose total work is `over_i(t)`,
and those still in service at `t`. The latter occupy distinct servers, and the
server that takes `j` is not one of them, so there are at most `k-1`, each of
work `<= L`. Adding `j` itself (`<= L`) gives `In_i < Bmax + kL`. (In the case
`t = s^P_i` the count is even smaller: `j`'s server and `i`'s server are two
distinct free servers, so at most `k-2` others are in service.) If `i` has no
overtaker then `In_i = 0`.

*Proof of (4).* Theorem 1 with `Out_i >= 0`:
`k*excess[i] <= In_i - Out_i + 2(k-1)L <= In_i + 2(k-1)L < Bmax + kL +
2(k-1)L = Bmax + (3k-2)L`, the last step being (3). If `i` has no overtaker,
`k*excess[i] <= 2(k-1)L`, which is `< Bmax + (3k-2)L` whenever `Bmax + kL > 0`.
∎

**What the proof reads, and what it does not.** The budget rule enters at
exactly one place, `over_i(t) < budget_i(t) <= Bmax`, evaluated at the single
epoch `t` at which `i`'s last overtaker is dispatched, and for the single job
`i`. Five consequences, all left implicit in revision 3; items 1, 2, 3 and 5 are
exercised by the sweeps of §4.2, item 4 is not implemented there:

1. **Monotonicity in `t` is irrelevant.** A rule that *decreases* with time is
   covered: a job that is in `E` at one epoch and out of it at a later one —
   un-fired — changes nothing, because the argument never claims `i` stays out
   of `E`, only that it is out of `E` at that one epoch.
2. **Rules may differ per job.** Only `budget_i` is read. Nothing compares the
   budgets of two jobs.
3. **The rule may be adversarial, randomised, or clairvoyant.** The statement is
   pathwise on the realised dispatch sequence, so a rule chosen with knowledge of
   the whole input, or by coin flips, or by an adversary who watches the base
   policy, is covered; no measurability or non-anticipation is used. The same is
   already true of the base policy `A`.
4. **`budget >= 0` is not needed for (3) or (4).** A negative budget puts every
   waiting job in `E(t)`, so no job is ever overtaken and `In_i = 0`. The lower
   bound `0` matters only for the reading in item 5.
5. **`budget == 0` is FCFS, exactly.** `over_q(t) >= 0` always, so `E(t)` is the
   whole waiting set, the wrapper serves the minimum-rank waiting job at every
   dispatch, and inside a phase it serves in increasing rank — which is the
   definition of FCFS in §1.1. Both bounds then read `In_i = 0`,
   `excess = 0 <= (3-2/k)L`.

**What is load-bearing.** Two things, and only two. First, `E(t)` must be served
by **minimum rank**: if the wrapper serves some other member of `E(t)` — the
natural alternative when several jobs are fired and fewer servers are free is to
serve them in some other order — then `i` can be in `E(t)` while `j` is
dispatched, `over_i(t) < budget_i(t)` fails, and both (3) and (4) fail (§4.2).
Serving every member of `E(t)` at once is not required, and is impossible when
fewer servers are free than `|E(t)|`: the rest of `E(t)` stays fired and is
served at the following epochs, which is the run the proof analyses. Second,
`over` must be
charged to the *completed* work of higher-ranked jobs; that is what makes
`over_i(t)` a lower bound on the part of `In_i` that is already finished, and
the `kL` in (3) is the price of not being able to charge work in progress.

**One notational point.** `budget_q(t)` is indexed by the clock in the paper and
here, but several dispatches may share an instant, and the proof allows the rule
to take a different value at each of them: read the index as the dispatch epoch,
not the clock time. `over_q(t)` does not change inside a phase (a zero-length job
dispatched and completed inside it adds `0`), so nothing else in the argument is
affected.

Nothing in the argument refers to `A`. **The guard is a wrapper that makes any
dispatcher FCFS-robust.** Both constants are optimal: Theorem 4C (§6.4) shows
that `Bmax/k` and `(3 - 2/k)L` are the exact suprema, each approached and never
attained, on a family that uses a constant budget and is therefore inside the
class of Theorem 4 verbatim.

### Theorem 4B (the multiplicative bound: age-relative shape, per-job constant) — **proved**

This is "Theorem B" of `guardkern.py`, promoted from that docstring to a theorem
here at the request of the paper draft (item D6). Let

    budget_q(t) = min( B0_q + eta * k * (t - a_q), Bmax ),   0 <= eta < 1,

with `B0_q >= 0` **a constant of `q`** — any quantity that does not vary with
`t`, in particular anything known at `a_q` — and `Bmax > 0` (or `Bmax = +inf`
for no cap). Then for every base policy `A`, every input and every job `i`,
writing `W = W_guard[i]`:

    In_i  <  B0_i + eta * k * W + k L      and, when Bmax < inf,  In_i < Bmax + kL   (5)
                                           (both whenever i has at least one overtaker)

    (1 - eta) * W  <=  W_FCFS[i] + B0_i/k + (3 - 2/k) L                              (6)

    W  <=  W_FCFS[i] + Bmax/k + (3 - 2/k) L                                          (7)

so the guarantee is the smaller of `(W_FCFS[i] + B0_i/k + (3-2/k)L)/(1-eta)` and
`W_FCFS[i] + Bmax/k + (3-2/k)L`. **`B0_i` is `i`'s own constant**, not a number
common to all jobs; Proposition 4B' below shows that the distinction is not
cosmetic.

*Proof.* (5) repeats the proof of (3) verbatim, with `Bmax` replaced by
`budget_i(t)` at the epoch `t` of `i`'s last overtaker: `i ∉ E(t)` gives
`over_i(t) < budget_i(t)`, and since `t <= s^P_i = a_i + W`,

    budget_i(t) <= B0_i + eta*k*(t - a_i) <= B0_i + eta*k*W,
    budget_i(t) <= Bmax .

Both bounds on `over_i(t)` then carry through the same "at most `k-1` in service
plus `j` itself" count, giving the two halves of (5). The guard "whenever `i`
has at least one overtaker" is the same one Theorem 4's (3) carries, and
revision 2 omitted it here (referee item R3-11): with `In_i = 0`, `B0_i = 0`,
`eta = 0` and `L = 0` the strict inequality would read `0 < 0`. If `i` has no
overtaker then `In_i = 0` and (6), (7) hold trivially.

(6): Theorem 1 with `Out_i >= 0` gives
`k*(W - W_FCFS[i]) <= In_i + 2(k-1)L < B0_i + eta*k*W + kL + 2(k-1)L`, i.e.
`k W - eta*k*W <= k W_FCFS[i] + B0_i + (3k-2)L`; divide by `k`. (7) is Theorem 4
with `Bmax` and is where the operator's promise comes from. ∎

**Reading of `eta`.** A waiting job tolerates at most a fraction `eta` of the
system's whole service capacity, taken over its own waiting time, being spent on
jobs that arrived after it. `eta = 0` recovers the constant case of Theorem 4.

### Proposition 4B' (the multiplicative bound needs the per-job constant) — **proved (negative)**

For the queue-length shape `B0_q = B0 + gam * n_q` with `gam > 0`, the
multiplicative bound stated with the **common** `B0`,

    W  <=  ( W_FCFS[i] + B0/k + (3 - 2/k) L ) / (1 - eta) ,                  (6')

is false, for every `eta in [0,1)`, by an unbounded margin. (6) with `i`'s own
`B0_i = B0 + gam * n_i` holds, and so does Theorem 4.

*Witness.* `k = 1`, `L = 1`, `B0 = 0`, `Bmax = gam`, any `eta in [0,1)`.

    rank 0:   a = 0, x = 1     n_q = 0, so budget == 0: always fired, served first
    rank 1:   a = 0, x = 1     THE VICTIM; n_q = 1, so budget_victim = gam
    rank 2..: a = 1, 2, 3, ..., x = 1, all of rank above the victim

base policy: always take the newest waiting job.

At `t = 0` job `0` has `n_q = 0`, hence budget `0`, hence is in `E(0)`, and being
the minimum-rank member it is served; it completes at `t = 1`. From then on the
victim's budget is `gam` and its `over` grows by `1` per unit of time as the late
unit jobs complete, so `E` is empty until `over_victim = gam` at `t = gam + 1`,
where the victim fires and is served. FCFS serves the victim at `t = 1`. Hence

    W = gam + 1,   W_FCFS = 1,   excess = gam  exactly,

against a right-hand side of (6') equal to `(1 + 0 + 1)/(1 - eta) = 2/(1 - eta)`,
which does not depend on `gam`. Taking `gam > (1 + eta)/(1 - eta)` breaks (6')
for that `eta`; `gam -> inf` makes the ratio of the two sides unbounded. Measured
(`gen_budget.py`, `out_gen_budget.txt`):

| `eta` | `gam` | RHS of (6') | `W` | `W_FCFS` | (6') holds |
|---|---|---|---|---|---|
| `0` | 3 | 2 | 4 | 1 | no |
| `1/2` | 5 | 4 | 6 | 1 | no |
| `3/4` | 9 | 8 | 10 | 1 | no |
| `9/10` | 21 | 20 | 22 | 1 | no |
| `99/100` | 201 | 200 | 202 | 1 | no |

On the same instance Theorem 4 holds with room to spare — `W = gam + 1` against
`W_FCFS + Bmax/k + (3-2/k)L = gam + 2` — and (6) with `B0_i = gam` holds for
every `eta`. ∎

*Reading.* The paper's `rem:mult_scope` says that with `gam > 0` the constant
part "is not a constant the operator can state in advance", and therefore claims
Theorem 4 alone for that shape. The conclusion is right and the mechanism is
worth stating as well: it is not only that the operator cannot *announce* the
bound, it is that the bound with the announced `B0` is *false*, and false by a
factor that grows with `gam`. The same holds for any per-job `B0_q` that is not
constant across jobs: `gam * n_q` is one way to make `B0_q` large for the victim,
a per-job draw is another (rule 4 of §4.2 finds violations of (6') too). What
survives for every shape in the family is the cap, that is Theorem 4 and (7),
and the operator's promise `G` is read off that.

**Parameter rule.** To promise `excess <= G` regardless of the shape, set

    Bmax = k ( G - (3 - 2/k) L ) ,

which is what (4) and (7) need; it is usable exactly when `G > (3 - 2/k)L`, so
`G > 3L` is always safe and `G = 2L` is infeasible for `k > 2` — the boundary
the cross-domain line hit independently.

### 4.2 Numerical attack on the general statement

Revision 3's attacks (`run_wrapper.py`, `out_wrapper.txt`: 400,000 instances,
`k in {1,2,3,4}`, budgets `0..5L`, bases drawn from `{FCFS, LIFO, SJF on true
sizes, LJF on true sizes (adversarial), ordering by a random permutation of
predictions, uniform random, EDF with random deadlines, 3-class priority}`, 0
violations; `run_thmB.py`, `out_sharp_thmB.txt`: 103,057,920 (schedule,
parameter) combinations and 505,915,200 job-checks, 0 failures) cover the
constant and the relative rule. Revision 4 adds `gen_budget.py`
(`out_gen_budget.txt`), which carries its own wrapper kernel — the budget rule is
a parameter of the kernel rather than a constant — and sweeps six rules:

    0 constant | 1 age-relative, common B0 | 2 queue-length + age (gam > 0)
    3 DECREASING in time: clamp(B0 - dec*(t - a_q), 0, Bmax)
    4 per-job constant, drawn independently per job
    5 adversarial: an independent value in [0, Bmax] per (job, dispatch epoch)

all clamped into `[0, Bmax]`, every comparison exact-integer, the base policy a
tape so that every work-conserving schedule it could produce is enumerated.

| sweep | schedules | job-checks | (3) | (4) | (4) strict | Thm 1 | (6) with `B0_i` | (5) | (6') with the common `B0` |
|---|---|---|---|---|---|---|---|---|---|
| exhaustive tapes, `k<=3`, `n<=5`, 6 rules, 9 parameter settings | 44,167,680 | 216,820,800 | 0 | 0 | 0 | 0 | 0 | 0 | **99,005 failures** |
| `n = 6, 7`, `k<=3`, 1,500 tapes/shape, 6 rules, 4 settings | 17,280,000 | 112,320,000 | 0 | 0 | 0 | 0 | 0 | 0 | **22,975 failures** |
| random, `k<=5`, `n<=12`, rule drawn uniformly | 1,000,000 | 6,993,818 | 0 | 0 | 0 | 0 | 0 | 0 | **1,693 failures** |

The last three columns are applied to the three rules that have a well-defined
constant part, rules 1, 2 and 4; the failures in the last column are
Proposition 4B' and are confined to rules 2 and 4, the two whose constant part
varies between jobs. Rule 1, the hypothesis of Theorem 4B, never fails any of
them. Worst `k*excess - Bmax` observed: `28` in the random sweep, against the
ceiling `(3k-2)L` of Theorem 4C.

Two probes on what is load-bearing:

* **`budget == 0` is FCFS.** 360,000 (instance, base tape) pairs, `k <= 4`,
  `n <= 6`: the wrapper's dispatch sequence and its start times agree with FCFS
  on every one, 0 mismatches.
* **The minimum-rank tie-break.** The same wrapper serving the **maximum**-rank
  member of `E(t)` instead: 1,536,000 exhaustive-tape combinations give 112
  failures of (3), and 1,000,000 random instances with `n <= 16` give 121,918
  failures of (3) and 75,211 failures of (4). So the tie-break is not a
  convenience; it is the step `i ∉ E(t)`.

Theorem 4C's family (§6.4) was replayed through this kernel as a constant rule
(`budget == B0 == Bmax`): all eight rows of the §6.4 table reproduce exactly,
`c(k) < 3k-2` strictly on each. The general statement therefore does not disturb
the tightness result, which is what one expects, a constant budget being a member
of the class.

*One defect found in revision 3's own instrumentation.*
`sharp_kernel.sched_guardB` implements the relative term as `(en/ed)*(t - a_q)`,
that is `eta*(t - a_q)`, while `run_thmB.py`'s checks assume the note's rule
`eta*k*(t - a_q)`. The two agree at `k = 1` and differ by a factor `k` above it,
so revision 3's Theorem 4B sweep tested a budget that grows `k` times more slowly
than the one claimed: the reported 0 failures are true but are not evidence for
the stated rule at `k > 1`. `gen_budget.py` uses `en*k*(t - a_q)` over `ed` and
re-runs the check for `k <= 5` (rules 1 and 2 above), 0 failures. The kernel is
left as it is so that revision 3's logs stay reproducible.

### Theorem 5 (consistency: when the wrapper is invisible) — **proved**, one direction

(a) *Sufficient condition.* Run the base policy `A` alone on the input. **If**
`over_q(t) < budget_q(t)` for every waiting `q` at every dispatch instant `t` of
the base run, **then** the wrapped run is identical to the base run — same
dispatch sequence, same waits.

*Proof.* Induction on dispatch instants. Up to the first instant at which the
two runs could differ their completion histories are identical, hence so is
`over`, so `E(t)` is empty in the wrapped run and the wrapped run copies `A`. ∎

(a') *The converse is **false*** (referee item O1). Revision 1 stated (a) as an
"iff". Counterexample (`evidence/guard_theory_referee/out_ce.txt`, CE3): `k=1`, `a = (0,0)`, `x = (1,1)`, base
`A` = "dispatch the higher rank first", `B = 1`. The base run and the wrapped
run are both `1, 0` and are identical, yet `E(t)` is non-empty at the second
dispatch — the guard fires and happens to choose exactly what the base would
have chosen. So "the runs agree" does **not** imply "the guard never fires".
Only the direction stated in (a) is true, and it is the direction (b) and (c)
below use.

(b) *Sufficient, in terms of the base's own overtaking.* `over_q(t) <= In^A_q`
for all `t` (a completed overtaker of `q` was dispatched while `q` waited, hence
before `q` started). Therefore, for a constant budget,

    max_i In^A_i < B     ==>     guard(A,B) == A  exactly.

(c) *Sufficient, in terms of the base's own FCFS-robustness.* If `A` itself
already satisfies `excess_A[i] <= G` for all `i` on this input, then by
Theorem 2 `In^A_i <= kG + (3k-2)L`, so

    B > k G + (3k - 2) L     ==>     guard(A,B) == A  exactly.

*In words: a base policy that is already FCFS-robust never sees the guard.*
This is the statement that makes the guard safe to bolt onto a good scheduler.

*Numerical attack* (`run_consistency.py`, `out_consistency.txt`, deterministic
bases only — a randomised base is a different policy on each run and cannot be
compared): 400,000 instances. (b) 0 failures, (c) 0 failures, and with `B` one
unit *below* the threshold of (b) the run changes in 8,402 of 194,386 applicable
cases, so the threshold is at the boundary and not slack. The second referee
re-ran (b) and (c) on 20,001 exhaustive triples plus 28,922 random ones: both
hold, and in the (c) regime the guard never fires at all.

### Proposition 6 (the loss when it fires is not boundable) — **proved (negative)**

There is no multiplicative consistency statement: for every `R` there is an
instance on which the guard's mean wait exceeds the base's by a factor `> R`.

*Proof.* Take `k = 1` and the family "one job of work `L` at `t = 0`, then `m`
jobs of work `1` at `t = 0`". First, `guard(SJF, 0) = FCFS`: with `B = 0` every
waiting job has `over_q(t) >= 0 = B`, so `E(t)` is the whole waiting set and the
guard dispatches its minimum-rank member at every dispatch, which is FCFS.
FCFS's waits are `0, L, L+1, …, L+m-1`, summing to `mL + m(m-1)/2`; SJF's are
`0, 1, …, m-1` for the small jobs and `m` for the large one, summing to
`m(m-1)/2 + m`. The ratio of mean waits is therefore

    ( mL + m(m-1)/2 ) / ( m(m-1)/2 + m )  =  ( 2L + m - 1 ) / ( m + 1 ) ,

which exceeds `R` as soon as `L > (R(m+1) - m + 1)/2`. ∎

Measured (`out_rev3_items.txt`) the closed form is exact: `40.6` at
`(L,m) = (100,4)`, `20.8` at `(100,9)`, `400.6` at `(1000,4)`, `4.6` at
`(10,4)`. Revision 2 reported the `40.6` from `out_wrapper.txt` and called the
ratio unbounded without an argument. The only consistency available is the
one-directional Theorem 5.

### Proposition 7 (the guard fires only on a saturated constraint) — **proved**

The guard fires on `q` only at instants where `over_q(t) >= budget_q(t)`, and
`over_q(t) <= In_q` always. So at every firing, the constraint
`In_q <= budget_q(t)` is already violated on completed work alone.

Revision 1 continued: "hence no wrapper that enforces a work budget can defer
`q` for longer and still promise the same `G`; within `Budg`, the guard is the
least restrictive rule achieving its guarantee." That does not follow: Theorem 2
bounds `In` for any policy achieving `G`, but a different wrapper could spend
its budget on a different set of jobs and still achieve `G`, and nothing here
rules that out. The minimality claim is withdrawn and is listed as open
(§8, item 1).

---

## 5. G3 — removing assumptions

### Proposition 8 (no global size bound) — **proved**, with the correct placement

Let `Λpref(t) = max{ x_j : a_j <= t }` (a prefix maximum, defined without any
global bound), and let `Λ^Q_i` be the largest work among the at most `k-1` jobs
other than `i` that are in service under `Q` at the instant `i` starts (`0` if
none). Then for every work-conserving non-preemptive `P` and every `i`:

    -(k-1)( Λpref(a_i) + Λ^P_i )  <=  D_i  <=  (k-1)( Λpref(a_i) + Λ^F_i ).   (8)

*Proof.* Step (2) of Theorem 1 gives `rho^Q_i <= (k-1) Λ^Q_i` directly. Step (4)
uses Lemma 1' — in the repaired form — instead of Lemma 1: the jobs present at
`u^-` for the reference time `u <= a_i` arrived strictly before `u`, hence by
`a_i`, so their sizes are `<= Λpref(a_i)`. ∎

**How far `L` may be replaced by a prefix maximum (referee item O2).** Revision 1
said flatly "Theorem 1, Corollary 1.2, Theorem 2 and Theorem 4 all hold with `L`
replaced by the running prefix maximum", meaning `Λpref(a_i)`. That is false in
two of the four places. The displayed inequality (8) is correct; what it implies
depends on the direction:

* **Upward (the identity and Corollary 1.2) — `Λpref(a_i)` is enough.**
  The jobs in service under FCFS at `s^F_i` all have rank `< i`, hence arrived
  by `a_i`, so `Λ^F_i <= Λpref(a_i)` and (8) gives
  `D_i <= 2(k-1) Λpref(a_i)`.
* **The wrapper bounds of Theorem 4 — `Λpref(a_i)` is NOT enough; the right
  reading is `Λpref(s^P_i)`** (referee item RR-1; revisions 1–4 asserted
  `Λpref(a_i)` here and proved only the identity half). Theorem 4's additive
  constant is `[(2k-2)L + kL]/k`. The `(2k-2)L` comes from the identity and does
  survive with `Λpref(a_i)`. The `kL` comes from `In_i < budget + kL`, whose
  proof charges the last overtaker `j` and the at most `k-1` overtakers still in
  service beside it — all of them jobs of rank **above** `i`, which arrive
  **after** `a_i` and which `Λpref(a_i)` does not bound. They are all dispatched
  at or before `s^P_i`, hence arrived by `s^P_i`, so what the proof gives is

      In_i     <  Bmax + k * Λpref(s^P_i)
      excess_i <  Bmax/k + Λpref(s^P_i) + (2 - 2/k) * Λpref(a_i)
               <= Bmax/k + (3 - 2/k) * Λpref(s^P_i),

  and the same substitution repairs Theorem 4B's two displays.

  *Counterexample to the `Λpref(a_i)` form* (`rev5_items.py`, RR-1; this is the
  CE1/CE2 mechanism of the second referee one step later in the run). `k = 1`,
  constant budget `B = 2`, no global size bound. At `t = 0` the victim `i`
  (rank 0, `x = 1`) and `A` (rank 1, `x = 1`) arrive, so `Λpref(a_i) = 1`; the
  base prefers `A`, and `over_i(0) = 0 < 2` leaves `E(0)` empty. `A` completes
  at `t = 1`, where `over_i = 1 < 2`, so `E(1)` is empty as well; a job `Z` of
  rank 2 and work `M` arrives at `t = 1` and the base dispatches it.

  | `M` | `In_0` | `B + k Λpref(a_i)` | `excess_0` | `B/k + (3-2/k) Λpref(a_i)` | `B + k Λpref(s^P_i)` |
  |---|---|---|---|---|---|
  | 1 | 2 | 3 | 2 | 3 | 3 |
  | 2 | 3 | 3 | 3 | 3 | 4 |
  | 3 | 4 | 3 | 4 | 3 | 5 |
  | 10 | 11 | 3 | 11 | 3 | 12 |
  | 1000 | 1001 | 3 | 1001 | 3 | 1002 |

  Both `Λpref(a_i)` forms fail from `M = 2` on and the failure is unbounded,
  while the `Λpref(s^P_i)` forms hold in every row. Brute force without a global
  size bound (Pareto(0.7) integer sizes, no cap, `k = 1..4`, 1,600 instances,
  2,074 job-checks with at least one overtaker): 156 failures of the `In` form
  and 126 of the additive form under `Λpref(a_i)`, **0** failures of either
  under `Λpref(s^P_i)` (`out_rev5_items.txt`, RR-1).
* **Downward (the lower half of Theorem 1) — it is not.** `Λ^P_i` is a maximum
  over jobs in service under `P` at `s^P_i`, which may be overtakers that
  arrived after `a_i`. The right prefix maximum is at `max(s^P_i, s^F_i)`.
* **Theorem 2 — the prefix maximum must be taken at `s^F_i + G`.** Lemma 2's
  window reaches `s^F_i + G`, and the "last job on each server" that contributes
  `L` there can be any job dispatched inside the window.

*Counterexample* (`evidence/guard_theory_referee/out_ce.txt`, CE1/CE2, the second referee). `k=2`, jobs (in
rank order) `0:(a=0,x=1) 1:(a=0,x=1) 2:(a=0,x=1) 3:(a=1,x=M)`; `P` dispatches
`1,2` at `t=0` and then the huge job `3` before `0` at `t=1`. Then
`Λpref(a_0) = 1` for every `M`, yet

| `M` | `D_0` | `2(k-1)Λpref(a_0)` | `In_0` | `kG + (3k-2)Λpref(a_0)` |
|---|---|---|---|---|
| 3 | -3 | 2 | 5 | 6 |
| 5 | -5 | 2 | 7 | 6 |
| 10 | -10 | 2 | 12 | 6 |
| 100 | -100 | 2 | 102 | 6 |
| 1000 | -1000 | 2 | 1002 | 6 |

so the prefix-at-`a_i` form of the lower direction fails for every `M >= 3`, and
the prefix-at-`a_i` form of Theorem 2 fails from `M = 5` on. Both are repaired
by moving the prefix maximum to `max(s^P_i, s^F_i)` and to `s^F_i + G`
respectively, and with `L` in place of the prefix maximum both hold in every
row.

*The prefix maximum cannot be replaced by anything local to `i`'s wait.*
`ce_local_L.py` / `out_ce_local_L.txt` builds, for each `M`, a `k=2` instance in
which every job except one has size `1`, the one job of size `M` is finished
under both policies long before `i` arrives, and yet the slack for `i` is `M/2`:

| M | slack `D` | largest job in service near `i` | localised bound `(k-1)(Λ^P+Λ^F)` |
|---|---|---|---|
| 10 | 4 | 1 | 2 |
| 20 | 10 | 1 | 2 |
| 40 | 20 | 1 | 2 |
| 80 | 40 | 1 | 2 |
| 160 | 80 | 1 | 2 |

The mechanism: the big job lets `P` idle a server for `Θ(M)` while FCFS stays
saturated; that creates a workload gap of `Θ(M)`, and a saturating arrival
stream afterwards freezes it. The correct refinement is Lemma 1': the constant
is the maximum size among the jobs present just before the last instant `<= a_i`
at which fewer than `k` of the servers were busy — the current all-servers-busy
epoch, not `i`'s wait. (Under work conservation "fewer than `k` servers busy"
and "fewer than `k` jobs in the system" coincide; the repaired Lemma 1' states
it in terms of the servers because that is what the left limit reads cleanly.)

Checked on 1,199,111 job-instances with Pareto(0.7) sizes and no cap: 0 failures
of the corrected statements (`out_assumptions.txt`); the second referee adds
599,400 job-checks with Pareto(0.6/0.7/1.0) unbounded sizes.

### Proposition 9 (servers of different speeds) — **proved**

Servers have speeds `v_1..v_k`; a job of work `x` on server `m` occupies it for
`x/v_m`. Let `V = v_1 + ... + v_k`. Then for every work-conserving non-preemptive
`P` and every `i`:

    | V ( W_P[i] - W_FCFS[i] ) - ( In_i - Out_i ) |  <=  2(k-1) L,

and the guard satisfies `W_guard[i] <= W_FCFS[i] + B/V + (3k-2)L/V`.

**Server selection** (referee item O11). With unequal speeds the model needs one
more rule: when several servers are free at a dispatch instant, which one takes
the job? Fix any rule — fastest-free, slowest-free, lowest index, random — and
apply *the same* rule under `P` and under FCFS. The statement does not depend on
which rule is chosen, because the proof uses only two facts about the servers:
(i) while every server is busy the system drains at the total rate `V`, and
(ii) at most `k-1` jobs other than `i` are in service at `s_i`, each with
remaining work `<= L`. Neither mentions the assignment.

*Proof.* Identical to Theorem 1. In step (1) the work executed while all servers
are busy over a window of length `W` is `V*W`, not `k*W`. Step (2) is unchanged:
at most `k-1` other jobs are in service, each with remaining work `<= L`. Step
(3) is unchanged. In step (4), Lemma 1 survives verbatim: if `U_A(t) > (k-1)L`
then `A` has at least `k` jobs, so all of `A`'s servers are busy and `A` drains
at the maximal rate `V >= ` `B`'s rate. ∎

**The budget is divided by total capacity, not by the server count.** `B/k`
becomes `B/V`; with identical servers `V = k` and the old form is recovered.
Checked on 150,000 instances (`k` up to 4, speeds in `1..4`, both
server-selection rules, exact integer arithmetic after scaling by `lcm(v)`): 0
failures; the second referee adds 532,396 job-checks over four combinations of
the selection rule, and reports the result robust to it.

### Proposition 10 (non-work-conserving pauses, vacations, setup) — **partly disproved**

Let `Γ^P_i` be the total server-idle time accumulated while at least one job
waited, during `[a_i, s^P_i)`. Step (1) of Theorem 1 becomes

    k W_P[i] = R^P_i + In_i - Out_i - rho^P_i + Γ^P_i,

and Lemma 1 becomes `U_P(t) - U_F(t) <= (k-1)L + Γ^P(t)` where `Γ^P(t)` is `P`'s
cumulative forced idleness up to `t`. So the identity survives with an explicit
idleness term, and **nothing survives without bounding cumulative idleness**:

*Counterexample.* `k=1`; pause the server for `T` while `i` waits.
`In_i = Out_i = 0`, and `excess = T`, unbounded. Numerically, with random pause
windows the plain bound `2(k-1)L` is violated in 7,427 of 501,458 job-checks,
while the crude allowance `2k * (total pause time)` covers all of them
(`out_assumptions.txt`).

*What does survive.* **Setup times**: if a setup of length `σ` is paid before
every service by both policies, absorb it into the job
(`x'_j = x_j + σ <= L + σ`). The model is then unchanged, so every result above
holds with `L -> L + σ` and work measured in `x + σ`. Checked on 300,214
job-checks: 0 failures.

### Proposition 11 (release constraints and a timeout kill) — **mixed**

(a) *Bounded preemption / timeout kill at `L`* — **proved**. If a running job is
killed at elapsed service `L` by the same rule in both runs, the executed work
`min(x_j, L)` is the same in both. Relabel `x_j := min(x_j, L)`; the model is
unchanged, so every result holds verbatim, now *without* any assumption on the
raw sizes.

**Read every currency in executed work** (referee item O10). Under the relabelling,
`In_i`, `Out_i`, `over_q(t)` and `L` are all in **executed (truncated)** work,
`min(x_j, L)`, not raw work. The relabelled statement is then a tautological
corollary of the untruncated one; read in raw work it is false, because a killed
job contributes `x_j > L` to `In_i` while only `L` of it is ever executed.
The distinction matters in practice: `guardkern.py` charges `over` at completion
with the value the runner reports, which is the truncated one, so the code is
already on the right side of this.

Checked on 401,723 job-checks with Pareto(0.6) raw sizes: 0 failures; the second
referee adds 180,085 job-checks and confirms both halves of the statement
(tautological in executed work, false in raw work).

(b) *Release times `r_j > a_j` with rank still keyed on `a_j`* — **disproved**.
Counterexample, `k=1`: job 0 with `a=0, r=10, x=1`; job 1 with `a=1, r=1, x=1`.
Every work-conserving policy runs job 1 at `t=1` and job 0 at `t=10`, so all
policies coincide and `excess = 0` for both jobs. But job 1 has the higher rank
and is dispatched first, so `In_0 = 1`, `Out_0 = 0`, and Theorem 1 at `k=1`
would predict a difference of `1`. The slack is exactly the forced idle time on
`[0,1)` — this is Proposition 10 in disguise.

*Fix* — **proved**: rank by release, `rank = (r_j, index)`, and read `a_j` as
`r_j`. The proofs use nothing about `a_j` except "no server idles while `i` is
eligible and waiting", so with that relabelling every result holds verbatim.

### Proposition 12 (batch arrivals and zero-length jobs) — **proved**

Simultaneous arrivals are already in the model (rank is `(arrival, index)`), and
`x_j = 0` is allowed: Lemma 1 needs "`U > (k-1)L` implies at least `k` jobs
present", which zero-length jobs can only help; step (2) of Theorem 1 counts jobs
in service, and a zero-length job completes at its dispatch instant so it never
occupies a server at `s^P_i`. Confirmed on 300,000 instances with all arrivals
tied and 779,751 zero-length jobs, 1,798,465 job-checks, 0 violations; this
revision's exhaustive and random sweeps include zero-length jobs throughout.

---

## 6. G4 — lower bounds and tightness

### 6.1 Theorem 3 (the constant of Theorem 1 is optimal) — **proved**

For every `k >= 2` and every `epsilon > 0` there are inputs and work-conserving
policies `P` and jobs `i` with

    D_i  >  2(k-1)L - epsilon      and, on another input,   D_i  <  -2(k-1)L + epsilon.

Hence `sup |D_i| = 2(k-1)L` and the constant cannot be lowered. The inequality
of Theorem 1 is moreover **strict** — `|D_i| < 2(k-1)L` on every instance — so
the supremum is never attained. The same holds for the normalised form: the
supremum of `|W_P[i] - W_FCFS[i] - (In_i - Out_i)/k|` is exactly `(2 - 2/k)L`,
and is not attained.

*Proof of the strictness.* Step (4) of Theorem 1 bounds `|R^P_i - R^F_i|` by
Lemma 1 applied at `t = a_i`; Lemma 1s sharpens that to
`|R^P_i - R^F_i| < (k-1)L` whenever `L > 0`. With `0 <= rho^P_i, rho^F_i <=
(k-1)L` from step (2), the two directions of step (5) give `|D_i| < 2(k-1)L`
strictly. (Revision 2 asserted strictness without this step; see Lemma 1s.)

*Proof, upward direction.* Run the cascade of Lemma 1'' for `m` rounds with
`L = k^m`, reaching time `T_m = mL` with FCFS empty and idle, and `P` holding
`k-1` jobs whose remaining work totals `rho_m = (k-1)L(1 - ((k-1)/k)^m)`. At
`T_m` inject, in index order:

* `k-1` jobs of work `L` (ranks below the victim),
* the victim `i`, of work `L`,
* `N` jobs of work `1` (ranks above the victim), with `N > 2kL`,

and let `P` continue as the static-priority policy "the `k-1` new big jobs
first, then the unit jobs, then `i`".

*What FCFS does.* At `T_m` all `k` of its servers are free and its waiting set
is, in rank order, the `k-1` new bigs, then `i`, then the units. It dispatches
the `k-1` bigs and then `i`, all in the phase at `T_m`. So `W_FCFS[i] = 0`, and
the `k-1` bigs are dispatched strictly before `i` in FCFS's sequence and are in
service at `s^F_i = T_m` with their full work: `rho^F_i = (k-1)L`, the maximum
step (2) allows. Also `R^F_i = (k-1)L`.

*What `P` does.* At `T_m`, `P` has one free server and takes a new big; when its
`k-1` cascade leftovers finish — all at the same instant, `T_m + f` with
`f = rho_m/(k-1) < L` — their servers take the remaining new bigs and then
units. `i` waits while any unit waits. The units are executed at rate at most
`k`, so they are not exhausted before `T_m + N/k`, and `N > 2kL > k(f + L)`
makes that later than `T_m + f + L`, by which time every new big has completed.
Hence `i` is dispatched after all `k-1` new bigs have finished, and at `s^P_i`
the other `k-1` servers hold unit jobs, so
`0 <= rho^P_i <= k-1`. And `R^P_i = rho_m + (k-1)L`, since the cascade leftovers
and the new bigs all have rank `< i` and the new bigs are untouched at `a_i`.

*Putting it together.* `R^P_i - R^F_i = rho_m` and

    D_i = (R^P_i - R^F_i) - rho^P_i + rho^F_i
        >= rho_m + (k-1)L - (k-1)
        =  2(k-1)L - (k-1)L((k-1)/k)^m - (k-1).

Both error terms are `o(L)` as `m -> infinity` with `L = k^m`, so `D_i/L ->
2(k-1)`.

*Proof, downward direction (the mirror).* Run the mirrored cascade: inject the
`L` unit jobs **first** in index order and the `k-1` bigs after, and let `P` be
"bigs before units". Lemma 1'''s induction runs with the two policies' roles
exchanged: at `T_j`, `P` is empty and idle while FCFS holds `k-1` jobs each with
remaining `rho_j/(k-1)`. At `T_m` inject, in index order:

* one **filler** job of work `f = rho_m/(k-1)` (rank below the victim),
* the victim `i`, of work `L-1`,
* `k-1` jobs of work `L` (ranks above the victim),

with `P` = "the `k-1` new bigs first, then `i`, then the filler".

FCFS at `T_m` has `k-1` servers busy with leftovers, each with exactly `f` left,
and one free server, which takes the filler — the lowest-ranked waiting job —
which also has work `f`. So all `k` of FCFS's servers complete simultaneously at
`T_m + f`, and FCFS then dispatches `i`, the lowest-ranked waiting job, with
nothing else dispatched in that phase before it. Hence `W_FCFS[i] = f` and
`rho^F_i = 0`.

`P` at `T_m` is empty with `k` free servers, and dispatches the `k-1` new bigs
and then `i`, all at `T_m`: `W_P[i] = 0`, `In_i = (k-1)L` (the new bigs are
same-phase overtakers), `rho^P_i = (k-1)L`, and the filler, of rank `< i`, is
dispatched after `i`, so `Out_i = f`. Therefore

    D_i = k(0 - f) - ((k-1)L - f) = -(k-1)f - (k-1)L = -rho_m - (k-1)L
        -> -2(k-1)L .                                                           ∎

**Verification** (`family_tight.py`, `out_sharp_family.txt`). Both families are
built and simulated by `sim_core.py`, in exact integers, and every intermediate
quantity of the proof is asserted job by job (`D_i = R^P-R^F-rho^P+rho^F`):

| `k` | `L` | `m` | `n` (upper / lower) | `D_i / L` (upper) | `D_i / L` (lower) | `2(k-1)` |
|---|---|---|---|---|---|---|
| 2 | 64 | 3 | 454 / 198 | 119/64 = 1.859 | -15/8 = -1.875 | 2 |
| 2 | 64 | 6 | 649 / 393 | 127/64 = 1.984 | -127/64 = -1.984 | 2 |
| 3 | 81 | 4 | 822 / 336 | 290/81 = 3.580 | -292/81 = -3.605 | 4 |
| 4 | 64 | 3 | 718 / 206 | 303/64 = 4.734 | -303/64 = -4.734 | 6 |

The upper family's `rho^F` is `(k-1)L` exactly in every row and its `rho^P` is
at most `k-1` time units; the lower family's `rho^P` is `(k-1)L` exactly and its
`rho^F` is `0`. The measured gap `R^P-R^F` matches `(k-1)L(1-((k-1)/k)^m)`
exactly in every row, which is the content of Lemma 1''.

### 6.2 What this settles, and what it overturns — the two directions separately

Both referees conjectured that the true constant of Theorem 1 is `(k-1)L` — half
of what is proved — on the strength of very large searches that never exceeded
`(k-1)L` by more than one time unit. **That conjecture is false.** Theorem 3
refutes it with margin: at `k=2` the family reaches `1.984 L` against the
conjectured `1 L`; at `k=3`, `3.605 L` against `2 L`; at `k=4`, `4.734 L`
against `3 L`. Revision 1's own conjecture ("the constant of Theorem 1 lies
between roughly `0.75 k L` and `2(k-1)L`") is likewise superseded: the answer is
the upper end.

Revision 2 stopped there, and stated the refutation symmetrically in both
directions. **The two directions are not alike, and only the upward one is a
statement about delay** (referee item R3-4). Measured on the two families
(`out_rev3_items.txt`):

| direction | `D_i/L` | `De_i/L` (executed work) | victim's real excess | share of `\|D_i\|` that is same-phase `In` |
|---|---|---|---|---|
| upward, `k=2, m=6` | `+1.9844` | `+1.9844` | `+3.000 L` | `0.00%` |
| upward, `k=3, m=4` | `+3.5802` | `+3.6049` | `+3.198 L` | `0.69%` |
| upward, `k=4, m=3` | `+4.7344` | `+4.7344` | `+3.188 L` | `0.00%` |
| downward, `k=2, m=6` | `-1.9844` | `-0.9844` | `-0.984 L` | `50.39%` |
| downward, `k=3, m=4` | `-3.6049` | `-1.6049` | `-0.802 L` | `55.48%` |
| downward, `k=4, m=3` | `-4.7344` | `-1.7344` | `-0.578 L` | `63.37%` |

*Upward the extremal value is real delay.* The victim's own excess is about
`+3L`, essentially none of `In_i` is same-phase, and the executed-work
convention reaches the same `2(k-1)L`. The victim genuinely waits `(2-2/k)L`
longer than `(In_i - Out_i)/k` predicts.

*Downward it is half a convention.* In the mirror family `In_i = (k-1)L`
consists **entirely** of overtakers dispatched in the victim's own phase, which
execute nothing during `[a_i, s^P_i)`; that is half of `|D_i|` and more. Under
the executed-work convention of Remark 1.3 the downward constant of the mirror
family is only `(k-1)L` — `-63/64 L` at `k=2,m=6`, `-130/81 L` at `k=3,m=4`,
`-111/64 L` at `k=4,m=3`. And the victim's real excess there is **negative**: it
starts *earlier* under `P` than under FCFS. So the honest statement is

* in the sequence convention (the main one), `sup |D_i| = 2(k-1)L` in both
  directions, not attained;
* in the executed-work convention, the upward supremum is the same `2(k-1)L`,
  while the best downward witness known is `(k-1)L` and the true downward
  constant for `De` is open (§8, item 2);
* the downward witness is not a statement about a job being delayed; it is a
  statement about how the sequence convention charges same-phase dispatches.

Remark 1.3 conceded the second point in passing; §6.2 and the §0 table of
revision 2 did not, and now do.

### 6.3 Why the searches missed it (a methodological note)

The extremal family needs `m` rounds to come within `((k-1)/k)^m` of the ceiling,
and each round needs `k-1` big jobs plus `L` units, so witnessing `1.98 L` at
`k=2` takes `n = 648` jobs with `L = 64`. Every search in this project and in
both referee directories — exhaustive to `n <= 7`, random to `n <= 14`,
annealing over `(arrivals, sizes, tape, B)` — lives far below that. The evidence
for it:

* This revision's hill-climbing (`run_sharp.py scan` / `deep`, `n <= 20`) finds
  `max|D|/L` of `1.75` at `k=2`, `2.75` at `k=3`, `3.50` at `k=4` (and, in the
  executed convention, `1.75 / 2.81 / 4.00`), all already
  above the conjectured `(k-1)` and all far below `2(k-1)`; and the ratio it
  reaches *falls* as `L` grows past 16, which is the signature of a search
  running out of power, not of a ceiling.
* The isolated Lemma 1 slack (`run_sharp.py parts`, `out_sharp_parts.txt`)
  saturates at `0.81 L` for `k=2` and `1.28 L` for `k=5` against the true
  supremum `(k-1)L`, again because the cascade is out of reach.
* The decomposition of every worst witness found by search
  (`out_sharp_parts.txt`, part B) has `rho^F = (k-1)L` **exactly** and
  `rho^P = 0` — i.e. search saturates the term that is attained and fails only
  on the term that requires the cascade. That is what pointed at the
  construction.

The general lesson, worth stating because it applies to the rest of this note:
random and small-`n` exhaustive search settle *correctness* (no counterexample
in `10^8` instances is strong evidence) but are nearly worthless for *tightness*
when the extremal family is a geometric cascade.

### Proposition 13 (`B/k` is tight) — **proved**

On the family below the guard's excess is exactly `ceil(B/k)`, so the `B/k` term
of Theorem 4 is attained whenever `k` divides `B` and cannot be improved.

*The family.* At `t = 0` there arrive, in rank order: `k` jobs of work `L`
(ranks `0..k-1`), the victim `i` (rank `k`, work `1`), and at least `B + k` jobs
of work `1` (ranks `> k`). All `k` servers are free. Fix any budget `B >= 0` and
any base policy that never chooses `i` while another job waits — for instance
the static priority "the `k` big jobs, then the unit overtakers, then `i`".

*Proof.* Under FCFS the `k` big jobs are dispatched in the phase at `t = 0` and
fill every server, so `i` waits until the first completion: `W_FCFS[i] = L`.

Under the guard, consider first `B = 0`. Then `E(t)` contains every waiting job
at every dispatch (`over_q(t) >= 0 = B`), so the guard is FCFS and
`excess = 0 = ceil(B/k)`. For `B > 0`: at `t = 0` no rank `> q` job has
completed, so `over_q(0) = 0 < B` for every waiting `q`, `E(0)` is empty, and
the base fills the `k` servers with the `k` big jobs. They all complete at
`t = L`, and `over_i(L) = 0` still, because every completed job has rank `< i`.
From `t = L` on, all `k` servers are free at each integer instant, `E` is empty
as long as `over_i < B`, and the base dispatches `k` unit overtakers, which
complete one time unit later. Hence `over_i(L + r) = rk` for
`r = 0, 1, 2, …`, and the first instant at which `over_i >= B` is
`L + ceil(B/k)`. At that instant `i` is the minimum-rank member of `E` — the
waiting jobs of rank `> i` have no completed job of still higher rank ahead of
them, so `over_q = 0 < B` for them — and the guard dispatches it. Therefore
`W_guard[i] = L + ceil(B/k)` and `excess = ceil(B/k)`. ∎

Revision 2 gave this family and the measurement but no argument; the `ceil` is
the part that was missing, and the measured configurations all had `k | B`.
Measured (`out_tightness.txt`, G4.2, reproduced independently by the second
referee, `evidence/guard_theory_referee/out_probes.txt` P3) on 24
configurations (`k in {1,2,3,4}`, `L in {4,16}`, `B in {0, 2kL, 8kL}`)

    excess  ==  B/k     exactly,     excess - B/k == 0.00

and re-measured in `out_rev3_items.txt` including budgets with `k` not dividing
`B` (`B = 3kL+1` and `B = 5`), where `excess == ceil(B/k)` in every
configuration.

### Proposition 14 (an additive `Ω(L)` is unavoidable; at `k=1` the bound is a supremum) — **proved**

Let `P` be any non-preemptive work-conserving policy that observes a job's work
only at its completion. Consider an empty system into which, at `t=0`, the
victim `i` (rank 0) and `k` further jobs (ranks `1..k`) arrive together, all of
work `L`. All `k` servers are free. FCFS starts `i` at once, so
`W_FCFS[i] = 0`. If `P` fills all `k` servers with the higher-ranked jobs —
which work conservation permits, and which `P` cannot be dissuaded from because
it has observed no service time yet — then `i` waits until the first completion,
so `W_P[i] = L` and `excess = L`.

Since the guard with any `B > 0` has `over_i(0) = 0 < B` and therefore does not
fire at `t=0`, **every wrapper whose budget is positive at the first dispatch
epoch admits instances with excess `>= L`, for every `k`**. Hence the additive
constant of Theorem 4 is at least `L`.

**The hypothesis, exactly** (referee item RR-2). The quantifier matters in two
directions, and the paper draft lost it in both.

*It cannot be dropped.* Stated over policies rather than wrappers — "every
non-preemptive work-conserving policy that reads a service time only at
completion admits excess `>= L`" — the proposition is **false**: FCFS is such a
policy and has excess `0` on every input, as does every rank-ordered policy.
What the argument above establishes is that work conservation *permits* the
`k` servers to be filled, not that a policy is forced to fill them; the force
comes from the guard's not firing, which is a statement about the budget rule.

*It is not necessary either.* A rule that is `0` at the first dispatch epoch but
positive later — the age-relative shape with `B0 = 0` and `eta > 0`, say — falls
to the same instance behind a saturating prefix. Let `k` jobs of work `L` arrive
at `t = 0` (the wrapper is FCFS there, every budget being `0` at age `0`), the
victim `i` at `t = 1`, and `k` further jobs at `t = L-1`. Up to `t = L` the
victim's wait is what FCFS gives it; at `t = L` its budget is positive because
it has aged, the guard does not fire, and the base fills every server with the
`k` newcomers. Measured at `k = 1,2,3` and `eta in {1/2, 1/10}`: `W_FCFS = 9`,
`W_P = 19`, excess `= L = 10` in every row (`out_rev5_items.txt`, RR-2(c)).

*What is left over is degenerate.* Suppose the rule gives budget `0` to a job
whenever no completed work has overtaken it, i.e. `budget_q(t) = 0` whenever
`over_q(t) = 0`. Then the wrapper **is FCFS**. By induction on dispatches: if
nothing has been overtaken so far, then `over_q(t) = 0` for every waiting `q`,
so the lowest-ranked waiting job `h` has `over_h(t) = 0 = budget_h(t)`, hence
`h in E(t)`; `h` is the minimum-rank waiting job, hence the minimum-rank member
of `E(t)`, hence the one dispatched. So no job is ever overtaken. Checked on 600
random instances at `k = 1..4`: 0 disagreements with the FCFS dispatch order
(`out_rev5_items.txt`, RR-2(d)).

**The base policy is existentially quantified** (second referee round, R2-1; added
2026-09-21). "Every wrapper … admits instances" above means: for every such budget
rule there are a base policy `A` and an input. It is false for every `A`: the guard
run around FCFS is FCFS whatever the budget. For a prediction-ranked base policy
(SPJF-E) the adversary needs only the predictions — give the victim the largest one.
So what is excluded is a promise `G < L` that holds around every base policy, or
around one prediction-ranked policy under arbitrary predictions, which is the
generality in which Theorem 4 is stated.

*The three shapes are exhausted.* With `budget = min(B0 + gamma*n_q + eta*k*(t-a_q), Bmax)`:
`Bmax = 0` or `B0 = gamma = eta = 0` gives budget `0` and FCFS; `B0 > 0` is the
proposition; `B0 = 0 < eta` is the saturating prefix; and `B0 = eta = 0 < gamma` falls
to `k+2` jobs of work `L` arriving together at `t = 0`: the first has `n_q = 0`, budget
`0`, and is released at once; every other job has positive budget and `over = 0`, so a
base that prefers the highest ranks passes over the rank-1 job at `t = 0` when `k >= 2`
(FCFS starts it at `0`) and at `t = L` when `k = 1` (FCFS starts it at `L`, the wrapper
at `2L`); its excess is `L`. Checked by `r2_floor_queue_shape.py` at `k = 1,2,3,4,8`,
`L in {10,60}` and three `(gamma, Bmax)` pairs: rank-1 excess `= L` in 30 of 30
configurations (`out_r2_floor_queue_shape.txt`).

So the correct reading is: a wrapper of this family either never overtakes
anything, or admits instances with excess `>= L`; and the clean sufficient
condition, the one the proof above uses and the one every rule in the paper
satisfies, is a budget positive at the first dispatch epoch.

**At `k = 1` the bound is exactly `B + L`, as a supremum that is never attained**
(referee item O3, and item D5). Theorem 4 proves `In_i < B + kL` *strictly*, so
at `k=1` it gives `excess < B + L` strictly.

*The approaching family* (referee item R3-7; revision 2 asserted "for every
`epsilon > 0` there are instances" and offered only measurements). Fix `L`, a
budget `B`, and a granularity `g` dividing `B` with `0 < g <= L`. Take `k = 1`
and, at `t = 0`, the victim `i` of rank `0`, then `B/g - 1` jobs of work `g`,
then one job of work `L`; let the base policy dispatch the `g`-jobs first, then
the `L`-job, and never `i`. FCFS starts `i` at once, so `W_FCFS[i] = 0`. Under
the guard, after `r` of the `g`-jobs have completed `over_i = rg`, which stays
below `B` for `r <= B/g - 1`; at the last such instant `over_i = B - g < B`, the
guard does not fire, and the base dispatches the job of work `L`. When it
completes, `over_i = B - g + L >= B` and the guard releases `i`. Hence

    excess  =  B - g + L ,    excess - B  =  L - g ,

which approaches `L` as `g -> 0` and never reaches it. Verified exactly
(`out_rev3_items.txt`): `(L,B,g) = (100,40,1)` gives `excess - B = 99`,
`(64,32,1)` gives `63`, `(16,8,1)` gives `15`, `(64,32,4)` gives `60`,
`(100,60,5)` gives `95`.

Revision 1 said the project's
single-server measurements "equal `B + L` on the nose at `B = 120, 600`", which
is wrong in the direction that matters: the logs show `88.84 / 179.25 / 658.25`
seconds against `B + L` of `90 / 180 / 660` at `L = 60` — strictly below, every
time. The second referee's probe P2 makes the pattern exact: in integer units
with budget `B`, `sup(excess - B) = L - 1` for `L in {2,3,5,9,20}`, i.e. the
supremum `L` is approached to within one time unit and never reached. This
revision's own search agrees: `15/16 L` at `k=1, L=16`
(`out_sharp_wrap.txt`).

So the correct statement is: `sup_instances (excess - B) = L` at `k = 1`, the
supremum is not attained, and the additive constant of Theorem 4 is optimal
at `k = 1`.

### 6.4 The wrapper's additive constant for `k >= 2` — **proved optimal**

**Units first** (referee items O4/O5/O6 and item D4). Two different numbers have
been circulating and they are the same statement in different units:

    c(k) := sup over instances and base policies of  ( k*excess_guard[i] - B ) / L
    additive constant on the WAIT  =  c(k) / k,

because Theorem 4 reads `excess <= B/k + (c(k)/k) L`. Theorem 4 proves
`c(k) <= 3k - 2`, i.e. a wait-additive of `(3 - 2/k) L < 3L`. **The
wait-additive stays below `3L` for every `k`; only `c(k)` grows linearly.**
Revision 1's conjecture that "the true additive constant of Theorem 4 is
`Θ(kL)`" was a units error: it described `c(k)`, not the constant in the bound
on the wait, and it is withdrawn. Theorem 4C below shows that both of these
bounds are exact — `c(k) = 3k-2` and the wait-additive is `(3-2/k)L` — so the
wait-additive is bounded but not flat: it increases from `1L` at `k=1` towards
`3L`.

### Theorem 4C (Theorem 4 is tight for every `k`) — **proved**

For every `k >= 2` and every `epsilon > 0` there are inputs, base policies and
budgets `B` on which the guard's victim satisfies

    ( k * excess_guard[i] - B ) / L  >  3k - 2 - epsilon ,

and by Theorem 4 together with the strictness of Theorem 3 the quantity is
always `< 3k - 2`. Hence

    c(k)  =  sup ( k * excess_guard[i] - B ) / L  =  3k - 2   exactly,

a supremum that is never attained, and equivalently

    W_guard[i]  <  W_FCFS[i] + B/k + (3 - 2/k) L

is optimal: the additive constant `(3 - 2/k)L` on the wait cannot be lowered for
any `k`, and it **grows** in `k` — `1L, 2L, 2.33L, 2.5L, 2.6L, 2.67L, … -> 3L`.

*The family* (the third referee's, item R3-1; rebuilt here from its description
and re-measured with `sharp_kernel.py`). Fix `k >= 2`, `m >= 1`, `L = k^m`, and
write `f = L(1 - ((k-1)/k)^m)`, so that `rho_m = (k-1)f`. Run the cascade of
Lemma 1'' for `m` rounds, reaching `T_m = mL` with FCFS empty and idle and `P`
holding `k-1` jobs in service, each with exactly `f` of work left and one server
free. At `T_m` inject, in index (rank) order, all arriving at `T_m`:

* `k-1` **new bigs** of work `L` (ranks below the victim),
* the **victim** `i`, of work `L`,
* one **sync** overtaker of work `f`,
* one **pre** overtaker of work `L`,
* `k` **final** overtakers of work `L`.

Set the budget to `B = f + L + 1` and let the base policy be the static priority
"cascade units, then sync, then the new bigs and pre, then the finals, and the
victim last".

*Proof.* **FCFS.** At `T_m` FCFS is empty with all `k` servers free, and its
waiting set in rank order is the `k-1` new bigs, then `i`, then the overtakers.
It dispatches the `k-1` new bigs and then `i`, all in the phase at `T_m`. So
`W_FCFS[i] = 0`, and the `k-1` new bigs are in service at `s^F_i = T_m` with
their full work: `rho^F_i = (k-1)L`.

**The guard never fires before `T_m`.** Inside round `j` of the cascade the only
waiting jobs of interest are that round's bigs, whose higher-ranked jobs are the
`L` units of round `j` and everything in later rounds; later rounds have not
arrived. Over `[T_j, T_j + tau_j]` the `k` servers execute `k tau_j = rho_j + L`
units of work, of which `rho_j` is the previous round's leftovers, so at most
`L` of *unit* work can have completed. Hence `over_q(t) <= L < B` for every
waiting `q` at every dispatch instant of the cascade, `E(t)` is empty, and the
guarded run copies the base — which is the cascade of Lemma 1''.

**The finale under the guard.** At `T_m` one server is free; `over_q(T_m) = 0`
for every waiting `q`, so the base chooses, and it takes the sync overtaker. The
`k-1` leftovers have exactly `f` left and the sync overtaker has work `f`, so
all `k` servers free **simultaneously** at `T_m + f`. There
`over_i = f` (only the sync overtaker, of rank `> i`, has completed) and
`f < B`, and no other waiting job has any completed higher-ranked job either, so
`E` is empty and the base fills all `k` servers with the `k-1` new bigs and pre.
They all have work `L` and complete simultaneously at `T_m + f + L`, where

    over_i  =  f + L  =  B - 1  <  B ,

because only sync and pre have rank `> i` among the completed jobs. So `E` is
still empty, the base fills all `k` servers with the `k` finals, and they
complete at `T_m + f + 2L`, at which instant `over_i = B - 1 + kL >= B`. The
guard fires, `i` is the minimum-rank member of `E`, and it is dispatched with
every server free, so `rho^P_i = 0`. Exactly:

    W_guard[i] = f + 2L,   In_i = B - 1 + kL,   Out_i = 0,
    D_i = k(f + 2L) - (B - 1 + kL) = (k-1) f + (k-1) L = rho_m + (k-1)L,

and therefore

    c  =  ( k * excess - B ) / L
       =  ( k(f + 2L) - (f + L + 1) ) / L
       =  ( (k-1) f + (2k-1) L - 1 ) / L .

As `m -> infinity` with `L = k^m`, `f/L = 1 - ((k-1)/k)^m -> 1` and `1/L -> 0`,
so `c -> (k-1) + (2k-1) = 3k - 2`.

*Non-attainment.* `c < 3k-2` on every instance, by Theorem 4 alone:
`k * excess <= In_i - Out_i + 2(k-1)L <= In_i + 2(k-1)L < B + kL + 2(k-1)L =
B + (3k-2)L`, the last step being the strict inequality (3). (Theorem 3's
strictness gives the same conclusion through `D_i < 2(k-1)L`; either suffices.)
∎

*Measured* (`wrapper_tight.py`, `out_wrapper_tight.txt`), with this directory's
own numba kernel, exact integers, and the closed form asserted row by row:

| `k` | `L` | `m` | `n` | `B` | excess | `c(k)` measured | rev. 2's best search | `3k-2` |
|---|---|---|---|---|---|---|---|---|
| 2 | 64 | 6 | 396 | 128 | 191 | `127/32 = 3.9688` | 3.4444 | 4 |
| 2 | 128 | 7 | 909 | 256 | 383 | `255/64 = 3.9844` | 3.4444 | 4 |
| 3 | 81 | 4 | 340 | 147 | 227 | `178/27 = 6.5926` | 5.3125 | 7 |
| 3 | 243 | 5 | 1233 | 455 | 697 | `1636/243 = 6.7325` | 5.3125 | 7 |
| 4 | 64 | 3 | 211 | 102 | 165 | `279/32 = 8.7188` | 6.9375 | 10 |
| 4 | 256 | 4 | 1046 | 432 | 687 | `579/64 = 9.0469` | 6.9375 | 10 |
| 5 | 125 | 3 | 399 | 187 | 311 | `1368/125 = 10.9440` | 8.6875 | 13 |
| 6 | 216 | 3 | 677 | 308 | 523 | `1415/108 = 13.1019` | 10.5000 | 16 |

**Is the excess real?** Yes, and this was worth checking, because Remark 1.0
shows how easy it is to manufacture a large `D_i` out of same-phase
bookkeeping. On every row of the table the same-phase share of `In_i` is **0**:
every overtaker is dispatched at a strictly earlier instant than the victim and
has *completed* before it starts, so `In_i = Ine_i` and the executed-work
convention gives the same number. The victim's raw waiting time exceeds FCFS's
by `2.42 L` to `2.99 L` (it is `f + 2L`, rising to `3L`), all of it spent with
all `k` servers busy on other jobs. The produced schedules were audited for
capacity and work conservation by a sweep over the start times that does not
consult the simulator's internals — 0 failures on 16 schedules — and replayed
through `sharp_kernel.sched_guard`, the guard kernel used everywhere else in
this directory, with identical results.

**Both slacks saturate on the same instance.** At `k=3, L=81, m=4` the victim has
`In_i = 389` against `B + kL = 390` *and* `D_i = 292 = 3.605 L`; at `k=2, L=64,
m=6`, `In_i = 255` against `256` and `D_i = 127 = 1.984 L` against `128`. This
is exactly what revision 2's open problem 8.1 asked, and the answer is yes, so
that problem is deleted.

**What was wrong with revision 2's conjecture.** It read: "The additive constant
of Theorem 4 on the wait is bounded in `k`, lies in `[L, (3-2/k)L]`, and is
approximately `2L`; equivalently `c(k) = Θ(k)` with a slope of `2` rather than
the proved `3`." Both halves are false. The wait-additive is `(3-2/k)L`, which
is not flat — it rises from `1L` at `k=1` to `3L` — and `c(k)` has slope `3`.
The conjecture also contradicted itself: the prose said "flat in `k` at roughly
`1.75 L`" and the boxed statement five lines later said "approximately `2L`"
(referee item R3-10).

**Why the search missed it, again.** The same mechanism as §6.3, one level up.
The witness needs the cascade *and* a finale timed so that all `k` servers free
simultaneously twice in a row; at `k=2` that is `n = 396` jobs with `L = 64`,
and at `k=3, L=243` it is `n = 1233`. Every search in this project and in the
three referee directories lives two orders of magnitude below that. The third
referee ran a cascade-blind hill-climb as a control and reached `2.89` at `k=2`,
`3.56` at `k=3`, `3.89` at `k=4` — *below* revision 2's own search, which was in
turn far below the truth. Revision 2's search is reported below for the record,
and it should be read as a lower bound on what search can see, not as evidence
about `c(k)`:

| `k` | best `c(k)` found by search | as a wait-additive | true `c(k) = 3k-2` (Thm 4C) | true wait-additive `(3-2/k)L` |
|---|---|---|---|---|
| 1 | 15/16 = 0.94 | 0.94 L | 1 | 1 L |
| 2 | 31/9 = 3.44 | 1.72 L | 4 | 2 L |
| 3 | 85/16 = 5.31 | 1.77 L | 7 | 2.33 L |
| 4 | 111/16 = 6.94 | 1.73 L | 10 | 2.5 L |
| 5 | 139/16 = 8.69 | 1.74 L | 13 | 2.6 L |
| 6 | 21/2 = 10.50 | 1.75 L | 16 | 2.67 L |

The second referee reported a frontier of `2k - 10/9` for `c(k)`. Revision 2
dismissed it on the grounds that "this search beats it at `k = 2, 3, 4`", which
was selective (referee item R3-10): at `k = 5` and `k = 6` revision 2's own
numbers `8.69` and `10.50` fall **below** `2k - 10/9 = 8.89` and `10.89`. Both
formulas are now superseded — the family of Theorem 4C beats `2k - 10/9` at
every `k >= 2` — but the dismissal should not have been written that way.

Revision 1 also reported two different numbers for `k = 4` — `23/4 = 5.75` in §4
and `41/7 = 5.857` in §6 — without saying they were the same quantity. They
were: both are `c(4)` from different runs of the same search, the §4 figure from
the 400,000-instance sweep and the §6 figure from the hill-climb. Both are
superseded by Theorem 4C.

The general lesson of §6.3 applies here with the extra force that revision 2
committed a conjecture to print on the strength of a search that was wrong by a
factor of two in `k`: a hill-climb over `n <= 15` instances says nothing about a
constant whose witness needs `n` in the hundreds.

---

## 7. G5 — the price of FCFS-fairness

### Lemma 15 (inversion sums) — **proved**; the `k > 1` clause is weak

Let `S` be the set of inverted pairs, `S = { (u,v) : u < v in rank, v -< u }`.
Then

    sum_i In_i = sum_{(u,v) in S} x_v,      sum_i Out_i = sum_{(u,v) in S} x_u,

exactly, for every `k` — these are two ways of counting the same set of pairs.
Hence by Corollary 1.1, at `k = 1`, for every work-conserving non-preemptive
policy

    sum_i ( W_FCFS[i] - W_P[i] )  =  sum_{(u,v) in S} ( x_u - x_v )        (exactly)

Checked exactly at `k=1` on 150,000 random instances: 0 mismatches
(`out_price.txt`); the second referee confirms the sums and the `k=1` identity.

**For `k > 1` only the following is true, and it is weak** (referee item O7).
Summing Theorem 1 over the `n` jobs gives

    | k * sum_i ( W_P[i] - W_FCFS[i] )  -  sum_{(u,v) in S} ( x_v - x_u ) |
        <=  2(k-1) L n ,

an error that grows with `n`. Revision 1 wrote "for general `k` the same holds
after dividing by `k`, with an error of at most `2(1-1/k)L` per job", which is
true but says nothing about the *total* saving beyond the display above; the
second referee is right that in the per-job-summed reading the clause is
vacuous. It is retained only because Theorem 16 uses it in a ratio, where the
`n`-dependence cancels against the `Θ(mn)` maximum saving.

At `k = 1` the identity is the classical exchange argument, stated on an
arbitrary arrival sequence instead of a single batch: *the only way to beat FCFS
in mean wait is to invert pairs in which the later-ranked job is the smaller
one, and the saving is exactly the sum of the size differences over the
inversions.*

### Theorem 16 (how much of the FCFS -> SJF gap a guarantee `G` can buy) — **proved**

Take the two-class batch family: `m` jobs of work `L` (ranks `1..m`) and `n` jobs
of work `s < L` (ranks `m+1..m+n`), all arriving at `t=0`. Let `P` be any
non-preemptive work-conserving policy with `excess_P[j] <= G` for every job.
Then

    ( mean W_FCFS - mean W_P )
    ---------------------------------  <=  ( k G + (3k-2) L ) / ( n s )  +  eps
    ( mean W_FCFS - mean W_SJF )

with `eps = 2(k-1)L(m+n) / ( m n (L-s) ) -> 0` as `m, n` grow.

*Proof.* Write `Δ(Q) = Σ_i (W_FCFS[i] - W_Q[i])` for the total saving of a
policy `Q` against FCFS, and `E = 2(1-1/k)L(m+n)`. Summing Theorem 1 over the
`m+n` jobs and using Lemma 15,

    | Δ(Q) - (1/k) Σ_{(u,v) in S(Q)} (x_u - x_v) |  <=  E     for every Q.     (9)

*Numerator.* A pair contributes positively to the sum only when `u` is a large
job and `v` a small one, contributing `L - s`. For a fixed large job `u`, the
number of small jobs dispatched before it is at most `In_u / s`, and Theorem 2
gives `In_u <= kG + (3k-2)L`. Summing over the `m` large jobs and applying (9),

    Δ(P)  <=  (1/k) m (L-s) (kG + (3k-2)L)/s  +  E .

*Denominator.* Revision 2 divided by "the maximum possible saving is SJF's,
`(1/k) m n (L-s)`", treating that as exact. At `k > 1` it is not: the same
error `E` appears in the denominator (referee item R3-13). SJF inverts every one
of the `mn` large–small pairs, so its pair sum is exactly `mn(L-s)`, and (9)
applied to SJF gives

    Δ(SJF)  >=  (1/k) m n (L-s)  -  E .

*Divide.* Both bounds are positive once `mn(L-s)/k > E`, i.e. for `m, n` large,
and

    Δ(P)/Δ(SJF)  <=  ( (1/k) m (L-s)(kG + (3k-2)L)/s + E )
                     / ( (1/k) m n (L-s) - E )
                  =  ( kG + (3k-2)L ) / ( n s )  +  eps ,

where `eps` collects both corrections. Both are `O((m+n)/(mn))`, because the
leading terms are `Θ(mn)` and `E = Θ(m+n)`, so `eps -> 0` as `m, n -> infinity`.
∎

**The implied constant** (referee item RR-26; revisions 1–4 left it as `O(·)`).
Write `N = (1/k) m (L-s)(kG + (3k-2)L)/s` and `D = (1/k) m n (L-s)` for the two
leading terms. Then

    eps  =  (N+E)/(D-E) - N/D  =  E (N + D) / ( D (D - E) ),

and since `E/D = 2(k-1)L(m+n) / (m n (L-s))` and `N/D = (kG+(3k-2)L)/(n s)`,

    eps * m n / (m+n)  ->  C  =  2(k-1) L ( 1 + (kG + (3k-2)L)/(n s) ) / (L - s),

from above. Note the factor `k`: `E = 2(1-1/k)L(m+n)` but `D` carries a `1/k` as
well, so `E/D` has `2(k-1)L`, not `2(1-1/k)L`. (The fourth referee's suggested
constant drops it; the two agree only at `k = 1`, where both vanish.) Checked at
`k = 2,3,5` over `(m,n)` from `(50,50)` to `(2000,5000)`: the ratio
`eps / (C (m+n)/(mn))` falls monotonically to `1.0016`
(`out_rev5_items.txt`, RR-26).

**Reading.** The closable fraction is

    (capacity x guarantee) / (work that wants to overtake),

linear in `G` and saturating at `1` when `kG` reaches the total work of the
impatient class. This is exactly the shape of a consistency-robustness trade-off
curve: the guarantee `G` is not a soft penalty, it is a hard cap on how much of
the SJF benefit is reachable at all, *by any policy whatsoever*, not only by the
guard.

### Proposition 17 (the achievable fraction at `k = 1`) — **proved** *(new in revision 5)*

In the family of Theorem 16 with `k = 1`, the largest realisable

    ( mean W_FCFS - mean W_P ) / ( mean W_FCFS - mean W_SJF )

over all non-preemptive work-conserving `P` with `excess_P[j] <= G` for every
job is **exactly** `min(1, floor(G/s)/n)`.

*Proof.* Let `r_u` be the number of short jobs dispatched before the long job
`u`. Every short job ranks above every long one, so `Out_u` for a long `u`
contains only long jobs, and a long–long inversion `(p,q)` puts `L` into `In_p`
and the same `L` into `Out_q`. Summing over the long jobs those terms cancel,
and Corollary 1.1 (`k = 1`, the identity is exact) gives

    sum_{u long} excess_P[u]  =  sum_{u long} (In_u - Out_u)  =  s * sum_u r_u.

Let `u*` be the long job dispatched **last** among the long ones. It has no
lower-ranked long job after it, so `Out_{u*} = 0` and
`excess_P[u*] = In_{u*} >= s r_{u*}`. And `r_u` is non-decreasing along the
dispatch order, so `r_{u*} = max_u r_u`. The guarantee therefore forces
`max_u r_u <= floor(G/s)` and `sum_u r_u <= m floor(G/s)`. Only long–short
inversions contribute to the saving, each `L - s`, so by Lemma 15
`Δ(P) = (L-s) sum_u r_u` against `Δ(SJF) = (L-s) m n`, and the fraction is at
most `min(1, floor(G/s)/n)`.

For achievability put `r = min(n, floor(G/s))` and dispatch the `r`
lowest-ranked short jobs, then the `m` long jobs in rank order, then the rest in
rank order. Every long job has excess exactly `r s <= G`; the first `r` short
jobs have `In = 0` and `Out = mL`, so excess `= -mL`; the remaining short jobs
have `In = Out = 0`. The fraction is `r/n`. ∎

**Why the aggregate step matters, and what it corrects.** Revision 4 recorded
this as a *measurement* ("at `k=1` the realised fraction equals `min(1, G/(n s))`
exactly in every case tested"); the paper draft printed it as a proved fact. Both
readings are wrong in the same place: the tested cases all had `s = 1`, where
`floor(G/s)/n` and `G/(n s)` coincide. With `s >= 2` they separate, and
`min(1, G/(n s))` overstates what any `G`-feasible policy can reach — at
`m=1, n=2, L=5, s=2, G=3` the claim is `3/4` and the truth is `1/2`. Exhaustive
enumeration of **every** work-conserving schedule over 1,161 settings
(`m <= 3`, `n <= 4`, six `(L,s)` pairs, `G <= 3L`): 0 disagreements with
Proposition 17 (`rev5_items.py`, `out_rev5_items.txt`, RR-4).

The proposition also localises the slack in Theorem 16: the `(3k-2)L` additive
comes from applying Theorem 2 to each long job separately, whereas the long jobs
can be charged together. At `k = 1` the aggregate charge removes it entirely.

Earlier numerics, unchanged (`run_price.py`, `out_price.txt`): on the larger
members of the family the guard closes `B/(n s)` of the gap almost exactly
(`k=1, n s = 40`: `B=5 -> 0.125`, `B=20 -> 0.500`, `B=80 -> 1.000`). The second
referee confirms that the bound is never violated, and that the exact-value
phenomenon is a `k = 1` one: at `k >= 2` the realised fraction is strictly below
`min(1, floor(G/s)/n)`.

---

## 8. Open problems

Revision 2's open problem 1 — "can `In_i` be pushed to `B + kL` on the same
instance that saturates Theorem 1?" — is settled affirmatively by Theorem 4C and
is deleted; the numbering below shifts accordingly.

1. **Minimality of the guard within `Budg`** (Proposition 7, Corollary 2.1).
   Is there a wrapper that enforces a work budget, achieves the same `G`, and
   defers some job strictly longer than the guard does? Revision 1 asserted
   there is not; nothing here proves it.
2. **The downward constant in the executed-work convention** (Remark 1.3,
   §6.2). The proof gives `2(k-1)L`, the mirror family only `(k-1)L`, and
   hill-climbing `1.63 L` at `k=2`. Which is it? This is the one place where the
   two conventions are still known to differ.
3. **Two-sided guards.** Theorem 1 is two-sided but the guard only constrains
   `In`. A rule that also constrains `Out` would bound `|excess|` rather than
   `excess`, which is what a fairness statement (nobody gains too much either)
   would need.
4. **Non-work-conserving with bounded vacations.** Proposition 10 needs a bound
   on cumulative forced idleness; the natural model (a vacation of length `<= v`
   after each completion) has unbounded cumulative idleness over a long wait. Is
   there a per-busy-period accounting that rescues a useful bound?
5. **Randomised lower bounds.** Proposition 14 is deterministic and adversarial
   in the service times. A randomised policy facing an oblivious adversary might
   do better than `L`.
6. **Beyond a single reference discipline.** The same proof template compares any
   policy to any *other* work-conserving policy, not only FCFS, if one replaces
   `In`/`Out` by the inversions relative to that reference. Which references give
   a useful currency?

---

## 9. Reproducing

    env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME \
        uv run --with numpy --with numba python <script>.py [mode]

| script | what it checks | log |
|---|---|---|
| `sim_core.py` | simulator 1 (pure Python, exact integers, independent of `guardkern.py`) | — |
| `sharp_kernel.py` | simulator 2 (numba, exact integers, independent of both) | — |
| `gen_budget.py` | simulator 3 and **Theorem 4 in its general form** (§4.2): six budget rules including decreasing-in-time and adversarial per-(job, epoch); the `budget == 0` and tie-break probes; **Proposition 4B'**'s witness; Theorem 4C's family replayed through it | `out_gen_budget.txt` |
| `run_sharp.py agree` | simulator 1 vs simulator 2, and the busy-period identity | `out_sharp_agree.txt` |
| `run_sharp.py exh` | Theorem 1 on every work-conserving schedule, 45.3M schedules | `out_sharp_exh.txt` |
| `run_sharp.py rand` | Theorem 1, 10.8M instances / 108M job-checks, both conventions | `out_sharp_rand.txt` |
| `run_sharp.py scan` / `deep` | how the best searchable `|D|/L` moves with `L` (§6.3) | — |
| `run_sharp.py parts` | which term of the decomposition search saturates (§6.3) | `out_sharp_parts.txt` |
| `run_sharp.py wrap` | revision 2's hill-climb for `c(k)`, superseded by Theorem 4C (§6.4) | `out_sharp_wrap.txt` |
| `family_tight.py` | **Theorem 3 and Lemma 1''**: both explicit families, exact | `out_sharp_family.txt` |
| `wrapper_tight.py` | **Theorem 4C**: the cascade-plus-finale family, its audits, and the replay through `sharp_kernel.sched_guard` | `out_wrapper_tight.txt` |
| `rev3_items.py` | revision 3's items: Lemma 1' counterexample and repair, §6.2's two directions, Prop 3(a,c), Prop 6, Prop 13, Prop 14's family, Lemma 2's witness | `out_rev3_items.txt` |
| `rev5_items.py` | revision 5's items: **Prop 8**'s wrapper placement (counterexample + brute force without a size cap), **Prop 14**'s hypothesis (the three cases), **Prop 17** (exhaustive over every schedule of 1,161 settings), Lemma 1s at `k=1`, Remark 1.3's `over <= Ine <= In`, Remark 4B''s instance, Theorem 4C's `over_i` trace, Theorem 16's `eps` constant, Prop 13 with the short class reversed, and the `floor` in Prop 3's inversion. Pure Python: `uv run --no-project python rev5_items.py` | `out_rev5_items.txt` |
| `run_thmB.py` | **Theorem 4B**: every base tape x every parameter combination. Its growth term is `eta*(t-a_q)`, not the note's `eta*k*(t-a_q)` — see the last paragraph of §4.2; `gen_budget.py` re-runs the check with the correct term | `out_sharp_thmB.txt` |
| `dbg_thmB.py` | witness hunt for the boundary case of Theorem 4B's step (5) | — |
| `run_identity.py` | revision 1: simulator self-test, Theorem 1 exhaustive + 1e6 random | `out_identity.txt` |
| `run_wrapper.py` | Theorem 4 for 8 base-policy families, Prop 6 | `out_wrapper.txt` |
| `run_consistency.py` | Lemma 2, Theorem 2, Theorem 5 (deterministic bases) | `out_consistency.txt` |
| `run_assumptions.py` | Prop 8-12 | `out_assumptions.txt` |
| `ce_local_L.py` | the counterexample to localising `L` | `out_ce_local_L.txt` |
| `run_tightness.py` | Prop 13, 14, 3, and revision 1's adversarial search | `out_tightness.txt` |
| `run_price.py` | Lemma 15, Theorem 16 | `out_price.txt` |
| `diag_localL.py` | diagnostic used to correct the first (wrong) form of Prop 8 | — |

The referee logs are in `evidence/guard_variants_referee/` (first referee, on
`guardkern.py`), `evidence/guard_theory_referee/` (second referee, on revision
1 of this note) and `evidence/guard_theory_referee3/` (third referee, on
revision 2). Where this note cites a log by a bare `out_*.txt` name the file is
in *this* directory; the three exceptions, all in the second referee's
directory, are written out in full (`out_ce.txt` in Proposition 8 and Theorem
5(a'), `out_probes.txt` in Proposition 13) — revision 2 cited them as if they
were local (referee item R3-8).

---

## 10. CHANGELOG — referee items and how each was resolved

Items `G1-G3` and `D1` are from the first referee
(`evidence/guard_variants_referee/`); `O1-O13` from the second
(`evidence/guard_theory_referee/`); `R3-1 … R3-14` from the third
(`evidence/guard_theory_referee3/`); `D4-D6` from the paper draft; `D7-D10`
from the paper draft's general statement of the wrapper theorem; `RR-1 … RR-31`
from the fourth referee, who read the built manuscript
(`docs/referee_readthrough/referee_report_full.md`).

### Revision 5 (the fourth referee, reading the paper)

All six items were re-derived here before being accepted or rejected; the
measurements are in `rev5_items.py` / `out_rev5_items.txt`.

| item | what it said | resolution |
|---|---|---|
| **RR-1** | Proposition 8's "upward (Corollary 1.2 **and the wrapper bound**) — `Λpref(a_i)` is enough" is false for the wrapper: the `kL` term charges overtakers, which arrive after `a_i` | **accepted, and the note was wrong too.** Revisions 1–4 asserted it and proved only the identity half. Proposition 8 now separates the two: `Λpref(a_i)` for the identity's upward direction and Corollary 1.2, `Λpref(s^P_i)` for Theorem 4's `In_i < Bmax + k Λ` and for the wait bound, with the sharp mixed form `Bmax/k + Λpref(s^P_i) + (2-2/k) Λpref(a_i)` written out and Theorem 4B carried along. The referee's counterexample reproduces exactly (`k=1, B=2`, victim and `A` of work `1` at `t=0`, `Z` of work `M` at `t=1`); one correction to the referee, who writes "violated for every `M > 2`" — the first violation is at `M = 2`, where `In_i = 3` is not `< 3`. Brute force without a size cap: 156 / 126 failures under `Λpref(a_i)`, 0 under `Λpref(s^P_i)` |
| **RR-2** | Proposition 14 is right here and was lost in compression; the paper states it over *policies*, where FCFS refutes it | **accepted for the paper, and the hypothesis sharpened here.** The note already said "every wrapper with a positive budget"; what it did not say is which epoch. Added: (a) the statement over policies is false (FCFS, and every rank-ordered policy, has excess `0`); (b) "positive at the first dispatch epoch" is sufficient but **not necessary** — a rule that is `0` there and positive later (age-relative with `B0 = 0`) falls to the same instance behind a saturating prefix, measured at `k = 1,2,3`; (c) the rules that escape are exactly those with `budget_q(t) = 0` whenever `over_q(t) = 0`, and those **are FCFS**, by a one-line induction, checked on 600 instances with 0 disagreements |
| **RR-4** | the `k=1` achievable fraction is asserted as proved in the paper and recorded as a measurement here; and the exact value is `floor(G/s)/n`, not `G/(n s)` | **accepted, both halves.** Promoted to **Proposition 17** with a proof: the long–long inversions cancel in the aggregate, so `sum_{u long} excess = s sum_u r_u`, and the long job dispatched *last* carries `max_u r_u` with `Out = 0`, which caps every `r_u` at `floor(G/s)`. The note's own numerics could not have seen the difference: every tested case had `s = 1`. Exhaustive over all work-conserving schedules of 1,161 settings: 0 disagreements |
| **RR-7** | Lemma 1's strictness is false at `k = 1`; the note carries the condition inside its proof but the statement does not | **accepted.** `k >= 2` moved into the statement of Lemma 1s and into §0; the two steps of the proof that need it are marked; the `k = 1` behaviour (`U_A ≡ U_B`, bound attained) is stated |
| **RR-8** | the stated reason for keeping the sequence convention — "completed work lower-bounds `In_i` but not `Ine_i`" — is false | **accepted; the referee's claim was checked before the text was changed.** A job of rank above `q` completing while `q` waits is dispatched at or after `a_q`, so all of its work is executed inside `[a_q, s^P_q)` and `over_q(t) <= Ine_q <= In_q`. 18,688 `(q,t)` checks at `k = 1..4`, 0 violations. Remark 1.3 now gives the two reasons that are true (exactly determined constant, symmetric sides) and states that both currencies are metered |
| **RR-26** | `eps = O((m+n)/(mn))` hides a constant a reader is entitled to see | **accepted with a correction.** `eps = E(N+D)/(D(D-E))` and `eps m n/(m+n) -> 2(k-1)L(1 + (kG+(3k-2)L)/(ns))/(L-s)` from above. The referee's `2(1-1/k)L(...)/(L-s)` drops a factor `k`, because `D` carries the `1/k` as well; the two agree only at `k = 1`, where both vanish |
| — | RR-3, RR-5, RR-13, RR-14, RR-17, RR-19, RR-21, RR-25, RR-30, RR-31, RR-35, RR-36, RR-54–58 | paper-only items (wording, notation, a stale number, a missing instance, an appendix title). Nothing in this note changes for them, except that the words "conservation law" are gone from its title and two headings: what is proved is a per-job pathwise *identity* against a named reference, and the classical multiserver conservation laws (Kleinrock 1965; Federgruen–Groenevelt 1988; Green–Stidham 2000) require a common service distribution, which is exactly the hypothesis unavailable here |

### Revision 4 (the paper draft's general wrapper theorem)

| item | what it said | resolution |
|---|---|---|
| **D7** | the paper states Theorem 4 for **any** budget rule with `0 <= budget_q(t) <= Bmax`, not only the constant and relative ones. Does the proof support that? | **yes, verbatim.** The rule is read at one dispatch epoch, for one job, and only through the cap. Theorem 4 is restated for the whole class, with the five properties the proof does not use (monotonicity in `t`, a common rule across jobs, measurability / non-anticipation, `budget >= 0` for the upper bound, and any relation between `E(t)` at different epochs) and the two it does (minimum-rank service of `E(t)`, and `over` charged to completed work) written out. Checked on 62.4M schedules over six rules, including budgets redrawn independently at every (job, dispatch epoch): 0 failures (§4.2) |
| **D8** | `budget == 0` must reduce the wrapper to FCFS | it does, and the argument is one line (`over >= 0` always, so `E(t)` is the whole waiting set and the wrapper serves minimum rank, which inside a phase is increasing rank). Measured on 360,000 (instance, tape) pairs: the dispatch sequence and the start times agree with FCFS on every one |
| **D9** | `rem:mult_scope` excludes `gam > 0` from the multiplicative bound because `B0_q = B0 + gam n_q` "is not a constant the operator can state in advance". Is that the right reason? | the conclusion is right, the reason is weaker than the truth. **Proposition 4B'** (new): with the common `B0` the multiplicative bound is not merely unannounceable, it is *false*, for every `eta in [0,1)`, by a margin that grows with `gam`. Witness at `k=1, L=1, B0=0`: the victim's excess is exactly `gam` against a right-hand side of `2/(1-eta)` that does not depend on `gam`. The per-job form (6) with `B0_i` holds on the same instance, and so does Theorem 4 |
| **D10** | does Theorem 4C survive the general statement? | yes: its family uses the constant budget `B = f + L + 1`, which is a member of the general class with `Bmax = B`. All eight rows replay through revision 4's kernel with the same numbers and `c(k) < 3k-2` strictly (§4.2) |
| — | revision 3's own instrumentation | `sharp_kernel.sched_guardB` grows the budget at `eta*(t-a_q)` while `run_thmB.py` checks against `eta*k*(t-a_q)`; the two agree only at `k=1`, so revision 3's Theorem 4B sweep tested a slower budget than the note claims. `gen_budget.py` re-runs it with the note's rule for `k <= 5`: 0 failures. The kernel is left unchanged so revision 3's logs stay reproducible |

### Revision 3 (the third referee)

| item | what it said | resolution |
|---|---|---|
| **R3-1** | §6.4's conjecture is false: an explicit family drives `c(k)` to the proved ceiling `3k-2`, and open problem 8.1 is settled | **reproduced.** The family was rebuilt from the referee's prose and measured with this directory's `sharp_kernel.py`: every number agrees, the schedules pass an independent work-conservation audit, the excess is real waiting (same-phase share of `In_i` is `0`), and the run replays identically through `sharp_kernel.sched_guard`. Promoted to **Theorem 4C** with a full proof of the limit and of non-attainment; the `1.75 L` conjecture is withdrawn; open problem 8.1 deleted; §6.4 rewritten with a note on why search could not reach it |
| **R3-2** | "never attained / strict" is asserted, not proved; three-line proof supplied | checked and written in as **Lemma 1s**, with the `L > 0` hypothesis made explicit; Lemma 1'''s faulty closing sentence replaced; Theorem 3's strictness now derives from Lemma 1s |
| **R3-3** | Lemma 1' is false as written; counterexample `k=2, a=(0,0,0,0,0,4,4), x=(4,1,1,1,1,10,10), t=5`; repair by reading the reference time at its left limit | confirmed with an exact (not grid-based) search over the constancy decomposition of the time line: no admissible `u` at `t=4` or `t=5`, gap `2 > 0`. Lemma 1' restated with the left-limit reference time and no fallback clause; Proposition 8 re-checked and unaffected. **One correction to the referee:** on the cascade *without* its finale the clause is not refuted, because `N_P(T_m) = k-1` makes the trivial choice `u = t` admissible; the refutation needs the arrivals at `T_m`, and that is now how the note states it |
| **R3-4** | §6.2 and §0 claim the refutation symmetrically; downward it is half a convention | §6.2 rewritten with the two directions stated separately and a measured table: upward the same-phase share is `0-0.84%` and the victim's real excess is `+3.0 L`; downward `In_i = (k-1)L` is `100%` same-phase, the executed convention reaches only `(k-1)L`, and the victim's real excess is negative. §0 carries the same caveat |
| R3-5 | Remark 1.3's "`rho_new = 0` at the victim" is wrong | corrected to `rho_old = 0` and `rho_new <= k-1 = o(L)`, with the measured values; the conclusion is unchanged since `De = D + rho_new >= D` |
| R3-6 | §1's sentence about the no-observation restriction contradicts Theorem 3's size-aware `P` | rewritten: the restriction is used by Proposition 14 alone |
| R3-7 | Proposition 14's approaching family is missing | supplied and proved (`excess - B = L - g`), with the measurements |
| R3-8 | three `out_*.txt` citations point at another directory | qualified in place, and §9 says what the convention is |
| R3-9 | Lemma 1's "if `S` is empty" branch is dead and self-contradictory | deleted, with the reason recorded |
| R3-10 | §6.4's `1.75 L` and `2 L` were already inconsistent with each other, and the dismissal of the `2k - 10/9` frontier was selective | both noted in §6.4; at `k=5,6` revision 2's own numbers fall below `2k-10/9`, which the note now says |
| R3-11 | Theorem 4B's (5) lacks the "at least one overtaker" guard | added |
| R3-12 | Lemma 2's cited evidence used a negative "guarantee" | replaced by the referee's `G = 0` witness, written out in full |
| R3-13 | Theorem 16's proof treats the SJF denominator as exact | proof rewritten with the error term on both sides and `eps` collecting both |
| R3-14 | four "proved" labels rest on measurements only | all four now carry proofs: Proposition 3(a) and 3(c) (explicit families), Proposition 6 (the exact ratio `(2L+m-1)/(m+1)`), Proposition 13 (`excess = ceil(B/k)`, which also fixes the `k \| B` assumption that was hidden in the measurements) |

### Revisions 1 and 2 (the first two referees and the paper draft)

| item | what it said | resolution |
|---|---|---|
| G1 / O12 | Lemma 1's "last time `<= t`" presumes an attained supremum | Lemma 1 reproved via the **left limit** `U_A(t0^-)` at the last crossing |
| G2 | the wrapper proof does not handle an overtaker dispatched at exactly `s_i` | Theorem 4's proof now names that case explicitly and notes the count is then `k-2`, not `k-1` |
| G3 / O9 | `R_i` must be read after the arrivals at `a_i`; tie conventions unstated | new §1.1 fixes the event order, the dispatch sequence, the phase, the reading of `R` and `rho`, and the same-phase rule; Remark 1.0 explains why the degenerate witnesses are not the worst ones |
| O9 (2nd half) | offer an executed-work convention for `In`/`Out` | Remark 1.3: defined, proved to obey the same constant, shown **not** to be smaller upward; sequence convention kept as the main theorem, with the reason stated |
| O1 | Theorem 5(a) is not an "iff"; the converse is false | (a) restated as one direction; (a') gives the referee's `k=1` counterexample; status table and §0 corrected |
| O2 | prefix-max at `a_i` is wrong for Thm 1 downward and for Thm 2 | Prop 8 now states three different placements (`a_i` upward, `max(s^P_i,s^F_i)` downward, `s^F_i+G` in Thm 2), with the referee's `M`-family table |
| O3 / D5 | at `k=1` the bound `B+L` is strict, not attained | Prop 14 restated as a **supremum** statement; the "on the nose" sentence deleted; the project's own logs (88.84/179.25/658.25 vs 90/180/660) quoted as confirming it |
| O4 / O5 | the constants are not tight; frontier data | **Theorem 3**: the constant of Theorem 1 is *proved optimal* — the referee's `(k-1)L` conjecture is disproved with an explicit family. Revision 2 rebuilt the wrapper frontier from its own search; revision 3 replaces that with **Theorem 4C** (see R3-1) |
| O6 | two inconsistent `k=4` numbers | both identified as `c(4)` from two runs of the same search, both superseded; there is now one table (§6.4) |
| O7 | Lemma 15's `k>1` clause is vacuous as stated | restated as the explicit `2(k-1)Ln` display, marked weak, with the exact `k=1` identity kept as the result |
| O8 | Prop 7 / Cor 2.1 claim "only" and "laziest" without proof | both claims withdrawn; Cor 2.1 now states the two containments only; Prop 7 states only that the constraint is saturated at a firing; minimality moved to §8, item 1 |
| O10 | the timeout version must read everything in executed work | Prop 11a says so explicitly, for `In`, `Out`, `over` and `L`, and notes the raw-work reading is false |
| O11 | server selection under unequal speeds is undefined | Prop 9 defines it and proves the result does not depend on it |
| O13 | say what the simulator is | §0 and §9: `sim_core.py` and `sharp_kernel.py` are both written by this note's author, share no code with `guardkern.py` or with each other, and are cross-checked (`out_sharp_agree.txt`) |
| Lemma 2 | free strengthening available | hypothesis weakened to `i` and the jobs of `Out_i`; referee probe P1 quoted showing both halves are needed |
| D4 | plan says the frontier is `(2 - 10/(9k))L`, note says `Θ(kL)` | §6.4 fixes the **units**: `c(k) = (k*excess-B)/L` grows linearly, the additive on the **wait** is `c(k)/k` and is bounded in `k`. The `Θ(kL)` conjecture is withdrawn as a units error. Revision 3 settles the value: `c(k) = 3k-2` and the wait-additive is `(3-2/k)L`, so `(2-10/(9k))L` is not the frontier either |
| D5 | Prop 14's "`B+L` on the nose" conflicts with the logs | see O3 |
| D6 | the capped relative budget is only in a docstring | **Theorem 4B** with full proof (any base, any `k`), the parameter rule `Bmax = k(G-(3-2/k)L)`, and a 103M-combination brute-force check |
| D1 | `guardkern.py`: `theta>0, Ncap=0` disables the count channel, contradicting the docstring | fixed in `evidence/guard_variants/guardkern.py`: the docstring now describes what the code does, and `run()` raises on `theta>0 xor Ncap>0`, so the unbounded "free short overtakers" rule cannot be selected by accident |
