"""Items 1(d)/1(e) continued and item 3(Lemma 1/1'):

  A. is  U_A(t) - U_B(t) = (k-1)L  ever ATTAINED?  (Lemma 1'' claims "never",
     but its proof only shows the cascade does not attain it.)
  B. is  |D_i| = 2(k-1)L  ever attained?
  C. Lemma 1' as literally stated ("if no such u exists, U_A(t) <= U_B(t)")
     -- counterexample from the note's own cascade.

Exhaustive over EVERY work-conserving schedule of small instances, both
policies free (Lemma 1 is a statement about two arbitrary policies).
"""
import itertools
from fractions import Fraction

from ref3_sim import simulate, fcfs, priority, audit, bookkeeping, n_present, unfinished
from ref3_thm3 import upper_family, upper_policy

OUT = []


def p(*args):
    s = " ".join(str(x) for x in args)
    OUT.append(s)
    print(s)


# --------------------------------------------------- enumerate all schedules
def all_schedules(a, x, k):
    """Every work-conserving schedule: (s, order, fin) triples."""
    n = len(a)
    s = [None] * n
    fin = [None] * n
    order = [None] * n
    out = []

    def rec(t, busy, waiting, nxt, cnt):
        free = None
        for m in range(k):
            if busy[m] is None:
                free = m
                break
        if waiting and free is not None:
            for jid in list(waiting):
                nb = list(busy)
                s[jid] = t
                fin[jid] = t + x[jid]
                order[jid] = cnt
                if x[jid] != 0:
                    nb[free] = t + x[jid]
                rec(t, tuple(nb), [w for w in waiting if w != jid], nxt, cnt + 1)
                s[jid] = None
                fin[jid] = None
                order[jid] = None
            return
        cands = []
        if nxt < n:
            cands.append(a[nxt])
        for m in range(k):
            if busy[m] is not None:
                cands.append(busy[m])
        if not cands:
            out.append((list(s), list(order), list(fin)))
            return
        t2 = min(cands)
        nb = [None if (busy[m] is not None and busy[m] <= t2) else busy[m]
              for m in range(k)]
        nw = list(waiting)
        j = nxt
        while j < n and a[j] <= t2:
            nw.append(j)
            j += 1
        nw.sort()
        rec(t2, tuple(nb), nw, j, cnt)

    t0 = a[0]
    w0 = [j for j in range(n) if a[j] <= t0]
    rec(t0, tuple([None] * k), w0, len(w0), 0)
    return out


def U_at(a, x, s, fin, t):
    tot = 0
    for j in range(len(a)):
        if a[j] > t:
            continue
        if s[j] >= t:
            tot += x[j]
        else:
            r = fin[j] - t
            if r > 0:
                tot += r
    return tot


