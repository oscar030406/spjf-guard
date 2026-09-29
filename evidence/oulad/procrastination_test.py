"""OULAD PROCRASTINATION pre-check: is the deadline peak the SUM of individual
students' timing habits, so that knowing WHICH students are enrolled predicts the
next peak better than course-level history + calendar alone?

If yes, student -> course message passing (heterogeneous graph) is mechanistically
justified; if no, it is not.

DEVELOPMENT DATA ONLY: code_presentation in {2013B, 2013J}.  Rows with 2014B /
2014J are dropped at read time and never enter any array.

Part 1  descriptive: lead-time distribution, within-student consistency
        (Spearman on consecutive assessments, one-way ICC by student within cp),
        deadline-window click share of the "last-minute" vs "early" third of
        students (classified on PRIOR assessments only).
Part 2  assessment-level (unit = one TMA/CMA with a predecessor in its cp):
        course history alone vs course history + enrolled-cohort profile, on
        (i) peak ratio, (ii) last-2-day share of window clicks, (iii) last-2-day
        submissions / registered.  Ridge + LightGBM, leave-one-cp-out, paired
        bootstrap over assessments.  Control: profiles shuffled across students
        inside the cp (kills WHO, keeps the cohort mean).
Part 3  bottom-up vs top-down daily course load, h in {3,7}:
        top-down  = F1 of load_forecast_test.py (course lags to t-h + calendar)
        bottom-up = student-day LightGBM (own lags to t-h + calendar + profile)
                    summed over the cp's students
        bottom-up without the profile features isolates the profile
        hybrid    = top-down features + cohort-aggregated profile
        time split (train day<=140, test 141..240) and leave-one-cp-out.

PROFILE of a student at reference day R (same cp, assessments with due < R only):
  n submitted, mean / median lead time (lead = due - date_submitted, <0 = late),
  share submitted in the last 2 days or late (lead <= 1), share not submitted,
  click intensity ratio = mean daily clicks inside previous deadline windows /
  mean daily clicks outside them.
Deadline window W_a = days D_a-6 .. D_a.
"""
import os
import sys
import time

import numpy as np
import pandas as pd
import lightgbm as lgb
from scipy import stats

T0 = time.time()
DATA = r"<repo-root>\data"
CACHE = os.environ.get("OULAD_CACHE", "")
PRES = ("2013B", "2013J")
SEED = 20260918
LGB_SEEDS = [0, 1, 2]
NBOOT = 2000

DMIN, DMAX = -30, 300
OFF = -DMIN
NDAY = DMAX - DMIN + 1
WLEN = 7                       # deadline window W_a = D_a-6 .. D_a
TRN_HI = 140                   # part 3 time split
TST_LO, TST_HI = 141, 240
DAY_LO = 14
NLAG_S = 7                     # student lags
HORIZONS = [3, 7]
TRAIN_FRAC = 0.20              # student-day TRAINING subsample (never evaluation)
TRAIN_CAP = 350_000
NROUND_S = 300                 # fixed rounds, no early stopping (no leak into test)
NROUND_C = 400

np.random.seed(SEED)


def log(m):
    print(f"[{time.time() - T0:7.1f}s] {m}", file=sys.stderr, flush=True)


# ============================================================== load (dev only)
ass_all = pd.read_csv(f"{DATA}/assessments.csv")
ass_all = ass_all[ass_all.code_presentation.isin(PRES)].copy()
ass_all["cp"] = ass_all.code_module + "_" + ass_all.code_presentation
ass_all["weight"] = ass_all.weight.fillna(0.0)

reg = pd.read_csv(f"{DATA}/studentRegistration.csv")
reg = reg[reg.code_presentation.isin(PRES)].copy()
reg["cp"] = reg.code_module + "_" + reg.code_presentation

sa = pd.read_csv(f"{DATA}/studentAssessment.csv")
sa = sa[sa.is_banked != 1]
sa = sa.merge(ass_all[["id_assessment", "cp", "code_presentation", "date", "assessment_type"]],
              on="id_assessment", how="inner")
sa = sa[sa.code_presentation.isin(PRES)]

crs = pd.read_csv(f"{DATA}/courses.csv")
crs = crs[crs.code_presentation.isin(PRES)].copy()
crs["cp"] = crs.code_module + "_" + crs.code_presentation
CLEN = dict(zip(crs.cp, crs.module_presentation_length))

vle = pd.read_csv(f"{DATA}/vle.csv")
vle = vle[vle.code_presentation.isin(PRES)].copy()
vle["cp"] = vle.code_module + "_" + vle.code_presentation

cache_f = os.path.join(CACHE, "studay_2013.parquet") if CACHE else ""
if cache_f and os.path.exists(cache_f):
    sd = pd.read_parquet(cache_f)
    log(f"student-day cache {sd.shape}")
else:
    parts = []
    for ch in pd.read_csv(f"{DATA}/studentVle.csv",
                          usecols=["code_module", "code_presentation", "id_student",
                                   "date", "sum_click"],
                          dtype={"id_student": np.int64, "date": np.int32,
                                 "sum_click": np.int32},
                          chunksize=3_000_000):
        ch = ch[ch.code_presentation.isin(PRES)]
        ch = ch[(ch.date >= DMIN) & (ch.date <= DMAX)]
        if len(ch):
            ch["cp"] = ch.code_module + "_" + ch.code_presentation
            parts.append(ch.groupby(["cp", "id_student", "date"],
                                    observed=True).sum_click.sum().reset_index())
    sd = pd.concat(parts, ignore_index=True).groupby(
        ["cp", "id_student", "date"], as_index=False).sum_click.sum()
    del parts
    if cache_f:
        sd.to_parquet(cache_f, index=False)
    log(f"student-day built {sd.shape}")

