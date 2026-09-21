"""OULAD deadline-kernel falsification pre-check.

Mechanistic hypothesis under test (from the problem scenario):
    platform load = baseline + SUPERPOSITION of anticipatory deadline kernels,
    r_cp(t) = b_cp(t) + sum_a w_a^gamma * kappa_{type(a)}(D_a - t)
with kappa a non-negative kernel over days-to-deadline u = D_a - t, SHARED across
course-presentations per assessment type, and b_cp(t) = level_cp * s(dow) * trend(t/len)
with s and trend shared and only level_cp course-specific.

If this small structural model transfers to an unseen course-presentation about as
well as a generic gradient-boosting model with the same calendar information, the
scenario-derived structure is real.  If it is clearly worse, or the fitted kernels are
unstable across course-presentations, it is not.

DEVELOPMENT DATA ONLY: code_presentation in {2013B, 2013J}.  2014B / 2014J rows are
dropped at read time and never enter any array (asserted).

Units: (cp, day t), t in 0..240.  y = total clicks of the cp that day.
n_t = currently registered students.  r = y / n_t = per-student load.
"""
import os
import sys
import time

import numpy as np
import pandas as pd
from scipy.optimize import nnls, lsq_linear
from scipy.stats import spearmanr
import lightgbm as lgb

T0 = time.time()
DATA = r"<repo-root>\data"
PRES = ("2013B", "2013J")
BANNED = ("2014B", "2014J")
SEED = 20260918
LGB_SEEDS = [0, 1, 2]          # same seeds as load_forecast_test.py
NBOOT = 2000

DMIN, DMAX = -30, 240
OFF = -DMIN
NDAY = DMAX - DMIN + 1
NLAG = 14                      # same as load_forecast_test.py
VAL_LO, VAL_HI = 141, 160      # early-stopping slice, same as load_forecast_test.py

EV_LO, EV_HI = 15, 240         # evaluation / fitting days
LVL_LO, LVL_HI = 0, 13         # days used to set the level of an unseen cp
UMIN, UMAX = -3, 21            # kernel support, u = D_a - t
NB = UMAX - UMIN + 1           # 25 piecewise-constant bins
KNOTS = np.linspace(0.0, 1.05, 6)
NITER = 10                     # alternating-NNLS sweeps
GAMMAS = [0.0, 0.5, 1.0]

np.random.seed(SEED)


def log(m):
    print(f"[{time.time() - T0:7.1f}s] {m}", file=sys.stderr, flush=True)


# ====================================================================== load
# (loading mirrors load_forecast_test.py; only cp-level daily clicks are needed)
clk_cp = {}
for ch in pd.read_csv(f"{DATA}/studentVle.csv",
                      usecols=["code_module", "code_presentation", "date", "sum_click"],
                      dtype={"date": np.int32, "sum_click": np.int32},
                      chunksize=2_000_000):
    ch = ch[ch.code_presentation.isin(PRES)]
    ch = ch[(ch.date >= DMIN) & (ch.date <= DMAX)]
    if not len(ch):
        continue
    assert not ch.code_presentation.isin(BANNED).any()
    ch["cp"] = ch.code_module + "_" + ch.code_presentation
    for (cp, d), v in ch.groupby(["cp", "date"], observed=True).sum_click.sum().items():
        clk_cp.setdefault(cp, np.zeros(NDAY))[d + OFF] += v
CPS = sorted(clk_cp)
log(f"clicks loaded, cps={len(CPS)}")

ass = pd.read_csv(f"{DATA}/assessments.csv")
ass = ass[ass.code_presentation.isin(PRES)].copy()
assert not ass.code_presentation.isin(BANNED).any()
ass["cp"] = ass.code_module + "_" + ass.code_presentation
ass["weight"] = ass.weight.fillna(0.0)
ass = ass[ass.date.notna()].copy()
ass["date"] = ass.date.astype(float)
TYPES = sorted(ass.assessment_type.unique())
TIDX = {t: i for i, t in enumerate(TYPES)}
NT = len(TYPES)

reg = pd.read_csv(f"{DATA}/studentRegistration.csv")
reg = reg[reg.code_presentation.isin(PRES)].copy()
assert not reg.code_presentation.isin(BANNED).any()
reg["cp"] = reg.code_module + "_" + reg.code_presentation

crs = pd.read_csv(f"{DATA}/courses.csv")
crs = crs[crs.code_presentation.isin(PRES)].copy()
crs["cp"] = crs.code_module + "_" + crs.code_presentation
CLEN = dict(zip(crs.cp, crs.module_presentation_length))

days = np.arange(DMIN, DMAX + 1)
NREG, Y, R = {}, {}, {}
for cp in CPS:
    q = reg[reg.cp == cp]
    rd = q.date_registration.fillna(-400).to_numpy(dtype=float)
    ud = q.date_unregistration.to_numpy(dtype=float)
    n = np.array([np.sum(rd <= t) - np.nansum(ud <= t) for t in days], dtype=float)
    NREG[cp] = np.maximum(n, 1.0)
    Y[cp] = np.maximum(clk_cp[cp], 0.0)
    R[cp] = Y[cp] / NREG[cp]
