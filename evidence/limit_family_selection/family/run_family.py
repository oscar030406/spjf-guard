"""The Skip, Timeout, Aging and Block grids of #31 through run_online_visibility (rov).

    python evidence/limit_family_selection/family/run_family.py --pool validation \
        --variants online --policies "Skip(300),Skip(n=8),Timeout(theta=120)" \
        --reps 0 --levels 0 --workers 1 --resume \
        --out-dir outputs/family_selection_<tag>/validation/<job>
    python evidence/limit_family_selection/family/run_family.py --pool validation \
        --variants fixed_point --policies "Block(32)" ... (Block runs on the fixed point)

rov is unchanged; three of its names are replaced, in the parent and, because spawn reruns
this module as __mp_main__, in every worker:

  _suite        Skip(n=m)   the package's dispatch-charged skip with N = floor(m*k/4);
                Aging(c=x)  linear aging at credit x on spjf_e (rov's --aging-grid policy);
                Block(W)    score order inside blocks of W ranks (evidence/skipc_block_online/
                            block_kernel.run_block, imported, cache=False);
                every other name (Skip(G), Timeout(G), Timeout(theta=t)) goes to rov's _suite.
  _refine       Block(W) only: refine_policy_online with the Block kernel as the simulator of
                every pass, as evidence/skipc_block_online/skipc_block_online.py does; the
                final scores fed back to the kernel must reproduce the online wait, start and
                dispatch order.  Every other policy goes to rov's _refine (online replay),
                followed by fixed_point.py's feed-back check.
  _check_bound  rov's own per-job assertion, then one printed line per bounded outcome.

The output directory must carry this code's tag (_setup.code_tag of _setup.py, fixed_point.py,
this file and block_kernel.py).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _setup  # noqa: E402,F401  (first: priority, bytecode, numba cache, sys.path)

import re  # noqa: E402
from argparse import Namespace  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402

from _setup import HERE, ROOT, code_tag, peak_gb, require_tag  # noqa: E402

sys.path.insert(0, str(ROOT / "evidence" / "skipc_block_online"))
from block_kernel import run_block  # noqa: E402

import fixed_point  # noqa: E402
import run_online_visibility as rov  # noqa: E402
from spjf_guard.experiment.online import refine_policy_online  # noqa: E402
from spjf_guard.sim.policy import BASE_SCORE, WRAP_SKIP, Policy, aging, spjf  # noqa: E402

STEM = "family_selection"
TAG = code_tag(HERE / "_setup.py", HERE / "fixed_point.py", Path(os.path.abspath(__file__)),
               ROOT / "evidence" / "skipc_block_online" / "block_kernel.py")
OWN = re.compile(r"Skip\(n=([0-9]+)\)|Aging\(c=([0-9.e-]+)\)|Block\(([0-9]+)\)")
ARRAYS = ("wait_us", "start_us", "dispatch_index")
_SUITE = rov._suite
_REFINE = fixed_point.wrap(rov._refine)
_CHECK = rov._check_bound


def _suite(cfg, args, servers):
    own, rest = [], []
    for name in args.policy_names:
        match = OWN.fullmatch(name)
        if match is None:
            rest.append(name)
        elif match.group(1):
            own.append(Policy(name=name, base=BASE_SCORE, wrapper=WRAP_SKIP, score_key="spjf_e",
                              skip_count=int(match.group(1)) * servers // 4))
        elif match.group(2):
            own.append(aging("spjf_e", float(match.group(2)), name))
        else:
            own.append(spjf("spjf_e", name))
    if not rest:
        return own
    delegated = _SUITE(cfg, Namespace(**{**vars(args), "policy_names": rest}), servers)
    if {p.name for p in delegated} != set(rest):
        raise SystemExit(f"rov does not know {sorted(set(rest) - {p.name for p in delegated})}")
    return own + delegated


def _refine(variant, trace, policy, servers, cfg, arrays, context, base, models):
    if not policy.name.startswith("Block("):
        return _REFINE(variant, trace, policy, servers, cfg, arrays, context, base, models)
    if variant != "fixed_point":
        raise SystemExit("Block(W) runs with --variants fixed_point")
    width = int(policy.name[6:-1])

    def run(score):
        return run_block(trace.arrival_us, trace.service_us, score, servers, width, policy.name)

    result = refine_policy_online(
        trace, policy, servers, int(cfg["run"]["segment_tree_window_ranks"]), arrays,
        context["online_index"], context["recomputer"], models, context["baseline_history"],
        base, variant, simulator=lambda current: run(next(iter(current.scores.values()))),
    )
    final = np.asarray(base, np.float64).copy()
    final[result.changed_jobs] = result.corrected_score
    fed = run(final)
    for field in ARRAYS:
        if not np.array_equal(getattr(fed, field), getattr(result.outcome, field)):
            raise AssertionError(f"{policy.name}: the final scores, fed back to the kernel, "
                                 f"do not reproduce the online {field}")
    commit, working = peak_gb()
    print(f"    {policy.name}: final scores fed back reproduce the online wait, start and "
          f"dispatch order after {len(result.passes)} passes; no promise, nothing asserted; "
          f"worker peak commit {commit:.2f} GB, working set {working:.2f} GB", flush=True)
    return result.initial_outcome, result, [vars(item) for item in result.passes]


def _check_bound(outcome, fcfs_wait, policy, servers, limit_s):
    _CHECK(outcome, fcfs_wait, policy, servers, limit_s)
    if policy.wrapper != "none" or policy.name.startswith("Timeout("):
        commit, working = peak_gb()
        print(f"    bound held: {outcome.policy} k = {servers}, {len(fcfs_wait):,} jobs; max "
              f"W - W_FCFS = {(outcome.wait_us - fcfs_wait).max() / 1e6:.6f} s; worker peak "
              f"commit {commit:.2f} GB, working set {working:.2f} GB", flush=True)


rov._suite = _suite
rov._refine = _refine
rov._check_bound = _check_bound


def main() -> int:
    require_tag(sys.argv[1:], STEM, TAG)
    sys.argv = ["run_online_visibility.py", *sys.argv[1:]]
    return rov.main()


if __name__ == "__main__":
    raise SystemExit(main())
