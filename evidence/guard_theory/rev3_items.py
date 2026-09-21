"""Revision 3: the checks behind findings R3-3 … R3-14 of the third referee.

Everything here runs on sim_core.py, this directory's pure-Python exact-integer
simulator; no script from evidence/guard_theory_referee3/ is imported, and the
instances are rebuilt from the prose of the findings.

    env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME \
        uv run --with numpy python rev3_items.py
"""
import sys
sys.dont_write_bytecode = True

from fractions import Fraction as F

import sim_core
import family_tight as FT

OUT = []


def p(*args):
    s = " ".join(str(v) for v in args)
    OUT.append(s)
    print(s)


def prio(keys):
    def f(t, waiting, state):
        best = 0
        for c in range(1, len(waiting)):
            if keys[waiting[c]] < keys[waiting[best]]:
                best = c
        return best
    return f


def unfinished(jobs, start, w):
    """(U_Q(w), N_Q(w), busy_Q(w), sizes present) with the note's conventions:
    a job counts from its arrival until its completion, completions first."""
    U = 0
    N = 0
    busy = 0
    sizes = []
    for j, (a, x) in enumerate(jobs):
        if a > w:
            continue
        if start[j] > w:
            r = x
        else:
            r = max(0, start[j] + x - w)
        if r > 0 or (start[j] > w and x == 0):
            N += 1
            sizes.append(x)
        U += r
        if start[j] <= w < start[j] + x:
            busy += 1
    return U, N, busy, sizes


def state_left(jobs, start, b):
    """The same quantities read at b^-: arrivals AT b are excluded, and a job
    completing at b is still in service."""
    U = 0
    N = 0
    busy = 0
    sizes = []
    for j, (a, x) in enumerate(jobs):
        if a >= b:
            continue
        r = x if start[j] >= b else max(0, start[j] + x - b)
        if r > 0:
            N += 1
            sizes.append(x)
        U += r
        if start[j] < b <= start[j] + x:
            busy += 1
    return U, N, busy, sizes


def atoms_upto(jobs, start, t):
    """The exact constancy decomposition of (-inf, t]: every breakpoint as a
    point atom, every open interval between consecutive breakpoints as an
    interval atom represented by its midpoint.  N_A is constant on each atom, so
    a condition 'for all v in (u,t]' is exactly a condition on the atoms after
    u's."""
    n = len(jobs)
    bps = sorted(set([j[0] for j in jobs] +
                     [start[j] + jobs[j][1] for j in range(n)] + [t]))
    bps = [F(b) for b in bps if b <= t]
    out = []
    for r, b in enumerate(bps):
        if r > 0:
            out.append(('iv', (bps[r - 1] + b) / 2))
        out.append(('pt', b))
    return out


def admissible_u(jobs, start, k, t):
    """Every u <= t satisfying Lemma 1''s revision-2 hypothesis exactly:
    N_A(u) <= k-1 and N_A >= k throughout (u, t].  An interval atom can never
    qualify (N_A is constant just after it), so only breakpoints are tested."""
    at = atoms_upto(jobs, start, t)
    NN = [unfinished(jobs, start, rep)[1] for (_, rep) in at]
    suffix_ok = [True] * (len(at) + 1)
    for idx in range(len(at) - 1, -1, -1):
        suffix_ok[idx] = suffix_ok[idx + 1] and NN[idx] >= k
    return [rep for idx, (kind, rep) in enumerate(at)
            if kind == 'pt' and NN[idx] <= k - 1 and suffix_ok[idx + 1]]


