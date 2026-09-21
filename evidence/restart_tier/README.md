# Kill-and-restart tiering: examined and rejected

**Question.** The obvious escape from the Omega(L) floor is to give every job a short
first attempt and restart the survivors. Does that move the additive constant of the
per-job FCFS-relative guarantee from the 60 s job limit down to the first-attempt cap?

**Answer.** No, and the idea costs more than it buys. `notes.md` has the model, the
counterexamples, the one bound that survives and its price, the trace numbers and the
prior-art verdict; `out_SUMMARY.txt` has it in ten lines.

**Paper items.** The kill-and-restart tiering paragraph of
`paper/sections/09_limitations.tex`.

**Inputs.** The development trace already built by
`evidence/guard_variants/build_inputs.py`; no sealed data is read.

**Status.** Current, and negative.

Absolute paths that were baked into the scripts appear as `<repo-root>` (your checkout) and `<cache-dir>` (a scratch directory outside the repository); set both before rerunning. Raw data is not redistributed with this folder — see `data/README.md` for where each dataset comes from.

---

## Original study notes

# restart_tier — kill-and-restart tiering, examined and rejected

Does giving every job a short first attempt (`tau` seconds, killed and requeued if it
does not finish) move the `Omega(L)` additive constant of the paper's per-job
FCFS-relative guarantee down from the 60 s job limit to `tau`? This directory holds the
answer: no. `notes.md` has the model, the counterexamples, the one bound that survives
and its price, the trace numbers and the prior-art verdict; `out_SUMMARY.txt` has the
verdict in ten lines. Nothing outside this directory is written or modified, and no
sealed data is read — the trace comes from the development cache that
`../guard_variants/build_inputs.py` already built.

Run order (each script carries its parameters inside it; prefix every run with
`NUMBA_NUM_THREADS=4 OMP_NUM_THREADS=4 env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME uv run --with numpy --with numba python ...`):

1. `verify.py` — `tierkern.py`'s non-tiered modes against `../guard_variants/guardkern.py`
   job by job, and its tiered modes against an independent pure-python simulator.
   -> `out_verify.txt`. Run this first; nothing below means anything if it fails.
2. `brute.py [n_instances]` — adversarial search over small instances (`n <= 7`, `k <= 3`)
   for the six candidate per-job bounds, the worst instance printed for each, plus the two
   analytic families. Used with 3,000,000. -> `out_brute.txt`
3. `run_trace.py <level 0|1|2> [taus]` — the full rep0 trace (17.6 M jobs), one row per
   policy. Used as `run_trace.py 2 1,2,5,10`. -> `out_trace_L2.txt`, `results_L2.csv`
4. `run_iso.py <level> [taus] [tag]` — the honest comparison: each tiered design against
   the `SPJF+guard` budget curve at the same guaranteed and the same measured worst-case
   excess, plus the reserved-server designs; asserts Proposition W on every job. Used as
   `run_iso.py 2 1,2`, `run_iso.py 1 1,2`, `run_iso.py 0 1,2`, `run_iso.py 0 2,5 _t2`.
   -> `out_iso_L*.txt`, `iso_L*.csv`

`tierkern.py` is the shared kernel (numba). Total runtime is about 25 minutes on four
threads; the trace arrays stay in the local cache directory, not here.
