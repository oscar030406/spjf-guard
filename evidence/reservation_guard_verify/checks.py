"""Independent checks of claims C2, C3, C4a and C6 of ../reservation_guard/report.md.

Uses only rguard_indep.py (this directory).  Nothing is imported from
../reservation_guard/ or ../guard_theory/.

Usage:  python checks.py <c2a|c2b|c3|c4|c6>
"""
import sys
from fractions import Fraction
from itertools import product

sys.dont_write_bytecode = True

import rguard_indep as R   # noqa: E402

INF = float("inf")


# --------------------------------------------------------------- choosers --
def sjf_chooser(svc):
    def f(t, queue, fin):
        best = 0
        for c in range(1, len(queue)):
            if svc[queue[c]] < svc[queue[best]]:
                best = c
        return best
    return f


def prio_chooser(prio):
    def f(t, queue, fin):
        best = 0
        for c in range(1, len(queue)):
            if prio[queue[c]] < prio[queue[best]]:
                best = c
        return best
    return f


def prefer_tail(nlong):
    def f(t, queue, fin):
        for c, q in enumerate(queue):
            if q >= nlong:
                return c
        return 0
    return f


def scripted_then_head(prefix):
    box = {"p": list(prefix)}

    def f(t, queue, fin):
        if box["p"]:
            j = box["p"][0]
            if j in queue:
                box["p"].pop(0)
                return queue.index(j)
            raise RuntimeError("forced job %d not available" % j)
        return 0
    return f


# ----------------------------------------------------------------- C2 (a) --
def closure(m, n, L, sig, G, ell_short):
    """Fraction of the FCFS-to-SJF total-wait gap closed by rule R at k=1."""
    jobs = tuple([(0, L)] * m + [(0, sig)] * n)
    ell = [L] * m + [ell_short] * n
    svc = [j[1] for j in jobs]
    ch = R.make_R_chooser(sjf_chooser(svc), svc, ell, G, len(jobs))
    sP, seqP = R.run_with_chooser(jobs, 1, ch)
    sS, _ = R.run_with_chooser(jobs, 1, sjf_chooser(svc))
    WF = R.fcfs_wait(jobs, 1)
    sumF = sum(WF[i] + jobs[i][0] for i in range(len(jobs)))
    dg = sumF - sum(sP)
    ds = sumF - sum(sS)
    exc = max(sP[i] - jobs[i][0] - WF[i] for i in range(len(jobs)))
    # number of shorts dispatched before the first long
    pos = {j: p for p, j in enumerate(seqP)}
    first_long = min(pos[i] for i in range(m))
    r = sum(1 for i in range(m, m + n) if pos[i] < first_long)
    return (Fraction(dg, ds) if ds else None), exc, r


