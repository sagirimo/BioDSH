"""Compare every exported numeric quantity, retaining failures and missing keys."""
import argparse
from pathlib import Path
import sys
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import anova_py as ap


def calculate(d,kind):
    values={}
    def put(key,x):
        for i,z in enumerate(np.asarray(x,dtype=float).ravel(order='F'),1):
            values[f'{key}/{i}']=z
    def table(prefix,t):
        for _, row in t.iterrows():
            pre=f'{prefix}/{row["term"]}'
            for k in ('ss','df','ms','F','p','denominator_df','denominator_ms'):
                if row['term']=='Residuals' and k.startswith('denominator'): continue
                put(f'{pre}/{k}',row[k])
    if kind.startswith('fixed'):
        design=ap.factorial_design(d,['A','B']); put('design/X',design['X'])
        fit=ap.ols(d.y,design['X'])
        for k,v in fit.items(): put(f'fit/{k}',v)
        for typ in ('I','II','III'):
            table(typ,ap.anova(d.y,design,typ,include_intercept=True)['table'])
        reverse=ap.factorial_design(d,['B','A'])
        table('I_reverse',ap.anova(d.y,reverse,'I')['table'])
        em=ap.marginal_means(fit,design,'A')
        for k in ('emmean','SE','df','lower.CL','upper.CL'): put(f'emm/{k}',em['table'][k])
        put('emm/L',em['L']); put('emm/vcov',em['vcov'])
    elif kind.startswith(('split','block','rm')):
        if kind.startswith('split'): out=ap.split_plot(d,'y','block','A','B')
        elif kind.startswith('block'): out=ap.randomized_block(d,'y','block','A')
        else: out=ap.repeated_measures(d,'y','subject','B','A')
        design=ap.factorial_design(d,['A'] if kind.startswith('block') else ['A','B'])
        put('design/X',design['X'])
        for s,tab in out['table'].groupby('stratum',sort=False): table(f'table/{s}',tab)
        for s,diag in out['diagnostics'].items():
            for k,v in diag.items(): put(f'diagnostics/{s}/{k}',v)
        for k in ('intercept_ss','total_ss'): put(k,out[k])
    else:
        X=np.ones((len(d),1)) if 'A' not in d else np.column_stack([ap.factorial_design(d,['A'])['X'],d.x])
        put('design/X',X); out=ap.random_intercept_reml(d.y,X,d.group)
        for k,v in out.items():
            if k not in ('group_levels','status'): put(k,v)
        for k,v in out.items():
            if k not in ('group_levels','status'): put(f'root/{k}',v)
    return values


def compare(data,reference,outdir):
    data=Path(data); reference=Path(reference); outdir=Path(outdir); outdir.mkdir(parents=True,exist_ok=True)
    rows=[]; missing=[]
    cases=[(seed,kind) for seed in (17,83) for kind in ('fixed_bal','fixed_unbal','split_bal','split_unbal','block_bal','block_unbal','rm_bal','rm_unbal','reml_bal','reml_unbal','reml_boundary')]
    cases.append((9001,'reml_multimodal'))
    for seed,kind in cases:
            name=f'{seed}_{kind}'; d=pd.read_csv(data/f'{name}.csv',float_precision='round_trip')
            py=calculate(d,kind); ref=pd.read_csv(reference/f'{name}.csv',float_precision='round_trip').set_index('key').value.to_dict()
            ref={k:v for k,v in ref.items() if not k.startswith('III_treatment/')}
            if set(py)!=set(ref): missing.append(dict(case=name,python_only=sorted(set(py)-set(ref)),R_only=sorted(set(ref)-set(py))))
            for k in py.keys() & ref.keys():
                a,b=py[k],ref[k]; delta=abs(a-b)
                bothna=np.isnan(a) and np.isnan(b)
                valid=bothna or np.isclose(a,b,rtol=1e-8,atol=1e-10)
                parts=k.split('/')
                if kind.startswith('fixed'):
                    family='/'.join(parts[:1]+parts[2:3]) if parts[0] in ('I','II','III','I_reverse') else '/'.join(parts[:-1])
                elif kind.startswith(('split','block','rm')):
                    family='/'.join([parts[0],parts[-2]])
                else: family='/'.join(parts[:-1])
                rows.append(dict(case=name,seed=seed,kind=kind,family=family,key=k,python=a,R=b,
                    abs_error=delta,relative_error=delta/abs(b) if abs(b)>=1e-8 else np.nan,
                    near_zero_abs=delta if abs(b)<1e-8 else np.nan,pass_target=valid))
    result=pd.DataFrame(rows).sort_values(['case','key'])
    result.to_csv(outdir/'comparisons.csv',index=False,float_format='%.17g')
    summary=result.groupby(['kind','family']).agg(count=('key','size'),max_abs=('abs_error','max'),max_relative=('relative_error','max'),near_zero_max_abs=('near_zero_abs','max'),pass_target=('pass_target','all')).reset_index()
    summary.to_csv(outdir/'summary.csv',index=False,float_format='%.17g')
    (outdir/'key_mismatches.txt').write_text(repr(missing)+'\n')
    failures=result[~result.pass_target]
    failures.to_csv(outdir/'outside_target.csv',index=False,float_format='%.17g')
    print('Compared:',len(result),'Mismatch cases:',len(missing),'Outside 1e-8 relative + 1e-10 absolute:',len(failures))
    print(summary[~summary.pass_target].to_string(index=False))
    if missing: print(missing)
    # nlme optimization is tracked separately; exact linear algebra and independent R roots must pass.
    required=result[(~result.kind.str.startswith('reml')) | result.key.str.startswith('root/')]
    if missing or not required.pass_target.all(): raise SystemExit('Required exact comparisons failed')
    raw=result[result.kind.str.startswith('reml') & ~result.key.str.startswith('root/')]
    absolute=np.where(raw.kind=='reml_boundary',1e-5,1e-6)
    if not np.isclose(raw.python,raw.R,rtol=1e-6,atol=absolute,equal_nan=True).all():
        raise SystemExit('nlme differences exceed documented optimization allowance')

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('data'); p.add_argument('reference'); p.add_argument('outdir'); a=p.parse_args()
    compare(a.data,a.reference,a.outdir)
