"""Check this study's kernel against the project's verified one before using it.

1. non-tiered modes of tierkern must reproduce guard_variants/guardkern.py job by job
   (FCFS, SPJF, constant-budget guard) on random instances and on a slice of the real
   rep0 trace;
2. the tiered kernel must reproduce a slow, obviously-correct pure-python simulator on
   random small instances, for every base mode, with and without the guard and the skip.

usage:  verify.py            ->  out_verify.txt
"""
import sys
sys.dont_write_bytecode = True
import os
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "guard_variants"))
import tierkern as T
import guardkern as G

SCRATCH = r"<cache-dir>"
IN = SCRATCH + "/gv_inputs"
L = 60.0


def naive(a, s, pred, k, tau, B, mode, skip_thr, m2=None):
    """Pure-python event simulator: the model, written out, no data structures."""
    n = len(a)
    INF = float("inf")
    tau = INF if tau is None else tau
    st = ["unborn"] * n
    w = [None] * n
    srv = []                       # (finish_time, job, kill)
    done = 0
    execed = [0.0] * n             # executed work credited so far, per rank
    t = -INF
    while done < n:
        # completions
        prog = True
        while prog:
            prog = False
            srv.sort(key=lambda x: (x[0], x[1]))
            for e in list(srv):
                if e[0] <= t:
                    srv.remove(e)
                    ft, j, kl, _i2 = e
                    execed[j] += tau if kl else s[j]
                    if kl:
                        st[j] = "t2"
                    else:
                        st[j] = "done"
                        done += 1
                    prog = True
                    break
        # arrivals
        for j in range(n):
            if st[j] == "unborn" and a[j] <= t:
                st[j] = ("t2" if (skip_thr > 0 and pred[j] >= skip_thr and tau < INF)
                         else "t1")
        cap = k if m2 is None else m2
        nr2 = sum(1 for e in srv if e[3])
        wait = [j for j in range(n) if st[j] == "t1"
                or (st[j] == "t2" and nr2 < cap)]
        if len(srv) < k and wait:
            head = min(wait)
            TC = sum(execed)
            over = TC - sum(execed[q] for q in range(head + 1))
            j = None
            if B is not None and over >= B - 1e-12:
                j = head
            elif mode == "rank":
                j = head
            elif mode == "pred":
                j = min(wait, key=lambda q: (pred[q], q))
            else:
                t1 = [q for q in wait if st[q] == "t1"]
                if t1:
                    j = (min(t1, key=lambda q: (pred[q], q)) if mode == "t1pred"
                         else min(t1))
                else:
                    j = min(q for q in wait if st[q] == "t2")
            kill = st[j] == "t1" and s[j] > tau
            i2 = st[j] == "t2"
            dur = tau if kill else s[j]
            if not kill:
                w[j] = t - a[j]
            st[j] = "run"
            srv.append((t + dur, j, kill, i2))
            continue
        nxt = INF
        if srv:
            nxt = min(e[0] for e in srv)
        for j in range(n):
            if st[j] == "unborn":
                nxt = min(nxt, a[j])
        if nxt == INF:
            break
        t = max(nxt, t)
    assert done == n
    return np.array(w, float)


def part1(rng, log):
    bad = 0
    for trial in range(400):
        n = int(rng.integers(2, 60))
        k = int(rng.integers(1, 5))
        a = np.sort(rng.random(n) * rng.choice([1.0, 20.0, 200.0]))
        s = rng.random(n) * rng.choice([1.0, 10.0, 60.0]) + 1e-3
        pred = rng.random(n) * 60
        for B in (None, 0.0, 5.0, 60.0, 600.0):
            for md, gm in (("rank", "fcfs"), ("pred", "pri")):
                if B is not None and md == "rank":
                    continue
                r1 = T.run(a, s, k, md, pred=pred, B=B)
                if B is None:
                    r2 = G.run(a, s, k, gm, pred=pred)
                else:
                    r2 = G.run(a, s, k, "guard", pred=pred, B=B)
                d = float(np.abs(r1.w - r2.w).max())
                if d > 1e-9:
                    bad += 1
                    if bad < 4:
                        log(f"  MISMATCH trial={trial} n={n} k={k} mode={md} B={B} "
                            f"maxdiff={d:.3e}")
    log(f"part 1 (tierkern vs guardkern, non-tiered): 400 random instances x 6 "
        f"configurations, mismatches = {bad}")
    return bad


def part2(rng, log):
    bad = 0
    ncase = 0
    for trial in range(300):
        n = int(rng.integers(2, 14))
        k = int(rng.integers(1, 4))
        a = np.sort(np.round(rng.random(n) * rng.choice([2.0, 20.0]), 3))
        s = np.round(rng.random(n) * rng.choice([2.0, 20.0]) + 0.01, 3)
        pred = np.round(rng.random(n) * 20, 3)
        tau = float(rng.choice([0.3, 1.0, 5.0]))
        for mode in ("rank", "pred", "t1rank", "t1pred"):
            for B in (None, 0.0, 3.0, 50.0):
                for sk, m2 in ((0.0, None), (5.0, None), (0.0, 1), (0.0, 2)):
                    ncase += 1
                    r = T.run(a, s, k, mode, pred=pred, tau=tau, B=B, skip_thr=sk,
                              m2=m2)
                    wn = naive(a, s, pred, k, tau, B, mode, sk, m2)
                    d = float(np.abs(r.w - wn).max())
                    if d > 1e-9:
                        bad += 1
                        if bad < 4:
                            log(f"  MISMATCH trial={trial} n={n} k={k} mode={mode} "
                                f"tau={tau} B={B} skip={sk} m2={m2} maxdiff={d:.3e}")
                            log(f"    a={list(a)}\n    s={list(s)}\n    pred={list(pred)}")
    log(f"part 2 (tiered kernel vs pure-python simulator): {ncase} cases, "
        f"mismatches = {bad}")
    return bad


def part3(log):
    Z = np.load(os.path.join(IN, "rep0.npz"))
    m = 3_000_000
    a = np.ascontiguousarray(Z["a"][:m])
    s = np.ascontiguousarray(Z["svc"][:m])
    pred = np.ascontiguousarray(Z["M4"][:m].astype(np.float64))
    bad = 0
    for k in (4, 8):
        for md, gm, kw in (("rank", "fcfs", {}), ("pred", "pri", {}),
                           ("pred", "guard", {"B": 600.0}), ("pred", "guard", {"B": 60.0})):
            B = kw.get("B")
            r1 = T.run(a, s, k, md, pred=pred, B=B)
            r2 = (G.run(a, s, k, gm, pred=pred, **kw) if gm != "fcfs"
                  else G.run(a, s, k, "fcfs"))
            d = float(np.abs(r1.w - r2.w).max())
            bad += d > 1e-9
            log(f"  real trace k={k:2d} {gm:5s} B={B}: max |w_tier - w_guardkern| = "
                f"{d:.3e}  (mean wait {r1.w.mean():.4f}s)")
    log(f"part 3 (3,000,000 jobs of rep0): mismatches = {bad}")
    return bad


def main():
    out = open(os.path.join(HERE, "out_verify.txt"), "w")

    def log(*a):
        print(*a, flush=True)
        print(*a, file=out, flush=True)

    rng = np.random.default_rng(20260919)
    log("verification of tierkern.py")
    b = part1(rng, log) + part2(rng, log) + part3(log)
    log(f"\nTOTAL mismatches: {b}")
    out.close()


if __name__ == "__main__":
    main()
