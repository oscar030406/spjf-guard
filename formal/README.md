# Lean 4 proofs of the theory results

This directory contains Lean 4 proofs of the main results in the theory section of the paper.
The proofs use the Mathlib library.

## Files

| File | Content |
|---|---|
| `Overtake.lean` | The model, and the results from Lemma "Workload comparison" to Corollary "A work budget is necessary" |
| `Guard.lean` | The results from Theorem "Guard bound" to Theorem "Price of the guarantee". This file imports `Overtake.lean`. |
| `lean-toolchain`, `lakefile.toml`, `lake-manifest.json` | The Lake project. These files fix the versions of Lean, Mathlib and the packages that Mathlib uses. |
| `compile_output.txt`, `Guard_compile_output.txt` | The compiler output of a Linux run on 2026-10-07 |
| `windows_compile_output.txt`, `windows_Guard_compile_output.txt`, `windows_leanchecker.txt` | The compiler output and the `leanchecker` output of a Windows 11 run on 2026-10-19 |

## Versions

- Lean `v4.35.0-rc4`, from `lean-toolchain`.
- Mathlib tag `v4.35.0-rc4`, from `lakefile.toml`. The tag is commit `1f414401f69059aa7eead47b53ee40bd38455eeb`, and `lake-manifest.json` records this commit.

## Requirements

