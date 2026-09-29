"""Numerical attack on the SHARP constants of theory.md (revision pass).

Modes (argv[1]):
  agree    cross-check sharp_kernel.py against sim_core.py (independent paths)
  exh      exhaustive: EVERY work-conserving schedule of small instances,
           both accounting conventions, per (k, L)
  scan     hill-climb the worst |D| and |De| for several L, to separate
           "(k-1)L + one time unit" from "(k-1)L + L/2"
  rand     large uniform random sweep (>= 1e7 instances)
  wrap     hill-climb the wrapper constant (k*excess - B)/L, constant budget
  thmB     Theorem B (capped relative budget): exhaustive + random check

Exact integers everywhere.  Run as
  env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME \
      uv run --with numpy --with numba python run_sharp.py <mode>
"""
import sys
sys.dont_write_bytecode = True

import time
from fractions import Fraction

import numpy as np
from numba import njit

import sharp_kernel as K

NEG = K.NEG


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def buffers(n, k):
    return (np.empty(n, np.int64), np.empty(n, np.int64), np.empty(k, np.int64),
            np.empty(n, np.int64), np.empty(n, np.int64), np.empty(n, np.int64),
            np.empty(n, np.int64), np.empty(8, np.int64))


def one(a, x, k, tape):
    """Return (maxD, minD, maxDe, minDe, argmaxD, argminD, argmaxDe, argminDe)."""
    n = len(a)
    st, od, fr, wt, stF, odF, pos, res = buffers(n, k)
    if K.sched(a, x, k, tape, 1, st, od, fr, wt) < 0:
        return None
    if K.sched(a, x, k, np.zeros(n, np.int64), 0, stF, odF, fr, wt) < 0:
        return None
    K.analyse(a, x, k, st, od, stF, pos, res)
    return res.copy()


def fmt(v, L):
    return str(Fraction(int(v), int(L)))


# --------------------------------------------------------------------------- #
# mode agree
# --------------------------------------------------------------------------- #
def mode_agree():
    import sim_core
    rng = np.random.default_rng(20260919)
    bad_sched = bad_io = bad_id = 0
    tot = 0
    for it in range(20000):
        n = int(rng.integers(1, 9))
        k = int(rng.integers(1, 5))
        L = int(rng.integers(1, 6))
        a = np.sort(rng.integers(0, 6, n)).astype(np.int64)
        x = rng.integers(0, L + 1, n).astype(np.int64)
        tape = rng.integers(0, 1 << 20, n).astype(np.int64)
        st, od, fr, wt, stF, odF, pos, res = buffers(n, k)
        K.sched(a, x, k, tape, 1, st, od, fr, wt)
        K.sched(a, x, k, np.zeros(n, np.int64), 0, stF, odF, fr, wt)

        jobs = [(int(a[i]), int(x[i])) for i in range(n)]
        cnt = {'d': 0}

        def chooser(t, waiting, state):
            c = int(tape[cnt['d']]) % len(waiting)
            cnt['d'] += 1
            return c

        s2, o2, d2 = sim_core.simulate(jobs, k, chooser)
        sF2 = sim_core.fcfs_wait(jobs, k)
        if list(st) != [int(v) for v in s2] or list(od) != list(o2):
            bad_sched += 1
        if [int(stF[i]) - int(a[i]) for i in range(n)] != [int(v) for v in sF2]:
            bad_sched += 1
        In2, Out2 = sim_core.in_out(jobs, o2)
        K.analyse(a, x, k, st, od, stF, pos, res)
        # recompute D by hand from sim_core's In/Out and compare to the kernel
        Ds = [k * (int(st[i]) - int(stF[i])) - (In2[i] - Out2[i]) for i in range(n)]
        if max(Ds) != res[0] or min(Ds) != res[1]:
            bad_io += 1
        # busy-period identity: k*W = work executed in [a_i, s_i)
        for i in range(n):
            w = int(st[i]) - int(a[i])
            ex = 0
            for j in range(n):
                if j == i:
                    continue
                lo = max(int(st[j]), int(a[i]))
                hi = min(int(st[j]) + int(x[j]), int(st[i]))
                if hi > lo:
                    ex += hi - lo
            if ex != k * w:
                bad_id += 1
            tot += 1
    print("agree: 20,000 instances, %d job-checks" % tot)
    print("  kernel vs sim_core, schedules+FCFS   : %d mismatches" % bad_sched)
    print("  kernel D vs sim_core In/Out          : %d mismatches" % bad_io)
    print("  busy-period identity k*W = executed  : %d failures" % bad_id)


