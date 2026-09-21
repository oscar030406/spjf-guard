"""G5: Lemma 15 (mean-wait accounting) and Theorem 16 (closable fraction).

Lemma 15 claims
  sum_i In_i  = sum_{(u,v) in S} x_v ,  sum_i Out_i = sum_{(u,v) in S} x_u
  k=1 : sum_i (W_F[i]-W_P[i]) = sum_S (x_u - x_v)                exactly
  k>1 : "the same holds after dividing by k, with an error of at most
         2(1-1/k)L per job"
The last clause is checked in both readings (error 2(1-1/k)L in total, and
error 2(1-1/k)L*N in total), because "per job" is ambiguous.

Theorem 16 is checked by exhaustive optimisation over EVERY work-conserving
schedule of the two-class batch family with max excess <= G.
"""
import sys, random
sys.dont_write_bytecode = True
from fractions import Fraction
from refsim2 import (simulate, fcfs_chooser, make_choice_chooser,
                     enumerate_schedules, in_out)


def inversions(x, order, n):
    pos = [0] * n
    for p, j in enumerate(order):
        pos[j] = p
    S = [(u, v) for u in range(n) for v in range(u + 1, n) if pos[v] < pos[u]]
    return S


def part_lemma15(log):
    rng = random.Random(515)
    n_sum = 0
    bad_sums = 0
    bad_k1 = 0
    bad_tot = 0
    bad_perjob = 0
    worst_err = Fraction(0)
    for trial in range(150000):
        n = rng.randint(1, 9)
        k = rng.randint(1, 5)
        a = sorted(rng.randint(0, 7) for _ in range(n))
        x = [rng.randint(0, 6) for _ in range(n)]
        if max(x) == 0:
            continue
        L = max(x)
        tp = [rng.randint(0, 9) for _ in range(n)]
        fst, _, fod = simulate(a, x, k, fcfs_chooser)
        st, _, od = simulate(a, x, k, make_choice_chooser(tp))
        In, Out = in_out(x, od, n)
        S = inversions(x, od, n)
        n_sum += 1
        if sum(In) != sum(x[v] for (u, v) in S) or \
           sum(Out) != sum(x[u] for (u, v) in S):
            bad_sums += 1
        saving = sum(fst[i] - st[i] for i in range(n))
        rhs = Fraction(sum(x[u] - x[v] for (u, v) in S), k)
        if k == 1 and saving != rhs:
            bad_k1 += 1
            if bad_k1 <= 3:
                log.write("  L15 k=1 MISMATCH a=%s x=%s od=%s %s vs %s\n"
                          % (a, x, od, saving, rhs))
        err = abs(Fraction(saving) - rhs)
        tol_total = Fraction(2 * (k - 1) * L, k)
        tol_perjob = tol_total * n
        if err > tol_total:
            bad_tot += 1
        if err > tol_perjob:
            bad_perjob += 1
        if L > 0 and k > 1:
            r = err / L
            if r > worst_err:
                worst_err = r
    log.write("Lemma 15: instances=%d\n" % n_sum)
    log.write("  sum In / sum Out vs the inverted-pair sums: %d mismatches\n"
              % bad_sums)
    log.write("  k=1 exact identity                        : %d mismatches\n"
              % bad_k1)
    log.write("  |saving - (1/k)sum_S(x_u-x_v)| > 2(1-1/k)L (total)  : %d\n"
              % bad_tot)
    log.write("  |saving - (1/k)sum_S(x_u-x_v)| > 2(1-1/k)L*N        : %d\n"
              % bad_perjob)
    log.write("  worst observed |error|/L at k>1                     : %s\n"
              % worst_err)
    log.write("  => the k>1 clause is only true in the PER-JOB-SUMMED reading;\n"
              "     it is NOT an identity with an O(L) error, and for a sum over\n"
              "     N jobs the error term 2(1-1/k)L*N is of the same order as\n"
              "     the quantity itself, so at k>1 Lemma 15 carries no content\n"
              "     beyond an O(NL) bound.\n")


def two_class(m, nn, L, s):
    a = [0] * (m + nn)
    x = [L] * m + [s] * nn
    return a, x


def part_theorem16(log):
    log.write("\nTheorem 16: exhaustive optimum over all G-feasible schedules\n")
    log.write("  columns: realised closable fraction | min(1,G/(n s)) | "
              "Theorem 16 bound (kG+(3k-2)L)/(n s) + eps\n")
    for (m, nn, L, s, k) in [(2, 3, 4, 1, 1), (2, 4, 4, 1, 1), (3, 3, 4, 1, 1),
                             (2, 3, 6, 2, 1), (2, 3, 4, 1, 2), (3, 3, 4, 1, 2),
                             (2, 4, 4, 1, 2), (2, 3, 4, 1, 3)]:
        a, x = two_class(m, nn, L, s)
        n = m + nn
        fst, _, fod = simulate(a, x, k, fcfs_chooser)
        WF = [fst[i] - a[i] for i in range(n)]
        scheds = enumerate_schedules(a, x, k)
        # SJF optimum = the best mean wait over all schedules
        best_any = None
        by_G = {}
        for (st, cp, od) in scheds:
            W = [st[i] - a[i] for i in range(n)]
            exc = [W[i] - WF[i] for i in range(n)]
            G = max(exc)
            tot = sum(W)
            if best_any is None or tot < best_any:
                best_any = tot
            if G not in by_G or tot < by_G[G]:
                by_G[G] = tot
        totF = sum(WF)
        gap = totF - best_any
        Gs = sorted(by_G)
        log.write("  m=%d n=%d L=%d s=%d k=%d  (FCFS total wait %d, best total "
                  "wait %d, gap %d, #schedules %d)\n"
                  % (m, nn, L, s, k, totF, best_any, gap, len(scheds)))
        for G in Gs:
            best = min(by_G[g] for g in Gs if g <= G)
            frac = Fraction(totF - best, gap) if gap else Fraction(0)
            pred = min(Fraction(1), Fraction(G, nn * s))
            bd = Fraction(k * G + (3 * k - 2) * L, nn * s)
            eps = Fraction(2 * (k - 1) * L * (m + nn), m * nn * (L - s))
            log.write("    G=%-3d realised %-6s | min(1,G/(ns)) = %-6s | "
                      "Thm16 bound %-8s (+eps %-6s) | bound respected: %s | "
                      "realised == min(1,G/(ns)): %s\n"
                      % (G, str(frac), str(pred), str(bd), str(eps),
                         frac <= bd + eps, frac == pred))


def main():
    with open("out_g5.txt", "w") as log:
        part_lemma15(log)
        part_theorem16(log)
    print(open("out_g5.txt").read())


if __name__ == "__main__":
    main()
