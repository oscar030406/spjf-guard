"""CodeBench service-side pre-check, v2: history features that respect when a past
result becomes available, forward (rolling-origin) predictions in the scheduling
simulation, and an overtake-budget guard whose accounting uses completion events.

Why v2.  v1 (../codebench_service/service_precheck.py, build_history) let submission i
read every strictly earlier ROW j < i, including runs that had not finished and rows
with the same timestamp.  Here a past record j reaches submission i only as follows:

    arrival-only information (j exists, its arrival time)      arrival[j] <  arrival[i]
    result information (cost, error, grade, heavy flag and      done[j] + delta <= arrival[i]
      anything derived from them, incl. relational stats)        and arrival[j] < arrival[i]

done is the ASSUMED RESULT-AVAILABILITY TIME (zero-queue completion approximation): the
log records one timestamp per run, not a completion time, so done is derived from it
under one of two readings of that timestamp ts:

    I-res  ts = result time  :  arrival = ts - C,  done = ts        PRIMARY
    I-sub  ts = receipt time :  arrival = ts,      done = ts + C    sensitivity

I-res is primary: evidence/codebench_semantics/ found the SUBMITION header to be the end
of the run (research_plan.md 2.2).  TEST blocks have no execution time and an unresolved
header; they never enter the simulation.  For features, a TEST's existence and time are
known from ts, its outcome (the error flag, the only TEST outcome any feature reads) from
done = ts + 60 s (ts + 600 s in ires0_t600), under both readings.

Clock jitter.  Every DEV header ts is a whole second, so under I-res arrival = ts - C
carries frac(-C) and every time gap read by a feature leaks the target's fraction.  Each
record j (TEST and SUBMITION) gets u_j ~ U[0,1) from a keyed hash of its stable id
(semester, class, user, assessment, exercise, blk_i) and ts'_j = ts_j + u_j replaces ts in
every clock above, in the simulated arrivals and in the context columns.  Co-ending groups
and repeated blocks stay defined on the raw integer ts.  Config 'clock0' = ires0 on the
un-jittered clock (P1 + forward sensitivity only).  C is the raw
execution_time; the prediction target and the simulator's service time are
C_cap = min(C, 60) (runs over 60 s before Sept 2019 are teardown artifacts, not demand).
delta (result-return lag, added to every done) is {0, 600} s under I-res and
{0, 60, 600, 3600} s under I-sub.  The second condition of the result rule only bites
when done + delta == arrival (zero cost at delta 0): a result is never visible while the
record itself is not.  2020-2022 SUBMITION blocks with C == 0 (empty outputs, never run)
stay in features and labels and are removed from the simulated traces only.

Simulation = a COUNTERFACTUAL shared judge pool: the original platform gave every
student a private Docker container and had no shared queue; the traces keep the real
arrival times and costs, the pool, queue and order are ours.  Two comparisons: PURE
(every policy sees the same enqueue times; Proposition 3 applies at k = 1) and
END-TO-END (predictive policies enqueue after their measured feature + inference
latency; no bound claimed).  Forward predictions only (rolling origin, frozen per
target semester); P1's cross-semester numbers never feed the simulation.

Overlay pool (research_plan.md 2.4, revision 27): the 60 s-limit DEV semesters 2020-ERE,
2020-2, 2021-1, 2021-2, 2022-1, 2022-2 (2020-1 incomplete, 2019-2 truncated).  'pool19'
(2019-1 added, the previous round's pool) is a labelled sensitivity.  The number of
overlay copies per trace is the smallest that gives k >= 4 at the rho 1.0 level and three
distinct k in every rep 0-4 (probe stored in copies_probe.csv).  Primary metric:
deadline-window p99 wait (research_plan.md 6.5); uncertainty = paired bootstrap over whole
weeks of the overlay timeline (2,000 resamples, the same week draws for every policy,
level and overlay of a trace).

Guard (overtake budget B).  over[i] = total TRUE service time of jobs that arrived after
i (stable rank on (arrival, id)) and have COMPLETED while i still waits; the scheduler
never reads the service time of a job that has not completed.  Kept with a Fenwick tree
over arrival rank in integer microseconds: on completion of j add C[j] at rank[j];
over[i] = suffix sum over ranks > rank[i].  When a worker frees (after applying the
completions and then the arrivals at that instant): if over[head] >= B for the
earliest-arrived waiting job, serve it, else serve the smallest predicted cost.  The
per-job bound W_guard <= W_FCFS + B + 60 is asserted for k = 1 only.

Stages (each < 10 min when split as in README.md; results cached under --cache; every
stage log starts with the script's sha256 and `report` refuses to run on a mismatch):

    selftest   simulator checks (Lindley / Kiefer-Wolfowitz, brute-force guard, audit burst,
               PK), week-bootstrap quantile vs brute force, incremental busy-hour probe
    load       read the DEV parquet tables once, cache the merged event table; calendars,
               zero-cost, repeated-block and co-ending group counts, clock jitter checks
    features   event-sweep features per configuration          --configs ires0,...
    leak       3,000 random DEV submissions recomputed from scratch per config, vs the sweep
               and vs v1; two-event and TEST-lag perturbation tests; fractional-arrival check
    p1         M0-M6, 3 seeds, test 2022-2          --configs ires0,... [--train core|remote]
    boot       user-block bootstrap, 2,000 resamples: AUROC CIs (all test rows / rows outside
               co-ending groups) and paired deltas               --configs ires0,...
    forward    rolling-origin predictions for the simulation
               --configs ires0,ires600,isub0,clock0,v1
    latency    streaming feature + LightGBM latency over 20,000 submissions (ires0)
    pool       the class-semesters of each trace, the overlay-copies probe (copies.csv,
               copies_probe.csv), bootstrap week sets, busiest-hour composition of every trace
    p2         multi-server overlay, k at busy-hour rho 0.5/0.8/1.0, one rep per call;
               --configs ires0 --variant base|pool19|sbatch|sdrop|dedup --reps 0 [--workers 10]
               (isub0: --configs isub0 --variant base); writes the per-policy week-bootstrap
               replicates of mean and deadline-window p99 wait
    p2boot     gains and pairwise differences with week-block bootstrap CIs, per trace
    guardk1    single-server configuration (busy-hour rho in [0.78, 0.82] at k = 1), per-job
               Proposition 3 assertion                  --configs ires0 --reps 0,1,2
    report     assemble out_service_v2.txt (summaries first, then the stage logs)

HOLDOUT 2023-1, 2023-2, 2024-1 is never opened.  No source code text is stored or
printed (the latency stage times code_vector() on the extracted 2016-2 sample in memory).

Usage (from any directory; no scikit-learn: the two sklearn metrics v1 imports are
replaced by the numpy versions below, checked in selftest):
    uv run --with pandas --with numpy --with scipy --with pyarrow --with lightgbm \
        python service_precheck_v2.py --stage <name> [--configs ..] [--reps ..] [--cache DIR]
"""
from __future__ import annotations

import os
import sys

sys.dont_write_bytecode = True                   # no __pycache__ here or in v1's folder,
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"      # also in spawned worker processes
for _v in ("PYTHONHOME", "PYTHONPATH", "UV_INTERNAL__PYTHONHOME"):
    os.environ.pop(_v, None)

import argparse
import hashlib
import heapq
import re
import tempfile
import time
import types
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from itertools import accumulate
from math import log1p, sqrt
from time import perf_counter

import numpy as np
import pandas as pd
from scipy.stats import kendalltau, rankdata

import lightgbm as lgb


def roc_auc_score(h, s):
    """Tie-aware AUROC (Mann-Whitney with mid-ranks); equals sklearn's roc_auc_score."""
    h = np.asarray(h).astype(bool)
    r = rankdata(np.asarray(s, float))
    n1 = int(h.sum())
    n0 = len(h) - n1
    return float((r[h].sum() - n1 * (n1 + 1) / 2.0) / (n1 * n0))


def average_precision_score(h, s):
    """sklearn's step-wise AP: sum over distinct thresholds of (R_n - R_{n-1}) * P_n."""
    h = np.asarray(h).astype(float)
    s = np.asarray(s, float)
    o = np.argsort(-s, kind="mergesort")
    s, h = s[o], h[o]
    last = np.r_[np.flatnonzero(s[1:] != s[:-1]), len(s) - 1]   # last index of each tie block
    tp = np.cumsum(h)[last]
    fp = (last + 1) - tp
    prec, rec = tp / (tp + fp), tp / h.sum()
    return float(np.sum(np.diff(np.r_[0.0, rec]) * prec))


try:                                     # v1 imports two sklearn metrics at module level
    import sklearn.metrics  # noqa: F401
except ImportError:
    _skm = types.ModuleType("sklearn.metrics")
    _skm.roc_auc_score, _skm.average_precision_score = roc_auc_score, average_precision_score
    _sk = types.ModuleType("sklearn")
    _sk.metrics = _skm
    sys.modules["sklearn"], sys.modules["sklearn.metrics"] = _sk, _skm

ROOT = r"<repo-root>"
PQ = os.path.join(ROOT, "data", "codebench", "parquet")
V1DIR = os.path.join(ROOT, "evidence", "codebench_service")
RAW_SAMPLE = os.path.join(ROOT, "data", "codebench", "raw", "2016-2")
HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.abspath(__file__), "rb") as _f:
    SCRIPT_SHA = hashlib.sha256(_f.read()).hexdigest()
sys.path.insert(0, V1DIR)
import service_precheck as v1   # noqa: E402  read-only reuse of v1 definitions
import code_features as v1cf    # noqa: E402

SEED = 3
SEEDS = (3, 4, 5)
TRAIN_CORE = ["2018-1", "2018-2", "2019-1", "2019-2"]
REMOTE = ["2020-ERE", "2020-1", "2020-2", "2021-1", "2021-2"]
VALID = ["2022-1"]
TEST = ["2022-2"]
DEV = TRAIN_CORE + REMOTE + VALID + TEST
HOLDOUT = ["2023-1", "2023-2", "2024-1"]
FORWARD_FROM = "2019-1"
L_CAP = 60.0
# (reading, delta, TEST-outcome lag in s, jittered clock); PRIMARY first
CONFIGS = {"ires0": ("res", 0.0, 60.0, True), "ires600": ("res", 600.0, 60.0, True),
           "ires0_t600": ("res", 0.0, 600.0, True),
           "isub0": ("sub", 0.0, 60.0, True), "isub60": ("sub", 60.0, 60.0, True),
           "isub600": ("sub", 600.0, 60.0, True), "isub3600": ("sub", 3600.0, 60.0, True),
           "clock0": ("res", 0.0, 60.0, False)}
PRIMARY = "ires0"
P1_CONFIGS = list(CONFIGS) + ["v1"]
BOOT_CONFIGS = ("ires0", "clock0", "ires600", "ires0_t600", "isub0", "isub600", "v1")
FORWARD_CONFIGS = ["ires0", "ires600", "isub0", "clock0"]
FORWARD_MODELS = {"ires0": ("M1", "M3", "M4", "M5"), "isub0": ("M1", "M4", "M5"),
                  "clock0": ("M4", "M5"), "ires600": ("M4",), "v1": ("M4",)}
# per-record clock jitter u in [0,1): keyed hash of the record id (16-byte key)
JITTER_KEY = "cbjitter20260919"
JITTER_ID = ["semester", "class", "user", "assessment", "exercise", "blk_i"]
# not run through the simulation: 2019-2 (archive stops 2019-09-19) and 2020-1 (~3% missing)
# are kept for per-event training/evaluation only, not for load or peak statistics
LOAD_EXCLUDE = ["2019-2", "2020-1"]
ZERO_DROP_SEMS = ["2020-ERE", "2020-1", "2020-2", "2021-1", "2021-2", "2022-1", "2022-2"]
POOL60 = ["2020-ERE", "2020-2", "2021-1", "2021-2", "2022-1", "2022-2"]   # primary overlay pool
POOL19 = ["2019-1"] + POOL60                                             # sensitivity 'pool19'
VARIANTS = ("base", "pool19", "sbatch", "sdrop", "dedup")    # simulated job sets, see p2_inputs
# simulated traces: name -> (config, variant, reps simulated)
TRACES = {"primary": (PRIMARY, "base", (0, 1, 2, 3, 4)), "pool19": (PRIMARY, "pool19", (0, 1, 2)),
          "sbatch": (PRIMARY, "sbatch", (0, 1, 2)), "sdrop": (PRIMARY, "sdrop", (0, 1, 2)),
          "isub0": ("isub0", "base", (0, 1, 2)), "dedup": (PRIMARY, "dedup", (0,))}
K_MIN_RHO1 = 4            # overlay copies: k >= 4 at the rho 1.0 level, three distinct k
PROBE_REPS = (0, 1, 2, 3, 4)
K1_WINDOW = (0.78, 0.82)  # busy-hour rho of the single-server configuration
K1_TARGET = 0.80
REF_MON = 1578268800      # 2020-01-06 00:00:00 UTC, the Monday every copy is aligned to
WEEK = 604800
N_REP = 5
N_BOOT = 2000
N_BOOT_P2 = 2000
BOOT_P2_SEED = 20260919
N_LEAK = 3000
N_LAT = 20000
GUARD_B = (30.0, 120.0, 600.0)
RHOS = (0.5, 0.8, 1.0)
N_WORKERS = 10

FEAT_CODE = v1.FEAT_CODE
HIST_COLS = v1.HIST_COLS
REL_COLS = v1.REL_COLS
CTX_COLS = v1.CTX_COLS
PERM_COLS = [c + "_perm" for c in REL_COLS]
AUX_COLS = ["ex_nres", "u_nres"]          # available-result counts (cold-start masks only)
FEAT_COLS = HIST_COLS + REL_COLS + PERM_COLS + AUX_COLS
X_COLS = FEAT_CODE + CTX_COLS + HIST_COLS + REL_COLS + PERM_COLS
COLI = {c: i for i, c in enumerate(X_COLS)}
GROUPS = v1.GROUPS
MODELS = ["M0", "M1", "M2", "M3", "M4", "M5", "M6"]

_OUT: list[str] = []
T0 = time.time()


def variants():
    return (("core", list(TRAIN_CORE)), ("remote", TRAIN_CORE + REMOTE))


def say(*a):
    s = " ".join(str(x) for x in a)
    _OUT.append(s)
    print(s, flush=True)


def head(t):
    say("\n" + "=" * 78)
    say(t)
    say("=" * 78)


