"""Job-for-job agreement with the exploratory kernels the development results came from.

The two modules under `prechecks/` are imported read-only and only here: the package
itself never depends on them.  Bytecode and the numba cache are redirected to a scratch
directory so that importing them leaves `prechecks/` untouched.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

from conftest import LIMIT_S, random_trace
from spjf_guard.sim import MICROS, simulate, spjf
from spjf_guard.sim.policy import fcfs, fixed, guard, sjf, skip

PRECHECKS = Path(__file__).resolve().parents[1] / "prechecks"
pytestmark = pytest.mark.crosscheck


@pytest.fixture(scope="module")
def kernels():
    needed = (
        PRECHECKS / "guard_variants" / "guardkern.py",
        PRECHECKS / "main_v3" / "v31" / "v31_skipkern.py",
    )
    missing = [p for p in needed if not p.is_file()]
    if missing:
        pytest.skip(
            "the exploratory kernels are not in this checkout ("
            + ", ".join(str(p.relative_to(PRECHECKS.parent)) for p in missing)
            + "); prechecks/ is not part of the package"
        )
    sys.dont_write_bytecode = True
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    os.environ.setdefault("NUMBA_CACHE_DIR", tempfile.mkdtemp(prefix="numba_xcheck_"))
    sys.path.insert(0, str(PRECHECKS / "guard_variants"))
    sys.path.insert(0, str(PRECHECKS / "main_v3" / "v31"))
    import guardkern
    import v31_skipkern

    return guardkern, v31_skipkern


def _guardkern_kwargs(policy, k):
    """The same rule expressed in the exploratory kernel's parameters."""
    if policy.wrapper == "none":
        return dict(policy="fcfs" if policy.base == "fcfs" else "pri")
    return dict(
        policy="guard", B=policy.b0_us / MICROS, eps=policy.eta_k, Bmax=policy.bmax_us / MICROS
    )


def _as_seconds(trace):
    return trace.arrival_us / MICROS, trace.service_us / MICROS


@pytest.mark.parametrize("k", (1, 2, 4, 7))
def test_waits_match_guardkern_job_for_job(kernels, rng, k):
    guardkern, _ = kernels
    trace = random_trace(rng, 5000, k, load=1.15)
    a, s = _as_seconds(trace)
    policies = [fcfs(), sjf(), spjf("good", "SPJF-E"), spjf("reversed", "SPJF-reversed")]
    for promise in (300.0, 600.0, 1200.0):
        policies.append(guard(promise, k, LIMIT_S, 120.0 * k / 4, 0.75, "good"))
        policies.append(fixed(promise, k, LIMIT_S, "good"))
    for policy in policies:
        score = None if policy.base == "fcfs" else trace.score_for(policy.score_key)
        theirs = guardkern.run(a, s, k, pred=score, **_guardkern_kwargs(policy, k))
        assert theirs.err == 0
        ours = simulate(trace, policy, k)
        theirs_us = np.rint(theirs.w * MICROS).astype(np.int64)
        assert np.array_equal(ours.wait_us, theirs_us), (
            f"{policy.name} at k={k}: {int((ours.wait_us != theirs_us).sum())} of "
            f"{len(trace)} waits differ, worst "
            f"{int(np.abs(ours.wait_us - theirs_us).max())} us"
        )


@pytest.mark.parametrize("k", (1, 2, 4))
def test_waits_match_the_dispatch_charged_skip_kernel(kernels, rng, k):
    _, skipkern = kernels
    trace = random_trace(rng, 5000, k, load=1.15)
    a, s = _as_seconds(trace)
    score = trace.score_for("good")
    for promise in (300.0, 600.0, 1200.0):
        policy = skip(promise, k, LIMIT_S, "good")
        theirs = skipkern.run(a, s, score, k, policy.skip_count)
        ours = simulate(trace, policy, k)
        theirs_us = np.rint(theirs.w * MICROS).astype(np.int64)
        assert np.array_equal(ours.wait_us, theirs_us), (
            f"{policy.name} at k={k}: "
            f"{int((ours.wait_us != theirs_us).sum())} of {len(trace)} waits differ"
        )