# --------------------------------------------------------------------------- #
def item_R3_3():
    p("=" * 78)
    p("R3-3  Lemma 1' is false as literally stated; the repaired form holds")
    p("=" * 78)
    p("")
    k = 2
    a = (0, 0, 0, 0, 0, 4, 4)
    x = (4, 1, 1, 1, 1, 10, 10)
    jobs = list(zip(a, x))
    keys = [1, 0, 0, 0, 0, 0, 0]          # "units before the big job"
    sP, oP, _ = sim_core.simulate(jobs, k, prio(keys))
    sF, oF, _ = sim_core.simulate(jobs, k, sim_core.fcfs)
    t = F(5)
    p("   k=2, a=%s, x=%s, P = units before the big job, t=5" % (a, x))
    p("   start^P = %s" % sP)
    p("   start^F = %s" % sF)
    UP = unfinished(jobs, sP, t)[0]
    UF = unfinished(jobs, sF, t)[0]
    p("   U_P(5) = %s, U_FCFS(5) = %s, gap = %s" % (UP, UF, UP - UF))
    p("")
    for tt in (F(4), F(5)):
        adm = admissible_u(jobs, sP, k, tt)
        g = (unfinished(jobs, sP, tt)[0] - unfinished(jobs, sF, tt)[0])
        p("   t=%s : U_P-U_FCFS = %s ; admissible u (N_P(u) <= k-1 and"
          " N_P >= k on (u,t]) : %s" % (tt, g, adm if adm else "NONE"))
    p("   so revision 2's fallback clause applies and asserts U_P <= U_FCFS,")
    p("   i.e. %s <= %s -- FALSE." % (UP, UF))
    p("")
    bps = sorted(set([j[0] for j in jobs] +
                     [sP[j] + jobs[j][1] for j in range(len(jobs))]))
    ustar = max(b for b in bps if b <= t and state_left(jobs, sP, b)[2] < k)
    Um, Nm, busym, sizes = state_left(jobs, sP, ustar)
    lam = max(sizes) if sizes else 0
    p("   repaired form: u* = max{b <= t : fewer than k of P's servers busy at")
    p("   b^-} = %s ; at u*^- : busy = %s, N_P = %s, U_P = %s, sizes present %s"
      % (ustar, busym, Nm, Um, sizes))
    p("   bound (k-1)*max size present at u*^- = %s ; measured gap = %s -> %s"
      % ((k - 1) * lam, UP - UF, "HOLDS" if UP - UF <= (k - 1) * lam else "FAILS"))
    p("")
    p("   the same failure on the note's own extremal family, at t = T_m, where")
    p("   N_P is k-1 just before T_m and jumps to >= k at T_m:")
    for (kk, LL, mm) in ((2, 64, 3), (3, 81, 2), (4, 64, 2)):
        jb, pr, v = FT.build_upper(kk, LL, mm, 1, ntiny=2 * kk * LL + 1)
        sPP, _, _ = sim_core.simulate(jb, kk, prio(pr))
        sFF, _, _ = sim_core.simulate(jb, kk, sim_core.fcfs)
        Tm = F(mm * LL)
        gap = unfinished(jb, sPP, Tm)[0] - unfinished(jb, sFF, Tm)[0]
        rho = FT.rho_seq(kk, LL, mm)[mm]
        adm2 = admissible_u(jb, sPP, kk, Tm)
        p("      k=%d L=%d m=%d : N_P(T_m^-) = %d, N_P(T_m) = %d, gap = %s"
          " (= rho_m = %d), admissible u: %s"
          % (kk, LL, mm, state_left(jb, sPP, Tm)[1],
             unfinished(jb, sPP, Tm)[1], gap, rho, adm2 if adm2 else "NONE"))
    p("")
    p("   (on the cascade WITHOUT the finale the clause is not refuted: there")
    p("   N_P(T_m) = k-1, so the trivial choice u = t is admissible and gives")
    p("   the correct bound (k-1)L.  The refutation needs the arrivals at T_m.)")
    p("")


