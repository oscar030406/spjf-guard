"""Gate 1: bf_kernel.simulate_backfill against the Python references on random small instances.

Every start time compared exactly, unit widths, M = k:
  A  estimate D for every job (the paper's "estimate = L"): kernel CBF vs backfill_ref
     ConservativeRef and backfill.Conservative; kernel SLACK vs SlackRef and backfill.Slack,
     candidates "now+anchor", G drawn from {0, D, 2D, 3D}.  Also CBF == FCFS (observed).
  B  per-job estimates est_j in [1, D] with overrun to L = D: kernel vs ref_est.CBFEst and
     ref_est.SlackEst (SLACK fallback counts compared too); ref_est with est = D vs
     backfill_ref (the extension reduces to the reference rules).
    python evidence/revision_r1/backfill_baselines/gate1_random.py
"""
import sys
import time
from pathlib import Path
from random import Random

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "evidence" / "llm_batching"))
sys.path.insert(0, str(ROOT / "evidence" / "llm_batching" / "backfill"))
from backfill import Conservative, Slack  # noqa: E402
from backfill_ref import ConservativeRef, SlackRef  # noqa: E402
from bf_kernel import C_ERR, C_FALLBACK, RULE_CBF, RULE_SLACK, simulate_backfill  # noqa: E402
from check_overtaking_cost import fcfs_list  # noqa: E402
from check_prefix_refund import run  # noqa: E402
from ref_est import CBFEst, SlackEst  # noqa: E402


def kernel(reqs, k, est, rule, G, L):
    a = np.array([r[0] for r in reqs], np.int64)
    s = np.array([r[2] for r in reqs], np.int64)
    start, _, cnt = simulate_backfill(a, s, np.array(est, np.int64), k, rule, G, L, 4096)
    assert cnt[C_ERR] == 0, cnt
    return [int(x) for x in start], cnt


def main():
    rng = Random(20261018)
    st = {k: 0 for k in ("instances", "jobs", "A cbf != ref", "A cbf != backfill.py",
                         "A slack != ref", "A slack != backfill.py", "A cbf != FCFS",
                         "B cbf != ref_est", "B slack != ref_est", "B fallback differs",
                         "ref_est(D) != backfill_ref")}
    seen = {"B overruns": 0, "B fallbacks": 0, "A slack != FCFS": 0}
    t0 = time.time()
    for trial in range(4000):
        k, D, n = rng.randint(1, 5), rng.randint(1, 8), rng.randint(1, 14)
        spread = rng.choice((0, 3, 10, 30))
        reqs = sorted((rng.randint(0, spread), 1, rng.randint(1, D)) for _ in range(n))
        G = rng.choice((0, D, 2 * D, 3 * D))
        w = [1] * n
        sf = fcfs_list(reqs, k, [])
        # A: uniform estimate D
        kc, _ = kernel(reqs, k, [D] * n, RULE_CBF, G, D)
        st["A cbf != ref"] += kc != run(reqs, k, ConservativeRef(w, k, D))
        st["A cbf != backfill.py"] += kc != run(reqs, k, Conservative(w, k, D))
        st["A cbf != FCFS"] += kc != sf
        ks, _ = kernel(reqs, k, [D] * n, RULE_SLACK, G, D)
        ref_s = run(reqs, k, SlackRef(w, k, D, G, "now+anchor"))
        st["A slack != ref"] += ks != ref_s
        st["A slack != backfill.py"] += ks != run(reqs, k, Slack(w, k, D, G, "now+anchor"))
        seen["A slack != FCFS"] += ks != sf
        st["ref_est(D) != backfill_ref"] += run(reqs, k, SlackEst([D] * n, k, D, G)) != ref_s
        # B: per-job estimates, overrun to L = D
        est = [rng.randint(1, D) for _ in range(n)]
        kc, _ = kernel(reqs, k, est, RULE_CBF, G, D)
        rc = CBFEst(est, k, D)
        st["B cbf != ref_est"] += kc != run(reqs, k, rc)
        seen["B overruns"] += rc.overruns
        ks, cnt = kernel(reqs, k, est, RULE_SLACK, G, D)
        rs = SlackEst(est, k, D, G)
        st["B slack != ref_est"] += ks != run(reqs, k, rs)
        st["B fallback differs"] += int(cnt[C_FALLBACK]) != rs.fallbacks
        seen["B fallbacks"] += rs.fallbacks
        st["instances"] += 1
        st["jobs"] += n
        if trial % 1000 == 999:
            print(f"after {trial + 1}: {st}", flush=True)
    print(f"observed (not asserted): {seen}")
    fails = sum(v for key, v in st.items() if key not in ("instances", "jobs"))
    print(f"{'PASS' if fails == 0 else 'FAIL'}: {fails} mismatches [{time.time() - t0:.0f} s]")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
