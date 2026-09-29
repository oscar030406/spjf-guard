"""`simulate(trace, policy, k) -> JobResults`, the whole interface of the simulator."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from spjf_guard.sim.kernel import (
    MODE_FCFS,
    MODE_GUARD,
    MODE_SCORE,
    MODE_SKIP,
    simulate_kernel,
)
from spjf_guard.sim.policy import (
    BASE_FCFS,
    MICROS,
    TRUE_SIZE,
    WRAP_SKIP,
    WRAP_WORK,
    Policy,
    eta_fraction,
    seconds_to_micros,
)

DEFAULT_WINDOW = 1 << 22
"""Segment-tree window in ranks; the live span of waiting ranks must fit inside it."""


@dataclass(frozen=True)
class Trace:
    """Arrivals and true service times in exact integer microseconds, in rank order.

    `scores` holds one array per named ranking score; the key `true_size` is answered
    from the service times themselves and need not be supplied.
    """

    arrival_us: np.ndarray
    service_us: np.ndarray
    scores: dict[str, np.ndarray] = field(default_factory=dict)
    limit_s: float = 60.0

    def __post_init__(self) -> None:
        if self.arrival_us.dtype != np.int64 or self.service_us.dtype != np.int64:
            raise TypeError("arrival_us and service_us must be int64 microseconds")
        if len(self.arrival_us) != len(self.service_us):
            raise ValueError("arrival and service arrays differ in length")
        if np.any(np.diff(self.arrival_us) < 0):
            raise ValueError("jobs must be given in rank order (arrival, input index)")
        if np.any(self.service_us <= 0):
            raise ValueError("service times must be positive")
        if np.any(self.service_us > round(self.limit_s * 1_000_000)):
            raise ValueError(
                f"a service time exceeds the limit {self.limit_s} s; the bound the guard "
                "asserts assumes executed work is capped at the limit"
            )

    def __len__(self) -> int:
        return len(self.arrival_us)

    @classmethod
    def from_seconds(cls, arrival_s, service_s, scores=None, limit_s: float = 60.0) -> Trace:
        """Quantise a trace given in float seconds to whole microseconds."""
        a = np.rint(np.asarray(arrival_s, np.float64) * MICROS).astype(np.int64)
        s = np.rint(np.asarray(service_s, np.float64) * MICROS).astype(np.int64)
        return cls(a, s, dict(scores or {}), limit_s)

    def score_for(self, key: str) -> np.ndarray:
        if key == TRUE_SIZE:
            return self.service_us.astype(np.float64)
        try:
            return np.ascontiguousarray(self.scores[key], np.float64)
        except KeyError as exc:
            raise KeyError(
                f"the trace carries no score {key!r}; it has {sorted(self.scores)}"
            ) from exc


@dataclass(frozen=True)
class JobResults:
    """Per-job outcome of one policy on one trace, plus the dispatch-level counters."""

    policy: str
    servers: int
    wait_us: np.ndarray
    start_us: np.ndarray
    dispatch_index: np.ndarray
    n_dispatch: int
    n_forced: int
    queue_weighted_dispatch: int
    queue_weighted_forced: int

    @property
    def wait_s(self) -> np.ndarray:
        return self.wait_us / MICROS

    @property
    def fired_fraction(self) -> float:
        """Share of dispatch epochs at which the wrapper overrode the base policy."""
        return self.n_forced / max(self.n_dispatch, 1)

    @property
    def fired_fraction_queue_weighted(self) -> float:
        return self.queue_weighted_forced / max(self.queue_weighted_dispatch, 1)

    @property
    def dispatch_order(self) -> np.ndarray:
        """order[p] = the job dispatched at sequence position p."""
        order = np.empty_like(self.dispatch_index)
        order[self.dispatch_index] = np.arange(len(self.dispatch_index), dtype=np.int64)
        return order


def _mode_of(policy: Policy) -> int:
    if policy.wrapper == WRAP_WORK:
        return MODE_GUARD
    if policy.wrapper == WRAP_SKIP:
        return MODE_SKIP
    if policy.base == BASE_FCFS:
        return MODE_FCFS
    return MODE_SCORE


def simulate(trace: Trace, policy: Policy, k: int, window: int = DEFAULT_WINDOW) -> JobResults:
    """Run `policy` on `trace` with `k` servers and return the per-job outcome.

    The clock, the budgets and the accounting are exact int64 microseconds, so no
    floating-point comparison decides a dispatch.  Ties in the base score are broken
    towards the smaller rank.
    """
    if k < 1:
        raise ValueError("k must be at least 1")
    mode = _mode_of(policy)
    if mode == MODE_FCFS:
        score = np.zeros(len(trace), np.float64)
    else:
        score = trace.score_for(policy.score_key)
        if len(score) != len(trace):
            raise ValueError("score array does not match the trace length")
        if policy.age_credit_per_s > 0.0:
            age_origin = trace.arrival_us[0]
            arrival_s = (trace.arrival_us - age_origin) / MICROS
            score = score + policy.age_credit_per_s * arrival_s
    if policy.wrapper == WRAP_WORK and policy.b0_us > policy.bmax_us > 0:
        raise ValueError("B0 must not exceed B_max")
    en, ed = eta_fraction(policy.eta_k)
    out = simulate_kernel(
        np.ascontiguousarray(trace.arrival_us),
        np.ascontiguousarray(trace.service_us),
        np.ascontiguousarray(score),
        int(k),
        mode,
        int(policy.b0_us),
        int(en),
        int(ed),
        int(policy.bmax_us),
        int(policy.skip_count),
        int(window),
        int(policy.gam_us),
    )
    (
        wait_us,
        dispatch_index,
        start_us,
        n_disp,
        n_forced,
        qw_total,
        qw_forced,
        _n_rebuild,
        _max_span,
        err,
    ) = out
    if err:
        raise RuntimeError(
            f"{policy.name}: the span of waiting ranks outgrew the {window}-rank window; "
            "raise `window`"
        )
    return JobResults(
        policy=policy.name,
        servers=int(k),
        wait_us=wait_us,
        start_us=start_us,
        dispatch_index=dispatch_index,
        n_dispatch=int(n_disp),
        n_forced=int(n_forced),
        queue_weighted_dispatch=int(qw_total),
        queue_weighted_forced=int(qw_forced),
    )


def limit_micros(trace: Trace) -> int:
    return seconds_to_micros(trace.limit_s)
