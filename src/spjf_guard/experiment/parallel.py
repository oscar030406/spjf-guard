"""Running many policies over one large trace, in a few worker processes.

A trace of 17.6 million jobs is too big to hand to every worker as an argument, so one
cell is written to `.npy` files once and each worker memory-maps them at start-up.  Every
worker runs its numba kernel on one thread; the pool size is the whole thread budget.
"""

from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

_ARRAYS: dict[str, np.ndarray] = {}
_TRACE = None

ARRAY_NAMES = ("arrival_us", "service_us", "in_window", "is_heavy", "week", "fcfs_wait_us")


def write_cell(directory: Path, trace, labels, fcfs_wait_us, scores: dict) -> Path:
    """Materialise one cell so that workers can map it instead of receiving it."""
    directory.mkdir(parents=True, exist_ok=True)
    np.save(directory / "arrival_us.npy", trace.arrival_us)
    np.save(directory / "service_us.npy", trace.service_us)
    np.save(directory / "in_window.npy", labels["in_window"])
    np.save(directory / "is_heavy.npy", labels["is_heavy"])
    np.save(directory / "fcfs_wait_us.npy", fcfs_wait_us)
    if "week" in labels:
        np.save(directory / "week.npy", labels["week"])
    for name, values in scores.items():
        np.save(directory / f"score_{name}.npy", np.asarray(values, np.float64))
    return directory


def _initialise(directory: str, limit_s: float, score_names: tuple[str, ...]) -> None:
    """Runs once per worker: map the cell and rebuild the trace object."""
    from spjf_guard.sim import Trace

    for variable in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS"):
        os.environ[variable] = "1"
    path = Path(directory)
    for name in ARRAY_NAMES:
        candidate = path / f"{name}.npy"
        if candidate.is_file():
            _ARRAYS[name] = np.load(candidate, mmap_mode="r")
    scores = {name: np.load(path / f"score_{name}.npy", mmap_mode="r") for name in score_names}
    global _TRACE
    _TRACE = Trace(
        np.ascontiguousarray(_ARRAYS["arrival_us"]),
        np.ascontiguousarray(_ARRAYS["service_us"]),
        {k: np.ascontiguousarray(v) for k, v in scores.items()},
        limit_s,
    )


def _bootstrap(wait_us, week, multiplicities, in_window):
    """Replicates of the two reported statistics, computed where the waits already are.

    Returning replicates rather than 17.6 million waits is what keeps the parent's
    memory flat while the differences stay paired: every policy uses the same draw.
    """
    from spjf_guard.experiment.bootstrap import resampled_mean, resampled_quantile
    from spjf_guard.sim.policy import MICROS

    wait_s = wait_us / MICROS
    return {
        "mean": resampled_mean(wait_s, week, multiplicities),
        "p99_dl": resampled_quantile(wait_s[in_window], week[in_window], multiplicities, 0.99),
    }


def _bound_check(out, reference, policy, servers, limit_s) -> dict:
    """What the per-job assertion checked, and how much of the allowance was used.

    `used / allowed` is the worst job's excess over FCFS divided by the excess the bound
    permits, so 1.0 would mean a job sat exactly on its bound and above 1.0 would be a
    violation the assertion has already refused to let through.
    """
    from spjf_guard.sim.bounds import guard_upper_bound
    from spjf_guard.sim.policy import MICROS

    bound = guard_upper_bound(reference, policy, servers, limit_s)
    allowed = bound - reference / MICROS
    used = (out.wait_us - reference) / MICROS
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(allowed > 0, used / allowed, 0.0)
    return {
        "jobs_checked": int(len(used)),
        "worst_excess_s": float(used.max()),
        "allowed_s": float(allowed.max()),
        "used_over_allowed": float(np.nanmax(ratio)),
        "violations": int((used > allowed + 1e-9).sum()),
    }


def _run(task: dict):
    """One policy on the mapped cell: simulate, assert its bound, summarise, resample."""
    from spjf_guard.experiment.metrics import summarise
    from spjf_guard.sim import simulate
    from spjf_guard.sim.bounds import assert_per_job_bounds, residual_summary

    policy = task["policy"]
    servers = task["servers"]
    assert _TRACE is not None, "the worker was not initialised"
    out = simulate(_TRACE, policy, servers, window=task["window"])
    reference = np.asarray(_ARRAYS["fcfs_wait_us"])
    if policy.wrapper != "none" and task["assert_bounds"]:
        assert_per_job_bounds(out, reference, policy, servers, task["limit_s"])
    in_window = np.asarray(_ARRAYS["in_window"])
    stats = summarise(out, reference, in_window, np.asarray(_ARRAYS["is_heavy"]))
    payload: dict = {"summary": stats}
    if policy.wrapper != "none":
        payload["bound"] = _bound_check(out, reference, policy, servers, task["limit_s"])
    if task.get("residuals"):
        payload["residuals"] = residual_summary(
            out.wait_us,
            reference,
            _TRACE.service_us,
            out.dispatch_order,
            servers,
            task["limit_s"],
            start_us=out.start_us,
        )
    if task.get("bootstrap") is not None:
        payload["replicates"] = _bootstrap(
            out.wait_us, np.asarray(_ARRAYS["week"]), task["bootstrap"], in_window
        )
    if task.get("keep_waits"):
        payload["wait_us"] = out.wait_us
    return task["tag"], payload


def map_policies(directory: Path, tasks, limit_s: float, score_names, workers: int = 4):
    """Run every task over one cell and yield (tag, payload) as they finish."""
    with ProcessPoolExecutor(
        max_workers=min(workers, max(len(tasks), 1)),
        initializer=_initialise,
        initargs=(str(directory), limit_s, tuple(score_names)),
    ) as pool:
        yield from pool.map(_run, tasks)