ASS = {cp: ass[ass.cp == cp].sort_values("date") for cp in CPS}
log("registration / assessments built")


# ============================================================ design helpers
def hat_basis(p):
    B = np.zeros((len(p), len(KNOTS)))
    for k in range(len(KNOTS)):
        v = np.zeros(len(p))
        if k > 0:
            lo = KNOTS[k - 1]
            m = (p >= lo) & (p <= KNOTS[k]); v[m] = (p[m] - lo) / (KNOTS[k] - lo)
        else:
            v[p <= KNOTS[k]] = 1.0
        if k < len(KNOTS) - 1:
            hi = KNOTS[k + 1]
            m = (p > KNOTS[k]) & (p <= hi); v[m] = (hi - p[m]) / (hi - KNOTS[k])
        else:
            v[p > KNOTS[k]] = 1.0
        B[:, k] = v
    return B


def kmat(cp, tt, gamma):
    """(len(tt), NT*NB) matrix of sum_a w_a^gamma 1[bin(D_a - t) = j] per type."""
    M = np.zeros((len(tt), NT * NB))
    a = ASS[cp]
    for D, w, ty in zip(a.date, a.weight, a.assessment_type):
        u = D - tt
        m = (u >= UMIN) & (u <= UMAX)
        if not m.any():
            continue
        col = TIDX[ty] * NB + (u[m] - UMIN).astype(int)
        M[np.where(m)[0], col] += (max(w, 0.0) ** gamma) if gamma > 0 else 1.0
    return M


DAYS_EV = np.arange(EV_LO, EV_HI + 1)
DAYS_LV = np.arange(LVL_LO, LVL_HI + 1)
DOW_EV = (DAYS_EV % 7).astype(int)
DOW_LV = (DAYS_LV % 7).astype(int)
PH = {cp: np.clip(DAYS_EV / float(CLEN[cp]), 0, 1.05) for cp in CPS}
PH_LV = {cp: np.clip(DAYS_LV / float(CLEN[cp]), 0, 1.05) for cp in CPS}
B_EV = {cp: hat_basis(PH[cp]) for cp in CPS}
B_LV = {cp: hat_basis(PH_LV[cp]) for cp in CPS}
KEV = {(cp, g): kmat(cp, DAYS_EV, g) for cp in CPS for g in GAMMAS}
KLV = {(cp, g): kmat(cp, DAYS_LV, g) for cp in CPS for g in GAMMAS}
D_EYE = np.eye(7)[DOW_EV]
RE = {cp: R[cp][DAYS_EV + OFF] for cp in CPS}
RL = {cp: R[cp][DAYS_LV + OFF] for cp in CPS}
EPS = {cp: max(1e-6, 1e-3 * np.median(RE[cp])) for cp in CPS}


# ======================================================= mechanistic model M
def fit_add(train, gamma):
    """Alternating NNLS for r = level_cp * s(dow) * trend(p) + K @ kappa."""
    n = len(train)
    rows = [len(DAYS_EV)] * n
    y = np.concatenate([RE[cp] for cp in train])
    K = np.vstack([KEV[(cp, gamma)] for cp in train])
    Bs = np.vstack([B_EV[cp] for cp in train])
    Ds = np.vstack([D_EYE] * n)
    cpI = np.zeros((len(y), n))
    o = 0
    for i, cp in enumerate(train):
        cpI[o:o + rows[i], i] = 1.0
        o += rows[i]
    s = np.ones(7)
    c = np.ones(len(KNOTS))
    lev = np.array([np.median(RE[cp]) for cp in train])
    for _ in range(NITER):
        tr = Bs @ c
        g = (Ds @ s) * tr
        A = np.hstack([cpI * g[:, None], K])
        x, _ = nnls(A, y)
        lev, kap = x[:n], x[n:]
        b = (cpI @ lev) * tr
        A = np.hstack([Ds * b[:, None], K])
        x, _ = nnls(A, y)
        s, kap = x[:7], x[7:]
        m = s.mean()
        if m > 0:
            s = s / m; lev = lev * m
        b = (cpI @ lev) * (Ds @ s)
        A = np.hstack([Bs * b[:, None], K])
        x, _ = nnls(A, y)
        c, kap = x[:len(KNOTS)], x[len(KNOTS):]
        tr = Bs @ c
        m = tr.mean()
        if m > 0:
            c = c / m; lev = lev * m
    return dict(kind="add", s=s, c=c, kappa=kap, gamma=gamma,
                lev=dict(zip(train, lev)))


