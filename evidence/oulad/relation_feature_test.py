"""Does resource-resource relation information improve demand PREDICTION and the
resulting top-k protection decision?

OULAD development presentation 2013J ONLY.  Never reads 2014J.
Data loading, SHA-256 group split, catalog rule, base LightGBM feature set and
hyperparameters (train 14..140, early stop 141..160, frozen afterwards), the
Jaccard graph builder (window t-14..t-1, >=2 common learners, greedy degree cap 4),
swap_edges, the top-k decision evaluation (k = pin slots, and 2k), cost share m1,
shared-link tail m3, oracle O, and the paired block bootstrap over (course, day)
are taken UNCHANGED from precheck_lgbm.py / decision_test.py.

Models (identical hyperparameters and seeds, only the feature set differs):
  M0  base
  M1  base + Jaccard-neighbour features (window t-14..t-1 only)
  M2  base + the same features on the degree-preserving swapped graph
  M3  base + non-graph course+group+activity_type aggregates
  M4  base + M1 features + M3 features
"""
import hashlib
import json
import sys
import time

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

import lightgbm as lgb

T_START = time.time()

SEED = 20260918
DATA = r"<repo-root>\data"
MODULES = ["AAA", "BBB", "DDD", "EEE", "FFF", "GGG"]
PRES = "2013J"
ATYPES = {"resource", "oucontent", "page"}
W = 14                 # lookback window
DAY_LO, DAY_HI = 161, 200
DEG_CAP = 4
MIN_COMMON = 2

TRN_LO, TRN_HI = 14, 140
VAL_LO, VAL_HI = 141, 160

KPIN = {"AAA": 7, "BBB": 11, "DDD": 8, "EEE": 3, "FFF": 11, "GGG": 4}
LGB_SEEDS = [0, 1, 2]
NBOOT = 2000

np.random.seed(SEED)


def log(msg):
    print(f"[{time.time() - T_START:7.1f}s] {msg}", file=sys.stderr, flush=True)


def grp(sid, mod, pres):
    s = json.dumps([int(sid), mod, pres], separators=(",", ":")) + "|17"
    return int.from_bytes(hashlib.sha256(s.encode()).digest()[:8], "big") % 2


# ---------------------------------------------------------------- load
vle = pd.read_csv(f"{DATA}/vle.csv", usecols=["id_site", "code_module", "code_presentation", "activity_type"])
vle = vle[(vle.code_presentation == PRES) & (vle.code_module.isin(MODULES)) & (vle.activity_type.isin(ATYPES))]
site_ok = set(vle.id_site.astype(np.int64))
atype = dict(zip(vle.id_site.astype(np.int64), vle.activity_type))

parts = []
for ch in pd.read_csv(f"{DATA}/studentVle.csv",
                      usecols=["code_module", "code_presentation", "id_student", "id_site", "date", "sum_click"],
                      dtype={"code_module": "category", "code_presentation": "category",
                             "id_student": np.int64, "id_site": np.int64,
                             "date": np.int32, "sum_click": np.int32},
                      chunksize=2_000_000):
    ch = ch[(ch.code_presentation == PRES) & (ch.code_module.isin(MODULES)) & (ch.date <= DAY_HI)]
    ch = ch[ch.id_site.isin(site_ok)]
    if len(ch):
        parts.append(ch[["code_module", "id_student", "id_site", "date", "sum_click"]])
df = pd.concat(parts, ignore_index=True)
df["code_module"] = df.code_module.astype(str)
del parts

pairs = df[["id_student", "code_module"]].drop_duplicates()
gmap = {(int(s), m): grp(s, m, PRES) for s, m in zip(pairs.id_student, pairs.code_module)}
df["grp"] = [gmap[(s, m)] for s, m in zip(df.id_student, df.code_module)]
log(f"load rows={len(df)} students={df.id_student.nunique()} sites={df.id_site.nunique()}")

D0 = 0
NDAY = DAY_HI + 1
ATL = sorted(ATYPES)
ATCODE = {a: i for i, a in enumerate(ATL)}
NAT = len(ATL)

