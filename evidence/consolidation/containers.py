"""Measurement 1: how many dedicated per-student containers the CodeBench design keeps
alive, and how much of that alive time a container actually spends executing a run.

What the log actually contains (checked here, printed per semester).  `logins.log` lives
under `<semester>/<class>/users/<uid>/` but holds that *user's whole platform history*:
the same rows appear in every class directory the user occurs in, and they reach back to
2016 inside a 2022 archive.  So the rows are deduplicated by (user, timestamp, kind) and
clipped to the semester's own event window before use, and the container unit is
(semester, user), not (semester, class, user) -- a student who takes two classes in one
semester has one container, not two.  Each user is attached to the class where most of
their events are, which is the only thing the class decides here (which overlay copy the
container belongs to); the number of users with more than one class is reported.

Two readings of "container alive":

  login_*  -- the platform's own session records.  A login opens a container; the next row
              of the same user closes it.  If that row is a `logout` the close is
              observed; if it is another `login` the container is replaced and the close is
              censored at the new login; if there is no next row the close is censored at
              the end of the window.
              login_obs : only the logins whose next row is a logout.  Every session whose
                          end was never written is dropped, so this is a lower bound.
              login_act : every login; a censored close is replaced by the user's last
                          event end inside the window.  This is the session estimate.
  proxy_G  -- activity proxy, as if there were no login records: every event of a user
              occupies [ts - C, ts] (C = execution time, 0 for TEST blocks, whose duration
              the log does not record); consecutive events of the same user stay in one
              session while the gap between them is <= G.  G = 1800 s primary, 600 and
              3600 s sensitivity.  proxy1800_lg adds the login and logout instants to the
              activity set, so a session that begins with editing is not cut short.

Executing time is the union (not the sum) of [ts - C_cap, ts] over the user's submissions,
C_cap = min(C, 60) as in the plan; two runs of the same student that overlap are counted
once.  Utilisation = executing seconds inside the alive intervals / alive seconds.

Scope: the 60-second-regime development semesters 2020-ERE, 2020-2, 2021-1, 2021-2,
2022-1, 2022-2, restricted to the 40 class-semesters of the paper's overlay pool.  The
sealed semesters 2023-1, 2023-2, 2024-1 are never opened.

The overlay is rebuilt through `evidence/codebench_service_v2` (imported read-only) with
the copy count, seed and per-class-semester week shifts of the trace the paper simulates,
so the container counts and the pooled k refer to one and the same demand.

usage:  containers.py            # writes dedicated.json next to this file; stdout ->
                                 # out_dedicated.txt
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True
import json
import os
import time

import numpy as np
import pandas as pd

ROOT = r"<repo-root>"
PQ = os.path.join(ROOT, "data", "codebench", "parquet")
V2 = os.path.join(ROOT, "evidence", "codebench_service_v2")
SCRATCH = r"<cache-dir>"
CACHE = os.path.join(SCRATCH, "cb_v2_cache_r4")
HERE = os.path.dirname(os.path.abspath(__file__))

POOL = ["2020-ERE", "2020-2", "2021-1", "2021-2", "2022-1", "2022-2"]
SEALED = {"2023-1", "2023-2", "2024-1"}
L_CAP = 60.0
GAPS = (600, 1800, 3600)
PRIMARY_DEF = "proxy1800"
DEFS = ["login_obs", "login_act", "proxy600", "proxy1800", "proxy3600", "proxy1800_lg"]
COPIES = 44                     # the paper's overlay: 44 copies of the 40 class-semesters
REP = 0
CFG = "ires0"
WEEK = 604800
US = 1_000_000                  # all interval arithmetic is int64 microseconds
UOFF = 1 << 46                  # per-user offset (~814 days) for the group tricks
T0 = time.time()


def log(*a):
    print(f"[{time.time() - T0:6.1f}s]", *a, flush=True)


# --------------------------------------------------------------------------- #
# interval primitives (int64 microseconds, `u` a dense per-semester user code)
# --------------------------------------------------------------------------- #
def merge_sessions(u, s, e, gap_us):
    """Merge each user's intervals while the gap between them is <= gap_us."""
    if len(u) == 0:
        z = np.zeros(0, np.int64)
        return z, z, z
    o = np.lexsort((s, u))
    u, s, e = u[o], s[o], e[o]
    off = u * UOFF
    cm = np.maximum.accumulate(e + off) - off            # running max end within the user
    prev = np.empty_like(cm)
    prev[0] = -(1 << 62)
    prev[1:] = cm[:-1]
    new_u = np.empty(len(u), bool)
    new_u[0] = True
    new_u[1:] = u[1:] != u[:-1]
    brk = new_u | (s - prev > gap_us)
    st = np.flatnonzero(brk)
    return u[st], s[st], np.maximum.reduceat(e, st)


