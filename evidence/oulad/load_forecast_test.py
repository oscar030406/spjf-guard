"""OULAD platform-LOAD forecasting pre-check: does real heterogeneous context
(assessment calendar, enrolment dynamics, cross-entity resource context) improve
day-ahead / 3-day / 7-day load forecasting and peak (congestion) early warning?

DEVELOPMENT DATA ONLY: code_presentation in {2013B, 2013J}.  Rows with 2014B /
2014J are filtered out at read time and never enter any array.

Targets, per course-presentation (cp) and day t in 0..240:
  T1  total clicks of the cp
  T2  clicks per (cp, activity_type) for the 8 most-clicked activity types
  T3  number of distinct active students of the cp

Horizons h in {1,3,7}: every feature uses only data up to day t-h, plus calendar
information genuinely known in advance (assessment due dates/types/weights, vle
week_from/week_to, presentation length, day index, day mod 7).

Models (LightGBM, log1p target, identical hyperparameters, no tuning):
  F0  own lags only        14 lags ending at t-h, their mean/max, day mod 7, day index
  F1  F0 + assessment calendar + vle open-window + presentation length
  F2  F1 + enrolment dynamics known at t-h
  F3  F2 + cross-entity context (per-activity-type lag totals of the same cp)
  naive7   value at t-7          mean14   mean of last 14 available days
"""
import os
import sys
import time

import numpy as np
import pandas as pd
import lightgbm as lgb

T0 = time.time()
DATA = r"<repo-root>\data"
PRES = ("2013B", "2013J")
SEED = 20260918
LGB_SEEDS = [0, 1, 2]
NBOOT = 2000

DMIN, DMAX = -30, 240           # day axis stored
OFF = -DMIN
NDAY = DMAX - DMIN + 1
TRN_LO, TRN_HI = 14, 140
VAL_LO, VAL_HI = 141, 160
TST_LO, TST_HI = 161, 240
HORIZONS = [1, 3, 7]
NLAG = 14
MODELS = ["F0", "F1", "F2", "F3"]

np.random.seed(SEED)


def log(m):
    print(f"[{time.time() - T0:7.1f}s] {m}", file=sys.stderr, flush=True)


# ------------------------------------------------------------------ load
vle = pd.read_csv(f"{DATA}/vle.csv")
vle = vle[vle.code_presentation.isin(PRES)].copy()
vle["cp"] = vle.code_module + "_" + vle.code_presentation
site_at = dict(zip(vle.id_site.astype(np.int64), vle.activity_type))
site_cp = dict(zip(vle.id_site.astype(np.int64), vle.cp))

clk_cp = {}          # cp -> array over days
clk_cp_at = {}       # (cp, atype) -> array
stu_parts = []
at_tot = {}
for ch in pd.read_csv(f"{DATA}/studentVle.csv",
                      usecols=["code_module", "code_presentation", "id_student",
                               "id_site", "date", "sum_click"],
                      dtype={"id_student": np.int64, "id_site": np.int64,
                             "date": np.int32, "sum_click": np.int32},
                      chunksize=2_000_000):
    ch = ch[ch.code_presentation.isin(PRES)]
    ch = ch[(ch.date >= DMIN) & (ch.date <= DMAX)]
    if not len(ch):
        continue
    ch["cp"] = ch.code_module + "_" + ch.code_presentation
    ch["at"] = ch.id_site.map(site_at)
    g = ch.groupby(["cp", "date"], observed=True).sum_click.sum()
    for (cp, d), v in g.items():
        clk_cp.setdefault(cp, np.zeros(NDAY))[d + OFF] += v
    g2 = ch.groupby(["cp", "at", "date"], observed=True).sum_click.sum()
    for (cp, a, d), v in g2.items():
        clk_cp_at.setdefault((cp, a), np.zeros(NDAY))[d + OFF] += v
        at_tot[a] = at_tot.get(a, 0) + v
    stu_parts.append(ch[["cp", "date", "id_student"]].drop_duplicates())

stu = pd.concat(stu_parts, ignore_index=True).drop_duplicates()
del stu_parts
nstu_cp = {}
for (cp, d), v in stu.groupby(["cp", "date"]).id_student.nunique().items():
    nstu_cp.setdefault(cp, np.zeros(NDAY))[d + OFF] = v
CPS = sorted(clk_cp)
TOP8 = [a for a, _ in sorted(at_tot.items(), key=lambda x: -x[1])[:8]]
log(f"loaded cps={len(CPS)} {CPS}")
log(f"top8 activity types = {TOP8}")

