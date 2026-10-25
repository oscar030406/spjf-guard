"""Is reservation charging with the public cap L (every ell_j = L) at least as permissive as
Algorithm 1 at the same promise G, and does it keep the promise?

At promise G the guard's cap is B = kG - (3k-2)L (Corollary 3) and the reservation rule's
constant allowance is Z = kG - (2k-2)L (Supplementary S7.6 with ell = L), so Z = B + kL.

Exhaustive over every base-policy choice at every dispatch, on every instance of the grid
below.  Uses the dispatch rules of ../reservation_guard_verify/rguard_indep.py.
    python check_public_cap.py > out_check_public_cap.txt
"""
import sys
from itertools import product
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reservation_guard_verify"))
from rguard_indep import INF, _next_time, allowed_C, allowed_R, fcfs_wait  # noqa: E402

L = 3
SIZES = (1, 2, 3)
ARRIVALS = (0, 1, 2)


def explore(jobs, k, B, Z, rule, stats):
    """Every run reachable under `rule` ('C' guard, 'R' reservation); per state, compare the
    two permitted sets; per finished run, record the largest excess."""
    n = len(jobs)
    arr = [a for a, _ in jobs]
    svc = [c for _, c in jobs]
    ell = [L] * n
    wf = fcfs_wait(jobs, k)

    def rec(t, busy, nxt, queue, start, fin, done):
        while nxt < n and arr[nxt] <= t:
            queue = queue + (nxt,)
            nxt += 1
        free = next((m for m in range(k) if busy[m] <= t), -1)
        if free >= 0 and queue:
            ac = allowed_C(t, queue, fin, svc, B, n)
            ar = allowed_R(t, queue, fin, svc, ell, Z, n)
            stats["states"] += 1
            if not set(ac) <= set(ar):
                stats["not_superset"] += 1
                stats.setdefault("witness", (jobs, k, t, queue, ac, ar))
            if len(ar) > len(ac):
                stats["strictly_more"] += 1
            for c in (ac if rule == "C" else ar):
                j = queue[c]
                nb = list(busy)
                nb[free] = t + svc[j]
                ns = list(start)
                ns[j] = t
                nf = list(fin)
                nf[j] = t + svc[j]
                rec(t, tuple(nb), nxt, queue[:c] + queue[c + 1:], tuple(ns), tuple(nf), done + 1)
            return
        if done == n:
            worst = max(start[i] - arr[i] - wf[i] for i in range(n))
            stats["runs"] += 1
            stats["max_excess"] = max(stats["max_excess"], worst)
            return
        t2 = _next_time(t, busy, arr, nxt, n)
        if t2 < INF:
            rec(t2, busy, nxt, queue, start, fin, done)

    rec(arr[0], tuple([-INF] * k), 0, (), tuple([None] * n), tuple([None] * n), 0)


def main():
    for k, n in ((2, 4), (2, 5), (3, 5)):
        for G_extra in range(0, 4):
            G = (3 * k - 2) * L // k + 1 + G_extra      # smallest integer G with B > 0, and up
            B = k * G - (3 * k - 2) * L
            Z = B + k * L
            for rule in ("C", "R"):
                stats = dict(states=0, not_superset=0, strictly_more=0, runs=0, max_excess=-INF)
                instances = 0
                for sizes in product(SIZES, repeat=n):
                    for arrivals in product(ARRIVALS, repeat=n):
                        if list(arrivals) != sorted(arrivals):
                            continue
                        instances += 1
                        explore(list(zip(arrivals, sizes)), k, B, Z, rule, stats)
                print(f"k={k} n={n} G={G} B={B} Z={Z} rule={rule}: instances={instances} "
                      f"runs={stats['runs']} states={stats['states']} "
                      f"not_superset={stats['not_superset']} strictly_more={stats['strictly_more']} "
                      f"strictly_more_share_pct={100 * stats['strictly_more'] / stats['states']:.1f} "
                      f"max_excess={stats['max_excess']} (promise G={G}, holds={stats['max_excess'] < G})",
                      flush=True)
                if "witness" in stats:
                    print("  witness", stats["witness"], flush=True)


if __name__ == "__main__":
    main()
