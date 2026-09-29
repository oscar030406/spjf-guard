"""Per-queue audit of the sole authorised trace.

Same filter ledger as the previous study (verified against its retained count),
then everything is reported per walltime class: distribution, tail share,
recorded waits, and the number of that queue's own jobs running at once.
"""
import sys
sys.dont_write_bytecode = True
from qcommon import *
import gzip
import re


def step_levels(start, end):
    """The running-job step function: (breakpoints, level on each half-open interval)."""
    events = np.r_[np.asarray(start, np.int64), np.asarray(end, np.int64)]
    delta = np.r_[np.ones(len(start), np.int64), -np.ones(len(end), np.int64)]
    order = np.lexsort((delta, events))          # completions before starts at a tie
    events = events[order]
    delta = delta[order]
    uniq, at = np.unique(events, return_index=True)
    level = np.cumsum(np.add.reduceat(delta, at))
    return uniq, level


def concurrency(start, end, span, outage):
    """Time-weighted quantiles and the maximum of simultaneously running jobs.

    Time inside the excluded incident carries no weight; the level itself is
    computed from every retained job, so no artificial gap is introduced.
    """
    if not len(start):
        return dict(max_concurrent=0, busy_time_fraction=np.nan)
    uniq, level = step_levels(start, end)
    lo, hi = outage
    edges = np.unique(np.r_[uniq, span[0], span[1], lo, hi])
    edges = edges[(edges >= span[0]) & (edges <= span[1])]
    j = np.searchsorted(uniq, edges[:-1], side='right') - 1
    lv = np.where(j >= 0, level[np.maximum(j, 0)], 0).astype(np.int64)
    width = np.diff(edges).astype(np.float64)
    valid = ~((edges[:-1] >= lo) & (edges[:-1] < hi))
    lv, width = lv[valid], width[valid]
    order = np.argsort(lv, kind='stable')
    lv, width = lv[order], width[order]
    cum = np.cumsum(width)
    total = cum[-1]
    out = dict(max_concurrent=int(level.max()))
    for q in [.5, .9, .99, .999]:
        out[f'concurrent_p{q * 100:g}'] = float(lv[np.searchsorted(cum, q * total, side='left')])
    out['mean_concurrent'] = float(np.sum(lv * width) / total)
    out['busy_time_fraction'] = float(width[lv > 0].sum() / total)
    return out


