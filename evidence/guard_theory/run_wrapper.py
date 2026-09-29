"""G2: the guard as a black-box wrapper.  Theorem A for arbitrary base policies,
exact consistency characterisation, and the loss when it fires."""
import sys
sys.dont_write_bytecode = True
import numpy as np
from fractions import Fraction
import sim_core as S

OUT = []
def say(*a):
    s = " ".join(str(z) for z in a); print(s); OUT.append(s)


def make_edf(rng, n):
    d = rng.integers(0, 60, n)
    def f(t, waiting, state):
        best = 0
        for c in range(1, len(waiting)):
            if d[waiting[c]] < d[waiting[best]]: best = c
        return best
    return f

def make_class_prio(rng, n):
    cl = rng.integers(0, 3, n)
    def f(t, waiting, state):
        best = 0
        for c in range(1, len(waiting)):
            if cl[waiting[c]] < cl[waiting[best]]: best = c
        return best
    return f

def make_maxrank(t_=None):
    def f(t, waiting, state): return len(waiting) - 1
    return f


def base_bank(rng, n):
    """A deliberately wild zoo of base policies: deterministic, randomised,
    size-aware, side-information-aware, adversarial."""
    r = rng.random()
    pred = list(rng.permutation(n))
    if r < .12: return S.fcfs, "fcfs", {}
    if r < .24: return S.lifo, "lifo", {}
    if r < .36: return S.sjf_true, "sjf(true sizes)", {}
    if r < .48: return S.ljf_true, "ljf(true sizes, adversarial)", {}
    if r < .60: return S.by_pred, "by_pred(random perm)", {'pred': pred}
    if r < .72: return S.make_random(rng), "uniform random", {}
    if r < .84: return make_edf(rng, n), "EDF(random deadlines)", {}
    return make_class_prio(rng, n), "3-class priority", {}


def theoremA(N=400000):
    say("=== G2 THEOREM A FOR AN ARBITRARY BASE POLICY ===")
    say("claim: k*W_guard[i] <= k*W_FCFS[i] + B + (3k-2)*L  for every job, every base")
    rng = np.random.default_rng(424242)
    worst = {k: (Fraction(-10**9), None) for k in (1,2,3,4)}
    viol = 0
    counts = {}
    for it in range(N):
        k = int(rng.integers(1, 5))
        n = int(rng.integers(1, 14))
        m = int(rng.integers(0, 4))
        if m == 0: a = np.sort(rng.integers(0, 3, n))
        elif m == 1: a = np.zeros(n, dtype=np.int64)
        elif m == 2: a = np.sort(rng.integers(0, 40, n))
        else: a = np.sort(rng.integers(0, 8, n))
        L = int(rng.integers(1, 12))
        x = rng.integers(0, L+1, n)
        if rng.random() < .4: x[rng.integers(0, n)] = L
        Lr = max(1, int(x.max()))
        jobs = [(int(a[i]), int(x[i])) for i in range(n)]
        base, name, st0 = base_bank(rng, n)
        B = int(rng.integers(0, 5*Lr+1))
        st = dict(st0)
        W, In, Out, order, start = S.run(jobs, k, S.make_guard(base, B), st)
        WF = S.fcfs_wait(jobs, k)
        counts[name] = counts.get(name, 0) + 1
        for i in range(n):
            lhs = k*(W[i]-WF[i]) - B                 # must be <= (3k-2)L
            r = Fraction(lhs, Lr)
            if r > worst[k][0]: worst[k] = (r, (jobs, k, B, name, i, lhs, Lr))
            if lhs > (3*k-2)*Lr: viol += 1
        if it % 100000 == 0 and it: say("   ... %d" % it)
    say("instances=%d  violations of Theorem A = %d" % (N, viol))
    for k in (1,2,3,4):
        r, w = worst[k]
        say("k=%d  max [k(W_g-W_F)-B]/L = %s   (Theorem A allows 3k-2 = %d)" % (k, r, 3*k-2))
        if w: say("     witness: jobs=%s B=%d base=%s job=%d" % (w[0], w[2], w[3], w[4]))
    say("base policies exercised: " + ", ".join("%s:%d" % kv for kv in sorted(counts.items())))
    say("")


