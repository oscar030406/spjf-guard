"""Falsification pre-check of a deadline-driven load model on CodeBench, hourly.

DEV = every semester except the holdout 2023-1 / 2023-2 / 2024-1, which are
touched here only for row counts.

    uv run --with pandas --with numpy --with scipy --with pyarrow --with lightgbm \
        python codebench_precheck.py
"""
from __future__ import annotations

import os

for _v in ("PYTHONHOME", "PYTHONPATH", "UV_INTERNAL__PYTHONHOME"):
    os.environ.pop(_v, None)

import warnings

import numpy as np
import pandas as pd
from scipy import optimize, stats

warnings.filterwarnings("ignore")
SEED = 0
rng = np.random.default_rng(SEED)

ROOT = r"<repo-root>"
PQ = os.path.join(ROOT, "data", "codebench", "parquet")
HOLDOUT = {"2023-1", "2023-2", "2024-1"}
REMOTE = {"2020-ERE", "2020-1", "2020-2", "2021-1", "2021-2"}
HOUR = np.timedelta64(3600, "s")


def to_hours(td):
    """Timedelta -> float hours, independent of the stored datetime resolution."""
    if isinstance(td, pd.Series):
        return td.dt.total_seconds() / 3600.0
    return td / HOUR

pd.set_option("display.width", 220, "display.max_columns", 60, "display.float_format",
              lambda v: f"{v:,.3f}")


def hr(title):
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def load(table):
    fs = sorted(os.listdir(os.path.join(PQ, table)))
    return pd.concat([pd.read_parquet(os.path.join(PQ, table, f)) for f in fs],
                     ignore_index=True)


# --------------------------------------------------------------------------- #
# 0. load + validate
# --------------------------------------------------------------------------- #
hr("0. LOAD AND VALIDATION")
ev = load("events")
ass = load("assessments")
usr = load("users")
lg = load("logins")

ev["cid"] = ev["semester"] + "/" + ev["class"]
ass["cid"] = ass["semester"] + "/" + ass["class"]
usr["cid"] = usr["semester"] + "/" + usr["class"]
enr = usr.groupby("cid")["user"].nunique().rename("enrolled")

print(f"events={len(ev):,}  assessments={len(ass):,}  users={len(usr):,}  logins={len(lg):,}")
print(f"holdout rows only: events={(ev.semester.isin(HOLDOUT)).sum():,} "
      f"assessments={(ass.semester.isin(HOLDOUT)).sum():,} users={(usr.semester.isin(HOLDOUT)).sum():,}")

ev = ev.merge(ass[["cid", "assessment", "type", "weight", "start", "end", "n_exercises"]],
              on=["cid", "assessment"], how="left")
ev["u"] = to_hours(ev["end"] - ev["ts"])                      # hours to deadline
ev.loc[ev["end"].isna(), "u"] = np.nan

v = ev.groupby("semester").agg(
    n_events=("ts", "size"),
    matched_assessment=("end", lambda s: s.notna().mean()),
    inside_window=("u", lambda s: np.nan),
)
inside = ev.assign(ins=(ev["ts"] >= ev["start"]) & (ev["ts"] <= ev["end"]))
v["inside_window"] = inside.groupby("semester")["ins"].mean()
v["after_deadline"] = ev.assign(a=ev["ts"] > ev["end"]).groupby("semester")["a"].mean()
v["ts_min"] = ev.groupby("semester")["ts"].min()
v["ts_max"] = ev.groupby("semester")["ts"].max()
v["dup_share"] = ev.duplicated(["semester", "class", "user", "assessment", "exercise",
                                "ts", "kind"]).groupby(ev["semester"]).mean()
v["holdout"] = v.index.isin(HOLDOUT)
v["remote"] = v.index.isin(REMOTE)
print(v.to_string())

DEV = ev[~ev.semester.isin(HOLDOUT) & ev["end"].notna()].copy()
DEV_ASS = ass[~ass.semester.isin(HOLDOUT)].copy()
DEV_ASS["dur_h"] = to_hours(DEV_ASS["end"] - DEV_ASS["start"])
print("\nassessment window duration (hours), DEV:")
print(DEV_ASS.groupby("type")["dur_h"].describe()[["count", "25%", "50%", "75%", "max"]].to_string())
print("\nDEV classes:", DEV["cid"].nunique(), " DEV events:", f"{len(DEV):,}",
      " remote-flagged DEV events:", f"{DEV.semester.isin(REMOTE).sum():,}")

# --------------------------------------------------------------------------- #
# P1 event study
# --------------------------------------------------------------------------- #
hr("P1. EVENT STUDY: executions per enrolled student per hour vs hours-to-deadline u")

