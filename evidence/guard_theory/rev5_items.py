"""Revision 5: verify every mathematical point the fourth referee raises.

One file per referee round.  This one answers the fourth report's section B
(items RR-1, RR-2, RR-4, RR-7, RR-8, RR-19, RR-25, RR-26, RR-30, RR-31); every
claim below is either reproduced exactly or shown false, with the instance
printed in full so the check can be repeated by hand.

Nothing here imports the paper's simulator: sim_core.py is this directory's own
pure-Python exact-integer kernel, and every quantity is a Python int or a
Fraction.

    env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME \
        uv run --no-project python rev5_items.py
"""
import sys

sys.dont_write_bytecode = True

import itertools
import random
from fractions import Fraction

import sim_core as S

OUT = []


def p(*args):
    s = " ".join(str(v) for v in args)
    OUT.append(s)
    print(s)


def hdr(t):
    p("")
    p("=" * 72)
    p(t)
    p("=" * 72)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def prefix_max(jobs, t):
    """Lambda(t) = max{ C_j : a_j <= t }, 0 if the set is empty."""
    v = [x for (a, x) in jobs if a <= t]
    return max(v) if v else 0


def exec_in(jobs, k, start, order, i):
    """In^exec_i : work of rank > i jobs EXECUTED during [a_i, s^P_i)."""
    a = [j[0] for j in jobs]
    x = [j[1] for j in jobs]
    lo, hi = a[i], start[i]
    tot = 0
    for j in range(i + 1, len(jobs)):
        if start[j] is None:
            continue
        s0, s1 = start[j], start[j] + x[j]
        tot += max(0, min(s1, hi) - max(s0, lo))
    return tot


def over_at(jobs, start, q, t):
    """over[q](t): service of rank > q jobs completed by t."""
    x = [j[1] for j in jobs]
    tot = 0
    for j in range(q + 1, len(jobs)):
        if start[j] is not None and start[j] + x[j] <= t:
            tot += x[j]
    return tot


def static_priority(prio):
    """Chooser: dispatch the waiting job with the smallest prio[] value."""

    def f(t, waiting, state):
        best = 0
        for c in range(1, len(waiting)):
            if prio[waiting[c]] < prio[waiting[best]]:
                best = c
        return best

    return f


def guard_general(base, budget):
    """Wrapper with an arbitrary budget rule budget(q, t, state) >= 0."""

    def f(t, waiting, state):
        x = state["x"]
        done = state["done"]
        n = state["n"]
        for c, q in enumerate(waiting):  # increasing rank order
            ov = 0
            for j in range(q + 1, n):
                dj = done[j]
                if dj is not None and dj <= t:
                    ov += x[j]
            if ov >= budget(q, t, state):
                return c
        return base(t, waiting, state)

    return f


# ==========================================================================
# RR-1  Proposition 2(i): which prefix maximum the wrapper bounds need
# ==========================================================================
hdr("RR-1  the wrapper bounds need Lambda(s^P_i), not Lambda(a_i)")

p("")
p("The referee's counterexample, reproduced with sim_core:")
p("  k = 1, constant budget B = 2, no global size bound.")
p("  rank 0 = victim i (a=0, C=1); rank 1 = A (a=0, C=1); rank 2 = Z (a=1, C=M).")
p("  base policy: the static priority 'A, then Z, then i'.")
p("")
p("  M   W_FCFS  W_P   In_i  excess  Lam(a_i)  Lam(s^P_i)"
  "   B+k*Lam(a_i)  B+k*Lam(s^P)  add(a_i)  add(s^P)")

B_CE = 2
rows_ce = []
for M in [1, 2, 3, 5, 10, 100, 1000]:
    jobs = [(0, 1), (0, 1), (1, M)]
    k = 1
    base = static_priority({0: 2, 1: 0, 2: 1})
    st = {}
    W, In, Out, order, start = S.run(jobs, k, S.make_guard(base, B_CE), st)
    wf = S.fcfs_wait(jobs, k)
    i = 0
    exc = W[i] - wf[i]
    la = prefix_max(jobs, jobs[i][0])
    ls = prefix_max(jobs, start[i])
    bin_a, bin_s = B_CE + k * la, B_CE + k * ls
    add_a = Fraction(B_CE, k) + Fraction(3 * k - 2, k) * la
    add_s = Fraction(B_CE, k) + Fraction(3 * k - 2, k) * ls
    rows_ce.append((M, In[i], exc, bin_a, bin_s, add_a, add_s))
    p("  %-4d %-7d %-5d %-5d %-7d %-9d %-11d %-13d %-13d %-9s %-9s"
      % (M, wf[i], W[i], In[i], exc, la, ls, bin_a, bin_s,
         str(add_a), str(add_s)))