def levels(s, e):
    """Concurrency step function: (level on each segment, segment length).  At an equal
    instant a close is applied before an open, so a container that closes exactly when
    another opens is not counted twice."""
    x = np.concatenate([s, e])
    d = np.concatenate([np.ones(len(s), np.int8), -np.ones(len(e), np.int8)])
    o = np.lexsort((d, x))
    return np.cumsum(d[o].astype(np.int32))[:-1], np.diff(x[o])


def tw_stats(lev, seg):
    """Time-weighted statistics of a step function."""
    tot = float(seg.sum())
    o = np.argsort(lev, kind="stable")
    l, w = lev[o], seg[o].astype(np.float64)
    cw = np.cumsum(w)

    def q(p):
        return int(l[min(len(l) - 1, int(np.searchsorted(cw, p * tot, side="left")))])

    alive = float((lev.astype(np.float64) * seg).sum())
    return dict(mean=alive / tot, p50=q(.5), p95=q(.95), p99=q(.99), max=int(lev.max()),
                span_s=tot / US, alive_s=alive / US)


def overlap(s1, e1, s2, e2):
    """Length of the intersection of the unions of two interval sets."""
    if len(s1) == 0 or len(s2) == 0:
        return 0.0
    x = np.concatenate([s1, e1, s2, e2])
    n1, n2 = len(s1), len(s2)
    d1 = np.concatenate([np.ones(n1, np.int8), -np.ones(n1, np.int8), np.zeros(2 * n2, np.int8)])
    d2 = np.concatenate([np.zeros(2 * n1, np.int8), np.ones(n2, np.int8), -np.ones(n2, np.int8)])
    o = np.lexsort((np.minimum(d1 + d2, 0), x))
    a = np.cumsum(d1[o].astype(np.int32))[:-1]
    b = np.cumsum(d2[o].astype(np.int32))[:-1]
    seg = np.diff(x[o])
    return float(seg[(a > 0) & (b > 0)].sum())


def union_len(u, s, e):
    if len(s) == 0:
        return 0.0
    _, ms, me = merge_sessions(u, s, e, 0)
    return float((me - ms).sum())


# --------------------------------------------------------------------------- #
# inputs
# --------------------------------------------------------------------------- #
def read_pool(pool_cs):
    evs, lgs = [], []
    for s in POOL:
        assert s not in SEALED, s
        evs.append(pd.read_parquet(os.path.join(PQ, "events", f"{s}.parquet"),
                                   columns=["semester", "class", "user", "ts", "kind",
                                            "exec_time"]))
        lgs.append(pd.read_parquet(os.path.join(PQ, "logins", f"{s}.parquet")))
    ev = pd.concat(evs, ignore_index=True)
    lg = pd.concat(lgs, ignore_index=True)
    n_nat = (int(ev["ts"].isna().sum()), int(lg["ts"].isna().sum()))
    ev = ev[ev["ts"].notna()].reset_index(drop=True)
    lg = lg[lg["ts"].notna()].reset_index(drop=True)
    for f in (ev, lg):
        f["cs"] = f["semester"].astype(str) + "|" + f["class"].astype(str)
        f["t"] = f["ts"].values.astype("datetime64[s]").astype("int64") * US
    n_all = len(ev)
    ev = ev[ev["cs"].isin(pool_cs)].reset_index(drop=True)
    lg = lg[lg["cs"].isin(pool_cs)].reset_index(drop=True)
    ev["is_sub"] = (ev["kind"].astype(str).values == "submit") & ev["exec_time"].notna().values
    C = np.where(ev["is_sub"].values,
                 np.nan_to_num(ev["exec_time"].values.astype("float64")), 0.0)
    ev["Ccap_us"] = np.rint(np.minimum(C, L_CAP) * US).astype(np.int64)
    ev["Craw_us"] = np.rint(C * US).astype(np.int64)
    log(f"unparsable timestamps dropped: {n_nat[0]} event rows, {n_nat[1]} login rows; "
        f"events outside the pool's {len(pool_cs)} class-semesters dropped: {n_all - len(ev):,}")
    return ev, lg


