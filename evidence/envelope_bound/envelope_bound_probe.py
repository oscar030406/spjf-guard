"""Falsification probe: an absolute per-job wait bound from the fluid rate-k backlog.

Claim under test (derived by hand, not yet in the paper):
  (1) FCFS on k servers: W_FCFS[i] <= U_{<i}(a_i) / k.
  (2) Any work-conserving k-server policy: U(t) <= V(t) + (k-1) L, with V the backlog of a
      single fluid server of rate k fed the same work.
  (3) Hence W_FCFS[i] <= (V_i - C_i + (k-1) L) / k, V_i the fluid backlog just after i arrives,
      and under Guard(G): W[i] < (V_i - C_i + (k-1) L) / k + G.
A single job above its bound refutes the derivation.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from spjf_guard import config as cfgmod  # noqa: E402
from spjf_guard.experiment.reproduce import load_overlay  # noqa: E402
from spjf_guard.sim.runner import simulate  # noqa: E402

OVERLAY = ROOT / "data" / "derived" / "overlay_traces" / "primary_rep0.npz"
LIMIT_S = 60.0
PROMISES = ("Guard(300)", "Guard(600)", "Guard(1200)")


def fluid_backlog(arrival_s: np.ndarray, service_s: np.ndarray, rate: float) -> np.ndarray:
    """V_n = max(0, V_{n-1} - rate (a_n - a_{n-1})) + C_n, in closed form."""
    prefix = np.concatenate(([0.0], np.cumsum(service_s)))
    x = prefix[1:] - rate * arrival_s
    floor = np.minimum.accumulate(prefix[:-1] - rate * arrival_s)
    return x - floor


def main() -> None:
    cfg = cfgmod.load(ROOT / "configs" / "main.yaml")
    for level in (0, 1, 2):
        trace, k, _ = load_overlay(OVERLAY, level, {"tweedie": "spjf_e"}, LIMIT_S)
        arrival_s = trace.arrival_us / 1e6
        service_s = trace.service_us / 1e6
        v = fluid_backlog(arrival_s, service_s, float(k))
        base = (v - service_s + (k - 1) * LIMIT_S) / k
        sigma = float(v.max())
        print(f"level {level}: k={k}, n={len(v):,}, sigma={sigma:,.1f} s of work, "
              f"envelope bound FCFS (sigma+(k-1)L)/k = {(sigma + (k - 1) * LIMIT_S) / k:,.1f} s")
        policies = {p.name: p for p in cfg.policies(k)}
        runs = [("FCFS", policies["FCFS"], 0.0), ("SPJF-E", policies["SPJF-E"], None)]
        runs += [(name, policies[name], float(name[6:-1])) for name in PROMISES]
        for name, policy, promise in runs:
            started = time.time()
            wait = simulate(trace, policy, k).wait_us / 1e6
            if promise is None:
                print(f"  {name:12s} max wait {wait.max():9.1f} s  (no bound claimed)"
                      f"  [{time.time() - started:.0f} s]")
                continue
            bound = base + promise
            slack = bound - wait
            worst = int(np.argmin(slack))
            print(f"  {name:12s} max wait {wait.max():9.1f} s  per-job violations "
                  f"{int((slack < -1e-6).sum())}  min slack {slack[worst]:8.2f} s  "
                  f"absolute bound {sigma / k + (k - 1) * LIMIT_S / k + promise:9.1f} s  "
                  f"ratio max_wait/abs_bound {wait.max() / (sigma / k + (k - 1) * LIMIT_S / k + promise):.3f}"
                  f"  [{time.time() - started:.0f} s]")


if __name__ == "__main__":
    main()
