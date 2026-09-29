"""G5: how much of the FCFS -> SJF mean-wait gap a per-job excess guarantee G
can buy, on a two-class worst-case family."""
import sys
sys.dont_write_bytecode = True
import itertools
import numpy as np
import sim_core as S

OUT = []


def say(*a):
    s = " ".join(str(z) for z in a)
    print(s)
    OUT.append(s)


def mean(v):
    return sum(v) / len(v)


def best_G_bounded_schedule(jobs, k, G, cap=400000):
    """Exhaustively minimise mean wait over all work-conserving schedules whose
    per-job excess is <= G.  Only usable for tiny instances; it is the ground
    truth the closed-form bound is compared against."""
    WF = S.fcfs_wait(jobs, k)
    n = len(jobs)
    best = None
    for order, start in S.all_schedules(jobs, k, cap=cap):
        W = [start[i] - jobs[i][0] for i in range(n)]
        if max(W[i] - WF[i] for i in range(n)) <= G:
            m = sum(W)
            if best is None or m < best:
                best = m
    return best, sum(WF)


def part_exact():
    say("=== G5.1  EXACT: the best a G-guaranteed policy can do, small instances ===")
    say("m large jobs of size L then n small jobs of size 1, all at t=0, k=1.")
    say("optimum over ALL schedules with per-job excess <= G, by exhaustive search.")
    say("  m  n  L   G   sum W FCFS  sum W SJF  sum W best(G)  fraction of gap closed  bound G/(n*1)+1/m")
    for (m, n, L) in ((2, 3, 4), (2, 4, 4), (3, 3, 5), (2, 5, 6)):
        jobs = [(0, L)] * m + [(0, 1)] * n
        k = 1
        sF = sum(S.fcfs_wait(jobs, k))
        WS, _, _, _, _ = S.run(jobs, k, S.sjf_true)
        sS = sum(WS)
        for G in (0, 1, 2, L, 2 * L):
            b, _ = best_G_bounded_schedule(jobs, k, G)
            frac = (sF - b) / (sF - sS) if sF > sS else 0.0
            say("  %d  %d  %d  %2d  %10d  %9d  %13d  %22.3f  %17.3f"
                % (m, n, L, G, sF, sS, b, frac, min(1.0, G / (n * 1.0) + 1.0 / m)))
    say("")


def part_family():
    say("=== G5.2  THE FAMILY (larger, guard-based, k=1 and k=4) ===")
    say("m large jobs of size L (ranks 0..m-1) then n small jobs of size s, all at")
    say("t=0.  The base policy is SJF (it wants to serve every small job first);")
    say("the guard with budget B caps how much small work may pass a large job.")
    say("  k   m    n   L   s     B   meanW FCFS  meanW SJF  meanW guard  gap closed  G=B/k+(3-2/k)L  bound kG/(n*s)+1/m")
    for k in (1, 4):
        for (m, n, L, s) in ((8, 40, 100, 1), (8, 40, 100, 10), (20, 100, 100, 5)):
            jobs = [(0, L)] * m + [(0, s)] * n
            WF = S.fcfs_wait(jobs, k)
            WS, _, _, _, _ = S.run(jobs, k, S.sjf_true)
            for B in (0, n * s // 8, n * s // 2, 2 * n * s):
                Wg, _, _, _, _ = S.run(jobs, k, S.make_guard(S.sjf_true, B))
                gap = mean(WF) - mean(WS)
                closed = (mean(WF) - mean(Wg)) / gap if gap > 0 else 0.0
                G = B / k + (3 - 2.0 / k) * L
                bound = min(1.0, k * G / (n * s) + 1.0 / m)
                say("  %d %3d %4d %3d %3d %5d  %10.2f %10.2f %12.2f %11.3f %15.1f %18.3f"
                    % (k, m, n, L, s, B, mean(WF), mean(WS), mean(Wg), closed, G, bound))
    say("")
    say("  the realised 'gap closed' never exceeds the bound kG/(total small work)+1/m.")


def part_proofcheck(N=200000):
    say("=== G5.3  THE TWO INGREDIENTS OF THE BOUND, CHECKED DIRECTLY ===")
    say("(a)  sum_i (W_FCFS[i] - W_P[i]) = (1/k) * sum over inverted pairs (u,v) of")
    say("     (x_u - x_v)  -- exact at k=1, up to 2(k-1)L per job otherwise.")
    say("(b)  for the LAST lower-ranked job to be dispatched, Out = 0, so In <= kG+(3k-2)L:")
    say("     the total higher-ranked work that may pass it is capped by the guarantee.")
    rng = np.random.default_rng(2)
    bad = 0
    tested = 0
    for it in range(N):
        n = int(rng.integers(1, 11))
        a = np.sort(rng.integers(0, 15, n))
        x = rng.integers(0, 7, n)
        jobs = [(int(a[i]), int(x[i])) for i in range(n)]
        ch = S.make_random(rng)
        W, In, Out, order, start = S.run(jobs, 1, ch)
        WF = S.fcfs_wait(jobs, 1)
        pos = {j: p for p, j in enumerate(order)}
        pair = 0
        for u in range(n):
            for v in range(u + 1, n):
                if pos[v] < pos[u]:
                    pair += x[u] - x[v]
        lhs = sum(WF[i] - W[i] for i in range(n))
        tested += 1
        if lhs != pair:
            bad += 1
    say("(a) at k=1, checked on %d instances: mismatches = %d" % (tested, bad))
    say("")


if __name__ == "__main__":
    part_exact()
    part_family()
    part_proofcheck(150000)
    open("out_price.txt", "w").write("\n".join(OUT) + "\n")
