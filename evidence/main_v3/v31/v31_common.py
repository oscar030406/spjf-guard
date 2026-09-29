"""Shared setup for v3.1 of the consolidated main experiment.

v3.1 keeps v3's pipeline and changes three things, all of them answers to the independent
verifier's findings in ../../main_v3_verify/out_VERDICT.txt:

  F8  the guard parameters are selected over EVERY validation overlay, not one: a
      configuration is feasible only if its harm is <= G/2 at every load level of every
      validation overlay, and the objective is the worst (overlay, level) gap closed.
      The same rule is applied to the fixed-budget family, so "capped beats fixed at
      equal G" is decided against the best FEASIBLE fixed budget, not only against
      B0 = Bmax.
  F4  the finite-skip baseline is charged at DISPATCH, which is what a position counter
      in the prior art does, and is given the largest skip count that still guarantees
      excess <= G under that accounting:  W <= W_FCFS + (N + 2k - 2) L / k,  so
      N = floor(G k / L - (2k - 2)) -- 34 rather than 30 at k = 4, G = 600 s.  v3's
      completion-charged variant is kept beside it under the name SKIPC.
  F1  the manifest hashes the imported modules too (guardkern.py, the v2.1 pipeline,
      the referee simulator, the ranking-score fitter), not only this study's scripts,
      so "no reported number can come from code that has since changed" is true of
      everything a number depends on.

This directory is a separate manifest from ../mv3_*.py; the v3 report ../out_main_v3.txt
and its stage logs are left exactly as they were.
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
    os.environ[_v] = "1"

import numpy as np                                                     # noqa: E402
import pandas as pd                                                    # noqa: E402

ROOT = r"<repo-root>"
V2DIR = os.path.join(ROOT, "evidence", "codebench_service_v2")
GVDIR = os.path.join(ROOT, "evidence", "guard_variants")
REFDIR = os.path.join(ROOT, "evidence", "guard_variants_referee")
RSDIR = os.path.join(ROOT, "evidence", "ranking_score")
HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)                      # evidence/main_v3
SCRATCH = r"<cache-dir>"
CACHE = os.path.join(SCRATCH, "cb_v2_cache_r4")
RSPRED = os.path.join(SCRATCH, "rank_score", "rs_pred_ires0.parquet")
PNDIR = os.path.join(SCRATCH, "pn")
WORK = os.path.join(SCRATCH, "mv31")
TRACEDIR = os.path.join(WORK, "traces")
SIMDIR = os.path.join(WORK, "sim")
NUMBA_CACHE = os.path.join(WORK, "numba_cache")
for _d in (WORK, TRACEDIR, SIMDIR, NUMBA_CACHE):
    os.makedirs(_d, exist_ok=True)
os.environ["NUMBA_CACHE_DIR"] = NUMBA_CACHE

sys.path.insert(0, V2DIR)
import service_precheck_v2 as SP                                       # noqa: E402
sys.path.insert(0, GVDIR)
import guardkern as GK                                                 # noqa: E402
sys.path.insert(0, HERE)
import v31_skipkern as SK                                              # noqa: E402

# external modules a number here depends on; hashed into the manifest (F1)
EXTERNAL = {
    "guard_variants/guardkern.py": os.path.join(GVDIR, "guardkern.py"),
    "codebench_service_v2/service_precheck_v2.py": os.path.join(V2DIR,
                                                                "service_precheck_v2.py"),
    "guard_variants_referee/refsim.py": os.path.join(REFDIR, "refsim.py"),
    "ranking_score/rs_fit.py": os.path.join(RSDIR, "rs_fit.py"),
}

# ---- study parameters (unchanged from v3 unless noted) --------------------- #
CFG = SP.PRIMARY
L = SP.L_CAP
SEED = SP.SEED
TEST_SEM = "2022-2"
RHOS = SP.RHOS
GS = (300.0, 600.0, 1200.0)
B0_BASE = (30.0, 120.0, 600.0)
ETAS = (0.0, 0.25, 0.5, 0.75, 0.9)
HARM_FRAC = 0.5
ADV_G = 600.0
T222_CMAX_OK = 100
MSLOTS = 1 << 22
VALID_REPS = (0, 1, 2, 3, 4)      # v3 selected on rep 0 alone; F8
PRIMARY_REPS = (0, 1, 2, 3, 4)
R1S_PARQUET = os.path.join(SCRATCH, "mv3", "r1s_forward.parquet")


def say(*a):
    print(*a, flush=True)


# ---- script + module hashes ------------------------------------------------ #
def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def input_table():
    """sha256 of the data artefacts every number here is computed from.  These are
    inputs, like the raw parquet, so they are not part of the code manifest; the build
    stage logs them and the report quotes them."""
    return [(n, sha256_file(p)) for n, p in sorted({
        "cb_v2_cache_r4/ev.parquet": os.path.join(CACHE, "ev.parquet"),
        "cb_v2_cache_r4/feat_ires0.parquet": os.path.join(CACHE, "feat_ires0.parquet"),
        "cb_v2_cache_r4/forward_ires0.parquet": os.path.join(CACHE,
                                                             "forward_ires0.parquet"),
        "rank_score/rs_pred_ires0.parquet": RSPRED,
        "mv3/r1s_forward.parquet": R1S_PARQUET,
    }.items()) if os.path.exists(p)]


def core_scripts():
    return sorted(f for f in os.listdir(HERE)
                  if f.startswith("v31_") and f.endswith(".py") and f != "v31_report.py")


def manifest():
    """One hash over this study's scripts AND the imported modules they depend on."""
    tab = [(f, sha256_file(os.path.join(HERE, f))) for f in core_scripts()]
    tab += [(f"[ext] {n}", sha256_file(p)) for n, p in sorted(EXTERNAL.items())]
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


