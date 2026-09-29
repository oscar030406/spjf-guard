"""Random instance generators shared by the simulator tests."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# numba reads NUMBA_CACHE_DIR once, when it is imported.  It has to be redirected here,
# before anything pulls numba in, or the compiled caches of the read-only kernels under
# prechecks/ land next to their sources.
os.environ.setdefault("NUMBA_CACHE_DIR", tempfile.mkdtemp(prefix="numba_tests_"))
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.dont_write_bytecode = True

import numpy as np  # noqa: E402
import pytest  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:  # tests run without an editable install
    sys.path.insert(0, str(ROOT / "src"))

from spjf_guard.sim import MICROS, Trace  # noqa: E402

LIMIT_S = 60.0


def random_trace(
    rng: np.random.Generator,
    n: int,
    k: int,
    load: float = 1.0,
    limit_s: float = LIMIT_S,
    heavy_share: float = 0.05,
) -> Trace:
    """A bursty trace with a heavy tail, clipped at the limit, in whole microseconds."""
    light = rng.gamma(0.4, 0.5, size=n)
    heavy = rng.uniform(5.0, limit_s, size=n)
    service = np.where(rng.random(n) < heavy_share, heavy, light)
    service = np.clip(service, 1e-3, limit_s)
    mean_rate = k * load / service.mean()
    gaps = rng.exponential(1.0 / mean_rate, size=n)
    gaps[rng.random(n) < 0.3] = 0.0  # bursts, so ties in arrival time occur
    arrival = np.cumsum(gaps)
    service_us = np.maximum(np.rint(service * MICROS).astype(np.int64), 1)
    arrival_us = np.rint(arrival * MICROS).astype(np.int64)
    scores = {
        "good": service + rng.normal(0.0, 0.3, size=n),
        "noisy": rng.random(n),
        "reversed": -service,
    }
    return Trace(arrival_us, service_us, scores, limit_s)


@pytest.fixture
def rng() -> np.random.Generator:
    return np.random.default_rng(20260920)
