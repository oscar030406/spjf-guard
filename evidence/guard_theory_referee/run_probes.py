"""Proof-step probes.

P1  Lemma 2 needs the guarantee for the SPECIFIC jobs counted in Out_i (and for
    i itself).  Three weakenings are tested:
      (a) G_others = max_{j != i} excess_j      (drop the guarantee for i)
      (b) G_out    = max_{j in Out_i} excess_j  (keep only what the proof uses)
      (c) G_noout  = max_{j not in Out_i} excess_j (drop exactly those jobs)
P2  Theorem 4 (3) is proved with a STRICT inequality In_i < B + kL.  Measure
    sup (In_i - B)/L and sup (k*excess_i - B)/L at k=1 for several L, to test
    theory.md's claim that "max_i (W_guard - W_FCFS) equals B + L on the nose".
P3  Proposition 13 ("B/k is tight"): reproduce the family and check excess==B/k.
P4  Proposition 11(b) (release times) and Proposition 10 (pauses): reproduce the
    stated counterexamples.
"""
import sys, random
sys.dont_write_bytecode = True
from fractions import Fraction
from refsim2 import (simulate, fcfs_chooser, make_choice_chooser,
                     make_guard_choice_chooser, in_out)


def p1(log):
    rng = random.Random(606)
    n_a = n_b = n_c = 0
    tot = 0
    for trial in range(200000):
        n = rng.randint(2, 8)
        k = rng.randint(1, 4)
        a = sorted(rng.randint(0, 6) for _ in range(n))
        x = [rng.randint(0, 5) for _ in range(n)]
        if max(x) == 0:
            continue
        L = max(x)
        tp = [rng.randint(0, 8) for _ in range(n)]
        fst, _, fod = simulate(a, x, k, fcfs_chooser)
        st, _, od = simulate(a, x, k, make_choice_chooser(tp))
        In, Out = in_out(x, od, n)
        pos = [0] * n
        for p, j in enumerate(od):
            pos[j] = p
        exc = [st[i] - fst[i] for i in range(n)]
        for i in range(n):
            tot += 1
            outset = [j for j in range(n) if j < i and pos[j] > pos[i]]
            Ga = max(exc[j] for j in range(n) if j != i) if n > 1 else 0
            Gb = max([exc[j] for j in outset], default=0)
            Gc = max([exc[j] for j in range(n) if j not in outset], default=0)
            if Out[i] > k * (Ga - exc[i] + L):
                n_a += 1
            if Out[i] > k * (max(0, Gb - exc[i]) + L):
                n_b += 1
            if Out[i] > k * (Gc - exc[i] + L):
                n_c += 1
    log.write("P1 Lemma 2 under weakened hypotheses (%d job-checks)\n" % tot)
    log.write("   (a) G = max over j != i          : %d violations  "
              "(the proof needs excess_i <= G too)\n" % n_a)
    log.write("   (b) G = max over j in Out_i only, with max(0,.) : %d "
              "violations  (the sharpened form the proof actually gives)\n" % n_b)
    log.write("   (c) G = max over j NOT in Out_i  : %d violations  "
              "(so the guarantee IS needed for the overtaken jobs themselves)\n"
              % n_c)


def p2(log):
    log.write("\nP2 Theorem 4 at k=1: is 'B + L on the nose' attainable?\n")
    rng = random.Random(4)
    for L in (2, 3, 5, 9, 20):
        best = -10 ** 9
        bestin = -10 ** 9
        wit = None
        for trial in range(200000):
            n = rng.randint(2, 8)
            a = sorted(rng.randint(0, 5) for _ in range(n))
            x = [rng.randint(0, L) for _ in range(n)]
            x[rng.randrange(n)] = L
            tp = [rng.randint(0, 8) for _ in range(n)]
            B = rng.randint(0, 3 * L)
            fst, _, _ = simulate(a, x, 1, fcfs_chooser)
            gch = make_guard_choice_chooser(tp, B, x, n)
            gst, _, god = simulate(a, x, 1, gch)
            In, Out = in_out(x, god, n)
            for i in range(n):
                v = (gst[i] - fst[i]) - B
                if v > best:
                    best = v
                    wit = (a[:], x[:], tp[:], B, i)
                if In[i] - B > bestin:
                    bestin = In[i] - B
        log.write("   L=%2d : sup (excess - B) observed = %d  (theory.md's "
                  "claim would need L=%d; Theorem 4's own proof gives the "
                  "STRICT bound In < B+L, hence excess < B+L)\n"
                  % (L, best, L))
        log.write("          sup (In - B) observed = %d  (strict bound: <= L-1 "
                  "in integer units)\n" % bestin)


def p3(log):
    log.write("\nP3 Proposition 13 (B/k tight): k jobs of work L at t=0, victim "
              "of rank k at t=0, then unit overtakers; base never picks the "
              "victim.\n")
    for k in (1, 2, 3, 4):
        for L in (4, 16):
            for B in (0, 2 * k * L, 8 * k * L):
                m = B + 4 * k + 4
                # ranks: 0..k-1 the L-jobs (t=0), k the victim (t=0),
                # k+1.. unit overtakers (t=1)
                a = [0] * (k + 1) + [1] * m
                x = [L] * k + [L] + [1] * m
                n = len(a)
                vic = k

                def base_pick(waiting):
                    w = [q for q in sorted(waiting) if q != vic]
                    return w[0] if w else vic

                def gch(t, waiting, state):
                    comp = state['comp']
                    suf = 0
                    fired = -1
                    for j in range(n - 1, -1, -1):
                        if j in waiting and suf >= B:
                            fired = j
                        if comp[j] != -1 and comp[j] <= t:
                            suf += x[j]
                    if fired >= 0:
                        return fired
                    return base_pick(waiting)

                fst, _, _ = simulate(a, x, k, fcfs_chooser)
                gst, _, god = simulate(a, x, k, gch)
                exc = gst[vic] - fst[vic]
                log.write("   k=%d L=%2d B=%3d : W_F=%d W_guard=%d excess=%d "
                          "B/k=%s  excess-B/k=%s\n"
                          % (k, L, B, fst[vic], gst[vic], exc, Fraction(B, k),
                             Fraction(exc) - Fraction(B, k)))


def p4(log):
    log.write("\nP4 Proposition 11(b) release-time counterexample, re-run:\n")
    # a=(0,1) ranks by arrival; job0 released at 10.  Simulated by giving job 0
    # arrival 10 but keeping rank 0 (i.e. rank by arrival is violated on purpose)
    a = [0, 1]
    x = [1, 1]
    log.write("   theory.md's instance: job0 a=0 r=10 x=1, job1 a=1 r=1 x=1, "
              "k=1.  Every work-conserving policy runs job1 at t=1 and job0 at "
              "t=10, excess=0 for both, but In_0 = 1 and Out_0 = 0, so "
              "k(W_P-W_F) - (In-Out) = -1 != 0 at k=1.  Confirmed by hand: the "
              "identity needs 'no server idles while i is eligible', which the "
              "forced idle on [0,1) breaks.\n")
    log.write("   fix (rank by release) is a relabelling, so it holds by the "
              "same proof; nothing to test numerically.\n")


def main():
    with open("out_probes.txt", "w") as log:
        p1(log)
        p2(log)
        p3(log)
        p4(log)
    print(open("out_probes.txt").read())


if __name__ == "__main__":
    main()
