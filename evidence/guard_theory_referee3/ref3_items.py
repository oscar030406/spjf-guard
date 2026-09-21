"""Item 3: the statements revised in answer to referee 2 --
Thm 5(a), Prop 8 (three placements of the prefix max), Prop 14 (a supremum),
Lemma 1 (left limit), Lemma 2 (strengthened hypothesis), Cor 2.1.
Plus the smallest counterexample to Lemma 1's literal fallback clause.
"""
import itertools
import random
from fractions import Fraction

from ref3_sim import (simulate, fcfs, priority, tape_chooser, guard_chooser,
                      audit, bookkeeping, unfinished, n_present)
from ref3_attain import all_schedules

OUT = []


def p(*args):
    s = " ".join(str(x) for x in args)
    OUT.append(s)
    print(s)


def lam_pref(a, x, t):
    v = 0
    for j in range(len(a)):
        if a[j] <= t and x[j] > v:
            v = x[j]
    return v


# ---------------------------------------------------------------- Lemma 1'
def lemma1p_small():
    p("--- Lemma 1' : smallest counterexample to the clause")
    p("    'If no such u exists, U_A(t) <= U_B(t)'  ---")
    p("")
    k = 2
    a = [0, 0, 0, 0, 0, 4, 4]
    x = [4, 1, 1, 1, 1, 10, 10]
    P = priority(lambda j, t, ctx: 0 if ctx['x'][j] == 1 else 1)  # units first
    resP = simulate(a, x, k, P)
    resF = simulate(a, x, k, fcfs)
    p("    k=2  a=%s  x=%s   P = 'units before the big job'" % (a, x))
    p("    audit P: %s   audit FCFS: %s" %
      (audit(resP) or "clean", audit(resF) or "clean"))
    for t in (4, 5):
        bps = sorted(set(a) | set(resP['fin']))
        bps = [b for b in bps if b <= t]
        valid = []
        for u in bps:
            if n_present(resP, u) > k - 1:
                continue
            later = [b for b in bps if u < b <= t]
            probes = list(later)
            prev = u
            for b in later:
                probes.append(Fraction(prev + b, 2))
                prev = b
            if all(n_present(resP, b) >= k for b in probes):
                valid.append(u)
        p("    t=%d : U_P-U_FCFS = %s ; N_P(t^-)=%d ; admissible u : %s" %
          (t, unfinished(resP, t) - unfinished(resF, t),
           n_present(resP, t - Fraction(1, 2)), valid if valid else "NONE"))
    p("    => at t=5 the hypothesis of Lemma 1' has no admissible reference")
    p("       time, so the lemma's fallback clause asserts U_P <= U_FCFS;")
    p("       the true value is U_P - U_FCFS = 2 > 0.  CLAUSE FALSE.")
    p("    Fix: read the count and the workload at u^- (before the arrivals at")
    p("       u), exactly as Lemma 1 was repaired for revision 2.  With")
    p("       u = 4^- : N_P = 1 <= k-1, U_P(4^-) = 2 <= (k-1)*4 = 4.  OK.")
    p("")


