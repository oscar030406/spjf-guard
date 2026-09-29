"""Regenerate and shrink the random-phase witnesses of refute_sim.py.

For every random instance whose seed is listed in out_refute_random.json as the worst
case of a check with violations, replay the exact loop of random_batch (same RNG
draws), keep the run that violates, then shrink the instance greedily (drop one job
at a time, then lower sizes and arrival gaps) while some deterministic base
(SJF, LJF, youngest-first, small-youngest-first) or, for n <= 8, some policy found by
exhaustive enumeration still violates the same check.  Prints the shrunk instance
with its full schedule.
"""

from __future__ import annotations

import json

import numba as nb
import numpy as np

import refute_sim as rs


@nb.njit(cache=True)
def regen(seed, kmax):
    np.random.seed(seed)
    k = 1 + np.random.randint(kmax)
    L = 3 if np.random.random() < 0.4 else (10 if np.random.random() < 0.7 else 24)
    arr, C = rs.gen_random(k, L, 40)
    u = np.random.randint(6)
    if u == 0:
        theta2 = 0
    elif u == 1:
        theta2 = 1
    elif u == 2:
        theta2 = 2 * L
    elif u == 3:
        theta2 = 2 * L + 1
    else:
        theta2 = np.random.randint(0, 8 * L + 1)
    u = np.random.randint(4)
    if u == 0:
        B = 0
    elif u == 1:
        B = L
    elif u == 2:
        B = k * L
    else:
        B = np.random.randint(0, 4 * k * L + 1)
    delta = np.random.randint(1, 3 * L + 1)
    gam = 0 if np.random.random() < 0.5 else np.random.randint(1, L + 1)
    return k, L, arr, C, theta2, B, delta, gam


def run_check(arr, C, k, L, mode, theta2, B, delta, gam, base, check):
    n = len(arr)
    WF = rs.fcfs_reference(arr, C, k) - arr
    V = rs.fluid_V(arr, C, k)
    s = np.zeros(n, np.int64)
    order = np.zeros(n, np.int64)
    dummy = np.zeros(n + 1, np.int64)
    rs.simulate(arr, C, k, mode, theta2, B, delta, gam, dummy, 0, dummy, base, s, order)
    r = np.full(rs.NCHK, rs.NEG)
    viol = np.zeros(rs.NCHK, np.int64)
    rs.evaluate(arr, C, k, L, mode, theta2, B, delta, s, order, WF, V, r, viol, mode == rs.FREE)
    return viol[check] > 0, float(r[check]), s, order, WF, V


def violates(arr, C, k, L, mode, theta2, B, delta, gam, check):
    for base in (rs.B_SJF, rs.B_LJF, rs.B_LIFO, rs.B_BIGYOUNG):
        ok, ratio, s, order, WF, V = run_check(arr, C, k, L, mode, theta2, B, delta, gam, base, check)
        if ok:
            return True, (ratio, s, order, WF, V, base)
    if len(arr) <= 8:
        r = np.full(rs.NCHK, rs.NEG)
        viol = np.zeros(rs.NCHK, np.int64)
        WF = rs.fcfs_reference(arr, C, k) - arr
        V = rs.fluid_V(arr, C, k)
        rs.explore(arr, C, k, L, mode, theta2, B, delta, gam, WF, V, r, viol, False)
        if viol[check] > 0:
            w = rs.witness(arr, C, k, L, mode, theta2, B, delta, gam, check)
            return True, (w["ratio"], np.array(w["starts"]), np.array(w["dispatch_order"]),
                          WF, V, "enumerated")
    return False, None


def normalise(arr):
    return arr - arr[0]


def shrink(arr, C, k, L, mode, theta2, B, delta, gam, check):
    changed = True
    while changed:
        changed = False
        for j in range(len(arr)):
            a2 = normalise(np.delete(arr, j))
            c2 = np.delete(C, j)
            if len(a2) >= 2 and violates(a2, c2, k, L, mode, theta2, B, delta, gam, check)[0]:
                arr, C, changed = a2, c2, True
                break
        if changed:
            continue
        for j in range(len(arr)):
            if C[j] > 1:
                c2 = C.copy()
                c2[j] -= 1
                if violates(arr, c2, k, L, mode, theta2, B, delta, gam, check)[0]:
                    C, changed = c2, True
                    break
        if changed:
            continue
        for j in range(1, len(arr)):
            if arr[j] > arr[j - 1]:
                a2 = arr.copy()
                a2[j:] -= 1
                if violates(a2, C, k, L, mode, theta2, B, delta, gam, check)[0]:
                    arr, changed = a2, True
                    break
    return arr, C


def main():
    data = json.load(open("evidence/new_theory_refutation/out_refute_random.json"))
    wanted = {"GFEX": (rs.UNION_GF, 0), "DGEX": (rs.UNION, 1), "TIEEX": (rs.CLOCK_TIE, 0)}
    out = {}
    for kk, per in data["random"]["per_k"].items():
        for name, (mode, use_delay) in wanted.items():
            e = per.get(name)
            if not e or e["violations"] == 0:
                continue
            k, L, arr, C, theta2, B, delta, gam = regen(e["worst_instance_seed"], 4)
            d = delta if use_delay else 0
            check = rs.NAMES.index(name)
            ok, _ = violates(arr, C, k, L, mode, theta2, B, d, gam, check)
            if not ok:
                out[f"{name} k={kk}"] = {"note": "worst seed violates only under the random base"}
                continue
            a2, c2 = shrink(arr, C, k, L, mode, theta2, B, d, gam, check)
            _, (ratio, s, order, WF, V, base) = violates(a2, c2, k, L, mode, theta2, B, d, gam, check)
            out[f"{name} k={kk}"] = {
                "seed": e["worst_instance_seed"], "k": int(k), "L": int(L), "theta": theta2 / 2,
                "B_cap": int(B), "gamma": int(gam), "delay": int(d), "base": str(base),
                "n_before_shrink": int(len(arr)), "arrivals": a2.tolist(), "sizes": c2.tolist(),
                "starts": [int(x) for x in s], "dispatch_order": [int(x) for x in order],
                "W": [int(x) - int(y) for x, y in zip(s, a2)], "W_FCFS": [int(x) for x in WF],
                "V_minus": [int(x) for x in V], "ratio": ratio}
            print(name, "k =", kk, json.dumps(out[f"{name} k={kk}"]), flush=True)
    with open("evidence/new_theory_refutation/out_refute_witness.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print("wrote evidence/new_theory_refutation/out_refute_witness.json")


if __name__ == "__main__":
    main()
