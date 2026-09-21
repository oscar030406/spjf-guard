"""Falsification pre-check: does co-heating-aware (anti-affinity) placement of course
resources across m servers lower per-server peak load vs load-only placement?

OULAD development presentation 2013J ONLY.  Never reads 2014J.
Data loading, Jaccard graph builder (deg cap 4, >=2 common learners) and swap_edges
are taken from precheck/decision_test.py; the access-group split is dropped
(demand d[r, day] = total clicks on resource r).

Rolling re-placement: decision day t0 in {100,120,140,160,180,200}; history = days < t0,
evaluation = days t0..t0+19.
"""
import sys
import time

import numpy as np
import pandas as pd

T_START = time.time()

SEED = 20260918
DATA = r"<repo-root>\data"
MODULES = ["AAA", "BBB", "DDD", "EEE", "FFF", "GGG"]
PRES = "2013J"
ATYPES_MAIN = {"resource", "oucontent", "page"}

W = 14                  # Jaccard window / mu window
SWIN = 28               # scale + covariance window
DEG_CAP = 4
MIN_COMMON = 2
T0S = [100, 120, 140, 160, 180, 200]
EVLEN = 20
DAY_HI = max(T0S) + EVLEN - 1          # 219
NDAY = DAY_HI + 1
DEV_T0 = [100, 120, 140]
TST_T0 = [160, 180, 200]
RHOS = [0.2, 0.5]
KAPPAS = [1.0, 2.0]
NHASH = 200
NBOOT = 2000
LS_MAX = 2000

np.random.seed(SEED)