CPS = sorted(sd.cp.unique())
NCP = len(CPS)

# ------------------------------------------------- per-cp student-day matrices
STU, SIDX, CLK, REGD, UNRD = {}, {}, {}, {}, {}
for cp in CPS:
    ids = np.union1d(sd.id_student[sd.cp == cp].unique(),
                     reg.id_student[reg.cp == cp].unique())
    STU[cp] = ids
    SIDX[cp] = {s: i for i, s in enumerate(ids)}
    M = np.zeros((len(ids), NDAY), dtype=np.float32)
    g = sd[sd.cp == cp]
    M[g.id_student.map(SIDX[cp]).to_numpy(), g.date.to_numpy() + OFF] = g.sum_click.to_numpy()
    CLK[cp] = M
    r = reg[reg.cp == cp]
    rd = np.full(len(ids), -1e9, dtype=np.float64)
    ud = np.full(len(ids), 1e9, dtype=np.float64)
    ri = r.id_student.map(SIDX[cp]).to_numpy()
    rd[ri] = r.date_registration.fillna(-1e9).to_numpy()
    ud[ri] = r.date_unregistration.fillna(1e9).to_numpy()
    REGD[cp], UNRD[cp] = rd, ud
CLK_CP = {cp: CLK[cp].sum(0) for cp in CPS}
log(f"cps={NCP} students={sum(len(STU[c]) for c in CPS)}")

# ------------------------------------------------------- TMA/CMA assessments
AS = {}
for cp in CPS:
    a = ass_all[(ass_all.cp == cp) & (ass_all.assessment_type != "Exam")
                & ass_all.date.notna()].sort_values("date")
    a = a[a.date <= CLEN[cp]]
    AS[cp] = a.reset_index(drop=True)

SUBD = {}
for cp in CPS:
    a = AS[cp]
    S = np.full((len(STU[cp]), len(a)), np.nan)
    m = sa[sa.cp == cp]
    pos = {ida: j for j, ida in enumerate(a.id_assessment)}
    m = m[m.id_assessment.isin(pos)]
    S[m.id_student.map(SIDX[cp]).to_numpy(), m.id_assessment.map(pos).to_numpy()] = \
        m.date_submitted.to_numpy()
    SUBD[cp] = S
LEAD = {cp: AS[cp].date.to_numpy(dtype=float)[None, :] - SUBD[cp] for cp in CPS}

PROF_NAMES = ["p_nsub", "p_mean_lead", "p_med_lead", "p_lastmin", "p_nosub", "p_clkratio"]
NPROF = len(PROF_NAMES)


def build_profiles(cp, lead_mat):
    """PROF[k] = (nstu, NPROF) using the first k assessments of cp only."""
    a = AS[cp]
    due = a.date.to_numpy(dtype=float)
    n = len(STU[cp])
    out = [np.full((n, NPROF), np.nan, dtype=np.float32)]
    for k in range(1, len(a) + 1):
        L = lead_mat[:, :k]
        sub = ~np.isnan(L)
        nsub = sub.sum(1).astype(float)
        with np.errstate(invalid="ignore"):
            mean_lead = np.where(nsub > 0, np.nansum(np.where(sub, L, 0), 1) / np.maximum(nsub, 1),
                                 np.nan)
            med_lead = np.nanmedian(np.where(sub, L, np.nan), 1) if k else np.full(n, np.nan)
        lastmin = np.sum(sub & (L <= 1), 1) / k
        nosub = (k - nsub) / k
        hi = int(due[k - 1]) + OFF
        win = np.zeros(NDAY, dtype=bool)
        for d in due[:k]:
            lo = int(d) - WLEN + 1 + OFF
            win[max(lo, OFF):int(d) + 1 + OFF] = True
        rng = np.zeros(NDAY, dtype=bool)
        rng[OFF:hi + 1] = True
        wm, om = win & rng, (~win) & rng
        mw = CLK[cp][:, wm].mean(1) if wm.sum() else np.zeros(n)
        mo = CLK[cp][:, om].mean(1) if om.sum() else np.zeros(n)
        ratio = (mw + 0.1) / (mo + 0.1)
        P = np.full((n, NPROF), np.nan, dtype=np.float32)
        P[:, 0] = nsub
        P[:, 1] = mean_lead
        P[:, 2] = med_lead
        P[:, 3] = lastmin
        P[:, 4] = nosub
        P[:, 5] = ratio
        out.append(P)
    return out


PROF = {cp: build_profiles(cp, LEAD[cp]) for cp in CPS}
RNG_SH = np.random.default_rng(SEED + 11)
PROF_SH = {}                           # 3 shuffled replicas (WHO destroyed, mean kept)
for rep in range(3):
    for cp in CPS:
        n = len(STU[cp])
        perm = RNG_SH.permutation(n)
        PROF_SH[(rep, cp)] = [P[perm] for P in PROF[cp]]


def prefix_k(cp, R):
    """number of TMA/CMA of cp with due day < R"""
    return int(np.sum(AS[cp].date.to_numpy(dtype=float) < R))


def registered_mask(cp, t):
    return (REGD[cp] <= t) & (UNRD[cp] > t)


OUT = []


def P(*a):
    s = " ".join(str(x) for x in a)
    OUT.append(s)
    print(s, flush=True)


