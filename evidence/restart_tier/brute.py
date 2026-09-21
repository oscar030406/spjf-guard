"""Adversarial small-instance search: which per-job bounds survive kill-and-restart?

Four hypotheses are tested on every job of every instance.  P = tiered policy (tier-1
cap tau, constant-budget guard B at piece level, adversarial base order given by `pred`);
FCFS = plain first-come-first-served, no tiering, on the same input; TFCFS = the SAME
tiering dispatched by rank.  L = max service.

  H1  W_P[i] <= W_FCFS[i]  + B/k + (3-2/k)L                     Theorem A, applied as is
  H2  W_P[i] <= W_TFCFS[i] + B/k + (3-2/k)L                     Theorem A vs a tiered ref
  H3  W_P[i] <= W_FCFS[i]  + (B + D)/k + (3-2/k)L               Proposition W (D = total
                                                                wasted work in the run)
  H4  W_P[i] <= W_FCFS[i]  + (B + D)/k + 3*tau     for LIGHT i  ("Omega(L) -> Omega(tau)")
  H5  W_P[i] <= W_TFCFS[i] + B/k + 3*tau           for LIGHT i  (the same, tiered ref)

Instances: random arrivals / sizes / predictions on small grids, n <= 7, k <= 3, plus the
structured families of `fam_*` (the analytic counterexamples of notes.md).  Every run also
re-checks that the plain, non-tiered guard still obeys H1 (a control: if that fails the
harness is wrong, not the idea).

usage:  brute.py [n_random]        ->  out_brute.txt
"""
import sys
sys.dont_write_bytecode = True
import os
import numpy as np
from numba import njit

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tierkern as T

NRAND = 2_000_000
SIZES = np.array([0.25, 0.5, 1.0, 1.5, 3.0, 8.0])     # tau = 1.0, so L = 8 = 8 tau
ARRS = np.array([0.0, 0.5, 1.0, 2.0, 4.0, 8.0])
TAU = 1.0
BS = np.array([0.0, 2.0, 8.0, 32.0])
MODES = np.array([1, 2, 3])                            # pred, t1rank, t1pred


@njit(cache=True)
def _one(a, s, pred, k, tau, B_us, mode, L):
    """Returns (worst violation of H1..H4, and the diagnostics of the worst job)."""
    n = a.shape[0]
    zero = np.zeros(n, np.float64)
    wf = T.simulate(a, s, zero, k, T.INF_TAU, -1, 0, 0.0, 1, k)[0]
    wt = T.simulate(a, s, zero, k, tau, -1, 0, 0.0, n + 8, k)[0]
    rp = T.simulate(a, s, pred, k, tau, B_us, mode, 0.0, n + 8, k)
    w, waste = rp[0], rp[2]
    B = B_us / 1.0e6
    slack = B / k + (3.0 - 2.0 / k) * L
    v1 = -1.0e18
    v2 = -1.0e18
    v3 = -1.0e18
    v4 = -1.0e18
    v5 = -1.0e18
    for i in range(n):
        d1 = w[i] - wf[i] - slack
        if d1 > v1:
            v1 = d1
        d2 = w[i] - wt[i] - slack
        if d2 > v2:
            v2 = d2
        d3 = w[i] - wf[i] - (B + waste) / k - (3.0 - 2.0 / k) * L
        if d3 > v3:
            v3 = d3
        if s[i] <= tau:
            d4 = w[i] - wf[i] - (B + waste) / k - 3.0 * tau
            if d4 > v4:
                v4 = d4
            d5 = w[i] - wt[i] - B / k - 3.0 * tau
            if d5 > v5:
                v5 = d5
    # control: the plain guard, no tiering, must satisfy H1
    wg = T.simulate(a, s, pred, k, T.INF_TAU, B_us, 1, 0.0, 1, k)[0]
    v0 = -1.0e18
    for i in range(n):
        d0 = wg[i] - wf[i] - slack
        if d0 > v0:
            v0 = d0
    return v0, v1, v2, v3, v4, v5, waste


@njit(cache=True)
def sweep(ntrial, seed, sizes, arrs, bs, modes, tau):
    np.random.seed(seed)
    best = np.full(6, -1.0e18)
    bestpar = np.zeros((6, 4), np.float64)
    bestinst = np.zeros((6, 3, 8), np.float64)
    nviol = np.zeros(6, np.int64)
    for it in range(ntrial):
        n = 2 + np.random.randint(6)
        k = 1 + np.random.randint(3)
        a = np.empty(n, np.float64)
        s = np.empty(n, np.float64)
        pred = np.empty(n, np.float64)
        for j in range(n):
            a[j] = arrs[np.random.randint(len(arrs))]
            s[j] = sizes[np.random.randint(len(sizes))]
            pred[j] = np.random.random()
        a = np.sort(a)
        L = s.max()
        B_us = np.int64(round(bs[np.random.randint(len(bs))] * 1.0e6))
        mode = modes[np.random.randint(len(modes))]
        v = _one(a, s, pred, k, tau, B_us, mode, L)
        for h in range(6):
            if v[h] > 1e-9:
                nviol[h] += 1
            if v[h] > best[h]:
                best[h] = v[h]
                bestpar[h, 0] = n
                bestpar[h, 1] = k
                bestpar[h, 2] = B_us / 1.0e6
                bestpar[h, 3] = mode
                for j in range(n):
                    bestinst[h, 0, j] = a[j]
                    bestinst[h, 1, j] = s[j]
                    bestinst[h, 2, j] = pred[j]
    return best, bestpar, nviol, bestinst


MODENAME = {0: "rank", 1: "pred", 2: "t1rank", 3: "t1pred"}


