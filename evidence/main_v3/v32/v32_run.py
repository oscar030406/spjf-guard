"""Stage 2/3 (v3.2): run one (trace, overlay, load level) cell.

Same pure-scheduling setup and the same two kernels as v3.1.  Two changes:

  * the `grid` set now carries BOTH budget families at equal grid density plus the hybrid
    (v32_common.grid_policies), with parameter sets that produce the same schedule
    simulated once and the result shared (v32_common.policy_key);
  * every policy additionally reports the excess distribution among the jobs FCFS already
    makes wait (W_FCFS > 60 s), which is where a multiplicative budget can differ from a
    constant one in kind and not only in degree.

Every guarded run asserts its per-job bound on every job:
    work budget  W <= min( (k W_F + C_i + (3k-2)L)/(k - eps),  W_F + (Bmax + (3k-2)L)/k )
    finite skip  W <= W_F + (N + 2k - 2) L / k

usage: v32_run.py --trace primary --rep 0 --level 2 --set main [--workers 6]
"""
from __future__ import annotations

import argparse
import os
import shutil
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

import v32_common as C
from v32_common import SP, GK, SK

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


def _stats(w, dm, xm, hv, wf, q1, hw):
    q = np.quantile
    ex = w - wf
    d = dict(SP.wstats(w, dm, xm, hv))
    d.update(max_excess=float(ex.max()), mean_excess=float(ex.mean()),
             p99_excess=float(q(ex, .99)),
             harm_wf1s=float(ex[q1].max()) if q1.any() else float("nan"),
             max_excess_dl=float(ex[dm].max()))
    if hw.any():
        e, r = ex[hw], w[hw] / np.maximum(wf[hw], 1e-12)
        d.update(lw_n=float(hw.sum()), lw_ex_mean=float(e.mean()),
                 lw_ex_p50=float(q(e, .5)), lw_ex_p90=float(q(e, .9)),
                 lw_ex_p99=float(q(e, .99)), lw_ex_max=float(e.max()),
                 lw_ratio_p99=float(q(r, .99)), lw_ratio_max=float(r.max()))
    else:
        for c in ("lw_n", "lw_ex_mean", "lw_ex_p50", "lw_ex_p90", "lw_ex_p99",
                  "lw_ex_max", "lw_ratio_p99", "lw_ratio_max"):
            d[c] = float("nan")
    return {k: float(v) for k, v in d.items()}


