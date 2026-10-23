"""Behavioral invariants, unsupported inputs, and a single-thread timing smoke test."""
from pathlib import Path
import argparse
import json
import sys
from time import perf_counter
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import anova_py as ap


def run(data,out):
    data=Path(data); checks=[]
    def check(name,condition):
        assert condition,name
        checks.append(name)
    def rejects(name,call):
        try: call()
        except ValueError: checks.append(name); return
        raise AssertionError(name+' did not reject unsupported input')
    for seed in (17,83):
        prefix=str(seed)
        d=pd.read_csv(data/f'{seed}_split_bal.csv')
        s=ap.split_plot(d,'y','block','A','B')
        tab=s['table'].set_index(['stratum','term'])
        check(prefix+' whole-plot denominator df',tab.loc[('block:A','A'),'denominator_df']==14)
        for term in ('B','A:B'):
            check(prefix+' subplot denominator '+term,tab.loc[('Within',term),'denominator_df']==21)
        for kind in ('split_bal','split_unbal','block_bal','block_unbal','rm_bal','rm_unbal'):
            dd=pd.read_csv(data/f'{seed}_{kind}.csv')
            if kind.startswith('split'): result=ap.split_plot(dd,'y','block','A','B')
            elif kind.startswith('block'): result=ap.randomized_block(dd,'y','block','A')
            else: result=ap.repeated_measures(dd,'y','subject','B','A')
            check(prefix+' SS conservation '+kind,np.isclose(result['table'].ss.sum()+result['intercept_ss'],result['total_ss'],rtol=1e-12))
            check(prefix+' df conservation '+kind,result['table'].df.sum()==len(dd)-1)
        f=pd.read_csv(data/f'{seed}_fixed_unbal.csv'); design=ap.factorial_design(f,['A','B'])
        fit=ap.ols(f.y,design['X'])
        check(prefix+' OLS normal equation',np.max(abs(design['X'].T@fit['residual']))<1e-10)
        check(prefix+' covariance symmetric',np.allclose(fit['vcov'],fit['vcov'].T))
        t=ap.anova(f.y,design,'III')['table'].set_index('term')
        # Direct coefficient-block Wald F must reproduce Type III partial SS.
        c=design['term_columns']['A']; b=fit['beta'][c]
        F=b@np.linalg.solve(fit['vcov'][np.ix_(c,c)],b)/len(c)
        check(prefix+' Type III coefficient Wald',np.isclose(F,t.loc['A','F'],rtol=1e-12))
        for coding in ('sum','treatment'):
            dx=ap.factorial_design(f,['A','B'],coding=coding)
            check(prefix+' Type II coding invariant '+coding,np.allclose(ap.anova(f.y,dx,'II')['table'].ss,ap.anova(f.y,design,'II')['table'].ss))
        empty=f[~((f.A=='a0')&(f.B=='b0'))]
        rejects(prefix+' empty factorial cell',lambda:ap.anova(empty.y,ap.factorial_design(empty,['A','B']),'III'))
        rejects(prefix+' treatment-coded Type III',lambda:ap.anova(f.y,ap.factorial_design(f,['A','B'],coding='treatment'),'III'))
        nan=f.copy(); nan.loc[0,'y']=np.nan
        rejects(prefix+' missing response',lambda:ap.ols(nan.y,design['X']))
        nan=f.copy(); nan.loc[0,'A']=np.nan
        rejects(prefix+' missing factor',lambda:ap.factorial_design(nan,['A','B']))
        rm=pd.read_csv(data/f'{seed}_rm_bal.csv')
        rejects(prefix+' missing repeated occasion',lambda:ap.repeated_measures(rm.iloc[1:],'y','subject','B','A'))
        rejects(prefix+' duplicate repeated occasion',lambda:ap.repeated_measures(pd.concat([rm,rm.iloc[:1]]),'y','subject','B','A'))
        bad=rm.copy(); bad.loc[0,'A']='a1'
        rejects(prefix+' between factor varies in subject',lambda:ap.repeated_measures(bad,'y','subject','B','A'))
        mixed=pd.read_csv(data/f'{seed}_reml_unbal.csv')
        X=np.column_stack([ap.factorial_design(mixed,['A'])['X'],mixed.x]); m=ap.random_intercept_reml(mixed.y,X,mixed.group)
        order=np.random.default_rng(seed).permutation(len(mixed))
        shuffled=ap.random_intercept_reml(mixed.y.to_numpy()[order],X[order],mixed.group.to_numpy()[order])
        check(prefix+' REML row-order invariance',np.allclose(m['vcov'],shuffled['vcov'],rtol=1e-10))
        rejects(prefix+' random intercept absorbed by fixed',lambda:ap.random_intercept_reml(mixed.y,ap.indicator(mixed.group),mixed.group))
        rejects(prefix+' unidentifiable singleton groups',lambda:ap.random_intercept_reml(mixed.y,X,np.arange(len(mixed))))
        boundary=pd.read_csv(data/f'{seed}_reml_boundary.csv')
        bfit=ap.random_intercept_reml(boundary.y,np.ones((len(boundary),1)),boundary.group)
        check(prefix+' exact zero variance component',bfit['tau2']==0 and bfit['status']=='boundary' and bfit['score']>0)
        rejects(prefix+' mixed EMM needs explicit df',lambda:ap.marginal_means(bfit,design,'A'))
    multimodal=pd.read_csv(data/'9001_reml_multimodal.csv')
    X=np.ones((len(multimodal),1))
    mm=ap.random_intercept_reml(multimodal.y,X,multimodal.group)
    ol=ap.ols(multimodal.y,X)
    ll0=-.5*(ol['df_residual']*(np.log(2*np.pi*ol['sigma2'])+1)+np.log(len(multimodal)))
    check('multimodal REML selects interior minimum',mm['status']=='interior' and mm['loglik']>ll0+.4)
    check('multimodal REML score root',abs(mm['score'])<1e-10)
    check('multimodal variance ratio reference',abs(mm['variance_ratio']-.6263051)<1e-7)
    # Each model is fitted to 3000 rows; import/data generation excluded.
    rng=np.random.default_rng(340); n=3000
    timing=[]
    def timed(name,call):
        durations=[]
        for _ in range(3):
            start=perf_counter(); call(); durations.append(perf_counter()-start)
        timing.append(dict(method=name,n=n,seconds_min=min(durations),seconds_median=float(np.median(durations)),seconds_max=max(durations)))
    d=pd.DataFrame([(f'r{r:02}',f'a{a}',f'b{b}') for r in range(50) for a in range(3) for b in range(20)],columns=['block','A','B'])
    d['y']=rng.normal(size=n); design=ap.factorial_design(d,['A','B'])
    timed('anova_II_60_columns',lambda:ap.anova(d.y,design,'II'))
    timed('split_plot_50_blocks_3x20',lambda:ap.split_plot(d,'y','block','A','B'))
    timed('randomized_block_50_blocks',lambda:ap.randomized_block(d,'y','block','A'))
    rm=pd.DataFrame({'subject':np.repeat([f's{i:03}' for i in range(300)],10),'B':np.tile([f'b{i:02}' for i in range(10)],300),'y':rng.normal(size=n)})
    timed('repeated_measures_300_subjects_10_times',lambda:ap.repeated_measures(rm,'y','subject','B'))
    X=np.column_stack([np.ones(n),rng.normal(size=(n,3))]); group=np.repeat(np.arange(300),10)
    y=X@np.array([1.,.2,-.3,.4])+np.repeat(rng.normal(size=300),10)+rng.normal(size=n)
    timed('reml_300_groups_4_columns',lambda:ap.random_intercept_reml(y,X,group))
    report=dict(checks_passed=len(checks),checks=checks,timing=timing,versions=dict(python=sys.version,numpy=np.__version__,pandas=pd.__version__))
    import scipy
    report['versions']['scipy']=scipy.__version__
    Path(out).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'checks_passed':len(checks),'timing':timing},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('data');p.add_argument('out');a=p.parse_args();run(a.data,a.out)
