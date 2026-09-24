"""Two side checks for the refutation report.

1. Wolff (1987) says earlier sample-path upper bounds on multichannel work in system
   are false.  The systems compared there (Wolff 1977; Loulou 1983) are the FCFS
   k-server queue against k single-server FCFS queues fed by cyclic assignment
   (job j to queue j mod k).  This searches small integer instances for the three
   sample-path orderings one would state:  U_FCFS(t) <= U_cyc(t) (work in system),
   Q_FCFS(t) <= Q_cyc(t) (work in queue), W_FCFS[i] <= W_cyc[i] (per-job delay),
   and, for contrast, the draft's L1 for FCFS:  V(t) <= U_FCFS(t) <= V(t) + (k-1)L.
2. Supremum witnesses for the clock's In bound and, at k = 1, its wait bound:
   a family on a grid of step 1/m (all quantities scaled by m) whose ratio -> 1.
"""

from __future__ import annotations

import itertools
import json
import random


def fcfs(arr, C, k):
    free = [arr[0]] * k
    st = []
    for a, c in zip(arr, C):
        m = min(range(k), key=lambda x: free[x])
        s = max(a, free[m])
        st.append(s)
        free[m] = s + c
    return st


def cyclic(arr, C, k):
    free = [arr[0]] * k
    st = []
    for j, (a, c) in enumerate(zip(arr, C)):
        m = j % k
        s = max(a, free[m])
        st.append(s)
        free[m] = s + c
    return st


def work(arr, C, st, t, queue_only=False):
    u = 0
    for a, c, s in zip(arr, C, st):
        if a <= t:
            if s > t:
                u += c
            elif not queue_only:
                u += max(0, c - (t - s))
    return u


def fluid(arr, C, k, t):
    v, last = 0, arr[0]
    for a, c in zip(arr, C):
        if a > t:
            break
        v = max(0, v - k * (a - last)) + c
        last = a
    return max(0, v - k * (t - last))


def wolff_search():
    found = {}
    rng = random.Random(1987)
    L = 3
    for k in (2, 3):
        for n in range(2, 7):
            space = itertools.product(
                itertools.combinations_with_replacement(range(5), n - 1),
                itertools.product((1, 2, 3), repeat=n))
            for tail, C in space:
                arr = (0,) + tail
                f = fcfs(arr, C, k)
                cy = cyclic(arr, C, k)
                tend = max(s + c for s, c in zip(cy, C)) + 1
                for t in range(tend):
                    uf, uc = work(arr, C, f, t), work(arr, C, cy, t)
                    qf, qc = work(arr, C, f, t, True), work(arr, C, cy, t, True)
                    v = fluid(arr, C, k, t)
                    if uf > uc:
                        found.setdefault(f"work_in_system k={k}", (arr, C, t, uf, uc))
                    if qf > qc:
                        found.setdefault(f"work_in_queue k={k}", (arr, C, t, qf, qc))
                    if not (v <= uf <= v + (k - 1) * L):
                        found.setdefault(f"L1_fcfs k={k}", (arr, C, t, v, uf))
                for i in range(n):
                    if f[i] - arr[i] > cy[i] - arr[i]:
                        found.setdefault(f"delay k={k}", (arr, C, i, f[i] - arr[i], cy[i] - arr[i]))
    del rng
    return {key: {"arrivals": list(v[0]), "sizes": list(v[1]), "t_or_job": v[2],
                  "fcfs": v[3], "other": v[4]} for key, v in found.items()}


def clock_family(k, theta, L, m):
    """Victim 0 at time 0, size 1; later-ranked filler of size 1 keeps every server busy on
    overtakers until theta - 1/m, then each server takes an overtaker of size L.  Base: youngest
    first.  Grid step 1/m, everything scaled by m.  Returns In/(k(theta+L)) and, for k = 1,
    excess/(theta+L)."""
    T, LL = theta * m, L * m
    arr, C = [0], [1]
    for step in range(T):  # k unit fillers arriving at every grid instant before theta
        arr += [step] * k
        C += [1] * k
    arr += [T - 1] * k  # k long overtakers, arriving at the last instant before theta
    C += [LL] * k
    n = len(arr)
    # simulate: youngest waiting first unless the head (job 0) has waited >= T
    free = [0] * k
    start = [None] * n
    order = []
    t = 0
    while any(s is None for s in start):
        waiting = [j for j in range(n) if start[j] is None and arr[j] <= t]
        for m_ in range(k):
            if free[m_] <= t and waiting:
                if t - arr[waiting[0]] >= T:
                    j = waiting[0]
                else:
                    j = waiting[-1]
                waiting.remove(j)
                start[j] = t
                order.append(j)
                free[m_] = t + C[j]
        nxt = [f for f in free if f > t] + [a for a in arr if a > t]
        t = min(nxt) if nxt else t + 1
    pos = {j: p for p, j in enumerate(order)}
    In = sum(C[j] for j in range(1, n) if pos[j] < pos[0])
    W = start[0]
    wf = fcfs(arr, C, k)[0]
    out = {"k": k, "theta": theta, "L": L, "m": m, "In": In / m, "In_ratio": In / (k * (T + LL)),
           "W": W / m, "W_FCFS": wf / m}
    if k == 1:
        out["excess_ratio"] = (W - wf) / (T + LL)
    return out


def sigma_check(trials=20000):
    """sigma = max_i (V_i^- + C_i) against the largest excess of arrived work over k times the
    length of any closed window [s, t], computed by brute force over window end points."""
    rng = random.Random(7)
    bad = 0
    for _ in range(trials):
        k = rng.randint(1, 4)
        n = rng.randint(1, 12)
        arr = sorted(rng.randint(0, 10) for _ in range(n))
        C = [rng.randint(1, 5) for _ in range(n)]
        v, sig = 0, 0
        for i in range(n):
            if i:
                v = max(0, v + C[i - 1] - k * (arr[i] - arr[i - 1]))
            sig = max(sig, v + C[i])
        brute = max(sum(c for a, c in zip(arr, C) if s <= a <= t) - k * (t - s)
                    for s in set(arr) for t in set(arr) if s <= t)
        bad += sig != brute
    return {"trials": trials, "mismatches": bad}


def main():
    res = {"sigma": sigma_check(), "wolff": wolff_search(),
           "clock_family": [clock_family(k, th, 3, m) for k in (1, 2, 3)
                            for th in (1, 3) for m in (1, 4, 16)]}
    path = "evidence/new_theory_refutation/out_refute_extras.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1)
    print("sigma check", res["sigma"])
    for key, v in res["wolff"].items():
        print("counterexample", key, v)
    for row in res["clock_family"]:
        print(row)
    print("wrote", path)


if __name__ == "__main__":
    main()
