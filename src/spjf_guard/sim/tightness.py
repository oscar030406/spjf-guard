"""The explicit families that make the two constants of the theory exact.

Both are geometric cascades: m rounds in which a policy preferring short jobs drives the
unfinished-work gap against FCFS to (k-1)L(1 - ((k-1)/k)^m), followed by one batch that
adds a second (k-1)L.  The builders return integer traces in the unit the caller picks,
so the same instance can be simulated exactly.

    identity_family   |k(W_P - W_FCFS) - (In - Out)| -> 2(k-1)L
    wrapper_family    (k excess - B)/L -> 3k-2

Published values these reproduce (prechecks/guard_theory/out_sharp_family.txt and
out_wrapper_tight.txt): at k = 2, L = 64, m = 6 the identity family reaches 127/64 L in
both directions on 649 and 393 jobs, and the wrapper family reaches c(2) = 127/32 with
B = 128 and an excess of 191 on 396 jobs.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Instance:
    """One adversarial trace: arrivals, service times, a static priority, and the victim."""

    arrival: np.ndarray
    service: np.ndarray
    priority: np.ndarray
    victim: int

    def __len__(self) -> int:
        return len(self.arrival)


def cascade_leftover(k: int, limit: int, rounds: int) -> int:
    """f = L(1 - ((k-1)/k)^m), the work each busy server still holds when the cascade ends."""
    return limit - (limit * (k - 1) ** rounds) // (k**rounds)


def _cascade(arrival, service, priority, k, limit, rounds, bigs_first: bool):
    """m rounds of k-1 jobs of service L and L jobs of service 1, the short ones preferred."""
    for j in range(rounds):
        start = j * limit
        big = (start, limit, 2 * j + (1 if bigs_first else 0))
        tiny = (start, 1, 2 * j + (0 if bigs_first else 1))
        first, second = (big, tiny) if bigs_first else (tiny, big)
        for _ in range(k - 1 if bigs_first else limit):
            arrival.append(first[0])
            service.append(first[1])
            priority.append(first[2])
        for _ in range(limit if bigs_first else k - 1):
            arrival.append(second[0])
            service.append(second[1])
            priority.append(second[2])


def identity_family(k: int, limit: int, rounds: int, direction: str = "upper") -> Instance:
    """The witness driving k(W_P - W_FCFS) - (In - Out) towards +/- 2(k-1)L.

    Upward, FCFS dispatches k-1 jobs of service L in the victim's own phase while P has
    nothing in service; downward is the mirror image.
    """
    if k < 2 or rounds_exponent(k, limit) < 0:
        raise ValueError("the cascade needs k >= 2 and L a power of k")
    arrival: list[int] = []
    service: list[int] = []
    priority: list[int] = []
    _cascade(arrival, service, priority, k, limit, rounds, bigs_first=direction == "upper")
    end = rounds * limit
    if direction == "upper":
        for _ in range(k - 1):
            arrival.append(end)
            service.append(limit)
            priority.append(2 * rounds)
        victim = len(arrival)
        arrival.append(end)
        service.append(limit)
        priority.append(2 * rounds + 2)
        for _ in range(2 * k * limit + 1):
            arrival.append(end)
            service.append(1)
            priority.append(2 * rounds + 1)
    elif direction == "lower":
        filler = cascade_leftover(k, limit, rounds)
        arrival.append(end)
        service.append(filler)
        priority.append(2 * rounds + 2)
        victim = len(arrival)
        arrival.append(end)
        service.append(limit - 1)
        priority.append(2 * rounds + 1)
        for _ in range(k - 1):
            arrival.append(end)
            service.append(limit)
            priority.append(2 * rounds)
    else:
        raise ValueError("direction must be 'upper' or 'lower'")
    return Instance(
        np.array(arrival, np.int64),
        np.array(service, np.int64),
        np.array(priority, np.float64),
        victim,
    )


def rounds_exponent(k: int, limit: int) -> int:
    """m with L = k**m, or -1 when L is not a power of k."""
    m, value = 0, 1
    while value < limit:
        value *= k
        m += 1
    return m if value == limit else -1


@dataclass(frozen=True)
class WrapperInstance(Instance):
    """A wrapper witness also fixes the budget the guard must be run with."""

    budget: int = 0
    leftover: int = 0


def wrapper_family(k: int, limit: int, rounds: int) -> WrapperInstance:
    """The witness driving c(k) = (k excess - B)/L towards 3k-2.

    After the cascade, a job of service f frees all k servers at once, the next batch
    leaves over[victim] one unit short of the budget, and the guard fires only one full
    round of service later, so both slacks of the guard bound saturate on one instance.
    """
    if limit != k**rounds:
        raise ValueError("the cascade needs L = k**m")
    arrival: list[int] = []
    service: list[int] = []
    priority: list[int] = []
    _cascade(arrival, service, priority, k, limit, rounds, bigs_first=True)
    end = rounds * limit
    leftover = cascade_leftover(k, limit, rounds)
    for _ in range(k - 1):  # new bigs, ranked below the victim
        arrival.append(end)
        service.append(limit)
        priority.append(2 * rounds + 1)
    victim = len(arrival)
    arrival.append(end)  # the victim, which the base never takes
    service.append(limit)
    priority.append(2 * rounds + 3)
    arrival.append(end)  # sync: frees every server at once
    service.append(leftover)
    priority.append(2 * rounds)
    arrival.append(end)  # pre
    service.append(limit)
    priority.append(2 * rounds + 1)
    for _ in range(k):  # finals
        arrival.append(end)
        service.append(limit)
        priority.append(2 * rounds + 2)
    return WrapperInstance(
        np.array(arrival, np.int64),
        np.array(service, np.int64),
        np.array(priority, np.float64),
        victim,
        budget=leftover + limit + 1,
        leftover=leftover,
    )
