# Revision 5 — every change, with the verification behind it

Scope: `paper/sections/06_theory.tex`, `paper/sections/A_proofs.tex`,
`evidence/guard_theory/theory.md` (rev. 4 → rev. 5), plus the new
`rev5_items.py` / `out_rev5_items.txt`. Nothing outside those files was touched;
in particular `paper/CHANGES_integration.md`, `outputs/`, `main.tex` and
sections 01–05 and 07–09 belong to other editors.

Source of the items: `docs/referee_readthrough/referee_report_full.md`
(fourth referee, reading the built manuscript). Every mathematical point was
re-derived or re-measured here before the text was changed; where the referee is
wrong that is said, with the correction.

Reproduce:

    cd evidence/guard_theory
    env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME \
        uv run --no-project python rev5_items.py      # writes out_rev5_items.txt

Build check (scratch copy of `paper/`, never `paper/main.pdf`): tectonic, 49
pages, 0 unresolved cross-references, 0 LaTeX errors.

---

## Verdict table

| item | verdict | where |
|---|---|---|
| RR-1 | APPLIED (with one correction to the referee) | `06:477–500`, `theory.md` Prop 8 |
| RR-2 | APPLIED WITH CHANGE (hypothesis is sufficient, not necessary; the true condition added) | `06:534–578`, `theory.md` Prop 14 |
| RR-3 (my part) | APPLIED | `06:255–296` |
| RR-4 | APPLIED (value corrected to `⌊G/σ⌋/n`, proposition added) | `06:585–600`, `A:465–505`, `theory.md` Prop 17 |
| RR-5 | APPLIED | `06:153–166` |
| RR-7 | APPLIED | `06:53–68`, `06:136`, `A:17–75`, `theory.md` Lem 1s |
| RR-8 | APPLIED (referee's claim verified first) | `06:193–201`, `theory.md` Rem 1.3 |
| RR-13 | APPLIED with one reported deviation (`σ`, not `c`; setup time moved to `θ`) | both files |
| RR-14 | APPLIED | `A:196–200` |
| RR-17 | APPLIED | `06:87`, `06:136`, `06:363` |
| RR-19 | APPLIED WITH CHANGE (the referee's own `W_FCFS[i] = 1` is wrong) | `06:388–404` |
| RR-21 | APPLIED | `A:5` |
| RR-25 | APPLIED WITH CHANGE (three epochs, not two) | `06:437–443` |
| RR-26 | APPLIED WITH CHANGE (the referee's constant drops a factor `k`) | `06:568–571`, `A:437–452` |
| RR-30 | APPLIED (the value is order-independent; the proof's sentence is not) | `A:227` |
| RR-31 | APPLIED | `06:289–291` |
| RR-35 | APPLIED (nothing to remove in the two tex files; `theory.md` title and two headings changed) | `theory.md` |
| RR-36 | APPLIED (`smith1956` was in `refs.bib` at the end, so it is cited) | `A:395–398` |
| RR-54…RR-58, cut at 06:403 | APPLIED | `06` |
| positioning (Yu & Scully) | APPLIED — no novelty claim for work-budgeting anywhere in the two files; one subsection heading retitled | `06:215` |

---

## RR-1 — Proposition 2(i): the wrapper bounds need `Λ(s^P_i)`

**Verified before changing anything.** The referee's counterexample reproduces
exactly with this directory's simulator (`rev5_items.py`, section RR-1):
`k = 1`, constant budget `B = 2`, victim `i` (rank 0, service 1) and `A`
(rank 1, service 1) at `t = 0`, `Z` (rank 2, service `M`) at `t = 1`, base
priority "A, then Z, then i".

| `M` | `In_i` | `B+kΛ(a_i)` | excess | `B/k+(3-2/k)Λ(a_i)` | `B+kΛ(s^P_i)` |
|---|---|---|---|---|---|
| 1 | 2 | 3 | 2 | 3 | 3 |
| 2 | 3 | 3 | 3 | 3 | 4 |
| 10 | 11 | 3 | 11 | 3 | 12 |
| 1000 | 1001 | 3 | 1001 | 3 | 1002 |

**One correction to the referee**, who writes "violated for every `M > 2`": the
first violation is at `M = 2`, where `In_i = 3` is not `< 3` and `excess = 3` is
not `< 3`.

**Brute force without a global size bound** (Pareto(0.7) integer sizes, no cap,
`k = 1..4`, 1,600 instances, 2,074 job-checks with at least one overtaker):
156 failures of the `In` bound and 126 of the additive bound under `Λ(a_i)`;
**0** failures of either under `Λ(s^P_i)`.

**Placement decided.** The proof of `eq:guardin` charges the last overtaker `j`
and the at most `k-1` overtakers in service beside it. All of them are
dispatched at or before `s^P_i`, hence arrived by `s^P_i`, so the right prefix
maximum is `Λ(s^P_i)`. The identity's upward half keeps `Λ(a_i)`. Composing,
the sharp forms are

    In_i      <  Bmax + k Λ(s^P_i)
    excess_i  <  Bmax/k + Λ(s^P_i) + (2-2/k) Λ(a_i)
              <= Bmax/k + (3-2/k) Λ(s^P_i),

so `eq:guardadd` may be stated uniformly at `Λ(s^P_i)`. The same substitution
carries `eq:guardinmult` and `eq:guardmult`, which the referee did not mention
and which have the same `kL` term.

**Before** (`06_theory.tex`):

> The upward direction of Theorem~\ref{thm:identity}, and hence
> Corollary~\ref{cor:sufficient} and \eqref{eq:guardadd}, hold with $L$ replaced
> by $\Lambda(a_i)$; the downward direction needs …

**After**: the item now separates the identity from the wrapper, gives the
mechanism (the `kL` term charges overtakers, which arrive after `a_i`), prints
the compact form of the counterexample, writes both sharp forms, and names
`eq:guardinmult` / `eq:guardmult` alongside.

`theory.md` Proposition 8: the bullet "**Upward (Corollary 1.2 and the wrapper
bound) — `Λpref(a_i)` is enough**" was wrong in the note too (it proved only the
identity half). It is split into two bullets, the second giving the wrapper
placement, the counterexample table and the brute-force counts. §0's Prop 8 row
updated.

## RR-2 — Proposition 3 (Impossibility)

**The referee is right that the printed statement is false**: FCFS is
non-preemptive, work-conserving, reads no service time before completion, and
has excess `0` on every input (measured at `k = 1,2,3`), as does every
rank-ordered policy.

**The exact hypothesis, which the task asked to be settled.** "Positive at the
first dispatch epoch" is what the proof uses and is *sufficient*; it is **not
necessary**. Three facts, all measured:

1. *Sufficient.* With `budget(i,0) > 0`, the instance "victim + `k` jobs of
   service `L` at `t = 0`" forces excess `= L`. With `budget(i,0) = 0` the
   guard fires on `i` at once and the excess is `0`. Measured at `k = 1..4`,
   budgets `0 / 1 / 5`: excess `0 / L / L` in every row.
2. *Not necessary — rules that are `0` at the first epoch and positive later
   still fall.* Age-relative shape with `B_0 = 0`, `η > 0`: prefix the instance
   with `k` jobs of service `L` at `t = 0` (the wrapper is FCFS there, every
   budget being `0` at age `0`), let the victim arrive at `t = 1` and `k`
   overtakers at `t = L-1`. At `t = L` the victim's budget is positive because
   it has aged. Measured at `k = 1,2,3`, `η ∈ {1/2, 1/10}`: `W_FCFS = 9`,
   `W_P = 19`, excess `= L = 10` in every row.
3. *What escapes is degenerate.* If `budget(q,t) = 0` whenever
   `over[q](t) = 0`, the wrapper **is FCFS**: by induction, nothing has been
   overtaken, so the lowest-ranked waiting job `h` has `over[h] = 0 = budget`,
   lies in `E(t)`, is its minimum-rank member, and is dispatched. Checked on
   600 random instances at `k = 1..4`: 0 disagreements with the FCFS dispatch
   order.

So the true condition is the dichotomy: **a wrapper of this family either never
overtakes anything (and is first-come first-served), or admits an input with
excess at least `L`.** The paper states the clean sufficient hypothesis in the
proposition and the dichotomy in the paragraph that follows it.

**Before**: "Let $P$ be any non-preemptive work-conserving policy that observes a
job's service time only at its completion. Then there are inputs on which some
job has $\mathrm{excess}_P[i]\ge L$. In particular no wrapper with a positive
budget can promise $G<L$ …"

**After** (final statement): *Let $A$ be any base policy that observes a job's
service time only at its completion, and run Algorithm 1 around it with any
budget rule that is positive at the first dispatch epoch. Then there is an input
on which some job has excess $\ge L$. Consequently no such wrapper can promise
$G < L$, and at $k = 1$ the bound $B+L$ of Theorem 4 is the exact supremum of the
excess, approached and not attained.*

The proof's false step ("`P` cannot be dissuaded from doing so") is replaced by
the guard's not firing, and the case where the guard fires on some other job at
`t = 0` is handled explicitly.

`theory.md` Prop 14 gains the three facts above and the dichotomy; §0 row
updated. Note for the integrator: `09_limitations.tex:45–47` carries the same
over-general sentence and is another editor's file.

## RR-3 — Remark 2's title and scope (my part only)

Verified: inside Section 3's model (`0 < C_i ≤ L`) the remark itself proves
`eq:skip`, so counting **is** sufficient. Only necessity fails unconditionally.

* Title **before**: "Counting overtakes is neither sufficient nor necessary".
  **After**: "Counting overtakes is not necessary, and is sufficient only at the
  worst-case charge".
* Opening rewritten to say that a count bound does give a per-job guarantee
  inside the model, is not necessary for one, and costs a factor `L/C̄`.
* The unbounded-service instance is now marked as stepping outside Section 3.
* `eq:skip` kept verbatim (with `N → κ`).

Abstract and introduction are other editors' files; `main.tex:109` already reads
"a count of overtakes is not necessary, and suffices only by charging `L` per
pass" in the build I compiled against.

## RR-4 — the `k = 1` achievable fraction

**The referee's aggregate argument is correct and his value is correct.**
Verified by exhaustive enumeration of *every* work-conserving schedule of the
two-class batch at `k = 1`, over 1,161 settings (`m ≤ 3`, `n ≤ 4`, six `(L,σ)`
pairs, `G ≤ 3L`): **0 disagreements** with `min(1, ⌊G/σ⌋/n)`; the paper's
`min(1, G/(nσ))` is strictly larger whenever `σ ∤ G` and `G < nσ` (e.g.
`m=1, n=2, L=5, σ=2, G=3`: claimed `3/4`, true `1/2`).

The note's own numerics could not have caught it: every case in `out_price.txt`
has `σ = 1`, where the two expressions coincide.

**The proof as added** (Proposition A1, `A_proofs.tex`, §A.7). Let `r_u` be the
number of short jobs dispatched before long job `u`. Long–long inversions cancel
between `In` and `Out`, so `Σ_{u long} excess[u] = σ Σ_u r_u`. The long job
dispatched **last** has `Out = 0` and carries `max_u r_u` (because `r` is
non-decreasing along the dispatch order — checked over all schedules of three
families, 0 violations), so `max_u r_u ≤ ⌊G/σ⌋` and `Σ_u r_u ≤ m⌊G/σ⌋`.
Achievability: dispatch `min(n, ⌊G/σ⌋)` short jobs, then the long jobs in rank
order, then the rest.

This is slightly stronger than the referee's write-up, which bounds
`Σ_u r_u ≤ mG/σ` from the aggregate alone; the aggregate bound is `⌊mG/σ⌋`,
which for `σ ∤ G` is larger than the truth `m⌊G/σ⌋`. The last-dispatched-long-job
step is what closes the gap.

**Final statement.** *In the family of Theorem 6 with `k = 1`, the largest
value of `(mean W_FCFS − mean W_P)/(mean W_FCFS − mean W_SJF)` over all
non-preemptive work-conserving `P` with `excess_P[j] ≤ G` for every job is
exactly `min(1, ⌊G/σ⌋/n)`.*

§6 **before**: "At $k = 1$ the achievable fraction is exactly $\min(1, G/(ns))$."
§6 **after**: "There the achievable fraction is known exactly: it is
$\lfloor G/\sigma\rfloor/n$, capped at $1$ (Proposition A1)."

`theory.md` §7: the paragraph headed "Numerics" that recorded this as a
measurement is replaced by **Proposition 17**, proved, with the `s = 1` blind
spot spelled out. §0 gains the row.

## RR-5 — the residual range

Read from `outputs/dev_tables/identity_residuals.csv`, all 81 rows, column
`ratio_to_bound`: **min 0.46982235** (overlay 0, level 0, `k = 8`, `Skip(300)`),
**max 0.51727123** (overlay 0, level 1, `k = 5`, `Guard(300)`); 0 violations.

`06:157–158` **before**: "reaches \devnum{0.485} to \devnum{0.521}".
**After**: "reaches \devnum{0.470} to \devnum{0.518}", rounded outwards so that
the same `0.518` serves the "never exceeds" reading in §8, plus a seven-line
`% PROVENANCE` comment naming the file, the two argmin/argmax rows and the exact
values.

Note for the integrator: `outputs/paper_tables/numbers.csv` rows
`06_theory:157:0` and `06_theory:158:0` still carry `0.485` / `0.521` and the
`theory-constant` label on the second; they need regenerating. That file is not
mine.

## RR-7 / RR-17 — strictness

Verified: at `k = 1` one server executes work at rate 1 whenever a job is
present, so `U_{Q_1} ≡ U_{Q_2}` and `(k-1)L = 0` is attained everywhere.
Measured `max |U_A − U_B| = 0` over 300 random `k=1` instances.

* Lemma 1 **before**: "… $\le (k-1)L$ for every $t$, and the inequality is
  strict: $|U_A(t)-U_B(t)|<(k-1)L$. The constant is the exact supremum …"
  **After**: "… $\le (k-1)L$ for every $t$. For $k \ge 2$ the inequality is
  strict …, and the constant is the exact supremum, approached but never
  attained. At $k = 1$ both sides vanish: one server executes work at rate $1$
  whenever any job is present, so every work-conserving policy has the same
  unfinished work at every instant."
* Theorem 1's *Comparison* step: `< (k-1)L` → `≤ (k-1)L`, strictly for `k ≥ 2`.
* Theorem 1's display: "with strict inequality for $k \ge 2$" added (RR-17).
* `eq:guardmult`: `\le` → `<`, with the strictness argument written into the
  proof (RR-17).
* `A_proofs.tex`: the strictness proof is retitled "for $k \ge 2$", the two
  steps that need it are marked, and the `k = 1` failure is stated.
* `A_proofs.tex` non-attainment step now opens "For $k \ge 2$".
* `theory.md` Lemma 1s: `k >= 2` moved into the statement; §0 row updated.

## RR-8 — the reason for the dispatch-sequence convention

**The referee's claim was checked before the text was touched.** If `j` has rank
above `q` and completes at `t ≤ s^P_q`, then `a_j ≥ a_q`, so `j` is dispatched
at `s^P_j ≥ a_j ≥ a_q` and finishes by `s^P_q`: all of `C_j` is executed inside
`[a_q, s^P_q)` and is counted in full by the executed-work variant. Hence
`over[q](t) ≤ In^exec_q ≤ In_q`. Measured: 1,000 instances at `k = 1..4`,
18,688 `(q,t)` pairs, **0** violations of either inequality.

**Before**: "We keep the dispatch-sequence convention because $\mathrm{In}_i$ is
the quantity a scheduler can meter: the guard charges completed work, which
lower-bounds $\mathrm{In}_i$ but not its executed-work variant."

**After**: two reasons (constant exactly determined in both directions, the
executed-work downward constant being open in `((k-1)L, 2(k-1)L]`; symmetric
sides), followed by the one-sentence proof that completed work lower-bounds both
currencies, so the guard is implementable either way.

`theory.md` Remark 1.3 carried the same false clause and is repaired the same
way; §0 row updated.

## RR-13 — the rename map, as actually applied

| from | to | where |
|---|---|---|
| Lemma 1's policies `A`, `B` | `Q_1`, `Q_2` | `06:53–68`; `A_proofs.tex` §A.1 (both proofs, including `N_A`→`N_{Q_1}`, `N_B`→`N_{Q_2}`) |
| appendix error term `E` | `\mathcal{E}` | `A_proofs.tex` §A.7 |
| skip count `N` | `\kappa` | `06:281–291`, including `eq:skip` |
| short jobs in the upward witness `N` | `n_{\mathrm{sh}}` | `A_proofs.tex` §A.3 |
| server index `m` in `V = Σ v_m` | `\ell` | `06:501` |
| total saving `Δ(Q)` | `S(Q)` | `A_proofs.tex` §A.7 |
| inverted-pair set `S(Q)` | `\mathcal{I}(Q)` | `A_proofs.tex` §A.7 |
| Lemma 2's window `δ` | `w` | `06:231–234` |
| short-job service `s` | **`\sigma`** (not `c`) | `06` Theorem 6 and surrounding text; `A_proofs.tex` §A.7 and Proposition A1 |

**Two collisions the map itself creates, and what was done.**

1. `c` is already the tightness constant `c(k)` of Theorem 5 (`06:381,387`;
   `A_proofs.tex:245,304`). As the task directs, the short-job service became
   `\sigma` instead of `c`.
2. `\sigma` was already in use, for the setup time in
   Proposition 7(iv) ("a setup of length `\sigma`"). It occurs nowhere else in
   the manuscript (`grep -rF '\sigma' paper/` returns only those three lines,
   all in `06_theory.tex`), so the setup time was moved to **`\theta`**, which
   is unused anywhere in `paper/`. This is the one deviation from the fixed map,
   and it is confined to one item of one proposition in a file I own.

`N_Q(t)` (number of jobs present), `N_{Q_1}`/`N_{Q_2}` in the appendix, and
`E(t)` (the fired set) are unchanged — they are not part of the map.

Other editors' files that use the same symbols (Table 4, Table 9, `05:221`,
`03:39`, `05:19,62`) are untouched.

## RR-14 — the dangling "step (ii)"

`A_proofs.tex` **before**: "step (ii) of Theorem~\ref{thm:identity} gives …"
**After**: "the *Bounding $\rho$* step of the proof of Theorem~\ref{thm:identity}
gives …". A sweep of the appendix found no other numbered-step reference.

## RR-19 — Remark 3's counterexample

**The referee's own instance is wrong in one number.** He writes "one job of
service 1 at `t=0`, a second job of service 1 at `t=0+`, then the victim … FCFS
starts `i` at `W_FCFS[i] = 1`". With `k = 1`, a job can only be *waiting* at the
victim's arrival if another is in service, so two jobs are ahead of `i` and
`W_FCFS[i] = 2`, not `1`; the right-hand side is then `3/(1-η)`, not `2/(1-η)`.

**The instance as written into the paper** (simulated, `rev5_items.py` RR-19):
`k = 1`, `B_0 = 0`, `B_max = γ`, any `η ∈ [0,1)`; a job of service `L` at
`t = 0`; a second of service `L` at `t = 1` with `n_q = 0`; the victim `i` of
service `L` at `t = 1`, ranked after it, so `n_i = 1` and its budget is `γ`; and
`γ` jobs of service `1` at `t = 2L`, all ranked above `i`.

    W_FCFS[i] = 2L - 1 ,   W_P[i] = 2L - 1 + γ ,
    RHS of (guardmult) with the common B0 = 0  =  (3L-1)/(1-η) ,
    violated for every γ > (3L-1)/(1-η) - (2L-1)   ( γ > L at η = 0 ).

Measured at `L ∈ {4,8}` and `γ ∈ {1,2,4,8,16,32}`: the crossing is exactly at
`γ = L` and the margin grows without bound.

## RR-21 — appendix title

**Before**: "Proofs of the tightness results". **After**: "Deferred proofs and
the extremal constructions".

## RR-25 — what `over[i]` does in the tightness family

Recomputed from the construction (`rev5_items.py` RR-25; `L = k^m`,
`f = L - (k-1)^m`, `B = f + L + 1`):

| `k` | `m` | `f` | `B` | epoch | `over[i]` | `B − over[i]` |
|---|---|---|---|---|---|---|
| 2 | 6 | 63 | 128 | `T_m` / `T_m+f` / `T_m+f+L` | 0 / 63 / 127 | 128 / 65 / **1** |
| 3 | 4 | 65 | 147 | same | 0 / 65 / 146 | 147 / 82 / **1** |
| 4 | 3 | 37 | 102 | same | 0 / 37 / 101 | 102 / 65 / **1** |

So `over[i]` stops one unit short **once**, not twice, and there are **three**
epochs at which it stays below the budget, with the base taking every free
server at each. The referee's fix ("two successive epochs … a third time") is
one epoch short; the text now says three.

**Before**: "…timed so that $\mathrm{over}[i]$ stops one unit short of the
budget twice in succession, letting the base policy fill every server a third
time before the guard fires."
**After**: "…timed so that $\mathrm{over}[i]$ stays below the budget
$B = f + L + 1$ at three successive dispatch epochs --- at $0$, at $f$, and at
$f + L = B - 1$, the last of them by a single unit --- letting the base policy
take every free server three times before the guard fires."

## RR-26 — the implied constant, and the slack

**The referee's constant is wrong by a factor `k`.** With
`N = (1/k) m (L-σ)(kG+(3k-2)L)/σ`, `D = (1/k) m n (L-σ)` and
`E = 2(1-1/k)L(m+n)`, the proof gives `ratio ≤ (N+E)/(D-E)`, so
`ε = E(N+D)/(D(D-E))` and

    ε · mn/(m+n)  →  2(k-1) L ( 1 + (kG+(3k-2)L)/(nσ) ) / (L-σ)     from above.

`E/D` carries the factor `k` because `D` itself has the `1/k`; the referee's
`2(1−1/k)L(…)/(L−σ)` drops it. The two agree only at `k = 1`, where both vanish.
Checked at `k = 2,3,5` over `(m,n)` from `(50,50)` to `(2000,5000)`: the ratio
`ε/(C(m+n)/(mn))` falls monotonically to `1.0016`.

Applied: the constant is printed in the theorem statement in §6 and derived in
the appendix proof, which now names `\mathcal{N}` and `\mathcal{D}` so the
algebra is followable. The slack sentence the referee asked for is added after
the theorem, and it now points at the proved Proposition A1 rather than at a
measurement.

## RR-30 — "in rank order"

The proof step "the waiting jobs of rank above $i$ have no completed job of
still higher rank ahead of them" is order-dependent and the base policy did not
fix the order inside the short class. Applied: "then the short ones" → "then the
short ones in rank order" at the statement of the base policy.

**Measured note, for honesty:** the family's *value* does not depend on the
order. With the short class taken in reverse rank order the excess is still
`⌈B/k⌉` at every `(k, L, B)` tested, because every waiting job then has the same
`over` and `i` is still the minimum-rank member of `E` when it fires. The
referee's fix repairs the sentence, not a broken result.

## RR-31 — the floor

`(κ + 2k−2)L/k ≤ G ⟺ κ ≤ Gk/L − (2k−2)`, and `2k−2` is an integer, so the
largest admissible `κ` is `⌊Gk/L⌋ − (2k−2)`. Checked at `k ∈ {1,2,4}` over four
`(L,G)` pairs: the printed value satisfies the constraint and `κ+1` does not.

**Before**: "a promise $G$ admits $N = Gk/L - (2k-2)$ passes."
**After**: "a promise $G$ admits $\kappa = \lfloor Gk/L\rfloor - (2k-2)$ passes,
the largest integer with $(\kappa + 2k-2)L/k \le G$."

`05_scheduling.tex:221` carries the same expression and is another editor's file.

## RR-35 / RR-36 — conservation law, and the exchange argument

`grep -i "conservation law"` over `06_theory.tex` and `A_proofs.tex` returns
nothing, and returned nothing before this revision: the two files only ever say
"work conservation" / "work-conserving", which is the correct and unrelated
term and is kept. Nothing to remove there.

`theory.md` did carry it, in the document title and two headings, and they are
changed:

* "A **conservation law** for FCFS-relative delay …" → "A **pathwise identity**
  for FCFS-relative delay …"
* "Theorem 1 (**conservation of net overtaken work**)" → "Theorem 1 (**the
  net-overtake identity**)"
