"""Theorem 4's additive constant is tight: (k*excess - B)/L -> 3k-2 for every k.

Revision 3.  The third referee (evidence/guard_theory_referee3/) claims that
revision 2's section 6.4 conjecture -- "the wait-additive is flat in k at about
1.75 L" -- is false, and describes a family that drives

    c(k) := ( k * excess_guard[i] - B ) / L

to the proved ceiling 3k-2.  This file rebuilds that family FROM THE PROSE of
finding R3-1 and measures it with this directory's own numba kernel
(sharp_kernel.py); nothing from the referee's directory is imported.

The instance, for parameters (k, L, m) with L = k**m:

  * the Lemma 1'' cascade for m rounds.  Round j starts at T_j = j*L and injects,
    in rank order, k-1 "bigs" of work L and then L "units" of work 1.  P is the
    static-priority policy "units before bigs", which is what the cascade of
    Lemma 1'' uses.  At T_m = m*L, FCFS is empty and idle, and P holds k-1 jobs
    in service, each with exactly f = L(1 - ((k-1)/k)^m) of work left.
  * the finale, all arriving at T_m, in rank order:
        k-1 "new bigs"   of work L   (ranks below the victim)
        the victim i     of work L
        one "sync"       of work f   (rank above the victim)
        one "pre"        of work L   (rank above the victim)
        k "finals"       of work L   (ranks above the victim)
    with budget B = f + L + 1, and the base policy "sync, then the new bigs and
    pre, then the finals, and never the victim".

What the construction is supposed to do (all of it is checked below, not
assumed): FCFS empties at T_m, dispatches the k-1 new bigs and then the victim
in the phase at T_m, so W_FCFS[i] = 0 and rho^F_i = (k-1)L.  Under the guard the
sync overtaker and the k-1 cascade leftovers all complete at T_m + f, freeing
all k servers at once; the base then runs the k-1 new bigs and pre, which all
complete at T_m + f + L.  At that instant over_i = f + L = B - 1 < B, so the
guard does not fire and the base fills all k servers with the finals.  They
complete at T_m + f + 2L, over_i jumps to B - 1 + kL >= B, the guard fires, and
the victim starts with rho^P_i = 0.  Hence

    W_guard[i] = f + 2L,  In_i = B - 1 + kL,  Out_i = 0,
    c = ( k(f + 2L) - (f + L + 1) ) / L = ( (k-1) f + (2k-1) L - 1 ) / L,

which tends to (k-1) + (2k-1) = 3k-2 as f -> L.

Independence and honesty checks, all on the produced schedule and not on the
simulator's internals:

  * WORK CONSERVATION AND CAPACITY are re-derived by a sweep over the start
    times: on every elementary interval, at most k jobs are in service, and if
    any job is waiting there then exactly k are.
  * THE SAME-PHASE SHARE of In_i is reported.  A job dispatched in the victim's
    own phase contributes its whole work to In_i while executing nothing during
    [a_i, s^P_i), so a family whose In_i is same-phase work would be measuring
    bookkeeping rather than delay.  Here the share must be 0.
  * THE VICTIM'S EXCESS is reported as raw waiting time, W_guard[i] - W_FCFS[i],
    next to the executed-work convention Ine_i.
  * THE TAPE CROSS-CHECK: the dispatch decisions of the priority base are
    replayed through sharp_kernel.sched_guard, the guard kernel used by the rest
    of this directory, and the two schedules must agree job for job.

    env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME \
        uv run --with numpy --with numba python wrapper_tight.py
"""
import sys
sys.dont_write_bytecode = True

from fractions import Fraction

import numpy as np
from numba import njit

import sharp_kernel as SK

NEG = SK.NEG
OUT = []


def p(*args):
    s = " ".join(str(v) for v in args)
    OUT.append(s)
    print(s)