P("=" * 84)
P("OULAD procrastination pre-check | dev presentations 2013B+2013J only "
  f"({NCP} course-presentations)")
P(f"course-presentations: {', '.join(CPS)}")
P(f"TMA/CMA with a valid due day: {sum(len(AS[c]) for c in CPS)} | "
  f"students (reg u vle): {sum(len(STU[c]) for c in CPS)}")
P(f"seeds {LGB_SEEDS}, bootstrap {NBOOT} resamples, window W_a = D_a-6..D_a")
P("=" * 84)

# ==================================================================== PART 1
P("\n" + "#" * 84)
P("# PART 1  descriptive: is late submission real, and is it a STUDENT trait?")
P("#" * 84)

rows = []
for cp in CPS:
    L = LEAD[cp]
    v = L[~np.isnan(L)]
    rows.append(dict(cp=cp, n=len(v), q05=np.quantile(v, .05), q25=np.quantile(v, .25),
                     med=np.median(v), q75=np.quantile(v, .75), q95=np.quantile(v, .95),
                     lastmin=float(np.mean(v <= 1)), late=float(np.mean(v < 0)),
                     nosub=float(np.mean(np.isnan(L)))))
D1 = pd.DataFrame(rows)
allv = np.concatenate([LEAD[cp][~np.isnan(LEAD[cp])] for cp in CPS])
alln = float(np.mean(np.concatenate([np.isnan(LEAD[cp]).ravel() for cp in CPS])))
P("\n## 1a lead time = due day - submission day (>0 early, <0 late), non-banked TMA/CMA")
P(f"{'cp':>10} {'n_sub':>7} {'q05':>6} {'q25':>6} {'med':>6} {'q75':>6} {'q95':>6} "
  f"{'<=1d share':>11} {'late share':>11} {'no-sub share':>13}")
for _, r in D1.iterrows():
    P(f"{r.cp:>10} {int(r.n):>7} {r.q05:>6.0f} {r.q25:>6.0f} {r.med:>6.0f} {r.q75:>6.0f} "
      f"{r.q95:>6.0f} {r.lastmin:>11.3f} {r.late:>11.3f} {r.nosub:>13.3f}")
P(f"{'ALL':>10} {len(allv):>7} {np.quantile(allv, .05):>6.0f} {np.quantile(allv, .25):>6.0f} "
  f"{np.median(allv):>6.0f} {np.quantile(allv, .75):>6.0f} {np.quantile(allv, .95):>6.0f} "
  f"{np.mean(allv <= 1):>11.3f} {np.mean(allv < 0):>11.3f} {alln:>13.3f}")

# --- consistency: Spearman on consecutive assessments + one-way ICC by student
rows = []
sp_x, sp_y = [], []
for cp in CPS:
    L = LEAD[cp]
    xs, ys = [], []
    for j in range(L.shape[1] - 1):
        m = ~np.isnan(L[:, j]) & ~np.isnan(L[:, j + 1])
        xs.append(L[m, j]); ys.append(L[m, j + 1])
    x = np.concatenate(xs); y = np.concatenate(ys)
    rho, pv = stats.spearmanr(x, y)
    sp_x.append(x); sp_y.append(y)
    # one-way random effects ICC on students with >=2 submissions
    keep = (~np.isnan(L)).sum(1) >= 2
    Lk = L[keep]
    grand = np.nanmean(Lk)
    ni = (~np.isnan(Lk)).sum(1).astype(float)
    mi = np.nanmean(Lk, 1)
    k_ = len(ni)
    msb = np.sum(ni * (mi - grand) ** 2) / (k_ - 1)
    msw = np.nansum((Lk - mi[:, None]) ** 2) / (np.sum(ni) - k_)
    n0 = (np.sum(ni) - np.sum(ni ** 2) / np.sum(ni)) / (k_ - 1)
    icc = (msb - msw) / (msb + (n0 - 1) * msw)
    rows.append(dict(cp=cp, npair=len(x), rho=rho, p=pv, nstu=k_, icc=icc))
D2 = pd.DataFrame(rows)
xa = np.concatenate(sp_x); ya = np.concatenate(sp_y)
rho_a, p_a = stats.spearmanr(xa, ya)
P("\n## 1b within-student consistency of lead time")
P(f"{'cp':>10} {'n_pairs':>8} {'spearman':>9} {'p':>9} {'n_stu>=2':>9} {'ICC_1':>7}")
for _, r in D2.iterrows():
    P(f"{r.cp:>10} {int(r.npair):>8} {r.rho:>9.3f} {r.p:>9.2e} {int(r.nstu):>9} {r.icc:>7.3f}")
P(f"{'POOLED':>10} {len(xa):>8} {rho_a:>9.3f} {p_a:>9.2e} {'':>9} "
  f"{D2.icc.mean():>7.3f}  (ICC = mean over cps)")

