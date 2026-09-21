# Internal referee report on the per-job guard theorem

**Question.** Does the per-job bound of `evidence/guard_variants/guardkern.py` survive
an adversarial attempt to break it by someone who did not write it?

**What it is.** An independent re-implementation (`refsim.py`, pure Python;
`fastkern.py`, numba; cross-checked against each other), exhaustive sweeps over small
instances, random and annealing attacks, a per-step audit of the proof, and a final
agreement test against the kernel under review. `out_*.txt` are the raw logs.

**Paper items.** This is the first of the three referee passes that revisions 1–3 of
`evidence/guard_theory/theory.md` answer; the theory note's CHANGELOG lists every item.

**Status.** Current.

Absolute paths that were baked into the scripts appear as `<repo-root>` (your checkout) and `<cache-dir>` (a scratch directory outside the repository); set both before rerunning. Raw data is not redistributed with this folder — see `data/README.md` for where each dataset comes from.

---

## Original study notes

Adversarial referee check of the per-job guard theorem: independent simulators (refsim.py pure-python reference, fastkern.py numba, cross-checked by check_agree.py/validate_sweep.py) plus exhaustive sweeps (run_exh_A/B.py), random and annealing attacks (run_random/anneal/extra.py), a per-step audit of the proof (run_steps.py, run_gaps.py, run_head_count.py) and a final agreement test against the colleague kernel (compare_kernel*.py); out_*.txt hold the raw run logs.
