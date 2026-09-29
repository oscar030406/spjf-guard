"""Audit the sole authorised trace; retain all executed positive service, including failures."""
import sys
sys.dont_write_bytecode=True
from common import *
import gzip
import re

def occupancy(d,start,end,k):
    n=int(np.ceil((end-start)/3600))
    hours=np.arange(n+1)*3600+start
    s=d.submit.values+d.wait.values; e=s+d.run.values
    events=np.r_[s,e]; changes=np.r_[np.ones(len(s),dtype=np.int64),-np.ones(len(e),dtype=np.int64)]
    order=np.lexsort((changes,events)); events=events[order]; changes=changes[order]
    uniq,at=np.unique(events,return_index=True); levels=np.cumsum(np.add.reduceat(changes,at))
    points=np.unique(np.r_[hours,uniq[(uniq>start)&(uniq<end)],end]); points=points[(points>=start)&(points<=end)]
    j=np.searchsorted(uniq,points[:-1],side='right')-1
    level=np.where(j>=0,levels[np.maximum(j,0)],0)
    duration=np.diff(points)
    h=np.minimum(((points[:-1]-start)//3600).astype(int),n-1)
    work=np.bincount(h,weights=level*duration,minlength=n)
    exposure=np.minimum(3600,end-hours[:-1])
    return work/exposure/k, dict(max_concurrency=int(levels.max()),time_at_or_above_nominal=float(duration[level>=k].sum()/(end-start)),mean_occupancy=float(np.sum(level*duration)/(end-start)))

def main():
    log,finish=log_start('audit')
    dump('protocol.json',protocol())
    with gzip.open(RAW,'rt') as f: header=''.join(line for line in f if line.startswith(';'))
    (HERE/'swf_header.txt').write_text(header,encoding='utf-8')
    log('HEADER',header)
    d=pd.read_csv(RAW,sep=r'\s+',comment=';',header=None,names=COLS)
    d['input_index']=np.arange(len(d)); origin=int(d.submit.min())
    d['a']=d.submit-origin; d['done']=d.a+d.wait+d.run
    d['L']=d.queue.map(QUEUE_L)
    audit={'raw_n':len(d),'origin_submit':origin,'span_days':float(d.a.max()/DAY),
           'status_raw':d.status.value_counts().to_dict(),'zero_run':int((d.run==0).sum()),'negative_run':int((d.run<0).sum()),
           'negative_wait':int((d.wait<0).sum()),'negative_submit':int((d.submit<0).sum()),
           'queue_requested_time':d.groupby(['part','queue','time_req']).size().reset_index(name='n').to_dict('records')}
    filters=[]
    for name,ok in [('known status 0/1/5',d.status.isin([0,1,5])),('positive runtime',d.run>0),('nonnegative wait and submit',(d.wait>=0)&(d.submit>=0)),('one allocated processor',d.nproc==1),('known queue/partition',d.L.notna()&d.part.isin([1,2,3]))]:
        before=len(d); d=d.loc[ok.loc[d.index]].copy(); filters.append(dict(filter=name,before=before,removed=before-len(d),after=len(d)))
    start=origin; end=int(d.submit.max()+1)
    timeseries=[]; concurrency=[]
    for pool,part,k in [('all',[1,2,3],140),('CE1',[2],84),('old_CE2',[1,3],56)]:
        sub=d[d.part.isin(part)]; util,conc=occupancy(sub,start,end,k); conc['pool']=pool; concurrency.append(conc)
        counts=np.bincount(((sub.submit-start)//3600).astype(int),minlength=len(util))
        timeseries.append(pd.DataFrame(dict(pool=pool,hour=np.arange(len(util)),log_day=np.arange(len(util))/24,recorded_utilisation=util,arrivals=counts)))
    pd.concat(timeseries).to_csv(HERE/'hourly_audit.csv',index=False)
    audit['concurrency']=concurrency
    raw_usable=d.copy()
    before=len(d); lo,hi=np.array(OUTAGE)*DAY
    submit_out=(d.a>=lo)&(d.a<hi)
    # Remove jobs whose observed queue/service interval crosses the excluded incident.
    intersects=(d.a<hi)&(d.done>lo)
    audit['outage_submit_only_removed']=int(submit_out.sum())
    audit['additional_outage_overlap_removed']=int((intersects&~submit_out).sum())
    d=d.loc[~(submit_out|intersects)].copy()
    filters.append(dict(filter='arrival or observed lifetime intersects outage [138d,153d)',before=before,removed=before-len(d),after=len(d)))
    d['c']=np.minimum(d.run,d.L).astype('int64')
    audit['exceeds_queue_L']=int((d.run>d.L).sum()); audit['excess_runtime_seconds']=int((d.run-d.c).sum())
    audit['exceeds_by_queue']=d.assign(exceeds=d.run>d.L).groupby('queue').exceeds.sum().to_dict()
    audit['filters']=filters; audit['status_retained']=d.status.value_counts().to_dict()
    audit['requested_time_mismatch']=int((d.time_req!=d.L).sum()); audit['exe_counts']=d.exe.value_counts().to_dict()
    d['pool']=np.where(d.part==2,'CE1','old_CE2'); d['segment']=(d.a>=hi).astype(int)
    d=d.sort_values(['a','input_index'],kind='stable').reset_index(drop=True)
    d.to_csv(HERE/'jobs.csv',index=False)
    rows=[]
    for pool in ['all',*NOMINAL]:
        p=d if pool=='all' else d[d.pool==pool]
        for queue in ['all',*sorted(p.queue.unique())]:
            s=p if queue=='all' else p[p.queue==queue]
            rows.append(dict(pool=pool,queue=queue,L=259200 if queue=='all' else QUEUE_L[queue],**stats(s.wait),**tails(s.c),raw_top1=tails(s.run)['top1'],raw_top5=tails(s.run)['top5'],exceeds=int((s.run>s.L).sum())))
    pd.DataFrame(rows).to_csv(HERE/'queue_audit.csv',index=False)
    # SWF epoch comes from the header, calendar displayed in the declared Europe/Paris zone.
    epoch=int(re.search(r'UnixStartTime:\s*(\d+)',header).group(1))
    dt=pd.to_datetime(epoch+d.submit,unit='s',utc=True).dt.tz_convert('Europe/Paris')
    for key,values in [('hour_of_day',dt.dt.hour),('day_of_week',dt.dt.dayofweek)]:
        d.assign(calendar=values).groupby('calendar').agg(n=('job','size'),work_s=('c','sum')).to_csv(HERE/f'{key}.csv')
    hour=np.arange(int(np.ceil((d.a.max()+1)/3600)))
    valid=(hour*3600<lo)|(hour*3600>=hi)
    counts=np.bincount((d.a//3600).astype(int),minlength=len(hour))[valid]
    audit['arrival_hourly_dispersion']=float(counts.var(ddof=1)/counts.mean())
    audit['arrival_hourly_max']=int(counts.max()); audit['arrival_hourly_mean']=float(counts.mean())
    audit['calendar_epoch']=epoch
    dump('audit.json',audit)
    log(json.dumps(audit,indent=2)); log(pd.DataFrame(rows).to_string(index=False)); finish()

if __name__=='__main__': main()