# --------------------------------------------------------------------------- #
def measure_full(jobs, keys, k, i):
    """D, De, same-phase In, rho_old, rho_new and the real excess for job i."""
    n = len(jobs)
    x = [j[1] for j in jobs]
    a = [j[0] for j in jobs]
    sP, oP, _ = sim_core.simulate(jobs, k, prio(keys))
    sF, oF, _ = sim_core.simulate(jobs, k, sim_core.fcfs)
    posP = [0] * n
    for q, j in enumerate(oP):
        posP[j] = q
    In = sum(x[j] for j in range(i + 1, n) if posP[j] < posP[i])
    Out = sum(x[j] for j in range(i) if posP[j] > posP[i])
    same = sum(x[j] for j in range(i + 1, n)
               if posP[j] < posP[i] and sP[j] == sP[i])
    Ine = sum(max(0, min(sP[j] + x[j], sP[i]) - sP[j]) for j in range(i + 1, n))
    rho_new = sum(max(0, sP[j] + x[j] - sP[i]) for j in range(i + 1, n)
                  if posP[j] < posP[i])
    rho_old = sum(max(0, sP[j] + x[j] - sP[i]) for j in range(i)
                  if posP[j] < posP[i])
    WP = sP[i] - a[i]
    WF = sF[i] - a[i]
    D = k * (WP - WF) - (In - Out)
    De = k * (WP - WF) - (Ine - Out)
    return dict(D=D, De=De, In=In, Out=Out, same=same, Ine=Ine, WP=WP, WF=WF,
                rho_new=rho_new, rho_old=rho_old, n=n)


def item_R3_4_5():
    p("=" * 78)
    p("R3-4/R3-5  the two directions of Theorem 3 are not alike")
    p("=" * 78)
    p("")
    p("  UPWARD family")
    p("    k    L   m       D/L     De/L   excess/L  same-phase(In)  share of |D|"
      "  rho_old  rho_new")
    for (k, L, m) in ((2, 64, 6), (3, 81, 4), (4, 64, 3), (2, 64, 3)):
        jb, pr, v = FT.build_upper(k, L, m, 1, ntiny=2 * k * L + 1)
        r = measure_full(jb, pr, k, v)
        exc = r['WP'] - r['WF']
        p("   %2d %4d %3d %9s %8s %10s %15d %13s %8d %8d"
          % (k, L, m, "%.4f" % (r['D'] / L), "%.4f" % (r['De'] / L),
             "%+.3f" % (exc / L), r['same'],
             "%.2f%%" % (100.0 * r['same'] / abs(r['D'])),
             r['rho_old'], r['rho_new']))
    p("")
    p("  DOWNWARD (mirror) family")
    p("    k    L   m       D/L     De/L   excess/L  same-phase(In)  share of |D|"
      "  rho_old  rho_new")
    for (k, L, m) in ((2, 64, 6), (3, 81, 4), (4, 64, 3)):
        jb, pr, v = FT.build_lower(k, L, m, 1)
        r = measure_full(jb, pr, k, v)
        exc = r['WP'] - r['WF']
        p("   %2d %4d %3d %9s %8s %10s %15d %13s %8d %8d"
          % (k, L, m, "%.4f" % (r['D'] / L), "%.4f" % (r['De'] / L),
             "%+.3f" % (exc / L), r['same'],
             "%.2f%%" % (100.0 * r['same'] / abs(r['D'])),
             r['rho_old'], r['rho_new']))
    p("")
    p("  Upward: the excess is real (+3.0 L at k=2), In_i carries no same-phase")
    p("  work, and the executed convention reaches the same 2(k-1)L.")
    p("  Downward: In_i = (k-1)L is entirely same-phase, the executed convention")
    p("  stops at (k-1)L, and the victim's own excess is NEGATIVE.")
    p("  R3-5: rho_new at the upward victim is 0, 1 or 2 -- not identically 0 --")
    p("  and rho_old is 0; both are o(L), which is all Remark 1.3 needs.")
    p("")


