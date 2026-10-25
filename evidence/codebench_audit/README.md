# CodeBench size and tail audit

**Question.** Do the event, submission and test counts of the parsed tables reconcile
with the dataset publisher's own release statistics? What does the cost tail look like
under one common definition?

**Paper items.** `out_tail_and_counts.txt` carries the CodeBench run count of Table 5
(Section 7.1, 4,611,325 events), the CodeBench tail share of Table 13 (Section 8.7) and the
CodeBench rows of Table S3 (Supplementary Section S2.4). The field audit of Supplementary
Section S2.1 cites it beside `evidence/codebench_service_v2/`.

**Inputs.** `data/codebench/parquet/` (built by `evidence/codebench/parse_codebench.py`).

**Rerun.** `tail_and_counts.py`, `counts_reconcile.py`, `verify_counts.py`. Each writes
the matching `out_*.txt`. `verify_counts.txt` is an independent recount written against
the same tables.

**Status.** Current.

Absolute paths that were written into the scripts appear as `<repo-root>` (your checkout) and `<cache-dir>` (a scratch directory outside the repository). Set both before you rerun a script. Raw data is not redistributed with this folder. `data/README.md` says where each dataset comes from.
