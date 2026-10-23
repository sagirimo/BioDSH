"""Compare every exported R scalar, including column-major matrix entries."""
import argparse
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from robust_se import (fit_linear, fit_glm, vcov_hc, vcov_cluster,
                       coefficient_test, wald_test)


def calculate(raw):
    keep = raw.notna().all(axis=1)
    d = raw.loc[keep]
    X = np.c_[np.ones(len(d)), d.x, d.z]
    fits = {
        'ols': fit_linear(X, d.y, offset=d.offset),
        'wls': fit_linear(X, d.y, weights=d.weight, offset=d.offset),
        'binomial': fit_glm(X, d.binomial, offset=d.offset),
        'poisson': fit_glm(X, d.poisson, family='poisson', offset=d.offset),
        'grouped_binomial': fit_glm(X, d.proportion, weights=d.trials, offset=d.offset),
        'weighted_poisson': fit_glm(X, d.poisson, family='poisson',
                                    weights=d.weight, offset=d.offset),
    }
    out = {'data.keep': keep.to_numpy(dtype=int)}
    for model, f in fits.items():
        def add(key, value):
            out[f'{model}.{key}'] = np.asarray(value).ravel(order='F')

        for key in ('coefficients', 'fitted', 'residuals', 'eta', 'working_residuals',
                    'working_weights', 'information', 'inverse_information', 'bread',
                    'scores', 'hat', 'dispersion', 'model_cov', 'df_resid', 'deviance',
                    'n', 'p', 'converged'):
            if key in f:
                add(key, f[key])
        g = d.cluster.nunique()

        def tests(label, V):
            for nm, df in [('normal', np.inf), ('residual', f['df_resid']), ('cluster', g-1)]:
                ct = coefficient_test(f, V, df=df)
                for key, value in ct.items():
                    add(f'{label}.test.{nm}.{key}', value)
                wt = wald_test(f, [[0, 1, 0], [0, 0, 1]], [.1, -.1], V, df=df)
                for key, value in wt.items():
                    if key != 'reference':
                        add(f'{label}.wald.{nm}.{key}', value)

        tests('model', f['model_cov'])
        for kind in ('HC0', 'HC1', 'HC2', 'HC3'):
            v = vcov_hc(f, kind)
            for key in ('cov', 'meat', 'factors', 'adjusted_scores'):
                add(f'{kind}.{key}', v[key])
            tests(kind, v['cov'])
        for kind in ('CR0', 'CR1', 'CR1S', 'CR2', 'CR2_precision', 'CR2_custom'):
            if kind == 'CR2_precision' and model != 'wls':
                continue
            target = (1/d.weight if kind == 'CR2_precision' else
                      .7+.3*np.abs(d.x) if kind == 'CR2_custom' else None)
            v = vcov_cluster(f, d.cluster, 'CR2' if kind.startswith('CR2') else kind,
                             target=target)
            for key in ('cov', 'meat', 'cluster_scores', 'n_clusters', 'df_cluster', 'factor'):
                add(f'{kind}.{key}', v[key])
            if kind.startswith('CR2'):
                add(f'{kind}.adjustments',
                    np.concatenate([a.ravel(order='F') for a in v['adjustments']]))
                add(f'{kind}.target', v['target'])
            tests(kind, v['cov'])
        cr0 = vcov_cluster(f, d.cluster, 'CR0')
        for typ in ('HC0', 'HC1'):
            for cadj in (False, True):
                factor = (f['n']-1)/(f['n']-f['p']) if typ == 'HC1' else 1.
                factor *= g/(g-1) if cadj else 1.
                for key in ('cov', 'meat'):
                    add(f'CL_{typ}_{str(cadj).upper()}.{key}', cr0[key]*factor)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('datadir', type=Path)
    parser.add_argument('refdir', type=Path)
    parser.add_argument('outdir', type=Path)
    args = parser.parse_args()
    rows = []
    for seed in (1, 2):
        raw = pd.read_csv(args.datadir/f'seed{seed}.csv', float_precision='round_trip')
        out = calculate(raw)
        ref = pd.read_csv(args.refdir/f'reference_seed{seed}.csv', float_precision='round_trip')
        assert set(ref.quantity) == set(out), (
            set(ref.quantity)-set(out), set(out)-set(ref.quantity))
        for key, group in ref.groupby('quantity', sort=False):
            expected = group.value.to_numpy()
            actual = np.asarray(out[key], float)
            assert actual.shape == expected.shape, (key, actual.shape, expected.shape)
            finite = np.isfinite(expected)
            assert np.array_equal(actual[~finite], expected[~finite]), key
            assert np.all(np.isfinite(actual[finite])), key
            diff = np.abs(actual[finite]-expected[finite])
            relative = diff/np.maximum(np.abs(expected[finite]), 1e-12)
            nonzero = np.abs(expected[finite]) >= 1e-8
            rows.append(dict(seed=seed, quantity=key, count=len(expected),
                             max_abs=float(diff.max(initial=0)),
                             max_rel=float(relative.max(initial=0)),
                             max_rel_nonzero=float(relative[nonzero].max(initial=0)),
                             near_zero_abs=float(diff[~nonzero].max(initial=0)),
                             passed=bool(np.all(diff <= 1e-12+1e-8*np.abs(expected[finite])))))
    result = pd.DataFrame(rows)
    args.outdir.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.outdir/'comparison.csv', index=False)
    summary = result.groupby('quantity', sort=False).max_rel.max()
    print(f'{len(result)} quantity groups; {result["count"].sum()} scalar comparisons')
    print(result.nlargest(20, 'max_rel').to_string(index=False))
    bad = result[~result.passed]
    print(f'Groups exceeding mixed tolerance atol=1e-12, rtol=1e-8: {len(bad)}')
    print(f'Max relative for |R|>=1e-8: {result.max_rel_nonzero.max():.6g}; '
          f'max absolute for |R|<1e-8: {result.near_zero_abs.max():.6g}')
    summary.to_csv(args.outdir/'max_relative_errors.csv')
    if len(bad):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
