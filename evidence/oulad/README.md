# OULAD pre-checks: the original direction, and why it was dropped

**Question.** The project started from relation-aware load forecasting on the Open
University Learning Analytics Dataset. These scripts are the falsification pre-checks
that were run on that direction.

**Paper items.** `out_load.txt` carries the OULAD header line of
`paper/sections/07_data.tex` (the nine 2013 course-presentations). Nothing else in this
folder appears in the paper.

**Inputs.** The seven OULAD csv files under `data/`. The `DATA` constant at the top of
each script points at that directory. The sealed 2014 presentations are never opened.

**Status.** Superseded as a research direction — the conclusion it supported was
overturned — but kept because the paper's data section quotes one of its logs and
because the negative results are the reason the project moved to judge-log workloads.

Absolute paths that were baked into the scripts appear as `<repo-root>` (your checkout) and `<cache-dir>` (a scratch directory outside the repository); set both before rerunning. Raw data is not redistributed with this folder — see `data/README.md` for where each dataset comes from.