# --- deadline-window click share by prior-behaviour tercile
rows = []
for cp in CPS:
    due = AS[cp].date.to_numpy(dtype=float)
    tot = np.zeros(4)                    # lastmin third, mid, early third, unclassified
    nass = 0
    for j in range(1, len(due)):
        k = prefix_k(cp, due[j] - 7)
        if k == 0:
            continue
        pr = PROF[cp][k]
        ml = pr[:, 1].astype(float)
        regm = registered_mask(cp, due[j] - 7)
        cls = regm & ~np.isnan(ml)
        if cls.sum() < 30:
            continue
        q1, q2 = np.quantile(ml[cls], [1 / 3, 2 / 3])
        lo = int(due[j]) - WLEN + 1 + OFF
        w = CLK[cp][:, max(lo, 0):int(due[j]) + 1 + OFF].sum(1)
        grp = np.full(len(ml), 3)
        grp[cls & (ml <= q1)] = 0
        grp[cls & (ml > q1) & (ml <= q2)] = 1
        grp[cls & (ml > q2)] = 2
        for g in range(4):
            tot[g] += w[grp == g].sum()
        nass += 1
    s = tot.sum()
    rows.append(dict(cp=cp, nass=nass, lastmin=tot[0] / s, mid=tot[1] / s,
                     early=tot[2] / s, unclass=tot[3] / s))
D3 = pd.DataFrame(rows)
P("\n## 1c share of deadline-window clicks by tercile of PRIOR mean lead time")
P("   (terciles among students registered at D_a-7 with >=1 prior submission;")
P("    'last-minute' = lowest prior lead time; 'unclassified' = no prior submission)")
P(f"{'cp':>10} {'n_ass':>6} {'last-min 1/3':>13} {'middle 1/3':>11} {'early 1/3':>10} "
  f"{'unclassified':>13}")
for _, r in D3.iterrows():
    P(f"{r.cp:>10} {int(r.nass):>6} {r.lastmin:>13.3f} {r.mid:>11.3f} {r.early:>10.3f} "
      f"{r.unclass:>13.3f}")
P(f"{'MEAN':>10} {'':>6} {D3.lastmin.mean():>13.3f} {D3.mid.mean():>11.3f} "
  f"{D3.early.mean():>10.3f} {D3.unclass.mean():>13.3f}")
log("part 1 done")

# ==================================================================== PART 2
P("\n" + "#" * 84)
P("# PART 2  assessment-level: does the enrolled cohort's profile beat course history?")
P("#" * 84)

H2 = 7                                    # everything known at D_a - 7
units = []
for ci, cp in enumerate(CPS):
    a = AS[cp]
    due = a.date.to_numpy(dtype=float)
    tgt = []
    for j in range(len(due)):
        d = int(due[j])
        lo = max(d - WLEN + 1 + OFF, 0)
        w = CLK_CP[cp][lo:d + 1 + OFF]
        base = CLK_CP[cp][max(d - 27 + OFF, 0):d - 7 + 1 + OFF]
        bm = base.mean() if len(base) else 0.0
        peak = w.max() / bm if bm > 0 else np.nan
        l2 = CLK_CP[cp][d - 1 + OFF:d + 1 + OFF].sum()
        shr = l2 / w.sum() if w.sum() > 0 else np.nan
        s = SUBD[cp][:, j]
        nreg = int(registered_mask(cp, d - H2).sum())
        sub2 = float(np.sum((s >= d - 1) & (s <= d))) / max(nreg, 1)
        tgt.append((peak, shr, sub2))
    for j in range(1, len(due)):
        if np.isnan(tgt[j][0]) or np.isnan(tgt[j][1]):
            continue
        R = due[j] - H2
        k = prefix_k(cp, R)
        regm = registered_mask(cp, R)
        rec = dict(cp=cp, ci=ci, id_assessment=int(a.id_assessment.iloc[j]), due=due[j],
                   y_peak=tgt[j][0], y_l2share=tgt[j][1], y_sub2=tgt[j][2],
                   h_peak=tgt[j - 1][0], h_l2share=tgt[j - 1][1], h_sub2=tgt[j - 1][2],
                   h_type=float(a.assessment_type.iloc[j] == "TMA"),
                   h_weight=float(a.weight.iloc[j]),
                   h_gap=float(due[j] - due[j - 1]), nreg=int(regm.sum()), k=k)
        for tag, src in [("", PROF[cp][k])] + [(f"_s{r}", PROF_SH[(r, cp)][k]) for r in range(3)]:
            sub = src[regm]
            with np.errstate(invalid="ignore"):
                rec[f"c_mean_lead{tag}"] = float(np.nanmean(sub[:, 1])) if k else np.nan
                rec[f"c_lastmin{tag}"] = float(np.nanmean(sub[:, 3])) if k else np.nan
                rec[f"c_nosub{tag}"] = float(np.nanmean(sub[:, 4])) if k else np.nan
        units.append(rec)
U = pd.DataFrame(units)
U = U[~U.h_peak.isna() & ~U.h_l2share.isna()].reset_index(drop=True)
P(f"\nunits = {len(U)} assessments with a predecessor in the same cp "
  f"({U.cp.nunique()} cps, {U.groupby('cp').size().to_dict()})")

HCOLS = ["h_peak", "h_l2share", "h_sub2", "h_type", "h_weight", "h_gap"]
PCOLS = ["c_mean_lead", "c_lastmin", "c_nosub"]
TARGETS = [("y_peak", "peak ratio"), ("y_l2share", "last-2d share of window clicks"),
           ("y_sub2", "last-2d submissions / registered")]
LGB2 = dict(objective="regression", metric="rmse", learning_rate=0.05, num_leaves=7,
            min_data_in_leaf=5, feature_fraction=0.9, bagging_fraction=0.9, bagging_freq=1,
            verbosity=-1, deterministic=True, num_threads=8)


def ridge_fit(X, y, alpha=1.0):
    mu = np.nanmean(X, 0)
    Xf = np.where(np.isnan(X), mu, X)
    sdv = Xf.std(0); sdv[sdv < 1e-9] = 1.0
    Z = (Xf - mu) / sdv
    ym = y.mean()
    w = np.linalg.solve(Z.T @ Z + alpha * np.eye(Z.shape[1]), Z.T @ (y - ym))
    return mu, sdv, ym, w