def fit_mult(train, gamma):
    """log r = L_cp + S(dow) + T(p) + K @ kappa ; kappa >= 0, rest free."""
    n = len(train)
    y = np.concatenate([np.log(np.maximum(RE[cp], EPS[cp])) for cp in train])
    K = np.vstack([KEV[(cp, gamma)] for cp in train])
    Bs = np.vstack([B_EV[cp] for cp in train])[:, 1:]
    Ds = np.vstack([D_EYE] * n)[:, 1:]
    cpI = np.zeros((len(y), n))
    for i in range(n):
        cpI[i * len(DAYS_EV):(i + 1) * len(DAYS_EV), i] = 1.0
    A = np.hstack([cpI, Ds, Bs, K])
    nf = n + 6 + len(KNOTS) - 1
    lo = np.concatenate([np.full(nf, -np.inf), np.zeros(NT * NB)])
    hi = np.full(A.shape[1], np.inf)
    res = lsq_linear(A, y, bounds=(lo, hi), max_iter=200, tol=1e-8)
    x = res.x
    return dict(kind="mult", s=np.concatenate([[0.0], x[n:n + 6]]),
                c=np.concatenate([[0.0], x[n + 6:nf]]), kappa=x[nf:], gamma=gamma,
                lev=dict(zip(train, x[:n])))


def level_from_first14(mod, cp):
    kp = KLV[(cp, mod["gamma"])] @ mod["kappa"]
    if mod["kind"] == "add":
        g = mod["s"][DOW_LV] * (B_LV[cp] @ mod["c"])
        num = float(np.sum(g * (RL[cp] - kp)))
        den = float(np.sum(g * g))
        return max(num / den, 1e-8) if den > 0 else 1e-8
    z = np.log(np.maximum(RL[cp], EPS[cp])) - mod["s"][DOW_LV] - (B_LV[cp] @ mod["c"]) - kp
    return float(np.mean(z))


def predict(mod, cp, lev=None):
    if lev is None:
        lev = mod["lev"][cp]
    kp = KEV[(cp, mod["gamma"])] @ mod["kappa"]
    if mod["kind"] == "add":
        return np.maximum(lev * mod["s"][DOW_EV] * (B_EV[cp] @ mod["c"]) + kp, 0.0)
    return np.exp(lev + mod["s"][DOW_EV] + (B_EV[cp] @ mod["c"]) + kp)


def loo_pred(kind, train, hold):
    """gamma chosen by inner leave-one-cp-out on the training cps only."""
    fit = fit_add if kind == "add" else fit_mult
    best, bg = None, None
    for g in GAMMAS:
        e = []
        for icp in train:
            itr = [c for c in train if c != icp]
            m = fit(itr, g)
            p = predict(m, icp, level_from_first14(m, icp)) * NREG[icp][DAYS_EV + OFF]
            e.append((np.log1p(p) - np.log1p(Y[icp][DAYS_EV + OFF])) ** 2)
        v = float(np.sqrt(np.mean(np.concatenate(e))))
        if best is None or v < best:
            best, bg = v, g
    m = fit(train, bg)
    return predict(m, hold, level_from_first14(m, hold)) * NREG[hold][DAYS_EV + OFF], bg, m


# ==================================================================== c1, c2
def c1_pred(train, hold):
    """level * shared dow profile only."""
    num = np.zeros(7); den = np.zeros(7)
    for cp in train:
        z = RE[cp] / max(np.mean(RE[cp]), 1e-9)
        for d in range(7):
            m = DOW_EV == d
            num[d] += z[m].sum(); den[d] += m.sum()
    s = num / np.maximum(den, 1)
    s = s / s.mean()
    lev = float(np.mean(RL[hold]) / max(np.mean(s[DOW_LV]), 1e-9))
    return lev * s[DOW_EV] * NREG[hold][DAYS_EV + OFF]


PARAMS = dict(objective="regression", metric="rmse", learning_rate=0.05,
              num_leaves=31, min_data_in_leaf=20, feature_fraction=0.8,
              bagging_fraction=0.8, bagging_freq=1, verbosity=-1,
              deterministic=True, num_threads=4)


def cal_feats(cp):
    a = ASS[cp]
    due = a.date.to_numpy(dtype=float)
    wts = a.weight.to_numpy(dtype=float)
    tps = np.array([TIDX[x] for x in a.assessment_type], dtype=float)
    d2n = np.full(len(DAYS_EV), 999.0); dsl = np.full(len(DAYS_EV), 999.0)
    nxw = np.zeros(len(DAYS_EV)); nxt = np.full(len(DAYS_EV), float(NT))
    n7 = np.zeros(len(DAYS_EV))
    for i, t in enumerate(DAYS_EV):
        nx = np.where(due >= t)[0]; pv = np.where(due < t)[0]
        if len(nx):
            d2n[i] = due[nx[0]] - t; nxw[i] = wts[nx[0]]; nxt[i] = tps[nx[0]]
        if len(pv):
            dsl[i] = t - due[pv[-1]]
        n7[i] = np.sum((due >= t) & (due <= t + 6))
    return pd.DataFrame(dict(days_to_next_due=d2n, days_since_last_due=dsl,
                             next_due_weight=nxw, next_due_type=nxt, n_due_next7=n7,
                             dow=DOW_EV.astype(float), phase=PH[cp], cp=cp,
                             day=DAYS_EV))