U_LO, U_HI = -24, 336
d = DEV[(DEV.u >= U_LO) & (DEV.u < U_HI)].copy()
d["ub"] = np.floor(d["u"]).astype(int)

akey = ["cid", "assessment"]
cnt = d.groupby(akey + ["ub"]).size().rename("n").reset_index()
aenr = DEV_ASS.merge(enr, left_on="cid", right_index=True, how="left")
aenr = aenr.dropna(subset=["enrolled", "dur_h"])

# Full (assessment x u) grid over the hours the assessment was actually OPEN, so the
# denominator does not shrink to "assessments that happen to have an event at that u".
open_hi = np.minimum(np.floor(aenr["dur_h"].to_numpy()), U_HI - 1).astype(int)
open_hi = np.maximum(open_hi, 0)
lens = (open_hi - U_LO + 1)
per_a = pd.DataFrame({
    "cid": np.repeat(aenr["cid"].to_numpy(), lens),
    "assessment": np.repeat(aenr["assessment"].to_numpy(), lens),
    "type": np.repeat(aenr["type"].to_numpy(), lens),
    "weight": np.repeat(aenr["weight"].to_numpy(), lens),
    "n_exercises": np.repeat(aenr["n_exercises"].to_numpy(), lens),
    "enrolled": np.repeat(aenr["enrolled"].to_numpy(), lens),
    "ub": np.concatenate([np.arange(U_LO, h + 1) for h in open_hi]),
})
per_a = per_a.merge(cnt, on=akey + ["ub"], how="left")
per_a["n"] = per_a["n"].fillna(0.0)
per_a["semester"] = per_a["cid"].str.split("/").str[0]
per_a["rate"] = per_a["n"] / per_a["enrolled"]

curve = (per_a.groupby(["type", "ub"])
         .apply(lambda g: g["n"].sum() / g["enrolled"].sum())
         .rename("rate").reset_index())
n_a = per_a.groupby(["type", "ub"])["assessment"].size().rename("n_ass").reset_index()
curve = curve.merge(n_a, on=["type", "ub"])
print("assessments open at each u (denominator support):")
print(curve.pivot_table(index="ub", columns="type", values="n_ass")
      .reindex([335, 240, 168, 72, 24, 6, 2, 1, 0, -1, -24]).to_string())

rows = []
fits = []
for typ, g in curve.groupby("type"):
    g = g.sort_values("ub").set_index("ub")
    r = g["rate"]
    sm = r.rolling(24, center=True, min_periods=12).mean()   # kills the hour-of-day cycle
    blo, bhi = (72, 168) if typ == "homework" else (3, 24)
    base = r.loc[blo:bhi].mean()
    dl = r.loc[0:24]
    gp = r.loc[0:]
    # ramp start: walking up from u=0 on the smoothed curve, where does it drop below 2x base
    ramp = np.nan
    below = 0
    for u in range(0, 336):
        val = sm.get(u, np.nan)
        if not np.isfinite(val):
            continue
        if val < 2 * base:
            below += 1
            if below >= 6:
                ramp = u - 5
                break
        else:
            below = 0
    rows.append(dict(type=typ, baseline_u=f"[{blo},{bhi}]", baseline_rate=base,
                     n_ass_at_baseline=int(g["n_ass"].loc[blo:bhi].min()),
                     deadline_peak_u=int(dl.idxmax()), deadline_peak_rate=dl.max(),
                     peak_over_baseline=dl.max() / base if base > 0 else np.nan,
                     ramp_start_u_h=ramp,
                     global_peak_u=int(gp.idxmax()), global_peak_rate=gp.max(),
                     mass_0_24h=r.loc[0:23].sum(), mass_0_336h=gp.sum(),
                     share_last24h=r.loc[0:23].sum() / gp.sum()))
    # ---- ramp fits on the de-seasonalised curve, u in [1,168] ---------- #
    f = sm.loc[1:168].dropna()
    f = f[f > 0]
    x, y = f.index.to_numpy(float), f.to_numpy(float)
    ly = np.log(y)

    def r2(pred):
        return 1 - np.sum((ly - pred) ** 2) / np.sum((ly - ly.mean()) ** 2)

    try:
        p, _ = optimize.curve_fit(lambda u, a, c: np.log(a) - np.log(u + c), x, ly,
                                  p0=[y[0] * (x[0] + 1), 1.0], maxfev=40000)
        r2h, ph = r2(np.log(p[0]) - np.log(x + p[1])), p
    except Exception:
        r2h, ph = np.nan, [np.nan, np.nan]
    sl, ic = np.polyfit(x, ly, 1)
    r2e = r2(ic + sl * x)
    fits.append(dict(type=typ, n_bins=len(x), hyperbolic_a=ph[0], hyperbolic_c=ph[1],
                     R2_log_hyperbolic=r2h, exp_a=np.exp(ic), exp_tau_h=-1 / sl,
                     R2_log_exponential=r2e,
                     better="hyperbolic" if r2h > r2e else "exponential"))