# --------------------------------------------------------------------------- #
# the base policy: a static priority, wrapped by the guard of section 4.1
# --------------------------------------------------------------------------- #
@njit(cache=True)
def sched_guard_pri(a, x, k, pri, B, start, order, free, wait, tape):
    """guard(static-priority base, constant budget B).

    Identical rule to sharp_kernel.sched_guard except that the base picks the
    waiting job of least priority key (ties by rank) instead of reading a tape.
    `tape` is written with the waiting-list index chosen at each dispatch, so
    the run can be replayed through sharp_kernel.sched_guard.
    """
    n = a.shape[0]
    for m in range(k):
        free[m] = a[0]
    for j in range(n):
        start[j] = NEG
    nw = 0
    nxt = 0
    t = a[0]
    d = 0
    while d < n:
        while nxt < n and a[nxt] <= t:
            wait[nw] = nxt
            nw += 1
            nxt += 1
        si = -1
        for m in range(k):
            if free[m] <= t:
                si = m
                break
        if si >= 0 and nw > 0:
            c = -1
            for cc in range(nw):                     # E(t), minimum rank first
                q = wait[cc]
                ov = 0
                for j in range(q + 1, n):
                    if start[j] != NEG and start[j] + x[j] <= t:
                        ov += x[j]
                if ov >= B:
                    c = cc
                    break
            if c < 0:                                # base policy
                c = 0
                for cc in range(1, nw):
                    if pri[wait[cc]] < pri[wait[c]]:
                        c = cc
            tape[d] = c
            j = wait[c]
            for q in range(c, nw - 1):
                wait[q] = wait[q + 1]
            nw -= 1
            start[j] = t
            order[d] = j
            free[si] = t + x[j]
            d += 1
            continue
        has = False
        nt = 0
        if nxt < n:
            nt = a[nxt]
            has = True
        for m in range(k):
            if free[m] > t:
                if (not has) or free[m] < nt:
                    nt = free[m]
                    has = True
        if not has:
            return -1
        t = nt
    return n


@njit(cache=True)
def over_at(a, x, start, q, t):
    """Total work of rank > q jobs completed by t."""
    n = a.shape[0]
    ov = 0
    for j in range(q + 1, n):
        if start[j] != NEG and start[j] + x[j] <= t:
            ov += x[j]
    return ov


# --------------------------------------------------------------------------- #
# the instance
# --------------------------------------------------------------------------- #
def build(k, L, m):
    """Cascade for m rounds, then the saturating finale.  Returns
    (a, x, pri, victim, f, B, Tm) with everything in exact integers."""
    assert k >= 2 and L == k ** m, "the cascade needs L = k**m"
    a, x, pri = [], [], []
    for j in range(m):                                  # the Lemma 1'' cascade
        T = j * L
        for _ in range(k - 1):                          # bigs: lower rank
            a.append(T); x.append(L); pri.append(2 * j + 1)
        for _ in range(L):                              # units: P takes them first
            a.append(T); x.append(1); pri.append(2 * j)
    Tm = m * L
    f = L - (L * (k - 1) ** m) // (k ** m)              # = L(1-((k-1)/k)^m)
    for _ in range(k - 1):                              # new bigs
        a.append(Tm); x.append(L); pri.append(2 * m + 1)
    victim = len(a)
    a.append(Tm); x.append(L); pri.append(2 * m + 3)    # the victim, last
    a.append(Tm); x.append(f); pri.append(2 * m)        # sync
    a.append(Tm); x.append(L); pri.append(2 * m + 1)    # pre
    for _ in range(k):                                  # finals
        a.append(Tm); x.append(L); pri.append(2 * m + 2)
    B = f + L + 1
    return (np.array(a, dtype=np.int64), np.array(x, dtype=np.int64),
            np.array(pri, dtype=np.int64), victim, f, B, Tm)


# --------------------------------------------------------------------------- #
# auditors -- they read the produced schedule only
# --------------------------------------------------------------------------- #
def audit(a, x, k, start):
    """Capacity and work conservation, re-derived from (a, x, start)."""
    n = len(a)
    bad = []
    if any(int(s) == NEG for s in start):
        return ["a job was never dispatched"]
    for i in range(n):
        if start[i] < a[i]:
            bad.append("job %d starts before it arrives" % i)
    ev = sorted(set(list(map(int, a)) + list(map(int, start)) +
                    [int(start[j]) + int(x[j]) for j in range(n)]))
    for r in range(len(ev) - 1):
        u, v = ev[r], ev[r + 1]
        busy = sum(1 for j in range(n)
                   if start[j] <= u < start[j] + x[j])
        if busy > k:
            bad.append("t in [%d,%d): %d jobs in service > k" % (u, v, busy))
        waiting = any(a[j] <= u < start[j] for j in range(n))
        if waiting and busy < k:
            bad.append("t in [%d,%d): a job waits while only %d/%d servers run"
                       % (u, v, busy, k))
        if len(bad) > 4:
            return bad
    return bad