# ------------------------------------------------------- calendar / context
ass = pd.read_csv(f"{DATA}/assessments.csv")
ass = ass[ass.code_presentation.isin(PRES)].copy()
ass["cp"] = ass.code_module + "_" + ass.code_presentation
ass["weight"] = ass.weight.fillna(0.0)
ATYPE_CODE = {t: i for i, t in enumerate(sorted(ass.assessment_type.unique()))}

reg = pd.read_csv(f"{DATA}/studentRegistration.csv")
reg = reg[reg.code_presentation.isin(PRES)].copy()
reg["cp"] = reg.code_module + "_" + reg.code_presentation

sa = pd.read_csv(f"{DATA}/studentAssessment.csv")
sa = sa.merge(ass[["id_assessment", "cp"]], on="id_assessment", how="inner")

crs = pd.read_csv(f"{DATA}/courses.csv")
crs = crs[crs.code_presentation.isin(PRES)].copy()
crs["cp"] = crs.code_module + "_" + crs.code_presentation
CLEN = dict(zip(crs.cp, crs.module_presentation_length))

days = np.arange(DMIN, DMAX + 1)
CAL, ENR, OPEN_CP, OPEN_AT = {}, {}, {}, {}
for cp in CPS:
    a = ass[ass.cp == cp].sort_values("date")
    due = a.date.to_numpy(dtype=float)
    wts = a.weight.to_numpy(dtype=float)
    tps = np.array([ATYPE_CODE[x] for x in a.assessment_type])
    d2n = np.full(NDAY, 999.0); dsl = np.full(NDAY, 999.0)
    nxw = np.zeros(NDAY)
    nxt = np.full(NDAY, float(len(ATYPE_CODE)))   # code for "no assessment left"
    n7 = np.zeros(NDAY); cw = np.zeros(NDAY)
    for i, t in enumerate(days):
        nx = np.where(due >= t)[0]
        pv = np.where(due < t)[0]
        if len(nx):
            d2n[i] = due[nx[0]] - t; nxw[i] = wts[nx[0]]; nxt[i] = tps[nx[0]]
        if len(pv):
            dsl[i] = t - due[pv[-1]]
        n7[i] = np.sum((due >= t) & (due <= t + 6))
        cw[i] = wts[due <= t].sum()
    CAL[cp] = dict(days_to_next_due=d2n, days_since_last_due=dsl, next_due_weight=nxw,
                   next_due_type=nxt, n_due_next7=n7, cum_weight_passed=cw)

    r = reg[reg.cp == cp]
    rd = r.date_registration.to_numpy(dtype=float)
    ud = r.date_unregistration.to_numpy(dtype=float)
    creg = np.array([np.sum(rd <= t) for t in days], dtype=float)
    cunr = np.array([np.nansum(ud <= t) for t in days], dtype=float)
    regc = creg - cunr
    unr14 = cunr - np.concatenate([np.zeros(14), cunr[:-14]])
    s = sa[sa.cp == cp].date_submitted.to_numpy(dtype=float)
    csub = np.array([np.sum(s <= t) for t in days], dtype=float)
    sub7 = csub - np.concatenate([np.zeros(7), csub[:-7]])
    ENR[cp] = dict(reg_count=regc, unreg_14=unr14, subm_7=sub7)

    v = vle[vle.cp == cp]
    wk = np.floor(days / 7.0)
    wf = v.week_from.to_numpy(dtype=float); wt = v.week_to.to_numpy(dtype=float)
    ok = ~np.isnan(wf) & ~np.isnan(wt)
    OPEN_CP[cp] = np.array([np.sum(ok & (wf <= w) & (wt >= w)) for w in wk], dtype=float)
    for a_ in TOP8:
        m = (v.activity_type == a_).to_numpy()
        OPEN_AT[(cp, a_)] = np.array(
            [np.sum(ok & m & (wf <= w) & (wt >= w)) for w in wk], dtype=float)

SER = {}   # (target, cp, sname) -> value array over days
for cp in CPS:
    SER[("T1", cp, "total")] = clk_cp[cp]
    SER[("T3", cp, "nstu")] = nstu_cp[cp]
    for a_ in TOP8:
        SER[("T2", cp, a_)] = clk_cp_at.get((cp, a_), np.zeros(NDAY))
AT_CODE = {a: i for i, a in enumerate(TOP8)}
log("context built")


# ------------------------------------------------------------- feature build
def lag_cols(arr, t, h):
    """14 lags ending at t-h (log1p), on the stored day axis."""
    return np.stack([np.log1p(np.maximum(arr[t - h - j + OFF], 0)) for j in range(NLAG)], 1)


