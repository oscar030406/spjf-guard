"""Exposure-normalised arrival audit and replay feature-availability diagnostics."""
import sys
sys.dont_write_bytecode=True
from common import *
from audit import occupancy

def main():
    log,finish=log_start('supplement'); d=load(); au=json.loads((HERE/'audit.json').read_text())
    origin=au['origin_submit']; epoch=au['calendar_epoch']; end=int(d.submit.max()+1)
    lo,hi=np.array(OUTAGE)*DAY
    # Minute-grid exposure, exact clipping at both ends; exposure normalisation, not a new filter.
    edges=np.unique(np.r_[origin,np.arange(origin//60*60+60,end,60),lo,hi,end])
    edges=edges[(edges>=origin)&(edges<=end)]; mid=(edges[:-1]+edges[1:])/2
    valid=(mid<lo)|(mid>=hi); dt=pd.to_datetime(epoch+mid,unit='s',utc=True).tz_convert('Europe/Paris')
    for name,values in [('hour_of_day',dt.hour),('day_of_week',dt.dayofweek)]:
        exposure=pd.DataFrame(dict(calendar=values,seconds=np.diff(edges)*valid)).groupby('calendar').seconds.sum()
        counts=pd.read_csv(HERE/f'{name}.csv').set_index('calendar')
        counts['exposure_hours']=exposure/3600; counts['arrivals_per_exposed_hour']=counts.n/counts.exposure_hours
        counts.to_csv(HERE/f'{name}_normalised.csv')
        log(name, 'rate peak/trough',float(counts.arrivals_per_exposed_hour.max()/counts.arrivals_per_exposed_hour.min()),
            'peak',int(counts.arrivals_per_exposed_hour.idxmax()),'trough',int(counts.arrivals_per_exposed_hour.idxmin()))
    rows=[]; hours=[]
    for pool,k in [('all',140),*NOMINAL.items()]:
        p=d if pool=='all' else d[d.pool==pool]
        util,conc=occupancy(p,origin,end,k)
        hourstart=origin+np.arange(len(util))*3600
        valid=(hourstart+3600<=lo)|(hourstart>=hi)
        counts=np.bincount(((p.submit-origin)//3600).astype(int),minlength=len(util))
        offered=np.bincount(((p.submit-origin)//3600).astype(int),weights=p.c,minlength=len(util))/(k*3600)
        rows.append(dict(pool=pool,k=k,valid_full_hours=int(valid.sum()),util_mean=float(util[valid].mean()),
            util_p50=float(np.quantile(util[valid],.5)),util_p90=float(np.quantile(util[valid],.9)),util_max=float(util[valid].max()),
            hour_at_or_above_90pct=float((util[valid]>=.9).mean()),**conc))
        hours.append(pd.DataFrame(dict(pool=pool,original_swf_hour=hourstart/3600,valid=valid,utilisation=util,arrivals=counts,offered_work_ratio=offered)))
    pd.concat(hours).to_csv(HERE/'hourly_cleaned.csv',index=False)
    pd.DataFrame(rows).to_csv(HERE/'utilisation_summary.csv',index=False)
    # A recorded-history replay is causal on the source log, but not necessarily under a new policy.
    # Count arrivals seeing at least one outcome that the counterfactual has not finished yet.
    waits=np.load(HERE/'policy_waits_us.npz'); fc=np.load(HERE/'fcfs_wait.npy'); test=d.a.values>=SPLIT_DAY*DAY
    a=d.a.values; recdone=d.done.values; user=d.uid.values
    checks=[]
    for name in ['FCFS','SPJF-E','Age-5L']:
        w=fc.astype(float); w[test]=waits[name]/1e6; simdone=a+w+d.c.values
        # A difference array of bad-history intervals per user, queried at that user's arrivals.
        affected=np.zeros(len(d),bool)
        for u in np.unique(user):
            ids=np.flatnonzero(user==u); bad=(simdone[ids]>recdone[ids])
            starts=np.sort(recdone[ids][bad]); ends=np.sort(simdone[ids][bad])
            count=np.searchsorted(starts,a[ids],side='right')-np.searchsorted(ends,a[ids],side='right')
            affected[ids]=count>0
        checks.append(dict(policy=name,n_test=int(test.sum()),affected_rows=int((affected&test).sum()),
            affected_fraction=float(affected[test].mean()),
            meaning='source-log history contains an outcome unfinished under this counterfactual; static-only comparator has no such dependency'))
    pd.DataFrame(checks).to_csv(HERE/'history_counterfactual_diagnostic.csv',index=False)
    log('RECORDED-HISTORY VERSUS COUNTERFACTUAL',checks)
    log('UTILISATION',rows)
    finish()

if __name__=='__main__': main()
