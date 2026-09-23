# Guard optimality: the independent re-check

**Question.** Do theorems T1, T2 and T3 of the optimality note hold when the model is
rebuilt from their written statements alone, by a check that imports nothing from the
study under review?

**Answer.** With corrections. `verification.md` is the complete report: corrected
statements, proofs, verdicts, a literature check and a recommendation on where each
result belongs in the paper. `sim.py` is an independently written event simulator and
`check_t1.py`, `check_t2.py`, `check_t3.py` are the numerical attacks, each with its own
captured log.

**Paper items.** Eight locations in `paper/sections/S_theory_additions.tex` and two in
`paper/supplementary.tex`, whose source comments name `verification.md`,
`literature_check.md`, `out_t1.txt`, `out_t2.txt` and `out_t3.txt`.

**Inputs.** None. Exact simulation over constructed instances; no dataset is read and no
sealed semester is opened.

**Status.** Current. It governs wherever it disagrees with the optimality note.

**One reference does not resolve here.** `sim.py` names `prechecks/guard_optimality/`,
the note under review, which has no copy in this folder; the sentence around it says what
the file was. The `__pycache__/` bytecode was dropped.

Absolute paths that were baked into the scripts appear as `<repo-root>` (your checkout), `<cache-dir>` (a scratch directory outside the repository) and `<python-root>` (the interpreter install); set them before rerunning. Raw data is not redistributed with this folder — see `data/README.md` for where each dataset comes from.

---

## Original study notes

Independent referee verification of `../guard_optimality/optimality.md` (T1/T2/T3).

- `verification.md`: complete report, corrected statements, proofs, verdicts, literature check, and paper-placement recommendations.
- `sim.py`: independently written event simulator.
- `check_t1.py`, `check_t2.py`, `check_t3.py`: numerical attacks.
- `out_t1.txt`, `out_t2.txt`, `out_t3.txt`: captured outputs from the corresponding checks.
- `literature_check.md`: correction note for the interrupted literature draft; the complete review is in `verification.md`.

Each check was run separately, from a bash shell, with:

```text
env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME uv run --no-project --with numpy python evidence/guard_optimality_verify/check_t1.py
env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME uv run --no-project --with numpy python evidence/guard_optimality_verify/check_t2.py
env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME uv run --no-project --with numpy python evidence/guard_optimality_verify/check_t3.py
```
