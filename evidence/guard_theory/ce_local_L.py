"""Counterexample for G3(i) claim B: the additive constant in the identity cannot
be localised to the jobs in service around i.  Family indexed by M."""
import sys
sys.dont_write_bytecode = True
import sim_core as S

OUT = []


def say(*a):
    s = " ".join(str(z) for z in a)
    print(s)
    OUT.append(s)


def build(M, tail=400):
    """k=2.  rank 0 is one job of work M; then 2M-2 unit jobs at t=0; then a
    saturating stream of 2 unit jobs per tick, starting well after the gap has
    been created.  Everything except rank 0 has size 1."""
    nsm = 2 * M - 2
    jobs = [(0, M)] + [(0, 1)] * nsm
    t0 = (3 * M) // 2
    for r in range(tail):
        jobs.append((t0 + r, 1))
        jobs.append((t0 + r, 1))
    return jobs


def defer_big(t, waiting, state):
    x = state["x"]
    for c in range(len(waiting)):
        if x[waiting[c]] == 1:
            return c
    return 0


say("=== COUNTEREXAMPLE: the L in the identity is not a local quantity (k=2) ===")
say("instance: one job of work M at t=0 (rank 0), then 2M-2 unit jobs at t=0,")
say("then 2 unit jobs per tick from t=3M/2 on, so both policies stay saturated.")
say("P defers the big job behind every unit job; FCFS does not.")
say("Every job other than rank 0 has size 1, so for any job i arriving in the")
say("saturated tail, Lam^P_i = Lam^F_i = 1 and the localised bound is (k-1)*2 = 2.")
say("")
say("   M     job i   a_i    D=k(W_P-W_F)-(In-Out)   Lam_in_service   D / bound")
for M in (10, 20, 40, 80, 160):
    jobs = build(M)
    k = 2
    n = len(jobs)
    a = [j[0] for j in jobs]
    x = [j[1] for j in jobs]
    sP, oP, dP = S.simulate(jobs, k, defer_big)
    sF, oF, dF = S.simulate(jobs, k, S.fcfs)
    In, Out = S.in_out(jobs, oP)
    posP = {j: p for p, j in enumerate(oP)}
    posF = {j: p for p, j in enumerate(oF)}
    bigdone = max(dP[0], dF[0])
    best = None
    for i in range(n):
        if a[i] <= bigdone:
            continue
        D = k * (sP[i] - sF[i]) - (In[i] - Out[i])
        lP = 1
        lF = 1
        for j in range(n):
            if j == i:
                continue
            if sP[j] <= sP[i] and dP[j] > sP[i] and posP[j] < posP[i]:
                lP = max(lP, x[j])
            if sF[j] <= sF[i] and dF[j] > sF[i] and posF[j] < posF[i]:
                lF = max(lF, x[j])
        bound = (k - 1) * (lP + lF)
        if best is None or D / bound > best[0]:
            best = (D / bound, i, a[i], D, max(lP, lF), bound)
    say("  %4d   %5d   %4d   %18d   %14d   %8.1f"
        % (M, best[1], best[2], best[3], best[4], best[0]))
say("")
say("D grows linearly in M while every job in service near i has size 1, so no")
say("bound in terms of the sizes local to i's wait can exist.  The big job is")
say("already finished (under both policies) before any of these jobs arrives.")
say("The prefix max Lam_pref = M does bound it, as claim A says.")

open("out_ce_local_L.txt", "w").write("\n".join(OUT) + "\n")
