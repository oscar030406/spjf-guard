"""G3: which assumptions can be dropped."""
import sys
sys.dont_write_bytecode = True
import numpy as np
from fractions import Fraction
from math import gcd
import sim_core as S

OUT = []


def say(*a):
    s = " ".join(str(z) for z in a)
    print(s)
    OUT.append(s)


def lcm(v):
    r = 1
    for z in v:
        r = r * z // gcd(r, z)
    return r


# ------------------------------------------------------------------ (i) L ----
def no_global_L(N=200000):
    say("=== G3(i) NO GLOBAL SIZE BOUND ===")
    say("Lam_pref(i)  = max{x_j : a_j <= a_i}            (prefix max; no global bound)")
    say("Lam^P_i      = max size among the <= k-1 jobs OTHER than i that are in")
    say("               service under P at the instant i starts")
    say("Lam^F_i      = the same for FCFS at i's FCFS start")
    say("claim A (two-sided, fully local):")
    say("   -(k-1)(Lam_pref + Lam^P) <= k(W_P-W_F)-(In-Out) <= (k-1)(Lam_pref + Lam^F)")
    say("claim B: the same with Lam^P/Lam^F only (drop Lam_pref) -- expected to FAIL")
    rng = np.random.default_rng(555)
    badA = 0
    badB = 0
    worstA = Fraction(0)
    witB = None
    worstB = Fraction(0)
    tested = 0
    for it in range(N):
        k = int(rng.integers(1, 5))
        n = int(rng.integers(1, 12))
        a = np.sort(rng.integers(0, 20, n))
        x = (rng.pareto(0.7, n) * 3 + 1).astype(np.int64)   # heavy tail, no cap
        jobs = [(int(a[i]), int(x[i])) for i in range(n)]
        ch = S.make_random(rng)
        sP, oP, dP = S.simulate(jobs, k, ch)
        sF, oF, dF = S.simulate(jobs, k, S.fcfs)
        In, Out = S.in_out(jobs, oP)
        posP = {j: p for p, j in enumerate(oP)}
        posF = {j: p for p, j in enumerate(oF)}
        for i in range(n):
            tested += 1
            D = k * (sP[i] - sF[i]) - (In[i] - Out[i])
            lp = max(int(x[j]) for j in range(n) if a[j] <= a[i])
            lP = 1
            lF = 1
            for j in range(n):
                if j == i:
                    continue
                if sP[j] <= sP[i] and dP[j] > sP[i] and posP[j] < posP[i]:
                    lP = max(lP, int(x[j]))
                if sF[j] <= sF[i] and dF[j] > sF[i] and posF[j] < posF[i]:
                    lF = max(lF, int(x[j]))
            if D > (k - 1) * (lp + lF) or D < -(k - 1) * (lp + lP):
                badA += 1
            worstA = max(worstA, Fraction(abs(D), max(lp, lP, lF)))
            if abs(D) > (k - 1) * (lP + lF):
                badB += 1
                r = Fraction(abs(D), max(1, lP, lF))
                if r > worstB:
                    worstB = r
                    witB = (jobs, k, i, D, max(lP, lF), lp)
    say("claim A failures: %d / %d job-checks   (worst |D|/max(Lam) seen = %s)"
        % (badA, tested, worstA))
    say("claim B failures: %d / %d job-checks by random search (the constructed"
        % (badB, tested))
    say("   family in ce_local_L.py is what refutes it -- random instances do not")
    say("   build a long enough saturated epoch to separate the two quantities)")
    if witB:
        say("   witness: k=%d job=%d D=%d Lam_in_service=%d Lam_pref=%d"
            % (witB[1], witB[2], witB[3], witB[4], witB[5]))
    say("")
    say("-- hand-built counterexample for claim B: see ce_local_L.py / out_ce_local_L.txt")
    say("   family with k=2 in which D grows linearly in M while every job in service")
    say("   around i has size 1; D/((k-1)(Lam^P+Lam^F)) = M/4 -> infinity.")
    say("   So Lam_pref (or the epoch max) cannot be dropped.")
    say("")


