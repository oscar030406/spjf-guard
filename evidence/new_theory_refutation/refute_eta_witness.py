"""Smallest guard-first union counterexample with the age-relative budget shape (eta > 0).

Uses the simulator of refute_crosscheck.py.  Searches random instances with n = 3..7,
k = 1 and 2, L = 3, and keeps the first violation of the clock excess bound found at the
smallest n; then replays the same instance under the head-first union.
"""

from __future__ import annotations

import json
import random
from fractions import Fraction as F

import refute_crosscheck as xc


def search(seed=7, tries=200000):
    rng = random.Random(seed)
    L = 3
    for n in range(3, 8):
        for _ in range(tries // 5):
            k = rng.choice([1, 2])
            arr = sorted(rng.randint(0, 4) for _ in range(n))
            arr = [a - arr[0] for a in arr]
            C = [rng.randint(1, L) for _ in range(n)]
            theta = F(rng.randint(0, 8), 2)
            cap = rng.randint(1, 3 * k * L)
            eta = F(rng.choice([1, 2, 3]), 4)
            shape = (0, 0, eta, cap)
            base = rng.choice(xc.BASES[1:])
            WFs, _ = xc.run(arr, C, k, "fcfs", None)
            st, seq = xc.run(arr, C, k, "union_guard", base, theta, shape, 0)
            bound = theta + F(3 * k - 2, k) * L
            ex = [st[i] - WFs[i] for i in range(n)]
            i = max(range(n), key=lambda x: ex[x])
            if ex[i] >= bound:
                st2, _ = xc.run(arr, C, k, "union_head", base, theta, shape, 0)
                return {"k": k, "L": L, "arrivals": arr, "sizes": C, "theta": str(theta),
                        "B_max": cap, "eta": str(eta), "base": base.__name__,
                        "guard_first_starts": st, "dispatch_order": seq, "W_FCFS": [s - a for s, a in zip(WFs, arr)],
                        "victim": i, "excess": ex[i], "clock_bound": str(bound),
                        "head_first_starts": st2,
                        "head_first_max_excess": max(st2[j] - WFs[j] for j in range(n))}
    return None


if __name__ == "__main__":
    w = search()
    print(json.dumps(w))
    with open("evidence/new_theory_refutation/out_refute_eta_witness.json", "w", encoding="utf-8") as f:
        json.dump(w, f, indent=1)
