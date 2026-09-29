"""Shared setup for v3.2 of the consolidated main experiment.

v3.2 exists because of one CRITICAL finding against v3.1
(../../main_v31_verify/out_VERDICT.txt, G1): "the best FEASIBLE fixed budget" was chosen
from FOUR budgets while the capped relative budget was chosen from fifteen, so the harm
constraint was slack at the fixed family's chosen point and the reported margin was an
artefact of an unequal search.  v3.2 gives both families equally fine, pre-stated grids
and reports whatever wins.

PRE-STATED GRIDS (written here before any v3.2 number was produced; one setting per
family per promise G, applied at every load level, every parameter scaled by k/4 so the
same setting means the same per-server budget at every k):

  fixed      constant budget B0 = B0_base * k/4, eta = 0.  B0_base = 32 log-spaced values
             from 15 to 4200 (= the equal-promise budget at G = 1200, k = 4) together with
             the anchors 15/30/60/120/240/360/480/600 that the capped grid also uses, so
             the two families share points and can be checked against each other; plus the
             exact equal-promise budget B0 = Bmax(G, k) per G.  38-42 values, of which at
             least 24 are admissible at every G (a constant budget's promise is
             B0/k + (3 - 2/k)L, so small budgets promise LESS than G).
  capped     budget min(B0 + eta*k*(t - a_q), Bmax) with Bmax = k(G - (3 - 2/k)L):
             B0_base in {0,15,30,60,120,240,360,480,600} x eta in {0,.25,.5,.75,.9,.95}.
             The eta = 0 rows are the same policy as the fixed rows at the same B0 and are
             used as a self-test that the two families agree.
  hybrid     budget min(B0 + gam*(jobs waiting when q arrived) + eta*k*(t - a_q), Bmax):
             B0_base in {0,30,120} x gam_base in {1,4,16} x eta in {0,0.9}.  Included
             because the rule might prefer it; it is reported if it wins and reported if
             it does not.

SELECTION RULE, unchanged from v3.1: feasible = harm (max excess over FCFS among jobs FCFS
would start within 1 s) <= G/2 in EVERY one of the 15 validation cells (5 overlays x 3
load levels); objective = the deadline-window p99 gap closed in the WORST cell; ties to
smaller worst-cell harm, then smaller B0, then smaller eta, then smaller gam.  The report
also prints the slack in the binding constraint, the whole feasible frontier, and the
selection with the single worst validation cell dropped (verifier finding G4).

v3 (../mv3_*.py, ../out_main_v3.txt) and v3.1 (../v31/, ../out_main_v31.txt) are left
exactly as they were.  v31_skipkern.py is imported from ../v31 rather than copied, and is
hashed into this manifest as an external module.
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
PARENT = os.path.dirname(HERE)
V31DIR = os.path.join(PARENT, "v31")
SCRATCH = r"<cache-dir>"
CACHE = os.path.join(SCRATCH, "cb_v2_cache_r4")
RSPRED = os.path.join(SCRATCH, "rank_score", "rs_pred_ires0.parquet")
WORK = os.path.join(SCRATCH, "mv32")
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
sys.path.insert(0, V31DIR)
import v31_skipkern as SK                                              # noqa: E402

EXTERNAL = {
    "guard_variants/guardkern.py": os.path.join(GVDIR, "guardkern.py"),
    "codebench_service_v2/service_precheck_v2.py": os.path.join(V2DIR,
                                                                "service_precheck_v2.py"),
    "guard_variants_referee/refsim.py": os.path.join(REFDIR, "refsim.py"),
    "ranking_score/rs_fit.py": os.path.join(RSDIR, "rs_fit.py"),
    "main_v3/v31/v31_skipkern.py": os.path.join(V31DIR, "v31_skipkern.py"),
}

# ---- study parameters ------------------------------------------------------ #
CFG = SP.PRIMARY
L = SP.L_CAP
SEED = SP.SEED
TEST_SEM = "2022-2"
RHOS = SP.RHOS
GS = (300.0, 600.0, 1200.0)
HARM_FRAC = 0.5
ADV_G = 600.0
T222_CMAX_OK = 100
MSLOTS = 1 << 22
VALID_REPS = (0, 1, 2, 3, 4)
PRIMARY_REPS = (0, 1, 2, 3, 4)
DROP_CELL = (1, 2)                 # the single cell G4 says decides G = 600 in v3.1
LONGWAIT = 60.0                    # "jobs FCFS already makes wait": W_FCFS > 60 s
R1S_PARQUET = os.path.join(SCRATCH, "mv3", "r1s_forward.parquet")

ANCHORS = (15.0, 30.0, 60.0, 120.0, 240.0, 360.0, 480.0, 600.0)
CAP_B0_BASE = (0.0,) + ANCHORS
CAP_ETA = (0.0, 0.25, 0.5, 0.75, 0.9, 0.95)
HYB_B0_BASE = (0.0, 30.0, 120.0)
HYB_GAM_BASE = (1.0, 4.0, 16.0)
HYB_ETA = (0.0, 0.9)
N_FIX_LOG = 32


def say(*a):
    print(*a, flush=True)


# ---- guard algebra --------------------------------------------------------- #
def bmax_of(G, k):
    return float(k) * (G - (3.0 - 2.0 / k) * L)


def fix_bases():
    """The fixed family's B0_base grid: log-spaced plus the shared anchors."""
    lo, hi = 15.0, bmax_of(1200.0, 4.0)
    g = [lo * (hi / lo) ** (i / (N_FIX_LOG - 1.0)) for i in range(N_FIX_LOG)]
    return sorted({round(x, 3) for x in g} | set(ANCHORS))


