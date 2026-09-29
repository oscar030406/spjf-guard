"""The one disagreement found in 6,000 small instances (vsmall.py, it=4941), isolated.

My simulator and the builder's kernel agree job for job; both disagree with the exact
rational reference on one job by 22.3 s.  The instance is replayed twice: once with the
times in seconds (float64 clock, as both simulators run them) and once with the identical
instance expressed in integer microseconds, where the float64 clock is exact.  If the
disagreement is a float-clock tie between a completion and an arrival, the second run
agrees with the exact reference and the first does not.
"""
from __future__ import annotations

import sys
from fractions import Fraction as Fr

import numpy as np

import vsim
from vsmall import brute

sys.path.insert(0, r"<repo-root>\evidence\guard_variants")
import guardkern as GK                                                  # noqa: E402

A_MS = [3, 3, 4, 8, 9, 10, 10, 11, 12, 14, 15, 16, 17, 17, 18, 18, 19, 20, 20, 22, 22,
        22, 23, 23]
S_MS = [5000, 2, 5000, 2, 1, 1, 1, 2, 1000, 17345, 5000, 1000, 5000, 1, 17345, 17345, 1,
        1, 17345, 2, 5000, 1, 5000, 5000]
PRED = [1., 3., 3., 0., 0., 2., 1., 0., 2., 0., 2., 0., 3., 1., 0., 0., 3., 0., 2., 0.,
        3., 0., 3., 1.]
K = 3

a_ms = np.array(A_MS, np.int64)
s_ms = np.array(S_MS, np.int64)
pred = np.array(PRED)
exact = np.array(brute([Fr(int(x), 1000) for x in a_ms], [Fr(int(x), 1000) for x in s_ms],
                       K, "pri", pred))

sec_mine = vsim.run(a_ms / 1000.0, s_ms / 1000.0, K, policy="pri", pred=pred)["w"]
sec_kern = GK.run(a_ms / 1000.0, s_ms / 1000.0, K, policy="pri", pred=pred).w
# same instance, integer microseconds: every clock value is an exact float64 integer
us_mine = vsim.run((a_ms * 1000).astype(float), (s_ms * 1000).astype(float), K,
                   policy="pri", pred=pred)["w"] / 1e6

print("job    exact      seconds-clock (mine)   seconds-clock (kernel)   microsecond clock")
for i in range(len(a_ms)):
    print(f"{i:3d} {exact[i]:10.6f} {sec_mine[i]:18.6f} {sec_kern[i]:22.6f} "
          f"{us_mine[i]:22.6f}")
print(f"\nmax |exact - seconds clock|      {np.abs(exact - sec_mine).max():.6f}")
print(f"max |exact - microsecond clock|  {np.abs(exact - us_mine).max():.6f}")
print(f"max |kernel - mine| (seconds)    {np.abs(sec_kern - sec_mine).max():.6f}")
t = (a_ms[9] / 1000.0)
print(f"\nthe contested instant: job 9 arrives at a[9] = {t!r}")
print(f"completion of job 4 + service chain reaches t with float error ~{np.spacing(t):.3e} s")
