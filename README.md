**English** | [简体中文](README.zh-CN.md)

# Prediction-Driven Non-Preemptive Scheduling with Bounded Overtaking

This is the code, the tables and the run logs behind one paper: *Prediction-Driven
Non-Preemptive Scheduling with Bounded Overtaking for Shared Execution Services under
Deadline-Driven Bursty Load*. It rebuilds every number the paper prints from the public
datasets the paper uses.

Read the paper in the browser: [paper/main.pdf](https://cdn.jsdelivr.net/gh/oscar030406/spjf-guard@main/paper/main.pdf),
and its supplementary material,
[paper/supplementary.pdf](https://cdn.jsdelivr.net/gh/oscar030406/spjf-guard@main/paper/supplementary.pdf).
These links go through the jsDelivr mirror of this repository, which may lag a push by up
to a day. GitHub's own file view does not display the two PDFs; to download them from
GitHub instead, use [main.pdf](https://github.com/oscar030406/spjf-guard/raw/main/paper/main.pdf)
and [supplementary.pdf](https://github.com/oscar030406/spjf-guard/raw/main/paper/supplementary.pdf).

## What the paper is about

The automatic grader of a programming course takes submissions from many students and
runs them on a few machines. Each machine runs one submission at a time. A submission is
never interrupted once it has started; it is killed only when it reaches a time limit,
which the paper calls `L`. Serverless platforms, software build farms and compute
clusters run other people's jobs in the same way.

Before an assignment deadline, hundreds of students submit at once. A submission that
loops keeps a machine busy for the whole time limit, and every submission behind it
waits. The natural fix is to predict how long each submission will run and to run the
short ones first. That shortens most waits. But a wrong prediction can push one job to
the back of the queue again and again. On the log studied here, one job waited close to
6,000 seconds longer than it would have if the queue had simply been served in arrival
order. No operator will deploy a scheduler that can do that to a user.

The paper gives every job a promise. It first proves that, on any such service with `k`
machines, the extra time a job waits compared with arrival order equals the work that
jumped ahead of it, minus the work it jumped ahead of itself, divided by `k`, up to an
error of at most `(2 - 2/k) L`. It
then wraps any ordering rule in a *guard*: a small rule that counts how much work has
jumped ahead of each waiting job and, when the count reaches a budget, makes the oldest
waiting job run next. The result is that no job waits more than `G` seconds longer than
it would have in arrival order, however wrong the predictions are. The operator chooses
`G`; the theorem turns it into a guarantee.

Three further results sit beside the guard. First, a maximum waiting time, the rule
deployed schedulers use against starvation, makes the same kind of promise, and the
paper proves it. Near full load, though, it keeps much less of the benefit, because it
charges a waiting job for the whole backlog ahead of it and not only for the work that
jumped ahead. Second, the arrival log alone bounds how long any job can wait in absolute
terms, so an operator can promise a number of seconds. Third, the paper says what the
guard still promises when machines report finished jobs late.

The claim is tested by replaying real logs: two programming-course graders, a serverless
platform, two pools of machines that build and test Firefox, and a compute cluster.

This repository is a reproduction package. It is not a scheduler that can be installed
on a server.

## What is in this repository

| path | what it holds |
| --- | --- |
| `src/spjf_guard/` | the Python package that runs the main experiment. `sim/` simulates a queue in front of `k` machines and checks the paper's bound on every simulated job. `data/` reads the datasets, handles their time stamps and refuses to read sealed data. `features/` computes each job's features from what is known when it arrives. `predict/` fits the model that predicts a job's running time. `experiment/` builds the replay traces, chooses the guard's settings, computes the metrics and writes the tables |
| `tests/` | correctness tests, written before the implementation |
| `configs/main.yaml` | every setting of the main experiment, each with a comment saying what it does |
| `scripts/` | the commands listed below |
| `evidence/` | the studies behind the numbers the package does not produce, one folder each; see "Where each number comes from" |
| `docs/adr/` | decisions that are hard to reverse, one page each, with the alternatives that were rejected |
| `docs/sealed_access_log.md` | every read of a sealed semester, one line per read |
| `paper/` | the manuscript source. Table numbers are copied in from `outputs/`; no script writes into `paper/` |
| `CONTEXT.md` | the glossary, in Chinese. One word per concept, used identically in the paper, the code, the configuration and the tables |
| `GENERATED.md` | every file a script produces: its source, the command that regenerates it, the command that checks it (in Chinese) |

`README.zh-CN.md` is this file in Chinese, section for section, with the same commands.

Two directories named below are not in the repository. `data/` holds the raw datasets,
which we may not redistribute. `outputs/` holds the tables the pipeline writes; the
commands below regenerate every one of them.

## Setup

Python 3.12. Dependencies are locked by [uv](https://docs.astral.sh/uv/). This installs
them into a `.venv` inside the repository:

```bash
uv sync --extra dev
```

Every command below calls the interpreter through a shell variable named `$UV`. The
variable unsets `PYTHONHOME` and `PYTHONPATH` in case your shell exports them (one of our
machines did, and child processes then loaded the wrong standard library), and it caps
the thread count, because the simulator is memory-bound and more threads only slow it
down:

```bash
export UV="env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME \
  NUMBA_NUM_THREADS=4 OMP_NUM_THREADS=4 uv run --no-sync"
```

No path variable has to be set. Every input location is written in the `data` section of
`configs/main.yaml`, relative to the repository root:

| configuration key | points at | written by |
|---|---|---|
| `archive_dir` | `data/codebench/archives/` | you, when you download the publisher's per-semester archives |
| `raw_parquet_dir` | `data/codebench/parquet/` | `scripts/parse_archive.py` |
| `cache_dir` | `data/derived/codebench_cache_r4/` | `scripts/build_cache.py` |
| `overlay_dir` | `data/derived/overlay_traces/` | `scripts/build_overlays.py` |
| `score_dir` | `data/derived/package_ranking_scores/` | `scripts/fit_scores.py` |

If one input has to live somewhere else on your machine, `${NAME}` inside those strings
is expanded from the environment. No file in the repository may contain a path that
exists on one machine only; `scripts/check_generated.py --only paths` fails if one does.

## Data

No raw data is redistributed here. Download each dataset from its publisher into
`data/<name>/` before running anything. The terms are given as the publisher states them.

| dataset | what it is | source | terms |
|---|---|---|---|
| CodeBench v1.81 | the log of an introductory programming course at the Federal University of Amazonas, Brazil: 18 semesters from 2016 to 2024, every action in the students' online editor with a millisecond time stamp, and the start and deadline of every assignment. The main experiment runs on this | <https://codebench.icomp.ufam.edu.br/dataset/> | the page states no licence. Used for academic research and cited; the raw archives are not redistributed. Write to the dataset authors before publishing |
| ACcoding v1.0.0 | the submission log of an online judge, the second grading platform | <https://zenodo.org/record/6522395>, doi:10.5281/zenodo.6522395 | the paper says CC BY 4.0, the Zenodo page says other-open; confirm before publishing |
| OULAD | Open University learning analytics dataset. The project began as a study of this dataset; that direction did not work, and nothing in the paper rests on it | <https://analyse.kmi.open.ac.uk/open_dataset>, doi:10.1038/sdata.2017.171 | CC BY 4.0 |
| Azure Functions 2021 | two weeks of function calls on Microsoft's serverless platform, 1,980,951 calls | <https://github.com/Azure/AzurePublicDataset> (Zhang et al., SOSP 2021) | CC BY 4.0 |
| Intel Netbatch 2012 | one pool of Intel's internal compute farm, 9,054,066 jobs, in the standard format of the Parallel Workloads Archive | <https://www.cs.huji.ac.il/labs/parallel/workload/l_intel_netbatch/> (Shai, Shmueli & Feitelson, JSSPP 2013) | the archive gives no licence, states that the log is free for researchers, and asks for acknowledgement and citation. Acknowledge Ohad Shai, Edi Shmueli and Nir Antebi (Intel); the file is not redistributed |
| LPC-EGEE 2004 | a grid compute farm in France whose jobs fall into six classes by time limit; used in `evidence/lpc_egee_queues/` | <https://www.cs.huji.ac.il/labs/parallel/workload/l_lpc/> | same archive terms. Acknowledge Emmanuel Medernach for the log, Dan Tsafrir for the SWF conversion, and the Parallel Workloads Archive |
| Mozilla Firefox CI | two pools of machines that build and test Firefox, 2026-08-24 to 09-14 and 2026-09-07 to 09-14. The only log here that records how long each job actually waited, so it is what the simulator is checked against | <https://firefox-ci-tc.services.mozilla.com/api/queue/v1> and <https://treeherder.mozilla.org/api>, public and unauthenticated | no licence statement. Taken from a public API and attributed to Mozilla; only the slice collected here is kept, and it is not redistributed |
| UPC Campus Nord Wi-Fi | Wi-Fi access-point occupancy on a university campus; an early direction nothing in the paper rests on | <https://data.mendeley.com/datasets/55vx86j8wf/1>, doi:10.17632/55vx86j8wf.1 | CC BY 4.0 |

SHA-256 checksums of the downloaded files are kept in `data/README.md` in the authors'
working tree, which is not committed. The Firefox CI slice has no checksum, because the
API expires old pages and a fresh download is not byte-identical.

No dataset row reaches this repository. What is committed is code, configuration,
aggregate tables and run logs. The identifier-like columns in the committed tables name
a configuration (policy, load level, overlay, pool, semester, model, target), never a
person. No student identifier, user name, e-mail address, IP address or line of student
source code is committed.

## Reproducing the tables

The steps below rebuild every development table in the paper from the raw datasets. Run
them from the repository root with `$UV` set as above, one process at a time. The whole
sequence takes about a day on the authors' machine; the slow step is choosing the
guard's settings.

Step 1 checks the code itself: style, types and the fast tests:

```bash
$UV ruff check src tests scripts
$UV mypy
$UV python -m pytest -q -m "not slow and not crosscheck"
```

Step 2 compares this package, job for job, with the two earlier programs the study was
first run with. They are kept under `evidence/main_v3/` and are imported read-only:

```bash
$UV python -m pytest -q -m crosscheck
```

Step 3 turns the raw data into the experiment's inputs. One semester of one course
rarely makes the grader busy enough to show queueing, so the experiment replays several
semesters laid on top of one another. Each submission keeps its weekday and hour, each
semester is shifted by a whole number of weeks, and the sum is one trace with a realistic
deadline rush. The paper calls such a trace an *overlay* and uses five, drawn with five
different shifts from the same semesters. A *pool* is the set of semesters that goes into
an overlay: `primary` is six semesters from 2020 to 2022, and `validation` is the same
set without its last semester. The guard's settings are chosen on the validation
overlays only, so that the semester they are tested on never influences them. The
single-server overlay is a separate trace on which the paper's identity holds exactly:

```bash
$UV python scripts/parse_archive.py --semesters 2022-1 --compare
$UV python scripts/build_cache.py --pool development
$UV python scripts/build_overlays.py --pool primary
$UV python scripts/build_overlays.py --pool validation
$UV python scripts/build_overlays.py --single-server
$UV python scripts/fit_scores.py --repeat
$UV python scripts/select_parameters.py --workers 2
$UV python scripts/select_aging.py --workers 2
```

Step 4 is the experiment. Every policy runs on the five overlays at three load levels,
where the level is how busy the machines are in the busiest hour: 50 %, 80 % or 100 %.
Then come the single-server line, the accuracy of the running-time predictor, and the
runs in which the predictor is allowed to see less history:

```bash
$UV python scripts/run_main.py --selection outputs/selection_v3/selected_parameters.csv \
    --out-dir outputs/dev_tables --workers 2
$UV python scripts/run_main.py --prefix k1 --reps 0 --levels 0 \
    --selection outputs/selection_v3/selected_parameters.csv --out-dir outputs/dev_tables/k1
$UV python scripts/eval_scores.py --pool primary
$UV python scripts/run_visibility.py --pool primary --workers 2
```

Step 5 checks the result: the per-job waits against the earlier programs, the overlays
against their specification, the tables against the committed copies, and the numbers
the paper prints against the tables:

```bash
$UV python scripts/check_reproduction.py --overlay-dir data/derived/overlay_traces
$UV python scripts/check_overlays.py
$UV python scripts/diff_dev_tables.py
$UV python scripts/emit_paper_tables.py
$UV python scripts/check_paper_numbers.py
$UV python scripts/check_generated.py
```

Three things are worth knowing before you start.

Choosing the guard's settings is slow. `select_parameters.py` tries 258 candidate
settings fixed in advance (`docs/adr/0005`) on every validation cell. One cell with two
worker processes took about 29 minutes on the authors' machine, and the fifteen cells
about 7.3 hours. Results are written per cell, so a crashed run continues where it
stopped. `--part i --nparts n` splits a cell across machines, and `--from-grid`
re-derives the choice from saved results without simulating again. A run over only some
cells writes a `selected_parameters.csv` that is not the final selection; combine the
parts with `--from-grid` into one output directory.

The bound is checked during the run. Step 4 asserts the paper's per-job bound on each
simulated job as it is dispatched, not afterwards on averages.

`check_reproduction.py` exits 1, and that is expected. It fails on a single unequal
per-job wait. The earlier programs kept time in floating-point seconds and this package
keeps it in whole microseconds (`docs/adr/0001`). The two disagree on 0.0043 % of 1.59
billion comparisons, and after aggregation one printed number moves: the p99 wait of
the unguarded predicted-order policy at the heaviest load, from 62.91 s to 62.92 s. No
gap-closed figure changes.

Every number in `outputs/main_table.tex` is wrapped in a LaTeX macro, `\devnum{}`, that
marks it as coming from the development semesters. Numbers from the sealed run are
wrapped in `\sealednum{}` instead, so the two kinds can be told apart on the printed
page.

## The sealed semesters

Three CodeBench semesters (2023-1, 2023-2 and 2024-1), the last fifth of the ACcoding
submissions by id, and the OULAD 2014 presentations are *sealed*. Until the method is
frozen, any code path that would read them raises an error before the file is opened
(`src/spjf_guard/data/sealed.py`; the reasoning is in `docs/adr/0004`). The point is to
make it impossible to adjust the method after seeing the test result.

Freezing goes in four steps. A rehearsal with `--dry-run-sealed` prints which files would
be read without opening any. Then the *protocol lock* is written: a file of hashes
covering the code, the configuration and every input artefact. Then a commit. Then
`scripts/freeze_protocol.py`, which refuses to run if the working tree is dirty, if
anything is uncommitted, or if any check fails. Only after that is the sealed pool run,
once, with `--unseal`. Each such run appends one line to `docs/sealed_access_log.md`:
the date, the script, which sealed semesters were read, what was produced, who saw it,
and whether it changed the design. `docs/sealed_run_procedure.md` has the full command
list, the prerequisites of each step, the running time and disk needed, and what to do
after a crash.

The machine load actually reached on the sealed semesters is reported as measured. The
machine count is not adjusted afterwards to hit a target, and the single-server copy
count stays the one chosen on the development semesters (`docs/adr/0006`).

## Where each number comes from

The paper prints two kinds of numbers.

The first kind comes from the package in `src/`. The commands above rebuild those tables
from the raw datasets, and `scripts/check_paper_numbers.py` checks that the manuscript
prints exactly what the tables contain.

The second kind comes from separate studies, each run once to answer one question.
`evidence/` keeps one folder per study, 30 in all. Each folder holds the scripts that
were run, the log they printed (`out_*.txt`), the tables they wrote, and a `README.md`
that states the question, which part of the paper uses the answer, what the study needs
as input, and whether it is finished. In plain terms, the studies cover:

- how the main grading log was parsed and checked against its publisher's own counts;
- the same method applied to the second grader, the serverless platform, the compute
  cluster and the grid;
- whether the simulator reproduces the queue waits the two Firefox build pools recorded;
- the comparison of running-time predictors, including the graph-network model the
  project started with;
- independent checks of the theorems, written as referee reports;
- robustness: replaying the log with users who wait for one result before submitting
  the next, varying the number of machines, running the guard on a real two-worker
  service, and a design that was tried and rejected.

`evidence/README.md` lists every folder with its question in one line. The manuscript's
source comments still name the folder the studies were run in, `prechecks/`;
`evidence/PATHS.md` maps each of those names onto `evidence/`.

The copies keep the file and directory names the scripts import each other by. Absolute
paths from the authors' machines were replaced by `<repo-root>` and `<cache-dir>`; no
measured value was changed. The `out_*.txt` logs were not rewritten. No raw dataset is
redistributed here, and no study read sealed data.

## Conventions

`CONTEXT.md` is the glossary. A term settled in discussion goes in it, and the paper,
the code, the configuration and the tables then use that one word. A decision that is
hard to reverse, surprising later, and a real trade-off gets a page in `docs/adr/`.
Every generated file has a row in `GENERATED.md` with its source, its regeneration
command and its check command; a hand edit to a generated file fails
`scripts/check_generated.py`, which the pre-commit hook runs.

## Licence and citation

The code is MIT-licensed; see `LICENSE`. The datasets are not covered by it; each keeps
the terms in the data table above. `CITATION.cff` carries the manuscript's title and
placeholder authors, to be filled in before release.
