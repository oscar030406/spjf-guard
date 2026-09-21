"""Stage 2/3: run one (trace, rep, load level) cell of the experiment.

Pure scheduling: every policy shares the same enqueue times, so the per-job theorem
applies.  The queue is the numba kernel of ../guard_variants/guardkern.py (cross-checked
in mv3_xcheck.py); FCFS is additionally checked against the pipeline's Kiefer-Wolfowitz
recursion.  Metrics and the week-block paired bootstrap are the pipeline's
(SP.wstats / SP.boot_weights / SP.boot_mean / SP.boot_quantile).

EVERY guarded run asserts, for EVERY job,
    W_guard[i] <= min( (k W_FCFS[i] + C_i + Ncap*theta + (3k-2)L) / (k - eps),
                       W_FCFS[i] + (Bmax + Ncap*theta + (3k-2)L) / k )        [Thm A / B]
and records the worst used/allowed ratio max (W_guard - W_FCFS) / (bound - W_FCFS).

policy sets
  grid   the validation selection grid: FCFS, SJF-ref, SPJF-tweedie and, per G, the
         fixed-budget guard plus every (B0, eta) of the grid.  Point estimates only.
  main   the reported policy set: the ranking scores, the selected guards at each G, the
         finite-skip baseline at equal guarantee and the adversarial predictors with and
         without the guard.  With bootstrap replicates.

usage: mv3_run.py --trace primary --rep 0 --level 2 --set main [--workers 6]
"""
from __future__ import annotations

import argparse
import os
import shutil
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

import mv3_common as C
from mv3_common import SP, GK

_A = {}


def _init(d, names):
    for n in names:
        _A[n] = np.load(os.path.join(d, n + ".npy"))


