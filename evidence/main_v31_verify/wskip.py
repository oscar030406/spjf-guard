"""V2: my own dispatch-charged finite-skip simulator, written from the definition in
paper/sections/06_theory.tex (Remark rem:counts, eq:skip).  It does not import
v31_skipkern, guardkern or refsim.

Definition used (rem:counts + Algorithm 'position counter'):
    k identical servers, non-preemptive, work conserving; service times in (0, L].
    Rank order = arrival order (the input arrays are already in it).
    cnt[q] = number of jobs of rank > q dispatched since q arrived.
    A waiting job q FIRES when cnt[q] >= N.
    Dispatch rule: if the fired set is non-empty serve its SMALLEST-RANK member,
    otherwise serve the waiting job of smallest `pred` (ties to the smaller rank).
Claimed guarantee (eq:skip):   W[i] <= W_FCFS[i] + (N + 2k - 2) L / k.

Two implementations here:
  * `brute`   literal, exact (Fraction clock), recomputes cnt[q] for the whole waiting
              set at every decision and takes min(fired).  No head shortcut.
  * `fast`    numba.  Uses the identity cnt[head] = TD - head (all ranks below the head
              are already dispatched) and the monotonicity of cnt in rank, so it needs
              no Fenwick tree at all; the equivalence with `brute` is what the small
              instances test.
"""
from __future__ import annotations

import argparse
import os
import sys
from fractions import Fraction

sys.dont_write_bytecode = True
for _v in ("PYTHONHOME", "PYTHONPATH", "UV_INTERNAL__PYTHONHOME"):
    os.environ.pop(_v, None)
os.environ.setdefault("NUMBA_NUM_THREADS", "4")
os.environ.setdefault("OMP_NUM_THREADS", "4")
SCRATCH = r"<cache-dir>"
WORK = os.path.join(SCRATCH, "mv31_verify")
os.makedirs(WORK, exist_ok=True)
os.environ["NUMBA_CACHE_DIR"] = os.path.join(WORK, "numba_cache")
os.makedirs(os.environ["NUMBA_CACHE_DIR"], exist_ok=True)

import numpy as np                                                       # noqa: E402
from numba import njit                                                   # noqa: E402

L = 60.0
OUT = []


