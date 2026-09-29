"""T2: the exact law, its corollaries, and the adaptive-budget rule.

Section [0] calibrates the simulator against results that were established
before this note (the tool is suspect until it reproduces a known answer).
"""
import random
import sim


def hdr(s):
    print('\n' + '=' * 70)
    print(s)
    print('=' * 70)


# ------------------------------------------------------------------- [0] ---
def selftest():
    hdr('[0] simulator calibration against previously established results')
    ok = True

    # (0a) FCFS has excess 0 and In = Out = 0 on every input.
    rng = random.Random(1)
    bad = 0
    for _ in range(400):
        k = rng.randint(1, 4)
        n = rng.randint(1, 8)
        a = sorted(rng.randint(0, 12) for _ in range(n))
        x = [rng.randint(0, 6) for _ in range(n)]
        r = sim.run_full(k, a, x, sim.fcfs)
        if any(v != 0 for v in r['In']) or any(v != 0 for v in r['Out']):
            bad += 1
    print(f'(0a) FCFS has In=Out=0 on 400 random inputs: {bad} failures')
    ok &= bad == 0

    # (0b) paper Prop floor: k+1 jobs of size L at t=0, base prefers the high
    #      ranks, any budget rule positive at the first epoch -> excess = L.
    bad = 0
    for k in (1, 2, 3, 4):
        L = 7
        n = k + 1
        a = [0] * n
        x = [L] * n
        g = sim.make_guard(sim.lifo, sim.const_budget(1))
        rp = sim.run_full(k, a, x, g)
        rf = sim.run_full(k, a, x, sim.fcfs)
        exc = max(rp['W'][i] - rf['W'][i] for i in range(n))
        if exc != L:
            bad += 1
            print(f'    k={k}: excess {exc} != L={L}')
    print(f'(0b) Prop(floor) instance gives excess exactly L: {bad} failures')
    ok &= bad == 0

    # (0c) paper Thm(identity): |Delta_i| <= 2(k-1)L, strict for k >= 2.
    bad = 0
    checks = 0
    for _ in range(300):
        k = rng.randint(1, 4)
        n = rng.randint(2, 9)
        a = sorted(rng.randint(0, 10) for _ in range(n))
        x = [rng.randint(1, 5) for _ in range(n)]
        L = max(x)
        rf = sim.run_full(k, a, x, sim.fcfs)
        for pol in (sim.sjf, sim.lifo, sim.make_random(rng)):
            rp = sim.run_full(k, a, x, pol)
            for i in range(n):
                d = k * (rp['W'][i] - rf['W'][i]) - (rp['In'][i] - rp['Out'][i])
                checks += 1
                if abs(d) > 2 * (k - 1) * L:
                    bad += 1
                if k >= 2 and abs(d) == 2 * (k - 1) * L:
                    bad += 1
    print(f'(0c) |Delta_i| < 2(k-1)L on {checks} job-checks: {bad} failures')
    ok &= bad == 0

    # (0d) Prop 17 (k=1 achievable fraction = min(1, floor(G/s)/n)) by
    #      exhaustive enumeration of every work-conserving schedule.
    bad = 0
    rows = 0
    for (L, s) in ((5, 2), (6, 2), (7, 3), (4, 1)):
        for m in (1, 2, 3):
            for nn in (1, 2, 3):
                a = [0] * (m + nn)
                x = [L] * m + [s] * nn
                scheds = sim.enumerate_schedules(1, a, x)
                rf = sim.derive(1, a, x, *sim.enumerate_schedules(1, a, x)[0]) \
                    if False else sim.run_full(1, a, x, sim.fcfs)
                rj = sim.run_full(1, a, x, sim.sjf)
                den = sum(rf['W']) - sum(rj['W'])
                for G in range(0, 3 * L + 1):
                    best = 0.0
                    for (ss, sq) in scheds:
                        r = sim.derive(1, a, x, ss, sq)
                        if max(r['W'][i] - rf['W'][i]
                               for i in range(m + nn)) <= G:
                            num = sum(rf['W']) - sum(r['W'])
                            best = max(best, num / den if den else 0.0)
                    pred = min(1.0, (G // s) / nn)
                    rows += 1
                    if abs(best - pred) > 1e-9:
                        bad += 1
                        if bad <= 3:
                            print(f'    L={L} s={s} m={m} n={nn} G={G}: '
                                  f'enum {best} vs Prop17 {pred}')
    print(f'(0d) Prop 17 over {rows} (family, G) rows: {bad} disagreements')
    ok &= bad == 0
    print(f'CALIBRATION: {"PASS" if ok else "FAIL"}')
    return ok


# ------------------------------------------------------------------- [A] ---
def law_residual(k, a, x, rp, rf):
    """k(W_P - W_FCFS) - [In-Out + (Gam_P(a_i)-Gam_F(a_i)) - rho_P + rho_F]."""
    out = []
    for i in range(len(a)):
        gp = sim.gamma(k, a, x, rp['s'], a[i])
        gf = sim.gamma(k, a, x, rf['s'], a[i])
        lhs = k * (rp['W'][i] - rf['W'][i])
        rhs = (rp['In'][i] - rp['Out'][i]) + (gp - gf) \
            - rp['rho'][i] + rf['rho'][i]
        out.append((lhs - rhs, gp - gf, rp['R'][i] - rf['R'][i],
                    sim.unfinished(a, x, rp['s'], a[i])
                    - sim.unfinished(a, x, rf['s'], a[i])))
    return out


def section_A():
    hdr('[A] T2 identity on random instances, many policies')
    rng = random.Random(20260921)
    bad_law = bad_gamR = bad_gamU = 0
    checks = 0
    bad_c = [0, 0, 0]
    for it in range(3000):
        k = rng.randint(1, 5)
        n = rng.randint(2, 12)
        a = sorted(rng.choice([0, 0, 0] + list(range(0, 15)))
                   for _ in range(n))
        x = [rng.choice([0] + list(range(1, 9))) for _ in range(n)]
        if max(x) == 0:
            continue
        L = max(x)
        rf = sim.run_full(k, a, x, sim.fcfs)
        pols = [sim.sjf, sim.sjf_advtie, sim.ljf, sim.lifo,
                sim.make_random(rng), sim.make_nonrank(it),
                sim.make_guard(sim.make_nonrank(it + 7),
                               sim.const_budget(rng.randint(0, 3 * L))),
                sim.make_guard(sim.sjf_advtie,
                               sim.const_budget(rng.randint(0, 2 * L)))]
        for pol in pols:
            rp = sim.run_full(k, a, x, pol)
            for i, (res, gd, rd, ud) in enumerate(
                    law_residual(k, a, x, rp, rf)):
                checks += 1
                if res != 0:
                    bad_law += 1
                if gd != rd:
                    bad_gamR += 1
                if gd != ud:
                    bad_gamU += 1
                # corollaries
                if abs(gd) > (k - 1) * L:
                    bad_c[0] += 1
                if not (0 <= rp['rho'][i] <= (k - 1) * L):
                    bad_c[1] += 1
                d = k * (rp['W'][i] - rf['W'][i]) \
                    - (rp['In'][i] - rp['Out'][i])
                if abs(d) > 2 * (k - 1) * L:
                    bad_c[2] += 1
    print(f'job-checks                         : {checks}')
    print(f'law residual != 0                  : {bad_law}')
    print(f'Gam-diff != R-diff                 : {bad_gamR}')
    print(f'Gam-diff != U-diff                 : {bad_gamU}')
    print(f'|Gam-diff| > (k-1)L                : {bad_c[0]}')
    print(f'rho outside [0,(k-1)L]             : {bad_c[1]}')
    print(f'|Delta| > 2(k-1)L                  : {bad_c[2]}')
    return checks


def section_B():
    hdr('[B] T2 identity over EVERY work-conserving schedule, small instances')
    rng = random.Random(7)
    checks = scheds = bad = 0
    for _ in range(250):
        k = rng.randint(1, 3)
        n = rng.randint(2, 5)
        a = sorted(rng.choice([0, 0, 1, 2, 3]) for _ in range(n))
        x = [rng.choice([0, 1, 2, 3, 4]) for _ in range(n)]
        if max(x) == 0:
            continue
        rf = sim.run_full(k, a, x, sim.fcfs)
        for (s, sq) in sim.enumerate_schedules(k, a, x, cap=400):
            rp = sim.derive(k, a, x, s, sq)
            scheds += 1
            for (res, gd, rd, ud) in law_residual(k, a, x, rp, rf):
                checks += 1
                if res != 0 or gd != rd or gd != ud:
                    bad += 1
    print(f'schedules {scheds}, job-checks {checks}, failures {bad}')
    return checks


def section_C():
    hdr('[C] k=1: both corrections identically zero')
    rng = random.Random(11)
    checks = bad = 0
    for it in range(1500):
        n = rng.randint(2, 10)
        a = sorted(rng.randint(0, 12) for _ in range(n))
        x = [rng.choice([0, 1, 2, 3, 5, 8]) for _ in range(n)]
        if max(x) == 0:
            continue
        rf = sim.run_full(1, a, x, sim.fcfs)
        for pol in (sim.sjf, sim.lifo, sim.make_random(rng),
                    sim.make_nonrank(it)):
            rp = sim.run_full(1, a, x, pol)
            for i in range(n):
                gp = sim.gamma(1, a, x, rp['s'], a[i])
                gf = sim.gamma(1, a, x, rf['s'], a[i])
                checks += 1
                if gp != gf or rp['rho'][i] != 0 or rf['rho'][i] != 0:
                    bad += 1
                if rp['W'][i] - rf['W'][i] != rp['In'][i] - rp['Out'][i]:
                    bad += 1
    print(f'job-checks {checks}, failures {bad}')
    return checks


# ------------------------------------------------------------------- [D] ---
def adaptive_budget_fn(k, a, x, G, L, fcfs_s, clamp=True):
    """budget_i = max(0, k(G-L) - (k-1)L - D_i), D_i = Gam_P(a_i)-Gam_F(a_i).

    D_i is read from the wrapper's OWN run (ctx['start']) at a_i, and from a
    precomputed FCFS shadow run; both depend only on the past at a_i.
    """
    cache = {}

    def f(q, t, ctx):
        if q in cache:
            return cache[q]
        gp = sim.gamma(k, a, x, ctx['start'], a[q])
        gf = sim.gamma(k, a, x, fcfs_s, a[q])
        b = k * (G - L) - (k - 1) * L - (gp - gf)
        if clamp:
            b = max(0, b)
        cache[q] = b
        return b
    return f


def section_D():
    hdr('[D] the T2 corollary budget rule: promise search')
    rng = random.Random(4242)
    viol = 0
    rows = 0
    gains = []
    worst = None
    for it in range(4000):
        k = rng.randint(1, 4)
        n = rng.randint(2, 11)
        a = sorted(rng.choice([0, 0, 0, 1, 2, 3, 5, 8, 13]) for _ in range(n))
        x = [rng.randint(1, 7) for _ in range(n)]
        L = max(x)
        G = rng.randint(int((3 - 2 / k) * L), 5 * L)
        rf = sim.run_full(k, a, x, sim.fcfs)
        for base in (sim.lifo, sim.ljf, sim.make_nonrank(it),
                     sim.make_random(rng)):
            bf = adaptive_budget_fn(k, a, x, G, L, rf['s'])  # fresh cache
            rp = sim.run_full(k, a, x, sim.make_guard(base, bf))
            rows += 1
            for i in range(n):
                e = rp['W'][i] - rf['W'][i]
                if e > G:
                    viol += 1
                    if worst is None or e - G > worst[0]:
                        worst = (e - G, k, a, x, G)
        stat = k * G - (3 * k - 2) * L
        bf2 = adaptive_budget_fn(k, a, x, G, L, rf['s'])
        for i in range(n):
            gains.append(bf2(i, 0, {'start': rp['s']}) - stat)
    print(f'runs {rows}, promise violations (excess > G): {viol}')
    if worst:
        print(f'  worst overshoot {worst}')
    print(f'mean budget gain over static kG-(3k-2)L: '
          f'{sum(gains) / len(gains):.3f}')
    return viol


def section_D2():
    hdr('[D2] adaptive budget with clamp, including G below the paper threshold')
    rng = random.Random(8181)
    runs = checks = viol = raw_negative = 0
    first = None
    for it in range(6000):
        k = rng.randint(1, 4)
        n = rng.randint(2, 10)
        a = sorted(rng.choice([0, 0, 0, 1, 2, 4, 7]) for _ in range(n))
        x = [rng.randint(1, 8) for _ in range(n)]
        L = max(x)
        G = rng.randint(0, 4 * L)
        rf = sim.run_full(k, a, x, sim.fcfs)
        for base in (sim.lifo, sim.ljf, sim.make_nonrank(it)):
            raw = adaptive_budget_fn(k, a, x, G, L, rf['s'], clamp=False)
            clamped = adaptive_budget_fn(k, a, x, G, L, rf['s'], clamp=True)
            rp = sim.run_full(k, a, x, sim.make_guard(base, clamped))
            runs += 1
            for i in range(n):
                checks += 1
                ctx = {'start': rp['s']}
                if raw(i, a[i], ctx) < 0:
                    raw_negative += 1
                e = rp['W'][i] - rf['W'][i]
                if e > G:
                    viol += 1
                    if first is None:
                        first = (k, a, x, G, i, e, rp['seq'])
    print(f'runs {runs}, job-checks {checks}, raw-negative budgets {raw_negative}')
    print(f'promise violations after clamping: {viol}')
    print(f'first violation: {first}')
    return viol


def section_same_phase():
    hdr('[F] adversarial same-phase dispatch accounting')
    bad = 0
    rows = 0
    for k in (2, 3, 4):
        a = [0] * (k + 2)
        x = [7] * (k + 2)
        rf = sim.run_full(k, a, x, sim.fcfs)
        rp = sim.run_full(k, a, x, sim.lifo)
        for i, (res, gd, rd, ud) in enumerate(law_residual(k, a, x, rp, rf)):
            rows += 1
            if res or gd != rd or gd != ud:
                bad += 1
    print(f'job-checks {rows}, failures {bad}')
    print('Same-phase overtakers enter In with full size and rho^P with the')
    print('same remaining size, hence cancel exactly in the identity.')


def section_E():
    hdr('[E] is Gamma_FCFS(a_i) computable online under size-obliviousness?')
    print('search: two inputs I, I\' differing only in the size of one job j*,')
    print('with P\'s run identical up to a_i and j* NOT completed under P by')
    print('a_i (so its size is unread), yet D_i = Gam_P(a_i) - Gam_F(a_i)')
    print('different.  Such a pair means D_i is not observable.')
    rng = random.Random(99)
    found = None
    tried = 0
    for it in range(200000):
        if found:
            break
        k = rng.randint(2, 3)
        n = rng.randint(4, 7)
        a = sorted(rng.choice([0, 0, 0, 1, 2, 3, 4]) for _ in range(n))
        a[-1] = a[-2] + rng.randint(1, 6)          # victim arrives last
        x0 = [rng.randint(1, 8) for _ in range(n)]
        base = sim.make_score([rng.randint(0, 50) for _ in range(n)])
        jstar = rng.randrange(n - 1)
        for db in (1, 2, 3):
            tried += 1
            xa = list(x0)
            xb = list(x0)
            xb[jstar] = x0[jstar] + db
            ra = sim.run_full(k, a, xa, base)
            rb = sim.run_full(k, a, xb, base)
            ti = a[-1]
            # P must not have completed j* by t_i under either input
            if ra['s'][jstar] is not None and ra['s'][jstar] + xa[jstar] <= ti:
                continue
            if rb['s'][jstar] is not None and rb['s'][jstar] + xb[jstar] <= ti:
                continue
            # P's visible history up to t_i must coincide
            va = sorted((j, ra['s'][j]) for j in range(n)
                        if ra['s'][j] is not None and ra['s'][j] <= ti)
            vb = sorted((j, rb['s'][j]) for j in range(n)
                        if rb['s'][j] is not None and rb['s'][j] <= ti)
            if va != vb:
                continue
            fa = sim.run_full(k, a, xa, sim.fcfs)
            fb = sim.run_full(k, a, xb, sim.fcfs)
            da = sim.gamma(k, a, xa, ra['s'], ti) \
                - sim.gamma(k, a, xa, fa['s'], ti)
            db_ = sim.gamma(k, a, xb, rb['s'], ti) \
                - sim.gamma(k, a, xb, fb['s'], ti)
            if da != db_:
                found = (k, a, xa, xb, jstar, ti, da, db_,
                         ra['s'], rb['s'], fa['s'], fb['s'])
                break
    if found:
        (k, a, xa, xb, js, ti, da, db_, sa, sb, fa_, fb_) = found
        print(f'  WITNESS after {tried} pairs:')
        print(f'    k={k} a={a}')
        print(f'    I : x={xa}   I\': x={xb}   (differ only at job {js})')
        print(f'    victim arrives at t={ti}')
        print(f'    P starts: I {sa}   I\' {sb}   (identical up to t)')
        print(f'    FCFS starts: I {fa_}   I\' {fb_}')
        print(f'    D_i = {da} on I but {db_} on I\'')
        print('  -> D_i is not a function of what a size-oblivious scheduler '
              'has observed by a_i.')
    else:
        print(f'  no witness in {tried} pairs (inconclusive)')


if __name__ == '__main__':
    selftest()
    c = section_A()
    c += section_B()
    c += section_C()
    print(f'\ntotal T2 identity job-checks: {c}')
    section_D()
    section_D2()
    section_E()
    section_same_phase()