CALF = pd.concat([cal_feats(cp) for cp in CPS], ignore_index=True)
LVL14 = {cp: max(float(np.mean(RL[cp])), 1e-9) for cp in CPS}
CALF["ylog"] = np.concatenate([np.log(np.maximum(RE[cp], EPS[cp]) / LVL14[cp]) for cp in CPS])
C2COLS = ["days_to_next_due", "days_since_last_due", "next_due_weight", "next_due_type",
          "n_due_next7", "dow", "phase"]


def c2_pred(train, hold):
    m_tr = CALF.cp.isin(train).to_numpy() & ~((CALF.day >= VAL_LO) & (CALF.day <= VAL_HI)).to_numpy()
    m_va = CALF.cp.isin(train).to_numpy() & ((CALF.day >= VAL_LO) & (CALF.day <= VAL_HI)).to_numpy()
    m_pr = (CALF.cp == hold).to_numpy()
    X = CALF[C2COLS]; yv = CALF.ylog.to_numpy()
    out = np.zeros(int(m_pr.sum()))
    for s in LGB_SEEDS:
        p = dict(PARAMS, seed=s, bagging_seed=s, feature_fraction_seed=s, data_random_seed=s)
        dtr = lgb.Dataset(X[m_tr], label=yv[m_tr], categorical_feature=["next_due_type"],
                          free_raw_data=False)
        dva = lgb.Dataset(X[m_va], label=yv[m_va], categorical_feature=["next_due_type"],
                          reference=dtr, free_raw_data=False)
        b = lgb.train(p, dtr, num_boost_round=500, valid_sets=[dva],
                      callbacks=[lgb.early_stopping(30, verbose=False)])
        out += b.predict(X[m_pr], num_iteration=b.best_iteration) / len(LGB_SEEDS)
    return np.exp(out) * LVL14[hold] * NREG[hold][DAYS_EV + OFF]


# ------------------------------------------- F0 / F1 (lag models, reference)
CAL_COLS_F = ["days_to_next_due", "days_since_last_due", "next_due_weight", "next_due_type",
              "n_due_next7", "cum_weight_passed", "pres_length", "days_remaining"]
F0_COLS = [f"lag{j + 1}" for j in range(NLAG)] + ["lag_mean", "lag_max", "dow", "day"]
FSET = {"F0": F0_COLS, "F1": F0_COLS + CAL_COLS_F}


def build_f(h):
    rows, ys, meta = [], [], []
    for cp in CPS:
        arr = Y[cp]
        L = np.stack([np.log1p(arr[DAYS_EV - h - j + OFF]) for j in range(NLAG)], 1)
        d = {f"lag{j + 1}": L[:, j] for j in range(NLAG)}
        d["lag_mean"] = L.mean(1); d["lag_max"] = L.max(1)
        d["dow"] = DOW_EV.astype(float); d["day"] = DAYS_EV.astype(float)
        cf = CALF[CALF.cp == cp].reset_index(drop=True)
        a = ASS[cp]
        due = a.date.to_numpy(dtype=float); wts = a.weight.to_numpy(dtype=float)
        for k in ["days_to_next_due", "days_since_last_due", "next_due_weight",
                  "next_due_type", "n_due_next7"]:
            d[k] = cf[k].to_numpy()
        d["cum_weight_passed"] = np.array([wts[due <= t].sum() for t in DAYS_EV], dtype=float)
        d["pres_length"] = np.full(len(DAYS_EV), float(CLEN[cp]))
        d["days_remaining"] = float(CLEN[cp]) - DAYS_EV
        rows.append(pd.DataFrame(d))
        ys.append(np.log1p(arr[DAYS_EV + OFF]))
        meta.append(pd.DataFrame(dict(cp=cp, day=DAYS_EV)))
    return (pd.concat(rows, ignore_index=True), np.concatenate(ys),
            pd.concat(meta, ignore_index=True))


