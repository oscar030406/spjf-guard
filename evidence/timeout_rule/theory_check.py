"""Falsification check: a head-of-line timeout carries the guard's FCFS-relative bound.

Claim (derived by hand, not yet in the paper).  Timeout(theta): at every dispatch
epoch, if the oldest waiting job has waited at least theta, serve it; otherwise serve
the base policy's choice.  On k identical non-preemptive servers with every service at
most L, for every base policy and every arrival sequence,

    W_timeout[i] <= W_FCFS[i] + theta + (3 - 2/k) L          for every job i.

Proof sketch: after a_i + theta only jobs older than i are dispatched until i starts,
so the work of later jobs that starts before i is at most k*theta + k*L; the
net-overtake identity then gives the bound.  The same inequality also follows from
the FCFS sandwich (V_i - C_i - (k-1)L)/k <= W_FCFS[i] <= (V_i - C_i + (k-1)L)/k,
which this script checks as well.

Independent of the package kernel: a plain event loop over integer times.  A single
job above its bound refutes the claim.
"""

from __future__ import annotations

import itertools
import random


def simulate(arrival, size, k, choose):
    """Start time of every job; jobs are indexed in rank (arrival) order."""
    n = len(arrival)
    start = [None] * n
    waiting, running = [], []
    t, nxt = 0, 0
    while any(s is None for s in start):
        running = [f for f in running if f > t]
        while nxt < n and arrival[nxt] <= t:
            waiting.append(nxt)
            nxt += 1
        while len(running) < k and waiting:
            j = choose(waiting, t)
            waiting.remove(j)
            start[j] = t
            running.append(t + size[j])
        events = running + ([arrival[nxt]] if nxt < n else [])
        t = min(events)
    return start


def fcfs_rule(waiting, t):
    return min(waiting)


def timeout_rule(arrival, score, theta):
    def choose(waiting, t):
        head = min(waiting)
        if t - arrival[head] >= theta:
            return head
        return min(waiting, key=lambda j: (score[j], j))

    return choose


def fluid_backlog(arrival, size, k):
    """V_i: backlog of one fluid server of rate k just after job i arrives."""
    out, v, last = [], 0.0, arrival[0]
    for a, c in zip(arrival, size):
        v = max(0.0, v - k * (a - last)) + c
        last = a
        out.append(v)
    return out


def check(arrival, size, score, k, theta, limit, worst):
    fcfs = simulate(arrival, size, k, fcfs_rule)
    w_fcfs = [s - a for s, a in zip(fcfs, arrival)]
    v = fluid_backlog(arrival, size, k)
    for i in range(len(arrival)):
        lo = (v[i] - size[i] - (k - 1) * limit) / k
        hi = (v[i] - size[i] + (k - 1) * limit) / k
        if not (lo - 1e-9 <= w_fcfs[i] <= hi + 1e-9):
            raise AssertionError(("sandwich", arrival, size, k, i, lo, w_fcfs[i], hi))
    timed = simulate(arrival, size, k, timeout_rule(arrival, score, theta))
    bound = theta + (3 - 2 / k) * limit
    for i in range(len(arrival)):
        excess = (timed[i] - arrival[i]) - w_fcfs[i]
        if excess > bound + 1e-9:
            raise AssertionError(("timeout", arrival, size, score, k, theta, i, excess, bound))
        key = (k, theta)
        if excess / bound > worst.get(key, (0.0, None))[0]:
            worst[key] = (excess / bound, (arrival, size, score, i, excess))


def exhaustive(limit=3, n_max=4, arrivals=range(0, 4)):
    worst, cases = {}, 0
    for k in (1, 2):
        for n in range(1, n_max + 1):
            for arrival in itertools.combinations_with_replacement(arrivals, n):
                for size in itertools.product(range(1, limit + 1), repeat=n):
                    for score in itertools.permutations(range(n)):
                        for theta in (0, 1, 2, 3):
                            check(list(arrival), list(size), list(score), k, theta, limit, worst)
                            cases += 1
    return cases, worst


def randomised(trials=200_000, seed=7):
    rng = random.Random(seed)
    worst = {}
    for _ in range(trials):
        k = rng.randint(1, 4)
        limit = rng.choice((3, 5, 10))
        n = rng.randint(2, 40)
        arrival = sorted(rng.randint(0, rng.choice((5, 20, 60))) for _ in range(n))
        size = [rng.choice((1, limit, rng.randint(1, limit))) for _ in range(n)]
        score = [rng.random() if rng.random() < 0.5 else -size[j] for j in range(n)]
        theta = rng.choice((0, 1, limit, 3 * limit, rng.randint(0, 4 * limit)))
        check(arrival, size, score, k, theta, limit, worst)
    return trials, worst


def main() -> None:
    cases, worst = exhaustive()
    print(f"exhaustive: {cases:,} (instance, theta) cases, k in (1, 2), n <= 4, L = 3: 0 violations")
    for key in sorted(worst):
        ratio, (arrival, size, score, i, excess) = worst[key]
        print(f"  k={key[0]} theta={key[1]}: worst excess/bound {ratio:.3f}"
              f"  (excess {excess} on job {i}; arrivals {arrival}, sizes {size}, scores {score})")
    trials, worst = randomised()
    print(f"randomised: {trials:,} instances, k in 1..4, n <= 40: 0 violations")
    by_k = {}
    for (k, _theta), (ratio, _) in worst.items():
        by_k[k] = max(by_k.get(k, 0.0), ratio)
    for k in sorted(by_k):
        print(f"  k={k}: worst excess/bound {by_k[k]:.3f}")


if __name__ == "__main__":
    main()