def build(target, h):
    rows_X, rows_y, meta = [], [], []
    tt = np.arange(TRN_LO, TST_HI + 1)
    for cp in CPS:
        snames = ["total"] if target == "T1" else (["nstu"] if target == "T3" else TOP8)
        pertype = np.stack([np.log1p(np.maximum(SER[("T2", cp, a_)], 0)) for a_ in TOP8])
        for sn in snames:
            arr = SER[(target, cp, sn)]
            L = lag_cols(arr, tt, h)
            d = dict()
            for j in range(NLAG):
                d[f"lag{j + 1}"] = L[:, j]
            d["lag_mean"] = L.mean(1)
            d["lag_max"] = L.max(1)
            d["dow"] = (tt % 7).astype(float)
            d["day"] = tt.astype(float)
            d["series_id"] = np.full(len(tt), AT_CODE.get(sn, 0), dtype=float)
            for k, v in CAL[cp].items():
                d[k] = v[tt + OFF]
            d["n_sites_open"] = (OPEN_AT[(cp, sn)] if target == "T2" else OPEN_CP[cp])[tt + OFF]
            d["pres_length"] = np.full(len(tt), float(CLEN[cp]))
            d["days_remaining"] = float(CLEN[cp]) - tt
            for k, v in ENR[cp].items():
                d[k] = v[tt - h + OFF]
            na = np.log1p(np.maximum(nstu_cp[cp], 0))
            for j in (1, 3, 7):
                d[f"nstu_lag{j}"] = na[tt - h - (j - 1) + OFF]
            d["nstu_mean14"] = np.stack([na[tt - h - j + OFF] for j in range(NLAG)], 1).mean(1)
            for i, a_ in enumerate(TOP8):
                d[f"at{i}_lag1"] = pertype[i][tt - h + OFF]
                d[f"at{i}_mean7"] = np.stack([pertype[i][tt - h - j + OFF] for j in range(7)], 1).mean(1)
            rows_X.append(pd.DataFrame(d))
            rows_y.append(np.log1p(np.maximum(arr[tt + OFF], 0)))
            meta.append(pd.DataFrame(dict(cp=cp, sname=sn, day=tt,
                                          naive7=arr[tt - 7 + OFF],
                                          mean14=np.stack([arr[tt - h - j + OFF]
                                                           for j in range(NLAG)], 1).mean(1),
                                          y_raw=arr[tt + OFF])))
    X = pd.concat(rows_X, ignore_index=True)
    y = np.concatenate(rows_y)
    M = pd.concat(meta, ignore_index=True)
    return X, y, M


CAL_COLS = list(CAL[CPS[0]].keys()) + ["n_sites_open", "pres_length", "days_remaining"]
ENR_COLS = list(ENR[CPS[0]].keys()) + ["nstu_lag1", "nstu_lag3", "nstu_lag7", "nstu_mean14"]
CROSS_COLS = [f"at{i}_{s}" for i in range(8) for s in ("lag1", "mean7")]
F0_COLS = [f"lag{j + 1}" for j in range(NLAG)] + ["lag_mean", "lag_max", "dow", "day", "series_id"]
FSET = {"F0": F0_COLS,
        "F1": F0_COLS + CAL_COLS,
        "F2": F0_COLS + CAL_COLS + ENR_COLS,
        "F3": F0_COLS + CAL_COLS + ENR_COLS + CROSS_COLS}
CATS = ["next_due_type", "series_id"]

PARAMS = dict(objective="regression", metric="rmse", learning_rate=0.05,
              num_leaves=31, min_data_in_leaf=20, feature_fraction=0.8,
              bagging_fraction=0.8, bagging_freq=1, verbosity=-1,
              deterministic=True, num_threads=4)


def fit_predict(X, y, mtr, mva, mpr, cols):
    """Seed-averaged log1p prediction on rows selected by mpr."""
    Xs = X[cols]
    cat = [c for c in CATS if c in cols]
    out = np.zeros(int(mpr.sum()))
    iters = []
    for s in LGB_SEEDS:
        p = dict(PARAMS, seed=s, bagging_seed=s, feature_fraction_seed=s, data_random_seed=s)
        dtr = lgb.Dataset(Xs[mtr], label=y[mtr], categorical_feature=cat, free_raw_data=False)
        dva = lgb.Dataset(Xs[mva], label=y[mva], categorical_feature=cat, reference=dtr,
                          free_raw_data=False)
        b = lgb.train(p, dtr, num_boost_round=500, valid_sets=[dva],
                      callbacks=[lgb.early_stopping(30, verbose=False)])
        out += b.predict(Xs[mpr], num_iteration=b.best_iteration) / len(LGB_SEEDS)
        iters.append(b.best_iteration)
    return out, iters