# --------------------------------------------------------------------------- #
# mode exh
# --------------------------------------------------------------------------- #
def mode_exh():
    import sim_core
    rng = np.random.default_rng(777)
    print("exhaustive: every work-conserving schedule of random small instances")
    print("  columns: max D, min D, max De, min De   (units of L)")
    for k in (1, 2, 3, 4):
        for L in (2, 3, 4, 6):
            best = [0, 0, 0, 0]
            wit = [None, None, None, None]
            nsched = 0
            ninst = 0
            t0 = time.time()
            while time.time() - t0 < 26.0:
                n = int(rng.integers(2, 7))
                a = np.sort(rng.integers(0, 4, n)).astype(np.int64)
                a = a - a[0]
                x = rng.integers(0, L + 1, n).astype(np.int64)
                jobs = [(int(a[i]), int(x[i])) for i in range(n)]
                scheds = sim_core.all_schedules(jobs, k, cap=40000)
                sF = sim_core.simulate(jobs, k, sim_core.fcfs)[0]
                ninst += 1
                for (order, start) in scheds:
                    nsched += 1
                    pos = [0] * n
                    for p, j in enumerate(order):
                        pos[j] = p
                    for i in range(n):
                        In = sum(int(x[j]) for j in range(i + 1, n) if pos[j] < pos[i])
                        Ine = 0
                        for j in range(i + 1, n):
                            e = min(start[j] + int(x[j]), start[i]) - start[j]
                            if e > 0:
                                Ine += e
                        Out = sum(int(x[j]) for j in range(i) if pos[j] > pos[i])
                        base = k * (start[i] - sF[i]) + Out
                        D = base - In
                        E = base - Ine
                        for idx, v in ((0, D), (1, -D), (2, E), (3, -E)):
                            if v > best[idx]:
                                best[idx] = v
                                wit[idx] = (list(a), list(x), list(order), i)
            print("  k=%d L=%2d  maxD=%-6s minD=%-6s maxDe=%-6s minDe=%-6s "
                  "(k-1)L=%d  [%d instances, %d schedules]"
                  % (k, L, fmt(best[0], L), fmt(-best[1], L), fmt(best[2], L),
                     fmt(-best[3], L), (k - 1) * L, ninst, nsched))
            for idx, nm in ((0, "maxD"), (2, "maxDe")):
                if wit[idx] is not None and best[idx] > (k - 1) * L:
                    aa, xx, oo, ii = wit[idx]
                    print("        %s witness > (k-1)L: a=%s x=%s order=%s i=%d"
                          % (nm, aa, xx, oo, ii))
    sys.stdout.flush()


# --------------------------------------------------------------------------- #
# hill-climb kernels
# --------------------------------------------------------------------------- #
@njit(cache=True)
def _obj(a, x, k, tape, obj, st, od, fr, wt, stF, odF, pos, res):
    if K.sched(a, x, k, tape, 1, st, od, fr, wt) < 0:
        return NEG
    if K.sched(a, x, k, tape, 0, stF, odF, fr, wt) < 0:
        return NEG
    K.analyse(a, x, k, st, od, stF, pos, res)
    if obj == 0:
        return res[0]
    if obj == 1:
        return -res[1]
    if obj == 2:
        return res[2]
    return -res[3]


