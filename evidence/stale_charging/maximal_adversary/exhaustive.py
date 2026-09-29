"""Exhaustive campaign. Scaled units: time x2, so L=6, sizes {2,4,6}."""
import sys, itertools, time, json
from multiprocessing import Pool
from core import explore

L = 6
SIZES = (2, 4, 6)


def arrivals(n, aset):
    for rest in itertools.combinations_with_replacement(aset, n - 1):
        yield (0,) + rest


def work(args):
    mode, n, aset, Bs, ds, a = args
    out = {}
    for C in itertools.product(SIZES, repeat=n):
        for k in (1, 2, 3):
            for B in Bs:
                for d in (ds if mode != 'rbp' else (0,)):
                    r = explore(list(a), list(C), k, L, B, d, mode)
                    key = k
                    o = out.setdefault(key, dict(runs=0, leaves=0, m1=-1e9, m2=-1e9, r1=-1, r2=-1,
                                                 arg1=None, arg2=None, viol=[]))
                    o['runs'] += 1
                    o['leaves'] += r[4]
                    inst = (a, C, k, B, d)
                    if r[0] > o['m1']:
                        o['m1'] = r[0]
                    if r[1] > o['m2']:
                        o['m2'] = r[1]
                    if r[2] > o['r1']:
                        o['r1'] = r[2]; o['arg1'] = inst
                    if r[3] > o['r2']:
                        o['r2'] = r[3]; o['arg2'] = inst
                    if r[0] >= 0 or r[1] >= 0:
                        o['viol'].append((inst, r))
    return mode, n, out


def main():
    mode = sys.argv[1]
    nmax = int(sys.argv[2])
    tasks = []
    for n in range(2, nmax + 1):
        if n <= 5:
            aset = (0, 1, 2, 3, 4, 6)
            Bs = (0, 2, 3, 4, 6, 8)
            ds = (1, 2, 3, 4, 6)
        else:
            aset = (0, 2, 4, 6)
            Bs = (0, 2, 4, 8)
            ds = (1, 2, 4, 6)
        for a in arrivals(n, aset):
            tasks.append((mode, n, aset, Bs, ds, a))
    agg = {}
    t0 = time.time()
    with Pool(2) as p:
        for i, (m, n, out) in enumerate(p.imap_unordered(work, tasks, chunksize=1)):
            for k, o in out.items():
                g = agg.setdefault((n, k), dict(runs=0, leaves=0, m1=-1e9, m2=-1e9, r1=-1, r2=-1,
                                                arg1=None, arg2=None, viol=[]))
                g['runs'] += o['runs']; g['leaves'] += o['leaves']
                g['m1'] = max(g['m1'], o['m1']); g['m2'] = max(g['m2'], o['m2'])
                if o['r1'] > g['r1']:
                    g['r1'] = o['r1']; g['arg1'] = o['arg1']
                if o['r2'] > g['r2']:
                    g['r2'] = o['r2']; g['arg2'] = o['arg2']
                g['viol'] += o['viol'][:5]
            if i % 50 == 0:
                print(f'{i}/{len(tasks)} {time.time()-t0:.0f}s', flush=True)
    print('MODE', mode)
    for (n, k), g in sorted(agg.items()):
        print(n, k, 'runs', g['runs'], 'paths', g['leaves'], 'max(k*exc-bound)', g['m1'],
              'max(In-bound)', g['m2'], 'r1 %.4f' % g['r1'], g['arg1'], 'r2 %.4f' % g['r2'], g['arg2'],
              'viol', len(g['viol']), g['viol'][:2], flush=True)


if __name__ == '__main__':
    main()
