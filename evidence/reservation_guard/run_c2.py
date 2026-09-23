"""C2.  k = 1: recovery on the two-size batch family, and pointwise maximality
of rule R among wrappers whose information is exactly the cap profile.

Part 1.  Family of Theorem "price": m jobs of size L ranked first, n jobs of
size sigma, all at t = 0, k = 1.  Base = exact SJF, wrapper = rule R with a
common allowance Z = G (rule R has promise exactly G at k = 1, by C1).  For a
common cap ell on the short class the predicted closed fraction is

    phi_R(ell) = min(1, max(0, floor((G - ell)/sigma) + 1) / n),

which is floor(G/sigma)/n at ell = sigma = C (Prop. A1's size-aware optimum)
and (floor((G-L)/sigma)+1)/n at ell = L (Cor. "k1 frontier", the sharp
size-oblivious value).  Measured against the simulator.

Part 2.  Necessity (the relabelling adversary of verification.md section 5,
extended to caps): at every reachable history of every enumerated rule-R run,
for every candidate j that rule R rejects because overR[h] + ell_j > G at the
head h, relabel every unfinished overtaker to its cap and check by simulation
that excess[h] > G.  The wrapper's observables up to that decision are
unchanged by the relabelling, so a wrapper that permitted j would break the
promise.  Combined with C1 (excess <= Z at k = 1), rule R is pointwise maximal.

    env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME \
        uv run --no-project --with numpy python run_c2.py
"""
import sys
import itertools
from fractions import Fraction

sys.dont_write_bytecode = True
import rguard  # noqa: E402
import sim_core  # noqa: E402


# ------------------------------------------------------------------ part 1 --
def two_size(m, n, L, sig):
    return [(0, L)] * m + [(0, sig)] * n


def total_gap(jobs, k, W):
    WF = sim_core.fcfs_wait(jobs, k)
    return sum(WF) - sum(W)


def closure(m, n, L, sig, G, ell_short):
    jobs = two_size(m, n, L, sig)
    ell = [L] * m + [ell_short] * n
    g = rguard.make_rguard(sim_core.sjf_true, G, ell)
    sP, oP, _ = sim_core.simulate(jobs, 1, g)
    W = [sP[i] for i in range(len(jobs))]
    sS, _, _ = sim_core.simulate(jobs, 1, sim_core.sjf_true)
    WS = [sS[i] for i in range(len(jobs))]
    dg = total_gap(jobs, 1, W)
    ds = total_gap(jobs, 1, WS)
    WF = sim_core.fcfs_wait(jobs, 1)
    exc = max(W[i] - WF[i] for i in range(len(jobs)))
    return Fraction(dg, ds) if ds else None, exc