def metrics(pred_log, y_log, y_raw):
    rmse = float(np.sqrt(np.mean((pred_log - y_log) ** 2)))
    mae = float(np.mean(np.abs(np.maximum(np.expm1(pred_log), 0) - y_raw)))
    return rmse, mae


# peak thresholds: top-10% of that series' own days 0..160
THR = {}
for (tg, cp, sn), arr in SER.items():
    THR[(tg, cp, sn)] = float(np.quantile(arr[0 + OFF:160 + OFF + 1], 0.90))


def peak_prf(M, pred_raw):
    thr = np.array([THR[(M.target.iloc[0], c, s)] for c, s in zip(M.cp, M.sname)])
    act = M.y_raw.to_numpy() > thr
    prd = pred_raw > thr
    tp = float(np.sum(act & prd)); fp = float(np.sum(~act & prd)); fn = float(np.sum(act & ~prd))
    pr = tp / (tp + fp) if tp + fp else 0.0
    rc = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * pr * rc / (pr + rc) if pr + rc else 0.0
    return pr, rc, f1


# ================================================================== main run
RES = []          # dict rows
SQE = {}          # (target,h,model) -> (M_test, per-row squared error, log preds)
for target in ["T1", "T2", "T3"]:
    for h in HORIZONS:
        X, y, M = build(target, h)
        M["target"] = target
        mtr = ((M.day >= TRN_LO) & (M.day <= TRN_HI)).to_numpy()
        mva = ((M.day >= VAL_LO) & (M.day <= VAL_HI)).to_numpy()
        mte = ((M.day >= TST_LO) & (M.day <= TST_HI)).to_numpy()
        Mt = M[mte].reset_index(drop=True)
        yt = y[mte]
        for base in ["naive7", "mean14"]:
            p = np.log1p(np.maximum(Mt[base].to_numpy(), 0))
            r, a = metrics(p, yt, Mt.y_raw.to_numpy())
            pr, rc, f1 = peak_prf(Mt, np.maximum(Mt[base].to_numpy(), 0))
            RES.append(dict(split="time", target=target, h=h, model=base, rmse=r, mae=a,
                            P=pr, R=rc, F1=f1))
        for mod in MODELS:
            p, it = fit_predict(X, y, mtr, mva, mte, FSET[mod])
            r, a = metrics(p, yt, Mt.y_raw.to_numpy())
            pr, rc, f1 = peak_prf(Mt, np.maximum(np.expm1(p), 0))
            RES.append(dict(split="time", target=target, h=h, model=mod, rmse=r, mae=a,
                            P=pr, R=rc, F1=f1))
            SQE[(target, h, mod)] = (Mt, (p - yt) ** 2)
            log(f"time {target} h={h} {mod} rmse={r:.4f} iters={it}")

        # ---- leave-one-course-presentation-out
        loco_p, loco_y, loco_M = {m: [] for m in MODELS}, [], []
        for cp in CPS:
            hold = (M.cp == cp).to_numpy()
            tr = (~hold) & ((M.day >= TRN_LO) & (M.day <= TST_HI)).to_numpy() & ~mva
            va = (~hold) & mva
            pr_m = hold & mte
            for mod in MODELS:
                pp, _ = fit_predict(X, y, tr, va, pr_m, FSET[mod])
                loco_p[mod].append(pp)
            loco_y.append(y[pr_m])
            loco_M.append(M[pr_m])
        ly = np.concatenate(loco_y)
        lM = pd.concat(loco_M, ignore_index=True)
        for mod in MODELS:
            pp = np.concatenate(loco_p[mod])
            r, a = metrics(pp, ly, lM.y_raw.to_numpy())
            pr, rc, f1 = peak_prf(lM, np.maximum(np.expm1(pp), 0))
            RES.append(dict(split="loco", target=target, h=h, model=mod, rmse=r, mae=a,
                            P=pr, R=rc, F1=f1))
        log(f"loco {target} h={h} done")

R = pd.DataFrame(RES)

