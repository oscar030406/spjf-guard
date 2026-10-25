# The common run-time limit as a reservation cap

**Question.** Suppose that every job is given the cap `ell_j = L`, the time limit that the
service already enforces. Is reservation charging with the allowance `budget + kL` then at
least as permissive as Algorithm 1 at every state, at the same promise `G`? Does it keep
`G`?

**Answer.** Yes on every instance checked. No reachable state has a dispatch that
Algorithm 1 permits and the reservation rule refuses. The rule permits strictly more at up
to 12.9% of the states reachable under Algorithm 1 (k = 2, five jobs, G = 7), and this share
falls to 0 as `G` grows. Every run of either rule keeps the largest excess below `G`.

**Paper items.** Supplementary Section S7.6 (`paper/sections/S_theory_additions.tex`),
Proposition S16 and the paragraph after its proof; the sentence of Section 6.5 that the
limit `L` is such a cap; the sentence of Section 9 on a wrapper that overrides less often
at the same `G`.

**Inputs.** None. Exact integer simulation over enumerated instances: `L = 3`, costs in
{1, 2, 3}, arrivals in {0, 1, 2}, k = 2 with four and five jobs and k = 3 with five jobs,
every sequence of base-policy proposals, constant budgets at the four smallest integer
promises with a positive cap.

**Status.** Current. Run from this folder:

    python check_public_cap.py > out_check_public_cap.txt

The dispatch rules are imported from `../reservation_guard_verify/rguard_indep.py`
(`allowed_C` is Algorithm 1 with completed-work charging, `allowed_R` the reservation
rule). Each output row covers one `(k, n, G)` and one rule whose runs are enumerated. It gives
four things:

- the states visited
- the states where Algorithm 1's permitted set is not contained in the reservation rule's
  (`not_superset`)
- the states where the reservation rule permits more (`strictly_more`, and its share in
  percent)
- the largest excess over all runs