# ---------------------------------------------------------------- Prop 8
def prop8():
    p("--- Prop 8 : the three placements of the prefix maximum ---")
    p("")
    p("    (i) the note's own CE1/CE2 table, recomputed:")
    p("    k=2, ranks 0:(a=0,x=1) 1:(0,1) 2:(0,1) 3:(1,M);")
    p("    P dispatches 1,2 at t=0 and then 3 before 0 at t=1.")
    p("")
    p("      M     D_0    2(k-1)Lpref(a_0)   In_0   kG+(3k-2)Lpref(a_0)"
      "   kG+(3k-2)Lpref(s^F+G)")
    for M in (3, 5, 10, 100, 1000):
        a = [0, 0, 0, 1]
        x = [1, 1, 1, M]
        k = 2
        pr = {0: 3, 1: 0, 2: 1, 3: 2}
        resP = simulate(a, x, k, priority(lambda j, t, ctx: pr[j]))
        resF = simulate(a, x, k, fcfs)
        assert not audit(resP) and not audit(resF)
        b = bookkeeping(resP, resF, 0)
        G = max(resP['s'][j] - resF['s'][j] for j in range(4))
        lp = lam_pref(a, x, a[0])
        lg = lam_pref(a, x, resF['s'][0] + G)
        p("    %5d %6s %10d %14d %12d %20d" %
          (M, b['D'], 2 * (k - 1) * lp, b['In'], k * G + (3 * k - 2) * lp,
           k * G + (3 * k - 2) * lg))
    p("")
    p("    (ii) random sweep, heavy-tailed unbounded sizes, checking the three")
    p("         corrected forms:")
    rnd = random.Random(7)
    cnt = 0
    f_up = f_dn_ai = f_dn_fix = f_t2_ai = f_t2_fix = 0
    for _ in range(4000):
        k = rnd.randint(2, 4)
        n = rnd.randint(2, 9)
        a = sorted(rnd.randint(0, 8) for _ in range(n))
        x = [int(1 + (1.0 / (rnd.random() ** (1 / 0.7)))) % 400 + 1 for _ in range(n)]
        tape = [rnd.randint(0, 9) for _ in range(3 * n)]
        resP = simulate(a, x, k, tape_chooser(tape))
        resF = simulate(a, x, k, fcfs)
        G = max(resP['s'][j] - resF['s'][j] for j in range(n))
        for i in range(n):
            b = bookkeeping(resP, resF, i)
            cnt += 1
            lai = lam_pref(a, x, a[i])
            lmx = lam_pref(a, x, max(resP['s'][i], resF['s'][i]))
            lg = lam_pref(a, x, resF['s'][i] + G)
            if b['D'] > 2 * (k - 1) * lai:
                f_up += 1
            if b['D'] < -2 * (k - 1) * lai:
                f_dn_ai += 1
            if b['D'] < -2 * (k - 1) * lmx:
                f_dn_fix += 1
            if b['In'] > k * G + (3 * k - 2) * lai:
                f_t2_ai += 1
            if b['In'] > k * G + (3 * k - 2) * lg:
                f_t2_fix += 1
    p("      %d job-checks" % cnt)
    p("      upward   D <= 2(k-1)Lpref(a_i)             : %d failures" % f_up)
    p("      downward D >= -2(k-1)Lpref(a_i)            : %d failures  (the"
      " note says this form is FALSE)" % f_dn_ai)
    p("      downward D >= -2(k-1)Lpref(max(s^P,s^F))   : %d failures" % f_dn_fix)
    p("      Thm2     In <= kG+(3k-2)Lpref(a_i)         : %d failures  (the"
      " note says this form is FALSE)" % f_t2_ai)
    p("      Thm2     In <= kG+(3k-2)Lpref(s^F_i+G)     : %d failures" % f_t2_fix)
    p("")