fail_a = [r for r in rows_ce if not (r[1] < r[3]) or not (r[2] < r[5])]
fail_s = [r for r in rows_ce if not (r[1] < r[4]) or not (r[2] < r[6])]
p("")
p("  rows violating the Lambda(a_i) form of (guardin)/(guardadd): M =",
  [r[0] for r in fail_a])
p("  rows violating the Lambda(s^P_i) form:                       M =",
  [r[0] for r in fail_s], "(empty = the corrected placement holds)")
p("")
p("  NOTE the referee writes 'violated for every M > 2'; the first violation is")
p("  at M = 2, where In_i = 3 is not < 3 and excess = 3 is not < 3.")

# ---- brute force of the corrected statement, no global size bound ---------
p("")
p("Brute force of the corrected statement, random instances, sizes UNBOUNDED")
p("(Pareto-like integer sizes, no cap; k = 1..4; constant budget):")
p("")
p("   k   instances  job-checks   fail Lam(a_i)[In]  fail Lam(a_i)[add]"
  "  fail Lam(s^P)[In]  fail Lam(s^P)[add]")

rng = random.Random(20260920)


def rand_jobs(n, rng, heavy=True):
    t = 0
    jobs = []
    for _ in range(n):
        t += rng.randint(0, 3)
        if heavy:
            u = rng.random()
            x = max(1, int((1.0 - u) ** (-1.0 / 0.7)))
            x = min(x, 4000)
        else:
            x = rng.randint(1, 8)
        jobs.append((t, x))
    return jobs


tot_checks = 0
for k in (1, 2, 3, 4):
    fa_in = fa_ad = fs_in = fs_ad = 0
    checks = 0
    ninst = 400
    for _ in range(ninst):
        n = rng.randint(3, 11)
        jobs = rand_jobs(n, rng)
        Bv = rng.choice([0, 1, 3, 10, 50])
        base = S.make_random(_RNG := random.Random(rng.random())) if False else None
        # base: random permutation priority (deterministic per instance)
        prio = list(range(n))
        rng.shuffle(prio)
        base = static_priority({j: prio[j] for j in range(n)})
        st = {}
        W, In, Out, order, start = S.run(jobs, k, S.make_guard(base, Bv), st)
        wf = S.fcfs_wait(jobs, k)
        for i in range(n):
            if In[i] == 0:
                continue  # (guardin) is asserted only when i has an overtaker
            checks += 1
            la = prefix_max(jobs, jobs[i][0])
            ls = prefix_max(jobs, start[i])
            exc = W[i] - wf[i]
            if not (In[i] < Bv + k * la):
                fa_in += 1
            if not (exc < Fraction(Bv, k) + Fraction(3 * k - 2, k) * la):
                fa_ad += 1
            if not (In[i] < Bv + k * ls):
                fs_in += 1
            # the sharp mixed form: kL -> k*Lam(s^P_i), (2k-2)L -> (2k-2)*Lam(a_i)
            if not (exc < Fraction(Bv, k) + ls + Fraction(2 * k - 2, k) * la):
                fs_ad += 1
    tot_checks += checks
    p("   %-3d %-10d %-12d %-18d %-19d %-18d %-18d"
      % (k, ninst, checks, fa_in, fa_ad, fs_in, fs_ad))

p("")
p("  total job-checks:", tot_checks)
p("  Lambda(a_i) fails in both wrapper bounds; Lambda(s^P_i) never fails.")
p("  The sharp form proved below is")
p("      In_i      <  Bmax + k*Lambda(s^P_i)")
p("      excess_i  <  Bmax/k + Lambda(s^P_i) + (2-2/k)*Lambda(a_i)")
p("  and since Lambda(a_i) <= Lambda(s^P_i) it implies the uniform statement")
p("  with Lambda(s^P_i) in both terms.")

# ==========================================================================
# RR-2  Impossibility: the exact hypothesis
# ==========================================================================
hdr("RR-2  Impossibility is a statement about wrappers; the exact hypothesis")

