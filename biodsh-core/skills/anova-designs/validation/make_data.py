"""Generate deterministic generic designs; no benchmark data is used."""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd


def generate(out):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    for seed in (17, 83):
        rng = np.random.default_rng(seed)
        def save(name, data):
            data.to_csv(out / f'{seed}_{name}.csv', index=False, float_format='%.17g')
        for balanced in (True, False):
            rows=[]
            for a in range(3):
                for b in range(2):
                    for _ in range(8 if balanced else [[3,12],[9,4],[5,14]][a][b]):
                        rows.append((f'a{a}',f'b{b}',2+.7*a-.5*b+.45*a*b+rng.normal()))
            save('fixed_bal' if balanced else 'fixed_unbal',pd.DataFrame(rows,columns=['A','B','y']))
        rows=[]
        for r in range(8):
            u=rng.normal(0,1.1)
            for a in range(3):
                v=rng.normal(0,.8)
                for b in range(2):
                    rows.append((f'r{r}',f'a{a}',f'b{b}',3+.8*a-.6*b+.3*a*b+u+v+rng.normal(0,.5)))
        split=pd.DataFrame(rows,columns=['block','A','B','y'])
        save('split_bal',split)
        save('split_unbal',split.drop(index=[0,9,28,35]).reset_index(drop=True))
        block=split.groupby(['block','A'],as_index=False)['y'].mean()
        save('block_bal',block)
        save('block_unbal',block.drop(index=[0,7]).reset_index(drop=True))
        for balanced in (True,False):
            rows=[]; subj=0
            for a in range(2):
                for _ in range(8 if balanced else [6,11][a]):
                    u=rng.normal(0,1.2)
                    for b in range(3):
                        rows.append((f's{subj:02}',f'a{a}',f'b{b}',1+.5*a+.4*b+.2*a*b+u+rng.normal(0,.7)))
                    subj+=1
            save('rm_bal' if balanced else 'rm_unbal',pd.DataFrame(rows,columns=['subject','A','B','y']))
        for balanced in (True,False):
            rows=[]
            for j in range(24):
                u=rng.normal(0,1.3)
                for _ in range(7 if balanced else 3+j%9):
                    x=rng.normal(); a=j%2
                    rows.append((f'g{j:02}',f'a{a}',x,1+.8*a-.6*x+u+rng.normal(0,.65)))
            save('reml_bal' if balanced else 'reml_unbal',pd.DataFrame(rows,columns=['group','A','x','y']))
        # Exact zero group means after fitting the intercept: REML optimum at tau2=0.
        rows=[]
        for j in range(12):
            z=rng.normal(size=5); z-=z.mean()
            for y in z: rows.append((f'g{j:02}',2+y))
        save('reml_boundary',pd.DataFrame(rows,columns=['group','y']))
    # Reproducible heterogeneous-noise stress case with two REML score roots.
    # Its fitted model remains a homoscedastic random-intercept model.
    rng=np.random.default_rng(9001); group=np.repeat(np.arange(4),[2,3,10,40])
    for _ in range(168):
        y=rng.normal(size=len(group))*rng.uniform(.2,3,4)[group]+rng.normal(size=4)[group]*rng.uniform(0,3)
    pd.DataFrame({'group':[f'g{g}' for g in group],'y':y}).to_csv(
        out/'9001_reml_multimodal.csv',index=False,float_format='%.17g')

if __name__ == '__main__':
    p=argparse.ArgumentParser(); p.add_argument('out'); generate(p.parse_args().out)