# ------------------------------------------------- per-course structures
# (identical to precheck_lgbm.py, except that the graph triples `tri` are built
#  over the FULL day range 0..199 so that graphs exist for every training day;
#  this cannot change any graph in 161..200 because the window filter is applied
#  per target day anyway.)
courses = {}
for mod, sub in df.groupby("code_module"):
    res = np.sort(sub.id_site.unique())
    ridx = {r: i for i, r in enumerate(res)}
    R = len(res)
    first = sub.groupby("id_site").date.min()
    first_arr = np.array([first[r] for r in res], dtype=np.int32)
    d = np.zeros((2, R, NDAY), dtype=np.float64)
    sw = sub[(sub.date >= D0) & (sub.date <= DAY_HI)]
    agg = sw.groupby(["grp", "id_site", "date"], observed=True).sum_click.sum()
    if len(agg):
        gi = agg.index.get_level_values(0).to_numpy()
        ri = np.array([ridx[x] for x in agg.index.get_level_values(1)])
        di = agg.index.get_level_values(2).to_numpy() - D0
        d[gi, ri, di] = agg.to_numpy()
    tri = {}
    dstu = np.zeros((2, R, NDAY + 2), dtype=np.int32)
    for g in (0, 1):
        s2 = sub[(sub.grp == g) & (sub.date >= TRN_LO - W) & (sub.date < DAY_HI)]
        s2 = s2[["id_student", "id_site", "date"]].drop_duplicates()
        s2 = s2.sort_values("date", kind="mergesort")
        stu = np.sort(s2.id_student.unique())
        sidx = {s: i for i, s in enumerate(stu)}
        tri[g] = (np.array([sidx[s] for s in s2.id_student], dtype=np.int32),
                  np.array([ridx[r] for r in s2.id_site], dtype=np.int32),
                  s2.date.to_numpy().astype(np.int32), len(stu))
        f2 = sub[(sub.grp == g) & (sub.date >= D0) & (sub.date < DAY_HI)]
        f2 = f2[["id_student", "id_site", "date"]].drop_duplicates()
        f2 = f2.sort_values(["id_site", "id_student", "date"], kind="mergesort")
        if len(f2):
            rv = np.array([ridx[r] for r in f2.id_site], dtype=np.int64)
            sv = f2.id_student.to_numpy()
            dv = f2.date.to_numpy().astype(np.int64)
            prev = np.full(len(dv), -10 ** 6, dtype=np.int64)
            same = np.zeros(len(dv), dtype=bool)
            same[1:] = (rv[1:] == rv[:-1]) & (sv[1:] == sv[:-1])
            prev[1:][same[1:]] = dv[:-1][same[1:]]
            lo = np.maximum(dv + 1, prev + W + 1)
            hi = dv + W
            lo = np.maximum(lo, TRN_LO)
            hi = np.minimum(hi, DAY_HI)
            ok = lo <= hi
            np.add.at(dstu[g], (rv[ok], lo[ok]), 1)
            np.add.at(dstu[g], (rv[ok], hi[ok] + 1), -1)
        dstu[g] = np.cumsum(dstu[g], axis=1)
    courses[mod] = dict(res=res, R=R, first=first_arr, d=d, tri=tri, dstu=dstu,
                        at=np.array([atype[r] for r in res]))
log("course structures built")


