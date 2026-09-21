"""Exhaustive attack: EVERY work-conserving non-preemptive schedule.

For each small instance we enumerate every dispatch sequence a work-conserving
non-preemptive policy could produce (not just named policies), and check

  T1   |k(W_P-W_F) - (In-Out)| <= 2(k-1)L            (Theorem 1)
  C11  k=1: k(W_P-W_F) - (In-Out) == 0               (Corollary 1.1)
  L2   Out_i <= k(G - excess_i + L), G = max_j excess_j   (Lemma 2)
  T2   In_i <= kG + (3k-2)L                          (Theorem 2)
  C12  excess_i <= (In_i-Out_i)/k + (2-2/k)L         (Corollary 1.2, per job)
  P8   prefix-max form of Theorem 1                  (Proposition 8)

and record the worst observed slack per k.
"""
import sys, os, random, itertools
sys.dont_write_bytecode = True
from fractions import Fraction
from refsim2 import simulate, fcfs_chooser, enumerate_schedules, in_out

ARG = sys.argv[1] if len(sys.argv) > 1 else "main"


def prefix_max(a, x, i):
    return max(x[j] for j in range(len(a)) if a[j] <= a[i])


def in_service_max(a, x, start, comp, i):
    """largest work among the jobs other than i in service at s_i."""
    t = start[i]
    m = 0
    for j in range(len(a)):
        if j != i and start[j] <= t < comp[j]:
            if x[j] > m:
                m = x[j]
    return m


def run(instances, ks, label, log):
    worst = {}          # k -> (Fraction slack/L, instance)
    worstT2 = {}
    worstL2 = {}
    nsched = 0
    njob = 0
    viol = []
    for (a, x) in instances:
        n = len(a)
        L = max(x)
        if L == 0:
            continue
        for k in ks:
            fs, fc, fo = simulate(a, x, k, fcfs_chooser)
            WF = [fs[i] - a[i] for i in range(n)]
            for (st, cp, od) in enumerate_schedules(a, x, k):
                nsched += 1
                In, Out = in_out(x, od, n)
                W = [st[i] - a[i] for i in range(n)]
                exc = [W[i] - WF[i] for i in range(n)]
                G = max(exc)
                for i in range(n):
                    njob += 1
                    D = k * (W[i] - WF[i]) - (In[i] - Out[i])
                    r = Fraction(abs(D), L)
                    if k not in worst or r > worst[k][0]:
                        worst[k] = (r, (a, x, k, od, i, D, L))
                    if abs(D) > 2 * (k - 1) * L:
                        viol.append(("T1", a, x, k, od, i, D, L))
                    if k == 1 and D != 0:
                        viol.append(("C1.1", a, x, k, od, i, D, L))
                    # Lemma 2 / Theorem 2 with G = realised max excess
                    s2 = k * (G - exc[i] + L) - Out[i]
                    if k not in worstL2 or s2 < worstL2[k][0]:
                        worstL2[k] = (s2, (a, x, k, od, i))
                    if s2 < 0:
                        viol.append(("L2", a, x, k, od, i, Out[i], G, exc[i], L))
                    s3 = k * G + (3 * k - 2) * L - In[i]
                    if k not in worstT2 or s3 < worstT2[k][0]:
                        worstT2[k] = (s3, (a, x, k, od, i))
                    if s3 < 0:
                        viol.append(("T2", a, x, k, od, i, In[i], G, L))
                    # Corollary 1.2 per job
                    if k * exc[i] > (In[i] - Out[i]) + 2 * (k - 1) * L:
                        viol.append(("C1.2", a, x, k, od, i))
                    # Proposition 8 (prefix max / in-service max)
                    lp = prefix_max(a, x, i)
                    lP = in_service_max(a, x, st, cp, i)
                    lF = in_service_max(a, x, fs, fc, i)
                    if not (-(k - 1) * (lp + lP) <= D <= (k - 1) * (lp + lF)):
                        viol.append(("P8", a, x, k, od, i, D, lp, lP, lF))
    log.write("--- %s\n" % label)
    log.write("schedules enumerated : %d\n" % nsched)
    log.write("job-checks           : %d\n" % njob)
    log.write("violations           : %d\n" % len(viol))
    for v in viol[:12]:
        log.write("  VIOLATION %r\n" % (v,))
    for k in sorted(worst):
        r, inst = worst[k]
        log.write("  k=%d worst |D|/L = %s (= %.4f)   bound 2(k-1) = %d\n"
                  % (k, r, float(r), 2 * (k - 1)))
        log.write("        witness a=%s x=%s order=%s i=%d D=%s L=%s\n"
                  % (inst[0], inst[1], inst[3], inst[4], inst[5], inst[6]))
    for k in sorted(worstT2):
        log.write("  k=%d min slack of T2 (kG+(3k-2)L - In) = %s\n"
                  % (k, worstT2[k][0]))
        log.write("  k=%d min slack of L2 (k(G-exc+L) - Out) = %s\n"
                  % (k, worstL2[k][0]))
    log.flush()
    return len(viol)