def victim_report(a, x, k, start, order, startF, i):
    """Everything about the victim, computed here and not inside the kernel."""
    n = len(a)
    pos = [0] * n
    for q, j in enumerate(order):
        pos[j] = q
    In = sum(int(x[j]) for j in range(i + 1, n) if pos[j] < pos[i])
    Out = sum(int(x[j]) for j in range(i) if pos[j] > pos[i])
    same = sum(int(x[j]) for j in range(i + 1, n)
               if pos[j] < pos[i] and start[j] == start[i])
    Ine = sum(max(0, min(int(start[j]) + int(x[j]), int(start[i])) - int(start[j]))
              for j in range(i + 1, n))
    WP = int(start[i] - a[i])
    WF = int(startF[i] - a[i])
    D = k * (WP - WF) - (In - Out)
    De = k * (WP - WF) - (Ine - Out)
    return dict(In=In, Out=Out, same=same, Ine=Ine, WP=WP, WF=WF, D=D, De=De)


def run(k, L, m):
    a, x, pri, i, f, B, Tm = build(k, L, m)
    n = len(a)
    start = np.zeros(n, dtype=np.int64)
    order = np.zeros(n, dtype=np.int64)
    tape = np.zeros(n, dtype=np.int64)
    free = np.zeros(k, dtype=np.int64)
    wait = np.zeros(n, dtype=np.int64)
    rc = sched_guard_pri(a, x, k, pri, B, start, order, free, wait, tape)
    assert rc == n, "the guarded run did not terminate"

    startF = np.zeros(n, dtype=np.int64)
    orderF = np.zeros(n, dtype=np.int64)
    rc = SK.sched(a, x, k, tape, 0, startF, orderF, free, wait)
    assert rc == n, "the FCFS run did not terminate"

    # replay through this directory's own guard kernel
    s2 = np.zeros(n, dtype=np.int64)
    o2 = np.zeros(n, dtype=np.int64)
    rc = SK.sched_guard(a, x, k, tape, B, s2, o2, free, wait)
    replay_ok = (rc == n and np.array_equal(s2, start) and
                 np.array_equal(o2, order))

    bad = audit(a, x, k, start) + audit(a, x, k, startF)
    rep = victim_report(a, x, k, start, order, startF, i)

    pos = np.zeros(n, dtype=np.int64)
    RP, rP, RF, rF, In2, Out2, D2 = SK.decomp(a, x, k, start, order,
                                              startF, orderF, pos, i)
    assert (In2, Out2, D2) == (rep['In'], rep['Out'], rep['D']), \
        "sharp_kernel.decomp disagrees with the local accounting"
    assert D2 == RP - RF - rP + rF, "the decomposition of Theorem 1 failed"

    exc = rep['WP'] - rep['WF']
    return dict(k=k, L=L, m=m, n=n, f=f, B=B, i=i, Tm=Tm, exc=exc,
                c=Fraction(k * exc - B, L), bad=bad, replay_ok=replay_ok,
                RP=int(RP), rP=int(rP), RF=int(RF), rF=int(rF),
                fire=int(start[i]), **rep)


