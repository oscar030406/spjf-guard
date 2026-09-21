"""Adversarial verification of the guard kernel and of the per-job theorems.

Three independent implementations are compared on small instances:
  naive_def   -- the rule read straight off its definition, O(n^2) per decision, no
                 data structures: at every decision instant it rebuilds over[] from the
                 completed set and takes the smallest-rank fired job;
  naive_head  -- the existing project rule (check the HEAD only, constant budget);
  guardkern   -- the segment-tree kernel used for the trace runs.
Plus a Lindley recursion for FCFS at k = 1.

What is asserted, on every instance of every family:
  (1) kernel waits == naive_def waits (exactly);
  (2) for a constant budget, naive_def == naive_head (the smallest-rank-fired rule and
      the head check coincide when the budget does not vary across jobs);
  (3) Theorem A/B:  (k - eps) W_guard[i] <= k W_fcfs[i] + C_i + Ncap*theta + (3k-2) L
      for EVERY job i, with L = max service time of the instance;
  (4) B = 0, eps = 0 reproduces FCFS exactly.
Then a hill-climbing search tries to violate (3) / to make it tight, and two explicit
counterexamples show which designs have no per-job bound at all.

usage:  brute.py            (writes brute_results.csv next to this file)
"""
import sys
sys.dont_write_bytecode = True
import os
import time
import numpy as np
import guardkern as G

HERE = os.path.dirname(os.path.abspath(__file__))
T0 = time.time()
US = 1000000.0


def log(*a):
    print(f"[{time.time()-T0:6.1f}s]", *a, flush=True)


# --------------------------------------------------------------------------- #
# reference implementations
# --------------------------------------------------------------------------- #
def naive_def(arr, svc, pred, k, C0=0.0, gam=0.0, eps=0.0, theta=0.0, Ncap=0,
              Bmax=0.0, mode="guard"):
    """The definition, with no data structures.  Integer microseconds for the budget
    test, float seconds for the clock, exactly as the kernel."""
    n = len(arr)
    en, ed = G.ratio(eps)
    C0u = int(round(C0 * US))
    gamu = int(round(gam * US))
    thu = int(round(theta * US))
    bmu = int(round(Bmax * US))
    su = [int(round(x * US)) for x in svc]
    au = [int(round(x * US)) for x in arr]
    use_cnt = thu > 0 and Ncap > 0
    fin = [None] * n
    waiting = []
    running = []                      # (finish, job)
    wait = np.zeros(n)
    cbud = np.zeros(n, np.int64)
    started = np.zeros(n, bool)
    i = 0
    t = -1e300
    ns = 0
    forced_n = 0
    while ns < n:
        running = [(f, j) for (f, j) in running if f > t]
        while i < n and arr[i] <= t:
            cbud[i] = C0u + gamu * len(waiting)
            waiting.append(i)
            i += 1
        if len(running) < k and waiting:
            tu = int(round(t * US))
            done = [c for c in range(n) if fin[c] is not None and fin[c] <= t]
            fired = []
            for q in waiting:
                ow = 0
                oc = 0
                for c in done:
                    if c > q:
                        if use_cnt and su[c] <= thu:
                            oc += 1
                        else:
                            ow += su[c]
                if C0u >= 0 and ed * ow >= ed * int(cbud[q]) + en * (tu - au[q]):
                    fired.append(q)
                elif bmu > 0 and ow >= bmu:
                    fired.append(q)
                elif use_cnt and oc >= Ncap:
                    fired.append(q)
            if mode == "fcfs":
                j = min(waiting)
                forced_n += 1
            elif mode == "pri":
                j = min(waiting, key=lambda q: (pred[q], q))
            elif fired:
                j = min(fired)
                forced_n += 1
            else:
                j = min(waiting, key=lambda q: (pred[q], q))
            waiting.remove(j)
            started[j] = True
            wait[j] = t - arr[j]
            fin[j] = t + svc[j]
            running.append((fin[j], j))
            ns += 1
            continue
        nxt = min([f for f, _ in running], default=1e300)
        if i < n and arr[i] < nxt:
            nxt = arr[i]
        if nxt >= 1e300:
            break
        t = max(t, nxt)
    return wait, cbud, forced_n