def sem_arrays(e, g):
    """Per-semester arrays with a dense user code; the container unit is the user.
    `g` is deduplicated by (user, ts, kind) and clipped to the semester's event window."""
    org = int(e["t"].min())
    hi = int(e["t"].max())
    n_lg_raw = len(g)
    g = g.drop_duplicates(subset=["user", "t", "kind"])
    n_dedup = len(g)
    g = g[(g["t"] >= org) & (g["t"] <= hi)]
    users = pd.Index(sorted(set(e["user"].astype(str))))
    g = g[g["user"].astype(str).isin(set(users))]
    ue = users.get_indexer(e["user"].astype(str)).astype(np.int64)
    ul = (users.get_indexer(g["user"].astype(str)).astype(np.int64) if len(g)
          else np.zeros(0, np.int64))
    te = e["t"].values - org
    sub = e["is_sub"].values
    # each user's primary class: the one with most of their events
    pc = (e.assign(one=1).groupby(["user", "cs"], observed=True)["one"].sum()
          .reset_index().sort_values(["user", "one"], kind="mergesort")
          .drop_duplicates("user", keep="last").set_index("user")["cs"])
    n_multi = int((e.groupby("user", observed=True)["cs"].nunique() > 1).sum())
    A = dict(org=org, users=users, n_users=len(users), u_ev=ue, ev_e=te,
             ev_s=te - e["Ccap_us"].values, u_lg=ul,
             lg_t=(g["t"].values - org) if len(g) else np.zeros(0, np.int64),
             lg_out=((g["kind"].astype(str).values == "logout") if len(g)
                     else np.zeros(0, bool)),
             n_sub=int(sub.sum()), n_test=int((~sub).sum()),
             work_cap_s=float(e["Ccap_us"].values[sub].sum()) / US,
             work_raw_s=float(e["Craw_us"].values[sub].sum()) / US,
             cs_of_user=np.asarray(pc.reindex(users).values, dtype=object),
             n_multi_class=n_multi, n_lg_raw=n_lg_raw, n_lg_dedup=n_dedup,
             n_lg_window=int(len(g)), win_s=(hi - org) / US)
    A["ex_u"], A["ex_s"], A["ex_e"] = ue[sub], A["ev_s"][sub], te[sub]
    A["exec_union_s"] = union_len(A["ex_u"], A["ex_s"], A["ex_e"]) / US
    assert A["ev_e"].max() < UOFF, f"semester span {A['ev_e'].max() / US / 86400:.0f} d"
    return A


def login_defs(A):
    """(login_obs, login_act) as (u, s, e) triples, plus the pairing diagnostics."""
    u, t, out = A["u_lg"], A["lg_t"], A["lg_out"]
    z = np.zeros(0, np.int64)
    diag = dict(logins=int((~out).sum()), logouts=int(out.sum()), paired=0, censored=0,
                censored_with_activity=0)
    if len(u) == 0:
        return (z, z, z), (z, z, z), diag
    o = np.lexsort((out, t, u))                        # a login precedes a logout at a tie
    u, t, out = u[o], t[o], out[o]
    last = np.empty(len(u), bool)
    last[-1] = True
    last[:-1] = u[1:] != u[:-1]
    nxt_t = np.where(last, 0, np.roll(t, -1))
    nxt_out = np.where(last, False, np.roll(out, -1))
    is_in = ~out
    paired = is_in & nxt_out
    diag["paired"] = int(paired.sum())
    obs = (u[paired], t[paired], nxt_t[paired])
    uu, s = u[is_in], t[is_in]
    lim = np.where(last[is_in], UOFF - 1, nxt_t[is_in])
    eo = np.lexsort((A["ev_e"], A["u_ev"]))
    ee = A["ev_e"][eo]
    ek = A["u_ev"][eo] * UOFF + ee
    lo = np.searchsorted(ek, uu * UOFF + s, side="left")
    hi = np.searchsorted(ek, uu * UOFF + lim, side="right")
    have = hi > lo
    cand = np.where(have, ee[np.clip(hi - 1, 0, len(ee) - 1)], s)
    cens = ~nxt_out[is_in]
    diag["censored"] = int(cens.sum())
    diag["censored_with_activity"] = int((cens & have).sum())
    e_act = np.maximum(np.where(cens, cand, nxt_t[is_in]), s)
    if diag["paired"]:
        d = (obs[2] - obs[1]) / US
        diag["paired_dur_s"] = [float(np.percentile(d, p)) for p in (10, 50, 90, 99)] + \
                               [float(d.max())]
    return obs, (uu, s, e_act), diag


