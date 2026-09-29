"""Falsification pre-check on OULAD 2013J development data only.

Never reads 2014J. Outputs compact numeric tables to stdout.
"""
import hashlib
import json
import sys

import numpy as np
import pandas as pd

SEED = 20260918
DATA = r"<repo-root>\data"
MODULES = ["AAA", "BBB", "DDD", "EEE", "FFF", "GGG"]
PRES = "2013J"
ATYPES = {"resource", "oucontent", "page"}
W = 14                 # lookback window
ALPHA = 0.3            # ewma
DAY_LO, DAY_HI = 161, 200
DEG_CAP = 4
MIN_COMMON = 2

rng_global = np.random.default_rng(SEED)


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

DAYS = np.arange(DAY_LO - W, DAY_HI + 1)
D0 = DAYS[0]
NDAY = len(DAYS)

# ------------------------------------------------- per-course structures
courses = {}
for mod, sub in df.groupby("code_module"):
    res = np.sort(sub.id_site.unique())
    ridx = {r: i for i, r in enumerate(res)}
    R = len(res)
    first = sub.groupby("id_site").date.min()
    first_arr = np.array([first[r] for r in res], dtype=np.int32)
    # demand cube (group, resource, day)
    d = np.zeros((2, R, NDAY), dtype=np.float64)
    sw = sub[(sub.date >= D0) & (sub.date <= DAY_HI)]
    agg = sw.groupby(["grp", "id_site", "date"], observed=True).sum_click.sum()
    if len(agg):
        gi = agg.index.get_level_values(0).to_numpy()
        ri = np.array([ridx[x] for x in agg.index.get_level_values(1)])
        di = agg.index.get_level_values(2).to_numpy() - D0
        d[gi, ri, di] = agg.to_numpy()
    # unique (student, resource, day) triples per group for graph windows
    tri = {}
    for g in (0, 1):
        s2 = sub[(sub.grp == g) & (sub.date >= D0) & (sub.date < DAY_HI)]
        s2 = s2[["id_student", "id_site", "date"]].drop_duplicates()
        stu = np.sort(s2.id_student.unique())
        sidx = {s: i for i, s in enumerate(stu)}
        tri[g] = (np.array([sidx[s] for s in s2.id_student], dtype=np.int32),
                  np.array([ridx[r] for r in s2.id_site], dtype=np.int32),
                  s2.date.to_numpy().astype(np.int32), len(stu))
    courses[mod] = dict(res=res, R=R, first=first_arr, d=d, tri=tri,
                        at=np.array([atype[r] for r in res]))

# ------------------------------------------------- predictors + residuals
w_ew = ALPHA * (1 - ALPHA) ** np.arange(W - 1, -1, -1)
w_ew = w_ew / w_ew.sum()

rows = []          # per-coordinate records
vecs = {}          # (mod, g, t) -> dict with arrays
for mod, C in courses.items():
    d = C["d"]
    for g in (0, 1):
        for t in range(DAY_LO, DAY_HI + 1):
            ti = t - D0
            cat = np.flatnonzero(C["first"] < t)
            if len(cat) == 0:
                continue
            win = d[g][np.ix_(cat, np.arange(ti - W, ti))]
            dh = win.mean(axis=1)
            dh_e = win @ w_ew
            act = d[g][cat, ti]
            vecs[(mod, g, t)] = dict(cat=cat, dh=dh, dh_e=dh_e, act=act,
                                     r=act - dh, r_e=act - dh_e, at=C["at"][cat])

for k, v in vecs.items():
    rows.append(None)  # placeholder, we build arrays below

allmod = np.concatenate([np.repeat(k[0], len(v["dh"])) for k, v in vecs.items()])
allday = np.concatenate([np.repeat(k[2], len(v["dh"])) for k, v in vecs.items()])
alldh = np.concatenate([v["dh"] for v in vecs.values()])
allr = np.concatenate([v["r"] for v in vecs.values()])
alldh_e = np.concatenate([v["dh_e"] for v in vecs.values()])
allr_e = np.concatenate([v["r_e"] for v in vecs.values()])
allat = np.concatenate([v["at"] for v in vecs.values()])