def dump(cache, name):
    """Write the stage log.  Line 1 = the sha256 of this script (checked by `report`)."""
    os.makedirs(os.path.join(cache, "txt"), exist_ok=True)
    hdr = [f"script_sha256 {SCRIPT_SHA}",
           f"command {' '.join(sys.argv[1:])}  finished {time.strftime('%Y-%m-%d %H:%M:%S')}"]
    with open(os.path.join(cache, "txt", name + ".txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(hdr + _OUT) + "\n")
    with open(os.path.join(cache, "manifest.tsv"), "a", encoding="utf-8") as f:
        f.write(f"{name}\t{SCRIPT_SHA}\t{time.strftime('%Y-%m-%d %H:%M:%S')}\t{' '.join(sys.argv[1:])}\n")
    _OUT.clear()


def el():
    return f"[{time.time() - T0:6.0f}s]"


def stamp(x):
    return str(pd.Timestamp(float(x), unit="s").floor("s"))


# --------------------------------------------------------------------------- #
# load (same tables, same merge, same order as v1.load_events)
# --------------------------------------------------------------------------- #
def load_events(cache):
    p = os.path.join(cache, "ev.parquet")
    if os.path.exists(p):
        return pd.read_parquet(p)
    ev, cf, ass = [], [], []
    for s in DEV:
        assert s not in HOLDOUT
        e = pd.read_parquet(os.path.join(PQ, "events", f"{s}.parquet"))
        e["blk_i"] = e.groupby(["class", "user", "assessment", "exercise"],
                               observed=True).cumcount().astype("int32")
        ev.append(e)
        cf.append(pd.read_parquet(os.path.join(PQ, "code_features", f"{s}.parquet")))
        ass.append(pd.read_parquet(os.path.join(PQ, "assessments", f"{s}.parquet")))
    ev = pd.concat(ev, ignore_index=True)
    cf = pd.concat(cf, ignore_index=True)
    ass = pd.concat(ass, ignore_index=True)
    key = ["semester", "class", "user", "assessment", "exercise", "blk_i"]
    cf = cf.drop(columns=["kind"]).rename(columns={"code_len": "code_len_cf"})
    ev = ev.merge(cf, on=key, how="left")
    ok = (ev["code_len"] == ev["code_len_cf"]).mean()
    print(f"events={len(ev):,}  code-feature join: matched code_len on {ok:.5f} of rows")
    ev = ev.drop(columns=["code_len_cf"])
    ass = ass.rename(columns={"start": "a_start", "end": "a_end", "type": "a_type",
                              "weight": "a_weight", "n_exercises": "a_nex"})
    ev = ev.merge(ass[["semester", "class", "assessment", "a_type", "a_weight",
                       "a_start", "a_end", "a_nex"]],
                  on=["semester", "class", "assessment"], how="left")
    ev["remote"] = ev["semester"].isin(REMOTE)
    ev = ev.sort_values("ts", kind="mergesort").reset_index(drop=True)
    os.makedirs(cache, exist_ok=True)
    ev.to_parquet(p, index=False)
    return ev


def _secs(s):
    return (s - pd.Timestamp("1970-01-01")).dt.total_seconds().values.astype("float64")


def jitter_u(ev, key=None):
    """u_j ~ U[0,1) per record, a deterministic function of the record's stable id
    (semester, class, user, assessment, exercise, blk_i; blk_i = the record's position among
    the blocks of its key in the semester's events table) and the fixed key JITTER_KEY:
    the top 53 bits of pandas' keyed SipHash of the id, times 2^-53.  Independent of the
    row order of `ev`.  Frames without blk_i (synthetic tests) number their rows per key."""
    idf = ev.reindex(columns=[c for c in JITTER_ID if c != "blk_i"]).astype(str)
    if "blk_i" in ev.columns:
        idf["blk_i"] = ev["blk_i"].values.astype(np.int64)
    else:
        idf["blk_i"] = idf.groupby(list(idf.columns), sort=False).cumcount().values.astype(np.int64)
    h = pd.util.hash_pandas_object(idf, index=False, hash_key=key or JITTER_KEY).values
    return (h >> np.uint64(11)).astype(np.float64) * 2.0 ** -53


def prep(ev, fixed=None):
    """Integer keys and numeric arrays for the sweep.  Thresholds and the M6
    permutation exactly as v1.part1, unless `fixed` = (heavy_thr, cuts) is given
    (synthetic frames: identity permutation)."""
    D = {}
    sub = (ev["kind"].astype(str).values == "submit") & ev["exec_time"].notna().values
    sidx = np.flatnonzero(sub)
    D["sub"], D["sidx"] = sub, sidx
    D["rowof"] = np.full(len(ev), -1, np.int64)
    D["rowof"][sidx] = np.arange(len(sidx))
    D["ts"] = ev["ts"].values.astype("datetime64[s]").astype("int64").astype("float64")
    D["u"] = jitter_u(ev)                   # ts' = ts + u is the clock of every config but clock0
    D["C"] = ev["exec_time"].values.astype("float64")
    D["sem"] = np.asarray(ev["semester"].astype(str), dtype=object)
    ex, ex_uni = pd.factorize(ev["exercise"])
    us, _ = pd.factorize(ev["user"])
    cl = ev["semester"].astype(str) + "|" + ev["class"].astype(str)
    cls, _ = pd.factorize(cl)
    asm_s = (cl + "|" + ev["assessment"].astype(str)).values
    asm, asm_uni = pd.factorize(asm_s)
    D["ex"], D["us"], D["cls"], D["asm"] = (x.astype(np.int64) for x in (ex, us, cls, asm))
    D["NE"], D["NC"] = int(ex.max()) + 1, int(cls.max()) + 1
    D["errf"] = ev["has_error"].values.astype("float64")
    D["ntc"] = ev["n_testcases"].values.astype("float64")
    Cz = np.nan_to_num(D["C"])
    D["lg"] = np.log1p(Cz)
    if fixed is None:
        y32 = ev["exec_time"].values                      # float32, as v1
        tr = np.isin(D["sem"][sidx], TRAIN_CORE)
        D["heavy_thr"] = float(np.quantile(np.minimum(y32[sidx][tr], L_CAP), .95))
        lt = np.log1p(np.minimum(y32[sidx][tr], L_CAP))
        D["cuts"] = (float(np.quantile(lt, 1 / 3)), float(np.quantile(lt, 2 / 3)))
        rng = np.random.default_rng(SEED)            # M6 permutation built as v1.part1
        uex = np.asarray(ev["exercise"].unique(), dtype=object)
        uas = np.unique(asm_s).astype(object)
        pe = dict(zip(uex, rng.permutation(uex)))
        pa = dict(zip(uas, rng.permutation(uas)))
        D["perm_str"] = (pe, pa)
        exc = {s: i for i, s in enumerate(ex_uni)}
        asc = {s: i for i, s in enumerate(asm_uni)}
        D["pex"] = np.array([exc[pe[s]] for s in ex_uni], np.int64)[D["ex"]]
        D["pas"] = np.array([asc[pa[s]] for s in asm_uni], np.int64)[D["asm"]]
        # repeated submissions: same key and second, same cost, grade, error, test-case
        # count and every static code feature -- the closest the parquet columns get to
        # byte-identical blocks (no text is kept).  Later members flagged; load side keeps
        # them by default, the --dedup sensitivity drops them.
        dcols = ["semester", "class", "user", "assessment", "exercise", "ts", "exec_time", "grade",
                 "has_error", "error_type", "n_testcases", "code_len", "code_lines"] + FEAT_CODE
        e = ev.iloc[sidx][dcols].copy()
        for c in ("error_type",):
            e[c] = e[c].astype(str)
        D["dup"] = np.zeros(len(ev), bool)
        D["dup"][sidx] = e.duplicated(keep="first").values
        # submission rows (sidx order) allowed into a simulated trace, and co-ending groups
        D["simok"] = ~((D["C"][sidx] == 0) & np.isin(D["sem"][sidx], ZERO_DROP_SEMS))
        D["coend"] = coend_groups(D)
    else:
        D["heavy_thr"], D["cuts"] = fixed
        D["pex"], D["pas"] = D["ex"].copy(), D["asm"].copy()
    D["hv"] = (Cz > D["heavy_thr"]).astype("float64")
    return D


def coend_groups(D):
    """Co-ending group id per submission row (sidx order), -1 when solo.  A group is a
    maximal set of SUBMITION blocks of the same user in the same semester with the same
    header second ts, size >= 2, taken over the rows that may enter a simulated trace
    (the 2020-2022 C == 0 blocks never ran and would pair a real run with its ghost)."""
    s, ok = D["sidx"], D["simok"]
    r = np.flatnonzero(ok)
    df = pd.DataFrame({"sem": D["sem"][s][r], "u": D["us"][s][r], "t": D["ts"][s][r]})
    g = df.groupby(["sem", "u", "t"], sort=False).ngroup().values
    gid = np.full(len(s), -1, np.int64)
    gid[r] = np.where(np.bincount(g)[g] >= 2, g, -1)
    return gid


def static_sub(ev, D):
    """Per-submission columns that do not depend on the timestamp reading."""
    e = ev.iloc[D["sidx"]]
    return {"code": np.column_stack([e[c].values.astype("float32") for c in FEAT_CODE]),
            "a_is_exam": (e["a_type"].astype(str).values == "exam").astype("float32"),
            "a_weight": pd.to_numeric(e["a_weight"], errors="coerce").values.astype("float32"),
            "a_nex": pd.to_numeric(e["a_nex"], errors="coerce").values.astype("float32"),
            "is_remote": e["remote"].values.astype("float32"),
            "a_end": _secs(e["a_end"]), "a_start": _secs(e["a_start"]),
            "cs": np.asarray(e["semester"].astype(str) + "|" + e["class"].astype(str), dtype=object),
            "user": np.asarray(e["user"].astype(str), dtype=object)}


def times(D, cfg):
    """(arrival, availability time = assumed done + delta) for every event, on the
    jittered clock ts' = ts + u (raw ts for clock0).  A TEST block (no execution time)
    arrives at ts' and its outcome is done at ts' + lag.  'v1' keeps v1's reading
    (arrival = ts', I-sub) for the arrival-time context columns."""
    if cfg == "v1":
        cfg = "isub0"
    mode, delta, test_lag, jit = CONFIGS[cfg]
    ts = D["ts"] + D["u"] if jit else D["ts"]
    sub = D["sub"]
    C = np.where(sub, np.nan_to_num(D["C"]), 0.0)
    if mode == "sub":
        arr, done = ts.copy(), ts + C
    else:
        arr, done = ts - C, ts.copy()
    done = np.where(sub, done, ts + test_lag)
    return arr, done + delta


def ctx_block(S, arr_s):
    hour = np.floor(np.mod(arr_s, 86400.0) / 3600.0)
    dow = np.mod(np.floor(arr_s / 86400.0) + 3.0, 7.0)          # 1970-01-01 = Thursday
    return np.column_stack([S["a_is_exam"], S["a_weight"], S["a_nex"],
                            (S["a_end"] - arr_s) / 3600.0, (arr_s - S["a_start"]) / 3600.0,
                            hour, dow, S["is_remote"]]).astype("float32")


def build_X(S, F, arr_s):
    X = np.empty((len(arr_s), len(X_COLS)), np.float32)
    X[:, :len(FEAT_CODE)] = S["code"]
    X[:, len(FEAT_CODE):len(FEAT_CODE) + len(CTX_COLS)] = ctx_block(S, arr_s)
    X[:, len(FEAT_CODE) + len(CTX_COLS):] = F[HIST_COLS + REL_COLS + PERM_COLS].values
    return X


# --------------------------------------------------------------------------- #
# the event sweep
# --------------------------------------------------------------------------- #
def sweep(D, arr, avail, probe=None, cb=None):
    """One pass over a merged stream of events sorted by (time, type, record):
         type 0  availability of a result (visible to arrivals at the same time)
         type 1  arrival of a submission: READ its features
         type 2  arrival of any record: register that it exists (after all reads at
                 the same time, so equal arrival times never see each other)
         type 3  availability of a result whose availability equals its own arrival
                 (zero cost, delta 0): after the reads, never seen by itself or by
                 records arriving at the same instant
    State is keyed by the true ids; the M6 read uses the permuted exercise/assessment.
    Returns (hist, rel, rel_perm, aux) for the submission rows in D['sidx'] order."""
    n = len(arr)
    sub, sidx = D["sub"], D["sidx"]
    ns = len(sidx)
    if not np.all(avail >= arr):
        raise AssertionError("a result became available before its own arrival")
    zero = avail == arr
    T = np.concatenate([avail, arr[sidx], arr])
    TY = np.concatenate([np.where(zero, 3, 0), np.ones(ns, np.int64), np.full(n, 2, np.int64)])
    RC = np.concatenate([np.arange(n), sidx, np.arange(n)])
    o = np.lexsort((RC, TY, T))
    TYl, RCl = TY[o].tolist(), RC[o].tolist()
    del T, TY, RC, o

    NE, NC = D["NE"], D["NC"]
    exl, usl, asl, cll = (D[k].tolist() for k in ("ex", "us", "asm", "cls"))
    pexl, pasl = D["pex"].tolist(), D["pas"].tolist()
    subl, errl = sub.tolist(), D["errf"].tolist()
    lgl, hvl, ntcl = D["lg"].tolist(), D["hv"].tolist(), D["ntc"].tolist()
    arrl, rowof = arr.tolist(), D["rowof"].tolist()
    lo, hi = D["cuts"]
    NAN = float("nan")
    N8, N6 = (NAN,) * 8, (NAN,) * 6

    EX, U, EXN, UN, UEA, UEL, ULA, ULE = {}, {}, {}, {}, {}, {}, {}, {}
    ASS, ASSEX, EXT, EXC = {}, {}, {}, {}
    outH, outR, outP, outA = [None] * ns, [None] * ns, [None] * ns, [None] * ns

    for typ, j in zip(TYl, RCl):
        if typ == 1:                                   # ---------- READ ----------
            row = rowof[j]
            timed = probe is not None and probe[row]
            if timed:
                t0 = perf_counter()
            t = arrl[j]
            e = exl[j]
            u = usl[j]
            ue = u * NE + e
            E = EX.get(e)
            if E is not None:
                nn, sl, sl2, ne, nh, sn, dq = E
                m = sl / nn
                s = sorted(dq)
                L = len(s) - 1
                exs = (m, sqrt(max(sl2 / nn - m * m, 0.0)), s[min(L, int(.5 * L + .5))],
                       s[min(L, int(.9 * L + .5))], s[-1], ne / nn, nh / nn, sn / nn)
                exr = nn
            else:
                exs, exr = N8, 0
            Uu = U.get(u)
            if Uu is not None:
                nn, sl, sl2, ne, nh, dq = Uu
                m = sl / nn
                s = sorted(dq)
                L = len(s) - 1
                uss = (m, sqrt(max(sl2 / nn - m * m, 0.0)), s[min(L, int(.5 * L + .5))],
                       s[min(L, int(.9 * L + .5))], ne / nn, nh / nn)
                ur = nn
                terc = 0 if m < lo else (1 if m < hi else 2)
            else:
                uss, ur, terc = N6, 0, 1
            a = UEA.get(ue)
            if a is not None:
                uen, uesec = a[0], log1p(max(t - a[1], 0.0))
            else:
                uen, uesec = 0, NAN
            b = UEL.get(ue)
            uel, uee = (b[2], b[3]) if b is not None else (NAN, NAN)
            la = ULA.get(u)
            pes = log1p(max(t - la, 0.0)) if la is not None else NAN
            le = ULE.get(u)
            pee = le[2] if le is not None else NAN
            H = (EXN.get(e, 0),) + exs + (UN.get(u, 0),) + uss + (uen, uel, uee, uesec, pee, pes)
            c = cll[j]
            rels = []
            for ek, ak in ((e, asl[j]), (pexl[j], pasl[j])):
                K = EXT.get(ek * 3 + terc)
                r0, r1 = (K[1] / K[0], K[2] / K[0]) if K is not None else (NAN, NAN)
                r2 = r3 = NAN
                A = ASS.get(ak)
                if A is not None:
                    AE = ASSEX.get(ak * NE + ek)
                    a0, a1, a2 = (AE[0], AE[1], AE[2]) if AE is not None else (0, 0.0, 0.0)
                    rest = A[0] - a0
                    if rest > 0:
                        r2, r3 = (A[1] - a1) / rest, (A[2] - a2) / rest
                K3 = EXC.get(ek * NC + c)
                r4 = K3[1] / K3[0] if K3 is not None else NAN
                rels.append((r0, r1, r2, r3, r4))
            outH[row], outR[row], outP[row], outA[row] = H, rels[0], rels[1], (exr, ur)
            if timed:
                cb(row, H, rels[0], t0)
        elif typ == 2:                                 # ---------- REGISTER ----------
            u = usl[j]
            ULA[u] = arrl[j]
            if subl[j]:
                e = exl[j]
                EXN[e] = EXN.get(e, 0) + 1
                UN[u] = UN.get(u, 0) + 1
                ue = u * NE + e
                a = UEA.get(ue)
                UEA[ue] = ((a[0] if a is not None else 0) + 1, arrl[j])
        else:                                          # ---------- AVAILABLE ----------
            u = usl[j]
            aj = arrl[j]
            le = ULE.get(u)
            if le is None or aj > le[0] or (aj == le[0] and j > le[1]):
                ULE[u] = (aj, j, errl[j])
            if subl[j]:
                e = exl[j]
                x, h, er = lgl[j], hvl[j], errl[j]
                E = EX.get(e)
                if E is None:
                    EX[e] = [1, x, x * x, er, h, ntcl[j], deque([x], maxlen=120)]
                else:
                    E[0] += 1; E[1] += x; E[2] += x * x; E[3] += er; E[4] += h
                    E[5] += ntcl[j]; E[6].append(x)
                Uu = U.get(u)
                if Uu is None:
                    Uu = U[u] = [1, x, x * x, er, h, deque([x], maxlen=120)]
                else:
                    Uu[0] += 1; Uu[1] += x; Uu[2] += x * x; Uu[3] += er; Uu[4] += h
                    Uu[5].append(x)
                m = Uu[1] / Uu[0]
                tag = 0 if m < lo else (1 if m < hi else 2)
                ue = u * NE + e
                b = UEL.get(ue)
                if b is None or aj > b[0] or (aj == b[0] and j > b[1]):
                    UEL[ue] = (aj, j, x, er)
                aa = asl[j]
                for d, key in ((ASS, aa), (ASSEX, aa * NE + e), (EXT, e * 3 + tag),
                               (EXC, e * NC + cll[j])):
                    K = d.get(key)
                    if K is None:
                        d[key] = [1, x, h]
                    else:
                        K[0] += 1; K[1] += x; K[2] += h
    return (np.array(outH, np.float32).reshape(ns, len(HIST_COLS)),
            np.array(outR, np.float32).reshape(ns, len(REL_COLS)),
            np.array(outP, np.float32).reshape(ns, len(REL_COLS)),
            np.array(outA, np.int64).reshape(ns, 2))


def feat_path(cache, cfg):
    return os.path.join(cache, f"feat_{cfg}.parquet")


def stage_load(ev, D, cache):
    head("LOAD")
    s = D["sidx"]
    say(f"DEV semesters {DEV[0]}..{DEV[-1]} ({len(DEV)}); events {len(ev):,}; "
        f"submissions with execution time {len(s):,}")
    say(f"heavy class: C_cap > train(2018-1..2019-2) p95 = {D['heavy_thr']:.4f} s; user-slowness "
        f"tercile cuts {D['cuts'][0]:.4f} {D['cuts'][1]:.4f} (as v1)")
    sem_s = D["sem"][s]
    z = pd.Series(sem_s[D["C"][s] == 0]).value_counts().reindex(DEV).fillna(0).astype(int)
    say(f"submissions with C = 0 (result available at their own arrival at delta 0): "
        f"{int(z.sum()):,}; per semester: " + ", ".join(f"{k_} {v_}" for k_, v_ in z.items()))
    say(f"  of which 2020-2022 (removed from the simulated traces only; features and labels keep "
        f"them): {int(z[ZERO_DROP_SEMS].sum()):,}")
    ez = ev.iloc[s[(D["C"][s] == 0) & np.isin(sem_s, ZERO_DROP_SEMS)]]
    nz = len(ez.drop_duplicates(subset=["semester", "class", "user", "assessment", "exercise", "kind",
                                        "ts", "exec_time", "n_testcases", "grade"]))
    say(f"  after codebench_semantics' block de-duplication (key, kind, ts, exec_time, n_tc, grade): "
        f"{nz:,} (the count quoted in research_plan.md 2.2); grade 0 on {(ez['grade'] == 0).mean():.3f}")
    say("  of them.  All of them are dropped from the simulated traces.")
    tsr = ev["ts"].values.astype("datetime64[us]").astype("int64")
    u = D["u"]
    ids = ev[JITTER_ID]
    say(f"\nclock jitter: header ts with a sub-second part {int((tsr % 1_000_000 != 0).sum()):,} of {len(ev):,}; "
        f"record ids {JITTER_ID} duplicated {int(ids.duplicated().sum())} times")
    assert not ids.duplicated().any(), "jitter ids are not unique"
    say(f"  u = keyed hash (key '{JITTER_KEY}') of the id: min {u.min():.2e}, max {1 - u.max():.2e} below 1, "
        f"mean {u.mean():.5f}, per-decile counts {np.histogram(u, 10, (0, 1))[0].tolist()}")
    rng = np.random.default_rng(SEED)
    pick = np.sort(rng.choice(len(ev), 100_000, replace=False))
    sh = ev.iloc[pick].sample(frac=1.0, random_state=SEED)
    same = np.array_equal(jitter_u(sh), u[sh.index.values])
    say(f"  recomputed on 100,000 rows in shuffled order: identical {same} (u depends on the id only)")
    assert same
    say("  co-ending groups and repeated blocks below use the raw integer ts.")
    g = D["coend"]
    ok = D["simok"]
    Cs = D["C"][s]
    rows = []
    for sem in DEV + ["ALL"]:
        m = np.ones(len(s), bool) if sem == "ALL" else sem_s == sem
        mo = m & ok
        ing = mo & (g >= 0)
        big = mo & (Cs >= 1)
        wc = np.minimum(Cs, L_CAP)
        sz = np.bincount(g[ing]) if ing.any() else np.zeros(1, int)
        rows.append((sem, int(m.sum()), int((m & ~ok).sum()), int(mo.sum()), int(len(np.unique(g[ing]))),
                     int(ing.sum()), round(ing.sum() / max(mo.sum(), 1), 4),
                     round(wc[ing].sum() / max(wc[mo].sum(), 1e-9), 4),
                     round((big & ing).sum() / max(big.sum(), 1), 4), int(sz.max()),
                     round(float(np.median(Cs[ing])), 3) if ing.any() else np.nan,
                     round(float(np.median(Cs[mo & (g < 0)])), 3)))
    cg = pd.DataFrame(rows, columns=["semester", "n_sub", "zero_dropped", "n_sim", "coend_groups",
                                     "blocks_in_groups", "share_blocks", "share_Ccap_work",
                                     "share_of_C>=1s_blocks", "max_group", "median_C_grouped",
                                     "median_C_solo"])
    say("\nco-ending groups (same user, same semester, same header second, >= 2 SUBMITION blocks,")
    say("over the rows that may enter a simulated trace):")
    say(cg.to_string(index=False))
    cg.to_csv(os.path.join(cache, "coend_groups.csv"), index=False)
    dp = pd.Series(sem_s[D["dup"][s]]).value_counts().reindex(DEV).fillna(0).astype(int)
    say(f"repeated submissions (same user/class/assessment/exercise/second, cost, grade, error, "
        f"test-case count and all {len(FEAT_CODE)} static code features; later members): "
        f"{int(dp.sum()):,} of {len(s):,}; per semester: " + ", ".join(f"{k_} {v_}" for k_, v_ in dp.items()))
    say("  kept on the load side by default; dropped in the --dedup sensitivity.  These are the")
    say("  closest the parquet columns get to byte-identical blocks: outputs and code text are not kept.")
    say("TEST events: existence and time from ts under both readings; outcome (error flag) from "
        "ts + 60 s + delta, sensitivity ts + 600 s (config ires0_t600).")
    for cfg in (PRIMARY, "isub0"):
        arr, av = times(D, cfg)
        rows = []
        for sem in DEV:
            m = D["sem"] == sem
            ms = m[s]
            rows.append((sem, stamp(arr[m].min()), stamp(arr[m].max()), stamp(av[s][ms].max()),
                         int(ms.sum()), int((~D["sub"] & m).sum())))
        say(f"semester calendar ({cfg}): first arrival, last arrival, last assumed result "
            f"availability of a submission")
        say(pd.DataFrame(rows, columns=["semester", "first_arrival", "last_arrival",
                                        "last_sub_available", "n_sub", "n_test"]).to_string(index=False))
    for cfg in CONFIGS:
        arr, av = times(D, cfg)
        trm = np.isin(D["sem"][s], TRAIN_CORE + REMOTE)
        te_first = arr[np.isin(D["sem"], TEST)].min()
        say(f"  P1 overlap check {cfg:8s}: latest train availability {stamp(av[s][trm].max())} "
            f"< first test event {stamp(te_first)}: {bool(av[s][trm].max() < te_first)}")


def stage_features(ev, D, cfgs, cache):
    head("F. AVAILABILITY-CORRECT FEATURE SWEEPS")
    for cfg in cfgs:
        arr, avail = times(D, cfg)
        t = time.time()
        H, R, RP, AX = sweep(D, arr, avail)
        F = pd.DataFrame(np.hstack([H, R, RP]), columns=HIST_COLS + REL_COLS + PERM_COLS)
        F["ex_nres"], F["u_nres"] = AX[:, 0], AX[:, 1]
        F.to_parquet(feat_path(cache, cfg), index=False)
        s = D["sidx"]
        say(f"  {el()} {cfg:8s} sweep {time.time()-t:4.0f} s; zero-lag submissions "
            f"{int((avail[s] == arr[s]).sum()):,}; previous run on the same exercise known on "
            f"{(H[:, 16] > 0).mean():.4f} of submissions, its result available on "
            f"{np.isfinite(H[:, 17]).mean():.4f}")


# --------------------------------------------------------------------------- #
# leak test
# --------------------------------------------------------------------------- #
def _groups(codes, idx):
    c = codes[idx]
    o = np.argsort(c, kind="stable")
    c, ii = c[o], idx[o]
    b = np.flatnonzero(np.r_[True, c[1:] != c[:-1]])
    e = np.r_[b[1:], len(c)]
    return {int(c[s]): ii[s:en] for s, en in zip(b, e)}


def avail_order(D, arr, avail):
    """Rank of every submission in availability order, and the user-slowness tercile
    its user had right after its own result became available (vectorised)."""
    s = D["sidx"]
    ty = np.where(avail[s] == arr[s], 3, 0)
    o = s[np.lexsort((s, ty, avail[s]))]
    rank = np.full(len(arr), -1, np.int64)
    rank[o] = np.arange(len(o))
    df = pd.DataFrame({"u": D["us"][o], "x": D["lg"][o]})
    m = df.groupby("u", sort=False)["x"].cumsum().values / \
        (df.groupby("u", sort=False).cumcount().values + 1)
    lo, hi = D["cuts"]
    tag = np.full(len(arr), -1, np.int64)
    tag[o] = np.where(m < lo, 0, np.where(m < hi, 1, 2))
    return rank, tag


def scratch_rows(D, arr, avail, evi, G, rank, tag):
    """Every feature of the sampled submissions, recomputed directly from the record
    set after deleting what the availability rule does not let through."""
    lg, hv, err, ntc = D["lg"], D["hv"], D["errf"], D["ntc"]
    ex, asm, cls = D["ex"], D["asm"], D["cls"]
    lo, hi = D["cuts"]
    E0 = np.empty(0, np.int64)
    out = np.full((len(evi), len(FEAT_COLS)), np.nan)

    def q(R):
        s = np.sort(lg[R[np.argsort(rank[R], kind="stable")][-120:]])
        L = len(s) - 1
        return s[min(L, int(.5 * L + .5))], s[min(L, int(.9 * L + .5))], s[-1]

    for r, i in enumerate(evi):
        t = arr[i]
        e, u = int(ex[i]), int(D["us"][i])

        def known(g):
            return g[arr[g] < t]

        def vis(g):
            return g[(avail[g] <= t) & (arr[g] < t)]

        o = out[r]
        ge, gu = G["ex"].get(e, E0), G["us"].get(u, E0)
        o[0] = len(known(ge))
        R = vis(ge)
        if len(R):
            o[1], o[2] = lg[R].mean(), lg[R].std()
            o[3], o[4], o[5] = q(R)
            o[6], o[7], o[8] = err[R].mean(), hv[R].mean(), ntc[R].mean()
        o[32] = len(R)
        o[9] = len(known(gu))
        R = vis(gu)
        if len(R):
            m = lg[R].mean()
            o[10], o[11] = m, lg[R].std()
            o[12], o[13], _ = q(R)
            o[14], o[15] = err[R].mean(), hv[R].mean()
            terc = 0 if m < lo else (1 if m < hi else 2)
        else:
            terc = 1
        o[33] = len(R)
        gue = gu[ex[gu] == e]
        K = known(gue)
        o[16] = len(K)
        if len(K):
            o[19] = np.log1p(max(t - arr[K].max(), 0.0))
        R = vis(gue)
        if len(R):
            last = R[np.lexsort((R, arr[R]))[-1]]
            o[17], o[18] = lg[last], err[last]
        ga = G["us_all"].get(u, E0)
        K = known(ga)
        if len(K):
            o[21] = np.log1p(max(t - arr[K].max(), 0.0))
        R = vis(ga)
        if len(R):
            o[20] = err[R[np.lexsort((R, arr[R]))[-1]]]
        for base, ek, ak in ((22, e, int(asm[i])), (27, int(D["pex"][i]), int(D["pas"][i]))):
            R = vis(G["ex"].get(ek, E0))
            Tt = R[tag[R] == terc]
            if len(Tt):
                o[base], o[base + 1] = lg[Tt].mean(), hv[Tt].mean()
            A = vis(G["asm"].get(ak, E0))
            if len(A):
                rest = A[ex[A] != ek]
                if len(rest):
                    o[base + 2], o[base + 3] = lg[rest].mean(), hv[rest].mean()
            Cc = R[cls[R] == cls[i]]
            if len(Cc):
                o[base + 4] = lg[Cc].mean()
    return out


def match(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    return (np.isnan(a) & np.isnan(b)) | (np.abs(a - b) <= 1e-5 + 1e-5 * np.abs(b))


def two_event_frame(c1, gap, reading, first_test=False, err1=False):
    """Job 1 ARRIVES at t0, job 2 (0.2 s) at t0 + gap (+0.8 s under I-res, whole-second
    ts), same user and exercise.  The header ts is placed so that the chosen reading
    gives exactly these arrivals: I-sub ts = arrival, I-res ts = arrival + C.  With
    first_test, job 1 is a TEST block (no cost) whose error flag is err1."""
    t0 = pd.Timestamp("2023-04-03 10:00:00")
    c1_ts = 0.0 if (reading == "sub" or first_test) else c1
    t2 = gap if reading == "sub" else gap + 1
    df = pd.DataFrame({
        "semester": ["2022-2"] * 2, "class": ["c"] * 2, "user": ["u"] * 2,
        "assessment": ["a"] * 2, "exercise": ["e"] * 2,
        "ts": pd.to_datetime([t0 + pd.Timedelta(seconds=c1_ts),
                              t0 + pd.Timedelta(seconds=t2)]).astype("datetime64[us]"),
        "kind": pd.Categorical(["test" if first_test else "submit", "submit"],
                               categories=["submit", "test"]),
        "exec_time": np.array([np.nan if first_test else c1, 0.2], np.float32),
        "has_error": [bool(err1), False], "n_testcases": np.array([3, 3], np.int32),
        "job": [1, 2]})
    return df.sort_values("ts", kind="mergesort").reset_index(drop=True)   # v1 reads in ts order


def _job2_vectors(df, cfg, fixed):
    """v2 sweep and v1 build_history features of job 2 (32 history + relational)."""
    D = prep(df, fixed)
    arr, av = times(D, cfg)
    H, R, RP, _ = sweep(D, arr, av)
    j2 = int(np.flatnonzero(df["job"].values == 2)[0])
    r2 = int(D["rowof"][j2])
    hv1, rv1 = v1.build_history(df, fixed[0], fixed[1], None)
    return np.r_[H[r2], R[r2], RP[r2]], np.r_[hv1[j2], rv1[j2]]


def _perturb_table(cases, variants_of, fixed, what):
    rows = []
    for label, cfg, must, mk in cases:
        vecs, v1vecs = zip(*(_job2_vectors(mk(v), cfg, fixed) for v in variants_of))
        same = all(match(vecs[0], v).all() for v in vecs[1:])
        same_v1 = all(match(v1vecs[0], v).all() for v in v1vecs[1:])
        ok = same if must == "unchanged" else not same
        rows.append((label, cfg, must, "unchanged" if same else "CHANGES", "PASS" if ok else "FAIL",
                     "unchanged" if same_v1 else "CHANGES"))
    say(pd.DataFrame(rows, columns=["case", "config", "required", f"v2 job-2 features ({what})", "v2",
                                    "v1 job-2 features"]).to_string(index=False))
    assert all(r[4] == "PASS" for r in rows), f"perturbation test failed: {what}"
    return rows


def two_event_test(D_real):
    """Job 1 arrives at t=0, job 2 at t=gap, same user and exercise.  Job 1's cost is
    changed between 30 and 60 s with its ARRIVAL fixed; job 2's features must not move
    when job 1's result is not yet available at job 2's arrival."""
    fixed = (D_real["heavy_thr"], D_real["cuts"])
    say("\ntwo-event perturbation test (job 1 arrives at t=0, job 2 at t=gap, same user/exercise;")
    say("job 1 cost C1 in {30, 45, 60} s with its arrival fixed; job 2's 32 history+relational")
    say("features compared across C1; v1 fed the same rows in header-time order; both records")
    say("carry their clock jitter u in [0,1), identical across C1, which moves no case across the")
    say("availability boundary):")
    mk = lambda rd, gap: (lambda c1: two_event_frame(c1, gap, rd))
    cases = [("I-sub d0, gap 1 s", "isub0", "unchanged", mk("sub", 1)),
             ("I-sub d60, gap 1 s", "isub60", "unchanged", mk("sub", 1)),
             ("I-sub d600, gap 1 s", "isub600", "unchanged", mk("sub", 1)),
             ("I-sub d3600, gap 1 s", "isub3600", "unchanged", mk("sub", 1)),
             ("I-sub d0, gap 100 s (positive control)", "isub0", "changes", mk("sub", 100)),
             ("I-res d0, gap 1.8 s (job 1 still running)", "ires0", "unchanged", mk("res", 1)),
             ("I-res d0, gap 100.8 s (positive control)", "ires0", "changes", mk("res", 100)),
             ("I-res d600, gap 100.8 s", "ires600", "unchanged", mk("res", 100)),
             ("I-res d600, gap 700.8 s (positive control)", "ires600", "changes", mk("res", 700))]
    rows = _perturb_table(cases, (30.0, 45.0, 60.0), fixed, "C1")
    v1_fail = rows[0][5] == "CHANGES"
    say(f"=> v2 passes all {len(rows)} cases; the v1 construction {'FAILS' if v1_fail else 'passes'} "
        f"the I-sub gap-1 s case (job 2 reads the cost of a run that is still executing).")


def test_lag_test(D_real):
    """A TEST block at t=0 whose error flag is flipped, then a submission of the same user
    at t=gap: its previous-event error feature may move only once the TEST outcome is
    available (ts + 60 s + delta, or ts + 600 s + delta in ires0_t600)."""
    fixed = (D_real["heavy_thr"], D_real["cuts"])
    say("\nTEST-outcome lag test (TEST block at t=0 with error flag 0 or 1, then a submission of")
    say("the same user at t=gap; only prev_ev_err can read the TEST outcome):")
    mk = lambda rd, gap: (lambda e1: two_event_frame(0.0, gap, rd, first_test=True, err1=e1))
    cases = [("I-res d0 lag 60, gap 30.8 s", "ires0", "unchanged", mk("res", 30)),
             ("I-res d0 lag 60, gap 100.8 s (positive control)", "ires0", "changes", mk("res", 100)),
             ("I-res d0 lag 600, gap 100.8 s", "ires0_t600", "unchanged", mk("res", 100)),
             ("I-res d0 lag 600, gap 700.8 s (positive control)", "ires0_t600", "changes", mk("res", 700)),
             ("I-res d600 lag 60, gap 100.8 s", "ires600", "unchanged", mk("res", 100)),
             ("I-res d600 lag 60, gap 700.8 s (positive control)", "ires600", "changes", mk("res", 700)),
             ("I-sub d0 lag 60, gap 30 s", "isub0", "unchanged", mk("sub", 30))]
    rows = _perturb_table(cases, (False, True), fixed, "TEST error")
    say(f"=> v2 passes all {len(rows)} cases; v1 on the gap-30 s case: {rows[0][5]} "
        f"(v1 reads a TEST outcome the moment the TEST row exists).")


ALT_JITTER_KEYS = ("cbjitter00000001", "cbjitter00000002", "cbjitter00000003")


def frac_channel(D, cache, ev, cfgs=("ires0", "clock0")):
    """The fractional-arrival channel.  On test 2022-2 submissions whose latest earlier
    record of the same user (strictly earlier arrival, the record prev_ev_log_sec reads) is
    a TEST less than 30 s before, score heavy by 1 - frac(gap), i.e. by frac(C) when the
    clock is the whole-second ts (arrival = ts - C, TEST at ts).  Also ires0 under three
    other jitter keys (the spread of the statistic across jitter draws)."""
    s = D["sidx"]
    te = np.flatnonzero(np.isin(D["sem"][s], TEST))
    Ccap = np.minimum(D["C"][s][te], L_CAP)
    hv = Ccap > D["heavy_thr"]
    rows = []
    runs = [(c, c, None) for c in cfgs] + [(f"ires0 key {k}", "ires0", k) for k in ALT_JITTER_KEYS]
    for label, cfg, key in runs:
        arr, _ = times(D if key is None else dict(D, u=jitter_u(ev, key)), cfg)
        R = pd.DataFrame({"a": arr, "u": D["us"], "ap": arr, "tsp": D["ts"], "test": ~D["sub"]}).sort_values(
            "a", kind="mergesort")
        Q = pd.DataFrame({"a": arr[s][te], "u": D["us"][s][te], "r": np.arange(len(te)),
                          "tsq": D["ts"][s][te]}).sort_values("a", kind="mergesort")
        m = pd.merge_asof(Q, R, on="a", by="u", allow_exact_matches=False, direction="backward")
        m = m.sort_values("r")
        gap = (m["a"] - m["ap"]).values
        sel = m["test"].fillna(False).values.astype(bool) & (gap < 30)
        fr = np.mod(gap[sel], 1.0)
        light = Ccap[sel] < 0.45
        far = (m["tsq"].values - m["tsp"].values >= 2)[sel]      # header seconds >= 2 s apart
        rows.append(dict(config=label, test_rows=len(te), rows_prev_TEST_lt30s=int(sel.sum()),
                         share=round(sel.mean(), 4), heavy_share=round(hv[sel].mean(), 4),
                         auroc_frac=round(roc_auc_score(hv[sel], 1.0 - fr), 4),
                         light_frac_lt_half=round(float(np.mean(fr[light] < 0.5)), 4),
                         rows_ts_gap_ge2=int(far.sum()),
                         light_frac_lt_half_ge2=round(float(np.mean(fr[light & far] < 0.5)), 4),
                         auroc_frac_ge2=round(roc_auc_score(hv[sel][far], 1.0 - fr[far]), 4)))
    t = pd.DataFrame(rows)
    say("\nfractional-arrival channel (test 2022-2 submissions whose previous record of the same user is a")
    say("TEST < 30 s earlier; auroc_frac = heavy AUROC of 1 - frac(gap); light_frac_lt_half = share of runs")
    say("with C_cap < 0.45 s whose gap has fraction < 0.5; 0.5 / ~0.5 = no channel):")
    say(t.to_string(index=False))
    say("(*_ge2: pairs whose header seconds are >= 2 s apart.  The three extra ires0 rows use other jitter keys")
    say(" and show the spread of the statistic across jitter draws; which record is 'previous' depends on the")
    say(" jitter of neighbouring records, so the selected rows differ slightly between keys.)")
    t.to_csv(os.path.join(cache, "frac_channel.csv"), index=False)


def stage_leak(ev, D, cache):
    head(f"L. LEAK TEST: {N_LEAK:,} random DEV submissions recomputed from scratch, every config")
    say("For each sampled submission i, every history and relational feature (22 history,")
    say("5 relational, 5 permuted-relational, plus the two available-result counts) is")
    say("recomputed directly from the record set after deleting all records that arrive")
    say("at or after arrival[i] and all results (incl. TEST outcomes) with done + delta >")
    say("arrival[i]; tolerance 1e-5 absolute + 1e-5 relative (float32 storage, different")
    say("summation order).  Sample: uniform over all DEV submissions 2018-1..2022-2, seed 3.")
    sidx = D["sidx"]
    rng = np.random.default_rng(SEED)
    samp = np.sort(rng.choice(len(sidx), min(N_LEAK, len(sidx)), replace=False))
    evi = sidx[samp]
    say("sample per semester: " + ", ".join(
        f"{k_} {v_}" for k_, v_ in pd.Series(D["sem"][evi]).value_counts().reindex(DEV).fillna(0)
        .astype(int).items()))
    G = {"ex": _groups(D["ex"], sidx), "us": _groups(D["us"], sidx),
         "us_all": _groups(D["us"], np.arange(len(D["sub"]))), "asm": _groups(D["asm"], sidx)}
    scratch, sweepv = {}, {}
    rows = []
    for cfg in CONFIGS:
        arr, avail = times(D, cfg)
        rank, tag = avail_order(D, arr, avail)
        t = time.time()
        Sx = scratch_rows(D, arr, avail, evi, G, rank, tag)
        Fv = pd.read_parquet(feat_path(cache, cfg))[FEAT_COLS].values[samp]
        ok = match(Fv, Sx)
        bad_rows = int((~ok.all(1)).sum())
        fin = np.isfinite(Fv) & np.isfinite(Sx)
        mad = float(np.abs(Fv - Sx)[fin].max()) if fin.any() else 0.0
        rows.append((cfg, len(evi), bad_rows, int((~ok).sum()), mad, round(time.time() - t, 1)))
        scratch[cfg], sweepv[cfg] = Sx, Fv
        if bad_rows:
            badc = pd.Series((~ok).sum(0), index=FEAT_COLS)
            say(f"  {cfg}: mismatching features: {badc[badc > 0].to_dict()}")
    lt = pd.DataFrame(rows, columns=["config", "rows", "rows_failing", "cells_failing", "max_abs_diff", "sec"])
    lt.to_csv(os.path.join(cache, "leak.csv"), index=False)
    say(lt.to_string(index=False))
    for r in rows:
        assert r[2] == 0, f"availability sweep disagrees with the from-scratch recomputation: {r}"
    say("=> the sweep passes for every configuration.")

    say("\npower checks (the same comparison is able to fail):")
    for a_cfg, b_cfg in (("ires0", "ires600"), ("ires600", "ires0"), ("ires0", "ires0_t600"),
                         ("ires0", "isub0"), ("isub0", "isub600"), ("isub600", "isub0"),
                         ("ires0", "clock0"), ("clock0", "ires0")):
        ok = match(sweepv[a_cfg], scratch[b_cfg])
        say(f"  sweep({a_cfg}) vs scratch({b_cfg}): {int((~ok.all(1)).sum()):,} of "
            f"{len(evi):,} rows fail")
    frac_channel(D, cache, ev)

    say("\nv1 construction (rows j < i), rebuilt with v1.build_history unchanged:")
    t = time.time()
    hv1, rv1 = v1.build_history(ev, D["heavy_thr"], D["cuts"], None)
    _, rpv1 = v1.build_history(ev, D["heavy_thr"], D["cuts"], D["perm_str"])
    V = np.hstack([hv1[sidx], rv1[sidx], rpv1[sidx]])
    Fv1 = pd.DataFrame(V, columns=HIST_COLS + REL_COLS + PERM_COLS)
    Fv1["ex_nres"], Fv1["u_nres"] = V[:, 0].astype(np.int64), V[:, 9].astype(np.int64)
    Fv1.to_parquet(feat_path(cache, "v1"), index=False)
    say(f"  v1 build_history x2: {time.time()-t:.0f} s")
    n32 = len(HIST_COLS) + len(REL_COLS) + len(PERM_COLS)
    nh, nr = len(HIST_COLS), len(REL_COLS)
    say("  (v1 reads a TEST error as soon as the TEST row exists and every earlier row's cost")
    say("   at once; the from-scratch rule of each config is the reference)")
    say("   result_features = the 27 features that read a past cost / error / heavy flag (all but")
    say("   the counts and the two time-since features, which only move with the arrival clock)")
    arr_only = [HIST_COLS.index(c) for c in ("ex_n", "u_n", "ue_n", "ue_log_sec_since", "prev_ev_log_sec")]
    res_cols = np.array([i for i in range(n32) if i not in arr_only])
    vrows = []
    for cfg in CONFIGS:
        ok = match(V[samp], scratch[cfg][:, :n32])
        badc = pd.Series((~ok).sum(0), index=FEAT_COLS[:n32])
        vrows.append((cfg, len(evi), int((~ok.all(1)).sum()), round(float((~ok.all(1)).mean()), 4),
                      int((~ok[:, res_cols].all(1)).sum()), round(float((~ok[:, res_cols].all(1)).mean()), 4),
                      int((~ok[:, :nh].all(1)).sum()), int((~ok[:, nh:nh + nr].all(1)).sum()),
                      int((~ok[:, nh + nr:].all(1)).sum()),
                      ", ".join(f"{k}={v}" for k, v in badc.sort_values(ascending=False).head(5).items()
                                if v > 0)))
    vt = pd.DataFrame(vrows, columns=["reference_rule", "rows", "v1_rows_failing", "share",
                                      "v1_fail_result_features", "share_result", "on_history",
                                      "on_relational", "on_perm_relational", "top failing features (rows)"])
    say(vt.to_string(index=False))
    vt.to_csv(os.path.join(cache, "leak_v1.csv"), index=False)
    say("\nwhy v1 fails, on the same sample:")
    ts, s = D["ts"], D["sidx"]
    dup = pd.DataFrame({"u": D["us"][s], "e": D["ex"][s], "t": ts[s]}).duplicated(keep=False).values
    say(f"  submissions sharing (user, exercise, second) with another submission: "
        f"{dup[samp].mean():.4f} of the sample, {dup.mean():.4f} of all DEV submissions")
    for cfg in (PRIMARY, "isub0"):
        dsame = ~match(V[samp][:, 17], scratch[cfg][:, 17])
        say(f"  {cfg}: ue_last_log differs on {int(dsame.sum())} sampled rows; of these "
            f"{dup[samp][dsame].mean() if dsame.any() else float('nan'):.3f} share their second "
            f"with another submission")
    two_event_test(D)
    test_lag_test(D)


# --------------------------------------------------------------------------- #
# P1
# --------------------------------------------------------------------------- #
def lgb_fit(params, X, y, seed):
    """LightGBM's native API with v1's sklearn-style parameters (the sklearn wrapper needs
    scikit-learn, which is not in this environment; the wrapper hands the same parameters,
    all of them LightGBM aliases, to lgb.train)."""
    p = dict(params, random_state=seed)
    n = p.pop("n_estimators")
    return lgb.train(p, lgb.Dataset(X, label=y), num_boost_round=n)


def fit_predict(Xtr, ytr, htr, Xte, cols, seed, clf=True):
    ci = [COLI[c] for c in cols]
    A, B = Xtr[:, ci], Xte[:, ci]
    yp = lgb_fit(v1.LGB_REG, A, ytr, seed).predict(B)
    hp = None
    if clf:
        hp = lgb_fit(v1.LGB_CLF, A, htr, seed).predict(B)    # binary objective: P(heavy)
    return yp, hp


def stage_p1(ev, D, S, cfgs, cache, vnames=None):
    """Cross-semester predictability check (retrospective; never simulation input).
    Written per (config, training variant) so that a stage can be split."""
    sidx = D["sidx"]
    sem = D["sem"][sidx]
    Ccap = np.minimum(D["C"][sidx], L_CAP)
    y, h = np.log1p(Ccap), (Ccap > D["heavy_thr"]).astype(int)
    m_te = np.isin(sem, TEST)
    for cfg in cfgs:
        head(f"P1 [{cfg}]  test 2022-2, seeds {SEEDS}")
        F = pd.read_parquet(feat_path(cache, cfg))
        arr, _ = times(D, cfg)
        X = build_X(S, F, arr[sidx])
        # 'nocoend': test rows outside every co-ending group (their C is not inflated by a
        # concurrent run of the same student); the 2022-2 C == 0 blocks stay in it
        cold = {"cold_ex": F["ex_nres"].values[m_te] < 5, "cold_user": F["u_nres"].values[m_te] < 5,
                "nocoend": D["coend"][m_te] < 0}
        say(f"cold-start rows in test: exercise <5 available results {int(cold['cold_ex'].sum())}, "
            f"user <5 {int(cold['cold_user'].sum())}; outside co-ending groups "
            f"{int(cold['nocoend'].sum())} of {int(m_te.sum())}")
        yte, hte = y[m_te], h[m_te]
        for vname, trsem in variants():
            if vnames and vname not in vnames:
                continue
            preds, rows = {}, []
            m_tr = np.isin(sem, trsem)
            Xtr, Xte = X[m_tr], X[m_te]
            for mod in MODELS:
                for seed in SEEDS:
                    if mod == "M0":
                        yp = np.full(m_te.sum(), y[m_tr].mean())
                        hp = np.full(m_te.sum(), h[m_tr].mean())
                    else:
                        yp, hp = fit_predict(Xtr, y[m_tr], h[m_tr], Xte, GROUPS[mod], seed)
                    preds[f"{vname}|{mod}|{seed}|y"] = yp
                    preds[f"{vname}|{mod}|{seed}|h"] = hp
                    r = dict(config=cfg, train=vname, model=mod, seed=seed, n=int(m_te.sum()))
                    r.update(v1.metrics(yte, hte, yp, hp))
                    for tag, msk in cold.items():
                        r[tag + "_n"] = int(msk.sum())
                        if msk.sum() > 30:
                            rr = v1.metrics(yte[msk], hte[msk], yp[msk], hp[msk])
                            for k_, v_ in rr.items():
                                r[f"{tag}_{k_}"] = v_
                    rows.append(r)
                say(f"  {el()} {vname:6s} {mod}: auroc {np.mean([q['auroc'] for q in rows[-3:]]):.4f} "
                    f"(outside co-ending groups {np.mean([q['nocoend_auroc'] for q in rows[-3:]]):.4f}) "
                    f"rmse {np.mean([q['rmse'] for q in rows[-3:]]):.4f}")
            pd.DataFrame(preds).to_parquet(os.path.join(cache, f"p1pred_{cfg}_{vname}.parquet"), index=False)
            pd.DataFrame(rows).to_csv(os.path.join(cache, f"p1_{cfg}_{vname}.csv"), index=False)
        dump(cache, f"p1_{cfg}_" + "_".join(vnames or [v for v, _ in variants()]))


# --------------------------------------------------------------------------- #
# bootstrap
# --------------------------------------------------------------------------- #
def auc_prep(score, label):
    o = np.argsort(score, kind="mergesort")
    s = score[o]
    gid = np.cumsum(np.r_[True, s[1:] != s[:-1]]) - 1
    return o, label[o].astype(bool), gid, int(gid[-1]) + 1


def w_auc(P, w):
    o, lab, gid, G = P
    ww = w[o]
    wn = np.bincount(gid, weights=np.where(lab, 0.0, ww), minlength=G)
    wp = np.bincount(gid, weights=np.where(lab, ww, 0.0), minlength=G)
    below = np.cumsum(wn) - wn
    return float((wp * (below + 0.5 * wn)).sum() / (wp.sum() * wn.sum()))


def stage_boot(ev, D, S, cfgs, cache):
    """User-block bootstrap on test 2022-2: a CI for each model's heavy-vs-not AUROC (all
    test rows, and rows outside co-ending groups) and paired deltas.  Per config, so the
    stage can be split; writes boot_<cfg>.csv (pairs) and bootauc_<cfg>.csv."""
    head(f"P1b. USER-BLOCK BOOTSTRAP, {N_BOOT:,} resamples, test 2022-2, configs {cfgs}")
    say("each resample draws test users with replacement; a statistic is the mean over the")
    say("3 seeds; CI = 2.5/97.5% of the resamples.  AUROC scores the LightGBM classifier's")
    say("heavy probability against the TRUE heavy label (C_cap > train p95).  'nocoend' drops")
    say("test rows inside co-ending groups (their C is shared with a concurrent run).  A pair's")
    say("delta = first - second model; negative dRMSE = first better.")
    sidx = D["sidx"]
    m_te = np.isin(D["sem"][sidx], TEST)
    Ccap = np.minimum(D["C"][sidx], L_CAP)[m_te]
    y, h = np.log1p(Ccap), (Ccap > D["heavy_thr"]).astype(int)
    nce = D["coend"][m_te] < 0
    uu, uidx = np.unique(S["user"][m_te], return_inverse=True)
    pairs = (("M4", "M1"), ("M4", "M3"), ("M5", "M4"), ("M5", "M6"))
    mods = MODELS[1:]
    one = np.ones(len(y))
    for cfg in cfgs:
        rows, arows = [], []
        for vname, _ in variants():
            pr = pd.read_parquet(os.path.join(cache, f"p1pred_{cfg}_{vname}.parquet"))
            P = {(m, s): (pr[f"{vname}|{m}|{s}|y"].values, auc_prep(pr[f"{vname}|{m}|{s}|h"].values, h),
                          auc_prep(pr[f"{vname}|{m}|{s}|h"].values[nce], h[nce]))
                 for m in mods for s in SEEDS}
            for (m, s), (yp, ap, _) in P.items():   # the weighted AUROC equals the plain one at w = 1
                assert abs(w_auc(ap, one) - roc_auc_score(h, pr[f"{vname}|{m}|{s}|h"].values)) < 1e-9
            rng = np.random.default_rng(SEED)
            st = {p: ([], []) for p in pairs}
            sa = {m: ([], []) for m in mods}
            for _ in range(N_BOOT):
                w = np.bincount(rng.integers(0, len(uu), len(uu)), minlength=len(uu))[uidx].astype(float)
                wn = w[nce]
                sw = w.sum()
                ok_a = 0 < (w * h).sum() < sw
                ok_n = 0 < (wn * h[nce]).sum() < wn.sum()
                rm, au, an = {}, {}, {}
                for (m, s), (yp, ap, apn) in P.items():
                    au[m, s] = w_auc(ap, w) if ok_a else np.nan
                    an[m, s] = w_auc(apn, wn) if ok_n else np.nan
                    if any(m in p for p in pairs):
                        rm[m, s] = np.sqrt((w * (y - yp) ** 2).sum() / sw)
                for m in mods:
                    sa[m][0].append(np.mean([au[m, s] for s in SEEDS]))
                    sa[m][1].append(np.mean([an[m, s] for s in SEEDS]))
                for a, b in pairs:
                    st[a, b][0].append(np.mean([rm[a, s] - rm[b, s] for s in SEEDS]))
                    st[a, b][1].append(np.mean([au[a, s] - au[b, s] for s in SEEDS]))
            for m in mods:
                ba, bn = np.array(sa[m][0]), np.array(sa[m][1])
                ba, bn = ba[np.isfinite(ba)], bn[np.isfinite(bn)]
                arows.append(dict(config=cfg, train=vname, model=m,
                                  auroc=np.mean([w_auc(P[m, s][1], one) for s in SEEDS]),
                                  lo=np.quantile(ba, .025), hi=np.quantile(ba, .975),
                                  auroc_nocoend=np.mean([w_auc(P[m, s][2], one[nce]) for s in SEEDS]),
                                  lo_nocoend=np.quantile(bn, .025), hi_nocoend=np.quantile(bn, .975),
                                  n=len(y), n_nocoend=int(nce.sum()), n_users=len(uu)))
            for a, b in pairs:
                dr, da = np.array(st[a, b][0]), np.array(st[a, b][1])
                da = da[np.isfinite(da)]
                pr_ = np.mean([np.sqrt(((y - P[a, s][0]) ** 2).mean()) -
                               np.sqrt(((y - P[b, s][0]) ** 2).mean()) for s in SEEDS])
                pa_ = np.mean([w_auc(P[a, s][1], one) - w_auc(P[b, s][1], one) for s in SEEDS])
                rows.append(dict(config=cfg, train=vname, pair=f"{a}-{b}", dRMSE=pr_,
                                 rmse_lo=np.quantile(dr, .025), rmse_hi=np.quantile(dr, .975),
                                 dAUROC=pa_, auc_lo=np.quantile(da, .025), auc_hi=np.quantile(da, .975)))
            say(f"  {el()} {cfg} {vname} done")
        pd.DataFrame(rows).to_csv(os.path.join(cache, f"boot_{cfg}.csv"), index=False)
        at = pd.DataFrame(arows)
        at.to_csv(os.path.join(cache, f"bootauc_{cfg}.csv"), index=False)
        say(at.round(4).to_string(index=False))
    dump(cache, "boot_" + "_".join(cfgs))


# --------------------------------------------------------------------------- #
# forward (rolling-origin) predictions for the simulation
# --------------------------------------------------------------------------- #
def cutoffs(ev, D, m):
    """Heavy cut-off (p95 of C_cap) and user-slowness tercile cuts, computed as in prep
    but on the submission rows m (sidx order)."""
    y = np.minimum(ev["exec_time"].values[D["sidx"]][m], L_CAP)          # float32, as v1
    lt = np.log1p(y)
    return float(np.quantile(y, .95)), (float(np.quantile(lt, 1 / 3)), float(np.quantile(lt, 2 / 3)))


def feature_frame(ev, D, cfg, thr, cuts):
    """History and relational features of every submission under cfg, with the heavy flag
    and the user-slowness terciles taken from the given cut-offs.  v1: rows j < i as
    v1.build_history, permuted-relational columns left empty (the forward v1 model is M4)."""
    if cfg == "v1":
        hv1, rv1 = v1.build_history(ev, thr, cuts, None)
        s = D["sidx"]
        V = np.hstack([hv1[s], rv1[s], np.full((len(s), len(PERM_COLS)), np.nan)])
    else:
        D2 = dict(D, heavy_thr=thr, cuts=cuts)
        D2["hv"] = (np.nan_to_num(D["C"]) > thr).astype("float64")
        arr, avail = times(D2, cfg)
        H, R, RP, _ = sweep(D2, arr, avail)
        V = np.hstack([H, R, RP])
    return pd.DataFrame(V, columns=HIST_COLS + REL_COLS + PERM_COLS)


def stage_forward(ev, D, S, cfgs, cache):
    head("P1c. FORWARD (ROLLING-ORIGIN) PREDICTIONS FOR THE SIMULATION")
    say("for each target semester s from 2019-1 on (calendar order of first events): train on")
    say("the submissions of the semesters that start before s, minus every record whose")
    say("assumed availability time (done + delta) is at or after the first event of s;")
    say("LightGBM regression as v1, seed 3.  Replaces v1's out-of-fold predictions.")
    say("The heavy cut-off and user-slowness tercile cuts INSIDE the features (heavy-rate and")
    say("similar-user columns) are the fixed 2018-1..2019-2 values only when all of those rows are")
    say("training rows of the target; otherwise (targets 2019-1, 2019-2) they are refit on the")
    say("target's own training rows and every feature is rebuilt with them (cutoffs column).  The")
    say("heavy LABEL used for evaluation stays the fixed train p95 (research_plan.md 6.1).")
    say("slow_train / slow_target = rows arriving 2019-06-01..2019-09-30 (the platform-wide slow")
    say("period: median C of trivial correct runs 0.73-1.06 s vs 0.15-0.23 s elsewhere).")
    sidx = D["sidx"]
    sem_s = D["sem"][sidx]
    Ccap = np.minimum(D["C"][sidx], L_CAP)
    y = np.log1p(Ccap)
    hh = (Ccap > D["heavy_thr"]).astype(int)
    core = np.isin(sem_s, TRAIN_CORE)
    assert cutoffs(ev, D, core) == (D["heavy_thr"], D["cuts"])
    slow0 = float(pd.Timestamp("2019-06-01").value // 10 ** 9)
    slow1 = float(pd.Timestamp("2019-10-01").value // 10 ** 9)
    for cfg in cfgs:
        mods = FORWARD_MODELS[cfg]
        arr, avail = times(D, "isub0" if cfg == "v1" else cfg)
        first = {s: float(arr[D["sem"] == s].min()) for s in DEV}
        order = sorted(DEV, key=first.get)
        F = pd.read_parquet(feat_path(cache, cfg))
        X = build_X(S, F, arr[sidx])
        a_s = avail[sidx]
        slow = (arr[sidx] >= slow0) & (arr[sidx] < slow1)
        out = {m: np.full(len(sidx), np.nan) for m in mods}
        rows = []
        for s in order[order.index(FORWARD_FROM):]:
            t = time.time()
            prior = [q for q in order if first[q] < first[s]]
            m_prior = np.isin(sem_s, prior)
            m_tr = m_prior & (a_s < first[s])
            m_te = sem_s == s
            if m_tr[core].all():
                Xs, thr, cuts, cfrom = X, D["heavy_thr"], D["cuts"], "2018-1..2019-2"
            else:                          # the fixed cut-offs would include the target
                thr, cuts = cutoffs(ev, D, m_tr)
                Xs, cfrom = build_X(S, feature_frame(ev, D, cfg, thr, cuts), arr[sidx]), "train rows"
            mm = {}
            for m in mods:
                yp, _ = fit_predict(Xs[m_tr], y[m_tr], None, Xs[m_te], GROUPS[m], SEED, clf=False)
                out[m][m_te] = yp
                r = v1.metrics(y[m_te], hh[m_te], yp, yp)
                mm.update({f"{m}_auroc": round(r["auroc"], 4), f"{m}_auprc": round(r["auprc"], 4)})
            r4 = v1.metrics(y[m_te], hh[m_te], out["M4"][m_te], out["M4"][m_te])
            rows.append(dict(target=s, first_event=stamp(first[s]), train_sems=f"{prior[0]}..{prior[-1]}",
                             n_prior=int(m_prior.sum()), dropped_not_yet_available=int(m_prior.sum() - m_tr.sum()),
                             n_train=int(m_tr.sum()), slow_train=int((m_tr & slow).sum()), n_target=int(m_te.sum()),
                             slow_target=int((m_te & slow).sum()),
                             **{"cutoffs (heavy / terciles)": f"{cfrom}: {thr:.4f} / {cuts[0]:.4f} {cuts[1]:.4f}"},
                             M4_rmse=round(r4["rmse"], 4), M4_spearman=round(r4["spearman"], 3), **mm,
                             sec=round(time.time() - t)))
        pd.DataFrame(out).to_parquet(os.path.join(cache, f"forward_{cfg}.parquet"), index=False)
        say(f"\n[{cfg}] ({el()}; models {mods}; AUROC / AUPRC score the regression output as the heavy-job "
            f"score against the fixed heavy label)")
        ft = pd.DataFrame(rows)
        ft.to_csv(os.path.join(cache, f"fwdtab_{cfg}.csv"), index=False)
        say(ft.to_string(index=False))


# --------------------------------------------------------------------------- #
# simulator
# --------------------------------------------------------------------------- #
def simulate(arr, svc, pri, k, mode="fcfs", B=None, acct="completion", return_order=False):
    """Non-preemptive k-server queue, arrivals sorted (rank = index).
    mode fcfs | pri (smallest pri first, ties to the earlier arrival) | guard.

    guard, acct="completion" (the method): over[i] = true service time of jobs with a
    higher rank than i that have COMPLETED by the decision time (all of them completed
    while i waited, since they arrived after i).  Completions with time <= the decision
    time are applied first, then arrivals <= the decision time, then the dispatch; each
    completion adds C[j] in integer microseconds at rank j of a Fenwick tree; over[head]
    is the total completed work minus the tree's prefix sum up to head, compared with B
    in integer microseconds (B = 0 is exactly FCFS).
    guard, acct="start" (kept only to reproduce the audit): over counts the work of
    later-arriving jobs from the moment they START, i.e. it reads the service time of a
    job still running; with k = 1 both accountings coincide."""
    n = len(arr)
    wait = np.empty(n)
    arr_l, svc_l = arr.tolist(), svc.tolist()
    pri_l = pri.tolist() if pri is not None else None
    guard = mode == "guard"
    comp = guard and acct == "completion"
    if guard:
        Bt = int(round(B * 1_000_000))
        if comp:
            svc_us = [int(round(x * 1_000_000)) for x in svc_l]
            tree = [0] * (n + 1)
            tot = 0
            ch = []
        else:
            svc_us_s = [int(round(x * 1_000_000)) for x in svc_l]
            P = [0] + list(accumulate(svc_us_s))[:-1]      # started work of ranks < i
            G = 0
    free = [0.0] * k
    heapq.heapify(free)
    i = qn = 0
    hq, fq = [], deque()
    served = bytearray(n)
    order = [] if return_order else None
    t_prev = -np.inf
    heappop, heappush = heapq.heappop, heapq.heappush
    while i < n or qn > 0:
        w = heappop(free)
        t = w if w > t_prev else t_prev
        if qn == 0 and i < n and arr_l[i] > t:
            t = arr_l[i]
        while i < n and arr_l[i] <= t:
            if mode == "fcfs":
                fq.append(i)
            elif mode == "pri":
                heappush(hq, (pri_l[i], i))
            else:
                fq.append(i)
                heappush(hq, (pri_l[i], i))
            qn += 1
            i += 1
        if qn == 0:
            heappush(free, w)
            continue
        if mode == "fcfs":
            j = fq.popleft()
        elif mode == "pri":
            j = heappop(hq)[1]
        else:
            while served[fq[0]]:
                fq.popleft()
            hd = fq[0]
            if comp:
                while ch and ch[0][0] <= t:
                    c = heappop(ch)[1]
                    x = svc_us[c]
                    tot += x
                    p = c + 1
                    while p <= n:
                        tree[p] += x
                        p += p & -p
                s = 0
                p = hd + 1
                while p:
                    s += tree[p]
                    p &= p - 1
                over = tot - s
            else:
                over = G - P[hd]
            if over >= Bt:
                j = fq.popleft()
            else:
                while served[hq[0][1]]:
                    heappop(hq)
                j = heappop(hq)[1]
            if comp:
                heappush(ch, (t + svc_l[j], j))
            else:
                G += svc_us_s[j]
        served[j] = 1
        qn -= 1
        wait[j] = t - arr_l[j]
        if t < t_prev:
            raise AssertionError("clock ran backwards")
        t_prev = t
        if order is not None:
            order.append(j)
        heappush(free, t + svc_l[j])
    if return_order:
        return wait, np.array(order)
    return wait


def brute_guard(arr, svc, pri, k, B):
    """Reference guard with an explicit over[] per waiting job, completion accounting,
    O(n^2).  Written independently of simulate()."""
    n = len(arr)
    wait = np.empty(n)
    over = np.zeros(n)
    free = [0.0] * k
    heapq.heapify(free)
    running = []
    waiting, i, t_prev = [], 0, -np.inf
    while i < n or waiting:
        w = heapq.heappop(free)
        t = max(w, t_prev)
        if not waiting and i < n and arr[i] > t:
            t = arr[i]
        while i < n and arr[i] <= t:
            waiting.append(i)
            i += 1
        for rc in [x for x in running if x[0] <= t]:
            running.remove(rc)
            for q in waiting:
                if q < rc[1]:
                    over[q] += svc[rc[1]]
        hd = min(waiting)
        j = hd if over[hd] >= B else min(waiting, key=lambda q: (pri[q], q))
        waiting.remove(j)
        wait[j] = t - arr[j]
        t_prev = t
        running.append((t + svc[j], j))
        heapq.heappush(free, t + svc[j])
    return wait


def lindley(arr, svc):
    w = np.empty(len(arr))
    cur = 0.0
    al, sl = arr.tolist(), svc.tolist()
    for i in range(len(al)):
        if i:
            cur = max(0.0, cur + sl[i - 1] - (al[i] - al[i - 1]))
        w[i] = cur
    return w


def fcfs_kw(arr, svc, k):
    """Independent k-server FCFS (Kiefer-Wolfowitz): start_i = max(arr_i, earliest free)."""
    free = [0.0] * k
    w = np.empty(len(arr))
    for i, (a, s) in enumerate(zip(arr.tolist(), svc.tolist())):
        f = heapq.heappop(free)
        st = a if a > f else f
        w[i] = st - a
        heapq.heappush(free, st + s)
    return w


def guard_check_traces():
    """The exact traces of evidence/guard_check/overtake_guard_check.py (same seed, same
    draw order), yielded as (k, B, arr, svc, pred)."""
    rng = np.random.default_rng(20260919)
    for k in (1, 2, 4):
        for B in (0.0, 30.0, 120.0, 600.0):
            for _ in range(60):
                n = 1500
                gaps = rng.exponential(1.0, n) * rng.choice([0.01, 0.2, 3.0], n, p=[.5, .3, .2])
                arr = np.cumsum(gaps)
                svc = np.minimum(np.where(rng.random(n) < .03, rng.uniform(20, 80, n),
                                          rng.exponential(0.3, n)) + 1e-3, L_CAP)
                mode = rng.integers(3)
                pred = svc if mode == 0 else (-svc if mode == 1 else rng.permutation(svc))
                yield k, B, arr, svc, pred


def stage_selftest(cache):
    head("S0. SIMULATOR SELF-TESTS")
    rng = np.random.default_rng(SEED)
    dmax = {}
    for k in (1, 2, 4, 7):
        n = 20000
        a = np.sort(np.round(np.cumsum(rng.exponential(0.4, n)) + 900 * (np.arange(n) // 2000))) + 1.6e9
        s = rng.lognormal(-1.4, 1.8, n)
        s[rng.integers(0, n, 20)] = 900.0
        s[rng.integers(0, n, 50)] = 0.0
        s = np.round(s * 1024) / 1024       # dyadic grid: every sum below is exact in float64
        p = rng.normal(0, 1, n)
        for mode, B in (("fcfs", None), ("pri", None), ("guard", 0.0), ("guard", 30.0), ("guard", 1e18)):
            w, st = simulate(a, s, p, k, mode, B, return_order=True)
            assert np.isfinite(w).all() and (w >= -1e-6).all(), (k, mode, B)
            assert np.all(np.diff((a + w)[st]) >= 0), "start times not monotone"
            if mode in ("fcfs", "pri"):
                assert np.array_equal(w, v1.simulate(a, s, p, k, mode)), "differs from v1.simulate"
        wf = simulate(a, s, p, k, "fcfs")
        assert np.array_equal(simulate(a, s, p, k, "guard", 0.0), wf), "guard B=0 != FCFS"
        assert np.array_equal(simulate(a, s, p, k, "guard", 1e18), simulate(a, s, p, k, "pri")), \
            "guard B=inf != SPJF"
        ref = lindley(a, s) if k == 1 else fcfs_kw(a, s, k)
        dmax[k] = float(np.abs(wf - ref).max())
        assert np.array_equal(wf, ref), (k, dmax[k])
        if k == 1:
            assert np.array_equal(simulate(a, s, p, 1, "guard", 30.0),
                                  simulate(a, s, p, 1, "guard", 30.0, acct="start")), "k=1 accountings differ"
    say("random bursty traces (20,000 jobs, 1.6e9 s epoch, ties, zero and 900 s jobs, times on a")
    say("  1/1024 s grid so that float64 sums are exact), k in")
    say("  {1,2,4,7}, modes fcfs / pri / guard(B=0,30,inf): finite, no negative waits, start times")
    say("  monotone; fcfs and pri identical to v1.simulate; guard(B=0) == FCFS and")
    say("  guard(B=inf) == SPJF job by job.")
    say("FCFS job by job against an independent recursion (k=1 Lindley, k>1 Kiefer-Wolfowitz),")
    say("  asserted bit-identical:")
    say("  max |W_sim - W_ref| = " + ", ".join(f"k={k}: {v:.1e} s" for k, v in dmax.items()))
    say("  (replaces v1's work-conservation assert, whose tolerance was 1e6 s)")
    ndiff = {1: 0, 2: 0, 3: 0}
    for k in (1, 2, 3):
        for B in (0.5, 2.0, 5.0):
            for _ in range(5):
                n = 400
                a = np.sort(rng.integers(0, 300, n) / 2.0)
                s = rng.integers(0, 40, n) / 8.0
                p = rng.normal(0, 1, n)
                wg = simulate(a, s, p, k, "guard", B)
                assert np.array_equal(wg, brute_guard(a, s, p, k, B)), ("guard != brute force", k, B)
                ws = simulate(a, s, p, k, "guard", B, acct="start")
                ndiff[k] += int(not np.array_equal(wg, ws))
    assert ndiff[1] == 0
    say("Fenwick completion-accounting guard == brute-force guard (explicit over[] per waiting")
    say("  job, updated on completion) job by job on 45 tied-arrival traces, k in {1,2,3},")
    say(f"  B in {{0.5,2,5}}.  Start-time accounting gives a different schedule on "
        f"{ndiff[2]}/15 (k=2) and {ndiff[3]}/15 (k=3) of them, 0/15 at k=1.")

    rows = []
    for k, B, a, s, p in guard_check_traces():
        wf = simulate(a, s, p, k, "fcfs")
        rows.append((k, B, float((simulate(a, s, p, k, "guard", B, acct="start") - wf).max()),
                     float((simulate(a, s, p, k, "guard", B) - wf).max())))
    gc = pd.DataFrame(rows, columns=["k", "B", "start", "completion"]).groupby(["k", "B"]).max()
    # guard_check/out_overtake_guard_check.txt (completion accounting, integer microseconds,
    # its own event loop: completions, arrivals, dispatch), rounded there to 3 decimals
    pub = {(1, 0): 0.0, (1, 30): 89.635, (1, 120): 179.998, (1, 600): 659.989, (2, 0): 0.0,
           (2, 30): 100.834, (2, 120): 139.045, (2, 600): 388.075, (4, 0): 0.0, (4, 30): 79.119,
           (4, 120): 107.422, (4, 600): 218.927}
    gc["guard_check_published"] = [pub[(int(k), int(b))] for k, b in gc.index]
    gc["B+60"] = [b + L_CAP for _, b in gc.index]
    say("\nmax_i (W_guard[i] - W_FCFS[i]) on the 720 traces of guard_check/overtake_guard_check.py")
    say("(same seed and draw order), start-time vs completion accounting, and the published")
    say("completion-accounting numbers of that independent implementation:")
    say(gc.round(3).to_string())
    k1 = gc.loc[1]
    assert (k1["completion"] <= k1["B+60"] + 1e-6).all()
    assert (np.abs(gc["completion"] - gc["guard_check_published"]) < 6e-4).all(), \
        "completion guard differs from guard_check"
    say("=> completion accounting reproduces guard_check in all 12 (k, B) cells (to its 3 decimals);")
    say("   k=1: both accountings coincide and stay within B+60.  k>1: no bound is claimed")
    say("   (k=2, B=30 exceeds B+60 = 90).")
    w4 = simulate(np.zeros(4), np.array([1.0, 1.0, 60.0, 60.0]), np.array([100.0, 90.0, 0.0, 1.0]),
                  2, "guard", 30.0)
    w4s = simulate(np.zeros(4), np.array([1.0, 1.0, 60.0, 60.0]), np.array([100.0, 90.0, 0.0, 1.0]),
                   2, "guard", 30.0, acct="start")
    assert w4.tolist() == [60.0, 60.0, 0.0, 0.0], w4
    say(f"audit four-job example (k=2, B=30, svc 1/1/60/60, predictions 100/90/0/1): waits "
        f"{w4.tolist()} (guard_check: [60, 60, 0, 0]); start-time accounting gives {w4s.tolist()}")

    worst = {}
    for B in GUARD_B:
        mx = -np.inf
        for _ in range(30):
            n = 1500
            gaps = rng.exponential(1.0, n) * rng.choice([0.01, 0.2, 3.0], n, p=[.5, .3, .2])
            a = np.cumsum(gaps)
            s = np.minimum(np.where(rng.random(n) < .03, rng.uniform(20, 80, n),
                                    rng.exponential(0.3, n)) + 1e-3, L_CAP)
            for p in (s, -s, rng.permutation(s)):
                mx = max(mx, float((simulate(a, s, p, 1, "guard", B) - simulate(a, s, p, 1, "fcfs")).max()))
        assert mx <= B + L_CAP + 1e-6, (B, mx)
        worst[B] = mx
    say("\nk=1 bound on 30 fresh bursty traces x 3 predictors (true, reversed, random): max excess " +
        ", ".join(f"B={b:g}: {v:.2f} (bound {b + L_CAP:g})" for b, v in worst.items()))
    a = np.r_[0.0, np.full(1000, .1), np.full(100, .2)]
    s = np.r_[60.0, np.full(1000, .2), np.full(100, 60.0)]
    p = np.r_[60.0, np.full(1000, 60.0), np.full(100, 0.0)]
    got = dict(fcfs=simulate(a, s, p, 1, "fcfs").mean(), unguarded=simulate(a, s, p, 1, "pri").mean(),
               B30=simulate(a, s, p, 1, "guard", 30.0).mean(),
               B120=simulate(a, s, p, 1, "guard", 120.0).mean())
    ref = dict(fcfs=438.49, unguarded=5869.92, B30=492.81, B120=547.12)
    say("audit burst (100 x 60 s jobs predicted shortest, k=1), mean wait here / in "
        "guard_check: " + ", ".join(f"{k_} {got[k_]:.2f}/{ref[k_]:.2f}" for k_ in ref))
    assert all(abs(got[k_] - ref[k_]) < 0.01 for k_ in ref)

    say("\nPollaczek-Khinchine on synthetic stationary M/G/1 FCFS (3,000,000 jobs, first 300,000")
    say("discarded as warm-up, 20 batch means for the standard error; target |error| < 2%):")
    rows = []
    for name, draw, rho in (("M/M/1", lambda m: rng.exponential(1.0, m), 0.7),
                            ("M/LN(0,1)/1", lambda m: rng.lognormal(0.0, 1.0, m), 0.5),
                            ("M/LN(0,1)/1", lambda m: rng.lognormal(0.0, 1.0, m), 0.7)):
        n, wu = 3_000_000, 300_000
        s = draw(n)
        ES, ES2 = s.mean(), (s ** 2).mean()
        a = np.cumsum(rng.exponential(ES / rho, n))
        w = simulate(a, s, None, 1, "fcfs")[wu:]
        pk = rho * ES2 / (2 * ES * (1 - rho))
        se = np.std([b.mean() for b in np.array_split(w, 20)], ddof=1) / np.sqrt(20)
        rows.append((name, rho, w.mean(), pk, w.mean() / pk - 1, se / pk))
    pkt = pd.DataFrame(rows, columns=["model", "rho", "sim_EW", "PK_EW", "rel_error", "rel_se"])
    say(pkt.round(4).to_string(index=False))
    assert (pkt.rel_error.abs() < 0.02).all(), "PK check outside 2%"
    say("real traces are not compared with PK (they are not stationary M/G/1).")

    # week-block bootstrap statistics against brute force on the expanded resample
    nd = 0
    for trial in range(6):
        n, nw = int(rng.integers(50, 20000)), int(rng.integers(3, 40))
        x = np.where(rng.random(n) < .4, 0.0, np.round(rng.lognormal(0, 2, n), 3))   # zeros and ties
        wk = rng.integers(0, nw, n)
        M = np.vstack([np.ones((1, nw), np.int64), boot_weights(nw, 60, seed=trial)])
        bq = boot_quantile(x, wk, M, 0.99, nblk=int(rng.integers(5, 300)))
        bm = boot_mean(x, wk, M)
        for b in range(len(M)):
            ex_ = np.repeat(x, M[b, wk])
            assert bq[b] == np.quantile(ex_, 0.99), (trial, b, bq[b], np.quantile(ex_, 0.99))
            assert abs(bm[b] - ex_.mean()) <= 1e-12 * max(1.0, abs(ex_.mean()))
            nd += 1
    say(f"\nweek-block bootstrap: p99 (exact block-scan) and mean of {nd} resamples (6 random samples with")
    say("  zeros and ties, 3-39 weeks, identity resample included) equal np.quantile / np.mean of the")
    say("  explicitly expanded resample (p99 bit-identical, mean within 1e-12 relative).")

    # incremental busiest-hour probe against v1.busy_hour_work on the built overlay
    per_cs = {}
    for c in range(7):
        m = int(rng.integers(200, 3000))
        ts_ = np.sort(1.60e9 + rng.integers(0, 3 * 3600, m) + rng.random(m))
        sv = np.minimum(rng.lognormal(1, 1, m), L_CAP)
        per_cs[f"s|{c}"] = {"ts": ts_, "arr": ts_ - sv, "svc": sv, "idx": np.arange(m), "base": cs_base(ts_.min())}
    pool = sorted(per_cs)
    for key in ("arr", "ts"):
        c_ok, Ws = copies_probe(pool, per_cs, key, (0, 1), cmax=400)
        for r in (0, 1):
            for c in (1, 2, c_ok, c_ok + 3):
                a_, s_, _, _ = overlay(ms_entries(pool, c, r), per_cs, key)
                assert abs(v1.busy_hour_work(a_, s_)[0] - Ws[r][c - 1]) < 1e-6
            assert all(np.diff(Ws[r]) >= 0) and k_ok(level_ks(Ws[r][c_ok - 1]))
            if c_ok > 1:
                assert not all(k_ok(level_ks(Ws[q][c_ok - 2])) for q in (0, 1))
    assert level_ks(3.6 * 3600) == [7, 5, 4] and not k_ok(level_ks(3.59 * 3600))
    say("incremental busiest-hour probe == v1.busy_hour_work of the built overlay (7 synthetic class-")
    say("  semesters, both arrival keys, copies 1, 2, c*, c*+3, reps 0-1); W monotone in copies; c* is the")
    say("  first count with k >= 4 at rho 1.0 and distinct k in both reps; level_ks(3.6 h) = [7, 5, 4].")
    dump(cache, "selftest")


# --------------------------------------------------------------------------- #
# latency
# --------------------------------------------------------------------------- #
def code_vector_times(nmax):
    """Time code_vector() per SUBMITION block of the extracted 2016-2 sample.  The code
    text lives only inside this function and is never stored or printed."""
    out = []
    for root, _, files in os.walk(RAW_SAMPLE):
        if os.path.basename(root) != "executions":
            continue
        for fn in sorted(files):
            if not fn.endswith(".log"):
                continue
            with open(os.path.join(root, fn), "rb") as f:
                raw = f.read()
            for blk in raw.split(v1cf.SEP):
                hh = v1cf.RE_HEAD.search(blk)
                if hh is None or hh.group(1) != b"SUBMITION":
                    continue
                marks = list(v1cf.RE_SECT.finditer(blk, hh.end()))
                code_b = b""
                for q, m in enumerate(marks):
                    if m.group(1) == b"CODE":
                        end = marks[q + 1].start() if q + 1 < len(marks) else len(blk)
                        code_b = blk[m.end() + 1: end].rstrip(b"\n")
                        break
                t0 = perf_counter()
                v1cf.code_vector(code_b.decode("utf-8", "replace"))
                out.append(perf_counter() - t0)
                if len(out) >= nmax:
                    return np.array(out)
    return np.array(out)


def stage_latency(ev, D, S, cache):
    head(f"P2a. PER-JOB PREDICTION LATENCY, streaming loop over {N_LAT:,} submissions ({PRIMARY})")
    sidx = D["sidx"]
    sem = D["sem"][sidx]
    Ccap = np.minimum(D["C"][sidx], L_CAP)
    F = pd.read_parquet(feat_path(cache, PRIMARY))
    arr, avail = times(D, PRIMARY)
    X = build_X(S, F, arr[sidx])
    m_tr = np.isin(sem, TRAIN_CORE + REMOTE)
    ci = [COLI[c] for c in GROUPS["M4"]]
    bst = lgb_fit(v1.LGB_REG, X[m_tr][:, ci], np.log1p(Ccap[m_tr]), SEED)
    test_rows = np.flatnonzero(np.isin(sem, TEST))[:N_LAT]
    probe = bytearray(len(sidx))
    for r in test_rows:
        probe[r] = 1
    code, a_is_exam, a_weight, a_nex = S["code"], S["a_is_exam"], S["a_weight"], S["a_nex"]
    a_end, a_start, is_remote = S["a_end"], S["a_start"], S["is_remote"]
    arr_s = arr[sidx]
    rec = {}

    def cb(row, H, rel, t0):
        t = arr_s[row]
        ctx = np.array([a_is_exam[row], a_weight[row], a_nex[row], (a_end[row] - t) / 3600.0,
                        (t - a_start[row]) / 3600.0, np.floor(np.mod(t, 86400.0) / 3600.0),
                        np.mod(np.floor(t / 86400.0) + 3.0, 7.0), is_remote[row]], np.float32)
        x = np.concatenate([code[row], ctx, np.asarray(H, np.float32)]).reshape(1, -1)
        t1 = perf_counter()
        p = bst.predict(x, num_threads=1)[0]
        t2 = perf_counter()
        rec[row] = (t1 - t0, t2 - t1, p)

    t = time.time()
    sweep(D, arr, avail, probe, cb)
    wall = time.time() - t
    tf = np.array([rec[r][0] for r in test_rows])
    tp = np.array([rec[r][1] for r in test_rows])
    ps = np.array([rec[r][2] for r in test_rows])
    pb = bst.predict(X[test_rows][:, ci], num_threads=1)
    tc = code_vector_times(N_LAT)
    rng = np.random.default_rng(SEED)
    total = tf + tp + rng.choice(tc, len(tf))
    q = lambda v: f"median {np.median(v)*1e3:.3f} ms, p99 {np.quantile(v,.99)*1e3:.3f} ms, max {v.max()*1e3:.2f} ms"
    say(f"history + relational features from the sweep state: {q(tf)}")
    say(f"LightGBM M4 single-row predict (1 thread):          {q(tp)}")
    say(f"static code features, code_vector() on {len(tc):,} 2016-2 blocks: {q(tc)}")
    say(f"total per submission (the three added):             {q(total)}; mean {total.mean()*1e3:.3f} ms")
    say(f"streamed vs batch prediction on the same rows: max |diff| = {np.abs(ps - pb).max():.2e}")
    say(f"whole sweep incl. all state updates: {wall:.0f} s for {len(sidx):,} submissions / "
        f"{len(ev):,} events = {wall/len(sidx)*1e3:.3f} ms per submission amortised")
    say(f"median C_cap in DEV is {np.median(Ccap)*1e3:.0f} ms; median prediction latency is "
        f"{np.median(total)/np.median(Ccap):.4f} of it")
    np.savez(os.path.join(cache, "latency.npz"), total=total, feat=tf, pred=tp, code=tc)
    dump(cache, "latency")


# --------------------------------------------------------------------------- #
# P2
# --------------------------------------------------------------------------- #
def cs_base(ts_min):
    """Whole-week shift putting the Monday 00:00 of the week of ts_min on REF_MON
    (v1.consolidate's rule): weekday and clock of every arrival are kept."""
    mon = 345600 + int((ts_min - 345600) // WEEK) * WEEK
    return REF_MON - mon


def ms_entries(pool, copies, rep):
    """The multi-server overlay of rep: `copies` copies of the pool, copy-major, each
    class-semester copy shifted by its own 0-11 extra whole weeks (seed 300 + rep, drawn in
    the previous round's order, so the overlay with c copies is a prefix of c + 1)."""
    rng = np.random.default_rng(SEED * 100 + rep)
    return [(cs, int(rng.integers(0, 12))) for _ in range(copies) for cs in pool]


def overlay(entries, per_cs, key):
    """Superpose the class-semester copies (cs, j): arrival column `key` + the base shift of
    cs + j weeks.  A job's identity in the overlay is (copy, row): copies never share ids, and
    no feature is computed on the overlay (predictions are attached per original row).
    Returns arrivals sorted (stable), service, row index, copy number."""
    arrs, svcs, idxs, cps = [], [], [], []
    for c, (cs, j) in enumerate(entries):
        g = per_cs[cs]
        arrs.append(g[key] + (g["base"] + j * WEEK))
        svcs.append(g["svc"])
        idxs.append(g["idx"])
        cps.append(np.full(len(g["idx"]), c, np.int32))
    a = np.concatenate(arrs)
    o = np.argsort(a, kind="stable")
    return (a[o].astype("float64"), np.concatenate(svcs)[o], np.concatenate(idxs)[o],
            np.concatenate(cps)[o])


def rebase(a):
    """Remove whole days from the epoch (after the busy-hour count): waits unchanged,
    float64 rounding of start times ~1e-9 s instead of ~2e-7 s."""
    return a - np.floor(a[0] / 86400.0) * 86400.0


def hour_hist(per_cs, key):
    """C_cap work per arrival hour of every class-semester after its base shift, as
    (hour index of the first bin relative to REF_MON, work per hour); the bins are
    floor(t / 3600) as in v1.busy_hour_work (REF_MON is a whole hour)."""
    out = {}
    for cs, g in per_cs.items():
        h = np.floor((g[key] + g["base"] - REF_MON) / 3600.0).astype(np.int64)
        off = int(h.min())
        out[cs] = (off, np.bincount(h - off, weights=g["svc"]))
    return out


def level_ks(W):
    """Integer k per target busy-hour rho: W / (3600 rho) rounded half up, at least 1."""
    return [max(1, int(np.floor(W / (3600.0 * r) + 0.5))) for r in RHOS]


def k_ok(ks):
    return ks[-1] >= K_MIN_RHO1 and all(x > y for x, y in zip(ks, ks[1:]))


def copies_probe(pool, per_cs, key, reps, cmax=300):
    """Busiest-hour C_cap work of the multi-server overlay of each rep as whole pool copies
    are added (the same draws as ms_entries).  Stops 5 copies after the first count at which
    every rep has k >= K_MIN_RHO1 at rho 1.0 and three distinct k.  Returns (count, {rep: [W(1),
    W(2), ...]}); the work is monotone in the count, so every larger count also qualifies."""
    hh = hour_hist(per_cs, key)
    lo = min(off for off, _ in hh.values())
    span = max(off + len(w) for off, w in hh.values()) - lo + 12 * 168 + 1
    tot = {r: np.zeros(span) for r in reps}
    rng = {r: np.random.default_rng(SEED * 100 + r) for r in reps}
    Ws = {r: [] for r in reps}
    c_ok = None
    for c in range(1, cmax + 1):
        for r in reps:
            t = tot[r]
            for cs in pool:
                j = int(rng[r].integers(0, 12))
                off, w = hh[cs]
                st = off - lo + j * 168
                t[st:st + len(w)] += w
            Ws[r].append(float(t.max()))
        if c_ok is None and all(k_ok(level_ks(Ws[r][-1])) for r in reps):
            c_ok = c
        if c_ok is not None and c >= c_ok + 5:
            break
    if c_ok is None:
        raise RuntimeError(f"no copy count up to {cmax} reaches k >= {K_MIN_RHO1} at rho 1.0")
    return c_ok, Ws


def p2_inputs(D, S, cfg, cache, variant="base"):
    """Per-row inputs of the simulated traces under reading `cfg`, and the pool.  Rows:
    submissions of the pool semesters (POOL60; POOL19 for variant pool19) with a forward
    prediction, minus the 2020-2022 C == 0 blocks.  variant: base / pool19 (every block its
    own job with its own C_cap) | sbatch (each co-ending group one job: arrival = min(ts' -
    C) over the members, service = max C_cap, predicted cost and deadline/exam membership of
    the EARLIEST-ARRIVING member, whose code and history are the only ones that exist at
    that arrival) | sdrop (co-ending groups removed) | dedup (repeated submissions removed).
    Arrivals and the week base use the jittered clock of cfg."""
    assert variant in VARIANTS, variant
    sidx = D["sidx"]
    sem = D["sem"][sidx]
    arr_all, _ = times(D, cfg)
    tsc = (D["ts"] + D["u"] if CONFIGS[cfg][3] else D["ts"])[sidx]
    arr = arr_all[sidx]
    Ccap = np.minimum(D["C"][sidx], L_CAP)
    fw = pd.read_parquet(os.path.join(cache, f"forward_{cfg}.parquet"))
    P = {m: fw[m].values.copy() for m in fw.columns}
    extra = {}
    d600 = "ires600" if CONFIGS[cfg][0] == "res" else "isub600"
    for tag, fn in (("d600", f"forward_{d600}.parquet"), ("v1feat", "forward_v1.parquet")):
        if variant == "base" and cfg == PRIMARY and os.path.exists(os.path.join(cache, fn)):
            extra[f"M4-{tag}"] = pd.read_parquet(os.path.join(cache, fn))["M4"].values.copy()
    have = np.isfinite(P["M4"])
    for v in list(P.values()) + list(extra.values()):
        assert np.array_equal(np.isfinite(v), have)
    pool_sems = POOL19 if variant == "pool19" else POOL60
    in_pool = have & np.isin(sem, pool_sems)
    keep = in_pool & D["simok"]
    dl = S["a_end"] - arr
    in_dl = (dl <= 86400) & (dl >= 0)
    in_exam = (S["a_is_exam"] == 1) & (arr >= S["a_start"]) & (arr <= S["a_end"])
    g = D["coend"]
    info = dict(rows=int(in_pool.sum()), zero_dropped=int((in_pool & ~D["simok"]).sum()))
    if variant == "sdrop":
        info["removed"] = int((keep & (g >= 0)).sum())
        keep &= g < 0
    elif variant == "dedup":
        info["removed"] = int((keep & D["dup"][sidx]).sum())
        keep &= ~D["dup"][sidx]
    elif variant == "sbatch":
        r = np.flatnonzero(keep & (g >= 0))
        r = r[np.lexsort((r, arr[r], g[r]))]            # by group, then arrival, then row
        st = np.flatnonzero(np.r_[True, g[r][1:] != g[r][:-1]])
        rep = r[st]                                      # earliest-arriving member
        Ccap = Ccap.copy()
        Ccap[rep] = np.maximum.reduceat(Ccap[r], st)     # its prediction stays its own
        keep[np.setdiff1d(r, rep)] = False
        info.update(groups=len(rep), members=len(r), removed=len(r) - len(rep))
    hvt = Ccap > D["heavy_thr"]
    codes, uni = pd.factorize(S["cs"])
    per_cs = {}
    for c in np.unique(codes[keep]):
        idx = np.flatnonzero((codes == c) & keep)
        o = np.argsort(tsc[idx], kind="stable")
        per_cs[uni[c]] = {"ts": tsc[idx][o], "arr": arr[idx][o], "svc": Ccap[idx][o], "idx": idx[o],
                          "base": cs_base(tsc[idx].min())}
    info["jobs"] = int(keep.sum())
    info["work_s"] = round(float(Ccap[keep].sum()), 1)
    return dict(P=P, extra=extra, in_dl=in_dl, in_exam=in_exam, hvt=hvt, pool=sorted(per_cs),
                per_cs=per_cs, Ccap=Ccap, keep=keep, info=info, pool_sems=pool_sems)


def trace_of(cfg, variant):
    for nm, (c, v, _) in TRACES.items():
        if (c, v) == (cfg, variant):
            return nm
    raise SystemExit(f"no trace ({cfg}, {variant}); traces: {TRACES}")


def trace_key(cfg):
    return "ts" if CONFIGS[cfg][0] == "sub" else "arr"


def busy_comp(a, svc, jidx, D, S):
    """Composition of the busiest arrival hour (floor(t/3600) bins, the hour that sets k):
    its C_cap work, the shares of it by semester, from jobs at the 60 s cap, and from
    co-ending group members (for sbatch: the collapsed group jobs)."""
    hr = np.floor(a / 3600.0).astype(np.int64)
    uh, inv = np.unique(hr, return_inverse=True)
    work = np.bincount(inv, weights=svc)
    h = int(work.argmax())
    m = inv == h
    W = float(work[h])
    sem = D["sem"][D["sidx"]][jidx[m]]
    sv = svc[m]
    r = dict(hour=stamp(uh[h] * 3600.0), W_s=round(W, 1), jobs=int(m.sum()),
             share_Ccap60=round(float(sv[sv >= L_CAP].sum() / W), 4),
             share_coend=round(float(sv[D["coend"][jidx[m]] >= 0].sum() / W), 4),
             distinct_cs=len(set(S["cs"][jidx[m]])))
    for s in POOL19:
        r[f"share_{s}"] = round(float(sv[sem == s].sum() / W), 4)
    return r, W


def wstats(w, d, xm, hvt):
    q = np.quantile
    nan = np.nan
    return dict(w_mean=w.mean(), w_p95=q(w, .95), w_p99=q(w, .99), w_max=w.max(),
                w_mean_dl=w[d].mean() if d.any() else nan,
                w_p95_dl=q(w[d], .95) if d.any() else nan,
                w_p99_dl=q(w[d], .99) if d.any() else nan,
                w_mean_exam=w[xm].mean() if xm.any() else nan,
                w_p99_exam=q(w[xm], .99) if xm.any() else nan,
                mean_heavy=w[hvt].mean() if hvt.any() else nan,
                p95_heavy=q(w[hvt], .95) if hvt.any() else nan,
                p99_heavy=q(w[hvt], .99) if hvt.any() else nan,
                max_heavy=w[hvt].max() if hvt.any() else nan)


# --------------------------------------------------------------------------- #
# week-block bootstrap of the queueing metrics
# --------------------------------------------------------------------------- #
def boot_weights(nw, nboot=N_BOOT_P2, seed=BOOT_P2_SEED):
    """Multiplicity of each week in each resample: nw weeks drawn with replacement."""
    return np.random.default_rng(seed).multinomial(nw, np.full(nw, 1.0 / nw), size=nboot)


def boot_mean(x, wk, M):
    """Mean of the pooled resample (week w taken M[b, w] times), per resample b."""
    nw = M.shape[1]
    s = np.bincount(wk, weights=x, minlength=nw)
    n = np.bincount(wk, minlength=nw).astype(float)
    return (M @ s) / (M @ n)


def _np_lerp(a, b, t):
    """numpy's quantile interpolation (numpy.lib._function_base_impl._lerp)."""
    d = b - a
    return b - d * (1.0 - t) if t >= 0.5 else a + d * t


def boot_quantile(x, wk, M, q, nblk=4000):
    """q-quantile (numpy's default 'linear' method) of the pooled resample in which week w
    appears M[b, w] times, exactly, per resample b.  The values are sorted once and cut into
    position blocks; block counts per resample (M @ per-week block counts) locate the block
    holding the needed order statistic, and a weighted scan inside the block finds it."""
    B, nw = M.shape
    o = np.argsort(x, kind="stable")
    xs, ws = x[o], wk[o]
    n = len(xs)
    edges = np.unique(np.linspace(0, n, min(nblk, n) + 1).astype(np.int64))
    nb = len(edges) - 1
    blk = np.repeat(np.arange(nb), np.diff(edges))
    H = np.bincount(ws * nb + blk, minlength=nw * nb).reshape(nw, nb).astype(float)
    cum = np.cumsum(M.astype(float) @ H, axis=1)
    N = cum[:, -1]
    out = np.full(B, np.nan)
    for b in range(B):
        nn = int(N[b])
        if nn == 0:
            continue
        vi = (nn - 1) * q                  # numpy's virtual index for method 'linear'
        prv = int(np.floor(vi))
        t = vi - prv
        prv = min(max(prv, 0), nn - 1)
        nxt = min(prv + 1, nn - 1)
        vals = []
        for r in (prv, nxt):
            j = int(np.searchsorted(cum[b], r, side="right"))
            before = cum[b, j - 1] if j > 0 else 0.0
            s0, s1 = edges[j], edges[j + 1]
            cw = np.cumsum(M[b, ws[s0:s1]])
            vals.append(xs[s0 + int(np.searchsorted(cw, r - before, side="right"))])
        out[b] = _np_lerp(vals[0], vals[1], t)
    return out


# --------------------------------------------------------------------------- #
# P2 stages
# --------------------------------------------------------------------------- #
def policies(svc, P, extra, rep, full=True):
    """(name, mode, predicted-cost key, B).  full (primary): FCFS, SJF-ref, SPJF with M1, M3,
    M4, M5 and the ires600 and v1-feature M4 contrasts, the M4 guard at every B, and the
    adversarial top-1%-predicted-shortest predictor with and without the B = 120 guard.
    Otherwise the reduced set every sensitivity runs.  Returns the policy list and the
    predicted-cost arrays it refers to."""
    pri = {"svc": svc}
    pri.update(P)
    pri.update(extra)
    pM4 = P["M4"]
    top1 = pM4.copy()
    top1[np.argsort(-svc, kind="stable")[:max(1, len(svc) // 100)]] = pM4.min() - 1.0
    pri["top1"] = top1
    pol = [("FCFS", "fcfs", None, None), ("SJF-ref", "pri", "svc", None), ("SPJF-M1", "pri", "M1", None)]
    if full:
        pol.append(("SPJF-M3", "pri", "M3", None))
    pol += [("SPJF-M4", "pri", "M4", None), ("SPJF-M5", "pri", "M5", None)]
    if full:
        pol += [(f"SPJF-{nm}", "pri", nm, None) for nm in extra]
    pol += [(f"GUARD-M4-B{b:g}", "guard", "M4", b) for b in GUARD_B]
    if full:
        pol += [("ADV-top1short", "pri", "top1", None), ("ADV-top1short+G120", "guard", "top1", 120.0)]
    return pol, pri


E2E = ("SPJF-M1", "SPJF-M4", "SPJF-M5") + tuple(f"GUARD-M4-B{b:g}" for b in GUARD_B)


def _p2_task(t):
    """Worker process: one policy at one level of a saved trace.  Returns the CSV row and,
    for pure runs, the week-bootstrap replicates of the mean and deadline-window p99 wait."""
    d = t["dir"]
    ld = lambda nm: np.load(os.path.join(d, nm + ".npy"))
    a, svc = ld("a"), ld("svc")
    pri = ld("pri_" + t["pri"]) if t["pri"] else None
    K, mode, B = t["K"], t["mode"], t["B"]
    t0 = time.time()
    if t["setting"] == "pure":
        w = simulate(a, svc, pri, K, mode, B)
    else:                   # end-to-end: enqueue after the job's latency, wait from arrival
        lj = ld("lj")
        al = a + lj
        ol = np.argsort(al, kind="stable")
        wl = np.empty(len(a))
        wl[ol] = simulate(al[ol], svc[ol], None if pri is None else pri[ol], K, mode, B)
        w = wl + lj
    if not (np.isfinite(w).all() and (w >= -1e-6).all()):
        raise RuntimeError(f"bad waits in {t['name']}")
    if t["name"] == "FCFS":
        dkw = float(np.abs(w - fcfs_kw(a, svc, K)).max())
        assert dkw == 0.0, ("FCFS != Kiefer-Wolfowitz on the real trace", dkw)
        np.save(os.path.join(d, f"wf_k{K}.npy"), w)
        wf = w
    else:
        wf = ld(f"wf_k{K}")
    dm, xm, hvt = ld("dl"), ld("exam"), ld("heavy")
    row = dict(t["base"], setting=t["setting"], policy=t["name"], max_excess=float((w - wf).max()),
               sim_sec=round(time.time() - t0, 1), **wstats(w, dm, xm, hvt))
    boot = None
    if t["setting"] == "pure":
        wk = ld("wk")
        M = np.vstack([np.ones((1, ld("M").shape[1]), np.int64), ld("M")])   # row 0 = identity
        bm = boot_mean(w, wk, M)
        bq = boot_quantile(w[dm], wk[dm], M, 0.99)
        assert abs(bm[0] - row["w_mean"]) <= 1e-9 * max(1.0, row["w_mean"]), (bm[0], row["w_mean"])
        assert abs(bq[0] - row["w_p99_dl"]) <= 1e-9 * max(1.0, row["w_p99_dl"]), (bq[0], row["w_p99_dl"])
        boot = (bm[1:], bq[1:])
    return t["rho"], t["name"], t["setting"], row, boot


def p2_weeks(cache, trace):
    wk = pd.read_csv(os.path.join(cache, "p2weeks.csv"))
    return np.sort(wk[wk.trace == trace].week.values.astype(np.int64))


def stage_p2(ev, D, S, cfg, reps, cache, variant="base", workers=N_WORKERS):
    trace = trace_of(cfg, variant)
    full = trace == "primary"
    cp = pd.read_csv(os.path.join(cache, "copies.csv")).set_index("trace")
    copies = int(cp.loc[trace, "copies"])
    weeks = p2_weeks(cache, trace)
    M = boot_weights(len(weeks))
    head(f"P2 [{trace}: {cfg}, {variant}] counterfactual shared judge pool, overlay reps {reps}, "
         f"target busy-hour rho {RHOS}")
    I = p2_inputs(D, S, cfg, cache, variant)
    key = trace_key(cfg)
    lat = np.load(os.path.join(cache, "latency.npz"))["total"]
    say(f"pool {len(I['pool'])} class-semesters of {I['pool_sems']}; rows {I['info']}; {copies} overlay copies "
        f"(copies.csv); {'full policy set, pure + end-to-end' if full else 'reduced policy set, pure only'}; "
        f"week bootstrap over {len(weeks)} weeks, {N_BOOT_P2} resamples (seed {BOOT_P2_SEED})")
    tmp = os.path.join(cache, "simtmp")
    os.makedirs(tmp, exist_ok=True)
    for rep in reps:
        t_rep = time.time()
        a, svc, jidx, _ = overlay(ms_entries(I["pool"], copies, rep), I["per_cs"], key)
        W = v1.busy_hour_work(a, svc)[0]
        Wp = float(cp.loc[trace, f"W_rep{rep}"]) if f"W_rep{rep}" in cp.columns else np.nan
        assert np.isnan(Wp) or abs(W - Wp) < 1e-6, (W, Wp)
        Ks = level_ks(W)
        assert k_ok(Ks), (trace, rep, W, Ks)
        wk = np.floor((a - REF_MON) / WEEK).astype(np.int64)
        wki = np.searchsorted(weeks, wk)
        assert np.array_equal(weeks[np.minimum(wki, len(weeks) - 1)], wk), "a job outside the trace's week set"
        a = rebase(a)
        pol, pri = policies(svc, {m: v[jidx] for m, v in I["P"].items()},
                            {m: v[jidx] for m, v in I["extra"].items()}, rep, full)
        arrays = dict(a=a, svc=svc, dl=I["in_dl"][jidx], exam=I["in_exam"][jidx], heavy=I["hvt"][jidx],
                      wk=wki, M=M)
        if full:
            arrays["lj"] = np.random.default_rng(SEED * 1000 + rep).choice(lat, len(a))  # per-job latency (s)
        for nm, v in arrays.items():
            np.save(os.path.join(tmp, nm + ".npy"), v)
        for nm in {p[2] for p in pol if p[2]}:
            np.save(os.path.join(tmp, "pri_" + nm + ".npy"), pri[nm])
        del arrays
        tasks1, tasks2 = [], []
        for rho_t, K in zip(RHOS, Ks):
            base = dict(config=cfg, variant=variant, trace=trace, rep=rep, rho_target=rho_t, k=K, copies=copies,
                        rho_busy=W / (3600.0 * K), rho_mean=svc.sum() / (K * (a[-1] - a[0])),
                        n_jobs=len(a), n_heavy=int(I["hvt"][jidx].sum()), n_dl=int(I["in_dl"][jidx].sum()))
            for name, mode, pk, B in pol:
                tk = dict(dir=tmp, name=name, setting="pure", mode=mode, pri=pk, B=B, K=K, rho=rho_t, base=base)
                (tasks1 if name == "FCFS" else tasks2).append(tk)
                if full and name in E2E:
                    tasks2.append(dict(tk, setting="e2e"))
        order = {"guard": 0, "pri": 1, "fcfs": 2}
        tasks2.sort(key=lambda x: (order[x["mode"]], x["setting"] != "e2e"))
        res = []
        with ProcessPoolExecutor(max_workers=min(workers, len(tasks2))) as ex:
            res += list(ex.map(_p2_task, tasks1))
            res += list(ex.map(_p2_task, tasks2))
        for rho_t, K in zip(RHOS, Ks):
            rr = [x for x in res if x[0] == rho_t]
            rows = [x[3] for x in rr]
            pd.DataFrame(rows).to_csv(os.path.join(cache, f"p2_{cfg}_{variant}_rep{rep}_r{rho_t:g}.csv"),
                                      index=False)
            bt = {f"{m}|{x[1]}": x[4][i] for x in rr if x[4] is not None for i, m in enumerate(("mean", "p99dl"))}
            np.savez(os.path.join(cache, f"p2bw_{cfg}_{variant}_rep{rep}_r{rho_t:g}.npz"), **bt)
            mw = {x[1]: x[3] for x in rr if x[2] == "pure"}
            say(f"  {el()} rep{rep} rho~{rho_t}: k={K}, {len(a):,} jobs, busy-hour rho={W/(3600.0*K):.3f}; "
                f"p99_dl FCFS {mw['FCFS']['w_p99_dl']:.3f} / SJF-ref {mw['SJF-ref']['w_p99_dl']:.3f} / SPJF-M4 "
                f"{mw['SPJF-M4']['w_p99_dl']:.3f} / GUARD-M4-B120 {mw['GUARD-M4-B120']['w_p99_dl']:.3f} s; mean "
                f"FCFS {mw['FCFS']['w_mean']:.4f} (== Kiefer-Wolfowitz) / SPJF-M4 {mw['SPJF-M4']['w_mean']:.4f} s")
        for fn in os.listdir(tmp):
            os.remove(os.path.join(tmp, fn))
        say(f"  rep{rep}: {time.time() - t_rep:.0f} s with {workers} worker processes")
    dump(cache, f"p2_{trace}_" + "_".join(map(str, reps)))


def stage_pool(ev, D, S, cache):
    head("P2 pool: class-semesters, overlay copies and busiest hours of the simulated traces")
    say("counterfactual shared judge pool: the original platform ran every student in a private")
    say("Docker container with no shared queue; arrivals and costs are real, pool/queue/order ours.")
    say(f"primary pool = the 60 s-limit DEV semesters {POOL60} (2020-1: archive incomplete,")
    say("2019-2: truncated); sensitivity 'pool19' adds 2019-1 (the previous round's pool).  Arrivals")
    say("on the jittered clock; C == 0 blocks of 2020-2022 dropped.")
    sidx = D["sidx"]
    sem = D["sem"][sidx]
    Iv = {v: p2_inputs(D, S, PRIMARY, cache, v) for v in VARIANTS}
    for v in ("base", "pool19"):
        by = {}
        for cs in Iv[v]["pool"]:
            s, c = cs.split("|")
            by.setdefault(s, []).append(c)
        say(f"\n{'primary' if v == 'base' else 'pool19'}: {len(Iv[v]['pool'])} class-semesters, "
            f"{Iv[v]['info']['jobs']:,} jobs and {Iv[v]['info']['work_s']:,.1f} s of C_cap work per copy")
        for s in DEV:
            if s in by:
                say(f"  {s}: classes {', '.join(sorted(by[s], key=lambda x: (len(x), x)))}")
    rows = []
    for v in VARIANTS:
        for s in DEV + ["ALL"]:
            m = (sem == s) if s != "ALL" else np.ones(len(sem), bool)
            k = Iv[v]["keep"] & m
            if not k.any():
                continue
            rows.append(dict(variant=v, semester=s, jobs=int(k.sum()),
                             work_Ccap_s=round(float(Iv[v]["Ccap"][k].sum()), 1),
                             heavy=int((k & Iv[v]["hvt"]).sum())))
        say(f"  variant {v}: {Iv[v]['info']}")
    pt = pd.DataFrame(rows)
    pt.to_csv(os.path.join(cache, "pool.csv"), index=False)
    say("\njobs per semester and variant (one copy):")
    say(pt.pivot_table(index="semester", columns="variant", values="jobs", sort=False).fillna(0)
        .astype(int).to_string())
    say("\nC_cap work (s) per semester and variant (one copy):")
    say(pt.pivot_table(index="semester", columns="variant", values="work_Ccap_s", sort=False).to_string())
    zd = pd.Series(sem[~D["simok"]]).value_counts().reindex(DEV).fillna(0).astype(int)
    say("\nC == 0 blocks removed from the traces (all semesters, 2020-2022 only): " +
        ", ".join(f"{k_} {v_}" for k_, v_ in zd.items()) + f"; total {int(zd.sum()):,}")
    ndup = Iv["dedup"]["info"]["removed"]
    run = [t for t in TRACES if not (t == "dedup" and ndup == 0)]
    say(f"repeated submissions inside the primary pool after the C == 0 drop: {ndup} per copy" +
        ("; the dedup trace equals the primary and is not run." if ndup == 0 else "."))

    head("P2 overlay copies: smallest count with k >= 4 at rho 1.0 and three distinct k in reps 0-4")
    say("k per level = busiest-hour C_cap work W / (3600 rho) rounded half up.  The overlay with c + 1")
    say("copies contains the one with c (copy-major draws), so W never falls as copies are added.")
    prow, crow, wrow, brow = [], [], [], []
    for tr in run:
        cfg, var, reps = TRACES[tr]
        I = Iv[var] if cfg == PRIMARY else p2_inputs(D, S, cfg, cache, var)
        key = trace_key(cfg)
        t = time.time()
        c_ok, Ws = copies_probe(I["pool"], I["per_cs"], key, PROBE_REPS)
        for r in PROBE_REPS:
            for c, W in enumerate(Ws[r], 1):
                ks = level_ks(W)
                prow.append(dict(trace=tr, config=cfg, variant=var, rep=r, copies=c, W_s=round(W, 3),
                                 W_over_3600=round(W / 3600.0, 4), k05=ks[0], k08=ks[1], k10=ks[2], ok=k_ok(ks)))
        cr = dict(trace=tr, config=cfg, variant=var, copies=c_ok, class_semesters=len(I["pool"]),
                  jobs_per_overlay=c_ok * I["info"]["jobs"], reps_simulated=",".join(map(str, reps)))
        for r in PROBE_REPS:
            cr[f"W_rep{r}"] = Ws[r][c_ok - 1]
            cr[f"k_rep{r}"] = "/".join(map(str, level_ks(Ws[r][c_ok - 1])))
        crow.append(cr)
        pr = pd.DataFrame([x for x in prow if x["trace"] == tr])
        lo_c = max(1, c_ok - 4)
        tb = pr[(pr.copies >= lo_c) & (pr.copies <= c_ok + 2)].groupby("copies").agg(
            W_min=("W_s", "min"), W_max=("W_s", "max"), k10_min=("k10", "min"), reps_ok=("ok", "sum"))
        say(f"\n[{tr}] {cfg}/{var}: chosen {c_ok} copies x {len(I['pool'])} class-semesters = "
            f"{c_ok * I['info']['jobs']:,} jobs per overlay ({time.time()-t:.0f} s); k at the chosen count: " +
            ", ".join(f"rep{r} {cr[f'k_rep{r}']}" for r in PROBE_REPS))
        say(tb.to_string())
        # busiest-hour composition and bootstrap week set of every simulated overlay
        wks = set()
        for r in reps:
            a, svc, jidx, _ = overlay(ms_entries(I["pool"], c_ok, r), I["per_cs"], key)
            comp, W = busy_comp(a, svc, jidx, D, S)
            assert abs(W - Ws[r][c_ok - 1]) < 1e-6, (tr, r, W, Ws[r][c_ok - 1])
            ks = level_ks(W)
            brow.append(dict(trace=tr, rep=r, copies=c_ok, k="/".join(map(str, ks)),
                             rho_busy="/".join(f"{W / (3600.0 * k):.3f}" for k in ks), **comp))
            wks |= set(np.unique(np.floor((a - REF_MON) / WEEK).astype(np.int64)).tolist())
            del a, svc, jidx
        wrow += [dict(trace=tr, week=w) for w in sorted(wks)]
    pd.DataFrame(prow).to_csv(os.path.join(cache, "copies_probe.csv"), index=False)
    pd.DataFrame(crow).to_csv(os.path.join(cache, "copies.csv"), index=False)
    pd.DataFrame(wrow).to_csv(os.path.join(cache, "p2weeks.csv"), index=False)
    bh = pd.DataFrame(brow)
    bh.to_csv(os.path.join(cache, "busy_hour.csv"), index=False)
    say("\nchosen copies (copies.csv; the full probe, copies vs W vs k per rep, is copies_probe.csv):")
    say(pd.DataFrame(crow)[["trace", "config", "variant", "copies", "class_semesters", "jobs_per_overlay"] +
                           [f"k_rep{r}" for r in PROBE_REPS]].to_string(index=False))
    say("\nbusiest hour of every simulated overlay (W_s = its C_cap work, which sets k; shares of W by")
    say("semester, from jobs at the 60 s cap and from co-ending group members):")
    say(bh.to_string(index=False))
    say("\nweeks in the bootstrap week set per trace: " +
        ", ".join(f"{t} {sum(1 for x in wrow if x['trace'] == t)}" for t in run))
    dump(cache, "p2_0pool")


def k1_select(pool, per_cs, seed, key):
    """Class-semester copies of the single-server configuration.  Phase 1 (random): the pool
    listed 8 times in a random order (seed), each copy with its own 0-11 extra whole weeks
    (seed + 1); a copy is added when the busiest-hour rho at k = 1 stays <= 0.82, and the phase
    stops at the first state with rho >= 0.80.  Phase 2 (top-up, only when phase 1 ends below
    0.78): the (class-semester, week shift) pair of the whole pool x 0-11 whose resulting rho
    is closest to 0.80 without passing 0.82 is added, while it raises rho.  Phase 2 is needed
    because a copy whose own peak misses the current busiest hour is free (it leaves rho where
    it is), so the random phase can exhaust its candidates below the window.  Of the states in
    [0.78, 0.82] the one closest to 0.80 is kept; the selection is a prefix of the additions,
    so the probe's rho is the rho of the returned entries.  Returns the entries and that rho."""
    L = 8
    cand = [(pool * L)[i] for i in np.random.default_rng(seed).permutation(L * len(pool))]
    js = np.random.default_rng(seed + 1).integers(0, 12, len(cand))
    hh = hour_hist(per_cs, key)
    lo = min(off for off, _ in hh.values())
    tot = np.zeros(max(off + len(w) for off, w in hh.values()) - lo + 12 * 168 + 1)
    cur, sel, states = 0.0, [], []

    def peak_after(cs, j):
        off, w = hh[cs]
        st = off - lo + int(j) * 168
        return st, len(w), float((tot[st:st + len(w)] + w).max())

    def add(cs, j, new):
        nonlocal cur
        st, n_, _ = peak_after(cs, j)
        tot[st:st + n_] += hh[cs][1]
        cur = new
        sel.append((cs, int(j)))
        states.append((len(sel), cur / 3600.0))

    for cs, j in zip(cand, js):
        new = max(cur, peak_after(cs, j)[2])
        if new / 3600.0 > K1_WINDOW[1]:
            continue
        add(cs, j, new)
        if cur / 3600.0 >= K1_TARGET:
            break
    while cur / 3600.0 < K1_WINDOW[0]:                      # phase 2
        best = None
        for cs in sorted(pool):
            for j in range(12):
                new = max(cur, peak_after(cs, j)[2])
                if new / 3600.0 > K1_WINDOW[1] or new <= cur + 1e-9:
                    continue
                d = abs(new / 3600.0 - K1_TARGET)
                if best is None or d < best[0]:
                    best = (d, cs, j, new)
        if best is None:
            break
        add(best[1], best[2], best[3])
    ok = [(abs(r - K1_TARGET), n, r) for n, r in states if K1_WINDOW[0] <= r <= K1_WINDOW[1]]
    if not ok:
        raise RuntimeError(f"single-server selection reached rho {cur / 3600.0:.3f}, outside {K1_WINDOW}")
    _, n, r = min(ok)
    return sel[:n], r


def stage_guardk1(ev, D, S, cfgs, reps, cache):
    head("G. SINGLE-SERVER CONFIGURATION (k = 1), PER-JOB PROPOSITION 3")
    say(f"pure scheduling (identical enqueue times for all policies), primary pool {POOL60}, busy-hour")
    say(f"rho at k=1 in {list(K1_WINDOW)}, closest to {K1_TARGET}; assert")
    say("W_guard[i] <= W_FCFS[i] + B + 60 for EVERY job, B in {30,120,600}, predictors M1/M3/M4/M5")
    say("(forward) and reversed / random / top-1%-predicted-shortest (adversarial); FCFS == Lindley.")
    for cfg in cfgs:
        I = p2_inputs(D, S, cfg, cache)
        key = trace_key(cfg)
        fwd = [m for m in ("M1", "M3", "M4", "M5") if m in I["P"]]
        for rep in reps:
            seed = SEED * 100 + 50 + rep
            sel, rho_p = k1_select(I["pool"], I["per_cs"], seed, key)
            a, svc, jidx, _ = overlay(sel, I["per_cs"], key)
            comp, W = busy_comp(a, svc, jidx, D, S)
            rho = W / 3600.0
            assert abs(rho - rho_p) < 1e-9 and K1_WINDOW[0] <= rho <= K1_WINDOW[1], (rho, rho_p)
            a = rebase(a)
            wf = simulate(a, svc, None, 1, "fcfs")
            dl = float(np.abs(wf - lindley(a, svc)).max())
            assert dl <= 1e-6, dl
            d, xm, hvt = I["in_dl"][jidx], I["in_exam"][jidx], I["hvt"][jidx]
            P = {m: I["P"][m][jidx] for m in fwd}
            rng = np.random.default_rng(SEED + rep)
            top1 = P["M4"].copy()
            top1[np.argsort(-svc, kind="stable")[:max(1, len(svc) // 100)]] = P["M4"].min() - 1.0
            preds = dict(P, reversed=-svc, random=rng.permutation(svc), top1short=top1)
            per_sem = pd.Series([cs.split("|")[0] for cs, _ in sel]).value_counts().sort_index()
            say(f"\n  {el()} {cfg} rep{rep}: {len(sel)} class-semester copies ({len(set(cs for cs, _ in sel))} "
                f"distinct; per semester {', '.join(f'{k_} {v_}' for k_, v_ in per_sem.items())}), {len(a):,} jobs, "
                f"{int(hvt.sum())} heavy, busy-hour rho at k=1 = {rho:.4f}; FCFS mean wait {wf.mean():.3f} s; "
                f"FCFS vs Lindley max |diff| {dl:.1e} s")
            say("  busiest hour: " + ", ".join(f"{k_} {v_}" for k_, v_ in comp.items()))
            rows, prow = [], []
            base = dict(config=cfg, rep=rep, n_cs=len(sel), n_jobs=len(a), rho_busy=rho)
            for name, w in (("FCFS", wf), ("SJF-ref", simulate(a, svc, svc, 1, "pri"))):
                prow.append(dict(base, policy=name, **wstats(w, d, xm, hvt)))
            for pn, pr in preds.items():
                wu = simulate(a, svc, pr, 1, "pri")
                r = dict(base, predictor=pn, fcfs_mean=wf.mean(), unguarded_mean=wu.mean(),
                         unguarded_max_excess=float((wu - wf).max()))
                if pn in P:
                    prow.append(dict(base, policy=f"SPJF-{pn}", **wstats(wu, d, xm, hvt)))
                for B in GUARD_B:
                    wg = simulate(a, svc, pr, 1, "guard", B)
                    ex_ = wg - wf
                    nviol = int((ex_ > B + L_CAP + 1e-6).sum())
                    assert nviol == 0, (cfg, rep, pn, B, float(ex_.max()))
                    r[f"B{B:g}_mean"] = wg.mean()
                    r[f"B{B:g}_max_excess"] = float(ex_.max())
                    r[f"B{B:g}_jobs_checked"] = len(ex_)
                    if pn in P:
                        prow.append(dict(base, policy=f"GUARD-{pn}-B{B:g}", **wstats(wg, d, xm, hvt)))
                rows.append(r)
            res = pd.DataFrame(rows)
            res.to_csv(os.path.join(cache, f"guardk1_{cfg}_rep{rep}.csv"), index=False)
            pd.DataFrame(prow).to_csv(os.path.join(cache, f"guardk1pol_{cfg}_rep{rep}.csv"), index=False)
            pd.DataFrame([dict(config=cfg, rep=rep, copies=len(sel), rho_busy=rho, **comp)]).to_csv(
                os.path.join(cache, f"guardk1busy_{cfg}_rep{rep}.csv"), index=False)
            say(res.drop(columns=["config", "rep", "n_cs", "n_jobs", "rho_busy"]).round(2).to_string(index=False))
            say(f"  => {len(a):,} jobs x {len(preds)} predictors x {len(GUARD_B)} budgets checked, "
                f"0 violations; bounds B+60 = 90 / 180 / 660 s.")
    dump(cache, "guardk1_" + "_".join(cfgs) + "_" + "_".join(map(str, reps)))


PAIRS = (("SPJF-M5", "SPJF-M4"), ("SPJF-M4", "GUARD-M4-B600"), ("SPJF-M4", "GUARD-M4-B120"),
         ("SPJF-M4", "SPJF-M1"))
BOOT_METRICS = (("p99dl", "w_p99_dl"), ("mean", "w_mean"))


def stage_p2boot(cache, traces):
    """Gains and pairwise gain differences with paired week-block bootstrap CIs."""
    head(f"P2b. WEEK-BLOCK BOOTSTRAP ({N_BOOT_P2:,} resamples, paired over policies, levels and overlays)")
    say("A resample draws whole weeks of the overlay timeline with replacement (the trace's week set,")
    say("p2weeks.csv); every policy, level and overlay rep of a trace uses the same draws.  Per resample:")
    say("gain_r = (FCFS_r - policy_r) / (FCFS_r - SJF-ref_r) on overlay r, averaged over the reps; the")
    say("point gain uses the full trace.  CI = 2.5/97.5% of the resamples.  unstable = rep-mean")
    say("(FCFS - SJF-ref) < 0.1 s or < 5% of rep-mean FCFS on that metric.  A pairwise difference is")
    say("gain(a) - gain(b); 'resolved' when its CI excludes 0.")
    grows, drows = [], []
    for tr in traces:
        cfg, var, _ = TRACES[tr]
        fs = sorted(n for n in os.listdir(cache) if n.startswith(f"p2bw_{cfg}_{var}_rep"))
        if not fs:
            continue
        reps_have = sorted({int(re.search(r"_rep(\d+)_", n).group(1)) for n in fs})
        sets = [("all", reps_have)]
        if tr == "primary" and len(reps_have) > 3:
            sets.append(("reps0-2", [r for r in reps_have if r <= 2]))
        for label, reps in sets:
            for rho in RHOS:
                csv = {r: pd.read_csv(os.path.join(cache, f"p2_{cfg}_{var}_rep{r}_r{rho:g}.csv")) for r in reps}
                csv = {r: c[c.setting == "pure"].set_index("policy") for r, c in csv.items()}
                bw = {r: np.load(os.path.join(cache, f"p2bw_{cfg}_{var}_rep{r}_r{rho:g}.npz")) for r in reps}
                pols = list(csv[reps[0]].index)
                for mk, col in BOOT_METRICS:
                    Fp = np.array([csv[r].loc["FCFS", col] for r in reps])
                    Sp = np.array([csv[r].loc["SJF-ref", col] for r in reps])
                    Fb = np.array([bw[r][f"{mk}|FCFS"] for r in reps])
                    Sb = np.array([bw[r][f"{mk}|SJF-ref"] for r in reps])
                    den = float(np.mean(Fp - Sp))
                    unstable = den < 0.1 or den < 0.05 * float(np.mean(Fp))
                    gb, gp = {}, {}
                    for p in pols:
                        Pp = np.array([csv[r].loc[p, col] for r in reps])
                        Pb = np.array([bw[r][f"{mk}|{p}"] for r in reps])
                        with np.errstate(divide="ignore", invalid="ignore"):
                            gb[p] = np.mean((Fb - Pb) / (Fb - Sb), axis=0)
                        gp[p] = float(np.mean((Fp - Pp) / (Fp - Sp)))
                        fin = np.isfinite(gb[p])
                        grows.append(dict(trace=tr, config=cfg, variant=var, reps=label, n_reps=len(reps), rho=rho,
                                          metric=mk, policy=p, k=float(np.mean([csv[r].loc[p, "k"] for r in reps])),
                                          rho_busy=float(np.mean([csv[r].loc[p, "rho_busy"] for r in reps])),
                                          wait=float(np.mean(Pp)), gain=gp[p],
                                          lo=float(np.percentile(gb[p][fin], 2.5)) if fin.any() else np.nan,
                                          hi=float(np.percentile(gb[p][fin], 97.5)) if fin.any() else np.nan,
                                          boot_nonfinite=int((~fin).sum()), fcfs_minus_sjf=den,
                                          unstable=unstable))
                    for pa, pb in PAIRS:
                        if pa not in gb or pb not in gb:
                            continue
                        dd = gb[pa] - gb[pb]
                        fin = np.isfinite(dd)
                        lo, hi = float(np.percentile(dd[fin], 2.5)), float(np.percentile(dd[fin], 97.5))
                        drows.append(dict(trace=tr, config=cfg, variant=var, reps=label, rho=rho, metric=mk,
                                          pair=f"{pa} - {pb}", diff=gp[pa] - gp[pb], lo=lo, hi=hi,
                                          resolved=bool(lo > 0 or hi < 0),
                                          verdict=(f"{pa} > {pb}" if lo > 0 else f"{pb} > {pa}" if hi < 0
                                                   else "unresolved"), unstable=unstable))
            say(f"  {el()} {tr} ({label}, reps {reps}) done")
    g = pd.DataFrame(grows)
    dd = pd.DataFrame(drows)
    g.to_csv(os.path.join(cache, "p2gain.csv"), index=False)
    dd.to_csv(os.path.join(cache, "p2diff.csv"), index=False)
    for tr in g.trace.unique():
        for mk, _ in BOOT_METRICS:
            z = g[(g.trace == tr) & (g.metric == mk) & (g.reps == "all")]
            z = z.assign(cell=[f"{a:.3f} [{l:.3f},{h:.3f}]" for a, l, h in zip(z.gain, z.lo, z.hi)])
            say(f"\n{tr}, gain on {mk} (point [95% week-block CI]):")
            say(z.pivot_table(index="policy", columns="rho", values="cell", aggfunc="first", sort=False).to_string())
    say("\npairwise gain differences:")
    say(dd.round(4).to_string(index=False))
    dump(cache, "p2boot")


# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #
def parse_v1(path):
    txt = open(path, encoding="utf-8").read().splitlines()
    p1, cold, boot, p2 = [], [], [], []
    num = r"(NaN|[-+]?[\d,]*\.?\d+)"
    rx = re.compile(r"^\s*C_cap\s+(train=\S+(?: remote)?)\s+test 2022-2\s+(M\d)" + (r"\s+" + num) * 6 + r"\s*$")
    rc = re.compile(r"^\s*C_cap\s+(train=\S+(?: remote)?)\s+test 2022-2\s+(M\d)" + (r"\s+" + num) * 8 + r"\s*$")
    rb = re.compile(r"^\s*(M\d)-(M\d): dRMSE ([+-][\d.]+) 95% CI \[([+-][\d.]+),([+-][\d.]+)\]\s+"
                    r"dAUROC ([+-][\d.]+) 95% CI \[([+-][\d.]+),([+-][\d.]+)\]")
    tv = lambda s: "core" if s.startswith("train=2018") else "remote"
    f = lambda s: float(s.replace(",", "")) if s != "NaN" else np.nan
    cur_train, in_p2, rho = None, False, None
    for ln in txt:
        m = rx.match(ln)
        if m:
            g = m.groups()
            p1.append(dict(train=tv(g[0]), model=g[1], rmse=f(g[4]), spearman=f(g[5]),
                           auroc=f(g[6]), auprc=f(g[7])))
            continue
        m = rc.match(ln)
        if m:
            g = m.groups()
            cold.append(dict(train=tv(g[0]), model=g[1], cold_ex_rmse=f(g[3]), cold_ex_spearman=f(g[4]),
                             cold_ex_auroc=f(g[5]), cold_user_rmse=f(g[7]), cold_user_spearman=f(g[8])))
            continue
        if ln.startswith("train=2018-1..2019-2   (") or ln.startswith("train=+2020/2021 remote   ("):
            cur_train = tv(ln)
        m = rb.match(ln)
        if m and cur_train:
            g = m.groups()
            boot.append(dict(train=cur_train, pair=f"{g[0]}-{g[1]}", dRMSE=f(g[2]), rmse_lo=f(g[3]),
                             rmse_hi=f(g[4]), dAUROC=f(g[5]), auc_lo=f(g[6]), auc_hi=f(g[7])))
        if ln.startswith("--- service time = C_cap"):
            in_p2 = True
            continue
        if ln.startswith("--- service time = C ---"):
            in_p2 = False
        if in_p2:
            tk = ln.split()
            if len(tk) == 15 and re.match(r"^[\d.]+$", tk[0]):
                rho, tk = float(tk[0]), tk[1:]
            if len(tk) == 14 and rho is not None and not re.match(r"^[\d.,]+$", tk[0]):
                v = [f(x) for x in tk[1:]]
                # k rho_busy n w_mean w_mean_sd p95 p99 w_dl p99_dl w_exam slowdown max_heavy gain
                p2.append(dict(rho_target=rho, policy=tk[0], k=v[0], rho_busy=v[1], w_mean=v[3], p99=v[6],
                               w_dl=v[7], p99_dl=v[8], gain=v[12]))
    return pd.DataFrame(p1), pd.DataFrame(cold), pd.DataFrame(boot), pd.DataFrame(p2)


def _csvs(cache, prefix):
    fs = sorted(n for n in os.listdir(cache) if n.startswith(prefix) and n.endswith(".csv"))
    return pd.concat([pd.read_csv(os.path.join(cache, n)) for n in fs], ignore_index=True) if fs else None


def summary_p1(cache, v1p1, v1cold, v1boot):
    head("SUMMARY 1. P1 PREDICTABILITY on test 2022-2 (n = 40,844), mean over 3 seeds")
    say("A retrospective check (cross-semester fits); these predictions never enter the simulation.")
    say("Heavy = TRUE C_cap above the train(2018-1..2019-2) p95 = 1.559 s.  AUROC scores the LightGBM")
    say("classifier's heavy probability.  CI = 2.5/97.5% of 2,000 user-block bootstrap resamples")
    say("(test users drawn with replacement, statistic = 3-seed mean).  'nocoend' = test rows outside")
    say("co-ending groups.  v1_published = v1's out_service.txt (seed 3, leaky features); v1_rerun =")
    say("v1's feature construction in this pipeline.  ires0 is the primary configuration.")
    res = _csvs(cache, "p1_")
    g = res.groupby(["train", "model", "config"], sort=False).mean(numeric_only=True).reset_index()
    sd = res[res.model != "M0"].groupby(["train", "model", "config"], sort=False)["auroc"].std().max()
    say(f"(largest seed-to-seed std of AUROC in any cell: {sd:.4f})")
    cfgs = [c for c in P1_CONFIGS if c in set(g.config)]
    ba = _csvs(cache, "bootauc_")
    if ba is not None:
        for col, lo, hi, what in (("auroc", "lo", "hi", "all test rows"),
                                  ("auroc_nocoend", "lo_nocoend", "hi_nocoend", "rows outside co-ending groups")):
            say(f"\nheavy-vs-not AUROC [95% user-block CI], {what}:")
            ba["cell"] = [f"{a:.4f} [{l:.4f},{h:.4f}]" for a, l, h in zip(ba[col], ba[lo], ba[hi])]
            pv = ba.pivot_table(index=["train", "model"], columns="config", values="cell", aggfunc="first",
                                sort=False)
            say(pv[[c for c in cfgs if c in pv.columns]].to_string())
        say(f"(n test rows {int(ba.n.iloc[0]):,}, outside co-ending groups {int(ba.n_nocoend.iloc[0]):,}, "
            f"users {int(ba.n_users.iloc[0]):,})")

    def piv(col):
        pv = g.pivot_table(index=["train", "model"], columns="config", values=col, sort=False)
        pv = pv[cfgs]
        pv.columns = ["v1_rerun" if c == "v1" else c for c in pv.columns]
        return pv

    for metric in ("auroc", "auprc", "rmse", "spearman"):
        pv = piv(metric)
        pv.insert(0, "v1_published", v1p1.set_index(["train", "model"])[metric].reindex(pv.index).values)
        say(f"\n{metric}, all test rows:")
        say(pv.round(4).to_string())
    for tag in ("nocoend", "cold_ex", "cold_user"):
        nn = g.groupby("config")[f"{tag}_n"].first().reindex(cfgs).astype(int).to_dict()
        say(f"\n{tag}: rows per config {nn}" +
            (" (v1: <5 prior rows; v2: <5 available results)" if tag.startswith("cold") else ""))
        for metric in ("rmse", "spearman", "auroc", "auprc"):
            col = f"{tag}_{metric}"
            if col not in g.columns or g[col].isna().all():
                continue
            pv = piv(col)
            if col in v1cold.columns:
                pv.insert(0, "v1_published", v1cold.set_index(["train", "model"])[col].reindex(pv.index).values)
            say(f"  {tag} {metric}:")
            say(pv.round(4).to_string())
    if "clock0" in cfgs:
        say("\njitter effect on P1 (ires0 = jittered clock minus clock0 = whole-second clock; 3-seed means):")
        j = g[g.config.isin([PRIMARY, "clock0"])].pivot_table(index=["train", "model"], columns="config",
                                                                values=["auroc", "auprc"], sort=False)
        jt = pd.DataFrame({"auroc_ires0": j[("auroc", PRIMARY)], "auroc_clock0": j[("auroc", "clock0")],
                           "auprc_ires0": j[("auprc", PRIMARY)], "auprc_clock0": j[("auprc", "clock0")]})
        jt["d_auroc"] = jt.auroc_ires0 - jt.auroc_clock0
        jt["d_auprc"] = jt.auprc_ires0 - jt.auprc_clock0
        if ba is not None:
            for c in (PRIMARY, "clock0"):
                q = ba[ba.config == c].set_index(["train", "model"])
                jt[f"ci_{c}"] = [f"[{q.lo.get(i, np.nan):.4f},{q.hi.get(i, np.nan):.4f}]" for i in jt.index]
        say(jt.round(4).to_string())
        jt.reset_index().to_csv(os.path.join(cache, "jitter_p1.csv"), index=False)
    b = _csvs(cache, "boot_")
    if b is not None:
        head("SUMMARY 2. paired user-block bootstrap, 2,000 resamples, test 2022-2 "
             "(v1 published: 400 resamples, seed 3 only)")
        b["o"] = b.config.map({c: i for i, c in enumerate(P1_CONFIGS)})
        b = b.sort_values(["o", "train"], kind="stable").drop(columns="o")
        say(pd.concat([v1boot.assign(config="v1_published"), b])[
            ["config", "train", "pair", "dRMSE", "rmse_lo", "rmse_hi", "dAUROC", "auc_lo", "auc_hi"]
        ].round(4).to_string(index=False))


def p2_frame(cache):
    sim = _csvs(cache, "p2_")
    if sim is None:
        return None
    key = ["config", "variant", "rep", "rho_target"]
    pure = sim[sim.setting == "pure"]
    F = pure[pure.policy == "FCFS"].set_index(key)
    R = pure[pure.policy == "SJF-ref"].set_index(key)
    s2 = sim.set_index(key)
    for m in ("w_mean", "w_p99", "w_p99_dl"):
        f_, r_ = F[m].reindex(s2.index).values, R[m].reindex(s2.index).values
        s2[f"den_{m}"] = f_ - r_
        s2[f"gain_{m}"] = (f_ - s2[m].values) / (f_ - r_)
    return s2.reset_index()


P2_AGG = dict(k=("k", "mean"), rho_busy=("rho_busy", "mean"), rho_mean=("rho_mean", "mean"),
              n=("n_jobs", "mean"), reps=("rep", "nunique"), w_mean=("w_mean", "mean"),
              p95=("w_p95", "mean"), p99=("w_p99", "mean"), w_dl=("w_mean_dl", "mean"),
              p99_dl=("w_p99_dl", "mean"), w_exam=("w_mean_exam", "mean"), p99_exam=("w_p99_exam", "mean"),
              mean_heavy=("mean_heavy", "mean"), p95_heavy=("p95_heavy", "mean"),
              p99_heavy=("p99_heavy", "mean"), max_heavy=("max_heavy", "mean"),
              gain_mean=("gain_w_mean", "mean"), gain_p99=("gain_w_p99", "mean"),
              gain_p99_dl=("gain_w_p99_dl", "mean"), max_excess=("max_excess", "max"))
RANK_POL = ["FCFS", "SPJF-M1", "SPJF-M4", "SPJF-M5", "GUARD-M4-B30", "GUARD-M4-B120", "GUARD-M4-B600"]


def _agg(s2):
    return s2.groupby(["setting", "trace", "rho_target", "policy"], sort=False).agg(**P2_AGG)


def _ci(g, l, h):
    return f"{g:.3f} [{l:.3f},{h:.3f}]"


def _gain_cells(gain, trace, reps, rho):
    """policy -> (p99_dl cell, mean cell) with CIs, and the unstable flags of the level."""
    z = gain[(gain.trace == trace) & (gain.reps == reps) & (gain.rho == rho)]
    cells, flags = {}, {}
    for mk, _ in BOOT_METRICS:
        q = z[z.metric == mk]
        for r in q.itertuples():
            cells.setdefault(r.policy, {})[mk] = _ci(r.gain, r.lo, r.hi)
        if len(q):
            flags[mk] = (bool(q.unstable.iloc[0]), float(q.fcfs_minus_sjf.iloc[0]))
    return cells, flags


def summary_p2(cache, v1p2):
    s2 = p2_frame(cache)
    gp, dp = os.path.join(cache, "p2gain.csv"), os.path.join(cache, "p2diff.csv")
    if s2 is None or not os.path.exists(gp):
        return
    gain, diff = pd.read_csv(gp), pd.read_csv(dp)
    cp = pd.read_csv(os.path.join(cache, "copies.csv")).set_index("trace")
    agg = _agg(s2)
    head("SUMMARY 3. P2 counterfactual shared judge pool, multi-server overlay, PRIMARY trace")
    c0 = int(cp.loc["primary", "copies"])
    say("The original platform had one Docker container per student and no shared queue; the traces")
    say("keep the real arrival times (I-res on the jittered clock: ts + u - C) and costs; the pool, queue")
    say(f"and order are ours.  Primary pool: {POOL60} ({int(cp.loc['primary', 'class_semesters'])} class-")
    say(f"semesters), {c0} overlay copies, each class-semester copy week-aligned by weekday and clock with")
    say("its own 0-11 whole-week jitter; one overlay per rep (seed 300 + rep); k per level from that")
    say("overlay's busiest-hour C_cap work.  Primary metric: deadline-window p99 wait (p99_dl: arrivals in")
    say("the 24 h before the assessment end, research_plan.md 6.5), then mean wait, overall p99 and the")
    say("heavy-job waits (heavy = TRUE C_cap > 1.559 s, a reporting label only).  gain = (W_FCFS - W_policy)")
    say("/ (W_FCFS - W_SJF-ref) per overlay, then averaged; SJF-ref = non-preemptive SJF on the TRUE C_cap, a")
    say("reference, not a bound.  [CI] = 95% paired week-block bootstrap (2,000 resamples of whole weeks of")
    say("the overlay timeline, the same draws for every policy, level and overlay).  Overall-p99 gains are")
    say("point values (no CI).  Predictions: forward (rolling-origin) LightGBM regression per target semester.")
    cols = ["k", "rho_busy", "p99_dl", "gain_p99_dl [CI]", "w_mean", "gain_mean [CI]", "p99", "gain_p99",
            "mean_heavy", "p99_heavy", "max_heavy", "p99_exam", "reps"]
    for rho in RHOS:
        a = agg.loc[("pure", "primary", rho)]
        cells, flags = _gain_cells(gain, "primary", "all", rho)
        a = a.assign(**{"gain_p99_dl [CI]": [cells.get(p, {}).get("p99dl", "") for p in a.index],
                        "gain_mean [CI]": [cells.get(p, {}).get("mean", "") for p in a.index]})
        say(f"\n--- 3a. PURE, primary, target rho {rho}; waits in s, mean over reps ---")
        say(a[cols].round(3).to_string())
        say("    unstable-gain flags (FCFS - SJF-ref < 0.1 s or < 5% of FCFS): " +
            ", ".join(f"{mk}: {'UNSTABLE' if f else 'stable'} (FCFS - SJF-ref = {dv:.4f} s)"
                      for mk, (f, dv) in flags.items()))
    z = diff[(diff.trace == "primary") & (diff.reps == "all")]
    say("\n--- 3b. PURE, primary: pairwise gain differences with 95% week-block CIs (a policy ranking is")
    say("    stated only where the CI excludes 0) ---")
    say(z[["rho", "metric", "pair", "diff", "lo", "hi", "verdict", "unstable"]].round(4).to_string(index=False))
    say("\n--- 3c. END-TO-END, primary: predictive policies enqueue after their measured feature + inference")
    say("    latency (drawn per job from the streaming measurements), wait counted from the original arrival;")
    say("    gains against the pure FCFS and SJF-ref of the same overlay; no bound ---")
    rows = []
    for (tr, rho, pol), z_ in agg.loc["e2e"].iterrows():
        p0 = agg.loc[("pure", tr, rho, pol)]
        rows.append(dict(trace=tr, rho=rho, policy=pol, k=z_.k, p99_dl_pure=p0.p99_dl, p99_dl_e2e=z_.p99_dl,
                         gain_p99_dl_pure=p0.gain_p99_dl, gain_p99_dl_e2e=z_.gain_p99_dl, w_mean_pure=p0.w_mean,
                         w_mean_e2e=z_.w_mean, gain_mean_pure=p0.gain_mean, gain_mean_e2e=z_.gain_mean,
                         max_heavy_e2e=z_.max_heavy, max_excess_pure=p0.max_excess, max_excess_e2e=z_.max_excess))
    say(pd.DataFrame(rows).round(4).to_string(index=False))
    say("\n--- 3d. overlay copies, k and achieved busy-hour rho per overlay, every trace ---")
    fc = s2[(s2.setting == "pure") & (s2.policy == "FCFS")]
    u = fc.pivot_table(index=["trace", "rep"], columns="rho_target", values=["k", "rho_busy"], sort=False)
    say(u.round(3).to_string())
    say("copies per trace: " + ", ".join(f"{t} {int(r.copies)} x {int(r.class_semesters)} class-semesters "
                                         f"({int(r.jobs_per_overlay):,} jobs)" for t, r in cp.iterrows()))
    bh = pd.read_csv(os.path.join(cache, "busy_hour.csv"))
    say("\nbusiest hour of every simulated overlay (sets k): C_cap work W_s, its shares by semester, from jobs at")
    say("the 60 s cap and from co-ending group members (sbatch: the collapsed group jobs):")
    say(bh.to_string(index=False))
    say("\n--- 3e. k > 1, not asserted: max over overlays of max_i (W_guard[i] - W_FCFS[i]), pure ---")
    gx = s2[s2.policy.str.contains("GUARD|\\+G") & (s2.setting == "pure")]
    mx = gx.groupby(["trace", "rho_target", "policy"]).agg(max_excess=("max_excess", "max")).reset_index()
    mx["B+60"] = [float(re.search(r"(?:B|G)(\d+)$", p).group(1)) + L_CAP for p in mx.policy]
    say(mx.pivot_table(index=["trace", "policy"], columns="rho_target", values="max_excess").round(1).to_string())
    say(f"cells (trace, level, policy) above B+60: {int((mx.max_excess > mx['B+60']).sum())} of {len(mx)}")
    say("\n--- 3f. v1 published vs v2.  DIFFERENT POOLS AND LOADS: v1 = 77 class-semesters (2018-1..2022-2)")
    say("    x 3 copies, out-of-fold predictions, leaky v1 features, arrival = whole-second ts; v2 primary =")
    say(f"    {int(cp.loc['primary', 'class_semesters'])} class-semesters of the 60 s semesters x {c0} copies; "
        f"v2 pool19 = {int(cp.loc['pool19', 'class_semesters']) if 'pool19' in cp.index else 0} class-semesters "
        f"incl. 2019-1 x {int(cp.loc['pool19', 'copies']) if 'pool19' in cp.index else 0} copies;")
    say("    both v2 on I-res jittered arrivals, forward predictions, availability-correct features.  v1's")
    say("    p99_dl gain is a ratio of its rep means (v1 published rep means only); v2 gains are means of")
    say("    per-overlay gains.  k and achieved busy-hour rho differ by column ---")
    cmp_rows = []
    for rho in RHOS:
        for pv1, pv2 in (("FCFS", "FCFS"), ("SPJF-oracle", "SJF-ref"), ("SPJF-M1", "SPJF-M1"),
                         ("SPJF-M4", "SPJF-M4"), (None, "SPJF-M4-v1feat"), (None, "GUARD-M4-B120")):
            r = dict(rho=rho, policy=pv2)
            q = v1p2[(v1p2.rho_target == rho) & (v1p2.policy == pv1)] if pv1 else v1p2.iloc[:0]
            f1 = v1p2[(v1p2.rho_target == rho) & (v1p2.policy == "FCFS")]
            o1 = v1p2[(v1p2.rho_target == rho) & (v1p2.policy == "SPJF-oracle")]
            r["v1_k"] = q.k.iloc[0] if len(q) else np.nan
            r["v1_rho_busy"] = q.rho_busy.iloc[0] if len(q) else np.nan
            r["v1_p99_dl"] = q.p99_dl.iloc[0] if len(q) else np.nan
            r["v1_gain_p99_dl"] = ((f1.p99_dl.iloc[0] - q.p99_dl.iloc[0]) / (f1.p99_dl.iloc[0] - o1.p99_dl.iloc[0])
                                   if len(q) and len(f1) and len(o1) else np.nan)
            r["v1_gain_mean"] = q.gain.iloc[0] if len(q) else np.nan
            for tr in ("primary", "pool19"):
                if ("pure", tr, rho, pv2) in agg.index:
                    z_ = agg.loc[("pure", tr, rho, pv2)]
                    r[f"{tr}_k"], r[f"{tr}_rho_busy"] = z_.k, z_.rho_busy
                    r[f"{tr}_p99_dl"], r[f"{tr}_gain_p99_dl"], r[f"{tr}_gain_mean"] = z_.p99_dl, z_.gain_p99_dl, z_.gain_mean
            cmp_rows.append(r)
    say(pd.DataFrame(cmp_rows).round(3).to_string(index=False))


def summary_sens(cache):
    gp, dp = os.path.join(cache, "p2gain.csv"), os.path.join(cache, "p2diff.csv")
    if not os.path.exists(gp):
        return
    gain, diff = pd.read_csv(gp), pd.read_csv(dp)
    s2 = p2_frame(cache)
    s2 = s2[s2.setting == "pure"]
    sens = [t for t in TRACES if t != "primary" and t in set(gain.trace)]
    head("SUMMARY 5. P2 SENSITIVITIES (pure scheduling), gains with week-block CIs and ranking changes")
    say("pool19: 2019-1 added to the pool (the previous round's pool).  S-batch: each co-ending group one job")
    say("(arrival = min(ts' - C), service = max C_cap, prediction of the earliest-arriving member).  S-drop:")
    say("co-ending groups removed.  isub0: the old reading (arrival = ts') with its own features and forward")
    say("models.  Each trace has its own copy count (copies.csv) and k; compared with the primary on its reps")
    say("0-2 (the same overlay seeds) and with the primary's 5 reps.  Ranking changes: pairwise verdicts")
    say("(CI of the gain difference excludes 0) that differ from the primary's.")
    if "dedup" not in set(gain.trace):
        say("dedup: not run (0 repeated submissions in the primary pool after the C == 0 drop; stage pool).")
    for tr in sens:
        g = gain[(gain.trace == tr) & (gain.reps == "all")]
        reps = int(g.n_reps.iloc[0])
        for rho in RHOS:
            c_s, f_s = _gain_cells(gain, tr, "all", rho)
            c_p, f_p = _gain_cells(gain, "primary", "reps0-2", rho)
            q = g[(g.rho == rho) & (g.metric == "p99dl")].set_index("policy")
            t = pd.DataFrame({"k": q.k, "rho_busy": q.rho_busy, "p99_dl": q.wait,
                              f"{tr} gain_p99_dl": [c_s[p]["p99dl"] for p in q.index],
                              "primary(0-2) gain_p99_dl": [c_p.get(p, {}).get("p99dl", "") for p in q.index],
                              f"{tr} gain_mean": [c_s[p]["mean"] for p in q.index],
                              "primary(0-2) gain_mean": [c_p.get(p, {}).get("mean", "") for p in q.index]})
            say(f"\n{tr} ({reps} reps), target rho {rho}:")
            say(t.round(3).to_string())
            say("    unstable flags " + tr + ": " + ", ".join(f"{m} {'UNSTABLE' if f else 'stable'} ({dv:.4f} s)"
                                                           for m, (f, dv) in f_s.items()))
    say("\nranking changes (pairwise verdicts; primary on reps 0-2 and on all 5 reps):")
    rows = []
    for tr in sens:
        for rho in RHOS:
            for mk, col in BOOT_METRICS:
                ds = diff[(diff.trace == tr) & (diff.reps == "all") & (diff.rho == rho) & (diff.metric == mk)]
                for r in ds.itertuples():
                    p3 = diff[(diff.trace == "primary") & (diff.reps == "reps0-2") & (diff.rho == rho) &
                              (diff.metric == mk) & (diff.pair == r.pair)]
                    p5 = diff[(diff.trace == "primary") & (diff.reps == "all") & (diff.rho == rho) &
                              (diff.metric == mk) & (diff.pair == r.pair)]
                    rows.append(dict(sensitivity=tr, rho=rho, metric=mk, pair=r.pair, sens=_ci(r.diff, r.lo, r.hi),
                                     sens_verdict=r.verdict,
                                     primary_0_2=p3.verdict.iloc[0] if len(p3) else "",
                                     primary_all=p5.verdict.iloc[0] if len(p5) else "",
                                     changed=bool(len(p5) and p5.verdict.iloc[0] != r.verdict)))
                a = s2[(s2.trace == "primary") & s2.rep.isin([0, 1, 2]) & (s2.rho_target == rho)].groupby("policy")[col].mean()
                b = s2[(s2.trace == tr) & (s2.rho_target == rho)].groupby("policy")[col].mean()
                rk = [p for p in RANK_POL if p in a.index and p in b.index]
                tau = kendalltau(a.loc[rk].values, b.loc[rk].values).statistic
                rows.append(dict(sensitivity=tr, rho=rho, metric=mk, pair="(point ranking of " + ", ".join(rk) + ")",
                                 sens=" < ".join(b.loc[rk].sort_values(kind="stable").index),
                                 sens_verdict=f"kendall tau vs primary(0-2) {tau:.3f}",
                                 primary_0_2=" < ".join(a.loc[rk].sort_values(kind="stable").index),
                                 primary_all="", changed=False))
    rt = pd.DataFrame(rows)
    rt.to_csv(os.path.join(cache, "p2_sens_ranking.csv"), index=False)
    say(rt.to_string(index=False))


def summary_guardk1(cache):
    res, pol = _csvs(cache, "guardk1_"), _csvs(cache, "guardk1pol_")
    if res is None:
        return
    head("SUMMARY 4. SINGLE-SERVER CONFIGURATION (k = 1): PROPOSITION 3 PER JOB, PURE SCHEDULING")
    say(f"Primary pool {POOL60}.  Class-semester copies drawn in a random order from the pool listed 8 times,")
    say("each with its own whole-week shift, added while the busiest-hour rho at k = 1 stays <= 0.82; the")
    say("state in [0.78, 0.82] closest to 0.80 is kept.  Asserted for every job: W_guard[i] <= W_FCFS[i] + B + 60")
    say("(B = 30/120/600), forward predictors M1/M3/M4/M5 and adversarial reversed/random/top1short.")
    bz = _csvs(cache, "guardk1busy_")
    if bz is not None:
        say(bz.to_string(index=False))
    cols = ["config", "rep", "n_cs", "n_jobs", "rho_busy", "predictor", "fcfs_mean", "unguarded_mean",
            "unguarded_max_excess"] + [f"B{b:g}_{x}" for b in GUARD_B for x in ("mean", "max_excess")]
    say(res[cols].round(3).to_string(index=False))
    say(f"jobs checked: {int(sum(res[f'B{b:g}_jobs_checked'].sum() for b in GUARD_B)):,} (job x predictor x B); "
        f"violations 0 (asserted)")
    if pol is not None:
        key = ["config", "rep"]
        F = pol[pol.policy == "FCFS"].set_index(key)
        R = pol[pol.policy == "SJF-ref"].set_index(key)
        p2 = pol.set_index(key)
        for m in ("w_mean", "w_p99_dl"):
            f_, r_ = F[m].reindex(p2.index).values, R[m].reindex(p2.index).values
            p2[f"gain_{m}"] = (f_ - p2[m].values) / (f_ - r_)
        p2 = p2.reset_index()
        p2.to_csv(os.path.join(cache, "guardk1_gains.csv"), index=False)
        say("\nwaits (s) and gains at k = 1, mean over reps (gain per rep, then averaged):")
        a = p2.groupby(["config", "policy"], sort=False).agg(
            reps=("rep", "nunique"), n=("n_jobs", "mean"), rho_busy=("rho_busy", "mean"),
            p99_dl=("w_p99_dl", "mean"), gain_p99_dl=("gain_w_p99_dl", "mean"),
            gain_p99_dl_min=("gain_w_p99_dl", "min"), gain_p99_dl_max=("gain_w_p99_dl", "max"),
            w_mean=("w_mean", "mean"), gain_mean=("gain_w_mean", "mean"), gain_mean_min=("gain_w_mean", "min"),
            gain_mean_max=("gain_w_mean", "max"), p99=("w_p99", "mean"), mean_heavy=("mean_heavy", "mean"),
            p99_heavy=("p99_heavy", "mean"), max_heavy=("max_heavy", "mean"))
        say(a.round(3).to_string())


def summary_head(cache):
    head("CodeBench service pre-check v2 (evidence/codebench_service_v2/service_precheck_v2.py)")
    say(f"script sha256 {SCRIPT_SHA}; every stage log below carries this hash (checked before writing).")
    say("Primary configuration ires0: the SUBMITION header ts is the result time; on the jittered clock")
    say("ts' = ts + u (u ~ U[0,1) per record, keyed hash of its id) arrival = ts' - C and done = ts'; results")
    say("visible to a later submission i iff done + 0 <= arrival[i]; TEST blocks never enter the simulation,")
    say("their existence is visible from ts' and their outcome from ts' + 60 s.  clock0 = ires0 on the raw")
    say("whole-second ts (P1 and forward sensitivity).  Every headline table is ires0; I-sub (arrival = ts',")
    say("done = ts' + C) is a secondary table.  Simulation = counterfactual shared judge pool on the 60 s-limit")
    say(f"semesters {POOL60} (pool19 = 2019-1 added, a sensitivity).  Forward predictions only.  Sealed")
    say("semesters 2023-1, 2023-2, 2024-1 were not opened.  All numbers are DEV-period.")
    say("\nDefinitions and reading notes:")
    say("  'last' in ue_last_log / ue_last_err / prev_ev_err = the latest-ARRIVING record whose result is visible")
    say("  (not the most recently available one); the 120-result windows are ordered by availability.")
    say("  heavy = TRUE C_cap > 1.559 s (p95 of 2018-1..2019-2): a reporting label only; the forward models of")
    say("  2019-1 / 2019-2 use cut-offs refit on their own training rows inside the features.")
    say("  Last round SPJF-M4-d600 (ires600 model, lower AUROC) beat SPJF-M4 on mean-wait gain at every level,")
    say("  so small mean-gain differences between predictors are not evidence of predictor value.")
    ft = os.path.join(cache, f"fwdtab_{PRIMARY}.csv")
    if os.path.exists(ft):
        drops = {c: int(pd.read_csv(os.path.join(cache, f"fwdtab_{c}.csv")).dropped_not_yet_available.sum())
                 for c in FORWARD_CONFIGS + ["v1"] if os.path.exists(os.path.join(cache, f"fwdtab_{c}.csv"))}
        say(f"  forward drop rule (training rows with done + delta >= the target's first arrival): rows dropped "
            f"per config {drops}; it binds on {sum(drops.values())} rows.")
    p = os.path.join(cache, "coend_groups.csv")
    if os.path.exists(p):
        cg = pd.read_csv(p)
        say("\nC == 0 blocks dropped from the simulated traces (2020-2022; features/labels keep them): " +
            ", ".join(f"{r.semester} {r.zero_dropped}" for r in cg.itertuples() if r.semester != "ALL") +
            f"; total {int(cg[cg.semester == 'ALL'].zero_dropped.iloc[0]):,}")
        say("co-ending groups per semester (same user, same raw header second, >= 2 SUBMITION blocks):")
        say(cg.to_string(index=False))
    p = os.path.join(cache, "leak_v1.csv")
    if os.path.exists(p):
        lk = pd.read_csv(p)
        l2 = pd.read_csv(os.path.join(cache, "leak.csv"))
        say("\nleak test (3,000 random DEV submissions, from-scratch recomputation of all 34 history and")
        say("relational features per config): v2 sweep rows failing " +
            ", ".join(f"{r.config} {r.rows_failing}" for r in l2.itertuples()) + " (asserted 0).")
        say("The v1 construction (rows j < i) against each config's rule (v1 runs on the whole-second I-sub")
        say("clock, so its two time-since features differ by construction; result_features excludes them):")
        say(lk[["reference_rule", "rows", "v1_rows_failing", "share", "v1_fail_result_features",
                "share_result"]].to_string(index=False))
    p = os.path.join(cache, "frac_channel.csv")
    if os.path.exists(p):
        say("\nfractional-arrival channel, test 2022-2 rows whose previous user record is a TEST < 30 s earlier:")
        say(pd.read_csv(p).to_string(index=False))
    if os.path.exists(ft):
        f = pd.read_csv(ft)
        say(f"\nthe 2019 slow period (arrivals 2019-06-01..2019-09-30) in the forward models ({PRIMARY}):")
        say(f[["target", "train_sems", "n_train", "slow_train", "n_target", "slow_target",
               "cutoffs (heavy / terciles)", "M4_auroc"]].to_string(index=False))
        sim_t = [t for t in f.target if t in POOL60]
        say(f"=> among the primary-pool target semesters the slow period is inside the training data of "
            f"{[t for t, n in zip(f.target, f.slow_train) if n > 0 and t in sim_t]}.")


def summary_fwd(cache):
    fs = {c: os.path.join(cache, f"fwdtab_{c}.csv") for c in FORWARD_CONFIGS + ["v1"]}
    fs = {c: pd.read_csv(p) for c, p in fs.items() if os.path.exists(p)}
    if PRIMARY not in fs:
        return
    head("SUMMARY 2b. FORWARD MODELS (the simulation input): per-target heavy AUROC / AUPRC of the regression output")
    rows = []
    for c, f in fs.items():
        for m in FORWARD_MODELS[c]:
            for r in f.itertuples():
                rows.append(dict(config=c, model=m, target=r.target, auroc=getattr(r, f"{m}_auroc"),
                                 auprc=getattr(r, f"{m}_auprc")))
    t = pd.DataFrame(rows)
    for met in ("auroc", "auprc"):
        say(f"\n{met} per target semester (rows config|model):")
        say(t.pivot_table(index=["config", "model"], columns="target", values=met, sort=False).round(4).to_string())
    if "clock0" in fs:
        say("\njitter effect on the forward models (ires0 jittered minus clock0 whole-second), per target:")
        a = t[t.config == PRIMARY].set_index(["model", "target"])
        b = t[t.config == "clock0"].set_index(["model", "target"])
        j = a.join(b, lsuffix="_ires0", rsuffix="_clock0", how="inner")
        j["d_auroc"] = j.auroc_ires0 - j.auroc_clock0
        j["d_auprc"] = j.auprc_ires0 - j.auprc_clock0
        say(j[["auroc_ires0", "auroc_clock0", "d_auroc", "auprc_ires0", "auprc_clock0", "d_auprc"]].round(4).to_string())
        j.reset_index().to_csv(os.path.join(cache, "jitter_forward.csv"), index=False)


def stage_report(cache, out_path):
    tdir = os.path.join(cache, "txt")
    names = sorted(n[:-4] for n in os.listdir(tdir) if n.endswith(".txt"))
    bad = []
    for nm in names:
        with open(os.path.join(tdir, nm + ".txt"), encoding="utf-8") as f:
            first = f.readline().strip()
        if first != f"script_sha256 {SCRIPT_SHA}":
            bad.append(f"{nm}: {first[:80]}")
    need = ["selftest", "load", "features", "leak", "p1_", "boot_", "forward", "latency", "p2_0pool",
            "p2_primary", "p2boot", "guardk1"]
    missing = [p for p in need if not any(n.startswith(p) for n in names)]
    if bad or missing:
        raise SystemExit(f"report refused: script sha256 {SCRIPT_SHA}\n  stage logs with another hash: {bad}\n"
                         f"  missing stages: {missing}")
    pick = lambda pre: [n for n in names if n.startswith(pre)]
    order = ["selftest", "load"] + pick("features") + ["leak"] + pick("p1_") + pick("boot_") + \
        pick("forward") + ["latency"] + pick("p2_") + ["p2boot"] + pick("guardk1")
    blocks = [open(os.path.join(tdir, nm + ".txt"), encoding="utf-8").read().rstrip("\n")
              for nm in order if os.path.exists(os.path.join(tdir, nm + ".txt"))]
    _OUT.clear()
    v1p1, v1cold, v1boot, v1p2 = parse_v1(os.path.join(V1DIR, "out_service.txt"))
    summary_head(cache)
    summary_p1(cache, v1p1, v1cold, v1boot)
    summary_fwd(cache)
    summary_p2(cache, v1p2)
    summary_guardk1(cache)
    summary_sens(cache)
    head(f"STAGE LOGS (verbatim, in run order; {len(blocks)} logs, all with sha256 {SCRIPT_SHA})")
    txt = "\n".join(_OUT) + "\n" + "\n".join(blocks) + "\n"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(txt)
    print(f"wrote {out_path} ({len(txt.splitlines())} lines)")


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True)
    ap.add_argument("--configs", default="")
    ap.add_argument("--reps", default="")
    ap.add_argument("--variant", default="base", choices=VARIANTS)
    ap.add_argument("--traces", default="", help="p2boot: subset of " + ",".join(TRACES))
    ap.add_argument("--workers", type=int, default=N_WORKERS, help="p2: worker processes")
    ap.add_argument("--train", default="", help="subset of the training variants core,remote (p1)")
    ap.add_argument("--cache", default=os.path.join(tempfile.gettempdir(), "codebench_service_v2_cache"))
    ap.add_argument("--out", default=os.path.join(HERE, "out_service_v2.txt"))
    a = ap.parse_args()
    assert not set(DEV) & set(HOLDOUT)
    os.makedirs(a.cache, exist_ok=True)
    pd.set_option("display.width", 250, "display.max_columns", 80, "display.max_rows", 500)
    stages = a.stage.split(",")
    if stages == ["report"]:
        stage_report(a.cache, a.out)
        return
    if stages == ["selftest"]:
        stage_selftest(a.cache)
        print(f"done in {(time.time()-T0)/60:.1f} min")
        return
    if stages == ["p2boot"]:
        stage_p2boot(a.cache, [t for t in a.traces.split(",") if t] or list(TRACES))
        print(f"done in {(time.time()-T0)/60:.1f} min")
        return
    ev = load_events(a.cache)
    D = prep(ev)
    S = static_sub(ev, D)
    cfgs = [c for c in a.configs.split(",") if c]
    reps = [int(r) for r in a.reps.split(",")] if a.reps else None
    for st in stages:
        if st == "load":
            stage_load(ev, D, a.cache)
            dump(a.cache, "load")
        elif st == "features":
            stage_features(ev, D, cfgs or list(CONFIGS), a.cache)
            dump(a.cache, "features_" + "_".join(cfgs or ["all"]))
        elif st == "leak":
            stage_leak(ev, D, a.cache)
            dump(a.cache, "leak")
        elif st == "p1":
            stage_p1(ev, D, S, cfgs or P1_CONFIGS, a.cache, [v for v in a.train.split(",") if v] or None)
        elif st == "boot":
            stage_boot(ev, D, S, cfgs or list(BOOT_CONFIGS), a.cache)
        elif st == "forward":
            stage_forward(ev, D, S, cfgs or FORWARD_CONFIGS + ["v1"], a.cache)
            dump(a.cache, "forward_" + "_".join(cfgs or ["all"]))
        elif st == "latency":
            stage_latency(ev, D, S, a.cache)
        elif st == "pool":
            stage_pool(ev, D, S, a.cache)
        elif st == "p2":
            cfg = (cfgs or [PRIMARY])[0]
            tr = trace_of(cfg, a.variant)
            stage_p2(ev, D, S, cfg, reps if reps is not None else list(TRACES[tr][2]), a.cache,
                     a.variant, a.workers)
        elif st == "guardk1":
            stage_guardk1(ev, D, S, cfgs or [PRIMARY], reps if reps is not None else [0, 1, 2], a.cache)
        else:
            raise SystemExit(f"unknown stage {st} (selftest, report and p2boot run alone)")
    print(f"done in {(time.time()-T0)/60:.1f} min")


if __name__ == "__main__":
    main()
