"""C2 part 1: my simulator against an exact rational brute force, and against the
builder's kernel, on small random instances.

The brute force below is a direct transcription of the definitions in chapter 4 of
docs/research_plan.md: it keeps the waiting set as a list, recomputes over[q] by charging
every completion to every waiting job of smaller rank, and scans the whole waiting set for
the fired one.  All times are Fractions, so the firing test is exact and the comparison
cannot hide a rounding disagreement.

Instances are drawn with simultaneous arrivals, tied predictions, tied service times,
zero budgets and budgets far larger than any overtake.

usage: vsmall.py [--n 5000]
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from fractions import Fraction as Fr

import numpy as np

import vsim
from vsim import L

sys.path.insert(0, r"<repo-root>\evidence\guard_variants")
import guardkern as GK                                                  # noqa: E402


def brute(a, svc, k, policy, pred, B0=0, eta=0, Bmax=0, Ncap=0):
    """Exact reference.  a, svc as Fractions.  Returns the wait of every job."""
    n = len(a)
    eta = Fr(eta).limit_denominator(1000)
    wait = [None] * n
    over = [Fr(0)] * n
    cnt = [0] * n
    waiting = []                      # ranks, kept sorted
    run = []                          # (finish, rank)
    nxt = 0
    t = a[0]
    done = 0
    while done < n:
        # completions at or before t
        for fin, c in sorted(run):
            if fin <= t:
                run.remove((fin, c))
                for q in waiting:
                    if q < c:
                        if policy == "skip":
                            cnt[q] += 1
                        else:
                            over[q] += svc[c]
        # arrivals at or before t
        while nxt < n and a[nxt] <= t:
            waiting.append(nxt)
            nxt += 1
        waiting.sort()
        # one dispatch
        if waiting and len(run) < k:
            j = None
            if policy == "guard" or policy == "skip":
                fired = []
                for q in waiting:
                    if policy == "skip":
                        if cnt[q] >= Ncap:
                            fired.append(q)
                    else:
                        bud = B0 + eta * k * (t - a[q])
                        if Bmax > 0 and bud > Bmax:
                            bud = Bmax
                        if over[q] >= bud:
                            fired.append(q)
                if fired:
                    j = min(fired)
            if j is None:
                if policy == "fcfs":
                    j = waiting[0]
                else:
                    j = min(waiting, key=lambda q: (pred[q], q))
            waiting.remove(j)
            wait[j] = t - a[j]
            run.append((t + svc[j], j))
            done += 1
            continue
        # advance
        cand = [f for f, _ in run]
        if nxt < n:
            cand.append(a[nxt])
        if not cand:
            break
        t = max(t, min(cand))
    return [float(w) for w in wait]


def draw(rng, i):
    n = int(rng.integers(1, 41))
    k = int(rng.integers(1, 5))
    # arrivals in whole milliseconds, with repeats so simultaneous arrivals happen often
    step = rng.choice([0, 0, 1, 5, 50, 500])
    a_ms = np.sort(rng.integers(0, max(1, int(step) * n + 1), size=n))
    s_ms = rng.choice([1, 1, 2, 1000, 5000, 60000, 17345], size=n)      # ties, and the cap
    pred = rng.choice([0.0, 1.0, 2.0, 3.0], size=n) if i % 3 == 0 else rng.random(n)
    return n, k, a_ms.astype(np.int64), s_ms.astype(np.int64), pred


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=5000)
    args = ap.parse_args()
    rng = np.random.default_rng(20260919)
    kinds = Counter()
    worst_bb = 0.0          # brute vs mine
    worst_bk = 0.0          # builder kernel vs mine
    worst_used = 0.0
    nviol = 0
    for it in range(args.n):
        n, k, a_ms, s_ms, pred = draw(rng, it)
        a = a_ms / 1000.0
        svc = s_ms / 1000.0
        aF = [Fr(int(x), 1000) for x in a_ms]
        sF = [Fr(int(x), 1000) for x in s_ms]
        pick = it % 5
        if pick == 0:
            kind, kw, gkw = "fcfs", dict(policy="fcfs"), dict(policy="fcfs")
        elif pick == 1:
            kind = "pri"
            kw = dict(policy="pri", pred=pred)
            gkw = dict(policy="pri", pred=pred)
        elif pick == 2:                       # capped relative budget, incl. zero budget
            G = float(rng.choice([300.0, 600.0, 1200.0]))
            Bmax = vsim.gmax(G, k)
            B0 = float(rng.choice([0.0, 1e-6, 7.5, 30.0, 120.0, 600.0])) * k / 4.0
            eta = float(rng.choice([0.0, 0.25, 0.5, 0.75, 0.9]))
            kind = "cap"
            kw = dict(policy="cap", pred=pred, B0=B0, eta=eta, Bmax=Bmax)
            gkw = dict(policy="guard", pred=pred, B=min(B0, Bmax), eps=eta * k, Bmax=Bmax,
                       Mslots=1 << 12)
        elif pick == 3:                       # fixed budget at the same guarantee
            G = float(rng.choice([300.0, 600.0, 1200.0]))
            Bmax = vsim.gmax(G, k)
            kind = "fix"
            kw = dict(policy="cap", pred=pred, B0=Bmax, eta=0.0, Bmax=Bmax)
            gkw = dict(policy="guard", pred=pred, B=Bmax, Bmax=Bmax, Mslots=1 << 12)
        else:
            G = float(rng.choice([300.0, 600.0, 1200.0]))
            Ncap = vsim.skip_n(G, k)
            kind = "skip"
            kw = dict(policy="skip", pred=pred, Ncap=Ncap)
            gkw = dict(policy="guard", pred=pred, B=-1.0, theta=L, Ncap=Ncap,
                       Mslots=1 << 12)
        kinds[kind] += 1
        mine = vsim.run(a, svc, k, **kw)["w"]
        gk = GK.run(a, svc, k, **gkw).w
        bpol = {"fcfs": "fcfs", "pri": "pri", "cap": "guard", "fix": "guard",
                "skip": "skip"}[kind]
        # the budgets enter the kernel as integer microseconds; the reference uses the
        # same exact values, so a disagreement can only be about the policy, not rounding
        b0f = Fr(int(round(kw.get("B0", 0.0) * 1e6)), 10 ** 6)
        bmf = Fr(int(round(kw.get("Bmax", 0.0) * 1e6)), 10 ** 6)
        bb = brute(aF, sF, k, bpol, pred, B0=b0f, eta=kw.get("eta", 0.0), Bmax=bmf,
                   Ncap=kw.get("Ncap", 0))
        dd = float(np.abs(np.asarray(bb) - mine).max())
        if dd > 1e-9 and worst_bb <= 1e-9:
            print(f"MISMATCH it={it} kind={kind} n={n} k={k} kw="
                  f"{ {q: v for q, v in kw.items() if q != 'pred'} }", flush=True)
            print("  a  =", list(a_ms), flush=True)
            print("  svc=", list(s_ms), flush=True)
            print("  pred=", list(np.round(pred, 4)), flush=True)
            print("  brute=", list(np.round(bb, 6)), flush=True)
            print("  mine =", list(np.round(mine, 6)), flush=True)
        worst_bb = max(worst_bb, dd)
        worst_bk = max(worst_bk, float(np.abs(gk - mine).max()))
        if kind in ("cap", "fix", "skip"):
            wf = vsim.run(a, svc, k, policy="fcfs")["w"]
            ub = vsim.bound(wf, k, B0=kw.get("B0", 0.0), eta=kw.get("eta", 0.0),
                            Bmax=kw.get("Bmax", 0.0), Ncap=kw.get("Ncap", 0))
            nviol += int((mine > ub + 1e-9).sum())
            r = (mine - wf) / np.maximum(ub - wf, 1e-12)
            worst_used = max(worst_used, float(r.max()))
        if (it + 1) % 1000 == 0:
            print(f"[{it + 1:5d}] brute-vs-mine {worst_bb:g}  kernel-vs-mine {worst_bk:g}  "
                  f"bound violations {nviol}  worst used/allowed {worst_used:.4f}",
                  flush=True)
    print(f"instances {args.n} {dict(kinds)}")
    print(f"max |brute - mine|          {worst_bb:g}")
    print(f"max |builder kernel - mine| {worst_bk:g}")
    print(f"per-job bound violations on MY waits: {nviol}; worst used/allowed {worst_used:.4f}")


if __name__ == "__main__":
    main()
