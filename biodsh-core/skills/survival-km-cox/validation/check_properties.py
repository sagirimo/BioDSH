"""Behavioral checks independent of the R export and single-thread speed test."""
import sys, json, time, os
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from survival_py import (administrative_censor, kaplan_meier, logrank, rmst, rmst_difference,
                         coxph, cox_components, baseline_hazard, predict_survival)
from make_data import simulate
root=Path(sys.argv[1]); results={}
d=simulate(20261021,403); t=d.time.to_numpy(); e=d.status.to_numpy(); x=d[['group','x']].to_numpy(); s=d.stratum.to_numpy(); c=d.cluster.to_numpy()
checks=0
def close(a,b,atol=1e-8):
    global checks
    np.testing.assert_allclose(a,b,atol=atol,rtol=1e-8,equal_nan=True); checks+=1

def rejects(fn):
    global checks
    try: fn()
    except (ValueError,RuntimeError,np.linalg.LinAlgError): checks+=1; return
    raise AssertionError('expected an explicit invalid-input/nonestimability failure')

for ties in ['breslow','efron']:
    f=coxph(t,e,x,strata=s,cluster=c,ties=ties)
    beta=np.array([.23,-.17]); comp=cox_components(t,e,x,beta,s,ties)
    h=1e-5; grad=[]; hess=[]
    for j in range(2):
        dv=np.eye(2)[j]*h
        p=cox_components(t,e,x,beta+dv,s,ties); m=cox_components(t,e,x,beta-dv,s,ties)
        grad.append((p['loglik']-m['loglik'])/(2*h)); hess.append(-(p['score']-m['score'])/(2*h))
    close(grad,comp['score'],atol=3e-8); close(np.array(hess).T,comp['information'],atol=3e-8)
    close(comp['score_residuals'].sum(0),comp['score'])
    close(f['score_residuals'].sum(0),f['score'])
    close(sum(a['information'].sum(0) for a in f['tables']),f['information'])
    close(sum(a['loglik'].sum() for a in f['tables']),f['loglik'])
    rng=np.random.default_rng(20); order=rng.permutation(len(t))
    perm=coxph(t[order],e[order],x[order],s[order],c[order],ties)
    close(perm['coefficients'],f['coefficients']); close(perm['covariance'],f['covariance'])
    shifted=coxph(t,e,x+np.array([1e4,-1e4]),s,c,ties)
    close(shifted['coefficients'],f['coefficients']); close(shifted['covariance'],f['covariance'])
    for method in ['breslow']+(['efron'] if ties=='efron' else []):
        pr=predict_survival(f,[[.4,-.2]],[0,1,3,7,10],strata=[0],method=method)
        bh=baseline_hazard(f,method,reference=[0,0])[0]
        h0=np.r_[0,bh['cumulative_hazard']][np.searchsorted(bh['time'],[0,1,3,7,10],side='right')]
        close(pr,np.exp(-h0*np.exp(np.array([.4,-.2])@f['coefficients']))[None,:])
        assert np.all(np.diff(pr)<=1e-14); checks+=1
    # A stratum with no events contributes no likelihood/score, has S(t)=1.
    ee=e.copy(); ee[s==2]=0
    noevent=coxph(t,ee,x,s,ties=ties)
    close(predict_survival(noevent,[[.4,-.2]],[0,1,3,7],strata=[2]),np.ones((1,4)))
    use=s!=2; smaller=coxph(t[use],ee[use],x[use],s[use],ties=ties)
    close(noevent['coefficients'],smaller['coefficients'])

for tt,dd in [([0,1,1,3],[0,0,0,0]),([0,0,0],[1,1,1]),([0,1,2],[1,1,1])]:
    a=rmst(tt,dd,max(tt)); assert a['variance']>=0; checks+=1
close(rmst([1,2,3],[0,0,0],2.5)['estimate'],2.5)
close(rmst([1,2,3],[1,1,1],3)['estimate'],2)
close(rmst([1,2,3],[1,1,1],3)['variance'],2/9)
close(rmst(t,e,0)['estimate'],0)
close(administrative_censor([1,2,3],[1,1,1],2)[1],[1,1,0])
td,ed=administrative_censor(t,e,10); close(rmst(t,e,10)['estimate'],rmst(td,ed,10)['estimate']); close(rmst(t,e,10)['variance'],rmst(td,ed,10)['variance'])
# Every group/covariate/label must be filtered by the same explicit mask.
rejects(lambda: kaplan_meier([1,np.nan],[1,0])); rejects(lambda: kaplan_meier([1,2],[1,np.nan]))
rejects(lambda: kaplan_meier([-1,2],[1,0])); rejects(lambda: kaplan_meier([1,2],[1,2]))
rejects(lambda: kaplan_meier([1,2],[1,0],alpha=1)); rejects(lambda: rmst([1,2],[1,0],3))
rejects(lambda: coxph(t,e,np.c_[x,np.ones(len(x))])); rejects(lambda: coxph(t,e,np.c_[x,x[:,0]]))
rejects(lambda: coxph(t,np.zeros(len(t)),x)); rejects(lambda: coxph(t,e,x,strata=np.full(len(t),np.nan)))
rejects(lambda: coxph(t,e,x,cluster=np.full(len(t),np.nan)))
rejects(lambda: coxph(t,e,x,ties='exact')); rejects(lambda: coxph(t,e,x,max_iter=1))
xx=x.copy(); xx[0,0]=np.nan; rejects(lambda: coxph(t,e,xx))
rejects(lambda: coxph([1,2,3,4],[1,1,0,0],[[1],[1],[0],[0]]))
f=coxph(t,e,x,s); rejects(lambda: predict_survival(f,[[0,0]],[1])); rejects(lambda: predict_survival(f,[[0,0]],[100],strata=[0])); rejects(lambda: predict_survival(f,[[0,0]],[1],strata=[9]))
no=logrank([1,2,3,4],[0,0,0,0],[0,0,1,1]); assert no['df']==0 and np.isnan(no['p_value']); checks+=1
rejects(lambda: logrank([1,2,1,2],[1,1,1,1],[0,0,1,1],[0,0,1,1]))
results['property_checks']=checks
# Timings exclude imports and CSV IO; preexisting modules only numpy/scipy/pandas.
big=simulate(20261021,5000); t=big.time.to_numpy(); e=big.status.to_numpy(); x=big[['group','x']].to_numpy(); s=big.stratum.to_numpy(); c=big.cluster.to_numpy()
operations={'km':lambda:kaplan_meier(t,e), 'logrank_stratified':lambda:logrank(t,e,big.group,s), 'rmst_difference':lambda:rmst_difference(t,e,big.group,10), 'cox_breslow':lambda:coxph(t,e,x,s,c,ties='breslow'), 'cox_efron':lambda:coxph(t,e,x,s,c,ties='efron')}
for name,fn in operations.items():
    fn(); timing=[]
    for _ in range(5):
        start=time.perf_counter(); fn(); timing.append(time.perf_counter()-start)
    results[name]={'seconds_min':min(timing),'seconds_median':float(np.median(timing)),'seconds_max':max(timing)}
    assert max(timing)<1, (name,timing)
results['speed_n']=5000; results['speed_p']=2
results['versions']={k:__import__(k).__version__ for k in ['numpy','scipy','pandas']}
results['thread_env']={k:os.environ.get(k) for k in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']}
(root/'properties.json').write_text(json.dumps(results,indent=2)); print(json.dumps(results,indent=2))