* "Corollary 1.1 (single server: **an exact conservation law**)" → "Corollary 1.1
  (single server: **the identity is exact**)"

RR-36: the inversion-sum step in §A.7 is now presented as an observation, with
the pointer the task asked for. `smith1956` **was** present in
`docs/related_work/refs.bib` when this work finished (the key was added by
another editor; the file grew from 70 to 90 entries), so it is cited rather than
left as a comment, and the citation resolves in the build. Text added:

> This is the standard exchange argument: at $k = 1$, where Theorem 1 is an
> equality, it says that the only way to beat first-come first-served in mean
> wait is to invert pairs whose later-ranked job is the shorter one, and that the
> saving is exactly the sum of the service differences over the inversions. That
> is the classical pairwise-interchange argument behind Smith's rule
> \cite{smith1956}, stated here on an arbitrary arrival sequence rather than on a
> single batch; we use it as an observation and claim nothing new in it.

## Positioning (Yu & Scully 2024; Yu et al. 2025)

Checked with `grep -niE "novel|for the first time|we are not aware|is new"` over
both files: no hit, before or after. Neither file claimed that budgeting work
rather than counting is itself new, and none was introduced.

One heading did assert more than the mathematics does now that RR-3 is applied:
"Necessity, and why positions are the wrong currency" → "Necessity, and What a
Count of Overtakes Costs". Remark 2 now states the count result as a
quantitative comparison (`L/C̄` looseness), not as a disqualification.