def consistency(N=300000):
    say("=== G2 CONSISTENCY ===")
    say("(C1) exact: wrapped run == base run  iff  max_i In_i^base < B is enough;")
    say("     tested as: In^base_max < B  =>  identical dispatch order and identical waits")
    say("(C2) sufficient in FCFS-robust terms: if the BASE already obeys")
    say("     W_base[i] <= W_FCFS[i] + G for all i, then B > kG + (3k-2)L never fires.")
    rng = np.random.default_rng(99)
    c1_tested = c1_bad = 0
    c2_tested = c2_bad = 0
    out_tested = out_bad = 0
    for it in range(N):
        k = int(rng.integers(1, 5)); n = int(rng.integers(1, 12))
        m = int(rng.integers(0, 4))
        if m == 0: a = np.sort(rng.integers(0, 3, n))
        elif m == 1: a = np.zeros(n, dtype=np.int64)
        elif m == 2: a = np.sort(rng.integers(0, 40, n))
        else: a = np.sort(rng.integers(0, 8, n))
        L = int(rng.integers(1, 10)); x = rng.integers(0, L+1, n)
        Lr = max(1, int(x.max()))
        jobs = [(int(a[i]), int(x[i])) for i in range(n)]
        base, name, st0 = base_bank(rng, n)
        Wb, Inb, Outb, orderb, startb = S.run(jobs, k, base, dict(st0))
        WF = S.fcfs_wait(jobs, k)
        G = max(Wb[i]-WF[i] for i in range(n))
        Inmax = max(Inb) if n else 0
        # -- Out-bound lemma: Out_i <= k*(G - excess_i + L)
        for i in range(n):
            out_tested += 1
            if Outb[i] > k*(G - (Wb[i]-WF[i]) + Lr): out_bad += 1
        # C1
        B = Inmax + 1
        Wg, Ing, Outg, orderg, _ = S.run(jobs, k, S.make_guard(base, B), dict(st0))
        c1_tested += 1
        if orderg != orderb or Wg != Wb: c1_bad += 1
        # C2
        B2 = k*G + (3*k-2)*Lr + 1
        Wg2, _, _, orderg2, _ = S.run(jobs, k, S.make_guard(base, B2), dict(st0))
        c2_tested += 1
        if orderg2 != orderb or Wg2 != Wb: c2_bad += 1
        # B one below: does it ever actually fire?  (necessity of the threshold)
    say("Out-bound lemma  Out_i <= k(G - excess_i + L):  tested %d, failures %d" % (out_tested, out_bad))
    say("(C1) B = max_i In_i^base + 1 :  tested %d, wrapped != base in %d" % (c1_tested, c1_bad))
    say("(C2) B = kG + (3k-2)L + 1   :  tested %d, wrapped != base in %d" % (c2_tested, c2_bad))
    say("")


def loss_when_it_fires():
    say("=== G2 LOSS WHEN IT FIRES (there is no bound relative to the base) ===")
    # one long job of size L arrives first, then m short jobs.  SJF is optimal;
    # the guard with B = 0 forces FCFS and the mean wait blows up by ~m/2.
    for m in (4, 10, 40, 200):
        L = 100
        jobs = [(0, L)] + [(0, 1) for _ in range(m)]
        Wb, _, _, _, _ = S.run(jobs, 1, S.sjf_true)
        Wg, _, _, _, _ = S.run(jobs, 1, S.make_guard(S.sjf_true, 0))
        WF = S.fcfs_wait(jobs, 1)
        say("  m=%3d  mean W: base(SJF)=%8.3f  guard(B=0)=%8.3f  FCFS=%8.3f   guard/base=%.2f"
            % (m, sum(Wb)/len(Wb), sum(Wg)/len(Wg), sum(WF)/len(WF), (sum(Wg)/max(1e-9,sum(Wb)))))
    say("  ratio guard/base is unbounded as m grows -> no multiplicative consistency;")
    say("  the only consistency statement available is the exact one (C1)/(C2) above.")
    say("")
    say("=== G2 LAZINESS ===")
    say("the guard fires on q only when over[q] >= B, and over[q] <= In_q always;")
    say("so at every firing the constraint In_q <= B is already saturated.  Combined")
    say("with the necessity proposition (any policy with excess <= G has In <= kG+(3k-2)L),")
    say("no wrapper enforcing a work budget can defer q longer and still promise G.")
    say("")


if __name__ == "__main__":
    theoremA(400000)
    consistency(300000)
    loss_when_it_fires()
    open("out_wrapper.txt", "w").write("\n".join(OUT) + "\n")
