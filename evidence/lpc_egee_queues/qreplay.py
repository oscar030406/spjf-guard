"""Counterfactual replays inside each walltime class, at that class's own L.

Every policy sees the same arrivals and the same service times; only the dispatch
order differs. Before the cutoff every policy runs FCFS, so the queue state at the
switch is identical. Guards are stated against the cell's own queue limit, which
is the whole difference from the pooled study.
"""
import sys
sys.dont_write_bytecode = True
from qcommon import *
from numba import njit
from spjf_guard.sim.runner import Trace, simulate
from spjf_guard.sim.policy import fcfs, spjf, fixed, guard, MICROS
from spjf_guard.sim.bounds import guard_upper_bound, assert_per_job_bounds, in_out, identity_residual


def policies(k, L):
    out = [fcfs(), spjf('oracle', 'SJF'), spjf('spjf_e', 'SPJF-E')]
    for g in PROMISES:
        out.append(fixed(g * L, k, L, 'spjf_e', name=f'Constant-{g:g}L'))
        out.append(guard(g * L, k, L, k * L * (.5 if g == 10 else .25), .75 if g == 10 else .5,
                         'spjf_e', name=f'Age-{g:g}L'))
    return out


POLICY_NAMES = [p.name for p in policies(2, 900.)]


@njit(cache=True)
def bootstrap_stats(sorted_w, sorted_week, draws, week_n, week_sum):
    """Exact numpy-style linear 99th percentile and mean of the expanded sample."""
    out = np.empty((len(draws), 2), np.float64)
    for b in range(len(draws)):
        mult = draws[b]
        n = 0
        total = 0.
        for h in range(len(mult)):
            n += mult[h] * week_n[h]
            total += mult[h] * week_sum[h]
        if n == 0:
            out[b, 0] = np.nan
            out[b, 1] = np.nan
            continue
        pos = .99 * (n - 1)
        low = int(np.floor(pos))
        high = int(np.ceil(pos))
        cum = 0
        vlo = 0.
        vhi = 0.
        got = False
        for i in range(len(sorted_w)):
            cum += mult[sorted_week[i]]
            if cum > low and not got:
                vlo = sorted_w[i]
                got = True
            if cum > high:
                vhi = sorted_w[i]
                break
        out[b, 0] = vlo + (pos - low) * (vhi - vlo)
        out[b, 1] = total / n
    return out


def ci(values):
    valid = np.isfinite(values)
    if not valid.any():
        return np.nan, np.nan, 0
    lo, hi = np.quantile(values[valid], [.025, .975])
    return float(lo), float(hi), int(valid.sum())


