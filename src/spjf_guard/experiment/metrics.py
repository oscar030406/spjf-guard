"""The quantities every table in the paper is built from.

The primary metric is the 99th percentile of the wait among jobs arriving inside a
deadline window.  Everything else is secondary: the mean wait, the largest excess over
FCFS, the harm, the firing rate, the worst wait among heavy jobs, and the fraction of the
gap between FCFS and the SJF reference that a policy closes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from spjf_guard.sim.policy import MICROS

STARTS_IMMEDIATELY_S = 1.0
"""A job FCFS would have started within this many seconds is one FCFS does not delay."""


@dataclass(frozen=True)
class Summary:
    """One policy on one (trace, overlay, load) cell.  Every wait is in seconds."""

    policy: str
    servers: int
    n_jobs: int
    p99_dl_s: float
    mean_s: float
    p99_all_s: float
    max_excess_s: float
    harm_s: float
    max_heavy_s: float
    fired_fraction_queue_weighted: float

    def as_row(self) -> dict:
        return asdict(self)


def deadline_window_p99(wait_s: np.ndarray, in_window: np.ndarray) -> float:
    """The primary metric; nan when no job arrives inside a window."""
    if not in_window.any():
        return float("nan")
    return float(np.quantile(wait_s[in_window], 0.99))


def harm(excess_s: np.ndarray, fcfs_wait_s: np.ndarray) -> float:
    """Largest excess among the jobs FCFS would not have delayed at all."""
    undelayed = fcfs_wait_s <= STARTS_IMMEDIATELY_S
    if not undelayed.any():
        return float("nan")
    return float(excess_s[undelayed].max())


def summarise(
    results, fcfs_wait_us: np.ndarray, in_window: np.ndarray, is_heavy: np.ndarray
) -> Summary:
    wait_s = results.wait_us / MICROS
    fcfs_s = fcfs_wait_us / MICROS
    excess = wait_s - fcfs_s
    return Summary(
        policy=results.policy,
        servers=results.servers,
        n_jobs=len(wait_s),
        p99_dl_s=deadline_window_p99(wait_s, in_window),
        mean_s=float(wait_s.mean()),
        p99_all_s=float(np.quantile(wait_s, 0.99)),
        max_excess_s=float(excess.max()),
        harm_s=harm(excess, fcfs_s),
        max_heavy_s=float(wait_s[is_heavy].max()) if is_heavy.any() else float("nan"),
        fired_fraction_queue_weighted=results.fired_fraction_queue_weighted,
    )


def gap_closed(value: float, reference: float, target: float) -> float:
    """(FCFS - P) / (FCFS - SJF).  Unstable when the denominator is small; the caller
    prints the two absolute waits next to every ratio."""
    denominator = reference - target
    if denominator == 0.0:
        return float("nan")
    return (reference - value) / denominator


def reduction_percent(value: float, reference: float) -> float:
    if reference == 0.0:
        return float("nan")
    return 100.0 * (reference - value) / reference
