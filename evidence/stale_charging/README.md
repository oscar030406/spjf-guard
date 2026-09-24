# Late completion charges: the guard when reports travel over a network

**Question.** Theorem 3 assumes that a completion is charged to the counter before the
next dispatch. In a distributed service a server may pull its next job before its report
arrives. If every charge arrives within delta of its completion, what does the guard
still promise, is the extra term tight, and which protocol restores Theorem 3?

**Paper items.** Proposition `prop:late` and the paragraph after it (Section 6.9); the
proofs, the lower-bound instances and the check summary in Supplementary Section S4.12;
the remark in Section 6.7 that the clock half of the combined rule survives late or lost
reports.

**Inputs.** None from `data/`. Synthetic integer instances only; no sealed data.

**Status.** Done. The bound In_i < B_max + kL + k(L + delta) holds with 0 violations on
2,273,660,361 exhaustively enumerated schedules (n <= 6) and 200,000 random instances.
The extra L + delta is attained in the limit at k = 1 and approached to within 0.2% at
k = 2 (ratios 0.9980 to 0.9987 at m = 8, L = 256); no limit argument is written for
k = 2. Report-before-pull keeps Theorem 3's constants for every delta, lost reports
included.

| File | What it is |
| --- | --- |
| `derivation.md` | the bound, its proof, the lower-bound instances, the per-server variant, the two mitigations and the union-rule check, with line references into the outputs |
| `sim_stale.py`, `out_sim_stale.txt` | lower-bound families, 200,000 random instances; the first run stops inside the exhaustive part |
| `out_sim_stale_exhaustive.txt`, `out_sim_stale_exhaustive_n6.txt` | the exhaustive enumeration, resumed, n <= 6 in full |
| `check_union_rule.py`, `out_check_union_rule.txt` | head-first against guard-first union under late charges |

Commands are at the top of `derivation.md`.
