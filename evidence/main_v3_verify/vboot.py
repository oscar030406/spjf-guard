"""C4: my own week-block paired bootstrap of the gap closed at rho 1.0.

Waits come from MY simulator (vsim), not from the builder's.  One resample draws the 30
whole weeks of the overlay timeline with replacement (multinomial), the SAME draw is
applied to every policy and to every one of the five overlays -- that is what "paired"
means here -- and the statistic is

    gap_b = mean over the five overlays of (FCFS_b - policy_b) / (FCFS_b - SJFref_b)

with each term the p99 of the waits of the deadline-window jobs of that resampled pool.
The quantile of a resampled pool is the order statistic at floor((N-1)*0.99) of the pooled
sample in which week w appears M[b,w] times (no interpolation between neighbours: with
4.2 M jobs per overlay the two neighbours differ by ~1e-3 s).

usage: vboot.py [--nboot 2000] [--seed 777]
"""
from __future__ import annotations

import argparse
import os
import time

import numpy as np

import vsim
from vsim import WORK

POLICIES = ("FCFS", "SJF-ref", "SPJF-tweedie", "SPJF-M4", "CAP-G600")
NBLK = 4000


class Q:
    """p99 of the deadline-window waits under week multiplicities, prepared once."""

    def __init__(self, w, wk, dl, nw):
        x = w[dl]
        k = wk[dl].astype(np.int64)
        o = np.argsort(x, kind="stable")
        self.xs = x[o]
        self.ws = k[o]
        n = len(self.xs)
        self.edges = np.unique(np.linspace(0, n, min(NBLK, n) + 1).astype(np.int64))
        nb = len(self.edges) - 1
        blk = np.repeat(np.arange(nb), np.diff(self.edges))
        self.H = np.bincount(self.ws * nb + blk, minlength=nw * nb).reshape(nw, nb)
        self.nb = nb

    def run(self, M, q=0.99):
        cum = np.cumsum(M.astype(np.float64) @ self.H.astype(np.float64), axis=1)
        out = np.empty(M.shape[0])
        for b in range(M.shape[0]):
            N = int(cum[b, -1])
            r = int(np.floor((N - 1) * q))
            j = int(np.searchsorted(cum[b], r, side="right"))
            before = cum[b, j - 1] if j > 0 else 0.0
            s0, s1 = self.edges[j], self.edges[j + 1]
            cw = np.cumsum(M[b, self.ws[s0:s1]])
            i = int(np.searchsorted(cw, r - before + 1, side="left"))
            out[b] = self.xs[s0 + min(i, s1 - s0 - 1)]
        return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nboot", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--level", type=int, default=2)
    ap.add_argument("--reps", default="0,1,2,3,4")
    a = ap.parse_args()
    reps = [int(x) for x in a.reps.split(",")]

    t0 = time.time()
    qs = {}
    nw = None
    point = {}
    for r in reps:
        z = np.load(os.path.join(vsim.BUILDER_TRACES, f"primary_rep{r}.npz"))
        Z = {q: z[q] for q in ("a", "svc", "dl", "wk", "weeks", "K", "tweedie", "M4",
                               "M4refit")}
        k = int(Z["K"][a.level])
        dl = Z["dl"].astype(bool)
        wk = Z["wk"].astype(np.int64)
        nw = len(Z["weeks"])
        assert wk.max() < nw
        for p in POLICIES:
            kw, _ = __import__("vbig").policy_spec(p, k, Z)
            w = vsim.run(Z["a"], Z["svc"], k, **kw)["w"]
            qs[(r, p)] = Q(w, wk, dl, nw)
            point[(r, p)] = float(np.quantile(w[dl], .99))
            print(f"[{time.time() - t0:5.0f}s] rep{r} {p:15s} p99dl {point[(r, p)]:.4f}",
                  flush=True)
        del Z, z
    print(f"weeks in the overlay timeline: {nw}", flush=True)

    M = np.random.default_rng(a.seed).multinomial(nw, np.full(nw, 1.0 / nw),
                                                  size=a.nboot).astype(np.int64)
    B = {(r, p): qs[(r, p)].run(M) for r in reps for p in POLICIES}
    gap = {}
    for p in POLICIES:
        g = np.mean([(B[(r, "FCFS")] - B[(r, p)]) /
                     (B[(r, "FCFS")] - B[(r, "SJF-ref")]) for r in reps], axis=0)
        gp = float(np.mean([(point[(r, "FCFS")] - point[(r, p)]) /
                            (point[(r, "FCFS")] - point[(r, "SJF-ref")]) for r in reps]))
        gap[p] = g
        print(f"{p:15s} gap {gp:.4f} [{np.percentile(g, 2.5):.4f}, "
              f"{np.percentile(g, 97.5):.4f}]   (bootstrap median {np.median(g):.4f})")
    for x, y in (("SPJF-tweedie", "SPJF-M4"), ("CAP-G600", "SPJF-tweedie")):
        d = gap[x] - gap[y]
        print(f"{x} - {y}: {np.mean(d):+.4f} [{np.percentile(d, 2.5):+.4f}, "
              f"{np.percentile(d, 97.5):+.4f}]")
    np.savez(os.path.join(WORK, f"vboot_L{a.level}.npz"),
             **{f"{p}": gap[p] for p in POLICIES})


if __name__ == "__main__":
    main()
