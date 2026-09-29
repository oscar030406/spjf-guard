"""L1 (fluid comparison) on small instances, and a recheck of the control in
docs/related_work/references_verified.md:193 that reports k servers against "one server
of speed k" breaching (k-1)L (max |D| = 22 at k = 3, L = 4).

L1: for every non-preemptive work-conserving k-server priority schedule,
    V(t) <= U(t) <= V(t) + (k-1) L  at every t,
with V the unfinished work of one server of rate k fed the same arrivals.

Integer arrivals and sizes: U has breakpoints at integers, V at multiples of 1/k, so
U - V is linear between consecutive multiples of 1/k and checking those points is exact.
Fractions throughout, no rounding.

Three columns per instance set:
  L1          U(t) - V(t) against [0, (k-1) L], V from the closed-form fluid recursion.
  control     |U - U_fast| with the control's speed-k server (next start = t + size,
              draining at rate k): reproduces the reported breach.
  corrected   the same with next start = t + size / k (a work-conserving speed-k server).

Run from the repository root:
  env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME uv run --no-sync python \
      evidence/envelope_bound/l1_check.py > evidence/envelope_bound/out_l1_check.txt
"""

from __future__ import annotations

import random
from fractions import Fraction as F


def k_server_starts(arrivals, sizes, keys, k):
    """Non-preemptive, work-conserving: at each event every free server takes the waiting
    job of smallest key."""
    n = len(arrivals)
    order = sorted(range(n), key=lambda j: (arrivals[j], j))
    start, free, waiting, p, t = [None] * n, [0] * k, [], 0, arrivals[order[0]]
    while p < n or waiting:
        while p < n and arrivals[order[p]] <= t:
            waiting.append(order[p])
            p += 1
        waiting.sort(key=lambda j: (keys[j], j))
        for s in range(k):
            if free[s] <= t and waiting:
                j = waiting.pop(0)
                start[j], free[s] = t, t + sizes[j]
        nxt = [arrivals[order[p]]] if p < n else []
        if waiting:
            nxt += [f for f in free if f > t]
        if not nxt:  # every job dispatched and no arrival left
            break
        t = min(nxt)
    return start


def unfinished(arrivals, sizes, start, t, rate):
    return sum(sizes[j] - min(sizes[j], rate * max(F(0), t - start[j]))
               for j in range(len(arrivals)) if arrivals[j] <= t)


def fluid(arrivals, sizes, t, k):
    """V(t): work arriving in [0, t] drained at rate k whenever positive."""
    events = sorted(zip(arrivals, sizes))
    v, last = F(0), F(0)
    for a, c in events:
        if a > t:
            break
        v = max(F(0), v - k * (a - last)) + c
        last = F(a)
    return max(F(0), v - k * (t - last))


def fast_single_starts(arrivals, sizes, k, divide):
    order = sorted(range(len(arrivals)), key=lambda j: (arrivals[j], j))
    start, free = [None] * len(arrivals), F(0)
    for j in order:
        start[j] = max(free, F(arrivals[j]))
        free = start[j] + (F(sizes[j], k) if divide else sizes[j])
    return start


def run(k, L, trials, seed):
    rng = random.Random(seed)
    lo = hi = worst_ctrl = worst_corr = F(0)
    lo_ex = hi_ex = None
    for _ in range(trials):
        n = rng.randint(2, 10)
        arrivals = sorted(rng.randint(0, 10) for _ in range(n))
        sizes = [rng.randint(1, L) for _ in range(n)]
        keys = [rng.random() for _ in range(n)]
        st = k_server_starts(arrivals, sizes, keys, k)
        ctrl = fast_single_starts(arrivals, sizes, k, divide=False)
        corr = fast_single_starts(arrivals, sizes, k, divide=True)
        horizon = max(arrivals) + sum(sizes) + 2
        for m in range(horizon * k + 1):
            t = F(m, k)
            u, v = unfinished(arrivals, sizes, st, t, 1), fluid(arrivals, sizes, t, k)
            d = u - v
            if d < lo:
                lo, lo_ex = d, (arrivals, sizes, t)
            if d > hi:
                hi, hi_ex = d, (arrivals, sizes, t)
            worst_ctrl = max(worst_ctrl, abs(u - unfinished(arrivals, sizes, ctrl, t, k)))
            worst_corr = max(worst_corr, abs(u - unfinished(arrivals, sizes, corr, t, k)))
    bound = (k - 1) * L
    print(f"k={k} L={L} trials={trials} seed={seed}: (k-1)L={bound}")
    print(f"  L1: min(U-V) = {lo} (must be >= 0), max(U-V) = {hi} (must be <= {bound});"
          f" {'PASS' if lo >= 0 and hi <= bound else 'FAIL'}")
    print(f"      max witness arrivals={hi_ex[0]} sizes={hi_ex[1]} t={hi_ex[2]}" if hi_ex else "")
    print(f"  control speed-k server (start gap = size): max |U - U_fast| = {float(worst_ctrl):.3f}")
    print(f"  corrected speed-k server (start gap = size/k): max |U - U_fast| ="
          f" {float(worst_corr):.3f}")


if __name__ == "__main__":
    run(3, 4, 4000, 7)
    for k, L, seed in ((2, 3, 1), (4, 5, 2), (5, 2, 3)):
        run(k, L, 2000, seed)
