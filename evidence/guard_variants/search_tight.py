"""Adversarial search: try hard to break Theorem A / Theorem B, and measure how much of
the allowed excess an adversary can actually reach.

Simulated annealing over small instances (arrival times, service times, predictions, all
on a coarse lattice so ties and simultaneous events occur).  The objective is the worst
job's used/allowed ratio; any value above 1 is a counterexample and aborts the run.
Also checks the conjecture W <= W_FCFS + B + k*L that the prior-art note suggested for a
finite-skip + work-budget rule, which Theorem A already implies.

usage:  search_tight.py
"""
import sys
sys.dont_write_bytecode = True
import os
import time
import numpy as np
import guardkern as G

HERE = os.path.dirname(os.path.abspath(__file__))
T0 = time.time()
LAT = 0.5                       # time lattice
SMAX = 4.0                      # service cap L for the search instances
DESIGNS = [("FIX-B1", dict(B=1.0), 0.0, 0.0),
           ("FIX-B4", dict(B=4.0), 0.0, 0.0),
           ("FIX-B16", dict(B=16.0), 0.0, 0.0),
           ("REL-B1-e.5k", dict(B=1.0), 0.5, 0.0),
           ("REL-B4-e.75k", dict(B=4.0), 0.75, 0.0),
           ("CAP-B1-e.5k-M8", dict(B=1.0, Bmax=8.0), 0.5, 0.0),
           ("SKIP-N3", dict(B=-1.0, theta=SMAX, Ncap=3), 0.0, 3 * SMAX)]


def log(*a):
    print(f"[{time.time()-T0:6.1f}s]", *a, flush=True)


def rand_inst(rng, n):
    a = np.sort(rng.integers(0, 3 * n, n).astype(float) * LAT)
    s = rng.integers(0, int(SMAX / LAT) + 1, n).astype(float) * LAT
    p = rng.integers(-3, 4, n).astype(float)
    return a, s, p


def score(a, s, p, k, kw, eta, extra):
    n = len(a)
    eps = eta * k
    r = G.run(a, s, k, "guard", pred=p, eps=eps, Mslots=max(4, n), **kw)
    assert r.err == 0
    wf = G.run(a, s, k, "fcfs", Mslots=max(4, n)).w
    cb = np.zeros(1) if kw.get("B", 0.0) < 0 else r.cbud / 1e6
    ub = G.guaranteed(wf, k, cb, eps=eps, extra=extra, L=SMAX, Bmax=kw.get("Bmax", 0.0))
    allow = np.maximum(ub - wf, 1e-12)
    used = (r.w - wf) / allow
    return float(used.max()), float((r.w - wf).max()), float(allow.max()), wf, r.w


def main():
    rng = np.random.default_rng(777)
    rows = []
    worst_conj = 0.0
    nrun = 0
    for k in (1, 2, 3, 4, 6):
        for name, kw, eta, extra in DESIGNS:
            if eta * k >= k and eta > 0:
                continue
            best = -1.0
            bestinst = None
            for restart in range(25):
                n = int(rng.integers(3, 17))
                a, s, p = rand_inst(rng, n)
                cur, _, _, _, _ = score(a, s, p, k, kw, eta, extra)
                nrun += 1
                T = 0.25
                for step in range(150):
                    a2, s2, p2 = a.copy(), s.copy(), p.copy()
                    for _ in range(int(rng.integers(1, 3))):
                        m = int(rng.integers(0, 3))
                        j = int(rng.integers(0, n))
                        if m == 0:
                            a2[j] = max(0.0, a2[j] + rng.choice([-1.0, -0.5, 0.5, 1.0]))
                            a2 = np.sort(a2)
                        elif m == 1:
                            s2[j] = min(SMAX, max(0.0, s2[j] + rng.choice([-1., -.5, .5, 1.])))
                        else:
                            p2[j] = float(rng.integers(-3, 4))
                    v, ex, al, wf, wg = score(a2, s2, p2, k, kw, eta, extra)
                    nrun += 1
                    assert v <= 1 + 1e-9, ("THEOREM VIOLATED", name, k, v, a2.tolist(),
                                           s2.tolist(), p2.tolist())
                    B_ = kw.get("B", 0.0)
                    if B_ >= 0 and eta == 0 and not kw.get("Bmax"):
                        worst_conj = max(worst_conj, ex / (B_ + k * SMAX))
                    if v > cur - T * rng.random():
                        a, s, p, cur = a2, s2, p2, v
                    if v > best:
                        best = v
                        bestinst = (a2.copy(), s2.copy(), p2.copy())
                    T *= 0.985
            rows.append((k, name, best, len(bestinst[0])))
            log(f"  k={k} {name:16s} best used/allowed = {best:.3f} "
                f"(n={len(bestinst[0])})")
    log(f"{nrun:,} simulated instances, 0 violations of Theorem A / Theorem B")
    log(f"worst observed excess / (B + k*L) for the constant-budget guard: {worst_conj:.3f} "
        f"-- the prior-art conjecture W <= W_fcfs + B + k L is implied by Theorem A "
        f"(B/k + (3-2/k)L <= B + kL for every k >= 1) and is never tight here")
    import csv
    with open(os.path.join(HERE, "search_tight.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["k", "design", "best_used_over_allowed", "n_of_best"])
        w.writerows(rows)
    log("wrote search_tight.csv")


if __name__ == "__main__":
    main()
