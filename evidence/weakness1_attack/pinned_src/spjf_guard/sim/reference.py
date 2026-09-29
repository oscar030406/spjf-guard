"""Independent, deliberately slow implementations the kernel is checked against.

Nothing here shares a line with `kernel.py`: these are written from the definitions so
that agreement between the two is evidence rather than a tautology.
"""

from __future__ import annotations

import heapq

import numpy as np


def lindley(arrival_us: np.ndarray, service_us: np.ndarray) -> np.ndarray:
    """Single-server FCFS waiting times by the Lindley recursion, in microseconds."""
    a = arrival_us.tolist()
    s = service_us.tolist()
    out = np.empty(len(a), np.int64)
    cur = 0
    for i in range(len(a)):
        if i:
            cur = max(0, cur + s[i - 1] - (a[i] - a[i - 1]))
        out[i] = cur
    return out


def kiefer_wolfowitz(arrival_us: np.ndarray, service_us: np.ndarray, k: int) -> np.ndarray:
    """k-server FCFS waiting times: start_i = max(a_i, earliest free server)."""
    free = [0] * k
    out = np.empty(len(arrival_us), np.int64)
    for i, (a, s) in enumerate(zip(arrival_us.tolist(), service_us.tolist())):
        f = heapq.heappop(free)
        start = a if a > f else f
        out[i] = start - a
        heapq.heappush(free, start + s)
    return out


class CostOracle:
    """The true service times, with every read recorded against the clock.

    The guard may read a job's cost only at or after the instant it completes; the
    reference scheduler asks this object, and `illegal_reads` is what a test inspects.
    """

    def __init__(self, service_us: np.ndarray):
        self._service = list(map(int, service_us))
        self.completion_us: dict[int, int] = {}
        self.reads: list[tuple[int, int, int]] = []

    def record_completion(self, job: int, when_us: int) -> None:
        self.completion_us[job] = when_us

    def read(self, job: int, now_us: int) -> int:
        """Read C_j at clock `now_us`; the read is legal only at or after j completed."""
        self.reads.append((job, now_us, self.completion_us.get(job, 1 << 62)))
        return self._service[job]

    def dispatch_service(self, job: int) -> int:
        """The server, not the scheduler, needs the size to know when the job ends."""
        return self._service[job]

    @property
    def illegal_reads(self) -> list[tuple[int, int, int]]:
        return [r for r in self.reads if r[1] < r[2]]


def _charge_completions(running, waiting, over, oracle, t, skip_count):
    """Retire every job finished by t and charge its work to the jobs it overtook."""
    for done_at, job in [x for x in running if x[0] <= t]:
        running.remove((done_at, job))
        oracle.record_completion(job, done_at)
        if skip_count == 0:
            cost = oracle.read(job, t)
            for q in waiting:
                if q < job:
                    over[q] += cost


def _fired_set(waiting, over, arrival_us, t, b0_us, eta_k, bmax_us):
    fired = []
    for q in waiting:
        budget = b0_us + eta_k * (t - arrival_us[q])
        if bmax_us > 0:
            budget = min(budget, bmax_us)
        if over[q] >= budget:
            fired.append(q)
    return fired


def brute_guard(
    arrival_us,
    service_us,
    score,
    k,
    b0_us=0,
    eta_k=0.0,
    bmax_us=0,
    skip_count=0,
    oracle: CostOracle | None = None,
):
    """O(n^2) reference wrapper written straight from Algorithm 1.

    `skip_count > 0` selects the position-count rule with the count charged at dispatch
    instead of the work budget.  Returns (wait_us, dispatch_index).
    """
    n = len(arrival_us)
    arrival = list(map(int, arrival_us))
    oracle = oracle or CostOracle(service_us)
    over = [0] * n
    passes = [0] * n
    wait = np.empty(n, np.int64)
    dispatch_index = np.empty(n, np.int64)
    free: list[int] = [0] * k
    heapq.heapify(free)
    running: list[tuple[int, int]] = []
    waiting: list[int] = []
    nxt = 0
    t = -(1 << 62)
    order = 0
    while nxt < n or waiting:
        server_free = heapq.heappop(free)
        t = max(server_free, t)
        if not waiting and nxt < n and arrival[nxt] > t:
            t = arrival[nxt]
        _charge_completions(running, waiting, over, oracle, t, skip_count)
        while nxt < n and arrival[nxt] <= t:
            waiting.append(nxt)
            nxt += 1
        if skip_count > 0:
            fired = [q for q in waiting if passes[q] >= skip_count]
        else:
            fired = _fired_set(waiting, over, arrival, t, b0_us, eta_k, bmax_us)
        j = min(fired) if fired else min(waiting, key=lambda q: (score[q], q))
        waiting.remove(j)
        for q in waiting:
            if q < j:
                passes[q] += 1
        wait[j] = t - arrival[j]
        dispatch_index[j] = order
        order += 1
        end = t + oracle.dispatch_service(j)
        running.append((end, j))
        heapq.heappush(free, end)
    return wait, dispatch_index