@njit(cache=True)
def climb(k, L, n, amax, iters, seed, obj, bestA, bestX, bestT):
    np.random.seed(seed)
    st = np.empty(n, np.int64); od = np.empty(n, np.int64)
    fr = np.empty(k, np.int64); wt = np.empty(n, np.int64)
    stF = np.empty(n, np.int64); odF = np.empty(n, np.int64)
    pos = np.empty(n, np.int64); res = np.empty(8, np.int64)
    a = np.empty(n, np.int64); x = np.empty(n, np.int64); tape = np.empty(n, np.int64)
    ca = np.empty(n, np.int64); cx = np.empty(n, np.int64); ct = np.empty(n, np.int64)
    gbest = NEG
    cur = NEG
    it = 0
    while it < iters:
        if it % 4000 == 0 or cur == NEG:
            v = 0
            for j in range(n):
                v += np.random.randint(0, amax + 1)
                a[j] = v
                x[j] = np.random.randint(0, L + 1)
                tape[j] = np.random.randint(0, 1 << 20)
            cur = _obj(a, x, k, tape, obj, st, od, fr, wt, stF, odF, pos, res)
        for j in range(n):
            ca[j] = a[j]; cx[j] = x[j]; ct[j] = tape[j]
        m = np.random.randint(0, 3)
        for _ in range(1 + np.random.randint(0, 2)):
            j = np.random.randint(0, n)
            if m == 0:
                x[j] = np.random.randint(0, L + 1)
            elif m == 1:
                tape[j] = np.random.randint(0, 1 << 20)
            else:
                d = np.random.randint(0, 2 * amax + 1) - amax
                v = a[j] + d
                if v < 0:
                    v = 0
                a[j] = v
                for q in range(1, n):          # keep arrivals nondecreasing
                    if a[q] < a[q - 1]:
                        a[q] = a[q - 1]
                for q in range(n - 2, -1, -1):
                    if a[q] > a[q + 1]:
                        a[q] = a[q + 1]
        v = _obj(a, x, k, tape, obj, st, od, fr, wt, stF, odF, pos, res)
        if v >= cur:
            cur = v
            if v > gbest:
                gbest = v
                for j in range(n):
                    bestA[j] = a[j]; bestX[j] = x[j]; bestT[j] = tape[j]
        else:
            for j in range(n):
                a[j] = ca[j]; x[j] = cx[j]; tape[j] = ct[j]
        it += 1
    return gbest


def mode_scan():
    print("hill-climb of the worst D and De, several L, to fix the SHAPE of the")
    print("constant ((k-1)L + 1 time unit?  (k-1)L + L/2?  something else?)")
    names = {0: "max D", 1: "max -D", 2: "max De", 3: "max -De"}
    for k in (2, 3, 4, 5):
        for L in (2, 4, 8, 16):
            row = []
            for obj in (0, 1, 2, 3):
                best = NEG
                bw = None
                for n in (8, 12, 16):
                    bA = np.zeros(n, np.int64); bX = np.zeros(n, np.int64)
                    bT = np.zeros(n, np.int64)
                    v = climb(k, L, n, 3, 240000, 991 + 17 * k + 3 * L + obj + n,
                              obj, bA, bX, bT)
                    if v > best:
                        best = v
                        bw = (list(bA), list(bX), list(bT))
                row.append((names[obj], int(best), bw))
            print("  k=%d L=%2d  " % (k, L) + "  ".join(
                "%s=%s(%d)" % (nm, fmt(v, L), v) for nm, v, _ in row)
                + "   (k-1)L=%d  2(k-1)L=%d" % ((k - 1) * L, 2 * (k - 1) * L))
            for nm, v, bw in row:
                if v > (k - 1) * L:
                    print("        %s = %s L  witness a=%s x=%s tape=%s"
                          % (nm, fmt(v, L), bw[0], bw[1], bw[2]))
            sys.stdout.flush()


