"""Group projection of the net-overtake identity (candidate N6, applications.md).

Summing k (W_P - W_FCFS) over a group g: a pair inside g (u earlier, v dispatched first)
contributes C_v - C_u, a pair across the boundary only its end in g. So
    sum_{i in g} k dW_i = intra(g) + inter_in(g) - inter_out(g) + err,
exact at k = 1, |err| < 2(k-1)L|g| for k >= 2 (sum of the per-job errors).
Under SJF every inversion puts a shorter job first, so intra(g) <= 0: reordering inside a
group never adds to that group's total wait beyond what crosses its boundary.
    python check_group.py > out_check_group.txt
"""
import sys
from fractions import Fraction
from pathlib import Path
from random import Random

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reservation_guard_verify"))
from rguard_indep import run_with_chooser  # noqa: E402

L = 3


def sjf(jobs):
    return lambda t, q, fin: min(range(len(q)), key=lambda c: (jobs[q[c]][1], q[c]))


def main(trials=20000, seed=7):
    rng = Random(seed)
    k1_exact = k1_bad = intra_pos = 0
    worst = {}
    for trial in range(trials):
        k = rng.randint(1, 4)
        n = rng.randint(2, 14)
        jobs = sorted((rng.randint(0, 15), Fraction(rng.randint(1, 6), 2)) for _ in range(n))
        grp = [rng.randrange(3) for _ in range(n)]
        fcfs, _ = run_with_chooser(jobs, k, lambda t, q, fin: 0)
        use_sjf = trial % 2 == 0
        chooser = sjf(jobs) if use_sjf else (lambda t, q, fin: rng.randrange(len(q)))
        p, seq = run_with_chooser(jobs, k, chooser)
        pos = {j: r for r, j in enumerate(seq)}
        for g in range(3):
            members = [i for i in range(n) if grp[i] == g]
            if not members:
                continue
            lhs = sum(k * (p[i] - fcfs[i]) for i in members)
            intra = inter = 0
            for i in members:
                for j in range(n):
                    if j > i and pos[j] < pos[i]:          # j overtook i
                        if grp[j] == g:
                            intra += jobs[j][1] - jobs[i][1]
                        else:
                            inter += jobs[j][1]
                    elif j < i and pos[j] > pos[i] and grp[j] != g:   # i overtook j
                        inter -= jobs[j][1]
            err = lhs - (intra + inter)
            if use_sjf and intra > 0:
                intra_pos += 1
            if k == 1:
                k1_exact += err == 0
                k1_bad += err != 0
            else:
                r_sum = float(abs(err) / (2 * (k - 1) * L * len(members)))
                r_one = float(abs(err) / (2 * (k - 1) * L))
                w = worst.setdefault(k, [0.0, 0.0])
                w[0], w[1] = max(w[0], r_sum), max(w[1], r_one)
    print(f"k=1: group identity exact in {k1_exact} groups, different in {k1_bad}")
    print(f"SJF runs: groups with intra(g) > 0: {intra_pos} (claim 0)")
    for k in (2, 3, 4):
        a, b = worst.get(k, [0.0, 0.0])
        print(f"k={k}: worst |err| / (2(k-1)L|g|) = {a:.4f} (claim < 1); "
              f"worst |err| / (2(k-1)L) = {b:.4f} (does one constant suffice?)")


if __name__ == "__main__":
    main()
