"""The time limit L as a scheduling parameter (#28): rov on the primary pool at L = 45/60/90/120 s.

    python evidence/limit_family_selection/limit/run_limit.py \
        --config evidence/limit_family_selection/limit/main_L45.yaml \
        --policies "SPJF-E,Guard(300),Guard(600),Guard(1200),Fixed(300),Fixed(600),Fixed(1200),Skip(300),Skip(600),Skip(1200)" \
        --reps 0 --levels 2 --workers 1 --resume \
        --out-dir outputs/limit_sensitivity_<tag>/L45/o0_l2

scripts/run_online_visibility.py (rov) is unchanged and runs with --pool primary --variants
online; its `original` rows are the original-clock replays.  The config is configs/main.yaml
with only clock.limit_s changed (make_configs.py).  Four of rov's names are replaced, in the
parent and, because spawn reruns this module as __mp_main__, in every worker:

  Config.root      the repository root.  A config outside configs/ would otherwise resolve
                   its relative data paths against its own folder (config.py, Config.root).
  prepare_context  called with limit_s = 60 s.  The predictor, its features and the heavy
                   label stay the frozen L = 60 s pipeline: fit_frozen_m4_models caps the
                   training label at limit_s and then requires the refit model to return the
                   stored scores exactly, which a different L cannot do (terms before
                   2019-08-28 have runs over 60 s).
  load_overlay     the stored service times (already min(C, 60 s), experiment/overlay.py)
                   capped at L: unchanged at L >= 60, truncated at L = 45.  K, W, dl and hvt
                   are read from the stored overlay as they are.
  _suite           the policies named in --policies, built at the run's L.  Guard(G) and
                   Fixed(G) need G > (3 - 2/k)L, Skip(G) a count floor(Gk/L - (2k - 2)) >= 1;
                   a policy that fails this is FCFS (it may overtake nothing), is not
                   replayed (replay_online refuses an FCFS base) and is printed.
  _check_bound     rov's own per-job assertion at the run's L, then one printed line.
  _refine          rov's, followed by fixed_point.py's check that the final scores, fed to
                   the static simulator, reproduce the online waits and starts.

The output directory must carry this code's tag (_setup.code_tag of _setup.py,
fixed_point.py and this file).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _setup  # noqa: E402,F401  (first: priority, bytecode, numba cache, sys.path)

import copy  # noqa: E402
import re  # noqa: E402
from math import floor  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402

from _setup import HERE, ROOT, code_tag, peak_gb, require_tag  # noqa: E402

import fixed_point  # noqa: E402
import run_online_visibility as rov  # noqa: E402
from spjf_guard import config as cfgmod  # noqa: E402
from spjf_guard.sim import Trace  # noqa: E402
from spjf_guard.sim.policy import fixed, skip, spjf  # noqa: E402

PIPELINE_LIMIT_S = 60.0
STEM = "limit_sensitivity"
TAG = code_tag(HERE / "_setup.py", HERE / "fixed_point.py", Path(os.path.abspath(__file__)))
NAME = re.compile(r"SPJF-E|(Guard|Fixed|Skip)\(([0-9]+)\)")

cfgmod.Config.root = property(lambda self: ROOT)
_PREPARE = rov.prepare_context
_CHECK = rov._check_bound


def _prepare_context(cfg, args, pool_terms):
    raw = copy.deepcopy(cfg.raw)
    raw["clock"]["limit_s"] = PIPELINE_LIMIT_S
    return _PREPARE(cfgmod.Config(path=cfg.path, raw=raw), args, pool_terms)


def _load_overlay(path, level, score_map, limit_s):
    """reproduce.load_overlay with the service times capped at L; rov passes score_map {}."""
    with np.load(path) as z:
        servers = int(z["K"][level])
        trace = Trace.from_seconds(z["a"], np.minimum(z["svc"], limit_s), {}, limit_s=limit_s)
        labels = {"in_window": z["dl"].astype(bool), "is_heavy": z["hvt"].astype(bool)}
    return trace, servers, labels


def admissible(kind: str, promise: float, k: int, limit_s: float) -> bool:
    if kind == "Skip":
        return floor(promise * k / limit_s - (2 * k - 2) + 1e-9) >= 1
    return promise > (3.0 - 2.0 / k) * limit_s


def _suite(cfg, args, servers):
    score_key = cfg["scheduling"]["ranking_score"]
    suite = []
    for name in args.policy_names:
        kind, value = NAME.fullmatch(name).groups()
        if kind is None:
            suite.append(spjf(score_key, "SPJF-E"))
            continue
        promise = float(value)
        if not admissible(kind, promise, servers, cfg.limit_s):
            print(f"    {name}: k = {servers}, L = {cfg.limit_s:g} s admits no budget; it is "
                  f"FCFS and is not replayed", flush=True)
            continue
        if kind == "Guard":
            suite.append(cfg._guard_from(cfg.selected(promise), promise, servers, name))
        elif kind == "Fixed":
            suite.append(fixed(promise, servers, cfg.limit_s, score_key))
        else:
            suite.append(skip(promise, servers, cfg.limit_s, score_key))
    return suite


def _check_bound(outcome, fcfs_wait, policy, servers, limit_s):
    _CHECK(outcome, fcfs_wait, policy, servers, limit_s)
    if policy.wrapper != "none":
        commit, working = peak_gb()
        print(f"    bound held: {outcome.policy} k = {servers}, L = {limit_s:g} s, "
              f"{len(fcfs_wait):,} jobs; max W - W_FCFS = "
              f"{(outcome.wait_us - fcfs_wait).max() / 1e6:.6f} s; worker peak commit "
              f"{commit:.2f} GB, working set {working:.2f} GB", flush=True)


rov.prepare_context = _prepare_context
rov.load_overlay = _load_overlay
rov._suite = _suite
rov._check_bound = _check_bound
rov._refine = fixed_point.wrap(rov._refine)


def main() -> int:
    require_tag(sys.argv[1:], STEM, TAG)
    sys.argv = ["run_online_visibility.py", "--pool", "primary", "--variants", "online",
                *sys.argv[1:]]
    return rov.main()


if __name__ == "__main__":
    raise SystemExit(main())
