"""Decision-level offline test: does any robust pin-selection rule beat top-k by d_hat?

OULAD development presentation 2013J ONLY. Never reads 2014J.
Data loading, SHA-256 group split, catalog rule, LightGBM predictor (train 14..140,
early stop on 141..160), Jaccard graph builder (deg cap 4) and swap_edges are taken
UNCHANGED from precheck_lgbm.py.

Fit window for scale parameters: days 161..170.
Kappa-pick window: days 171..180.  Evaluation window: days 181..200.
"""
import hashlib
import json
import sys

import numpy as np
import pandas as pd

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

KPIN = {"AAA": 7, "BBB": 11, "DDD": 8, "EEE": 3, "FFF": 11, "GGG": 4}
KAPPAS = [0.5, 1.0, 2.0, 4.0, 8.0]
NBOOT = 2000

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
print("=== frozen predictor (same as precheck_lgbm.py) ===")
print(f"best_iter={booster.best_iteration}  val RMSE_log1p(LGBM)="
      f"{float(np.sqrt(np.mean((pred_va - Y[mva]) ** 2))):.4f}  "
      f"mean14={float(np.sqrt(np.mean((np.log1p(MEAN14[mva]) - Y[mva]) ** 2))):.4f}")

pred_all = np.zeros(len(Y), dtype=np.float64)
pred_all[mte] = booster.predict(Xdf[mte], num_iteration=booster.best_iteration)
DHAT = np.maximum(0.0, np.expm1(pred_all))

# ------------------------------------------------- vectors
vecs = {}
for (mod, g, t, st, L) in blocks:
    if not (DAY_LO <= t <= DAY_HI):
        continue
    C = courses[mod]
    cat = np.flatnonzero(C["first"] < t)
    dh = DHAT[st:st + L]
    act = C["d"][g][cat, t]
    vecs[(mod, g, t)] = dict(cat=cat, dh=dh, act=act, r=act - dh, at=C["at"][cat],
                             ids=C["res"][cat])

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

# rho: pooled Pearson of z on Jaccard edges, days 161..170
zx, zy = [], []
for k in FITK:
    z = ZS[k]
    for (u, v_) in graphs[k]["E"]:
        zx.append(z[u]); zy.append(z[v_])
zx = np.array(zx); zy = np.array(zy)
rho_raw = float(np.corrcoef(zx, zy)[0, 1])
rho = rho_raw if 4.0 * rho_raw < 1.0 else 0.24

# q_f: 80% quantile of |f_e|/sqrt(w_e) from (I + M W M^T) v = u, f = W M^T v on z
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

print("\n=== scale parameters fitted on days 161-170 ===")
print("  q_type (std of z per activity_type): " + ", ".join(f"{a}={q_type[a]:.4f}" for a in ATL))
print("  q80_type (80% quantile of |r|/gamma per type): " + ", ".join(f"{a}={q80_type[a]:.4f}" for a in ATL))
print(f"  q_bar={q_bar:.4f}   q_f={q_f:.4f}   rho_raw={rho_raw:.4f} -> rho={rho:.4f} "
      f"(4*rho={4*rho:.3f})   edges used for rho: {len(zx)}")

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
    """Start from S empty, add the item with the largest decrease in the objective,
    kk times; ties broken by ascending resource id."""
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


# ============================================================ run all rules
RULES = ["N", "O", "B", "BU", "R", "C", "C0", "CS"]
ROBUST = ["B", "BU", "R", "C", "C0", "CS"]
EVK = sorted([k for k in vecs if PICK_LO <= k[2] <= EVL_HI])

# course mean daily total demand on days 141..160 (both groups, all resources)
denom = {m: float(courses[m]["d"][:, :, 141:161].sum()) / 20.0 for m in MODULES}

