"""Format report tables directly from the final capacity CSV; no new inference."""
from pathlib import Path
import sys
sys.dont_write_bytecode=True
import csv
import json
import time

HERE=Path(__file__).resolve().parent
DISPLAY_K=(1,2,3,4,5,8,14,20)
GUARDS=('Guard(300)','Guard(600)','Guard(1200)')


def number(value):
    if value is None or value=='':
        return 'undefined'
    x=float(value)
    if abs(x)>=1000:
        return f'{x:,.1f}'
    if abs(x)>=1:
        return f'{x:.2f}'
    return f'{x:.4f}'


def interval(row,point,low,high):
    p=number(row[point])
    if row[low]=='' or row[high]=='':
        return p+' [interval unavailable]'
    return f'{p} [{number(row[low])}, {number(row[high])}]'


def main():
    wall,cpu=time.perf_counter(),time.process_time()
    with (HERE/'capacity_curve.csv').open(encoding='utf-8',newline='') as f:
        rows=list(csv.DictReader(f))
    index={(int(r['k']),r['policy']):r for r in rows}
    lines=['# Capacity tables from the final CSV','',
           'All values average the five overlay-specific deadline-window quantiles. '
           'Intervals in the first table are pointwise paired-week percentile intervals.','',
           '| k | FCFS p99, s [95% interval] | SPJF-E p99, s [95% interval] | Guard(600) p99, s [95% interval] |',
           '|---:|---:|---:|---:|']
    for k in DISPLAY_K:
        values=[interval(index[k,p],'p99_deadline_s','p99_deadline_lo','p99_deadline_hi') for p in ('FCFS','SPJF-E','Guard(600)')]
        lines.append('| '+str(k)+' | '+' | '.join(values)+' |')
    lines+=['','Positive D = FCFS p99 minus policy p99. Brackets below are the single '
            '95% simultaneous band over all 80 predeclared capacity-policy coordinates.','',
            '| k | Guard(300) D, s [simultaneous band] | Guard(600) D, s [simultaneous band] | Guard(1200) D, s [simultaneous band] |',
            '|---:|---:|---:|---:|']
    for k in DISPLAY_K:
        values=[interval(index[k,p],'absolute_p99_improvement_s','simultaneous_improvement_lo','simultaneous_improvement_hi') for p in GUARDS]
        lines.append('| '+str(k)+' | '+' | '.join(values)+' |')
    lines+=['','The next table focuses on Guard(600). Maxima are observed across all jobs '
            'and all five overlays, with no population-maximum confidence claim. '
            'Harm restricts to jobs whose same-input FCFS wait is at most 1 s.','',
            '| k | Gap closed [pointwise 95% interval] | Maximum excess, s | Harm, s | FCFS p99 / theorem floor | FCFS p99 / G |',
            '|---:|---:|---:|---:|---:|---:|']
    for k in DISPLAY_K:
        r=index[k,'Guard(600)']
        vals=[interval(r,'gap_closed','gap_closed_lo','gap_closed_hi')]+[
            number(r[key]) for key in ('max_excess_s','harm_s','fcfs_p99_div_floor','fcfs_p99_div_G')]
        lines.append('| '+str(k)+' | '+' | '.join(vals)+' |')
    payload='\n'.join(lines)+'\n'
    (HERE/'report_capacity_tables.md').write_text(payload,encoding='utf-8')
    timing={'wall_s':time.perf_counter()-wall,'cpu_s':time.process_time()-cpu}
    (HERE/'out_report_capacity_tables.txt').write_text(json.dumps(timing)+'\n'+payload,encoding='utf-8')
    print(payload)


if __name__=='__main__':
    main()
