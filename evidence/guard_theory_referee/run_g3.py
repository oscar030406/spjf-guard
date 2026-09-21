"""G3: removing assumptions.

(i)   Proposition 8, the no-global-L form, on heavy-tailed UNBOUNDED sizes.
      Checks the exact two-sided statement of theory.md
        -(k-1)(Lpref(i)+Lam^P_i) <= D <= (k-1)(Lpref(i)+Lam^F_i)
      and also the weaker "L -> Lpref everywhere" reading of the sentence
      "Theorem 1 ... holds with L replaced by the running prefix maximum",
        |D| <= 2(k-1) Lpref(i).
(ii)  Proposition 9, heterogeneous speeds.  The note never says which server a
      job goes to when several are free, so all four combinations of
      (P: fastest/slowest free server) x (FCFS: fastest/slowest) are tried,
      including MISMATCHED ones.  Exact integers: time is scaled by lcm(v).
(iv)  Proposition 11(a), timeout kill at elapsed service L: simulate the kill
      explicitly and compare with the relabelled instance x := min(x_raw, L).
"""
import sys, random
sys.dont_write_bytecode = True
from math import gcd
from refsim2 import (simulate, fcfs_chooser, make_choice_chooser,
                     make_guard_choice_chooser, in_out, sim_speeds)


def pareto_int(rng, alpha, scale=1):
    u = rng.random()
    while u <= 0.0:
        u = rng.random()
    return int(scale * (u ** (-1.0 / alpha)))


def in_service_max(a, x, start, comp, i):
    t = start[i]
    m = 0
    for j in range(len(a)):
        if j != i and start[j] <= t < comp[j] and x[j] > m:
            m = x[j]
    return m


def part_i(log):
    rng = random.Random(4242)
    nchk = 0
    bad_exact = 0
    bad_pref = 0
    bad_start = 0
    bad_t2 = 0
    bad_t2r = 0
    bad_c12 = 0
    worst_ratio = (0, 1)
    maxsize = 0
    for trial in range(120000):
        n = rng.randint(1, 9)
        k = rng.randint(1, 5)
        a = sorted(rng.randint(0, 8) for _ in range(n))
        x = [pareto_int(rng, rng.choice([0.6, 0.7, 1.0])) for _ in range(n)]
        if max(x) == 0:
            continue
        maxsize = max(maxsize, max(x))
        tp = [rng.randint(0, 8) for _ in range(n)]
        fst, fcp, fod = simulate(a, x, k, fcfs_chooser)
        st, cp, od = simulate(a, x, k, make_choice_chooser(tp))
        In, Out = in_out(x, od, n)
        G = max(st[i] - fst[i] for i in range(n))
        for i in range(n):
            nchk += 1
            D = k * (st[i] - fst[i]) - (In[i] - Out[i])
            lp = max(x[j] for j in range(n) if a[j] <= a[i])
            tstart = max(st[i], fst[i])
            lps = max(x[j] for j in range(n) if a[j] <= tstart)
            if abs(D) > 2 * (k - 1) * lps:
                bad_start += 1
            if In[i] > k * G + (3 * k - 2) * lp:
                bad_t2 += 1
            lpw = max(x[j] for j in range(n) if a[j] <= fst[i] + G)
            if In[i] > k * G + (3 * k - 2) * lpw:
                bad_t2r += 1
            if k * (st[i] - fst[i]) > (In[i] - Out[i]) + 2 * (k - 1) * lp:
                bad_c12 += 1
            lP = in_service_max(a, x, st, cp, i)
            lF = in_service_max(a, x, fst, fcp, i)
            if not (-(k - 1) * (lp + lP) <= D <= (k - 1) * (lp + lF)):
                bad_exact += 1
                if bad_exact <= 3:
                    log.write("  P8 EXACT FORM VIOLATED a=%s x=%s k=%d od=%s "
                              "i=%d D=%d Lpref=%d LamP=%d LamF=%d\n"
                              % (a, x, k, od, i, D, lp, lP, lF))
            if abs(D) > 2 * (k - 1) * lp:
                bad_pref += 1
                if bad_pref <= 3:
                    log.write("  P8 PREFIX-MAX READING VIOLATED a=%s x=%s k=%d "
                              "od=%s i=%d D=%d Lpref=%d\n"
                              % (a, x, k, od, i, D, lp))
            if k > 1 and abs(D) * worst_ratio[1] > worst_ratio[0] * lp:
                worst_ratio = (abs(D), lp)
    from fractions import Fraction
    log.write("G3(i) Pareto unbounded sizes: job-checks=%d  largest size seen=%d\n"
              % (nchk, maxsize))
    log.write("  violations of the exact Prop 8 two-sided form : %d\n" % bad_exact)
    log.write("  violations of |D| <= 2(k-1)Lpref(i)           : %d   <-- the\n"
              "      sentence 'Theorem 1 ... holds with L replaced by the running\n"
              "      prefix maximum' is FALSE when Lpref is read at a_i\n" % bad_pref)
    log.write("  violations of |D| <= 2(k-1)Lpref(max(s^P_i,s^F_i)) : %d   <-- the\n"
              "      repaired reading (prefix max at the START time) survives\n"
              % bad_start)
    log.write("  violations of Cor 1.2 with L -> Lpref(i)     : %d\n" % bad_c12)
    log.write("  violations of Thm 2   with L -> Lpref(i)     : %d   <-- also FALSE\n"
              % bad_t2)
    log.write("  violations of Thm 2   with L -> Lpref(s^F_i+G) : %d   <-- repaired\n"
              % bad_t2r)
    log.write("  worst |D|/Lpref (k>=2) = %s\n"
              % Fraction(worst_ratio[0], worst_ratio[1]))


