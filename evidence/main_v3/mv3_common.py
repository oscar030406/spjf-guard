"""Shared setup for the consolidated main experiment (v3).

Read-only import of evidence/codebench_service_v2/service_precheck_v2.py (the verified
pipeline: leak-free jittered-clock features under config ires0, rolling-origin forward
models, overlay builder ms_entries/overlay, level_ks, week-block paired bootstrap,
k1_select) and of evidence/guard_variants/guardkern.py (the numba kernel of the guard
family and its per-job bound `guaranteed`).  Neither folder is written to; byte
compilation is off so no __pycache__ appears in them.

Every parameter of the experiment lives here.

Traces
  primary   evaluation pool = the 60 s-regime DEV semesters (SP.POOL60), 44 copies, the
            pipeline's own week set and overlay draws.  Reps 0..4.
  valid     VALIDATION pool = the same minus the dev-test semester 2022-2, copy count from
            the pipeline's own SP.copies_probe (stored), week set from the overlay.  Every
            choice in this study is made here and nowhere else.
  t222      2022-2 alone, held-out-style; usable only if it carries load with a sane copy
            count (<= T222_CMAX_OK copies).
  k1        single-server configuration from SP.k1_select, busy-hour rho ~ 0.80.

Guard family (guardkern): budget(q, t) = min(B0 + eta*k*(t - a_q), Bmax), dispatch = the
smallest-rank fired job.  The service-level knob is G = guaranteed max excess over FCFS;
Bmax = k*(G - (3 - 2/k)L), so Theorem A at B = Bmax gives W_guard[i] <= W_FCFS[i] + G.
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
# one thread per process: the runner uses up to six worker processes
for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
           "NUMEXPR_NUM_THREADS", "NUMBA_NUM_THREADS"):
    os.environ[_v] = "1"

import numpy as np                                                     # noqa: E402
import pandas as pd                                                    # noqa: E402

ROOT = r"<repo-root>"
V2DIR = os.path.join(ROOT, "evidence", "codebench_service_v2")
GVDIR = os.path.join(ROOT, "evidence", "guard_variants")
RSDIR = os.path.join(ROOT, "evidence", "ranking_score")
HERE = os.path.dirname(os.path.abspath(__file__))
SCRATCH = r"<cache-dir>"
CACHE = os.path.join(SCRATCH, "cb_v2_cache_r4")        # the verified v2.1 cache
RSPRED = os.path.join(SCRATCH, "rank_score", "rs_pred_ires0.parquet")
PNDIR = os.path.join(SCRATCH, "pn")                    # neural study scratch (R1 embeddings)
WORK = os.path.join(SCRATCH, "mv3")                    # our own scratch
TRACEDIR = os.path.join(WORK, "traces")
SIMDIR = os.path.join(WORK, "sim")
NUMBA_CACHE = os.path.join(WORK, "numba_cache")
for _d in (WORK, TRACEDIR, SIMDIR, NUMBA_CACHE):
    os.makedirs(_d, exist_ok=True)
# keep numba's compiled cache out of the other prechecks' directories
os.environ["NUMBA_CACHE_DIR"] = NUMBA_CACHE

sys.path.insert(0, V2DIR)
import service_precheck_v2 as SP                                       # noqa: E402
sys.path.insert(0, GVDIR)
import guardkern as GK                                                 # noqa: E402

# ---- study parameters ------------------------------------------------------ #
CFG = SP.PRIMARY                 # "ires0"
L = SP.L_CAP                     # 60.0 s service cap
SEED = SP.SEED                   # 3
TEST_SEM = "2022-2"              # dev test; 2023-1 / 2023-2 / 2024-1 are never read
RHOS = SP.RHOS                   # (0.5, 0.8, 1.0)
GS = (300.0, 600.0, 1200.0)      # guaranteed max excess over FCFS, seconds
B0_BASE = (30.0, 120.0, 600.0)   # B0 grid, scaled by k/4
ETAS = (0.0, 0.25, 0.5, 0.75, 0.9)
HARM_FRAC = 0.5                  # feasibility: harm <= G * HARM_FRAC on the validation trace
ADV_G = 600.0                    # the G whose selected guard is paired with the adversaries
T222_CMAX_OK = 100               # more copies than this and the 2022-2 trace is not usable
MSLOTS = 1 << 22

SCORES = ("M4", "M4refit", "tweedie")     # ranking scores always carried on a trace
R1S_PARQUET = os.path.join(WORK, "r1s_forward.parquet")   # written by mv3_r1s.py, optional


def say(*a):
    print(*a, flush=True)


# ---- script hashes --------------------------------------------------------- #
def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def core_scripts():
    """Every script whose content can change a number, sorted.  mv3_report.py only
    formats what the other stages wrote, so it is hashed separately in the report."""
    return sorted(f for f in os.listdir(HERE)
                  if f.startswith("mv3_") and f.endswith(".py") and f != "mv3_report.py")


def manifest():
    """One hash over the core scripts (name + content), plus the per-file table."""
    tab = [(f, sha256_file(os.path.join(HERE, f))) for f in core_scripts()]
    h = hashlib.sha256()
    for f, s in tab:
        h.update(f.encode() + b"\0" + s.encode() + b"\0")
    return h.hexdigest(), tab


class Log:
    """Appends to evidence/main_v3/out_<stage>.txt; every invocation starts with a line
    carrying the manifest hash, so mv3_report.py can refuse a report built from a stage
    that ran on different code."""

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


# ---- guard algebra --------------------------------------------------------- #
def bmax_of(G, k):
    """Work budget cap giving the service-level guarantee G at k servers (Theorem A)."""
    return float(k) * (G - (3.0 - 2.0 / k) * L)


def skip_ncap(G, k):
    """Finite-skip / position-count baseline at the same guarantee:
    W_guard[i] <= W_FCFS[i] + L (N + 3k - 2)/k  =  W_FCFS[i] + G."""
    n = int(round(G * k / L - (3 * k - 2)))
    assert n >= 1 and abs(L * (n + 3 * k - 2) / k - G) < 1e-9, (G, k, n)
    return n


def guard_kwargs(name, k, pred, B0=None, eta=None, G=None):
    """(kwargs for guardkern.run, eps, extra, Bmax) of one guarded policy."""
    if name == "cap":
        bm = bmax_of(G, k)
        b0 = min(B0, bm)
        return dict(policy="guard", pred=pred, B=b0, eps=eta * k, Bmax=bm,
                    Mslots=MSLOTS), eta * k, 0.0, bm
    if name == "fix":
        bm = bmax_of(G, k)
        return dict(policy="guard", pred=pred, B=bm, Bmax=bm, Mslots=MSLOTS), 0.0, 0.0, bm
    if name == "skip":
        n = skip_ncap(G, k)
        return (dict(policy="guard", pred=pred, B=-1.0, theta=L, Ncap=n, Mslots=MSLOTS),
                0.0, n * L, 0.0)
    raise SystemExit(name)


# ---- trace construction ---------------------------------------------------- #
def load_base():
    ev = SP.load_events(CACHE)
    D = SP.prep(ev)
    S = SP.static_sub(ev, D)
    return ev, D, S


def pool_of(trace, I):
    if trace in ("primary", "k1"):
        return sorted(I["per_cs"])
    if trace == "valid":
        return sorted(cs for cs in I["per_cs"] if cs.split("|")[0] != TEST_SEM)
    if trace == "t222":
        return sorted(cs for cs in I["per_cs"] if cs.split("|")[0] == TEST_SEM)
    raise SystemExit(trace)


def trace_path(trace, rep):
    return os.path.join(TRACEDIR, f"{trace}_rep{rep}.npz")


def load_trace(trace, rep):
    z = np.load(trace_path(trace, rep))
    return {k: z[k] for k in z.files}


def predictions(I, jidx):
    """Ranking scores over the overlay jobs.  Smaller = dispatched first; only the induced
    order matters, so the log1p scale of M4 and the raw scale of Tweedie mix freely."""
    P = pd.read_parquet(RSPRED)
    out = {"M4": I["P"]["M4"][jidx].astype(np.float64),
           "M4refit": P["log"].values[jidx].astype(np.float64),
           "tweedie": P["tweedie"].values[jidx].astype(np.float64)}
    if os.path.exists(R1S_PARQUET):
        R = pd.read_parquet(R1S_PARQUET)
        out["r1s"] = R["r1s_tweedie"].values[jidx].astype(np.float64)
        out["tweedie_itr"] = R["m4tw_itr"].values[jidx].astype(np.float64)
    for k, v in out.items():
        assert np.isfinite(v).all(), k
    return out
