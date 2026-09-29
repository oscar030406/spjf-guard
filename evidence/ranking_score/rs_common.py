"""Shared setup for the ranking-score study.

Read-only import of evidence/codebench_service_v2/service_precheck_v2.py (the verified
pipeline: features under the availability rule on the jittered clock, rolling-origin
forward models, simulator, overlay builder, level_ks, week-block bootstrap).  Nothing in
that folder or its v1 parent is written to; __pycache__ is disabled before the import.

Parameters of the whole study live here so every script carries them.
"""
from __future__ import annotations

import os
import sys

sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
for _v in ("PYTHONHOME", "PYTHONPATH", "UV_INTERNAL__PYTHONHOME"):
    os.environ.pop(_v, None)

import numpy as np                                                    # noqa: E402
import pandas as pd                                                   # noqa: E402

ROOT = r"<repo-root>"
V2DIR = os.path.join(ROOT, "evidence", "codebench_service_v2")
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = (r"<cache-dir>"
         r"\cb_v2_cache_r4")
# our own scratch (predictions, per-trace arrays); never inside the project tree
WORK = (r"<cache-dir>"
        r"\rank_score")
os.makedirs(WORK, exist_ok=True)

sys.path.insert(0, V2DIR)
import service_precheck_v2 as SP                                      # noqa: E402

# ---- study parameters ------------------------------------------------------ #
CFG = SP.PRIMARY                 # "ires0": arrival = t - C, delta = 0, jittered clock
SEED = SP.SEED                   # 3, as the verified forward models
NTHREADS = 4                     # other jobs run CPU-heavy work concurrently on this host
VALID_SEM = "2022-1"             # every threshold/choice is fixed here and earlier
TEST_SEM = "2022-2"              # dev test; 2023-1/2023-2/2024-1 are never read
POOL = SP.POOL60                 # the overlay pool = the 60 s-limit DEV semesters
FEATS = SP.GROUPS["M4"]          # the M4 feature set, unchanged
HEAVY_Q = 0.95                   # heavy = C_cap above the fixed 2018-1..2019-2 p95

PRED_PARQUET = os.path.join(WORK, f"rs_pred_{CFG}.parquet")
CAL_DIR = HERE


def say(*a):
    print(*a, flush=True)


def load_base():
    """events, D, S, X (M4 design matrix over submission rows) for CFG."""
    ev = SP.load_events(CACHE)
    D = SP.prep(ev)
    S = SP.static_sub(ev, D)
    arr, avail = SP.times(D, CFG)
    F = pd.read_parquet(SP.feat_path(CACHE, CFG))
    X = SP.build_X(S, F, arr[D["sidx"]])
    return ev, D, S, X, arr, avail


def targets_in_order(D, arr):
    """DEV semesters in calendar order of their first arrival (SP.stage_forward's order)."""
    first = {s: float(arr[D["sem"] == s].min()) for s in SP.DEV}
    return sorted(SP.DEV, key=first.get), first
