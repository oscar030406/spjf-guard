# CI pool: held-out refit of the effective capacity

**Question.** The simulator validation of `evidence/firefox_ci/` fits the effective
capacity to the recorded waits of the whole window, so agreement of the mean is the
objective rather than evidence. Does the validation survive when the fit is frozen on
one chronological part of the window and tested on another?

**Paper items.** The held-out rows of `paper/sections/07_data.tex` (the k_eff step-1
grid per split, and the 90th percentile that does not survive); the same grid in
Section 8; the sharpness and circularity discussion of `paper/supplementary.tex`.

**Inputs.** The two parquet files already in `data/mozilla_firefox_ci/`; nothing is
re-downloaded.

**Status.** Current.

Absolute paths that were baked into the scripts appear as `<repo-root>` (your checkout) and `<cache-dir>` (a scratch directory outside the repository); set both before rerunning. Raw data is not redistributed with this folder — see `data/README.md` for where each dataset comes from.

---

## Original study notes

Held-out capacity fit for the Firefox CI simulator validation.

`../firefox_ci/` replayed our k-server non-preemptive simulator on the **recorded**
arrivals and services of two Mozilla Firefox CI hardware worker pools and compared it
with the **recorded** waits (`out_SUMMARY.txt` §B). The row a reader is told to read —
`effective k = 156 | priority-then-FIFO | service + setup` on the osx pool, `k = 96` on
the talos pool — has its effective capacity fitted to the recorded waits of the *whole*
window, by a criterion that is the agreement of the mean and the p90. Agreement of the
mean is then the objective, not evidence. This directory refits on one chronological part
of the window, freezes, and tests on another.

**Verdict in one line.** The validation survives out of sample: mean wait within 14%,
per-hour mean-wait Pearson ≥ 0.94, per-job Spearman ≥ 0.94, while the no-fit baseline
(k = nominal machine count) is off by a factor of 1.3–2.6. `k_eff` is stable — 155/155/157
of 173 on the osx pool, 96/92 of 105 on the talos pool. The p90 does not survive
unchanged: out of sample it sits at 0.81–1.21 of the recorded p90. Read `out_SUMMARY.txt`
§F.

## What is fitted, and what is frozen

| quantity | fitted to | handled here |
| --- | --- | --- |
| `k_eff`, effective capacity | the **recorded waits**, minimising `\|log(mean ratio)\| + \|log(p90 ratio)\|` over a grid of k | refitted on the fit part only, on the original's coarse grid *and* on a step-1 grid |
| `s0`, setup/teardown per task | the recorded start/resolve times (median inter-run gap < 600 s on the same worker) — not the waits, but still in-sample | re-estimated on the fit part only |

Nothing else. The discipline (priority-then-FIFO), the priority ranking, the arrivals,
the services and the hourly bucketing are read from the data or fixed in the code.

## Splits

| pool | window | splits (days from the pool's window start) |
| --- | --- | --- |
| `releng-hardware/gecko-t-osx-1500-m4` | 21 d | fit [0,10.5) → test [10.5,21); reverse; fit [0,7) → test [7,21) |
| `releng-hardware/gecko-t-linux-talos-2404` | 7 d | fit [0,3.5) → test [3.5,7); reverse |

## Warm start

Every variant simulates the **whole window once** and the metrics are read off the test
part's mask, so the queue state crosses the split boundary: nothing is reset and no
burn-in is discarded. This is exact, not an approximation — under a non-idling
work-conserving discipline a run's start time depends only on runs that became pending
before it, so masking a full-window simulation gives the same waits on the test part as
simulating up to the end of that part. The one cold start that does intrude is in the
**reverse** splits, whose test part begins at the window's own start where the simulator
begins empty and the real pool did not; §D of the report repeats every held-out row with
the first 12 h of the test part dropped, and the shift is small.

## What is inside

| file | what |
| --- | --- |
| `fch_common.py` | paths, the splits, the manifest, and thin wrappers over the imported simulator |
| `fch_holdout.py` | fit on the fit part, freeze, test on the test part; the no-fit and circular baselines → `holdout.csv`, `ksearch.csv`, `out_holdout.txt` |
| `fch_report.py` | formats `out_SUMMARY.txt`; computes nothing |
| `holdout.csv` | one row per (pool, split, part ∈ {test, test-burnin, fit}, variant) |
| `ksearch.csv` | the k search itself: every k tried, on both grids, with its objective |
| `out_holdout.txt` | stage log, each invocation stamped with the manifest |
| `out_SUMMARY.txt` | the report |

## Reused code, not copied code

The simulator `simulate_kt`, the loader `load`, the setup estimator `setup_estimate` and
the priority map `PRIO_RANK` are **imported** from `../firefox_ci/fci_simval.py`, so they
cannot drift from what was validated there. Nothing in `../firefox_ci/` is written: the
numba cache is redirected to the cache directory (`NUMBA_CACHE_DIR`) and bytecode writing is
off, so importing leaves no `__pycache__` behind. The sha256 of every imported file and
of both parquet files is in the manifest at the top of `out_SUMMARY.txt` and in every
line of `out_holdout.txt`:

```
firefox_ci/fci_simval.py         18b4a4fc8ee24a1f2535750553e71000bf4a77f096b84316020cd5eed01b1c1f
firefox_ci/fci_common.py         d500f24287b057196c062dd3875f6dd802a9a5d02fc7ac18b44342739d9620bf
firefox_ci/fci_collect.py        f7331c4c516d7dd3593570b6e475ca9bf164711a6c3cef05c3777d8c1a44b4db
firefox_ci/guardkern_snapshot.py 5579cbb61837a07e218fc7ed85da8b34191676b12e689e254af3354d40114c12
data/.../runs_..._osx-1500-m4.parquet        ae1376d4a54f621125bfc28d66f89673d4110679c356c286f014477378e8f85e
data/.../runs_..._linux-talos-2404.parquet   ff35f4e35f764a2bff11c6c82ff638fe22b8169a020cff52d08e73049408e7c5
```

## How to rerun

Nothing is re-downloaded; the only inputs are the two parquet files already in
`data/mozilla_firefox_ci/`. Prefix with
`env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME PYTHONDONTWRITEBYTECODE=1
NUMBA_NUM_THREADS=4 OMP_NUM_THREADS=4 uv run --with numpy --with pandas --with pyarrow
--with numba --with requests python`, from this directory (`PYTHONDONTWRITEBYTECODE=1`
only keeps a one-file `__pycache__` from appearing beside these scripts — `fch_common.py`
sets it itself, but too late for its own import):

```
fch_holdout.py releng-hardware__gecko-t-linux-talos-2404   ~2 s
fch_holdout.py releng-hardware__gecko-t-osx-1500-m4       ~15 s
fch_report.py                                              ~1 s  -> out_SUMMARY.txt
```

(`fch_holdout.py` with no arguments does both pools in one go.)

Generated artefacts: source = the two parquet files; artefacts = `holdout.csv`,
`ksearch.csv`, `out_SUMMARY.txt`; regenerate = the run order above; check =
`fch_report.py` exits non-zero and writes nothing if `out_holdout.txt` carries a manifest
other than the current hash over `fch_*.py` (except `fch_report.py`), the imported
`fci_*.py` / `guardkern_snapshot.py`, the two `keff_*.csv` and the two parquet files.

No education data is read and nothing outside this directory is written.
