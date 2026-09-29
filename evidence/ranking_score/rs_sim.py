"""Run every candidate ranking score through the verified simulator.

Trace construction, overlay, level k, metrics and the week-block bootstrap are the
pipeline's (service_precheck_v2): SP.p2_inputs / SP.overlay / SP.ms_entries / SP.level_ks /
SP.simulate / SP.wstats / SP.boot_weights / SP.boot_mean / SP.boot_quantile.  Only the
priority arrays are ours.  Pure scheduling only (every policy shares the same enqueue times).

traces
  primary   the verified primary trace: pool = POOL60, 44 copies, k = 8/5/4 at busy-hour
            rho 0.5/0.8/1.0, week set and copy count read from the cache.
  validpre  VALIDATION trace: same construction as the primary, pool = the POOL60 semesters
            up to and including the validation semester 2022-1 (i.e. POOL60 minus the dev-test
            semester 2022-2), copy count chosen by the pipeline's own rule (SP.copies_probe),
            week set from the overlay.  Every threshold and every model choice is fixed here.
            A pool of 2022-1 alone was tried first and rejected: 8 class-semesters need 139
            copies to load the pool, which stacks the same 8 course calendars into deadline
            spikes far sharper than the primary trace's (FCFS deadline-window p99 687 s at
            rho 0.8 against the primary's 119 s), so it is not a stand-in for the primary.

policy groups (--group)
  scores    FCFS, SJF-ref, SPJF with the current M4 log score and with each candidate
  twoclass  the two-class rules at a grid of P(heavy) thresholds
  mech      diagnostic oracles for the misranking decomposition (not deployable)
usage: rs_sim.py --trace primary --rep 0 --rhos 0.5,0.8,1.0 --group scores
"""
from __future__ import annotations

import argparse
import os
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

import rs_common as C
from rs_common import SP, say

TMP = os.path.join(C.WORK, "simtmp")
OUT = os.path.join(C.WORK, "sim")
os.makedirs(TMP, exist_ok=True)
os.makedirs(OUT, exist_ok=True)

CAND = ["l2raw", "tweedie", "gamma", "hurdle", "q50", "q90", "q99", "phv", "logvar"]
# "log" is our refit of the CURRENT M4 score with the same protocol and features.  Four of the
# six targets reproduce the cached forward M4 bit for bit; 2020-2 and 2022-1 differ by up to
# 0.50 / 0.011 in the log1p score (LightGBM's multi-threaded histogram summation is not
# bit-reproducible run to run).  Running it as its own policy gives the refit noise floor
# against which every candidate's difference has to be read.
TAUS = (0.02, 0.05, 0.10, 0.20, 0.40)          # P(heavy) thresholds swept on the validation trace
ERR_PCT = (0.1, 1.0)                           # top-x% costliest errors, both directions
BIG = 1e3                                      # > any log1p(C_cap) score: "behind everything"


# --------------------------------------------------------------------------- #
def trace_inputs(trace, D, S, cache):
    """(per-class-semester job groups, row-level columns, copies, week set)."""
    I = SP.p2_inputs(D, S, C.CFG, cache, "base")
    if trace == "primary":
        cp = pd.read_csv(os.path.join(cache, "copies.csv")).set_index("trace")
        copies = int(cp.loc["primary", "copies"])
        weeks = SP.p2_weeks(cache, "primary")
        return I, copies, weeks
    assert trace == "validpre"
    keep = {cs: g for cs, g in I["per_cs"].items() if cs.split("|")[0] != C.TEST_SEM}
    I = dict(I, per_cs=keep, pool=sorted(keep))
    key = SP.trace_key(C.CFG)
    copies, _ = SP.copies_probe(I["pool"], I["per_cs"], key, SP.PROBE_REPS)
    wks = set()
    for r in (0, 1):
        a, _, _, _ = SP.overlay(SP.ms_entries(I["pool"], copies, r), I["per_cs"], key)
        wks |= set(np.unique(np.floor((a - SP.REF_MON) / SP.WEEK).astype(np.int64)).tolist())
        del a
    return I, copies, np.array(sorted(wks), dtype=np.int64)