The four things the two files do claim as this paper's own — a two-sided per-job
identity on arbitrary sample paths with an exact constant for `k` servers, the
necessity direction, an online wrapper around any base policy, and exact
tightness — are all stated as results, not as priority claims, and are left
alone. The related-work framing is another editor's file.

## Cross-editor items from the literature editor

1. **Applied.** `06:48–52` co-cited `daley1987fcfs,kiefer1955queues` for "the
   extremal properties of first-come first-served for the unfinished-work
   vector". Split, and the majorization result is no longer stated
   unconditionally. **After**: "The unfinished-work vector of a $k$-server queue
   obeys the Kiefer--Wolfowitz recursion~\cite{kiefer1955queues}, and first-come
   first-served minimises that vector in the weak-majorization order for systems
   in which arrivals are allocated to servers in a manner that does not depend
   on their service times~\cite{daley1987fcfs}. The policies compared below are
   not restricted that way, so what carries the single-server argument to
   $k > 1$ here is a two-sided bound between two arbitrary policies rather than
   an ordering." Both keys verified present in `refs.bib`; the citations resolve
   in the build.
2. **Applied**, see RR-36 above: `smith1956` exists, so it is cited and the
   `% CITE-SMITH-1956` placeholder was removed.
3. **Nothing to do.** No Grosof–Scully–Harchol-Balter 2018 citation was added;
   `grep` confirms the key is absent from `refs.bib` and absent from both files.