print(pd.DataFrame(rows).to_string(index=False))
print("\nramp fit on the 24h-smoothed curve, u in [1,168] h, R2 of log(rate):")
print(pd.DataFrame(fits).to_string(index=False))

# ---- is the peak at the deadline or at the assessment OPENING? ------------ #
dv = DEV[DEV.type == "homework"].copy()
dv["v"] = to_hours(dv["ts"] - dv["start"])
dv = dv[(dv.v >= 0) & (dv.v < 336)]
dv["vb"] = np.floor(dv["v"]).astype(int)
cv = dv.groupby("vb").size().rename("n").reset_index()
hwa = aenr[aenr.type == "homework"]
den = np.array([hwa.loc[hwa["dur_h"] >= b, "enrolled"].sum() for b in cv["vb"]])
cv["rate"] = cv["n"] / np.maximum(den, 1)
cvr = cv.set_index("vb")["rate"]
hwr = curve[curve.type == "homework"].set_index("ub")["rate"]
bands = [(0, 3), (3, 12), (12, 24), (24, 72), (72, 168)]
print("\nhomework: mean rate per band, measured from the DEADLINE (u) vs from the OPENING (v):")
print(pd.DataFrame({
    "band_h": [f"[{a},{b}]" for a, b in bands],
    "from_deadline_u": [hwr.loc[a:b].mean() for a, b in bands],
    "from_opening_v": [cvr.loc[a:b].mean() for a, b in bands],
}).to_string(index=False))

print("\ncurve shape, homework, rate per enrolled student per hour:")
hw = curve[curve.type == "homework"].set_index("ub")["rate"]
show = [335, 240, 168, 120, 72, 48, 24, 12, 6, 3, 1, 0, -1, -6, -24]
print(pd.DataFrame({"u_h": show, "rate": [hw.get(u, np.nan) for u in show]}).to_string(index=False))
ex = curve[curve.type == "exam"].set_index("ub")["rate"]
print("exam (windows are ~2 h, so u>2 has almost no open assessment):",
      " ".join(f"{u}:{ex.get(u, np.nan):.4f}" for u in [6, 3, 2, 1, 0, -1, -6]))
_exev = DEV[DEV.type == "exam"]
print(f"share of exam executions inside the exam window: "
      f"{((_exev.u >= 0) & (_exev.u <= to_hours(_exev.end - _exev.start))).mean():.3f}")

# ---- stability of the normalised curve ------------------------------------ #
def norm_curves(keys, typ="homework", umin=0, umax=169):
    sub = per_a[(per_a.type == typ) & (per_a.ub >= umin) & (per_a.ub < umax)]
    piv = (sub.groupby(keys + ["ub"])["n"].sum().unstack("ub")
           .reindex(columns=range(umin, umax)).fillna(0.0))
    piv = piv[piv.sum(1) > 0]
    return piv.div(piv.sum(1), axis=0)


def pairwise_corr(piv, min_n=2):
    if len(piv) < min_n:
        return np.nan, 0
    c = np.corrcoef(piv.to_numpy())
    iu = np.triu_indices_from(c, 1)
    return float(np.nanmedian(c[iu])), len(piv)


for lbl, keys in [("between classes", ["cid"]), ("between semesters", ["semester"])]:
    for typ in ["homework", "exam"]:
        piv = norm_curves(keys, typ)
        m, n = pairwise_corr(piv)
        print(f"normalised-curve median pairwise Pearson, {lbl:18s} {typ:9s}: {m:.3f}  (n={n})")

# remote vs on-campus
for lbl, sems in [("on-campus", sorted(set(DEV.semester) - REMOTE)), ("remote", sorted(REMOTE))]:
    sub = per_a[per_a.type == "homework"]
    sub = sub[sub["cid"].str.split("/").str[0].isin(sems)]
    g = sub[(sub.ub >= 0) & (sub.ub < 336)]
    base = g[(g.ub >= 168)].groupby("ub").apply(lambda x: x.n.sum() / x.enrolled.sum()).mean()
    pk = g[(g.ub < 24)].groupby("ub").apply(lambda x: x.n.sum() / x.enrolled.sum()).max()
    print(f"{lbl:10s} homework: baseline={base:.4f} peak(<24h)={pk:.4f} ratio={pk/base:.1f}")

# ---- amplitude ------------------------------------------------------------ #
amp = (per_a[(per_a.ub >= 0)].groupby(akey + ["type", "weight", "n_exercises", "enrolled"])["n"]
       .sum().rename("n").reset_index())
