# Scheduling on a shared pool of grading servers, with per-job guarantees

This repository rewrites the exploratory scripts in `prechecks/` as a configuration-driven, reproducible package: it replays the development-phase results of the paper's main line job by job, and after the method is frozen it runs once on the sealed terms. The glossary lists only concepts specific to this project; the paper, code, configuration and tables use the same vocabulary.

## Language

**job**:
The unit of work to execute after one submission enters the grading system. In the paper it corresponds to submission / invocation / run.
_Avoid_: submission, task, request, "assignment" (that word means an assessment)

**server**:
One machine that executes jobs. In deployments it is called executor, judge host or worker.
_Avoid_: executor, judge host, worker, machine, node

**rank**:
The total order induced by (arrival, input index). `j < i` means j has the smaller rank. FCFS always dispatches the waiting job with the smallest rank.
_Avoid_: index, order, priority, arrival order

**work-conserving**:
No server is idle while a job is waiting. The one assumption neither theorem can drop.
_Avoid_: non-idling, busy, fully loaded

**dispatch epoch**:
An instant at which some server is idle and the queue is non-empty; the policy selects one waiting job at that instant. Events at the same instant are processed in the order completion, arrival, dispatch.
_Avoid_: decision point, scheduling instant

**C_cap** (executed work):
`min(C, L)`, the wall-clock seconds one grading actually executes; a job stopped at the limit contributes exactly L. The simulation, the accounting and the guard's charging all use it.
_Avoid_: exec_time, service time (English prose may use service time), cost (cost means the predicted quantity)

**L** (limit):
The execution limit of a single job, observed as 60 seconds on CodeBench. The guarantees are stated in units of L.
_Avoid_: timeout, cap, "time-out"

**excess**:
`W_P[i] - W_FCFS[i]`, the extra seconds waited relative to first-come first-served on the same input and the same k.
_Avoid_: delay, slowdown, "latency"

**harm**:
The largest excess among the jobs that could start within 1 second under FCFS. The guarantee G does not constrain its distribution; it is what an operator actually feels.
_Avoid_: unfairness, "maximum harm", victim delay

**heavy job**:
A job whose true C_cap exceeds a threshold fixed on the training period (the 95th percentile of the training terms). A heavy job predicted as light still counts.
_Avoid_: long job, outlier, "long-tail job"

**gap closed**:
`(W_FCFS - W_P) / (W_FCFS - W_SJF)`, computed on the primary metric. It is not a percentage reduction in waiting; the two absolute values must be printed alongside it.
_Avoid_: improvement, gain, "size of improvement"

**deadline window**:
The 24 hours before each assessment's deadline. A job belongs to the window if and only if its arrival falls in the window; jobs that arrive in the window and complete after it still count.
_Avoid_: peak, rush window, "peak period"

**over[q]** (charged overtaking work):
The sum of the true C_cap of the jobs whose rank is after q and that have already completed. It is charged only at completion events, which is why the guard is deployable.
_Avoid_: overtaken work, "overtaking amount" (usable in prose)

**budget**:
`min(B0 + gam w_q + eta k (t - a_q), Bmax)`, with `w_q` the number of jobs waiting when q arrived: the largest `over` that q tolerates. `eta = gam = 0` is the constant shape, `gam = 0` the age-relative shape, and both positive the queue-length shape (ADR 0005). `Bmax = k(G - (3 - 2/k)L)` is solved from the promise G, without data.
_Avoid_: threshold, quota, "allowance"

**guard**:
A wrapper around any base scheduler: when the trigger set is non-empty it dispatches the job with the smallest rank in that set, otherwise it follows the base scheduler.
_Avoid_: wrapper (usable in English prose), limiter, "protection mechanism"

**SPJF-E**:
The base policy that orders by the expected cost `E[C_cap | x]` fitted with Tweedie(p=1.5), without a guard.
_Avoid_: SPJF, predicted-SJF, "ordering by prediction"

