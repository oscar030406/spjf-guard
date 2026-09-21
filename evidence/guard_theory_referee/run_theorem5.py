"""Attack on Theorem 5 (consistency) and on the worst constants' witnesses.

(a) is stated in theory.md as an EXACT CHARACTERISATION ("iff"):
      guard(A,B) == A  <=>  over_q(t) < B for every waiting q at every
                            dispatch instant t of the base run.
    The "=>" direction is attacked here by exhaustive enumeration of small
    instances over all deterministic bases realisable by a choice tape.
(b) max_i In^A_i < B  ==>  guard(A,B) == A
(c) excess_A <= G for all i  and  B > kG + (3k-2)L  ==>  guard(A,B) == A
    plus: does the guard ever FIRE (E(t) non-empty) in that regime?
    plus: is the threshold sharp, i.e. does B = kG + (3k-2)L (not strict) or
          B = max In^A (not strict) already change the run?
"""
import sys, itertools, random
sys.dont_write_bytecode = True
from fractions import Fraction
from refsim2 import (simulate, fcfs_chooser, make_choice_chooser,
                     make_guard_choice_chooser, in_out)


def guard_fires_anywhere(a, x, k, tape, B, n):
    """run guard(A,B) and record whether E(t) was ever non-empty."""
    fired = [False]

    def ch(t, waiting, state):
        comp = state['comp']
        suf = [0] * (n + 1)
        for j in range(n - 1, -1, -1):
            suf[j] = suf[j + 1] + (x[j] if (comp[j] != -1 and comp[j] <= t) else 0)
        E = [q for q in waiting if suf[q + 1] >= B]
        if E:
            fired[0] = True
            return min(E)
        p = len(state['order'])
        w = sorted(waiting)
        return w[tape[p] % len(w)]
    st, cp, od = simulate(a, x, k, ch)
    return st, cp, od, fired[0]


def base_condition_holds(a, x, k, tape, B, n):
    """check theory.md 5(a)'s condition on the BASE run: over_q(t) < B for
    every waiting q at every dispatch instant t."""
    ok = [True]

    def ch(t, waiting, state):
        comp = state['comp']
        suf = [0] * (n + 1)
        for j in range(n - 1, -1, -1):
            suf[j] = suf[j + 1] + (x[j] if (comp[j] != -1 and comp[j] <= t) else 0)
        for q in waiting:
            if suf[q + 1] >= B:
                ok[0] = False
        p = len(state['order'])
        w = sorted(waiting)
        return w[tape[p] % len(w)]
    st, cp, od = simulate(a, x, k, ch)
    return st, cp, od, ok[0]


