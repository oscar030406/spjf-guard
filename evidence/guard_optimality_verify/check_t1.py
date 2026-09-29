"""T1(a) sandwich, T1(b) instance optimality, T1(b') maximality, T1(c) Pareto."""
import random
import sim


def hdr(s):
    print('\n' + '=' * 70)
    print(s)
    print('=' * 70)


def family(m, n, L, s):
    a = [0] * (m + n)
    x = [L] * m + [s] * n
    return a, x


def frac(k, a, x, rP, rF, rS):
    den = sum(rF['W']) - sum(rS['W'])
    if den <= 0:
        return None
    return (sum(rF['W']) - sum(rP['W'])) / den


# ------------------------------------------------------------------ T1(a) ---
def section_A():
    hdr('[A] T1(a): exhaustive F*(G) on the two-size family, and the sandwich')
    rows = 0
    up_viol = lo_viol = gt_viol = prom_viol = 0
    on_line = off_line = 0
    worst_lo = None
    for k in (1, 2, 3):
        for (L, s) in ((6, 2), (5, 1), (7, 3), (4, 2)):
            for m in (1, 2, 3):
                for n in (1, 2, 3, 4):
                    if m + n > 6:
                        continue
                    a, x = family(m, n, L, s)
                    rF = sim.run_full(k, a, x, sim.fcfs)
                    rS = sim.run_full(k, a, x, sim.sjf)
                    den = sum(rF['W']) - sum(rS['W'])
                    if den <= 0:
                        continue
                    scheds = sim.enumerate_schedules(k, a, x)
                    for G in range(0, 4 * L + 1):
                        # F*(G): best over EVERY work-conserving schedule
                        best = 0.0
                        for (ss, sq) in scheds:
                            r = sim.derive(k, a, x, ss, sq)
                            if max(r['W'][i] - rF['W'][i]
                                   for i in range(m + n)) <= G:
                                f = (sum(rF['W']) - sum(r['W'])) / den
                                best = max(best, f)
                        ub = (k * G + (3 * k - 2) * L) / (n * s)
                        B = k * G - (3 * k - 2) * L
                        lb = min(1.0, max(0, B) / (n * s))
                        rows += 1
                        if best > ub + 1e-9:
                            up_viol += 1
                        if B < 0:
                            continue
                        rg = sim.run_full(k, a, x,
                                          sim.make_guard(sim.sjf,
                                                         sim.const_budget(B)))
                        fg = (sum(rF['W']) - sum(rg['W'])) / den
                        if max(rg['W'][i] - rF['W'][i]
                               for i in range(m + n)) > G:
                            prom_viol += 1
                        if fg < lb - 1e-9:
                            lo_viol += 1
                            if worst_lo is None or lb - fg > worst_lo[0]:
                                worst_lo = (lb - fg, k, m, n, L, s, G, fg, lb)
                        if fg > best + 1e-9:
                            gt_viol += 1
                        if abs(fg - lb) < 1e-9:
                            on_line += 1
                        else:
                            off_line += 1
    print(f'rows (setting, G)                      : {rows}')
    print(f'F* above the published upper bound     : {up_viol}')
    print(f'guard below the claimed lower end      : {lo_viol}  {worst_lo}')
    print(f'guard above F* (impossible)            : {gt_viol}')
    print(f'guard breaks its own promise           : {prom_viol}')
    print(f'guard EXACTLY on the line C_lo         : {on_line}')
    print(f'guard strictly ABOVE the line C_lo     : {off_line}')
    print('  (the boxed corollary says the realised pairs "lie on the line";')
    print('   any row in the last category refutes that reading.)')


