# CodeBench size and tail audit

**Question.** Do the event, submission and test counts of the parsed tables reconcile
with the dataset publisher's own release statistics, and what does the cost tail look
like under one common definition?

**Paper items.** `out_tail_and_counts.txt` carries the CodeBench sizes of
`paper/sections/07_data.tex` (4,611,325 events; 1,398,801 submits; 3,212,524 tests), the
per-era row counts of the same section, the tail share of the CodeBench row in
Section 8's cross-domain table, and the field audit cited in `paper/supplementary.tex`.

**Inputs.** `data/codebench/parquet/` (built by `evidence/codebench/parse_codebench.py`).

**Rerun.** `tail_and_counts.py`, `counts_reconcile.py`, `verify_counts.py`; each writes
the matching `out_*.txt`. `verify_counts.txt` is an independent recount written against
the same tables.

**Status.** Current.

Absolute paths that were baked into the scripts appear as `<repo-root>` (your checkout) and `<cache-dir>` (a scratch directory outside the repository); set both before rerunning. Raw data is not redistributed with this folder — see `data/README.md` for where each dataset comes from.