def main():
    log, finish = log_start('qreplay')
    d = load()
    cut = SPLIT_DAY * DAY
    caps = json.loads((HERE / 'qcapacity.json').read_text())
    pred = np.load(HERE / 'predictions.npz')
    busy_flag = np.load(HERE / 'busy.npy')
    fcfs_reference = np.load(HERE / 'fcfs_wait_fit.npy')
    n = len(d)
    test = d.a.values >= cut
    scores = {'spjf_e': pred['spjf_e'].copy(), 'oracle': d.c.values.astype(float)}
    for key in scores:                       # every policy runs FCFS before the cutoff
        scores[key][~test] = np.arange(n)[~test] - n - 1
    waits = {name: np.zeros(n, np.int64) for name in POLICY_NAMES}
    covered = np.zeros(n, bool)
    checks, params, dispatch = [], [], []
    for pool, queue, L in cells(d):
        key = f'{pool}|{queue}'
        if key not in caps['k']['fit']:
            continue
        k = caps['k']['fit'][key]
        for segment in [0, 1]:
            ids = np.flatnonzero((d.pool.values == pool) & (d.queue.values == queue)
                                 & (d.segment.values == segment))
            if not len(ids):
                continue
            covered[ids] = True
            sub = d.iloc[ids]
            trace = Trace.from_seconds(sub.a, sub.c, {key2: v[ids] for key2, v in scores.items()},
                                       limit_s=L)
            window = max(16, 1 << int(len(sub)).bit_length())
            m = sub.a.values >= cut
            f = None
            for pol in policies(k, L):
                r = simulate(trace, pol, k, window=window)
                waits[pol.name][ids] = r.wait_us
                if pol.name == 'FCFS':
                    f = r
                params.append(dict(pool=pool, queue=queue, queue_name=QUEUE_NAME[queue], segment=segment,
                                   policy=pol.name, k=k, L=L, b0_s=pol.b0_us / MICROS,
                                   bmax_s=pol.bmax_us / MICROS, eta=pol.eta_k / k))
                dispatch.append(dict(pool=pool, queue=queue, queue_name=QUEUE_NAME[queue],
                                     segment=segment, policy=pol.name, n_dispatch=r.n_dispatch,
                                     n_forced=r.n_forced, fired_fraction=r.fired_fraction,
                                     fired_fraction_queue_weighted=r.fired_fraction_queue_weighted,
                                     scope='whole segment, FCFS prefix included'))
                if pol.wrapper == 'none':
                    continue
                checked = assert_per_job_bounds(r, f.wait_us, pol, k, L)
                excess = (r.wait_us - f.wait_us) / MICROS
                allowance = guard_upper_bound(f.wait_us, pol, k, L) - f.wait_s
                wi, wo = in_out(trace.service_us, r.dispatch_order)
                residual = identity_residual(r.wait_us, f.wait_us, wi, wo, k)
                assert np.all(np.abs(residual) <= 2 * (k - 1) * L * MICROS)
                checks.append(dict(pool=pool, queue=queue, queue_name=QUEUE_NAME[queue], segment=segment,
                                   policy=pol.name, k=k, L=L, checked=checked, test_checked=int(m.sum()),
                                   violations=int((excess > allowance).sum()),
                                   worst_ratio=float(np.max(excess / allowance)),
                                   test_worst_ratio=float(np.max(excess[m] / allowance[m])) if m.any() else 0.,
                                   max_excess_s=float(excess.max()),
                                   theoretical_max_s=float(allowance.max()),
                                   identity_worst_ratio=float(np.max(np.abs(residual)) / (2 * (k - 1) * L * MICROS))
                                   if k > 1 else 0.))
            log('REPLAY', key, QUEUE_NAME[queue], 'segment', segment, 'k', k, 'L', L, 'jobs', len(ids))
    replayable = d.pool.isin(NOMINAL).values & (d.queue.values != 6)
    assert covered[replayable].all(), 'every job of a fitted cell must be replayed'
    log('REPLAYED', int(covered.sum()), 'of', len(d), 'retained jobs; the rest are the early clrglop195 '
        'partition and the batch queue, neither of which has a capacity fit')
    assert np.array_equal(waits['FCFS'][covered], fcfs_reference[covered] * MICROS)
    log('FCFS REPLAY MATCHES THE VALIDATED FITTED-CAPACITY WAITS on', int(covered.sum()), 'jobs')

    ids = np.flatnonzero(test & covered)
    td = d.iloc[ids].copy()
    td['busy'] = busy_flag[ids]
    td['week'] = ((td.a - cut) // (7 * DAY)).astype(int)
    week = td.week.values
    nw = int(week.max() + 1)
    rng = np.random.default_rng(BOOT_SEED)
    draws = rng.multinomial(nw, np.full(nw, 1 / nw), size=BOOT_N).astype(np.int64)
    v = np.array([0., 1., 2., 6., 10.])
    wk = np.array([0, 0, 1, 1, 2])
    dr = np.array([[1, 1, 1], [2, 0, 1], [0, 0, 3]])
    chk = bootstrap_stats(v, wk, dr, np.bincount(wk), np.bincount(wk, weights=v))
    for i, mult in enumerate(dr):
        expanded = np.repeat(v, mult[wk])
        assert np.allclose(chk[i], [np.quantile(expanded, .99), expanded.mean()])
    log('WEIGHTED-QUANTILE BOOTSTRAP CHECKED against explicitly duplicated weeks')

    rows = []
    groups = [(QUEUE_NAME[q], QUEUE_NAME[q], td.queue.values == q)
              for q in sorted(td.queue.unique())]
    groups += [(f'{pool}|{QUEUE_NAME[q]}', QUEUE_NAME[q],
                (td.pool.values == pool) & (td.queue.values == q))
               for pool, q, _ in cells(d) if ((td.pool.values == pool) & (td.queue.values == q)).any()]
    for scope_name, queue_name, gmask in groups:
        if gmask.sum() < 50:
            continue
        baseline = waits['FCFS'][ids] / MICROS
        oracle = waits['SJF'][ids] / MICROS
        boot = {}
        block = []
        for name in POLICY_NAMES:
            w = waits[name][ids] / MICROS
            excess = w - baseline
            busy = gmask & td.busy.values
            row = dict(scope=scope_name, queue_name=queue_name, policy=name, n=int(gmask.sum()),
                       n_busy=int(busy.sum()), mean=float(w[gmask].mean()),
                       p99=float(np.quantile(w[gmask], .99)),
                       p99_busy=float(np.quantile(w[busy], .99)) if busy.any() else np.nan,
                       max_excess=float(excess[gmask].max()),
                       harm=float(excess[gmask & (baseline <= 1)].max()) if (gmask & (baseline <= 1)).any() else 0.,
                       heavy_p99=float(np.quantile(w[gmask & pred['heavy'][ids]], .99))
                       if (gmask & pred['heavy'][ids]).any() else np.nan)
            for scope, mask in [('overall', gmask), ('busy', busy)]:
                if not mask.any():
                    continue
                order = np.argsort(w[mask], kind='stable')
                sw = w[mask][order]
                sh = week[mask][order]
                wn = np.bincount(sh, minlength=nw)
                ws = np.bincount(sh, weights=sw, minlength=nw)
                bs = bootstrap_stats(sw, sh, draws, wn, ws)
                boot[(name, scope)] = bs
                for j, metric in [(0, 'p99'), (1, 'mean')]:
                    lo, hi, _ = ci(bs[:, j])
                    row[f'{scope}_{metric}_lo'] = lo
                    row[f'{scope}_{metric}_hi'] = hi
            for metric in ['mean', 'p99', 'p99_busy']:
                mask = (gmask & td.busy.values) if metric == 'p99_busy' else gmask
                if not mask.any():
                    continue
                fun = np.mean if metric == 'mean' else (lambda x: np.quantile(x, .99))
                b = fun(baseline[mask])
                o = fun(oracle[mask])
                row[f'{metric}_reduction'] = float(1 - row[metric] / b) if b else np.nan
                row[f'{metric}_gap'] = float((b - row[metric]) / (b - o)) if b - o > 0 else np.nan
            block.append(row)
        for row in block:
            name = row['policy']
            for metric, scope, j in [('mean', 'overall', 1), ('p99', 'overall', 0), ('p99_busy', 'busy', 0)]:
                if (name, scope) not in boot:
                    continue
                b = boot[('FCFS', scope)][:, j]
                o = boot[('SJF', scope)][:, j]
                x = boot[(name, scope)][:, j]
                den = b - o
                gap = np.divide(b - x, den, out=np.full_like(b, np.nan), where=den > 0)
                red = np.divide(b - x, b, out=np.full_like(b, np.nan), where=b > 0)
                for tag, arr in [('gap', gap), ('reduction', red)]:
                    lo, hi, valid = ci(arr)
                    row[f'{metric}_{tag}_lo'] = lo
                    row[f'{metric}_{tag}_hi'] = hi
                    row[f'{metric}_{tag}_valid'] = valid
        rows.extend(block)
        log('BOOTSTRAP', scope_name, nw, 'week blocks,', BOOT_N, 'draws')
    out = pd.DataFrame(rows)
    out.to_csv(HERE / 'policy_metrics.csv', index=False)
    pd.DataFrame(checks).to_csv(HERE / 'bound_checks.csv', index=False)
    pd.DataFrame(params).drop_duplicates(['pool', 'queue', 'policy']).to_csv(HERE / 'policy_parameters.csv', index=False)
    pd.DataFrame(dispatch).to_csv(HERE / 'guard_dispatches.csv', index=False)
    td[['job', 'a', 'pool', 'queue', 'L', 'week', 'busy']].to_csv(HERE / 'test_jobs.csv', index=False)
    np.savez_compressed(HERE / 'policy_waits_us.npz', **{name: v[ids] for name, v in waits.items()})
    dump('bootstrap.json', dict(n_weeks=nw, replicates=BOOT_N, seed=BOOT_SEED,
                                method='paired resampling of arrival-week blocks, one multiplicity vector shared '
                                       'by every queue and policy; exact expanded-sample linear quantiles',
                                limits='conditional on the trace, the fitted capacity and the frozen model'))
    log(out.query("scope=='test'")[['policy', 'mean', 'p99', 'p99_busy', 'p99_busy_gap',
                                    'max_excess', 'harm']].to_string(index=False))
    log('BOUND CHECKS', sum(x['checked'] for x in checks), 'violations',
        sum(x['violations'] for x in checks), 'worst ratio', max(x['worst_ratio'] for x in checks))
    finish()


if __name__ == '__main__':
    main()
