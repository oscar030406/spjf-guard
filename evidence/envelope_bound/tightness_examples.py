"""Two hand-built inputs that show how close the envelope bound can be reached, run through
the package simulator so that the simulator is also checked against a hand-computed wait.

Example A (burst behind k-1 long jobs), k servers, L = 60 s, all at t = 0:
  k-1 jobs of size L, then B/d jobs of size d.  sigma = (k-1) L + B and the last small
  job waits within d of sigma/k (exact discrete wait computed below), so sigma/k is
  reached as d -> 0.
Example B (k = 2, one stagger), L = 60 s:
  t = 0: one job of size L; t = L/2: one job of size L, then B/d jobs of size d.
  sigma = L + B, and the last small job waits L/4 - O(d) more than sigma/k: the term
  (1-1/k) L cannot be dropped, and at k = 2 at least half of it is needed.
The bound claims W <= (V_i - C_i + (k-1) L)/k for every job; both examples check it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from spjf_guard.sim.policy import MICROS, fcfs  # noqa: E402
from spjf_guard.sim.runner import Trace, simulate  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from envelope_bound import fluid_backlog_us  # noqa: E402

L_US = 60 * MICROS


def report(name: str, arrival_us, service_us, k: int, hand_last_wait_us: int) -> None:
    a = np.asarray(arrival_us, np.int64)
    c = np.asarray(service_us, np.int64)
    wait = simulate(Trace(a, c, {}, 60.0), fcfs(), k).wait_us
    v = fluid_backlog_us(a, c, k)
    slack = v - c + (k - 1) * L_US - k * wait
    sigma = int(v.max())
    print(f"{name}: k={k}, n={len(a)}, last wait {wait[-1] / MICROS:.6f} s "
          f"(hand {hand_last_wait_us / MICROS:.6f} s, equal {int(wait[-1]) == hand_last_wait_us}); "
          f"sigma/k {sigma / k / MICROS:.6f} s; wait - sigma/k {(k * int(wait[-1]) - sigma) / k / MICROS:+.6f} s; "
          f"(1-1/k)L {(k - 1) * L_US / k / MICROS:.3f} s; per-job violations {int((slack < 0).sum())}")


def example_a(k: int, burst_s: int, d_us: int) -> None:
    n_small = burst_s * MICROS // d_us
    arrival = np.zeros(k - 1 + n_small, np.int64)
    service = np.concatenate([np.full(k - 1, L_US), np.full(n_small, d_us)])
    # Server k runs L/d small jobs during [0, L); from L on, k at a time.
    left = n_small - L_US // d_us
    hand = L_US + (-(-left // k) - 1) * d_us
    report(f"A(B={burst_s}s, d={d_us}us)", arrival, service, k, hand)


def example_b(burst_s: int, d_us: int) -> None:
    n_small = burst_s * MICROS // d_us
    arrival = np.concatenate([[0, L_US // 2], np.full(n_small, L_US // 2)])
    service = np.concatenate([[L_US, L_US], np.full(n_small, d_us)])
    # Server 1 frees at L and runs (L/2)/d small jobs until server 2 frees at 3L/2;
    # from then on two at a time.  The burst arrives at L/2.
    left = n_small - (L_US // 2) // d_us
    hand = 3 * L_US // 2 + (-(-left // 2) - 1) * d_us - L_US // 2
    report(f"B(B={burst_s}s, d={d_us}us)", arrival, service, 2, hand)


def main() -> None:
    for k in (2, 4, 8):
        example_a(k, 600, 1_000_000)
    example_b(600, 1_000_000)
    example_b(600, 100_000)


if __name__ == "__main__":
    main()
