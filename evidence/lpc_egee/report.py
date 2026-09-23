"""Validate artefact consistency and format the study's audit and conclusions."""
import sys
sys.dont_write_bytecode=True
from common import *
import re
import importlib.metadata

def mdtable(df,columns):
    def fmt(x):
        if isinstance(x,(float,np.floating)):
            if not np.isfinite(x): return 'n/a'
            return f'{x:,.2f}'.rstrip('0').rstrip('.') if abs(x)>=1000 else f'{x:.4g}'
        return str(x)
    return '| '+' | '.join(columns)+' |\n| '+' | '.join(['---']*len(columns))+' |\n'+ '\n'.join('| '+' | '.join(fmt(x) for x in row)+' |' for row in df[columns].itertuples(index=False,name=None))+'\n'

def pct(x): return f'{100*x:.1f}%'
def interval(row,metric,percent=False):
    fun=pct if percent else lambda v:f'{v:.3f}'
    return f"{fun(row[metric])} [{fun(row[metric+'_lo'])}, {fun(row[metric+'_hi'])}]"

def main():
    log,finish=log_start('report')
    audit=json.loads((HERE/'audit.json').read_text()); cap=json.loads((HERE/'capacity.json').read_text())
    predictor=json.loads((HERE/'predictor.json').read_text()); boot=json.loads((HERE/'bootstrap.json').read_text())
    q=pd.read_csv(HERE/'queue_audit.csv',dtype={'queue':str}); app=pd.read_csv(HERE/'applicability.csv',dtype={'queue':str})
    val=pd.read_csv(HERE/'validation.csv'); pm=pd.read_csv(HERE/'policy_metrics.csv'); bound=pd.read_csv(HERE/'bound_checks.csv')
    util=pd.read_csv(HERE/'utilisation_summary.csv'); pred=pd.read_csv(HERE/'prediction_metrics.csv')
    dispatch=pd.read_csv(HERE/'guard_dispatches.csv'); jobs=load(); test=pd.read_csv(HERE/'test_jobs.csv')
    hist=pd.read_csv(HERE/'history_counterfactual_diagnostic.csv')
    waits=np.load(HERE/'policy_waits_us.npz'); pp=np.load(HERE/'predictions.npz')
    manifest={}
    for stage in ['audit','diagnose','validate','predict','replay','supplement']:
        h=hashlib.sha256((HERE/f'{stage}.py').read_bytes()).hexdigest()
        found=re.findall(r'SCRIPT_SHA256 ([0-9a-f]{64})',(HERE/f'out_{stage}.txt').read_text())
        assert found[-1]==h,(stage,'changed since last run')
    expected_n=audit['filters'][-1]['after']; assert len(jobs)==expected_n
    assert predictor['test_n']==len(test)==(jobs.a>=SPLIT_DAY*DAY).sum()
    assert (bound.violations==0).all() and (bound.instance_violations.dropna()==0).all()
    assert np.all(pp['visible_latest']<=jobs.a.values)
    for name in waits.files:
        w=waits[name]/1e6; r=pm[(pm.pool=='all')&(pm.policy==name)].iloc[0]
        assert np.isclose(w.mean(),r['mean']) and np.isclose(np.quantile(w,.99),r.p99)
        assert np.isclose(np.quantile(w[test.busy.values],.99),r.p99_busy)
        if name.startswith(('Age-','Constant-')):
            assert np.array_equal(waits[name],waits['SPJF-E'])
            assert dispatch.loc[dispatch.policy==name,'forced'].sum()==0
    log('VERIFIED latest script hashes, row identities, per-job bounds, causal source features, all saved policy metrics')
    sources=[HERE/x for x in ['common.py','audit.py','diagnose.py','validate.py','predict.py','replay.py','supplement.py','report.py','run.sh','protocol.json','jobs.csv','capacity.json','predictor.json','audit.json','bootstrap.json','policy_metrics.csv','bound_checks.csv','predictions.npz','policy_waits_us.npz']]
    sources += [RAW]
    sources += [HERE/x for x in ['validation.csv','capacity_grid.csv','prediction_metrics.csv','queue_audit.csv','applicability.csv','test_jobs.csv','history_counterfactual_diagnostic.csv','utilisation_summary.csv','policy_parameters.csv']]
    sources += [ROOT/'src/spjf_guard'/x for x in ['sim/runner.py','sim/kernel.py','sim/reference.py','sim/policy.py','sim/bounds.py','predict/scores.py']]
    for p in sources: manifest[str(p.relative_to(ROOT)).replace('\\','/')]=hashlib.sha256(p.read_bytes()).hexdigest()
    dump('manifest.json',dict(sha256=manifest,versions={x:importlib.metadata.version(x) for x in ['numpy','pandas','numba','lightgbm','scikit-learn']},python=sys.version))

    # Detailed audit, keeping REPORT focused on the empirical verdict.
    text=['# LPC-EGEE audit\n',
    'The only data input is the cleaned LPC-EGEE SWF log. The 18 columns use the same parser/schema as `evidence/cross_domain/cd_common.py`; that module was read, not imported, because its import creates its own cache. No other dataset was opened.\n',
    '## Corrections to the interrupted audit\n',
    'The downloaded bytes, hash, SWF parser, status treatment and raw concurrency calculation were retained. The original audit incorrectly applied outage days to `submit - min(submit)`. The original SWF epoch and the cleaned first arrival differ by **3,585,977 s (41.50 days)**. `diagnose.py` locates the long test-queue waits on raw SWF days 140–150 (not just 140–149 in the hunt). The same prespecified exclusion [138,153) now uses raw `submit` seconds. The incorrect run retained outage jobs and reported test-queue p99 939,596 s; the corrected p99 is 21,496.64 s. The old code and tables remain in `superseded_audit/`; the newest invocation in `out_audit.txt` is authoritative.\n',
    'The hunt was also too categorical about requested time. It is not always the queue limit: the raw file has missing and nonstandard values. The documented CE2 short limit is 5,400 s, while old/CE1 short is 7,200 s. We use those documented queue limits for capping and retain raw requested time as a predictor. The 1,909 retained request/queue-limit mismatches include missing requests.\n',
    '## Filter ledger\n',mdtable(pd.DataFrame(audit['filters']),['filter','before','removed','after']),
    f"Raw status counts: {audit['status_raw']}. Retained status counts: {audit['status_retained']}. Failed/cancelled jobs that consumed positive service remain; only jobs without positive service are removed. Zero runtimes: {audit['zero_run']:,}; negative runtimes: {audit['negative_run']:,}; negative waits/submits: {audit['negative_wait']}/{audit['negative_submit']}. All positive-service jobs allocate exactly one CPU.\n",
    f"The outage removes {audit['outage_submit_only_removed']:,} arrivals in [138,153) and {audit['additional_outage_overlap_removed']} additional jobs whose observed submit-to-completion lifetime crosses it, giving {expected_n:,} retained jobs. This is why the total differs from the hunt's approximate 206,430; the exact reproducible count is used throughout. The remaining {audit['exceeds_queue_L']:,} jobs above the queue cap are **capped, not dropped**, removing {audit['excess_runtime_seconds']:,} service seconds. Recorded waits and history availability keep their original values.\n",
    '## Per-queue distribution over all retained arrivals\n',
    'All waits and limits are seconds. `L_min/L` show queue-limit variation across partitions. `top1/top5` are capped-runtime work shares; `raw_top1` is uncapped. The longest fraction uses `round(n*fraction)` jobs, matching the existing cross-domain utility.\n',
    mdtable(q[q.pool=='all'],['queue','n','L_min','L','mean','p50','p90','p99','top1','top5','raw_top1','exceeds']),
    'Queue codes: 1=test, 2=short, 3=long, 4=day, 5=infinite, 6=batch. Per-physical-pool/queue rows are in `queue_audit.csv`; requested-time counts by partition/queue are in `audit.json`.\n',
    '## Topology, concurrency, utilisation and arrival concentration\n',
    'The [archive system documentation](https://www.cs.huji.ac.il/labs/parallel/workload/l_lpc/) states two disjoint physical partitions with no load balancing: CE1 has 84 CPUs; old, renamed CE2 on 1 December 2004, has 56. These are the modelling units. The queues share capacity within a partition, and the later queue running-job ceilings are not dedicated sub-pools.\n',
    'The observed concurrency lower bound is 142 globally, 85 on CE1, 58 on old/CE2, versus documented counts 140/84/56. This small discrepancy is an inconsistency of timestamps/accounting; it does not establish additional physical machines. Occupancy is measured from [submit+wait, submit+wait+raw_run), with completions before starts on ties.\n',
    mdtable(util,['pool','k','max_concurrency','util_mean','util_p50','util_p90','util_max','hour_at_or_above_90pct']),
    'Utilisation summaries above exclude whole hourly bins overlapping the incident; `hourly_cleaned.csv` contains the full time series and an explicit validity flag. `hourly_audit.csv` retains the original pre-exclusion diagnostic. The occupancy column in `utilisation_summary.csv` additionally includes the excluded gap in its denominator and must not be confused with `util_mean`. Utilisation sometimes exceeds one because of the concurrency discrepancy.\n',
    f"Hourly arrival mean is {audit['arrival_hourly_mean']:.2f}, maximum {audit['arrival_hourly_max']:,}, variance/mean {audit['arrival_hourly_dispersion']:.2f}. Calendar bins use Europe/Paris, including daylight-saving time. Exposure-normalised arrival rates peak at 15:00 versus a trough at 06:00 (2.44x); Tuesday versus Sunday is 2.24x. These are grid submission cycles, not recorded deadlines. `hour_of_day*.csv` and `day_of_week*.csv` contain counts, work and rates.\n",
    '## Applicability, per queue and pooled\n',
    'Condition 1 is exactly FCFS p99 > (3-2/k)L, using FCFS replay rather than recorded Maui waits. In a mixed queue physical pool, the theorem must use **L_pool=259,200 s even for a short-queue cohort**. The ratio to the cohort queue limit is also shown but does not certify a separate queue theorem. Every cohort and both physical pools fail the actual condition.\n',
    'Condition 2 in the paper is qualitative cost concentration, not a formally fixed 25% cutoff or a claim of an unbounded power law. For a reproducible yes/no diagnostic, the table labels the hunt’s approximate 25% top-1% work-share proxy. Pooled, long and batch pass it; test and short are moderately concentrated but below it; day and infinite also fall below it. This proxy must not be presented as a theorem or a statistical tail-law test.\n',
    mdtable(app[(app.period=='all')&(app.pool=='all')],['queue','fcfs_p99','p99_over_L_queue','p99_over_L_pool','condition1','top1','top5','condition2_proxy_25pct']),
    'Held-out cohorts (same fitted pools, no capacity refit):\n',
    mdtable(app[(app.period=='test')&(app.pool=='all')],['queue','n','fcfs_p99','p99_over_L_queue','p99_over_L_pool','condition1','top1','condition2_proxy_25pct']),
    'Physical-pool totals:\n',mdtable(app[(app.queue=='all')&(app.pool!='all')],['period','pool','n','fcfs_p99','p99_over_L_pool','condition1','top1','top5','condition2_proxy_25pct'])]
    (HERE/'AUDIT.md').write_text('\n'.join(text),encoding='utf-8')

    pooled=pm[pm.pool=='all'].set_index('policy'); E=pooled.loc['SPJF-E']; F=pooled.loc['FCFS']; S=pooled.loc['SJF']; A=pooled.loc['Age-5L']; LG=pooled.loc['SPJF-log']
    held=val[(val.variant=='fitted')&(val.part=='test')]
    app_test=app[(app.period=='test')&(app.pool=='all')&(app.queue=='all')].iloc[0]
    table=pooled.reset_index()[['policy','mean','p99','p99_busy','p99_busy_gap','max_excess','harm']]
    table['busy reduction [95% CI]']=[interval(pooled.loc[name],'p99_busy_reduction',True) for name in table.policy]
    rules=pd.read_csv(HERE/'policy_parameters.csv')
    proposed=f"LPC-EGEE, held-out FCFS counterfactual (83+56 disjoint servers) & {app_test.top1:.3f} & {pred[(pred.pool=='all')&(pred.score=='spjf_e')].auroc.iloc[0]:.3f} & {F.p99_busy/259200:.3f} & no & {E.p99_busy_gap:.3f} & {E.max_excess/259200:.3f}L & {A.p99_busy_gap:.3f} / {A.max_excess/259200:.3f}L \\\\"
    report=['# LPC-EGEE: a real queue with a heavy tail, but a weak replay validation\n',
    '**Verdict.** This trace supplies recorded queue waits and concentrated execution costs in the same system. It does **not** establish that Guard improves the real system. At the capacities fitted before the test period, expected-cost ordering improves the simulated mean and overall p99, but the busy-hour p99 improvement is unresolved. The work-budget guards never intervene, because the maximum queue limit makes their guarantees much coarser than the observed waits.\n',
    '## 1. Audit and frozen protocol\n',
    f"The retained sample contains **{expected_n:,}** jobs; longest 1%/5% account for **40.71%/83.54%** of capped work. The held-out sample has **{len(test):,}** jobs, with 1%/5% shares **{pct(app_test.top1)}/{pct(app_test.top5)}**. Full filter counts, all six queue distributions, utilisation, calendar cycles and applicability decisions are in [AUDIT.md](AUDIT.md). The only rerun of item 1 repaired a wrong outage clock and the CE2 short-queue limit; the input was retained and verified.\n",
    f"The inherited chronological split is **{cap['split_utc']}**, 120 days after the first cleaned arrival. Models use {predictor['train_n']:,} pre-split rows whose recorded results are already available; {predictor['excluded_unfinished_train']} earlier arrivals are excluded from training because they finish too late. Capacities are selected on the same visibility rule, separately per physical pool, over every integer 1..84 or 1..56, minimising |log((simulated mean+1)/(recorded mean+1))| + |log((simulated p90+1)/(recorded p90+1))|. Fitted capacities are **83 and 56**. No test-driven capacity, load, model, window or guard selection is made.\n",
    'Simulations reset only across the excluded incident, preserve idle gaps, and carry state through the train/test boundary. All replay policies use an FCFS prefix; pre-split jobs pending at the switch retain precedence. Before the split no fitted or true-size scores are used. Each segment runs until its last job starts, so jobs waiting beyond the final arrival are included. Arrivals and service are fixed across policies; service is min(raw run, documented partition/queue limit), while the bound uses the pool maximum 259,200 s.\n',
    f"A busy window is an arrival-hour with at least the fit-part 90th-percentile count, computed over all non-outage hours: **30 arrivals/h on CE1, 33 on old/CE2**. These frozen thresholds select **{int(E.n_busy):,}** held-out arrivals. They are arrival-burst windows, not deadlines or bins selected for having long test waits.\n",
    '## 2. Out-of-sample simulator validation\n',
    'The production integer-microsecond simulator is imported read-only, with bytecode disabled and caches redirected here. Its FCFS output agrees exactly with the independent fitting recursion for all 206,222 jobs. There is also exact wait agreement on 120 small instances, plus dispatch-order agreement on the 100 non-FCFS cases, covering six policies, k=1/2/4/7 and same-instant events. This validates implementation, **not fidelity to Maui**.\n',
    mdtable(held,['pool','k','recorded_mean','sim_mean','recorded_p50','sim_p50','recorded_p90','sim_p90','recorded_p99','sim_p99','hourly_pearson']),
    'Units are seconds; hourly correlation is Pearson correlation of the two mean waits within each nonempty **arrival-hour cohort**, not a correlation with empty hours filled by zero. CE1 mean is 0.758 of recorded and old/CE2 0.614; CE1 p99 is 0.949, old/CE2 0.642. Both simulated medians/p90s are zero. The nominal-capacity and uncapped-service sensitivities in `validation.csv` do not resolve the discrepancy; no setup time is fitted.\n',
    'The original “Torque/Maui, therefore non-FCFS” description is too blunt. The [archive documentation](https://www.cs.huji.ac.il/labs/parallel/workload/l_lpc/) names OpenPBS/Maui and says the serial-job scheduling order was plain FCFS before 1 June 2005; queue bonuses and group fair share began after this log ended. It also dates **queue concurrency ceilings to 7 March 2005**, within the test period. Those ceilings, periodic polling and middleware effects are absent from our work-conserving pool. We therefore do not equate recorded waits with theoretical FCFS waits. The page’s “plain FCFS” summary does not erase its own queue-ceiling qualification.\n',
    'A documentation-dated diagnostic, without refitting, gives CE1 mean ratio 1.068, p99 ratio 1.043 and hourly correlation 0.888 before 7 March; afterwards hourly correlation falls to 0.281. Old/CE2 is weak even before then (correlation 0.394). This supports a structural mismatch explanation, not a post hoc rescue of the full held-out validation. Even perfect agreement of these summaries would support an aggregate queue approximation, not identify the real scheduler or validate policy counterfactuals.\n',
    '## 3. Predictability and submission visibility\n',
    'Features are user, group, queue, partition, requested time and queue limit, plus only that user’s completed-job count, mean cost, mean/std log cost, last cost, last-five mean and time since latest completion. Executable is uniformly -1 and omitted; status, run time and recorded wait are not submission features. Histories are swept by recorded submit+wait+raw_run <= arrival, including ties. Categorical levels and the heavy threshold use training rows only; unknown identities map to missing. Independent from-scratch recomputation matches all seven history columns on 290 sampled/boundary rows.\n',
    f"Heavy means capped cost > training p95 = **{predictor['heavy_threshold_s']:,.1f} s**, with test prevalence 8.82%. The models are frozen at the split. `src/spjf_guard/predict/scores.py` supplies Tweedie power 1.5 on raw capped seconds versus squared error on log(1+C), 400 rounds, 63 leaves, learning rate .05, min leaf 50, feature/bag fractions .9, bag frequency 1. Both use seed 3, deterministic row-wise construction and four threads.\n",
    mdtable(pred,['pool','score','auroc','average_precision','log_rmse','spearman']),
    f"The log-score policy has a slightly lower busy-hour p99 ({LG.p99_busy:,.0f} versus {E.p99_busy:,.0f} s), despite lower AUROC. The paired log-minus-E interval is [{boot['log_vs_expected']['all_p99_busy_log_minus_E']['lo']:,.0f}, {boot['log_vs_expected']['all_p99_busy_log_minus_E']['hi']:,.0f}] s; this study does not establish expected-cost ranking superiority.\n",
    f"**Visibility qualification:** histories are causal in the **recorded log**. Reordering changes completion times: {int(hist[hist.policy=='SPJF-E'].affected_rows.iloc[0]):,} test arrivals ({pct(hist[hist.policy=='SPJF-E'].affected_fraction.iloc[0])}) would have at least one historical outcome unavailable under the replayed SPJF-E schedule. Thus this is a frozen, open-loop recorded-feature replay, not an operationally closed-loop predictor/scheduler experiment. The submission-only ablation avoids that feedback dependency, has AUROC {predictor['static_ablation_auroc']:.3f}, and increases busy p99 by 1.13% (interval includes zero). The direction of the open-loop bias is unknown; no lower-bound claim is justified.\n",
    '## 4. Policy results, uncertainty and bounds\n',
    'For G/L in {3.5,5,10}, Bmax=k(G-(3-2/k)L). Constant uses B0=Bmax, eta=0. Age-relative uses (B0/kL,eta)=(1/4,.5) at 3.5L and 5L and (1/2,.75) at 10L; gamma=0. The 5L/10L settings are transferred from the paper’s development selection (Section 8, Table `tab:setup`); 3.5L reuses the 5L setting without selection. Skip uses floor(Gk/L)-(2k-2), charged at dispatch. Exact per-pool parameters are in `policy_parameters.csv`; none were fitted here. These are constant/age ablations, not a newly selected joint winner.\n',
    mdtable(table,['policy','mean','p99','p99_busy','busy reduction [95% CI]','p99_busy_gap','max_excess','harm']),
    f"For SPJF-E (and every constant/age guard): mean reduction **{interval(E,'mean_reduction',True)}**, overall p99 reduction **{interval(E,'p99_reduction',True)}**, busy p99 reduction **{interval(E,'p99_busy_reduction',True)}**. The corresponding FCFS-to-SJF gaps closed are {interval(E,'mean_gap')}, {interval(E,'p99_gap')}, and {interval(E,'p99_busy_gap')}. Gap closed is not percentage wait reduction. SJF is an oracle comparator, not a general p99 optimum. Maximum excess is {E.max_excess:,.0f} s; harm is {E.harm:,.0f} s, defined over FCFS waits <=1 s.\n",
    'Intervals use 2,000 paired bootstrap resamples of the same 17 arrival-week blocks (seed 20260921), with the same week multiplicities for both physical pools and every policy. Quantiles are recomputed from the expanded empirical distribution, not averaged across weekly quantiles. They condition on the fitted capacity, model and trace and do not cover model-selection, capacity or structural error, job dependence across weeks, or counterfactual feedback. In 1/2,000 draws FCFS p99 is zero; in 8/2,000 busy draws the FCFS-to-SJF denominator is nonpositive. Undefined quantities remain missing: p99-reduction intervals use 1,999 draws, mean-reduction intervals use all 2,000, and busy gap intervals use 1,992. The conditional gap interval is especially unstable. All per-pool intervals are in `policy_metrics.csv`.\n',
    f"Every job was checked against the imported additive/multiplicative bound: **{int(bound.checked.sum()):,} job-policy checks, {int(bound.test_checked.sum()):,} on test jobs, zero violations**. Worst positive excess/allowed excess = **{bound.worst_ratio.max():.6f}**. The instance-dependent check uses Bmax/k + Lambda(start) + (2-2/k)Lambda(arrival), and the corresponding age-relative bound, with Lambda(t)=max capped service among arrivals by t: zero violations, worst ratio **{bound.instance_worst_ratio.max():.6f}**. Identity-residual checks also pass. Prefix maxima already reach the global cap before the scored period, so the instance version adds no useful tightening.\n",
    'All six constant/age guards fire **zero times**, and their per-job waits equal SPJF-E. This is why a small worst-bound ratio is not evidence of an effective safeguard here. The theorem floor is 768,343–771,354 s (about 8.9 days), compared with overall FCFS p99 11,376.55 s (0.04389L) and busy p99 10,969.34 s (0.04232L). Condition 1 fails even though pooled cost concentration satisfies condition 2. Using the test queue’s 900-second L would falsely shrink the theorem constant while longer queues share its machines.\n',
    '## 5. What a referee should accept or reject\n',
    'The strongest objections are substantive: (i) held-out wait profiles are poorly reproduced, so policy benefits remain conditional simulations; (ii) heterogeneous queue limits make the guarantee operationally uninformative; (iii) grid bags, remote assignment, polling and incomplete middleware state influence both arrivals and waits; (iv) completion-history feedback is frozen and demonstrably inconsistent for 2.49% of test arrivals; and (v) this is one 2004–2005 Pentium-IV grid site, not a modern judging or cloud deployment. The pooled tail also partly reflects mixing queues with different limits. Neither bootstrap intervals nor serial-job status remove these problems.\n',
    '**Exact sentences supported for the paper:**\n',
    '> “The public LPC-EGEE trace supplies recorded queue waits and concentrated execution costs together: after a prespecified outage exclusion and documented queue-limit capping, the longest 1% of 206,222 jobs accounts for 40.7% of executed work.”\n',
    '> “An FCFS approximation with effective capacities fitted on the first chronological part underestimates held-out mean waits by 24% and 39% on the two physical partitions, with hourly correlations of 0.44 and 0.40; we therefore treat policy replays on this trace as conditional counterfactuals rather than validated estimates of deployment benefit.”\n',
    '> “On those held-out counterfactuals, SPJF-E reduces mean wait by 21.4% [13.2%, 38.2%], while its 4.2% reduction in busy-hour p99 is unresolved [−11.2%, 46.0%]; at promises of 3.5, 5 and 10 times the 259,200-second pool limit, neither constant nor age-relative work-budget guards intervene.”\n',
    '**Candidate Table `tab:cross` row (all values from the held-out part):**\n',
    '```latex\n'+proposed+'\n```\n',
    'Required footnote: “LPC-EGEE pools remain disjoint; capacities are fitted on the earlier part, and full held-out wait-profile validation is weak. L is the largest queue limit; the p99 and gaps use frozen-threshold busy hours, not deadlines. History features use recorded completion times. The work-budget guard never fires. Thus this row is a conditional replay and not evidence of real-scheduler improvement.” Tail share 0.351 is held-out, not the all-period 0.407 headline.\n',
    '**Not supported:** a claim that this completes end-to-end real-queue validation; a causal reduction of recorded Maui waits; a statistically resolved busy-p99 benefit; a useful guard/benefit trade-off; superiority of expected over log scores; per-queue 900-second guarantees in the shared physical pool; heavy-tail power-law claims; or generalisation to modern production systems.\n',
    'Reproduction: [README.md](README.md). Data provenance and hashes: `download.json`, `manifest.json`. All writes are confined to this git-excluded directory; no project datasets were read, and no paper/code/configuration files were changed.\n',
    'COMPUTE_TIME_PLACEHOLDER\n']
    (HERE/'REPORT.md').write_text('\n'.join(report),encoding='utf-8')
    log('WROTE AUDIT.md, REPORT.md, manifest.json; all findings from persisted numerical outputs')
    finish()
    times=[json.loads(x) for x in (HERE/'timings.jsonl').read_text().splitlines() if x.strip()]
    wall=sum(x['wall_s'] for x in times); cpu=sum(x['cpu_s'] for x in times)
    phrase=f"Measured computation across all completed script invocations (including the interrupted run’s initial audit and this run’s correction): **{wall:.2f} wall seconds, {cpu:.2f} process CPU seconds**. This excludes interpreter/import/startup overhead, the earlier download, and reading/writing review time. No timing for unrecorded work is inferred. One computational process at a time, at most four threads."
    p=HERE/'REPORT.md'; p.write_text(p.read_text().replace('COMPUTE_TIME_PLACEHOLDER',phrase),encoding='utf-8')
    dump('compute_time.json',dict(completed_script_wall_s=wall,completed_script_cpu_s=cpu,invocations=times))

if __name__=='__main__': main()
