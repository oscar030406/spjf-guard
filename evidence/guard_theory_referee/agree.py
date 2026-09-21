"""fastsim.sim must agree with refsim2.simulate job by job (start times AND the
dispatch sequence) before any number from fastsim is used."""
import sys, random
sys.dont_write_bytecode = True
import numpy as np
from refsim2 import (simulate, fcfs_chooser, make_score_chooser,
                     make_guard_chooser, make_choice_chooser,
                     make_guard_choice_chooser)
import fastsim as F


def main():
    random.seed(99)
    bad = 0
    nchk = 0
    for trial in range(6000):
        n = random.randint(1, 8)
        k = random.randint(1, 4)
        a = np.array(sorted(random.randint(0, 6) for _ in range(n)), dtype=np.int64)
        x = np.array([random.randint(0, 4) for _ in range(n)], dtype=np.int64)
        score = np.array([random.randint(0, 20) for _ in range(n)], dtype=np.int64)
        B = np.int64(random.randint(0, 3 * (int(x.max()) + 1)))
        st = np.zeros(n, np.int64); cp = np.zeros(n, np.int64)
        od = np.zeros(n, np.int64)
        se = np.zeros(k, np.int64); sj = np.zeros(k, np.int64)
        wt = np.zeros(n, np.int64)
        rs = np.zeros(1, np.uint64); rs[0] = np.uint64(12345)
        for mode, chooser in ((F.FCFS, fcfs_chooser),
                              (F.SCORE, make_score_chooser(list(score))),
                              (F.MAXRANK, make_score_chooser([-j for j in range(n)])),
                              (F.GUARD, make_guard_chooser(list(score), int(B),
                                                           list(x), n)),
                              (F.CHOICE, make_choice_chooser(list(score))),
                              (F.GCHOICE, make_guard_choice_chooser(
                                  list(score), int(B), list(x), n))):
            F.sim(a, x, k, mode, score, B, st, cp, od, se, sj, wt, rs)
            rst, rcp, rod = simulate(list(a), list(x), k, chooser)
            nchk += 1
            if list(st) != rst or list(od) != rod or list(cp) != rcp:
                bad += 1
                if bad < 6:
                    print("MISMATCH mode", mode, list(a), list(x), k,
                          list(score), int(B))
                    print("  fast start", list(st), "ref", rst)
                    print("  fast order", list(od), "ref", rod)
        # in_out
        In = np.zeros(n, np.int64); Out = np.zeros(n, np.int64)
        pos = np.zeros(n, np.int64)
        F.in_out(x, od, n, In, Out, pos)
        from refsim2 import in_out as ref_io
        rIn, rOut = ref_io(list(x), list(od), n)
        if list(In) != rIn or list(Out) != rOut:
            bad += 1
            print("IN/OUT MISMATCH", list(a), list(x), k)
    print("agree: comparisons =", nchk, " failures =", bad)


if __name__ == "__main__":
    main()