# --------------------------------------------------------------------------- #
# mode rand
# --------------------------------------------------------------------------- #
@njit(cache=True)
def rand_sweep(k, L, n, amax, iters, seed, out):
    np.random.seed(seed)
    st = np.empty(n, np.int64); od = np.empty(n, np.int64)
    fr = np.empty(k, np.int64); wt = np.empty(n, np.int64)
    stF = np.empty(n, np.int64); odF = np.empty(n, np.int64)
    pos = np.empty(n, np.int64); res = np.empty(8, np.int64)
    a = np.empty(n, np.int64); x = np.empty(n, np.int64); tape = np.empty(n, np.int64)
    mxD = NEG; mnD = -NEG; mxE = NEG; mnE = -NEG
    v2 = 2 * (k - 1) * L
    v1 = (k - 1) * L
    bad2 = 0
    bad1 = 0
    bad1e = 0
    checks = 0
    for _ in range(iters):
        v = 0
        for j in range(n):
            v += np.random.randint(0, amax + 1)
            a[j] = v
            x[j] = np.random.randint(0, L + 1)
            tape[j] = np.random.randint(0, 1 << 20)
        if K.sched(a, x, k, tape, 1, st, od, fr, wt) < 0:
            continue
        if K.sched(a, x, k, tape, 0, stF, odF, fr, wt) < 0:
            continue
        K.analyse(a, x, k, st, od, stF, pos, res)
        checks += n
        if res[0] > mxD:
            mxD = res[0]
        if res[1] < mnD:
            mnD = res[1]
        if res[2] > mxE:
            mxE = res[2]
        if res[3] < mnE:
            mnE = res[3]
        if res[0] > v2 or -res[1] > v2:
            bad2 += 1
        if res[0] > v1 or -res[1] > v1:
            bad1 += 1
        if res[2] > v1 or -res[2] > v1:
            bad1e += 1
    out[0] = mxD; out[1] = mnD; out[2] = mxE; out[3] = mnE
    out[4] = bad2; out[5] = bad1; out[6] = bad1e; out[7] = checks


def mode_rand():
    print("uniform random sweep, exact integers")
    tot_i = 0
    tot_c = 0
    agg = {}
    for k in (1, 2, 3, 4, 5, 6):
        for L in (2, 5, 9):
            for n in (6, 10, 14):
                out = np.zeros(8, np.int64)
                it = 200000
                rand_sweep(k, L, n, 3, it, 4242 + k * 101 + L * 7 + n, out)
                tot_i += it
                tot_c += int(out[7])
                key = (k, L)
                p = agg.get(key, [NEG, -NEG, NEG, -NEG, 0, 0, 0])
                p[0] = max(p[0], int(out[0])); p[1] = min(p[1], int(out[1]))
                p[2] = max(p[2], int(out[2])); p[3] = min(p[3], int(out[3]))
                p[4] += int(out[4]); p[5] += int(out[5]); p[6] += int(out[6])
                agg[key] = p
    print("  %d instances, %d job-checks" % (tot_i, tot_c))
    print("  k  L | maxD   minD   maxDe  minDe | viol 2(k-1)L | viol (k-1)L D/De")
    for (k, L), p in sorted(agg.items()):
        print("  %d %2d | %-6s %-6s %-6s %-6s | %d | %d / %d"
              % (k, L, fmt(p[0], L), fmt(p[1], L), fmt(p[2], L), fmt(p[3], L),
                 p[4], p[5], p[6]))


# --------------------------------------------------------------------------- #
# mode wrap: the wrapper constant, constant budget
# --------------------------------------------------------------------------- #
@njit(cache=True)
def _wobj(a, x, k, tape, B, st, od, fr, wt, stF, odF):
    n = a.shape[0]
    if K.sched_guard(a, x, k, tape, B, st, od, fr, wt) < 0:
        return NEG, -1
    if K.sched(a, x, k, tape, 0, stF, odF, fr, wt) < 0:
        return NEG, -1
    m = NEG
    ai = -1
    for i in range(n):
        v = k * (st[i] - stF[i]) - B
        if v > m:
            m = v
            ai = i
    return m, ai