def ridge_pred(m, X):
    mu, sdv, ym, w = m
    return ((np.where(np.isnan(X), mu, X) - mu) / sdv) @ w + ym


def loco_pred(cols, ycol, kind):
    pred = np.full(len(U), np.nan)
    Xall = U[cols].to_numpy(dtype=float)
    yall = U[ycol].to_numpy(dtype=float)
    for cp in CPS:
        te = (U.cp == cp).to_numpy()
        tr = ~te
        if te.sum() == 0:
            continue
        if kind == "ridge":
            pred[te] = ridge_pred(ridge_fit(Xall[tr], yall[tr]), Xall[te])
        else:
            acc = np.zeros(int(te.sum()))
            for s in LGB_SEEDS:
                p = dict(LGB2, seed=s, bagging_seed=s, feature_fraction_seed=s, data_random_seed=s)
                d = lgb.Dataset(Xall[tr], label=yall[tr])
                b = lgb.train(p, d, num_boost_round=250)
                acc += b.predict(Xall[te]) / len(LGB_SEEDS)
            pred[te] = acc
    return pred


def r2_mae(y, p):
    return (1 - np.sum((y - p) ** 2) / np.sum((y - y.mean()) ** 2), float(np.mean(np.abs(y - p))))


FSETS = [("hist", HCOLS), ("hist+prof", HCOLS + PCOLS)] + \
        [(f"hist+shuf{r}", HCOLS + [c + f"_s{r}" for c in PCOLS]) for r in range(3)]
PRED2 = {}
P("\n## 2a leave-one-course-presentation-out prediction of the NEXT deadline peak")
P(f"{'target':>32} {'model':>6} {'features':>11} {'R2':>7} {'MAE':>9}")
for ycol, nm in TARGETS:
    y = U[ycol].to_numpy(dtype=float)
    for kind in ["ridge", "lgbm"]:
        for fn, cols in FSETS:
            pr = loco_pred(cols, ycol, kind)
            PRED2[(ycol, kind, fn)] = pr
            r2, mae = r2_mae(y, pr)
            if fn.startswith("hist+shuf") and fn != "hist+shuf0":
                continue
            lbl = "hist+SHUF" if fn == "hist+shuf0" else fn
            P(f"{nm:>32} {kind:>6} {lbl:>11} {r2:>7.3f} {mae:>9.4f}")
    # mean of the 3 shuffle replicas
    for kind in ["ridge", "lgbm"]:
        rr = [r2_mae(y, PRED2[(ycol, kind, f'hist+shuf{r}')]) for r in range(3)]
        P(f"{nm:>32} {kind:>6} {'SHUF mean3':>11} {np.mean([x[0] for x in rr]):>7.3f} "
          f"{np.mean([x[1] for x in rr]):>9.4f}")

rng = np.random.default_rng(SEED + 3)
BIDX = rng.integers(0, len(U), size=(NBOOT, len(U)))
P("\n## 2b paired bootstrap over assessments, dMAE = MAE(a) - MAE(b), 95% CI "
  "(negative = a better)")
P(f"{'target':>32} {'model':>6} {'contrast':>22} {'dMAE':>9} {'95%lo':>9} {'95%hi':>9}  verdict")
for ycol, nm in TARGETS:
    y = U[ycol].to_numpy(dtype=float)
    for kind in ["ridge", "lgbm"]:
        for a, b, lbl in [("hist+prof", "hist", "prof - hist"),
                          ("hist+shuf0", "hist", "SHUF - hist"),
                          ("hist+prof", "hist+shuf0", "prof - SHUF")]:
            ea = np.abs(y - PRED2[(ycol, kind, a)])
            eb = np.abs(y - PRED2[(ycol, kind, b)])
            d = ea[BIDX].mean(1) - eb[BIDX].mean(1)
            pt = ea.mean() - eb.mean()
            lo, hi = np.quantile(d, .025), np.quantile(d, .975)
            P(f"{nm:>32} {kind:>6} {lbl:>22} {pt:>9.4f} {lo:>9.4f} {hi:>9.4f}  "
              f"{'CI excludes 0' if (lo > 0 or hi < 0) else 'CI covers 0'}")
log("part 2 done")

# ==================================================================== PART 3
P("\n" + "#" * 84)
P("# PART 3  bottom-up (sum of students) vs top-down (course lags + calendar) load")
P("#" * 84)

