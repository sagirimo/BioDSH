# synthetic RSEM-like fractional counts with a group effect, a continuous covariate and some all-zero/low genes
import numpy as np, pandas as pd, sys
rng = np.random.default_rng(int(sys.argv[1]) if len(sys.argv) > 1 else 1)
G, N = 4000, 24
mu = np.exp(rng.normal(3, 2, G))
grp = np.r_[np.zeros(10), np.ones(14)]; age = rng.normal(60, 12, N)
eff = np.where(rng.random(G) < 0.1, rng.normal(0, 1.2, G), 0)
lib = rng.uniform(0.5, 2.0, N)
m = mu[:, None] * lib[None] * np.exp(eff[:, None] * grp[None] + 0.01 * (age - 60)[None])
disp = 0.1 + 1 / np.sqrt(mu)[:, None]
c = rng.negative_binomial(1 / disp, 1 / (1 + m * disp)).astype(float)
c = c * rng.uniform(0.85, 1.0, c.shape)            # fractional expected counts
c[:50] = 0                                         # all-zero genes
pd.DataFrame(c, index=[f'g{i}' for i in range(G)]).to_csv(sys.argv[2])
pd.DataFrame({'grp': grp, 'age': age}).to_csv(sys.argv[3], index=False)