RESULT = {}   # (kmult, rule, kappa) -> dict key -> (share, cost, symdiff)
for kmult in (1, 2):
    for rule in RULES:
        kl = KAPPAS if rule in ROBUST else [None]
        for kap in kl:
            out = {}
            for k in EVK:
                T = ST[k]
                kk = KPIN[k[0]] * kmult
                inS = select(rule, kap if kap is not None else 0.0, T, kk)
                cost = float(T["act"][~inS].sum())
                out[k] = (inS, cost)
            RESULT[(kmult, rule, kap)] = out

# ---------------------------------------------------------------- metrics
def metrics(kmult, rule, kap, lo, hi, courses_sel=None):
    out = RESULT[(kmult, rule, kap)]
    outN = RESULT[(kmult, "N", None)]
    keys = [k for k in EVK if lo <= k[2] <= hi and (courses_sel is None or k[0] in courses_sel)]
    shares, nzero = [], 0
    ndiff, symd = 0, []
    for k in keys:
        inS, cost = out[k]
        tot = ST[k]["tot"]
        if tot <= 0:
            nzero += 1
        else:
            shares.append(cost / tot)
        sN = outN[k][0]
        sd = int(np.sum(inS ^ sN))
        symd.append(sd / (KPIN[k[0]] * kmult))
        ndiff += (sd > 0)
    # m3 per (course, day)
    m3 = {}
    for k in keys:
        mod, g, t = k
        m3[(mod, t)] = m3.get((mod, t), 0.0) + out[k][1]
    m3v = np.array([c / denom[m] for (m, t), c in m3.items()])
    sh = np.array(shares)
    return dict(n=len(keys), nzero=nzero,
                m1=float(sh.mean()) if len(sh) else np.nan,
                q90=float(np.quantile(sh, 0.90)) if len(sh) else np.nan,
                q95=float(np.quantile(sh, 0.95)) if len(sh) else np.nan,
                m3m=float(m3v.mean()), m3q95=float(np.quantile(m3v, 0.95)),
                fdiff=ndiff / max(len(keys), 1), msym=float(np.mean(symd)))


PICK = {}
for kmult in (1, 2):
    for rule in ROBUST:
        best = min(KAPPAS, key=lambda kp: metrics(kmult, rule, kp, PICK_LO, PICK_HI)["m1"])
        PICK[(kmult, rule)] = best


def print_table(kmult, lo, hi, title):
    print(f"\n{title}   (k x{kmult}; vectors {lo}-{hi})")
    z = metrics(kmult, "N", None, lo, hi)
    print(f"  vectors={z['n']}  zero-demand skipped in m1={z['nzero']}")
    print(f"{'rule':>5} {'kappa':>6} | {'m1 mean':>8} {'q90':>7} {'q95':>7} | "
          f"{'m3 mean':>8} {'m3 q95':>7} | {'m4 frac':>8} {'m4 sym/k':>8}")
    for rule in RULES:
        kl = KAPPAS if rule in ROBUST else [None]
        for kap in kl:
            M = metrics(kmult, rule, kap, lo, hi)
            mark = "*" if (rule in ROBUST and PICK[(kmult, rule)] == kap) else " "
            ks = f"{kap:>5.1f}{mark}" if kap is not None else f"{'-':>6}"
            print(f"{rule:>5} {ks} | {M['m1']:>8.4f} {M['q90']:>7.4f} {M['q95']:>7.4f} | "
                  f"{M['m3m']:>8.4f} {M['m3q95']:>7.4f} | {M['fdiff']:>8.3f} {M['msym']:>8.3f}")