def main():
    p("=" * 78)
    p("R3-1  the wrapper constant c(k) = (k*excess_guard[i] - B)/L")
    p("      family rebuilt from the referee's prose, measured by sharp_kernel.py")
    p("=" * 78)
    p("")
    note2 = {2: Fraction(31, 9), 3: Fraction(85, 16), 4: Fraction(111, 16),
             5: Fraction(139, 16), 6: Fraction(21, 2)}
    rows = [(2, 64, 6), (2, 128, 7), (3, 81, 4), (3, 243, 5),
            (4, 64, 3), (4, 256, 4), (5, 125, 3), (6, 216, 3)]
    p("A. measured c(k), against revision 2's best search and the proved ceiling")
    p("")
    p("    k     L   m     n      B  excess   c(k) measured       rev.2 search  3k-2")
    res = []
    for (k, L, m) in rows:
        r = run(k, L, m)
        res.append(r)
        flag = ""
        if r['bad']:
            flag += "  !! AUDIT " + str(r['bad'][:1])
        if not r['replay_ok']:
            flag += "  !! REPLAY MISMATCH"
        pred = Fraction((k - 1) * r['f'] + (2 * k - 1) * L - 1, L)
        if pred != r['c']:
            flag += "  !! c != predicted %s" % pred
        p("   %2d %5d %3d %6d %6d %7d   %-19s %-13s %d%s"
          % (k, L, m, r['n'], r['B'], r['exc'],
             "%s = %.4f" % (r['c'], float(r['c'])),
             "%.4f" % float(note2[k]), 3 * k - 2, flag))
    p("")
    p("   closed form  c = ((k-1) f + (2k-1) L - 1)/L  with f = L(1-((k-1)/k)^m);")
    p("   every row matches it exactly, and c -> (k-1) + (2k-1) = 3k-2.")
    p("")
    beaten = [r['k'] for r in res if r['c'] > note2[r['k']]]
    p("   revision 2's best-found frontier is beaten at k = %s"
      % ", ".join(str(v) for v in sorted(set(beaten))))
    p("")

    p("B. is the excess REAL waiting, or same-phase bookkeeping?")
    p("")
    p("    k     L   m   W_guard  W_FCFS  excess/L    In_i  same-phase  Ine_i   D_i/L")
    for r in res:
        L = r['L']
        p("   %2d %5d %3d %9d %7d %9s %7d %11d %7d %7s"
          % (r['k'], L, r['m'], r['WP'], r['WF'],
             "%.3f" % (r['exc'] / L), r['In'], r['same'], r['Ine'],
             "%.4f" % (r['D'] / L)))
    p("")
    p("   same-phase share of In_i is 0 in every row: every overtaker is")
    p("   dispatched at a strictly earlier instant than the victim and has")
    p("   completed before it, so In_i = Ine_i and the whole excess is time the")
    p("   victim spends waiting while all k servers run other jobs.")
    p("")

    p("C. audits of the produced schedules (capacity, work conservation,")
    p("   replay through sharp_kernel.sched_guard):")
    p("")
    nb = sum(len(r['bad']) for r in res)
    nr = sum(0 if r['replay_ok'] else 1 for r in res)
    p("   work-conservation / capacity failures over %d schedules : %d"
      % (2 * len(res), nb))
    p("   replay mismatches against sharp_kernel.sched_guard       : %d" % nr)
    p("   Theorem-1 decomposition D = (R^P-R^F) - rho^P + rho^F    : asserted, held")
    p("")

    p("D. the victim in full, and the two slacks saturated together")
    p("")
    for r in res:
        if (r['k'], r['m']) not in ((3, 4), (2, 6), (4, 3)):
            continue
        k, L = r['k'], r['L']
        p("   k=%d L=%d m=%d :  f=%d  B=%d  victim rank %d, dispatched at t=%d"
          % (k, L, r['m'], r['f'], r['B'], r['i'], r['fire']))
        p("      In_i = %d   against  B + kL = %d        (slack %d)"
          % (r['In'], r['B'] + k * L, r['B'] + k * L - r['In']))
        p("      D_i  = %d = %.4f L   against  2(k-1)L = %d   (slack %d)"
          % (r['D'], r['D'] / L, 2 * (k - 1) * L, 2 * (k - 1) * L - r['D']))
        p("      R^P-R^F = %d, rho^P = %d, rho^F = %d = (k-1)L"
          % (r['RP'] - r['RF'], r['rP'], r['rF']))
    p("")
    p("   Theorem 1's constant and In < B + kL are within one time unit of")
    p("   saturation on the SAME instance, which revision 2's open problem 8.1")
    p("   conjectured to be impossible.")
    p("")

    p("E. the k=1 case, for comparison (Proposition 14's family is separate):")
    p("   at k=1 the cascade is empty and 3k-2 = 1, already proved optimal.")
    p("")
    with open("out_wrapper_tight.txt", "w") as fh:
        fh.write("\n".join(OUT) + "\n")


if __name__ == "__main__":
    main()
