"""G1: net-overtake identity.  Self-test, exhaustive enumeration, random attack."""
import sys
sys.dont_write_bytecode = True
import numpy as np
from fractions import Fraction
import sim_core as S

OUT = []
def say(*a):
    s = " ".join(str(z) for z in a)
    print(s); OUT.append(s)


# ---------------------------------------------------------------- self test --
def selftest():
    say("=== SELF-TEST OF THE SIMULATOR (verify the tool before trusting it) ===")
    rng = np.random.default_rng(7)
    bad = 0
    for _ in range(20000):
        n = int(rng.integers(1, 9))
        a = np.sort(rng.integers(0, 30, n)); x = rng.integers(1, 8, n)
        jobs = [(int(a[i]), int(x[i])) for i in range(n)]
        W = S.fcfs_wait(jobs, 1)
        # Lindley
        LW = [0]*n
        for i in range(1, n):
            LW[i] = max(0, LW[i-1] + int(x[i-1]) - (int(a[i]) - int(a[i-1])))
        if LW != W: bad += 1
    say("k=1 FCFS vs Lindley recursion, 20000 instances, mismatches =", bad)

    # work conservation + no idling while a job waits, k=1..4, random policies
    rng = np.random.default_rng(11)
    bad2 = 0; bad3 = 0
    for _ in range(20000):
        n = int(rng.integers(1, 10)); k = int(rng.integers(1, 5))
        a = np.sort(rng.integers(0, 25, n)); x = rng.integers(0, 9, n)
        jobs = [(int(a[i]), int(x[i])) for i in range(n)]
        ch = S.make_random(rng)
        st, order, done = S.simulate(jobs, k, ch)
        if sorted(order) != list(range(n)): bad2 += 1
        for i in range(n):
            if st[i] < a[i]: bad3 += 1
        # every server busy while a job waits: total work done in [a_i, s_i) == k*W_i
        In, Out = S.in_out(jobs, order)
        for i in range(n):
            lo, hi = a[i], st[i]
            tot = 0
            for j in range(n):
                if j == i: continue
                s0, s1 = st[j], done[j]
                tot += max(0, min(s1, hi) - max(s0, lo))
            if tot != k*(hi-lo): bad3 += 1
    say("dispatch completeness failures =", bad2, "; start>=arrival / busy-server identity failures =", bad3)
    say("")


# --------------------------------------------- exhaustive over ALL schedules --
def exhaustive():
    say("=== G1 EXHAUSTIVE: every work-conserving schedule of every small instance ===")
    say("slack D = k*(W_P[i]-W_FCFS[i]) - (In_i-Out_i);  claim |D| <= 2(k-1)L")
    rng = np.random.default_rng(3)
    for k in (1, 2, 3, 4):
        worst_hi = (-10**9, None); worst_lo = (10**9, None)
        nsched = 0; ninst = 0
        Lset = 4
        for trial in range(4000 if k <= 3 else 2000):
            n = int(rng.integers(2, 7 if k <= 2 else 7))
            a = np.sort(rng.integers(0, 6, n)); x = rng.integers(0, Lset+1, n)
            jobs = [(int(a[i]), int(x[i])) for i in range(n)]
            L = max(1, int(x.max()))
            WF = S.fcfs_wait(jobs, k)
            scheds = S.all_schedules(jobs, k, cap=60000)
            ninst += 1
            for order, start in scheds:
                nsched += 1
                In, Out = S.in_out(jobs, order)
                for i in range(n):
                    W = start[i] - jobs[i][0]
                    D = k*(W - WF[i]) - (In[i]-Out[i])
                    r = Fraction(D, L)
                    if r > worst_hi[0]: worst_hi = (r, (jobs, k, order, i, D, L))
                    if r < worst_lo[0]: worst_lo = (r, (jobs, k, order, i, D, L))
        say("k=%d  instances=%d schedules=%d   max D/L = %s   min D/L = %s   [bound +-2(k-1) = +-%d]"
            % (k, ninst, nsched, worst_hi[0], worst_lo[0], 2*(k-1)))
        if k > 1:
            for tag, w in (("argmax", worst_hi), ("argmin", worst_lo)):
                jobs, kk, order, i, D, L = w[1]
                say("   %s witness: k=%d jobs=%s order=%s job=%d D=%d L=%d" % (tag, kk, jobs, list(order), i, D, L))
    say("")


# ------------------------------------------------------------- random attack --
def random_attack(N=1000000):
    say("=== G1 RANDOM ATTACK: %d instances, random/adversarial policies ===" % N)
    rng = np.random.default_rng(20260919)
    worst = {k: (Fraction(-10**9), Fraction(10**9)) for k in (1,2,3,4)}
    wit = {k: [None, None] for k in (1,2,3,4)}
    pol_names = ["random", "lifo", "sjf", "ljf", "badpred", "guardB"]
    for it in range(N):
        k = int(rng.integers(1, 5))
        n = int(rng.integers(1, 13))
        mode = int(rng.integers(0, 4))
        if mode == 0:            # bursty: many ties
            a = np.sort(rng.integers(0, 3, n))
        elif mode == 1:          # all simultaneous
            a = np.zeros(n, dtype=np.int64)
        elif mode == 2:
            a = np.sort(rng.integers(0, 40, n))
        else:                    # heavy load
            a = np.sort(rng.integers(0, 8, n))
        L = int(rng.integers(1, 12))
        x = rng.integers(0, L+1, n)           # zero-length jobs included
        if rng.random() < 0.3:
            x[rng.integers(0, n)] = L          # make sure L is attained sometimes
        Lr = max(1, int(x.max()))
        jobs = [(int(a[i]), int(x[i])) for i in range(n)]
        p = int(rng.integers(0, len(pol_names)))
        st = {}
        if p == 0: ch = S.make_random(rng)
        elif p == 1: ch = S.lifo
        elif p == 2: ch = S.sjf_true
        elif p == 3: ch = S.ljf_true
        elif p == 4:
            st['pred'] = list(rng.permutation(n))       # adversarial prediction
            ch = S.by_pred
        else:
            base = S.by_pred if rng.random() < .5 else S.make_random(rng)
            st['pred'] = list(rng.permutation(n))
            ch = S.make_guard(base, int(rng.integers(0, 4*Lr+1)))
        W, In, Out, order, start = S.run(jobs, k, ch, st)
        WF = S.fcfs_wait(jobs, k)
        hi, lo = worst[k]
        for i in range(n):
            D = k*(W[i]-WF[i]) - (In[i]-Out[i])
            r = Fraction(D, Lr)
            if r > hi: hi = r; wit[k][0] = (jobs, order, i, D, Lr, pol_names[p])
            if r < lo: lo = r; wit[k][1] = (jobs, order, i, D, Lr, pol_names[p])
        worst[k] = (hi, lo)
        if it % 200000 == 0 and it: say("   ... %d" % it)
    for k in (1,2,3,4):
        hi, lo = worst[k]
        say("k=%d  max D/L = %s   min D/L = %s   [bound +-2(k-1) = +-%d]" % (k, hi, lo, 2*(k-1)))
        for tag, w in (("argmax", wit[k][0]), ("argmin", wit[k][1])):
            if w and k > 1:
                say("   %s: jobs=%s order=%s job=%d D=%d L=%d pol=%s" % (tag, w[0], list(w[1]), w[2], w[3], w[4], w[5]))
    say("")


if __name__ == "__main__":
    selftest()
    exhaustive()
    random_attack(1000000)
    open("out_identity.txt", "w").write("\n".join(OUT) + "\n")