def const_promise(B0, k):
    """Promise of a CONSTANT budget B0 at k servers (Theorem B with eps = 0)."""
    return B0 / k + (3.0 - 2.0 / k) * L


def skip_ncap_dispatch(G, k):
    n = int(np.floor(G * k / L - (2 * k - 2) + 1e-9))
    assert n >= 1 and L * (n + 2 * k - 2) / k <= G + 1e-9, (G, k, n)
    return n


def policy_key(B0, eps, gam, Bmax):
    """Two parameter sets that produce the same schedule get the same key, so a cell
    simulates each distinct policy once.  A budget already at or above the cap is the
    constant-Bmax policy whatever eps and gam are."""
    if B0 >= Bmax - 1e-9 and gam >= 0.0:
        return ("sat", round(Bmax, 6))
    return (round(B0, 6), round(eps, 9), round(gam, 6), round(Bmax, 6))


def grid_policies(k):
    """Every guarded configuration of the validation grid at k servers.
    Returns [(name, family, G_or_-1, B0, eta, gam, Bmax, eps, promise)].
    A fixed-family row is simulated once, with the largest cap, because a constant budget
    below the cap is the same schedule at every G; its promise is B0/k + (3-2/k)L."""
    out = []
    bmax_top = bmax_of(max(GS), k)
    for b in fix_bases():
        B0 = b * k / 4.0
        if B0 >= bmax_top:
            continue
        out.append((f"FIXG-B{b:g}", "fixed", -1.0, B0, 0.0, 0.0, bmax_top, 0.0,
                    const_promise(B0, k)))
    for G in GS:
        bm = bmax_of(G, k)
        out.append((f"FIXEQ-G{G:g}", "fixed", G, bm, 0.0, 0.0, bm, 0.0, G))
        for b in CAP_B0_BASE:
            for eta in CAP_ETA:
                B0 = min(b * k / 4.0, bm)
                out.append((f"CAPG-G{G:g}-B{b:g}-e{eta:g}", "capped", G, B0, eta, 0.0, bm,
                            eta * k,
                            min(G, const_promise(B0, k) / (1.0 - eta))))
        for b in HYB_B0_BASE:
            for gm in HYB_GAM_BASE:
                for eta in HYB_ETA:
                    B0 = min(b * k / 4.0, bm)
                    out.append((f"HYBG-G{G:g}-B{b:g}-g{gm:g}-e{eta:g}", "hybrid", G, B0,
                                eta, gm * k / 4.0, bm, eta * k, G))
    return out


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


# ---- hashes ---------------------------------------------------------------- #
def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def input_table():
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
                  if f.startswith("v32_") and f.endswith(".py") and f != "v32_report.py")


def manifest():
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
