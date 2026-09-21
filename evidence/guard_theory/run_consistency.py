"""G2 consistency, with deterministic bases only (a randomised base cannot be
compared run-to-run: it is a different policy each time)."""
import sys
sys.dont_write_bytecode = True
import numpy as np
from fractions import Fraction
import sim_core as S

OUT = []
def say(*a):
    s = " ".join(str(z) for z in a); print(s); OUT.append(s)

def make_det_pseudorandom(seed):
    """Deterministic 'arbitrary' policy: a hash of the decision context."""
    def f(t, waiting, state):
        h = (seed * 1000003) ^ (t * 2654435761) ^ (len(waiting) * 40503) ^ (waiting[0] * 97)
        h = (h ^ (h >> 13)) & 0x7fffffff
        return h % len(waiting)
    return f

def make_edf(d):
    def f(t, waiting, state):
        best = 0
        for c in range(1, len(waiting)):
            if d[waiting[c]] < d[waiting[best]]: best = c
        return best
    return f

def make_prio(cl):
    def f(t, waiting, state):
        best = 0
        for c in range(1, len(waiting)):
            if cl[waiting[c]] < cl[waiting[best]]: best = c
        return best
    return f

def det_bank(rng, n, it):
    r = rng.random(); pred = list(rng.permutation(n))
    d = list(rng.integers(0, 60, n)); cl = list(rng.integers(0, 3, n))
    if r < .14: return S.fcfs, "fcfs", {}
    if r < .28: return S.lifo, "lifo", {}
    if r < .42: return S.sjf_true, "sjf", {}
    if r < .56: return S.ljf_true, "ljf", {}
    if r < .70: return S.by_pred, "by_pred", {'pred': pred}
    if r < .85: return make_edf(d), "EDF", {}
    return make_prio(cl), "prio3", {}

def main(N=400000):
    say("=== G2 CONSISTENCY (deterministic bases) ===")
    rng = np.random.default_rng(2024)
    c1t=c1b=0; c2t=c2b=0; nec_t=nec_b=0; outt=outb=0
    fired_below = 0; below_t = 0
    for it in range(N):
        k = int(rng.integers(1,5)); n = int(rng.integers(1,12))
        m = int(rng.integers(0,4))
        if m==0: a = np.sort(rng.integers(0,3,n))
        elif m==1: a = np.zeros(n,dtype=np.int64)
        elif m==2: a = np.sort(rng.integers(0,40,n))
        else: a = np.sort(rng.integers(0,8,n))
        L = int(rng.integers(1,10)); x = rng.integers(0,L+1,n)
        Lr = max(1,int(x.max()))
        jobs = [(int(a[i]),int(x[i])) for i in range(n)]
        if rng.random() < .15:
            base, name, st0 = make_det_pseudorandom(it), "det-pseudorandom", {}
        else:
            base, name, st0 = det_bank(rng, n, it)
        Wb, Inb, Outb, orderb, _ = S.run(jobs, k, base, dict(st0))
        WF = S.fcfs_wait(jobs, k)
        G = max(Wb[i]-WF[i] for i in range(n))
        # necessity proposition: In_i <= kG + (3k-2)L for any policy with excess <= G
        for i in range(n):
            nec_t += 1
            if Inb[i] > k*G + (3*k-2)*Lr: nec_b += 1
            outt += 1
            if Outb[i] > k*(G - (Wb[i]-WF[i]) + Lr): outb += 1
        B = max(Inb)+1 if n else 1
        Wg, _, _, orderg, _ = S.run(jobs, k, S.make_guard(base, B), dict(st0))
        c1t += 1
        if orderg != orderb or Wg != Wb: c1b += 1
        B2 = k*G + (3*k-2)*Lr + 1
        Wg2, _, _, orderg2, _ = S.run(jobs, k, S.make_guard(base, B2), dict(st0))
        c2t += 1
        if orderg2 != orderb or Wg2 != Wb: c2b += 1
        # does a budget just under max In actually fire?  (threshold is not vacuous)
        if max(Inb) > 0:
            below_t += 1
            Wg3, _, _, orderg3, _ = S.run(jobs, k, S.make_guard(base, max(Inb)), dict(st0))
            if orderg3 != orderb: fired_below += 1
        if it % 100000 == 0 and it: say("   ... %d" % it)
    say("necessity  In_i <= kG+(3k-2)L      : tested %d, failures %d" % (nec_t, nec_b))
    say("Out lemma  Out_i <= k(G-excess_i+L): tested %d, failures %d" % (outt, outb))
    say("(C1) B = max_i In_i^base + 1  =>  wrapped == base : tested %d, failures %d" % (c1t, c1b))
    say("(C2) B = kG + (3k-2)L + 1     =>  wrapped == base : tested %d, failures %d" % (c2t, c2b))
    say("(C3) B = max_i In_i^base (one unit lower) changes the run in %d of %d cases"
        " -- the threshold in (C1) is exactly at the boundary, not slack" % (fired_below, below_t))
    say("")

if __name__ == "__main__":
    main(400000)
    open("out_consistency.txt","w").write("\n".join(OUT)+"\n")