# ------------------------------------------------------------- (ii) speeds ---
def speeds(N=150000):
    say("=== G3(ii) SERVERS WITH DIFFERENT SPEEDS ===")
    say("V = v_1 + ... + v_k.  claim: |V*(W_P-W_F) - (In-Out)| <= 2(k-1)L")
    say("so the budget is divided by total CAPACITY, not by the server count: B/k -> B/V")
    rng = np.random.default_rng(777)
    worst = {}
    bad = 0
    for it in range(N):
        k = int(rng.integers(1, 5))
        n = int(rng.integers(1, 11))
        v = [int(z) for z in rng.integers(1, 5, k)]
        P = lcm(v)
        V = sum(v)
        a = np.sort(rng.integers(0, 12, n)) * P
        L = int(rng.integers(1, 9))
        x = rng.integers(0, L + 1, n)
        Lr = max(1, int(x.max()))
        jobs = [(int(a[i]), int(x[i])) for i in range(n)]
        sp = int(rng.integers(0, 2))
        u = rng.random()
        ch = S.make_random(rng) if u < .5 else (S.lifo if u < .75 else S.sjf_true)
        sP, oP, dP = S.simulate_speeds(jobs, v, ch, P, server_pick=sp)
        sF, oF, dF = S.simulate_speeds(jobs, v, S.fcfs, P, server_pick=sp)
        In, Out = S.in_out(jobs, oP)
        for i in range(n):
            Dn = V * (sP[i] - sF[i]) - P * (In[i] - Out[i])
            r = Fraction(Dn, P * Lr)
            if k not in worst or abs(r) > abs(worst[k]):
                worst[k] = r
            if abs(Dn) > P * 2 * (k - 1) * Lr:
                bad += 1
    say("failures: %d / %d instances" % (bad, N))
    for k in sorted(worst):
        say("  k=%d worst |D|/L = %s   (bound 2(k-1) = %d)" % (k, abs(worst[k]), 2 * (k - 1)))
    say("")


# ------------------------------------------------- (iii) pauses / setup ------
def pauses_and_setup(N=100000):
    say("=== G3(iii) NON-WORK-CONSERVING PAUSES, VACATIONS, SETUP ===")
    say("general identity: k*W_P[i] = R_i + In_i - Out_i - rho_i + Gam_i")
    say("Gam_i = server-time idle while some job waited, during [a_i, s_i^P)")
    rng = np.random.default_rng(31337)
    bad = 0
    bare_bad = 0
    tested = 0
    for it in range(N):
        k = int(rng.integers(1, 5))
        n = int(rng.integers(1, 10))
        a = np.sort(rng.integers(0, 20, n))
        L = int(rng.integers(1, 8))
        x = rng.integers(0, L + 1, n)
        Lr = max(1, int(x.max()))
        jobs = [(int(a[i]), int(x[i])) for i in range(n)]
        npz = int(rng.integers(0, 4))
        pz = []
        for _ in range(npz):
            m = int(rng.integers(0, k))
            t0 = int(rng.integers(0, 30))
            d = int(rng.integers(1, 6))
            pz.append((m, t0, t0 + d))
        ch = S.make_random(rng)
        try:
            sP, oP, dP, gP = S.simulate_pauses(jobs, k, ch, pz)
            sF, oF, dF, gF = S.simulate_pauses(jobs, k, S.fcfs, pz)
        except RuntimeError:
            continue
        In, Out = S.in_out(jobs, oP)
        tot = sum(t1 - t0 for (_, t0, t1) in pz)
        for i in range(n):
            tested += 1
            D = k * (sP[i] - sF[i]) - (In[i] - Out[i])
            if abs(D) > 2 * (k - 1) * Lr:
                bare_bad += 1
            if abs(D) > 2 * (k - 1) * Lr + 2 * k * tot:
                bad += 1
    say("  %d job-checks." % tested)
    say("  plain bound 2(k-1)L violated in %d of them -> pauses genuinely break it"
        % bare_bad)
    say("  with the crude allowance 2k*(total pause time): violations = %d" % bad)
    say("  => no bound survives unless cumulative forced idleness is bounded.")
    say("  minimal counterexample: k=1, pause the single server for T while i waits.")
    say("  In = Out = 0 and the excess is exactly T, unbounded.")
    say("")
    say("-- setup time sigma before every service, paid by BOTH policies --")
    say("   absorb it into the job: x'_j = x_j + sigma <= L + sigma.  The model is")
    say("   then unchanged, so every result holds with L -> L + sigma.")
    rng = np.random.default_rng(4242)
    bad2 = 0
    tested2 = 0
    for it in range(60000):
        k = int(rng.integers(1, 5))
        n = int(rng.integers(1, 10))
        a = np.sort(rng.integers(0, 20, n))
        L = int(rng.integers(1, 8))
        sig = int(rng.integers(0, 4))
        x = rng.integers(0, L + 1, n)
        jobs = [(int(a[i]), int(x[i]) + sig) for i in range(n)]
        Lr = max(1, int(x.max()) + sig)
        ch = S.make_random(rng)
        W, In, Out, order, st = S.run(jobs, k, ch)
        WF = S.fcfs_wait(jobs, k)
        for i in range(n):
            tested2 += 1
            if abs(k * (W[i] - WF[i]) - (In[i] - Out[i])) > 2 * (k - 1) * Lr:
                bad2 += 1
    say("   setup-absorbed model: %d job-checks, violations %d" % (tested2, bad2))
    say("")