def section_A2():
    hdr('[A2] T1(a): does the guard sit exactly on C_lo at k = 1, 2?')
    bad = 0
    shown = 0
    for k in (1, 2):
        for (L, s) in ((6, 2), (8, 3), (10, 4)):
            for n in (4, 5, 8):
                m = 3
                a, x = family(m, n, L, s)
                rF = sim.run_full(k, a, x, sim.fcfs)
                rS = sim.run_full(k, a, x, sim.sjf)
                den = sum(rF['W']) - sum(rS['W'])
                for G in range(int((3 - 2 / k) * L), 3 * L + 1):
                    B = k * G - (3 * k - 2) * L
                    if B < 0:
                        continue
                    rg = sim.run_full(k, a, x,
                                      sim.make_guard(sim.sjf,
                                                     sim.const_budget(B)))
                    fg = (sum(rF['W']) - sum(rg['W'])) / den
                    lb = min(1.0, B / (n * s))
                    if abs(fg - lb) > 1e-9:
                        bad += 1
                        if shown < 6:
                            shown += 1
                            print(f'  k={k} L={L} s={s} m={m} n={n} G={G}: '
                                  f'guard {fg:.4f} vs C_lo {lb:.4f}')
    print(f'rows where the guard is NOT exactly on C_lo: {bad}')


# ------------------------------------------------------------------ T1(b) ---
def section_B():
    hdr('[B] T1(b): instance optimality of the guard')
    k, m, n, L, s, G = 1, 4, 10, 10, 1, 10
    a, x = family(m, n, L, s)
    rF = sim.run_full(k, a, x, sim.fcfs)
    rS = sim.run_full(k, a, x, sim.sjf)
    den = sum(rF['W']) - sum(rS['W'])
    B = k * G - (3 * k - 2) * L
    rg = sim.run_full(k, a, x, sim.make_guard(sim.sjf, sim.const_budget(
        max(0, B))))
    fg = (sum(rF['W']) - sum(rg['W'])) / den
    # the rival: all shorts, then the longs in rank order
    seq = list(range(m, m + n)) + list(range(m))
    order = {j: p for p, j in enumerate(seq)}
    rr = sim.run_full(k, a, x, sim.make_score([order[j] for j in range(m + n)]))
    fr = (sum(rF['W']) - sum(rr['W'])) / den
    exc = max(rr['W'][i] - rF['W'][i] for i in range(m + n))
    print(f'B_max = k(G-(3-2/k)L) = {B}; guard closes {fg:.3f} of the gap')
    print(f'rival policy: worst excess {exc} (<= G = {G}), closes {fr:.3f}')
    print(f'additive gap in total wait: {sum(rg["W"]) - sum(rr["W"])}')
    print('=> the guard is NOT instance-optimal among G-feasible policies.')
    # the same at k >= 2, and with arrivals not all at 0
    print('\n  sweep, arrivals not all at 0:')
    rng = random.Random(3)
    worst = 0
    for _ in range(3000):
        k = rng.randint(1, 3)
        nn = rng.randint(3, 8)
        a = sorted(rng.choice([0, 0, 0, 1, 2, 4]) for _ in range(nn))
        x = [rng.randint(1, 6) for _ in range(nn)]
        L = max(x)
        G = rng.randint(int((3 - 2 / k) * L), 3 * L)
        B = max(0, k * G - (3 * k - 2) * L)
        rF = sim.run_full(k, a, x, sim.fcfs)
        rg = sim.run_full(k, a, x, sim.make_guard(sim.sjf,
                                                  sim.const_budget(B)))
        best = None
        for (ss, sq) in sim.enumerate_schedules(k, a, x, cap=3000):
            r = sim.derive(k, a, x, ss, sq)
            if max(r['W'][i] - rF['W'][i] for i in range(nn)) <= G:
                tot = sum(r['W'])
                if best is None or tot < best:
                    best = tot
        if best is not None and sum(rg['W']) - best > worst:
            worst = sum(rg['W']) - best
    print(f'  worst additive shortfall of the guard vs the best G-feasible '
          f'schedule: {worst} time units')

    print('\n  unbounded TOTAL-WAIT ratio, still with admissible G >= L:')
    print('  one rank-first job of size L, two unit jobs, k=1, G=L;')
    print('  guard B=G-L=0 is FCFS, rival dispatches the two units first.')
    for L in (10, 100, 1000, 10000):
        a, x = family(1, 2, L, 1)
        rF = sim.run_full(1, a, x, sim.fcfs)
        rG = sim.run_full(1, a, x,
                          sim.make_guard(sim.sjf, sim.const_budget(0)))
        order = [1, 2, 0]
        score = [order.index(j) for j in range(3)]
        rR = sim.run_full(1, a, x, sim.make_score(score))
        worst_e = max(rR['W'][i] - rF['W'][i] for i in range(3))
        ratio = sum(rG['W']) / sum(rR['W'])
        print(f'    L={L:5d}: guard/rival total wait={ratio:9.3f}, '
              f'rival max excess={worst_e} <= G={L}')


