"""Frozen forward predictors using only submission fields and visible own history."""
import sys
sys.dont_write_bytecode=True
from common import *
from collections import defaultdict, deque
import lightgbm as lgb
from sklearn.metrics import roc_auc_score, average_precision_score, mean_squared_error
from spjf_guard.predict.scores import SCORE_SPECS, DEFAULT_LGB_PARAMS, DEFAULT_ROUNDS

STATIC=['uid','gid','queue','part','time_req','L']
HISTORY=['history_count','history_mean_c','history_mean_log','history_sd_log','history_last_c','history_last5_mean','history_age_s']

def make_features(d):
    a=d.a.values; done=d.done.values; cost=d.c.values; uid=d.uid.values
    order=np.argsort(done,kind='stable'); p=0
    state={}; hist=np.full((len(d),len(HISTORY)),np.nan)
    visible_latest=np.full(len(d),-1,np.int64)
    for i,t in enumerate(a):
        while p<len(d) and done[order[p]]<=t:
            j=order[p]; u=uid[j]; x=float(cost[j]); z=np.log1p(x)
            if u not in state: state[u]=[0,0.,0.,0.,deque(maxlen=5),0]
            st=state[u]; st[0]+=1; st[1]+=x; st[2]+=z; st[3]+=z*z; st[4].append(x); st[5]=int(done[j]); p+=1
        if uid[i] in state:
            n,total,logs,sq,last5,end=state[uid[i]]
            hist[i]=[n,total/n,logs/n,np.sqrt(max(0,sq/n-(logs/n)**2)),last5[-1],np.mean(last5),t-end]
            visible_latest[i]=end
        else: hist[i,0]=0
    assert np.all(visible_latest<=a)
    features=pd.concat([d[STATIC].reset_index(drop=True),pd.DataFrame(hist,columns=HISTORY)],axis=1)
    # Treat anonymised identities as categories, with levels learned only on training.
    train=(d.a<SPLIT_DAY*DAY)&(d.done<SPLIT_DAY*DAY)
    mapping={}
    for col in ['uid','gid','queue','part']:
        known=sorted(d.loc[train,col].unique().tolist())
        mapping[col]=known
        features[col]=pd.Categorical(d[col],categories=known)
    return features,mapping,visible_latest

def verify_features(d,x,log):
    rng=np.random.default_rng(BOOT_SEED)
    ids=np.unique(np.r_[np.arange(20),rng.choice(len(d),250,replace=False),np.flatnonzero(d.a.values>=SPLIT_DAY*DAY)[:20]])
    for i in ids:
        p=d[(d.uid==d.uid.iloc[i])&(d.done<=d.a.iloc[i])].sort_values('done',kind='stable')
        if len(p):
            z=np.log1p(p.c.values)
            expect=[len(p),p.c.mean(),z.mean(),z.std(),p.c.iloc[-1],p.c.iloc[-5:].mean(),d.a.iloc[i]-p.done.iloc[-1]]
        else: expect=[0,*([np.nan]*6)]
        assert np.allclose(x.loc[i,HISTORY].astype(float).values,expect,rtol=1e-7,atol=1e-5,equal_nan=True),int(i)
    log('INDEPENDENT HISTORY RECOMPUTATION',len(ids),'rows, 0 mismatches; completion <= arrival')

def main():
    log,finish=log_start('predict'); d=load(); x,mapping,latest=make_features(d); verify_features(d,x,log)
    train=(d.a.values<SPLIT_DAY*DAY)&(d.done.values<SPLIT_DAY*DAY); test=d.a.values>=SPLIT_DAY*DAY
    threshold=float(np.quantile(d.c.values[train],.95)); y=d.c.values>threshold
    rows=[]; pred={}
    for key,spec in SCORE_SPECS.items():
        params=dict(DEFAULT_LGB_PARAMS,**spec.params,objective=spec.objective,seed=SEED,random_state=SEED,
                    num_threads=4,deterministic=True,force_row_wise=True)
        model=lgb.train(params,lgb.Dataset(x[train],label=spec.target_of(d.c.values)[train]),num_boost_round=DEFAULT_ROUNDS)
        values=np.full(len(d),np.nan); values[test]=model.predict(x[test],num_threads=4); pred[key]=values
        model.save_model(str(HERE/f'model_{key}.txt'))
        for pool in ['all',*NOMINAL]:
            m=test if pool=='all' else test&(d.pool.values==pool)
            v=values[m]; raw=np.maximum(v,0) if key=='spjf_e' else np.expm1(np.clip(v,0,np.log1p(259200)))
            row=dict(score=key,pool=pool,n=int(m.sum()),heavy_threshold_s=threshold,heavy_rate=float(y[m].mean()),
                auroc=float(roc_auc_score(y[m],v)),average_precision=float(average_precision_score(y[m],v)),
                log_rmse=float(np.sqrt(mean_squared_error(np.log1p(d.c.values[m]),np.log1p(raw)))),
                spearman=float(pd.Series(v).corr(pd.Series(d.c.values[m]),method='spearman')))
            rows.append(row); log(json.dumps(row))
        log('MODEL PARAMETERS',key,params,'rounds',DEFAULT_ROUNDS)
    # Submission-only ablation removes policy-dependent completion-history features.
    spec=SCORE_SPECS['spjf_e']; params=dict(DEFAULT_LGB_PARAMS,**spec.params,objective=spec.objective,
        seed=SEED,random_state=SEED,num_threads=4,deterministic=True,force_row_wise=True)
    model=lgb.train(params,lgb.Dataset(x.loc[train,STATIC],label=d.c.values[train]),num_boost_round=DEFAULT_ROUNDS)
    v=np.full(len(d),np.nan); v[test]=model.predict(x.loc[test,STATIC],num_threads=4); pred['static_e']=v
    model.save_model(str(HERE/'model_static_e.txt'))
    log('STATIC-ONLY ABLATION AUROC',roc_auc_score(y[test],v[test]))
    np.savez_compressed(HERE/'predictions.npz',**pred,heavy=y,visible_latest=latest)
    pd.DataFrame(rows).to_csv(HERE/'prediction_metrics.csv',index=False)
    dump('predictor.json',dict(train_n=int(train.sum()),test_n=int(test.sum()),
        excluded_unfinished_train=int(((d.a.values<SPLIT_DAY*DAY)&~train).sum()),heavy_threshold_s=threshold,
        features=STATIC+HISTORY,categorical_levels=mapping,executable='all -1, omitted',
        defaults_source='src/spjf_guard/predict/scores.py DEFAULT_LGB_PARAMS, DEFAULT_ROUNDS, SCORE_SPECS',
        n_rounds=DEFAULT_ROUNDS,seed=SEED,num_threads=4,model_frozen=True,
        visibility='recorded completion <= recorded arrival; own user only; later test completions update history but never the fitted trees',
        caveat='open-loop recorded-history feature stream is not recomputed under each counterfactual policy',
        static_ablation_auroc=float(roc_auc_score(y[test],v[test]))))
    finish()

if __name__=='__main__': main()
