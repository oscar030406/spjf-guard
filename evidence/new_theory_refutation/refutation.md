# Refutation attempt: fluid comparison, absolute bound, clock rule, guard-or-clock union

Question: do L1, P-abs, P-clock and P-union in `evidence/timeout_rule/draft_clock_main.tex` and `evidence/timeout_rule/draft_clock_and_envelope_proofs.tex` survive a line-by-line reading against the paper's model and an adversarial search?
Paper items: Lemma `lem:fluid`, Proposition `prop:absolute`, Corollary `cor:absolute`, Proposition `prop:clock` and the union paragraph (supplement draft lines 97-105, main draft lines 40-43).
Inputs: no data; synthetic integer instances only. No sealed data opened.
Status: L1 and P-abs verified; P-clock verified with one wording fix; P-union refuted as written, corrected statement below.

## Verdicts

| Statement | Verdict | One-line reason |
|---|---|---|
| L1 | VERIFIED | Proof read line by line and correct; 0 violations exhaustive, random and exact-breakpoint cross-check. |
| P-abs (and FCFS corollary, operator rule) | VERIFIED | Follows from eq. (busy), L1 at the pre-arrival reading, Theorem 3; 0 violations; equality attained at k = 1. |
| P-clock | VERIFIED, wording fix required | Holds when "oldest" means minimum rank (arrival time, input index). Breaks by a factor up to 16.7 if same-instant ties are left to the base policy. |
| P-union | REFUTED as written | With job-dependent budgets (gamma > 0 or eta > 0), a union that serves the guard's pick while the head is aged breaks the clock bound. Head-first union keeps both bounds, lost reports included. |

## Files

| File | Origin | Role |
|---|---|---|
| `refute_sim.py` | first run, reused | numba simulator: exhaustive enumeration of every base-policy choice sequence, random bursty phase, 17 checks. Rerun the second run. |
| `out_refute_exhaustive.txt/json`, `out_refute_random.txt/json` | rerun in the second run | Text identical to the first run's except timings (diffed against the first run's copy). |
| `refute_extras.py`, `out_refute_extras.txt/json` | first run, rerun | sigma check, FCFS vs cyclic assignment search, clock supremum family. Output identical. |
| `refute_witness.py`, `out_refute_witness.json` | first run, reused, not rerun | Shrunk witnesses of the random phase. Every witness replayed independently below. |
| `refute_crosscheck.py`, `out_refute_crosscheck.txt/json` | new | Independent pure-Python simulator (exact fractions, no code shared with `refute_sim.py`): witness replay, both union readings, eta budgets, delta = infinity, L1 at every breakpoint. 20,000 instances x 4 bases x 7 rules. |
| `refute_eta_witness.py`, `out_refute_eta_witness.txt/json` | new | Smallest found union counterexample with the age-relative shape. |

Commands, from the repository root, each with `env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME NUMBA_NUM_THREADS=4 OMP_NUM_THREADS=4 uv run --no-sync python`: `evidence/new_theory_refutation/refute_sim.py exhaustive`, `... refute_sim.py random`, `... refute_extras.py`, `... refute_crosscheck.py`, `... refute_eta_witness.py`.

## Model fidelity

Both simulators follow `paper/sections/03_problem_model.tex:28-31`: rank = (arrival, index); at one instant completions, then arrivals, then dispatches; a phase is the ordered list of dispatches at one instant (`06_theory.tex:39-48`). Delayed reports are credited to jobs still waiting at report time. `refute_sim.py` checks its FCFS against an independent start-time recursion on every instance (flag in check 14) and asserts the busy-period identity `k W = R + In - Out - rho` exactly on every FREE run: 0 failures (`out_refute_exhaustive.txt:16,34,52`, `out_refute_random.txt:2-5`, IDENT). `refute_crosscheck.py` checks feasibility (non-preemptive, <= k busy, no idle server while a job waits) of every schedule it produces.

Search space. Exhaustive: k = 1, 2, 3; n = 1..6; sizes {1,2,3}; L = 3; arrivals nondecreasing in 0..4 with a_1 = 0 (shift-invariant); 112,152 instances per k, and every dispatch where the rule leaves a choice branches over every waiting job, so all deterministic, clairvoyant and randomised base policies are covered; 53.0-55.7 million runs per k over 34 rule settings (theta in {0, 0.5, ..., 4}, B in {0,1,3,6,9}, gamma in {0,1,2,3}, delta in {0,2,3,4}) (`out_refute_exhaustive.txt:1,19,37`). Random: 320,000 bursty instances, k = 1..4, n <= 40, L in {3, 10, 24}, same-instant groups, theta in {0, 1/2, L, L + 1/2, random half-integers}, 5 bases (random x3, SJF, LJF, youngest, small-youngest) (`out_refute_random.txt:1`). Cross-check: 20,000 instances, n <= 18, L in {3,4,10}, budget shapes constant / gamma / eta / gamma+eta, delta in {0, 7, infinity}.