# ============================================================ Q1
print("\n=== Q1 heteroscedasticity (target days 161-180) ===")
m18 = (allday >= 161) & (allday <= 180)
edges_bin = [(-0.5, 1e-12), (1e-12, 1), (1, 5), (5, 20), (20, 100), (100, np.inf)]
names = ["0", "(0,1]", "(1,5]", "(5,20]", "(20,100]", ">100"]
for tag, dh_, r_ in (("mean14", alldh, allr), ("ewma0.3", alldh_e, allr_e)):
    print(f"-- predictor {tag}")
    print(f"{'bin':>9} {'count':>9} {'q80|r|':>9} {'q95|r|':>9} {'meanDhat':>9}")
    for (lo, hi), nm in zip(edges_bin, names):
        sel = m18 & (dh_ > lo) & (dh_ <= hi)
        n = int(sel.sum())
        if n == 0:
            print(f"{nm:>9} {0:>9}")
            continue
        a = np.abs(r_[sel])
        print(f"{nm:>9} {n:>9} {np.quantile(a,0.8):>9.2f} {np.quantile(a,0.95):>9.2f} {dh_[sel].mean():>9.2f}")
    x = np.log1p(dh_[m18]); y = np.log(1e-3 + np.abs(r_[m18]))
    b, a0 = np.polyfit(x, y, 1)
    print(f"  OLS slope log(1e-3+|r|) ~ log(1+dhat): {b:.4f} (intercept {a0:.4f}, n={m18.sum()})")

# ============================================================ Q2
print("\n=== Q2 uniform-scale box looseness (mean14 predictor) ===")
gamma = {k: 1.0 + v["dh"].mean() for k, v in vecs.items()}

def fit_q(norm_fn, days):
    out = {}
    for at_ in sorted(ATYPES):
        vals = []
        for k, v in vecs.items():
            if not (days[0] <= k[2] <= days[1]):
                continue
            sel = v["at"] == at_
            if sel.sum() == 0:
                continue
            vals.append(np.abs(v["r"][sel]) / norm_fn(v, gamma[k])[sel])
        out[at_] = np.quantile(np.concatenate(vals), 0.8) if vals else 1.0
    return out

scales = {
    "S_uniform": lambda v, gm: np.full(len(v["dh"]), gm),
    "S_sqrt":    lambda v, gm: np.sqrt(1 + v["dh"]),
    "S_lin":     lambda v, gm: 1 + v["dh"],
}
print(f"{'scale':>10} {'rho_cal':>9} {'looseness':>11} {'cov181-200':>11} {'q80 by type (oucontent/page/resource)':>40}")
for nm, fn in scales.items():
    qt = fit_q(fn, (161, 170))
    def S_of(k, v):
        return fn(v, gamma[k]) * np.array([qt[a] for a in v["at"]])
    rho = []
    for k, v in vecs.items():
        if 171 <= k[2] <= 180:
            S = S_of(k, v)
            rho.append(np.max(np.abs(v["r"]) / S))
    rho_cal = float(np.quantile(rho, 0.8))
    loose, cov = [], []
    for k, v in vecs.items():
        if 171 <= k[2] <= 180:
            S = S_of(k, v)
            den = v["dh"].sum()
            if den > 0:
                loose.append(rho_cal * S.sum() / den)
        if 181 <= k[2] <= 200:
            S = S_of(k, v)
            cov.append(np.max(np.abs(v["r"]) / S) <= rho_cal)
    qs = "/".join(f"{qt[a]:.3f}" for a in ["oucontent", "page", "resource"])
    print(f"{nm:>10} {rho_cal:>9.3f} {np.mean(loose):>11.2f} {np.mean(cov):>11.3f} {qs:>40}")

