# OULAD pre-checks: the original direction, and why it was dropped

**Question.** The project started from relation-aware load forecasting on the Open
University Learning Analytics Dataset. These scripts are the falsification pre-checks
that were run on that direction.

**Paper items.** `out_load.txt` carries the OULAD row of Table 5 (Section 7.1), the OULAD
paragraph of Section 7.2 (activity 1.29 to 2.95 times higher before an assessment; a peak
warning with F1 0.593 against 0.000) and the development presentations named in Section
7.3. Nothing else in this folder appears in the paper.

**Inputs.** The seven OULAD csv files under `data/`. The `DATA` constant at the top of
each script points at that directory. Only `audit_oulad_stats.py` opens the sealed 2014
presentations: it counted their requests, as the paper's data section states. Every other
script keeps only the 2013 presentations.

**Status.** Superseded as a research direction: the conclusion that it supported was
overturned. It is kept because the paper's data section quotes one of its logs, and
because the negative results are the reason why the project moved to judge-log workloads.

Absolute paths that were written into the scripts appear as `<repo-root>` (your checkout) and `<cache-dir>` (a scratch directory outside the repository). Set both before you rerun a script. Raw data is not redistributed with this folder. `data/README.md` says where each dataset comes from.