def show(log, title, par, inst, tau):
    """Re-run the worst instance found for one hypothesis and print it job by job."""
    n, k, B, mode = int(par[0]), int(par[1]), float(par[2]), MODENAME[int(par[3])]
    a, s, pred = inst[0, :n].copy(), inst[1, :n].copy(), inst[2, :n].copy()
    L = float(s.max())
    wf = T.run(a, s, k, "rank").w
    wt = T.run(a, s, k, "rank", tau=tau).w
    r = T.run(a, s, k, mode, pred=pred, tau=tau, B=B)
    log(f"\nworst instance for {title}")
    log(f"    n={n} k={k} B={B:g} base={mode} tau={tau:g} L={L:g} "
        f"wasted={r.waste:g} ({r.n_killed} kills)")
    log(f"    {'rank':>4} {'arrival':>8} {'service':>8} {'pred':>6} {'W_P':>8} "
        f"{'W_FCFS':>8} {'W_TFCFS':>8} {'excess':>8}")
    for j in range(n):
        log(f"    {j:>4} {a[j]:>8.2f} {s[j]:>8.2f} {pred[j]:>6.3f} {r.w[j]:>8.2f} "
            f"{wf[j]:>8.2f} {wt[j]:>8.2f} {r.w[j]-wf[j]:>8.2f}")
    log(f"    Theorem A slack B/k+(3-2/k)L = {B/k+(3-2/k)*L:.2f}; "
        f"max excess over plain FCFS = {float((r.w-wf).max()):.2f}; "
        f"over tiered FCFS = {float((r.w-wt).max()):.2f}")


def fam_waste(k, nheavy, tau, L):
    """n identical heavy jobs at t=0: every kill-everything schedule loses n*tau/k."""
    a = np.zeros(nheavy)
    s = np.full(nheavy, L)
    return a, s


def analytic(log):
    log("\n--- family A: n identical heavy jobs (work L) arriving together, no other job")
    log("    every tiered schedule must execute n*(L+tau); the worst job's excess over")
    log("    plain FCFS therefore grows linearly in n.  (theory: >= n*tau/k - L)")
    log(f"    {'k':>2} {'n':>3} {'tau':>5} {'maxexc_TIER':>12} {'n*tau/k':>9} "
        f"{'maxexc_SPJFguard':>17}")
    for k in (1, 2, 3):
        for nh in (2, 4, 8, 16, 32):
            L, tau = 8.0, 1.0
            a, s = fam_waste(k, nh, tau, L)
            pred = np.arange(nh, dtype=float)
            wf = T.run(a, s, k, "rank").w
            for mode, nm in (("rank", "TFCFS"), ("t1rank", "TIER")):
                w = T.run(a, s, k, mode, pred=pred, tau=tau, B=0.0).w
                if nm == "TIER":
                    e = float((w - wf).max())
            wg = T.run(a, s, k, "pred", pred=pred, B=0.0).w
            log(f"    {k:>2} {nh:>3} {tau:>5.1f} {e:>12.3f} {nh*tau/k:>9.3f} "
                f"{float((wg-wf).max()):>17.3f}")

    log("\n--- family B: does the additive constant for a LIGHT job scale with tau or L?")
    log("    tau is held at 1.0 and the largest service L is varied; for each L the same")
    log("    random search reports  max over LIGHT jobs of (W_P - W_TFCFS) - B/k  and")
    log("    (W_P - W_FCFS - wasted/k).  If tiering moved the barrier from L to tau these")
    log("    would stay flat in L.")
    log(f"    {'L/tau':>6} {'light excess vs TFCFS - B/k':>28} "
        f"{'light excess vs FCFS - (B+waste)/k':>35}")
    tau = 1.0
    for Lm in (2.0, 4.0, 8.0, 16.0, 32.0):
        sz = np.array([0.25, 0.5, 1.0, 1.5, Lm / 2.0, Lm])
        b, _, _, _ = sweep(400000, 77 + int(Lm), sz, ARRS, BS, MODES, tau)
        log(f"    {Lm/tau:>6.0f} {b[5] + 3*tau:>28.3f} {b[4] + 3*tau:>35.3f}")


def main():
    nt = int(sys.argv[1]) if len(sys.argv) > 1 else NRAND
    out = open(os.path.join(HERE, "out_brute.txt"), "w")

    def log(*a):
        print(*a, flush=True)
        print(*a, file=out, flush=True)

    log("adversarial search over small instances; tau = 1.0, sizes in "
        f"{list(SIZES)}, arrivals in {list(ARRS)}, B in {list(BS)}, n <= 7, k <= 3")
    log(f"random instances: {nt:,}")
    best, bp, nv, bi = sweep(nt, 20260919, SIZES, ARRS, BS, MODES, TAU)
    names = ["H0 control: plain guard vs FCFS, Theorem A",
             "H1 tiered+guard vs plain FCFS, Theorem A slack",
             "H2 tiered+guard vs TIERED FCFS, Theorem A slack",
             "H3 tiered+guard vs plain FCFS, slack (B+waste)/k + (3-2/k)L",
             "H4 LIGHT jobs vs plain FCFS, slack (B+waste)/k + 3*tau",
             "H5 LIGHT jobs vs TIERED FCFS, slack B/k + 3*tau"]
    log(f"\n{'hypothesis':<52} {'violations':>11} {'worst excess over the bound':>28}")
    for h in range(6):
        log(f"{names[h]:<52} {nv[h]:>11,} {best[h]:>28.4f}"
            + (f"   (n={bp[h,0]:.0f} k={bp[h,1]:.0f} B={bp[h,2]:g} mode={bp[h,3]:.0f})"
               if nv[h] else ""))
    for h in (1, 4, 5):
        if nv[h]:
            show(log, names[h], bp[h], bi[h], TAU)
    analytic(log)
    out.close()


if __name__ == "__main__":
    main()
