"""Random + hill-climbing search on larger bursty instances (deterministic adversary)."""
import sys, random, time
from sim import run, fcfs
from core import bounds

L = 12


def score(inst, k, mode):
    arr, C, dl, pr, B, d, bud = inst
    dl2 = [None if (mode == 'rbp' and x < 0) else max(x, 0) for x in dl]
    st, In = run(arr, C, k, B, dl2, pr, mode, bud)
    sf = fcfs(arr, C, k)
    kWb, Inb = bounds(mode, k, L, B, d)
    r1 = max(k * (st[j] - sf[j]) / kWb for j in range(len(arr)))
    r2 = max((In[j] / Inb for j in range(len(arr)) if In[j] > 0), default=0.0)
    return r1, r2


def rand_inst(n, rng):
    d = rng.choice([1, 3, 6, 12, 24])
    B = rng.choice([0, 1, 6, 12, 24, 48])
    arr = sorted(rng.choice([0, 0, 0, rng.randrange(0, 60)]) for _ in range(n))
    C = [rng.choice([1, 1, 2, 3, L // 2, L, L]) for _ in range(n)]
    dl = [rng.choice([0, d, rng.randrange(0, d + 1), -1]) for _ in range(n)]
    pr = [rng.random() for _ in range(n)]
    bud = rng.choice(['const', 'max'])
    return [arr, C, dl, pr, B, d, bud]


def mutate(inst, rng):
    arr, C, dl, pr, B, d, bud = [list(x) if isinstance(x, list) else x for x in inst]
    n = len(arr)
    for _ in range(rng.randint(1, 3)):
        j = rng.randrange(n)
        w = rng.randrange(6)
        if w == 0:
            arr[j] = max(0, arr[j] + rng.choice([-3, -1, 1, 3]))
        elif w == 1:
            C[j] = rng.randint(1, L)
        elif w == 2:
            dl[j] = rng.choice([0, d, rng.randrange(0, d + 1), -1])
        elif w == 3:
            pr[j] = rng.random()
        elif w == 4:
            B = max(0, B + rng.choice([-2, -1, 1, 2]))
        else:
            i2 = rng.randrange(n); pr[j], pr[i2] = pr[i2], pr[j]
    # keep rank order = arrival order: sort jobs by arrival, stable
    idx = sorted(range(n), key=lambda x: (arr[x], x))
    arr = [arr[x] for x in idx]; C = [C[x] for x in idx]; dl = [dl[x] for x in idx]; pr = [pr[x] for x in idx]
    return [arr, C, dl, pr, B, d, bud]


def main():
    mode = sys.argv[1]; k = int(sys.argv[2]); secs = float(sys.argv[3]); seed = int(sys.argv[4])
    rng = random.Random(seed)
    best = {0: (-1, None), 1: (-1, None)}
    t0 = time.time(); evals = 0; restarts = 0; viol = []
    while time.time() - t0 < secs:
        restarts += 1
        n = rng.randint(8, 40)
        cur = rand_inst(n, rng)
        obj = rng.randrange(2)
        cs = score(cur, k, mode); evals += 1
        for step in range(400):
            cand = mutate(cur, rng)
            s = score(cand, k, mode); evals += 1
            if s[0] >= 1 or s[1] >= 1:
                viol.append((cand, s))
            if s[obj] >= cs[obj]:
                cur, cs = cand, s
        for o in (0, 1):
            if cs[o] > best[o][0]:
                best[o] = (cs[o], cur)
    print(mode, k, 'restarts', restarts, 'evals', evals, 'viol', len(viol))
    for o in (0, 1):
        r, inst = best[o]
        print('  best', ['W', 'In'][o], '%.4f' % r, 'n', len(inst[0]), 'B', inst[4], 'd', inst[5], inst[6])
    if viol:
        print('  VIOL', viol[0])


if __name__ == '__main__':
    main()
