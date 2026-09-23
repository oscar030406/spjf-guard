"""One submission-visible expected-cost score per walltime class.

The paper's visibility protocol, applied inside each queue: the features are the
fields a submission carries plus the outcomes of that user's own jobs that had
already completed when the job arrived. Levels, the heavy threshold and the trees
are all fixed on the pre-cutoff part of that queue.
"""
import sys
sys.dont_write_bytecode = True
from qcommon import *
from collections import deque
import lightgbm as lgb
from sklearn.metrics import roc_auc_score, average_precision_score, mean_squared_error
from spjf_guard.predict.scores import SCORE_SPECS, DEFAULT_LGB_PARAMS, DEFAULT_ROUNDS

STATIC = ['uid', 'gid', 'part', 'time_req', 'L']
HISTORY = ['history_count', 'history_mean_c', 'history_mean_log', 'history_sd_log',
           'history_last_c', 'history_last5_mean', 'history_age_s']


def history_features(d, scope):
    """Own-user completion history readable at each arrival.

    `scope` is a boolean mask of the jobs allowed into the history, so the same
    routine gives the all-queue stream and the same-queue-only ablation.
    """
    a, done, cost, uid = d.a.values, d.done.values, d.c.values, d.uid.values
    order = np.argsort(done, kind='stable')
    hist = np.full((len(d), len(HISTORY)), np.nan)
    state, p = {}, 0
    for i, t in enumerate(a):
        while p < len(d) and done[order[p]] <= t:
            j = order[p]
            p += 1
            if not scope[j]:
                continue
            u = uid[j]
            x = float(cost[j])
            z = np.log1p(x)
            st = state.setdefault(u, [0, 0., 0., 0., deque(maxlen=5), 0])
            st[0] += 1
            st[1] += x
            st[2] += z
            st[3] += z * z
            st[4].append(x)
            st[5] = int(done[j])
        if uid[i] in state:
            n, total, logs, sq, last5, end = state[uid[i]]
            hist[i] = [n, total / n, logs / n, np.sqrt(max(0, sq / n - (logs / n) ** 2)),
                       last5[-1], np.mean(last5), t - end]
        else:
            hist[i, 0] = 0
    return pd.DataFrame(hist, columns=HISTORY)


def verify(d, x, scope, log, tag):
    """Recompute the history of a sample of rows from scratch and compare."""
    rng = np.random.default_rng(BOOT_SEED)
    ids = np.unique(np.r_[np.arange(10), rng.choice(len(d), 150, replace=False)])
    for i in ids:
        prior = d[(d.uid == d.uid.iloc[i]) & (d.done <= d.a.iloc[i]) & scope].sort_values('done', kind='stable')
        if len(prior):
            z = np.log1p(prior.c.values)
            expect = [len(prior), prior.c.mean(), z.mean(), z.std(), prior.c.iloc[-1],
                      prior.c.iloc[-5:].mean(), d.a.iloc[i] - prior.done.iloc[-1]]
        else:
            expect = [0, *([np.nan] * 6)]
        assert np.allclose(x.iloc[i].astype(float).values, expect, rtol=1e-7, atol=1e-5, equal_nan=True), int(i)
    log('INDEPENDENT HISTORY RECOMPUTATION', tag, len(ids), 'rows, 0 mismatches')


def main():
    log, finish = log_start('qpredict')
    d = load()
    cut = SPLIT_DAY * DAY
    train_all = (d.a.values < cut) & (d.done.values < cut)
    test_all = d.a.values >= cut
    caps = json.loads((HERE / 'qcapacity.json').read_text())
    queues = sorted({int(key.split('|')[1]) for key in caps['k']['fit']})
    hist_all = history_features(d, np.ones(len(d), bool))
    verify(d, hist_all, np.ones(len(d), bool), log, 'all-queue history')
    spec = SCORE_SPECS['spjf_e']
    params = dict(DEFAULT_LGB_PARAMS, **spec.params, objective=spec.objective, seed=SEED,
                  random_state=SEED, num_threads=4, deterministic=True, force_row_wise=True)
    log('MODEL PARAMETERS', json.dumps(params), 'rounds', DEFAULT_ROUNDS)
    score = np.full(len(d), np.nan)
    heavy = np.zeros(len(d), bool)
    rows = []
    for queue in queues:
        inq = d.queue.values == queue
        scope_same = inq.copy()
        hist_same = history_features(d, scope_same)
        if queue == queues[0]:
            verify(d, hist_same, scope_same, log, f'same-queue history (queue {queue})')
        for tag, hist in [('all_queue_history', hist_all), ('same_queue_history', hist_same)]:
            x = pd.concat([d[STATIC].reset_index(drop=True), hist], axis=1)
            for col in ['uid', 'gid', 'part']:
                known = sorted(d.loc[train_all & inq, col].unique().tolist())
                x[col] = pd.Categorical(d[col], categories=known)
            tr = train_all & inq
            te = test_all & inq
            threshold = float(np.quantile(d.c.values[tr], .95))
            y = d.c.values > threshold
            model = lgb.train(params, lgb.Dataset(x[tr], label=spec.target_of(d.c.values)[tr]),
                              num_boost_round=DEFAULT_ROUNDS)
            v = model.predict(x[te], num_threads=4)
            if tag == 'all_queue_history':
                score[te] = v
                heavy[inq] = y[inq]
                model.save_model(str(HERE / f'model_q{queue}.txt'))
            for pool in ['all', *NOMINAL]:
                sel = np.ones(te.sum(), bool) if pool == 'all' else (d.pool.values[te] == pool)
                if sel.sum() < 50 or len(np.unique(y[te][sel])) < 2:
                    continue
                raw = np.maximum(v[sel], 0)
                row = dict(queue=queue, queue_name=QUEUE_NAME[queue], features=tag, pool=pool,
                           n_train=int(tr.sum()), n_test=int(sel.sum()), heavy_threshold_s=threshold,
                           heavy_rate=float(y[te][sel].mean()),
                           auroc=float(roc_auc_score(y[te][sel], v[sel])),
                           average_precision=float(average_precision_score(y[te][sel], v[sel])),
                           log_rmse=float(np.sqrt(mean_squared_error(np.log1p(d.c.values[te][sel]), np.log1p(raw)))),
                           spearman=float(pd.Series(v[sel]).corr(pd.Series(d.c.values[te][sel]), method='spearman')))
                rows.append(row)
                if pool == 'all':
                    log('SCORE', QUEUE_NAME[queue], tag, json.dumps(
                        {q: (round(row[q], 4) if isinstance(row[q], float) else row[q])
                         for q in ['n_train', 'n_test', 'heavy_threshold_s', 'heavy_rate', 'auroc',
                                   'average_precision', 'spearman']}))
    pd.DataFrame(rows).to_csv(HERE / 'prediction_metrics.csv', index=False)
    np.savez_compressed(HERE / 'predictions.npz', spjf_e=score, heavy=heavy)
    dump('qpredictor.json', dict(features=STATIC + HISTORY, per_queue=True,
                                 primary_features='all_queue_history',
                                 ablation='same_queue_history',
                                 visibility='recorded completion <= recorded arrival, own user only',
                                 caveat='open-loop: the history stream is the recorded one and is not '
                                        'recomputed under the counterfactual schedules',
                                 params=params, rounds=DEFAULT_ROUNDS, seed=SEED,
                                 defaults_source='src/spjf_guard/predict/scores.py'))
    finish()


if __name__ == '__main__':
    main()
