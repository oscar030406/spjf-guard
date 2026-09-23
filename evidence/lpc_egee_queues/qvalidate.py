"""Fit one effective capacity per walltime class on the earlier part, then test it.

Each (partition, queue) cell is simulated as its own work-conserving pool. Two
capacities are carried, both decided without the held-out part:

  fit  the inherited grid objective on arrivals that had submitted *and* completed
       before the cutoff;
  obs  the largest number of that cell's own jobs seen running at once before the
       cutoff, which is the structural reading of a queue concurrency ceiling.

`fit` is the primary; `obs` exists so that a corner solution of the objective is
visible rather than hidden.
"""
import sys
sys.dont_write_bytecode = True
from qcommon import *
from numba import njit
import heapq
from spjf_guard.sim.runner import Trace, simulate
from spjf_guard.sim.policy import fcfs, MICROS


@njit(cache=True)
def fast_fcfs(a, c, k):
    free = [np.int64(0) for _ in range(k)]
    w = np.zeros(len(a), np.int64)
    for i in range(len(a)):
        t = max(a[i], heapq.heappop(free))
        w[i] = t - a[i]
        heapq.heappush(free, t + c[i])
    return w


def fcfs_frame(d, k, service='c'):
    """FCFS waits, restarting the pool across the excluded incident."""
    w = np.zeros(len(d), np.int64)
    for seg in sorted(d.segment.unique()):
        m = d.segment.values == seg
        w[m] = fast_fcfs(d.a.values[m].astype(np.int64), d[service].values[m].astype(np.int64), k)
    return w


def max_concurrent(sub, lo, hi, until):
    """Largest number of this cell's jobs running at once before `until`, incident aside."""
    s = (sub.a + sub.wait).values
    e = s + sub.run.values
    keep = s < until
    s, e = s[keep], np.minimum(e[keep], until)
    if not len(s):
        return 1
    events = np.r_[s, e]
    delta = np.r_[np.ones(len(s), np.int64), -np.ones(len(e), np.int64)]
    order = np.lexsort((delta, events))
    events, delta = events[order], delta[order]
    uniq, at = np.unique(events, return_index=True)
    level = np.cumsum(np.add.reduceat(delta, at))
    outside = (uniq < lo) | (uniq >= hi)
    return int(max(1, level[outside].max() if outside.any() else level.max()))


def compare(rec, sim, hours):
    h = pd.DataFrame(dict(hour=hours, rec=rec, sim=sim)).groupby('hour').mean()
    out = {f'recorded_{key}': v for key, v in stats(rec).items()}
    out.update({f'sim_{key}': v for key, v in stats(sim).items()})
    with np.errstate(invalid='ignore'):
        out.update(hourly_pearson=float(h.rec.corr(h.sim)), n_hours=len(h),
                   median_abs_error=float(np.median(np.abs(sim - rec))))
    for q in ['mean', 'p50', 'p90', 'p99']:
        out[q + '_ratio'] = out['sim_' + q] / out['recorded_' + q] if out['recorded_' + q] else np.nan
    return out