@njit(cache=True)
def wclimb(k, L, n, amax, Bmax, iters, seed, bestA, bestX, bestT, bestB):
    np.random.seed(seed)
    st = np.empty(n, np.int64); od = np.empty(n, np.int64)
    fr = np.empty(k, np.int64); wt = np.empty(n, np.int64)
    stF = np.empty(n, np.int64); odF = np.empty(n, np.int64)
    a = np.empty(n, np.int64); x = np.empty(n, np.int64); tape = np.empty(n, np.int64)
    ca = np.empty(n, np.int64); cx = np.empty(n, np.int64); ct = np.empty(n, np.int64)
    B = 0
    cB = 0
    gbest = NEG
    cur = NEG
    for it in range(iters):
        if it % 4000 == 0 or cur == NEG:
            v = 0
            for j in range(n):
                v += np.random.randint(0, amax + 1)
                a[j] = v
                x[j] = np.random.randint(0, L + 1)
                tape[j] = np.random.randint(0, 1 << 20)
            B = np.random.randint(0, Bmax + 1)
            cur, _ = _wobj(a, x, k, tape, B, st, od, fr, wt, stF, odF)
        for j in range(n):
            ca[j] = a[j]; cx[j] = x[j]; ct[j] = tape[j]
        cB = B
        m = np.random.randint(0, 4)
        for _ in range(1 + np.random.randint(0, 2)):
            j = np.random.randint(0, n)
            if m == 0:
                x[j] = np.random.randint(0, L + 1)
            elif m == 1:
                tape[j] = np.random.randint(0, 1 << 20)
            elif m == 2:
                d = np.random.randint(0, 2 * amax + 1) - amax
                v = a[j] + d
                if v < 0:
                    v = 0
                a[j] = v
                for q in range(1, n):
                    if a[q] < a[q - 1]:
                        a[q] = a[q - 1]
                for q in range(n - 2, -1, -1):
                    if a[q] > a[q + 1]:
                        a[q] = a[q + 1]
            else:
                B = np.random.randint(0, Bmax + 1)
        v, _ = _wobj(a, x, k, tape, B, st, od, fr, wt, stF, odF)
        if v >= cur:
            cur = v
            if v > gbest:
                gbest = v
                bestB[0] = B
                for j in range(n):
                    bestA[j] = a[j]; bestX[j] = x[j]; bestT[j] = tape[j]
        else:
            B = cB
            for j in range(n):
                a[j] = ca[j]; x[j] = cx[j]; tape[j] = ct[j]
    return gbest


def mode_wrap():
    print("wrapper, constant budget: hill-climb of (k*excess - B)/L")
    print("  proved bound (3k-2);  the additive on the WAIT is that over k")
    for k in (1, 2, 3, 4, 5, 6):
        best = Fraction(-10 ** 9)
        bw = None
        for L in (4, 9, 16):
            for n in (8, 12, 15):
                bA = np.zeros(n, np.int64); bX = np.zeros(n, np.int64)
                bT = np.zeros(n, np.int64); bB = np.zeros(1, np.int64)
                v = wclimb(k, L, n, 3, 4 * k * L, 200000,
                           31337 + k * 13 + L * 5 + n, bA, bX, bT, bB)
                f = Fraction(int(v), L)
                if f > best:
                    best = f
                    bw = (list(bA), list(bX), list(bT), int(bB[0]), L, n)
        print("  k=%d  best (k*excess-B)/L = %s = %.4f   proved %d   "
              "=> additive on the WAIT = %s L (proved %s L)"
              % (k, best, float(best), 3 * k - 2, best / k,
                 Fraction(3 * k - 2, k)))
        print("       witness L=%d n=%d B=%d a=%s x=%s tape=%s"
              % (bw[4], bw[5], bw[3], bw[0], bw[1], bw[2]))
        sys.stdout.flush()


