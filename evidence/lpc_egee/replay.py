"""Fixed-capacity counterfactual replays and paired week-block intervals."""
import sys
sys.dont_write_bytecode=True
from common import *
from numba import njit
from spjf_guard.sim.runner import Trace, simulate
from spjf_guard.sim.policy import fcfs, spjf, fixed, guard, skip, MICROS
from spjf_guard.sim.bounds import guard_upper_bound, assert_per_job_bounds, in_out, identity_residual

L=259200

def policies(k):
    out=[fcfs(),spjf('oracle','SJF'),spjf('spjf_e','SPJF-E'),spjf('spjf_log','SPJF-log'),spjf('static_e','SPJF-static')]
    for g in [3.5,5.,10.]:
        out.extend([fixed(g*L,k,L,'spjf_e',name=f'Constant-{g:g}L'),
            guard(g*L,k,L,k*L*(.5 if g==10 else .25),.75 if g==10 else .5,'spjf_e',name=f'Age-{g:g}L'),
            skip(g*L,k,L,'spjf_e',name=f'Skip-{g:g}L')])
    return out

@njit(cache=True)
def bootstrap_stats(sorted_w,sorted_week,draws,week_n,week_sum):
    # Exact numpy-style linear quantile of the expanded integer-weight sample.
    out=np.empty((len(draws),2),np.float64)
    for b in range(len(draws)):
        mult=draws[b]; n=0; total=0.
        for h in range(len(mult)):
            n+=mult[h]*week_n[h]; total+=mult[h]*week_sum[h]
        if n==0:
            out[b,0]=np.nan; out[b,1]=np.nan; continue
        pos=.99*(n-1); low=int(np.floor(pos)); high=int(np.ceil(pos)); cum=0; vlo=0.; vhi=0.; got=False
        for i in range(len(sorted_w)):
            count=mult[sorted_week[i]]
            cum+=count
            if cum>low and not got: vlo=sorted_w[i]; got=True
            if cum>high:
                vhi=sorted_w[i]; break
        out[b,0]=vlo+(pos-low)*(vhi-vlo); out[b,1]=total/n
    return out

def ci(values):
    valid=np.isfinite(values)
    if not valid.any(): return np.nan,np.nan,0
    lo,hi=np.quantile(values[valid],[.025,.975])
    return float(lo),float(hi),int(valid.sum())