## L1 (fluid comparison): VERIFIED

Proof, supplement draft lines 15-24. Between arrivals D = U - V has slope (k - busy) while V > 0 and slope -busy when V = 0, so: D > 0 and V > 0 gives slope >= 0; V = 0 gives D = U >= 0; if D > (k-1)L then U > (k-1)L, at least k jobs are present, all k servers busy, slope 0 (V > 0) or -k (V = 0). Arrivals shift U and V equally. Each step checks. The reading at a_i "after the arrivals of rank below i and before i's own" (lines 26-33) is legitimate: no dispatch happens between same-instant arrivals, and at that point U = R_i as defined in `06_theory.tex:88-91`.

Search: 0 violations of either side, exhaustive and random (`out_refute_exhaustive.txt:3-4,21-22,39-40`; `out_refute_random.txt:2-5`, L1UP, L1LO) and in the exact cross-check that evaluates D at every arrival, start, completion and fluid-emptying instant (`out_refute_crosscheck.txt`, line `L1`).

Worst observed (U - V)/((k-1)L): k = 2: 0.850, k = 3: 0.667, k = 4: 0.583 (random); cross-check 0.75, 0.556, 0.483. The constant is not shown tight; I found no construction approaching (k-1)L for k >= 3. The paper's two-policy Lemma `lem:gap` is strict with a cascade; whether that cascade transfers to the fluid is UNVERIFIED.

### Wolff 1987 and whether L1 falls under it

Read: Cambridge Core abstract page of Wolff (1987), J. Appl. Prob. 24(2) 547-551, doi 10.2307/3214279: "Previously derived sample path upper bounds for multi-channel work in system and work in queue are shown to be false." Its reference list on that page: Wolff (1977) "An upper bound for multi-channel queues", J. Appl. Prob. 14(4) 884-888; Loulou (1983) "Two sample-path inequalities for G/G/k queues", INFOR 21, 136-144; Wolff (1984). Brumelle (1971) is not in that list; judging by the list, the refuted bounds are Wolff 1977's and Loulou 1983's, not Brumelle's. Wolff 1977's abstract: performance measures of the multi-channel queue "are shown to be bounded above by corresponding quantities for one or a collection of single-channel queues". I did not read either full text; that the collection is cyclic assignment (job j to single queue j mod k) is my inference, not a quote.

What that family of statements looks like when false: `refute_extras.py` finds, at k = 2, arrivals all 0, sizes (2,1,1,2), that FCFS work in system at t = 3 is 1 while cyclic assignment's is 0 (`out_refute_extras.txt:4`); similar for work in queue and per-job delay (lines 2-7). Those are sample-path orderings between two systems with no additive slack.

L1 is a different statement: an additive envelope around the rate-k fluid with slack (k-1)L, which is vacuous without the service cap. The lower side V <= U is the direction nobody refuted. The same search that finds the Wolff-type orderings false finds no L1 violation for FCFS over the same instances (`refute_extras.py` records key `L1_fcfs`; none printed). L1 does not fall under Wolff's refutation, and there is no instance to give.

## P-abs (absolute bound): VERIFIED

