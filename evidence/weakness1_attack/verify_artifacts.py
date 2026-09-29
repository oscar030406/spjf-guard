"""Check the completed numerical artefacts and their development-only provenance."""
import sys
sys.dont_write_bytecode = True
import json
import hashlib
import math
import time
import platform
from importlib.metadata import version
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
EXPECTED_REPS=range(5)
COMMON_K=range(1,21)
EXTENSION_K=range(21,77)
POLICIES=['FCFS','SJF','SPJF-E','Guard(300)','Guard(600)','Guard(1200)']
PROMISE={'Guard(300)':300,'Guard(600)':600,'Guard(1200)':1200}
METRICS=('q99','mean','max_excess','harm')
EXPECTED_JOBS=17_634_760
N_DRAWS=2001
LIMIT_S=60.0
PARAMETERS={
    'reps':list(range(5)),
    'common_k':list(range(1,21)),
    'extension_rep':0,
    'extension_k':list(range(21,77)),
    'resamples':2000,
    'seed':20260921,
    'score':'tweedie',
    'limit_s':60.0,
    'window':1<<22,
    'guard_settings':[
        [300.0,15.0,0.5,0.0],
        [600.0,30.0,0.75,0.0],
        [1200.0,0.0,0.0,4.0],
    ],
}
EXPECTED_PROTOCOL=hashlib.sha256(json.dumps(PARAMETERS,sort_keys=True).encode()).hexdigest()
GUARD_SHAPE={
    'Guard(300)':(15.0,0.5,0.0),
    'Guard(600)':(30.0,0.75,0.0),
    'Guard(1200)':(0.0,0.0,4.0),
}
from common import development_overlay, development_input_path
from spjf_guard.data import sealed
TERMS=('2020-ERE','2020-2','2021-1','2021-2','2022-1','2022-2')
DEV_HASHES={
    0:'4f5a6c84a59d1e60342593d26a81e92a38cb76a2b730c69a6babaffc983d4971',
    1:'f300b3195d03bad713951bcf7051610ae6b7eb99753c61e85465299b9737b720',
    2:'053b24fa860f2595ea2c0427945d107dabab1e65abf2e46a264678834dd3d981',
    3:'84e95b15b9da99a4d6d6a9606c835db7396b552448995312bc238e2a3b4191e4',
    4:'5581859bdf016c22f105563b43711543e4db908d3874ac1549d6a0adb454c1aa',
}


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):
            h.update(block)
    return h.hexdigest()


def expected_parameters(policy,k):
    floor_s=(3.0-2.0/k)*LIMIT_S
    if policy not in PROMISE:
        return {'floor_s':floor_s,'b0_s':0.0,'eta':0.0,'gamma_s':0.0,'bmax_s':0.0}
    b0_per_k,eta,gamma_per_k=GUARD_SHAPE[policy]
    bmax_s=k*(PROMISE[policy]-floor_s)
    return {
        'floor_s':floor_s,
        'b0_s':min(b0_per_k*k,bmax_s),
        'eta':eta,
        'gamma_s':gamma_per_k*k,
        'bmax_s':bmax_s,
    }


def assert_finite_number(value,label):
    assert isinstance(value,(int,float)) and not isinstance(value,bool),label
    assert math.isfinite(float(value)),label