TT = np.arange(DAY_LO, TST_HI + 1)
NT = len(TT)
ATYPE_CODE = {t: i for i, t in enumerate(sorted(ass_all.assessment_type.unique()))}
CAL, OPEN_CP = {}, {}
days = np.arange(DMIN, DMAX + 1)
for cp in CPS:
    a = ass_all[(ass_all.cp == cp) & ass_all.date.notna()].sort_values("date")
    due = a.date.to_numpy(dtype=float)
    wts = a.weight.to_numpy(dtype=float)
    tps = np.array([ATYPE_CODE[x] for x in a.assessment_type])
    d2n = np.full(NDAY, 999.0); dsl = np.full(NDAY, 999.0)
    nxw = np.zeros(NDAY); nxt = np.full(NDAY, float(len(ATYPE_CODE)))
    n7 = np.zeros(NDAY); cw = np.zeros(NDAY)
    for i, t in enumerate(days):
        nx = np.where(due >= t)[0]; pv = np.where(due < t)[0]
        if len(nx):
            d2n[i] = due[nx[0]] - t; nxw[i] = wts[nx[0]]; nxt[i] = tps[nx[0]]
        if len(pv):
            dsl[i] = t - due[pv[-1]]
        n7[i] = np.sum((due >= t) & (due <= t + 6))
        cw[i] = wts[due <= t].sum()
    CAL[cp] = dict(days_to_next_due=d2n, days_since_last_due=dsl, next_due_weight=nxw,
                   next_due_type=nxt, n_due_next7=n7, cum_weight_passed=cw)
    v = vle[vle.cp == cp]
    wk = np.floor(days / 7.0)
    wf = v.week_from.to_numpy(dtype=float); wt = v.week_to.to_numpy(dtype=float)
    ok = ~np.isnan(wf) & ~np.isnan(wt)
    OPEN_CP[cp] = np.array([np.sum(ok & (wf <= w) & (wt >= w)) for w in wk], dtype=float)

# deadline-window day mask and window id per (cp, day)
DLW = {}
for cp in CPS:
    m = np.zeros(NDAY, dtype=np.int32) - 1
    for j, d in enumerate(AS[cp].date.to_numpy(dtype=float)):
        lo = max(int(d) - WLEN + 1 + OFF, 0)
        m[lo:int(d) + 1 + OFF] = j
    DLW[cp] = m
THR = {cp: float(np.quantile(CLK_CP[cp][0 + OFF:TRN_HI + OFF + 1], 0.90)) for cp in CPS}

# ---------------------------------------------------------- course-level table
CAL_COLS = ["days_to_next_due", "days_since_last_due", "next_due_weight", "next_due_type",
            "n_due_next7", "cum_weight_passed", "n_sites_open", "pres_length", "days_remaining"]
COH_COLS = ["k_mean_lead", "k_lastmin", "k_nosub", "k_clkratio"]


def cohort_agg(cp, R):
    k = prefix_k(cp, R)
    if k == 0:
        return [np.nan] * 4
    pr = PROF[cp][k][registered_mask(cp, R)]
    with np.errstate(invalid="ignore"):
        return [float(np.nanmean(pr[:, i])) if len(pr) else np.nan for i in (1, 3, 4, 5)]


def build_course(h):
    frames = []
    for cp in CPS:
        arr = CLK_CP[cp]
        d = {}
        L = np.stack([np.log1p(np.maximum(arr[TT - h - j + OFF], 0)) for j in range(14)], 1)
        for j in range(14):
            d[f"lag{j + 1}"] = L[:, j]
        d["lag_mean"] = L.mean(1); d["lag_max"] = L.max(1)
        d["dow"] = (TT % 7).astype(float); d["day"] = TT.astype(float)
        for k_, v in CAL[cp].items():
            d[k_] = v[TT + OFF]
        d["n_sites_open"] = OPEN_CP[cp][TT + OFF]
        d["pres_length"] = np.full(NT, float(CLEN[cp]))
        d["days_remaining"] = float(CLEN[cp]) - TT
        coh = np.array([cohort_agg(cp, t - h) for t in TT])
        for i, c in enumerate(COH_COLS):
            d[c] = coh[:, i]
        f = pd.DataFrame(d)
        f["cp"] = cp; f["t"] = TT
        f["y_raw"] = arr[TT + OFF]
        f["y"] = np.log1p(np.maximum(arr[TT + OFF], 0))
        f["win"] = DLW[cp][TT + OFF]
        frames.append(f)
    return pd.concat(frames, ignore_index=True)


F0C = [f"lag{j + 1}" for j in range(14)] + ["lag_mean", "lag_max", "dow", "day"]
TD_COLS = F0C + CAL_COLS
HY_COLS = TD_COLS + COH_COLS
LGB3 = dict(objective="regression", metric="rmse", learning_rate=0.05, num_leaves=31,
            min_data_in_leaf=20, feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=1,
            verbosity=-1, deterministic=True, num_threads=8)


def fit_course(Xtr, ytr, Xpr, cols, seeds):
    out = np.zeros(len(Xpr))
    for s in seeds:
        p = dict(LGB3, seed=s, bagging_seed=s, feature_fraction_seed=s, data_random_seed=s)
        b = lgb.train(p, lgb.Dataset(Xtr[cols], label=ytr,
                                     categorical_feature=["next_due_type"]),
                      num_boost_round=NROUND_C)
        out += b.predict(Xpr[cols]) / len(seeds)
    return out


# ----------------------------------------------------------- student-day table
SLAG = [f"slag{j + 1}" for j in range(NLAG_S)] + ["slag_mean14", "slag_max14", "slag_act14"]
SCAL = ["days_to_next_due", "days_since_last_due", "next_due_weight", "next_due_type",
        "n_due_next7", "dow", "day", "reg_active", "days_since_reg"]
BU_COLS = SLAG + SCAL
BUP_COLS = BU_COLS + PROF_NAMES
LGB_S = dict(objective="poisson", learning_rate=0.06, num_leaves=63, min_data_in_leaf=50,
             feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=1, verbosity=-1,
             deterministic=True, num_threads=8, max_bin=127)


