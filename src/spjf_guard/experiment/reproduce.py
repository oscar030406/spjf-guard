"""The acceptance check: this package reproduces the v3.1 development result exactly.

On the primary overlay at the three load levels, the per-job waits of FCFS, SJF, SPJF-E,
Guard(600), Fixed(600) and Skip(600) must equal, job for job, the waits the exploratory
kernels produce on the same trace, and the summary numbers must match
`prechecks/main_v3/v31/table_main_primary.csv` to the precision that file prints.

Predictions are taken from the stored v3.1 arrays.  Regenerating them is a separate
question: a LightGBM refit is not bit-reproducible across thread counts, so the equality
check runs on stored scores and any movement from a refit is reported on its own.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from spjf_guard.experiment.metrics import Summary, gap_closed, summarise
from spjf_guard.sim import MICROS, Trace, simulate
from spjf_guard.sim.policy import fcfs, fixed, guard, sjf, skip, spjf

SCORE_KEY = "tweedie"
"""The v3.1 name of the expected-cost score the paper calls SPJF-E."""

POLICY_COLUMN = {
    "FCFS": "FCFS",
    "SJF": "SJF-ref",
    "SPJF-E": "SPJF-tweedie",
    "Guard(600)": "CAP-G600",
    "Fixed(600)": "FIX-G600",
    "Skip(600)": "SKIP-G600",
}
"""Paper name -> the policy label v3.1's table carries."""


@dataclass(frozen=True)
class Comparison:
    """One policy at one load level, measured both ways."""

    level: int
    servers: int
    policy: str
    jobs_differing: int
    worst_difference_us: int
    ours: Summary
    theirs: dict
    gap_closed: float


def load_overlay(
    path: Path, level: int, score_map: dict[str, str] | None = None, limit_s: float = 60.0
):
    """Read one stored overlay and quantise it to whole microseconds.

    The stored arrays are float64 seconds; the trace this package simulates is integer
    microseconds, so the two differ only by the quantisation the kernel would apply
    anyway.  `score_map` renames stored score arrays to the keys the policies ask for.
    """
    score_map = score_map or {SCORE_KEY: SCORE_KEY}
    with np.load(path) as z:
        servers = int(z["K"][level])
        trace = Trace.from_seconds(
            z["a"],
            z["svc"],
            {key: z[stored] for stored, key in score_map.items()},
            limit_s=limit_s,
        )
        labels = {"in_window": z["dl"].astype(bool), "is_heavy": z["hvt"].astype(bool)}
    return trace, servers, labels


def policies_for(
    servers: int, limit_s: float, b0_base: float, eta: float, promise: float
) -> list:
    """The six policies of the acceptance check at one load level."""
    return [
        fcfs(),
        sjf(),
        spjf(SCORE_KEY, "SPJF-E"),
        guard(promise, servers, limit_s, b0_base * servers / 4.0, eta, SCORE_KEY),
        fixed(promise, servers, limit_s, SCORE_KEY),
        skip(promise, servers, limit_s, SCORE_KEY),
    ]


def _import_reference_kernels(prechecks: Path):
    """Import the exploratory kernels read-only.

    `NUMBA_CACHE_DIR` must already point somewhere outside `prechecks/`: numba reads it
    when it is imported, which has happened long before this call, so setting it here
    would be too late.  The entry points do it at their first line.
    """
    cache = os.environ.get("NUMBA_CACHE_DIR", "")
    if not cache or Path(cache).resolve() == prechecks.resolve():
        raise RuntimeError(
            "NUMBA_CACHE_DIR must be set to a scratch directory before numba is "
            "imported, or the compiled caches of the read-only kernels under "
            "prechecks/ are written next to their sources"
        )
    sys.dont_write_bytecode = True
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.path.insert(0, str(prechecks / "guard_variants"))
    sys.path.insert(0, str(prechecks / "main_v3" / "v31"))
    import guardkern
    import v31_skipkern

    return guardkern, v31_skipkern


def _reference_wait_us(kernels, trace: Trace, policy, servers: int) -> np.ndarray:
    """The waits the exploratory kernels produce, in microseconds."""
    guardkern, skipkern = kernels
    arrival = trace.arrival_us / MICROS
    service = trace.service_us / MICROS
    score = None if policy.base == "fcfs" else trace.score_for(policy.score_key)
    if policy.wrapper == "skip":
        out = skipkern.run(arrival, service, score, servers, policy.skip_count)
    elif policy.wrapper == "work":
        out = guardkern.run(
            arrival,
            service,
            servers,
            policy="guard",
            pred=score,
            B=policy.b0_us / MICROS,
            eps=policy.eta_k,
            Bmax=policy.bmax_us / MICROS,
            Mslots=1 << 22,
        )
        assert out.err == 0, "the exploratory kernel's window was too small"
    else:
        out = guardkern.run(
            arrival,
            service,
            servers,
            pred=score,
            policy="fcfs" if policy.base == "fcfs" else "pri",
        )
    return np.rint(out.w * MICROS).astype(np.int64)


def compare_level(
    trace: Trace,
    servers: int,
    labels: dict,
    level: int,
    table: dict,
    prechecks: Path,
    b0_base: float,
    eta: float,
    promise: float = 600.0,
) -> list[Comparison]:
    """Run the six policies both ways at one load level and line them up."""
    kernels = _import_reference_kernels(prechecks)
    policies = policies_for(servers, trace.limit_s, b0_base, eta, promise)
    reference_wait = simulate(trace, fcfs(), servers).wait_us
    out = []
    summaries = {}
    for policy in policies:
        ours = simulate(trace, policy, servers)
        theirs = _reference_wait_us(kernels, trace, policy, servers)
        differing = int((ours.wait_us != theirs).sum())
        worst = int(np.abs(ours.wait_us - theirs).max()) if len(theirs) else 0
        summaries[policy.name] = summarise(
            ours, reference_wait, labels["in_window"], labels["is_heavy"]
        )
        out.append(
            Comparison(
                level=level,
                servers=servers,
                policy=policy.name,
                jobs_differing=differing,
                worst_difference_us=worst,
                ours=summaries[policy.name],
                theirs=table[(level, POLICY_COLUMN[policy.name])],
                gap_closed=float("nan"),
            )
        )
        del ours, theirs
    reference_p99 = summaries["FCFS"].p99_dl_s
    target_p99 = summaries["SJF"].p99_dl_s
    return [
        Comparison(
            level=c.level,
            servers=c.servers,
            policy=c.policy,
            jobs_differing=c.jobs_differing,
            worst_difference_us=c.worst_difference_us,
            ours=c.ours,
            theirs=c.theirs,
            gap_closed=gap_closed(c.ours.p99_dl_s, reference_p99, target_p99),
        )
        for c in out
    ]


def read_v31_table(path: Path) -> dict:
    """{(level, policy label): row} from v3.1's reported table."""
    import csv

    rows = {}
    with open(path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["trace"] != "primary":
                continue
            rows[(int(row["level"]), row["policy"])] = {
                k: (float(v) if v not in ("", "-") else float("nan"))
                for k, v in row.items()
                if k not in ("trace", "policy", "score", "guard")
            }
    return rows
