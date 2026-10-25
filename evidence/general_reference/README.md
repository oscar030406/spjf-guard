# The identity against other references, under failures, and summed over jobs

**Question.** Which assumptions of the net-overtake identity and of the guard's bound can
be relaxed beyond Supplementary Section S4.10: a reference other than first-come
first-served, servers that fail, and sums of the identity over all jobs or over a group?

**Answer.** Each relaxation holds with one added term, and each added term is needed.

- A reference that orders the queue by a key fixed at arrival adds `Lam_i`, the work on
  which the reference's order and the order of arrival disagree about `i`. The exhaustive
  check attains the bound at `k = 1`. A burst of later-arriving jobs ahead of `i` raises
  the excess to `In + burst`, with `In` held at 3 (`check_general_reference.py`,
  `check_exhaustive.py`).
- A failure that destroys the running job's progress adds `L` per failure in the job's
  stretch of congestion, in capacity-time. Without that term, 434 jobs (identity form) and
  73 jobs (guard form) exceed the bound (`check_crashes.py`).
- Both together (`check_combined.py`): no violation, worst ratio 0.889. Without either term, 67 jobs
  exceed the bound. Not cited in the paper.
- The identity weighted by cost and summed over all jobs gives Kleinrock's conservation
  law on every sample path at `k = 1` (4,946 runs, all exactly equal) and an error below
  `(k-1) L T` for `k >= 2` (`check_conservation.py`). Summed over a group of jobs, the
  identity is exact at `k = 1`, and under SJF the pairs inside a group never add to the
  group's total wait (`check_group.py`).

**Paper items.** Supplementary Section S7.3 (Proposition S8 and the paragraph after its
proof), Supplementary Section S7.7 (Propositions S17 and S18 and the paragraph of checks
after them), Supplementary Section S7.8 (Proposition S19 and the paragraph after its
proof), the sentence of Section 3.3 on why the reference is first-come first-served,
and the sentence of Section 6.9 on failures.

**Inputs.** None. Exact rational or integer simulation of random and enumerated
instances with `L = 3`. No dataset is read.

**Status.** Current. Each script writes its own log. Run them from this folder:

    python check_general_reference.py > out_check_general_reference.txt
    python check_exhaustive.py > out_check_exhaustive.txt
    python check_crashes.py > out_check_crashes.txt
    python check_combined.py > out_check_combined.txt
    python check_conservation.py > out_check_conservation.txt
    python check_group.py > out_check_group.txt

The simulators are imported from `../reservation_guard_verify/rguard_indep.py`, except
that `check_crashes.py` carries its own simulator with failures, which `check_combined.py`
imports.
