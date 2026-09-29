# 0005 The guard is one mechanism and the budget shape is a design freedom; three grids of equal density, winner chosen by the rule

Date 2026-09-20.

## Decision

The guard has a single mechanism: when the overtaking work `over[q]` exceeds the budget, a dispatch is forced. Its guarantee depends only on the cap

```
B_max = k (G - (3 - 2/k) L)
```

What the budget looks like below the cap is a design freedom, not another mechanism:

```
budget(q, t) = min(B0 + gam * (number of jobs waiting when q arrived) + eta * k * (t - a_q), B_max)
```

`eta = gam = 0` is a constant budget, `gam = 0` is a budget that relaxes with waiting time, and both positive is a budget that relaxes with queue length. The three shapes are written as three grids **written in advance** (`scheduling.selection.grids` in `configs/main.yaml`, with 42 / 162 / 54 points), and selected with the same rule:

- feasible: in **every cell** of five validation overlays × three load levels, the harm is ≤ G/2;
- objective: gap closed at the p99 of the deadline window, in the worst cell;
- ties: smaller worst-cell harm, then smaller `B0`, `eta`, `gam`.

The rule is run four times: once in each of the three families, giving three ablation rows (Guard-fixed / Guard-age / Guard-queue), and once more over the three families together; that winner is **Guard(G)** in the paper.

A constant budget carries its own promise `B0/k + (3 - 2/k)L`, which can exceed G, so a fixed point counts as a candidate for G only if **its actual promise in the worst cell is ≤ G**. That way the three families compare the same thing at the same G.

## Why

The independent review raised a CRITICAL against v3.1 (G1 in `prechecks/main_v31_verify/out_VERDICT.txt`): the fixed budget was picked from **four** values and the relative budget from **fifteen**, so the harm constraint was slack for the fixed family at its selected point, and part of the reported difference came from the different search densities and not from the mechanism.

There were two ways to fix it. One was to make the fixed family's grid denser and compare only two shapes. The other was to accept that the budget shape is a design freedom in the first place, add the third shape (the queue-length term), give all three grids equal density, and let the rule choose. We chose the latter because it states what is true: what the paper wants to claim is "this cap gives a per-job promise", not "the relative way of writing the budget is better than the constant way". Calling the winner Guard(G) and reporting the best point of each of the three families as ablation rows lets the reader see how much the shape actually buys.

## Cost

- Parameter selection goes from 15 points to 258 points, and one cell from about 190 seconds to about 20 minutes, about 5 hours for 15 cells. So each cell is written to disk as it finishes, runs can resume, and `--part/--nparts` can also split a cell.
- The queue-length term means the multiplicative form of the bound no longer applies: `(1-eta)W ≤ W_FCFS + B0/k + (3-2/k)L` is stated for a constant part that is **the same for every job**, whereas `B0 + gam w_q` differs from job to job. So when `gam > 0` only the additive form `W ≤ W_FCFS + B_max/k + (3-2/k)L` is claimed, which is exactly the defining expression of the promise G. In the code, `guard_upper_bound` follows this branch, and the per-job assertions still run.
- The simulator has to carry one more parameter. The kernel clamps the constant part `B0 + gam w_q` to the cap before writing it into the segment tree. This changes no schedule (the budget is taken as the min with the cap anyway), but it keeps the integer comparisons inside int64.

## What did not change

The formula for the cap, the ratio in the harm constraint (G/2), the objective and tie-break order, and the split between validation and test sets are all the same as in v3.1. The skip-type guard (Skip) is still a separate mechanism that counts dispatches, and is not in these three grids.
