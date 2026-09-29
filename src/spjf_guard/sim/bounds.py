"""The two per-job statements of the theory, evaluated job by job on a realised run.

    identity   | k (W_P[i] - W_FCFS[i]) - (In_i - Out_i) |  <=  2(k-1) L
    guard      W[i] < W_FCFS[i] + B_max/k + (3 - 2/k) L
               (1 - eta) W[i] <= W_FCFS[i] + B_0/k + (3 - 2/k) L
    skip       W[i] <= W_FCFS[i] + (N + 2k - 2) L / k

In_i is the work of the higher-ranked jobs dispatched before i, Out_i the work of the
lower-ranked jobs dispatched after it; both follow the dispatch sequence, which is the
convention the guard can meter.  Everything here is int64 microseconds.
"""

from __future__ import annotations

import numpy as np
from numba import njit

from spjf_guard.sim.policy import MICROS, WRAP_SKIP, WRAP_WORK, Policy


@njit(cache=True)
def _in_out_sweep(service_us, order):
    """One walk of the dispatch sequence with a Fenwick tree over arrival rank.

    When i is dispatched the tree holds exactly the jobs dispatched before it, so
    In_i = total - prefix(i) and Out_i = prefix_static(i) - prefix(i).
    """
    n = service_us.shape[0]
    tree = np.zeros(n + 1, np.int64)
    static = np.zeros(n + 1, np.int64)
    for j in range(n):
        static[j + 1] = static[j] + service_us[j]
    work_in = np.empty(n, np.int64)
    work_out = np.empty(n, np.int64)
    total = 0
    for p in range(n):
        i = order[p]
        s = 0
        q = i + 1
        while q > 0:
            s += tree[q]
            q -= q & -q
        # i itself is not in the tree yet, so `s` is the dispatched work of ranks below i
        work_in[i] = total - s
        work_out[i] = static[i] - s
        total += service_us[i]
        q = i + 1
        while q <= n:
            tree[q] += service_us[i]
            q += q & -q
    return work_in, work_out


