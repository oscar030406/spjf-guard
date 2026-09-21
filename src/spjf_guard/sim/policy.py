"""Policy names and the arithmetic that turns a service promise into a budget.

Every time and every budget in this package is an exact integer number of
microseconds.  Seconds appear only at the boundary, in `seconds_to_micros`.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import floor

MICROS = 1_000_000
"""Microseconds per second: the unit of the simulator's clock and of every budget."""

_ETA_DEN = 720720
"""Denominator carrying 2..12 and 16 as factors, so the grid values of eta*k are exact."""

BASE_FCFS = "fcfs"
BASE_SCORE = "score"
TRUE_SIZE = "true_size"
"""Score key the trace answers with the true service times, for the SJF reference."""

WRAP_NONE = "none"
WRAP_WORK = "work"
WRAP_SKIP = "skip"


def seconds_to_micros(x: float) -> int:
    """Round seconds to whole microseconds, half away from zero, as the kernel does."""
    return int(round(x * MICROS))


def eta_fraction(eta_k: float, den: int = _ETA_DEN) -> tuple[int, int]:
    """eta*k as an exact fraction en/ed in lowest terms."""
    if eta_k == 0.0:
        return 0, 1
    num = int(round(eta_k * den))
    a, b = num, den
    while b:
        a, b = b, a % b
    return num // a, den // a


def bmax_for_promise(promise_s: float, k: int, limit_s: float) -> float:
    """B_max = k (G - (3 - 2/k) L), the inversion of the guard bound.

    Uses no data.  Raises when the promise is below the floor of order L that no
    policy learning service times at completion can undercut.
    """
    floor_s = (3.0 - 2.0 / k) * limit_s
    if promise_s <= floor_s:
        raise ValueError(
            f"promise G = {promise_s} s is not above the floor (3 - 2/k)L = {floor_s} s "
            f"at k = {k}, L = {limit_s} s; no positive budget is admissible"
        )
    return float(k) * (promise_s - floor_s)


def skip_count_for_promise(promise_s: float, k: int, limit_s: float) -> int:
    """Largest dispatch-charged skip count N with W <= W_FCFS + (N + 2k - 2) L / k <= G."""
    n = int(floor(promise_s * k / limit_s - (2 * k - 2) + 1e-9))
    if n < 1:
        raise ValueError(f"promise G = {promise_s} s admits no positive skip count at k = {k}")
    assert limit_s * (n + 2 * k - 2) / k <= promise_s + 1e-9
    return n


@dataclass(frozen=True)
class Policy:
    """A base ordering, optionally wrapped by a rule that bounds overtaken work.

    `name` is the label the paper's tables carry.  `base` is FCFS or an arbitrary
    score supplied at simulation time; the wrapper never inspects the base.
    """

    name: str
    base: str = BASE_FCFS
    wrapper: str = WRAP_NONE
    score_key: str = ""
    b0_us: int = 0
    eta_k: float = 0.0
    bmax_us: int = 0
    skip_count: int = 0
    gam_us: int = 0
    age_credit_per_s: float = 0.0
    """Budget added per job waiting when q arrived.  The guarantee does not depend on it:
    the shape of the budget under the cap is a design freedom, the cap is not."""

    def __post_init__(self) -> None:
        if self.base not in (BASE_FCFS, BASE_SCORE):
            raise ValueError(f"unknown base policy {self.base!r}")
        if self.wrapper not in (WRAP_NONE, WRAP_WORK, WRAP_SKIP):
            raise ValueError(f"unknown wrapper {self.wrapper!r}")
        if self.wrapper == WRAP_WORK and not (0.0 <= self.eta_k):
            raise ValueError("eta*k must be >= 0")
        if self.wrapper == WRAP_WORK and (self.b0_us < 0 or self.gam_us < 0):
            raise ValueError("B0 and gamma must be >= 0, so that the budget is never negative")
        if self.wrapper == WRAP_WORK and self.bmax_us > 0 and self.b0_us > self.bmax_us:
            raise ValueError(
                f"the constant part of the budget ({self.b0_us} us) is above the cap "
                f"({self.bmax_us} us); the cap is what the promise rests on"
            )
        if self.wrapper == WRAP_SKIP and self.skip_count < 0:
            raise ValueError("skip count must be >= 0")
        if self.age_credit_per_s < 0.0:
            raise ValueError("the linear age credit must be >= 0")

    @property
    def needs_score(self) -> bool:
        return self.base == BASE_SCORE

    @property
    def eta(self) -> float:
        raise AttributeError("the policy stores eta*k; divide by k at the call site")