# --------------------------------------------------------------------------- #
# mode deep: does max|D| / L keep climbing towards 2(k-1) as L grows?
# --------------------------------------------------------------------------- #
def mode_deep():
    print("deep hill-climb: is the proved constant 2(k-1)L a SUPREMUM?")
    print("  if max|D|/L rises towards 2(k-1) as L grows, the referee's")
    print("  conjectured (k-1)L is an artefact of searching only L=2.")
    print("  k   L   maxD/L    max-D/L   maxDe/L   max-De/L  | (k-1) | 2(k-1)")
    for k in (2, 3, 4):
        for L in (8, 16, 32, 64, 128):
            vals = []
            for obj in (0, 1, 2, 3):
                best = Fraction(-10 ** 9)
                for n in (12, 16, 20):
                    bA = np.zeros(n, np.int64); bX = np.zeros(n, np.int64)
                    bT = np.zeros(n, np.int64)
                    v = climb(k, L, n, 4, 400000,
                              5501 + 31 * k + 7 * L + 3 * obj + n, obj, bA, bX, bT)
                    f = Fraction(int(v), L)
                    if f > best:
                        best = f
                        if obj == 0:
                            wit = (list(bA), list(bX), list(bT), n)
                vals.append(best)
            print("  %d %4d  %-9s %-9s %-9s %-9s | %d | %d"
                  % (k, L, "%.4f" % float(vals[0]), "%.4f" % float(vals[1]),
                     "%.4f" % float(vals[2]), "%.4f" % float(vals[3]),
                     k - 1, 2 * (k - 1)))
            sys.stdout.flush()


# --------------------------------------------------------------------------- #
# mode parts: which term of D = (R^P-R^F) - rho^P + rho^F is the bottleneck?
# --------------------------------------------------------------------------- #
@njit(cache=True)
def _robj(a, x, k, tape, st, od, fr, wt, stF, odF):
    if K.sched(a, x, k, tape, 1, st, od, fr, wt) < 0:
        return NEG
    if K.sched(a, x, k, tape, 0, stF, odF, fr, wt) < 0:
        return NEG
    return K.max_rgap(a, x, k, st, stF)


@njit(cache=True)
def rclimb(k, L, n, amax, iters, seed, bestA, bestX, bestT):
    np.random.seed(seed)
    st = np.empty(n, np.int64); od = np.empty(n, np.int64)
    fr = np.empty(k, np.int64); wt = np.empty(n, np.int64)
    stF = np.empty(n, np.int64); odF = np.empty(n, np.int64)
    a = np.empty(n, np.int64); x = np.empty(n, np.int64); tape = np.empty(n, np.int64)
    ca = np.empty(n, np.int64); cx = np.empty(n, np.int64); ct = np.empty(n, np.int64)
    gbest = NEG
    cur = NEG
    for it in range(iters):
        if it % 4000 == 0 or cur == NEG:
            v = 0
            for j in range(n):
                v += np.random.randint(0, amax + 1)
                a[j] = v
                x[j] = np.random.randint(0, L + 1)
                tape[j] = np.random.randint(0, 1 << 20)
            cur = _robj(a, x, k, tape, st, od, fr, wt, stF, odF)
        for j in range(n):
            ca[j] = a[j]; cx[j] = x[j]; ct[j] = tape[j]
        m = np.random.randint(0, 3)
        for _ in range(1 + np.random.randint(0, 2)):
            j = np.random.randint(0, n)
            if m == 0:
                x[j] = np.random.randint(0, L + 1)
            elif m == 1:
                tape[j] = np.random.randint(0, 1 << 20)
            else:
                d = np.random.randint(0, 2 * amax + 1) - amax
                v = a[j] + d
                if v < 0:
                    v = 0
                a[j] = v
                for q in range(1, n):
                    if a[q] < a[q - 1]:
                        a[q] = a[q - 1]
                for q in range(n - 2, -1, -1):
                    if a[q] > a[q + 1]:
                        a[q] = a[q + 1]
        v = _robj(a, x, k, tape, st, od, fr, wt, stF, odF)
        if v >= cur:
            cur = v
            if v > gbest:
                gbest = v
                for j in range(n):
                    bestA[j] = a[j]; bestX[j] = x[j]; bestT[j] = tape[j]
        else:
            for j in range(n):
                a[j] = ca[j]; x[j] = cx[j]; tape[j] = ct[j]
    return gbest


