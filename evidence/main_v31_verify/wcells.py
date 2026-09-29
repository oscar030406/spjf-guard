"""V3/V5/V6: re-simulate whole cells of v3.1 with code the builder did not write.

Work-budget guards and the completion-charged skip come from the v3 verifier's `vsim`
(re-validated in wrevalidate.py, sha256 recorded there); the dispatch-charged skip is
mine (wskip.py).  Every metric, every gap and both per-job bounds are recomputed here.

usage: wcells.py --trace primary --rep 0 --level 2 [--workers 4] [--set main|grid]
output: <scratch>/mv31_verify/cells/<tag>.csv  and an appended out_cells.txt
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

sys.dont_write_bytecode = True
for _v in ("PYTHONHOME", "PYTHONPATH", "UV_INTERNAL__PYTHONHOME"):
    os.environ.pop(_v, None)
os.environ.setdefault("NUMBA_NUM_THREADS", "4")
os.environ.setdefault("OMP_NUM_THREADS", "4")

import numpy as np                                                      # noqa: E402
import pandas as pd                                                     # noqa: E402

ROOT = r"<repo-root>"
VDIR = os.path.join(ROOT, "evidence", "main_v3_verify")
HERE = os.path.dirname(os.path.abspath(__file__))
SCRATCH = r"<cache-dir>"
WORK = os.path.join(SCRATCH, "mv31_verify")
CELLS = os.path.join(WORK, "cells")
TMP = os.path.join(WORK, "tmp")
for d in (WORK, CELLS, TMP):
    os.makedirs(d, exist_ok=True)
sys.path.insert(0, VDIR)
sys.path.insert(0, HERE)

L = 60.0
SEED = 3                       # service_precheck_v2.SEED, used for the 'random' predictor
GS = (300.0, 600.0, 1200.0)
SEL_CAP = {300.0: (30.0, 0.5), 600.0: (120.0, 0.75), 1200.0: (120.0, 0.9)}
SEL_FIXSEL = {300.0: 120.0, 600.0: 600.0, 1200.0: 600.0}
ADV_G = 600.0
_A = {}


def bmax_of(G, k):
    return float(k) * (G - (3.0 - 2.0 / k) * L)


def ncap_dispatch(G, k):
    n = 0
    while (n + 1 + 2 * k - 2) * L / k <= G + 1e-12:
        n += 1
    return n


def ncap_completion(G, k):
    n = 0
    while (n + 1 + 3 * k - 2) * L / k <= G + 1e-12:
        n += 1
    return n


def _init(names):
    for n in names:
        _A[n] = np.load(os.path.join(TMP, n + ".npy"), mmap_mode="r")


def _task(t):
    import vsim
    import wskip
    t0 = time.time()
    a = np.ascontiguousarray(_A["a"])
    svc = np.ascontiguousarray(_A["svc"])
    wf = np.asarray(_A["wf"])
    k = t["k"]
    pred = None if t["pri"] is None else np.ascontiguousarray(_A["pri_" + t["pri"]])
    kind = t["kind"]
    if kind == "fcfs":
        r = vsim.run(a, svc, k, "fcfs")
        w, qwf = r["w"], 0.0
        ub = None
    elif kind == "pri":
        r = vsim.run(a, svc, k, "pri", pred=pred)
        w, qwf = r["w"], 0.0
        ub = None
    elif kind == "skip":                                   # dispatch charge (mine)
        w, nf, qt, qf = wskip.fast(a, svc, pred, k, t["N"])
        qwf = qf / max(qt, 1)
        ub = wf + (t["N"] + 2.0 * k - 2.0) * L / k
    elif kind == "skipc":                                  # completion charge (vsim)
        r = vsim.run(a, svc, k, "skip", pred=pred, Ncap=t["N"])
        w, qwf = r["w"], r["qw_forced_frac"]
        ub = wf + (t["N"] * L + (3.0 * k - 2.0) * L) / k
    else:                                                  # work budget
        r = vsim.run(a, svc, k, "cap", pred=pred, B0=t["B0"], eta=t["eta"],
                     Bmax=t["Bmax"])
        w, qwf = r["w"], r["qw_forced_frac"]
        # budget(q,t) = min(B0 + eta*k*(t-a_q), Bmax): with eta = 0 the cap in force is
        # B0 itself, so Theorem A is applied with the effective cap.
        beff = t["B0"] if t["eta"] == 0.0 else t["Bmax"]
        ubA = wf + beff / k + (3.0 - 2.0 / k) * L
        ubB = ((wf + t["B0"] / k + (3.0 - 2.0 / k) * L) / (1.0 - t["eta"])
               if t["eta"] > 0 else None)
        ub = ubA if ubB is None else np.minimum(ubA, ubB)
    ex = w - wf
    dl = np.asarray(_A["dl"]).astype(bool)
    hvt = np.asarray(_A["hvt"]).astype(bool)
    q1 = wf <= 1.0
    row = dict(policy=t["name"], kind=kind, G=t["G"], B0=t["B0"], eta=t["eta"],
               Bmax=t["Bmax"], Ncap=t["N"], k=k,
               w_mean=float(w.mean()), w_p99=float(np.quantile(w, 0.99)),
               w_p99_dl=float(np.quantile(w[dl], 0.99)),
               max_heavy=float(w[hvt].max()),
               max_excess=float(ex.max()), harm_wf1s=float(ex[q1].max()),
               qw_forced_frac=float(qwf))
    if ub is None:
        row.update(bound_viol=-1, used_over_allowed=np.nan, guar_excess_max=np.inf,
                   bound_violA=-1, bound_violB=-1, usedA=np.nan, usedB=np.nan)
    else:
        row["bound_viol"] = int((w > ub + 1e-6).sum())
        row["used_over_allowed"] = float(np.max(ex / np.maximum(ub - wf, 1e-12)))
        row["guar_excess_max"] = float((ub - wf).max())
        if kind in ("cap", "fix", "fixsel"):
            row["bound_violA"] = int((w > ubA + 1e-6).sum())
            row["usedA"] = float(np.max(ex / np.maximum(ubA - wf, 1e-12)))
            if ubB is not None:
                row["bound_violB"] = int((w > ubB + 1e-6).sum())
                row["usedB"] = float(np.max(ex / np.maximum(ubB - wf, 1e-12)))
            else:
                row["bound_violB"], row["usedB"] = -1, np.nan
        else:
            row["bound_violA"] = row["bound_viol"]
            row["usedA"] = row["used_over_allowed"]
            row["bound_violB"], row["usedB"] = -1, np.nan
    row["nchecks"] = 0 if ub is None else len(w)
    row["sec"] = round(time.time() - t0, 1)
    return row, None


def adv_pred(kind, svc, base):
    if kind == "reversed":
        return -svc
    if kind == "random":
        return np.random.default_rng(SEED).permutation(svc)
    if kind == "top1short":
        p = base.copy()
        p[np.argsort(-svc, kind="stable")[:max(1, len(svc) // 100)]] = p.min() - 1.0
        return p
    raise SystemExit(kind)


def build(pset, k, Z):
    out = []
    pri = {"svc": np.asarray(Z["svc"], np.float64)}
    out.append(dict(name="FCFS", pri=None, kind="fcfs", G=-1.0, B0=-1.0, eta=-1.0,
                    Bmax=0.0, N=-1))
    out.append(dict(name="SJF-ref", pri="svc", kind="pri", G=-1.0, B0=-1.0, eta=-1.0,
                    Bmax=0.0, N=-1))
    if pset == "fixgrid":
        # a FINER fixed-budget grid than the builder's {30, 120, 600} k/4 + Bmax.
        # With eta = 0 the budget is the constant min(B0, Bmax), so one run per B0
        # serves every G for which B0 <= Bmax(G); feasibility is judged per G.
        pri["tweedie"] = np.asarray(Z["tweedie"], np.float64)
        out.append(dict(name="SPJF-tweedie", pri="tweedie", kind="pri", G=-1.0,
                        B0=-1.0, eta=-1.0, Bmax=0.0, N=-1))
        for b0b in (30.0, 60.0, 90.0, 120.0, 180.0, 240.0, 300.0, 360.0, 420.0, 480.0,
                    540.0, 600.0, 900.0, 1200.0, 2400.0, 4800.0):
            b0 = b0b * k / 4.0
            out.append(dict(name=f"FIXG-B{b0b:g}", pri="tweedie", kind="fix",
                            G=-1.0, B0=b0, eta=0.0, Bmax=b0, N=0))
        return out, pri
    if pset == "grid":
        pri["tweedie"] = np.asarray(Z["tweedie"], np.float64)
        out.append(dict(name="SPJF-tweedie", pri="tweedie", kind="pri", G=-1.0,
                        B0=-1.0, eta=-1.0, Bmax=0.0, N=-1))
        # the three v3.1 picks plus the rejected v3 G = 600 setting
        for nm, G, b0b, eta in (("CAP-G300-B30-e0.5", 300.0, 30.0, 0.5),
                                ("CAP-G600-B120-e0.75", 600.0, 120.0, 0.75),
                                ("CAP-G1200-B120-e0.9", 1200.0, 120.0, 0.9),
                                ("CAP-G600-B30-e0.9", 600.0, 30.0, 0.9),
                                ("FIXSEL-G300", 300.0, 120.0, 0.0),
                                ("FIXSEL-G600", 600.0, 600.0, 0.0)):
            bm = bmax_of(G, k)
            out.append(dict(name=nm, pri="tweedie", kind="cap", G=G,
                            B0=min(b0b * k / 4.0, bm), eta=eta, Bmax=bm, N=0))
        for G in GS:
            bm = bmax_of(G, k)
            out.append(dict(name=f"FIX-G{G:g}", pri="tweedie", kind="fix", G=G, B0=bm,
                            eta=0.0, Bmax=bm, N=0))
        return out, pri
    for s in ("M4", "M4refit", "tweedie", "tweedie_itr", "r1s"):
        if s in Z:
            pri[s] = np.asarray(Z[s], np.float64)
            out.append(dict(name=f"SPJF-{s}", pri=s, kind="pri", G=-1.0, B0=-1.0,
                            eta=-1.0, Bmax=0.0, N=-1))
    for G in GS:
        bm = bmax_of(G, k)
        out.append(dict(name=f"FIX-G{G:g}", pri="tweedie", kind="fix", G=G, B0=bm,
                        eta=0.0, Bmax=bm, N=0))
        out.append(dict(name=f"FIXSEL-G{G:g}", pri="tweedie", kind="fixsel", G=G,
                        B0=min(SEL_FIXSEL[G] * k / 4.0, bm), eta=0.0, Bmax=bm, N=0))
        b0b, eta = SEL_CAP[G]
        out.append(dict(name=f"CAP-G{G:g}", pri="tweedie", kind="cap", G=G,
                        B0=min(b0b * k / 4.0, bm), eta=eta, Bmax=bm, N=0))
        out.append(dict(name=f"SKIP-G{G:g}", pri="tweedie", kind="skip", G=G, B0=-1.0,
                        eta=0.0, Bmax=0.0, N=ncap_dispatch(G, k)))
        out.append(dict(name=f"SKIPC-G{G:g}", pri="tweedie", kind="skipc", G=G, B0=-1.0,
                        eta=0.0, Bmax=0.0, N=ncap_completion(G, k)))
    for adv in ("reversed", "random", "top1short"):
        pri[adv] = adv_pred(adv, pri["svc"], pri["tweedie"])
        out.append(dict(name=f"SPJF-{adv}", pri=adv, kind="pri", G=-1.0, B0=-1.0,
                        eta=-1.0, Bmax=0.0, N=-1))
        b0b, eta = SEL_CAP[ADV_G]
        bm = bmax_of(ADV_G, k)
        out.append(dict(name=f"CAP-G{ADV_G:g}-{adv}", pri=adv, kind="cap", G=ADV_G,
                        B0=min(b0b * k / 4.0, bm), eta=eta, Bmax=bm, N=0))
    return out, pri


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace", default="primary")
    ap.add_argument("--rep", type=int, default=0)
    ap.add_argument("--level", type=int, default=2)
    ap.add_argument("--set", dest="pset", default="main")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()

    import vsim
    tag = f"{a.trace}_rep{a.rep}_L{a.level}_{a.pset}"
    t0 = time.time()
    z = np.load(os.path.join(SCRATCH, "mv31", "traces", f"{a.trace}_rep{a.rep}.npz"))
    Z = {q: z[q] for q in z.files}
    K = list(Z["K"])
    k = int(K[a.level]) if len(K) > 1 else int(K[0])
    A = np.ascontiguousarray(Z["a"], np.float64)
    S = np.ascontiguousarray(Z["svc"], np.float64)
    wf = vsim.run(A, S, k, "fcfs")["w"]
    log = open(os.path.join(HERE, "out_cells.txt"), "a", encoding="utf-8")

    def say(*x):
        s = " ".join(str(y) for y in x)
        print(s, flush=True)
        log.write(s + "\n")
        log.flush()

    say(f"## {time.strftime('%Y-%m-%d %H:%M:%S')} {tag}  k={k} n={len(A):,} "
        f"argv={' '.join(sys.argv[1:])}")
    pol, pri = build(a.pset, k, Z)
    np.save(os.path.join(TMP, "a.npy"), A)
    np.save(os.path.join(TMP, "svc.npy"), S)
    np.save(os.path.join(TMP, "wf.npy"), wf)
    for q in ("dl", "hvt", "wk"):
        np.save(os.path.join(TMP, q + ".npy"), np.asarray(Z[q]))
    names = ["a", "svc", "wf", "dl", "hvt", "wk"]
    for nm in {p["pri"] for p in pol if p["pri"]}:
        np.save(os.path.join(TMP, "pri_" + nm + ".npy"), pri[nm])
        names.append("pri_" + nm)
    say(f"   jobs FCFS would start within 1 s: {int((wf <= 1.0).sum()):,} "
        f"({(wf <= 1.0).mean() * 100:.1f}%)")
    for p in pol:
        p.update(k=k, boot=False)
    del Z, pri, A, S, wf
    with ProcessPoolExecutor(max_workers=min(a.workers, len(pol)),
                             initializer=_init, initargs=(names,)) as ex:
        res = list(ex.map(_task, pol))
    rows = [r[0] for r in res]
    d = pd.DataFrame(rows)
    d.insert(0, "level", a.level)
    d.insert(0, "rep", a.rep)
    d.insert(0, "trace", a.trace)
    d.to_csv(os.path.join(CELLS, f"{tag}.csv"), index=False)
    s = d.set_index("policy")
    fq, sq = s.loc["FCFS", "w_p99_dl"], s.loc["SJF-ref", "w_p99_dl"]
    s["gap"] = (fq - s.w_p99_dl) / (fq - sq)
    say(s[["w_p99_dl", "gap", "w_mean", "w_p99", "max_excess", "harm_wf1s", "max_heavy",
           "qw_forced_frac", "guar_excess_max", "used_over_allowed", "usedA", "usedB",
           "bound_viol", "bound_violA", "bound_violB", "sec"]].round(4).to_string())
    gcheck = int(d[d.bound_viol >= 0].bound_viol.sum())
    gA = int(d[d.bound_violA >= 0].bound_violA.sum())
    gB = int(d[d.bound_violB >= 0].bound_violB.sum())
    nch = int(d[d.bound_viol >= 0].nchecks.sum())
    say(f"   per-job bound checks {nch:,}; violations combined {gcheck}, "
        f"Theorem A form {gA}, Theorem B (eta) form {gB}")
    say(f"## done in {time.time() - t0:.0f} s")
    log.close()


if __name__ == "__main__":
    main()