def main():
    p("=" * 78)
    p("ITEMS 1(d)/3 -- is the bound ATTAINED?  (the note asserts 'never')")
    p("=" * 78)
    p("")
    p("--- A. max over every PAIR of work-conserving schedules of")
    p("       U_A(t) - U_B(t) , against Lemma 1's ceiling (k-1)L ---")
    p("")
    best = {}
    npairs = 0
    for k in (2, 3):
        for n in range(2, 6):
            for arr in itertools.combinations_with_replacement(range(3), n):
                for sz in itertools.product(range(1, 4), repeat=n):
                    a = list(arr)
                    x = list(sz)
                    L = max(x)
                    S = all_schedules(a, x, k)
                    if len(S) > 60:
                        continue
                    bps = sorted(set(a) | {f for (_, _, fn) in S for f in fn})
                    Us = []
                    for (s_, o_, f_) in S:
                        Us.append([U_at(a, x, s_, f_, t) for t in bps])
                    for ia in range(len(S)):
                        for ib in range(len(S)):
                            npairs += 1
                            d = max(Us[ia][q] - Us[ib][q] for q in range(len(bps)))
                            key = (k, L)
                            r = Fraction(d, L)
                            if key not in best or r > best[key][0]:
                                best[key] = (r, a, x)
    p("   k  L   max (U_A-U_B)/L found   ceiling (k-1)   attained?")
    for (k, L) in sorted(best):
        r, a, x = best[(k, L)]
        p("   %d %2d   %-22s %d            %s" %
          (k, L, "%s = %.4f" % (r, float(r)), k - 1,
           "YES **" if r == k - 1 else "no (strict)"))
    p("   (%d ordered schedule pairs examined)" % npairs)
    p("")
    p("--- B. max |D_i| over every work-conserving schedule vs FCFS ---")
    p("")
    bestD = {}
    nsched = 0
    for k in (2, 3, 4):
        for n in range(2, 7):
            for arr in itertools.combinations_with_replacement(range(3), n):
                for sz in itertools.product(range(1, 4), repeat=n):
                    a = list(arr)
                    x = list(sz)
                    L = max(x)
                    resF = simulate(a, x, k, fcfs)
                    oF = resF['order']
                    WF = [resF['s'][i] - a[i] for i in range(n)]
                    S = all_schedules(a, x, k)
                    if len(S) > 200:
                        continue
                    for (s_, o_, f_) in S:
                        nsched += 1
                        for i in range(n):
                            In = sum(x[j] for j in range(i + 1, n) if o_[j] < o_[i])
                            Out = sum(x[j] for j in range(i) if o_[j] > o_[i])
                            D = k * ((s_[i] - a[i]) - WF[i]) - (In - Out)
                            key = (k, L)
                            r = Fraction(D, L)
                            cur = bestD.get(key)
                            if cur is None or abs(r) > abs(cur[0]):
                                bestD[key] = (r, a, x, i)
    p("   k  L   max |D|/L found   ceiling 2(k-1)   attained?")
    for (k, L) in sorted(bestD):
        r, a, x, i = bestD[(k, L)]
        p("   %d %2d   %-18s %d              %s" %
          (k, L, "%s = %.4f" % (r, float(r)), 2 * (k - 1),
           "YES **" if abs(r) == 2 * (k - 1) else "no (strict)"))
    p("   (%d schedules examined)" % nsched)
    p("")
    p("--- C. Lemma 1' as literally stated, on the note's OWN cascade ---")
    p("")
    p("  Lemma 1': 'Let u <= t be any time with N_A(u) <= k-1 and N_A >= k")
    p("  throughout (u,t].  Then U_A(t) - U_B(t) <= (k-1) max{x_j : j at u}.")
    p("  If no such u exists, U_A(t) <= U_B(t).'")
    p("")
    for (k, L, m) in ((2, 64, 3), (3, 81, 2), (4, 64, 2)):
        a, x, victim, Tm = upper_family(k, L, m)
        resP = simulate(a, x, k, upper_policy(k, L, m, victim, Tm))
        resF = simulate(a, x, k, fcfs)
        t = Tm                      # read just after the arrivals at T_m
        # candidate reference times u <= t
        bps = sorted(set(a) | set(f for f in resP['fin']))
        bps = [b for b in bps if b <= t]
        # N_P is piecewise constant and changes only at breakpoints, so
        # "N_P >= k throughout (u,t]" is tested at every breakpoint in (u,t]
        # AND at one interior point of every gap between consecutive ones.
        valid = []
        for u in bps:
            if n_present(resP, u) > k - 1:
                continue
            later = [b for b in bps if u < b <= t]
            probes = list(later)
            prev = u
            for b in later:
                probes.append(Fraction(prev + b, 2))
                prev = b
            if all(n_present(resP, b) >= k for b in probes):
                valid.append(u)
        gap = unfinished(resP, t) - unfinished(resF, t)
        nb = n_present(resP, Tm - Fraction(1, 2))
        p("  k=%d L=%d m=%d  at t=T_m=%d :  U_P-U_FCFS = %s   (> 0)" %
          (k, L, m, t, gap))
        p("      N_P just before T_m = %d  (<= k-1 = %d)" % (nb, k - 1))
        p("      reference times u satisfying Lemma 1''s hypothesis: %s" %
          (valid if valid else "NONE"))
        if not valid:
            p("      => Lemma 1' then asserts U_P(t) <= U_FCFS(t); measured "
              "%s > 0.   *** CLAUSE FALSE ***" % gap)
        p("")
    with open("out_attain.txt", "w") as fh:
        fh.write("\n".join(OUT) + "\n")


if __name__ == "__main__":
    main()