# ================================================================== bootstrap
def boot(target, h, a, b):
    Mt, ea = SQE[(target, h, a)]
    _, eb = SQE[(target, h, b)]
    blk = list(zip(Mt.cp, (Mt.day // 7).astype(int)))
    keys = sorted(set(blk))
    kidx = {k: i for i, k in enumerate(keys)}
    idx = np.array([kidx[k] for k in blk])
    order = np.argsort(idx, kind="mergesort")
    ea, eb, idx = ea[order], eb[order], idx[order]
    bounds = np.searchsorted(idx, np.arange(len(keys) + 1))
    sa = np.add.reduceat(ea, bounds[:-1]); sb = np.add.reduceat(eb, bounds[:-1])
    cnt = np.diff(bounds).astype(float)
    rng = np.random.default_rng(SEED + 7)
    pick = rng.integers(0, len(keys), size=(NBOOT, len(keys)))
    n = cnt[pick].sum(1)
    d = np.sqrt(sa[pick].sum(1) / n) - np.sqrt(sb[pick].sum(1) / n)
    point = float(np.sqrt(sa.sum() / cnt.sum()) - np.sqrt(sb.sum() / cnt.sum()))
    return point, float(np.quantile(d, .025)), float(np.quantile(d, .975))


# ================================================================== output
print("=" * 78)
print("OULAD load-forecast pre-check | dev presentations 2013B+2013J only "
      f"({len(CPS)} course-presentations)")
print(f"course-presentations: {', '.join(CPS)}")
print(f"top-8 activity types: {', '.join(TOP8)}")
print(f"target days 14..240 | train 14..140, early-stop 141..160, test 161..240")
print(f"LightGBM seeds {LGB_SEEDS}, feature/bagging fraction 0.8, lr 0.05, 500 rounds, es 30")
print("=" * 78)

for target, nm in [("T1", "total clicks"), ("T2", "clicks per activity type"),
                   ("T3", "distinct active students")]:
    print(f"\n### {target} = {nm} -- time split, test 161..240")
    print(f"{'h':>2} {'model':>7} {'logRMSE':>9} {'MAE_raw':>11} {'peakP':>7} {'peakR':>7} {'peakF1':>7}")
    for h in HORIZONS:
        for _, r in R[(R.split == "time") & (R.target == target) & (R.h == h)].iterrows():
            print(f"{h:>2} {r.model:>7} {r.rmse:>9.4f} {r.mae:>11.1f} "
                  f"{r.P:>7.3f} {r.R:>7.3f} {r.F1:>7.3f}")

print("\n### leave-one-course-presentation-out (train on the other cps' full timelines)")
print(f"{'target':>7} {'h':>2} {'model':>5} {'logRMSE':>9} {'MAE_raw':>11} {'peakF1':>7}")
for target in ["T1", "T2", "T3"]:
    for h in HORIZONS:
        for _, r in R[(R.split == "loco") & (R.target == target) & (R.h == h)].iterrows():
            print(f"{target:>7} {h:>2} {r.model:>5} {r.rmse:>9.4f} {r.mae:>11.1f} {r.F1:>7.3f}")

print(f"\n### paired block bootstrap on log1p RMSE, time split, {NBOOT} resamples "
      "over (cp, week) blocks, seed-averaged predictions  (negative = the richer set wins)")
print(f"{'target':>7} {'h':>2} {'contrast':>9} {'dRMSE':>9} {'95%lo':>9} {'95%hi':>9}  verdict")
for target in ["T1", "T2", "T3"]:
    for h in HORIZONS:
        for a, b in [("F1", "F0"), ("F2", "F1"), ("F3", "F2"), ("F3", "F0")]:
            p, lo, hi = boot(target, h, a, b)
            v = "CI excludes 0" if (lo > 0 or hi < 0) else "CI covers 0"
            print(f"{target:>7} {h:>2} {a + '-' + b:>9} {p:>9.4f} {lo:>9.4f} {hi:>9.4f}  {v}")

print("\n### deadline-driven congestion: test days 161..240, days within 3 days before "
      "an assessment due date (due-3..due) vs other test days, total clicks")
print(f"{'cp':>10} {'n_dl':>5} {'n_oth':>6} {'mean_dl':>10} {'mean_oth':>10} {'ratio':>7} "
      f"{'var_share_dl':>13}")
for cp in CPS:
    due = ass[ass.cp == cp].date.dropna().to_numpy()
    d = np.arange(TST_LO, TST_HI + 1)
    isdl = np.zeros(len(d), bool)
    for u in due:
        isdl |= (d >= u - 3) & (d <= u)
    v = clk_cp[cp][d + OFF]
    mu = v.mean()
    ssd = float(np.sum((v[isdl] - mu) ** 2)); sst = float(np.sum((v - mu) ** 2))
    print(f"{cp:>10} {int(isdl.sum()):>5} {int((~isdl).sum()):>6} {v[isdl].mean():>10.0f} "
          f"{v[~isdl].mean():>10.0f} {v[isdl].mean() / max(v[~isdl].mean(), 1e-9):>7.2f} "
          f"{ssd / max(sst, 1e-9):>13.3f}")

print(f"\nruntime {time.time() - T0:.1f}s")
