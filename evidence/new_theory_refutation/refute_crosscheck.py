"""Independent cross-check of refute_sim.py, written without its code.

Pure Python, exact arithmetic (fractions).  Three parts:
  1. replay every witness in out_refute_witness.json: check the schedule is feasible
     (non-preemptive, work-conserving, k servers) and recompute W, W_FCFS, V_i^-, In
     and the bound it is said to violate;
  2. the guard-first versus head-first readings of P-union on the GFEX witness;
  3. random bursty instances under budget shapes the first simulator did not cover
     (age-relative eta > 0), lost reports (delta = infinity), rank-head clock and
     both union readings, with L1 evaluated at every breakpoint of U and V.

Event order (paper/sections/03_problem_model.tex): completions, then reports that
reach the counter, then arrivals (n_q = queue length at q's arrival), then the
dispatch phase.  Rank = (arrival, index).
"""

from __future__ import annotations

import json
import random
from fractions import Fraction as F

INF = float("inf")


def budget(q, t, arr, nq, k, shape):
    b0, gam, eta, cap = shape
    return min(b0 + gam * nq[q] + eta * k * (t - arr[q]), cap)


def run(arr, C, k, rule, base, theta=F(0), shape=(0, 0, F(0), 0), delta=0, rng=None):
    """rule: 'fcfs', 'free', 'clock', 'clock_time', 'guard', 'union_head', 'union_guard'.
    Returns start times and the dispatch sequence."""
    n = len(arr)
    free_at = [None] * k  # completion time of the job on each server, None if idle
    start = [None] * n
    comp = [None] * n
    reported = [False] * n
    over = [0] * n
    nq = [0] * n
    waiting = []  # ranks, kept sorted
    seq = []
    arrived = 0
    t = arr[0]
    while len(seq) < n:
        for m in range(k):
            if free_at[m] is not None and free_at[m] <= t:
                free_at[m] = None
        for c in range(n):
            if comp[c] is not None and not reported[c] and comp[c] + delta <= t:
                reported[c] = True
                for q in waiting:
                    if q < c:
                        over[q] += C[c]
        while arrived < n and arr[arrived] == t:
            nq[arrived] = len(waiting)
            waiting.append(arrived)
            arrived += 1
        while waiting and any(f is None for f in free_at):
            m = free_at.index(None)
            head = waiting[0]
            aged = t - arr[head] >= theta
            fired = [q for q in waiting if over[q] >= budget(q, t, arr, nq, k, shape)]
            j = None
            if rule == "fcfs":
                j = head
            elif rule == "clock" and aged:
                j = head
            elif rule == "guard" and fired:
                j = fired[0]
            elif rule == "union_head":
                if aged:
                    j = head
                elif fired:
                    j = fired[0]
            elif rule == "union_guard":
                if fired:
                    j = fired[0]
                elif aged:
                    j = head
            if j is None:
                opts = waiting
                if rule == "clock_time" and aged:
                    opts = [q for q in waiting if arr[q] == arr[head]]
                j = base(opts, t, C, rng)
            waiting.remove(j)
            start[j] = t
            comp[j] = t + C[j]
            free_at[m] = comp[j]
            seq.append(j)
        cand = [f for f in free_at if f is not None and f > t]
        if arrived < n:
            cand.append(arr[arrived])
        if delta != INF:
            cand += [comp[c] + delta for c in range(n)
                     if comp[c] is not None and not reported[c] and comp[c] + delta > t]
        t = min(cand) if cand else t
    return start, seq


def b_random(opts, t, C, rng):
    return rng.choice(opts)


def b_sjf(opts, t, C, rng):
    return min(opts, key=lambda q: (C[q], -q))


def b_ljf(opts, t, C, rng):
    return max(opts, key=lambda q: (C[q], q))


def b_youngest(opts, t, C, rng):
    return opts[-1]


BASES = [b_random, b_sjf, b_ljf, b_youngest]


def feasible(arr, C, k, start):
    """Non-preemptive k-server schedule that never idles a server while a job waits."""
    n = len(arr)
    pts = sorted(set(arr) | set(start) | {s + c for s, c in zip(start, C)})
    for t in pts:
        busy = sum(1 for j in range(n) if start[j] <= t < start[j] + C[j])
        wait = sum(1 for j in range(n) if arr[j] <= t < start[j])
        if busy > k or (wait > 0 and busy < k) or any(start[j] < arr[j] for j in range(n)):
            return False
    return True


def fluid_V(arr, C, k):
    V = [F(0)] * len(arr)
    for i in range(1, len(arr)):
        V[i] = max(F(0), V[i - 1] + C[i - 1] - k * (arr[i] - arr[i - 1]))
    return V


