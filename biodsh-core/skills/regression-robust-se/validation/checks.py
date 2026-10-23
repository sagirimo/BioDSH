"""Independent invariants, explicit rejection cases, and single-thread timing."""
import json
import os
from pathlib import Path
import platform
import sys
import time
import numpy as np
import scipy
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from robust_se import (fit_linear, fit_glm, vcov_hc, vcov_cluster,
                       coefficient_test, wald_test)


def main(outdir):
    checked = []

    def close(name, x, y):
        np.testing.assert_allclose(x, y, rtol=1e-10, atol=1e-12)
        checked.append(name)

    def rejects(name, fn):
        try:
            fn()
        except ValueError:
            checked.append(name)
        else:
            raise AssertionError(f'{name}: expected ValueError')

    rng = np.random.default_rng(20261020)
    n = 120
    X = np.c_[np.ones(n), rng.normal(size=(n, 2))]
    w = rng.uniform(.3, 2., n)
    eta = X @ np.array([.2, .3, -.1])
    y = eta + rng.normal(size=n)
    cl = np.repeat(np.arange(12), 10)
    perm = rng.permutation(n)
    original = [a.copy() for a in (X, y, w, cl)]
    for name, fitfun, response, weight in (
        ('ols', fit_linear, y, None), ('wls', fit_linear, y, w),
        ('binomial', fit_glm, rng.binomial(1, 1/(1+np.exp(-eta))), None),
        ('poisson', lambda x,y,**kw: fit_glm(x,y,family='poisson',**kw),
         rng.poisson(np.exp(eta)), w),
    ):
        fit = fitfun(X, response, weights=weight)
        reordered = fitfun(X[perm], response[perm],
                           weights=None if weight is None else weight[perm])
        close(f'{name}: row-order coefficients', fit['coefficients'], reordered['coefficients'])
        close(f'{name}: score equation', fit['scores'].sum(0), np.zeros(3))
        close(f'{name}: hat trace', fit['hat'].sum(), 3.)
        for cr, hc in [('CR0','HC0'), ('CR1S','HC1'), ('CR2','HC2')]:
            target = 1/w if cr=='CR2' and name=='wls' else None
            close(f'{name}: singleton {cr}={hc}',
                  vcov_cluster(fit, np.arange(n), cr, target=target)['cov'],
                  vcov_hc(fit, hc)['cov'])
        for kind in ('CR0','CR1','CR1S','CR2'):
            v = vcov_cluster(fit, cl, kind)
            close(f'{name}: {kind} row-order covariance', v['cov'],
                  vcov_cluster(reordered, cl[perm], kind)['cov'])
            close(f'{name}: {kind} sandwich identity', v['cov'],
                  v['bread'] @ v['meat'] @ v['bread']/n)
            close(f'{name}: {kind} meat identity', v['meat'],
                  v['cluster_scores'].T @ v['cluster_scores']/n)
        for df in (np.inf, 11):
            v = vcov_cluster(fit, cl)['cov']
            ct = coefficient_test(fit, v, df=df)
            wt = wald_test(fit, [0, 1, 0], covariance=v, df=df)
            close(f'{name}: Wald=t² df={df}', wt['statistic'], ct['statistic'][1]**2)
            close(f'{name}: Wald/coeftest p df={df}', wt['p_value'], ct['p_value'][1])
    for before, after, label in zip(original, (X,y,w,cl), ('X','y','weights','cluster')):
        close(f'input unchanged: {label}', before, after)
    f = fit_linear(X, y, w)
    scaled = fit_linear(X, y, w*10)
    close('WLS scale-invariant coefficients', f['coefficients'], scaled['coefficients'])
    close('WLS scale-invariant model covariance', f['model_cov'], scaled['model_cov'])
    close('WLS scale-invariant CR2', vcov_cluster(f, cl, 'CR2')['cov'],
          vcov_cluster(scaled, cl, 'CR2')['cov'])
    rejects('missing X', lambda: fit_linear(np.where(X>.5, np.nan, X), y))
    rejects('rank deficient X', lambda: fit_linear(np.c_[X, X[:,1]], y))
    rejects('n <= p', lambda: fit_linear(np.eye(3), y[:3]))
    rejects('zero weights', lambda: fit_linear(X, y, np.zeros(n)))
    rejects('negative weights', lambda: fit_linear(X, y, -w))
    rejects('invalid offset', lambda: fit_linear(X, y, offset=[0]))
    rejects('invalid binomial response', lambda: fit_glm(X, y))
    rejects('invalid Poisson response', lambda: fit_glm(X, np.full(n,.5), 'poisson'))
    rejects('invalid family', lambda: fit_glm(X, y, 'gamma'))
    rejects('nonconvergence', lambda: fit_glm(X, (y>0).astype(float), max_iter=1))
    rejects('complete separation', lambda: fit_glm(X, (X[:,1]>0).astype(float)))
    rejects('one cluster', lambda: vcov_cluster(f, np.ones(n)))
    rejects('missing cluster', lambda: vcov_cluster(f, np.full(n,np.nan)))
    rejects('short cluster', lambda: vcov_cluster(f, cl[:-1]))
    rejects('invalid CR kind', lambda: vcov_cluster(f, cl, 'CR3'))
    rejects('target used outside CR2', lambda: vcov_cluster(f, cl, target=w))
    rejects('nonpositive CR2 target', lambda: vcov_cluster(f, cl, 'CR2', target=-w))
    rejects('invalid HC kind', lambda: vcov_hc(f, 'HC4'))
    rejects('nonpositive df', lambda: coefficient_test(f, df=0))
    rejects('invalid level', lambda: coefficient_test(f, level=1))
    rejects('negative variance', lambda: coefficient_test(f, -np.eye(3)))
    rejects('asymmetric covariance', lambda: coefficient_test(f, np.triu(np.ones((3,3)))))
    rejects('rank deficient contrast', lambda: wald_test(f, [[0,1,0],[0,1,0]]))
    rejects('nonfinite null', lambda: wald_test(f, [0,1,0], null=np.nan))
    rejects('singular Wald covariance', lambda: wald_test(f, [0,1,0], covariance=np.zeros((3,3))))
    leverage_X = np.c_[np.ones(10), np.r_[1.,np.zeros(9)]]
    leverage_fit = fit_linear(leverage_X, np.arange(10))
    rejects('HC2 unit leverage', lambda: vcov_hc(leverage_fit,'HC2'))
    rejects('CR2 singular block', lambda: vcov_cluster(leverage_fit,np.arange(10),'CR2'))

    # Whole pipeline timing: four models, each HC0-3 + CR0/1/1S/2 + tests.
    n = 3000
    X = np.c_[np.ones(n), rng.normal(size=(n,4))]
    eta = X @ np.array([.1,.1,-.2,.15,.1])
    ys = [eta+rng.normal(size=n), rng.binomial(1,1/(1+np.exp(-eta))),
          rng.poisson(np.exp(eta))]
    w = rng.uniform(.5,2,n)
    cl = np.repeat(np.arange(60),50)

    def pipeline():
        fits = [fit_linear(X,ys[0]), fit_linear(X,ys[0],w),
                fit_glm(X,ys[1]), fit_glm(X,ys[2],'poisson')]
        for fit in fits:
            for hc in ('HC0','HC1','HC2','HC3'):
                vcov_hc(fit,hc)
            for cr in ('CR0','CR1','CR1S','CR2'):
                v = vcov_cluster(fit,cl,cr)
                coefficient_test(fit,v['cov'],df=59)
                wald_test(fit,[0,1,0,0,0],covariance=v['cov'],df=59)

    pipeline()  # excludes imports and warmup from timing
    elapsed = []
    for _ in range(5):
        start = time.perf_counter()
        pipeline()
        elapsed.append(time.perf_counter()-start)
    report = dict(check_count=len(checked), checks=checked,
                  python=platform.python_version(), numpy=np.__version__,
                  scipy=scipy.__version__, pandas=pd.__version__,
                  thread_env={k:os.getenv(k) for k in
                              ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')},
                  benchmark=dict(n=3000,p=5,clusters=60,cluster_size=50,
                                 pipeline_seconds=elapsed, median_seconds=float(np.median(elapsed)),
                                 max_seconds=max(elapsed), under_one_second=max(elapsed)<1))
    Path(outdir, 'checks.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f'{len(checked)} independent checks passed; four-model pipeline times: {elapsed}')
    assert max(elapsed)<1, 'Performance target missed on this machine; inspect checks.json'


if __name__ == '__main__':
    main(sys.argv[1])