# ============================================================ graph builders
def build_graph(mod, g, t, cat, posmap):
    """Jaccard graph on window t-14..t-1, >=MIN_COMMON common learners, greedy
    degree cap 4 in order of descending weight.  Identical rule to precheck.py."""
    C = courses[mod]
    si, ri, di, nstu = C["tri"][g]
    lo = int(np.searchsorted(di, t - W, "left"))
    hi = int(np.searchsorted(di, t, "left"))
    if hi <= lo:
        return (np.zeros(0, np.int64), np.zeros(0, np.int64), np.zeros(0))
    ss = si[lo:hi]
    rr = posmap[ri[lo:hi]]          # every triple's resource has first < t, so it is in cat
    su, sinv = np.unique(ss, return_inverse=True)
    ncat = len(cat)
    A = np.zeros((len(su), ncat), dtype=np.float32)
    A[sinv, rr] = 1.0
    I = (A.T @ A).astype(np.float64)
    sz = np.diag(I).copy()
    with np.errstate(divide="ignore", invalid="ignore"):
        un = sz[:, None] + sz[None, :] - I
        J = np.where(un > 0, I / np.maximum(un, 1e-9), 0.0)
    iu, ju = np.triu_indices(ncat, 1)
    ok = (I[iu, ju] >= MIN_COMMON) & (J[iu, ju] > 0)
    iu, ju, wv = iu[ok], ju[ok], J[iu, ju][ok]
    if len(iu) == 0:
        return (np.zeros(0, np.int64), np.zeros(0, np.int64), np.zeros(0))
    order = np.lexsort((ju, iu, -wv))
    deg = np.zeros(ncat, dtype=np.int32)
    nfree = ncat
    E0, E1, WT = [], [], []
    for o in order:
        u, v = int(iu[o]), int(ju[o])
        if deg[u] < DEG_CAP and deg[v] < DEG_CAP:
            E0.append(u); E1.append(v); WT.append(float(wv[o]))
            deg[u] += 1
            deg[v] += 1
            if deg[u] == DEG_CAP:
                nfree -= 1
            if deg[v] == DEG_CAP:
                nfree -= 1
            if nfree < 2:
                break
    return (np.array(E0, np.int64), np.array(E1, np.int64), np.array(WT))


def swap_edges(E, rng, mult=10):
    """Degree-preserving double-edge swap, unchanged from precheck_lgbm.py."""
    if len(E) < 2:
        return list(E)
    ed = [list(e) for e in E]
    es = set(frozenset(e) for e in ed)
    m = len(ed)
    for _ in range(mult * m):
        i, j = int(rng.integers(m)), int(rng.integers(m))
        if i == j:
            continue
        a, b = ed[i]; c, dd = ed[j]
        if len({a, b, c, dd}) < 4:
            continue
        n1, n2 = frozenset((a, dd)), frozenset((c, b))
        if n1 in es or n2 in es:
            continue
        es.discard(frozenset((a, b))); es.discard(frozenset((c, dd)))
        es.add(n1); es.add(n2)
        ed[i] = [a, dd]; ed[j] = [c, b]
    return [tuple(e) for e in ed]


# ---------------------------------------------------------------- graph cache
# one graph per (course, group, target day) for EVERY day 14..200, training days
# included; the swapped graph keeps the weight attached to its list position.
GR = {}
t_graph = time.time()
_rng = np.random.default_rng(SEED)
for mod in sorted(courses):
    C = courses[mod]
    first = C["first"]
    for g in (0, 1):
        for t in range(TRN_LO, DAY_HI + 1):
            cat = np.flatnonzero(first < t)
            if len(cat) == 0:
                continue
            posmap = np.full(C["R"], -1, dtype=np.int64)
            posmap[cat] = np.arange(len(cat))
            eu, ev, ew = build_graph(mod, g, t, cat, posmap)
            Es = swap_edges(list(zip(eu.tolist(), ev.tolist())), _rng)
            if len(Es):
                su = np.array([e[0] for e in Es], dtype=np.int64)
                sv = np.array([e[1] for e in Es], dtype=np.int64)
            else:
                su = sv = np.zeros(0, dtype=np.int64)
            GR[(mod, g, t)] = (eu, ev, ew, su, sv)
    log(f"graphs done for {mod}")
GRAPH_SEC = time.time() - t_graph
log(f"graph cache: {len(GR)} graphs in {GRAPH_SEC:.1f}s")


# ============================================================ features
BASE = ([f"lag{k}" for k in range(1, W + 1)] +
        ["other_sum14", "n_students", "active_days", "days_since_last",
         "days_since_first", "activity_type", "t", "t_mod7", "group_total14"])
RELF = ["rel_ndeg", "rel_wmax", "rel_wsum", "rel_lag1", "rel_lag2", "rel_lag3",
        "rel_sum14", "rel_surp"]
TYPF = ["typ_lag1", "typ_lag2", "typ_lag3", "typ_sum14", "typ_surp"]


