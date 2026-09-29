"""Fixed-demand integer capacity envelope, with exact paired week resampling.

Reruns validate and resume complete cells with the same protocol identifier. At most two workers.
"""
import sys
sys.dont_write_bytecode = True
import time
import json
import hashlib
import os
from common import HERE, ROOT, TERMS, development_overlay, timing, np
from spjf_guard.sim import simulate
from spjf_guard.sim.policy import fcfs, sjf, spjf, guard
from spjf_guard.sim.bounds import assert_per_job_bounds, guard_upper_bound
from spjf_guard.sim.bounds import in_out
from spjf_guard.experiment import bootstrap as bs

PARAMETERS = dict(reps=list(range(5)), common_k=list(range(1,21)),
                  extension_rep=0, extension_k=list(range(21,77)), resamples=2000,
                  seed=20260921, score='tweedie', limit_s=60., window=1<<22,
                  guard_settings=[(300.,15.,.5,0.),(600.,30.,.75,0.),(1200.,0.,0.,4.)])
PROTOCOL = hashlib.sha256(json.dumps(PARAMETERS, sort_keys=True).encode()).hexdigest()
CELLS = HERE / 'cells'
CELLS.mkdir(exist_ok=True)
METRICS = ('q99','mean','max_excess','harm')


def policies(k):
    out = [fcfs(), sjf(), spjf('tweedie','SPJF-E')]
    for g,b,e,q in PARAMETERS['guard_settings']:
        if k > 20 and g != 600:
            continue
        out.append(guard(g,k,60.,b*k,e,'tweedie',gam_s=q*k))
    return out


def resample_max(values, week, mult):
    maximum = np.full(mult.shape[1], -np.inf)
    np.maximum.at(maximum, week, values)
    return np.max(np.where(mult > 0, maximum[None,:], -np.inf), axis=1)


def validate_complete_cell(rep, k):
    """Return metadata only after both cell files pass the full resume contract."""
    stem = CELLS / f'rep{rep}_k{k}'
    json_path, npz_path = stem.with_suffix('.json'), stem.with_suffix('.npz')
    if json_path.exists() != npz_path.exists():
        raise RuntimeError(f'partial cell artifact at {stem}: JSON/NPZ must coexist')
    if not json_path.exists():
        return None
    try:
        document = json.loads(json_path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f'unreadable completed cell {json_path}: {exc}') from exc
    if document.get('protocol') != PROTOCOL:
        raise RuntimeError(f'protocol mismatch in completed cell {json_path}')
    if json.dumps(document.get('parameters'), sort_keys=True) != json.dumps(PARAMETERS, sort_keys=True):
        raise RuntimeError(f'parameter mismatch in completed cell {json_path}')
    expected_policies = [p.name for p in policies(k)]
    rows = document.get('rows')
    if not isinstance(rows, list) or [row.get('policy') for row in rows] != expected_policies:
        raise RuntimeError(f'policy rows in {json_path} do not equal {expected_policies}')
    if any(row.get('rep') != rep or row.get('k') != k for row in rows):
        raise RuntimeError(f'cell coordinates disagree inside {json_path}')
    expected_keys = {f'{policy}_{metric}' for policy in expected_policies for metric in METRICS}
    try:
        with np.load(npz_path, allow_pickle=False) as store:
            if set(store.files) != expected_keys:
                raise RuntimeError(
                    f'NPZ schema mismatch in {npz_path}: '
                    f'missing={sorted(expected_keys-set(store.files))}, '
                    f'extra={sorted(set(store.files)-expected_keys)}'
                )
            expected_shape = (PARAMETERS['resamples'] + 1,)
            for name in store.files:
                value = store[name]
                if value.shape != expected_shape:
                    raise RuntimeError(
                        f'NPZ shape mismatch in {npz_path}, {name}: '
                        f'{value.shape} != {expected_shape}'
                    )
                if not np.isfinite(value).all():
                    raise RuntimeError(f'nonfinite draw in {npz_path}, {name}')
    except (OSError, ValueError) as exc:
        raise RuntimeError(f'unreadable completed draws {npz_path}: {exc}') from exc
    return document


