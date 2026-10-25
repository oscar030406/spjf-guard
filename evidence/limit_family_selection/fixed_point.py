"""The online replay is a fixed point: its final scores, fed to the static simulator, give it back.

wrap(refine) returns rov's _refine with one check added after every online replay: the base
score with the replay's corrected scores applied (each job's score at its admission) is fed to
spjf_guard.sim.simulate (rov's Timeout kernel for a Timeout policy), and the wait, start and
dispatch arrays must equal the replay's, value for value (wait and start for Timeout,
whose kernel numbers dispatches by start time).
"""

import numpy as np

import run_online_visibility as rov
from spjf_guard.sim import Trace, simulate


def wrap(refine):
    def checked(variant, trace, policy, servers, cfg, arrays, context, base, models):
        original, result, costs = refine(
            variant, trace, policy, servers, cfg, arrays, context, base, models
        )
        if variant != "online":
            return original, result, costs
        final = np.asarray(base, np.float64).copy()
        final[result.changed_jobs] = result.corrected_score
        fed_trace = Trace(trace.arrival_us, trace.service_us, {variant: final}, trace.limit_s)
        promise = rov._timeout_promise(policy, servers, cfg.limit_s)
        fed = (
            simulate(fed_trace, policy, servers,
                     window=int(cfg["run"]["segment_tree_window_ranks"]))
            if promise is None
            else rov._timeout_simulator(promise, servers, cfg.limit_s)(fed_trace)
        )
        fields = ("wait_us", "start_us") + (("dispatch_index",) if promise is None else ())
        for field in fields:
            if not np.array_equal(getattr(fed, field), getattr(result.outcome, field)):
                raise AssertionError(f"{policy.name}: the final scores, fed to the static "
                                     f"simulator, do not reproduce the online {field}")
        print(f"    fixed point: {policy.name} final scores ({len(result.changed_jobs):,} "
              f"rescored) fed to the static simulator reproduce the online "
              f"{'/'.join(fields)} of all {len(final):,} jobs", flush=True)
        return original, result, costs

    return checked