def nbr_block(n, eu, ev, ew, xs):
    """Neighbour aggregates on an undirected weighted graph.
    Weighted averages are NaN for isolated nodes (LightGBM missing value);
    count / max / sum are 0 there."""
    deg = np.zeros(n); wsum = np.zeros(n); wmax = np.zeros(n)
    out = np.empty((n, 3 + len(xs)), dtype=np.float32)
    if len(eu):
        np.add.at(deg, eu, 1.0); np.add.at(deg, ev, 1.0)
        np.add.at(wsum, eu, ew); np.add.at(wsum, ev, ew)
        np.maximum.at(wmax, eu, ew); np.maximum.at(wmax, ev, ew)
    out[:, 0] = deg; out[:, 1] = wmax; out[:, 2] = wsum
    has = wsum > 0
    for c, x in enumerate(xs):
        acc = np.zeros(n)
        if len(eu):
            np.add.at(acc, eu, ew * x[ev])
            np.add.at(acc, ev, ew * x[eu])
        out[:, 3 + c] = np.where(has, acc / np.maximum(wsum, 1e-12), np.nan)
    return out


blocks = []
Xb, Xr, Xs, Xt, Yp = [], [], [], [], []
cursor = 0
t_feat = time.time()
for mod in sorted(courses):
    C = courses[mod]
    d, first = C["d"], C["first"]
    atc = np.array([ATCODE[a] for a in C["at"]], dtype=np.int32)
    for g in (0, 1):
        for t in range(TRN_LO, DAY_HI + 1):
            cat = np.flatnonzero(first < t)
            if len(cat) == 0:
                continue
            n = len(cat)
            win = d[g][cat, t - W:t]                     # days t-14..t-1
            lags = win[:, ::-1]                          # column 0 = lag1
            other = d[1 - g][cat, t - W:t].sum(axis=1)
            pos = win > 0
            has = pos.any(axis=1)
            lastrel = (W - 1) - np.argmax(pos[:, ::-1], axis=1)
            dsl = np.where(has, W - lastrel, 999.0)
            # ---- base (unchanged from precheck_lgbm.py)
            feat = np.empty((n, len(BASE)), dtype=np.float32)
            feat[:, :W] = lags
            feat[:, W] = other
            feat[:, W + 1] = C["dstu"][g][cat, t]
            feat[:, W + 2] = pos.sum(axis=1)
            feat[:, W + 3] = dsl
            feat[:, W + 4] = t - first[cat]
            feat[:, W + 5] = atc[cat]
            feat[:, W + 6] = t
            feat[:, W + 7] = t % 7
            feat[:, W + 8] = win.sum()
            Xb.append(feat)
            # ---- node series used by both relation blocks
            x1, x2, x3 = lags[:, 0], lags[:, 1], lags[:, 2]
            xs14 = win.sum(axis=1)
            xsur = lags[:, 0] - lags[:, 1:].mean(axis=1)
            xs = [x1, x2, x3, xs14, xsur]
            eu, ev, ew, su, sv = GR[(mod, g, t)]
            Xr.append(nbr_block(n, eu, ev, ew, xs))
            Xs.append(nbr_block(n, su, sv, ew, xs))
            # ---- non-graph activity-type aggregates (control)
            tc = atc[cat]
            tf = np.empty((n, len(TYPF)), dtype=np.float32)
            tlag = np.zeros((NAT, W))
            for a in range(NAT):
                m = tc == a
                if m.any():
                    tlag[a] = lags[m].sum(axis=0)
            tsur = tlag[:, 0] - tlag[:, 1:].mean(axis=1)
            tf[:, 0] = tlag[tc, 0]
            tf[:, 1] = tlag[tc, 1]
            tf[:, 2] = tlag[tc, 2]
            tf[:, 3] = tlag[tc].sum(axis=1)
            tf[:, 4] = tsur[tc]
            Xt.append(tf)
            Yp.append(np.log1p(d[g][cat, t]).astype(np.float32))
            blocks.append((mod, g, t, cursor, n))
            cursor += n

XB = np.concatenate(Xb); XR = np.concatenate(Xr)
XS = np.concatenate(Xs); XT = np.concatenate(Xt)
Y = np.concatenate(Yp)
del Xb, Xr, Xs, Xt, Yp
TDAY = np.concatenate([np.full(L, t, dtype=np.int32) for (_, _, t, _, L) in blocks])
log(f"features built rows={len(Y)} in {time.time() - t_feat:.1f}s")