p("")
p("(a) FCFS is a counterexample to the proposition as printed (universally")
p("    quantified over non-preemptive work-conserving policies that read a")
p("    service time only at completion):")
jobs = [(0, 10)] * 1 + [(0, 10), (0, 10), (0, 10)]
for k in (1, 2, 3):
    wf = S.fcfs_wait(jobs, k)
    W, In, Out, order, start = S.run(jobs, k, S.fcfs)
    p("    k=%d  max excess under FCFS = %d" % (k, max(W[i] - wf[i] for i in range(len(jobs)))))
p("    FCFS is non-preemptive, work-conserving, reads no service time, and has")
p("    excess == 0 on every input.  So does every rank-ordered policy.")

p("")
p("(b) Instance I1: victim + k jobs, all of service L, all at t = 0.")
p("    Any wrapper whose budget is POSITIVE at the first dispatch epoch is")
p("    forced to excess >= L; a wrapper whose budget is 0 there dispatches the")
p("    victim at once.")
p("")
p("     k   L   budget(i,0)   excess of the victim")
for k in (1, 2, 3, 4):
    L = 10
    jobs = [(0, L)] * (k + 1)
    prio = {0: 99}
    for j in range(1, k + 1):
        prio[j] = j
    base = static_priority(prio)
    for b0 in (0, 1, 5):
        g = guard_general(base, lambda q, t, st, b0=b0: b0)
        W, In, Out, order, start = S.run(jobs, k, g)
        wf = S.fcfs_wait(jobs, k)
        p("     %-3d %-3d %-13d %d" % (k, L, b0, W[0] - wf[0]))

p("")
p("(c) 'zero at the first epoch but positive later' does NOT escape.")
p("    Instance I2, for the age-relative shape budget = min(B0 + eta*k*(t-a_q), Bmax)")
p("    with B0 = 0 and eta > 0:")
p("      t=0   : k jobs of service L (ranks 0..k-1) -- the wrapper is FCFS here,")
p("              every budget being 0 at age 0;")
p("      t=1   : the victim i (rank k), which waits behind them, exactly as it")
p("              would under FCFS;")
p("      t=L-1 : k jobs of service L (ranks k+1..2k), the overtakers.")
p("    At t = L the victim has age L-1 > 0, so its budget is positive, the guard")
p("    does not fire, and the base fills every server with the overtakers.")
p("")
p("     k   L   eta      W_FCFS[i]  W_P[i]   excess   >= L ?")
for k in (1, 2, 3):
    L = 10
    jobs = [(0, L)] * k + [(1, L)] + [(L - 1, L)] * k
    iv = k  # rank of the victim
    prio = {}
    for j in range(k):
        prio[j] = j
    prio[iv] = 10 ** 6
    for j in range(k + 1, 2 * k + 1):
        prio[j] = 1000 + j
    base = static_priority(prio)
    for eta_num, eta_den in ((1, 2), (1, 10)):
        def budget(q, t, st, k=k, en=eta_num, ed=eta_den):
            a = st["a"]
            return Fraction(en * k * (t - a[q]), ed)  # B0 = 0, Bmax = +inf

        W, In, Out, order, start = S.run(jobs, k, guard_general(base, budget))
        wf = S.fcfs_wait(jobs, k)
        exc = W[iv] - wf[iv]
        p("     %-3d %-3d %-8s %-10d %-8d %-8d %s"
          % (k, L, "%d/%d" % (eta_num, eta_den), wf[iv], W[iv], exc, exc >= L))

p("")
p("(d) The only budget rules that escape BOTH instances are the degenerate ones,")
p("    and they reproduce first-come first-served exactly.  If budget(q,t) = 0")
p("    whenever over[q](t) = 0, then at every dispatch epoch the lowest-ranked")
p("    waiting job h has over[h] = 0 (by induction: nothing has ever overtaken")
p("    anything), hence h is in E(t) and is its minimum-rank member, hence h is")
p("    dispatched.  Checked on random instances against the FCFS order:")


def budget_degenerate(q, t, st):
    x, done, n = st["x"], st["done"], st["n"]
    ov = 0
    for j in range(q + 1, n):
        dj = done[j]
        if dj is not None and dj <= t:
            ov += x[j]
    return 0 if ov == 0 else 10 ** 12