4. **Already satisfied**, see the Positioning section above. Neither file
   presents measuring overtaking in work as new, before or after this revision;
   the one heading that overstated the count comparison was retitled.

## Writing rows

| row | before | after |
|---|---|---|
| RR-54 (`06:153`) | "looks like an artefact of the proof, and it is not, although neither search nor real input shows it" | "is not an artefact of the proof, although neither search nor real input reaches it" |
| RR-55 (`06:179`) | Remark title "The two directions are not alike" | "The upward and downward extremes have different content" |
| RR-56 (`06:200`) | "Theorem~\ref{thm:identity} also runs backwards." | "Theorem~\ref{thm:identity} has a converse." |
| RR-57 (`06:413`) | "When the guard is invisible" | "When the Wrapper Changes Nothing" |
| RR-58 (`06:521`) | "and empty when it is not" | "and says nothing when it is not" |
| cut (`06:403`) | "…are saturated on the same instance, **which is what makes the composition tight rather than each part separately**, and the excess is real waiting time…" | clause deleted |

Improved beyond the referee's wording where the referee's own sentence repeated
a frame the report elsewhere asks to thin: Remark 2's opening and closing were
rewritten rather than patched, and the closing sentence I had first added
("the claim against a count is quantitative and one-sided…") was removed again
as a restatement of the opening.

## New files

* `evidence/guard_theory/rev5_items.py` — pure Python, `sim_core.py` only, no
  third-party package. Sections RR-1, RR-2, RR-4, RR-7, RR-8, RR-19, RR-25,
  RR-26, RR-30, RR-31.
* `evidence/guard_theory/out_rev5_items.txt` — its log.
* `evidence/guard_theory/CHANGES_rev5.md` — this file.

`evidence/guard_theory/README.md` and `theory.md` §9 both list the new script.

## Not done, and why

* `09_limitations.tex:45–47` repeats the over-general Impossibility sentence.
  Another editor's file; flagged here for the integrator, with the replacement
  wording: "…on some job by any wrapper of this family whose budget is positive
  at the first dispatch epoch, whatever base policy it is given".
* `outputs/paper_tables/numbers.csv` rows `06_theory:157:0` and `06_theory:158:0`
  are stale after RR-5. Generated artefact, not mine.
* Page count rose from 46 to 49 in the scratch build (which also contains the
  other two editors' in-flight changes). Proposition A1, the expanded
  Proposition 7(i), the Impossibility paragraph and the explicit Remark 3
  instance account for roughly a page and a half of that. Part G of the report
  proposes ~7.9 pages of cuts, none of them in the material added here.