amp["mass_per_student"] = amp["n"] / amp["enrolled"]
print("\namplitude = executions per enrolled student per assessment (u in [0,336h]):")
print(amp.groupby("type")["mass_per_student"].agg(
    n="size", mean="mean", sd="std", cv=lambda s: s.std() / s.mean(),
    p10=lambda s: s.quantile(.1), p90=lambda s: s.quantile(.9)).to_string())
cls_cv = (amp[amp.type == "homework"].groupby("cid")["mass_per_student"].mean())
print(f"between-class CV of homework amplitude: {cls_cv.std()/cls_cv.mean():.3f} "
      f"(n_classes={len(cls_cv)})")
a2 = amp[amp.type == "homework"].dropna(subset=["weight", "n_exercises"])
print("Spearman of amplitude vs: "
      f"weight r={stats.spearmanr(a2.weight, a2.mass_per_student).statistic:.3f} "
      f"p={stats.spearmanr(a2.weight, a2.mass_per_student).pvalue:.1e} | "
      f"n_exercises r={stats.spearmanr(a2.n_exercises, a2.mass_per_student).statistic:.3f} "
      f"p={stats.spearmanr(a2.n_exercises, a2.mass_per_student).pvalue:.1e}")
print("mean amplitude by type: " + amp.groupby("type")["mass_per_student"].mean().round(3).to_dict().__str__())

# --------------------------------------------------------------------------- #
# build the hourly panel (needed by P2 and P4)
# --------------------------------------------------------------------------- #
hr("HOURLY PANEL")
DEV["hour"] = DEV["ts"].dt.floor("h")
panel_parts = []
for cid, g in DEV.groupby("cid"):
    lo, hi = g["hour"].min(), g["hour"].max()
    if to_hours(hi - lo) > 24 * 400:
        hi = lo + pd.Timedelta(days=400)
    idx = pd.date_range(lo, hi, freq="h")
    y = g.groupby("hour").size().reindex(idx, fill_value=0)
    panel_parts.append(pd.DataFrame({"cid": cid, "hour": idx, "y": y.to_numpy()}))
panel = pd.concat(panel_parts, ignore_index=True)
panel["semester"] = panel["cid"].str.split("/").str[0]
panel = panel.merge(enr, left_on="cid", right_index=True, how="left")
print(f"panel rows={len(panel):,} classes={panel.cid.nunique()} "
      f"median hours/class={panel.groupby('cid').size().median():.0f}")

A = DEV_ASS.dropna(subset=["start", "end"]).copy()
A["end_h"] = A["end"].dt.floor("h")


def calendar_features(pan):
    """hours-to-next-deadline and open-assessment features per (cid, hour)."""
    out = []
    for cid, g in pan.groupby("cid", sort=False):
        aa = A[A.cid == cid]
        hrs = g["hour"].to_numpy("datetime64[ns]")
        if len(aa) == 0:
            out.append(pd.DataFrame({"cid": cid, "hour": g["hour"], "u_next": 336.0,
                                     "type_next": "none", "w_next": 0.0, "nex_next": 0.0,
                                     "n_open": 0, "n_dl_72": 0}))
            continue
        ends = aa["end"].to_numpy("datetime64[ns]")
        starts = aa["start"].to_numpy("datetime64[ns]")
        du = (ends[None, :] - hrs[:, None]) / HOUR                      # hours to each end
        open_mask = (hrs[:, None] >= starts[None, :]) & (du >= 0)
        fut = np.where(du >= 0, du, np.inf)
        j = np.argmin(fut, axis=1)
        u_next = np.take_along_axis(fut, j[:, None], 1).ravel()
        u_next = np.minimum(u_next, 336.0)
        out.append(pd.DataFrame({
            "cid": cid, "hour": g["hour"],
            "u_next": u_next,
            "type_next": aa["type"].to_numpy()[j],
            "w_next": pd.to_numeric(aa["weight"], errors="coerce").fillna(0).to_numpy()[j],
            "nex_next": pd.to_numeric(aa["n_exercises"], errors="coerce").fillna(0).to_numpy()[j],
            "n_open": open_mask.sum(1),
            "n_dl_72": ((du >= 0) & (du <= 72) & open_mask).sum(1),
        }))
    return pd.concat(out, ignore_index=True)


cal = calendar_features(panel)
panel = panel.merge(cal, on=["cid", "hour"], how="left")
panel["hod"] = panel["hour"].dt.hour
panel["dow"] = panel["hour"].dt.dayofweek

# --------------------------------------------------------------------------- #
# P2 superposition
# --------------------------------------------------------------------------- #
hr("P2. SUPERPOSITION: is load additive when deadlines overlap?")

