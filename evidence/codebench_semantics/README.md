# CodeBench field semantics: what `EXECUTION TIME` and the block headers mean

**Question.** What exactly do the `EXECUTION TIME` field and the
`== SUBMITION/TEST (...)` header time measure, and from when does the 60 s evaluation
limit apply? Every cost model in the paper is built on the answers.

**Paper items.** Section 7's description of the CodeBench trace and the 60 s per-job
limit `L` used throughout Sections 6 and 8; the field audit cited in
`paper/supplementary.tex` alongside `evidence/codebench_audit/`.

**Inputs.** The per-semester archives and the parquet tables of
`evidence/codebench/`. The parse cache (`cache/*.parquet`) and the copies of the
publisher's web pages (`sources/`) are **not** included here: the cache is derived
student-log data and the web pages are the publisher's copyright. Rebuild the cache with
`build_cache.py` before rerunning anything downstream of it.

**Status.** Current.

Absolute paths that were baked into the scripts appear as `<repo-root>` (your checkout) and `<cache-dir>` (a scratch directory outside the repository); set both before rerunning. Raw data is not redistributed with this folder — see `data/README.md` for where each dataset comes from.

---

## Original study notes

What the CodeBench `EXECUTION TIME` field and the `== SUBMITION/TEST (...)` header time mean, tested on DEV semesters 2018-1..2022-2: run `build_cache.py` first (streams archives into `cache/`, no code or keystroke text kept), then `t1_lag.py` (must precede `t3_t4_t5.py`/`refine_checks.py`/`extra_checks.py`, which read `cache/t1_matched.parquet`), `t2_gaps.py`, `t2_file_order.py`, `inspect_long_runs.py`; each script's stdout is the matching `out_*.txt`. The publisher's official web pages were read as fetched on 2026-09-18; they are the publisher's copyright and are not redistributed here.

Verdicts (2026-09-19, adopted in `docs/research_plan.md` §2.2): SUBMITION header = result time (high confidence); EXECUTION TIME = wall-clock seconds from start to end of one evaluation, startup included (medium); scope over test cases unresolved; 60 s limit from Sept 2019; TEST header meaning unresolved; the platform runs each student's code in their own Docker container (no shared queue).

Maintainer letter: we wrote to the dataset maintainers on 2026-09-19, at the address given on the platform's official contact page, copying the author of the dataset descriptor paper. 13 questions: 8 on fields and timestamps, 5 on the release statistics from `../codebench_audit/out_counts_reconcile.txt`. Every number in the letter was checked against `out_t3_t4_t5.txt`, `out_t2_file_order.txt`, `out_refine_checks.txt`, `out_extra_checks.txt` and `../codebench_audit/out_counts_reconcile.txt` before it was sent. No reply had arrived when this folder was assembled; record any reply here.

Correction after sending: question 8 says 1,172 zero-time SUBMITION blocks; counting the parquet directly gives 1,671 in 2020-ERE..2022-2 (the semantics cache covered 1,172 of them). The question itself stands.

Skeptic re-check: `verify_independent.py build` then `verify_independent.py analyze > verify_independent.txt` (own parser and matching, semesters 2018-2/2019-2/2021-2/2022-1, results per class; cache in `cache/verify_independent/`).