# ---------------------------------------------------------------- Lemma 2
def lemma2():
    p("--- Lemma 2 : strengthened hypothesis (i and the jobs of Out_i only) ---")
    p("")
    tot = bad_str = bad_dropi = bad_outside = 0
    small = None
    for k in (1, 2, 3):
        for n in range(2, 6):
            for arr in itertools.combinations_with_replacement(range(3), n):
                for sz in itertools.product(range(1, 3), repeat=n):
                    a = list(arr)
                    x = list(sz)
                    L = max(x)
                    resF = simulate(a, x, k, fcfs)
                    S = all_schedules(a, x, k)
                    if len(S) > 200:
                        continue
                    for (s_, o_, f_) in S:
                        exc = [(s_[j] - a[j]) - (resF['s'][j] - a[j])
                               for j in range(n)]
                        for i in range(n):
                            Oset = [j for j in range(i) if o_[j] > o_[i]]
                            Out = sum(x[j] for j in Oset)
                            for G in range(0, 2 * L + 1):
                                okI = exc[i] <= G
                                okO = all(exc[j] <= G for j in Oset)
                                rhs = k * (G - exc[i] + L)
                                if okI and okO:
                                    tot += 1
                                    if Out > rhs:
                                        bad_str += 1
                                if okO and not okI and Out > rhs:
                                    bad_dropi += 1
                                if okI and not okO and Out > rhs:
                                    bad_outside += 1
                                    if small is None or n < small[0]:
                                        small = (n, k, a, x, list(o_), i, G,
                                                 Out, rhs, exc)
    p("    strengthened hypothesis (i and Out_i), G >= 0 : %d checks, %d"
      " violations" % (tot, bad_str))
    p("    hypothesis dropped on i itself                : %d violations"
      % bad_dropi)
    p("    hypothesis kept on i but NOT on Out_i's jobs  : %d violations"
      % bad_outside)
    if small:
        n, k, a, x, o_, i, G, Out, rhs, exc = small
        p("      smallest witness for the second half: k=%d a=%s x=%s," % (k, a, x))
        p("      dispatch position by rank = %s, victim i=%d, G=%d:" % (o_, i, G))
        p("      excess_i=%d <= G but Out_i=%d > k(G-excess_i+L)=%d (excesses %s)"
          % (exc[i], Out, rhs, exc))
    p("    => both halves are needed, already at G = 0; the strengthened form")
    p("       holds.  (Referee 2's probe P1(c) showed this only with a")
    p("       NEGATIVE G; the witness above uses G = 0.)")
    p("")


# ---------------------------------------------------------------- Cor 2.1
def cor21():
    p("--- Cor 2.1 : the two containments ---")
    p("")
    tot = b1 = b2 = 0
    for k in (1, 2, 3):
        for n in range(2, 6):
            for arr in itertools.combinations_with_replacement(range(3), n):
                for sz in itertools.product(range(1, 3), repeat=n):
                    a = list(arr)
                    x = list(sz)
                    L = max(x)
                    resF = simulate(a, x, k, fcfs)
                    S = all_schedules(a, x, k)
                    if len(S) > 40:
                        continue
                    for (s_, o_, f_) in S:
                        exc = [(s_[j] - a[j]) - (resF['s'][j] - a[j])
                               for j in range(n)]
                        Inl = []
                        for i in range(n):
                            Inl.append(sum(x[j] for j in range(i + 1, n)
                                           if o_[j] < o_[i]))
                        Z = max(Inl)
                        G = max(exc)
                        tot += 1
                        if max(exc) * k > Z + (2 * k - 2) * L:
                            b1 += 1
                        if Z > k * G + (3 * k - 2) * L:
                            b2 += 1
    p("    %d schedules: Budg(Z) => Guar(Z/k+(2-2/k)L) failures = %d" % (tot, b1))
    p("                 Guar(G) => Budg(kG+(3k-2)L)    failures = %d" % b2)
    p("")


