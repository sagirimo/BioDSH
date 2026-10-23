"""Compare every exported R quantity, fail on shape/nonfinite/1e-8 scaled error."""
import sys, json, time
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from survival_py import (kaplan_meier, administrative_censor, logrank, rmst_difference,
                         coxph, cox_components, baseline_hazard, predict_survival, rmst)
from make_data import simulate
root=Path(sys.argv[1]); report=[]; findings={}
for seed in ['20261020','20261021','edge']:
    d=pd.read_csv(root/('edge.csv' if seed=='edge' else f'data_{seed}.csv'),float_precision='round_trip')
    t,e,g=d.time.to_numpy(),d.status.to_numpy(),d.group.to_numpy()
    out={}
    def put(k,v): out[k]=np.asarray(v,float).ravel(order='F')
    def kmout(pre,t,e):
        for ct in ['log','log-log']:
            f=kaplan_meier(t,e,conf_type=ct)
            for r,p in dict(time='time',n_risk='n.risk',n_event='n.event',n_censor='n.censor',survival='surv',std_err_log='std.err',lower='lower',upper='upper',greenwood='greenwood',variance='variance',se='se').items(): put(f'{pre}.{ct}.{p}',f[r])
    kmout('km',t,e)
    tau=3 if seed=='edge' else 10
    td,ed=administrative_censor(t,e,tau); put('admin.time',td); put('admin.status',ed); kmout('admin.km',td,ed)
    rd=rmst_difference(t,e,g,tau)
    for k,a in enumerate(rd['arms']):
        pre=f'rmst.{k}.'
        put(pre+'summary',[a[q] for q in ['estimate','se','lower','upper','variance','rmtl','tau']])
        for p,q in dict(tt='time',widths='widths',areas='areas',tail='tail_areas',inc='greenwood_increment',contrib='variance_contributions').items(): put(pre+p,a[q])
    put('rmst.diff',[rd[k] for k in ['estimate','lower','upper','p_value']])
    put('rmst.diff_details',[rd[k] for k in ['variance','se','z']])
    def lrout(pre,t,e,g,strata=None):
        f=logrank(t,e,g,strata)
        for p,q in dict(obs='observed_by_stratum',exp='expected_by_stratum',var='covariance',chisq='statistic',df='df',p='p_value').items(): put(pre+'.'+p,f[q])
        return f
    lrout('lr',t,e,g)
    if seed=='edge':
        kmout('allcensored',[0,1,1,3],[0,0,0,0])
        kmout('allzero',[0,0,0],[1,1,1])
        term=rmst(t,e,4)
        put('terminal.rmst',[term[k] for k in ['estimate','se','lower','upper','variance']])
    if seed!='edge':
        x=d[['group','x']].to_numpy(); s=d.stratum.to_numpy(); cluster=d.cluster.to_numpy()
        ls=lrout('lr.strata',t,e,g,s)
        lrout('lr.three',t,e,cluster%3); lrout('lr.three.strata',t,e,cluster%3,s)
        for j in np.unique(s):
            ix=s==j; lrout(f'lr.stratum{j}',t[ix],e[ix],g[ix])
        for ties in ['breslow','efron']:
            ee=e.copy(); ee[s==2]=0
            fz=coxph(t,ee,x,s,ties=ties)
            fs=coxph(t,e,x[:,1:],ties=ties)
            for name,fit in [('zeroevent',fz),('single',fs)]:
                put(f'{name}.{ties}.beta',fit['coefficients']); put(f'{name}.{ties}.cov',fit['covariance'])
            for st in [False,True]:
                for cl in [False,True]:
                    pre=f'cox.{ties}.{int(st)}.{int(cl)}'
                    fit=coxph(t,e,x,strata=s if st else None,cluster=cluster if cl else None,ties=ties)
                    for p,q in dict(beta='coefficients',cov='covariance',model_cov='model_covariance',info='information',score_residuals='score_residuals',score='score',se='se',z='z',p='p_value',hr='hazard_ratio',coef_lower='coef_lower',coef_upper='coef_upper',reference='reference',null_score='null_score',null_info='null_information').items(): put(pre+'.'+p,fit[q])
                    put(pre+'.loglik',[fit['loglik_null'],fit['loglik']]); put(pre+'.n',[fit['n'],fit['n_event']])
                    for p,q in dict(wald='wald',score_test='score_test',lr='likelihood_ratio').items(): put(pre+'.'+p,[fit[q][z] for z in ['statistic','df','p_value']])
                    if cl:
                        put(pre+'.cluster_scores',fit['cluster_scores']); put(pre+'.meat',fit['meat'])
                        put(pre+'.robust_score',[fit['robust_score'][z] for z in ['statistic','df','p_value']])
                    def detailout(comp,p):
                        tables=comp['tables']
                        for r,q in dict(time='event_time',nevent='n_event',nrisk='n_risk',means='mean',score='score',imat='information',hazard='hazard',wtrisk='risk_sum',death_risk_sum='death_risk_sum',loglik='loglik',hazard_breslow='hazard_breslow').items():
                            vals=[]
                            for table in tables:
                                v=table[q]
                                if q in ['n_event','n_risk','hazard','hazard_breslow']: v=v[table['n_event']>0]
                                if q=='mean': v=v+fit['reference']
                                vals.append(v)
                            v=np.concatenate(vals,axis=0)
                            if q=='information': v=v.transpose(1,2,0)
                            put(p+'.'+r,v)
                    detailout(fit,pre+'.detail')
                    fixed=cox_components(t,e,x-fit['reference'],[.23,-.17],s if st else None,ties)
                    detailout(fixed,pre+'.fixed'); put(pre+'.fixed.loglik',fixed['loglik']); put(pre+'.fixed.residuals',fixed['score_residuals'])
                    bh=baseline_hazard(fit,method=ties); bh0=baseline_hazard(fit,method=ties,reference=np.zeros(2))
                    put(pre+'.basehaz',np.concatenate([a['cumulative_hazard'] for a in bh])); put(pre+'.basetime',np.concatenate([a['time'] for a in bh])); put(pre+'.basehaz0',np.concatenate([a['cumulative_hazard'] for a in bh0]))
                    for ctype,method in [(1,'breslow'),(2,'efron')]:
                        if method=='efron' and ties=='breslow': continue
                        for sid in range(3) if st else [0]:
                            put(f'{pre}.prediction.{ctype}.{sid}',predict_survival(fit,[[.4,-.2]],[0,1,3,7,10],strata=[sid] if st else None,method=method))
                    if not cl and not st:
                        findings[f'{seed}.{ties}.beta']=fit['coefficients'].tolist()
        findings[f'{seed}.n']=len(t); findings[f'{seed}.events']=int(e.sum()); findings[f'{seed}.group_sizes']=np.bincount(g).tolist()
        findings[f'{seed}.rmst_difference']=rd['estimate']
    ref=pd.read_csv(root/f'r_{seed}.csv',float_precision='round_trip')
    for key,rr in ref.groupby('key',sort=False):
        # ctype=2 after Breslow fit is deliberately not exposed by the library.
        if key.startswith('cox.breslow.') and '.prediction.2.' in key: continue
        if key not in out: raise AssertionError(f'missing Python comparator {key}')
        a,b=out.pop(key),rr.value.to_numpy()
        if a.shape!=b.shape: raise AssertionError((seed,key,a.shape,b.shape))
        finite=np.isfinite(a)&np.isfinite(b)
        nf=bool(np.array_equal(np.isnan(a),np.isnan(b)) and np.array_equal(np.isposinf(a),np.isposinf(b)) and np.array_equal(np.isneginf(a),np.isneginf(b)))
        delta=np.abs(a[finite]-b[finite]); scale=np.maximum(1,np.abs(b[finite]))
        rel=delta/np.maximum(1e-12,np.abs(b[finite]))
        row=dict(seed=seed,key=key,n=len(a),max_abs=float(delta.max(initial=0)),max_rel=float(rel.max(initial=0)),max_scaled=float((delta/scale).max(initial=0)),nonfinite_match=nf, max_rel_nonzero=float(rel[np.abs(b[finite])>1e-7].max(initial=0)), nearzero_abs=float(delta[np.abs(b[finite])<=1e-7].max(initial=0)))
        report.append(row)
    if out: raise AssertionError(f'Python outputs not compared: {list(out)}')
summary=pd.DataFrame(report); summary.to_csv(root/'comparison.csv',index=False)
(root/'findings.json').write_text(json.dumps(findings,indent=2))
failed=summary[(summary.max_scaled>1e-8)|(summary.max_rel_nonzero>1e-8)|~summary.nonfinite_match]
print(f'{len(summary)} arrays/scalars, {summary.n.sum()} numeric entries; failures={len(failed)}')
print(failed.to_string(index=False))
print('Largest relative discrepancies:'); print(summary.nlargest(15,'max_rel').to_string(index=False))
if len(failed): raise SystemExit(1)
