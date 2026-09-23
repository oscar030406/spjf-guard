"""Render every table of REPORT.md from the CSVs, so no number is transcribed by hand."""
import sys
sys.dont_write_bytecode = True
from qcommon import *


def md(frame, floats=2):
    f = frame.copy()
    for col in f.columns:
        if f[col].dtype.kind == 'f':
            f[col] = f[col].map(lambda x: '' if pd.isna(x) else f'{x:,.{floats}f}'.rstrip('0').rstrip('.')
                                if abs(x) < 1e6 else f'{x:,.0f}')
    head = '| ' + ' | '.join(map(str, f.columns)) + ' |'
    rule = '| ' + ' | '.join('---' for _ in f.columns) + ' |'
    body = ['| ' + ' | '.join(map(str, row)) + ' |' for row in f.values]
    return '\n'.join([head, rule, *body])


def main():
    log, finish = log_start('qreport')
    d = load()
    cut = SPLIT_DAY * DAY
    test = d.a.values >= cut
    audit = json.loads((HERE / 'qaudit.json').read_text())
    caps = json.loads((HERE / 'qcapacity.json').read_text())
    qa = pd.read_csv(HERE / 'queue_audit.csv')
    app = pd.read_csv(HERE / 'applicability.csv')
    val = pd.read_csv(HERE / 'validation.csv')
    pm = pd.read_csv(HERE / 'policy_metrics.csv')
    pr = pd.read_csv(HERE / 'prediction_metrics.csv')
    bc = pd.read_csv(HERE / 'bound_checks.csv')
    gd = pd.read_csv(HERE / 'guard_dispatches.csv')
    out = []

    out.append('## Partitions\n\n' + md(pd.DataFrame(audit['partition_spans']), 2))
    out.append('## Queues shared the machines of their partition\n\n' + md(pd.DataFrame(audit['sharing']), 2))

    a = qa[qa.pool == 'all'].copy()
    a['p99/L'] = a.recorded_p99_over_L
    out.append('## Per-queue audit, all retained arrivals\n\n' + md(a[[
        'queue_name', 'n', 'n_test', 'L', 'wait_p50', 'wait_p90', 'wait_p99', 'p99/L',
        'top1', 'top5', 'raw_top1', 'mean_c', 'max_concurrent', 'concurrent_p99', 'concurrent_p99.9']], 3))
    out.append('## Per-queue audit, by partition\n\n' + md(qa[qa.pool.isin(NOMINAL) & (qa.queue != 'all')][[
        'pool', 'queue_name', 'n', 'n_test', 'L', 'wait_p90', 'wait_p99', 'recorded_p99_over_L',
        'top1', 'top5', 'max_concurrent', 'concurrent_p99']], 3))

    # Queue-level pooling of the per-cell FCFS counterfactual.
    waits = {v: np.load(HERE / f'fcfs_wait_{v}.npy') for v in ['fit', 'obs']}
    busy = np.load(HERE / 'busy.npy')
    fitted = set(caps['k']['fit'])
    rows = []
    for variant in waits:
        for queue in sorted(d.queue.unique()):
            m = test & (d.queue.values == queue) & np.array(
                [f'{p}|{q}' in fitted for p, q in zip(d.pool.values, d.queue.values)])
            if m.sum() < 50:
                continue
            w = waits[variant][m].astype(float)
            L = int(d.L.values[m].max())
            ks = sorted({caps['k'][variant][f'{p}|{queue}'] for p in d.pool.values[m]})
            t = tails(d.c.values[m])
            mb = m & busy
            rows.append(dict(variant=variant, queue_name=QUEUE_NAME[queue], n=int(m.sum()), L=L,
                             k=','.join(map(str, ks)),
                             recorded_p99=float(np.quantile(d.wait.values[m], .99)),
                             recorded_p99_over_L=float(np.quantile(d.wait.values[m], .99) / L),
                             fcfs_p99=float(np.quantile(w, .99)), fcfs_p99_over_L=float(np.quantile(w, .99) / L),
                             fcfs_p99_busy_over_L=float(np.quantile(waits[variant][mb], .99) / L),
                             condition1_3L=bool(np.quantile(w, .99) >= 3 * L),
                             top1=t['top1'], top5=t['top5'],
                             condition2_proxy_25pct=bool(t['top1'] >= .25)))
    out.append('## Applicability per walltime class, held-out part, both partitions pooled\n\n'
               + md(pd.DataFrame(rows), 3))
    out.append('## Applicability per cell, held-out part\n\n' + md(app.query("period=='test'")[[
        'variant', 'pool', 'queue_name', 'n', 'n_busy', 'L', 'k', 'corner', 'thin_fit', 'floor_seconds',
        'fcfs_p99', 'fcfs_p99_over_L', 'fcfs_p99_busy_over_L', 'recorded_p99_over_L',
        'condition1_floor', 'condition1_3L', 'condition1_recorded_3L', 'top1',
        'condition2_proxy_25pct']], 3))

    out.append('## Capacity fit and held-out wait profile, primary variant\n\n' + md(val.query(
        "variant=='fit'")[['pool', 'queue_name', 'L', 'k', 'nominal', 'part', 'n', 'n_fit_rows', 'thin_fit',
                           'corner', 'offered_load', 'recorded_mean', 'sim_mean', 'recorded_p90', 'sim_p90',
                           'recorded_p99', 'sim_p99', 'hourly_pearson']], 3))
    out.append('## The same, at the observed concurrency ceiling\n\n' + md(val.query(
        "variant=='obs' and part=='test'")[['pool', 'queue_name', 'L', 'k', 'offered_load', 'recorded_mean',
                                            'sim_mean', 'recorded_p99', 'sim_p99', 'hourly_pearson']], 3))

    out.append('## Predictor, held-out part\n\n' + md(pr[pr.pool == 'all'][[
        'queue_name', 'features', 'n_train', 'n_test', 'heavy_threshold_s', 'heavy_rate', 'auroc',
        'average_precision', 'spearman']], 4))

    cols = ['policy', 'n', 'n_busy', 'mean', 'p99', 'p99_busy', 'p99_busy_reduction',
            'p99_busy_reduction_lo', 'p99_busy_reduction_hi', 'p99_busy_gap', 'p99_busy_gap_lo',
            'p99_busy_gap_hi', 'mean_reduction', 'mean_reduction_lo', 'mean_reduction_hi',
            'max_excess', 'harm']
    for scope in ['test', 'CE1|test', 'CE2|test']:
        out.append(f'## Replay, {scope} queue (L = 900 s)\n\n' + md(pm[pm.scope == scope][cols], 3))
    out.append('## Replay, the other walltime classes (both partitions pooled)\n\n' + md(pm[
        pm.scope.isin(['short', 'long', 'day', 'infinite'])][
        ['scope', 'policy', 'n', 'mean', 'p99', 'p99_busy', 'p99_busy_gap', 'max_excess', 'harm']], 3))

    fire = gd[gd.policy.str.contains('Constant|Age')].groupby(['queue_name', 'policy'])[
        ['n_dispatch', 'n_forced']].sum().reset_index()
    fire['firing_rate'] = fire.n_forced / fire.n_dispatch
    worst = bc.groupby(['queue_name', 'policy'])[['checked', 'violations', 'max_excess_s',
                                                  'theoretical_max_s', 'worst_ratio']].agg(
        dict(checked='sum', violations='sum', max_excess_s='max', theoretical_max_s='max',
             worst_ratio='max')).reset_index()
    out.append('## Guard firing and per-job bound checks\n\n'
               + md(worst.merge(fire, on=['queue_name', 'policy']), 4))

    timings = [json.loads(line) for line in (HERE / 'timings.jsonl').read_text().splitlines()]
    total = dict(wall_s=sum(t['wall_s'] for t in timings), cpu_s=sum(t['cpu_s'] for t in timings),
                 invocations=len(timings))
    out.append('## Measured computation\n\n' + md(pd.DataFrame(timings + [dict(stage='TOTAL', **{
        k: v for k, v in total.items() if k != 'invocations'})]), 3))
    dump('compute_time.json', total)
    (HERE / 'tables.md').write_text('\n\n'.join(out) + '\n', encoding='utf-8')
    log('TABLES WRITTEN', len(out), 'sections;', json.dumps(total))
    finish()


if __name__ == '__main__':
    main()