- [elan](https://github.com/leanprover/elan), the Lean version manager. At the first `lake` command in this directory, elan installs the Lean version from `lean-toolchain`.
- `git` and `curl`.
- A network connection. The first command downloads Mathlib, eight other packages and 453 MB of compiled Mathlib files (9,004 archives).
- At least 12 GB of free disk space. On Windows, the build used 7.4 GB in `.lake`, 453 MB in the cache directory of Mathlib and 3.3 GB for the Lean toolchain.
- At least 8 GB of RAM. The largest `lean` process used about 7 GB on Linux (resident set size) and about 3.5 GB on Windows (peak working set).

## Build

Run these two commands in this directory:

```sh
lake exe cache get
lake build
```

The first command downloads Mathlib and its compiled files.
Thus `lake build` does not compile Mathlib.
The second command checks `Overtake.lean` and then `Guard.lean`.

On a Windows 11 computer with 24 logical processors, the first command took 8 minutes and the second command took 1 minute.
The cache directory of Mathlib was empty before the first command.
The download time depends on the network.

## Expected output

`lake build` shows no errors and ends with this line:

```text
Build completed successfully (9022 jobs).
```

The output also has 49 lines of the form below, 18 lines for `Overtake.lean` and 31 lines for `Guard.lean`:

```text
info: Overtake.lean:2246:0: 'Overtake.workload_comparison' depends on axioms: [propext, Classical.choice, Quot.sound]
```

These lines come from the `#print axioms` commands at the end of the two files.
Each line lists only `propext`, `Classical.choice` and `Quot.sound`, the three standard axioms of Lean and Mathlib.
If a proof used `sorry`, its line would also list `sorryAx`.

The output also has 52 warnings.
Lean gives 51 linter and deprecation warnings, and Lake gives 1 warning about the module system.
These warnings do not change the proofs.

If you run `lake build` again, Lake does not check the files again.
It shows the same 49 lines from its log.

To see the compiler output for one file, run one of these commands after `lake build`:

```sh
lake env lean Overtake.lean
lake env lean Guard.lean
```

The output is the same as `compile_output.txt` or `Guard_compile_output.txt`, except for the file paths and the two last lines (time and exit status).

## More checks

The command below shows no lines.
Thus the two files contain no `sorry`, `admit`, `axiom`, `native_decide`, `implemented_by` or `extern`.

```sh
grep -nwE 'sorry|admit|axiom|native_decide|implemented_by|extern' Overtake.lean Guard.lean
```

The command below checks all declarations of the two files again with the Lean kernel.
It ends with exit status 0 after about 35 seconds.

```sh
lake env leanchecker Overtake Guard
```

## Model

- `Input` is a finite set of jobs with arrival times and costs, `k ≥ 1` servers and a time limit `L > 0`. The paper states only `0 < C_i ≤ L`.
- `Sched` is a non-preemptive, work-conserving schedule of an input. The run of a policy gives a `Sched`. This is also true for a policy that knows the future.
- Each theorem holds for every `Sched` that satisfies its hypotheses.
- A policy is a condition on a `Sched`, for example `IsFCFS` or `Sched.IsGuard`. The files do not prove that a schedule with such a condition exists for every input.

## Lean names and paper results

All names are in the namespace `Overtake`.

### Overtake.lean

| Paper result | Lean name | Note |
|---|---|---|
| Lemma "Workload comparison": the bound `(k-1)L` | `workload_comparison` | |
| Lemma "Workload comparison": strict bound for `k ≥ 2` | `workload_comparison_strict` | The proof differs from the paper proof. |
| Lemma "Workload comparison": for `k ≥ 2`, the difference comes arbitrarily close to `(k-1)L` | `workload_comparison_approached` | |
| Lemma "Workload comparison": both sides are 0 for `k = 1` | `workload_comparison_k1` | |
| The equation `k W_P[i] = R^P_i + In_i - Out_i - β^P_i` | `Sched.busy` | |
| Theorem "Net-overtake identity" | `identity` | |
| Theorem "Net-overtake identity": the bound `2(k-1)L` | `identity_bound` | |
| Theorem "Net-overtake identity": strict bound for `k ≥ 2` | `identity_bound_strict` | |
| Theorem "Net-overtake identity": the form with `(2 - 2/k)L` | `identity_bound'` | |
| Theorem "Net-overtake identity": the case `k = 1` | `identity_k1` | |
| Corollary "A work budget is sufficient" | `sufficient`, `sufficient_In`, `sufficient_job` | `sufficient_job` is a per-job form. It has no `#print axioms` line, but `sufficient` uses it. |
| Theorem "Tightness" of the net-overtake identity | `tightness`, `Tight.tight_up`, `Tight.tight_down` | The Lean witness for the upper bound is different from the instances in the paper. |
| Lemma "Outbound work under a guarantee" | `outbound` | |
| Corollary "A work budget is necessary" | `necessary` | |
| Not in the paper: FCFS start times are unique | `fcfs_unique` | Thus `W_FCFS` and `excess` have one value. |

### Guard.lean

| Paper result | Lean name | Note |
|---|---|---|
| Theorem "Guard bound": `In_i < B_max + kL` | `guard_In` | |
| Theorem "Guard bound": `W < W_FCFS[i] + B_max/k + (3 - 2/k)L` | `guard_bound` | |
| Theorem "Guard bound" with completion reports counted twice | `guard_bound_dup` | |
| Corollary "The cap for a given bound" | `cap_for_bound`, `cap_pos_iff`, `guard_cap_zero_fcfs` | The Lean bound is strict. With `B_max = 0`, the guard is FCFS. |
| A budget of 0 on every empty account makes the guard FCFS | `guard_fcfs_of_zero` | This is the zero-budget case of the second sentence of Proposition "Floor". |
| The budget family respects the cap | `budgetFamily_respects` | `n_q` can be any function from jobs to natural numbers. |
| The multiplicative bound for the age-relative budget | `guard_mult` | |
| Corollary "Largest flow time" | `maxflow`, `fcfs_flow` | Lean takes `F*` over a fractional relaxation. This `F*` is not larger than the `F*` of the paper. Thus the Lean bound is not weaker. |
| FCFS attains `F*` for `k = 1` | `fcfs_flow_k1` | |
| Proposition "Timeout bound" | `timeout_In`, `timeout_bound` | |
| The combined rule (clock first, then guard) | `combined_bounds`, `combined_clock_any_reports` | |
| Proposition "Absolute bound" | `absolute_le`, `absolute_fcfs`, `absolute_guard`, `fluidV_isFluid` | `fluidV_isFluid` shows that the fluid recursion has a solution. |
| The deadline rule, and the absolute bound for the clock | `deadline`, `absolute_timeout` | |
| Proposition "Late charges": the two bounds | `late_In`, `late_bound`, `Sched.delayedCharges_of_d` | The bounds need `δ ≥ 0`. `Sched.delayedCharges_of_d` shows that the delay model of the paper satisfies the Lean definition. |
| Proposition "Late charges": report before pull | `rbp_In`, `rbp_bound` | For every delay, and also for lost reports |
| Proposition "Late charges": one view of the counter per server | `perServer_bound` | |
| Proposition "Floor", first sentence | `floor`, `floor_core` | The budget of job `q` at decision `n` is `ρ q n`. The proof does not cover a budget rule that uses other parts of the history. |
| Theorem "Price of the guarantee" | `price` | Lean states SJF as a hypothesis on the dispatch order. |

## Parts that are not formalised

The Lean files do not prove these parts of the paper:

- The existence of an FCFS run, a guard run or an SJF run on a general input. The theorems take such a run as a hypothesis. The witnesses for "Tightness" and "Floor" are explicit.
- The witness instances for "Tightness" in the supplementary material, and the values in their table.
- The claim that a static-priority policy can make the witness runs of "Tightness". Such a policy does not know the future. We checked this claim by hand.
- The constructions that show that two terms of the guard bound are tight: `B_max/k` and `(3 - 2/k)L`.
- The attainment claims of Proposition "Late charges": the limit at `k = 1`, the instances at `k = 2`, and the per-server bound at `k = 2`.
- The single-server supremum in the supplementary material.
- The second sentence of Proposition "Floor", except for the case of a budget of 0. The other two cases need explicit constructions.
- The statement that the finite-sample term of Theorem "Price of the guarantee" is `O((m+n)/(mn))`.
- The attainment remarks after Theorem "Price of the guarantee", and the search over 1,161 parameter settings.
- The refund variant of the charge.
- The remark that a guard that never fires does not change the run.
- The consistency of replicas.
- The results of the supplementary section "Additional Theory: Scope, Accounting and Instance-Dependent Bounds".

If a statement of the paper is not in the two tables above, it is also not formalised.

## Test record

The files `compile_output.txt` and `Guard_compile_output.txt` come from a Linux run on 2026-10-07 with the same Lean and Mathlib versions.
On 2026-10-19, the commands in this file gave the same 49 axiom lines and the same 51 Lean warnings on Windows 11.
The files `windows_compile_output.txt` and `windows_Guard_compile_output.txt` are that run's output of `lake env lean` for the two files.
Apart from the file paths and the two last lines, they are identical to the Linux files.
The file `windows_leanchecker.txt` is that run's output of `lake env leanchecker Overtake Guard`.
