# Independent verification of the main experiment (v3.1)

**Question.** Do the numbers of `evidence/main_v3/out_main_v31.txt`, and the Section 8
tables built from them, hold up under a second implementation — and is the fixed-budget
grid the comparison rests on fine enough to be fair?

**Paper items.** Finding G1 of `out_VERDICT.txt` is why version 3.2 of the main
experiment exists and why the paper's claim about the capped budget's margin is the
weaker one; `out_paper.txt` pins by sha256 the version of `paper/sections/` it checked.

**Reading the logs.** *Builder* means the implementation under review, *mine* the one
written here. 50 cells, 804 guarded runs and 13,921,826,346 per-job bound checks were run
on this directory's own waits.

**Status.** Current as the v3.1 verification.

Absolute paths that were baked into the scripts appear as `<repo-root>` (your checkout) and `<cache-dir>` (a scratch directory outside the repository); set both before rerunning. Raw data is not redistributed with this folder — see `data/README.md` for where each dataset comes from.

---

## Original study notes

Adversarial verification of `../main_v3/out_main_v31.txt` and `../main_v3/v31/`, and of
the Section 8 tables of `../../paper/sections/08_experiments.tex`. Nothing outside this
directory is modified; my own large files go to `<cache-dir>/mv31_verify/`.

What is written here, and by whom
---------------------------------

- `wskip.py` is **mine**: a dispatch-charged finite-skip simulator written from the
  definition in `paper/sections/06_theory.tex` (Remark `rem:counts`, equation `eq:skip`),
  in two implementations — a literal exact-arithmetic reference that recomputes `cnt[q]`
  for the whole waiting set and takes `min(fired)`, and a numba kernel that uses the
  identity `cnt[head] = TD - head`. Neither imports `v31_skipkern`.
- The work-budget guard, FCFS and the pure-prediction order are **reused** from the v3
  verifier's `../main_v3_verify/vsim.py`
  (sha256 `3a01397a754a98c46062f0c7eb48660c4207ef716d34f1bbee2e8e71bd3eb4ee`), which was
  written independently of the builder and which v3.1 does not touch. Reuse is only
  admissible after re-validation: `wrevalidate.py` checks it against an exact rational
  brute force written here and against the builder's `guardkern` on 2,500 random small
  instances before any conclusion uses it.
- Everything else — metrics, aggregation, the selection rule, the bootstrap, the bound
  assertions, the finer fixed-budget grid — is written here.

Run order (prefix every command with
`env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME NUMBA_NUM_THREADS=4
OMP_NUM_THREADS=4 uv run --no-project --with numpy --with pandas --with pyarrow --with
numba python`):

```
w_manifest.py                               ~40 s   V7   -> out_manifest.txt
w_select.py                                  ~5 s   V1   -> out_select.txt
wrevalidate.py --n 2500                      ~3 min       -> out_revalidate.txt
wskip.py --nsmall 4000 --cell primary:0:2   ~12 min  V2   -> out_skip.txt
wcells.py --trace T --rep R --level L [--set main|grid|fixgrid] --workers 4
                                            ~32 s per primary cell, 7 s for k = 1
                                                     V3/V5/V6 -> out_cells.txt and
                                                     <cache-dir>/mv31_verify/cells/*.csv
wvalid.py                                    ~5 s   V1   -> out_valid.txt
wtrace.py                                   ~20 s   V3/V5/V6 -> out_trace.txt
wboot.py --nboot 2000 --seed 31337 --level 2 ~2 min  V4   -> out_boot_L2.txt
wfixgrid.py                                  ~5 s   G1   -> out_fixgrid.txt
wpaper.py                                    ~5 s   paper -> out_paper.txt
```

Cells simulated here: all 16 reported cells (primary overlays 0-4 at levels 0, 1, 2 and
the k = 1 cell) with the full 28-policy set; 4 validation grid cells with the selected
and rejected guard settings; and a 16-point fixed-budget grid on all 15 validation cells
and all 15 primary cells. 50 cells, 804 guarded runs, 13,921,826,346 per-job bound
checks on my own waits.

The verdict is `out_VERDICT.txt`.

Footprint note: the first command was run without `--no-project` and `uv` created
`<repo-root>\.venv` in the project root. Every later command used
`--no-project`. Nothing else outside this directory and the cache directory was written.

Concurrency note: the paper was being edited in parallel while this ran (every file
in `paper/sections/` was rewritten between 00:37 and 00:59 on 2026-09-20). `out_paper.txt`
pins the exact version it checked by sha256; rerun `wpaper.py` after any further edit.
`evidence/main_v3/` and `evidence/main_v3/v31/` were not touched during the run: the
report and every csv still carry their 22:41-22:43 timestamps.