def build_student(h):
    blocks, meta_cp, meta_t, ys = [], [], [], []
    for ci, cp in enumerate(CPS):
        M = CLK[cp]
        n = len(STU[cp])
        cols = {}
        for j in range(NLAG_S):
            cols[f"slag{j + 1}"] = np.log1p(M[:, TT - h - j + OFF])
        W = np.stack([M[:, TT - h - j + OFF] for j in range(14)], 2)
        cols["slag_mean14"] = np.log1p(W.mean(2))
        cols["slag_max14"] = np.log1p(W.max(2))
        cols["slag_act14"] = (W > 0).mean(2)
        del W
        for c in ["days_to_next_due", "days_since_last_due", "next_due_weight",
                  "next_due_type", "n_due_next7"]:
            cols[c] = np.broadcast_to(CAL[cp][c][TT + OFF], (n, NT))
        cols["dow"] = np.broadcast_to((TT % 7).astype(np.float32), (n, NT))
        cols["day"] = np.broadcast_to(TT.astype(np.float32), (n, NT))
        rm = np.stack([registered_mask(cp, t) for t in TT], 1).astype(np.float32)
        cols["reg_active"] = rm
        dsr = np.clip(TT[None, :] - REGD[cp][:, None], -50, 400).astype(np.float32)
        cols["days_since_reg"] = dsr
        ks = np.array([prefix_k(cp, t - h) for t in TT])
        PP = np.stack([PROF[cp][k] for k in ks], 1)          # (n, NT, NPROF)
        for i, c in enumerate(PROF_NAMES):
            cols[c] = PP[:, :, i]
        del PP
        blocks.append(pd.DataFrame({c: np.asarray(v, dtype=np.float32).reshape(-1)
                                    for c, v in cols.items()}))
        meta_cp.append(np.full(n * NT, ci, dtype=np.int16))
        meta_t.append(np.broadcast_to(TT, (n, NT)).reshape(-1).astype(np.int16))
        ys.append(M[:, TT + OFF].reshape(-1))
        del cols
    X = pd.concat(blocks, ignore_index=True)
    del blocks
    return X, np.concatenate(ys), np.concatenate(meta_cp), np.concatenate(meta_t)


def agg_course(pred, mcp, mt):
    gid = mcp.astype(np.int64) * NT + (mt - DAY_LO)
    return np.bincount(gid, weights=pred, minlength=NCP * NT)


def course_frame_index(C):
    """row index of course frame C in the (cp, t) grid order used by agg_course"""
    ci = C.cp.map({c: i for i, c in enumerate(CPS)}).to_numpy()
    return ci.astype(np.int64) * NT + (C.t.to_numpy() - DAY_LO)


def eval_block(C, pred_raw, mask, tag):
    y_raw = C.y_raw.to_numpy()[mask]
    p = np.maximum(pred_raw[mask], 0)
    yl = np.log1p(np.maximum(y_raw, 0)); pl = np.log1p(p)
    rmse = float(np.sqrt(np.mean((pl - yl) ** 2)))
    mae = float(np.mean(np.abs(p - y_raw)))
    return rmse, mae, (pl - yl) ** 2


def peak_f1(C, pred_raw, mask):
    thr = C.cp.map(THR).to_numpy()[mask]
    act = C.y_raw.to_numpy()[mask] > thr
    prd = np.maximum(pred_raw[mask], 0) > thr
    tp = float((act & prd).sum()); fp = float((~act & prd).sum()); fn = float((act & ~prd).sum())
    pr = tp / (tp + fp) if tp + fp else 0.0
    rc = tp / (tp + fn) if tp + fn else 0.0
    return 2 * pr * rc / (pr + rc) if pr + rc else 0.0


RES3, SQE3, SCAL3 = [], {}, {}
MODELS3 = ["TD", "HYB", "BU", "BU+P"]
for h in HORIZONS:
    C = build_course(h)
    ridx = course_frame_index(C)
    Xs, ys, mcp, mt = build_student(h)
    log(f"h={h} student rows {Xs.shape} course rows {C.shape}")
    ctr = (C.t <= TRN_HI).to_numpy()
    cte = (C.t >= TST_LO).to_numpy()
    str_ = (mt <= TRN_HI)
    rng_s = np.random.default_rng(SEED + h)

    for split in ["time", "loco"]:
        preds = {m: np.zeros(len(C)) for m in MODELS3}
        for m in MODELS3:
            if split == "time":
                folds = [(ctr, cte, str_, (mt >= TST_LO))]
            else:
                folds = []
                for ci, cp in enumerate(CPS):
                    hold_c = (C.cp == cp).to_numpy()
                    hold_s = (mcp == ci)
                    folds.append((~hold_c, hold_c & cte, ~hold_s, hold_s & (mt >= TST_LO)))
            seeds = LGB_SEEDS if split == "time" else [0]
            for (ctr_m, cpr_m, str_m, spr_m) in folds:
                if m in ("TD", "HYB"):
                    cols = TD_COLS if m == "TD" else HY_COLS
                    Xtr = C[ctr_m]; ytr = C.y.to_numpy()[ctr_m]
                    pl = fit_course(Xtr, ytr, C[cpr_m], cols, seeds)
                    praw = np.maximum(np.expm1(pl), 0)
                    ptr = np.maximum(np.expm1(fit_course(Xtr, ytr, C[ctr_m], cols, seeds)), 0)
                    scale = C.y_raw.to_numpy()[ctr_m].sum() / max(ptr.sum(), 1e-9)
                    preds[m][cpr_m] = praw * scale
                else:
                    cols = BU_COLS if m == "BU" else BUP_COLS
                    idx = np.where(str_m)[0]
                    ntake = min(TRAIN_CAP, int(len(idx) * TRAIN_FRAC))
                    take = rng_s.choice(idx, size=ntake, replace=False)
                    Xtake = Xs.iloc[take][cols]
                    Xpr = Xs.iloc[np.where(spr_m)[0]][cols]
                    acc = np.zeros(len(Xpr))
                    acc_tr = np.zeros(len(take))
                    for s in seeds:
                        p = dict(LGB_S, seed=s, bagging_seed=s, feature_fraction_seed=s,
                                 data_random_seed=s)
                        b = lgb.train(p, lgb.Dataset(Xtake, label=ys[take],
                                                     categorical_feature=["next_due_type"]),
                                      num_boost_round=NROUND_S)
                        acc += b.predict(Xpr) / len(seeds)
                        acc_tr += b.predict(Xtake) / len(seeds)
                    del Xtake, Xpr
                    scale = ys[take].sum() / max(acc_tr.sum(), 1e-9)
                    cl = agg_course(acc, mcp[spr_m], mt[spr_m])
                    preds[m][cpr_m] = cl[ridx[cpr_m]] * scale
                SCAL3.setdefault((h, split, m), []).append(float(scale))
                log(f"h={h} {split} {m} fold done scale={scale:.3f}")
        mte = cte
        mdl = cte & (C.win.to_numpy() >= 0)
        for m in MODELS3:
            r_a, m_a, e_a = eval_block(C, preds[m], mte, "all")
            r_d, m_d, e_d = eval_block(C, preds[m], mdl, "dl")
            f1 = peak_f1(C, preds[m], mte)
            RES3.append(dict(h=h, split=split, model=m, rmse_all=r_a, mae_all=m_a,
                             rmse_dl=r_d, mae_dl=m_d, peakF1=f1))
            SQE3[(h, split, m, "all")] = (C[mte].reset_index(drop=True), e_a)
            SQE3[(h, split, m, "dl")] = (C[mdl].reset_index(drop=True), e_d)
    del Xs, ys, mcp, mt, C
