"""Independent attacks on the instance-dependent Lambda constants."""
import random

import numpy as np

import sim


def hdr(s):
    print('\n' + '=' * 72)
    print(s)
    print('=' * 72)


def topsum(values, count):
    if count <= 0:
        return 0
    return sum(sorted(values, reverse=True)[:count])


def lam_arrived(a, x, t, count):
    return topsum([x[j] for j in range(len(a)) if a[j] <= t], count)


def lam_below(x, i, count):
    return topsum(x[:i], count)


def lam_above(a, x, i, t, count):
    return topsum([x[j] for j in range(i + 1, len(a)) if a[j] <= t], count)


def unfinished_times(a, x, starts):
    times = set(a)
    for j, st in enumerate(starts):
        times.add(st)
        times.add(st + x[j])
    return sorted(times)


def random_checks():
    hdr('[A] random T3 checks, arrivals, ties, equal sizes, k=1..4')
    rng = random.Random(20260921)
    gap_checks = gap_bad = 0
    job_checks = t32_bad = t33_bad = t34_bad = 0
    policies = [sim.fcfs, sim.sjf, sim.sjf_advtie, sim.ljf, sim.lifo]
    for it in range(3500):
        k = rng.randint(1, 4)
        n = rng.randint(2, 10)
        a = sorted(rng.choice([0, 0, 0, 1, 2, 3, 5, 8]) for _ in range(n))
        if it % 7 == 0:
            z = rng.randint(1, 8)
            x = [z] * n
        else:
            x = [rng.randint(1, 9) for _ in range(n)]
        rf = sim.run_full(k, a, x, sim.fcfs)
        runs = [sim.run_full(k, a, x, p) for p in policies]
        runs.append(sim.run_full(k, a, x, sim.make_nonrank(it)))
        B = rng.randint(0, 3 * max(x))
        rg = sim.run_full(k, a, x,
                          sim.make_guard(sim.make_nonrank(it + 19),
                                         sim.const_budget(B)))
        runs.append(rg)

        for p in range(0, len(runs), 2):
            r1 = runs[p]
            r2 = runs[(p + 1) % len(runs)]
            ts = sorted(set(unfinished_times(a, x, r1['s']) +
                            unfinished_times(a, x, r2['s'])))
            for t in ts:
                d = abs(sim.unfinished(a, x, r1['s'], t) -
                        sim.unfinished(a, x, r2['s'], t))
                la = lam_arrived(a, x, t, k - 1)
                gap_checks += 1
                gap_bad += d > la

        for rp in runs:
            for i in range(n):
                lhs = k * (rp['W'][i] - rf['W'][i])
                rhs2 = (rp['In'][i] - rp['Out'][i]
                        + lam_arrived(a, x, a[i], k - 1)
                        + lam_below(x, i, k - 1))
                job_checks += 1
                t32_bad += lhs > rhs2

        for i in range(n):
            lg = lam_above(a, x, i, rg['s'][i], k)
            if rg['In'][i] > 0:
                t33_bad += not (rg['In'][i] < B + lg)
            rhs4 = (B + lg + lam_arrived(a, x, a[i], k - 1)
                    + lam_below(x, i, k - 1))
            strict_required = rg['In'][i] > 0
            t34_bad += lhs_violation(k, rg, rf, i, rhs4, strict_required)

    print(f'T3-1 time-checks {gap_checks}, violations {gap_bad}')
    print(f'T3-2 job-checks {job_checks}, violations {t32_bad}')
    print(f'T3-3 overtaker-case violations {t33_bad}')
    print(f'T3-4 violations {t34_bad}')


def lhs_violation(k, rp, rf, i, rhs, strict_required):
    lhs = k * (rp['W'][i] - rf['W'][i])
    return lhs >= rhs if strict_required else lhs > rhs


def exhaustive_gap():
    hdr('[B] T3-1 over every enumerated work-conserving schedule pair')
    rng = random.Random(104)
    checks = bad = pairs = 0
    for _ in range(180):
        k = rng.randint(1, 3)
        n = rng.randint(2, 5)
        a = sorted(rng.choice([0, 0, 1, 2, 3]) for _ in range(n))
        x = [rng.choice([1, 1, 2, 3, 4]) for _ in range(n)]
        schedules = sim.enumerate_schedules(k, a, x, cap=500)
        for p in range(len(schedules)):
            for q in range(p, len(schedules)):
                s1, _ = schedules[p]
                s2, _ = schedules[q]
                pairs += 1
                ts = sorted(set(unfinished_times(a, x, s1) +
                                unfinished_times(a, x, s2)))
                for t in ts:
                    d = abs(sim.unfinished(a, x, s1, t) -
                            sim.unfinished(a, x, s2, t))
                    checks += 1
                    bad += d > lam_arrived(a, x, t, k - 1)
    print(f'schedule-pairs {pairs}, time-checks {checks}, violations {bad}')


def pareto_ratios():
    hdr('[C] truncated Pareto: ex-post sample maximum vs fixed support bound')
    rng = np.random.default_rng(73621)
    alpha = 1.5
    xmin = 1.0
    cap = 1000.0
    jobs = 200
    reps = 5000
    u = rng.random((reps, jobs))
    sizes = np.minimum(cap, xmin * np.power(1.0 - u, -1.0 / alpha))
    sample_max = sizes.max(axis=1)
    print(f'Pareto alpha={alpha}, xmin={xmin}, hard cap={cap}, '
          f'{jobs} jobs, {reps} samples, seed=73621')
    print(' k   E[Lambda/((k-1)*sample_max)]   E[Lambda/((k-1)*cap)]')
    for k in (4, 8, 16):
        top = np.partition(sizes, jobs - (k - 1), axis=1)[:, -(k - 1):].sum(axis=1)
        ex_post = np.mean(top / ((k - 1) * sample_max))
        fixed = np.mean(top / ((k - 1) * cap))
        print(f'{k:2d}                 {ex_post:.4f}                       {fixed:.4f}')
    print('The first column is comparable to the earlier script, which sets L')
    print('to each finite sample maximum.  The second uses the known truncation')
    print('cap, matching a deployed timeout bound fixed before the sample.')


if __name__ == '__main__':
    random_checks()
    exhaustive_gap()
    pareto_ratios()
