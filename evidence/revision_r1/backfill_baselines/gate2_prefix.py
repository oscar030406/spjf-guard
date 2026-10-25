"""Gate 2: bf_kernel against the Python backfill.py on slices of overlay 0, level 2 (k = 4).

backfill.py keeps one usage counter per time step, so each slice is quantised to a unit u:
arrival = (a_us - a_us[first]) // u, duration = ceil(s_us / u) clipped to [1, L/u],
estimate D = L/u for every job, G = 300 s / u.  Both implementations run the same integer
instance; every start time is compared.  Rules: Conservative, and Slack with candidates
"now+anchor" (backfill.py's reduction).  Slices:
  first   the first 20,000 jobs (light load), u = 10 ms
  busy    20,000 jobs from 2,000 before the first arrival that finds >= 40 jobs waiting
          under FCFS (production kernel, microseconds), u = 100 ms
    python evidence/revision_r1/backfill_baselines/gate2_prefix.py [--n 20000]
"""
import argparse
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "evidence" / "llm_batching"))
sys.path.insert(0, str(ROOT / "evidence" / "llm_batching" / "backfill"))
from backfill import Conservative, Slack  # noqa: E402
from bf_kernel import C_ERR, RULE_CBF, RULE_SLACK, simulate_backfill  # noqa: E402
from check_prefix_refund import run  # noqa: E402
from spjf_guard.experiment.reproduce import load_overlay  # noqa: E402
from spjf_guard.sim import simulate  # noqa: E402
from spjf_guard.sim.policy import fcfs  # noqa: E402

OVERLAY = ROOT / "data" / "derived" / "overlay_traces" / "primary_rep0.npz"
L_US = 60_000_000
G_US = 300_000_000


def compare(name, a_us, s_us, k, unit_us):
    a = (a_us - a_us[0]) // unit_us
    D = L_US // unit_us
    d = np.minimum(np.maximum(-(-s_us // unit_us), 1), D)
    G = G_US // unit_us
    reqs = [(int(x), 1, int(y)) for x, y in zip(a, d)]
    n = len(reqs)
    out = {}
    for rule, label in ((RULE_CBF, "conservative"), (RULE_SLACK, "slack now+anchor")):
        t0 = time.time()
        pol = Conservative([1] * n, k, D) if rule == RULE_CBF else Slack([1] * n, k, D, G, "now+anchor")
        py = run(reqs, k, pol)
        t1 = time.time()
        st, _, cnt = simulate_backfill(
            a.astype(np.int64), d.astype(np.int64), np.full(n, D, np.int64), k, rule, G, D, 1 << 16
        )
        t2 = time.time()
        assert cnt[C_ERR] == 0, cnt
        diff = int(np.sum(np.asarray(py, np.int64) != st))
        wait = np.asarray(py, np.int64) - a
        out[label] = diff
        print(f"{name}: {n} jobs, unit {unit_us} us, D {D}, G {G}, span {int(a[-1])} units;"
              f" {label}: {diff} starts differ; mean wait {wait.mean():.3f} units,"
              f" max {int(wait.max())}; backfill.py {t1 - t0:.0f} s, kernel {t2 - t1:.1f} s",
              flush=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20000)
    args = ap.parse_args()
    trace, k, _ = load_overlay(OVERLAY, 2, {}, 60.0)
    a_us, s_us = trace.arrival_us, trace.service_us
    fails = 0
    res = compare("first", a_us[: args.n], s_us[: args.n], k, 10_000)
    fails += sum(res.values())
    st = simulate(trace, fcfs(), k).start_us
    waiting = np.arange(len(a_us)) - np.searchsorted(st, a_us, side="right")
    i = int(np.flatnonzero(waiting >= 40)[0])
    lo = max(0, i - 2000)
    print(f"busy slice from job {lo} (job {i} finds {int(waiting[i])} waiting under FCFS;"
          f" largest FCFS queue in the slice {int(waiting[lo:lo + args.n].max())})", flush=True)
    res = compare("busy", a_us[lo: lo + args.n], s_us[lo: lo + args.n], k, 100_000)
    fails += sum(res.values())
    print(f"{'PASS' if fails == 0 else 'FAIL'}: {fails} starts differ")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
