"""The scheduling simulator: one small interface over a deep kernel.

    simulate(trace, policy, k) -> JobResults

`trace` carries arrivals and true service times in exact integer microseconds; `policy`
names a base ordering and, optionally, the wrapper that bounds overtaken work.  Nothing
in this package reads a data file or a configuration.
"""

from spjf_guard.sim.bounds import (
    guard_upper_bound,
    identity_residual,
    in_out,
    skip_upper_bound,
)
from spjf_guard.sim.policy import (
    MICROS,
    Policy,
    bmax_for_promise,
    fixed,
    guard,
    seconds_to_micros,
    skip_count_for_promise,
    spjf,
)
from spjf_guard.sim.runner import JobResults, Trace, simulate

__all__ = [
    "MICROS",
    "JobResults",
    "Policy",
    "Trace",
    "bmax_for_promise",
    "fixed",
    "guard",
    "guard_upper_bound",
    "identity_residual",
    "in_out",
    "seconds_to_micros",
    "simulate",
    "skip_count_for_promise",
    "skip_upper_bound",
    "spjf",
]
