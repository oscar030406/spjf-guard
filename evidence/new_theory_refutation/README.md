# Refutation of the clock and absolute bounds

**Question.** Before Sections 6.7 and 6.8 entered the paper, an independent reader tried
to break them: the fluid-comparison lemma, the absolute bound, the maximum-waiting-time
bound and the rule that combines the clock with the guard. Which statements survive a
line-by-line reading and an adversarial search, and in what wording?

**Paper items.** Lemma `lem:fluid`, Proposition `prop:absolute` (Section 6.8),
Proposition `prop:clock` and the combined rule (Section 6.7), and the counterexamples and
check summary of Supplementary Section S4.11.

**Inputs.** None from `data/`. Synthetic integer instances only; no sealed data. The
text under test is `evidence/timeout_rule/draft_clock_main.tex` and
`draft_clock_and_envelope_proofs.tex`.

**Status.** Done. The fluid lemma and the absolute bound are verified. The clock bound is
verified when "oldest" means the waiting job of minimum rank; if equal arrival times are
left to the base policy it fails by up to 16.7 times at k = 1. The combined rule as first
written, serving the guard's fired job before an aged head, is refuted for budgets that
differ between jobs; serving the aged head first keeps both bounds, lost reports
included. The paper states the corrected forms.

`refutation.md` holds the verdicts, the search space, the witnesses and the table of
worst ratios, with a file-by-file provenance table. Two simulators share no code:
`refute_sim.py` (numba, exhaustive and random) and `refute_crosscheck.py` (pure Python,
exact fractions).
