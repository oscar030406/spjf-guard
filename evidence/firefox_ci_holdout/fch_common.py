"""Shared setup for the held-out capacity fit of the Firefox CI simulator validation.

Why this directory exists.  `../firefox_ci/` replayed our k-server non-preemptive
simulator on the RECORDED arrivals and services of two Mozilla Firefox CI hardware pools
and compared it with the RECORDED waits (`out_SUMMARY.txt` section B).  The headline row
of each pool -- "effective k = 156", "effective k = 96" -- has the effective capacity
FITTED to the recorded waits of the whole window, by a criterion that is itself the
agreement of the mean and the p90.  Agreement of the mean is then not evidence: it is the
objective.  This directory redoes the comparison out of sample: fit on one chronological
part of the window, freeze, test on another.

Nothing here re-downloads anything and nothing outside this directory is written.  The
simulator, the loader, the setup/teardown estimator and the priority map are IMPORTED
from `../firefox_ci/fci_simval.py`, not copied, so they cannot drift; the sha256 of every
imported file and of both parquet files is logged with every run.  Numba's cache is
redirected to the cache directory so that importing writes no `__pycache__` into
`../firefox_ci/`.
"""
from __future__ import annotations

import hashlib
import os
import sys
import time

sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
for _v in ("PYTHONHOME", "PYTHONPATH", "UV_INTERNAL__PYTHONHOME"):
    os.environ.pop(_v, None)
for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
           "NUMEXPR_NUM_THREADS", "NUMBA_NUM_THREADS"):
    os.environ[_v] = "4"

ROOT = r"<repo-root>"
HERE = os.path.dirname(os.path.abspath(__file__))
FCIDIR = os.path.join(ROOT, "evidence", "firefox_ci")
SCRATCH = r"<cache-dir>"
NUMBA_CACHE = os.path.join(SCRATCH, "nb")
os.makedirs(NUMBA_CACHE, exist_ok=True)
os.environ["NUMBA_CACHE_DIR"] = NUMBA_CACHE       # keeps __pycache__ out of ../firefox_ci

import numpy as np                                                     # noqa: E402
import pandas as pd                                                    # noqa: E402

sys.path.insert(0, FCIDIR)
import fci_common as FC                                                # noqa: E402
import fci_simval as SV                                                # noqa: E402

DATA = FC.DATA
POOLS = list(FC.POOLS)
HOURS = SV.HOURS

# every file a number here depends on
IMPORTED = {
    "firefox_ci/fci_simval.py": os.path.join(FCIDIR, "fci_simval.py"),
    "firefox_ci/fci_common.py": os.path.join(FCIDIR, "fci_common.py"),
    "firefox_ci/fci_collect.py": os.path.join(FCIDIR, "fci_collect.py"),
    "firefox_ci/guardkern_snapshot.py": os.path.join(FCIDIR, "guardkern_snapshot.py"),
    "firefox_ci/keff_releng-hardware__gecko-t-osx-1500-m4.csv":
        os.path.join(FCIDIR, "keff_releng-hardware__gecko-t-osx-1500-m4.csv"),
    "firefox_ci/keff_releng-hardware__gecko-t-linux-talos-2404.csv":
        os.path.join(FCIDIR, "keff_releng-hardware__gecko-t-linux-talos-2404.csv"),
}
INPUT_DATA = {
    "data/mozilla_firefox_ci/runs_releng-hardware__gecko-t-osx-1500-m4.parquet":
        os.path.join(DATA, "runs_releng-hardware__gecko-t-osx-1500-m4.parquet"),
    "data/mozilla_firefox_ci/runs_releng-hardware__gecko-t-linux-talos-2404.parquet":
        os.path.join(DATA, "runs_releng-hardware__gecko-t-linux-talos-2404.parquet"),
}

# Chronological splits, in days from the pool's own window start.  The window is 21 days
# for the osx pool and 7 days for the talos pool (../firefox_ci/fci_common.POOL_WINDOW).
SPLITS = {
    "releng-hardware/gecko-t-osx-1500-m4": [
        ("fwd-half", (0.0, 10.5), (10.5, 21.0)),
        ("rev-half", (10.5, 21.0), (0.0, 10.5)),
        ("fit7-test14", (0.0, 7.0), (7.0, 21.0)),
    ],
    "releng-hardware/gecko-t-linux-talos-2404": [
        ("fwd-half", (0.0, 3.5), (3.5, 7.0)),
        ("rev-half", (3.5, 7.0), (0.0, 3.5)),
    ],
}
BURN_IN_H = 12.0          # hours of the test part dropped in the burn-in variant


def say(*a):
    print(*a, flush=True)


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def core_scripts():
    return sorted(f for f in os.listdir(HERE)
                  if f.startswith("fch_") and f.endswith(".py") and f != "fch_report.py")


def manifest():
    tab = [(f, sha256_file(os.path.join(HERE, f))) for f in core_scripts()]
    tab += [(f"[imported] {n}", sha256_file(p)) for n, p in sorted(IMPORTED.items())
            if os.path.exists(p)]
    tab += [(f"[data] {n}", sha256_file(p)) for n, p in sorted(INPUT_DATA.items())
            if os.path.exists(p)]
    h = hashlib.sha256()
    for f, s in tab:
        h.update(f.encode() + b"\0" + s.encode() + b"\0")
    return h.hexdigest(), tab


