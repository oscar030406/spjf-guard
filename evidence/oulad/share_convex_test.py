"""Follow-up tests on OULAD development data (presentation 2013J ONLY, never 2014J).

Part 1  total x share decomposition of the demand vectors (days 161..200).
Part 2  convex / threshold (exceedance) cost of each pin-selection rule.

Everything up to and including the rule definitions is taken UNCHANGED from
decision_test.py: data loading, SHA-256 group split, catalog rule, frozen
LightGBM predictor (train 14..140, early stop 141..160), Jaccard graph +
swap_edges, scale fitting on days 161..170, rules N/O/B/BU/R/C/C0/CS with the
kappa grid, k = pin slots (and 2k), and the (course,day) block bootstrap.

The ONLY change to that code: the prediction mask `mte` now also covers days
141..160 so that rule N's realized unprotected demand can be measured on the
cap-calibration window.  The booster, its training data and best_iteration are
untouched, so every number that decision_test.py prints is reproduced bit for
bit.
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

FIT_LO, FIT_HI = 161, 170     # scale parameters fitted here
PICK_LO, PICK_HI = 171, 180   # kappa would be picked here
EVL_LO, EVL_HI = 181, 200     # headline evaluation
CAP_LO, CAP_HI = 141, 160     # cap calibration window (rule N only)

KPIN = {"AAA": 7, "BBB": 11, "DDD": 8, "EEE": 3, "FFF": 11, "GGG": 4}
KAPPAS = [0.5, 1.0, 2.0, 4.0, 8.0]
NBOOT = 2000
QS = [0.5, 0.75, 0.9]

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
        s2 = sub[(sub.grp == g) & (sub.date >= DAY_LO - W) & (sub.date < DAY_HI)]
        s2 = s2[["id_student", "id_site", "date"]].drop_duplicates()
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

# ------------------------------------------------- LightGBM feature build
FEATS = ([f"lag{k}" for k in range(1, W + 1)] +
         ["other_sum14", "n_students", "active_days", "days_since_last",
          "days_since_first", "activity_type", "t", "t_mod7", "group_total14"])

blocks = []
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
            win = d[g][cat, t - W:t]
            lags = win[:, ::-1]
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
mte = (TDAY >= CAP_LO) & (TDAY <= DAY_HI)      # <-- only change: 141..200 instead of 161..200

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
print("=== frozen predictor (same as precheck_lgbm.py / decision_test.py) ===")
print(f"best_iter={booster.best_iteration}  val RMSE_log1p(LGBM)="
      f"{float(np.sqrt(np.mean((pred_va - Y[mva]) ** 2))):.4f}  "
      f"mean14={float(np.sqrt(np.mean((np.log1p(MEAN14[mva]) - Y[mva]) ** 2))):.4f}")

pred_all = np.zeros(len(Y), dtype=np.float64)
pred_all[mte] = booster.predict(Xdf[mte], num_iteration=booster.best_iteration)
DHAT = np.maximum(0.0, np.expm1(pred_all))

# ------------------------------------------------- vectors (161..200, unchanged)
vecs = {}
vecs_cap = {}
for (mod, g, t, st, L) in blocks:
    C = courses[mod]
    if DAY_LO <= t <= DAY_HI:
        cat = np.flatnonzero(C["first"] < t)
        dh = DHAT[st:st + L]
        act = C["d"][g][cat, t]
        vecs[(mod, g, t)] = dict(cat=cat, dh=dh, act=act, r=act - dh, at=C["at"][cat],
                                 ids=C["res"][cat])
    elif CAP_LO <= t <= CAP_HI:
        cat = np.flatnonzero(C["first"] < t)
        vecs_cap[(mod, g, t)] = dict(dh=DHAT[st:st + L], act=C["d"][g][cat, t],
                                     ids=C["res"][cat], n=L)

gamma = {k: 1.0 + v["dh"].mean() for k, v in vecs.items()}
ZS = {k: v["r"] / np.sqrt(1.0 + v["dh"]) for k, v in vecs.items()}


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


graphs = {}
_rng = np.random.default_rng(SEED)
for k, v in vecs.items():
    mod, g, t = k
    E, WT = build_graph(mod, g, t, v["cat"])
    Es = swap_edges(E, _rng)
    graphs[k] = dict(E=E, W=WT, Es=Es, n=len(v["cat"]))

# ============================================================ scale parameters (fit on 161..170)
FITK = [k for k in vecs if FIT_LO <= k[2] <= FIT_HI]

zbuf = {a: [] for a in ATL}
abuf = {a: [] for a in ATL}
for k in FITK:
    v = vecs[k]
    z = ZS[k]
    ra = np.abs(v["r"]) / gamma[k]
    for a in ATL:
        m = v["at"] == a
        if m.any():
            zbuf[a].append(z[m]); abuf[a].append(ra[m])
q_type = {}
q80_type = {}
for a in ATL:
    q_type[a] = float(np.std(np.concatenate(zbuf[a]))) if zbuf[a] else 0.0
    q80_type[a] = float(np.quantile(np.concatenate(abuf[a]), 0.80)) if abuf[a] else 0.0
q_bar = float(np.mean([q_type[a] for a in ATL]))

zx, zy = [], []
for k in FITK:
    z = ZS[k]
    for (u, v_) in graphs[k]["E"]:
        zx.append(z[u]); zy.append(z[v_])
zx = np.array(zx); zy = np.array(zy)
rho_raw = float(np.corrcoef(zx, zy)[0, 1])
rho = rho_raw if 4.0 * rho_raw < 1.0 else 0.24

fvals = []
for k in FITK:
    G = graphs[k]
    E, WT = G["E"], G["W"]
    if len(E) == 0:
        continue
    n = G["n"]
    u = ZS[k]
    L = np.zeros((n, n))
    for (a, b), w in zip(E, WT):
        L[a, a] += w; L[b, b] += w; L[a, b] -= w; L[b, a] -= w
    vv = np.linalg.solve(np.eye(n) + L, u)
    f = np.array([w * (vv[a] - vv[b]) for (a, b), w in zip(E, WT)])
    fvals.append(np.abs(f) / np.sqrt(WT))
fvals = np.concatenate(fvals)
q_f = float(np.quantile(fvals, 0.80))

print("\n=== scale parameters fitted on days 161-170 (unchanged) ===")
print(f"  q_bar={q_bar:.4f}   q_f={q_f:.4f}   rho_raw={rho_raw:.4f} -> rho={rho:.4f}   edges: {len(zx)}")

# ============================================================ per-vector static arrays
ST = {}
for k, v in vecs.items():
    G = graphs[k]
    n = G["n"]
    s = np.array([q_type[a] for a in v["at"]]) * np.sqrt(1.0 + v["dh"])
    s_bu = gamma[k] * np.array([q80_type[a] for a in v["at"]])
    if len(G["E"]):
        eu = np.array([e[0] for e in G["E"]], dtype=np.int64)
        ev = np.array([e[1] for e in G["E"]], dtype=np.int64)
        ew = np.asarray(G["W"], dtype=np.float64)
        beta = q_f * np.sqrt(ew) * 0.5 * (s[eu] + s[ev]) / max(q_bar, 1e-12)
    else:
        eu = ev = np.zeros(0, dtype=np.int64); ew = beta = np.zeros(0)
    if len(G["Es"]):
        su = np.array([e[0] for e in G["Es"]], dtype=np.int64)
        sv = np.array([e[1] for e in G["Es"]], dtype=np.int64)
    else:
        su = sv = np.zeros(0, dtype=np.int64)
    ST[k] = dict(n=n, dh=v["dh"], act=v["act"], ids=v["ids"], s=s, s_bu=s_bu,
                 eu=eu, ev=ev, ew=ew, beta=beta, su=su, sv=sv,
                 tot=float(v["act"].sum()))

NEG = -np.inf


def greedy(kk, delta_fn, ids, n):
    inS = np.zeros(n, dtype=bool)
    for _ in range(min(kk, n)):
        dl = delta_fn(inS).astype(np.float64).copy()
        dl[inS] = NEG
        j = int(np.lexsort((ids, -dl))[0])
        inS[j] = True
    return inS


def select(rule, kap, T, kk):
    n, dh, s = T["n"], T["dh"], T["s"]
    ids = T["ids"]
    if rule == "N":
        return greedy(kk, lambda inS: dh, ids, n)
    if rule == "O":
        return greedy(kk, lambda inS: T["act"], ids, n)
    if rule == "B":
        base = dh + kap * s
        return greedy(kk, lambda inS: base, ids, n)
    if rule == "BU":
        base = dh + kap * T["s_bu"]
        return greedy(kk, lambda inS: base, ids, n)
    if rule == "R":
        eu, ev, beta = T["eu"], T["ev"], T["beta"]

        def dfn(inS):
            sign = np.where(inS, -1.0, 1.0)
            dcut = np.zeros(n)
            if len(eu):
                np.add.at(dcut, eu, beta * sign[ev])
                np.add.at(dcut, ev, beta * sign[eu])
            return dh + kap * s - kap * dcut
        return greedy(kk, dfn, ids, n)
    if rule in ("C", "C0", "CS"):
        if rule == "C0":
            au = av = np.zeros(0, dtype=np.int64); rh = 0.0
        elif rule == "C":
            au, av, rh = T["eu"], T["ev"], rho
        else:
            au, av, rh = T["su"], T["sv"], rho
        s2 = s * s

        def dfn(inS):
            a = (~inS).astype(np.float64)
            sa = s * a
            Q = float(s2 @ a)
            if len(au):
                Q += 2.0 * rh * float(np.sum(sa[au] * sa[av]))
            nb = np.zeros(n)
            if len(au):
                np.add.at(nb, au, sa[av])
                np.add.at(nb, av, sa[au])
            dQ = -s2 - 2.0 * rh * s * nb
            return dh + kap * (np.sqrt(max(Q, 0.0)) - np.sqrt(np.maximum(Q + dQ, 0.0)))
        return greedy(kk, dfn, ids, n)
    raise ValueError(rule)


# ============================================================ run all rules (171..200, unchanged)
RULES = ["N", "O", "B", "BU", "R", "C", "C0", "CS"]
ROBUST = ["B", "BU", "R", "C", "C0", "CS"]
EVK = sorted([k for k in vecs if PICK_LO <= k[2] <= EVL_HI])

RESULT = {}
for kmult in (1, 2):
    for rule in RULES:
        kl = KAPPAS if rule in ROBUST else [None]
        for kap in kl:
            out = {}
            for k in EVK:
                T = ST[k]
                kk = KPIN[k[0]] * kmult
                inS = select(rule, kap if kap is not None else 0.0, T, kk)
                out[k] = (inS, float(T["act"][~inS].sum()))
            RESULT[(kmult, rule, kap)] = out

# ############################################################################
# PART 1 -- total x share decomposition
# ############################################################################
P1K = sorted([k for k in vecs
              if vecs[k]["act"].sum() > 0 and vecs[k]["dh"].sum() > 0])

SHARE = {}
for k in P1K:
    v = vecs[k]
    T = float(v["act"].sum()); Th = float(v["dh"].sum())
    pi = v["act"] / T
    pih = v["dh"] / Th
    e = pi - pih
    es = e / np.sqrt(pih * (1.0 - pih) + 1e-6)
    SHARE[k] = dict(T=T, Th=Th, pi=pi, pih=pih, e=e, es=es, n=len(e))

print("\n" + "=" * 78)
print("PART 1  total x share decomposition   (days 161-200)")
print("=" * 78)
print(f"vectors used (sum d > 0 and sum dhat > 0): {len(P1K)} of {len(vecs)}")


def pair_sets(keys, rng_seed):
    """Returns dict pairtype -> (u_index_list, v_index_list) per vector key."""
    rng = np.random.default_rng(rng_seed)
    out = {"jaccard": {}, "swapped": {}, "random": {}}
    for k in keys:
        G = graphs[k]
        n = G["n"]
        E, Es = G["E"], G["Es"]
        out["jaccard"][k] = (np.array([e[0] for e in E], dtype=np.int64),
                             np.array([e[1] for e in E], dtype=np.int64))
        out["swapped"][k] = (np.array([e[0] for e in Es], dtype=np.int64),
                             np.array([e[1] for e in Es], dtype=np.int64))
        m = len(E)
        if m == 0 or n < 2:
            out["random"][k] = (np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64))
            continue
        a = rng.integers(0, n, size=m)
        b = rng.integers(0, n, size=m)
        for _ in range(20):
            bad = a == b
            if not bad.any():
                break
            b[bad] = rng.integers(0, n, size=int(bad.sum()))
        ok = a != b
        out["random"][k] = (a[ok].astype(np.int64), b[ok].astype(np.int64))
    return out


PAIRS = pair_sets(P1K, SEED + 101)
PTYPES = ["jaccard", "swapped", "random"]


def pooled_corr(keys, ptype, field):
    xs, ys = [], []
    for k in keys:
        u, v = PAIRS[ptype][k]
        if len(u) == 0:
            continue
        a = SHARE[k][field]
        xs.append(a[u]); ys.append(a[v])
    if not xs:
        return np.nan, np.nan, 0
    x = np.concatenate(xs); y = np.concatenate(ys)
    if len(x) < 3 or np.std(x) == 0 or np.std(y) == 0:
        return np.nan, np.nan, len(x)
    pe = float(np.corrcoef(x, y)[0, 1])
    sp = float(spearmanr(x, y).statistic)
    return pe, sp, len(x)


def baselines(keys):
    ns = np.array([SHARE[k]["n"] for k in keys], dtype=np.float64)
    mv = np.array([len(PAIRS["jaccard"][k][0]) for k in keys], dtype=np.float64)
    b = -1.0 / np.maximum(ns - 1.0, 1.0)
    return float(b.mean()), float((b * mv).sum() / max(mv.sum(), 1.0))


print("\n--- 1a  edge-level correlation of the share residual e = pi - pi_hat ---")
for field, lab in (("e", "raw e"), ("es", "e / sqrt(pi_hat(1-pi_hat)+1e-6)")):
    print(f"\n  [{lab}]")
    print(f"{'scope':>8} {'npair':>7} | " +
          " | ".join(f"{p[:4]} pear {p[:4]} spear" for p in PTYPES) +
          " | base(vec) base(edge)")
    for scope in ["POOLED"] + MODULES:
        keys = P1K if scope == "POOLED" else [k for k in P1K if k[0] == scope]
        cells = []
        npair = 0
        for p in PTYPES:
            pe, sp, m = pooled_corr(keys, p, field)
            if p == "jaccard":
                npair = m
            cells.append(f"{pe:>9.4f} {sp:>10.4f}")
        bv, be = baselines(keys)
        print(f"{scope:>8} {npair:>7} | " + " | ".join(cells) + f" | {bv:>9.4f} {be:>9.4f}")

# ---------------------------------------------------------------- 1b
print("\n--- 1b  variance decomposition of the cost forecast error, rule N ---")
print("    log(L/L_hat) = log(T/T_hat) + log(u/u_hat),  u = unprotected share")
print(f"{'k':>3} {'scope':>8} {'nvec':>5} | {'var logT':>9} {'var logu':>9} {'cov':>9} "
      f"{'var logL':>9} | {'shT':>6} {'shu':>6} {'sh2cov':>7} | {'attrT':>6} {'attru':>6}")
for kmult in (1, 2):
    rows = {}
    for k in P1K:
        T = ST[k]
        inS = select("N", 0.0, T, KPIN[k[0]] * kmult)
        S = SHARE[k]
        cu = float(T["act"][~inS].sum())
        cuh = float(T["dh"][~inS].sum())
        if cu <= 0 or cuh <= 0:
            continue
        u = cu / S["T"]; uh = cuh / S["Th"]
        rows[k] = (np.log(S["T"] / S["Th"]), np.log(u / uh))
    for scope in ["POOLED"] + MODULES:
        ks = [k for k in rows if scope == "POOLED" or k[0] == scope]
        if len(ks) < 3:
            continue
        a = np.array([rows[k][0] for k in ks])
        b = np.array([rows[k][1] for k in ks])
        va = float(np.var(a)); vb = float(np.var(b))
        cv = float(np.cov(a, b, bias=True)[0, 1])
        vt = float(np.var(a + b))
        print(f"x{kmult:>2} {scope:>8} {len(ks):>5} | {va:>9.5f} {vb:>9.5f} {cv:>9.5f} "
              f"{vt:>9.5f} | {va/vt:>6.3f} {vb/vt:>6.3f} {2*cv/vt:>7.3f} | "
              f"{(va+cv)/vt:>6.3f} {(vb+cv)/vt:>6.3f}")

# ---------------------------------------------------------------- 1c
print("\n--- 1c  between-cluster correlation of aggregated share residuals ---")


def components(n, E):
    par = list(range(n))

    def find(x):
        while par[x] != x:
            par[x] = par[par[x]]; x = par[x]
        return x
    for a, b in E:
        ra, rb = find(a), find(b)
        if ra != rb:
            par[rb] = ra
    comp = {}
    for i in range(n):
        comp.setdefault(find(i), []).append(i)
    return [np.array(v, dtype=np.int64) for v in comp.values() if len(v) >= 2]


CLUST = {k: components(graphs[k]["n"], graphs[k]["E"]) for k in P1K}

print(f"{'scope':>8} {'nvec':>5} {'npair':>7} {'mclu':>6} {'msize':>6} {'mass':>6} | "
      f"{'pear(e)':>8} {'spear(e)':>9} {'pear(es)':>9} | {'meanR_v':>8} {'base':>7}")
for scope in ["POOLED"] + MODULES:
    keys = [k for k in P1K if (scope == "POOLED" or k[0] == scope) and len(CLUST[k]) >= 2]
    if not keys:
        continue
    xs, ys, xss, yss, rv, bl, nclu, csz, mass = [], [], [], [], [], [], [], [], []
    for k in keys:
        cl = CLUST[k]
        S = SHARE[k]
        Ec = np.array([S["e"][c].sum() for c in cl])
        Es_ = np.array([S["es"][c].sum() for c in cl])
        m = len(cl)
        iu, ju = np.triu_indices(m, 1)
        xs.append(Ec[iu]); ys.append(Ec[ju])
        xss.append(Es_[iu]); yss.append(Es_[ju])
        ss = float((Ec ** 2).sum())
        if ss > 0 and m >= 2:
            rv.append((float(Ec.sum()) ** 2 - ss) / ((m - 1) * ss))
        bl.append(-1.0 / (m - 1))
        nclu.append(m); csz.append(np.mean([len(c) for c in cl]))
        mass.append(float(np.abs(S["e"][np.concatenate(cl)]).sum()) /
                    max(float(np.abs(S["e"]).sum()), 1e-12))
    x = np.concatenate(xs); y = np.concatenate(ys)
    xz = np.concatenate(xss); yz = np.concatenate(yss)
    pe = float(np.corrcoef(x, y)[0, 1]) if len(x) > 2 else np.nan
    sp = float(spearmanr(x, y).statistic) if len(x) > 2 else np.nan
    pz = float(np.corrcoef(xz, yz)[0, 1]) if len(xz) > 2 else np.nan
    print(f"{scope:>8} {len(keys):>5} {len(x):>7} {np.mean(nclu):>6.2f} {np.mean(csz):>6.2f} "
          f"{np.mean(mass):>6.3f} | {pe:>8.4f} {sp:>9.4f} {pz:>9.4f} | "
          f"{np.mean(rv):>8.4f} {np.mean(bl):>7.4f}")
print("  meanR_v = per-vector mean pairwise correlation surrogate")
print("            [ (sum_c E_c)^2 - sum_c E_c^2 ] / [ (m-1) * sum_c E_c^2 ];")
print("            equals the mechanical baseline -1/(m-1) exactly when sum_c E_c = 0.")

# ############################################################################
# PART 2 -- convex / threshold cost
# ############################################################################
print("\n" + "=" * 78)
print("PART 2  convex / threshold cost")
print("=" * 78)

# ---- caps: rule N's L on days 141..160, per course, per kmult
CAP = {}
LN_CAL = {}
for kmult in (1, 2):
    agg = {}
    for (mod, g, t), v in vecs_cap.items():
        T = dict(n=v["n"], dh=v["dh"], act=v["act"], ids=v["ids"], s=np.zeros(v["n"]))
        inS = select("N", 0.0, T, KPIN[mod] * kmult)
        agg[(mod, t)] = agg.get((mod, t), 0.0) + float(v["act"][~inS].sum())
    LN_CAL[kmult] = agg
    CAP[kmult] = {}
    for mod in MODULES:
        arr = np.array([agg[(mod, t)] for t in range(CAP_LO, CAP_HI + 1) if (mod, t) in agg])
        CAP[kmult][mod] = {q: float(np.quantile(arr, q)) for q in QS}

print(f"\ncaps = quantiles of rule N's realized unprotected demand L over days {CAP_LO}-{CAP_HI}")
print(f"{'k':>3} {'course':>7} {'ndays':>6} {'cap0.50':>10} {'cap0.75':>10} {'cap0.90':>10}")
for kmult in (1, 2):
    for mod in MODULES:
        nd = sum(1 for t in range(CAP_LO, CAP_HI + 1) if (mod, t) in LN_CAL[kmult])
        c = CAP[kmult][mod]
        print(f"x{kmult:>2} {mod:>7} {nd:>6} {c[0.5]:>10.1f} {c[0.75]:>10.1f} {c[0.9]:>10.1f}")

METRICS = [("exc", 0.5), ("exc", 0.75), ("exc", 0.9),
           ("mexc", 0.5), ("mexc", 0.75), ("mexc", 0.9), ("sq", None)]
MLAB = {("exc", 0.5): "exc.50", ("exc", 0.75): "exc.75", ("exc", 0.9): "exc.90",
        ("mexc", 0.5): "mex.50", ("mexc", 0.75): "mex.75", ("mexc", 0.9): "mex.90",
        ("sq", None): "sq"}

BLK = {}
for lo, hi in ((PICK_LO, PICK_HI), (EVL_LO, EVL_HI)):
    BLK[(lo, hi)] = sorted({(k[0], k[2]) for k in EVK if lo <= k[2] <= hi})


def block_L(kmult, rule, kap, lo, hi):
    out = RESULT[(kmult, rule, kap)]
    bl = BLK[(lo, hi)]
    bidx = {b: i for i, b in enumerate(bl)}
    L = np.zeros(len(bl))
    for k in EVK:
        if lo <= k[2] <= hi:
            L[bidx[(k[0], k[2])]] += out[k][1]
    return L


def per_block(kmult, L, lo, hi):
    bl = BLK[(lo, hi)]
    out = {}
    c05 = np.array([max(CAP[kmult][b[0]][0.5], 1e-9) for b in bl])
    for q in QS:
        cq = np.array([max(CAP[kmult][b[0]][q], 1e-9) for b in bl])
        out[("exc", q)] = (L > cq).astype(np.float64)
        out[("mexc", q)] = np.maximum(0.0, L - cq) / cq
    out[("sq", None)] = (L / c05) ** 2
    return out


PB = {}
for kmult in (1, 2):
    for rule in RULES:
        for kap in (KAPPAS if rule in ROBUST else [None]):
            for lo, hi in ((PICK_LO, PICK_HI), (EVL_LO, EVL_HI)):
                PB[(kmult, rule, kap, lo, hi)] = per_block(
                    kmult, block_L(kmult, rule, kap, lo, hi), lo, hi)

PICK2 = {}
for kmult in (1, 2):
    for rule in ROBUST:
        for M in METRICS:
            PICK2[(kmult, rule, M)] = min(
                KAPPAS, key=lambda kp: float(PB[(kmult, rule, kp, PICK_LO, PICK_HI)][M].mean()))

for kmult in (1, 2):
    for lo, hi in ((EVL_LO, EVL_HI), (PICK_LO, PICK_HI)):
        tag = "EVAL" if lo == EVL_LO else "PICK"
        print(f"\n=== {tag} days {lo}-{hi}, k x{kmult}  ({len(BLK[(lo,hi)])} course-day blocks) ===")
        print(f"{'rule':>5} {'kappa':>6} | " + " ".join(f"{MLAB[M]:>8}" for M in METRICS))
        for rule in RULES:
            for kap in (KAPPAS if rule in ROBUST else [None]):
                pb = PB[(kmult, rule, kap, lo, hi)]
                marks = "".join("*" if (rule in ROBUST and PICK2[(kmult, rule, M)] == kap) else ""
                                for M in METRICS)
                ks = f"{kap:>5.1f}" if kap is not None else f"{'-':>5}"
                cells = " ".join(f"{float(pb[M].mean()):>8.4f}" for M in METRICS)
                print(f"{rule:>5} {ks}{'*' if marks else ' '} | {cells}"
                      + (f"   <-{','.join(MLAB[M] for M in METRICS if rule in ROBUST and PICK2[(kmult,rule,M)] == kap)}"
                         if marks else ""))

print("\n=== picked kappa on days 171-180, per metric ===")
print(f"{'k':>3} {'rule':>5} | " + " ".join(f"{MLAB[M]:>7}" for M in METRICS))
for kmult in (1, 2):
    for rule in ROBUST:
        print(f"x{kmult:>2} {rule:>5} | " +
              " ".join(f"{PICK2[(kmult, rule, M)]:>7.1f}" for M in METRICS))

print(f"\n=== paired block bootstrap 95% CI of (rule - N) at the picked kappa, "
      f"{NBOOT} resamples, days {EVL_LO}-{EVL_HI} ===")
print(f"{'k':>3} {'rule':>5} {'metric':>7} {'kap':>4} | {'N':>9} {'rule':>9} {'delta':>9} "
      f"{'lo':>9} {'hi':>9}")
bl_e = BLK[(EVL_LO, EVL_HI)]
_brng = np.random.default_rng(SEED + 11)
BIDX = _brng.integers(0, len(bl_e), size=(NBOOT, len(bl_e)))
for kmult in (1, 2):
    for rule in ("C", "C0", "CS", "R", "B"):
        for M in METRICS:
            kap = PICK2[(kmult, rule, M)]
            xr = PB[(kmult, rule, kap, EVL_LO, EVL_HI)][M]
            xn = PB[(kmult, "N", None, EVL_LO, EVL_HI)][M]
            d = xr[BIDX].mean(axis=1) - xn[BIDX].mean(axis=1)
            print(f"x{kmult:>2} {rule:>5} {MLAB[M]:>7} {kap:>4.1f} | "
                  f"{xn.mean():>9.4f} {xr.mean():>9.4f} {xr.mean()-xn.mean():>9.5f} "
                  f"{float(np.quantile(d, 0.025)):>9.5f} {float(np.quantile(d, 0.975)):>9.5f}")

print("\n[done]")