# single-deadline reference kernel: hours where exactly one assessment is in [0,72]
ref_src = panel[panel.n_dl_72 == 1].copy()
ref_src["ub"] = np.floor(ref_src["u_next"]).astype(int)
ref = (ref_src.groupby(["type_next", "ub"])
       .apply(lambda g: g["y"].sum() / g["enrolled"].sum()).rename("k"))
ref_d = {k: float(v) for k, v in ref.items()}
# hour-of-day multiplier: u alone smears the diurnal cycle across deadlines set at
# different clock times, which would otherwise confound the additivity test
ref_src["_k"] = [ref_d.get((t, b), 0.0) for t, b in zip(ref_src.type_next, ref_src.ub)]
ref_src["_k"] *= ref_src["enrolled"]
HOD_M = (ref_src.groupby("hod").apply(lambda g: g["y"].sum() / max(g["_k"].sum(), 1e-9))
         .clip(0.05, 20).to_dict())


def predict_add(cid, hour_arr, enrolled):
    hod = pd.DatetimeIndex(hour_arr).hour.to_numpy()
    aa = A[A.cid == cid]
    if len(aa) == 0:
        return np.zeros(len(hour_arr))
    ends = aa["end"].to_numpy("datetime64[ns]")
    starts = aa["start"].to_numpy("datetime64[ns]")
    types = aa["type"].to_numpy()
    du = (ends[None, :] - hour_arr[:, None]) / HOUR
    m = (du >= 0) & (du <= 72) & (hour_arr[:, None] >= starts[None, :])
    pr = np.zeros(len(hour_arr))
    ub = np.floor(du).astype(int)
    for j in range(len(aa)):
        sel = m[:, j]
        if not sel.any():
            continue
        vals = np.array([ref_d.get((types[j], int(b)), 0.0) for b in ub[sel, j]])
        pr[sel] += vals * enrolled
    return pr * np.array([HOD_M.get(h, 1.0) for h in hod])


p2 = []
for cid, g in panel.groupby("cid", sort=False):
    g = g.sort_values("hour")
    pr = predict_add(cid, g["hour"].to_numpy("datetime64[ns]"), g["enrolled"].iloc[0])
    p2.append(pd.DataFrame({"cid": cid, "hour": g["hour"], "y": g["y"].to_numpy(),
                            "pred": pr, "n_dl_72": g["n_dl_72"].to_numpy(),
                            "semester": g["semester"].to_numpy()}))
p2 = pd.concat(p2, ignore_index=True)
q = p2[(p2.n_dl_72 >= 1) & (p2.pred > 0)].copy()
q["k"] = q["n_dl_72"].clip(upper=4)
tab = q.groupby("k").agg(hours=("y", "size"), obs=("y", "sum"), pred=("pred", "sum"))
tab["ratio_obs_pred"] = tab["obs"] / tab["pred"]
qq = q[q.pred >= 10.0]
tab["hours_pred_ge10"] = qq.groupby("k").size()
tab["y0_share_pred_ge10"] = qq.groupby("k").apply(lambda g: (g.y == 0).mean())
tab["median_ratio_pred_ge10"] = qq.groupby("k").apply(lambda g: (g.y / g.pred).median())
print("class level, k = number of assessments with u in [0,72h] in that hour:")
print(tab.to_string())

# platform level: only classes that actually have a deadline within 72h contribute,
# otherwise the observed side carries load the single-deadline model never claims to predict
p2d = p2[p2.n_dl_72 >= 1]
plat = (p2d.groupby(["semester", "hour"]).agg(y=("y", "sum"), pred=("pred", "sum"),
                                              n_cls=("cid", "nunique")))
plat = plat[plat.pred > 0].reset_index()
plat["kc"] = plat["n_cls"].clip(upper=4)
pt = plat.groupby("kc").agg(hours=("y", "size"), obs=("y", "sum"), pred=("pred", "sum"))
pt["ratio_obs_pred"] = pt["obs"] / pt["pred"]
print("\nplatform level, kc = number of classes with a deadline within 72h at that hour:")
print(pt.to_string())

# --------------------------------------------------------------------------- #
# P3 individual timing
# --------------------------------------------------------------------------- #
hr("P3. INDIVIDUAL TIMING")
sub = DEV[(DEV.kind == "submit") & DEV.u.notna() & (DEV.u > -240) & (DEV.u < 336 * 2)]
ua = sub.groupby(["cid", "assessment", "type", "user"])["u"].agg(
    first_lead="max", last_lead="min", n="size").reset_index()
print("lead time of first / last submission before deadline (hours), DEV:")
print(ua.groupby("type")[["first_lead", "last_lead"]].describe()
      .loc[:, (slice(None), ["50%", "25%", "75%"])].to_string())
print("share of students whose LAST submission is within 24h of the deadline: "
      f"{(ua.last_lead < 24).mean():.3f}; within 3h: {(ua.last_lead < 3).mean():.3f}")


