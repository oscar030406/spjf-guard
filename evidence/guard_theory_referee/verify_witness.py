"""Re-verify the worst-constant witnesses found by the numba search, using the
pure-python reference simulator only."""
import sys
sys.dont_write_bytecode = True
from fractions import Fraction
from refsim2 import (simulate, fcfs_chooser, make_choice_chooser,
                     make_guard_choice_chooser, in_out)

W = [
 # (k, a, x, tape, label)   -- from run_tight.py after the state-restore fix
 (2, [0, 0, 0, 1, 2, 2, 3, 3, 3, 3, 4, 4, 5, 5, 5, 5],
     [0, 1, 2, 2, 0, 0, 0, 2, 1, 1, 0, 0, 1, 1, 2, 2],
     [12, 8, 8, 6, 15, 0, 2, 2, 5, 8, 12, 14, 8, 5, 11, 6], "T1 worst k=2"),
 (3, [1, 1, 1, 1, 1, 1, 1, 3, 3, 3, 3, 3, 3, 3, 3, 4],
     [0, 0, 2, 0, 1, 2, 1, 0, 0, 2, 2, 1, 2, 1, 2, 1],
     [11, 1, 6, 13, 2, 14, 2, 7, 0, 10, 8, 15, 15, 8, 1, 11], "T1 worst k=3"),
 (4, [0, 0, 1, 1, 1, 1, 1, 2, 3, 3, 3, 3, 3, 3],
     [2, 1, 2, 2, 1, 1, 1, 0, 2, 2, 0, 2, 0, 1],
     [7, 15, 3, 11, 11, 3, 0, 5, 7, 9, 7, 12, 7, 14], "T1 worst k=4"),
 (5, [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1],
     [2, 2, 0, 2, 2, 2, 2, 0, 0, 2, 0, 0, 0, 1, 2, 2],
     [15, 6, 14, 12, 1, 8, 9, 11, 7, 4, 14, 13, 9, 15, 12, 2], "T1 worst k=5"),
 (6, [0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 2],
     [2, 2, 2, 2, 0, 0, 2, 2, 0, 2, 2, 0, 2, 0],
     [7, 1, 10, 1, 15, 1, 0, 2, 10, 0, 14, 8, 1, 15], "T1 worst k=6"),
]


G = [
 # (k, B, a, x, tape, label)  -- worst (k*excess - B)/L for guard(A,B)
 (1, 1, [0, 0, 1, 1, 1], [2, 3, 9, 1, 0], [14, 5, 7, 1, 13], "T4 worst k=1"),
 (3, 10, [0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1],
     [9, 9, 1, 0, 3, 9, 3, 0, 9, 9, 6, 5],
     [8, 0, 12, 4, 6, 2, 15, 3, 13, 3, 4, 12], "T4 worst k=3"),
 (4, 8, [0, 0, 0, 0, 0, 0, 1, 2, 2, 2], [7, 7, 0, 7, 0, 7, 7, 7, 7, 7],
     [8, 7, 7, 12, 14, 6, 15, 2, 5, 12], "T4 worst k=4"),
 (6, 10, [0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1],
     [9, 7, 7, 9, 9, 3, 9, 8, 3, 9, 9, 9, 0, 8, 7],
     [1, 0, 7, 8, 0, 9, 13, 12, 6, 11, 6, 14, 11, 7, 7], "T4 worst k=6"),
]


def guards(out):
    for (k, B, a, x, tape, label) in G:
        n = len(a)
        L = max(x)
        fst, _, _ = simulate(a, x, k, fcfs_chooser)
        gst, _, god = simulate(a, x, k,
                               make_guard_choice_chooser(tape, B, x, n))
        In, Out = in_out(x, god, n)
        best = (-10 ** 9, -1)
        for i in range(n):
            v = k * (gst[i] - fst[i]) - B
            if v > best[0]:
                best = (v, i)
        v, i = best
        out.write("%s : k=%d n=%d L=%d B=%d\n" % (label, k, n, L, B))
        out.write("   a=%s\n   x=%s\n" % (a, x))
        out.write("   FCFS starts %s\n   guard starts %s  order %s\n"
                  % (fst, gst, god))
        out.write("   i=%d excess=%d  In=%d (bound B+kL=%d, strict: %s)  "
                  "(k*excess-B)/L = %s  bound 3k-2 = %d  holds=%s\n\n"
                  % (i, gst[i] - fst[i], In[i], B + k * L, In[i] < B + k * L,
                     Fraction(v, L), 3 * k - 2, v <= (3 * k - 2) * L))


def main():
    out = open("out_witness.txt", "w")
    for (k, a, x, tape, label) in W:
        n = len(a)
        L = max(x)
        fst, _, fod = simulate(a, x, k, fcfs_chooser)
        st, cp, od = simulate(a, x, k, make_choice_chooser(tape))
        In, Out = in_out(x, od, n)
        best = (0, 1, -1)
        for i in range(n):
            D = k * (st[i] - fst[i]) - (In[i] - Out[i])
            if abs(D) * best[1] > best[0] * L:
                best = (abs(D), L, i)
        i = best[2]
        D = k * (st[i] - fst[i]) - (In[i] - Out[i])
        out.write("%s : k=%d n=%d L=%d\n" % (label, k, n, L))
        out.write("   a    = %s\n   x    = %s\n" % (a, x))
        out.write("   FCFS order %s starts %s\n" % (fod, fst))
        out.write("   P    order %s starts %s\n" % (od, st))
        out.write("   i=%d  W_P=%d W_F=%d In=%d Out=%d  D=%d  |D|/L=%s  "
                  "bound 2(k-1)=%d   holds=%s\n\n"
                  % (i, st[i] - a[i], fst[i] - a[i], In[i], Out[i], D,
                     Fraction(abs(D), L), 2 * (k - 1),
                     abs(D) <= 2 * (k - 1) * L))
    guards(out)
    out.close()
    print(open("out_witness.txt").read())


if __name__ == "__main__":
    main()
