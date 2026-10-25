# Closed-loop replay with abandonment and resubmission: report

Development overlays only. Model, parameters and the asserted reference: `MODEL.md`
(written before the first overlay run, unchanged). Grid: 15 primary cells (overlays 0-4,
levels 0-2) x 10 patience/coin combinations (infinite; mean 60/300/1800 s x p_resubmit
0/0.5/1; at most 3 resubmissions) x 6 policies (FCFS, SJF, SPJF-E, Guard(300/600/1200)):
900 rows in `out/cells.csv`. All levels and policies: `out/tables.md`.

## Commands (repository root, in order)

```sh
PY="env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME .venv/Scripts/python.exe"
$PY evidence/abandonment_loop/check_reference.py
bash evidence/abandonment_loop/gated.sh evidence/abandonment_loop/run_abandon.py validate
bash evidence/abandonment_loop/gated.sh evidence/abandonment_loop/run_abandon.py check-r1
bash evidence/abandonment_loop/gated.sh evidence/abandonment_loop/run_abandon.py run --reps 0 --levels 2 --combos 60:0.5 --out profile_combo.csv
bash evidence/abandonment_loop/run_grid.sh "2 1 0"
$PY evidence/abandonment_loop/make_tables.py
```

## Checks

(a) `out/validation.json`, overlay 0 level 2 k=4: with infinite patience the kernel
matches `closed_kernel.simulate_closed` (gating on, late kept) with max |diff| 0 us on
wait and realised arrival, and with gating off matches `spjf_guard.sim.simulate` with
max |diff| 0 us, for FCFS, SJF, SPJF-E, Guard(300), Guard(600), Guard(1200); run before
and after the open-arrival change, 0 both times. The 36 infinite-patience grid rows that
closed_loop also ran reproduce `closed_cells.csv` (closed, kept) with max |diff| 0.0 on
p99_dl_s, mean_s, max_s, max_excess_s, worst_ratio_to_bound (`out/consistency.log`).

(b) `out/check_reference.json`: 18,503 random integer instances compared (1,497 skipped:
8-slot window overflow, err = 1), 896 with window rebuilds, 0 mismatches on every per-job
output and on the abandon/resubmit/withdraw counts; 173,050 abandonments, 102,055
resubmissions, 70,995 withdrawals. R1 additive and multiplicative violations 0; R2 over
the bound on 156 instances (255 jobs). Mutation tests on scratch copies: strict fired
test gave 2 mismatches / 300, resubmission delayed by one unit 84 / 300.

(c) Reference R1 (FCFS without abandonment on the served attempts' realised arrivals) is
asserted via `guard_upper_bound`: 0 violations in all 450 guarded runs, worst W/bound
0.9511. R2 (FCFS with the same abandonment on first-attempt arrivals, user delay) is
descriptive: exceeded in 144 of 450 guarded runs, 8,484 jobs, all at p_resubmit > 0
(1,640 at 0.5, 6,844 at 1, 0 at 0). `out/check_r1.json`: the fast R1 FCFS equals
closed_loop's `fcfs_open_on` with max |diff| 0 us for the five non-FCFS policies.

## Profile

First level-2 combination: 124 s (> 90 s rule). Per policy: kernel 2.9 s, R1 via
`fcfs_open_on` 12.3 s, R2 1.6 s. R1 replaced by the k-server FCFS recursion (0.8 s,
checked equal); open-loop arrivals fed from a sorted index. Same combination after: 55 s;
the grid ran on all 15 cells; slowest row 18.3 s.

## Level 2 (k = 4), means over overlays 0-4 (max excess: worst overlay, vs R1)

| patience (s) | p | FCFS p99 | SJF p99 | SPJF-E gap | SPJF-E withdrawn | SPJF-E max exc | G600 gap | G600 withdrawn | G600 max exc | G600 W/bound | FCFS withdrawn |
|---|---|---|---|---|---|---|---|---|---|---|---|
| inf | - | 72.186 | 32.833 | 0.849 | 0 | 5,400.4 | 0.813 | 0 | 515.3 | 0.9033 | 0 |
| 1800 | 0 | 62.498 | 30.645 | 0.823 | 0.00058 | 3,410.5 | 0.786 | 0.00060 | 512.4 | 0.8925 | 0.00126 |
| 1800 | 0.5 | 65.819 | 31.551 | 0.835 | 0.00030 | 3,537.2 | 0.811 | 0.00031 | 518.7 | 0.8984 | 0.00066 |
| 1800 | 1 | 69.240 | 32.676 | 0.841 | 0.00000 | 4,774.8 | 0.818 | 0.00000 | 514.3 | 0.9103 | 0.00000 |
| 300 | 0 | 43.146 | 25.163 | 0.763 | 0.00257 | 1,450.0 | 0.756 | 0.00259 | 492.0 | 0.8546 | 0.00493 |
| 300 | 0.5 | 48.717 | 27.316 | 0.780 | 0.00150 | 1,775.1 | 0.769 | 0.00151 | 492.4 | 0.8514 | 0.00292 |
| 300 | 1 | 58.036 | 30.890 | 0.800 | 0.00002 | 1,836.7 | 0.786 | 0.00002 | 517.6 | 0.8766 | 0.00006 |
| 60 | 0 | 22.318 | 14.741 | 0.675 | 0.00753 | 312.5 | 0.677 | 0.00752 | 291.1 | 0.5065 | 0.01200 |
| 60 | 0.5 | 26.924 | 17.876 | 0.691 | 0.00492 | 399.9 | 0.683 | 0.00492 | 354.3 | 0.6140 | 0.00815 |
| 60 | 1 | 36.989 | 24.653 | 0.668 | 0.00027 | 421.2 | 0.680 | 0.00027 | 337.6 | 0.5987 | 0.00116 |

## Findings

- FCFS has the highest and SJF the lowest deadline-window p99 in all 150
  (overlay, level, patience, p) groups.
- The served-attempt p99 falls as patience shortens in 267 of 270 series; read it with
  the withdrawn fraction. On the 96 groups with >= 1,000 SPJF-E withdrawals,
  Guard(600)/SPJF-E withdrawn ratio 0.976-1.080 and SPJF-E/FCFS 0.208-0.709.
- At 60 s patience the gap closed by SPJF-E and Guard(600) is 0.681-0.727 (level 0),
  0.659-0.714 (level 1), 0.668-0.691 (level 2), against 0.81-0.85 with infinite patience.
- SPJF-E's worst excess falls to 312-421 s at 60 s patience and stays 1,450-4,775 s at
  300 and 1800 s; Guard(600)'s is 492-519 s in every level-2 combination.

## Limitations

- A mutation test (abandon only strictly past due) made the reference loop forever; not counted.
- Peak RSS was not measured; one process at a time behind a 76 GB committed-memory gate.
- Gap closed is the mean of per-overlay ratios; compare against the infinite-patience row
  here rather than across documents.
- MODEL.md section 9 applies: patience is stated, not measured.