# ---- guard algebra --------------------------------------------------------- #
def bmax_of(G, k):
    """Work budget cap giving the guarantee G at k servers (Theorem A)."""
    return float(k) * (G - (3.0 - 2.0 / k) * L)


def skip_ncap_dispatch(G, k):
    """Largest skip count with W_skip[i] <= W_FCFS[i] + (N + 2k - 2) L / k <= G, the
    bound of a count charged when the overtaker is DISPATCHED (v31_skipkern)."""
    n = int(np.floor(G * k / L - (2 * k - 2) + 1e-9))
    assert n >= 1 and L * (n + 2 * k - 2) / k <= G + 1e-9, (G, k, n)
    return n


def skip_ncap_completion(G, k):
    """v3's count, charged when the overtaker COMPLETES (guardkern's count channel):
    W <= W_FCFS + (N + 3k - 2) L / k.  Kept for continuity with ../out_main_v3.txt."""
    n = int(np.floor(G * k / L - (3 * k - 2) + 1e-9))
    assert n >= 1 and L * (n + 3 * k - 2) / k <= G + 1e-9, (G, k, n)
    return n


def guard_kwargs(tag, k, B0=None, eta=None, G=None):
    """(kwargs for guardkern.run without `pred`, eps, extra, Bmax, Ncap) per policy."""
    if tag == "cap":
        bm = bmax_of(G, k)
        return dict(policy="guard", B=min(B0, bm), eps=eta * k, Bmax=bm,
                    Mslots=MSLOTS), eta * k, 0.0, bm, 0
    if tag == "fix":                       # equal-G baseline: eta = 0, B0 = Bmax
        bm = bmax_of(G, k)
        return dict(policy="guard", B=bm, Bmax=bm, Mslots=MSLOTS), 0.0, 0.0, bm, 0
    if tag == "fixsel":                    # best FEASIBLE fixed budget at the same G
        bm = bmax_of(G, k)
        return dict(policy="guard", B=min(B0, bm), Bmax=bm, Mslots=MSLOTS), 0.0, 0.0, bm, 0
    if tag == "skipc":                     # v3's completion-charged finite skip
        n = skip_ncap_completion(G, k)
        return (dict(policy="guard", B=-1.0, theta=L, Ncap=n, Mslots=MSLOTS),
                0.0, n * L, 0.0, n)
    raise SystemExit(tag)


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