def c2a():
    print("=" * 78)
    print("C2(a) independent  Prop. R4 closure formula, k=1, base = exact SJF")
    print("=" * 78)
    rows = 0
    bad = 0
    badexc = 0
    shown = 0
    for (m, n, L, sig) in [(3, 4, 6, 2), (2, 5, 8, 3), (4, 4, 5, 1),
                           (3, 6, 12, 4), (5, 3, 9, 2), (2, 7, 10, 5),
                           (1, 8, 7, 2), (6, 2, 11, 3)]:
        for G in range(0, 3 * L + 1):
            for ell_short in sorted({sig, (sig + L) // 2, L, sig + 1}):
                if ell_short > L or ell_short < sig:
                    continue
                F, exc, r = closure(m, n, L, sig, G, ell_short)
                cnt = 0 if G < ell_short else (G - ell_short) // sig + 1
                phi = min(Fraction(1), Fraction(min(cnt, n), n))
                rows += 1
                if F != phi or r != min(cnt, n):
                    bad += 1
                    if shown < 20:
                        shown += 1
                        print("  MISMATCH (m,n,L,s)=%s G=%d ell=%d F=%s "
                              "phi=%s shorts_ahead=%d pred=%d"
                              % ((m, n, L, sig), G, ell_short, F, phi, r,
                                 min(cnt, n)))
                if exc > G:
                    badexc += 1
                    print("  PROMISE BROKEN (m,n,L,s)=%s G=%d ell=%d exc=%d"
                          % ((m, n, L, sig), G, ell_short, exc))
                # the two corners quoted in the report
                if ell_short == sig:
                    a1 = min(Fraction(1), Fraction(G // sig, n))
                    if F != a1:
                        bad += 1
                        print("  CORNER ell=C mismatch", (m, n, L, sig), G, F,
                              a1)
                if ell_short == L:
                    obl = min(Fraction(1),
                              Fraction(max(0, (G - L) // sig + 1), n))
                    if F != obl:
                        bad += 1
                        print("  CORNER ell=L mismatch", (m, n, L, sig), G, F,
                              obl)
    print("  rows %d, formula mismatches %d, promise violations %d"
          % (rows, bad, badexc))


# ----------------------------------------------------------------- C2 (b) --
def relabel_probe(jobs, ell, G, k, limit=200000):
    """At every reachable rule-R history, take every candidate the rule
    rejects because overR[head] + ell_j > G, relabel every unfinished job of
    rank above the head (and the candidate) to its cap, force the candidate
    through, and measure the head's excess in that relabelled instance."""
    n = len(jobs)
    arr = [j[0] for j in jobs]
    svc = [j[1] for j in jobs]
    stat = {"tests": 0, "fail": 0, "worst_margin": None, "nodes": 0,
            "examples": []}

    def test(t, queue, fin, seq, h, j, ovh):
        svc2 = list(svc)
        svc2[j] = ell[j]
        for r in range(n):
            if fin[r] is not None and fin[r] > t and r > h:
                svc2[r] = ell[r]
        jobs2 = tuple((arr[i], svc2[i]) for i in range(n))
        start2, seq2 = R.run_with_chooser(
            jobs2, k, scripted_then_head(list(seq) + [j]))
        WF2 = R.fcfs_wait(jobs2, k)
        exc = start2[h] - arr[h] - WF2[h]
        In2, Out2 = R.in_out(jobs2, seq2)
        stat["tests"] += 1
        margin = exc - G
        if stat["worst_margin"] is None or margin < stat["worst_margin"]:
            stat["worst_margin"] = margin
        if exc <= G:
            stat["fail"] += 1
            if len(stat["examples"]) < 6:
                stat["examples"].append(
                    (jobs, tuple(ell), G, k, tuple(seq), h, j, ovh, exc,
                     In2[h], Out2[h]))

    def rec(t, busy, nxt, queue, seq, start, fin):
        if stat["nodes"] >= limit:
            return
        stat["nodes"] += 1
        while nxt < n and arr[nxt] <= t:
            queue = queue + (nxt,)
            nxt += 1
        free = -1
        for idx in range(k):
            if busy[idx] <= t:
                free = idx
                break
        if free >= 0 and queue:
            h = queue[0]
            ovh = R.overR(h, t, svc, ell, fin, n)
            for c in range(1, len(queue)):
                j = queue[c]
                if ovh + ell[j] > G:
                    test(t, queue, fin, seq, h, j, ovh)
            for c in R.allowed_R(t, queue, fin, svc, ell, G, n):
                j = queue[c]
                nb = list(busy)
                nb[free] = t + svc[j]
                ns = list(start)
                ns[j] = t
                nf = list(fin)
                nf[j] = t + svc[j]
                rec(t, tuple(nb), nxt, queue[:c] + queue[c + 1:],
                    seq + (j,), tuple(ns), tuple(nf))
            return
        if len(seq) == n:
            return
        t2 = R._next_time(t, busy, arr, nxt, n)
        if t2 == INF:
            return
        rec(t2, busy, nxt, queue, seq, start, fin)

    rec(arr[0], tuple([-INF] * k), 0, (), (), tuple([None] * n),
        tuple([None] * n))
    return stat


def c2b():
    print("=" * 78)
    print("C2(b) independent  Theorem R3 relabelling necessity")
    print("=" * 78)
    for k in (1, 2, 3):
        tot = {"tests": 0, "fail": 0, "worst": None, "ex": []}
        for L, sizes, n in ((3, (1, 2, 3), 4), (4, (1, 2, 4), 4),
                            (3, (1, 3), 5)):
            for sv, cv in R.size_cap_vectors(n, sizes, L):
                for arr in ([(0,) * n, tuple(range(n)),
                             (0, 0) + tuple(range(1, n - 1))]):
                    jobs = tuple(zip(arr, sv))
                    for G in range(0, 2 * L + 1):
                        st = relabel_probe(jobs, list(cv), G, k)
                        tot["tests"] += st["tests"]
                        tot["fail"] += st["fail"]
                        if st["worst_margin"] is not None:
                            if tot["worst"] is None or \
                                    st["worst_margin"] < tot["worst"]:
                                tot["worst"] = st["worst_margin"]
                        for e in st["examples"]:
                            if len(tot["ex"]) < 4:
                                tot["ex"].append(e)
        print("  k=%d : %d relabelling tests, %d in which the relabelled "
              "excess did NOT exceed G, min(excess-G)=%s"
              % (k, tot["tests"], tot["fail"], tot["worst"]))
        for e in tot["ex"]:
            print("      COUNTEREXAMPLE jobs=%s ell=%s G=%s k=%s prefix=%s "
                  "head=%s cand=%s overR[h]=%s exc=%s In_h=%s Out_h=%s" % e)


# ------------------------------------------------------------------- C3 ----
def c3():
    print("=" * 78)
    print("C3 independent  entry threshold and In = ell*floor(B/ell)")
    print("=" * 78)
    L = 12
    B = 10
    print("  designed family (k long victims of size L, then shorts of size "
          "ell), L=%d B=%d" % (L, B))
    print("  %-5s %-14s %-14s %-16s" % ("ell", "In_R (max)", "In_C (max)",
                                        "pred R = ell*floor(B/ell)"))
    for k in (1, 2, 4):
        print("   k=%d" % k)
        for ell in (1, 2, 3, 4, 6, 12):
            nshort = 6 * k + 8
            jobs = tuple([(0, L)] * k + [(0, ell)] * nshort)
            caps = [L] * k + [ell] * nshort
            n = len(jobs)
            svc = [j[1] for j in jobs]
            base = prefer_tail(k)
            chR = R.make_R_chooser(base, svc, caps, B, n)
            sR, seqR = R.run_with_chooser(jobs, k, chR)
            InR, _ = R.in_out(jobs, seqR)

            def chC(t, queue, fin, _svc=svc, _n=n):
                allowed = R.allowed_C(t, queue, fin, _svc, B, _n)
                c = base(t, queue, fin)
                return c if c in allowed else allowed[0]
            sC, seqC = R.run_with_chooser(jobs, k, chC)
            InC, _ = R.in_out(jobs, seqC)
            print("     %-5d %-14d %-14d %-16d"
                  % (ell, max(InR), max(InC), ell * (B // ell)))
    print()
    print("  entry thresholds (smallest promise G admitting one overtaker of "
          "cap ell = L), in units of L")
    print("  %-4s %-26s %-26s %s" % ("k", "rule R: G >= (2-1/k)L",
                                     "Alg.1: G > (3-2/k)L", "difference"))
    for k in (1, 2, 3, 4, 8, 16):
        tR = Fraction(2 * k - 1, k)
        tC = Fraction(3 * k - 2, k)
        print("  %-4d %-26s %-26s %s" % (k, tR, tC, tC - tR))
    print("  difference is (1 - 1/k)L, which is 0 at k=1 and -> L only as "
          "k -> infinity; it is NOT L for any finite k.")


# ------------------------------------------------------------------- C4 ----
def cascade(k, L, m, s=1):
    jobs = []
    prio = []
    for j in range(m):
        T = j * L
        for _ in range(k - 1):
            jobs.append((T, L))
            prio.append(2 * j + 1)
        for _ in range(L // s):
            jobs.append((T, s))
            prio.append(2 * j)
    return jobs, prio, m * L


def workload(jobs, start, t):
    u = 0
    for i, (a, x) in enumerate(jobs):
        if a <= t:
            if start[i] is None or start[i] >= t:
                u += x
            else:
                u += max(0, start[i] + x - t)
    return u


def c4():
    print("=" * 78)
    print("C4(a) independent  a victim with In=Out=0 and excess -> L")
    print("=" * 78)
    print("  %-4s %-6s %-4s %-7s %-8s %-8s %-8s %-10s %s"
          % ("k", "L", "m", "n", "In_i", "Out_i", "excess", "pred f",
             "excess < L ?"))
    ok = True
    for k in (2, 3, 4):
        L = k ** 3
        for m in (1, 2, 3, 5):
            jobs, prio, T = cascade(k, L, m, 1)
            g = len(jobs)
            jobs = tuple(jobs + [(T, L), (T, L)])
            prio = prio + [10 ** 6, 10 ** 6 + 1]
            victim = g + 1
            sP, seqP = R.run_with_chooser(jobs, k, prio_chooser(prio))
            WF = R.fcfs_wait(jobs, k)
            In, Out = R.in_out(jobs, seqP)
            exc = sP[victim] - jobs[victim][0] - WF[victim]
            f = L * (1 - Fraction(k - 1, k) ** m)
            sF, _ = R.run_with_chooser(jobs, k, R.fcfs_chooser)
            gapF = workload(jobs, sP, T) - workload(jobs, sF, T)
            print("  %-4d %-6d %-4d %-7d %-8d %-8d %-8s %-10s %s"
                  % (k, L, m, len(jobs), In[victim], Out[victim], exc, f,
                     exc < L))
            if In[victim] or Out[victim] or exc != f or exc >= L:
                ok = False
                print("     MISMATCH  gap at T = %s , (k-1)L = %s"
                      % (gapF, (k - 1) * L))
    print("  all rows have In=Out=0, excess = L(1-((k-1)/k)^m) < L : %s" % ok)
    print("  comparison with the residual of Cor. sufficient, (2-2/k)L:")
    for k in (2, 3, 4, 8):
        print("     k=%d : sup of this construction = L ; (2-2/k)L = %sL ; "
              "construction covers the residual only at k=2"
              % (k, Fraction(2 * k - 2, k)))


# ------------------------------------------------------------------- C6 ----
def c6():
    print("=" * 78)
    print("C6 independent  E(B) = worst excess over the family and over every "
          "base policy")
    print("=" * 78)
    L = 3
    n = 5
    sizes = (1, 2, 3)
    arrivals = [(0,) * n, (0, 0, 0, 1, 1)]
    bmax = 12
    tabs = {}
    for k in (1, 2):
        for tag, rule, capmode in (("C (completed work)", "C", None),
                                   ("R, ell = L", "R", "L"),
                                   ("R, ell = C", "R", "C")):
            E = {B: 0 for B in range(bmax + 1)}
            runs = 0
            for arr in arrivals:
                for x in product(sizes, repeat=n):
                    jobs = tuple(zip(arr, x))
                    ell = ([L] * n if capmode == "L" else list(x)) \
                        if rule == "R" else None
                    WF = R.fcfs_wait(jobs, k)
                    for B in range(bmax + 1):
                        for start, seq in R.enumerate_runs(jobs, k, rule, B,
                                                           ell):
                            runs += 1
                            exc = R.excess(jobs, start, WF)
                            mx = max(exc)
                            if mx > E[B]:
                                E[B] = mx
            tabs[(k, tag)] = E
            print()
            print("  k=%d rule %-22s (%d runs)" % (k, tag, runs))
            print("     B    : %s" % "  ".join("%2d" % B
                                               for B in range(bmax + 1)))
            print("     E(B) : %s" % "  ".join("%2d" % E[B]
                                               for B in range(bmax + 1)))
            if k == 1 and rule == "C":
                pred = [max(0, B + L - 1) if B >= 1 else 0
                        for B in range(bmax + 1)]
                print("     B+L-1: %s  (clipped by the family's reach)"
                      % "  ".join("%2d" % p for p in pred))
            if k == 1 and rule == "R":
                print("     B    : %s  (rule R's claimed E(B)=B)"
                      % "  ".join("%2d" % B for B in range(bmax + 1)))
    print()
    print("  largest constant budget with promise G, from this family "
          "(an UPPER bound on the universal B*)")
    for k in (1, 2):
        print("   k=%d" % k)
        hdr = ["G"] + [t for (kk, t) in sorted(tabs) if kk == k] + \
              ["kG-(3k-2)L", "kG-(2k-2)L", "k(G-L)"]
        print("     " + "  ".join("%-20s" % h for h in hdr))
        for G in range(L, 4 * L + 1):
            row = ["%d" % G]
            for (kk, t) in sorted(tabs):
                if kk != k:
                    continue
                E = tabs[(kk, t)]
                ok = [B for B in range(bmax + 1) if E[B] <= G]
                row.append("%s%s" % (max(ok) if ok else "-",
                                     "+" if (ok and max(ok) == bmax) else ""))
            row.append("%d" % (k * G - (3 * k - 2) * L))
            row.append("%d" % (k * G - (2 * k - 2) * L))
            row.append("%d" % (k * (G - L)))
            print("     " + "  ".join("%-20s" % c for c in row))


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "c2a"
    {"c2a": c2a, "c2b": c2b, "c3": c3, "c4": c4, "c6": c6}[which]()
