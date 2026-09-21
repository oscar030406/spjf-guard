# Internal referee report on the theory note (second pass)

**Question.** Does `evidence/guard_theory/theory.md` survive an adversarial reading by
someone working from an independent simulator?

**What it is.** `refsim2.py` is an exact-integer simulator written independently of the
note's own code; the directory adds exhaustive enumeration of every work-conserving
schedule on small instances, more than 5e8 random job-checks, annealing, and
per-statement attacks. `out_SUMMARY.txt` is the report; the other `out_*.txt` are raw
logs.

**Paper items.** One of the three referee passes that revisions 1–3 of the theory note
answer.

**Status.** Current.

Absolute paths that were baked into the scripts appear as `<repo-root>` (your checkout) and `<cache-dir>` (a scratch directory outside the repository); set both before rerunning. Raw data is not redistributed with this folder — see `data/README.md` for where each dataset comes from.

---

## Original study notes

Adversarial referee of evidence/guard_theory/theory.md: independent exact-integer simulator (refsim2.py), exhaustive enumeration of every work-conserving schedule on small instances, >5e8 random job-checks, annealing, and per-statement attacks; out_*.txt are the raw logs.
