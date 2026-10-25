"""Checks of the net-overtake identity against a general static-key reference.

Reference R: non-preemptive, work-conserving list scheduling that always starts the waiting
job with the smallest (key, index).  FCFS is key = arrival time.  For a job i write j <| i
when (key_j, j) < (key_i, i) ("ahead of i in R's order").  Claims checked:

(T3) for every work-conserving non-preemptive P and every job i,
     | k (W_P[i] - W_R[i]) - (In_i - Out_i) | < 2(k-1)L + Lam_i   (k >= 2; <= at k = 1)
     In_i  = cost of jobs behind i in R's order that P starts while i waits, before i;
     Out_i = cost of jobs ahead of i in R's order, arrived by P's start of i, started after i;
     Lam_i = cost of jobs behind i that arrived strictly before i
           + cost of jobs ahead of i that arrived strictly after i.
(G)  the guard run on R's order (over[q] = completed cost of jobs behind q started at or
     after a_q; start the first eligible job in R's order, else the base's choice) keeps
     k * excess_R[i] < B + (3k-2)L + Lam_i.
(A)  amplification: one overtake of cost L followed by a burst of later-arriving jobs that
     are ahead in R's order makes the excess grow with the burst, so Lam_i cannot be dropped.

    python check_general_reference.py > out_check_general_reference.txt
"""
import sys
from pathlib import Path
from random import Random

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reservation_guard_verify"))
from rguard_indep import run_with_chooser  # noqa: E402

L = 3


def order_key(jobs, keys):
    return {j: (keys[j], j) for j in range(len(jobs))}


def reference(jobs, k, keys):
    ok = order_key(jobs, keys)
    start, _ = run_with_chooser(jobs, k, lambda t, q, fin: min(range(len(q)), key=lambda c: ok[q[c]]))
    return start


def measures(jobs, keys, start, seq):
    """In, Out and Lam of every job, relative to R's order, for the schedule (start, seq)."""
    n = len(jobs)
    ok = order_key(jobs, keys)
    pos = {j: p for p, j in enumerate(seq)}
    out = []
    for i in range(n):
        a_i, s_i = jobs[i][0], start[i]
        inn = sum(jobs[j][1] for j in range(n)
                  if ok[j] > ok[i] and pos[j] < pos[i] and start[j] >= a_i)
        outt = sum(jobs[j][1] for j in range(n)
                   if ok[j] < ok[i] and pos[j] > pos[i] and jobs[j][0] <= s_i)
        lam = sum(jobs[j][1] for j in range(n)
                  if (ok[j] > ok[i] and jobs[j][0] < a_i) or (ok[j] < ok[i] and jobs[j][0] > a_i))
        out.append((inn, outt, lam))
    return out


def guard_chooser(jobs, keys, B, rng):
    ok = order_key(jobs, keys)

    def choose(t, q, fin):
        def over(x):
            return sum(jobs[j][1] for j in range(len(jobs))
                       if ok[j] > ok[x] and fin[j] is not None and fin[j] <= t
                       and fin[j] - jobs[j][1] >= jobs[x][0])
        eligible = [c for c in range(len(q)) if over(q[c]) >= B]
        if eligible:
            return min(eligible, key=lambda c: ok[q[c]])
        return rng.randrange(len(q))
    return choose


def random_instance(rng, n, spread, h, strict):
    arrivals = sorted(rng.randint(0, spread) for _ in range(n))
    jobs = [(a, rng.randint(1, L)) for a in arrivals]
    if strict:                               # two strict priority classes, FCFS within each
        keys = [(rng.randint(0, 1), a) for a, _ in jobs]
    else:                                    # arrival time plus an offset in [0, h]
        keys = [(a + rng.randint(0, h),) for a, _ in jobs]
    return jobs, keys


def check_identity(trials, seed):
    rng = Random(seed)
    worst = {}
    for _ in range(trials):
        k = rng.randint(1, 4)
        n = rng.randint(2, 11)
        h = rng.choice((0, 0, 1, 2, 5))
        strict = rng.random() < 0.2
        jobs, keys = random_instance(rng, n, rng.choice((3, 8, 15)), h, strict)
        wr = reference(jobs, k, keys)
        for _ in range(6):
            start, seq = run_with_chooser(jobs, k, lambda t, q, fin: rng.randrange(len(q)))
            for i, (inn, outt, lam) in enumerate(measures(jobs, keys, start, seq)):
                lhs = k * ((start[i] - jobs[i][0]) - (wr[i] - jobs[i][0])) - (inn - outt)
                slack = 2 * (k - 1) * L + lam
                tag = ("strict" if strict else f"h={h}", k)
                w = worst.setdefault(tag, [0.0, 0])
                ratio = abs(lhs) / slack if slack else (0.0 if lhs == 0 else float("inf"))
                w[0] = max(w[0], ratio)
                w[1] += abs(lhs) > slack if k == 1 else abs(lhs) >= slack   # strict for k >= 2
    return worst


def check_guard(trials, seed):
    rng = Random(seed)
    worst, violations = 0.0, 0
    for _ in range(trials):
        k = rng.randint(1, 3)
        n = rng.randint(2, 10)
        jobs, keys = random_instance(rng, n, rng.choice((3, 8)), rng.choice((0, 1, 2, 5)), False)
        B = rng.randint(0, 6)
        wr = reference(jobs, k, keys)
        start, seq = run_with_chooser(jobs, k, guard_chooser(jobs, keys, B, rng))
        for i, (inn, outt, lam) in enumerate(measures(jobs, keys, start, seq)):
            excess = (start[i] - jobs[i][0]) - (wr[i] - jobs[i][0])
            bound = B + (3 * k - 2) * L + lam
            worst = max(worst, k * excess / bound)
            violations += k * excess >= bound
    return worst, violations


def amplification(burst):
    """k = 1.  At t = 0 job i (key 0 + 5) and job b (key 0 + 6) arrive; b overtakes i.
    At t = 1 a burst of unit jobs with key 1 + 0 arrives, ahead of i in R's order."""
    jobs = [(0, 1), (0, L)] + [(1, 1)] * burst          # i = job 0 (cost 1), b = job 1
    keys = [(5,), (6,)] + [(1,)] * burst
    wr = reference(jobs, 1, keys)

    def p(t, q, fin):                                   # b first, then the burst, then i
        for j in (1, *range(2, 2 + burst), 0):
            if j in q:
                return q.index(j)
    start, seq = run_with_chooser(jobs, 1, p)
    inn, outt, lam = measures(jobs, keys, start, seq)[0]
    return start[0] - wr[0], inn, outt, lam


def main():
    for tag, (ratio, bad) in sorted(check_identity(4000, 1).items(), key=str):
        print(f"T3 {tag}: worst |k(W_P-W_R)-(In-Out)| / (2(k-1)L+Lam) = {ratio:.3f}, violations {bad}")
    worst, bad = check_guard(3000, 2)
    print(f"G  guard on R's order: worst k*excess / (B+(3k-2)L+Lam) = {worst:.3f}, violations {bad}")
    for burst in (0, 5, 20, 80):
        print("A  burst %3d: excess of i = %s, In = %s, Out = %s, Lam = %s" % (burst, *amplification(burst)))


if __name__ == "__main__":
    main()
