"""Error co-movement pre-check with a LightGBM predictor replacing the 14-day mean.

OULAD development presentation 2013J ONLY. Never reads 2014J.
Data loading, SHA-256 group split, catalog rule, Jaccard graph builder,
swap_edges, and the Q3/Q4 statistics are taken unchanged from precheck.py.
Only the predictor changes.
"""
import hashlib
import json
import sys

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

import lightgbm as lgb

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

np.random.seed(SEED)


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
print(f"[load] rows={len(df)} students={df.id_student.nunique()} sites={df.id_site.nunique()}", file=sys.stderr)

# full day axis needed for LightGBM features (target day 14 needs days 0..13)
D0 = 0
NDAY = DAY_HI + 1
ATL = sorted(ATYPES)
ATCODE = {a: i for i, a in enumerate(ATL)}

# ------------------------------------------------- per-course structures
courses = {}
for mod, sub in df.groupby("code_module"):
    res = np.sort(sub.id_site.unique())
    ridx = {r: i for i, r in enumerate(res)}
    R = len(res)
    first = sub.groupby("id_site").date.min()
    first_arr = np.array([first[r] for r in res], dtype=np.int32)
    # demand cube (group, resource, day) over days 0..200
    d = np.zeros((2, R, NDAY), dtype=np.float64)
    sw = sub[(sub.date >= D0) & (sub.date <= DAY_HI)]
    agg = sw.groupby(["grp", "id_site", "date"], observed=True).sum_click.sum()
    if len(agg):
        gi = agg.index.get_level_values(0).to_numpy()
        ri = np.array([ridx[x] for x in agg.index.get_level_values(1)])
        di = agg.index.get_level_values(2).to_numpy() - D0
        d[gi, ri, di] = agg.to_numpy()
    # unique (student, resource, day) triples per group for graph windows
    # (unchanged: same date filter as precheck.py)
    tri = {}
    dstu = np.zeros((2, R, NDAY + 2), dtype=np.int32)   # distinct students in window ending t-1
    for g in (0, 1):
        s2 = sub[(sub.grp == g) & (sub.date >= DAY_LO - W) & (sub.date < DAY_HI)]
        s2 = s2[["id_student", "id_site", "date"]].drop_duplicates()
        stu = np.sort(s2.id_student.unique())
        sidx = {s: i for i, s in enumerate(stu)}
        tri[g] = (np.array([sidx[s] for s in s2.id_student], dtype=np.int32),
                  np.array([ridx[r] for r in s2.id_site], dtype=np.int32),
                  s2.date.to_numpy().astype(np.int32), len(stu))
        # distinct-student counts over every 14-day window, via interval accumulation:
        # a (student,resource,day) triple contributes one NEW distinct student for
        # target day t iff day in [t-14, t-1] and the previous access of the same
        # (student,resource) pair is < t-14.
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

# ------------------------------------------------- LightGBM feature build
FEATS = ([f"lag{k}" for k in range(1, W + 1)] +
         ["other_sum14", "n_students", "active_days", "days_since_last",
          "days_since_first", "activity_type", "t", "t_mod7", "group_total14"])

blocks = []    # (mod, g, t, start, length)
Xp, Yp, MEANp = [], [], []
cursor = 0
for mod in sorted(courses):
    C = courses[mod]
    d, first = C["d"], C["first"]
    atc = np.array([ATCODE[a] for a in C["at"]], dtype=np.int32)
    for g in (0, 1):
        for t in range(TRN_LO, DAY_HI + 1):
            cat = np.flatnonzero(first < t)
            if len(cat) == 0:
                continue
            win = d[g][cat, t - W:t]                     # (n, 14) days t-14..t-1
            lags = win[:, ::-1]                          # lag1 = day t-1
            other = d[1 - g][cat, t - W:t].sum(axis=1)
            pos = win > 0
            has = pos.any(axis=1)
            lastrel = (W - 1) - np.argmax(pos[:, ::-1], axis=1)
            dsl = np.where(has, W - lastrel, 999.0)
            n = len(cat)
            feat = np.empty((n, len(FEATS)), dtype=np.float32)
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
            Xp.append(feat)
            Yp.append(np.log1p(d[g][cat, t]).astype(np.float32))
            MEANp.append(win.mean(axis=1).astype(np.float32))
            blocks.append((mod, g, t, cursor, n))
            cursor += n

X = np.concatenate(Xp); Y = np.concatenate(Yp); MEAN14 = np.concatenate(MEANp)
del Xp, Yp, MEANp
TDAY = np.concatenate([np.full(L, t, dtype=np.int32) for (_, _, t, _, L) in blocks])
Xdf = pd.DataFrame(X, columns=FEATS)
Xdf["activity_type"] = Xdf["activity_type"].astype(int).astype("category")

