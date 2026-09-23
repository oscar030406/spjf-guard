# Reservation-and-refund charging: the study

**Question.** Algorithm 1 charges a passing job the job limit `L`. If the platform
enforces a per-job runtime cap that is known at arrival, the guard could instead reserve
the cap and refund the unused part on completion (rule R). Does that rule keep the
per-job guarantee, by how much does it lower the additive constant, and is the resulting
allowance the largest safe one?

**Answer.** At `k = 1` the rule is clean and sharp: `In_i <= Z_i` and `excess <= B` held in
every exhaustive run, the safe allowance is `B* = G` rather than `G - L + 1`, and the
closed form for the family frontier is exact. The `kL` overshoot disappears, so the
additive constant drops from `(3-2/k)L` to `(2-2/k)L`; the residual `(2-2/k)L` survives
and is approached but not attained. At `k >= 2` pointwise maximality fails. Six
conjectures C1-C6 with their exact integer simulators and logs; `report.md` has the
verdicts.

**Paper items.** None are cited from this folder directly. The manuscript's supplementary
theory section quotes the independent re-check in `evidence/reservation_guard_verify/`,
which restated and re-ran these claims from a separate implementation; where the two
disagree the re-check governs. This folder is where the claims come from, and `report.md`
is what the re-check was run against.

**Inputs.** None. Exact integer simulation over enumerated instances; no dataset is read
and no sealed semester is opened.

**Status.** Superseded on the points where `evidence/reservation_guard_verify/` refutes or
qualifies it: read `verification.md` first, and this folder for the construction and the
counts.

Absolute paths that were baked into the scripts appear as `<repo-root>` (your checkout) and `<cache-dir>` (a scratch directory outside the repository); set both before rerunning. Raw data is not redistributed with this folder — see `data/README.md` for where each dataset comes from.

---

## Original study notes

Falsify-first study of the reservation-and-refund charging rule for Algorithm 1 (item 3 of the internal ideas list): exact integer simulators (rguard.py), per-conjecture run scripts run_c*.py with their logs out_*.txt, and the verdicts in report.md.