def main():
    log = open("out_theorem5.txt", "w")
    # ---------------- (a) the "iff" -------------------------------------
    log.write("=== Theorem 5(a): is the characterisation really an 'iff'? ===\n")
    ce = None
    nchk = 0
    ndiff = 0
    random.seed(11)
    insts = []
    for n in range(2, 6):
        for _ in range(500):
            a = sorted(random.randint(0, 3) for _ in range(n))
            x = [random.randint(1, 3) for _ in range(n)]
            insts.append((a, x))
    for (a, x) in insts:
        n = len(a)
        L = max(x)
        for k in (1, 2, 3):
            for tape in itertools.product(range(n), repeat=min(n, 4)):
                tp = list(tape) + [0] * n
                bst, bcp, bod = simulate(a, x, k, make_choice_chooser(tp))
                for B in range(0, 3 * L * k + 2):
                    nchk += 1
                    _, _, _, cond = base_condition_holds(a, x, k, tp, B, n)
                    gst, gcp, god, fired = guard_fires_anywhere(a, x, k, tp, B, n)
                    same = (gst == bst and god == bod)
                    if same and not cond and ce is None:
                        ce = (a, x, k, tp[:n], B, bod, god)
                    if (not same) and cond:
                        log.write("  '<=' DIRECTION BROKEN %r\n"
                                  % ((a, x, k, tp[:n], B, bod, god),))
                        ndiff += 1
                if ce is not None and nchk > 20000:
                    break
            if ce is not None and nchk > 20000:
                break
        if ce is not None and nchk > 20000:
            break
    log.write("  checks: %d ; violations of the '<=' (sufficient) direction: %d\n"
              % (nchk, ndiff))
    if ce:
        a, x, k, tp, B, bod, god = ce
        log.write("  '=>' DIRECTION FALSE.  Smallest witness found:\n")
        log.write("     a=%s x=%s k=%d base-tape=%s B=%d\n" % (a, x, k, tp, B))
        log.write("     base dispatch order  = %s\n" % bod)
        log.write("     guard dispatch order = %s  (IDENTICAL run)\n" % god)
        log.write("     but the base run has a waiting q with over_q(t) >= B\n")
    # the hand-made minimal one
    a, x, k, tp, B = [0, 0], [1, 1], 1, [1, 0], 1
    bst, bcp, bod = simulate(a, x, k, make_choice_chooser(tp))
    gst, gcp, god, fired = guard_fires_anywhere(a, x, k, tp, B, 2)
    _, _, _, cond = base_condition_holds(a, x, k, tp, B, 2)
    log.write("  hand-made minimal: k=1, a=[0,0], x=[1,1], base=LIFO, B=1\n")
    log.write("     base starts %s order %s ; guard starts %s order %s ; "
              "identical=%s ; 5(a) condition holds in base run=%s ; "
              "guard actually fired=%s\n"
              % (bst, bod, gst, god, (bst == gst and bod == god), cond, fired))

    # ---------------- (b) and (c) ---------------------------------------
    log.write("\n=== Theorem 5(b) max In^A < B  ==>  guard == base ===\n")
    log.write("=== Theorem 5(c) excess_A <= G, B > kG+(3k-2)L ==> guard == base ===\n")
    nb = nc = 0
    fb = fc = 0
    fired_c = 0
    sharp_b = sharp_b_tot = 0
    sharp_c = sharp_c_tot = 0
    random.seed(23)
    for trial in range(30000):
        n = random.randint(1, 7)
        k = random.randint(1, 4)
        a = sorted(random.randint(0, 5) for _ in range(n))
        x = [random.randint(0, 4) for _ in range(n)]
        if max(x) == 0:
            continue
        L = max(x)
        tp = [random.randint(0, 6) for _ in range(n)]
        bst, bcp, bod = simulate(a, x, k, make_choice_chooser(tp))
        fst, fcp, fod = simulate(a, x, k, fcfs_chooser)
        In, Out = in_out(x, bod, n)
        G = max(bst[i] - fst[i] for i in range(n))
        mi = max(In)
        # (b)
        B = mi + 1
        gst, gcp, god, fired = guard_fires_anywhere(a, x, k, tp, B, n)
        nb += 1
        if not (gst == bst and god == bod):
            fb += 1
            log.write("  5(b) FAILS a=%s x=%s k=%d tape=%s B=%d\n" % (a, x, k, tp, B))
        # sharpness of (b): B = max In^A exactly
        gst2, _, god2, _ = guard_fires_anywhere(a, x, k, tp, mi, n)
        sharp_b_tot += 1
        if not (gst2 == bst and god2 == bod):
            sharp_b += 1
        # (c)
        thr = k * G + (3 * k - 2) * L
        B = thr + 1
        gst, gcp, god, fired = guard_fires_anywhere(a, x, k, tp, B, n)
        nc += 1
        if not (gst == bst and god == bod):
            fc += 1
            log.write("  5(c) FAILS a=%s x=%s k=%d tape=%s G=%d L=%d B=%d\n"
                      % (a, x, k, tp, G, L, B))
        if fired:
            fired_c += 1
            log.write("  5(c) guard FIRED although base is G-robust and B>thr: "
                      "a=%s x=%s k=%d tape=%s G=%d L=%d B=%d\n"
                      % (a, x, k, tp, G, L, B))
        # sharpness of (c): B = threshold exactly (not strictly greater)
        gst2, _, god2, _ = guard_fires_anywhere(a, x, k, tp, thr, n)
        sharp_c_tot += 1
        if not (gst2 == bst and god2 == bod):
            sharp_c += 1
    log.write("  5(b) checks=%d failures=%d\n" % (nb, fb))
    log.write("  5(c) checks=%d failures=%d ; runs where E(t) ever fired=%d\n"
              % (nc, fc, fired_c))
    log.write("  sharpness: B = max In^A exactly changes the run in %d/%d cases\n"
              % (sharp_b, sharp_b_tot))
    log.write("  sharpness: B = kG+(3k-2)L exactly changes the run in %d/%d cases\n"
              % (sharp_c, sharp_c_tot))
    log.close()
    print(open("out_theorem5.txt").read())


if __name__ == "__main__":
    main()