def main():
    start,cpu=time.perf_counter(),time.process_time()
    protocols=set()
    bound_checks=0
    counts={'simulated':0,'certified_identical':0}
    verified_certificates=0
    certificates_by_rep={r:0 for r in EXPECTED_REPS}
    certificate_validations_by_rep={r:0 for r in EXPECTED_REPS}
    cells=0
    policy_rows=0
    worst_ratio=0.
    legacy_fcfs_flag_cells=[]
    for rep in EXPECTED_REPS:
        for k in list(COMMON_K)+(list(EXTENSION_K) if rep==0 else []):
            stem=HERE/'cells'/f'rep{rep}_k{k}'
            d=json.loads(stem.with_suffix('.json').read_text(encoding='utf-8'))
            protocols.add(d['protocol'])
            assert d['protocol']==EXPECTED_PROTOCOL
            assert d['parameters']==PARAMETERS
            expected=POLICIES if k<=20 else ['FCFS','SJF','SPJF-E','Guard(600)']
            assert [r['policy'] for r in d['rows']]==expected
            by_policy={r['policy']:r for r in d['rows']}
            expected_arrays={f'{p}_{metric}' for p in expected for metric in METRICS}
            with np.load(stem.with_suffix('.npz'),allow_pickle=False) as z:
                assert set(z.files)==expected_arrays
                for row in d['rows']:
                    assert row['rep']==rep and row['k']==k and row['n']==EXPECTED_JOBS
                    p=row['policy']
                    for field,value in expected_parameters(p,k).items():
                        assert_finite_number(row[field],f'{stem.name} {p} {field}')
                        assert abs(float(row[field])-value)<1e-9,(stem.name,p,field,row[field],value)
                    assert isinstance(row['dispatches'],int) and row['dispatches']>=0
                    assert isinstance(row['forced_dispatches'],int)
                    assert 0<=row['forced_dispatches']<=row['dispatches']
                    for field in ['fired_fraction','fired_queue_weighted']:
                        assert_finite_number(row[field],f'{stem.name} {p} {field}')
                        assert 0.0<=float(row[field])<=1.0
                    if p not in PROMISE:
                        legacy_fifo_flag=(rep==0 and k in (1,2,3) and p=='FCFS'
                                          and 'execution' not in row)
                        if legacy_fifo_flag:
                            # The retained initial invocation copied the kernel FIFO flag.
                            # It means FCFS selection, not a Guard firing; raw records stay intact.
                            assert row['forced_dispatches']==row['dispatches']==EXPECTED_JOBS
                            assert row['fired_fraction']==1 and row['fired_queue_weighted']==1
                            legacy_fcfs_flag_cells.append({'rep':rep,'k':k})
                        else:
                            assert row['forced_dispatches']==0
                            assert row['fired_fraction']==0 and row['fired_queue_weighted']==0
                    for suffix,field in [('q99','p99_deadline_s'),('mean','mean_s'),('max_excess','max_excess_s'),('harm','harm_s')]:
                        arr=z[p+'_'+suffix]
                        assert arr.shape==(N_DRAWS,) and np.isfinite(arr).all()
                        assert abs(float(arr[0])-row[field])<1e-8
                    if p in PROMISE:
                        assert row['bound_checks']==EXPECTED_JOBS
                        assert row['bound_violations']==0 and row['max_bound_violation_s']==0
                        # Maxima derive from exact integer differences; recover the integer.
                        assert int(round(row['max_excess_s']*1e6))<=PROMISE[p]*1_000_000
                        assert_finite_number(
                            row['max_fraction_of_allowed_excess'],
                            f'{stem.name} {p} max_fraction_of_allowed_excess',
                        )
                        assert 0<=row['max_fraction_of_allowed_excess']<=1+1e-12
                        bound_checks+=row['bound_checks']
                        worst_ratio=max(worst_ratio,row['max_fraction_of_allowed_excess'])
                        execution=row.get('execution','simulated')
                        assert execution in counts
                        counts[execution]+=1
                        validation=bool(row.get('certificate_checked_against_kernel',False))
                        if execution=='certified_identical':
                            assert row['gamma_s']==0 and row['eta']>=0
                            assert row['certificate_max_in_us']<int(round(row['b0_s']*1e6))
                            assert row['forced_dispatches']==0
                            assert row['fired_fraction']==0 and row['fired_queue_weighted']==0
                            for suffix in ['q99','mean','max_excess','harm']:
                                assert np.array_equal(z[p+'_'+suffix],z['SPJF-E_'+suffix])
                            for field in ['p99_all_s','max_wait_s','positive_wait_jobs']:
                                assert row[field]==by_policy['SPJF-E'][field]
                            certificates_by_rep[rep]+=1
                        else:
                            assert row.get('certificate_max_in_us') is None
                            assert not validation
                        if validation:
                            assert execution=='certified_identical'
                            certificate_validations_by_rep[rep]+=1
                            verified_certificates+=1
                    policy_rows+=1
            cells+=1
    assert cells==156 and policy_rows==824 and protocols=={EXPECTED_PROTOCOL}
    assert bound_checks==6_277_974_560
    for rep in EXPECTED_REPS:
        required=min(2,certificates_by_rep[rep])
        assert certificate_validations_by_rep[rep]>=required,(
            rep,certificate_validations_by_rep[rep],required,certificates_by_rep[rep]
        )
    endpoint=json.loads((HERE/'cells/rep0_k76.json').read_text(encoding='utf-8'))
    assert all(r['positive_wait_jobs']==0 and r['max_wait_s']==0 for r in endpoint['rows'])
    before=json.loads((HERE/'cells/rep0_k75.json').read_text(encoding='utf-8'))
    assert before['rows'][0]['positive_wait_jobs']>0
    source=json.loads((HERE/'source_baseline.json').read_text(encoding='utf-8-sig'))
    drift=json.loads((HERE/'source_drift.json').read_text(encoding='utf-8'))
    snapshots={entry['path']:entry for entry in drift['sources']}
    current_source_changes=[]
    for entry in source['sources']:
        assert digest(HERE/snapshots[entry['path']]['snapshot'])==entry['sha256']
        current=digest(ROOT/entry['path'])
        if current!=entry['sha256']:
            assert entry['path'] in ('src/spjf_guard/sim/runner.py','src/spjf_guard/sim/policy.py','configs/main.yaml')
            current_source_changes.append({'path':entry['path'],'current_sha256':current,'baseline_sha256':entry['sha256']})
    inputs=[]
    week_axes=[]
    sealed.guard_semesters(TERMS,ROOT,unseal=False)
    for rep,expected_hash in DEV_HASHES.items():
        path=development_input_path(rep)
        actual=digest(path)
        assert actual==expected_hash, path
        trace,labels=development_overlay(rep)
        assert len(trace)==EXPECTED_JOBS and int(labels['in_window'].sum())==4_219_556
        assert 0<int(trace.service_us.min())<=int(trace.service_us.max())<=60_000_000
        assert np.isfinite(trace.scores['tweedie']).all()
        assert labels['n_weeks']==30 and int(labels['week'].min())>=0 and int(labels['week'].max())<30
        week_axes.append(labels['week_axis'])
        inputs.append({'path':str(path.relative_to(ROOT)).replace('\\','/'),
                       'bytes':path.stat().st_size,'sha256':actual,
                       'service_min_s':float(trace.service_us.min()/1e6),
                       'service_max_s':float(trace.service_us.max()/1e6),
                       'all_cached_scores_finite':True,
                       'week_axis':labels['week_axis'],
                       'basis':'previous development manifest outputs/dev_tables/manifest.json'})
        del trace,labels
    assert all(axis==week_axes[0] for axis in week_axes), 'stored paired week axes differ'
    result={'status':'PASS','complete_cells':cells,'policy_rows':policy_rows,
            'bound_checks':bound_checks,'bound_violations':0,'guard_evaluations':counts,
             'certificates_validated_against_kernel':verified_certificates,
             'certified_cells_by_rep':certificates_by_rep,
             'certificate_kernel_validations_by_rep':certificate_validations_by_rep,
             'retained_legacy_fcfs_fifo_flag_cells':legacy_fcfs_flag_cells,
             'certificate_validation_requirement':'at least min(2, certified cells) in every overlay',
             'worst_fraction_of_allowed_excess':worst_ratio,
             'protocol':EXPECTED_PROTOCOL,'parameters':PARAMETERS,
             'development_inputs':inputs,'sources':source['sources'],
             'concurrent_source_changes':current_source_changes,
             'reproduction_uses_hash_matched_baseline_simulation_snapshot':True,
             'stored_week_axes_identical':True,
             'runtime_versions':{'python':platform.python_version(),'platform':platform.platform(),
                                 'numpy':version('numpy'),'numba':version('numba')},
             'wall_s':time.perf_counter()-start,'cpu_s':time.process_time()-cpu}
    (HERE/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
