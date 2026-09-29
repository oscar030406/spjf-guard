"""Account for recorded experiment resources without double-counting worker CPU."""
from pathlib import Path
import sys
sys.dont_write_bytecode = True
import json
from datetime import datetime, timezone
import re
import time

HERE = Path(__file__).resolve().parent


def read(name):
    return json.loads((HERE/name).read_text(encoding='utf-8-sig'))


def json_documents_after_heading(name):
    """Parse consecutive JSON documents after a one-line text heading."""
    text=(HERE/name).read_text(encoding='utf-8-sig')
    _,payload=text.split('\n',1)
    decoder=json.JSONDecoder()
    documents=[]
    position=0
    while position < len(payload):
        while position < len(payload) and payload[position].isspace():
            position+=1
        if position == len(payload):
            break
        document,position=decoder.raw_decode(payload,position)
        documents.append(document)
    return documents


def main():
    started,cpu=time.perf_counter(),time.process_time()
    rows=[]
    def add(name, wall, cpu_value, note='', evidence=None, timing_status=None,
            include_wall=True, include_cpu=True, details=None):
        status=timing_status or ('known' if wall is not None and cpu_value is not None else 'unknown')
        rows.append({'experiment':name,'wall_s':wall,'cpu_s':cpu_value,
                     'timing_status':status,
                     'included_in_instrumented_wall_sum':bool(include_wall and wall is not None),
                     'included_in_instrumented_cpu_sum':bool(include_cpu and cpu_value is not None),
                     'evidence':evidence,'details':details,'note':note})

    def audit_cpu(directory):
        worker=0.
        dispatcher=0.
        count=0
        for path in directory.glob('physical_*_audit.json'):
            detail=json.loads(path.read_text(encoding='utf-8'))
            resources=detail['run_resources']
            worker+=resources['worker_cpu_through_last_finish_s']
            dispatcher+=resources['dispatcher_cpu_s']
            count+=1
        return {'worker_cpu_s':worker,'dispatcher_cpu_s':dispatcher,'audit_files':count}
    p=read('pilot.json')
    add('pilot',p['wall_s'],p['cpu_s'])
    p=read('initial_execution.json')
    add('initial serial capacity invocation',
        (datetime.fromisoformat(p['stop'])-datetime.fromisoformat(p['start'])).total_seconds(),
        p['cpu_s'],'completed cells were reused; partial in-flight work is included')
    p=read('sweep_execution.json')
    add('resumed two-worker capacity sweep',p['wall_s'],p['cpu_s'],
        'CPU is the sum of the five worker invocation CPU totals, not the sum of cell timers')
    coordinator_ledgers=sorted(
        HERE.glob('sweep_execution_invocation_coordinator_pid*_*.json')
    )
    for invocation in coordinator_ledgers:
        p=json.loads(invocation.read_text(encoding='utf-8'))
        if p.get('canonical_preserved') is not True:
            continue
        add('capacity sweep no-op coordinator rerun',p['wall_s'],p['cpu_s'],
            'one coordinator invocation; CPU already sums its child processes, so nested runs and '
            'rep invocation ledgers are not added separately',
            invocation.name,
            details={'canonical_preserved':True,
                     'canonical_execution_file':p.get('canonical_execution_file'),
                     'invocation_ledger':p.get('invocation_ledger'),
                     'workers':p.get('workers')})
    p=read('source_drift.json')
    add('source drift audit',p['timing']['wall_s'],p['timing']['cpu_s'],
        'separate audit; not included in capacity-worker CPU', 'source_drift.json')
    p=read('recovered_development_inputs.json')
    add('recover original development-input backups',p['timing']['wall_s'],p['timing']['cpu_s'],
        'one successful recovery invocation covering all five originals; counted once',
        'recovered_development_inputs.json; out_recover_original_backups.txt')
    p=read('container_serialization_check.json')
    add('recovered-container serialization diagnostic',p['timing']['wall_s'],p['timing']['cpu_s'],
        'container diagnostic only; rejected candidate generation is accounted separately',
        'container_serialization_check.json; out_check_recovered_container.txt')
    add('failed additive recovery attempt',None,None,
        'failure and rejected candidate are preserved, but launcher wall/CPU timing was not recorded; '
        'excluded from instrumented sums rather than estimated',
        'rejected_additive_recovery.json; out_recover_development_inputs.txt')
    for name, log_name in (
        ('failed source-drift capacity verification', 'out_verify_artifacts_source_drift.txt'),
        ('failed input-drift capacity verification', 'out_verify_artifacts_input_drift.txt'),
        ('physical preparation with rejected log collision', 'out_prepare_physical_input_log_collision.txt'),
    ):
        if (HERE/log_name).exists():
            add(name,None,None,
                'failure log retained; no independent invocation wall/CPU timer was recorded',
                log_name,timing_status='unknown')
    p=read('clock_resolution.json')
    add('physical clock resolution diagnostic',p['execution']['wall_s'],p['execution']['cpu_s'],
        'identified the 15.625 ms GetTickCount64 resolution and the 100 ns QPC replacement; '
        'the recorded CPU value of zero is a known measurement, not missing timing',
        'clock_resolution.json; out_clock_resolution.txt')

    archived=HERE/'physical_v1_coarse_clock'
    p=json.loads((archived/'physical_preparation.json').read_text(encoding='utf-8'))
    add('archived v1 physical input preparation',p['execution']['wall_s'],p['execution']['cpu_s'],
        'coarse-clock protocol preparation; separate from the later QPC preparation',
        'physical_v1_coarse_clock/physical_preparation.json')
    p=json.loads((archived/'physical_smoke'/'summary.json').read_text(encoding='utf-8'))
    archived_cpu=audit_cpu(archived/'physical_smoke')
    add('archived v1 coarse-clock physical smoke',p['wall_s'],
        p['root_cpu_s']+archived_cpu['worker_cpu_s'],
        'invalidated as timing evidence by the coarse clock, but its consumed resources are counted',
        'physical_v1_coarse_clock/physical_smoke/summary.json',
        details=archived_cpu)

    stop=read('physical_coarse_clock_stop.json')
    coarse_start=datetime.fromisoformat('2026-09-21T10:02:02-04:00')
    coarse_stop=datetime.fromisoformat(stop['stopped_at'])
    coarse_wall=(coarse_stop-coarse_start).total_seconds()
    coarse_events=HERE/'physical_records'/'fcfs_attempt_20260921T100204_54313046000000_events.jsonl'
    completion_count=0
    charged_worker_holding_s=0.
    if coarse_events.exists():
        for line in coarse_events.read_text(encoding='utf-8').splitlines():
            event=json.loads(line)
            if event.get('type')=='completion_visible':
                completion_count+=1
                charged_worker_holding_s+=event['charged_worker_holding_ns']/1e9
    add('stopped v1 coarse-clock physical FCFS attempt',coarse_wall,stop['root_cpu_s'],
        'wall is derived from a one-second-resolution log start and an exact stop timestamp; '
        'CPU is root-process CPU only, so worker CPU and shutdown overhead remain unknown',
        'out_physical_service.txt; physical_coarse_clock_stop.json; '+str(coarse_events.relative_to(HERE)),
        timing_status='partial',include_wall=False,
        details={'wall_measurement':'estimated_from_one_second_log_stamp',
                 'root_cpu_measurement':'known','worker_cpu_measurement':'unknown',
                 'completed_jobs_observed':completion_count,
                 'charged_worker_holding_s_not_cpu':charged_worker_holding_s})
    add('stopped v1 coarse-clock worker CPU remainder',None,None,
        'completion events preserve counts and holding time but not worker process CPU; excluded from sums',
        str(coarse_events.relative_to(HERE)),timing_status='unknown')

    failed_smoke=HERE/'physical_smoke_v2_arrival_fixture'
    p=json.loads((failed_smoke/'summary.json').read_text(encoding='utf-8'))
    failed_cpu=audit_cpu(failed_smoke)
    add('failed v2 QPC arrival-fixture smoke',p['wall_s'],
        failed_cpu['worker_cpu_s']+failed_cpu['dispatcher_cpu_s'],
        'wall is known; CPU is a measured lower bound from three policy audits because overall root CPU '
        'was not recorded before the fixture assertion failed',
        'physical_smoke_v2_arrival_fixture/summary.json',timing_status='partial',
        details={**failed_cpu,'root_total_cpu_measurement':'unknown'})
    add('failed v2 QPC smoke root/audit CPU remainder',None,None,
        'root preparation, simulator-audit, and failure-handling CPU were not recorded; excluded from sums',
        'physical_smoke_v2_arrival_fixture/summary.json',timing_status='unknown')
    capacity_summaries=[
        ('initial capacity summary','coverage_initial_summary.json'),
    ]
    if (HERE/'coverage_label_summary.json').exists():
        capacity_summaries.append(
            ('first capacity summary label/CSV rerun','coverage_label_summary.json')
        )
    capacity_summaries.append(
        ('final capacity summary figure-caption rerun','coverage.json')
    )
    for name,path in capacity_summaries:
        p=read(path)['summary_timing']
        add(name,p['wall_s'],p['cpu_s'])
    for name,path,key in [('capacity verification','verification.json',None),
                          ('physical input preparation','physical_preparation.json','execution'),
                          ('physical summary','physical_numbers.json','execution')]:
        p=read(path)
        if key:
            p=p[key]
        add(name,p['wall_s'],p['cpu_s'])

    report_log=HERE/'out_report_capacity_tables.txt'
    if report_log.exists():
        report_timing=json.loads(report_log.read_text(encoding='utf-8-sig').splitlines()[0])
        add('capacity table formatting',report_timing['wall_s'],report_timing['cpu_s'],
            'formatting pass only; no new inference or simulation',
            'out_report_capacity_tables.txt')

    transport_documents=json_documents_after_heading('out_transport_bound_check.txt')
    transport_result=transport_documents[-1]
    if transport_result.get('status') != 'PASS' or 'timing' not in transport_result:
        raise RuntimeError('transport-bound log has no passing timed result')
    p=transport_result['timing']
    add('exact transport-bound arithmetic check',p['wall_s'],p['cpu_s'],
        'final JSON result after the heading and parameter JSON; zero CPU is a recorded value',
        'out_transport_bound_check.txt',
        details={'parameter_document':transport_documents[0],
                 'result_status':transport_result['status']})

    physical_verification=HERE/'physical_verification.json'
    discrepancy_summary=HERE/'physical_discrepancy.json'
    if discrepancy_summary.exists():
        p=json.loads(discrepancy_summary.read_text(encoding='utf-8'))
        timing=p.get('execution', p.get('timing', {}))
        add('stored physical SPJF sequence discrepancy diagnostic',
            timing.get('wall_s'),timing.get('cpu_s'),
            'single-process JSON postprocessing; no new scheduling run',
            'physical_discrepancy.json; out_physical_discrepancy.txt')

    stall_summary=HERE/'stall_bound_check.json'
    if stall_summary.exists():
        p=json.loads(stall_summary.read_text(encoding='utf-8'))
        timing=p['execution']
        add('exact dispatch-stall accounting and bound check',
            timing['wall_ns']/1e9,timing['cpu_ns']/1e9,
            'single-process exact-integer checks; no physical execution or worker process',
            'stall_bound_check.json; out_stall_bound_check.txt',
            details={'status':p['status']})

    if physical_verification.exists():
        p=json.loads(physical_verification.read_text(encoding='utf-8'))['execution']
        add('physical artifact verification',p['wall_s'],p['cpu_s'],
            'verification-process timing only; physical workers are counted with the service invocation',
            'physical_verification.json; out_verify_physical.txt')

    thinning_summary=HERE/'thinning_check.json'
    if thinning_summary.exists():
        p=json.loads(thinning_summary.read_text(encoding='utf-8'))['execution']
        add('frozen-window thinning sensitivity',p['wall_s'],p['cpu_s'],
            'single-process total from thinning_check; per-scenario simulator timings are not added',
            'thinning_check.json; out_thinning_check.txt')

    natural_resources=HERE/'natural_resources.json'
    natural_failed_launcher=HERE/'out_natural_preflight_launch.txt'
    if natural_failed_launcher.exists() and not natural_resources.exists():
        add('natural-window preflight stopped at import-time source gate',None,None,
            'source mismatch occurred before the script invocation timer and before data access; '
            'launcher output is retained, but no internal process CPU total was recorded',
            natural_failed_launcher.name,timing_status='unknown')

    recovery_attempts=sorted(HERE.glob('out_natural_source_recovery_attempt*.txt'))
    recovery_current=HERE/'out_natural_source_recovery.txt'
    seen_recovery_contents=set()
    for recovery_log in recovery_attempts+([recovery_current] if recovery_current.exists() else []):
        content=recovery_log.read_text(encoding='utf-8-sig')
        if content in seen_recovery_contents:
            continue
        seen_recovery_contents.add(content)
        detail=json.loads(content)
        timing=detail['execution']
        add('natural configuration source recovery: '+recovery_log.name,
            timing['wall_s'],timing['cpu_s'],
            'source-only recovery; CPU is the Python process timer and excludes Git subprocess CPU; '
            'a duplicate canonical log is counted only once',
            recovery_log.name,details={'status':detail['status']})
    if natural_resources.exists():
        p=json.loads(natural_resources.read_text(encoding='utf-8'))
        add('natural-window preflight',p.get('wall_s'),p.get('cpu_s'),
            'top-level process total only; nested phase and policy timings are included and not added again',
            'natural_resources.json; out_natural_preflight.txt',
            timing_status='known' if p.get('wall_s') is not None and p.get('cpu_s') is not None else 'unknown',
            details={'status':p.get('status'),'processes':p.get('processes'),
                     'children':p.get('children')})

    p=read('physical_summary.json')
    worker_cpu=sum(a['run_resources']['worker_cpu_through_last_finish_s'] for a in p['audits'].values())
    add('physical service including input and ideal audits',p['total_invocation_wall_s'],
        p['root_invocation_cpu_s']+worker_cpu,
        'root invocation CPU plus worker cumulative CPU through last finish; worker shutdown CPU is not instrumented')

    natural_physical=HERE/'natural_physical'
    natural_service_summary=natural_physical/'physical_summary.json'
    if natural_service_summary.exists():
        p=json.loads(natural_service_summary.read_text(encoding='utf-8'))
        worker_cpu=sum(
            audit['run_resources']['worker_cpu_through_last_finish_s']
            for audit in p['audits'].values()
        )
        add('natural-window physical service including ideal audits',
            p['total_invocation_wall_s'],p['root_invocation_cpu_s']+worker_cpu,
            'root invocation CPU plus worker cumulative CPU through last finish; nested service-policy '
            'timers are included and not added separately',
            'natural_physical/physical_summary.json',
            details={'root_invocation_cpu_s':p['root_invocation_cpu_s'],
                     'worker_cpu_through_last_finish_s':worker_cpu,
                     'policies':list(p['audits'])})
        for name,path in [
            ('natural-window physical artifact verification',
             natural_physical/'physical_verification.json'),
            ('natural-window physical summary',natural_physical/'physical_numbers.json'),
        ]:
            if path.exists():
                execution=json.loads(path.read_text(encoding='utf-8'))['execution']
                add(name,execution['wall_s'],execution['cpu_s'],
                    'separate single-process postprocessing; no physical worker CPU is added',
                    str(path.relative_to(HERE)).replace('\\','/'))

    text=(HERE/'out_feedback_counterexamples.txt').read_text(encoding='utf-8')
    def last_number(label):
        return float(re.findall(rf'^{label}=([0-9.]+)$',text,re.MULTILINE)[-1])
    add('exact feedback counterexamples',last_number('wall_seconds'),last_number('cpu_seconds'))
    probe=read('probe_taskcluster_summary.json')
    # The probe preserves its own timing object, including failures where available.
    probe_timing=probe.get('timing',probe.get('execution',{}))
    add('bounded public-queue probe',probe_timing.get('wall_s',probe_timing.get('wall_seconds')),
        probe_timing.get('cpu_s',probe_timing.get('process_cpu_seconds')),
        'see probe summary for exact timing fields and retrieval/cache counts')
    smoke_path=HERE/'physical_smoke'/'summary.json'
    if smoke_path.exists():
        smoke=json.loads(smoke_path.read_text(encoding='utf-8'))
        smoke_cpu=audit_cpu(HERE/'physical_smoke')
        add('synthetic physical smoke check',smoke.get('wall_s'),
            smoke.get('root_cpu_s',0.)+smoke_cpu['worker_cpu_s'],
            'passed v3 QPC occupied-workers fixture; root CPU plus worker cumulative CPU through last finish',
            'physical_smoke/summary.json',details=smoke_cpu)
    output={'recorded_at_utc':datetime.now(timezone.utc).isoformat(),
            'plan_created_utc':datetime.fromtimestamp((HERE/'PLAN.md').stat().st_ctime,timezone.utc).isoformat(),
            'elapsed_since_plan_creation_s':time.time()-(HERE/'PLAN.md').stat().st_ctime,
            'experiments':rows,
            'summed_instrumented_cpu_s':sum(
                r['cpu_s'] or 0. for r in rows if r['included_in_instrumented_cpu_sum']),
            'summed_instrumented_experiment_wall_s':sum(
                r['wall_s'] or 0. for r in rows if r['included_in_instrumented_wall_sum']),
            'estimated_wall_s_excluded_from_instrumented_sum':sum(
                r['wall_s'] or 0. for r in rows
                if r['wall_s'] is not None and not r['included_in_instrumented_wall_sum']),
            'missing_timing_rows':[r['experiment'] for r in rows if r['cpu_s'] is None or r['wall_s'] is None],
            'known_timing_rows':[r['experiment'] for r in rows if r['timing_status']=='known'],
            'unknown_timing_rows':[r['experiment'] for r in rows if r['timing_status']=='unknown'],
            'partial_timing_rows':[r['experiment'] for r in rows if r['timing_status']=='partial'],
            'limitations':['command launcher and interpreter startup are not fully instrumented',
                           'read-only inspection, writing and public documentation browsing CPU are not instrumented',
                           'elapsed wall includes analysis and review between sequential experiments',
                           'no resource usage from other concurrent research jobs is included'],
            'ledger_execution':{'wall_s':time.perf_counter()-started,'cpu_s':time.process_time()-cpu}}
    text=json.dumps(output,indent=2,allow_nan=False)+'\n'
    (HERE/'resource_ledger.json').write_text(text,encoding='utf-8')
    (HERE/'out_resource_ledger.txt').write_text(text,encoding='utf-8')
    print(text)


if __name__=='__main__':
    main()