# ----------------------------------------------------------------- T1(b') ---
def section_C():
    hdr("[C] T1(b'): the worst excess of guard(B) at k = 1, over ALL bases")
    print('exhaustive over every guard-realisable schedule (= every base)')
    rows = bad_hi = 0
    attained = 0
    misses = []
    rng = random.Random(5)
    for trial in range(1200):
        n = rng.randint(2, 6)
        a = sorted(rng.choice([0, 0, 0, 1, 2, 3]) for _ in range(n))
        x = [rng.randint(1, 5) for _ in range(n)]
        L = max(x)
        for B in range(0, 2 * L + 1):
            rF = sim.run_full(1, a, x, sim.fcfs)
            mx = 0
            for (ss, sq) in sim.enumerate_constrained(
                    1, a, x, sim.guard_allowed(B), cap=4000):
                r = sim.derive(1, a, x, ss, sq)
                mx = max(mx, max(r['W'][i] - rF['W'][i] for i in range(n)))
            rows += 1
            if mx > B + L - 1:
                bad_hi += 1
                misses.append(('EXCEEDS', a, x, B, mx))
    print(f'rows {rows}; guard(B) excess above B+L-1 at k=1: {bad_hi}')
    if misses[:3]:
        print(f'  {misses[:3]}')

    print('\n  interrupted script\'s attempted family (not a sharp witness):')
    for L in (4, 8, 16):
        for B in (1, L // 2, L, 2 * L):
            best = 0
            # Retained to diagnose the interrupted check: LIFO selects the
            # last (long) job first, contrary to the intended construction.
            for g in (1, 2, L // 2 if L >= 2 else 1):
                if g == 0 or B % g:
                    continue
                cnt = B // g
                a = [0] + [0] * cnt
                x = [L] + [g] * cnt
                rF = sim.run_full(1, a, x, sim.fcfs)
                rg = sim.run_full(1, a, x, sim.make_guard(
                    sim.lifo, sim.const_budget(B)))
                best = max(best, max(rg['W'][i] - rF['W'][i]
                                     for i in range(len(a))))
            # a sharper family: units arriving just in time
            a = [0] + list(range(0, B)) + [B]
            x = [L] + [1] * B + [L]
            rF = sim.run_full(1, a, x, sim.fcfs)
            rg = sim.run_full(1, a, x, sim.make_guard(
                sim.lifo, sim.const_budget(B)))
            best = max(best, max(rg['W'][i] - rF['W'][i]
                                 for i in range(len(a))))
            print(f'    L={L:3d} B={B:3d}: best excess found {best:3d}'
                  f'   target B+L-1 = {B + L - 1}')

    print('\n  direct sharp witness (B-1 units, then one size-L overtaker):')
    direct_bad = 0
    for L in (4, 8, 16):
        for B in (1, L // 2, L, 2 * L):
            a = [0] * (B + 1)
            x = [L] + [1] * (B - 1) + [L]
            dispatch = list(range(1, B)) + [B, 0]
            score = [dispatch.index(j) for j in range(B + 1)]
            rF = sim.run_full(1, a, x, sim.fcfs)
            rG = sim.run_full(1, a, x, sim.make_guard(
                sim.make_score(score), sim.const_budget(B)))
            e0 = rG['W'][0] - rF['W'][0]
            direct_bad += (e0 != B + L - 1)
            print(f'    L={L:3d} B={B:3d}: victim excess {e0:3d}, '
                  f'target {B + L - 1:3d}')
    print(f'  direct-witness mismatches: {direct_bad}')

    print('\n  exhaustive attainment search over small instances')
    for L in (2, 3, 4):
        for B in range(1, 2 * L + 1):
            best = 0
            for n in (2, 3, 4, 5):
                for trial in range(300):
                    a = sorted(rng.choice([0, 0, 0, 1, 2]) for _ in range(n))
                    x = [rng.randint(1, L) for _ in range(n)]
                    if max(x) != L:
                        continue
                    rF = sim.run_full(1, a, x, sim.fcfs)
                    for (ss, sq) in sim.enumerate_constrained(
                            1, a, x, sim.guard_allowed(B), cap=2000):
                        r = sim.derive(1, a, x, ss, sq)
                        best = max(best, max(r['W'][i] - rF['W'][i]
                                             for i in range(n)))
            print(f'    L={L} B={B}: max excess found {best}, '
                  f'B+L-1 = {B + L - 1}'
                  f'{"  ATTAINED" if best == B + L - 1 else "  NOT attained"}')


def section_C2():
    hdr("[C2] T1(b') lemma: the relabelling adversary, and its hypothesis")
    print('threshold wrappers theta = G-L+1 and theta = G-L+2 at k = 1')
    for L in (4, 6, 10):
        for G in (L, L + 2, 2 * L):
            for theta in (G - L + 1, G - L + 2):
                # adversary: victim of rank 0 size L; theta-1 unit overtakers
                # released so that over[victim] = theta-1; then one more job
                # of size L that the base takes.
                w = theta - 1
                a = [0] + [0] * w + [0]
                x = [L] + [1] * w + [L]
                rF = sim.run_full(1, a, x, sim.fcfs)
                dispatch = list(range(1, w + 1)) + [w + 1, 0]
                score = [dispatch.index(j) for j in range(w + 2)]
                rg = sim.run_full(1, a, x, sim.make_guard(
                    sim.make_score(score), sim.const_budget(theta)))
                e = max(rg['W'][i] - rF['W'][i] for i in range(len(a)))
                flag = 'OK' if e <= G else f'EXCEEDS G by {e - G}'
                print(f'  L={L:3d} G={G:3d} theta={theta:3d}: '
                      f'worst excess {e:3d}  {flag}')

    print('\n  does the lemma need its "Out_i = 0" hypothesis?')
    print('  search: k=1 guard(B) schedules with a waiting job i that has')
    print('  Out_i > 0 and over[i](t) > G-L at an epoch where a higher-ranked')
    print('  job is dispatched, while EVERY job still keeps excess <= G.')
    rng = random.Random(17)
    found = 0
    for _ in range(4000):
        n = rng.randint(3, 6)
        a = sorted(rng.choice([0, 0, 0, 1, 2]) for _ in range(n))
        x = [rng.randint(1, 4) for _ in range(n)]
        L = max(x)
        rF = sim.run_full(1, a, x, sim.fcfs)
        for (ss, sq) in sim.enumerate_schedules(1, a, x, cap=500):
            r = sim.derive(1, a, x, ss, sq)
            exc = [r['W'][i] - rF['W'][i] for i in range(n)]
            G = max(exc)
            thr = G - L
            # violation of the lemma's conclusion at some dispatch
            for i in range(n):
                if r['Out'][i] == 0:
                    continue
                # over[i] just before i's last overtaker is dispatched
                ovtk = [j for j in range(i + 1, n)
                        if r['pos'][j] < r['pos'][i]]
                if not ovtk:
                    continue
                tlast = max(ss[j] for j in ovtk)
                ov = sum(x[j] for j in ovtk if ss[j] + x[j] <= tlast)
                if ov > thr:
                    found += 1
                    break
            if found:
                break
        if found:
            break
    print(f'  witnesses with Out_i > 0 and over[i] > G-L: {found}')
    print('  (the witness shows the hypothesis is load-bearing for arbitrary i;')
    print('   verification.md repairs the proof by choosing the queue head.)')

    print('\n  real-size edge: the +1 is an integrality effect')
    print('  With the published >= firing test, every B>G-L is unsafe: choose')
    print('  completed work w strictly between G-L and B, then dispatch a')
    print('  still-unseen job of size L.  B=G-L fires at equality although')
    print('  equality is safe.  A pointwise-maximal real-size rule must fire')
    print('  on over>G-L (strict), not over>=B for any constant B.')


# ------------------------------------------------------------------ T1(c) ---
def section_D():
    hdr('[D] T1(c): the size-oblivious frontier at k = 1')
    print('C_bo(G) = min(1, (floor((G-L)/s)+1)/n)')
    bad_f = bad_g = bad_paper = 0
    rows = 0
    show = 0
    for (L, s) in ((6, 2), (6, 3), (8, 2), (5, 1), (9, 4)):
        for m in (1, 2, 3):
            for n in (1, 2, 3, 4):
                if m + n > 6:
                    continue
                a, x = family(m, n, L, s)
                rF = sim.run_full(1, a, x, sim.fcfs)
                rS = sim.run_full(1, a, x, sim.sjf)
                den = sum(rF['W']) - sum(rS['W'])
                if den <= 0:
                    continue
                for G in range(L, 3 * L + 1):
                    rows += 1
                    cbo = min(1.0, ((G - L) // s + 1) / n)
                    # (i) exhaustive max over schedules obeying the lemma's
                    #     necessary condition for a size-oblivious wrapper
                    best = 0.0
                    for (ss, sq) in sim.enumerate_constrained(
                            1, a, x, sim.defer_allowed(G - L), cap=5000):
                        r = sim.derive(1, a, x, ss, sq)
                        if max(r['W'][i] - rF['W'][i]
                               for i in range(m + n)) <= G:
                            best = max(best,
                                       (sum(rF['W']) - sum(r['W'])) / den)
                    if abs(best - cbo) > 1e-9:
                        bad_f += 1
                        if show < 6:
                            show += 1
                            print(f'  frontier mismatch L={L} s={s} m={m} '
                                  f'n={n} G={G}: enum {best:.4f} '
                                  f'vs C_bo {cbo:.4f}')
                    # (ii) guard at the SHARP budget B* = G-L+1
                    rg = sim.run_full(1, a, x, sim.make_guard(
                        sim.sjf, sim.const_budget(G - L + 1)))
                    fg = (sum(rF['W']) - sum(rg['W'])) / den
                    if max(rg['W'][i] - rF['W'][i]
                           for i in range(m + n)) > G or abs(fg - cbo) > 1e-9:
                        bad_g += 1
                    # (iii) guard at the PAPER's budget B_max = G - L
                    rp = sim.run_full(1, a, x, sim.make_guard(
                        sim.sjf, sim.const_budget(max(0, G - L))))
                    fp = (sum(rF['W']) - sum(rp['W'])) / den
                    if abs(fp - cbo) > 1e-9:
                        bad_paper += 1
    print(f'rows {rows}')
    print(f'  exhaustive frontier != C_bo                 : {bad_f}')
    print(f'  guard at B* = G-L+1 not exactly on C_bo     : {bad_g}')
    print(f"  guard at the PAPER's B_max = G-L off C_bo   : {bad_paper}")
    print('  (the last line is the cost of keeping the published B_max.)')


if __name__ == '__main__':
    section_A()
    section_A2()
    section_B()
    section_C()
    section_C2()
    section_D()