def naive_head(arr, svc, pred, k, B):
    """The existing project rule: serve the head iff over[head] >= B."""
    n = len(arr)
    Bu = int(round(B * US))
    su = [int(round(x * US)) for x in svc]
    fin = [None] * n
    waiting = []
    running = []
    wait = np.zeros(n)
    i = 0
    t = -1e300
    ns = 0
    while ns < n:
        running = [(f, j) for (f, j) in running if f > t]
        while i < n and arr[i] <= t:
            waiting.append(i)
            i += 1
        if len(running) < k and waiting:
            h = min(waiting)
            ov = sum(su[c] for c in range(n)
                     if fin[c] is not None and fin[c] <= t and c > h)
            j = h if ov >= Bu else min(waiting, key=lambda q: (pred[q], q))
            waiting.remove(j)
            wait[j] = t - arr[j]
            fin[j] = t + svc[j]
            running.append((fin[j], j))
            ns += 1
            continue
        nxt = min([f for f, _ in running], default=1e300)
        if i < n and arr[i] < nxt:
            nxt = arr[i]
        if nxt >= 1e300:
            break
        t = max(t, nxt)
    return wait


def lindley(arr, svc):
    w = np.zeros(len(arr))
    for i in range(1, len(arr)):
        w[i] = max(0.0, w[i - 1] + svc[i - 1] - (arr[i] - arr[i - 1]))
    return w