def in_out(seq, C):
    pos = {j: p for p, j in enumerate(seq)}
    n = len(seq)
    In = [sum(C[j] for j in range(i + 1, n) if pos[j] < pos[i]) for i in range(n)]
    Out = [sum(C[j] for j in range(i) if pos[j] > pos[i]) for i in range(n)]
    return In, Out


def l1_gap(arr, C, k, start):
    """max_t (U(t) - V(t)) and min_t (U(t) - V(t)) over every breakpoint, exact."""
    n = len(arr)

    def U(t):
        return sum(F(C[j]) if start[j] >= t else max(F(0), C[j] - (t - start[j]))
                   for j in range(n) if arr[j] <= t)

    def Vt(t):
        v, last = F(0), arr[0]
        for a, c in zip(arr, C):
            if a > t:
                break
            v = max(F(0), v - k * (a - last)) + c
            last = a
        return max(F(0), v - k * (t - last))

    pts = set(arr) | set(start) | {s + c for s, c in zip(start, C)}
    for a in set(arr):  # instants the fluid empties
        v = Vt(a)
        pts.add(a + v / k)
    lo, hi = F(0), F(0)
    for t in pts:
        d = U(t) - Vt(t)
        hi, lo = max(hi, d), min(lo, d)
    return hi, lo


def check_run(arr, C, k, L, start, seq, WF, V, theta, cap, stats, key, clock_claim, guard_claim):
    In, _ = in_out(seq, C)
    for i in range(len(arr)):
        W = start[i] - arr[i]
        rec = stats.setdefault(key, {})

        def put(name, lhs, rhs, strict):
            r = rec.setdefault(name, [F(0), 0])
            if rhs > 0 and F(lhs) / rhs > r[0]:
                r[0] = F(lhs) / rhs
            if (strict and lhs >= rhs) or (not strict and lhs > rhs):
                r[1] += 1

        put("PABS", k * W, V[i] + (k - 1) * L + In[i], False)
        if clock_claim:
            if In[i] > 0:
                put("CIN", In[i], k * (theta + L), True)
            put("CEX", W - WF[i], theta + F(3 * k - 2, k) * L, True)
            put("CABS", W, V[i] / k + theta + F(2 * k - 1, k) * L, True)
        if guard_claim:
            if In[i] > 0:
                put("GIN", In[i], cap + k * L, True)
            put("GEX", W - WF[i], F(cap, k) + F(3 * k - 2, k) * L, True)
            put("GABS", W, (V[i] + cap) / k + F(2 * k - 1, k) * L, True)


def replay_witnesses(path):
    data = json.load(open(path, encoding="utf-8"))
    out = {}
    for name, w in data.items():
        if "arrivals" not in w:
            continue
        arr, C, st, k, L = w["arrivals"], w["sizes"], w["starts"], w["k"], w["L"]
        n = len(arr)
        WF_start, _ = run(arr, C, k, "fcfs", None)
        WF = [s - a for s, a in zip(WF_start, arr)]
        V = fluid_V(arr, C, k)
        In, _ = in_out(w["dispatch_order"], C)
        theta, cap = F(w["theta"]).limit_denominator(2), w["B_cap"]
        ex = [st[i] - arr[i] - WF[i] for i in range(n)]
        if name.startswith("GFEX") or name.startswith("TIEEX"):
            bound = theta + F(3 * k - 2, k) * L
            label = "clock excess bound theta+(3-2/k)L"
        else:
            bound = F(cap, k) + F(3 * k - 2, k) * L
            label = "guard excess bound B/k+(3-2/k)L"
        i = max(range(n), key=lambda x: ex[x])
        out[name] = {"feasible": feasible(arr, C, k, st), "W_FCFS_matches": WF == w["W_FCFS"],
                     "V_matches": [int(v) for v in V] == w["V_minus"], "victim": i,
                     "excess": ex[i], "bound": str(bound), "bound_kind": label,
                     "violated": ex[i] >= bound, "In_victim": In[i], "ratio": float(ex[i] / bound)}
    return out


def gfex_readings(w):
    """Replay the GFEX witness's own schedule rule by rule under both union readings."""
    arr, C, k, L = w["arrivals"], w["sizes"], w["k"], w["L"]
    theta = F(w["theta"]).limit_denominator(2)
    shape = (0, w["gamma"], F(0), w["B_cap"])
    forced = list(w["dispatch_order"])

    def base_follow(opts, t, C_, rng):  # the witness's base choice when the rule leaves one
        for j in forced:
            if j in opts:
                return j
        raise AssertionError("witness base choice not available")

    WF_start, _ = run(arr, C, k, "fcfs", None)
    res = {}
    for rule in ("union_guard", "union_head"):
        st, seq = run(arr, C, k, rule, base_follow, theta, shape, 0)
        ex = [st[i] - arr[i] - (WF_start[i] - arr[i]) for i in range(len(arr))]
        res[rule] = {"starts": st, "order": seq, "max_excess": max(ex),
                     "clock_bound": str(theta + F(3 * k - 2, k) * L),
                     "guard_bound": str(F(w["B_cap"], k) + F(3 * k - 2, k) * L)}
    return res