# ---------------------------------------------------------------- bootstrap
def boot(kmult, rule, kap, lo, hi):
    outR = RESULT[(kmult, rule, kap)]
    outN = RESULT[(kmult, "N", None)]
    bl = sorted({(k[0], k[2]) for k in EVK if lo <= k[2] <= hi})
    bidx = {b: i for i, b in enumerate(bl)}
    shR = np.full((len(bl), 2), np.nan); shN = np.full((len(bl), 2), np.nan)
    cR = np.zeros(len(bl)); cN = np.zeros(len(bl))
    for k in EVK:
        if not (lo <= k[2] <= hi):
            continue
        i = bidx[(k[0], k[2])]
        tot = ST[k]["tot"]
        if tot > 0:
            shR[i, k[1]] = outR[k][1] / tot
            shN[i, k[1]] = outN[k][1] / tot
        cR[i] += outR[k][1]; cN[i] += outN[k][1]
    dn = np.array([denom[b[0]] for b in bl])
    m3R = cR / dn; m3N = cN / dn
    rng = np.random.default_rng(SEED + 11)
    idx = rng.integers(0, len(bl), size=(NBOOT, len(bl)))
    with np.errstate(invalid="ignore"):
        d1 = np.nanmean(shR[idx].reshape(NBOOT, -1), axis=1) - np.nanmean(shN[idx].reshape(NBOOT, -1), axis=1)
        d3 = np.quantile(m3R[idx], 0.95, axis=1) - np.quantile(m3N[idx], 0.95, axis=1)
    return (float(np.quantile(d1, 0.025)), float(np.quantile(d1, 0.975)),
            float(np.quantile(d3, 0.025)), float(np.quantile(d3, 0.975)))


# ============================================================ output
print(f"\nk per course (x1): " + ", ".join(f"{m}={KPIN[m]}" for m in MODULES))
print(f"denominator (course mean daily total demand, days 141-160): " +
      ", ".join(f"{m}={denom[m]:.0f}" for m in MODULES))
print("\nR formula used:")
print("  obj_R(S) = a.dhat + kappa * [ sum_e beta_e |a_u - a_v| + sum_i s_i a_i ],  a_i = 1 - [i in S]")
print("  s_i    = q_type(i) * sqrt(1 + dhat_i)")
print("  beta_e = q_f * sqrt(w_e) * 0.5*(s_u + s_v) / q_bar")
print("  q_f    = 80% quantile over fit-window Jaccard edges of |f_e| / sqrt(w_e),")
print("           f = W M^T v,  (I + M W M^T) v = z,  M = signed node-edge incidence,")
print("           W = diag(Jaccard weights),  M W M^T = weighted Laplacian,  z = r/sqrt(1+dhat)")
print("  q_bar  = mean over the 3 activity types of q_type")

for kmult in (1, 2):
    print_table(kmult, EVL_LO, EVL_HI, f"=== POOLED, evaluation days {EVL_LO}-{EVL_HI} ===")
    print_table(kmult, PICK_LO, PICK_HI, f"=== POOLED, kappa-pick days {PICK_LO}-{PICK_HI} ===")

print("\n=== per-course m1 (mean cost share), evaluation days 181-200, kappa = picked ===")
for kmult in (1, 2):
    print(f"-- k x{kmult}")
    hdr = f"{'rule':>5} {'kap':>4} |" + "".join(f"{m:>8}" for m in MODULES) + f"{'POOLED':>9}"
    print(hdr)
    for rule in RULES:
        kap = PICK[(kmult, rule)] if rule in ROBUST else None
        cells = "".join(f"{metrics(kmult, rule, kap, EVL_LO, EVL_HI, [m])['m1']:>8.4f}" for m in MODULES)
        ks = f"{kap:>4.1f}" if kap is not None else f"{'-':>4}"
        print(f"{rule:>5} {ks} |" + cells +
              f"{metrics(kmult, rule, kap, EVL_LO, EVL_HI)['m1']:>9.4f}")

print("\n=== paired bootstrap 95% CI of (rule - N), 2000 resamples over (course,day) blocks, days 181-200 ===")
print(f"{'k':>3} {'rule':>5} {'kappa':>6} | {'d m1 lo':>9} {'d m1 hi':>9} | {'d m3q95 lo':>11} {'d m3q95 hi':>11}")
for kmult in (1, 2):
    for rule in ("B", "R", "C"):
        kap = PICK[(kmult, rule)]
        a, b, c, dd = boot(kmult, rule, kap, EVL_LO, EVL_HI)
        print(f"x{kmult:>2} {rule:>5} {kap:>6.1f} | {a:>9.5f} {b:>9.5f} | {c:>11.5f} {dd:>11.5f}")

print("\n[done]")