def main():
    log, finish = log_start('qaudit')
    dump('qprotocol.json', protocol())
    with gzip.open(RAW, 'rt') as f:
        header = ''.join(line for line in f if line.startswith(';'))
    (HERE / 'swf_header.txt').write_text(header, encoding='utf-8')
    d = pd.read_csv(RAW, sep=r'\s+', comment=';', header=None, names=COLS)
    d['input_index'] = np.arange(len(d))
    origin = int(d.submit.min())
    d['a'] = d.submit - origin
    d['done'] = d.a + d.wait + d.run
    d['L'] = d.queue.map(QUEUE_L)
    d.loc[(d.part == 3) & (d.queue == 2), 'L'] = 5400        # documented CE2 short limit
    audit = dict(raw_n=len(d), origin_submit=origin, span_days=float(d.a.max() / DAY),
                 status_raw=d.status.value_counts().to_dict())
    filters = []
    for name, ok in [('known status 0/1/5', d.status.isin([0, 1, 5])),
                     ('positive runtime', d.run > 0),
                     ('nonnegative wait and submit', (d.wait >= 0) & (d.submit >= 0)),
                     ('one allocated processor', d.nproc == 1),
                     ('known queue/partition', d.L.notna() & d.part.isin([1, 2, 3]))]:
        before = len(d)
        d = d.loc[ok.loc[d.index]].copy()
        filters.append(dict(filter=name, before=before, removed=before - len(d), after=len(d)))
    lo, hi = np.array(OUTAGE) * DAY - origin
    before = len(d)
    submit_out = (d.a >= lo) & (d.a < hi)
    intersects = (d.a < hi) & (d.done > lo)
    d = d.loc[~(submit_out | intersects)].copy()
    filters.append(dict(filter='arrival or observed lifetime intersects original SWF outage [138d,153d)',
                        before=before, removed=before - len(d), after=len(d)))
    assert len(d) == 206222, f'retained count {len(d)} differs from the previous audit 206222'
    audit['filters'] = filters
    audit['retained_matches_previous_study'] = True
    d['c'] = np.minimum(d.run, d.L).astype('int64')
    d['pool'] = d.part.map(POOL_OF_PART)
    d['segment'] = (d.a >= hi).astype(int)
    d = d.sort_values(['a', 'input_index'], kind='stable').reset_index(drop=True)
    d.to_csv(HERE / 'jobs.csv', index=False)

    span = (0, int(d.a.max() + 1))
    start = (d.a + d.wait).values
    end = start + d.run.values
    cut = SPLIT_DAY * DAY
    rows = []
    for pool in ['all', EARLY_POOL, *NOMINAL]:
        mp = np.ones(len(d), bool) if pool == 'all' else (d.pool.values == pool)
        for queue in ['all', *sorted(d.queue.unique())]:
            m = mp if queue == 'all' else mp & (d.queue.values == queue)
            if not m.sum():
                log('EMPTY CELL', pool, QUEUE_NAME[queue], '- this queue never ran on this partition')
                continue
            s = d[m]
            w = stats(s.wait)
            row = dict(pool=pool, queue=queue,
                       queue_name='all' if queue == 'all' else QUEUE_NAME[queue],
                       n=int(m.sum()), n_test=int((m & (d.a.values >= cut)).sum()),
                       L=int(s.L.max()), L_min=int(s.L.min()),
                       wait_mean=w['mean'], wait_p50=w['p50'], wait_p90=w['p90'], wait_p99=w['p99'],
                       wait_max=w['max'], recorded_p99_over_L=w['p99'] / float(s.L.max()),
                       **tails(s.c),
                       raw_top1=tails(s.run)['top1'], raw_top5=tails(s.run)['top5'],
                       exceeds_L=int((s.run > s.L).sum()),
                       mean_c=float(s.c.mean()), p99_c=float(np.quantile(s.c, .99)),
                       **concurrency(start[m], end[m], span, (lo, hi)))
            rows.append(row)
            log('CELL', pool, row['queue_name'], 'n', row['n'], 'L', row['L'],
                'wait p99', round(row['wait_p99'], 1), 'top1', round(row['top1'], 4),
                'max concurrent', row['max_concurrent'])
    audit_table = pd.DataFrame(rows)
    audit_table.to_csv(HERE / 'queue_audit.csv', index=False)

    # Did the queues share machines? If each queue owned nodes, the per-queue running
    # maxima could not sum past the partition's CPU count. They do, by a wide margin.
    sharing = []
    for pool, nom in NOMINAL.items():
        p = audit_table[(audit_table.pool == pool) & (audit_table.queue != 'all')]
        sharing.append(dict(pool=pool, nominal_cpus=nom,
                            pool_max_concurrent=int(audit_table.query(
                                "pool==@pool and queue=='all'").max_concurrent.iloc[0]),
                            sum_of_queue_maxima=int(p.max_concurrent.sum()),
                            queues_share_machines=bool(p.max_concurrent.sum() >
                                                       audit_table.query("pool==@pool and queue=='all'").max_concurrent.iloc[0])))
    audit['sharing'] = sharing
    for row in sharing:
        log('SHARING', json.dumps(row))
    spans = []
    for part, pool in POOL_OF_PART.items():
        s = d[d.part == part]
        spans.append(dict(part=int(part), pool=pool, n=len(s), first_day=float(s.a.min() / DAY),
                          last_day=float(s.a.max() / DAY), n_test=int((s.a >= cut).sum()),
                          n_fit_visible=int(((s.a < cut) & (s.done < cut)).sum()),
                          max_concurrent=concurrency(start[d.part.values == part], end[d.part.values == part],
                                                     span, (lo, hi))['max_concurrent']))
    audit['partition_spans'] = spans
    for row in spans:
        log('PARTITION', json.dumps(row))
    epoch = int(re.search(r'UnixStartTime:\s*(\d+)', header).group(1))
    audit['calendar_epoch'] = epoch
    audit['split_utc'] = pd.Timestamp(epoch + origin + cut, unit='s', tz='UTC').isoformat()
    audit['header_partitions'] = 'One small partition, later replaced by two disjoint partitions (SWF header)'
    audit['header_queues'] = 'Queues enforce a runtime limit on the jobs that populate them (SWF header)'
    dump('qaudit.json', audit)
    log(audit_table[['pool', 'queue_name', 'n', 'L', 'wait_p99', 'recorded_p99_over_L',
                     'top1', 'top5', 'max_concurrent', 'concurrent_p99']].to_string(index=False))
    finish()


if __name__ == '__main__':
    main()