Supplement lines 35-59. `k W <= R + In` from eq. (busy) (`06_theory.tex:116-119`) with Out, rho >= 0; `R <= V^- + (k-1)L` from L1; under FCFS In = 0; under Algorithm 1 `In < B_max + kL` is Theorem 3 (`06_theory.tex:242-255`, which covers every budget rule with 0 <= budget <= B_max). Arithmetic: (V + (k-1)L + B + kL)/k = (V + B)/k + (2 - 1/k)L. The sigma step is strict (V^- <= sigma - C_i < sigma). The k = 1 remark (V^- = W_FCFS, and the bound equals Theorem 3's) and the "pays 2(k-1)L again" remark check out (in wait units the gain is 2(k-1)L/k).

sigma: the recursion's maximum equals the brute-force largest excess of arrived work over k times the length of a closed window [s, t]: 0 mismatches in 20,000 trials (`out_refute_extras.txt:1`). The closed window matters: same-instant bursts at both ends count.

Operator rule `B_max = kD - sigma - (2k-1)L` gives W < D exactly by substitution, provided B_max >= 0 and the period's realised sigma does not exceed the one assumed. The second condition is an assumption on the arrivals, not part of the proof; the draft says "expects", which is the right strength.

Search: 0 violations of `kW <= V^- + (k-1)L + In` for every policy, of `W_FCFS <= (V^- + (k-1)L)/k`, and of the guarded form (exhaustive, random, cross-check including gamma and eta shapes). Worst ratios in the table below.

## P-clock (Timeout(theta)): VERIFIED with a wording fix

Proof, supplement lines 86-95, checked:
- Every overtaker of i starts in [a_i, a_i + theta): it has rank above i, so arrives at or after a_i; from a_i + theta the head (rank <= i) is aged and is served. This needs "waited at least theta" (>=); with > the interval closes and In <= k(theta + L) loses strictness.
- Per server, overtakers occupy disjoint intervals inside [a_i, a_i + theta + L), total < theta + L. The sentence "ends before its start plus L" should read "no later than"; the half-open interval carries the strictness.
- "Corollary 1 turns this into the first bound": Corollary 1 (`06_theory.tex:137-142`) is stated with <= and gives only `excess <= theta + (3-2/k)L`. The strict form needs Theorem 1 applied to the strict In bound. Replace the reference.
- No-overtaker case: excess <= (2 - 2/k)L < theta + (3 - 2/k)L; kW <= V + (k-1)L. Correct.
- theta = 0 gives In = 0, i.e. FCFS: consistent.

Wording fix required. "Oldest" must be the minimum-rank waiting job. If jobs of equal arrival time are treated as equally old and the base policy picks among them, the proof's step "serves a job older than i" fails for same-instant arrivals of higher rank. Counterexample (exhaustive, `out_refute_exhaustive.json`, TIEIN k = 1): k = 1, L = 3, theta = 0, six jobs at t = 0, sizes (1,3,3,3,3,3); the base serves jobs 1..5 first; job 0 waits 15, W_FCFS = 0, In = 15 against k(theta + L) = 3, ratio 5.0. In the random phase the ratio reaches 16.7 at k = 1, 9.1 at k = 2 (`out_refute_random.txt:2-5`, TIEIN/TIEEX). An implementation that breaks equal ages by score does exactly this. Write "the waiting job of minimum rank (earliest arrival, then input index)".

Search with the rank reading: 0 violations of In < k(theta + L), of W < W_FCFS + theta + (3-2/k)L and of W < V^-/k + theta + (2-1/k)L, across all bases including clairvoyant ones via enumeration, theta = 0 and half-integers, sizes exactly L, same-instant bursts.

Heterogeneous speeds: the drafts do not claim them; the L1 step "all k servers busy, U falls at rate k" uses identical unit-rate servers. Not checked.

## P-union (guard or clock): REFUTED as written

The drafts say firing on either rule keeps both bounds "because each proof reads only its own condition" (main draft lines 40-43, supplement lines 101-105), without saying which job is served when the guard fires on q while the head is aged and not in E.

Guard-first reading (serve min-rank of E if E is non-empty, else the head if aged, else the base): the clock half fails whenever budgets differ between jobs, because the guard can then serve a younger job while the aged head waits.

Witness 1, queue-length shape (`out_refute_witness.json`, key "GFEX k=1", found by the first run; replayed here by `refute_crosscheck.py` from its own simulator). k = 1, L = 3, theta = 3.5, budget = min(3 n_q, 5) (gamma = 3, B_0 = 0, B_max = 5). Arrivals (0,0,0,2,2,2), sizes (1,1,1,3,1,3). Budgets: jobs 0..5 get 0, 3, 5, 3, 5, 5. Base serves 0, 1, then 4 at t = 2 and 5 at t = 3. At t = 6: over[2] = over[3] = 4, head job 2 has waited 6 >= 3.5 but 4 < 5, job 3 has 4 >= 3 and is in E. Guard-first serves job 3; job 2 starts at 9. W = 9, W_FCFS = 2, excess 7 >= theta + L = 6.5 (ratio 1.077). The guard bound B_max/k + (3-2/k)L = 5 + 3 = 8 holds. Head-first on the same base choices: job 2 starts at 6, maximum excess 4 (`out_refute_crosscheck.txt`, lines "GFEX k=1 under ..."). The schedule is feasible and W_FCFS and V^- recompute to the witness's values.

Witness 2, age-relative shape (`out_refute_eta_witness.json`). k = 1, L = 3, theta = 0, budget = min(k t_age / 4, 6) (eta = 1/4, B_0 = 0). Arrivals (0,1,2), sizes (2,3,3), base SJF. At t = 2 the head (job 1, age 1, budget 1/4, over 0) is aged but not fired; job 2 (age 0, budget 0) is fired; guard-first serves job 2; job 1 waits 4 against W_FCFS = 1, excess 3 >= theta + L = 3. Head-first: excess 0.

Frequency. `refute_sim.py` random phase, gamma shapes: 11 violations at k = 1, worst 1.077 (`out_refute_random.txt:2`, GFEX, GFIN). Cross-check, eta shape, guard-first: clock excess violated 1,055 times at k = 1 (worst 1.8) and 4 at k = 2 (1.11); In bound at every k (worst 1.8, 1.8, 1.0, 1.43) (`out_refute_crosscheck.txt`, lines `k=* union_guard/eta`). No violation under constant budgets: there over[q] is non-increasing in rank (`05_scheduling.tex:85-87`), E is a prefix, and the two readings coincide.

Is the witness a counterexample to one of the four statements? Yes, to P-union's clock half, inside the paper's own budget family (Algorithm 1 admits gamma, eta > 0), under the guard-first dispatch that the draft's wording and its justification allow. It is not a counterexample to L1, P-abs or P-clock, each of which it satisfies. The other entries of `out_refute_witness.json` are outside the four statements: "DGEX k=1..4" violate the guard's bound with late reports (delta = 28..72), which P-union does not claim (that is the stale-charging question); "TIEEX k=1..4" violate the clock bound under the arrival-time tie reading addressed in P-clock above. All nine were replayed as feasible with the stated excess (`out_refute_crosscheck.txt`, "witness" lines).

Corrected statement. Serve the minimum-rank member of E(t) union A_theta(t), with A_theta(t) = {waiting q : t - a_q >= theta}; since A_theta is a prefix, this is "the head if it has waited theta, otherwise Algorithm 1". Proof: when j is served ahead of a waiting i < j, either the base chose (both sets empty, so i is not in E), or j is the minimum of the union, so i is in neither set; either way i is not in E, which is all Theorem 3 uses. When the head is aged it is the minimum of the union and is served, which is all the clock proof uses. The clock half reads no report, so it holds for any delay. Search under this rule: 0 violations of both bounds at delta = 0 and of the clock bound at delta = 7 and delta = infinity, for constant, gamma, eta and mixed shapes (`out_refute_crosscheck.txt`, `union_head*` lines; `out_refute_random.txt`, CIN/CEX/CABS/GIN/GEX/GABS for UNION). Replace "each proof reads only its own condition" by this argument.

Not claimed and not holding: the guard's bound under late reports. Exhaustive, head-first union, delta > 0: In < B + kL violated 40,200 times at k = 2 and 11,340 at k = 3 (`out_refute_exhaustive.txt:33,51`); random, excess bound violated up to ratio 4.0 (`out_refute_random.txt:2-5`, DGEX, DGIN).

## Worst observed ratio to each bound (no violations unless stated)

Random phase of `refute_sim.py` (320,000 instances, `out_refute_random.txt:2-5`); exhaustive in brackets (`out_refute_exhaustive.txt`).

| Bound | k = 1 | k = 2 | k = 3 | k = 4 | Tight? |
|---|---|---|---|---|---|
| L1 upper, (U-V)/((k-1)L) | 0 (U = V) | 0.850 [0.833] | 0.667 [0.667] | 0.583 | not shown; looks loose for k >= 3 |
| P-abs, kW / (V^- + (k-1)L + In) | 1.000 [1.000] | 0.985 [0.857] | 0.962 [0.750] | 0.939 | attained at k = 1; near 1 for k = 2 |
| FCFS abs, kW_FCFS / (V^- + (k-1)L) | 1.000 | 0.982 | 0.938 | 0.909 | attained at k = 1 |
| Clock In, In / k(theta+L) | 0.996 | 0.996 | 0.995 | 0.995 | supremum: family with ratio 0.984, 0.990 at m = 16 (`out_refute_extras.txt:8-25`) |
| Clock excess | 0.996 | 0.829 | 0.780 | 0.756 | supremum at k = 1; (3-2/k)L looks loose for k >= 2 |
| Clock absolute | 0.998 | 0.945 | 0.899 | 0.865 | near 1 at k = 1, 2 |
| Guard In, In/(B+kL) | 0.992 | 0.996 | 0.997 | 0.998 | near 1 |
| Guard excess | 0.992 | 0.906 | 0.869 | 0.848 | Theorem 3, constants stated exact at `06_theory.tex:30-32` |
| Guard absolute, (V^-+B)/k + (2-1/k)L | 0.998 | 0.965 | 0.940 | 0.906 | near 1 at k = 1, 2 |

For k >= 2 the clock excess bound stacks two slacks (In < k(theta+L) and |Delta| < 2(k-1)L) that the search never realises together; the absolute form loses less.

## Changes the drafts need

1. P-clock: define "oldest" as minimum rank; ">=" theta; cite Theorem 1 (not Corollary 1) for the strict inequality; "ends no later than its start plus L".
2. P-union: state the dispatch rule (head first when aged, otherwise Algorithm 1) and replace "each proof reads only its own condition" by the two-line argument above. Without it the claim is false for the queue-length and age-relative shapes the paper uses.
3. L1: keep "<="; do not claim (k-1)L is exact without a construction.
4. Wolff 1987: cite it as refuting sample-path orderings against single-channel comparison systems (Wolff 1977, Loulou 1983); L1 is an additive envelope with the cap L and is proved directly.
