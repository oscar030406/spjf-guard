"""Capacity pilot: all jobs, one development overlay, no policy selection."""
import sys
sys.dont_write_bytecode = True
import time
import json
from common import HERE, TERMS, development_overlay, save_json, timing, np
from spjf_guard.sim import simulate
from spjf_guard.sim.policy import fcfs, sjf, spjf, guard
from spjf_guard.sim.bounds import assert_per_job_bounds

REP = 0
CAPACITIES = [1, 4, 8, 16, 32, 64, 128]
GUARD_CAPACITY = 4
GUARD_G = 600.
WINDOW = 1 << 22


def main():
    t, c = time.perf_counter(), time.process_time()
    tr, lab = development_overlay(REP)
    print('loaded', len(tr), 'jobs', 'deadline', int(lab['in_window'].sum()), flush=True)
    a = tr.arrival_us
    s = tr.service_us
    # Infinite-server occupancy: exact no-wait threshold. Completions precede arrivals.
    finishes = np.sort(a + s)
    occupancy = np.arange(1, len(a) + 1) - np.searchsorted(finishes, a, side='right')
    peak = int(occupancy.max())
    bins = ((a - a[0]) // 3_600_000_000).astype(np.int64)
    work = np.bincount(bins, weights=s / 1e6)
    week = ((a - a[0]) // 604_800_000_000).astype(np.int64)
    print('no_wait_capacity', peak, 'busy_hour_work', float(work.max()), 'weeks', int(week.max()+1), flush=True)
    rows = []
    for k in sorted(set(CAPACITIES + [peak - 1, peak])):
        if k < 1:
            continue
        t0 = time.perf_counter()
        f = simulate(tr, fcfs(), k, window=WINDOW)
        row = {'k': k, 'p99_deadline_s': float(np.quantile(f.wait_s[lab['in_window']], .99)),
               'p99_all_s': float(np.quantile(f.wait_s, .99)), 'max_wait_s': float(f.wait_s.max()),
               'positive_wait_jobs': int((f.wait_us > 0).sum()), 'runtime_s': time.perf_counter()-t0}
        rows.append(row)
        print(json.dumps(row), flush=True)
        if k == GUARD_CAPACITY:
            for p in [sjf(), spjf('tweedie', 'SPJF-E'), guard(GUARD_G, k, 60., 120*k/4, .75, 'tweedie')]:
                t0 = time.perf_counter()
                r = simulate(tr, p, k, window=WINDOW)
                checked = assert_per_job_bounds(r, f.wait_us, p, k, 60.) if p.wrapper == 'work' else 0
                print(json.dumps({'policy': p.name, 'k': k, 'p99_deadline_s': float(np.quantile(r.wait_s[lab['in_window']], .99)), 'bound_checks': checked, 'forced': r.n_forced, 'runtime_s': time.perf_counter()-t0}), flush=True)
    out = {'terms': TERMS, 'rep': REP, 'n': len(tr), 'n_deadline': int(lab['in_window'].sum()),
           'span_s': float((a[-1]-a[0])/1e6), 'busy_hour_work_s': float(work.max()),
           'no_wait_capacity': peak, 'n_weeks': int(week.max()+1), 'fcfs': rows, **timing(t,c)}
    save_json('pilot.json', out)
    print(json.dumps(out), flush=True)


if __name__ == '__main__':
    main()