def main():
    log, finish = log_start('qvalidate')
    d = load()
    cut = SPLIT_DAY * DAY
    audit = json.loads((HERE / 'qaudit.json').read_text())
    origin = audit['origin_submit']
    lo, hi = (np.array(OUTAGE) * DAY - origin).astype(int)
    end_of_log = int(d.a.max() + 1)
    caps = {v: {} for v in ['fit', 'obs']}
    waits = {v: np.zeros(len(d), np.int64) for v in caps}
    busy_threshold, busy_flag = {}, np.zeros(len(d), bool)
    rows, search, meta = [], [], {}
    for pool, queue, L in cells(d):
        key = f'{pool}|{queue}'
        ids = np.flatnonzero((d.pool.values == pool) & (d.queue.values == queue))
        p = d.iloc[ids]
        prefix = p[p.a < cut]
        visible = prefix.done.values < cut
        rec = prefix.wait.values[visible]
        if len(rec) == 0:
            log('NO CAPACITY FIT', key, QUEUE_NAME[queue],
                '- no arrival both submitted and completed before the cutoff; the cell is dropped')
            continue
        best = None
        for k in range(1, NOMINAL[pool] + 1):
            w = fcfs_frame(prefix, k)[visible]
            obj = (abs(np.log((w.mean() + 1) / (rec.mean() + 1)))
                   + abs(np.log((np.quantile(w, .9) + 1) / (np.quantile(rec, .9) + 1))))
            search.append(dict(pool=pool, queue=queue, k=k, objective=obj, n_fit=int(visible.sum()),
                               sim_mean=float(w.mean()), recorded_mean=float(rec.mean()),
                               sim_p90=float(np.quantile(w, .9)), recorded_p90=float(np.quantile(rec, .9))))
            if best is None or obj < best[0]:
                best = (obj, k)
        caps['fit'][key] = int(best[1])
        caps['obs'][key] = min(max_concurrent(prefix, lo, hi, cut), NOMINAL[pool])
        # Hours before the queue's own first arrival are not idle hours of that queue: it did
        # not exist yet. The busy threshold and the offered load both start when the cell does.
        born = int(p.a.min())
        counts = np.bincount((prefix.a.values // 3600).astype(int), minlength=SPLIT_DAY * 24)
        hour_start = np.arange(len(counts)) * 3600
        valid = ((hour_start < lo) | (hour_start >= hi)) & (hour_start >= born - born % 3600)
        busy_threshold[key] = float(max(1.0, np.quantile(counts[valid], .9))) if valid.any() else 1.0
        fit_span = max(1, cut - max(born, 0) - max(0, min(hi, cut) - max(lo, born)))
        test_span = max(1, end_of_log - max(cut, born))
        test_counts = pd.Series(p.a.values // 3600).map(pd.Series(p.a.values // 3600).value_counts())
        busy_flag[ids] = test_counts.values >= busy_threshold[key]
        meta[key] = dict(pool=pool, queue=queue, queue_name=QUEUE_NAME[queue], L=L,
                         n_fit_rows=int(visible.sum()), thin_fit=bool(len(rec) < MIN_FIT_ROWS),
                         busy_arrivals_per_hour=busy_threshold[key], first_arrival_day=float(born / DAY),
                         fit_span_days=fit_span / DAY, test_span_days=test_span / DAY,
                         fit_recorded_mean=float(rec.mean()), fit_recorded_p90=float(np.quantile(rec, .9)),
                         objective=float(best[0]))
        log('FROZEN', key, QUEUE_NAME[queue], 'L', L, '| k_fit', caps['fit'][key],
            '| k_obs', caps['obs'][key], 'of', NOMINAL[pool], '| fit rows', int(visible.sum()),
            '| busy arrivals/h', busy_threshold[key], '| THIN FIT' if meta[key]['thin_fit'] else '')
        for variant in caps:
            k = caps[variant][key]
            w = fcfs_frame(p, k)
            waits[variant][ids] = w
            for part, m, span in [('fit', (p.a.values < cut) & (p.done.values < cut), fit_span),
                                  ('test', p.a.values >= cut, test_span)]:
                if not m.any():
                    continue
                row = dict(pool=pool, queue=queue, queue_name=QUEUE_NAME[queue], L=L, variant=variant,
                           k=k, nominal=NOMINAL[pool], part=part, n=int(m.sum()),
                           n_fit_rows=meta[key]['n_fit_rows'], thin_fit=meta[key]['thin_fit'],
                           corner=bool(k == 1 or k == NOMINAL[pool]),
                           first_arrival_day=meta[key]['first_arrival_day'],
                           span_days=span / DAY, busy_arrivals_per_hour=busy_threshold[key],
                           offered_load=float(p.c.values[m].sum() / (k * span)),
                           **compare(p.wait.values[m].astype(float), w[m].astype(float),
                                     p.a.values[m] // 3600))
                rows.append(row)
                if part == 'test' and variant == 'fit':
                    log('HELD-OUT', key, json.dumps({q: round(row[q], 4) for q in
                                                     ['offered_load', 'recorded_mean', 'sim_mean',
                                                      'recorded_p90', 'sim_p90', 'recorded_p99', 'sim_p99',
                                                      'hourly_pearson']}))
            # The fast fitting recursion must agree exactly with the production kernel.
            for seg in sorted(p.segment.unique()):
                s = p[p.segment == seg]
                out = simulate(Trace.from_seconds(s.a, s.c, limit_s=L), fcfs(), k,
                               window=max(16, 1 << int(len(s)).bit_length()))
                assert np.array_equal(out.wait_us, fcfs_frame(s, k) * MICROS)
    log('FCFS EXACT AGREEMENT WITH THE PRODUCTION KERNEL on every cell and both capacities')

    pd.DataFrame(rows).to_csv(HERE / 'validation.csv', index=False)
    pd.DataFrame(search).to_csv(HERE / 'capacity_grid.csv', index=False)
    for variant in caps:
        np.save(HERE / f'fcfs_wait_{variant}.npy', waits[variant])
    np.save(HERE / 'busy.npy', busy_flag)
    dump('qcapacity.json', dict(k=caps, busy_arrivals_per_hour=busy_threshold, nominal=NOMINAL,
                                min_fit_rows=MIN_FIT_ROWS, meta=meta, split_seconds=cut,
                                split_utc=audit['split_utc'], primary='fit',
                                interpretation='k is an effective capacity for a queue treated as its own '
                                               'pool; the queues in fact shared their partition machines'))

    # Applicability, with each cell's own L in the theorem constant.
    app = []
    for period, base in [('all', np.ones(len(d), bool)), ('test', d.a.values >= cut)]:
        for pool, queue, L in cells(d):
            key = f'{pool}|{queue}'
            if key not in caps['fit']:
                continue
            m = base & (d.pool.values == pool) & (d.queue.values == queue)
            if not m.any():
                continue
            t = tails(d.c.values[m])
            mb = m & busy_flag
            for variant in caps:
                k = caps[variant][key]
                wf = waits[variant][m].astype(float)
                floor = (3 - 2 / k) * L
                app.append(dict(period=period, variant=variant, pool=pool, queue=queue,
                                queue_name=QUEUE_NAME[queue], n=int(m.sum()), n_busy=int(mb.sum()),
                                L=L, k=k, floor_seconds=floor, thin_fit=meta[key]['thin_fit'],
                                corner=bool(k == 1 or k == NOMINAL[pool]),
                                fcfs_p99=float(np.quantile(wf, .99)), fcfs_mean=float(wf.mean()),
                                fcfs_p99_busy=float(np.quantile(waits[variant][mb], .99)) if mb.any() else np.nan,
                                recorded_p99=float(np.quantile(d.wait.values[m], .99)),
                                recorded_p99_busy=float(np.quantile(d.wait.values[mb], .99)) if mb.any() else np.nan,
                                fcfs_p99_over_L=float(np.quantile(wf, .99) / L),
                                fcfs_p99_busy_over_L=float(np.quantile(waits[variant][mb], .99) / L) if mb.any() else np.nan,
                                recorded_p99_over_L=float(np.quantile(d.wait.values[m], .99) / L),
                                condition1_floor=bool(np.quantile(wf, .99) > floor),
                                condition1_3L=bool(np.quantile(wf, .99) >= 3 * L),
                                condition1_busy_3L=bool(mb.any() and np.quantile(waits[variant][mb], .99) >= 3 * L),
                                condition1_recorded_3L=bool(np.quantile(d.wait.values[m], .99) >= 3 * L),
                                condition2_proxy_25pct=bool(t['top1'] >= .25), **t))
    pd.DataFrame(app).to_csv(HERE / 'applicability.csv', index=False)
    log(pd.DataFrame(app).query("period=='test' and variant=='fit'")[
        ['pool', 'queue_name', 'n', 'L', 'k', 'corner', 'thin_fit', 'fcfs_p99', 'fcfs_p99_over_L',
         'condition1_3L', 'top1', 'condition2_proxy_25pct']].to_string(index=False))
    log(pd.DataFrame(app).query("period=='test' and variant=='obs'")[
        ['pool', 'queue_name', 'n', 'L', 'k', 'fcfs_p99', 'fcfs_p99_over_L', 'condition1_3L']].to_string(index=False))
    finish()


if __name__ == '__main__':
    main()