def f_pred(X, y, M, mod, train, hold):
    m_tr = M.cp.isin(train).to_numpy() & ~((M.day >= VAL_LO) & (M.day <= VAL_HI)).to_numpy()
    m_va = M.cp.isin(train).to_numpy() & ((M.day >= VAL_LO) & (M.day <= VAL_HI)).to_numpy()
    m_pr = (M.cp == hold).to_numpy()
    Xs = X[FSET[mod]]
    cat = ["next_due_type"] if "next_due_type" in FSET[mod] else []
    out = np.zeros(int(m_pr.sum()))
    for s in LGB_SEEDS:
        p = dict(PARAMS, seed=s, bagging_seed=s, feature_fraction_seed=s, data_random_seed=s)
        dtr = lgb.Dataset(Xs[m_tr], label=y[m_tr], categorical_feature=cat, free_raw_data=False)
        dva = lgb.Dataset(Xs[m_va], label=y[m_va], categorical_feature=cat, reference=dtr,
                          free_raw_data=False)
        b = lgb.train(p, dtr, num_boost_round=500, valid_sets=[dva],
                      callbacks=[lgb.early_stopping(30, verbose=False)])
        out += b.predict(Xs[m_pr], num_iteration=b.best_iteration) / len(LGB_SEEDS)
    return np.maximum(np.expm1(out), 0.0)


# =================================================================== PART 1
out = []
W = out.append
W("=" * 88)
W("OULAD deadline-kernel pre-check | dev presentations 2013B+2013J only "
  f"({len(CPS)} course-presentations)")
W(f"cps: {', '.join(CPS)}")
W(f"assessment types with a due date: {TYPES}; kernel support u=D-t in [{UMIN},{UMAX}], "
  f"{NB} unit bins")
W(f"unit = (cp, day); y = total clicks; n_t = registered students; r = y/n_t; "
  f"eval days {EV_LO}..{EV_HI}")
W("=" * 88)

RMED = {cp: float(np.median(R[cp][0 + OFF:DMAX + OFF + 1])) for cp in CPS}
UU = np.arange(UMAX, UMIN - 1, -1)          # 21 .. -3 (before -> after)
curves = {}                                  # (type, cp) -> array over UU
peakrows = []
for ty in TYPES:
    for cp in CPS:
        a = ASS[cp][ASS[cp].assessment_type == ty]
        if not len(a):
            continue
        acc = np.full((len(a), len(UU)), np.nan)
        for i, (D, w) in enumerate(zip(a.date, a.weight)):
            t = D - UU
            ok = (t >= 0) & (t <= DMAX)
            acc[i, ok] = R[cp][t[ok].astype(int) + OFF] / max(RMED[cp], 1e-12)
            win = (UU >= 0) & (UU <= 6) & ok
            if win.any():
                peakrows.append(dict(cp=cp, ty=ty, w=float(w), D=float(D),
                                     peak=float(np.nanmax(acc[i, win]))))
        with np.errstate(invalid="ignore"):
            curves[(ty, cp)] = np.nanmean(acc, 0)

W("\n### PART 1  event study: r / (cp median r) vs u = days-to-deadline, mean over cps")
W(f"{'type':>5} " + " ".join(f"{u:>5d}" for u in UU))
P1 = {}
for ty in TYPES:
    ks = [k for k in curves if k[0] == ty]
    if not ks:
        continue
    Mx = np.vstack([curves[k] for k in ks])
    mu = np.nanmean(Mx, 0); sd = np.nanstd(Mx, 0)
    P1[ty] = (Mx, mu, sd, [k[1] for k in ks])
    W(f"{ty:>5} " + " ".join(f"{v:>5.2f}" for v in mu))
    W(f"{'sd':>5} " + " ".join(f"{v:>5.2f}" for v in sd))

W(f"\n{'type':>5} {'ncp':>4} {'nass':>5} {'peak_u':>7} {'peak':>6} {'contig>1.1x':>12} "
  f"{'nu>1.1x':>8} {'post(u=-1..-3)':>15} {'meanCorr':>9} {'minCorr':>8}")
for ty in TYPES:
    if ty not in P1:
        continue
    Mx, mu, sd, cl = P1[ty]
    pu = int(UU[np.nanargmax(mu)])
    j = int(np.where(UU == 0)[0][0])
    rise = 0
    while j - rise >= 0 and UU[j - rise] <= UMAX and mu[j - rise] > 1.1:
        rise += 1
    nab = int(np.sum((mu > 1.1) & (UU >= 0)))
    post = float(np.nanmean(mu[(UU <= -1) & (UU >= -3)]))
    cc = []
    for i in range(len(cl)):
        for j in range(i + 1, len(cl)):
            m = ~np.isnan(Mx[i]) & ~np.isnan(Mx[j])
            if m.sum() > 5:
                cc.append(float(np.corrcoef(Mx[i][m], Mx[j][m])[0, 1]))
    nass = int(sum(1 for _ in ASS if True) * 0) + int(
        sum(len(ASS[c][ASS[c].assessment_type == ty]) for c in CPS))
    W(f"{ty:>5} {len(cl):>4} {nass:>5} {pu:>7} {np.nanmax(mu):>6.2f} {rise:>12} {nab:>8} "
      f"{post:>15.2f} {np.mean(cc) if cc else float('nan'):>9.3f} "
      f"{np.min(cc) if cc else float('nan'):>8.3f}")