def write_invocation_ledger(canonical_name, result, tag):
    """Write a unique rerun ledger and create the historical canonical file only once."""
    canonical = HERE / canonical_name
    invocation = HERE / (
        f'sweep_execution_invocation_{tag}_pid{os.getpid()}_{time.time_ns()}.json'
    )
    enriched = {
        **result,
        'invocation_ledger': invocation.name,
        'canonical_execution_file': canonical.name,
        'canonical_preserved': canonical.exists(),
    }
    invocation.write_text(json.dumps(enriched, indent=2), encoding='utf-8')
    if not canonical.exists():
        canonical.write_text(json.dumps(enriched, indent=2), encoding='utf-8')
    return enriched


def main(rep_arg=None):
    start, cpu = time.perf_counter(), time.process_time()
    print('protocol', PROTOCOL, json.dumps(PARAMETERS), flush=True)
    for rep in (PARAMETERS['reps'] if rep_arg is None else [rep_arg]):
        capacities = PARAMETERS['common_k'] + (PARAMETERS['extension_k'] if rep==0 else [])
        existing = {k: validate_complete_cell(rep, k) for k in capacities}
        certificates_validated = sum(
            row.get('execution') == 'certified_identical'
            and bool(row.get('certificate_checked_against_kernel'))
            for document in existing.values() if document is not None
            for row in document['rows']
        )
        certified_rows = sum(
            row.get('execution') == 'certified_identical'
            for document in existing.values() if document is not None
            for row in document['rows']
        )
        if all(document is not None for document in existing.values()):
            required = min(2, certified_rows)
            if certificates_validated < required:
                raise RuntimeError(
                    f'rep {rep} has {certificates_validated} prior certificate validations; '
                    f'{required} required'
                )
            print('skip complete rep',rep,flush=True)
            continue
        tr, labels = development_overlay(rep)
        dl = labels['in_window']
        wk = labels['week']
        nweek = labels['n_weeks']
        assert nweek == 30
        mult = bs.with_point_estimate(bs.week_multiplicities(nweek, PARAMETERS['resamples'], PARAMETERS['seed']))
        finishes = np.sort(tr.arrival_us + tr.service_us)
        occupancy = np.arange(1,len(tr)+1)-np.searchsorted(finishes,tr.arrival_us,side='right')
        peak = int(occupancy.max())
        del finishes, occupancy
        meta = {'rep':rep,'n':len(tr),'n_deadline':int(dl.sum()),'n_weeks':nweek,
                'copies':labels['copies'],'busy_hour_work_s':labels['busy_hour_work_s'],
                'infinite_server_peak':peak, 'terms':TERMS,
                'service_top1_share':float(np.sort(tr.service_us)[-int(np.ceil(len(tr)*.01)):].sum()/tr.service_us.sum()),
                'span_s':float((tr.arrival_us[-1]-tr.arrival_us[0])/1e6)}
        (HERE / f'overlay{rep}_metadata.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
        print('loaded',json.dumps(meta),flush=True)
        for k in capacities:
            stem = CELLS / f'rep{rep}_k{k}'
            if existing[k] is not None:
                print('skip',rep,k,flush=True)
                continue
            t0,c0 = time.perf_counter(),time.process_time()
            rows, draws = [], {}
            fwait = None
            base_result, base_row, max_in = None, None, None
            for p in policies(k):
                ts,cs = time.perf_counter(),time.process_time()
                certified = (p.wrapper=='work' and p.gam_us==0 and max_in is not None
                             and max_in < p.b0_us)
                validation = False
                if certified:
                    certified_rows += 1
                    from dataclasses import replace
                    r = replace(base_result, policy=p.name, n_forced=0, queue_weighted_forced=0)
                    if certificates_validated < 2:
                        actual = simulate(tr,p,k,window=PARAMETERS['window'])
                        assert np.array_equal(actual.wait_us,r.wait_us)
                        assert np.array_equal(actual.dispatch_index,r.dispatch_index)
                        assert actual.n_forced==0
                        certificates_validated += 1
                        validation = True
                        del actual
                else:
                    r = simulate(tr,p,k,window=PARAMETERS['window'])
                if p.name=='FCFS':
                    fwait = r.wait_us.copy()
                wait = r.wait_us / 1e6
                excess = (r.wait_us-fwait)/1e6
                undelayed = fwait <= 1_000_000
                if certified:
                    q,means,mx,harm = [draws['SPJF-E_'+m] for m in ['q99','mean','max_excess','harm']]
                else:
                    q = bs.resampled_quantile(wait[dl],wk[dl],mult,.99)
                    assert abs(q[0]-np.quantile(wait[dl],.99)) < 1e-7
                    means = bs.resampled_mean(wait,wk,mult)
                    mx = resample_max(excess,wk,mult)
                    harm = resample_max(excess[undelayed],wk[undelayed],mult)
                draws[p.name+'_q99'] = q
                draws[p.name+'_mean'] = means
                draws[p.name+'_max_excess'] = mx
                draws[p.name+'_harm'] = harm
                checked=0
                violation=0.
                ratio=0.
                if p.wrapper=='work':
                    checked=assert_per_job_bounds(r,fwait,p,k,60.)
                    bound = guard_upper_bound(fwait,p,k,60.)
                    violation=float(np.maximum(wait-bound,0).max())
                    ratio=float(np.maximum(excess,0).__truediv__(bound-fwait/1e6).max())
                    del bound
                row = {'policy':p.name,'rep':rep,'k':k,'n':len(tr),'p99_deadline_s':float(q[0]),
                       'mean_s':float(means[0]),'p99_all_s':base_row['p99_all_s'] if certified else float(np.quantile(wait,.99)),
                       'max_wait_s':float(wait.max()),'max_excess_s':float(mx[0]),'harm_s':float(harm[0]),
                       'positive_wait_jobs':int((r.wait_us>0).sum()),'forced_dispatches':r.n_forced if p.wrapper=='work' else 0,
                       'dispatches':r.n_dispatch,'fired_fraction':r.fired_fraction if p.wrapper=='work' else 0.,
                       'fired_queue_weighted':r.fired_fraction_queue_weighted if p.wrapper=='work' else 0.,
                       'bound_checks':checked,'bound_violations':0,'max_bound_violation_s':violation,
                       'max_fraction_of_allowed_excess':ratio,
                       'floor_s':(3-2/k)*60.,'busy_hour_offered_load':labels['busy_hour_work_s']/(3600*k),
                       'b0_s':p.b0_us/1e6,'eta':p.eta_k/k,'gamma_s':p.gam_us/1e6,'bmax_s':p.bmax_us/1e6,
                       'execution':'certified_identical' if certified else 'simulated',
                       'certificate_max_in_us':max_in if certified else None,
                       'certificate_checked_against_kernel':validation,
                       **timing(ts,cs)}
                rows.append(row)
                print(json.dumps(row),flush=True)
                if p.name=='SPJF-E':
                    base_result,base_row = r,row
                    if k >= 8:
                        work_in,work_out = in_out(tr.service_us,r.dispatch_order)
                        max_in = int(work_in.max())
                        del work_in,work_out
                del r,wait,excess
            fq=draws['FCFS_q99'][0]
            sq=draws['SJF_q99'][0]
            for row in rows:
                row['gap_closed']=(fq-row['p99_deadline_s'])/(fq-sq) if fq>sq else None
                row['reduction_pct']=100*(fq-row['p99_deadline_s'])/fq if fq>0 else None
            np.savez(stem.with_suffix('.npz'),**draws)
            result={'protocol':PROTOCOL,'parameters':PARAMETERS,'rows':rows,**timing(t0,c0)}
            stem.with_suffix('.json').write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
            print('CELL_COMPLETE',rep,k,json.dumps(timing(t0,c0)),flush=True)
            del fwait,base_result
        required = min(2, certified_rows)
        if certificates_validated < required:
            raise RuntimeError(
                f'rep {rep} finished with {certificates_validated} certificate validations; '
                f'{required} required'
            )
        del tr,labels
    result={'protocol':PROTOCOL,'rep':rep_arg,
            'resume_validation':'protocol, parameters, policy rows, NPZ schema/shape/finite',
            **timing(start,cpu)}
    result=write_invocation_ledger(f'sweep_execution_rep{rep_arg}.json',result,f'rep{rep_arg}')
    print('REP_COMPLETE',json.dumps(result),flush=True)
    return result


if __name__=='__main__':
    from concurrent.futures import ProcessPoolExecutor
    import multiprocessing
    start=time.perf_counter()
    with ProcessPoolExecutor(max_workers=2,mp_context=multiprocessing.get_context('spawn')) as pool:
        completed=list(pool.map(main,PARAMETERS['reps']))
    result={'protocol':PROTOCOL,'workers':2,'wall_s':time.perf_counter()-start,
            'cpu_s':sum(v['cpu_s'] for v in completed),'runs':completed}
    result=write_invocation_ledger('sweep_execution.json',result,'coordinator')
    print('SWEEP_COMPLETE',json.dumps(result),flush=True)