def _adv(kind, svc, base):
    if kind == "reversed":
        return -svc
    if kind == "random":
        return np.random.default_rng(C.SEED).permutation(svc)
    if kind == "top1short":
        p = base.copy()
        p[np.argsort(-svc, kind="stable")[:max(1, len(svc) // 100)]] = p.min() - 1.0
        return p
    raise SystemExit(kind)


def _stats(w, dm, xm, hv, wf, q1):
    q = np.quantile
    ex = w - wf
    d = dict(SP.wstats(w, dm, xm, hv))
    d.update(max_excess=float(ex.max()), mean_excess=float(ex.mean()),
             p99_excess=float(q(ex, .99)),
             harm_wf1s=float(ex[q1].max()) if q1.any() else float("nan"),
             max_excess_dl=float(ex[dm].max()))
    return {k: float(v) for k, v in d.items()}


def _task(t):
    t0 = time.time()
    svc, wf = _A["svc"], _A[f"wf_k{t['k']}"]
    pred = None if t["pri"] is None else _A["pri_" + t["pri"]]
    r = GK.run(_A["a"], svc, t["k"], pred=pred, **t["kw"])
    assert r.err == 0, (t["name"], "segment-tree window too small")
    viol, used, gbound = -1, float("nan"), float("inf")
    if t["kw"]["policy"] == "guard":
        cb = np.zeros(1) if t["kw"].get("B", 0.0) < 0 else r.cbud / 1e6
        ub = GK.guaranteed(wf, t["k"], cb, eps=t["eps"], extra=t["extra"], L=C.L,
                           Bmax=t["bmax"])
        viol = int((r.w > ub + 1e-6).sum())
        assert viol == 0, (t["name"], float((r.w - ub).max()))
        used = float(np.max((r.w - wf) / np.maximum(ub - wf, 1e-12)))
        gbound = float((ub - wf).max())
    st = _stats(r.w, _A["dl"], _A["exam"], _A["hvt"], wf, _A["q1"])
    row = dict(t["base"], policy=t["name"], score=t["pri"] or "-", guard=t["guard"],
               G=t["G"], B0=t["B0"], eta=t["eta"], Bmax=t["bmax"], Ncap=t["ncap"], **st,
               bound_viol=viol, used_over_allowed=used, guar_excess_max=gbound,
               forced_frac=r.n_forced / max(r.n_disp, 1),
               qw_forced_frac=r.qw_forced / max(r.qw_total, 1),
               n_forced=r.n_forced, n_disp=r.n_disp, sim_sec=round(time.time() - t0, 1))
    bw = None
    if t["boot"]:
        M = _A["M"]
        wk = _A["wk"].astype(np.int64)
        bm = SP.boot_mean(r.w, wk, M)
        bq = SP.boot_quantile(r.w[_A["dl"]], wk[_A["dl"]], M, 0.99)
        assert abs(bm[0] - row["w_mean"]) <= 1e-9 * max(1.0, row["w_mean"])
        assert abs(bq[0] - row["w_p99_dl"]) <= 1e-9 * max(1.0, row["w_p99_dl"])
        bw = (bm[1:], bq[1:])
    row["sec"] = round(time.time() - t0, 1)
    return t["name"], row, bw


def build_policies(pset, k, Z, sel):
    """[(name, score key or None, kwargs, eps, extra, Bmax, guard tag, G, B0, eta, Ncap)]"""
    svc = Z["svc"]
    out = [("FCFS", None, dict(policy="fcfs"), 0.0, 0.0, 0.0, "-", -1, -1, -1, -1),
           ("SJF-ref", "svc", dict(policy="pri"), 0.0, 0.0, 0.0, "-", -1, -1, -1, -1)]
    pri = {"svc": svc}
    if pset == "grid":
        pri["tweedie"] = Z["tweedie"]
        out.append(("SPJF-tweedie", "tweedie", dict(policy="pri"), 0, 0, 0, "-", -1, -1, -1, -1))
        for G in C.GS:
            kw, eps, ex, bm = C.guard_kwargs("fix", k, None, G=G)
            kw.pop("pred")
            out.append((f"FIX-G{G:g}", "tweedie", kw, eps, ex, bm, "fix", G, bm, 0.0, 0))
            for b0b in C.B0_BASE:
                for eta in C.ETAS:
                    b0 = b0b * k / 4.0
                    kw, eps, ex, bm = C.guard_kwargs("cap", k, None, B0=b0, eta=eta, G=G)
                    kw.pop("pred")
                    out.append((f"CAP-G{G:g}-B{b0b:g}-e{eta:g}", "tweedie", kw, eps, ex,
                                bm, "cap", G, b0, eta, 0))
        return out, pri
    assert pset == "main"
    extra = tuple(s for s in ("tweedie_itr", "r1s") if s in Z)
    for s in ("M4", "M4refit", "tweedie") + extra:
        pri[s] = Z[s]
        out.append((f"SPJF-{s}", s, dict(policy="pri"), 0, 0, 0, "-", -1, -1, -1, -1))
    for G in C.GS:
        b0b, eta = sel[G]
        b0 = b0b * k / 4.0
        for tag, kw_args in (("fix", dict(G=G)), ("cap", dict(B0=b0, eta=eta, G=G)),
                             ("skip", dict(G=G))):
            kw, eps, ex, bm = C.guard_kwargs(tag, k, None, **kw_args)
            kw.pop("pred")
            nm = {"fix": f"FIX-G{G:g}", "cap": f"CAP-G{G:g}", "skip": f"SKIP-G{G:g}"}[tag]
            out.append((nm, "tweedie", kw, eps, ex, bm, tag, G,
                        bm if tag == "fix" else (b0 if tag == "cap" else -1),
                        0.0 if tag != "cap" else eta,
                        C.skip_ncap(G, k) if tag == "skip" else 0))
    for adv in ("reversed", "random", "top1short"):
        pri[adv] = _adv(adv, svc, Z["tweedie"])
        out.append((f"SPJF-{adv}", adv, dict(policy="pri"), 0, 0, 0, "-", -1, -1, -1, -1))
        b0b, eta = sel[C.ADV_G]
        b0 = b0b * k / 4.0
        kw, eps, ex, bm = C.guard_kwargs("cap", k, None, B0=b0, eta=eta, G=C.ADV_G)
        kw.pop("pred")
        out.append((f"CAP-G{C.ADV_G:g}-{adv}", adv, kw, eps, ex, bm, "cap", C.ADV_G,
                    b0, eta, 0))
    return out, pri


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace", default="primary")
    ap.add_argument("--rep", type=int, default=0)
    ap.add_argument("--level", type=int, default=2)
    ap.add_argument("--set", dest="pset", default="main")
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()

    lg = C.Log("run")
    Z = C.load_trace(a.trace, a.rep)
    K = list(Z["K"])
    k = int(K[a.level]) if len(K) > 1 else int(K[0])
    W = float(Z["W"])
    rho_t = C.RHOS[a.level] if len(K) > 1 else round(W / (3600.0 * k), 2)
    n = len(Z["a"])
    sel = None
    if a.pset == "main":
        s = pd.read_csv(os.path.join(C.HERE, "selected_params.csv")).set_index("G")
        sel = {float(g): (float(s.loc[g, "B0_base"]), float(s.loc[g, "eta"])) for g in s.index}
    tag = f"{a.trace}_rep{a.rep}_L{a.level}_{a.pset}"
    lg.el(f"{tag}: k={k} rho_busy={W / (3600.0 * k):.4f} (target {rho_t}) n={n:,} "
          f"weeks={len(Z['weeks'])} selected={sel}")

    pol, pri = build_policies(a.pset, k, Z, sel)
    tmp = os.path.join(C.WORK, "tmp_" + tag)
    os.makedirs(tmp, exist_ok=True)
    arrays = dict(a=Z["a"], svc=Z["svc"], dl=Z["dl"], exam=Z["exam"], hvt=Z["hvt"],
                  wk=Z["wk"])
    wf = GK.run(Z["a"], Z["svc"], k, "fcfs").w
    dev = float(np.abs(wf - SP.fcfs_kw(Z["a"], Z["svc"], k)).max())
    assert dev == 0.0, f"kernel FCFS != Kiefer-Wolfowitz, max |diff| {dev}"
    lg.el(f"FCFS reproduces the Kiefer-Wolfowitz recursion exactly (max |diff| {dev:g})")
    arrays[f"wf_k{k}"] = wf
    arrays["q1"] = wf <= 1.0
    boot = a.pset == "main"
    if boot:
        # row 0 = every week once: bm[0] / bq[0] are then the full-trace point estimates,
        # which is how the pipeline's _p2_task checks the resampler (SP.stage_p2)
        Mb = SP.boot_weights(len(Z["weeks"]))
        arrays["M"] = np.vstack([np.ones((1, Mb.shape[1]), np.int64), Mb])
    lg.el(f"jobs FCFS would start within 1 s: {int(arrays['q1'].sum()):,} "
          f"({arrays['q1'].mean() * 100:.1f}%)")
    for nm, v in arrays.items():
        np.save(os.path.join(tmp, nm + ".npy"), v)
    for nm in {p[1] for p in pol if p[1]}:
        np.save(os.path.join(tmp, "pri_" + nm + ".npy"), pri[nm])
    names = list(arrays) + ["pri_" + x for x in {p[1] for p in pol if p[1]}]
    del arrays, pri, wf, Z

    base = dict(trace=a.trace, rep=a.rep, level=a.level, rho_target=rho_t, k=k,
                rho_busy=W / (3600.0 * k), n_jobs=n, pset=a.pset)
    tasks = [dict(name=nm, pri=pk, kw=kw, eps=eps, extra=ex, bmax=bm, guard=g, G=G,
                  B0=B0, eta=et, ncap=nc, k=k, base=base, boot=boot)
             for nm, pk, kw, eps, ex, bm, g, G, B0, et, nc in pol]
    with ProcessPoolExecutor(max_workers=min(a.workers, len(tasks)),
                             initializer=_init, initargs=(tmp, names)) as ex_:
        res = list(ex_.map(_task, tasks))
    rows = [r[1] for r in res]
    pd.DataFrame(rows).to_csv(os.path.join(C.SIMDIR, f"{tag}.csv"), index=False)
    if boot:
        np.savez(os.path.join(C.SIMDIR, f"bw_{tag}.npz"),
                 **{f"{m}|{r[0]}": r[2][i] for r in res
                    for i, m in enumerate(("mean", "p99dl"))})
    d = pd.DataFrame(rows).set_index("policy")
    fq, sq = d.loc["FCFS", "w_p99_dl"], d.loc["SJF-ref", "w_p99_dl"]
    fm, sm = d.loc["FCFS", "w_mean"], d.loc["SJF-ref", "w_mean"]
    d["gap_p99dl"] = (fq - d.w_p99_dl) / (fq - sq)
    d["red_p99dl_pct"] = 100.0 * (fq - d.w_p99_dl) / fq
    d["gap_mean"] = (fm - d.w_mean) / (fm - sm)
    lg.w(d[["w_p99_dl", "gap_p99dl", "red_p99dl_pct", "w_mean", "gap_mean", "max_excess",
            "harm_wf1s", "max_heavy", "guar_excess_max", "used_over_allowed",
            "qw_forced_frac", "bound_viol", "sim_sec"]].round(4).to_string())
    shutil.rmtree(tmp, ignore_errors=True)
    lg.close()


if __name__ == "__main__":
    main()