PR = pd.DataFrame(peakrows)
W(f"\n{'group':>8} {'n':>4} {'spearman(weight, peak)':>24} {'p':>8}")
for g, q in [("ALL", PR)] + [(t, PR[PR.ty == t]) for t in TYPES]:
    if len(q) > 3 and q.w.nunique() > 1:
        rho, pv = spearmanr(q.w, q.peak)
        W(f"{g:>8} {len(q):>4} {rho:>24.3f} {pv:>8.3f}")
    else:
        W(f"{g:>8} {len(q):>4} {'n/a':>24} {'':>8}")
log("part 1 done")

# =================================================================== PART 2
PRED = {}
GSEL = {}
Xf, yf, Mf = {}, {}, {}
for h in (3, 7):
    Xf[h], yf[h], Mf[h] = build_f(h)

rows = []
for cp in CPS:
    tr = [c for c in CPS if c != cp]
    d = dict(cp=cp, day=DAYS_EV, y=Y[cp][DAYS_EV + OFF], n=NREG[cp][DAYS_EV + OFF])
    for kind, nm in [("add", "M-add"), ("mult", "M-mult")]:
        p, g, _ = loo_pred(kind, tr, cp)
        d[nm] = p
        GSEL[(nm, cp)] = g
    d["c1"] = c1_pred(tr, cp)
    d["c2"] = c2_pred(tr, cp)
    for h in (3, 7):
        for mod in ("F0", "F1"):
            d[f"{mod}h{h}"] = f_pred(Xf[h], yf[h], Mf[h], mod, tr, cp)
    rows.append(pd.DataFrame(d))
    log(f"loo {cp} done")
P = pd.concat(rows, ignore_index=True)

# deadline-window flag: some assessment with u in [0,6]
inwin = np.zeros(len(P), bool)
nwin = np.zeros(len(P))
for cp in CPS:
    m = (P.cp == cp).to_numpy()
    cnt = np.zeros(len(DAYS_EV))
    for D in ASS[cp].date:
        cnt += ((D - DAYS_EV >= 0) & (D - DAYS_EV <= 6)).astype(float)
    nwin[m] = cnt
    inwin[m] = cnt > 0
P["nwin"] = nwin
P["inwin"] = inwin

MODS = ["M-add", "M-mult", "c1", "c2", "F0h3", "F1h3", "F0h7", "F1h7"]


def mets(sub, mcol):
    e = np.log1p(sub[mcol].to_numpy()) - np.log1p(sub.y.to_numpy())
    return float(np.sqrt(np.mean(e ** 2))), float(np.mean(np.abs(sub[mcol] - sub.y)))


def peakf1(mcol, mode):
    tp = fp = fn = 0.0
    for cp in CPS:
        q = P[P.cp == cp]
        k = int(round(0.10 * len(q)))
        yy = q.y.to_numpy(); pp = q[mcol].to_numpy()
        act = np.zeros(len(q), bool); act[np.argsort(-yy)[:k]] = True
        if mode == "rank":
            prd = np.zeros(len(q), bool); prd[np.argsort(-pp)[:k]] = True
        else:
            thr = np.quantile(yy, 0.90); prd = pp > thr
        tp += np.sum(act & prd); fp += np.sum(~act & prd); fn += np.sum(act & ~prd)
    pr = tp / (tp + fp) if tp + fp else 0.0
    rc = tp / (tp + fn) if tp + fn else 0.0
    return (2 * pr * rc / (pr + rc)) if pr + rc else 0.0


W("\n### PART 2  Evaluation A: leave-one-cp-out, predict days 15..240 of the held-out cp")
W("    M / c1 / c2 use NO load of the held-out cp after day 14 (level only, days 0..13);")
W("    F0/F1 additionally use that cp's own lagged load up to t-h (reference, easier task).")
W(f"{'model':>7} {'logRMSE':>9} {'MAE_raw':>10} {'logRMSE_dl':>11} {'MAE_dl':>10} "
  f"{'peakF1_rank':>12} {'peakF1_abs':>11}")
for m in MODS:
    a1, a2 = mets(P, m)
    b1, b2 = mets(P[P.inwin], m)
    W(f"{m:>7} {a1:>9.4f} {a2:>10.1f} {b1:>11.4f} {b2:>10.1f} "
      f"{peakf1(m, 'rank'):>12.3f} {peakf1(m, 'abs'):>11.3f}")
W(f"gamma chosen by inner LOO: M-add {[GSEL[('M-add', c)] for c in CPS]}, "
  f"M-mult {[GSEL[('M-mult', c)] for c in CPS]} (cp order {CPS})")