DFB = pd.DataFrame(XB, columns=BASE)
DFB["activity_type"] = DFB["activity_type"].astype(int).astype("category")
DFR = pd.DataFrame(XR, columns=RELF)
DFS = pd.DataFrame(XS, columns=RELF)
DFT = pd.DataFrame(XT, columns=TYPF)

MODELS = {
    "M0": DFB,
    "M1": pd.concat([DFB, DFR], axis=1),
    "M2": pd.concat([DFB, DFS], axis=1),
    "M3": pd.concat([DFB, DFT], axis=1),
    "M4": pd.concat([DFB, DFR, DFT], axis=1),
}
MORDER = ["M0", "M1", "M2", "M3", "M4"]

mtr = (TDAY >= TRN_LO) & (TDAY <= TRN_HI)
mva = (TDAY >= VAL_LO) & (TDAY <= VAL_HI)
mte = (TDAY >= DAY_LO) & (TDAY <= DAY_HI)

BASE_PARAMS = dict(objective="regression", metric="rmse", learning_rate=0.05,
                   num_leaves=31, min_data_in_leaf=20, feature_fraction=0.8,
                   bagging_fraction=0.8, bagging_freq=1, verbosity=-1,
                   deterministic=True, num_threads=4)

# ============================================================ train
PRED = {}       # (name, seed) -> full-length log1p prediction on val+test rows
BITER = {}
t_train = time.time()
for name in MORDER:
    Xdf = MODELS[name]
    for s in LGB_SEEDS:
        p = dict(BASE_PARAMS, seed=s, bagging_seed=s, feature_fraction_seed=s,
                 data_random_seed=s)
        dtr = lgb.Dataset(Xdf[mtr], label=Y[mtr], categorical_feature=["activity_type"],
                          free_raw_data=False)
        dva = lgb.Dataset(Xdf[mva], label=Y[mva], categorical_feature=["activity_type"],
                          reference=dtr, free_raw_data=False)
        bst = lgb.train(p, dtr, num_boost_round=500, valid_sets=[dva],
                        callbacks=[lgb.early_stopping(30, verbose=False)])
        pr = np.zeros(len(Y))
        pr[mva] = bst.predict(Xdf[mva], num_iteration=bst.best_iteration)
        pr[mte] = bst.predict(Xdf[mte], num_iteration=bst.best_iteration)
        PRED[(name, s)] = pr
        BITER[(name, s)] = bst.best_iteration
        log(f"trained {name} seed={s} best_iter={bst.best_iteration}")
TRAIN_SEC = time.time() - t_train

# ============================================================ prediction tables
WINDOWS = [("test 161-200", DAY_LO, DAY_HI), ("val 141-160", VAL_LO, VAL_HI)]


def rmse_stats(name, s, lo, hi):
    m = (TDAY >= lo) & (TDAY <= hi)
    pr = PRED[(name, s)][m]
    y = Y[m]
    full = float(np.sqrt(np.mean((pr - y) ** 2)))
    act = np.expm1(y)
    dh = np.maximum(0.0, np.expm1(pr))
    sel = (act > 0) | (dh > 0)
    part = float(np.sqrt(np.mean((pr[sel] - y[sel]) ** 2))) if sel.any() else np.nan
    return full, part, int(sel.sum()), int(m.sum())


print("=" * 100)
print("RELATION-FEATURE TEST  (OULAD 2013J only)")
print("=" * 100)
print(f"rows: train(14-140)={int(mtr.sum())}  val(141-160)={int(mva.sum())}  test(161-200)={int(mte.sum())}")
print(f"LightGBM seeds {LGB_SEEDS}; feature_fraction=bagging_fraction=0.8; all other "
      f"hyperparameters as in precheck_lgbm.py")
print("best_iter per model/seed: " +
      ", ".join(f"{n}:{[BITER[(n, s)] for s in LGB_SEEDS]}" for n in MORDER))

