"""Deterministic generic survival simulations, independent of benchmarks."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

def simulate(seed, n):
    rng = np.random.default_rng(seed)
    g = rng.binomial(1, .31, n)
    x = rng.normal(size=n)
    s = rng.choice(3, n, p=[.5, .3, .2])
    cluster = np.arange(n) // 5
    frailty = rng.normal(0, .25, cluster.max()+1)[cluster]
    event = rng.exponential(1/(.09*np.exp(.48*g-.3*x+.25*s+frailty)))
    censor = rng.uniform(2, 19, n)
    time = np.minimum(event, censor)
    status = (event <= censor).astype(int)
    if seed == 20261021:
        time = np.round(time*2)/2  # event/censor ties and events at zero
    return pd.DataFrame(dict(time=time,status=status,group=g,x=x,stratum=s,cluster=cluster))

if __name__ == '__main__':
    out = Path(sys.argv[1]); out.mkdir(parents=True,exist_ok=True)
    for seed,n in [(20261020,257),(20261021,403)]:
        simulate(seed,n).to_csv(out/f'data_{seed}.csv',index=False)
    pd.DataFrame(dict(time=[0,1,1,2,3,3,4,4],status=[0,1,0,1,0,1,1,1],group=[0,0,1,1,0,1,0,1])).to_csv(out/'edge.csv',index=False)