def boot(a, b):
    ea = (np.log1p(P[a].to_numpy()) - np.log1p(P.y.to_numpy())) ** 2
    eb = (np.log1p(P[b].to_numpy()) - np.log1p(P.y.to_numpy())) ** 2
    keys = sorted(set(zip(P.cp, (P.day // 7).astype(int))))
    kidx = {k: i for i, k in enumerate(keys)}
    idx = np.array([kidx[k] for k in zip(P.cp, (P.day // 7).astype(int))])
    o = np.argsort(idx, kind="mergesort")
    ea, eb, idx = ea[o], eb[o], idx[o]
    bnd = np.searchsorted(idx, np.arange(len(keys) + 1))
    sa = np.add.reduceat(ea, bnd[:-1]); sb = np.add.reduceat(eb, bnd[:-1])
    cnt = np.diff(bnd).astype(float)
    rng = np.random.default_rng(SEED + 7)
    pick = rng.integers(0, len(keys), size=(NBOOT, len(keys)))
    n = cnt[pick].sum(1)
    d = np.sqrt(sa[pick].sum(1) / n) - np.sqrt(sb[pick].sum(1) / n)
    pt = float(np.sqrt(sa.sum() / cnt.sum()) - np.sqrt(sb.sum() / cnt.sum()))
    return pt, float(np.quantile(d, .025)), float(np.quantile(d, .975))


W(f"\n### paired block bootstrap on log1p RMSE, {NBOOT} resamples over (cp, week) blocks "
  "(negative = first model wins)")
W(f"{'contrast':>16} {'dRMSE':>9} {'95%lo':>9} {'95%hi':>9}  verdict")
for a, b in [("M-add", "c1"), ("M-add", "c2"), ("M-add", "F1h7"), ("M-add", "F0h7"),
             ("M-mult", "c2"), ("M-mult", "M-add"), ("M-add", "F1h3")]:
    p_, lo, hi = boot(a, b)
    W(f"{a + ' - ' + b:>16} {p_:>9.4f} {lo:>9.4f} {hi:>9.4f}  "
      f"{'CI excludes 0' if (lo > 0 or hi < 0) else 'CI covers 0'}")

W("\n### Evaluation B: superposition (observed / predicted, M-add LOO predictions)")
W(f"{'stratum':>28} {'ndays':>6} {'mean_ratio':>11} {'median':>8}")
for nm, m in [("no assessment in u=[0,6]", (P.nwin == 0).to_numpy()),
              ("exactly 1 assessment", (P.nwin == 1).to_numpy()),
              (">=2 assessments (overlap)", (P.nwin >= 2).to_numpy())]:
    q = P[m]
    if not len(q):
        W(f"{nm:>28} {0:>6}")
        continue
    ra = q.y.to_numpy() / np.maximum(q["M-add"].to_numpy(), 1e-9)
    W(f"{nm:>28} {len(q):>6} {np.mean(ra):>11.3f} {np.median(ra):>8.3f}")

J = [c for c in CPS if c.endswith("2013J")]
ag = P[P.cp.isin(J)].groupby("day").agg(y=("y", "sum"), p=("M-add", "sum"),
                                        ncp=("nwin", lambda v: int((v > 0).sum())))
W(f"\nplatform total over {len(J)} 2013J cps (deadlines of different modules overlapping)")
W(f"{'stratum':>28} {'ndays':>6} {'mean_ratio':>11} {'median':>8}")
for nm, m in [("0-1 module in deadline win", (ag.ncp <= 1).to_numpy()),
              ("2 modules overlapping", (ag.ncp == 2).to_numpy()),
              (">=3 modules overlapping", (ag.ncp >= 3).to_numpy())]:
    q = ag[m]
    if not len(q):
        W(f"{nm:>28} {0:>6}")
        continue
    ra = q.y.to_numpy() / np.maximum(q.p.to_numpy(), 1e-9)
    W(f"{nm:>28} {len(q):>6} {np.mean(ra):>11.3f} {np.median(ra):>8.3f}")
log("part 2 done")

# =================================================================== PART 3
GFULL = max(set(GSEL[("M-add", c)] for c in CPS),
            key=[GSEL[("M-add", c)] for c in CPS].count)
FULL = fit_add(CPS, GFULL)


def kap_of(train):
    return fit_add(train, GFULL)["kappa"]


B13 = [c for c in CPS if c.endswith("2013B")]
J13 = [c for c in CPS if c.endswith("2013J")]
kB, kJ = kap_of(B13), kap_of(J13)
W(f"\n### PART 3  kernel stability (M-add, gamma={GFULL} = modal inner-LOO choice)")
W(f"{'split':>22} {'ncp':>4} " + " ".join(f"{'mass_' + t:>10}" for t in TYPES))
for nm, cl, kk in [("all dev cps", CPS, FULL["kappa"]), ("2013B only", B13, kB),
                   ("2013J only", J13, kJ)]:
    W(f"{nm:>22} {len(cl):>4} " +
      " ".join(f"{kk[TIDX[t] * NB:(TIDX[t] + 1) * NB].sum():>10.4f}" for t in TYPES))
W(f"\n{'pair':>22} {'type':>5} {'corr':>7} {'mass_ratio':>11}")
for t in TYPES:
    sl = slice(TIDX[t] * NB, (TIDX[t] + 1) * NB)
    a, b = kB[sl], kJ[sl]
    if a.sum() > 0 and b.sum() > 0:
        W(f"{'2013B vs 2013J':>22} {t:>5} {np.corrcoef(a, b)[0, 1]:>7.3f} "
          f"{a.sum() / b.sum():>11.3f}")
    else:
        W(f"{'2013B vs 2013J':>22} {t:>5} {'n/a (zero mass)':>19}")

MODULES = sorted(set(c.split("_")[0] for c in CPS))
KM = {}
for mo in MODULES:
    cl = [c for c in CPS if c.startswith(mo + "_")]
    KM[mo] = kap_of(cl)
W(f"\nper-module kernels vs the pooled all-cp kernel")
W(f"{'module':>7} {'ncp':>4} {'type':>5} {'corr_vs_pooled':>15} {'mass_ratio':>11}")
for mo in MODULES:
    cl = [c for c in CPS if c.startswith(mo + "_")]
    for t in TYPES:
        sl = slice(TIDX[t] * NB, (TIDX[t] + 1) * NB)
        a, b = KM[mo][sl], FULL["kappa"][sl]
        if a.sum() > 0 and b.sum() > 0:
            W(f"{mo:>7} {len(cl):>4} {t:>5} {np.corrcoef(a, b)[0, 1]:>15.3f} "
              f"{a.sum() / b.sum():>11.3f}")
        else:
            W(f"{mo:>7} {len(cl):>4} {t:>5} {'n/a':>15} {'n/a':>11}")
cc = []
for i in range(len(MODULES)):
    for j in range(i + 1, len(MODULES)):
        for t in TYPES:
            sl = slice(TIDX[t] * NB, (TIDX[t] + 1) * NB)
            a, b = KM[MODULES[i]][sl], KM[MODULES[j]][sl]
            if a.sum() > 0 and b.sum() > 0:
                cc.append(np.corrcoef(a, b)[0, 1])
W(f"pairwise between-module kernel correlation: n={len(cc)} mean={np.mean(cc):.3f} "
  f"min={np.min(cc):.3f} max={np.max(cc):.3f}")
log("part 3 done")

# =================================================================== PART 4
W("\n### PART 4  what-if (MODEL-BASED SANITY ONLY, NOT VALIDATED): shift each 2013J "
  "assessment by at most +/-3 days")


def plat_total(shift):
    tot = np.zeros(len(DAYS_EV))
    for cp in J13:
        a = ASS[cp]
        kp = np.zeros(len(DAYS_EV))
        for (idx, D, w, ty) in zip(a.index, a.date, a.weight, a.assessment_type):
            Dn = D + shift.get(idx, 0)
            u = Dn - DAYS_EV
            m = (u >= UMIN) & (u <= UMAX)
            col = TIDX[ty] * NB + (u[m] - UMIN).astype(int)
            kp[np.where(m)[0]] += ((max(w, 0.0) ** GFULL) if GFULL > 0 else 1.0) * \
                FULL["kappa"][col]
        b = FULL["lev"][cp] * FULL["s"][DOW_EV] * (B_EV[cp] @ FULL["c"])
        tot += np.maximum(b + kp, 0.0) * NREG[cp][DAYS_EV + OFF]
    return tot


def obj(tot):
    return float(np.mean(np.sort(tot)[-3:]))


IDS = [(cp, i) for cp in J13 for i in ASS[cp].index]
sh = {}
base = plat_total(sh)
cur = obj(base)
for _ in range(3):
    improved = False
    for cp, i in IDS:
        best = (cur, sh.get(i, 0))
        for d in range(-3, 4):
            s2 = dict(sh); s2[i] = d
            v = obj(plat_total(s2))
            if v < best[0] - 1e-9:
                best = (v, d)
        if best[1] != sh.get(i, 0):
            sh[i] = best[1]; cur = best[0]; improved = True
    if not improved:
        break
new = plat_total(sh)
nmoved = sum(1 for v in sh.values() if v != 0)
W(f"{'':>26} {'pred_peak':>12} {'pred_top3':>12}")
W(f"{'actual calendar':>26} {base.max():>12.0f} {obj(base):>12.0f}")
W(f"{'greedy +/-3d calendar':>26} {new.max():>12.0f} {obj(new):>12.0f}")
W(f"predicted peak reduction {100 * (1 - new.max() / base.max()):.1f}% "
  f"(top-3 mean {100 * (1 - obj(new) / obj(base)):.1f}%); "
  f"{nmoved} of {len(IDS)} assessments moved, shifts "
  f"{sorted(set(v for v in sh.values() if v != 0))}")
W("This is the model predicting its own counterfactual. No held-out evidence supports it.")

W(f"\nruntime {time.time() - T0:.1f}s")
txt = "\n".join(out)
print(txt)
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "out_deadline_kernel.txt"), "w", encoding="utf-8") as f:
    f.write(txt + "\n")