for wname, lo, hi in WINDOWS:
    print(f"\n=== T1  prediction accuracy, log1p space, {wname} (mean +- std over 3 seeds) ===")
    print(f"{'model':>6} {'nfeat':>6} | {'RMSE all':>16} | {'RMSE d>0 or dhat>0':>22} {'ncoord':>9} {'/':>1} {'ntot':>9}")
    for name in MORDER:
        a = np.array([rmse_stats(name, s, lo, hi) for s in LGB_SEEDS])
        print(f"{name:>6} {MODELS[name].shape[1]:>6} | "
              f"{a[:,0].mean():>8.4f} +-{a[:,0].std():>6.4f} | "
              f"{a[:,1].mean():>13.4f} +-{a[:,1].std():>6.4f} "
              f"{int(a[0,2]):>9} {'/':>1} {int(a[0,3]):>9}")

# ============================================================ decision evaluation
vecs = {}
for (mod, g, t, st, L) in blocks:
    if t < VAL_LO:
        continue
    C = courses[mod]
    cat = np.flatnonzero(C["first"] < t)
    vecs[(mod, g, t)] = dict(cat=cat, st=st, L=L, act=C["d"][g][cat, t],
                             ids=C["res"][cat], at=C["at"][cat])

# denominator: course mean daily total demand on days 141..160 (as in decision_test.py)
denom = {m: float(courses[m]["d"][:, :, 141:161].sum()) / 20.0 for m in MODULES}


def topk_cost(score, ids, act, kk):
    """Top-k by descending score, ties broken by ascending resource id; cost is
    the actual demand left unprotected."""
    n = len(score)
    if kk >= n:
        return 0.0
    sel = np.lexsort((ids, -score))[:kk]
    keep = np.zeros(n, dtype=bool)
    keep[sel] = True
    return float(act[~keep].sum())


def costs_for(scorer, kmult, lo, hi):
    """scorer(key, v) -> score vector.  Returns {key: cost}."""
    out = {}
    for k, v in vecs.items():
        if not (lo <= k[2] <= hi):
            continue
        out[k] = topk_cost(scorer(k, v), v["ids"], v["act"], KPIN[k[0]] * kmult)
    return out


def m_metrics(cost):
    shares, m3 = [], {}
    for k, c in cost.items():
        tot = float(vecs[k]["act"].sum())
        if tot > 0:
            shares.append(c / tot)
        m3[(k[0], k[2])] = m3.get((k[0], k[2]), 0.0) + c
    m3v = np.array([c / denom[m] for (m, t), c in m3.items()])
    sh = np.array(shares)
    return (float(sh.mean()), float(np.quantile(m3v, 0.95)), len(sh), len(cost) - len(sh))


DEC = {}    # (name, seed, kmult, window) -> cost dict
for wname, lo, hi in WINDOWS:
    for kmult in (1, 2):
        for name in MORDER:
            for s in LGB_SEEDS:
                pr = PRED[(name, s)]

                def sc(k, v, pr=pr):
                    return np.maximum(0.0, np.expm1(pr[v["st"]:v["st"] + v["L"]]))
                DEC[(name, s, kmult, wname)] = costs_for(sc, kmult, lo, hi)
        DEC[("O", 0, kmult, wname)] = costs_for(lambda k, v: v["act"], kmult, lo, hi)

for wname, lo, hi in WINDOWS:
    print(f"\n=== T2  top-k protection decision, {wname} (mean +- std over 3 seeds) ===")
    z = m_metrics(DEC[("M0", 0, 1, wname)])
    print(f"  vectors={z[2] + z[3]}  zero-demand vectors skipped in m1={z[3]}")
    print(f"{'model':>6} | {'m1 (k)':>17} {'m3q95 (k)':>17} | {'m1 (2k)':>17} {'m3q95 (2k)':>17}")
    for name in MORDER:
        cells = []
        for kmult in (1, 2):
            a = np.array([m_metrics(DEC[(name, s, kmult, wname)])[:2] for s in LGB_SEEDS])
            cells.append(f"{a[:,0].mean():>9.4f} +-{a[:,0].std():>6.4f}")
            cells.append(f"{a[:,1].mean():>9.4f} +-{a[:,1].std():>6.4f}")
        print(f"{name:>6} | {cells[0]} {cells[1]} | {cells[2]} {cells[3]}")
    o1 = m_metrics(DEC[("O", 0, 1, wname)])
    o2 = m_metrics(DEC[("O", 0, 2, wname)])
    print(f"{'O':>6} | {o1[0]:>9.4f} {'':>8} {o1[1]:>9.4f} {'':>8} | "
          f"{o2[0]:>9.4f} {'':>8} {o2[1]:>9.4f} {'':>8}   (oracle, seed-free)")