def fcfs() -> Policy:
    """The deployed baseline and the reference the guarantee is stated against."""
    return Policy(name="FCFS", base=BASE_FCFS, wrapper=WRAP_NONE)


def spjf(score_key: str, name: str = "SPJF") -> Policy:
    """Rank the queue by the named score of the trace; no wrapper."""
    return Policy(name=name, base=BASE_SCORE, wrapper=WRAP_NONE, score_key=score_key)


def aging(score_key: str, credit_per_s: float, name: str = "Aging") -> Policy:
    """Rank by predicted cost minus a linear credit for time already spent waiting.

    At a dispatch time t, ``score_i - beta * (t - a_i)`` has the same ordering as
    ``score_i + beta * a_i`` because ``-beta*t`` is common to the whole queue.  The
    runner applies that static transform, so the existing exact kernel needs no new
    dynamic data structure.  This heuristic carries no per-job guarantee.
    """
    return Policy(
        name=name,
        base=BASE_SCORE,
        wrapper=WRAP_NONE,
        score_key=score_key,
        age_credit_per_s=float(credit_per_s),
    )


def guard(
    promise_s: float,
    k: int,
    limit_s: float,
    b0_s: float,
    eta: float,
    score_key: str,
    name: str | None = None,
    gam_s: float = 0.0,
) -> Policy:
    """One mechanism, three shapes of the same budget:

        budget(q, t) = min(B0 + gam * (jobs waiting when q arrived) + eta k (t - a_q), B_max)

    `eta = gam = 0` is the constant budget, `gam = 0` the capped relative one, and both
    positive the queue-length one.  The promise rests on `B_max` alone, so all three
    carry the same guarantee at the same G.
    """
    bmax_s = bmax_for_promise(promise_s, k, limit_s)
    return Policy(
        name=name or f"Guard({promise_s:g})",
        base=BASE_SCORE,
        wrapper=WRAP_WORK,
        score_key=score_key,
        b0_us=seconds_to_micros(min(b0_s, bmax_s)),
        eta_k=eta * k,
        bmax_us=seconds_to_micros(bmax_s),
        gam_us=seconds_to_micros(max(gam_s, 0.0)),
    )


def fixed(
    promise_s: float,
    k: int,
    limit_s: float,
    score_key: str,
    b0_s: float | None = None,
    name: str | None = None,
) -> Policy:
    """Constant budget (eta = 0).  With b0_s omitted this is B0 = B_max, the equal-promise
    comparator; with b0_s given it is the constant budget of that size, whose promise is
    tighter than G."""
    bmax_s = bmax_for_promise(promise_s, k, limit_s)
    b0 = bmax_s if b0_s is None else min(b0_s, bmax_s)
    return Policy(
        name=name or f"Fixed({promise_s:g})",
        base=BASE_SCORE,
        wrapper=WRAP_WORK,
        score_key=score_key,
        b0_us=seconds_to_micros(b0),
        eta_k=0.0,
        bmax_us=seconds_to_micros(bmax_s),
    )


def skip(
    promise_s: float, k: int, limit_s: float, score_key: str, name: str | None = None
) -> Policy:
    """Position-count guard, the count charged when an overtaker is dispatched."""
    return Policy(
        name=name or f"Skip({promise_s:g})",
        base=BASE_SCORE,
        wrapper=WRAP_SKIP,
        score_key=score_key,
        skip_count=skip_count_for_promise(promise_s, k, limit_s),
    )


def sjf() -> Policy:
    """Sorts by true service time.  Undeployable reference, not an optimum."""
    return Policy(name="SJF", base=BASE_SCORE, wrapper=WRAP_NONE, score_key=TRUE_SIZE)