# ============================================================ graphs
print("\n=== relation graph (Jaccard, deg<=4, >=2 common learners) ===")


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
rng = np.random.default_rng(SEED)
gstat = {}
for k, v in vecs.items():
    mod, g, t = k
    E, WT = build_graph(mod, g, t, v["cat"])
    Es = swap_edges(E, rng)
    n = len(v["cat"])
    deg = np.zeros(n);
    for u, vv in E:
        deg[u] += 1; deg[vv] += 1
    graphs[k] = dict(E=E, W=WT, Es=Es, n=n, iso=float((deg == 0).mean()))
    gstat.setdefault(mod, []).append((len(E), graphs[k]["iso"], n))
print(f"{'course':>7} {'nodes':>7} {'edges':>8} {'isolated':>9}")
for mod in MODULES:
    if mod in gstat:
        a = np.array(gstat[mod])
        print(f"{mod:>7} {a[:,2].mean():>7.1f} {a[:,0].mean():>8.1f} {a[:,1].mean():>9.3f}")

# ============================================================ Q3
print("\n=== Q3 error co-movement on edges (days 161-200, resid/gamma) ===")


def collect(kind, restrict_pos):
    per = {}
    rr = np.random.default_rng(SEED + 7)
    for k, v in vecs.items():
        mod, g, t = k
        gm = gamma[k]
        rn = v["r"] / gm
        dh = v["dh"]
        G = graphs[k]
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
                P = [(int(x), int(y)) for x, y in zip(a, b) if x != y]
        for u, w in P:
            if restrict_pos and not (dh[u] > 0 and dh[w] > 0):
                continue
            per.setdefault(mod, []).append((rn[u], rn[w]))
    return per


def summarize(per):
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
        out[mod] = (len(x), float(np.corrcoef(x, y)[0, 1]), sg)
    x = np.concatenate(allx); y = np.concatenate(ally)
    nz = (x != 0) & (y != 0)
    out["POOLED"] = (len(x), float(np.corrcoef(x, y)[0, 1]),
                     float(np.mean(np.sign(x[nz]) == np.sign(y[nz]))))
    return out


for restrict in (False, True):
    tag = "both dhat>0" if restrict else "all pairs"
    res = {kd: summarize(collect(kd, restrict)) for kd in ("jac", "swap", "rand")}
    print(f"-- {tag}")
    print(f"{'course':>7} | {'jac n':>8} {'corr':>7} {'sign':>6} | {'swap n':>8} {'corr':>7} {'sign':>6} | {'rand n':>8} {'corr':>7} {'sign':>6}")
    for mod in MODULES + ["POOLED"]:
        if mod not in res["jac"]:
            continue
        cells = []
        for kd in ("jac", "swap", "rand"):
            n, c, s = res[kd].get(mod, (0, np.nan, np.nan))
            cells.append(f"{n:>8} {c:>7.3f} {s:>6.3f}")
        print(f"{mod:>7} | " + " | ".join(cells))

# ============================================================ Q4
print("\n=== Q4 residual energy explained by reallocation term ===")
for kind in ("jac", "swap"):
    vals = []
    for k, v in vecs.items():
        G = graphs[k]
        E = G["E"] if kind == "jac" else G["Es"]
        if len(E) == 0:
            continue
        n = G["n"]
        u = v["r"] / gamma[k]
        if np.dot(u, u) == 0:
            continue
        L = np.zeros((n, n))
        for (a, b), w in zip(E, G["W"]):
            L[a, a] += w; L[b, b] += w; L[a, b] -= w; L[b, a] -= w
        vv = np.linalg.solve(np.eye(n) + L, u)
        vals.append(1 - np.dot(vv, vv) / np.dot(u, u))
    print(f"{kind:>6}: mean 1-||v||^2/||u||^2 = {np.mean(vals):.4f}  (median {np.median(vals):.4f}, n_vec={len(vals)})")
