# platform_testbed

Evidence for the scripted two-worker run on the back end of an online course platform, reported in Section 8.7 of the paper and in Supplementary Section S6.9 (Table S25). The jobs are language-model calls of two classes, a short learner report and a long study plan, served by two worker slots from one queue with an enforced per-job limit. Demand came from 20 scripted accounts on a local deployment; no human learner was in the loop.

- `results.md` — the results of the six full cells (FCFS, SPJF, and the guard under two charging rules and three demand rules), with the bound check, measured service times, the simulator comparison and dispatcher overhead. `results.zh-CN.md` is the Chinese original.
- `records/` — the data written by the run: per-job records (`jobs-*.jsonl`), per-dispatch decisions (`decisions-*.jsonl`), client-side records (`client-*.jsonl`), per-run parameters (`manifest-*.json`) and token usage (`usage-*.log`), for the six full cells (`*-full-*`) and the smoke tests (`*-smoke-*`); the per-cell summary `summary.json`; the simulator comparison `simulator_replay.json`; and the open-loop arrival timetables `arrivals_deadline_burst*.csv`.
- `make_arrivals.py` — cuts one deadline-window arrival burst out of a development overlay and scales it to the two-worker service, for the open-loop demand rule.
- `replay_simulator.py` — feeds each cell's measured arrivals and executed work into the package simulator and compares the per-job waits with the measured ones.
- `results_tables.py` — joins the files in `records/` and prints the tables in `results.md`.

The dispatcher, the guard and the per-job limit were added to the platform's own code, which is not part of this repository.