def build_scores(group, m4, cand, svc, hvt, taus):
    """Priority arrays over the overlay jobs.  Smaller = dispatched first.
    m4 / cand values are on the log1p scale for log-type scores and on the raw scale for
    the E[C]-type ones; only the induced order matters, so no rescaling is needed."""
    pol, pri = [], {"svc": svc, "M4": m4}
    if group == "scores":
        pol = [("FCFS", "fcfs", None), ("SJF-ref", "pri", "svc"), ("SPJF-M4", "pri", "M4")]
        for nm, v in cand.items():
            pri[nm] = v
            pol.append((f"SPJF-{nm}" if nm != "log" else "SPJF-M4refit", "pri", nm))
    elif group == "twoclass":
        pol = [("FCFS", "fcfs", None), ("SJF-ref", "pri", "svc"), ("SPJF-M4", "pri", "M4")]
        p, tw = cand["phv"], cand["tweedie"]
        pri["tweedie"] = tw
        pol.append(("SPJF-tweedie", "pri", "tweedie"))
        for t in taus:
            hi = p > t
            pri[f"2C-FCFS-t{t}"] = hi.astype(np.float64)                     # FCFS in each class
            pri[f"2C-SPJF-t{t}"] = np.where(hi, BIG + m4, m4)                # SPJF-M4 in each class
            pri[f"2C-TW-t{t}"] = np.where(hi, BIG + tw, tw)                  # SPJF-tweedie in each
            pol += [(f"2CLASS-FCFS-tau{t}", "pri", f"2C-FCFS-t{t}"),
                    (f"2CLASS-SPJF-tau{t}", "pri", f"2C-SPJF-t{t}"),
                    (f"2CLASS-TWEEDIE-tau{t}", "pri", f"2C-TW-t{t}")]
    elif group == "mech":
        tl = np.log1p(svc)
        pol = [("FCFS", "fcfs", None), ("SJF-ref", "pri", "svc"), ("SPJF-M4", "pri", "M4")]
        pri["tweedie"] = cand["tweedie"]
        pol.append(("SPJF-tweedie", "pri", "tweedie"))
        pri["orc_heavy"] = np.where(hvt, tl, m4)          # true size for the truly-heavy jobs
        pri["orc_light"] = np.where(hvt, m4, tl)          # true size for the truly-light jobs
        pol += [("ORACLE-on-true-heavy", "pri", "orc_heavy"),
                ("ORACLE-on-true-light", "pri", "orc_light")]
        err = svc - np.expm1(m4)                          # + = under-predicted, - = over-predicted
        n = len(svc)
        for x in ERR_PCT:
            k = max(1, int(round(n * x / 100.0)))
            u = np.argpartition(-err, k)[:k]              # worst under-predictions
            o = np.argpartition(err, k)[:k]               # worst over-predictions
            for tag, ix in (("under", u), ("over", o)):
                v = m4.copy()
                v[ix] = tl[ix]
                pri[f"orc_{tag}{x}"] = v
                pol.append((f"ORACLE-top{x}pct-{tag}", "pri", f"orc_{tag}{x}"))
    else:
        raise SystemExit(group)
    return pol, pri


