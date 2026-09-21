"""Minimal counterexamples, printed in full and re-verified with the
pure-python reference simulator.

CE1  the sentence "Theorem 1 ... holds with L replaced by the running prefix
     maximum" (Prop 8) is false for the LOWER direction when the prefix
     maximum is read at a_i, as Prop 8 defines it.
CE2  Theorem 2 with L -> Lpref(i) is false for the same reason (Lemma 2's
     "the last one adds <= L" charges a job that arrived after a_i).
CE3  Theorem 5(a) is stated as an "iff"; the "=>" direction is false.
CE4  worst-case witnesses for the constant of Theorem 1.
"""
import sys
sys.dont_write_bytecode = True
from refsim2 import (simulate, fcfs_chooser, make_choice_chooser,
                     make_guard_choice_chooser, in_out)


def show(a, x, k, tape, label, log):
    n = len(a)
    fst, fcp, fod = simulate(a, x, k, fcfs_chooser)
    st, cp, od = simulate(a, x, k, make_choice_chooser(tape))
    In, Out = in_out(x, od, n)
    L = max(x)
    WF = [fst[i] - a[i] for i in range(n)]
    WP = [st[i] - a[i] for i in range(n)]
    exc = [WP[i] - WF[i] for i in range(n)]
    G = max(exc)
    log.write("%s\n" % label)
    log.write("  k=%d  a=%s  x=%s  L=%d\n" % (k, a, x, L))
    log.write("  FCFS  order=%s starts=%s W=%s\n" % (fod, fst, WF))
    log.write("  P     order=%s starts=%s W=%s\n" % (od, st, WP))
    log.write("  excess=%s   G=max excess=%d\n" % (exc, G))
    log.write("  In =%s\n  Out=%s\n" % (In, Out))
    for i in range(n):
        D = k * exc[i] - (In[i] - Out[i])
        lp = max(x[j] for j in range(n) if a[j] <= a[i])
        log.write("   i=%d  D=%d   2(k-1)L=%d   Lpref(a_i)=%d  "
                  "2(k-1)Lpref=%d  [T1 ok=%s, prefix-form ok=%s]  "
                  "In=%d  kG+(3k-2)L=%d  kG+(3k-2)Lpref=%d [T2 ok=%s, "
                  "prefix-form ok=%s]\n"
                  % (i, D, 2 * (k - 1) * L, lp, 2 * (k - 1) * lp,
                     abs(D) <= 2 * (k - 1) * L, abs(D) <= 2 * (k - 1) * lp,
                     In[i], k * G + (3 * k - 2) * L, k * G + (3 * k - 2) * lp,
                     In[i] <= k * G + (3 * k - 2) * L,
                     In[i] <= k * G + (3 * k - 2) * lp))
    log.write("\n")
    return st, od, In, Out, exc, G


def main():
    log = open("out_ce.txt", "w")
    log.write("=== CE1/CE2: Prop 8's 'L -> running prefix maximum' sentence ===\n")
    log.write("Family: k=2, jobs (rank order)  0:(a=0,x=1) 1:(a=0,x=1) "
              "2:(a=0,x=1) 3:(a=1,x=M).\n"
              "P dispatches 1,2 at t=0 (so the victim 0 waits) and at t=1 "
              "dispatches the huge job 3 before 0.\n"
              "FCFS dispatches 0,1 at t=0.  Lpref(a_0)=1 for every M.\n\n")
    for M in (3, 5, 10, 100, 1000):
        # tape: at dispatch 1 pick index1 of [0,1,2] -> job1; then [0,2] -> job2;
        # at t=1 waiting [0,3] -> pick index1 = job3; then job0.
        show([0, 0, 0, 1], [1, 1, 1, M], 2, [1, 1, 1, 0],
             "M = %d" % M, log)

    log.write("=== CE3: Theorem 5(a) is not an 'iff' ===\n")
    a, x, k, B = [0, 0], [1, 1], 1, 1
    tape = [1, 0]          # base = dispatch the higher-rank job first (LIFO)
    bst, bcp, bod = simulate(a, x, k, make_choice_chooser(tape))
    n = 2
    fired = [False]
    cond_fail = [False]

    def gch(t, waiting, state):
        comp = state['comp']
        suf = [0] * (n + 1)
        for j in range(n - 1, -1, -1):
            suf[j] = suf[j + 1] + (x[j] if (comp[j] != -1 and comp[j] <= t) else 0)
        E = [q for q in waiting if suf[q + 1] >= B]
        if E:
            fired[0] = True
            return min(E)
        p = len(state['order'])
        return sorted(waiting)[tape[p] % len(waiting)]
    gst, gcp, god = simulate(a, x, k, gch)

    def bch(t, waiting, state):
        comp = state['comp']
        suf = [0] * (n + 1)
        for j in range(n - 1, -1, -1):
            suf[j] = suf[j + 1] + (x[j] if (comp[j] != -1 and comp[j] <= t) else 0)
        for q in waiting:
            if suf[q + 1] >= B:
                cond_fail[0] = True
        p = len(state['order'])
        return sorted(waiting)[tape[p] % len(waiting)]
    simulate(a, x, k, bch)
    log.write("  k=1, a=[0,0], x=[1,1], base A = 'dispatch the higher rank "
              "first', B=1.\n")
    log.write("  base  : order=%s starts=%s\n" % (bod, bst))
    log.write("  guard : order=%s starts=%s\n" % (god, gst))
    log.write("  runs identical                        : %s\n"
              % (bod == god and bst == gst))
    log.write("  guard's fired set E(t) was non-empty  : %s\n" % fired[0])
    log.write("  5(a)'s condition 'over_q(t) < B for every waiting q at every\n"
              "  dispatch instant of the BASE run' holds: %s\n" % (not cond_fail[0]))
    log.write("  => the 'only if' half of Theorem 5(a) is false: the run can be\n"
              "     identical while the condition fails (the guard fires and\n"
              "     happens to choose exactly what the base would have chosen).\n"
              "     The half that Theorem 5(b),(c) actually use is the other one\n"
              "     and it survives.\n\n")

    log.write("=== CE4: witnesses for the worst constant of Theorem 1 ===\n")
    log.write("  (these are NOT violations; they are the largest |D|/L found)\n")
    show([0, 0, 0, 0], [3, 3, 3, 3], 4, [1, 1, 1, 0],
         "k=4, four jobs of size L at t=0, victim = rank 0 dispatched last: "
         "|D| = (k-1)L", log)
    show([0, 0, 0, 0, 0], [2, 2, 2, 1, 2], 4, [1, 1, 1, 1, 0],
         "k=4, L=2 probe", log)
    log.close()
    print(open("out_ce.txt").read())


if __name__ == "__main__":
    main()