def mode_parts():
    print("A. how large can the Lemma 1 slack R^P_i - R^F_i get?  (bound (k-1)L)")
    for k in (2, 3, 4, 5):
        row = []
        for L in (8, 16, 32, 64):
            best = Fraction(-10 ** 9)
            for n in (10, 14, 18):
                bA = np.zeros(n, np.int64); bX = np.zeros(n, np.int64)
                bT = np.zeros(n, np.int64)
                v = rclimb(k, L, n, 4, 300000, 8081 + k * 19 + L + n, bA, bX, bT)
                f = Fraction(int(v), L)
                if f > best:
                    best = f
            row.append((L, best))
        print("  k=%d  (k-1)=%d  " % (k, k - 1)
              + "  ".join("L=%d:%.4f" % (L, float(b)) for L, b in row))
        sys.stdout.flush()

    print()
    print("B. decomposition of the worst D witnesses  D = (R^P-R^F) - rho^P + rho^F")
    for k in (2, 3, 4):
        for L in (8, 16):
            best = Fraction(-10 ** 9)
            wit = None
            for obj in (0, 1):
                for n in (12, 16, 20):
                    bA = np.zeros(n, np.int64); bX = np.zeros(n, np.int64)
                    bT = np.zeros(n, np.int64)
                    v = climb(k, L, n, 4, 400000,
                              5501 + 31 * k + 7 * L + 3 * obj + n, obj, bA, bX, bT)
                    f = Fraction(int(v), L)
                    if f > best:
                        best = f
                        wit = (bA.copy(), bX.copy(), bT.copy(), n, obj)
            a, x, tape, n, obj = wit
            st, od, fr, wt, stF, odF, pos, res = buffers(n, k)
            K.sched(a, x, k, tape, 1, st, od, fr, wt)
            K.sched(a, x, k, tape, 0, stF, odF, fr, wt)
            K.analyse(a, x, k, st, od, stF, pos, res)
            i = int(res[4] if obj == 0 else res[5])
            RP, rP, RF, rF, In, Out, D = K.decomp(a, x, k, st, od, stF, odF, pos, i)
            print("  k=%d L=%2d  %s = %s L  at job %d: R^P=%s R^F=%s rho^P=%s "
                  "rho^F=%s  (each bound (k-1)L=%s)"
                  % (k, L, "max D" if obj == 0 else "max -D", best, i,
                     fmt(RP, L), fmt(RF, L), fmt(rP, L), fmt(rF, L),
                     fmt((k - 1) * L, L)))
            print("       R^P-R^F=%s L, -rho^P=%s L, +rho^F=%s L, sum=%s L"
                  % (fmt(RP - RF, L), fmt(-rP, L), fmt(rF, L),
                     fmt(RP - RF - rP + rF, L)))
            sys.stdout.flush()


MODES = {"agree": mode_agree, "exh": mode_exh, "scan": mode_scan,
         "rand": mode_rand, "wrap": mode_wrap, "deep": mode_deep,
         "parts": mode_parts}

if __name__ == "__main__":
    m = sys.argv[1] if len(sys.argv) > 1 else "agree"
    MODES[m]()