def say(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    OUT.append(s)


# --------------------------------------------------------------------------- #
# literal reference: exact arithmetic, min-rank fired, cnt recomputed each time
# --------------------------------------------------------------------------- #
def brute(a, s, pred, k, N):
    n = len(a)
    a = [Fraction(x) for x in a]
    s = [Fraction(x) for x in s]
    free = [None] * k                 # finish time per server, None = idle
    waiting = []
    start = [None] * n
    disp = []                         # (rank, dispatch time) in order
    nxt = 0
    t = min(a)
    done = 0
    while done < n:
        for q in range(k):
            if free[q] is not None and free[q] <= t:
                free[q] = None
                done += 1
        while nxt < n and a[nxt] <= t:
            waiting.append(nxt)
            nxt += 1
        while waiting and any(f is None for f in free):
            fired = [q for q in waiting
                     if sum(1 for (d, dt) in disp if d > q and dt >= a[q]) >= N]
            pick = min(fired) if fired else min(waiting, key=lambda q: (pred[q], q))
            srv = free.index(None)
            free[srv] = t + s[pick]
            start[pick] = t
            disp.append((pick, t))
            waiting.remove(pick)
        nt = None
        for f in free:
            if f is not None and (nt is None or f < nt):
                nt = f
        if nxt < n and (nt is None or a[nxt] < nt):
            nt = a[nxt]
        if nt is None:
            break
        t = nt
    return [float(start[i] - a[i]) for i in range(n)], [d for d, _ in disp]


def brute_fcfs(a, s, k):
    """FCFS by the same event loop (used as the reference W_FCFS)."""
    n = len(a)
    return brute(a, s, list(range(n)), k, 0)[0]


# --------------------------------------------------------------------------- #
# fast version
# --------------------------------------------------------------------------- #
@njit(cache=True)
def _push(hk, hx, m, key, ix):
    hk[m] = key
    hx[m] = ix
    c = m
    while c > 0:
        p = (c - 1) >> 1
        if hk[p] > hk[c] or (hk[p] == hk[c] and hx[p] > hx[c]):
            hk[p], hk[c] = hk[c], hk[p]
            hx[p], hx[c] = hx[c], hx[p]
            c = p
        else:
            break
    return m + 1


@njit(cache=True)
def _pop(hk, hx, m):
    m -= 1
    hk[0] = hk[m]
    hx[0] = hx[m]
    c = 0
    while True:
        l = 2 * c + 1
        if l >= m:
            break
        r = l + 1
        b = l
        if r < m and (hk[r] < hk[l] or (hk[r] == hk[l] and hx[r] < hx[l])):
            b = r
        if hk[b] < hk[c] or (hk[b] == hk[c] and hx[b] < hx[c]):
            hk[b], hk[c] = hk[c], hk[b]
            hx[b], hx[c] = hx[c], hx[b]
            c = b
        else:
            break
    return m


@njit(cache=True)
def _fast(a, s, pred, k, N):
    n = a.shape[0]
    wait = np.empty(n, np.float64)
    served = np.zeros(n, np.uint8)
    INF = 1.0e300
    fin = np.full(k, INF, np.float64)
    busy = np.zeros(k, np.uint8)
    hk = np.empty(n + 1, np.float64)
    hx = np.empty(n + 1, np.int64)
    nh = 0
    head = 0        # smallest rank not yet dispatched
    TD = 0          # total dispatched
    i = 0
    nwait = 0
    nstart = 0
    nforced = 0
    qw_total = 0
    qw_forced = 0
    t = -1.0e300
    while nstart < n:
        for q in range(k):
            if busy[q] == 1 and fin[q] <= t:
                busy[q] = 0
                fin[q] = INF
        while i < n and a[i] <= t:
            nh = _push(hk, hx, nh, pred[i], i)
            nwait += 1
            i += 1
        slot = -1
        for q in range(k):
            if busy[q] == 0:
                slot = q
                break
        if nwait > 0 and slot >= 0:
            while served[head] == 1:
                head += 1
            # cnt[head] = TD - head : every rank below the head is already dispatched
            if TD - head >= N:
                j = head
                forced = 1
            else:
                while served[hx[0]] == 1:
                    nh = _pop(hk, hx, nh)
                j = hx[0]
                nh = _pop(hk, hx, nh)
                forced = 0
            served[j] = 1
            TD += 1
            qw_total += nwait
            if forced == 1:
                nforced += 1
                qw_forced += nwait
            nwait -= 1
            nstart += 1
            wait[j] = t - a[j]
            fin[slot] = t + s[j]
            busy[slot] = 1
            continue
        nx = INF
        for q in range(k):
            if busy[q] == 1 and fin[q] < nx:
                nx = fin[q]
        if i < n and a[i] < nx:
            nx = a[i]
        if nx >= INF:
            break
        if nx < t:
            nx = t
        t = nx
    return wait, nforced, qw_total, qw_forced


def fast(a, s, pred, k, N):
    return _fast(np.ascontiguousarray(a, np.float64),
                 np.ascontiguousarray(s, np.float64),
                 np.ascontiguousarray(pred, np.float64), int(k), int(N))


@njit(cache=True)
def _fcfs(a, s, k):
    n = a.shape[0]
    w = np.empty(n, np.float64)
    fin = np.zeros(k, np.float64)
    for i in range(n):
        m = 0
        for q in range(1, k):
            if fin[q] < fin[m]:
                m = q
        st = fin[m] if fin[m] > a[i] else a[i]
        w[i] = st - a[i]
        fin[m] = st + s[i]
    return w


def ncap(G, k, Ls=L):
    """largest N with (N + 2k - 2) L / k <= G"""
    n = 0
    while (n + 1 + 2 * k - 2) * Ls / k <= G + 1e-12:
        n += 1
    return n


# --------------------------------------------------------------------------- #
def rand_instance(rng, n, k, tie, Lmax=L):
    """arrivals on a coarse integer grid so ties and coincidences are common."""
    step = rng.choice([1, 2, 5])
    a = np.sort(rng.integers(0, max(2, n // tie) * step, size=n).astype(np.float64))
    grid = rng.choice([1.0, 0.5, 0.25])
    s = np.maximum(1.0, rng.integers(1, int(Lmax / grid) + 1, size=n) * grid)
    s = np.minimum(s, Lmax).astype(np.float64)
    pred = rng.integers(0, max(2, n // 2), size=n).astype(np.float64)
    return a, s, pred


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nsmall", type=int, default=4000)
    ap.add_argument("--cell", default="")          # e.g. primary:0:2
    a_ = ap.parse_args()

    say("=" * 96)
    say("1. N = floor(Gk/L - (2k-2)) IS THE LARGEST N THE eq:skip GUARANTEE ALLOWS")
    say("=" * 96)
    say("   bound  (N + 2k - 2) L / k <= G,   L = 60 s")
    say("   k    G      N(mine)  promise(N)    promise(N+1)  report N   match")
    rep = {(4, 300.0): 14, (4, 600.0): 34, (4, 1200.0): 74,
           (5, 300.0): 17, (5, 600.0): 42, (5, 1200.0): 92,
           (7, 300.0): 23, (7, 600.0): 58, (7, 1200.0): 128,
           (8, 300.0): 26, (8, 600.0): 66, (8, 1200.0): 146,
           (1, 300.0): 5, (1, 600.0): 10, (1, 1200.0): 20}
    nbad = 0
    for k in (1, 4, 5, 7, 8):
        for G in (300.0, 600.0, 1200.0):
            N = ncap(G, k)
            p0 = (N + 2 * k - 2) * L / k
            p1 = (N + 1 + 2 * k - 2) * L / k
            ok = rep[(k, G)] == N
            nbad += 0 if ok else 1
            say(f"   {k:2d} {G:7.0f}   {N:5d}   {p0:9.2f} s   {p1:9.2f} s    "
                f"{rep[(k, G)]:5d}   {ok}")
    say(f"   disagreements with the report's Ncap column: {nbad}")
    say("   (also: the completion charge (N + 3k - 2)L/k <= G gives "
        f"k=4,G=600 -> N={int(600 * 4 / 60 - (3 * 4 - 2))}, which is v3's 30)")

    say("")
    say("=" * 96)
    say(f"2. SMALL INSTANCES: my literal reference vs my fast kernel vs v31_skipkern")
    say("=" * 96)
    sys.path.insert(0, os.path.join(r"<repo-root>", "evidence",
                                    "main_v3", "v31"))
    import v31_skipkern as BK                      # the builder's kernel, compared only

    rng = np.random.default_rng(20260920)
    mx_bf = mx_bk = 0.0
    nfc = npp = 0
    worst_used = 0.0
    worst_inst = None
    nviol = 0
    ncmp = 0
    minrank_ne_head = 0
    for it in range(a_.nsmall):
        n = int(rng.integers(2, 14))
        k = int(rng.integers(1, 5))
        tie = int(rng.integers(1, 4))
        a, s, pred = rand_instance(rng, n, k, tie)
        Nmax = int(rng.integers(0, n + 3))
        wb, order = brute(a, s, pred, k, Nmax)
        wf_e = brute_fcfs(a, s, k)
        wm = fast(a, s, pred, k, Nmax)[0]
        wk = BK.run(a, s, pred, k, Nmax).w
        mx_bf = max(mx_bf, float(np.abs(np.array(wb) - wm).max()))
        mx_bk = max(mx_bk, float(np.abs(np.array(wb) - wk).max()))
        ncmp += n
        # anchors
        if Nmax == 0:
            nfc += 1
            assert np.abs(np.array(wb) - np.array(wf_e)).max() < 1e-12, ("N=0 != FCFS", it)
        if Nmax >= n:
            npp += 1
        # the bound, on MY OWN waits, in exact terms
        ub = np.array(wf_e) + (Nmax + 2 * k - 2) * L / k
        ex = np.array(wb) - np.array(wf_e)
        bad = int((np.array(wb) > ub + 1e-9).sum())
        nviol += bad
        if bad:
            say(f"   !! BOUND VIOLATION it={it} n={n} k={k} N={Nmax}")
            say(f"      a={list(a)} s={list(s)} pred={list(pred)}")
        allowed = (Nmax + 2 * k - 2) * L / k
        if allowed > 0:
            u = float(ex.max() / allowed)
            if u > worst_used:
                worst_used, worst_inst = u, (it, n, k, Nmax)
    say(f"   instances {a_.nsmall}, jobs compared {ncmp:,}")
    say(f"   max |literal reference - my fast kernel|   = {mx_bf:.3g}")
    say(f"   max |literal reference - v31_skipkern|     = {mx_bk:.3g}")
    say(f"   N = 0 anchors (must equal FCFS): {nfc}, all exact")
    say(f"   N >= n instances: {npp}")
    say(f"   bound violations on MY waits: {nviol}")
    say(f"   worst used/allowed {worst_used:.4f} at {worst_inst}")
    say("   NOTE the literal reference takes min(fired) over the whole waiting set and")
    say("        never assumes the head; the fast kernel uses cnt[head] = TD - head.")
    say(f"        disagreements between the two: {'0' if mx_bf == 0 else mx_bf}")

    say("")
    say("=" * 96)
    say("3. TRYING TO BREAK THE BOUND ON PURPOSE")
    say("=" * 96)
    # tight structured families: all services exactly L, simultaneous arrivals, small N
    worst = 0.0
    warg = None
    nv2 = 0
    tested = 0
    for k in (1, 2, 3, 4, 5):
        for N in (0, 1, 2, 3, 5, 8):
            for trial in range(400):
                n = int(rng.integers(2, 16))
                mode = trial % 4
                if mode == 0:                     # everything at t=0, service L
                    a = np.zeros(n)
                    s = np.full(n, L)
                elif mode == 1:                   # burst at 0, then a trickle
                    a = np.concatenate([np.zeros(max(1, n - 2)),
                                        np.full(min(2, n), 1.0)])[:n]
                    s = rng.choice([1e-6, L], size=n)
                elif mode == 2:                   # k-1 long, one short, one long
                    a = np.zeros(n)
                    s = np.full(n, L)
                    s[min(n - 1, k - 1)] = 1e-9
                else:
                    a = np.sort(rng.integers(0, 3, size=n).astype(float))
                    s = rng.choice([1e-9, 1.0, L], size=n)
                pred = rng.permutation(n).astype(float)
                if mode == 2:
                    pred = -s                      # longest-first: maximal damage
                wb, _ = brute(a, s, pred, k, N)
                wf_e = brute_fcfs(a, s, k)
                allowed = (N + 2 * k - 2) * L / k
                ex = np.array(wb) - np.array(wf_e)
                tested += n
                if ex.max() > allowed + 1e-9:
                    nv2 += 1
                    say(f"   !! VIOLATION k={k} N={N} excess {ex.max():.6f} > {allowed:.6f}")
                    say(f"      a={list(a)} s={list(s)} pred={list(pred)}")
                if allowed > 0 and ex.max() / allowed > worst:
                    worst = ex.max() / allowed
                    warg = (k, N, n, mode)
    say(f"   structured adversarial instances: {5 * 6 * 400}, jobs {tested:,}")
    say(f"   violations: {nv2}")
    say(f"   worst used/allowed {worst:.6f} at (k, N, n, mode) = {warg}")

    # exhaustive enumeration over tiny instances
    say("")
    say("   exhaustive: n <= 5, arrivals in {0,1,2}, services in {1, 30, 60}, "
        "all pred permutations")
    import itertools
    nv3 = 0
    cnt3 = 0
    w3 = 0.0
    for n in (2, 3, 4):
        for k in (1, 2, 3):
            for av in itertools.product((0.0, 1.0, 2.0), repeat=n):
                if list(av) != sorted(av):
                    continue
                for sv in itertools.product((1.0, 30.0, 60.0), repeat=n):
                    for pv in itertools.permutations(range(n)):
                        for N in (0, 1, 2):
                            wb, _ = brute(list(av), list(sv), list(map(float, pv)), k, N)
                            wf_e = brute_fcfs(list(av), list(sv), k)
                            ex = np.array(wb) - np.array(wf_e)
                            allowed = (N + 2 * k - 2) * L / k
                            cnt3 += 1
                            if ex.max() > allowed + 1e-9:
                                nv3 += 1
                                if nv3 < 4:
                                    say(f"   !! EXH VIOLATION n={n} k={k} N={N} a={av} "
                                        f"s={sv} pred={pv} excess {ex.max()}")
                            if allowed > 0:
                                w3 = max(w3, ex.max() / allowed)
    say(f"   exhaustive instances {cnt3:,}, violations {nv3}, worst used/allowed {w3:.4f}")

    # ---- 4. a full primary cell at rho 1.0 ---------------------------------
    if a_.cell:
        say("")
        say("=" * 96)
        say("4. FULL CELL: my kernel vs v31_skipkern, and the bound on my waits")
        say("=" * 96)
        tr, rep_, lev = a_.cell.split(":")
        z = np.load(os.path.join(SCRATCH, "mv31", "traces", f"{tr}_rep{rep_}.npz"))
        K = list(z["K"])
        k = int(K[int(lev)]) if len(K) > 1 else int(K[0])
        A = np.ascontiguousarray(z["a"], np.float64)
        S = np.ascontiguousarray(z["svc"], np.float64)
        P = np.ascontiguousarray(z["tweedie"], np.float64)
        say(f"   {tr} rep{rep_} L{lev}: k={k} n={len(A):,} max service {S.max():.4f} s")
        wf = _fcfs(A, S, k)
        for G in (300.0, 600.0, 1200.0):
            N = ncap(G, k)
            wm = fast(A, S, P, k, N)[0]
            wk = BK.run(A, S, P, k, N).w
            d = np.abs(wm - wk)
            ub = wf + (N + 2 * k - 2) * L / k
            v = int((wm > ub + 1e-6).sum())
            ex = wm - wf
            allowed = (N + 2 * k - 2) * L / k
            dl = z["dl"].astype(bool)
            q1 = wf <= 1.0
            say(f"   G={G:6.0f} N={N:4d}: differing jobs {int((d > 0).sum())}, "
                f"max |diff| {d.max():.3g}; bound violations {v}; "
                f"max excess {ex.max():.4f} s (allowed {allowed:.1f}, "
                f"used/allowed {ex.max() / allowed:.4f})")
            say(f"            my p99_dl {np.quantile(wm[dl], 0.99):.4f} s, "
                f"harm(W_FCFS<=1s) {ex[q1].max():.4f} s, "
                f"FCFS p99_dl {np.quantile(wf[dl], 0.99):.4f} s")

    open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "out_skip.txt"),
         "w", encoding="utf-8").write("\n".join(OUT) + "\n")


if __name__ == "__main__":
    main()