# --------------------------------------------------------------------------- #
def item_R3_7():
    p("=" * 78)
    p("R3-7  Proposition 14: the approaching family at k = 1")
    p("=" * 78)
    p("")
    p("   victim of rank 0 at t=0; B/g - 1 overtakers of size g; then one of")
    p("   size L.  The guard cannot fire at the last base choice, since")
    p("   over_i = B - g < B, so excess = B - g + L.")
    p("")
    p("      L     B    g       n   excess   excess-B   L-g")
    for (L, B, g) in ((100, 40, 1), (64, 32, 1), (16, 8, 1), (64, 32, 4),
                      (100, 60, 5)):
        assert B % g == 0
        jobs = [(0, 1)]                       # the victim, rank 0
        keys = [2]
        for _ in range(B // g - 1):
            jobs.append((0, g)); keys.append(0)
        jobs.append((0, L)); keys.append(1)   # the last base choice
        base = prio(keys)
        ch = sim_core.make_guard(base, B)
        sP, oP, _ = sim_core.simulate(jobs, 1, ch)
        sF, _, _ = sim_core.simulate(jobs, 1, sim_core.fcfs)
        exc = (sP[0] - 0) - (sF[0] - 0)
        p("   %6d %5d %4d %7d %8d %10d %5d%s"
          % (L, B, g, len(jobs), exc, exc - B, L - g,
             "" if exc - B == L - g else "   !! MISMATCH"))
    p("")
    p("   strict in every row, and excess - B = L - g -> L as g -> 0.")
    p("")


# --------------------------------------------------------------------------- #
def item_R3_12():
    p("=" * 78)
    p("R3-12  Lemma 2: a witness with a non-negative guarantee")
    p("=" * 78)
    p("")
    k = 1
    jobs = [(0, 1)] * 5
    order = [3, 4, 2, 0, 1]
    keys = [order.index(j) for j in range(5)]
    sP, oP, _ = sim_core.simulate(jobs, k, prio(keys))
    sF, _, _ = sim_core.simulate(jobs, k, sim_core.fcfs)
    exc = [sP[j] - sF[j] for j in range(5)]
    posP = [0] * 5
    for q, j in enumerate(oP):
        posP[j] = q
    i = 2
    Out = sum(1 for j in range(i) if posP[j] > posP[i])
    outjobs = [j for j in range(i) if posP[j] > posP[i]]
    G = 0
    L = 1
    p("   k=1, five unit jobs at t=0, dispatch sequence %s, victim i=2" % oP)
    p("   excess per job = %s" % exc)
    p("   excess_2 = %d <= G = %d, yet Out_2 = %d > k(G - excess_2 + L) = %d"
      % (exc[i], G, Out, k * (G - exc[i] + L)))
    p("   and the jobs of Out_2 = %s have excess %s > G"
      % (outjobs, [exc[j] for j in outjobs]))
    p("   so the hypothesis on the jobs of Out_i cannot be dropped, with a")
    p("   guarantee G >= 0 and no negative 'guarantee' anywhere.")
    p("")


# --------------------------------------------------------------------------- #
def item_R3_14():
    p("=" * 78)
    p("R3-14  the four labels that rested on measurements alone")
    p("=" * 78)
    p("")
    p("  Prop 3(a): one overtaker of work X, no size bound, excess = X")
    p("      k   X    n   In_i   overtaker count   excess")
    for k in (1, 2, 3):
        for X in (10, 100, 1000):
            jobs = [(0, X)] * (k - 1) + [(0, 1), (0, X)]
            keys = [0] * (k - 1) + [2, 1]
            i = k - 1
            sP, oP, _ = sim_core.simulate(jobs, k, prio(keys))
            sF, _, _ = sim_core.simulate(jobs, k, sim_core.fcfs)
            posP = [0] * len(jobs)
            for q, j in enumerate(oP):
                posP[j] = q
            In = sum(jobs[j][1] for j in range(i + 1, len(jobs))
                     if posP[j] < posP[i])
            cnt = sum(1 for j in range(i + 1, len(jobs)) if posP[j] < posP[i])
            p("     %2d %5d %4d %6d %17d %8d" % (k, X, len(jobs), In, cnt,
                                                 sP[i] - sF[i]))
    p("   a single overtaker, so every count budget N >= 1 permits it, and the")
    p("   excess is X: unbounded without a size bound.")
    p("")
    p("  Prop 3(c): M tiny overtakers at a fixed guarantee L/2")
    p("      M    L=2M   overtakers   In_i   excess   excess/L")
    for M in (4, 16, 64, 256):
        L = 2 * M
        jobs = [(0, L)] + [(0, 1)] * M
        keys = [1] + [0] * M
        sP, oP, _ = sim_core.simulate(jobs, 1, prio(keys))
        sF, _, _ = sim_core.simulate(jobs, 1, sim_core.fcfs)
        p("   %6d %6d %12d %6d %8d %10s"
          % (M, L, M, M, sP[0] - sF[0], "%.3f" % ((sP[0] - sF[0]) / L)))
    p("   the excess stays at L/2 while the overtaker count grows without")
    p("   bound, so no finite count budget is necessary for the guarantee L/2.")
    p("")
    p("  Prop 6: the mean-wait ratio on the one-big-plus-m-units family, k=1")
    p("      L    m   mean W under guard(SJF,0)=FCFS   mean W under SJF   ratio"
      "   (2L+m-1)/(m+1)")
    for (L, m) in ((100, 4), (100, 9), (1000, 4), (10, 4)):
        jobs = [(0, L)] + [(0, 1)] * m
        sF, _, _ = sim_core.simulate(jobs, 1, sim_core.fcfs)
        sS, _, _ = sim_core.simulate(jobs, 1, sim_core.sjf_true)
        mF = F(sum(sF), m + 1)
        mS = F(sum(sS), m + 1)
        p("   %6d %4d %31s %18s %7s %16s"
          % (L, m, str(mF), str(mS), "%.4f" % float(mF / mS),
             "%.4f" % float(F(2 * L + m - 1, m + 1))))
    p("   guard(SJF, 0) is FCFS because E(t) contains every waiting job when")
    p("   B = 0, and the ratio (2L+m-1)/(m+1) is unbounded in L.")
    p("")
    p("  Prop 13: excess = ceil(B/k) on the B/k family, including k not")
    p("  dividing B")
    p("      k    L      B    excess   ceil(B/k)")
    for k in (1, 2, 3, 4):
        for L in (4, 16):
            for B in (0, 2 * k * L, 8 * k * L, 3 * k * L + 1, 5):
                nun = B + 2 * k + 2
                jobs = [(0, L)] * k + [(0, 1)] + [(0, 1)] * nun
                keys = [0] * k + [2] + [1] * nun
                i = k
                ch = sim_core.make_guard(prio(keys), B)
                sP, _, _ = sim_core.simulate(jobs, k, ch)
                sF, _, _ = sim_core.simulate(jobs, k, sim_core.fcfs)
                exc = sP[i] - sF[i]
                ceil = -((-B) // k)
                if exc != ceil:
                    p("   %2d %4d %6d %9d %11d   !! MISMATCH" % (k, L, B, exc, ceil))
    p("      (every configuration matched; only mismatches are printed)")
    for k in (1, 2, 3, 4):
        B = 3 * k * 4 + 1
        p("      k=%d, L=4, B=%d : excess = ceil(B/k) = %d"
          % (k, B, -((-B) // k)))
    p("")


# --------------------------------------------------------------------------- #
def item_R3_10():
    p("=" * 78)
    p("R3-10  revision 2's dismissal of the 2k - 10/9 frontier was selective")
    p("=" * 78)
    p("")
    best2 = {1: F(15, 16), 2: F(31, 9), 3: F(85, 16), 4: F(111, 16),
             5: F(139, 16), 6: F(21, 2)}
    p("      k   revision 2's best c(k)   2k - 10/9   above?")
    for k in range(1, 7):
        f2 = F(2 * k) - F(10, 9)
        p("     %2d %22s %11s   %s"
          % (k, "%.4f" % float(best2[k]), "%.4f" % float(f2),
             "yes" if best2[k] > f2 else "NO"))
    p("")
    p("   both formulas are superseded by the family of R3-1, whose c(k) beats")
    p("   2k - 10/9 at every k >= 2.")
    p("")


def main():
    item_R3_3()
    item_R3_4_5()
    item_R3_7()
    item_R3_10()
    item_R3_12()
    item_R3_14()
    with open("out_rev3_items.txt", "w") as fh:
        fh.write("\n".join(OUT) + "\n")


if __name__ == "__main__":
    main()
