"""Check (b): a brute-force pure-Python reference of the model against the kernel.

    python evidence/abandonment_loop/check_reference.py [--instances 5000]

The reference keeps every waiting attempt in a plain list and recomputes every choice by
scanning it (the overtaking work of each waiting attempt is summed afresh at each
dispatch); it shares with the kernel only the seeded draws (`patience_us`, `resubmits`)
and the loop shape of MODEL.md section 3.  On random small integer instances (ties in
arrivals, services, scores and patience everywhere, zero services, services equal to L,
gating on and off, small segment-tree windows that force rebuilds) every per-job output
must agree exactly.

On each guarded instance it also evaluates the per-job bound against the two references
of MODEL.md section 7: R1 (FCFS without abandonment on the served attempts) must hold on
every instance; R2 (FCFS with the same abandonment on the first-attempt arrivals) is only
counted.  Writes out/check_reference.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from abandon_kernel import (  # noqa: E402
    ERR_WINDOW,
    GATE_RESULT,
    GATE_SUBMIT,
    MODE_FCFS,
    MODE_GUARD,
    MODE_SCORE,
    STATUS_SERVED,
    STATUS_WITHDRAWN,
    patience_us,
    resubmits,
    simulate_abandon,
)

MAX_RESUB = 3


def reference(a0, s, score, succ, gate, delta, offset, k, mode, b0, en, ed, bmax, gam,
              closed, seed, mean, p, max_resub):
    n = len(a0)
    pending = [(int(a0[i]), i) for i in range(n) if closed == 0 or gate[i] == 2]
    att = [0] * n
    status = [0] * n
    wait = [-1] * n
    a_prime = [-1] * n
    a_first = [-1] * n
    end = [-1] * n
    rank_job, rank_a, rank_cb, rank_due = [], [], [], []
    waiting = []  # ranks
    running = []  # (done, rank)
    completed = []  # (rank, work)
    n_abandon = n_resub = n_withdrawn = 0
    t = -(1 << 62)
    while True:
        # completions
        still = []
        for done, r in running:
            if done <= t:
                o = rank_job[r]
                completed.append((r, int(s[o])))
                if closed == 1 and succ[o] >= 0 and gate[succ[o]] == GATE_RESULT:
                    pending.append((done + int(delta[succ[o]]), int(succ[o])))
            else:
                still.append((done, r))
        running = still
        # abandonments
        for r in [r for r in waiting if rank_due[r] <= t]:
            waiting.remove(r)
            n_abandon += 1
            o = rank_job[r]
            if resubmits(seed, o, att[o], p, max_resub):
                att[o] += 1
                n_resub += 1
                pending.append((rank_due[r], o))
            else:
                status[o] = STATUS_WITHDRAWN
                end[o] = rank_due[r]
                n_withdrawn += 1
                if closed == 1 and succ[o] >= 0 and gate[succ[o]] == GATE_RESULT:
                    pending.append((rank_due[r] + int(delta[succ[o]]), int(succ[o])))
        # arrivals, in (instant, input index) order, including any released on the way
        while True:
            due_now = [x for x in pending if x[0] <= t]
            if not due_now:
                break
            rel, o = min(due_now)
            pending.remove((rel, o))
            a_prime[o] = rel
            if att[o] == 0:
                a_first[o] = rel
                nx = succ[o]
                if closed == 1 and nx >= 0 and gate[nx] == GATE_SUBMIT:
                    pending.append((rel + int(offset[nx]), int(nx)))
            cb = b0 + gam * len(waiting)
            if bmax > 0:
                cb = min(cb, bmax)
            rank_job.append(o)
            rank_a.append(rel)
            rank_cb.append(cb)
            rank_due.append(rel + int(patience_us(seed, o, att[o], mean)))
            waiting.append(len(rank_job) - 1)
        # one dispatch
        if len(running) < k and waiting:
            head = min(waiting)
            j = None
            if mode == MODE_FCFS:
                j = head
            elif mode == MODE_GUARD:
                def over(q):
                    return sum(w for r, w in completed if r > q)
                if bmax > 0 and over(head) >= bmax:
                    j = head
                else:
                    fired = [q for q in waiting
                             if ed * over(q) >= ed * rank_cb[q] + en * (t - rank_a[q])]
                    if fired:
                        j = min(fired)
            if j is None:
                j = min(waiting, key=lambda q: (score[rank_job[q]], q))
            waiting.remove(j)
            o = rank_job[j]
            wait[o] = t - a_prime[o]
            end[o] = t
            status[o] = STATUS_SERVED
            running.append((t + int(s[o]), j))
            continue
        # advance
        cands = [d for d, _ in running] + [x[0] for x in pending] + [rank_due[r] for r in waiting]
        if not cands:
            break
        t = max(min(cands), t)
    return {
        "wait": wait, "a_prime": a_prime, "a_first": a_first, "end": end,
        "status": status, "att": att,
        "counts": (n_abandon, n_resub, n_withdrawn),
    }


def random_instance(rng):
    n = int(rng.integers(1, 41))
    L = 12
    a0 = np.sort(rng.integers(0, 61, n)).astype(np.int64)
    s = rng.integers(0, L + 1, n).astype(np.int64)
    s[rng.random(n) < 0.1] = L
    s[rng.random(n) < 0.1] = 0
    users = rng.integers(0, max(1, n // 3) + 1, n)
    pred = np.full(n, -1, np.int64)
    last = {}
    for i in range(n):
        u = int(users[i])
        if u in last:
            pred[i] = last[u]
        last[u] = i
    succ = np.full(n, -1, np.int64)
    has = pred >= 0
    succ[pred[has]] = np.flatnonzero(has)
    delta = np.zeros(n, np.int64)
    offset = np.zeros(n, np.int64)
    delta[has] = a0[has] - (a0[pred[has]] + s[pred[has]])
    offset[has] = a0[has] - a0[pred[has]]
    gate = np.full(n, 2, np.uint8)
    gate[has] = np.where(delta[has] >= 0, 1, 0).astype(np.uint8)
    score = rng.integers(0, 6, n).astype(np.float64)
    k = int(rng.integers(1, 4))
    mode = int(rng.choice([MODE_FCFS, MODE_SCORE, MODE_GUARD, MODE_GUARD]))
    bmax = int(rng.integers(1, 41))
    b0 = int(rng.integers(0, bmax + 1))
    ed = int(rng.integers(1, 5))
    en = int(rng.integers(0, ed * k))  # eta = en / ed / k < 1
    gam = int(rng.choice([0, 0, rng.integers(1, 6)]))
    return {
        "a0": a0, "s": s, "score": score, "succ": succ, "gate": gate, "delta": delta,
        "offset": offset, "k": k, "mode": mode, "b0": b0, "en": en, "ed": ed,
        "bmax": bmax, "gam": gam, "L": L,
        "closed": int(rng.integers(0, 2)),
        "seed": int(rng.integers(0, 2**31)),
        "mean": float(rng.choice([0.0, 1.5, 4.0, 12.0, 40.0])),
        "p": float(rng.choice([0.0, 0.5, 1.0])),
        "mslots": int(rng.choice([8, 16, 1 << 10])),
    }


def run_kernel(x, a0=None, closed=None, mode=None, mean=None):
    a0 = x["a0"] if a0 is None else a0
    n = len(a0)
    out = simulate_abandon(
        np.ascontiguousarray(a0, np.int64), x["s"], x["score"], x["succ"], x["gate"],
        x["delta"], x["offset"], x["k"], x["mode"] if mode is None else mode,
        x["b0"], x["en"], x["ed"], x["bmax"], x["mslots"], x["gam"],
        x["closed"] if closed is None else closed, x["seed"],
        x["mean"] if mean is None else mean, x["p"], MAX_RESUB, (MAX_RESUB + 1) * n,
        np.argsort(a0, kind="stable").astype(np.int64),
    )
    return out


def fcfs_plain(a, s, k):
    """FCFS without abandonment, open-loop, by the reference (ties to the input order)."""
    n = len(a)
    z = np.zeros(n, np.int64)
    r = reference(a, s, np.zeros(n), np.full(n, -1, np.int64), np.full(n, 2, np.uint8),
                  z, z, k, MODE_FCFS, 0, 0, 1, 0, 0, 0, 0, 0.0, 0.0, 0)
    return np.array(r["wait"], np.int64)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--instances", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)
    stats = {"instances": 0, "window_errors_skipped": 0, "mismatches": 0, "by_mode": {},
             "instances_with_window_rebuild": 0,
             "abandon_events": 0, "resubmissions": 0, "withdrawn": 0,
             "guarded_instances": 0, "r1_additive_violations": 0,
             "r1_multiplicative_violations": 0, "r2_instances_over_bound": 0,
             "r2_jobs_over_bound": 0, "r2_worst_excess_minus_bound": None}
    first_bad = None
    for _ in range(args.instances):
        x = random_instance(rng)
        out = run_kernel(x)
        if out[7] == ERR_WINDOW:
            stats["window_errors_skipped"] += 1
            continue
        assert out[7] == 0, out[7]
        ref = reference(x["a0"], x["s"], x["score"], x["succ"], x["gate"], x["delta"],
                        x["offset"], x["k"], x["mode"], x["b0"], x["en"], x["ed"],
                        x["bmax"], x["gam"], x["closed"], x["seed"], x["mean"], x["p"],
                        MAX_RESUB)
        stats["instances"] += 1
        stats["by_mode"][x["mode"]] = stats["by_mode"].get(x["mode"], 0) + 1
        same = (
            np.array_equal(out[0], ref["wait"]) and np.array_equal(out[1], ref["a_prime"])
            and np.array_equal(out[2], ref["a_first"]) and np.array_equal(out[3], ref["end"])
            and np.array_equal(out[4], ref["status"]) and np.array_equal(out[5], ref["att"])
            and tuple(int(v) for v in out[6][4:7]) == ref["counts"]
        )
        assert set(np.unique(out[4])) <= {STATUS_SERVED, STATUS_WITHDRAWN}
        if not same:
            stats["mismatches"] += 1
            if first_bad is None:
                first_bad = {k_: (v.tolist() if isinstance(v, np.ndarray) else v)
                             for k_, v in x.items()}
            continue
        stats["instances_with_window_rebuild"] += int(out[6][7] > 0)
        stats["abandon_events"] += ref["counts"][0]
        stats["resubmissions"] += ref["counts"][1]
        stats["withdrawn"] += ref["counts"][2]
        if x["mode"] != MODE_GUARD:
            continue
        stats["guarded_instances"] += 1
        k, L = x["k"], x["L"]
        served = out[4] == STATUS_SERVED
        w = out[0][served]
        # R1: FCFS without abandonment on the served attempts' realised arrivals
        order = np.argsort(out[1][served], kind="stable")
        wf_sorted = fcfs_plain(out[1][served][order], x["s"][served][order], k)
        wf = np.empty_like(wf_sorted)
        wf[order] = wf_sorted
        add_rhs = k * wf + x["bmax"] + (3 * k - 2) * L
        stats["r1_additive_violations"] += int((k * w > add_rhs).sum())
        if x["gam"] == 0:
            lhs = (k * x["ed"] - x["en"]) * w
            rhs = x["ed"] * (k * wf + x["b0"] + (3 * k - 2) * L)
            stats["r1_multiplicative_violations"] += int((lhs > rhs).sum())
        # R2: FCFS with the same abandonment rule, open-loop, on the first-attempt arrivals
        r2 = run_kernel(x, a0=out[2], closed=0, mode=MODE_FCFS)
        both = served & (r2[4] == STATUS_SERVED)
        d_p = out[3][both] - out[2][both]
        d_f = r2[3][both] - r2[2][both]
        over = k * d_p - (k * d_f + x["bmax"] + (3 * k - 2) * L)
        if (over > 0).any():
            stats["r2_instances_over_bound"] += 1
            stats["r2_jobs_over_bound"] += int((over > 0).sum())
            worst = int(over.max())
            prev = stats["r2_worst_excess_minus_bound"]
            stats["r2_worst_excess_minus_bound"] = worst if prev is None else max(prev, worst)
    stats["by_mode"] = {["FCFS", "SCORE", "GUARD"][m]: c for m, c in stats["by_mode"].items()}
    stats["first_mismatch"] = first_bad
    print(json.dumps(stats, indent=2))
    (HERE / "out" / "check_reference.json").write_text(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
