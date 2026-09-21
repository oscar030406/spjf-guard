"""Item 5: the wrapper constant  c(k) = sup ( k*excess_guard[i] - B ) / L.

The note (section 6.4) reports a best-found frontier of
    c = 15/16, 31/9, 85/16, 111/16, 139/16, 21/2   for k = 1..6
and conjectures c(k) = Theta(k) with SLOPE 2 (wait-additive flat at ~1.75 L),
against the proved c(k) <= 3k-2.

This file builds an explicit family that drives c(k) -> 3k-2, i.e. the proved
constant is the exact supremum and the conjecture is false.  Idea: run the
note's own Lemma-1'' cascade (which saturates Theorem 1) and then arrange the
finale so that In_i saturates B + kL ON THE SAME INSTANCE -- exactly the
combination the note's open problem 1 asks about.

Finale at T_m (index order = rank order), all arriving at T_m:
    k-1 "new bigs"  of work L        (rank < victim)
    the victim i    of work L
    one "sync" overtaker of work f = rho_m/(k-1)
    one "pre"  overtaker of work L
    k "final" overtakers of work L
Budget B = f + L + 1.  Base policy: sync, then the new bigs and pre, then the
finals, never the victim.  The guard fires on i only at T_m + f + 2L.
"""
import random
from fractions import Fraction

from ref3_sim import (simulate, fcfs, priority, guard_chooser, audit,
                      bookkeeping, check_identity, tape_chooser)

OUT = []


def p(*args):
    s = " ".join(str(x) for x in args)
    OUT.append(s)
    print(s)


def wrapper_family(k, L, m):
    assert L % (k ** m) == 0
    a, x = [], []
    for j in range(m):
        T = j * L
        for _ in range(k - 1):
            a.append(T); x.append(L)
        for _ in range(L):
            a.append(T); x.append(1)
    Tm = m * L
    f = L - (L * (k - 1) ** m) // (k ** m)
    for _ in range(k - 1):
        a.append(Tm); x.append(L)
    victim = len(a); a.append(Tm); x.append(L)
    sync = len(a); a.append(Tm); x.append(f)
    pre = len(a); a.append(Tm); x.append(L)
    finals = []
    for _ in range(k):
        finals.append(len(a)); a.append(Tm); x.append(L)
    B = f + L + 1
    return a, x, victim, sync, pre, set(finals), Tm, f, B


def wrapper_base(k, L, m, victim, sync, pre, finals, Tm):
    def key(j, t, ctx):
        xx, aa = ctx['x'], ctx['a']
        if t < Tm:
            return 0 if xx[j] == 1 else 1
        if j == sync:
            return 0
        if j == pre or (aa[j] == Tm and j < victim):
            return 1
        if j in finals:
            return 2
        return 3                      # the victim, last
    return priority(key)


def run_family(k, L, m):
    a, x, i, sync, pre, finals, Tm, f, B = wrapper_family(k, L, m)
    base = wrapper_base(k, L, m, i, sync, pre, finals, Tm)
    res = simulate(a, x, k, guard_chooser(base, lambda q, t, ctx: B))
    resF = simulate(a, x, k, fcfs)
    bad = audit(res, L=L) + audit(resF, L=L)
    errs = check_identity(res, resF, i)
    b = bookkeeping(res, resF, i)
    exc = b['excess']
    c = Fraction(k * exc - B, L)
    return dict(k=k, L=L, m=m, n=len(a), f=f, B=B, exc=exc, c=c, b=b,
                bad=bad, errs=errs)


