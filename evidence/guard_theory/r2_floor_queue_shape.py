"""Floor of order L for the queue-length budget shape (B0 = eta = 0 < gamma).

Instance: k+2 jobs of work L arrive together at t = 0, ranks 0..k+1.  The wrapper is
Algorithm 1 of the paper with budget(q) = min(gamma * n_q, Bmax), n_q = number of jobs
waiting when q arrived, around a base policy that always prefers the highest rank.
Claim: the rank-1 job has excess exactly L over first-come first-served, for every k.

Run:  python r2_floor_queue_shape.py   (prints one line per configuration, then PASS/FAIL)
"""

from __future__ import annotations

import heapq


def simulate(k: int, n_jobs: int, L: int, gamma: float, bmax: float, guarded: bool) -> list[int]:
    """All jobs arrive at t = 0 in rank order with work L.  Returns start times by rank."""
    n_at_arrival = list(range(n_jobs))  # job q finds q jobs already waiting
    waiting = list(range(n_jobs))
    over = [0.0] * n_jobs
    start = [-1] * n_jobs
    running: list[tuple[int, int]] = []  # (completion time, rank)
    free, t = k, 0
    while waiting:
        while free and waiting:
            fired = [q for q in waiting if over[q] >= min(gamma * n_at_arrival[q], bmax)]
            if not guarded:
                j = min(waiting)  # first-come first-served
            elif fired:
                j = min(fired)
            else:
                j = max(waiting)  # base policy: highest rank first
            waiting.remove(j)
            start[j] = t
            heapq.heappush(running, (t + L, j))
            free -= 1
        if not waiting:
            break
        t, c = heapq.heappop(running)
        done = [c]
        while running and running[0][0] == t:
            done.append(heapq.heappop(running)[1])
        for c in done:
            free += 1
            for q in waiting:
                if q < c:
                    over[q] += L
    return start


def main() -> int:
    ok = True
    for k in (1, 2, 3, 4, 8):
        for L in (10, 60):
            for gamma, bmax in ((0.5, 5 * L), (L, 3 * L), (4 * L, 10 * L)):
                n = k + 2
                fcfs = simulate(k, n, L, gamma, bmax, guarded=False)
                wrap = simulate(k, n, L, gamma, bmax, guarded=True)
                excess = max(w - f for w, f in zip(wrap, fcfs))
                victim_excess = wrap[1] - fcfs[1]
                line_ok = victim_excess >= L and wrap[0] == 0
                ok &= line_ok
                print(
                    f"k={k} L={L} gamma={gamma} Bmax={bmax}: rank-1 excess={victim_excess} "
                    f"(= {victim_excess / L:.2f} L), max excess={excess}, "
                    f"rank-0 start={wrap[0]}  {'ok' if line_ok else 'FAIL'}"
                )
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