def icc1(df, val="last_lead"):
    g = df.groupby("user")[val]
    k = g.size()
    if len(k) < 3 or k.max() < 2:
        return np.nan
    kbar = k[k >= 1].mean()
    gm = df[val].mean()
    msb = (k * (g.mean() - gm) ** 2).sum() / (len(k) - 1)
    msw = ((df[val] - df["user"].map(g.mean())) ** 2).sum() / max(1, (len(df) - len(k)))
    v = (msb - msw) / (msb + (kbar - 1) * msw)
    return float(np.clip(v, -1, 1))


hw_u = ua[ua.type == "homework"]
iccs = hw_u.groupby("cid").apply(lambda g: icc1(g) if g.user.nunique() >= 5 else np.nan).dropna()
print(f"\nICC(1) of last-submission lead time by student within class (homework): "
      f"median={iccs.median():.3f} IQR=[{iccs.quantile(.25):.3f},{iccs.quantile(.75):.3f}] "
      f"n_classes={len(iccs)}")

sp = []
for cid, g in hw_u.groupby("cid"):
    order = (DEV_ASS[DEV_ASS.cid == cid].sort_values("end")["assessment"].tolist())
    piv = g.pivot_table(index="user", columns="assessment", values="last_lead")
    cols = [c for c in order if c in piv.columns]
    for i in range(len(cols) - 1):
        x = piv[[cols[i], cols[i + 1]]].dropna()
        if len(x) >= 10:
            sp.append(stats.spearmanr(x.iloc[:, 0], x.iloc[:, 1]).statistic)
sp = np.array(sp, float)
print(f"Spearman of last-submission lead between CONSECUTIVE assessments: "
      f"median={np.nanmedian(sp):.3f} IQR=[{np.nanpercentile(sp,25):.3f},"
      f"{np.nanpercentile(sp,75):.3f}] n_pairs={np.isfinite(sp).sum()}")

# share of last-24h load from the most last-minute third, classified on prior assessments
shares = []
for cid, g in hw_u.groupby("cid"):
    order = DEV_ASS[DEV_ASS.cid == cid].sort_values("end")["assessment"].tolist()
    ev_c = sub[(sub.cid == cid) & (sub.type == "homework")]
    for i in range(2, len(order)):
        prior = g[g.assessment.isin(order[:i])].groupby("user")["last_lead"].mean()
        if len(prior) < 9:
            continue
        thr = prior.quantile(1 / 3)
        late = set(prior[prior <= thr].index)     # smallest lead = most last-minute
        cur = ev_c[(ev_c.assessment == order[i]) & (ev_c.u >= 0) & (ev_c.u < 24)]
        if len(cur) < 30:
            continue
        shares.append(dict(cid=cid, n_late=len(late), n_all=len(prior),
                           share=cur.user.isin(late).mean(),
                           expected=len(late) / len(prior)))
sh = pd.DataFrame(shares)
print(f"\nshare of the last-24h execution load from the most last-minute third "
      f"(classified only on earlier assessments): mean={sh.share.mean():.3f} "
      f"median={sh.share.median():.3f} vs expected {sh.expected.mean():.3f} "
      f"(n_assessments={len(sh)})")

# --------------------------------------------------------------------------- #
# P4 forecasting
# --------------------------------------------------------------------------- #
hr("P4. FORECASTING hourly executions per class, horizons 24h and 168h")
import lightgbm as lgb

pan = panel.sort_values(["cid", "hour"]).reset_index(drop=True)
g = pan.groupby("cid")["y"]
LAGS = [0, 1, 2, 3, 6, 12, 24, 48, 168]
feat_lag = []
for L in LAGS:
    pan[f"lag{L}"] = g.shift(L)
    feat_lag.append(f"lag{L}")
pan["rm24"] = g.transform(lambda s: s.shift(0).rolling(24).mean())
pan["rm168"] = g.transform(lambda s: s.shift(0).rolling(168).mean())
feat_lag += ["rm24", "rm168"]

FEAT_CAL = ["u_next_h", "type_h", "w_h", "nex_h", "n_open_h", "hod_h", "dow_h", "enrolled"]
rows = []
for hz in (24, 168):
    p = pan.copy()
    gg = p.groupby("cid")
    p["y_t"] = gg["y"].shift(-hz)
    for src, dst in [("u_next", "u_next_h"), ("w_next", "w_h"), ("nex_next", "nex_h"),
                     ("n_open", "n_open_h"), ("hod", "hod_h"), ("dow", "dow_h")]:
        p[dst] = gg[src].shift(-hz)
    p["type_h"] = gg["type_next"].shift(-hz)
    p["snaive"] = gg["y"].shift(168 - hz)          # same hour last week, known at t
    p["horizon"] = hz
    p = p.dropna(subset=["y_t", "lag168", "rm168", "u_next_h", "snaive"])
    p["type_h"] = p["type_h"].astype("category").cat.codes
    rows.append(p)
