"""C2/C3/C6: rerun a full cell of the main experiment with MY simulator and compare every
metric with the builder's stored row for that cell.

The trace (arrivals, true service times, ranking scores, deadline-window and heavy flags)
is read from the builder's trace file; everything downstream -- the schedule, the waits,
the metrics and the per-job bound -- is computed here.

    vbig.py --trace primary --rep 0 --level 2 --policies FCFS,SJF-ref,SPJF-tweedie,CAP-G600

Writes one row per policy to <scratch>/mv3_verify/vcell_<trace>_rep<r>_L<l>.csv and prints
the difference against <scratch>/mv3/sim/<trace>_rep<r>_L<l>_main.csv.
"""
from __future__ import annotations

import argparse
import os
import time

import numpy as np
import pandas as pd

import vsim
from vsim import L, SCRATCH, WORK

BUILDER_SIM = os.path.join(SCRATCH, "mv3", "sim")
GS = (300.0, 600.0, 1200.0)
SEL = {300.0: (30.0, 0.5), 600.0: (30.0, 0.9), 1200.0: (120.0, 0.9)}   # selected_params.csv


def adv_pred(kind, svc, base, seed=3):
    if kind == "reversed":
        return -svc
    if kind == "random":
        return np.random.default_rng(seed).permutation(svc)
    if kind == "top1short":
        p = base.copy()
        p[np.argsort(-svc, kind="stable")[:max(1, len(svc) // 100)]] = p.min() - 1.0
        return p
    raise SystemExit(kind)


def policy_spec(name, k, Z):
    """(kwargs for vsim.run, kwargs for vsim.bound)"""
    if name == "FCFS":
        return dict(policy="fcfs"), None
    if name == "SJF-ref":
        return dict(policy="pri", pred=Z["svc"]), None
    if name.startswith("SPJF-"):
        s = name[5:]
        pred = Z[s] if s in Z else adv_pred(s, Z["svc"], Z["tweedie"])
        return dict(policy="pri", pred=pred), None
    G = float(name.split("-G")[1].split("-")[0])
    adv = name.split("-")[2] if name.count("-") >= 2 else None
    pred = Z["tweedie"] if adv is None else adv_pred(adv, Z["svc"], Z["tweedie"])
    Bmax = vsim.gmax(G, k)
    if name.startswith("CAP"):
        b0b, eta = SEL[G]
        B0 = min(b0b * k / 4.0, Bmax)
        return (dict(policy="cap", pred=pred, B0=B0, eta=eta, Bmax=Bmax),
                dict(B0=B0, eta=eta, Bmax=Bmax))
    if name.startswith("FIX"):
        return (dict(policy="cap", pred=pred, B0=Bmax, eta=0.0, Bmax=Bmax),
                dict(B0=Bmax, eta=0.0, Bmax=Bmax))
    if name.startswith("SKIP"):
        n = vsim.skip_n(G, k)
        return dict(policy="skip", pred=pred, Ncap=n), dict(Ncap=n)
    if name.startswith("XSKIP"):          # C5: the count a dispatch-time charge allows
        n = int(round(G * k / L - (2 * k - 2)))
        return dict(policy="skip", pred=pred, Ncap=n), dict(Ncap=n)
    raise SystemExit(name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace", default="primary")
    ap.add_argument("--rep", type=int, default=0)
    ap.add_argument("--level", type=int, default=2)
    ap.add_argument("--policies", default="FCFS,SJF-ref,SPJF-tweedie,CAP-G600")
    a = ap.parse_args()
    pols = a.policies.split(",")

    need = {"a", "svc", "dl", "hvt", "K", "W"}
    for p in pols:
        if p.startswith("SPJF-"):
            need.add(p[5:])
    need |= {"tweedie"}
    z = np.load(os.path.join(vsim.BUILDER_TRACES, f"{a.trace}_rep{a.rep}.npz"))
    Z = {q: z[q] for q in z.files if q in need or q in ("svc", "a")}
    K = list(Z["K"])
    k = int(K[a.level]) if len(K) > 1 else int(K[0])
    n = len(Z["a"])
    dl, hvt = Z["dl"].astype(bool), Z["hvt"].astype(bool)
    print(f"{a.trace} rep{a.rep} level{a.level}: k={k} n={n:,} dl={dl.sum():,} "
          f"heavy={hvt.sum():,} W={float(Z['W']):,.1f}", flush=True)

    t0 = time.time()
    wf = vsim.run(Z["a"], Z["svc"], k, policy="fcfs")["w"]
    print(f"[{time.time() - t0:5.0f}s] FCFS done", flush=True)
    # independent check of FCFS: Kiefer-Wolfowitz on free-server times
    free = np.zeros(k)
    chk = np.empty(min(n, 2_000_000))
    for i in range(len(chk)):
        j = int(np.argmin(free))
        st = max(Z["a"][i], free[j])
        chk[i] = st - Z["a"][i]
        free[j] = st + Z["svc"][i]
    print(f"FCFS vs an independent recursion on the first {len(chk):,} jobs: "
          f"max |diff| {np.abs(chk - wf[:len(chk)]).max():g}", flush=True)
    q1 = wf <= 1.0
    rows = []
    for nm in pols:
        t1 = time.time()
        kw, bkw = policy_spec(nm, k, Z)
        r = vsim.run(Z["a"], Z["svc"], k, **kw)
        w = r["w"]
        ex = w - wf
        row = dict(trace=a.trace, rep=a.rep, level=a.level, k=k, policy=nm,
                   w_p99_dl=float(np.quantile(w[dl], .99)), w_mean=float(w.mean()),
                   w_p99=float(np.quantile(w, .99)), max_excess=float(ex.max()),
                   harm_wf1s=float(ex[q1].max()), max_heavy=float(w[hvt].max()),
                   qw_forced_frac=r["qw_forced_frac"], sec=round(time.time() - t1, 1))
        if bkw is not None:
            ub = vsim.bound(wf, k, **bkw)
            row["bound_viol"] = int((w > ub + 1e-6).sum())
            row["used_over_allowed"] = float(np.max(ex / np.maximum(ub - wf, 1e-12)))
            row["guar_excess_max"] = float((ub - wf).max())
        rows.append(row)
        print(f"[{time.time() - t0:5.0f}s] {nm:22s} p99dl {row['w_p99_dl']:9.4f}  "
              f"mean {row['w_mean']:8.4f}  maxex {row['max_excess']:9.2f}  "
              f"harm {row['harm_wf1s']:8.2f}  viol {row.get('bound_viol', '-')}",
              flush=True)
    mine = pd.DataFrame(rows)
    out = os.path.join(WORK, f"vcell_{a.trace}_rep{a.rep}_L{a.level}.csv")
    mine.to_csv(out, index=False)

    bp = os.path.join(BUILDER_SIM, f"{a.trace}_rep{a.rep}_L{a.level}_main.csv")
    if os.path.exists(bp):
        b = pd.read_csv(bp).set_index("policy")
        cols = ["w_p99_dl", "w_mean", "w_p99", "max_excess", "harm_wf1s", "max_heavy",
                "qw_forced_frac", "used_over_allowed"]
        print("\npolicy                 " + "".join(f"{c:>20s}" for c in cols))
        for _, r in mine.iterrows():
            if r.policy not in b.index:
                print(f"{r.policy:22s} not in the builder's cell")
                continue
            d = []
            for c in cols:
                if c in r and np.isfinite(r.get(c, np.nan)) and c in b.columns:
                    bv = float(b.loc[r.policy, c])
                    d.append(f"{float(r[c]) - bv:+20.10g}")
                else:
                    d.append(f"{'-':>20s}")
            print(f"{r.policy:22s}" + "".join(d))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