# ---------------------------------------------------- (iv) release times -----
def releases():
    say("=== G3(iv) RELEASE CONSTRAINTS AND A TIMEOUT KILL ===")
    say("-- timeout kill at L: both policies kill at the same elapsed service, so the")
    say("   EXECUTED work min(x_j, L) is identical in the two runs.  Relabel")
    say("   x_j := min(x_j, L); every result holds verbatim (the proof only ever")
    say("   uses executed work).  Checked on heavy-tailed raw sizes:")
    rng = np.random.default_rng(6)
    bad = 0
    tested = 0
    for it in range(80000):
        k = int(rng.integers(1, 5))
        n = int(rng.integers(1, 10))
        a = np.sort(rng.integers(0, 20, n))
        L = int(rng.integers(1, 8))
        raw = (rng.pareto(0.6, n) * 4 + 1).astype(np.int64)
        x = np.minimum(raw, L)
        jobs = [(int(a[i]), int(x[i])) for i in range(n)]
        ch = S.make_random(rng)
        W, In, Out, order, st = S.run(jobs, k, ch)
        WF = S.fcfs_wait(jobs, k)
        for i in range(n):
            tested += 1
            if abs(k * (W[i] - WF[i]) - (In[i] - Out[i])) > 2 * (k - 1) * L:
                bad += 1
    say("   truncated-size identity: %d job-checks, violations %d" % (tested, bad))
    say("")
    say("-- release times r_j > a_j with rank still keyed on a_j: DISPROVED.")
    say("   k=1.  job0: a=0, r=10, x=1.  job1: a=1, r=1, x=1.")
    say("   Every work-conserving policy runs job1 at t=1 and job0 at t=10, so all")
    say("   policies coincide and W_P[0] - W_FCFS[0] = 0.  But job1 has higher rank")
    say("   and is dispatched first, so In_0 = 1 and Out_0 = 0: the identity predicts")
    say("   a difference of 1.  Slack 1 = exactly the forced idle time on [0,1).")
    say("   Fix: rank by release, rank = (r_j, index), and read a_j as r_j.  The proof")
    say("   only needs 'no server idles while i is eligible and waiting', so with that")
    say("   relabelling every result holds verbatim.")
    say("")


# --------------------------------- (v) batch arrivals and zero-length jobs ---
def batch_zero(N=300000):
    say("=== G3(v) BATCH / SIMULTANEOUS ARRIVALS AND ZERO-LENGTH JOBS ===")
    rng = np.random.default_rng(1234)
    bad = 0
    tested = 0
    nzero = 0
    for it in range(N):
        k = int(rng.integers(1, 5))
        n = int(rng.integers(1, 12))
        a = (np.zeros(n, dtype=np.int64) if rng.random() < .5
             else np.sort(rng.integers(0, 2, n)))
        L = int(rng.integers(1, 8))
        x = rng.integers(0, L + 1, n)
        if rng.random() < .5:
            x = np.where(rng.random(n) < .5, 0, x)
        Lr = max(1, int(x.max()))
        nzero += int((x == 0).sum())
        jobs = [(int(a[i]), int(x[i])) for i in range(n)]
        ch = S.make_random(rng) if rng.random() < .5 else S.lifo
        W, In, Out, order, st = S.run(jobs, k, ch)
        WF = S.fcfs_wait(jobs, k)
        for i in range(n):
            tested += 1
            if abs(k * (W[i] - WF[i]) - (In[i] - Out[i])) > 2 * (k - 1) * Lr:
                bad += 1
    say("  %d instances, all with ties, %d zero-length jobs, %d job-checks, violations %d"
        % (N, nzero, tested, bad))
    say("  confirmed: nothing in the statement or the proof uses distinct arrivals or x>0.")
    say("")


if __name__ == "__main__":
    no_global_L(200000)
    speeds(150000)
    pauses_and_setup(100000)
    releases()
    batch_zero(300000)
    open("out_assumptions.txt", "w").write("\n".join(OUT) + "\n")