def _task(t):
    t0 = time.time()
    svc, wf = _A["svc"], _A[f"wf_k{t['k']}"]
    pred = None if t["pri"] is None else _A["pri_" + t["pri"]]
    if t["family"] == "skip":
        r = SK.run(_A["a"], svc, pred, t["k"], t["ncap"])
        ub = SK.guaranteed(wf, t["k"], t["ncap"], C.L)
    elif t["family"] == "-":
        r = GK.run(_A["a"], svc, t["k"], pred=pred, policy=t["mode"])
        ub = None
    else:
        r = GK.run(_A["a"], svc, t["k"], pred=pred, policy="guard", B=t["B0"],
                   eps=t["eps"], gam=t["gam"], Bmax=t["bmax"], Mslots=C.MSLOTS)
        assert r.err == 0, (t["name"], "segment-tree window too small")
        ub = GK.guaranteed(wf, t["k"], r.cbud / 1e6, eps=t["eps"], L=C.L, Bmax=t["bmax"])
    viol, used, gbound = -1, float("nan"), float("inf")
    if ub is not None:
        viol = int((r.w > ub + 1e-6).sum())
        assert viol == 0, (t["name"], float((r.w - ub).max()))
        used = float(np.max((r.w - wf) / np.maximum(ub - wf, 1e-12)))
        gbound = float((ub - wf).max())
    st = _stats(r.w, _A["dl"], _A["exam"], _A["hvt"], wf, _A["q1"], _A["hw"])
    row = dict(t["base"], policy=t["name"], score=t["pri"] or "-", family=t["family"],
               G=t["G"], B0=t["B0"], eta=t["eta"], gam=t["gam"], Bmax=t["bmax"],
               Ncap=t["ncap"], promise=t["promise"], **st,
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
    return t["name"], row, bw


def _p(name, family, G, B0, eta, gam, bmax, eps, promise, ncap=0, pri="tweedie",
       mode="guard"):
    return dict(name=name, family=family, G=G, B0=B0, eta=eta, gam=gam, bmax=bmax,
                eps=eps, promise=promise, ncap=ncap, pri=pri, mode=mode)


def build_policies(pset, k, Z, sel):
    svc = Z["svc"]
    pri = {"svc": svc}
    out = [_p("FCFS", "-", -1, -1, -1, -1, 0.0, 0.0, float("inf"), pri=None, mode="fcfs"),
           _p("SJF-ref", "-", -1, -1, -1, -1, 0.0, 0.0, float("inf"), pri="svc",
              mode="pri")]
    if pset == "grid":
        pri["tweedie"] = Z["tweedie"]
        out.append(_p("SPJF-tweedie", "-", -1, -1, -1, -1, 0.0, 0.0, float("inf"),
                      mode="pri"))
        for nm, fam, G, B0, eta, gam, bm, eps, pr in C.grid_policies(k):
            out.append(_p(nm, fam, G, B0, eta, gam, bm, eps, pr))
        return out, pri
    assert pset == "main"
    for s in ("M4", "M4refit", "tweedie") + tuple(
            x for x in ("tweedie_itr", "r1s") if x in Z):
        pri[s] = Z[s]
        out.append(_p(f"SPJF-{s}", "-", -1, -1, -1, -1, 0.0, 0.0, float("inf"), pri=s,
                      mode="pri"))
    for G in C.GS:
        bm = C.bmax_of(G, k)
        out.append(_p(f"FIX-G{G:g}", "fixed_eq", G, bm, 0.0, 0.0, bm, 0.0, G))
        for fam, tag in (("fixed", "FIXSEL"), ("capped", "CAP"), ("hybrid", "HYB")):
            r = sel[(fam, G)]
            B0 = min(r["B0_base"] * k / 4.0, bm)
            gam = r["gam_base"] * k / 4.0
            eta = r["eta"]
            pr = (G if fam == "hybrid"
                  else min(G, C.const_promise(B0, k) / (1.0 - eta)))
            out.append(_p(f"{tag}-G{G:g}", fam, G, B0, eta, gam, bm, eta * k, pr))
        n = C.skip_ncap_dispatch(G, k)
        out.append(_p(f"SKIP-G{G:g}", "skip", G, -1.0, 0.0, 0.0, 0.0, 0.0, G, ncap=n))
    for adv in ("reversed", "random", "top1short"):
        pri[adv] = _adv(adv, svc, Z["tweedie"])
        out.append(_p(f"SPJF-{adv}", "-", -1, -1, -1, -1, 0.0, 0.0, float("inf"),
                      pri=adv, mode="pri"))
        bm = C.bmax_of(C.ADV_G, k)
        r = sel[("capped", C.ADV_G)]
        B0 = min(r["B0_base"] * k / 4.0, bm)
        out.append(_p(f"CAP-G{C.ADV_G:g}-{adv}", "capped", C.ADV_G, B0, r["eta"], 0.0, bm,
                      r["eta"] * k,
                      min(C.ADV_G, C.const_promise(B0, k) / (1.0 - r["eta"])), pri=adv))
    return out, pri


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace", default="primary")
    ap.add_argument("--rep", type=int, default=0)
    ap.add_argument("--level", type=int, default=2)
    ap.add_argument("--set", dest="pset", default="main")
    ap.add_argument("--workers", type=int, default=6)
    # a cell of the validation grid is ~250 simulations and does not fit in one command
    # slot, so it is run in contiguous chunks of the distinct-schedule list; results are
    # appended and already-computed policies are skipped, so the parts can run in any
    # order and a part can be repeated without changing anything.
    ap.add_argument("--part", type=int, default=1)
    ap.add_argument("--nparts", type=int, default=1)
    a = ap.parse_args()
    assert 1 <= a.part <= a.nparts

    lg = C.Log("run")
    Z = C.load_trace(a.trace, a.rep)
    K = list(Z["K"])
    k = int(K[a.level]) if len(K) > 1 else int(K[0])
    W = float(Z["W"])
    rho_t = C.RHOS[a.level] if len(K) > 1 else round(W / (3600.0 * k), 2)
    n = len(Z["a"])
    sel = None
    if a.pset == "main":
        s = pd.read_csv(os.path.join(C.HERE, "selected_params.csv"))
        sel = {(r.family, float(r.G)): dict(B0_base=float(r.B0_base), eta=float(r.eta),
                                            gam_base=float(r.gam_base))
               for r in s.itertuples()}
    tag = f"{a.trace}_rep{a.rep}_L{a.level}_{a.pset}"
    pol, pri = build_policies(a.pset, k, Z, sel)
    lg.el(f"{tag}: k={k} rho_busy={W / (3600.0 * k):.4f} (target {rho_t}) n={n:,} "
          f"weeks={len(Z['weeks'])} policies={len(pol)}")

    tmp = os.path.join(C.WORK, "tmp_" + tag)
    os.makedirs(tmp, exist_ok=True)
    arrays = dict(a=Z["a"], svc=Z["svc"], dl=Z["dl"], exam=Z["exam"], hvt=Z["hvt"],
                  wk=Z["wk"])
    wf = GK.run(Z["a"], Z["svc"], k, "fcfs").w
    dev = float(np.abs(wf - SP.fcfs_kw(Z["a"], Z["svc"], k)).max())
    assert dev == 0.0, f"kernel FCFS != Kiefer-Wolfowitz, max |diff| {dev}"
    arrays[f"wf_k{k}"] = wf
    arrays["q1"] = wf <= 1.0
    arrays["hw"] = wf > C.LONGWAIT
    boot = a.pset == "main"
    if boot:
        Mb = SP.boot_weights(len(Z["weeks"]))
        arrays["M"] = np.vstack([np.ones((1, Mb.shape[1]), np.int64), Mb])
    lg.el(f"FCFS == Kiefer-Wolfowitz; jobs with W_FCFS <= 1 s: "
          f"{int(arrays['q1'].sum()):,} ({arrays['q1'].mean() * 100:.1f}%); with "
          f"W_FCFS > {C.LONGWAIT:g} s: {int(arrays['hw'].sum()):,} "
          f"({arrays['hw'].mean() * 100:.2f}%)")
    for nm, v in arrays.items():
        np.save(os.path.join(tmp, nm + ".npy"), v)
    for nm in {p["pri"] for p in pol if p["pri"]}:
        np.save(os.path.join(tmp, "pri_" + nm + ".npy"), pri[nm])
    names = list(arrays) + ["pri_" + x for x in {p["pri"] for p in pol if p["pri"]}]
    del arrays, pri, wf, Z

    base = dict(trace=a.trace, rep=a.rep, level=a.level, rho_target=rho_t, k=k,
                rho_busy=W / (3600.0 * k), n_jobs=n, pset=a.pset)
    # one simulation per distinct schedule; identical parameter sets share the result
    uniq, first = {}, {}
    for p in pol:
        key = (p["mode"], p["pri"], p["family"] == "skip", p["ncap"],
               C.policy_key(p["B0"], p["eps"], p["gam"], p["bmax"])
               if p["family"] not in ("-", "skip") else None)
        uniq.setdefault(key, []).append(p)
        first.setdefault(key, p)
    allkeys = list(uniq)
    cut = np.array_split(np.arange(len(allkeys)), a.nparts)[a.part - 1]
    keys = [allkeys[i] for i in cut]
    csvp = os.path.join(C.SIMDIR, f"{tag}.csv")
    bwp = os.path.join(C.SIMDIR, f"bw_{tag}.npz")
    prev = pd.read_csv(csvp) if os.path.exists(csvp) else None
    done = set(prev.policy) if prev is not None else set()
    keys = [key for key in keys
            if not all(p["name"] in done for p in uniq[key])]
    tasks = [dict(first[key], k=k, base=base, boot=boot) for key in keys]
    lg.el(f"{len(pol)} configurations -> {len(allkeys)} distinct schedules; part "
          f"{a.part}/{a.nparts} covers {len(cut)}, {len(tasks)} still to run "
          f"({len(done)} policies already on disk)")
    res = []
    if tasks:
        with ProcessPoolExecutor(max_workers=min(a.workers, len(tasks)),
                                 initializer=_init, initargs=(tmp, names)) as ex_:
            res = list(ex_.map(_task, tasks))
    rows, bws = [], {}
    if boot and os.path.exists(bwp):
        z = np.load(bwp)
        bws = {kk: z[kk] for kk in z.files}
    for key, (_, row, bw) in zip(keys, res):
        for p in uniq[key]:
            rows.append(dict(row, policy=p["name"], family=p["family"], G=p["G"],
                             B0=p["B0"], eta=p["eta"], gam=p["gam"], Bmax=p["bmax"],
                             Ncap=p["ncap"], promise=p["promise"],
                             shared_with=row["policy"]))
            if bw is not None:
                bws[f"mean|{p['name']}"] = bw[0]
                bws[f"p99dl|{p['name']}"] = bw[1]
    out = pd.DataFrame(rows)
    if prev is not None:
        out = pd.concat([prev, out], ignore_index=True)
    out = out.drop_duplicates(subset=["policy"], keep="last")
    out.to_csv(csvp, index=False)
    if boot:
        np.savez(bwp, **bws)
    want = {p["name"] for p in pol}
    miss = sorted(want - set(out.policy))
    lg.el(f"cell now holds {len(out)} of {len(want)} policies"
          + (f"; still missing {len(miss)}" if miss else "; COMPLETE"))
    d = out.set_index("policy")
    fq, sq = d.loc["FCFS", "w_p99_dl"], d.loc["SJF-ref", "w_p99_dl"]
    d["gap_p99dl"] = (fq - d.w_p99_dl) / (fq - sq)
    show = d if a.pset == "main" else d[d.index.str.startswith(("FCFS", "SJF", "SPJF"))]
    lg.w(show[["w_p99_dl", "gap_p99dl", "w_mean", "max_excess", "harm_wf1s",
               "lw_ex_p99", "lw_ex_max", "lw_ratio_max", "guar_excess_max",
               "used_over_allowed", "qw_forced_frac", "bound_viol"]].round(4).to_string())
    shutil.rmtree(tmp, ignore_errors=True)
    lg.close()


if __name__ == "__main__":
    main()