class Log:
    def __init__(self, stage, argv=None):
        self.p = os.path.join(HERE, f"out_{stage}.txt")
        self.f = open(self.p, "a", encoding="utf-8")
        m, _ = manifest()
        self.t0 = time.time()
        self.w(f"## {time.strftime('%Y-%m-%d %H:%M:%S')} manifest={m} "
               f"argv={' '.join(argv or sys.argv[1:])}")

    def w(self, *a):
        s = " ".join(str(x) for x in a)
        print(s, flush=True)
        self.f.write(s + "\n")
        self.f.flush()

    def el(self, *a):
        self.w(f"[{time.time() - self.t0:6.0f}s]", *a)

    def close(self):
        self.w(f"## done in {time.time() - self.t0:.0f} s")
        self.f.close()


# --------------------------------------------------------------------------- #
# the pieces of ../firefox_ci/fci_simval.py this study reuses unchanged
# --------------------------------------------------------------------------- #
def load_pool(pool):
    """SV.load: runs with a finite start and resolve, service = resolved - started,
    wait = max(started - scheduled, 0), sorted by (scheduled, task_id, run_id)."""
    df = SV.load(pool)
    t0, t1 = FC.iso_to_epoch(FC.window(pool)[0]), FC.iso_to_epoch(FC.window(pool)[1])
    return df, t0, t1


def prio_key(df):
    """The real discipline: priority first, then the order tasks became pending."""
    n = len(df)
    prio = df.priority.map(SV.PRIO_RANK).fillna(3).values.astype(np.float64)
    return prio * 1e9 + np.arange(n, dtype=np.float64)


def simulate(df, t0, t1, k, extra_service):
    """One full-window simulation at constant k with `extra_service` seconds of
    setup/teardown folded into every service.  Returns the simulated wait of every run.

    The whole window is always simulated and the metrics are then read off a mask.  A
    run's start time depends only on runs that became pending before it, so restricting
    the simulation to a prefix would give the same answer on that prefix: simulating the
    whole window and masking is the warm start, not an approximation of one."""
    nb = int(np.ceil((t1 - t0) / HOURS))
    arrival = df.scheduled.values.astype(np.float64)
    serv = df.service.values.astype(np.float64) + float(extra_service)
    st = SV.simulate_kt(arrival, serv, prio_key(df), np.full(nb, int(k), np.int64),
                        t0, HOURS)
    return np.maximum(st - arrival, 0.0)


def setup_seconds(df_fit):
    """SV.setup_estimate on the FIT part only: median gap < 600 s between consecutive
    runs on the same worker."""
    return SV.setup_estimate(None, df_fit)


def fit_objective(sim, rec):
    """The criterion ../firefox_ci/fci_simval.py minimises over k:
    |log((mean_sim+1)/(mean_rec+1))| + |log((p90_sim+1)/(p90_rec+1))|."""
    return (abs(np.log((sim.mean() + 1) / (rec.mean() + 1)))
            + abs(np.log((np.percentile(sim, 90) + 1) / (np.percentile(rec, 90) + 1))))


def k_grid(nwork, fine=False):
    """The original's grid, and the step-1 refinement used to measure stability."""
    lo = max(2, int(0.5 * nwork))
    if fine:
        return list(range(lo, nwork + 1))
    return list(range(lo, nwork + 1, max(1, nwork // 24)))


def metrics(rec, sim, sched, t0, tag):
    """Recorded-vs-simulated agreement, same definitions as fci_simval.agree /
    hourly_corr: quantiles, per-hour mean-wait Pearson, per-job Spearman, median
    absolute per-job error."""
    q = (50, 90, 99, 99.9)
    rq = np.percentile(rec, q)
    sq = np.percentile(sim, q)
    d = sim - rec
    hb = ((sched - t0) // HOURS).astype(np.int64)
    a = pd.Series(rec).groupby(hb).mean()
    b = pd.Series(sim).groupby(hb).mean()
    j = pd.concat([a, b], axis=1).dropna()
    out = dict(variant=tag, n=int(len(rec)),
               rec_mean=float(rec.mean()), sim_mean=float(sim.mean()),
               mean_ratio=float(sim.mean() / max(rec.mean(), 1e-9)))
    for nm, s_, r_ in zip(("p50", "p90", "p99", "p999"), sq, rq):
        out[f"sim_{nm}"] = float(s_)
        out[f"rec_{nm}"] = float(r_)
        out[f"{nm}_ratio"] = float(s_ / max(r_, 1e-9))
    out.update(
        hourly_pearson=float(np.corrcoef(j.iloc[:, 0], j.iloc[:, 1])[0, 1])
        if len(j) > 2 else float("nan"),
        n_hours=int(len(j)),
        job_spearman=float(pd.Series(sim).rank().corr(pd.Series(rec).rank())),
        job_pearson=float(np.corrcoef(sim, rec)[0, 1]),
        med_abs_err=float(np.median(np.abs(d))),
        within60=float(np.mean(np.abs(d) <= 60)),
        fit_objective=float(fit_objective(sim, rec)))
    return out
