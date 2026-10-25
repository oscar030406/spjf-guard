"""Exhaustive form of the T3 check: every dispatch sequence any base policy can produce, on
every small instance, against a static-key reference with offsets in [0, h].

    python check_exhaustive.py > out_check_exhaustive.txt
"""
import sys
from itertools import product
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reservation_guard_verify"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_general_reference import L, measures, reference  # noqa: E402
from rguard_indep import enumerate_runs  # noqa: E402


def main():
    for k, n, h in ((1, 5, 2), (2, 5, 1), (2, 5, 2), (3, 5, 1)):
        worst, bad, runs, instances = 0.0, 0, 0, 0
        for sizes in product((1, 3), repeat=n):
            for arrivals in product((0, 1, 2), repeat=n):
                if list(arrivals) != sorted(arrivals):
                    continue
                for offsets in product(range(h + 1), repeat=n):
                    jobs = list(zip(arrivals, sizes))
                    keys = [(a + d,) for a, d in zip(arrivals, offsets)]
                    instances += 1
                    wr = reference(jobs, k, keys)
                    for start, seq in enumerate_runs(jobs, k, "free", 0):
                        runs += 1
                        for i, (inn, outt, lam) in enumerate(measures(jobs, keys, start, seq)):
                            lhs = k * (start[i] - wr[i]) - (inn - outt)
                            slack = 2 * (k - 1) * L + lam
                            if slack:
                                worst = max(worst, abs(lhs) / slack)
                            bad += abs(lhs) > slack if k == 1 else abs(lhs) >= slack
        print(f"k={k} n={n} h={h}: instances {instances}, runs {runs}, "
              f"worst |k(W_P-W_R)-(In-Out)|/(2(k-1)L+Lam) = {worst:.3f}, violations {bad}", flush=True)


if __name__ == "__main__":
    main()
