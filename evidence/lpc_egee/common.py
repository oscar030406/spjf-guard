"""Frozen protocol and utilities for the LPC-EGEE study."""
import os
import sys
from pathlib import Path
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
for key in ('NUMBA_NUM_THREADS', 'OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[key] = '4'
os.environ['NUMBA_CACHE_DIR'] = str(HERE / 'cache' / 'numba')
sys.path.insert(0, str(ROOT / 'src'))
import json
import time
import hashlib
import numpy as np
import pandas as pd
DAY = 86400
SPLIT_DAY = 120
OUTAGE = (138, 153)  # ORIGINAL SWF submit/86400, NOT days after cleaned trace start
SEED = 3
BOOT_SEED = 20260921
BOOT_N = 2000
QUEUE_L = {1:900, 2:7200, 3:86400, 4:129600, 5:259200, 6:3600}
QUEUE_NAME = {1:'test', 2:'short', 3:'long', 4:'day', 5:'infinite', 6:'batch'}
NOMINAL = {'CE1':84, 'old_CE2':56}
COLS = ['job','submit','wait','run','nproc','cpu_used','mem_used','nproc_req','time_req','mem_req','status','uid','gid','exe','queue','part','prev_job','think']
RAW = HERE / 'raw' / 'LPC-EGEE-2004-1.2-cln.swf.gz'

def dump(name, value):
    (HERE/name).write_text(json.dumps(value, indent=2, default=lambda x: x.item() if isinstance(x,np.generic) else str(x)), encoding='utf-8')

def log_start(name):
    f = open(HERE/f'out_{name}.txt','a',encoding='utf-8')
    started = time.perf_counter()
    cpu = time.process_time()
    def log(*args):
        s = ' '.join(map(str,args)); print(s,flush=True); f.write(s+'\n'); f.flush()
    log('START',pd.Timestamp.now(tz='UTC').isoformat())
    log('SCRIPT_SHA256',hashlib.sha256((HERE/f'{name}.py').read_bytes()).hexdigest())
    def finish():
        result = dict(stage=name, wall_s=time.perf_counter()-started, cpu_s=time.process_time()-cpu)
        log('TIMING',json.dumps(result)); f.close()
        with open(HERE/'timings.jsonl','a',encoding='utf-8') as out: out.write(json.dumps(result)+'\n')
    return log, finish

def load():
    return pd.read_csv(HERE/'jobs.csv')

def stats(x):
    x=np.asarray(x)
    return dict(n=len(x),mean=float(np.mean(x)),p50=float(np.quantile(x,.5)),p90=float(np.quantile(x,.9)),p99=float(np.quantile(x,.99)),max=float(np.max(x)))

def tails(x):
    x=np.sort(np.asarray(x))[::-1]
    return {f'top{int(p*100)}':float(x[:max(1,int(round(len(x)*p)))].sum()/x.sum()) for p in [.01,.05]}

def segments(df):
    for pool in NOMINAL:
        for segment in [0,1]:
            ids=np.flatnonzero((df.pool.values==pool)&(df.segment.values==segment))
            if len(ids): yield pool,segment,ids

def protocol():
    return dict(split_days_after_first_cleaned_submit=SPLIT_DAY,outage_original_SWF_days_half_open=OUTAGE,seed=SEED,bootstrap_seed=BOOT_SEED,bootstrap_replicates=BOOT_N,
                busy_definition='arrival count >= fit-part 90th percentile of ALL hourly bins, nonzero arrivals',
                k_grid='every integer 1..nominal independently per physical pool',
                capacity_objective='abs(log((sim_mean+1)/(rec_mean+1))) + abs(log((sim_p90+1)/(rec_p90+1)))',
                fit_visibility='submit < cutoff and recorded completion < cutoff',
                shapes={'constant':'B0=Bmax, eta=0','age_3.5L_and_5L':'B0=k*L/4, eta=0.5 (paper 5L point transferred to 3.5L)','age_10L':'B0=k*L/2, eta=0.75 (paper 10L point)'},
                promises_L=[3.5,5,10],primary='two disjoint physical pools; queues share each pool; k held fixed on test',
                cap='min(recorded run, documented partition/queue wall limit); CE2 short 5400 s, other short 7200 s; theorem uses maximum queue limit 259200 s',
                history='own-user completions at recorded submit+wait+raw_run <= arrival; frozen scores, open-loop feature stream',
                no_test_selection=True)