mtr = (TDAY >= TRN_LO) & (TDAY <= TRN_HI)
mva = (TDAY >= VAL_LO) & (TDAY <= VAL_HI)
mte = (TDAY >= DAY_LO) & (TDAY <= DAY_HI)

params = dict(objective="regression", metric="rmse", learning_rate=0.05,
              num_leaves=31, min_data_in_leaf=20, feature_fraction=0.9,
              bagging_fraction=0.9, bagging_freq=1, verbosity=-1,
              seed=SEED, bagging_seed=SEED, feature_fraction_seed=SEED,
              data_random_seed=SEED, deterministic=True, num_threads=4)
dtr = lgb.Dataset(Xdf[mtr], label=Y[mtr], categorical_feature=["activity_type"], free_raw_data=False)
dva = lgb.Dataset(Xdf[mva], label=Y[mva], categorical_feature=["activity_type"], reference=dtr, free_raw_data=False)
booster = lgb.train(params, dtr, num_boost_round=500, valid_sets=[dva],
                    callbacks=[lgb.early_stopping(30, verbose=False)])

pred_va = booster.predict(Xdf[mva], num_iteration=booster.best_iteration)
rmse_lgb = float(np.sqrt(np.mean((pred_va - Y[mva]) ** 2)))
rmse_m14 = float(np.sqrt(np.mean((np.log1p(MEAN14[mva]) - Y[mva]) ** 2)))

print("=== predictor comparison (validation days 141-160, log1p space) ===")
print(f"{'rows train':>11} {'rows val':>9} {'rows test':>10} {'best_iter':>10}")
print(f"{int(mtr.sum()):>11} {int(mva.sum()):>9} {int(mte.sum()):>10} {booster.best_iteration:>10}")
print(f"{'predictor':>12} {'RMSE_log1p':>11}")
print(f"{'LightGBM':>12} {rmse_lgb:>11.4f}")
print(f"{'mean14':>12} {rmse_m14:>11.4f}")
imp = sorted(zip(FEATS, booster.feature_importance("gain")), key=lambda z: -z[1])[:8]
print("  top gain: " + ", ".join(f"{a}={b:.0f}" for a, b in imp))

pred_all = np.zeros(len(Y), dtype=np.float64)
pred_all[mte] = booster.predict(Xdf[mte], num_iteration=booster.best_iteration)
DHAT = np.maximum(0.0, np.expm1(pred_all))

# ------------------------------------------------- residual containers
vecs = {}
for (mod, g, t, st, L) in blocks:
    if not (DAY_LO <= t <= DAY_HI):
        continue
    C = courses[mod]
    cat = np.flatnonzero(C["first"] < t)
    dh = DHAT[st:st + L]
    act = C["d"][g][cat, t]
    vecs[(mod, g, t)] = dict(cat=cat, dh=dh, act=act, r=act - dh, at=C["at"][cat])

gamma = {k: 1.0 + v["dh"].mean() for k, v in vecs.items()}
RG = {k: v["r"] / gamma[k] for k, v in vecs.items()}                       # r / gamma
ZS = {k: v["r"] / np.sqrt(1.0 + v["dh"]) for k, v in vecs.items()}         # z = r/sqrt(1+dhat)

# ============================================================ graphs (unchanged)
def build_graph(mod, g, t, cat):
    C = courses[mod]
    si, ri, di, nstu = C["tri"][g]
    sel = (di >= t - W) & (di <= t - 1)
    if sel.sum() == 0:
        return [], np.zeros((0,))
    pos = {r: i for i, r in enumerate(cat)}
    ss, rr = si[sel], ri[sel]
    keep = np.array([r in pos for r in rr])
    ss, rr = ss[keep], np.array([pos[r] for r in rr[keep]], dtype=np.int32)
    if len(ss) == 0:
        return [], np.zeros((0,))
    A = np.zeros((nstu, len(cat)), dtype=np.float32)
    A[ss, rr] = 1.0
    I = A.T @ A
    sz = np.diag(I).copy()
    with np.errstate(divide="ignore", invalid="ignore"):
        un = sz[:, None] + sz[None, :] - I
        J = np.where(un > 0, I / np.maximum(un, 1e-9), 0.0)
    iu, ju = np.triu_indices(len(cat), 1)
    ok = (I[iu, ju] >= MIN_COMMON) & (J[iu, ju] > 0)
    iu, ju, wv = iu[ok], ju[ok], J[iu, ju][ok]
    order = np.lexsort((ju, iu, -wv))
    deg = np.zeros(len(cat), dtype=np.int32)
    E, WT = [], []
    for o in order:
        u, v = int(iu[o]), int(ju[o])
        if deg[u] < DEG_CAP and deg[v] < DEG_CAP:
            E.append((u, v)); WT.append(float(wv[o])); deg[u] += 1; deg[v] += 1
    return E, np.array(WT)


