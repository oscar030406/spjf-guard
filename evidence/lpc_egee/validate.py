"""Fit physical-pool effective capacities before the chronological cutoff."""
import sys
sys.dont_write_bytecode=True
from common import *
from numba import njit
import heapq
from spjf_guard.sim.runner import Trace, simulate
from spjf_guard.sim.policy import fcfs, sjf, spjf, fixed, guard, skip, MICROS
from spjf_guard.sim.reference import brute_guard, kiefer_wolfowitz

@njit(cache=True)
def fast_fcfs(a,c,k):
    free=[np.int64(0) for _ in range(k)]
    w=np.zeros(len(a),np.int64)
    for i in range(len(a)):
        t=max(a[i],heapq.heappop(free))
        w[i]=t-a[i]
        heapq.heappush(free,t+c[i])
    return w

def fcfs_frame(d,k,service='c'):
    w=np.zeros(len(d),np.int64)
    for seg in sorted(d.segment.unique()):
        m=d.segment.values==seg
        w[m]=fast_fcfs(d.a.values[m].astype(np.int64),d[service].values[m].astype(np.int64),k)
    return w

def metrics(d,w,mask):
    r=d.wait.values[mask]; s=w[mask]
    h=pd.DataFrame(dict(hour=d.a.values[mask]//3600,rec=r,sim=s)).groupby('hour').mean()
    out={f'recorded_{key}':v for key,v in stats(r).items()}
    out.update({f'sim_{key}':v for key,v in stats(s).items()})
    out.update(hourly_pearson=float(h.rec.corr(h.sim)),n_hours=len(h),
               job_spearman=float(pd.Series(r).corr(pd.Series(s),method='spearman')),
               median_abs_error=float(np.median(np.abs(s-r))))
    for q in ['mean','p50','p90','p99']:
        out[q+'_ratio']=out['sim_'+q]/out['recorded_'+q] if out['recorded_'+q] else np.nan
    return out,h

def toy_check(log):
    rng=np.random.default_rng(SEED); cases=0
    for k in [1,2,4,7]:
        for rep in range(5):
            a=np.sort(rng.integers(0,30,80)); c=rng.integers(1,11,80)
            score=rng.integers(0,5,80).astype(float)
            trace=Trace.from_seconds(a,c,{'E':score},limit_s=10)
            for pol in [fcfs(),sjf(),spjf('E'),fixed(50,k,10,'E'),guard(50,k,10,k*10/4,.5,'E'),skip(50,k,10,'E')]:
                out=simulate(trace,pol,k,window=128)
                if pol.name=='FCFS':
                    ref=kiefer_wolfowitz(trace.arrival_us,trace.service_us,k)
                    assert np.array_equal(fast_fcfs(a,c,k)*MICROS,out.wait_us)
                else:
                    ref,order=brute_guard(trace.arrival_us,trace.service_us,trace.score_for(pol.score_key),k,
                        b0_us=pol.b0_us if pol.wrapper!='none' else 10**15,
                        eta_k=pol.eta_k,bmax_us=pol.bmax_us,skip_count=pol.skip_count)
                    assert np.array_equal(order,out.dispatch_index),pol.name
                assert np.array_equal(ref,out.wait_us),pol.name
                cases+=1
    log('TOY EXACT AGREEMENT',cases,'policy instances, ties/completions/arrivals, k=1,2,4,7')

def main():
    log,finish=log_start('validate'); toy_check(log)
    d=load(); cut=SPLIT_DAY*DAY
    audit=json.loads((HERE/'audit.json').read_text())
    epoch=audit['calendar_epoch']+audit['origin_submit']
    march=int(pd.Timestamp('2005-03-07',tz='Europe/Paris').timestamp())-epoch
    rows=[]; search=[]; fitted={}; busy={}; all_w=np.zeros(len(d),np.int64)
    for pool,nom in NOMINAL.items():
        ids=np.flatnonzero(d.pool.values==pool); p=d.iloc[ids]
        fit=(p.a.values<cut)&(p.done.values<cut); test=p.a.values>=cut
        # Simulating only the prefix prevents future arrivals or completions entering fitting.
        prefix=p[p.a<cut]; fit_prefix=prefix.done.values<cut
        rec=prefix.wait.values[fit_prefix]
        candidates=[]
        for k in range(1,nom+1):
            w=fcfs_frame(prefix,k)[fit_prefix]
            obj=abs(np.log((w.mean()+1)/(rec.mean()+1)))+abs(np.log((np.quantile(w,.9)+1)/(np.quantile(rec,.9)+1)))
            candidates.append((obj,k))
            search.append(dict(pool=pool,k=k,objective=obj,n_fit=int(fit.sum()),sim_mean=w.mean(),recorded_mean=rec.mean(),sim_p90=np.quantile(w,.9),recorded_p90=np.quantile(rec,.9)))
        _,kbest=min(candidates); fitted[pool]=int(kbest)
        counts=np.bincount((prefix.a//3600).astype(int),minlength=SPLIT_DAY*24)
        hour_mid=(np.arange(len(counts))+.5)*3600+audit['origin_submit']
        valid=(hour_mid<OUTAGE[0]*DAY)|(hour_mid>=OUTAGE[1]*DAY)
        busy[pool]=float(np.quantile(counts[valid],.9))
        log('FROZEN',pool,'k',kbest,'nominal',nom,'fit',fit.sum(),'test',test.sum(),'busy arrivals/hour',busy[pool])
        for variant,k,service in [('fitted',kbest,'c'),('nominal',nom,'c'),('raw_service_sensitivity',kbest,'run')]:
            w=fcfs_frame(p,k,service)
            if variant=='fitted': all_w[ids]=w
            for name,mask in [('fit',fit),('test',test),('test_before_queue_ceilings',test&(p.a.values<march)),('test_after_queue_ceilings',test&(p.a.values>=march)),('test_drop_first_3_days',p.a.values>=(cut+3*DAY))]:
                if not mask.any(): continue
                result,h=metrics(p,w,mask)
                row=dict(pool=pool,variant=variant,part=name,k=k,**result); rows.append(row)
                if name=='test':
                    log(json.dumps(row)); h.to_csv(HERE/f'validation_hourly_{pool}_{variant}.csv')
        # Exact full-trace agreement of fast fitting routine with production kernel.
        for seg in p.segment.unique():
            s=p[p.segment==seg]
            trace=Trace.from_seconds(s.a,s.c,limit_s=259200)
            out=simulate(trace,fcfs(),kbest,window=1<<int(len(s)).bit_length())
            assert np.array_equal(out.wait_us,fcfs_frame(s,kbest)*MICROS)
        log('FULL FCFS EXACT AGREEMENT',pool,len(p))
    dump('capacity.json',dict(k=fitted,nominal=NOMINAL,busy_arrivals_per_hour=busy,split_seconds=cut,
        split_utc=pd.Timestamp(epoch+cut,unit='s',tz='UTC').isoformat(),queue_ceiling_change_seconds=march,
        interpretation='k is an FCFS effective-capacity fit; held-out agreement must be evaluated, not presumed'))
    pd.DataFrame(rows).to_csv(HERE/'validation.csv',index=False)
    pd.DataFrame(search).to_csv(HERE/'capacity_grid.csv',index=False)
    np.save(HERE/'fcfs_wait.npy',all_w)
    # Per-queue rows are cohorts within the physical pool, not invented dedicated sub-pools.
    applicability=[]
    for period,m in [('all',np.ones(len(d),bool)),('test',d.a.values>=cut)]:
        for pool in ['all',*NOMINAL]:
            mp=m if pool=='all' else m&(d.pool.values==pool)
            for q in ['all',*sorted(d.loc[mp,'queue'].unique())]:
                mq=mp if q=='all' else mp&(d.queue.values==q)
                p=d[mq]; wf=all_w[mq]; L=int(p.L.max())
                floor=max((3-2/fitted[x])*259200 for x in p.pool.unique())
                descriptive_floor=max((3-2/fitted[x])*L for x in p.pool.unique())
                tail=tails(p.c)
                applicability.append(dict(period=period,pool=pool,queue=q,n=len(p),L_queue_max=L,L_theorem=259200,
                    fcfs_p99=float(np.quantile(wf,.99)),p99_over_L_queue=float(np.quantile(wf,.99)/L),
                    p99_over_L_pool=float(np.quantile(wf,.99)/259200),floor_seconds=floor,
                    condition1=bool(np.quantile(wf,.99)>floor),queue_L_only_diagnostic=bool(np.quantile(wf,.99)>descriptive_floor),
                    condition2_proxy_25pct=bool(tail['top1']>=.25),**tail))
    pd.DataFrame(applicability).to_csv(HERE/'applicability.csv',index=False)
    finish()

if __name__=='__main__': main()
