import sys, numpy as np, pandas as pd
sys.path.insert(0, sys.argv[1])
from limma_py import tmm_factors, voom, lm_fit, e_bayes, p_adjust_bh, lowess_r
d = sys.argv[2]
cnt = pd.read_csv(f'{d}/counts.csv', index_col=0).to_numpy(); cv = pd.read_csv(f'{d}/covars.csv')
X = np.c_[np.ones(len(cv)), cv.grp, cv.age]
nf = tmm_factors(cnt); lib = cnt.sum(0) * nf
v = voom(cnt, X, lib_size=lib); fit = e_bayes(lm_fit(v['E'], X, v['weights']))
r = lambda f: pd.read_csv(f'{d}/{f}')
def rel(a, b): a, b = np.asarray(a, float), np.asarray(b, float); return float(np.nanmax(np.abs(a - b) / np.maximum(np.abs(b), 1e-12)))
sx, sy = r('r_xy.csv').sx.to_numpy(), r('r_xy.csv').sy.to_numpy()
lx, ly = lowess_r(sx, sy, f=v["span"])
rf = r('r_fit.csv'); pr = r('r_prior.csv')
print('TMM factors   max rel diff', rel(nf, r('r_nf.csv').nf))
print('voom x/y      max rel diff', rel(v['trend'][0][cnt.sum(1) != 0], sx), rel(v['trend'][1][cnt.sum(1) != 0], sy))
print('lowess (same input) max rel diff', rel(ly, r('r_lowess.csv').ly))
print('voom weights  max rel diff', rel(v['weights'], r('r_w.csv').to_numpy()))
print('prior df      ', fit['df_prior'], 'R', pr.d0[0], ' prior var', fit['s2_prior'], 'R', pr.s0[0])
print('coef/t/p/padj max rel diff', rel(fit['coefficients'][:, 1], rf.coef), rel(fit['t'][:, 1], rf.t), rel(fit['p_value'][:, 1], rf.p), rel(p_adjust_bh(fit['p_value'][:, 1]), rf.padj))
print('df.total      max rel diff', rel(fit['df_total'], rf.dft))