# --------------------------------------------------------------------------- #
# instance families
# --------------------------------------------------------------------------- #
def make(rng, family, n):
    """All times on a 0.5 s lattice so ties and simultaneous events are common."""
    if family == "uniform":
        a = np.sort(rng.integers(0, 4 * n, n).astype(float) * 0.5)
        s = rng.integers(0, 9, n).astype(float) * 0.5
    elif family == "burst":
        a = np.sort(np.where(rng.random(n) < .7, 0.0,
                             rng.integers(0, 3, n).astype(float)))
        s = np.where(rng.random(n) < .3, 4.0, rng.integers(0, 3, n).astype(float) * 0.5)
    elif family == "ties":
        a = np.sort(rng.integers(0, 3, n).astype(float))
        s = rng.choice(np.array([0.0, 1.0, 4.0]), n)
    elif family == "heavy":
        a = np.sort(rng.integers(0, 2 * n, n).astype(float) * 0.5)
        s = np.where(rng.random(n) < .5, 4.0, 0.5)
    else:                                            # 'zero' : zero-length jobs
        a = np.sort(rng.integers(0, n, n).astype(float))
        s = np.where(rng.random(n) < .4, 0.0, rng.integers(1, 4, n).astype(float))
    kind = rng.integers(5)
    if kind == 0:
        p = -s                                       # exactly reversed
    elif kind == 1:
        p = rng.permutation(s)
    elif kind == 2:
        p = np.zeros(n)                              # all tied
    elif kind == 3:
        p = s.copy()
        p[np.argsort(-s, kind="stable")[:max(1, n // 5)]] = -1.0   # longest look shortest
    else:
        p = rng.random(n)
    return np.ascontiguousarray(a), np.ascontiguousarray(s), np.ascontiguousarray(p)


PARAMS = [                # (label, C0, gam, eps, theta, Ncap, Bmax)
    ("fixed B=0", 0.0, 0.0, 0.0, 0.0, 0, 0.0),
    ("fixed B=1", 1.0, 0.0, 0.0, 0.0, 0, 0.0),
    ("fixed B=4", 4.0, 0.0, 0.0, 0.0, 0, 0.0),
    ("rel B0=0 eps=.5", 0.0, 0.0, 0.5, 0.0, 0, 0.0),
    ("rel B0=1 eps=1", 1.0, 0.0, 1.0, 0.0, 0, 0.0),
    ("rel B0=0 eps=2", 0.0, 0.0, 2.0, 0.0, 0, 0.0),
    ("qlen B0=0 gam=1", 0.0, 1.0, 0.0, 0.0, 0, 0.0),
    ("qlen B0=1 gam=.5 eps=.5", 1.0, 0.5, 0.5, 0.0, 0, 0.0),
    ("thresh B=1 th=1 N=2", 1.0, 0.0, 0.0, 1.0, 2, 0.0),
    ("thresh B=0 th=.5 N=3 eps=1", 0.0, 0.0, 1.0, 0.5, 3, 0.0),
    ("cap B0=1 eps=1 Bmax=3", 1.0, 0.0, 1.0, 0.0, 0, 3.0),
    ("cap B0=0 eps=2 Bmax=2", 0.0, 0.0, 2.0, 0.0, 0, 2.0),
    ("cap B0=1 eps=.5 Bmax=1", 1.0, 0.0, 0.5, 0.0, 0, 1.0),
    ("cap+cnt B=1 e=1 th=1 N=2 Bm=4", 1.0, 0.0, 1.0, 1.0, 2, 4.0),
    ("skip N=2 (work channel off)", -1.0, 0.0, 0.0, 4.0, 2, 0.0),
    ("skip N=5 (work channel off)", -1.0, 0.0, 0.0, 4.0, 5, 0.0),
]


def check_instance(a, s, p, k, rows, counts, tol=1e-9):
    n = len(a)
    L = float(s.max()) if n else 0.0
    wf_k = G.run(a, s, k, "fcfs", Mslots=max(4, n)).w
    wf_n, _, _ = naive_def(a, s, p, k, mode="fcfs")
    counts["fcfs_cmp"] += 1
    assert np.allclose(wf_k, wf_n, atol=tol), ("fcfs kernel vs naive", a, s, k)
    if k == 1:
        assert np.allclose(wf_k, lindley(a, s), atol=tol), ("fcfs vs lindley", a, s)
    wp_k = G.run(a, s, k, "pri", pred=p, Mslots=max(4, n)).w
    wp_n, _, _ = naive_def(a, s, p, k, mode="pri")
    assert np.allclose(wp_k, wp_n, atol=tol), ("pri kernel vs naive", a, s, p, k)
    counts["pri_cmp"] += 1
    worst = 0.0
    for label, C0, gam, eps, th, N, Bm in PARAMS:
        if eps >= k:                                  # theorem needs eps < k
            continue
        r = G.run(a, s, k, "guard", pred=p, B=C0, eps=eps, gam=gam, theta=th, Ncap=N,
                  Bmax=Bm, Mslots=max(4, n))
        assert r.err == 0
        wn, cb, _ = naive_def(a, s, p, k, C0=C0, gam=gam, eps=eps, theta=th, Ncap=N,
                              Bmax=Bm)
        counts["guard_cmp"] += 1
        assert np.allclose(r.w, wn, atol=tol), ("guard kernel vs naive", label, a, s, p, k)
        if C0 >= 0:
            assert np.array_equal(r.cbud, cb), ("cbud", label, a, s, p, k)
        if eps == 0.0 and gam == 0.0 and th == 0.0 and Bm == 0.0:
            wh = naive_head(a, s, p, k, C0)
            counts["head_cmp"] += 1
            assert np.allclose(r.w, wh, atol=tol), ("head-check equivalence", label, a, s, p, k)
            if C0 == 0.0:
                assert np.allclose(r.w, wf_k, atol=tol), ("B=0 must be FCFS", a, s, p, k)
        cbs = np.zeros(n) if C0 < 0 else r.cbud / US
        ub = G.guaranteed(wf_k, k, cbs, eps=eps, extra=N * th, L=L, Bmax=Bm)
        counts["bound_cmp"] += 1
        slack = float((r.w - ub).max())
        assert slack <= tol, ("BOUND VIOLATED", label, k, slack, a.tolist(), s.tolist(),
                              p.tolist())
        # tightness: how much of the allowed excess is used
        allow = ub - wf_k
        used = r.w - wf_k
        frac = float((used / np.maximum(allow, 1e-12)).max())
        worst = max(worst, frac)
        rows.append((label, k, n, L, float(used.max()), float(allow.max()), frac))
    return worst


def main():
    rng = np.random.default_rng(20260919)
    rows = []
    counts = dict(fcfs_cmp=0, pri_cmp=0, guard_cmp=0, head_cmp=0, bound_cmp=0, inst=0)
    log("warming up the kernel")
    G.run(np.zeros(2), np.ones(2), 1, "guard", pred=np.zeros(2), B=1.0, eps=0.5,
          theta=1.0, Ncap=1, Mslots=4)
    best = 0.0
    for family in ("uniform", "burst", "ties", "heavy", "zero"):
        fbest = 0.0
        for _ in range(240):
            n = int(rng.integers(2, 10))
            k = int(rng.integers(1, 4))
            a, s, p = make(rng, family, n)
            fbest = max(fbest, check_instance(a, s, p, k, rows, counts))
            counts["inst"] += 1
        best = max(best, fbest)
        log(f"family {family:8s}: 240 instances passed, worst used/allowed = {fbest:.3f}")
    log(f"random phase: {counts['inst']} instances, "
        f"{counts['guard_cmp']} guard kernel-vs-naive comparisons, "
        f"{counts['head_cmp']} head-check equivalences, {counts['bound_cmp']} bound checks; "
        f"worst used/allowed {best:.3f}")

    # ------------------------------------------------------------------ search
    log("hill-climbing search for a violation / for tightness (fixed budget)")
    srows = []
    for k in (1, 2, 3, 4):
        for B in (0.0, 1.0, 4.0):
            cur = None
            curv = -1e9
            for restart in range(40):
                n = int(rng.integers(3, 11))
                a, s, p = make(rng, "burst", n)
                for step in range(120):
                    if step and cur is not None:
                        a, s, p = [x.copy() for x in cur]
                        m = int(rng.integers(0, 3))
                        j = int(rng.integers(0, len(a)))
                        if m == 0:
                            a[j] = max(0.0, a[j] + rng.choice([-1.0, -0.5, 0.5, 1.0]))
                            a = np.sort(a)
                        elif m == 1:
                            s[j] = min(4.0, max(0.0, s[j] + rng.choice([-1.0, -0.5, .5, 1.])))
                        else:
                            p[j] = float(rng.integers(-2, 3))
                    r = G.run(a, s, k, "guard", pred=p, B=B, Mslots=max(4, len(a)))
                    wf = G.run(a, s, k, "fcfs", Mslots=max(4, len(a))).w
                    L = float(s.max()) if s.max() > 0 else 1.0
                    allow = B / k + (3 - 2 / k) * L
                    v = float((r.w - wf).max()) / allow
                    assert v <= 1 + 1e-12, ("SEARCH FOUND A VIOLATION", k, B, v,
                                            a.tolist(), s.tolist(), p.tolist())
                    if v > curv:
                        curv = v
                        cur = (a.copy(), s.copy(), p.copy())
            srows.append((k, B, curv))
            log(f"  k={k} B={B:g}: best excess / (B/k + (3-2/k)L) found = {curv:.3f}")

    # --------------------------------------------------- explicit counterexamples
    log("counterexamples for the designs that have NO per-job bound")
    # (d) age-blended priority  pred - alpha*age : a burst of cheap-looking jobs starves i
    for alpha in (0.1, 1.0):
        P = 10.0
        for m in (200, 400, 800):
            # every overtaker arrives INSIDE the aging window (0, P/alpha), so aging
            # never promotes job 0 before all of them have run
            a = np.r_[0.0, np.linspace(0.0, P / alpha - 0.002, m)]
            s = np.r_[1.0, np.full(m, 1.0)]
            pr = np.r_[P, np.zeros(m)]
            wb = G.run(a, s, 1, "pri", pred=pr + alpha * a).w   # argmin(pred - alpha*age)
            wfc = G.run(a, s, 1, "fcfs").w
            log(f"  age-blend alpha={alpha}, {m} overtakers inside the window "
                f"P/alpha={P/alpha:.0f}s: W[0]={wb[0]:.1f}s vs FCFS {wfc[0]:.1f}s, "
                f"excess {wb[0]-wfc[0]:.1f}s -> grows linearly in m, no per-job bound")
    # (c) short overtakers free, no count cap: a stream of jobs of size theta starves i
    m = 500
    th = 1.0
    a = np.r_[0.0, 0.0, np.arange(m) * 0.5]
    s = np.r_[2.0, 2.0, np.full(m, 0.5)]
    pr = np.r_[100.0, 100.0, np.zeros(m)]
    r_free = G.run(a, s, 1, "guard", pred=pr, B=1.0, theta=th, Ncap=10 ** 9)
    r_cap = G.run(a, s, 1, "guard", pred=pr, B=1.0, theta=th, Ncap=4)
    wfc = G.run(a, s, 1, "fcfs").w
    log(f"  free-short (theta={th}, no count cap): W[0]={r_free.w[0]:.1f}s vs FCFS "
        f"{wfc[0]:.1f}s, excess {r_free.w[0]-wfc[0]:.1f}s (grows with the stream); "
        f"with a count cap N=4: W[0]={r_cap.w[0]:.1f}s, excess {r_cap.w[0]-wfc[0]:.1f}s, "
        f"bound B + N*theta + L = {1.0 + 4 * th + s.max():.1f}s")

    # ------------------------------------- cross-check against the project simulator
    log("cross-check: eps=0 guard / pri / fcfs against evidence/codebench_service_v2")
    sys.path.insert(0, r"<repo-root>/evidence/codebench_service_v2")
    import service_precheck_v2 as V2          # read-only import
    nx = 0
    for _ in range(300):
        n = int(rng.integers(2, 12))
        k = int(rng.integers(1, 5))
        a, s, p = make(rng, str(rng.choice(["uniform", "burst", "ties", "heavy"])), n)
        for B in (0.0, 1.0, 4.0):
            wv = V2.simulate(a, s, p, k, "guard", B)
            wm = G.run(a, s, k, "guard", pred=p, B=B, Mslots=max(4, n)).w
            assert np.allclose(wv, wm, atol=1e-9), ("v2 guard mismatch", k, B,
                                                    a.tolist(), s.tolist(), p.tolist())
            nx += 1
        assert np.allclose(V2.simulate(a, s, None, k, "fcfs"),
                           G.run(a, s, k, "fcfs", Mslots=max(4, n)).w, atol=1e-9)
        assert np.allclose(V2.simulate(a, s, p, k, "pri"),
                           G.run(a, s, k, "pri", pred=p, Mslots=max(4, n)).w, atol=1e-9)
        nx += 2
    log(f"  {nx} comparisons against the project simulator, all identical")

    import csv
    with open(os.path.join(HERE, "brute_results.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["design", "k", "n", "L", "max_excess", "max_allowed", "used_over_allowed"])
        for r in rows:
            w.writerow(r)
        w.writerow([])
        w.writerow(["search_k", "search_B", "best_excess_over_allowance"])
        for r in srows:
            w.writerow(r)
    log(f"wrote brute_results.csv ({len(rows)} rows); "
        f"totals: {counts['guard_cmp']} guard comparisons, {counts['bound_cmp']} bound "
        f"checks, {counts['head_cmp']} head-check equivalences, 0 violations")


if __name__ == "__main__":
    main()
