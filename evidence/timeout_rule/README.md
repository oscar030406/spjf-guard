# Timeout rule: a clock against the work counter

Question: does a maximum waiting time (serve the oldest job once it has waited theta)
keep the guard's FCFS-relative promise, and what does it give up at the same promise?

Paper items: Proposition `prop:clock` and the charge comparison (Section 6.7), the
related-work sentence on maximum waiting times (Section 2), the introduction's
contribution bullet, Table `tab:clock` and the equal-promise comparison (Section 8.4),
and the check summary in Supplementary Section S4.11. `draft_clock_main.tex` and
`draft_clock_and_envelope_proofs.tex` are the first drafts of that text, the version the
refutation in `evidence/new_theory_refutation/` was run against.

Inputs: development overlays `data/derived/overlay_traces/primary_rep0..4.npz`, stored
expected-cost score (original clock, the optimistic reference of Table tab:guard).
No sealed data.

Status: done. Theory check passed; five-overlay comparison done (`out_summarise.txt`);
paired intervals in `timeout_intervals.csv`; the independent refutation in
`evidence/new_theory_refutation/` found the bound true under the minimum-rank reading of
"oldest" and false, by up to 16.7 times, when ties in arrival time go to the base policy.

| File | What it is |
|---|---|
| `theory_check.py`, `out_theory_check.txt` | exhaustive (k = 1, 2, n <= 4) and 200,000 random instances; the bound W <= W_FCFS + theta + (3 - 2/k)L and the FCFS sandwich from the fluid backlog |
| `timeout_overlays.py`, `out_timeout_overlays.txt`, `timeout_overlays.csv` | Timeout(G - (3 - 2/k)L) against Guard(G) and Fixed(G) on five overlays and three loads, plus a theta grid on overlay 0; its separate kernel is checked job for job against the package's FCFS and SPJF-E first |
| `summarise.py`, `out_summarise.txt` | means over overlays and paired Guard - Timeout differences |
| `timeout_intervals.py`, `out_timeout_intervals.txt`, `timeout_intervals.csv` | the paired week-block bootstrap intervals of Table `tab:clock` (2,000 resamples, seed 20260919), printed to six decimals; its Guard columns reproduce Table `tab:guard` |
| `draft_clock_main.tex`, `draft_clock_and_envelope_proofs.tex` | the first drafts of Sections 6.7-6.8 and their proofs, as audited |

Rerun from the repository root:

```bash
env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME uv run --no-sync python evidence/timeout_rule/timeout_overlays.py
```
