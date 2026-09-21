"""Shared setup for the net-overtake identity residual measurement.

What is measured.  ../guard_theory/theory.md Theorem 1 (and the paper's
`paper/sections/06_theory.tex`) states that for every non-preemptive work-conserving
k-server policy P and every job i

    D_i := k * ( W_P[i] - W_FCFS[i] )  -  ( In_i - Out_i ),      |D_i| <= 2(k-1)L

with the §1.1 conventions: jobs are numbered in rank order (arrival, input index); at an
instant, completions are processed, then arrivals, then dispatches one at a time; the
dispatches form ONE sequence, `j -< i` means j precedes i in it, a maximal run of
dispatches at one instant is a phase; and

    In_i  = sum{ x_j : rank j > i and j -< i }
    Out_i = sum{ x_j : rank j < i and i -< j }

Both are defined by the dispatch SEQUENCE, not by the clock, so a job dispatched in i's
own phase before i counts its whole x_j in In_i (Remark 1.0).  Nobody has measured D_i on
the real trace; this directory does.

Units.  Everything that is summed is kept in exact int64 microseconds:

  * service times are metered as  x_us = round(x * 1e6),  which is exactly the conversion
    ../guard_variants/guardkern.py already applies when it charges a completed overtaker
    (`cus = int64(round(s[c] * 1e6))`), so In and Out are measured in the same currency
    the guard itself meters;
  * waits are metered as  W_us = round(start * 1e6) - round(a * 1e6)  from the float64
    clock the project simulator runs on.  The two roundings are each at most 0.5 us, so
    the reported D_us differs from the D of the exact float64 schedule by at most 2k us
    (<= 16 us here) -- 2.7e-7 L against a bound of 2(k-1)L = 840 s.  `ir_run.py` also
    computes D in float64 seconds and reports the max difference between the two, so the
    size of this quantisation is measured rather than assumed.

Everything outside this directory is imported read-only: `../main_v3/v31/v31_common.py`
(paths, trace loader, guard algebra, the v3.1 selected parameters) and, through it, the
v2.1 pipeline; `ir_kern.py` is a verbatim copy of `../guard_variants/guardkern.py` with
the dispatch sequence recorded, `ir_refsim.py` a verbatim copy of
`../guard_variants_referee/refsim.py` with the same addition.  Sealed semesters 2023-1,
2023-2 and 2024-1 are never opened.
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

import numpy as np                                                     # noqa: E402
import pandas as pd                                                    # noqa: E402

ROOT = r"<repo-root>"
HERE = os.path.dirname(os.path.abspath(__file__))
V31DIR = os.path.join(ROOT, "evidence", "main_v3", "v31")
GVDIR = os.path.join(ROOT, "evidence", "guard_variants")
REFDIR = os.path.join(ROOT, "evidence", "guard_variants_referee")
SCRATCH = r"<cache-dir>"
WORK = os.path.join(SCRATCH, "ident_res")
# short on purpose: <scratch>/ident_res/numba_cache/<44-char module dir>/<70-char file>
# overruns Windows' 260-character path limit and numba fails with FileNotFoundError.
NUMBA_CACHE = os.path.join(SCRATCH, "nb")
for _d in (WORK, NUMBA_CACHE):
    os.makedirs(_d, exist_ok=True)
os.environ["NUMBA_CACHE_DIR"] = NUMBA_CACHE

sys.path.insert(0, V31DIR)
import v31_common as V31                                               # noqa: E402
# v31_common points NUMBA_CACHE_DIR at <scratch>/mv31/numba_cache and pins the thread
# counts at 1; numba has already latched the value, so the env has to be rewritten AND
# numba's config reloaded.
import numba.core.config as _nbconfig                                  # noqa: E402
os.environ["NUMBA_CACHE_DIR"] = NUMBA_CACHE
for _v in ("OMP_NUM_THREADS", "NUMBA_NUM_THREADS"):
    os.environ[_v] = "4"
_nbconfig.reload_config()
assert _nbconfig.CACHE_DIR == NUMBA_CACHE, _nbconfig.CACHE_DIR
sys.path.insert(0, HERE)
import ir_kern as IK                                                   # noqa: E402

GK = V31.GK                       # the project kernel, uninstrumented
L = V31.L                         # 60.0 s service cap
L_US = int(round(L * 1e6))
TRACE = "primary"
REP = 0
LEVELS = (0, 1, 2)
MSLOTS = V31.MSLOTS

# the three policies of this study
POLICIES = ("spjf", "cap600", "adv")
POLICY_LABEL = {
    "spjf": "SPJF-tweedie (expected-cost score, unguarded)",
    "cap600": "CAP-G600 (guard, v3.1 selected parameters)",
    "adv": "SPJF-reversed (adversarial: score = -service time)",
}

# files whose content every number here depends on
EXTERNAL = {
    "guard_variants/guardkern.py": os.path.join(GVDIR, "guardkern.py"),
    "guard_variants_referee/refsim.py": os.path.join(REFDIR, "refsim.py"),
    "main_v3/v31/v31_common.py": os.path.join(V31DIR, "v31_common.py"),
    "main_v3/v31/selected_params.csv": os.path.join(V31DIR, "selected_params.csv"),
}


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
                  if f.startswith("ir_") and f.endswith(".py") and f != "ir_report.py")


def manifest():
    tab = [(f, sha256_file(os.path.join(HERE, f))) for f in core_scripts()]
    tab += [(f"[ext] {n}", sha256_file(p)) for n, p in sorted(EXTERNAL.items())
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
# policies
# --------------------------------------------------------------------------- #
def selected(family, G):
    s = pd.read_csv(os.path.join(V31DIR, "selected_params.csv"))
    r = s[(s.family == family) & (s.G == float(G))].iloc[0]
    return float(r.B0_base), float(r.eta)


def policy_spec(tag, k, Z):
    """(pred array, guardkern kwargs, human description)."""
    if tag == "spjf":
        return Z["tweedie"], dict(policy="pri"), "pred = Tweedie expected-cost score"
    if tag == "adv":
        return -Z["svc"], dict(policy="pri"), "pred = -service time (reversed score)"
    if tag == "cap600":
        b0b, eta = selected("cap", 600.0)
        b0 = b0b * k / 4.0
        kw, _eps, _ex, bm, _nc = V31.guard_kwargs("cap", k, B0=b0, eta=eta, G=600.0)
        return (Z["tweedie"], kw,
                f"guard, G = 600 s, B0 = {b0b:g}*k/4 = {b0:g} s, eta = {eta:g} "
                f"(eps = {eta * k:g}), Bmax = {bm:.1f} s")
    raise SystemExit(tag)


def run_policy(a, svc, k, pred, kw):
    """Instrumented run; asserts the waits are bit-identical to the project kernel's."""
    r = IK.run(a, svc, k, pred=pred, **kw)
    assert r.err == 0, "segment-tree window too small"
    assert r.n_disp == len(a), (r.n_disp, len(a))
    g = GK.run(a, svc, k, pred=pred, **kw)
    assert g.err == 0
    bad = int((r.w != g.w).sum())
    assert bad == 0, f"instrumented kernel disagrees with guardkern on {bad} jobs"
    # the dispatch sequence is a permutation, and its clock is non-decreasing
    assert np.array_equal(np.sort(r.dord), np.arange(len(a)))
    order = np.empty(len(a), np.int64)
    order[r.dord] = np.arange(len(a))
    assert np.all(np.diff(r.dtime[order]) >= 0.0)
    return r


def us(x):
    """float64 seconds -> exact int64 microseconds.  `np.rint` is round-half-to-even,
    which is what `round()` does inside the numba kernel, so a service time is metered
    here exactly as guardkern meters it when it charges a completed overtaker."""
    return np.rint(np.asarray(x, np.float64) * 1e6).astype(np.int64)
