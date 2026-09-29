"""Constructed lower-bound instances for the late-charge bound (shared counter).

k = 1: victim, B-1 unit jobs (delay 0), one L job + (delta-1) units (delay delta), one L job.
k >= 2: cascade of Lemma S8.1 for m rounds (L = k^m), then a finale:
  k-1 new longs (L), victim (L), sync (f), pre (L), k finals (L),
  k*(delta-1) tiny units, k finals2 (L); budget B = f + L + 1.
  finals and tiny are charged late by delta; everything else at once.
"""
import sys
from fractions import Fraction
from sim import run, fcfs


def k1(L, B, d):
    arr, C, dl, pr = [], [], [], []
    def add(c, delay, p):
        arr.append(0); C.append(c); dl.append(delay); pr.append(p)
    add(L, 0, 10**9)             # victim
    for x in range(B - 1):
        add(1, 0, len(arr))
    add(L, d, len(arr))
    for x in range(d - 1):
        add(1, d, len(arr))
    add(L, d, len(arr))
    return arr, C, dl, pr, 0


def cascade_finale(k, m, d, stale=True):
    L = k ** m
    arr, C, dl, pr = [], [], [], []
    P_SHORT, P_SYNC, P_LONG, P_FIN, P_TINY, P_FIN2, P_VIC = range(7)
    def add(a, c, delay, p):
        arr.append(a); C.append(c); dl.append(delay); pr.append(p)
    for j in range(m):
        T = j * L
        for _ in range(k - 1):
            add(T, L, 0, P_LONG)
        for _ in range(L):
            add(T, 1, 0, P_SHORT)
    T = m * L
    f = L - L * (k - 1) ** m // k ** m
    B = f + L + 1
    for _ in range(k - 1):
        add(T, L, 0, P_LONG)
    vic = len(arr); add(T, L, 0, P_VIC)
    add(T, f, 0, P_SYNC)
    add(T, L, 0, P_LONG)       # pre
    for _ in range(k):
        add(T, L, d if stale else 0, P_FIN)
    if stale:
        for _ in range(k * (d - 1)):
            add(T, 1, d, P_TINY)
        for _ in range(k):
            add(T, L, d, P_FIN2)
    # priorities: static, ties by rank
    pr = [p * 10**7 + i for i, p in enumerate(pr)]
    return arr, C, dl, pr, vic, L, B, f


if __name__ == '__main__':
    # k = 1 check
    for (L, B, d) in [(3, 2, 2), (10, 7, 4), (100, 50, 30), (1000, 500, 1)]:
        arr, C, dl, pr, v = k1(L, B, d)
        st, In = run(arr, C, 1, B, dl, pr)
        sf = fcfs(arr, C, 1)
        exc = st[v] - sf[v]
        print(f'k=1 L={L} B={B} d={d}: excess={exc} bound={B+2*L+d} target B+2L+d-2={B+2*L+d-2} '
              f'In={In[v]} InBound={B+2*L+d} thm3={B+L}')
    for k in (2, 3, 4):
        for m in range(1, 13 if k == 2 else (8 if k == 3 else 6)):
            L = k ** m
            for dfrac in (Fraction(1, L), Fraction(1, 2), Fraction(1), Fraction(2)):
                d = max(1, int(dfrac * L))
                arr, C, dl, pr, v, L, B, f = cascade_finale(k, m, d)
                if len(arr) > 60000:
                    continue
                st, In = run(arr, C, k, B, dl, pr)
                sf = fcfs(arr, C, k)
                exc = st[v] - sf[v]
                kb = B + (4 * k - 2) * L + k * d
                inb = B + k * L + k * (L + d)
                print(f'k={k} m={m} L={L} d={d} n={len(arr)} B={B} excess={exc} '
                      f'ratio={k*exc/kb:.5f} gap_to_bound={Fraction(kb,k)-exc} '
                      f'In={In[v]} In/bound={In[v]/inb:.5f} over_thm3={exc - Fraction(B + (3*k-2)*L, k)}',
                      flush=True)


def pserv_k2(m, d):
    """k = 2 per-server-view witness: cascade, then sync, new-long + pre, then on each
    server one L job and d-1 units whose charges reach the other view after d, then two L jobs."""
    k = 2
    L = k ** m
    arr, C, dl, pr = [], [], [], []
    P_SHORT, P_SYNC, P_LONG, P_ST, P_TINY, P_FIN, P_VIC = range(7)
    def add(a, c, delay, p):
        arr.append(a); C.append(c); dl.append(delay); pr.append(p)
    for j in range(m):
        T = j * L
        add(T, L, 0, P_LONG)
        for _ in range(L):
            add(T, 1, 0, P_SHORT)
    T = m * L
    f = L - L // k ** m
    B = f + 2 * L + d
    add(T, L, 0, P_LONG)          # new long, rank below victim
    vic = len(arr); add(T, L, 0, P_VIC)
    add(T, f, 0, P_SYNC)
    add(T, L, 0, P_LONG)          # pre
    for _ in range(2):
        add(T, L, d, P_ST)
    for _ in range(2 * (d - 1)):
        add(T, 1, d, P_TINY)
    for _ in range(2):
        add(T, L, d, P_FIN)
    pr = [p * 10**7 + i for i, p in enumerate(pr)]
    return arr, C, dl, pr, vic, L, B, f


def main_pserv():
    for m in range(1, 12):
        for d in sorted({1, 2 ** m // 2 or 1, 2 ** m, 2 ** (m + 1)}):
            arr, C, dl, pr, v, L, B, f = pserv_k2(m, d)
            st, In = run(arr, C, 2, B, dl, pr, 'pserv', 'const')
            sf = fcfs(arr, C, 2)
            exc = st[v] - sf[v]
            kb = B + 4 * L + (L + d)          # k*bound: B + (3k-2)L + (k-1)(L+d)
            inb = B + 2 * L + (L + d)
            print(f'pserv k=2 m={m} L={L} d={d} n={len(arr)} B={B} excess={exc} ratio={2*exc/kb:.5f} '
                  f'gap={Fraction(kb,2)-exc} In={In[v]} In/bound={In[v]/inb:.5f}', flush=True)
