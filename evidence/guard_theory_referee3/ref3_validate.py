"""Simulator self-validation, and a diff of MY reconstruction of the Theorem 3
families against the note's own generator (family_tight.py).

The note's code is imported ONLY here, and only after ref3_thm3.py was written
from the prose.
"""
import random
import sys
from fractions import Fraction

from ref3_sim import simulate, fcfs, priority, tape_chooser, audit, bookkeeping
from ref3_thm3 import upper_family, lower_family

OUT = []


def p(*args):
    s = " ".join(str(x) for x in args)
    OUT.append(s)
    print(s)


def lindley(a, x):
    """k=1 FCFS waiting times."""
    W = []
    free = 0
    for j in range(len(a)):
        s = max(a[j], free)
        W.append(s - a[j])
        free = s + x[j]
    return W


def main():
    p("=" * 78)
    p("REFEREE-3 SIMULATOR VALIDATION")
    p("=" * 78)
    p("")
    rnd = random.Random(31337)

    # 1. k=1 FCFS vs Lindley
    bad = 0
    for _ in range(20000):
        n = rnd.randint(1, 12)
        a = sorted(rnd.randint(0, 20) for _ in range(n))
        x = [rnd.randint(0, 9) for _ in range(n)]
        r = simulate(a, x, 1, fcfs)
        W = [r['s'][i] - a[i] for i in range(n)]
        if W != lindley(a, x):
            bad += 1
    p("  k=1 FCFS vs the Lindley recursion : 20000 instances, %d mismatches" % bad)

    # 2. audits + busy-period identity on random instances, all k
    bad_audit = bad_id = checks = 0
    for _ in range(6000):
        k = rnd.randint(1, 5)
        n = rnd.randint(1, 12)
        a = sorted(rnd.randint(0, 15) for _ in range(n))
        x = [rnd.randint(0, 7) for _ in range(n)]
        tape = [rnd.randint(0, 9) for _ in range(3 * n)]
        rP = simulate(a, x, k, tape_chooser(tape))
        rF = simulate(a, x, k, fcfs)
        bad_audit += len(audit(rP)) + len(audit(rF))
        if max(x) == 0:
            continue
        for i in range(n):
            b = bookkeeping(rP, rF, i)
            checks += 1
            if k * b['W_P'] != b['R_P'] + b['In'] - b['Out'] - b['rho_P']:
                bad_id += 1
            if b['D'] != (b['R_P'] - b['R_F']) - b['rho_P'] + b['rho_F']:
                bad_id += 1
            if abs(b['D']) > 2 * (k - 1) * max(x):
                bad_id += 1
    p("  work-conservation / non-preemption audit, k<=5 : 6000 instances x 2"
      " policies, %d failures" % bad_audit)
    p("  busy-period identity + decomposition + Theorem 1 : %d job-checks, %d"
      " failures" % (checks, bad_id))

    # 3. my simulator vs the note's sim_core.py
    sys.path.insert(0, "../guard_theory")
    try:
        import sim_core
        ok = True
    except Exception as e:                    # pragma: no cover
        p("  (sim_core.py could not be imported: %s)" % e)
        ok = False
    if ok:
        mism = 0
        n_cmp = 0
        for _ in range(4000):
            k = rnd.randint(1, 4)
            n = rnd.randint(1, 10)
            a = sorted(rnd.randint(0, 12) for _ in range(n))
            x = [rnd.randint(0, 6) for _ in range(n)]
            jobs = list(zip(a, x))
            prio = [rnd.randint(0, 5) for _ in range(n)]

            def mine(t, waiting, ctx):
                return min(waiting, key=lambda j: (prio[j], j))

            def theirs(t, waiting, state):
                best = 0
                for c in range(1, len(waiting)):
                    if (prio[waiting[c]], waiting[c]) < (prio[waiting[best]],
                                                         waiting[best]):
                        best = c
                return best
            r1 = simulate(a, x, k, mine)
            s2, o2, _ = sim_core.simulate(jobs, k, theirs)
            n_cmp += 1
            if list(r1['s']) != list(s2):
                mism += 1
            f1, _, _ = sim_core.simulate(jobs, k, sim_core.fcfs)
            rF = simulate(a, x, k, fcfs)
            if list(rF['s']) != list(f1):
                mism += 1
        p("  ref3_sim.py vs the note's sim_core.py (start times, FCFS and a"
          " random static priority) : %d instances, %d mismatches" % (n_cmp, mism))

    # 4. diff the family instances
    p("")
    p("  diff of MY family reconstruction against family_tight.py:")
    if ok:
        import family_tight
        for (k, L, m) in ((2, 64, 3), (2, 64, 6), (3, 81, 4), (4, 64, 3)):
            a, x, vic, Tm = upper_family(k, L, m)
            jobs, prio, v2 = family_tight.build_upper(k, L, m, 1, ntiny=2 * k * L + 1)
            same = (list(zip(a, x)) == jobs) and (vic == v2)
            a2, x2, vic2, fl, Tm2, f = lower_family(k, L, m)
            jobs2, prio2, v3 = family_tight.build_lower(k, L, m, 1)
            same2 = (list(zip(a2, x2)) == jobs2) and (vic2 == v3)
            p("    k=%d L=%d m=%d : upper instance identical = %s ;"
              " lower instance identical = %s" % (k, L, m, same, same2))
    p("")
    with open("out_validate.txt", "w") as fh:
        fh.write("\n".join(OUT) + "\n")


if __name__ == "__main__":
    main()