# ============================================================ paired bootstrap
COMPARE = [("M1", "M0"), ("M1", "M2"), ("M1", "M3"), ("M4", "M3")]


def boot_m1(a, b, kmult, wname, lo, hi):
    """Paired block bootstrap over (course, day) of the m1 difference a - b,
    using seed-averaged costs."""
    keys = [k for k in vecs if lo <= k[2] <= hi]
    bl = sorted({(k[0], k[2]) for k in keys})
    bidx = {x: i for i, x in enumerate(bl)}
    shA = np.full((len(bl), 2), np.nan)
    shB = np.full((len(bl), 2), np.nan)
    for k in keys:
        tot = float(vecs[k]["act"].sum())
        if tot <= 0:
            continue
        i = bidx[(k[0], k[2])]
        shA[i, k[1]] = np.mean([DEC[(a, s, kmult, wname)][k] for s in LGB_SEEDS]) / tot
        shB[i, k[1]] = np.mean([DEC[(b, s, kmult, wname)][k] for s in LGB_SEEDS]) / tot
    rng = np.random.default_rng(SEED + 11)
    idx = rng.integers(0, len(bl), size=(NBOOT, len(bl)))
    with np.errstate(invalid="ignore"):
        d1 = (np.nanmean(shA[idx].reshape(NBOOT, -1), axis=1) -
              np.nanmean(shB[idx].reshape(NBOOT, -1), axis=1))
    point = float(np.nanmean(shA) - np.nanmean(shB))
    return point, float(np.quantile(d1, 0.025)), float(np.quantile(d1, 0.975))


for wname, lo, hi in WINDOWS:
    print(f"\n=== T3  paired block bootstrap on m1, {wname}, {NBOOT} resamples over "
          f"(course,day) blocks, seed-averaged costs ===")
    print(f"{'k':>3} {'comparison':>12} | {'d m1':>9} {'95% lo':>9} {'95% hi':>9}  sign")
    for kmult in (1, 2):
        for a, b in COMPARE:
            p, lo_, hi_ = boot_m1(a, b, kmult, wname, lo, hi)
            sg = "CI excludes 0" if (lo_ > 0 or hi_ < 0) else "CI covers 0"
            print(f"x{kmult:>2} {a + '-' + b:>12} | {p:>9.5f} {lo_:>9.5f} {hi_:>9.5f}  {sg}")

# ============================================================ residual edge correlation
print(f"\n=== T4  residual co-movement on edges, z = r/sqrt(1+dhat), test days "
      f"{DAY_LO}-{DAY_HI}, seed-averaged dhat ===")
print(f"{'model':>6} {'edge set':>10} | {'n pairs':>9} {'pearson':>9} {'spearman':>9}")
for name in ("M0", "M1"):
    prm = np.mean([PRED[(name, s)] for s in LGB_SEEDS], axis=0)
    zx = {"jac": [], "swap": []}
    zy = {"jac": [], "swap": []}
    for k, v in vecs.items():
        if not (DAY_LO <= k[2] <= DAY_HI):
            continue
        dh = np.maximum(0.0, np.expm1(prm[v["st"]:v["st"] + v["L"]]))
        z = (v["act"] - dh) / np.sqrt(1.0 + dh)
        eu, ev, ew, su, sv = GR[k]
        zx["jac"].append(z[eu]); zy["jac"].append(z[ev])
        zx["swap"].append(z[su]); zy["swap"].append(z[sv])
    for kind in ("jac", "swap"):
        x = np.concatenate(zx[kind]); y = np.concatenate(zy[kind])
        print(f"{name:>6} {kind:>10} | {len(x):>9} "
              f"{float(np.corrcoef(x, y)[0, 1]):>9.4f} "
              f"{float(spearmanr(x, y).statistic):>9.4f}")

print(f"\nruntime: graphs {GRAPH_SEC:.1f}s, training {TRAIN_SEC:.1f}s, "
      f"total {time.time() - T_START:.1f}s")
print("[done]")
