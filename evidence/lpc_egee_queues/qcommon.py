"""Frozen protocol and shared helpers for the per-queue LPC-EGEE study.

Adapted from `evidence/lpc_egee/common.py`, which is left untouched. The
difference that matters: the unit of analysis is a (partition, queue) cell, each
with its own documented walltime limit L, its own fitted effective capacity, its
own predictor and its own replay. Nothing is selected on the test part.
"""
import os
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
PREV = ROOT / 'prechecks' / 'lpc_egee'
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
SPLIT_DAY = 120           # inherited chronological split, days after the first cleaned arrival
OUTAGE = (138, 153)       # ORIGINAL SWF submit/86400, the corrected clock of the previous audit
SEED = 3
BOOT_SEED = 20260921
BOOT_N = 2000
PROMISES = [3.5, 5.0, 10.0]
QUEUE_L = {1: 900, 2: 7200, 3: 86400, 4: 129600, 5: 259200, 6: 3600}
QUEUE_NAME = {1: 'test', 2: 'short', 3: 'long', 4: 'day', 5: 'infinite', 6: 'batch'}
# The three SWF partitions are three machines in time, not two. clrglop195 (partition 1)
# is the small early cluster; it stops on day 76.8 and owns no held-out arrival, so it is
# audited and then excluded from every fit and replay. The previous study merged it into
# "old_CE2", which is why a short-queue capacity of 2 CPUs was fitted there.
POOL_OF_PART = {1: 'GLOP195', 2: 'CE1', 3: 'CE2'}
NOMINAL = {'CE1': 84, 'CE2': 56}         # documented CPUs of the two held-out partitions
EARLY_POOL = 'GLOP195'
MIN_FIT_ROWS = 500                       # below this a capacity fit is reported but not trusted
SHORT_QUEUES = [1, 6, 2]                 # 900 s, 3,600 s, 7,200 s: the validation focus
COLS = ['job', 'submit', 'wait', 'run', 'nproc', 'cpu_used', 'mem_used', 'nproc_req', 'time_req',
        'mem_req', 'status', 'uid', 'gid', 'exe', 'queue', 'part', 'prev_job', 'think']
RAW = PREV / 'raw' / 'LPC-EGEE-2004-1.2-cln.swf.gz'


def dump(name, value):
    (HERE / name).write_text(
        json.dumps(value, indent=2, default=lambda x: x.item() if isinstance(x, np.generic) else str(x)),
        encoding='utf-8')


def log_start(name):
    f = open(HERE / f'out_{name}.txt', 'a', encoding='utf-8')
    started = time.perf_counter()
    cpu = time.process_time()

    def log(*args):
        s = ' '.join(map(str, args))
        print(s, flush=True)
        f.write(s + '\n')
        f.flush()

    log('START', pd.Timestamp.now(tz='UTC').isoformat())
    log('SCRIPT_SHA256', hashlib.sha256((HERE / f'{name}.py').read_bytes()).hexdigest())

    def finish():
        result = dict(stage=name, wall_s=time.perf_counter() - started, cpu_s=time.process_time() - cpu)
        log('TIMING', json.dumps(result))
        f.close()
        with open(HERE / 'timings.jsonl', 'a', encoding='utf-8') as out:
            out.write(json.dumps(result) + '\n')
    return log, finish


def load():
    return pd.read_csv(HERE / 'jobs.csv')


def stats(x):
    x = np.asarray(x, np.float64)
    if not len(x):
        return dict(n=0, mean=np.nan, p50=np.nan, p90=np.nan, p99=np.nan, max=np.nan)
    return dict(n=len(x), mean=float(np.mean(x)), p50=float(np.quantile(x, .5)),
                p90=float(np.quantile(x, .9)), p99=float(np.quantile(x, .99)), max=float(np.max(x)))


def tails(x):
    x = np.sort(np.asarray(x, np.float64))[::-1]
    total = x.sum()
    return {f'top{int(p * 100)}': float(x[:max(1, int(round(len(x) * p)))].sum() / total) if total > 0 else np.nan
            for p in [.01, .05]}


def cells(df):
    """(pool, queue, L) for every non-empty walltime-class sub-pool, in a fixed order."""
    out = []
    for pool in NOMINAL:
        for queue in sorted(df.queue.unique()):
            m = (df.pool.values == pool) & (df.queue.values == queue)
            if m.sum():
                out.append((pool, int(queue), int(df.L.values[m].max())))
    return out


def protocol():
    return dict(
        unit='one pool per (physical partition, queue) walltime class; L is that class documented limit',
        partitions='SWF partitions 2 (CE1, 84 CPUs) and 3 (CE2, 56 CPUs); partition 1 (clrglop195) '
                   'stops on day 76.8 and owns no held-out arrival, so it is audited and then excluded',
        min_fit_rows=MIN_FIT_ROWS,
        split_days_after_first_cleaned_submit=SPLIT_DAY,
        outage_original_SWF_days_half_open=list(OUTAGE),
        seed=SEED, bootstrap_seed=BOOT_SEED, bootstrap_replicates=BOOT_N,
        busy_definition='arrival-hour count >= that cell own fit-part 90th percentile over all non-outage hours, at least 1',
        k_grid='every integer 1..nominal CPUs of the host partition, independently per cell',
        capacity_objective='abs(log((sim_mean+1)/(rec_mean+1))) + abs(log((sim_p90+1)/(rec_p90+1)))',
        fit_visibility='submit < cutoff and recorded completion < cutoff',
        cap='service = min(recorded run, documented partition/queue wall limit); CE2 short 5400 s',
        theorem_L='the cell own queue limit, NOT the pool maximum: this is the whole point of the study',
        promises_L=PROMISES,
        shapes={'constant': 'B0=Bmax, eta=0',
                'age_3.5L_and_5L': 'B0=k*L/4, eta=0.5 (the paper 5L development point, reused at 3.5L)',
                'age_10L': 'B0=k*L/2, eta=0.75 (the paper 10L development point)'},
        predictor='per-queue LightGBM, package defaults, submission fields plus own-user completion history visible at arrival',
        no_test_selection=True,
        caveat='queues shared the machines of their partition; a per-queue pool is a model we impose, '
               'so the recorded waits of a queue validate the sub-pool model only')