log("part 3 fits done")

R3 = pd.DataFrame(RES3)
P(f"\n## 3a course-day load, test days {TST_LO}..{TST_HI} "
  f"(TD = F1 of load_forecast_test.py, rebuilt with fixed {NROUND_C} rounds)")
P("   BU = sum over the cp's students of a student-day Poisson LightGBM; "
  "BU+P adds the profile")
P("   HYB = TD features + cohort-aggregated profile")
P(f"{'h':>2} {'split':>5} {'model':>5} {'RMSEall':>8} {'MAEall':>9} {'RMSEdl':>8} "
  f"{'MAEdl':>9} {'peakF1':>7} {'scale':>6}")
for h in HORIZONS:
    for split in ["time", "loco"]:
        for m in MODELS3:
            r = R3[(R3.h == h) & (R3.split == split) & (R3.model == m)].iloc[0]
            P(f"{h:>2} {split:>5} {m:>5} {r.rmse_all:>8.4f} {r.mae_all:>9.1f} "
              f"{r.rmse_dl:>8.4f} {r.mae_dl:>9.1f} {r.peakF1:>7.3f} "
              f"{np.mean(SCAL3[(h, split, m)]):>6.3f}")


def boot3(h, split, a, b, sub):
    Ca, ea = SQE3[(h, split, a, sub)]
    _, eb = SQE3[(h, split, b, sub)]
    if sub == "dl":
        blk = list(zip(Ca.cp, Ca.win))
    else:
        blk = list(zip(Ca.cp, (Ca.t // 7).astype(int)))
    keys = sorted(set(blk)); kidx = {k: i for i, k in enumerate(keys)}
    idx = np.array([kidx[k] for k in blk])
    order = np.argsort(idx, kind="mergesort")
    ea2, eb2, idx = ea[order], eb[order], idx[order]
    bounds = np.searchsorted(idx, np.arange(len(keys) + 1))
    sa_ = np.add.reduceat(ea2, bounds[:-1]); sb_ = np.add.reduceat(eb2, bounds[:-1])
    cnt = np.diff(bounds).astype(float)
    rng = np.random.default_rng(SEED + 17)
    pick = rng.integers(0, len(keys), size=(NBOOT, len(keys)))
    n = cnt[pick].sum(1)
    d = np.sqrt(sa_[pick].sum(1) / n) - np.sqrt(sb_[pick].sum(1) / n)
    pt = float(np.sqrt(sa_.sum() / cnt.sum()) - np.sqrt(sb_.sum() / cnt.sum()))
    return pt, float(np.quantile(d, .025)), float(np.quantile(d, .975))


P(f"\n## 3b paired block bootstrap on log1p RMSE ({NBOOT} resamples; deadline-window days "
  "block = (cp, assessment), all days block = (cp, week)); negative = a better")
P(f"{'h':>2} {'split':>5} {'days':>5} {'contrast':>12} {'dRMSE':>9} {'95%lo':>9} {'95%hi':>9}"
  "  verdict")
for h in HORIZONS:
    for split in ["time", "loco"]:
        for sub in ["dl", "all"]:
            for a, b in [("BU+P", "TD"), ("BU+P", "BU"), ("HYB", "TD"), ("BU", "TD")]:
                pt, lo, hi = boot3(h, split, a, b, sub)
                P(f"{h:>2} {split:>5} {sub:>5} {a + '-' + b:>12} {pt:>9.4f} {lo:>9.4f} "
                  f"{hi:>9.4f}  {'CI excludes 0' if (lo > 0 or hi < 0) else 'CI covers 0'}")

P(f"\nruntime {time.time() - T0:.1f}s")
