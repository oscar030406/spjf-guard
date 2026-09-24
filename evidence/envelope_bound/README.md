# Envelope bound: an absolute per-job wait bound from the arrival log

Question: does every job on the development traces wait less than the absolute bound of
P-abs, (V_i^- + B_max)/k + (2 - 1/k)L for guarded policies and (V_i^- + (k-1)L)/k for
FCFS; how well does one period's sigma predict the next; and what did anyone state
before about the fluid comparison (L1) and a maximum-waiting-time rule (P-clock)?

Paper items: Proposition `prop:absolute` and the operator rule
B_max = kD - sigma - (2k-1)L (Section 6.8, "An Absolute Bound from the Arrival Log",
first drafted in `evidence/timeout_rule/draft_clock_main.tex`); `sec:exp_bound` in
Section 8, including the sigma forecast and its margin;
the related-work sentence on maximum waiting times (`paper/sections/02_related_work.tex:28`);
the bibliography of the new text.

Inputs: development overlays only, `data/derived/overlay_traces/primary_rep0..4.npz`,
`validation_rep0..4.npz`, `k1_rep0.npz` (sha256 in `run_manifest.json`); configuration
`configs/main.yaml`. No sealed data.

Status: done. 0 per-job violations of the tight bound in 304 (overlay, level, policy)
rows; prior art written up; bibliography extended. The equality case at k = 1 (FCFS,
every job exactly on the bound) is reached.

## Results

Tight absolute bound (part a). `tight_bound.py` rescores the saved `envelope_bound.csv`
without simulating: each tight per-job bound is the old one minus a constant, 2(1 - 1/k)L
for work guards and (kG - (k-1+N)L)/k for Skip(G), so the tight minimum slack is the old
one minus that constant. No row needed a rerun (`out_tight_bound.txt:306-308`).
`verify_tight_cell.py` reran the smallest-slack primary cell job by job in int64
microseconds and reproduced the subtraction to the microsecond: overlay 3, level 2, k = 4,
Fixed(300) min slack 44.004822 s, Guard(300) 44.005647 s, 0 violations over 17,634,760
jobs (`out_verify_tight_cell.txt:1-2`; same values in `tight_bound.csv`).

| Family | Overlays | Level (k) | Rows | Max wait / bound | Min slack (s) | Violations |
|---|---|---|---|---|---|---|
| FCFS | k1_rep0 | 0 (1) | 1 | 0.9990 | 0.000 | 0 |
| FCFS | primary | 0 (7, 8) | 5 | 0.8807 | 39.538 | 0 |
| FCFS | primary | 1 (5) | 5 | 0.9446 | 36.649 | 0 |
| FCFS | primary | 2 (4) | 5 | 0.9653 | 32.545 | 0 |
| work guards | k1_rep0 | 0 (1) | 15 | 0.9759 | 4.865 | 0 |
| work guards | primary | 0 (7, 8) | 75 | 0.8860 | 68.480 | 0 |
| work guards | primary | 1 (5) | 75 | 0.9506 | 46.335 | 0 |
| work guards | primary | 2 (4) | 75 | 0.9625 | 44.005 | 0 |
| Skip | k1_rep0 | 0 (1) | 3 | 0.8263 | 204.914 | 0 |
| Skip | primary | 0 (7, 8) | 15 | 0.6519 | 238.021 | 0 |
| Skip | primary | 1 (5) | 15 | 0.7956 | 238.184 | 0 |
| Skip | primary | 2 (4) | 15 | 0.8521 | 218.719 | 0 |

Source: `out_summarise_tight.txt:3-14`; per row in `tight_bound.csv` and
`out_tight_bound.txt:1-305`. "Work guards" are Guard, Guard-fixed, Guard-age, Guard-queue
and Fixed at G = 300, 600, 1200 s, all with B_max = k(G - (3 - 2/k)L), L = 60 s. At k = 1
the FCFS rows sit on the bound for every job (3,209,347 ties, `envelope_bound.csv` row
k1_rep0 FCFS), as P-abs predicts. At k = 1 the tight and old bounds coincide (shift 0) and P-abs
reduces to Theorem 3.