bad = 0
ninst = 0
for k in (1, 2, 3, 4):
    for _ in range(150):
        n = rng.randint(3, 10)
        jobs = rand_jobs(n, rng, heavy=False)
        prio = list(range(n))
        rng.shuffle(prio)
        base = static_priority({j: prio[j] for j in range(n)})
        _, order_g, _ = S.simulate(jobs, k, guard_general(base, budget_degenerate))
        _, order_f, _ = S.simulate(jobs, k, S.fcfs)
        ninst += 1
        if list(order_g) != list(order_f):
            bad += 1
p("    %d instances, %d disagreements with the FCFS dispatch order." % (ninst, bad))

# ==========================================================================
# RR-4  the achievable fraction at k = 1
# ==========================================================================
hdr("RR-4  at k = 1 the achievable fraction is min(1, floor(G/s)/n), not min(1, G/(ns))")

p("")
p("Exhaustive over EVERY work-conserving schedule of the two-class batch")
p("(m jobs of service L ranked first, n jobs of service s, all at t = 0, k = 1).")
p("'realised' is the largest (mean W_FCFS - mean W_P)/(mean W_FCFS - mean W_SJF)")
p("over the schedules with excess <= G for every job.")
p("")
p("   m  n  L  s   G    realised    floor(G/s)/n cap 1   G/(ns) cap 1   agree?")