def part1():
    print("=" * 78)
    print("C2 part 1  two-size batch family, k = 1, base = exact SJF, rule R")
    print("=" * 78)
    print("%-22s %-4s %-10s %-10s %-10s %-10s %s"
          % ("(m,n,L,sigma)", "G", "cap ell", "closed F", "pred phi_R",
             "PropA1 sz", "maxexc"))
    bad = 0
    rows = 0
    for (m, n, L, sig) in [(3, 4, 6, 2), (2, 5, 8, 3), (4, 4, 5, 1),
                           (3, 6, 12, 4), (5, 3, 9, 2), (2, 7, 10, 5)]:
        for G in range(0, 3 * L + 1):
            for ell_short in sorted({sig, (sig + L) // 2, L}):
                F, exc = closure(m, n, L, sig, G, ell_short)
                cnt = 0 if G < ell_short else (G - ell_short) // sig + 1
                phi = min(Fraction(1), Fraction(min(cnt, n), n))
                a1 = min(Fraction(1), Fraction(G // sig, n))
                obl = min(Fraction(1),
                          Fraction(max(0, (G - L) // sig + 1), n))
                rows += 1
                ok = (F == phi)
                ok2 = (ell_short != sig or F == a1)
                ok3 = (ell_short != L or F == obl)
                if not (ok and ok2 and ok3) or exc > G:
                    bad += 1
                    print("MISMATCH (m,n,L,s)=%s G=%d ell=%d F=%s phi=%s "
                          "a1=%s obl=%s exc=%d"
                          % ((m, n, L, sig), G, ell_short, F, phi, a1, obl,
                             exc))
                if G in (0, L, 2 * L) or (G % L == sig and G <= 2 * L):
                    print("%-22s %-4d %-10s %-10s %-10s %-10s %d"
                          % ((m, n, L, sig), G, ell_short, F, phi, a1, exc))
    print()
    print("rows checked %d, mismatches %d" % (rows, bad))
    print("phi_R(ell)=min(1,max(0,floor((G-ell)/sigma)+1)/n);  at ell=sigma it "
          "equals Prop.A1 floor(G/sigma)/n, at ell=L the oblivious frontier.")


# ------------------------------------------------------------------ part 2 --
def scripted(prefix):
    """Dispatch the prescribed ranks in order, then always the head."""
    box = {'p': list(prefix)}

    def f(t, waiting, state):
        while box['p']:
            j = box['p'][0]
            if j in waiting:
                box['p'].pop(0)
                return waiting.index(j)
            return 0
        return 0
    return f


def probe(jobs, ell, G, cap=20000):
    """Walk every reachable rule-R history at k = 1; at each, test every
    rejected candidate by relabelling.  Returns (#tests, #failures, worst)."""
    n = len(jobs)
    a = [j[0] for j in jobs]
    x = [j[1] for j in jobs]
    tests = [0]
    fails = []

    def rec(t, free, nxt, waiting, order, done):
        if tests[0] > cap:
            return
        while nxt < n and a[nxt] <= t:
            waiting = waiting + (nxt,)
            nxt += 1
        if free <= t and waiting:
            h = waiting[0]
            ovh = rguard.overR(h, t, x, ell, done, n)
            allowed = [0]
            for c in range(1, len(waiting)):
                j = waiting[c]
                good = all(rguard.overR(waiting[cq], t, x, ell, done, n)
                           + ell[j] <= G for cq in range(c))
                if good:
                    allowed.append(c)
                elif ovh + ell[j] > G:
                    # rejected because of the HEAD: relabel and verify
                    tests[0] += 1
                    y = list(x)
                    for r in range(n):
                        if done[r] is not None and done[r] > t:
                            y[r] = ell[r]
                    y[j] = ell[j]
                    jobs2 = list(zip(a, y))
                    pre = list(order) + [j]
                    sP, oP, _ = sim_core.simulate(jobs2, 1, scripted(pre))
                    In, Out, W, WF, exc = rguard.metrics(jobs2, 1, oP, sP)
                    if not (exc[h] > G):
                        fails.append((jobs, ell, G, t, h, j, exc[h]))
            for c in allowed:
                j = waiting[c]
                nd = list(done)
                nd[j] = t + x[j]
                rec(t, t + x[j], nxt, waiting[:c] + waiting[c + 1:],
                    order + (j,), tuple(nd))
            return
        if len(order) == n:
            return
        cand = []
        if nxt < n:
            cand.append(a[nxt])
        if free > t:
            cand.append(free)
        if not cand:
            return
        rec(min(cand), free, nxt, waiting, order, done)

    rec(a[0], a[0], 0, (), (), tuple([None] * n))
    return tests[0], fails


def part2():
    print()
    print("=" * 78)
    print("C2 part 2  necessity of rule R's test at k = 1 (relabelling)")
    print("=" * 78)
    L = 3
    tot = 0
    allfails = []
    for n in (3, 4):
        for a in ([(0,) * n] + [tuple(sorted(p)) for p in
                                itertools.product((0, 1), repeat=n)]):
            if list(a) != sorted(a):
                continue
            for x in itertools.product((1, 2, 3), repeat=n):
                jobs = list(zip(a, x))
                for prof in ('C', 'L', 'mix'):
                    if prof == 'C':
                        ell = list(x)
                    elif prof == 'L':
                        ell = [L] * n
                    else:
                        ell = [min(L, c + 1) for c in x]
                    for G in range(0, 8):
                        t, f = probe(jobs, ell, G)
                        tot += t
                        allfails += f
    print("rejected-candidate relabelling tests: %d" % tot)
    print("cases where the relabelled excess did NOT exceed G: %d"
          % len(allfails))
    for f in allfails[:5]:
        print("   ", f)
    print("(every rejection is therefore forced: no cap-informed wrapper with "
          "promise G may permit it)")


if __name__ == "__main__":
    part1()
    part2()
