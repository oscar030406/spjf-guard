# Reservation-and-refund charging: the independent re-check

**Question.** Do the verdicts of `evidence/reservation_guard/report.md` hold when the rule
is reimplemented from its written definition alone, by a check that does not read the
original simulator?

**Answer.** Mostly, with three corrections and three refutations. Rule R was rewritten in
`rguard_indep.py` from the prose of `report.md`, importing nothing from
`evidence/reservation_guard/` or `evidence/guard_theory/`. At `k = 1` the bounds held
across 10.2 million per-job checks with no violation, the maximality claim survives and is
strengthened, and reservation and refund are shown to be idle there — `overR` equals
`overC` at `k = 1`, so the working part of the test is the single look-ahead term. At
`k >= 2` maximality is refuted by explicit counterexamples, and one claim recorded as open
is shown to be false. The verdict section recommends the supplement rather than the main
text, and names the conservative-backfilling literature the mechanism belongs to.

**Paper items.** The supplementary theory section of
`paper/sections/S_theory_additions.tex`: the three readings and the corrected definition
pointer (`verification.md` Section 4), the decision-table rows C1-a to C1-f, C2-a to C2-c,
C3-d and C6-c, the `k = 1` reading counts in `out_overR_eq_overC_k1.txt`, and the witness
runs in `out_c1b_indep.txt`, `out_c2b_indep.txt` and `out_c4b_indep.txt`.

**Inputs.** None. Exact integer simulation over enumerated instances; no dataset is read
and no sealed semester is opened.

**Status.** Current. `verification.md` governs wherever it disagrees with
`evidence/reservation_guard/report.md`. Its Sections 5 and 6 list the sentences the paper
may and may not state. The notes are in Chinese; the decision table and the log files are
readable without it.

Absolute paths that were baked into the scripts appear as `<repo-root>` (your checkout) and `<cache-dir>` (a scratch directory outside the repository); set both before rerunning. Raw data is not redistributed with this folder — see `data/README.md` for where each dataset comes from.

---

## Original study notes

Independent adversarial re-check of the reservation-and-refund rule R: own simulator (rguard_indep.py), logs out_*.txt, verdicts in verification.md.