def part_ii(log):
    rng = random.Random(777)
    nchk = 0
    bad = {}
    badg = {}
    worst = {}
    for trial in range(30000):
        n = rng.randint(1, 8)
        k = rng.randint(2, 4)
        v = [rng.randint(1, 4) for _ in range(k)]
        lc = 1
        for s in v:
            lc = lc * s // gcd(lc, s)
        V = sum(v)
        a = sorted(rng.randint(0, 6) * lc for _ in range(n))
        L = rng.randint(1, 5)
        x = [rng.randint(0, L) for _ in range(n)]
        if max(x) == 0:
            continue
        L = max(x)
        tp = [rng.randint(0, 8) for _ in range(n)]
        B = rng.randint(0, 3 * L * k)
        for pa in ("fastest", "slowest"):
            for fa in ("fastest", "slowest"):
                fst, fcp, fod, _ = sim_speeds(a, x, v, fcfs_chooser, assign=fa)
                st, cp, od, _ = sim_speeds(a, x, v, make_choice_chooser(tp),
                                           assign=pa)
                In, Out = in_out(x, od, n)
                key = (pa, fa)
                for i in range(n):
                    nchk += 1
                    D = V * (st[i] - fst[i]) - lc * (In[i] - Out[i])
                    if abs(D) > 2 * (k - 1) * L * lc:
                        bad[key] = bad.get(key, 0) + 1
                        if bad[key] <= 2:
                            log.write("  P9 VIOLATED %s a=%s x=%s v=%s od=%s "
                                      "i=%d D=%d bound=%d\n"
                                      % (key, a, x, v, od, i, D,
                                         2 * (k - 1) * L * lc))
                    r = (abs(D), L * lc)
                    if key not in worst or r[0] * worst[key][1] > worst[key][0] * r[1]:
                        worst[key] = r
                # guard bound  V*(W_g - W_F) <= lc*(B + (3k-2)L)
                gch = make_guard_choice_chooser(tp, B, x, n)
                gst, gcp, god, _ = sim_speeds(a, x, v, gch, assign=pa)
                for i in range(n):
                    if V * (gst[i] - fst[i]) > lc * (B + (3 * k - 2) * L):
                        badg[key] = badg.get(key, 0) + 1
                        if badg[key] <= 2:
                            log.write("  P9 GUARD BOUND VIOLATED %s a=%s x=%s "
                                      "v=%s B=%d i=%d\n" % (key, a, x, v, B, i))
    from fractions import Fraction
    log.write("\nG3(ii) heterogeneous speeds: job-checks=%d\n" % nchk)
    for key in sorted(worst):
        log.write("  P(%s)/FCFS(%s): identity violations=%d guard violations=%d "
                  "worst |D|/(L*lcm) = %s\n"
                  % (key[0], key[1], bad.get(key, 0), badg.get(key, 0),
                     Fraction(worst[key][0], worst[key][1])))