def all_defs(A):
    """name -> (u, s, e) rebased container-alive intervals."""
    out = {}
    obs, act, diag = login_defs(A)
    out["login_obs"], out["login_act"] = obs, act
    for g in GAPS:
        out[f"proxy{g}"] = merge_sessions(A["u_ev"], A["ev_s"], A["ev_e"], g * US)
    u2 = np.concatenate([A["u_ev"], A["u_lg"]])
    s2 = np.concatenate([A["ev_s"], A["lg_t"]])
    e2 = np.concatenate([A["ev_e"], A["lg_t"]])
    out["proxy1800_lg"] = merge_sessions(u2, s2, e2, 1800 * US)
    return out, diag


def exec_inside(A, use, mask=None):
    """Executing seconds inside a set of alive intervals (optionally one user subset)."""
    u, s, e = use
    xu, xs, xe = A["ex_u"], A["ex_s"], A["ex_e"]
    if mask is not None:
        k = mask[u]
        u, s, e = u[k], s[k], e[k]
        kx = mask[xu]
        xu, xs, xe = xu[kx], xs[kx], xe[kx]
    if len(s) == 0 or len(xs) == 0:
        return 0.0
    return overlap(xu * UOFF + xs, xu * UOFF + xe, u * UOFF + s, u * UOFF + e) / US