def build_neg_graph(mod, g, t, cat):
    """Edges weighted max(0, -Pearson) of the two 14-day demand series."""
    C = courses[mod]
    win = C["d"][g][cat, t - W:t]
    Xc = win - win.mean(axis=1, keepdims=True)
    sd = win.std(axis=1)
    good = sd > 0
    with np.errstate(divide="ignore", invalid="ignore"):
        cov = (Xc @ Xc.T) / W
        corr = cov / np.outer(np.maximum(sd, 1e-12), np.maximum(sd, 1e-12))
    corr = np.where(np.outer(good, good), corr, 0.0)
    iu, ju = np.triu_indices(len(cat), 1)
    wv = np.maximum(0.0, -corr[iu, ju])
    ok = wv > 0
    iu, ju, wv = iu[ok], ju[ok], wv[ok]
    order = np.lexsort((ju, iu, -wv))
    deg = np.zeros(len(cat), dtype=np.int32)
    E, WT = [], []
    for o in order:
        u, v = int(iu[o]), int(ju[o])
        if deg[u] < DEG_CAP and deg[v] < DEG_CAP:
            E.append((u, v)); WT.append(float(wv[o])); deg[u] += 1; deg[v] += 1
    return E, np.array(WT)


def swap_edges(E, rng, mult=10):
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


def make_graphs(builder, seed):
    out, stat = {}, {}
    rng = np.random.default_rng(seed)
    for k, v in vecs.items():
        mod, g, t = k
        E, WT = builder(mod, g, t, v["cat"])
        Es = swap_edges(E, rng)
        n = len(v["cat"])
        deg = np.zeros(n)
        for u, vv in E:
            deg[u] += 1; deg[vv] += 1
        out[k] = dict(E=E, W=WT, Es=Es, n=n, iso=float((deg == 0).mean()))
        stat.setdefault(mod, []).append((len(E), out[k]["iso"], n))
    return out, stat


graphs, gstat = make_graphs(build_graph, SEED)
ngraphs, ngstat = make_graphs(build_neg_graph, SEED)
print("\n=== graphs (both deg<=4) ===")
print(f"{'course':>7} | {'jac nodes':>9} {'jac edges':>9} {'jac iso':>8} | {'neg edges':>9} {'neg iso':>8}")
for mod in MODULES:
    if mod in gstat:
        a = np.array(gstat[mod]); b = np.array(ngstat[mod])
        print(f"{mod:>7} | {a[:,2].mean():>9.1f} {a[:,0].mean():>9.1f} {a[:,1].mean():>8.3f} | "
              f"{b[:,0].mean():>9.1f} {b[:,1].mean():>8.3f}")

# ============================================================ pair collection
def collect(graphdict, kind, valmap, restrict_pos):
    per = {}
    rr = np.random.default_rng(SEED + 7)
    for k, v in vecs.items():
        mod, g, t = k
        x = valmap[k]
        dh = v["dh"]
        G = graphdict[k]
        if kind == "jac":
            P = G["E"]
        elif kind == "swap":
            P = G["Es"]
        else:
            n = G["n"]
            m = len(G["E"])
            if n < 2 or m == 0:
                P = []
            else:
                a = rr.integers(0, n, m); b = rr.integers(0, n, m)
                P = [(int(p), int(q)) for p, q in zip(a, b) if p != q]
        for u, w in P:
            if restrict_pos and not (dh[u] > 0 and dh[w] > 0):
                continue
            per.setdefault(mod, []).append((x[u], x[w]))
    return per


def summarize(per, spear=False):
    out = {}
    allx, ally = [], []
    for mod, lst in per.items():
        if len(lst) < 3:
            continue
        a = np.array(lst)
        x, y = a[:, 0], a[:, 1]
        allx.append(x); ally.append(y)
        nz = (x != 0) & (y != 0)
        sg = float(np.mean(np.sign(x[nz]) == np.sign(y[nz]))) if nz.sum() else np.nan
        sp = float(spearmanr(x, y).statistic) if spear else np.nan
        out[mod] = (len(x), float(np.corrcoef(x, y)[0, 1]), sg, sp)
    if not allx:
        return out
    x = np.concatenate(allx); y = np.concatenate(ally)
    nz = (x != 0) & (y != 0)
    out["POOLED"] = (len(x), float(np.corrcoef(x, y)[0, 1]),
                     float(np.mean(np.sign(x[nz]) == np.sign(y[nz]))),
                     float(spearmanr(x, y).statistic) if spear else np.nan)
    return out