def gen_instances(seed, count, nmax, amax, xmax, allow_zero, tie_heavy):
    random.seed(seed)
    out = []
    for _ in range(count):
        n = random.randint(1, nmax)
        if tie_heavy:
            a = sorted(random.randint(0, 1) for _ in range(n))
        else:
            a = sorted(random.randint(0, amax) for _ in range(n))
        lo = 0 if allow_zero else 1
        x = [random.randint(lo, xmax) for _ in range(n)]
        if max(x) == 0:
            x[0] = 1
        out.append((a, x))
    return out


def main():
    with open("out_exh.txt", "w") as log:
        total = 0
        # A: full systematic sweep over tiny instances (all arrival patterns,
        #    all size vectors) for n<=4, k in 1..3
        inst = []
        for n in range(1, 5):
            for a in itertools.product(range(0, 3), repeat=n):
                if list(a) != sorted(a):
                    continue
                for x in itertools.product(range(0, 3), repeat=n):
                    if max(x) == 0:
                        continue
                    inst.append((list(a), list(x)))
        total += run(inst, [1, 2, 3], "A: systematic n<=4, a in 0..2, x in 0..2",
                     log)

        # B: random n<=6, sizes up to 4, arrivals up to 5
        total += run(gen_instances(1, 4000, 6, 5, 4, True, False),
                     [1, 2, 3], "B: random n<=6 x<=4 (zero sizes allowed)", log)
        # C: all arrivals tied (worst case for the dispatch-phase convention)
        total += run(gen_instances(2, 4000, 6, 0, 4, True, True),
                     [1, 2, 3], "C: n<=6 all/mostly tied arrivals", log)
        # D: n=7, sizes in {0,1,2}
        total += run(gen_instances(3, 1200, 7, 4, 2, True, False),
                     [1, 2, 3], "D: random n=7 x<=2", log)
        # E: sizes all equal to L (the extremal case for the proof)
        random.seed(4)
        inst = []
        for _ in range(3000):
            n = random.randint(2, 6)
            a = sorted(random.randint(0, 3) for _ in range(n))
            inst.append((a, [3] * n))
        total += run(inst, [1, 2, 3, 4], "E: all sizes = L = 3", log)
        # F: one huge job among unit jobs
        random.seed(5)
        inst = []
        for _ in range(3000):
            n = random.randint(2, 6)
            a = sorted(random.randint(0, 4) for _ in range(n))
            x = [1] * n
            x[random.randrange(n)] = random.choice([5, 8])
            inst.append((a, x))
        total += run(inst, [1, 2, 3], "F: one big job among unit jobs", log)
        log.write("\nTOTAL VIOLATIONS = %d\n" % total)
    print(open("out_exh.txt").read()[-4000:])


if __name__ == "__main__":
    main()