P = pd.concat(rows, ignore_index=True)
P["week"] = P["hour"].dt.to_period("W").astype(str)
print(f"supervised rows={len(P):,} classes={P.cid.nunique()}")

LGB = dict(n_estimators=400, learning_rate=0.05, num_leaves=63, min_child_samples=40,
           subsample=0.9, subsample_freq=1, colsample_bytree=0.9, verbose=-1,
           random_state=SEED, n_jobs=8)


def fit_lgb(tr, te, feats):
    m = lgb.LGBMRegressor(**LGB)
    m.fit(tr[feats], np.log1p(tr["y_t"]))
    return np.expm1(np.clip(m.predict(te[feats]), 0, None))


def kernel_model(tr, te):
    """shared non-negative kernel per assessment type over u, x hour-of-day, x class level."""
    t = tr.copy()
    t["ub"] = np.minimum(np.floor(t["u_next_h"]), 336).astype(int)
    K = (t.groupby(["type_h", "ub"]).apply(lambda z: z["y_t"].sum() / z["enrolled"].sum())
         .rename("k").to_dict())
    kg = t["y_t"].sum() / t["enrolled"].sum()
    base = t.assign(kv=[K.get((a, b), kg) for a, b in zip(t.type_h, t.ub)])
    base["kv"] *= base["enrolled"]
    M = (base.groupby("hod_h").apply(lambda z: z["y_t"].sum() / max(z["kv"].sum(), 1e-9))
         .rename("m").to_dict())
    e = te.copy()
    e["ub"] = np.minimum(np.floor(e["u_next_h"]), 336).astype(int)
    kv = np.array([K.get((a, b), kg) for a, b in zip(e.type_h, e.ub)]) * e["enrolled"].to_numpy()
    mv = np.array([M.get(h, 1.0) for h in e.hod_h])
    raw = kv * mv
    # class level: observed vs kernel-predicted load over the class's own first two weeks
    lev = {}
    e = e.assign(_raw=raw)
    for cid, z in e.groupby("cid"):
        first = z[z.hour < z.hour.min() + pd.Timedelta(days=14)]
        den = first["_raw"].mean()
        lev[cid] = float(np.clip(first["y"].mean() / den, 0.2, 5.0)) if len(first) and den > 0 else 1.0
    lvv = np.array([lev.get(c, 1.0) for c in e.cid])
    return np.clip(raw * lvv, 0, None)


def metrics(y, p, cid, q=0.95):
    y, p = np.asarray(y, float), np.asarray(p, float)
    out = dict(rmse_log1p=float(np.sqrt(np.mean((np.log1p(y) - np.log1p(p)) ** 2))),
               mae=float(np.mean(np.abs(y - p))))
    df = pd.DataFrame({"y": y, "p": p, "cid": cid})
    tp = fp = fn = 0
    for c, z in df.groupby("cid"):
        if len(z) < 40:
            continue
        ty = z.y >= z.y.quantile(q)
        tpd = z.p >= z.p.quantile(q)
        tp += int((ty & tpd).sum()); fp += int((~ty & tpd).sum()); fn += int((ty & ~tpd).sum())
    pr = tp / max(tp + fp, 1); rc = tp / max(tp + fn, 1)
    out.update(peak_precision=pr, peak_recall=rc,
               peak_f1=2 * pr * rc / max(pr + rc, 1e-9))
    return out


def run_split(tr, te, tag, hz, store):
    preds = {"seasonal_naive": te["snaive"].to_numpy(float),
             "lgbm_lags": fit_lgb(tr, te, feat_lag),
             "lgbm_lags_cal": fit_lgb(tr, te, feat_lag + FEAT_CAL),
             "lgbm_cal_only": fit_lgb(tr, te, FEAT_CAL),
             "kernel_superpos": kernel_model(tr, te)}
    for name, pv in preds.items():
        m = metrics(te["y_t"], pv, te["cid"])
        m.update(model=name, split=tag, horizon=hz, n=len(te))
        store.append(m)
    return preds


res, boot_store = [], {}
classes = np.array(sorted(P.cid.unique()))
rng.shuffle(classes)
folds = np.array_split(classes, 5)
for hz in (24, 168):
    Ph = P[P.horizon == hz]
    for i, f in enumerate(folds):
        te = Ph[Ph.cid.isin(f)]
        tr = Ph[~Ph.cid.isin(f)]
        if len(te) < 500:
            continue
        pr = run_split(tr, te, "grouped-class-CV", hz, res)
        boot_store.setdefault(("cv", hz), []).append((te, pr))
    tr = Ph[Ph.semester.isin(["2016-1", "2016-2", "2017-1", "2017-2", "2018-1", "2018-2"])]
    te = Ph[Ph.semester.isin(["2019-1", "2019-2"])]
    if len(tr) and len(te):
        pr = run_split(tr, te, "forward 2019", hz, res)
        boot_store[("fwd", hz)] = [(te, pr)]

