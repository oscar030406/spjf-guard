"""Re-validate the referee simulator BEFORE using it for any certified number.

(1) FCFS at k=1 against the Lindley recursion.
(2) FCFS at k>=2 against the Kiefer-Wolfowitz workload-vector recursion.
(3) invariants: no server idle while a job waits, busy<=k, total executed work.
(4) cross-check against the PREDECESSOR referee's independent simulator
    (guard_variants_referee/refsim.py), which is itself re-validated here by
    (1)-(2) through its own fcfs policy.
(5) the enumerator: FCFS and any explicit chooser must appear among the
    enumerated schedules, and the enumerated set must contain no duplicates.
"""
import sys, os, random
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "guard_variants_referee"))
from refsim2 import (simulate, fcfs_chooser, make_score_chooser,
                     make_guard_chooser, enumerate_schedules, in_out)
import refsim as pred_ref


def lindley(a, x):
    """k=1 FCFS start times, from the Lindley recursion."""
    n = len(a)
    st = [0] * n
    free = a[0]
    for i in range(n):
        st[i] = max(a[i], free)
        free = st[i] + x[i]
    return st


def kiefer_wolfowitz(a, x, k):
    """k-server FCFS start times: V = sorted vector of server availability."""
    n = len(a)
    V = [a[0]] * k
    st = [0] * n
    for i in range(n):
        V.sort()
        s = max(a[i], V[0])
        st[i] = s
        V[0] = s + x[i]
    return st


def check_invariants(a, x, k, start, comp):
    n = len(a)
    for j in range(n):
        assert start[j] >= a[j]
        assert comp[j] == start[j] + x[j], (j, start[j], comp[j], x[j])
    T = max(comp) if comp else 0
    pts = sorted(set(a) | set(start) | set(comp))
    for t in pts:
        busy = sum(1 for j in range(n) if start[j] <= t < comp[j])
        wait = sum(1 for j in range(n) if a[j] <= t < start[j])
        assert busy <= k, ("overload", a, x, k, t)
        assert not (busy < k and wait > 0), ("idle+waiting", a, x, k, t, start)
    assert sum(comp[j] - start[j] for j in range(n)) == sum(x)


def main():
    random.seed(20260919)
    n1 = n2 = n3 = n4 = n5 = 0
    bad = 0
    for trial in range(20000):
        n = random.randint(1, 7)
        k = random.randint(1, 4)
        L = random.choice([1, 2, 3, 5])
        a = sorted(random.randint(0, 6) for _ in range(n))
        x = [random.randint(0, L) for _ in range(n)]
        st, cp, od = simulate(a, x, k, fcfs_chooser)
        check_invariants(a, x, k, st, cp)
        n3 += 1
        if k == 1:
            if st != lindley(a, x):
                bad += 1
                print("LINDLEY MISMATCH", a, x, st, lindley(a, x))
            n1 += 1
        if st != kiefer_wolfowitz(a, x, k):
            bad += 1
            print("KW MISMATCH", a, x, k, st, kiefer_wolfowitz(a, x, k))
        n2 += 1
        # FCFS must have In = Out = 0 (theory.md step 3 of Theorem 1)
        In, Out = in_out(x, od, n)
        if any(In) or any(Out):
            bad += 1
            print("FCFS In/Out nonzero", a, x, k, od, In, Out)
        # cross-check the predecessor simulator on the same input, FCFS policy
        if min(x) > 0:
            pr = list(range(n))
            ps, pc = pred_ref.simulate(list(a), list(x), pr, k, "fcfs")
            if ps != st:
                bad += 1
                print("PRED-REF FCFS MISMATCH", a, x, k, st, ps)
            n4 += 1
            # and on the guard policy with a random base prediction order
            random.shuffle(pr)
            B = random.randint(0, 3 * max(x))
            ps, pc = pred_ref.simulate(list(a), list(x), list(pr), k, "guard",
                                       B0=B, Bmax=B)
            score = [0] * n
            for r, j in enumerate(pr):
                score[j] = pr[j]
            ch = make_guard_chooser([pr[j] for j in range(n)], B, x, n)
            gs, gc, go = simulate(a, x, k, ch)
            if gs != ps:
                bad += 1
                print("PRED-REF GUARD MISMATCH", a, x, k, pr, B, gs, ps)
            n5 += 1
    print("validate: lindley k=1 checks   =", n1)
    print("validate: kiefer-wolfowitz     =", n2)
    print("validate: invariant checks     =", n3)
    print("validate: vs predecessor FCFS  =", n4)
    print("validate: vs predecessor GUARD =", n5)
    print("validate: failures             =", bad)

    # ---- enumerator sanity
    random.seed(7)
    nenum = 0
    ebad = 0
    for trial in range(400):
        n = random.randint(1, 5)
        k = random.randint(1, 3)
        a = sorted(random.randint(0, 3) for _ in range(n))
        x = [random.randint(0, 3) for _ in range(n)]
        scheds = enumerate_schedules(a, x, k)
        nenum += len(scheds)
        orders = [tuple(o) for (_, _, o) in scheds]
        if len(set(orders)) != len(orders):
            ebad += 1
            print("DUPLICATE ORDERS", a, x, k)
        st, cp, od = simulate(a, x, k, fcfs_chooser)
        if tuple(od) not in set(orders):
            ebad += 1
            print("FCFS NOT ENUMERATED", a, x, k, od, orders)
        for _ in range(5):
            sc = [random.random() for _ in range(n)]
            s2, c2, o2 = simulate(a, x, k, make_score_chooser(sc))
            if tuple(o2) not in set(orders):
                ebad += 1
                print("SCORE POLICY NOT ENUMERATED", a, x, k, o2)
            for (ss, cc, oo) in scheds:
                if tuple(oo) == tuple(o2):
                    if ss != s2:
                        ebad += 1
                        print("START MISMATCH enum vs sim", a, x, k, oo, ss, s2)
        for (ss, cc, oo) in scheds:
            check_invariants(a, x, k, ss, cc)
    print("enumerator: schedules enumerated =", nenum)
    print("enumerator: failures             =", ebad)


if __name__ == "__main__":
    main()