def _task(t):
    d = t["dir"]
    ld = lambda nm: np.load(os.path.join(d, nm + ".npy"))
    a, svc = ld("a"), ld("svc")
    pri = ld("pri_" + t["pri"]) if t["pri"] else None
    t0 = time.time()
    w = SP.simulate(a, svc, pri, t["K"], t["mode"], t["B"])
    if not (np.isfinite(w).all() and (w >= -1e-6).all()):
        raise RuntimeError(f"bad waits in {t['name']}")
    dm, xm, hvt = ld("dl"), ld("exam"), ld("heavy")
    wf = ld(f"wf_k{t['K']}")
    row = dict(t["base"], policy=t["name"], max_excess=float((w - wf).max()),
               sim_sec=round(time.time() - t0, 1), **SP.wstats(w, dm, xm, hvt))
    wk = ld("wk")
    M = np.vstack([np.ones((1, ld("M").shape[1]), np.int64), ld("M")])
    bm = SP.boot_mean(w, wk, M)
    bq = SP.boot_quantile(w[dm], wk[dm], M, 0.99)
    assert abs(bm[0] - row["w_mean"]) <= 1e-9 * max(1.0, row["w_mean"])
    assert abs(bq[0] - row["w_p99_dl"]) <= 1e-9 * max(1.0, row["w_p99_dl"])
    return t["rho"], t["name"], row, (bm[1:], bq[1:])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace", default="primary")
    ap.add_argument("--rep", type=int, default=0)
    ap.add_argument("--rhos", default="0.5,0.8,1.0")
    ap.add_argument("--group", default="scores")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    rhos = [float(x) for x in a.rhos.split(",")]

    t0 = time.time()
    ev, D, S, X, arr, avail = C.load_base()
    I, copies, weeks = trace_inputs(a.trace, D, S, C.CACHE)
    P = pd.read_parquet(C.PRED_PARQUET)
    keep = I["keep"]
    for nm in CAND + ["log"]:
        assert np.isfinite(P[nm].values[keep]).all(), nm
    d = float(np.abs(P["log"].values[keep] - I["P"]["M4"][keep]).max())
    nd = int((P["log"].values[keep] != I["P"]["M4"][keep]).sum())
    say(f"{a.trace}: {len(I['pool'])} class-semesters, {copies} copies, {len(weeks)} weeks; "
        f"refit log score vs cached forward M4: max |diff| = {d:.3e} on {nd:,} of "
        f"{int(keep.sum()):,} rows (refit noise, see CAND note)")

    key = SP.trace_key(C.CFG)
    ar, svc, jidx, _ = SP.overlay(SP.ms_entries(I["pool"], copies, a.rep), I["per_cs"], key)
    W = SP.v1.busy_hour_work(ar, svc)[0]
    Ks = SP.level_ks(W)
    wk = np.floor((ar - SP.REF_MON) / SP.WEEK).astype(np.int64)
    wki = np.searchsorted(weeks, wk)
    assert np.array_equal(weeks[np.minimum(wki, len(weeks) - 1)], wk)
    ar = SP.rebase(ar)
    M = SP.boot_weights(len(weeks))
    hvt = I["hvt"][jidx]
    say(f"rep {a.rep}: {len(ar):,} jobs, busiest-hour work {W:,.1f} s, k per rho {dict(zip(SP.RHOS, Ks))}, "
        f"heavy {hvt.sum():,} ({hvt.mean():.4%}), deadline-window jobs {I['in_dl'][jidx].sum():,}")

    pol, pri = build_scores(a.group, I["P"]["M4"][jidx],
                            {n: P[n].values[jidx] for n in (["log"] + CAND if a.group == "scores" else CAND)},
                            svc, hvt, TAUS)
    for nm, v in dict(a=ar, svc=svc, dl=I["in_dl"][jidx], exam=I["in_exam"][jidx], heavy=hvt,
                      wk=wki, M=M).items():
        np.save(os.path.join(TMP, nm + ".npy"), v)
    for nm in {p[2] for p in pol if p[2]}:
        np.save(os.path.join(TMP, "pri_" + nm + ".npy"), pri[nm])
    del pri, X

    for rho_t in rhos:
        K = Ks[SP.RHOS.index(rho_t)]
        base = dict(trace=a.trace, rep=a.rep, rho_target=rho_t, k=K, copies=copies,
                    rho_busy=W / (3600.0 * K), n_jobs=len(ar), n_heavy=int(hvt.sum()),
                    n_dl=int(I["in_dl"][jidx].sum()))
        wf = SP.simulate(ar, svc, None, K, "fcfs")
        assert float(np.abs(wf - SP.fcfs_kw(ar, svc, K)).max()) == 0.0, "FCFS != Kiefer-Wolfowitz"
        np.save(os.path.join(TMP, f"wf_k{K}.npy"), wf)
        del wf
        tasks = [dict(dir=TMP, name=n, mode=m, pri=p, B=None, K=K, rho=rho_t, base=base)
                 for n, m, p in pol]
        with ProcessPoolExecutor(max_workers=min(a.workers, len(tasks))) as ex:
            res = list(ex.map(_task, tasks))
        rows = [r[2] for r in res]
        tag = f"{a.trace}_rep{a.rep}_r{rho_t:g}_{a.group}"
        pd.DataFrame(rows).to_csv(os.path.join(OUT, f"rs_{tag}.csv"), index=False)
        np.savez(os.path.join(OUT, f"rsbw_{tag}.npz"),
                 **{f"{m}|{r[1]}": r[3][i] for r in res for i, m in enumerate(("mean", "p99dl"))})
        z = pd.DataFrame(rows).set_index("policy")
        say(f"\n[{tag}] k={K}, busy-hour rho {W/(3600.0*K):.3f}  ({time.time()-t0:.0f} s)")
        say(z[["w_p99_dl", "w_mean", "w_p99", "max_heavy", "sim_sec"]].round(4).to_string())
    for fn in os.listdir(TMP):
        os.remove(os.path.join(TMP, fn))
    say(f"\ntotal {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
