"""Deterministic generic simulations; no benchmark questions or answers used."""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd


def make(seed):
    rng = np.random.default_rng(seed)
    sizes = [1, 2, 3, 5, 7, 9, 11, 14, 17, 21, 25] if seed == 1 else [1, 3, 4, 8, 13, 21, 34]
    cluster = np.repeat(np.arange(len(sizes)), sizes).astype(float)
    n = len(cluster)
    x = rng.normal(size=n)
    x[0] = 5.5 if seed == 1 else 7.
    z = rng.choice([0., 1., 2.], n, p=[.6, .3, .1])
    w = rng.uniform(.3, 2.3, n)
    offset = rng.uniform(-.3, .3, n)
    random_effect = rng.normal(0, .35, len(sizes))[cluster.astype(int)]
    eta = -.3 + .25*x - .15*z + offset + random_effect
    prob = 1/(1+np.exp(-eta))
    trials = rng.integers(2, 10, n)
    data = pd.DataFrame(dict(cluster=cluster, x=x, z=z, weight=w, offset=offset,
        y=1+.45*x-.25*z+offset+random_effect+rng.normal(size=n)*(.5+.4*np.abs(x)),
        binomial=rng.binomial(1, prob), poisson=rng.poisson(np.exp(eta)),
        trials=trials, proportion=rng.binomial(trials, prob)/trials))
    data.loc[7, 'x'] = np.nan
    data.loc[15, 'y'] = np.nan
    data.loc[22, 'cluster'] = np.nan
    return data


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('outdir', type=Path)
    args = parser.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)
    for seed in (1, 2):
        make(seed).to_csv(args.outdir/f'seed{seed}.csv', index=False)
