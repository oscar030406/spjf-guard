"""Item 1: Theorem 3 (and Lemma 1'').

The two families are rebuilt HERE from the prose of theory.md section 6.1 and
Lemma 1'' -- no code from evidence/guard_theory/ was read before writing this
file.  Everything is simulated by ref3_sim.py and audited from the schedule.
"""
import sys
from fractions import Fraction
from ref3_sim import (simulate, fcfs, priority, audit, bookkeeping,
                      check_identity, unfinished, n_present)

OUT = []


def p(*args):
    s = " ".join(str(x) for x in args)
    OUT.append(s)
    print(s)


# ------------------------------------------------------------------ families
def upper_family(k, L, m, Nmul=2):
    """Lemma 1'' cascade (units-first policy P) + the section 6.1 finale."""
    a, x = [], []
    for j in range(m):
        T = j * L
        for _ in range(k - 1):
            a.append(T); x.append(L)          # bigs first => lower ranks
        for _ in range(L):
            a.append(T); x.append(1)
    Tm = m * L
    for _ in range(k - 1):
        a.append(Tm); x.append(L)             # k-1 new bigs, ranks below victim
    victim = len(a)
    a.append(Tm); x.append(L)                 # the victim
    N = Nmul * k * L + 1                      # N > 2kL
    for _ in range(N):
        a.append(Tm); x.append(1)
    return a, x, victim, Tm


def upper_policy(k, L, m, victim, Tm):
    def key(j, t, ctx):
        xx, aa = ctx['x'], ctx['a']
        if t < Tm:
            return 0 if xx[j] == 1 else 1            # units before bigs
        if aa[j] == Tm and j < victim and xx[j] == L:
            return 0                                 # the k-1 new bigs
        if xx[j] == 1:
            return 1                                 # then the units
        return 2                                     # then i
    return priority(key)


def lower_family(k, L, m):
    """Mirror cascade: units injected FIRST (lower ranks), P = bigs-before-units,
    so FCFS is the surplus holder.  Then the section 6.1 mirror finale."""
    assert L % (k ** m) == 0, "need k^m | L for the cascade to stay integral"
    a, x = [], []
    for j in range(m):
        T = j * L
        for _ in range(L):
            a.append(T); x.append(1)          # units first => lower ranks
        for _ in range(k - 1):
            a.append(T); x.append(L)
    Tm = m * L
    f = L - (L * (k - 1) ** m) // (k ** m)    # = rho_m / (k-1)
    filler = len(a)
    a.append(Tm); x.append(f)                 # filler, rank below the victim
    victim = len(a)
    a.append(Tm); x.append(L - 1)             # the victim
    for _ in range(k - 1):
        a.append(Tm); x.append(L)             # k-1 bigs, ranks above the victim
    return a, x, victim, filler, Tm, f


def lower_policy(k, L, m, victim, filler, Tm):
    def key(j, t, ctx):
        xx, aa = ctx['x'], ctx['a']
        if t < Tm:
            return 0 if xx[j] == L else 1            # bigs before units
        if aa[j] == Tm and j > victim:
            return 0                                 # the k-1 new bigs
        if j == victim:
            return 1
        return 2                                     # the filler last
    return priority(key)


# ------------------------------------------------------------------- reports
def rho_pred(k, L, m):
    return Fraction((k - 1) * L) * (1 - Fraction((k - 1) ** m, k ** m))


def run_upper(k, L, m, verbose=True):
    a, x, i, Tm = upper_family(k, L, m)
    resP = simulate(a, x, k, upper_policy(k, L, m, i, Tm))
    resF = simulate(a, x, k, fcfs)
    bad = audit(resP, L=L) + audit(resF, L=L)
    errs = check_identity(resP, resF, i)
    b = bookkeeping(resP, resF, i)
    gap = unfinished(resP, Tm) - unfinished(resF, Tm)
    sp = sum(x[j] for j in range(len(a))
             if j > i and resP['order'][j] < resP['order'][i]
             and resP['s'][j] == resP['s'][i])
    return dict(k=k, L=L, m=m, n=len(a), victim=i, bad=bad, errs=errs, b=b,
                gap=gap, rho_pred=rho_pred(k, L, m), samephase_In=sp,
                resP=resP, resF=resF, Tm=Tm)


def run_lower(k, L, m):
    a, x, i, fl, Tm, f = lower_family(k, L, m)
    resP = simulate(a, x, k, lower_policy(k, L, m, i, fl, Tm))
    resF = simulate(a, x, k, fcfs)
    bad = audit(resP, L=L) + audit(resF, L=L)
    errs = check_identity(resP, resF, i)
    b = bookkeeping(resP, resF, i)
    gap = unfinished(resF, Tm) - unfinished(resP, Tm)
    sp = sum(x[j] for j in range(len(a))
             if j > i and resP['order'][j] < resP['order'][i]
             and resP['s'][j] == resP['s'][i])
    return dict(k=k, L=L, m=m, n=len(a), victim=i, bad=bad, errs=errs, b=b,
                gap=gap, rho_pred=rho_pred(k, L, m), samephase_In=sp, f=f,
                resP=resP, resF=resF, Tm=Tm)


def fmt(v, L):
    fr = Fraction(v, 1) / L
    return "%s/%s = %.4f" % (fr.numerator, fr.denominator, float(fr))