def in_out(service_us: np.ndarray, dispatch_order: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(In, Out) in microseconds, by the O(n log n) sweep."""
    return _in_out_sweep(
        np.ascontiguousarray(service_us, np.int64),
        np.ascontiguousarray(dispatch_order, np.int64),
    )


@njit(cache=True)
def _same_phase_sweep(service_us, order, start_us):
    """The part of In_i contributed by jobs dispatched in i's own phase.

    A phase is a maximal run of dispatches at one instant of the clock.  A job dispatched
    in i's phase before i executes nothing while i waits, so its work enters In_i and the
    new-work term alike and cancels inside the proof of the identity.  A second Fenwick
    tree is filled over the phase and unwound at its end, so the whole walk stays
    O(n log n) and exact in int64.
    """
    n = service_us.shape[0]
    tree = np.zeros(n + 1, np.int64)
    same = np.zeros(n, np.int64)
    p = 0
    n_phases = 0
    while p < n:
        instant = start_us[order[p]]
        end = p
        while end < n and start_us[order[end]] == instant:
            end += 1
        n_phases += 1
        total = 0
        for r in range(p, end):
            i = order[r]
            s = 0
            q = i + 1
            while q > 0:
                s += tree[q]
                q -= q & -q
            same[i] = total - s
            total += service_us[i]
            q = i + 1
            while q <= n:
                tree[q] += service_us[i]
                q += q & -q
        for r in range(p, end):  # unwind, so the tree is all zeros for the next phase
            i = order[r]
            q = i + 1
            while q <= n:
                tree[q] -= service_us[i]
                q += q & -q
        p = end
    return same, n_phases


def in_same_phase(
    service_us: np.ndarray, dispatch_order: np.ndarray, start_us: np.ndarray
) -> tuple[np.ndarray, int]:
    """(same-phase part of In, number of dispatch phases), in microseconds."""
    return _same_phase_sweep(
        np.ascontiguousarray(service_us, np.int64),
        np.ascontiguousarray(dispatch_order, np.int64),
        np.ascontiguousarray(start_us, np.int64),
    )


def in_same_phase_quadratic(service_us: np.ndarray, dispatch_index: np.ndarray, start_us):
    """The definition written out; the sweep is checked against it on small instances."""
    n = len(service_us)
    same = np.zeros(n, np.int64)
    for i in range(n):
        for j in range(n):
            if j > i and dispatch_index[j] < dispatch_index[i] and start_us[j] == start_us[i]:
                same[i] += service_us[j]
    return same


def in_out_quadratic(service_us: np.ndarray, dispatch_index: np.ndarray):
    """The definition written out as a double loop; the sweep is checked against it."""
    n = len(service_us)
    work_in = np.zeros(n, np.int64)
    work_out = np.zeros(n, np.int64)
    for i in range(n):
        for j in range(n):
            if j > i and dispatch_index[j] < dispatch_index[i]:
                work_in[i] += service_us[j]
            elif j < i and dispatch_index[i] < dispatch_index[j]:
                work_out[i] += service_us[j]
    return work_in, work_out


def identity_residual(
    wait_us: np.ndarray,
    fcfs_wait_us: np.ndarray,
    work_in: np.ndarray,
    work_out: np.ndarray,
    k: int,
) -> np.ndarray:
    """k (W_P - W_FCFS) - (In - Out), per job, in microseconds.  Theorem 1 bounds its
    absolute value by 2(k-1)L."""
    return k * (wait_us - fcfs_wait_us) - (work_in - work_out)


def identity_slack_us(k: int, limit_s: float) -> int:
    return int(round(2 * (k - 1) * limit_s * MICROS))


def skip_upper_bound(
    fcfs_wait_us: np.ndarray, k: int, skip_count: int, limit_s: float
) -> np.ndarray:
    """W <= W_FCFS + (N + 2k - 2) L / k, the dispatch-charged count bound, in seconds."""
    return fcfs_wait_us / MICROS + limit_s * (skip_count + 2 * k - 2) / k


def guard_upper_bound(
    fcfs_wait_us: np.ndarray, policy: Policy, k: int, limit_s: float
) -> np.ndarray:
    """The smaller of the two guard bounds, per job, in seconds.

    Additive:       W_FCFS + B_max/k + (3 - 2/k) L
    Multiplicative: (W_FCFS + B_0/k + (3 - 2/k) L) / (1 - eta)

    The multiplicative form is stated for the constant part of the budget, so it applies
    only when that part is the same for every job.  With a queue-length term the constant
    part is B_0 + gam w_q, which is bounded by the cap and nothing tighter, so only the
    additive form is claimed.  That is the form the promise G is defined from.
    """
    if policy.wrapper == WRAP_SKIP:
        return skip_upper_bound(fcfs_wait_us, k, policy.skip_count, limit_s)
    if policy.wrapper != WRAP_WORK:
        raise ValueError(f"{policy.name} carries no guard bound")
    wf = fcfs_wait_us / MICROS
    const = (3.0 - 2.0 / k) * limit_s
    eta = policy.eta_k / k
    if eta >= 1.0:
        raise ValueError("eta must be below 1")
    if policy.gam_us > 0:
        if policy.bmax_us <= 0:
            raise ValueError(
                f"{policy.name}: a queue-length term without a cap carries no bound"
            )
        return wf + policy.bmax_us / MICROS / k + const
    bound = (wf + policy.b0_us / MICROS / k + const) / (1.0 - eta)
    if policy.bmax_us > 0:
        bound = np.minimum(bound, wf + policy.bmax_us / MICROS / k + const)
    return bound


def assert_per_job_bounds(
    results,
    fcfs_wait_us: np.ndarray,
    policy: Policy,
    k: int,
    limit_s: float,
    tolerance_s: float = 0.0,
) -> int:
    """Assert the guard bound for every job separately, inside the run.

    Returns the number of jobs checked.  The comparison is exact by default: both sides
    are computed from integer microseconds.
    """
    bound = guard_upper_bound(fcfs_wait_us, policy, k, limit_s)
    wait = results.wait_us / MICROS
    bad = np.flatnonzero(wait > bound + tolerance_s)
    if bad.size:
        worst = int(bad[np.argmax(wait[bad] - bound[bad])])
        raise AssertionError(
            f"{policy.name}: job {worst} waits {wait[worst]:.6f} s against a bound of "
            f"{bound[worst]:.6f} s ({bad.size} violations of {len(wait)} jobs)"
        )
    return len(wait)


def residual_summary(
    wait_us: np.ndarray,
    fcfs_wait_us: np.ndarray,
    service_us: np.ndarray,
    dispatch_order: np.ndarray,
    k: int,
    limit_s: float,
    start_us: np.ndarray | None = None,
) -> dict:
    """What the identity explains on one realised run, as the paper reports it.

    `max|D| / 2(k-1)L` says how much of the slack the run uses; `share of D = 0` says how
    often the identity is exact; `R2` says how much of the per-job excess over FCFS is
    explained by (In - Out)/k alone.  Everything is computed from the same integer
    microseconds the schedule was decided in.

    With `start_us` the same-phase part of In is measured too.  It matters because the
    degenerate instances that drive the lower bound of the identity are built entirely
    out of it: a job dispatched in i's own phase before i never runs while i waits, so its
    work is bookkeeping that cancels in the proof.  A small share says the trace does not
    live near those instances.
    """
    work_in, work_out = in_out(service_us, dispatch_order)
    residual = identity_residual(wait_us, fcfs_wait_us, work_in, work_out, k)
    bound = identity_slack_us(k, limit_s)
    excess = (wait_us - fcfs_wait_us) / MICROS
    predicted = (work_in - work_out) / (MICROS * k)
    centred = excess - excess.mean()
    ss_tot = float(np.square(centred).sum())
    ss_res = float(np.square(excess - predicted).sum())
    phases: dict = {}
    if start_us is not None:
        same, n_phases = in_same_phase(service_us, dispatch_order, start_us)
        positive = work_in > 0
        total_in = int(work_in.sum())
        phases = {
            "n_phases": int(n_phases),
            "frac_in_positive": float(positive.mean()),
            "samephase_share_sum_in": (float(same.sum()) / total_in) if total_in else 0.0,
            "frac_in_all_samephase": (
                float((positive & (same == work_in)).sum()) / int(positive.sum())
                if positive.any()
                else 0.0
            ),
            "sum_in_s": float(work_in.sum()) / MICROS,
            "sum_out_s": float(work_out.sum()) / MICROS,
        }
    return {
        "n_jobs": int(len(wait_us)),
        "max_abs_residual_L": float(np.abs(residual).max()) / (limit_s * MICROS),
        "bound_L": 2.0 * (k - 1),
        "ratio_to_bound": (float(np.abs(residual).max()) / bound) if bound else 0.0,
        "share_residual_zero": float((residual == 0).mean()),
        "mean_abs_residual_L": float(np.abs(residual).mean()) / (limit_s * MICROS),
        "r2_net_over_k": 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan"),
        "max_abs_error_s": float(np.abs(excess - predicted).max()),
        "mean_excess_s": float(excess.mean()),
        "max_excess_s": float(excess.max()),
        "violations": int((np.abs(residual) > bound + 2 * k).sum()),
        **phases,
    }