def part_iv(log):
    """timeout kill at elapsed service L, simulated explicitly."""
    rng = random.Random(31337)
    nchk = 0
    bad = 0
    mism = 0
    for trial in range(40000):
        n = rng.randint(1, 8)
        k = rng.randint(1, 4)
        L = rng.randint(1, 5)
        a = sorted(rng.randint(0, 6) for _ in range(n))
        raw = [pareto_int(rng, 0.6) for _ in range(n)]
        # explicit kill: the executed work of j is min(raw_j, L) in BOTH runs
        xk = [min(r, L) for r in raw]
        if max(xk) == 0:
            continue
        tp = [rng.randint(0, 8) for _ in range(n)]
        fst, fcp, fod = simulate(a, xk, k, fcfs_chooser)
        st, cp, od = simulate(a, xk, k, make_choice_chooser(tp))
        In, Out = in_out(xk, od, n)
        Lk = max(xk)
        if Lk > L:
            mism += 1
        for i in range(n):
            nchk += 1
            D = k * (st[i] - fst[i]) - (In[i] - Out[i])
            if abs(D) > 2 * (k - 1) * L:
                bad += 1
                if bad <= 3:
                    log.write("  P11a VIOLATED a=%s raw=%s L=%d k=%d i=%d D=%d\n"
                              % (a, raw, L, k, i, D))
    log.write("\nG3(iv) timeout kill at elapsed L, raw sizes Pareto(0.6) "
              "unbounded: job-checks=%d violations=%d (max executed work > L "
              "in %d instances)\n" % (nchk, bad, mism))
    log.write("  note: the kill makes the executed work min(x,L) in both runs, "
              "so the relabelled instance IS the original model; the claim is "
              "true but tautological, and In/Out must then be read in EXECUTED "
              "work, not raw work.\n")
    # does the statement survive if In/Out are read in RAW work?
    rng = random.Random(999)
    bad_raw = 0
    nraw = 0
    for trial in range(20000):
        n = rng.randint(2, 7)
        k = rng.randint(1, 3)
        L = rng.randint(1, 4)
        a = sorted(rng.randint(0, 5) for _ in range(n))
        raw = [pareto_int(rng, 0.6) for _ in range(n)]
        xk = [min(r, L) for r in raw]
        if max(xk) == 0:
            continue
        tp = [rng.randint(0, 8) for _ in range(n)]
        fst, _, _ = simulate(a, xk, k, fcfs_chooser)
        st, _, od = simulate(a, xk, k, make_choice_chooser(tp))
        In, Out = in_out(raw, od, n)     # RAW work
        for i in range(n):
            nraw += 1
            D = k * (st[i] - fst[i]) - (In[i] - Out[i])
            if abs(D) > 2 * (k - 1) * L:
                bad_raw += 1
    log.write("  if In/Out are computed on RAW sizes instead: %d violations in "
              "%d job-checks\n" % (bad_raw, nraw))


def main():
    with open("out_g3.txt", "w") as log:
        part_i(log)
        part_ii(log)
        part_iv(log)
    print(open("out_g3.txt").read())


if __name__ == "__main__":
    main()