R = pd.DataFrame(res)
agg = (R.groupby(["split", "horizon", "model"])[["rmse_log1p", "mae", "peak_precision",
                                                 "peak_recall", "peak_f1"]].mean())
print(agg.to_string())


def paired_boot(key, a, b, metric="rmse_log1p", B=400):
    packs = boot_store.get(key, [])
    if not packs:
        return None
    frames = []
    for te, pr in packs:
        frames.append(pd.DataFrame({"cid": te["cid"].to_numpy(), "y": te["y_t"].to_numpy(),
                                    "week": te["week"].to_numpy(),
                                    "a": pr[a], "b": pr[b]}))
    d = pd.concat(frames, ignore_index=True)
    d["blk"] = d["cid"] + "|" + d["week"]
    blks = d["blk"].unique()
    grp = {k: v for k, v in d.groupby("blk")}
    diffs = []
    for _ in range(B):
        s = rng.choice(blks, len(blks), replace=True)
        z = pd.concat([grp[k] for k in s], ignore_index=True)
        if metric == "rmse_log1p":
            fa = np.sqrt(np.mean((np.log1p(z.y) - np.log1p(z.a)) ** 2))
            fb = np.sqrt(np.mean((np.log1p(z.y) - np.log1p(z.b)) ** 2))
        else:
            fa, fb = np.mean(np.abs(z.y - z.a)), np.mean(np.abs(z.y - z.b))
        diffs.append(fa - fb)
    diffs = np.array(diffs)
    return float(diffs.mean()), float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))


print("\npaired bootstrap over (class, week) blocks, delta log1p-RMSE (negative = first better):")
for key, lbl in [(("cv", 24), "CV h=24"), (("cv", 168), "CV h=168"),
                 (("fwd", 24), "fwd h=24"), (("fwd", 168), "fwd h=168")]:
    for a, b in [("lgbm_lags_cal", "lgbm_lags"), ("kernel_superpos", "lgbm_cal_only")]:
        r = paired_boot(key, a, b)
        if r:
            print(f"  {lbl:10s} {a:16s} - {b:15s}: {r[0]:+.4f}  95% CI [{r[1]:+.4f}, {r[2]:+.4f}]")

# --------------------------------------------------------------------------- #
# P5 service side
# --------------------------------------------------------------------------- #
hr("P5. SERVICE SIDE: execution cost")
allev = ev[~ev.semester.isin(HOLDOUT)]
subm = allev[allev.kind == "submit"]
s5 = allev.groupby("semester").agg(n=("ts", "size"), error_share=("has_error", "mean"))
s5["n_submit"] = subm.groupby("semester").size()
s5["exec_time_recorded_submit"] = subm.groupby("semester")["exec_time"].apply(lambda s: s.notna().mean())
s5["exec_time_recorded_all"] = allev.groupby("semester")["exec_time"].apply(lambda s: s.notna().mean())
s5["timeout_share"] = allev.assign(t=allev.error_type.astype(str).isin(["TimeLimit"])
                                   ).groupby("semester")["t"].mean()
print(s5.to_string())

et = allev["exec_time"].dropna()
print(f"\nexecution time (s), n={len(et):,}: mean={et.mean():.3f} "
      + " ".join(f"p{q}={et.quantile(q/100):.3f}" for q in (50, 90, 99, 99.9))
      + f" max={et.max():.1f}")
print("top-5% share of total recorded execution time: "
      f"{et[et >= et.quantile(.95)].sum()/et.sum():.3f}")
for col in ["n_testcases", "code_len"]:
    c = allev[col].astype(float)
    c = c[c > 0]
    print(f"{col}: median={c.median():.0f} p95={c.quantile(.95):.0f} "
          f"top-5% share of total={c[c >= c.quantile(.95)].sum()/c.sum():.3f}")
sub5 = allev[allev.exec_time.notna() & (allev.n_testcases > 0)]
print(f"Spearman exec_time vs n_testcases r="
      f"{stats.spearmanr(sub5.exec_time, sub5.n_testcases).statistic:.3f}; "
      f"vs code_len r={stats.spearmanr(sub5.exec_time, sub5.code_len).statistic:.3f}")
print("\nerror types (DEV, share of all executions):")
print((allev.error_type.value_counts(normalize=True).head(10) * 100).round(2).to_string())
print("\ndone.")
