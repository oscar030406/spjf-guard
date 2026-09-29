"""V4: my own week-block paired bootstrap of the two claims the report leans on.

  CAP-G600 gap closed at rho 1.0          report 0.800 [0.764, 0.840]
  CAP-G600 - FIXSEL-G600 at rho 1.0       report +0.350 [0.218, 0.411]

Everything here is mine: the waits (vsim, re-validated), the resampling (my own RNG and
seed, different from the pipeline's 20260919), the weighted order statistic, and the
pairing.  One draw of the 30 week multiplicities is applied to every policy and to all
five overlays; the statistic is the mean over the overlays of
(FCFS_b - P_b) / (FCFS_b - SJFref_b) with each term the p99 of the deadline-window waits
of that resampled pool.

usage: wboot.py [--nboot 2000] [--seed 31337] [--level 2]
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.dont_write_bytecode = True
for _v in ("PYTHONHOME", "PYTHONPATH", "UV_INTERNAL__PYTHONHOME"):
    os.environ.pop(_v, None)
os.environ.setdefault("NUMBA_NUM_THREADS", "4")
os.environ.setdefault("OMP_NUM_THREADS", "4")

import numpy as np                                                       # noqa: E402
import pandas as pd                                                      # noqa: E402

ROOT = r"<repo-root>"
VDIR = os.path.join(ROOT, "evidence", "main_v3_verify")
V31 = os.path.join(ROOT, "evidence", "main_v3", "v31")
HERE = os.path.dirname(os.path.abspath(__file__))
SCRATCH = r"<cache-dir>"
sys.path.insert(0, VDIR)
L = 60.0
NBLK = 4000
OUT = []


def say(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    OUT.append(s)


class WQ:
    """q-quantile of a pooled resample in which week w appears M[b, w] times.

    numpy's default 'linear' method: virtual index v = (N-1)q, take the order
    statistics floor(v) and floor(v)+1 and interpolate.  Values are sorted once and
    cut into position blocks; M @ (per-week block counts) locates the block holding
    the order statistic and a weighted scan inside it finds the value.
    """

    def __init__(self, x, wk, nw):
        o = np.argsort(x, kind="stable")
        self.xs = np.ascontiguousarray(x[o])
        self.ws = np.ascontiguousarray(wk[o].astype(np.int64))
        n = len(self.xs)
        self.edges = np.unique(np.linspace(0, n, min(NBLK, n) + 1).astype(np.int64))
        nb = len(self.edges) - 1
        blk = np.repeat(np.arange(nb), np.diff(self.edges))
        self.H = np.bincount(self.ws * nb + blk,
                             minlength=nw * nb).reshape(nw, nb).astype(np.float64)

    def _val(self, b, r, cum, M):
        j = int(np.searchsorted(cum[b], r, side="right"))
        before = cum[b, j - 1] if j > 0 else 0.0
        s0, s1 = self.edges[j], self.edges[j + 1]
        cw = np.cumsum(M[b, self.ws[s0:s1]])
        i = int(np.searchsorted(cw, r - before + 1, side="left"))
        return self.xs[s0 + min(i, s1 - s0 - 1)]

    def run(self, M, q=0.99):
        cum = np.cumsum(M.astype(np.float64) @ self.H, axis=1)
        out = np.empty(M.shape[0])
        for b in range(M.shape[0]):
            N = int(cum[b, -1])
            v = (N - 1) * q
            lo = int(np.floor(v))
            t = v - lo
            a0 = self._val(b, lo, cum, M)
            a1 = self._val(b, min(lo + 1, N - 1), cum, M)
            out[b] = a1 - (a1 - a0) * (1.0 - t) if t >= 0.5 else a0 + (a1 - a0) * t
        return out


def bmax_of(G, k):
    return float(k) * (G - (3.0 - 2.0 / k) * L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nboot", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=31337)
    ap.add_argument("--level", type=int, default=2)
    a = ap.parse_args()
    import vsim

    reps = [0, 1, 2, 3, 4]
    POLS = ("FCFS", "SJF-ref", "SPJF-tweedie", "CAP-G600", "FIXSEL-G600", "FIX-G600",
            "SPJF-M4", "SKIP-G600")
    t0 = time.time()
    Q, pt = {}, {}
    nw = None
    for r in reps:
        z = np.load(os.path.join(SCRATCH, "mv31", "traces", f"primary_rep{r}.npz"))
        A = np.ascontiguousarray(z["a"], np.float64)
        S = np.ascontiguousarray(z["svc"], np.float64)
        TW = np.ascontiguousarray(z["tweedie"], np.float64)
        M4 = np.ascontiguousarray(z["M4"], np.float64)
        k = int(list(z["K"])[a.level])
        dl = z["dl"].astype(bool)
        wk = z["wk"].astype(np.int64)
        nw = len(z["weeks"])
        bm = bmax_of(600.0, k)
        spec = {"FCFS": dict(policy="fcfs"),
                "SJF-ref": dict(policy="pri", pred=S),
                "SPJF-tweedie": dict(policy="pri", pred=TW),
                "SPJF-M4": dict(policy="pri", pred=M4),
                "CAP-G600": dict(policy="cap", pred=TW, B0=min(120.0 * k / 4.0, bm),
                                 eta=0.75, Bmax=bm),
                "FIXSEL-G600": dict(policy="cap", pred=TW, B0=min(600.0 * k / 4.0, bm),
                                    eta=0.0, Bmax=bm),
                "FIX-G600": dict(policy="cap", pred=TW, B0=bm, eta=0.0, Bmax=bm)}
        for p in POLS:
            if p == "SKIP-G600":
                import wskip
                N = 0
                while (N + 1 + 2 * k - 2) * L / k <= 600.0 + 1e-12:
                    N += 1
                w = wskip.fast(A, S, TW, k, N)[0]
            else:
                w = vsim.run(A, S, k, **spec[p])["w"]
            Q[(r, p)] = WQ(w[dl], wk[dl], nw)
            pt[(r, p)] = float(np.quantile(w[dl], 0.99))
            say(f"[{time.time() - t0:5.0f}s] rep{r} k={k} {p:14s} p99_dl "
                f"{pt[(r, p)]:.4f}")
        del z, A, S, TW, M4
    say(f"  weeks in the overlay timeline: {nw}")

    M = np.random.default_rng(a.seed).multinomial(
        nw, np.full(nw, 1.0 / nw), size=a.nboot).astype(np.int64)
    say(f"  {a.nboot} resamples, my seed {a.seed} (the pipeline's is 20260919)")
    B = {(r, p): Q[(r, p)].run(M) for r in reps for p in POLS}
    gap, gpt = {}, {}
    for p in POLS:
        gap[p] = np.mean([(B[(r, "FCFS")] - B[(r, p)])
                          / (B[(r, "FCFS")] - B[(r, "SJF-ref")]) for r in reps], axis=0)
        gpt[p] = float(np.mean([(pt[(r, "FCFS")] - pt[(r, p)])
                                / (pt[(r, "FCFS")] - pt[(r, "SJF-ref")]) for r in reps]))
    T = pd.read_csv(os.path.join(V31, "table_main_primary.csv"))
    T = T[T.level == a.level].set_index("policy")
    say("")
    say("=" * 96)
    say(f"GAP CLOSED, level {a.level} (rho 1.0), 5 overlays")
    say("=" * 96)
    say("  policy            mine                          report")
    for p in POLS:
        g = gap[p]
        lo, hi = np.percentile(g, 2.5), np.percentile(g, 97.5)
        if p in T.index:
            rr = (f"{T.loc[p, 'gap_closed']:.4f} [{T.loc[p, 'gap_lo']:.4f},"
                  f"{T.loc[p, 'gap_hi']:.4f}]")
        else:
            rr = "-"
        say(f"  {p:16s} {gpt[p]:.4f} [{lo:.4f},{hi:.4f}]      {rr}")
    say("")
    say("=" * 96)
    say("PAIRED DIFFERENCES")
    say("=" * 96)
    D = pd.read_csv(os.path.join(V31, "gaindiff_primary.csv"))
    D = D[(D.level == a.level) & (D.metric == "p99dl") & (D.quantity == "gain")]
    for x, y in (("CAP-G600", "FIXSEL-G600"), ("CAP-G600", "FIX-G600"),
                 ("CAP-G600", "SPJF-tweedie"), ("SPJF-tweedie", "SPJF-M4"),
                 ("CAP-G600", "SKIP-G600")):
        d = gap[x] - gap[y]
        lo, hi = np.percentile(d, 2.5), np.percentile(d, 97.5)
        row = D[D.pair == f"{x} - {y}"]
        rr = (f"{row['diff'].iloc[0]:+.4f} [{row.lo.iloc[0]:+.4f},{row.hi.iloc[0]:+.4f}]"
              if len(row) else "-")
        say(f"  {x} - {y:16s} mine {gpt[x] - gpt[y]:+.4f} [{lo:+.4f},{hi:+.4f}]   "
            f"report {rr}   resolved_mine={bool(lo > 0 or hi < 0)}")
    open(os.path.join(HERE, f"out_boot_L{a.level}.txt"), "w",
         encoding="utf-8").write("\n".join(OUT) + "\n")


if __name__ == "__main__":
    main()