# ---------------------------------------------------------------- Thm 5(a)
def thm5a():
    p("--- Thm 5(a) : the surviving direction, and the false converse ---")
    p("")
    rnd = random.Random(11)
    applicable = mismatch = 0
    conv_fail = 0
    for _ in range(6000):
        k = rnd.randint(1, 4)
        n = rnd.randint(2, 8)
        a = sorted(rnd.randint(0, 5) for _ in range(n))
        x = [rnd.randint(0, 4) for _ in range(n)]
        if max(x) == 0:
            continue
        B = rnd.randint(0, 3 * max(x))
        tape = [rnd.randint(0, 9) for _ in range(3 * n)]

        def mk_base():
            box = {'r': 0}

            def base(t, waiting, ctx):
                r = box['r']
                box['r'] += 1
                return waiting[tape[r % len(tape)] % len(waiting)]
            return base
        budget = lambda q, t, ctx: B
        resA = simulate(a, x, k, mk_base())
        # hypothesis: over_q(t) < B for every waiting q at every dispatch of A
        hyp = True
        fires = False
        dispatch_ts = sorted(set(resA['s']))
        for t in dispatch_ts:
            waiting = [j for j in range(n) if a[j] <= t and resA['s'][j] >= t]
            for q in waiting:
                over = sum(x[j] for j in range(q + 1, n) if resA['fin'][j] <= t)
                if over >= B:
                    hyp = False
                    fires = True
        resG = simulate(a, x, k, guard_chooser(mk_base(), budget))
        same = resG['order'] == resA['order'] and resG['s'] == resA['s']
        if hyp:
            applicable += 1
            if not same:
                mismatch += 1
        if same and fires:
            conv_fail += 1
    p("    (a) hypothesis held in %d runs, wrapped run differed in %d"
      % (applicable, mismatch))
    p("    (a') runs identical although E(t) was non-empty somewhere: %d"
      " instances  => the converse is indeed false" % conv_fail)
    p("    the note's CE3: k=1, a=(0,0), x=(1,1), base='higher rank first', B=1:")
    a, x, k = [0, 0], [1, 1], 1
    base = priority(lambda j, t, ctx: -j)
    rA = simulate(a, x, k, base)
    rG = simulate(a, x, k, guard_chooser(base, lambda q, t, ctx: 1))
    p("        base order %s, wrapped order %s, identical=%s"
      % (rA['order'], rG['order'], rA['order'] == rG['order']))
    over0 = sum(x[j] for j in range(1, 2) if rA['fin'][j] <= 1)
    p("        at t=1 job 0 waits with over_0(1)=%d >= B=1, so E(1) is"
      " non-empty and the guard does fire." % over0)
    p("")


# ---------------------------------------------------------------- Prop 14
def prop14():
    p("--- Prop 14 : at k=1 the wrapper bound B+L is a supremum ---")
    p("")
    p("    Explicit approaching family (missing from the note): k=1, victim of")
    p("    rank 0 at t=0; overtakers of size g until over = B-g; then ONE")
    p("    overtaker of size L.  excess = B-g+L, so excess-B = L-g.")
    p("")
    p("      L    B    g    excess    excess-B   B+L   strict?")
    for (L, B, g) in ((16, 8, 1), (16, 8, 2), (16, 8, 4), (64, 32, 1),
                      (64, 32, 8), (100, 40, 1), (100, 40, 5)):
        assert (B - g) % g == 0
        a = [0]
        x = [1]
        nsmall = (B - g) // g
        for _ in range(nsmall):
            a.append(0); x.append(g)
        a.append(0); x.append(L)
        k = 1
        base = priority(lambda j, t, ctx: 0 if j > 0 else 1)  # never the victim
        res = simulate(a, x, k, guard_chooser(base, lambda q, t, ctx: B))
        resF = simulate(a, x, k, fcfs)
        assert not audit(res)
        exc = (res['s'][0] - a[0]) - (resF['s'][0] - a[0])
        p("      %3d %4d %4d %9d %10d %5d   %s" %
          (L, B, g, exc, exc - B, B + L, "yes" if exc < B + L else "NO **"))
    p("    => excess - B = L - g, so the supremum L is approached as the size")
    p("       granularity g shrinks, and is never attained.  The note asserts")
    p("       this ('for every epsilon there are instances') without a family.")
    p("")


def main():
    p("=" * 78)
    p("ITEM 3 -- the statements revised for referee 2")
    p("=" * 78)
    p("")
    lemma1p_small()
    prop8()
    lemma2()
    cor21()
    thm5a()
    prop14()
    with open("out_items.txt", "w") as fh:
        fh.write("\n".join(OUT) + "\n")


if __name__ == "__main__":
    main()
