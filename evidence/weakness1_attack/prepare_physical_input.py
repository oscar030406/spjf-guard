"""Freeze the preselected physical input and estimate execution/logging resources."""
from pathlib import Path
import sys
sys.dont_write_bytecode = True
import json
import time
import physical_service as physical
import numpy as np

HERE = Path(__file__).resolve().parent


def main():
    start,cpu=time.perf_counter(),time.process_time()
    data,metadata,digest=physical.prepare_input()
    from spjf_guard.sim import Trace, simulate
    from spjf_guard.sim.policy import fcfs
    from spjf_guard.sim.bounds import assert_per_job_bounds
    trace=Trace(data['target_release_offset_ns']//1000,
                data['requested_service_ns']//1000,
                {physical.SCORE_KEY:data['score']},limit_s=physical.FORMAL_LIMIT_S)
    baseline=simulate(trace,fcfs(),physical.K)
    estimates=[]
    for name in physical.POLICIES:
        policy=physical.policy_object(name)
        result=baseline if name=='FCFS' else simulate(trace,policy,physical.K)
        waiting=np.searchsorted(trace.arrival_us,result.start_us,side='right')-result.dispatch_index
        assert int(waiting.min())>=1
        checks=assert_per_job_bounds(result,baseline.wait_us,policy,physical.K,physical.FORMAL_LIMIT_S) if name.startswith('Guard') else 0
        estimates.append({'policy':name,'jobs':len(trace),
            'nominal_physical_makespan_s':max(physical.WINDOW_S,float((result.start_us+trace.service_us).max()/1e6)),
            'nominal_wait_mean_s':float(result.wait_us.mean()/1e6),
            'nominal_wait_p99_s':float(np.quantile(result.wait_us,.99)/1e6),
            'nominal_max_waiting_at_dispatch':int(waiting.max()),
            'nominal_waiting_job_evaluations':int(waiting.sum()),
            'nominal_guard_firings':int(result.n_forced) if name.startswith('Guard') else 0,
            'nominal_bound_checks':int(checks)})
    report={'input':metadata,'input_sha256':digest,
            'selection_unchanged_after_policy_estimates':True,
            'purpose':'resource estimate after the deterministic demand-only selection; no policy-based window selection',
            'nominal_replays':estimates,
            'estimated_three_policy_real_time_s':sum(row['nominal_physical_makespan_s'] for row in estimates),
            'execution':{'wall_s':time.perf_counter()-start,'cpu_s':time.process_time()-cpu}}
    text=json.dumps(report,indent=2,allow_nan=False)+'\n'
    (HERE/'physical_preparation.json').write_text(text,encoding='utf-8')
    print(text)


if __name__=='__main__':
    main()
