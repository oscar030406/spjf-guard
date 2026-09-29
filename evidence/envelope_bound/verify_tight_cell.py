"""Direct per-job check of the tight bound on the cell with the smallest tight slack among
primary work-guard rows (tight_bound.py: overlay 3, level 2, Fixed(300)), plus the
same cell's Guard(300), so the subtraction in tight_bound.py is checked by a rerun.

Tight bound, work guard:  k W[i] < V_i^- + B_max + (2k - 1) L, in int64 microseconds.

Run from the repository root:
  env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME NUMBA_NUM_THREADS=4 \
      OMP_NUM_THREADS=4 uv run --no-sync python evidence/envelope_bound/verify_tight_cell.py \
      > evidence/envelope_bound/out_verify_tight_cell.txt
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from envelope_bound import (  # noqa: E402
    CONFIG, PRIMARY, SCORE_MAP, checked_backlog, cfgmod, load_overlay, simulate, MICROS,
)

OVERLAY, LEVEL, NAMES = 3, 2, ("Fixed(300)", "Guard(300)")


def main() -> None:
    cfg = cfgmod.load(CONFIG)
    trace, _, _ = load_overlay(PRIMARY[OVERLAY], 0, SCORE_MAP, cfg.limit_s)
    with np.load(PRIMARY[OVERLAY]) as z:
        k = int(z["K"].tolist()[LEVEL])
    limit_us = round(cfg.limit_s * MICROS)
    v_pre = checked_backlog(trace, k) - trace.service_us
    for policy in (p for p in cfg.policies(k) if p.name in NAMES):
        wait = simulate(trace, policy, k).wait_us
        slack = v_pre + policy.bmax_us + (2 * k - 1) * limit_us - np.int64(k) * wait
        worst = int(np.argmin(slack))
        print(f"overlay {OVERLAY} level {LEVEL} k={k} {policy.name}: B_max {policy.bmax_us / MICROS} s,"
              f" n={len(trace):,}, violations {int((slack <= 0).sum())},"
              f" min slack {int(slack.min()) / k / MICROS:.6f} s at job {worst}"
              f" (wait {int(wait[worst]) / MICROS:.3f} s), max wait {int(wait.max()) / MICROS:.3f} s")


if __name__ == "__main__":
    main()
