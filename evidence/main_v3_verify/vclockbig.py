"""How much does the float64-seconds clock matter on a REAL trace?

The same cell is simulated twice: with the times in seconds (the builder's representation,
which mine mirrors) and with the identical times in integer microseconds, where every
clock value is an exact float64 integer and the event order cannot be decided by rounding.
Only the unguarded policies are run: the guard's internal accounting converts to
microseconds itself and would overflow if it were handed microsecond inputs.

usage: vclockbig.py --trace k1 --rep 0 --level 0
"""
from __future__ import annotations

import argparse
import os

import numpy as np

import vsim


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace", default="k1")
    ap.add_argument("--rep", type=int, default=0)
    ap.add_argument("--level", type=int, default=0)
    a = ap.parse_args()
    z = np.load(os.path.join(vsim.BUILDER_TRACES, f"{a.trace}_rep{a.rep}.npz"))
    arr, svc, K = z["a"], z["svc"], list(z["K"])
    tw = z["tweedie"]
    k = int(K[a.level]) if len(K) > 1 else int(K[0])
    au = np.round(arr * 1e6)
    su = np.round(svc * 1e6)
    print(f"{a.trace} rep{a.rep} L{a.level}: k={k} n={len(arr):,}; "
          f"microsecond values exact in float64: {bool(au.max() < 2 ** 53)}")
    for nm, kw in (("FCFS", dict(policy="fcfs")),
                   ("SPJF-tweedie", dict(policy="pri", pred=tw))):
        ws = vsim.run(arr, svc, k, **kw)["w"]
        wu = vsim.run(au, su, k, **kw)["w"] / 1e6
        d = np.abs(ws - wu)
        n = int((d > 1e-6).sum())
        print(f"  {nm:14s} jobs whose wait differs between the two clocks: {n:,} "
              f"({100.0 * n / len(d):.5f}%), max |diff| {d.max():.6f} s; "
              f"p99 of the deadline window {np.quantile(ws[z['dl'].astype(bool)], .99):.4f}"
              f" vs {np.quantile(wu[z['dl'].astype(bool)], .99):.4f} s")


if __name__ == "__main__":
    main()