def main():
    p("=" * 78)
    p("ITEM 1 -- Theorem 3 / Lemma 1''  (referee 3, own simulator)")
    p("=" * 78)
    rows = [(2, 64, 3), (2, 64, 6), (3, 81, 4), (4, 64, 3)]
    p("")
    p("--- A. the note's own four rows, rebuilt from the TEXT ---")
    p("")
    hdr = ("  k   L  m   n(up)  D_up/L        De_up/L       n(lo)  D_lo/L       "
           " De_lo/L       2(k-1)")
    p(hdr)
    for (k, L, m) in rows:
        U = run_upper(k, L, m)
        Lo = run_lower(k, L, m)
        p("  %d %3d  %d  %5d  %-13s %-13s %5d  %-13s %-13s %d" % (
            k, L, m, U['n'], fmt(U['b']['D'], L), fmt(U['b']['De'], L),
            Lo['n'], fmt(Lo['b']['D'], L), fmt(Lo['b']['De'], L), 2 * (k - 1)))
        for tag, R in (("upper", U), ("lower", Lo)):
            if R['bad']:
                p("      !! %s AUDIT FAILURES: %s" % (tag, R['bad'][:3]))
            if R['errs']:
                p("      !! %s IDENTITY FAILURES: %s" % (tag, R['errs']))
    p("")
    p("--- B. full decomposition of the victim, both families ---")
    p("")
    for (k, L, m) in rows:
        for tag, R in (("upper", run_upper(k, L, m)), ("lower", run_lower(k, L, m))):
            b = R['b']
            p("  k=%d L=%d m=%d  [%s]  n=%d  victim=%d" %
              (k, L, m, tag, R['n'], R['victim']))
            p("     W_P=%s  W_F=%s  excess=%s (=%.4f L)" %
              (b['W_P'], b['W_F'], b['excess'], float(Fraction(b['excess'], L))))
            p("     In=%s  Out=%s  In_samephase=%s  rho_new=%s" %
              (b['In'], b['Out'], R['samephase_In'], b['rho_new']))
            p("     R^P=%s R^F=%s  R^P-R^F=%s (pred rho_m=%s)  rho^P=%s rho^F=%s"
              % (b['R_P'], b['R_F'], b['R_P'] - b['R_F'], R['rho_pred'],
                 b['rho_P'], b['rho_F']))
            p("     D=%s = %.4f L   De=%s = %.4f L   (k-1)L=%d  2(k-1)L=%d" %
              (b['D'], float(Fraction(b['D'], L)), b['De'],
               float(Fraction(b['De'], L)), (k - 1) * L, 2 * (k - 1) * L))
            p("     Lemma1'' gap U_surplus-U_other at T_m = %s (predicted %s) %s"
              % (R['gap'], R['rho_pred'],
                 "OK" if R['gap'] == R['rho_pred'] else "MISMATCH"))
            p("     audit: %s   identities: %s" %
              ("clean" if not R['bad'] else R['bad'],
               "clean" if not R['errs'] else R['errs']))
            p("")
    p("--- C. limit in m, both directions, several k (does D/L -> 2(k-1)?) ---")
    p("")
    sweep = [(2, 128, [1, 2, 3, 4, 5, 6, 7]), (3, 81, [1, 2, 3, 4]),
             (4, 64, [1, 2, 3]), (5, 25, [1, 2]), (6, 36, [1, 2])]
    for (k, L, ms) in sweep:
        for m in ms:
            try:
                U = run_upper(k, L, m)
                Lo = run_lower(k, L, m)
            except AssertionError as e:
                p("  k=%d L=%d m=%d  skipped (%s)" % (k, L, m, e))
                continue
            predU = rho_pred(k, L, m) + (k - 1) * L
            p("  k=%d L=%3d m=%d : D_up=%-12s D_lo=%-13s  pred |D|~%-10s "
              "2(k-1)L=%d  audit=%s%s" %
              (k, L, m, fmt(U['b']['D'], L), fmt(Lo['b']['D'], L),
               "%.4f L" % float(Fraction(predU, L)), 2 * (k - 1) * L,
               "clean" if not (U['bad'] + Lo['bad']) else "FAIL",
               "" if not (U['errs'] + Lo['errs']) else " IDENT-FAIL"))
    p("")
    p("--- D. how much of the extremal |D| is same-phase bookkeeping ---")
    p("")
    p("  (In_samephase = work of overtakers dispatched in i's OWN phase, which")
    p("   execute nothing while i waits; De = the executed-work convention)")
    p("")
    for (k, L, m) in rows:
        for tag, R in (("upper", run_upper(k, L, m)), ("lower", run_lower(k, L, m))):
            b = R['b']
            D = b['D']
            frac = Fraction(R['samephase_In'], abs(D)) if D else 0
            p("  k=%d m=%d [%s]: |D|=%s  In_samephase=%s (%.1f%% of |D|)  "
              "real excess=%s=%.3fL  De/|2(k-1)L|=%.3f" %
              (k, m, tag, abs(D), R['samephase_In'], 100 * float(frac),
               b['excess'], float(Fraction(b['excess'], L)),
               float(Fraction(abs(b['De']), 2 * (k - 1) * L))))
    p("")
    with open("out_thm3.txt", "w") as fh:
        fh.write("\n".join(OUT) + "\n")


if __name__ == "__main__":
    main()
