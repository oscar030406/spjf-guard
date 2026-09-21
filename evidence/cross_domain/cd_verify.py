"""Check cd_kernel.simulate against an independent brute-force simulator.

The reference below is deliberately slow and literal: at every dispatch it recomputes
over[q] for every waiting job by summing the true service of the completed jobs of
higher rank, exactly as the definition reads.  Integer microseconds on both sides, so
the comparison of start times is exact.

    uv run ... python cd_verify.py     ->  out_verify.txt
"""
import sys

sys.dont_write_bytecode = True

import os
import numpy as np

import cd_common as C
from cd_kernel import simulate, POL_FCFS, POL_SPJF, POL_GUARD

INF = 1e30


def ref_sim(arrival, serv, pred, k, policy, en, ed, C0_us, Bcap_us):
    n = len(arrival)
    a_us = np.rint(arrival * 1e6).astype(np.int64)
    w_us = np.rint(serv * 1e6).astype(np.int64)
    start = np.full(n, -1.0)
    cw = np.zeros(n, np.int64)          # completed work by rank
    busy = []                            # (completion time, rank)
    waiting = set()
    i = 0
    t = float(arrival[0])
    ndisp = 0
    fired_count = 0
    while ndisp < n:
        keep = []
        for ct, r in busy:
            if ct <= t:
                cw[r] = w_us[r]
            else:
                keep.append((ct, r))
        busy = keep
        while i < n and arrival[i] <= t:
            waiting.add(i)
            i += 1
        while len(busy) < k and waiting:
            if policy == POL_FCFS:
                q = min(waiting)
            elif policy == POL_SPJF:
                q = min(waiting, key=lambda r: (pred[r], r))
            else:
                t_us = np.int64(round(t * 1e6))
                fired = []
                for qq in waiting:
                    over = int(cw[qq + 1:].sum())
                    ok = ed * over >= ed * C0_us + en * (t_us - a_us[qq])
                    if Bcap_us >= 0 and over >= Bcap_us:
                        ok = True
                    if ok:
                        fired.append(qq)
                if fired:
                    q = min(fired)
                    fired_count += 1
                else:
                    q = min(waiting, key=lambda r: (pred[r], r))
            start[q] = t
            waiting.discard(q)
            busy.append((t + serv[q], q))
            ndisp += 1
        nt = INF
        if i < n:
            nt = min(nt, float(arrival[i]))
        if busy:
            nt = min(nt, min(ct for ct, _ in busy))
        if nt >= INF:
            break
        t = nt
    return start, fired_count


def main():
    rng = np.random.default_rng(C.SEED)
    out = os.path.join(C.HERE, "out_verify.txt")
    with open(out, "w", encoding="utf-8") as fh:
        C.log(fh, "cd_kernel vs brute-force reference (exact start-time comparison)")
        bad = 0
        for trial in range(6):
            n = 900
            # bursty arrivals: a mixture of a Poisson stream and short dense bursts
            gaps = rng.exponential(0.6, n) * (rng.random(n) < 0.7)
            arrival = np.cumsum(gaps)
            serv = np.where(rng.random(n) < 0.03,
                            rng.uniform(5.0, 30.0, n), rng.exponential(0.3, n))
            serv = np.maximum(np.round(serv, 6), 1e-3)
            noise = np.exp(rng.normal(0, 1.2, n))
            pred = np.round(serv * noise, 6)
            if trial == 5:                      # adversarial: the longest 1% look shortest
                pred = serv.copy()
                big = np.argsort(-serv)[: max(1, n // 100)]
                pred[big] = 1e-6
            L = float(serv.max())
            for k in (1, 3, 7):
                cases = [("FCFS", POL_FCFS, 0, 1, 0, -1),
                         ("SPJF", POL_SPJF, 0, 1, 0, -1),
                         ("guard B=2L", POL_GUARD, 0, 1, int(round(2 * L * 1e6)), -1),
                         ("guard B=0", POL_GUARD, 0, 1, 0, -1),
                         ("guard rel eta=.5", POL_GUARD, 2 * k, 4,
                          int(round(k * L * 1e6)), int(round(12 * k * L * 1e6))),
                         ("guard rel eta=.75", POL_GUARD, 3 * k, 4,
                          int(round(k * L * 1e6)), int(round(4 * L * 1e6)))]
                for name, pol, en, ed, C0, Bc in cases:
                    s1, nf, nd = simulate(arrival, serv, pred, k, pol, en, ed, C0, Bc)
                    s2, nf2 = ref_sim(arrival, serv, pred, k, pol, en, ed, C0, Bc)
                    d = np.max(np.abs(s1 - s2))
                    if d > 0:
                        bad += 1
                        C.log(fh, f"  MISMATCH trial={trial} k={k} {name}: max|dt|={d:.9f} "
                                  f"first at rank {int(np.argmax(np.abs(s1-s2)))}")
            C.log(fh, f"  trial {trial}: done")
        C.log(fh, f"start-time mismatches over all trials/k/policies: {bad}")
        # the constant-budget guard must reduce to FCFS at B=0 and to SPJF at B=+inf
        n = 4000
        arrival = np.cumsum(rng.exponential(0.5, n))
        serv = np.maximum(np.round(rng.exponential(0.4, n), 6), 1e-3)
        pred = np.round(serv * np.exp(rng.normal(0, 1.0, n)), 6)
        k = 4
        s_f, _, _ = simulate(arrival, serv, pred, k, POL_FCFS, 0, 1, 0, -1)
        s_g0, _, _ = simulate(arrival, serv, pred, k, POL_GUARD, 0, 1, 0, -1)
        s_s, _, _ = simulate(arrival, serv, pred, k, POL_SPJF, 0, 1, 0, -1)
        s_gi, _, _ = simulate(arrival, serv, pred, k, POL_GUARD, 0, 1,
                              np.int64(10 ** 15), -1)
        C.log(fh, f"degenerate cases: max|guard(B=0)-FCFS| = {np.abs(s_g0-s_f).max():.9f}, "
                  f"max|guard(B=huge)-SPJF| = {np.abs(s_gi-s_s).max():.9f}")
        # work conservation / feasibility checks on a random run
        s, _, _ = simulate(arrival, serv, pred, k, POL_SPJF, 0, 1, 0, -1)
        C.log(fh, f"all jobs started: {bool((s >= 0).all())}; "
                  f"no start before arrival: {bool((s >= arrival - 1e-12).all())}")
        occ = 0
        ev = np.concatenate([s, s + serv])
        typ = np.concatenate([np.ones(n), -np.ones(n)])
        o = np.lexsort((typ, ev))   # a completion is ordered before a start at equal times
        cur = 0
        mx = 0
        for j in o:
            cur += typ[j]
            mx = max(mx, cur)
        C.log(fh, f"max concurrent jobs in service = {mx:.0f} (k = {k})")
        C.log(fh, "VERDICT: " + ("PASS" if bad == 0 else "FAIL"))
    print("wrote", out)


if __name__ == "__main__":
    main()
