# CodeBench archives: parser and first arrival-side pre-check

**Question.** Can the 18 semester archives of the CodeBench CS1 judge log be parsed into
a per-semester table, and does an hourly deadline-driven load model survive on them?

**Paper items.** The parser is the head of the CodeBench data path described in
Section 7 (`paper/sections/07_data.tex`); `out_parse.txt` is also the source of the
raw `n_logins` count quoted in `evidence/consolidation/README.md`.

**Inputs.** `data/codebench/archives/cb_dataset_<semester>_v1.81.tar.gz`, the publisher's
per-semester archives. Development semesters only; the sealed semesters 2023-1, 2023-2
and 2024-1 are never opened.

**Status.** Current for the parse; the arrival-side model in `out_codebench.txt` was an
early direction and is not used in the paper.

Absolute paths that were baked into the scripts appear as `<repo-root>` (your checkout) and `<cache-dir>` (a scratch directory outside the repository); set both before rerunning. Raw data is not redistributed with this folder — see `data/README.md` for where each dataset comes from.

---

## Original study notes

CodeBench (UFAM CS1 判题日志，18 个学期)：`parse_codebench.py` 流式解析 tar.gz 到 `data/codebench/parquet/`，`codebench_precheck.py` 做小时级截止日期驱动负载模型的证伪预检（DEV = 2023-1/2023-2/2024-1 之外的学期），输出见 `out_parse.txt` / `out_codebench.txt`。