def hillclimb(k, L, nmax, iters, seed):
    """Independent check: hill-climb over (arrivals, sizes, base tape, B)."""
    rnd = random.Random(seed)
    best = None
    for restart in range(12):
        n = rnd.randint(4, nmax)
        a = sorted(rnd.randint(0, 3 * L) for _ in range(n))
        x = [rnd.randint(1, L) for _ in range(n)]
        x[rnd.randrange(n)] = L
        tape = [rnd.randint(0, 11) for _ in range(3 * n)]
        B = rnd.randint(0, 3 * k * L)

        def score(a, x, tape, B):
            box = {'r': 0}

            def base(t, waiting, ctx):
                r = box['r']
                box['r'] += 1
                return waiting[tape[r % len(tape)] % len(waiting)]
            try:
                res = simulate(a, x, k, guard_chooser(base, lambda q, t, c: B))
                rF = simulate(a, x, k, fcfs)
            except AssertionError:
                return None
            LL = max(x)
            if LL == 0:
                return None
            return max(Fraction(k * ((res['s'][i] - a[i]) - (rF['s'][i] - a[i]))
                                - B, LL) for i in range(len(a)))
        cur = score(a, x, tape, B)
        if cur is None:
            continue
        for it in range(iters):
            a2, x2, t2, B2 = list(a), list(x), list(tape), B
            mv = rnd.randrange(4)
            if mv == 0:
                j = rnd.randrange(len(a2)); a2[j] = max(0, a2[j] + rnd.randint(-L, L)); a2.sort()
            elif mv == 1:
                j = rnd.randrange(len(x2)); x2[j] = max(1, min(L, x2[j] + rnd.randint(-L // 2, L // 2)))
            elif mv == 2:
                j = rnd.randrange(len(t2)); t2[j] = rnd.randint(0, 11)
            else:
                B2 = max(0, B2 + rnd.randint(-L, L))
            s2 = score(a2, x2, t2, B2)
            if s2 is not None and s2 >= cur:
                a, x, tape, B, cur = a2, x2, t2, B2, s2
        if best is None or cur > best[0]:
            best = (cur, a, x, B)
    return best


def main():
    p("=" * 78)
    p("ITEM 5 -- the wrapper constant c(k) = sup (k*excess - B)/L")
    p("=" * 78)
    p("")
    p("A. explicit family (cascade + saturating finale), own simulator:")
    p("")
    p("    k    L   m     n      B    excess   c(k) found      note's best   3k-2")
    note_best = {1: Fraction(15, 16), 2: Fraction(31, 9), 3: Fraction(85, 16),
                 4: Fraction(111, 16), 5: Fraction(139, 16), 6: Fraction(21, 2)}
    rows = [(2, 64, 6), (2, 128, 7), (3, 81, 4), (3, 243, 5), (4, 64, 3),
            (4, 256, 4), (5, 125, 3), (6, 36, 2), (6, 216, 3)]
    beat = []
    for (k, L, m) in rows:
        r = run_family(k, L, m)
        flag = ""
        if r['bad']:
            flag = "  !! AUDIT: %s" % r['bad'][:2]
        if r['errs']:
            flag += "  !! IDENT: %s" % r['errs']
        p("    %d %5d %3d %6d %6d %8s   %-15s %-13s %d%s" %
          (k, L, m, r['n'], r['B'], r['exc'],
           "%s = %.4f" % (r['c'], float(r['c'])),
           "%.4f" % float(note_best[k]), 3 * k - 2, flag))
        if r['c'] > note_best[k]:
            beat.append((k, r['c'], note_best[k]))
    p("")
    p("    predicted by hand:  c = ((k-1) f + (2k-1) L - 1)/L  with")
    p("    f = L(1-((k-1)/k)^m) -> L, so c -> (k-1)+(2k-1) = 3k-2.")
    p("")
    if beat:
        p("    *** the note's best-found frontier is beaten at k = %s ***" %
          ", ".join(str(b[0]) for b in beat))
    p("")
    p("B. the same family's victim, in full (k=3, L=81, m=4):")
    r = run_family(3, 81, 4)
    b = r['b']
    p("    W_P=%s W_F=%s excess=%s ; In=%s (bound B+kL=%s) ; Out=%s" %
      (b['W_P'], b['W_F'], b['excess'], b['In'], r['B'] + 3 * 81, b['Out']))
    p("    D=%s = %.4f L  (ceiling 2(k-1)L = %d) ; rho^P=%s rho^F=%s R^P-R^F=%s"
      % (b['D'], float(Fraction(b['D'], 81)), 2 * 2 * 81, b['rho_P'],
         b['rho_F'], b['R_P'] - b['R_F']))
    p("    => Theorem 1's constant and  In < B+kL  ARE saturated together,")
    p("       which is exactly what open problem 8.1 asks.")
    p("")
    p("C. independent hill-climb (no knowledge of the construction), for")
    p("   comparison with the note's own search:")
    p("")
    for k in (1, 2, 3, 4):
        bst = hillclimb(k, 9, 12, 900, 1000 + k)
        if bst:
            p("    k=%d : best c found by hill-climb = %s = %.4f   (note: %.4f)"
              % (k, bst[0], float(bst[0]), float(note_best[k])))
    p("")
    with open("out_wrapc.txt", "w") as fh:
        fh.write("\n".join(OUT) + "\n")


if __name__ == "__main__":
    main()