Sigma forecast (part b), from `envelope_sigma_validation.csv`, validation sigma computed at
the primary k of each level (`out_tight_bound.txt:310-336`). The paired validation sigma
ranges from 0.738 to 1.573 times the primary sigma and falls short in 10 of 15 cells. To
cover every cell from its own validation overlay an operator would have needed a factor
1.3555 on sigma, or an additive margin on the promised deadline of 42.9 s at level 0,
180.7 s at level 1 and 408.8 s at level 2 (sigma shortfall / k). Taking the largest of the
five validation sigmas covers the largest primary sigma at levels 0 and 1 but not at level
2 (6197.0 against 6234.5 s of work). Quoting D from the paired validation sigma, the
realised maximum wait reached or passed the quote in 18 of 60 (overlay, level, policy)
rows for FCFS and Guard(300, 600, 1200), by up to 349.8 s (overlay 0, level 2, FCFS) and
298.3 s for a guard (overlay 0, level 2, Guard(1200)). At level 0 the validation overlays
of rep 0 and 3 have their own k = 7 against 8 on primary, and rep 4 the reverse; the
forecast above uses the primary k.

Prior art (part c): `prior_art.md`. L1's upper half is the all-jobs-relevant case of
Lemma 5.2 of Grosof, Scully and Harchol-Balter (SRPT-k, preemptive); no source read states
L1 for every non-preemptive work-conserving policy or the FCFS consequence with sigma. No
pathwise per-job bound of a maximum-waiting-time rule relative to FCFS was found; the
nearest is the Boost argument of Li et al. (2026, App. A.2), M/G/1 only. L1 does not fall
under Wolff (1987). The same file records that the speed-k control in
`docs/related_work/references_verified.md` (R2-6, "数值旁证") was built wrong
(`out_l1_check.txt:1-5`).

Bibliography (part d): `bib_entries.bib`. Added in the second run: brumelle1971inequalities,
wolff1977upper, wu2023fastserve, luo2025autellix, openpbs2021starving; the key
leboudec2001netcal was renamed leboudec2001network to match `draft_clock_main.tex:55`.
Entries already in `docs/related_work/refs.bib` are listed in the file header.

## Files

| File | Origin | What it is |
|---|---|---|
| `envelope_bound.py`, `out_envelope_bound.txt`, `envelope_bound.csv`, `envelope_sigma_validation.csv`, `run_manifest.json` | first run, reused | simulations on 5 primary overlays x 3 levels x every configured policy, plus k1_rep0; per-job check of the older, looser bound; sigma on validation overlays; sha256 of script, config, inputs, outputs |
| `tight_bound.py`, `out_tight_bound.txt`, `tight_bound.csv` | first run, reused | parts a and b: rescoring under the tight bound, sigma forecast |
| `verify_tight_cell.py`, `out_verify_tight_cell.txt` | first run, reused | direct rerun of the smallest-slack primary cell under the tight bound |
| `summarise_tight.py`, `out_summarise_tight.txt` | second run | per family and level summary of `tight_bound.csv` (the table above) |
| `l1_check.py`, `out_l1_check.txt` | first run, reused | L1 on small exact instances, and the recheck of the speed-k control |
| `tightness_examples.py`, `out_tightness_examples.txt` | first run, reused | hand-built bursts: FCFS last wait minus sigma/k is -1 to -0.5 s in family A and +14 to +14.9 s in family B, against (1 - 1/k)L = 30 to 52.5 s |
| `envelope_bound_probe.py`, `envelope_bound_probe.log`, `inspect_npz.py`, `out_inspect_npz.txt` | first run | first probe on overlay 0 with the old bound; npz field listing |
| `crossref_check.py`, `out_crossref_check.txt`, `out_crossref_check_resume.txt` | first run; second printout in the second run | Crossref fields for every DOI in `bib_entries.bib` and `prior_art.md` |
| `bib_entries.bib` | extended in the second run | BibTeX with x-verified fields |
| `prior_art.md` | second run | part c |

## Rerun

From the repository root (the simulation took 4377 s, `out_envelope_bound.txt:469`; the rest take seconds):

```bash
env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME NUMBA_NUM_THREADS=4 OMP_NUM_THREADS=4 \
    uv run --no-sync python evidence/envelope_bound/envelope_bound.py > evidence/envelope_bound/out_envelope_bound.txt
env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME uv run --no-sync python \
    evidence/envelope_bound/tight_bound.py > evidence/envelope_bound/out_tight_bound.txt
env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME uv run --no-sync python \
    evidence/envelope_bound/summarise_tight.py > evidence/envelope_bound/out_summarise_tight.txt
```

sha256 on 2026-09-23: `envelope_bound.csv` be23f8d9...c7940 (matches `run_manifest.json`),
`envelope_sigma_validation.csv` 23154a06...6ec75 (matches), `tight_bound.csv`
fd16d2f6...b4b62.