def gen(rng, k, L):
    n = rng.randint(2, 18)
    arr, C, t = [], [], 0
    while len(arr) < n:
        for _ in range(rng.randint(1, 2 * k + 2)):
            if len(arr) < n:
                arr.append(t)
                C.append(L if rng.random() < 0.4 else rng.randint(1, L))
        t += rng.choice([0, 0, 1, rng.randint(1, L), rng.randint(1, 3 * L)])
    return arr, C


def random_phase(N, seed):
    rng = random.Random(seed)
    stats = {}
    l1 = {}
    for x in range(N):
        k = rng.randint(1, 4)
        L = rng.choice([3, 4, 10])
        arr, C = gen(rng, k, L)
        theta = F(rng.choice([0, 1, L, 2 * L, rng.randint(0, 4 * L)]), rng.choice([1, 2]))
        cap = rng.choice([0, L, k * L, rng.randint(0, 4 * k * L)])
        shape = rng.choice([(0, 0, F(0), cap), (0, rng.randint(1, L), F(0), cap),
                            (0, 0, F(rng.choice([1, 2, 3]), 4), cap),
                            (rng.randint(0, cap), rng.randint(0, L), F(1, 2), cap)])
        WFs, _ = run(arr, C, k, "fcfs", None)
        WF = [s - a for s, a in zip(WFs, arr)]
        V = fluid_V(arr, C, k)
        for base in BASES:
            st, seq = run(arr, C, k, "free", base, rng=rng)
            hi, lo = l1_gap(arr, C, k, st)
            e = l1.setdefault(k, [F(0), 0, 0])
            if k > 1:
                e[0] = max(e[0], hi / ((k - 1) * L))
            e[1] += hi > (k - 1) * L
            e[2] += lo < 0
            assert feasible(arr, C, k, st)
            check_run(arr, C, k, L, st, seq, WF, V, theta, cap, stats, (k, "free"), False, False)
            for rule, delta in (("clock", 0), ("union_head", 0), ("union_head", 7), ("union_head", INF),
                                ("union_guard", 0), ("guard", 0)):
                st, seq = run(arr, C, k, rule, base, theta, shape, delta, rng)
                assert feasible(arr, C, k, st)
                clock_claim = rule in ("clock", "union_head", "union_guard")
                guard_claim = rule in ("guard", "union_head", "union_guard") and delta == 0
                tag = rule + ("" if delta == 0 else f"_delta{delta}")
                shp = {(False, False): "const", (True, False): "gamma", (False, True): "eta",
                       (True, True): "gamma+eta"}[(shape[1] > 0, shape[2] > 0)]
                check_run(arr, C, k, L, st, seq, WF, V, theta, cap, stats, (k, f"{tag}/{shp}"),
                          clock_claim, guard_claim)
    return stats, l1


def main():
    d = "evidence/new_theory_refutation/"
    res = {"witness_replay": replay_witnesses(d + "out_refute_witness.json")}
    w = json.load(open(d + "out_refute_witness.json", encoding="utf-8"))["GFEX k=1"]
    res["gfex_readings"] = gfex_readings(w)
    N, seed = int(__import__("os").environ.get("XC_N", 20000)), 20260923
    stats, l1 = random_phase(N, seed)
    res["random"] = {"instances": N, "seed": seed,
                     "l1": {str(k): {"worst_hi_ratio": float(v[0]), "upper_viol": v[1], "lower_viol": v[2]}
                            for k, v in sorted(l1.items())},
                     "checks": {f"k={k} {rule}": {nm: {"worst_ratio": round(float(r[0]), 4), "violations": r[1]}
                                                  for nm, r in rec.items()}
                                for (k, rule), rec in sorted(stats.items())}}
    for name, v in res["witness_replay"].items():
        print("witness", name, json.dumps(v))
    for rule, v in res["gfex_readings"].items():
        print("GFEX k=1 under", rule, json.dumps(v))
    print("L1", json.dumps(res["random"]["l1"]))
    for key, rec in res["random"]["checks"].items():
        print(key, " ".join(f"{nm}={r['worst_ratio']}/{r['violations']}" for nm, r in rec.items()))
    with open(d + "out_refute_crosscheck.json", "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1, default=str)
    print("wrote", d + "out_refute_crosscheck.json")


if __name__ == "__main__":
    main()