# --------------------------------------------------------------------------- #
def main():
    sys.path.insert(0, V2)
    import service_precheck_v2 as b                       # noqa: E402  read-only reuse
    evc = b.load_events(CACHE)
    D = b.prep(evc)
    S = b.static_sub(evc, D)
    I = b.p2_inputs(D, S, CFG, CACHE)
    del evc, D, S
    pool_cs = list(I["pool"])
    base = {cs: int(round(I["per_cs"][cs]["base"] * US)) for cs in pool_cs}
    entries = b.ms_entries(pool_cs, COPIES, REP)
    log(f"overlay: {len(pool_cs)} class-semesters x {COPIES} copies = {len(entries)} "
        f"entries; simulated jobs {I['info']['jobs']:,}, work {I['info']['work_s']:,.1f} s")

    ev, lg = read_pool(set(pool_cs))
    A_of, D_of, diag_of = {}, {}, {}
    for sem in POOL:
        A = sem_arrays(ev[ev["semester"] == sem], lg[lg["semester"] == sem])
        d, diag = all_defs(A)
        A_of[sem], D_of[sem], diag_of[sem] = A, d, diag
        log(f"{sem}: users={A['n_users']:4d} (multi-class {A['n_multi_class']}) "
            f"events={len(A['u_ev']):7,d} submissions={A['n_sub']:6,d} | login rows "
            f"{A['n_lg_raw']:6,d} -> dedup {A['n_lg_dedup']:6,d} -> in window "
            f"{A['n_lg_window']:6,d} (logins {diag['logins']:5,d}, logouts "
            f"{diag['logouts']:5,d}, login->logout pairs {diag['paired']:5,d} = "
            f"{diag['paired'] / max(1, diag['logins']):.1%})")

    res = {"pool_cs": pool_cs, "semesters": {}, "overlay": {},
           "sim": {"jobs": int(I["info"]["jobs"]), "work_s": float(I["info"]["work_s"]),
                   "copies": COPIES, "rep": REP, "entries": len(entries)},
           "defs": DEFS, "primary_def": PRIMARY_DEF, "diag": {}}

    # ---------------- per semester ----------------
    for sem in POOL:
        A, d = A_of[sem], D_of[sem]
        row = {k: A[k] for k in ("n_users", "n_sub", "n_test", "work_cap_s", "work_raw_s",
                                 "exec_union_s", "n_multi_class", "n_lg_raw",
                                 "n_lg_dedup", "n_lg_window", "win_s")}
        row.update({k: diag_of[sem][k] for k in ("logins", "logouts", "paired", "censored")})
        row["defs"] = {}
        for nm in DEFS:
            u, s, e = d[nm]
            if len(s) == 0:
                continue
            lev, seg = levels(s, e)
            st = tw_stats(lev, seg)
            st["n_sessions"] = int(len(s))
            st["exec_inside_s"] = exec_inside(A, d[nm])
            st["util"] = st["exec_inside_s"] / st["alive_s"] if st["alive_s"] else float("nan")
            row["defs"][nm] = st
        res["semesters"][sem] = row
        res["diag"][sem] = diag_of[sem]
        p = row["defs"].get(PRIMARY_DEF, {})
        log(f"{sem}: {PRIMARY_DEF} sessions={p.get('n_sessions'):6,d} "
            f"mean={p.get('mean', float('nan')):6.2f} p95={p.get('p95')} "
            f"p99={p.get('p99')} max={p.get('max')} util={p.get('util', float('nan')):.4f}")

    # ---------------- overlay ----------------
    # every container is attached to its user's primary class-semester; the copy shifts
    # are the ones the simulated trace uses.
    cs_idx = {}
    for sem in POOL:
        A = A_of[sem]
        cu = A["cs_of_user"]
        for cs in set(cu):
            cs_idx[cs] = (sem, np.asarray(cu == cs))
    miss = [cs for cs in pool_cs if cs not in cs_idx]
    log(f"class-semesters with no container (no user has them as primary class): {miss}")

    per_cs_def = {}
    per_cs_exec = {}
    for cs in pool_cs:
        if cs not in cs_idx:
            per_cs_def[cs] = {nm: (np.zeros(0, np.int64), np.zeros(0, np.int64))
                              for nm in DEFS}
            per_cs_exec[cs] = {nm: 0.0 for nm in DEFS}
            continue
        sem, mask = cs_idx[cs]
        A, d = A_of[sem], D_of[sem]
        per_cs_def[cs] = {}
        per_cs_exec[cs] = {}
        for nm in DEFS:
            u, s, e = d[nm]
            k = mask[u] if len(u) else np.zeros(0, bool)
            per_cs_def[cs][nm] = (s[k] + A["org"], e[k] + A["org"])
            per_cs_exec[cs][nm] = exec_inside(A, d[nm], mask)

    for nm in DEFS:
        ss = [per_cs_def[cs][nm][0] + base[cs] + j * WEEK * US for cs, j in entries]
        ee = [per_cs_def[cs][nm][1] + base[cs] + j * WEEK * US for cs, j in entries]
        s, e = np.concatenate(ss), np.concatenate(ee)
        del ss, ee
        if len(s) == 0:
            continue
        lev, seg = levels(s, e)
        st = tw_stats(lev, seg)
        st["n_sessions"] = int(len(s))
        st["exec_inside_s"] = sum(per_cs_exec[cs][nm] for cs, _ in entries)
        st["util"] = st["exec_inside_s"] / st["alive_s"] if st["alive_s"] else float("nan")
        res["overlay"][nm] = st
        log(f"overlay {nm:13s}: sessions={st['n_sessions']:9,d} mean={st['mean']:8.2f} "
            f"p95={st['p95']:5d} p99={st['p99']:5d} max={st['max']:5d} "
            f"span={st['span_s'] / 86400:7.2f} d util={st['util']:.4f}")
        del s, e, lev, seg

    cs_union = {}
    for cs in pool_cs:
        if cs not in cs_idx:
            cs_union[cs] = 0.0
            continue
        sem, mask = cs_idx[cs]
        A = A_of[sem]
        k = mask[A["ex_u"]]
        cs_union[cs] = union_len(A["ex_u"][k], A["ex_s"][k], A["ex_e"][k]) / US
    res["overlay_exec_union_s"] = sum(cs_union[cs] for cs, _ in entries)
    per_cs_work = (ev[ev["is_sub"]].groupby("cs", observed=True)["Ccap_us"].sum() / US).to_dict()
    res["overlay_work_cap_s"] = sum(per_cs_work.get(cs, 0.0) for cs, _ in entries)
    res["overlay_sim_work_s"] = float(I["info"]["work_s"]) * COPIES
    with open(os.path.join(HERE, "dedicated.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1, default=float)
    log(f"overlay executed seconds: all submissions, sum of C_cap "
        f"{res['overlay_work_cap_s']:,.0f} s; simulated job set "
        f"{res['overlay_sim_work_s']:,.0f} s")
    log("wrote dedicated.json")


if __name__ == "__main__":
    main()