def main():
    log,finish=log_start('replay'); d=load(); cap=json.loads((HERE/'capacity.json').read_text()); pred=np.load(HERE/'predictions.npz')
    cut=SPLIT_DAY*DAY; test=d.a.values>=cut; warm=~test; n=len(d)
    scores={key:pred[key].copy() for key in ['spjf_e','spjf_log','static_e']}
    scores['oracle']=d.c.values.astype(float)
    # All policies share an FCFS prefix. Pending pre-cutoff jobs keep precedence.
    for key in scores: scores[key][warm]=np.arange(n)[warm]-n-1
    waits={p.name:np.zeros(n,np.int64) for p in policies(2)}
    busy=np.zeros(n,bool); checks=[]; params=[]; dispatch=[]
    for pool,seg,ids in segments(d):
        sub=d.iloc[ids]; k=cap['k'][pool]
        counts=d[d.pool==pool].groupby(d.loc[d.pool==pool,'a']//3600).size()
        busy[ids]=np.array([counts.loc[h]>=cap['busy_arrivals_per_hour'][pool] for h in sub.a.values//3600])
        trace=Trace.from_seconds(sub.a,sub.c,{key:v[ids] for key,v in scores.items()},limit_s=L)
        window=1<<int(len(sub)).bit_length(); f=None
        prefix=np.maximum.accumulate(sub.c.values)
        at_a=prefix[np.searchsorted(sub.a.values,sub.a.values,side='right')-1]
        for pol in policies(k):
            r=simulate(trace,pol,k,window=window); waits[pol.name][ids]=r.wait_us
            if pol.name=='FCFS': f=r
            params.append(dict(pool=pool,segment=int(seg),policy=pol.name,k=k,L=L,b0_s=pol.b0_us/MICROS,
                bmax_s=pol.bmax_us/MICROS,eta=pol.eta_k/k,skip_count=pol.skip_count))
            m=sub.a.values>=cut
            dispatch.append(dict(pool=pool,segment=int(seg),policy=pol.name,n=r.n_dispatch,forced=r.n_forced,
                scope='whole segment including FCFS prefix',fraction=r.fired_fraction))
            if pol.wrapper!='none':
                checked=assert_per_job_bounds(r,f.wait_us,pol,k,L)
                excess=(r.wait_us-f.wait_us)/MICROS
                allowance=guard_upper_bound(f.wait_us,pol,k,L)-f.wait_s
                row=dict(pool=pool,segment=int(seg),policy=pol.name,checked=checked,test_checked=int(m.sum()),
                    violations=int((excess>allowance).sum()),worst_ratio=float(np.max(excess/allowance)),
                    test_worst_ratio=float(np.max(excess[m]/allowance[m])) if m.any() else 0,
                    max_excess_s=float(excess.max()),theoretical_max_s=float(allowance.max()))
                if pol.wrapper=='work':
                    at_s=prefix[np.searchsorted(sub.a.values,r.start_us/MICROS,side='right')-1]
                    term=at_s+(2-2/k)*at_a
                    inst=pol.bmax_us/MICROS/k+term
                    inst=np.minimum(inst,(f.wait_s+pol.b0_us/MICROS/k+term)/(1-pol.eta_k/k)-f.wait_s)
                    assert np.all(excess<inst)
                    row.update(instance_violations=0,instance_worst_ratio=float(np.max(excess/inst)),
                        instance_bound_min=float(inst.min()),instance_bound_max=float(inst.max()))
                wi,wo=in_out(trace.service_us,r.dispatch_order)
                residual=identity_residual(r.wait_us,f.wait_us,wi,wo,k)
                assert np.all(np.abs(residual)<=2*(k-1)*L*MICROS)
                row['identity_worst_ratio']=float(np.max(np.abs(residual))/(2*(k-1)*L*MICROS))
                checks.append(row)
        log('REPLAY COMPLETE',pool,'segment',seg,'jobs',len(sub),'policies',len(waits))
    assert np.array_equal(waits['FCFS'],np.load(HERE/'fcfs_wait.npy')*MICROS)
    ids=np.flatnonzero(test); td=d.iloc[ids].copy(); td['busy']=busy[ids]
    td['week']=((td.a-cut)//(7*DAY)).astype(int)
    week=td.week.values; nw=int(week.max()+1)
    rng=np.random.default_rng(BOOT_SEED); draws=rng.multinomial(nw,np.full(nw,1/nw),size=BOOT_N).astype(np.int64)
    # Check weighted quantiles against explicitly duplicated weeks on a toy sample.
    v=np.array([0.,1.,2.,6.,10.]); wk=np.array([0,0,1,1,2]); dr=np.array([[1,1,1],[2,0,1],[0,0,3]])
    check=bootstrap_stats(v,wk,dr,np.bincount(wk),np.bincount(wk,weights=v))
    for i,mult in enumerate(dr):
        expanded=np.repeat(v,mult[wk]); assert np.allclose(check[i],[np.quantile(expanded,.99),expanded.mean()])
    all_boot={}; rows=[]
    for pool in ['all',*NOMINAL]:
        poolmask=np.ones(len(td),bool) if pool=='all' else td.pool.values==pool
        baseline=waits['FCFS'][ids]/MICROS; oracle=waits['SJF'][ids]/MICROS
        boot={}
        for name,wfull in waits.items():
            w=wfull[ids]/MICROS; excess=w-baseline
            row=dict(pool=pool,policy=name,n=int(poolmask.sum()),n_busy=int((poolmask&td.busy.values).sum()),
                mean=float(w[poolmask].mean()),p99=float(np.quantile(w[poolmask],.99)),
                p99_busy=float(np.quantile(w[poolmask&td.busy.values],.99)),
                max_excess=float(excess[poolmask].max()),harm=float(excess[poolmask&(baseline<=1)].max()),
                heavy_p99=float(np.quantile(w[poolmask&pred['heavy'][ids]],.99)),
                heavy_max=float(w[poolmask&pred['heavy'][ids]].max()))
            for scope,mask in [('overall',poolmask),('busy',poolmask&td.busy.values)]:
                order=np.argsort(w[mask],kind='stable'); sw=w[mask][order]; sh=week[mask][order]
                wn=np.bincount(sh,minlength=nw); ws=np.bincount(sh,weights=sw,minlength=nw)
                bs=bootstrap_stats(sw,sh,draws,wn,ws); boot[(name,scope)]=bs
                for j,metric in [(0,'p99'),(1,'mean')]:
                    lo,hi,valid=ci(bs[:,j]); row[f'{scope}_{metric}_lo']=lo; row[f'{scope}_{metric}_hi']=hi
            for metric in ['mean','p99','p99_busy']:
                m=poolmask&td.busy.values if metric=='p99_busy' else poolmask
                fun=np.mean if metric=='mean' else lambda x:np.quantile(x,.99)
                b=fun(baseline[m]); o=fun(oracle[m]); den=b-o
                row[f'{metric}_reduction']=float(1-row[metric]/b) if b else np.nan
                row[f'{metric}_gap']=float((b-row[metric])/den) if den>0 else np.nan
            rows.append(row)
        for row in rows:
            if row['pool']!=pool: continue
            name=row['policy']
            for metric,scope,j in [('mean','overall',1),('p99','overall',0),('p99_busy','busy',0)]:
                b=boot[('FCFS',scope)][:,j]; o=boot[('SJF',scope)][:,j]; v=boot[(name,scope)][:,j]
                den=b-o
                gap=np.divide(b-v,den,out=np.full_like(b,np.nan),where=den>0)
                red=np.divide(b-v,b,out=np.full_like(b,np.nan),where=b>0)
                for tag,arr in [('gap',gap),('reduction',red)]:
                    lo,hi,valid=ci(arr); row[f'{metric}_{tag}_lo']=lo; row[f'{metric}_{tag}_hi']=hi; row[f'{metric}_{tag}_valid']=valid
                diff=boot[('SPJF-log',scope)][:,j]-boot[('SPJF-E',scope)][:,j]
                all_boot[f'{pool}_{metric}_log_minus_E']=dict(zip(['lo','hi','valid'],ci(diff)))
        log('BOOTSTRAP COMPLETE',pool,nw,'week blocks',BOOT_N,'draws')
    pd.DataFrame(rows).to_csv(HERE/'policy_metrics.csv',index=False)
    pd.DataFrame(checks).to_csv(HERE/'bound_checks.csv',index=False)
    pd.DataFrame(params).drop_duplicates(['pool','policy']).to_csv(HERE/'policy_parameters.csv',index=False)
    pd.DataFrame(dispatch).to_csv(HERE/'guard_dispatches.csv',index=False)
    dump('bootstrap.json',dict(n_weeks=nw,replicates=BOOT_N,seed=BOOT_SEED,
        method='paired resampling of arrival-week blocks; same multiplicities across all policies and both pools; exact expanded-sample linear quantiles; endpoints include partial weeks',
        limits='conditional on the fixed trace, capacity, fitted models, and open-loop arrivals; no refitting or queue rerun inside bootstrap',log_vs_expected=all_boot))
    td[['job','a','pool','queue','L','week','busy']].to_csv(HERE/'test_jobs.csv',index=False)
    np.savez_compressed(HERE/'policy_waits_us.npz',**{key:v[ids] for key,v in waits.items()})
    pd.DataFrame(rows).query("pool=='all'").to_csv(HERE/'pooled_policy_metrics.csv',index=False)
    log(pd.DataFrame(rows).query("pool=='all'")[['policy','mean','p99','p99_busy','p99_busy_gap','max_excess','harm']].to_string(index=False))
    log('BOUND CHECKS',sum(x['checked'] for x in checks),'violations',sum(x['violations'] for x in checks),'worst ratio',max(x['worst_ratio'] for x in checks))
    finish()

if __name__=='__main__': main()