**SPJF-log**:
The comparator with the same features and the same protocol, fitted on `log1p(C_cap)` and then back-transformed.
_Avoid_: M4, "log point prediction"

**Guard(G) / Fixed(G) / Skip(G)**:
Three guards under the same promise G: the guard with the budget shape and parameters selected jointly over the three shapes (Guard-fixed(G), Guard-age(G) and Guard-queue(G) are the best of each single shape), the fixed budget (`budget = Bmax`), and the position-count guard that counts dispatches (`N = floor(Gk/L - (2k-2))`).
_Avoid_: CAP / FIX / SKIP (old labels from `prechecks/`, not used in new code)

**overlay**:
A single trace formed by aligning several class-terms on their true day of week and time of day, shifting them by whole weeks and superimposing them. The five overlays are different constructions from the same data, not five independent platforms.
_Avoid_: replica, trace (trace means the simulator's input object), "copy"

**online / exact / original** (score visibility protocols):
Which past results a job's score may use. online: the scheduler runs once; at the moment a job arrives, its history is recomputed from the results of the same
class-term copy that have already completed in this replay, and the frozen model scores it (the headline result, ADR 0008). exact: offline monotone withholding, replaying repeatedly until
no score uses an incomplete result; a conservative solution (ADR 0007). original: the recorded clock of the original platform, an optimistic reference.
conservative and static are two further, stricter references.
_Avoid_: using "exact" to mean online; calling original "leak-free"

**sealed**:
The part that cannot be read before the freeze: CodeBench 2023-1 / 2023-2 / 2024-1, ACcoding ids 80%–100%, OULAD 2014. Refused at the path level; see `src/spjf_guard/data/sealed.py`.
_Avoid_: holdout, test set, "held-out set"

**`\devnum{}` / `\sealednum{}`** (number-labelling macros):
The layer around every number in the paper. `\devnum` says the number comes from development data, `\sealednum` says it comes from the sealed run;
the two are mutually exclusive. The table scripts split by this, and the value-by-value checking script also finds numbers by it, so a sealed number wrapped in `\devnum` is not just
mislabelled; it will also be checked as a development number.
_Avoid_: writing a sealed number as `\devnum`; giving the same number two layers of labels

**`rho_target` / `rho_realised`** (target utilisation / realised utilisation):
`rho_target` is the load level this cell was built for, and the number the paper prints; `rho_realised` is the utilisation this overlay actually reaches at this k
in the busy hour (busy-hour work ÷ 3600k). The difference comes from rounding k. The value actually reached on the sealed terms is reported as it is,
and k is not adjusted afterwards to hit the target, so both columns have to be in the table.
_Avoid_: comparing `rho_realised` as if it were the target; using the single word "utilisation" for both

**protocol lock**:
`protocol_lock.json`. The set of hashes that freezes the method: code, configuration, input artefacts, plus the term split, visibility protocol, predictor and seeds, ordering scores, guard families and selection rule, k and the load construction, primary metric, bootstrap settings. `protocol_lock.draft.json` is a draft and unseals nothing.
_Avoid_: manifest, freeze file, snapshot

**manifest** (output manifest):
`outputs/**/manifest.json`. What one run writes next to the tables it produced: the script that produced them, the sha256 of the configuration and inputs, and the sha256 of every output. `scripts/check_generated.py --only outputs` uses it to decide whether anyone edited a table by hand, or whether the configuration was changed after the tables were produced. It does not decide whether the numbers are right.
_Avoid_: metadata, protocol lock (the protocol lock freezes the method; the manifest records one run)

**sealed dry run**:
`scripts/run_main.py --dry-run-sealed`. Prints the files the sealed run will read, the policies it will run and the state of the lock, without opening a single file.
_Avoid_: "simulated run", "trial run", preview

**per-cell writes to disk**:
Parameter selection and the main run write each (overlay, load level) cell to its own file as soon as it is measured; after a crash, rerunning unchanged skips the cells that already have a file.
_Avoid_: "resumable transfer", checkpoint, cache
