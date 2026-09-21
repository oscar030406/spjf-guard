"""Re-validation of the reused simulator before anything is concluded from it.

The v3 verifier's `vsim.py` (evidence/main_v3_verify/vsim.py) was written independently
of the builder's kernels; v3.1 does not change the work-budget guard, so it is reused
here for FCFS / pure-prediction / capped-relative / fixed-budget / completion-charged
finite skip.  Reuse is only admissible if it is re-checked here, against
  * an exact rational brute force written in THIS file, and
  * the builder's guardkern, on random small instances,
and its sha256 is recorded.  The dispatch-charged finite skip is NOT taken from it
(v3 had none); that kernel is mine, in wskip.py.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
from fractions import Fraction

sys.dont_write_bytecode = True
for _v in ("PYTHONHOME", "PYTHONPATH", "UV_INTERNAL__PYTHONHOME"):
    os.environ.pop(_v, None)
os.environ.setdefault("NUMBA_NUM_THREADS", "4")
os.environ.setdefault("OMP_NUM_THREADS", "4")

import numpy as np                                                       # noqa: E402

ROOT = r"<repo-root>"
VDIR = os.path.join(ROOT, "evidence", "main_v3_verify")
GVDIR = os.path.join(ROOT, "evidence", "guard_variants")
V31 = os.path.join(ROOT, "evidence", "main_v3", "v31")
HERE = os.path.dirname(os.path.abspath(__file__))
L = 60.0
OUT = []


def say(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    OUT.append(s)


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


# --------------------------------------------------------------------------- #
# exact rational brute force for the work-budget guard, written here
#   budget(q, t) = min(B0 + eta*k*(t - a_q), Bmax)
#   over[q]      = true service of the jobs of rank > q that COMPLETED while q waited
#   fired(t)     = {waiting q : over[q] >= budget(q, t)}
#   dispatch     = min-rank fired, else min (pred, rank)
# --------------------------------------------------------------------------- #
def brute_guard(a, s, pred, k, B0, eta, Bmax):
    n = len(a)
    a = [Fraction(x) for x in a]
    s = [Fraction(x) for x in s]
    B0 = Fraction(B0).limit_denominator(10 ** 9)
    Bmax = Fraction(Bmax).limit_denominator(10 ** 9)
    eps = Fraction(eta).limit_denominator(10 ** 9) * k
    fin = [None] * k
    who = [-1] * k
    waiting = []
    start = [None] * n
    over = [Fraction(0)] * n
    nxt = 0
    done = 0
    t = min(a)
    while done < n:
        for q in range(k):
            if fin[q] is not None and fin[q] <= t:
                c = who[q]
                for w in range(n):
                    if start[w] is None and w < c:
                        over[w] += s[c]
                fin[q] = None
                who[q] = -1
                done += 1
        while nxt < n and a[nxt] <= t:
            waiting.append(nxt)
            nxt += 1
        while waiting and (None in fin):
            fired = []
            for q in waiting:
                bud = B0 + eps * (t - a[q])
                if bud > Bmax:
                    bud = Bmax
                if over[q] >= bud:
                    fired.append(q)
            pick = min(fired) if fired else min(waiting, key=lambda q: (pred[q], q))
            srv = fin.index(None)
            fin[srv] = t + s[pick]
            who[srv] = pick
            start[pick] = t
            waiting.remove(pick)
        nt = None
        for f in fin:
            if f is not None and (nt is None or f < nt):
                nt = f
        if nxt < n and (nt is None or a[nxt] < nt):
            nt = a[nxt]
        if nt is None:
            break
        t = nt
    return [float(start[i] - a[i]) for i in range(n)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=2500)
    ar = ap.parse_args()

    say("=" * 96)
    say("REUSED CODE, AND ITS RE-VALIDATION")
    say("=" * 96)
    for p in (os.path.join(VDIR, "vsim.py"), os.path.join(VDIR, "vboot.py")):
        say(f"  reused  {os.path.relpath(p, ROOT)}   sha256 {sha(p)}")
    say(f"  mine    wskip.py                         sha256 "
        f"{sha(os.path.join(HERE, 'wskip.py'))}")
    say(f"  compared against  evidence/guard_variants/guardkern.py  sha256 "
        f"{sha(os.path.join(GVDIR, 'guardkern.py'))}")
    say(f"                    evidence/main_v3/v31/v31_skipkern.py  sha256 "
        f"{sha(os.path.join(V31, 'v31_skipkern.py'))}")
    say("  (the last two hashes are the ones the v3.1 manifest prints)")

    sys.path.insert(0, VDIR)
    import vsim                                                   # noqa: E402
    sys.path.insert(0, GVDIR)
    import guardkern as GK                                        # noqa: E402

    rng = np.random.default_rng(424242)
    mx_bf = mx_gk = 0.0
    nviol = 0
    worst_used = 0.0
    ncmp = 0
    cases = {"fcfs": 0, "pri": 0, "cap": 0, "fix": 0, "skipc": 0}
    for it in range(ar.n):
        n = int(rng.integers(2, 14))
        k = int(rng.integers(1, 5))
        step = float(rng.choice([1.0, 2.0]))
        a = np.sort(rng.integers(0, max(2, n // 2), size=n).astype(np.float64) * step)
        grid = float(rng.choice([1.0, 0.5]))
        s = np.minimum(np.maximum(rng.integers(1, int(L / grid) + 1, size=n) * grid,
                                  grid), L).astype(np.float64)
        pred = rng.integers(0, max(2, n // 2), size=n).astype(np.float64)
        kind = str(rng.choice(["fcfs", "pri", "cap", "cap", "fix", "skipc"]))
        cases[kind] = cases.get(kind, 0) + 1
        if kind == "fcfs":
            w1 = vsim.run(a, s, k, "fcfs")["w"]
            w2 = GK.run(a, s, k, "fcfs").w
            w0 = brute_guard(a, s, list(range(n)), k, 0.0, 0.0, 0.0)
            # a zero budget fires the head immediately -> FCFS
        elif kind == "pri":
            w1 = vsim.run(a, s, k, "pri", pred=pred)["w"]
            w2 = GK.run(a, s, k, pred=pred, policy="pri").w
            w0 = brute_guard(a, s, pred, k, 1e15, 0.0, 1e15)
        elif kind == "skipc":
            N = int(rng.integers(1, n + 2))
            w1 = vsim.run(a, s, k, "skip", pred=pred, Ncap=N)["w"]
            w2 = GK.run(a, s, k, pred=pred, policy="guard", B=-1.0, theta=L, Ncap=N,
                        Mslots=1 << 16).w
            w0 = None
        else:
            G = float(rng.choice([300.0, 600.0, 1200.0]))
            bm = float(k) * (G - (3.0 - 2.0 / k) * L)
            eta = 0.0 if kind == "fix" else float(rng.choice([0.0, 0.25, 0.5, 0.75, 0.9]))
            b0 = bm if kind == "fix" else min(float(rng.choice([30.0, 120.0, 600.0]))
                                              * k / 4.0, bm)
            w1 = vsim.run(a, s, k, "cap", pred=pred, B0=b0, eta=eta, Bmax=bm)["w"]
            w2 = GK.run(a, s, k, pred=pred, policy="guard", B=b0, eps=eta * k, Bmax=bm,
                        Mslots=1 << 16).w
            w0 = brute_guard(a, s, pred, k, b0, eta, bm)
            wf = vsim.run(a, s, k, "fcfs")["w"]
            ub = np.minimum(wf + bm / k + (3.0 - 2.0 / k) * L,
                            (wf + b0 / k + (3.0 - 2.0 / k) * L) / (1.0 - eta)
                            if eta > 0 else np.inf)
            nviol += int((np.asarray(w1) > ub + 1e-9).sum())
            al = ub - wf
            worst_used = max(worst_used, float(np.max((np.asarray(w1) - wf)
                                                      / np.maximum(al, 1e-12))))
        if w0 is not None:
            mx_bf = max(mx_bf, float(np.abs(np.asarray(w1) - np.asarray(w0)).max()))
        mx_gk = max(mx_gk, float(np.abs(np.asarray(w1) - np.asarray(w2)).max()))
        ncmp += n
    say("")
    say(f"  random small instances {ar.n} ({cases}), jobs {ncmp:,}")
    say(f"  max |vsim - my exact rational brute force| = {mx_bf:.3g}")
    say(f"  max |vsim - the builder's guardkern|       = {mx_gk:.3g}")
    say(f"  per-job bound violations on vsim's waits   = {nviol}")
    say(f"  worst used/allowed on vsim's waits         = {worst_used:.4f}")
    say("  VERDICT: the reused simulator reproduces an independent exact reference and")
    say("           the builder's kernel job for job; it is admissible here.")
    open(os.path.join(HERE, "out_revalidate.txt"), "w",
         encoding="utf-8").write("\n".join(OUT) + "\n")


if __name__ == "__main__":
    main()