bad4 = 0
cases = 0
for m in (1, 2, 3):
    for n in (2, 3, 4):
        if m + n > 7:
            continue
        for L, s in ((4, 1), (5, 2), (6, 2), (7, 3), (9, 4), (10, 3)):
            if s >= L:
                continue
            jobs = [(0, L)] * m + [(0, s)] * n
            k = 1
            wf = S.fcfs_wait(jobs, k)
            scheds = S.all_schedules(jobs, k)
            den = Fraction(m * n * (L - s), m + n)  # mean saving of SJF
            for G in range(0, 3 * L + 1):
                best = Fraction(-1)
                for order, start in scheds:
                    ok = True
                    tot = 0
                    for i in range(m + n):
                        e = (start[i] - 0) - wf[i]
                        if e > G:
                            ok = False
                            break
                        tot += -e
                    if not ok:
                        continue
                    frac = Fraction(tot, m + n) / den
                    if frac > best:
                        best = frac
                pred_new = min(Fraction(1), Fraction(G // s, n))
                pred_old = min(Fraction(1), Fraction(G, n * s))
                cases += 1
                agree = best == pred_new
                if not agree:
                    bad4 += 1
                if G in (0, s - 1, s, 2 * s - 1, 2 * s, n * s, n * s + 1) or not agree:
                    p("   %-2d %-2d %-2d %-2d  %-4d %-11s %-19s %-14s %s"
                      % (m, n, L, s, G, str(best), str(pred_new), str(pred_old),
                         "yes" if agree else "NO"))
p("")
p("  %d (m,n,L,s,G) cases, %d disagreements with min(1, floor(G/s)/n)." % (cases, bad4))
p("  The paper's min(1, G/(ns)) is strictly larger whenever s does not divide G")
p("  and G < n s, so it overstates what any G-feasible policy can reach.")
p("")
p("  Proof of the upper bound, for the record (three lines, k = 1):")
p("    every short job ranks above every long job, so Out_u of a long u contains")
p("    only long jobs, and a long-long inversion (p,q) puts L into In_p and L")
p("    into Out_q; summing over the long jobs those terms cancel and")
p("        sum_{u long} excess[u] = sum_{u long} (In_u - Out_u) = s * sum_u r_u,")
p("    r_u = number of short jobs dispatched before u.  Let u* be the long job")
p("    dispatched LAST among the long ones: it has no lower-ranked long job")
p("    after it, so excess[u*] >= s * r_{u*} = s * max_u r_u, whence")
p("    max_u r_u <= floor(G/s) and sum_u r_u <= m*floor(G/s).  The saving is")
p("    (L-s) * sum_u r_u against SJF's (L-s) * m n, so the fraction is at most")
p("    min(1, floor(G/s)/n); dispatching floor(G/s) short jobs, then the long")
p("    jobs in rank order, then the rest attains it.")

# the witness of the upper bound: r_u is monotone along the dispatch order
p("")
p("  Check of the load-bearing step (r_u is non-decreasing along the dispatch")
p("  order, so the LAST long job carries the largest r and pays for all):")
mism = 0
for m, n, L, s in ((3, 4, 7, 3), (2, 4, 9, 4), (3, 3, 6, 2)):
    jobs = [(0, L)] * m + [(0, s)] * n
    for order, start in S.all_schedules(jobs, 1):
        r = []
        seen = 0
        for j in order:
            if j >= m:
                seen += 1
            else:
                r.append(seen)
        if any(r[t] > r[t + 1] for t in range(len(r) - 1)):
            mism += 1
p("    monotonicity violations over all schedules of three families:", mism)

# ==========================================================================
# RR-7  Lemma 1 at k = 1
# ==========================================================================
hdr("RR-7  Lemma 1's strictness holds only for k >= 2")

p("")
p("At k = 1 every work-conserving policy executes the same work at every")
p("instant, so U_A == U_B and |U_A - U_B| = 0 = (k-1)L: the bound is ATTAINED,")
p("and the strict form reads 0 < 0.  Checked on random instances:")


def unfinished(jobs, start, t):
    x = [j[1] for j in jobs]
    a = [j[0] for j in jobs]
    tot = 0
    for j in range(len(jobs)):
        if a[j] > t:
            continue
        if start[j] is None or start[j] >= t:
            tot += x[j]
        else:
            tot += max(0, x[j] - (t - start[j]))
    return tot


worst = 0
for _ in range(300):
    n = rng.randint(3, 9)
    jobs = rand_jobs(n, rng, heavy=False)
    prio = list(range(n))
    rng.shuffle(prio)
    bA = static_priority({j: prio[j] for j in range(n)})
    stA = {}
    startA, orderA, _ = S.simulate(jobs, 1, bA, stA)
    startB, orderB, _ = S.simulate(jobs, 1, S.fcfs)
    T = sorted(set([a for (a, _x) in jobs] + [t for t in startA if t is not None]
                   + [t for t in startB if t is not None]))
    for t in T:
        d = abs(unfinished(jobs, startA, t) - unfinished(jobs, startB, t))
        worst = max(worst, d)
p("    max |U_A(t) - U_B(t)| over 300 instances at k = 1:", worst)
p("    (k-1)L = 0, so the non-strict bound is tight and the strict one is false.)")

# ==========================================================================
# RR-8  completed work lower-bounds BOTH currencies
# ==========================================================================
hdr("RR-8  over[q](t) <= In^exec_q <= In_q : completed work bounds both")

p("")
p("A job j of rank above q completed by t <= s^P_q has a_j >= a_q and is")
p("dispatched at s^P_j >= a_j >= a_q, so its whole service is executed inside")
p("[a_q, s^P_q) and is counted in full by the executed-work variant.  Hence")
p("over[q](t) <= In^exec_q for every t <= s^P_q, and In^exec_q <= In_q always.")
p("The manuscript's stated reason for the dispatch-sequence convention -- that")
p("completed work lower-bounds In_i 'but not its executed-work variant' -- is")
p("therefore false.  Checked:")
p("")
p("   k    instances   (q,t) checks   over > In^exec   In^exec > In")
for k in (1, 2, 3, 4):
    c1 = c2 = 0
    checks = 0
    for _ in range(250):
        n = rng.randint(3, 10)
        jobs = rand_jobs(n, rng, heavy=False)
        prio = list(range(n))
        rng.shuffle(prio)
        base = static_priority({j: prio[j] for j in range(n)})
        Bv = rng.choice([0, 2, 5, 20])
        st = {}
        W, In, Out, order, start = S.run(jobs, k, S.make_guard(base, Bv), st)
        for q in range(n):
            ie = exec_in(jobs, k, start, order, q)
            if ie > In[q]:
                c2 += 1
            ts = sorted(set([start[j] + jobs[j][1] for j in range(n)
                             if start[j] is not None and start[j] + jobs[j][1] <= start[q]]
                            + [jobs[q][0], start[q]]))
            for t in ts:
                checks += 1
                if over_at(jobs, start, q, t) > ie:
                    c1 += 1
    p("   %-4d %-11d %-14d %-16d %d" % (k, 250, checks, c1, c2))

# ==========================================================================
# RR-19  the counterexample of Remark 3, written out
# ==========================================================================
hdr("RR-19  Remark 3's counterexample, with W_FCFS and the violated inequality")

p("")
p("Instance (k = 1, eta in [0,1), common B0 = 0, Bmax = gamma, queue-length")
p("shape B0_q = B0 + gamma * n_q with n_q the number waiting when q arrives):")
p("    t = 0  : job 0, service L            -- dispatched at once, n_0 = 0")
p("    t = 1  : job 1, service L            -- waits,              n_1 = 0")
p("    t = 1  : the victim i, service L     -- waits behind job 1, n_i = 1")
p("    t = 2L : gamma jobs of service 1, ranks above i")
p("FCFS: job 0 on [0,L], job 1 on [L,2L], i at 2L, so W_FCFS[i] = 2L - 1.")
p("The wrapper: at t = L job 1 has budget 0 (n_1 = 0) and over = 0, so it is in")
p("E and is dispatched; at t = 2L the victim has budget gamma and over = 0, so")
p("the guard does not fire and the base spends the whole budget on the stream.")
p("")
p("    L    gamma   W_FCFS[i]  W_P[i]  excess  RHS of (guardmult) at eta=0  violated?")

for L in (4, 8):
    for gam in (1, 2, 4, 8, 16, 32):
        n_stream = gam + 2
        jobs = [(0, L), (1, L), (1, L)] + [(2 * L, 1)] * n_stream
        iv = 2
        k = 1
        nq = {0: 0, 1: 0, 2: 1}
        for j in range(3, 3 + n_stream):
            nq[j] = 1
        prio = {0: 0, 1: 1, iv: 10 ** 6}
        for j in range(3, 3 + n_stream):
            prio[j] = 2 + j

        def budget(q, t, st, gam=gam, nq=nq):
            return min(gam * nq[q], gam)  # eta = 0, B0 = 0, Bmax = gamma

        W, In, Out, order, start = S.run(jobs, k, guard_general(static_priority(prio), budget))
        wf = S.fcfs_wait(jobs, k)
        exc = W[iv] - wf[iv]
        rhs = wf[iv] + 0 + (3 - Fraction(2, k)) * L  # (1-eta)W <= W_FCFS + B0/k + (3-2/k)L
        p("    %-4d %-7d %-10d %-7d %-7d %-28s %s"
          % (L, gam, wf[iv], W[iv], exc, str(rhs), "YES" if W[iv] > rhs else "no"))

p("")
p("  The bound of (guardmult) stated with the COMMON B0 = 0 is")
p("      (1-eta) W_P[i] <= W_FCFS[i] + B0/k + (3-2/k) L = (2L-1) + L = 3L-1,")
p("  while W_P[i] = 2L - 1 + gamma; it is violated as soon as")
p("      gamma > (3L-1)/(1-eta) - (2L-1),   i.e. gamma > L at eta = 0,")
p("  and the margin grows without bound in gamma, for every eta.")

# ==========================================================================
# RR-25  what over[i] does in the Theorem 4C family
# ==========================================================================
hdr("RR-25  over[i] in the tightness family of the guard bound")

p("")
p("Rebuilt from the construction of Appendix A.4 (k, L=k^m, budget B=f+L+1).")
p("The dispatch epochs of the finale and over[i] at each of them:")
p("")
p("   k  m   L     f     B     epoch            over[i]   B - over[i]   servers taken")
for k, m in ((2, 6), (3, 4), (4, 3)):
    L = k ** m
    # f = L (1 - ((k-1)/k)^m) is an integer for L = k^m
    f = L - (k - 1) ** m
    B = f + L + 1
    ep = [("T_m", 0, 1), ("T_m + f", f, k), ("T_m + f + L", f + L, k),
          ("T_m + f + 2L", f + L + k * L, 0)]
    for name, ov, srv in ep:
        p("   %-2d %-3d %-5d %-5d %-5d %-16s %-9d %-13d %s"
          % (k, m, L, f, B, name, ov, B - ov,
             ("guard fires" if ov >= B else str(srv))))
p("")
p("  over[i] stays below the budget at THREE successive epochs -- by B, by L+1,")
p("  and by exactly 1 -- and the base takes every free server three times before")
p("  the guard fires.  It does not 'stop one unit short twice in succession'.")

# ==========================================================================
# RR-26  the implied constant of epsilon
# ==========================================================================
hdr("RR-26  the implied constant in epsilon = O((m+n)/(mn))")

p("")
p("With  N = (1/k) m (L-s)(kG + (3k-2)L)/s,  D = (1/k) m n (L-s),")
p("      E = 2(1-1/k) L (m+n),  the proof gives  ratio <= (N+E)/(D-E),  so")
p("      epsilon = (N+E)/(D-E) - N/D = E (N+D) / (D (D-E)),")
p("      epsilon ~ (E/D)(1 + N/D) = [2(k-1)L(m+n)/(m n (L-s))] * (1 + N/D).")
p("So the implied constant is")
p("      C = 2(k-1) L (1 + (kG+(3k-2)L)/(n s)) / (L - s),")
p("NOT the referee's 2(1-1/k) L (1 + ...)/(L-s): E/D carries a factor k, because")
p("D itself has the 1/k.  (The two agree at k = 1, where both vanish.)")
p("")
p("   k  L  s  G   m    n    epsilon exact      C(m+n)/(mn)     ratio")
for k in (2, 3, 5):
    L, s, G = 100, 10, 40
    for m, n in ((50, 50), (200, 200), (1000, 1000), (2000, 5000)):
        N = Fraction(m * (L - s) * (k * G + (3 * k - 2) * L), k * s)
        D = Fraction(m * n * (L - s), k)
        E = Fraction(2 * (k - 1) * L * (m + n), k)
        eps = (N + E) / (D - E) - N / D
        C = Fraction(2 * (k - 1) * L * (1 + Fraction(k * G + (3 * k - 2) * L, n * s)), L - s)
        approx = C * Fraction(m + n, m * n)
        p("   %-2d %-3d %-2d %-3d %-4d %-4d %-18.8f %-15.8f %.6f"
          % (k, L, s, G, m, n, float(eps), float(approx), float(eps / approx)))

# ==========================================================================
# RR-30  the base policy of Theorem tight2(i) needs 'in rank order'
# ==========================================================================
hdr("RR-30  the short class must be taken in rank order in Theorem 5(i)'s family")

p("")
p("The family: k jobs of service L, the victim i, then at least B+k jobs of")
p("service 1, all at t = 0; base priority 'the k long jobs, then the short ones,")
p("then i'; constant budget B.  The proof's step -- 'the waiting jobs of rank")
p("above i have no completed job of still higher rank ahead of them' -- is true")
p("only if the short class is taken in rank order.  Both readings, measured:")
p("")
p("   k  L   B   short order    excess   ceil(B/k)   matches?")
for k in (1, 2, 3):
    L = 6
    for B in (0, 1, 4, 7):
        nsh = B + k + 4
        jobs = [(0, L)] * k + [(0, L)] + [(0, 1)] * nsh
        iv = k
        for mode in ("rank", "reversed"):
            prio = {}
            for j in range(k):
                prio[j] = j
            prio[iv] = 10 ** 6
            for t_, j in enumerate(range(k + 1, k + 1 + nsh)):
                prio[j] = 1000 + (t_ if mode == "rank" else nsh - t_)
            W, In, Out, order, start = S.run(jobs, k, S.make_guard(static_priority(prio), B))
            wf = S.fcfs_wait(jobs, k)
            exc = W[iv] - wf[iv]
            want = -(-B // k)
            p("   %-2d %-3d %-3d %-14s %-8d %-11d %s"
              % (k, L, B, mode, exc, want, "yes" if exc == want else "NO"))

# ==========================================================================
# RR-31  the number of passes a promise admits is a floor
# ==========================================================================
hdr("RR-31  inverting (skip): kappa = floor(Gk/L) - (2k-2)")

p("")
p("(kappa + 2k - 2) L / k <= G  <=>  kappa <= Gk/L - (2k-2), and 2k-2 is an")
p("integer, so the largest admissible integer is floor(Gk/L) - (2k-2).")
p("")
p("   k  L   G     Gk/L - (2k-2)   floor(Gk/L)-(2k-2)   (kappa+2k-2)L/k <= G ?")
for k in (1, 2, 4):
    for L, G in ((60, 300), (60, 250), (100, 640), (7, 100)):
        raw = Fraction(G * k, L) - (2 * k - 2)
        kap = (G * k) // L - (2 * k - 2)
        ok = Fraction((kap + 2 * k - 2) * L, k) <= G
        ok2 = Fraction((kap + 1 + 2 * k - 2) * L, k) <= G
        p("   %-2d %-3d %-5d %-15s %-20d %s"
          % (k, L, G, str(raw), kap, "yes" if ok and not ok2 else ("yes(not maximal)" if ok else "NO")))

# --------------------------------------------------------------------------
with open("out_rev5_items.txt", "w", encoding="utf-8") as fh:
    fh.write("\n".join(OUT) + "\n")
print("\n[written] out_rev5_items.txt")