# ---------------------------------------------------------------- load
def load(atypes):
    vle = pd.read_csv(f"{DATA}/vle.csv",
                      usecols=["id_site", "code_module", "code_presentation", "activity_type"])
    vle = vle[(vle.code_presentation == PRES) & (vle.code_module.isin(MODULES))]
    if atypes is not None:
        vle = vle[vle.activity_type.isin(atypes)]
    site_ok = set(vle.id_site.astype(np.int64))

    parts = []
    for ch in pd.read_csv(f"{DATA}/studentVle.csv",
                          usecols=["code_module", "code_presentation", "id_student",
                                   "id_site", "date", "sum_click"],
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
    return df


def build(df):
    """Global resource index, demand matrix D (R x NDAY), first-seen day, window triples."""
    res = np.sort(df.id_site.unique())
    ridx = {int(r): i for i, r in enumerate(res)}
    R = len(res)
    rvec = np.array([ridx[int(r)] for r in df.id_site], dtype=np.int32)
    first = np.full(R, 10 ** 6, dtype=np.int32)
    np.minimum.at(first, rvec, df.date.to_numpy().astype(np.int32))
    D = np.zeros((R, NDAY), dtype=np.float64)
    dts = df.date.to_numpy().astype(np.int64)
    clk = df.sum_click.to_numpy().astype(np.float64)
    ok = dts >= 0
    np.add.at(D, (rvec[ok], dts[ok]), clk[ok])
    mod_of = np.empty(R, dtype=object)
    mm = df[["id_site", "code_module"]].drop_duplicates()
    for s, m in zip(mm.id_site, mm.code_module):
        mod_of[ridx[int(s)]] = m
    # unique (student, resource, day) triples for graph building
    tri = df[["id_student", "id_site", "date"]].drop_duplicates()
    tri = tri[(tri.date >= min(T0S) - W) & (tri.date < max(T0S))]
    stu = np.sort(tri.id_student.unique())
    sidx = {int(s): i for i, s in enumerate(stu)}
    TS = np.array([sidx[int(s)] for s in tri.id_student], dtype=np.int32)
    TR = np.array([ridx[int(r)] for r in tri.id_site], dtype=np.int32)
    TD = tri.date.to_numpy().astype(np.int32)
    return dict(res=res, R=R, D=D, first=first, mod=mod_of,
                TS=TS, TR=TR, TD=TD, NSTU=len(stu), ids=res.astype(np.int64))


# ---------------------------------------------------------------- graph (from decision_test.py)
def build_graph(B, cat, t0):
    """Jaccard co-learner graph over days t0-W .. t0-1, all students. cat = global indices."""
    sel = (B["TD"] >= t0 - W) & (B["TD"] <= t0 - 1)
    ss, rr = B["TS"][sel], B["TR"][sel]
    pos = -np.ones(B["R"], dtype=np.int64)
    pos[cat] = np.arange(len(cat))
    keep = pos[rr] >= 0
    ss, rr = ss[keep], pos[rr[keep]]
    if len(ss) == 0:
        return []
    ustu, ss2 = np.unique(ss, return_inverse=True)
    A = np.zeros((len(ustu), len(cat)), dtype=np.float32)
    A[ss2, rr] = 1.0
    I = (A.T @ A).astype(np.float64)
    sz = np.diag(I).copy()
    un = sz[:, None] + sz[None, :] - I
    J = np.where(un > 0, I / np.maximum(un, 1e-9), 0.0)
    iu, ju = np.triu_indices(len(cat), 1)
    ok = (I[iu, ju] >= MIN_COMMON) & (J[iu, ju] > 0)
    iu, ju, wv = iu[ok], ju[ok], J[iu, ju][ok]
    order = np.lexsort((ju, iu, -wv))
    deg = np.zeros(len(cat), dtype=np.int32)
    E = []
    for o in order:
        u, v = int(iu[o]), int(ju[o])
        if deg[u] < DEG_CAP and deg[v] < DEG_CAP:
            E.append((u, v)); deg[u] += 1; deg[v] += 1
    return E


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


# ---------------------------------------------------------------- placement machinery
def _max_excl(scores_sorted_idx, scores, a, j):
    """max over servers not in {a, j}; scores_sorted_idx = top-3 indices desc."""
    for t in scores_sorted_idx:
        if t != a and t != j:
            return scores[t]
    return -np.inf


def greedy_place(mu, own, coup_cols, kappa, m, ids, R):
    """LPT-style greedy minimising max_j [M_j + kappa*sqrt(V_j)].
    coup_cols(r) -> (idx array, val array) of couplings of r to other resources (self excluded)."""
    order = np.lexsort((ids, -mu))
    M = np.zeros(m); V = np.zeros(m)
    CS = np.zeros((R, m))
    assign = np.full(R, -1, dtype=np.int32)
    for r in order:
        r = int(r)
        newV = V + own[r] + 2.0 * CS[r]
        newM = M + mu[r]
        cand = newM + kappa * np.sqrt(np.maximum(newV, 0.0))
        sc = M + kappa * np.sqrt(np.maximum(V, 0.0))
        # oth[j] = max over servers k != j of sc[k]
        t0i = int(np.argmax(sc))
        oth = np.full(m, sc[t0i])
        if m > 1:
            s2nd = np.max(np.delete(sc, t0i))
            oth[t0i] = s2nd
        else:
            oth[t0i] = -np.inf
        bj = int(np.argmin(np.maximum(cand, oth)))
        M[bj] += mu[r]; V[bj] = newV[bj]
        idxs, vals = coup_cols(r)
        if len(idxs):
            CS[idxs, bj] += vals
        assign[r] = bj
    return assign, M, V, CS


def local_search(assign, M, V, CS, mu, own, coup_cols, kappa, m, R, maxmoves=LS_MAX):
    assign = assign.copy(); M = M.copy(); V = V.copy(); CS = CS.copy()
    ar = np.arange(R)
    moves = 0
    for _ in range(maxmoves):
        sc = M + kappa * np.sqrt(np.maximum(V, 0.0))
        cur = sc.max()
        a = assign
        Ma = M[a] - mu
        Va = V[a] - own - 2.0 * CS[ar, a]
        sa = Ma + kappa * np.sqrt(np.maximum(Va, 0.0))
        Mj = M[None, :] + mu[:, None]
        Vj = V[None, :] + own[:, None] + 2.0 * CS
        sj = Mj + kappa * np.sqrt(np.maximum(Vj, 0.0))
        k = min(3, m)
        top = np.argsort(-sc)[:k]
        oth = np.full((R, m), -np.inf)
        for t in top[::-1]:
            mask = (a[:, None] != t) & (np.arange(m)[None, :] != t)
            oth = np.where(mask, sc[t], oth)
        obj = np.maximum(np.maximum(sa[:, None], sj), oth)
        obj[ar, a] = np.inf
        flat = int(np.argmin(obj))
        r, j = flat // m, flat % m
        if obj[r, j] >= cur - 1e-9:
            break
        aa = int(a[r])
        M[aa] -= mu[r]; V[aa] = max(Va[r], 0.0)
        M[j] += mu[r]; V[j] = max(Vj[r, j], 0.0)
        idxs, vals = coup_cols(r)
        if len(idxs):
            CS[idxs, aa] -= vals
            CS[idxs, j] += vals
        assign[r] = j
        moves += 1
    return assign, moves


def metrics(assign, Dev, m):
    """imbalance stats over evaluation days."""
    R, nd = Dev.shape
    oh = np.zeros((m, R))
    oh[assign, np.arange(R)] = 1.0
    loads = oh @ Dev
    tot = loads.sum(axis=0)
    ok = tot > 0
    mx = loads.max(axis=0)
    imb = mx[ok] / (tot[ok] / m)
    return dict(mean=float(imb.mean()), q95=float(np.quantile(imb, 0.95)),
                peak=float(mx.max()), frac=float((imb > 1.5).mean()), nday=int(ok.sum()))


# ---------------------------------------------------------------- one scope/window
def run_window(B, cat, t0, m_list, rng, res_store, scope_key, variant, scope_all):
    Dh = B["D"][cat]                                     # history+eval demand rows
    mu = Dh[:, t0 - W:t0].mean(axis=1)
    s = Dh[:, t0 - SWIN:t0].std(axis=1)
    s = np.maximum(s, 1e-6)
    Dev = Dh[:, t0:t0 + EVLEN]
    R = len(cat)
    ids = B["ids"][cat]
    mu_or = Dev.mean(axis=1)                             # oracle mean load

    E = build_graph(B, cat, t0)
    Es = swap_edges(E, rng)

    def nbrs(E):
        out = [[] for _ in range(R)]
        for u, v in E:
            out[u].append(v); out[v].append(u)
        return [np.array(x, dtype=np.int64) for x in out]

    NB, NBS = nbrs(E), nbrs(Es)

    X = Dh[:, t0 - SWIN:t0]
    Sig = np.cov(X)
    if Sig.ndim == 0:
        Sig = Sig.reshape(1, 1)
    Sig = 0.5 * Sig + 0.5 * np.diag(np.diag(Sig))
    Sig_own = np.maximum(np.diag(Sig).copy(), 0.0)
    Sig_off = Sig.copy()
    np.fill_diagonal(Sig_off, 0.0)

    zero = (np.zeros(0, dtype=np.int64), np.zeros(0))

    def cc_none(r):
        return zero

    def make_cc_graph(NBx, rho):
        def f(r):
            nb = NBx[r]
            return (nb, rho * s[r] * s[nb]) if len(nb) else zero
        return f

    def cc_cov(r):
        return (np.arange(R), Sig_off[:, r])

    s2 = s * s
    zown = np.zeros(R)

    configs = []                                          # (label, mu_w, own, cc, kappa, do_ls)
    configs.append(("L", mu, zown, cc_none, 0.0, True))
    for kp in KAPPAS:
        configs.append((f"V k{kp:g}", mu + kp * s, zown, cc_none, 0.0, False))
    for rho in RHOS:
        for kp in KAPPAS:
            configs.append((f"G r{rho:g} k{kp:g}", mu, s2, make_cc_graph(NB, rho), kp, True))
            configs.append((f"GS r{rho:g} k{kp:g}", mu, s2, make_cc_graph(NBS, rho), kp, True))
    for kp in KAPPAS:
        configs.append((f"G0 k{kp:g}", mu, s2, cc_none, kp, True))
        configs.append((f"E k{kp:g}", mu, Sig_own, cc_cov, kp, True))
    configs.append(("O", mu_or, zown, cc_none, 0.0, False))

    for m in m_list:
        for (lab, muw, own, cc, kp, dols) in configs:
            a0, M, V, CS = greedy_place(muw, own, cc, kp, m, ids, R)
            mt = metrics(a0, Dev, m); mt["moves"] = 0
            res_store[(variant, scope_key, m, t0, lab, 0)] = mt
            if dols:
                a1, nm = local_search(a0, M, V, CS, muw, own, cc, kp, m, R)
                mt = metrics(a1, Dev, m); mt["moves"] = nm
                res_store[(variant, scope_key, m, t0, lab, 1)] = mt
        # atomic lower bound: no placement can put less than the biggest single resource
        # on the busiest server
        tot_d = Dev.sum(axis=0)
        okd = tot_d > 0
        fair = tot_d[okd] / m
        lb = np.maximum(Dev.max(axis=0)[okd], fair) / fair
        res_store[(variant, scope_key, m, t0, "LB", 0)] = dict(
            mean=float(lb.mean()), q95=float(np.quantile(lb, 0.95)),
            peak=float(np.maximum(Dev.max(axis=0), tot_d / m).max()),
            frac=float((lb > 1.5).mean()), nday=int(okd.sum()), moves=0)
        # random hash, averaged over NHASH seeds
        acc = {"mean": 0.0, "q95": 0.0, "peak": 0.0, "frac": 0.0}
        for sd in range(NHASH):
            rr = np.random.default_rng(SEED + 1000 * sd + m)
            a = rr.integers(0, m, size=R).astype(np.int32)
            mt = metrics(a, Dev, m)
            for kk in acc:
                acc[kk] += mt[kk] / NHASH
        acc["nday"] = EVLEN
        acc["moves"] = 0
        res_store[(variant, scope_key, m, t0, "H", 0)] = acc
    # concentration + share of evaluation load on resources that did not exist before t0
    tot = Dev.sum(axis=1)
    new = np.setdiff1d(scope_all, cat)
    newload = float(B["D"][new][:, t0:t0 + EVLEN].sum()) if len(new) else 0.0
    top5 = float(np.sort(tot)[-5:].sum() / max(tot.sum(), 1e-9))
    return dict(R=R, edges=len(E), top5=top5,
                top1=float(tot.max() / max(tot.sum(), 1e-9)),
                newshare=newload / max(tot.sum() + newload, 1e-9))


# ---------------------------------------------------------------- reporting
def agg(res, variant, scopes, m, t0s, lab, ls, field, baseL=None):
    vals = []
    for sk in scopes:
        for t0 in t0s:
            k = (variant, sk, m, t0, lab, ls)
            if k not in res:
                return np.nan
            v = res[k][field]
            if field == "peak":
                v = v / res[(variant, sk, m, t0, "L", 0)]["peak"]
            vals.append(v)
    return float(np.mean(vals))


def pick_best(res, variant, scopes, m, prefix, ls):
    cands = [l for l in LABELS if l.startswith(prefix + " ")] if prefix in ("G", "GS", "G0", "E") else [prefix]
    best, bl = np.inf, None
    for l in cands:
        v = agg(res, variant, scopes, m, DEV_T0, l, ls, "mean")
        if v == v and v < best:
            best, bl = v, l
    return bl


def boot_ci(res, variant, blocks, la, lb, ls, field):
    da = []
    for (sk, m, t0) in blocks:
        A = res[(variant, sk, m, t0, la, ls)][field]
        Bv = res[(variant, sk, m, t0, lb, ls)][field]
        da.append(A - Bv)
    da = np.array(da)
    rng = np.random.default_rng(SEED + 7)
    idx = rng.integers(0, len(da), size=(NBOOT, len(da)))
    bs = da[idx].mean(axis=1)
    return float(da.mean()), float(np.quantile(bs, 0.025)), float(np.quantile(bs, 0.975))


LABELS = (["H", "L"] + [f"V k{k:g}" for k in KAPPAS] +
          [f"G r{r:g} k{k:g}" for r in RHOS for k in KAPPAS] +
          [f"G0 k{k:g}" for k in KAPPAS] +
          [f"GS r{r:g} k{k:g}" for r in RHOS for k in KAPPAS] +
          [f"E k{k:g}" for k in KAPPAS] + ["O", "LB"])
LS_LABELS = set(["L"] + [l for l in LABELS if l[0] in "GE" and l != "H"])


def main():
    out = []

    def P(*a):
        line = " ".join(str(x) for x in a)
        print(line)
        out.append(line)

    res = {}
    info = {}
    for variant, atypes in [("main(resource/oucontent/page)", ATYPES_MAIN), ("all-activity-types", None)]:
        t0v = time.time()
        df = load(atypes)
        B = build(df)
        P(f"\n########## VARIANT: {variant} ##########")
        P(f"[load] rows={len(df)}  resources={B['R']}  students={df.id_student.nunique()}  "
          f"graph-window students={B['NSTU']}")
        del df
        rng = np.random.default_rng(SEED)
        mod_of = B["mod"]
        for t0 in T0S:
            catg = np.flatnonzero(B["first"] < t0)
            # S1: per course
            allidx = np.arange(B["R"])
            for mod in MODULES:
                scope_all = allidx[np.array([mod_of[i] == mod for i in allidx])]
                cat = catg[np.array([mod_of[i] == mod for i in catg])]
                nfo = run_window(B, cat, t0, [2, 4], rng, res, ("S1", mod), variant, scope_all)
                info[(variant, ("S1", mod), t0)] = nfo
            # S2: all six courses pooled
            nfo = run_window(B, catg, t0, [4, 8, 16], rng, res, ("S2", "pooled"), variant, allidx)
            info[(variant, ("S2", "pooled"), t0)] = nfo
            P(f"[t0={t0}] pooled catalog R={nfo['R']} edges={nfo['edges']} "
              f"top5 share={nfo['top5']:.3f} top1 share={nfo['top1']:.3f} "
              f"post-t0-resource share of eval load={nfo['newshare']:.3f}  "
              f"(per-course R/edges/top5: " +
              ", ".join(f"{m}:{info[(variant, ('S1', m), t0)]['R']}/"
                        f"{info[(variant, ('S1', m), t0)]['edges']}/"
                        f"{info[(variant, ('S1', m), t0)]['top5']:.2f}" for m in MODULES) + ")")

        S1 = [("S1", m) for m in MODULES]
        S2 = [("S2", "pooled")]

        for tag, scopes, ms in [("S1 (per course, averaged over the 6 courses)", S1, [2, 4]),
                                ("S2 (all six courses pooled)", S2, [4, 8, 16])]:
            for m in ms:
                P(f"\n=== {variant} | {tag} | m={m} | test windows t0={TST_T0} ===")
                P(f"{'rule':>12} {'ls':>3} | {'imb mean':>9} {'imb q95':>8} {'peak/L':>7} "
                  f"{'frac>1.5':>9} {'ls moves':>9}")
                for lab in LABELS:
                    for ls in ([0, 1] if lab in LS_LABELS else [0]):
                        P(f"{lab:>12} {ls:>3} | "
                          f"{agg(res, variant, scopes, m, TST_T0, lab, ls, 'mean'):>9.4f} "
                          f"{agg(res, variant, scopes, m, TST_T0, lab, ls, 'q95'):>8.4f} "
                          f"{agg(res, variant, scopes, m, TST_T0, lab, ls, 'peak'):>7.4f} "
                          f"{agg(res, variant, scopes, m, TST_T0, lab, ls, 'frac'):>9.3f} "
                          f"{agg(res, variant, scopes, m, TST_T0, lab, ls, 'moves'):>9.1f}")

        # ---- bootstrap at the configuration picked on the dev windows
        P(f"\n=== {variant} | paired bootstrap 95% CI, {NBOOT} resamples over (scope unit, window) "
          f"blocks; test windows {TST_T0}; (rho,kappa) picked on {DEV_T0} ===")
        for tag, scopes, ms, blockmode in [("S1", S1, [2, 4], "perm"), ("S2", S2, [4, 8, 16], "poolm")]:
            for ls in (0, 1):
                if blockmode == "perm":
                    groups = [([m], [(sk, m, t0) for sk in scopes for t0 in TST_T0]) for m in ms]
                else:
                    groups = [(ms, [(sk, m, t0) for sk in scopes for m in ms for t0 in TST_T0])]
                for (mlist, blocks) in groups:
                    mref = mlist[0]
                    g = pick_best(res, variant, scopes, mref, "G", ls)
                    g0 = pick_best(res, variant, scopes, mref, "G0", ls)
                    gs = pick_best(res, variant, scopes, mref, "GS", ls)
                    e = pick_best(res, variant, scopes, mref, "E", ls)
                    P(f"-- {tag} m={mlist} ls={ls}  picked: G={g}  G0={g0}  GS={gs}  E={e}  "
                      f"blocks={len(blocks)}")
                    P(f"{'comparison':>12} | {'d imb mean':>10} {'95% CI':>22} | "
                      f"{'d imb q95':>10} {'95% CI':>22}")
                    for name, la, lb in [("G-L", g, "L"), ("G-G0", g, g0), ("G-GS", g, gs),
                                         ("G-E", g, e), ("E-L", e, "L")]:
                        r1 = boot_ci(res, variant, blocks, la, lb, ls, "mean")
                        r2 = boot_ci(res, variant, blocks, la, lb, ls, "q95")
                        P(f"{name:>12} | {r1[0]:>10.5f} [{r1[1]:>9.5f},{r1[2]:>9.5f}] | "
                          f"{r2[0]:>10.5f} [{r2[1]:>9.5f},{r2[2]:>9.5f}]")

        # ---- per-course detail on mean imbalance at the picked G vs L (m=4)
        P(f"\n=== {variant} | per-course mean imbalance, m=4, test windows, ls=0 ===")
        gp = pick_best(res, variant, S1, 4, "G", 0)
        P(f"{'course':>8} |" + "".join(f"{l:>12}" for l in ["H", "L", gp, "O", "LB"]))
        for mod in MODULES:
            P(f"{mod:>8} |" + "".join(
                f"{agg(res, variant, [('S1', mod)], 4, TST_T0, l, 0, 'mean'):>12.4f}"
                for l in ["H", "L", gp, "O", "LB"]))

        for fld, nm in [("top5", "top-5 share"), ("top1", "top-1 share"),
                        ("newshare", "post-t0-resource share")]:
            P(f"[concentration] {nm} of evaluation-window load, mean over test windows: "
              f"S2 pooled={np.mean([info[(variant, ('S2','pooled'), t)][fld] for t in TST_T0]):.3f}; "
              + ", ".join(f"{m}={np.mean([info[(variant, ('S1', m), t)][fld] for t in TST_T0]):.3f}"
                          for m in MODULES))
        P(f"[variant runtime] {time.time() - t0v:.1f}s")

    P(f"\n[total runtime] {time.time() - T_START:.1f}s")
    with open("out_placement.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
