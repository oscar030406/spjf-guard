# Independent verification of the main experiment (v3)

**Question.** Do the numbers of `evidence/main_v3/out_main_v3.txt` hold up when the
simulator, the metrics, the aggregation and the bootstrap are written a second time from
the written policy definitions rather than reused?

**Paper items.** `out_VERDICT.txt` section C2 and its "MAY" list are the independent
simulator figures quoted in `paper/sections/08_experiments.tex`.

**Reading the logs.** In these logs *builder* means the original implementation under
review and *mine* the independent re-implementation written here; the two are compared
job for job.

**Status.** Current as the v3 verification. Its findings F1, F4 and F8 are what produced
version 3.1 of the main experiment.

Absolute paths that were baked into the scripts appear as `<repo-root>` (your checkout) and `<cache-dir>` (a scratch directory outside the repository); set both before rerunning. Raw data is not redistributed with this folder — see `data/README.md` for where each dataset comes from.

---

## Original study notes

Adversarial verification of `../main_v3`. Nothing in `../main_v3` or anywhere else in the
project is modified; this directory holds only my own scripts, logs and verdict. The
builder's traces and per-cell outputs are read from the local cache directory
(`<cache-dir>/mv3/`); my own large files go to `<cache-dir>/mv3_verify/`.

The simulator here is written from the policy definitions in `docs/research_plan.md`
chapters 4-5. It does not import `guardkern.py`, `refsim.py` or
`service_precheck_v2.py`; the only thing taken from the builder is the input (arrival
times, true service times, ranking scores, deadline-window and heavy flags) and, for the
comparison, its stored per-cell numbers.

Run order (prefix every command with
`env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME uv run --with numpy --with
pandas --with pyarrow --with numba python`):

```
vsmall.py --n 6000                    ~4 min   my sim vs an exact rational brute force
                                               and vs the builder's kernel  -> out_small.txt
vbig.py --trace k1 --rep 0 --level 0 --policies ...      ~10 s  -> out_cell_*.txt
vbig.py --trace primary --rep R --level L --policies ... ~2 min per cell, 15 cells
                                                                -> out_cells.txt
vtrace.py [--mine]                    ~20 s   every number of out_main_v3.txt against the
                                               per-cell csv files    -> out_trace*.txt
vboot.py --nboot 2000 --seed 777      ~6 min   my own week-block paired bootstrap
                                                                     -> out_boot.txt
vhygiene.py                           ~1 min   validation pool, selection rule, section 9
                                                                     -> out_hygiene.txt
vcomplete.py                          ~20 s   manifest, stage logs, cell completeness
                                                                     -> out_complete.txt
vselect2.py --rep 1                   ~12 min  the guard choice redone on the unused
                                               validation overlay    -> out_select2.txt
vtable.py 2                           ~5 s    the headline table rebuilt from my own cells
                                                                     -> out_table_L2.txt
vclock.py                             ~30 s   the one small instance where the float-seconds
                                               clock and exact arithmetic disagree
                                                                     -> out_clock.txt
vclockbig.py --trace k1               ~30 s   the same question on a real trace
```

Files: `vsim.py` (the simulator and the per-job bounds), `vsmall.py`, `vbig.py`,
`vtrace.py`, `vboot.py`, `vhygiene.py`, `vcomplete.py`, `vselect2.py`; logs `out_*.txt`;
the verdict is `out_VERDICT.txt`.

What is checked where: C2 (simulator) in `out_small.txt` + `out_cell_primary_rep0_L2.txt`
+ `out_cells.txt`; C3 (headline numbers) in `out_trace.txt` / `out_trace_mine.txt`;
C4 (bootstrap) in `out_boot.txt`; C1 and C5 in `out_hygiene.txt`, `out_cells.txt` and
`out_select2.txt`; C6 in `out_cell_primary_rep0_L2.txt` and the k = 1 cell log;
C7 in `out_complete.txt`.