def table(graphdict, valmap, title, spear, label0="graph"):
    print(f"\n{title}")
    for restrict in (False, True):
        tag = "both dhat>0" if restrict else "all pairs"
        res = {kd: summarize(collect(graphdict, kd, valmap, restrict), spear) for kd in ("jac", "swap", "rand")}
        print(f"-- {tag}")
        hdr_one = f"{'n':>8} {'corr':>7} {'sign':>6}" + (f" {'spear':>7}" if spear else "")
        print(f"{'course':>7} | {label0:>{len(hdr_one)}} | {'swap':>{len(hdr_one)}} | {'rand':>{len(hdr_one)}}")
        print(f"{'':>7} | " + " | ".join([hdr_one] * 3))
        for mod in MODULES + ["POOLED"]:
            if mod not in res["jac"]:
                continue
            cells = []
            for kd in ("jac", "swap", "rand"):
                n, c, s, sp = res[kd].get(mod, (0, np.nan, np.nan, np.nan))
                cell = f"{n:>8} {c:>7.3f} {s:>6.3f}"
                if spear:
                    cell += f" {sp:>7.3f}"
                cells.append(cell)
            print(f"{mod:>7} | " + " | ".join(cells))


# ============================================================ T1
table(graphs, RG, "=== T1  Q3 on LightGBM residuals r/gamma (days 161-200) ===", spear=False, label0="jaccard")

# ============================================================ T2
table(graphs, ZS, "=== T2  standardized z = r/sqrt(1+dhat), with Spearman ===", spear=True, label0="jaccard")

# ============================================================ T3
print("\n=== T3  difference vs sum energy of z on edges ===")
print(f"{'course':>7} | {'jac n':>8} {'(zu-zv)^2':>10} {'(zu+zv)^2':>10} {'ratio':>7} | "
      f"{'swap n':>8} {'(zu-zv)^2':>10} {'(zu+zv)^2':>10} {'ratio':>7}")
acc = {kd: {} for kd in ("jac", "swap")}
for kd in ("jac", "swap"):
    per = collect(graphs, kd, ZS, False)
    for mod, lst in per.items():
        a = np.array(lst)
        acc[kd][mod] = (len(a), float(np.mean((a[:, 0] - a[:, 1]) ** 2)),
                        float(np.mean((a[:, 0] + a[:, 1]) ** 2)))
    allp = np.concatenate([np.array(v) for v in per.values()])
    acc[kd]["POOLED"] = (len(allp), float(np.mean((allp[:, 0] - allp[:, 1]) ** 2)),
                         float(np.mean((allp[:, 0] + allp[:, 1]) ** 2)))
for mod in MODULES + ["POOLED"]:
    if mod not in acc["jac"]:
        continue
    cells = []
    for kd in ("jac", "swap"):
        n, dif, sm = acc[kd][mod]
        cells.append(f"{n:>8} {dif:>10.3f} {sm:>10.3f} {dif/max(sm,1e-12):>7.3f}")
    print(f"{mod:>7} | " + " | ".join(cells))

# ============================================================ T4
print("\n=== T4  residual energy absorbed by the (I+L)^-1 projection (r/gamma) ===")
print(f"{'graph':>8} {'mean':>8} {'median':>8} {'n_vec':>7}")
for kind in ("jac", "swap"):
    vals = []
    for k, v in vecs.items():
        G = graphs[k]
        E = G["E"] if kind == "jac" else G["Es"]
        if len(E) == 0:
            continue
        n = G["n"]
        u = RG[k]
        if np.dot(u, u) == 0:
            continue
        L = np.zeros((n, n))
        for (a, b), w in zip(E, G["W"]):
            L[a, a] += w; L[b, b] += w; L[a, b] -= w; L[b, a] -= w
        vv = np.linalg.solve(np.eye(n) + L, u)
        vals.append(1 - np.dot(vv, vv) / np.dot(u, u))
    print(f"{kind:>8} {np.mean(vals):>8.4f} {np.median(vals):>8.4f} {len(vals):>7}")

# ============================================================ T5
table(ngraphs, RG, "=== T5  T1 on the negative-correlation graph (max(0,-Pearson) of 14d demand) ===",
      spear=False, label0="neg-corr")
