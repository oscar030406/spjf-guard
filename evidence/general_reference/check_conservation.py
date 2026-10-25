"""The cost-weighted projection of the net-overtake identity: a pathwise Kleinrock law.

k = 1: sum_i C_i W_i is the same for every non-preemptive work-conserving policy.
k > 1: |sum_i C_i (W_P[i] - W_FCFS[i])| < (k-1) L T, T the length of the union of the
two schedules' busy time (sum_i C_i W_i + C_i^2/2 is the integral of the unfinished work,
and Lemma 1 bounds the gap of the two integrands).
    python check_conservation.py > out_check_conservation.txt
"""
import sys
from fractions import Fraction
from pathlib import Path
from random import Random

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reservation_guard_verify"))
from rguard_indep import run_with_chooser  # noqa: E402

L = 3


def busy_union(jobs, *starts):
    spans = sorted((s[j], s[j] + jobs[j][1]) for s in starts for j in range(len(jobs)))
    total, end = 0, None
    for a, b in spans:
        if end is None or a > end:
            total += b - a
            end = b
        elif b > end:
            total += b - end
            end = b
    return total


def main(trials=20000, seed=5):
    rng = Random(seed)
    exact_k1, worst = 0, {}
    for _ in range(trials):
        k = rng.randint(1, 4)
        n = rng.randint(2, 12)
        jobs = sorted((rng.randint(0, 15), Fraction(rng.randint(1, 6), 2)) for _ in range(n))
        fcfs, _ = run_with_chooser(jobs, k, lambda t, q, fin: 0)
        p, _ = run_with_chooser(jobs, k, lambda t, q, fin: rng.randrange(len(q)))
        diff = sum(c * ((p[i] - a) - (fcfs[i] - a)) for i, (a, c) in enumerate(jobs))
        if k == 1:
            exact_k1 += diff == 0
            worst[1] = worst.get(1, 0) + (diff != 0)
        else:
            bound = (k - 1) * L * busy_union(jobs, p, fcfs)
            worst[k] = max(worst.get(k, 0.0), float(abs(diff) / bound) if bound else 0.0)
    print(f"k=1: sum C_i W_i equal to FCFS in {exact_k1} runs, different in {worst.get(1, 0)}")
    for k in (2, 3, 4):
        print(f"k={k}: worst |sum C_i dW_i| / ((k-1) L T) = {worst.get(k, 0.0):.4f} (claim < 1)")


if __name__ == "__main__":
    main()
