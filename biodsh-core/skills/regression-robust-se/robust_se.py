"""OLS/WLS, canonical logistic/Poisson IRLS, HC0-3 and CR0/1/1S/2.

Only numpy/scipy/pandas; no I/O or global state. Explicit finite complete-case
inputs, positive weights, full-rank design (include an intercept yourself).
R references and tested conventions are in SKILL.md and VALIDATION.md.
"""
import numpy as np
import pandas as pd
from scipy import special, stats


def _vector(x, n, name, default=None):
    a = np.full(n, default, dtype=float) if x is None else np.asarray(x, float)
    if a.shape != (n,) or not np.all(np.isfinite(a)):
        raise ValueError(f'{name} must be a finite vector of length {n}')
    return a.copy()


def _inputs(X, y, weights, offset):
    X = np.array(X, dtype=float, copy=True)
    if X.ndim != 2 or not np.all(np.isfinite(X)):
        raise ValueError('X must be a finite n x p matrix; handle missing rows explicitly')
    n, p = X.shape
    if p == 0 or n <= p or np.linalg.matrix_rank(X) != p:
        raise ValueError('Require n > p and full column rank')
    y = _vector(y, n, 'y')
    w = _vector(weights, n, 'weights', 1.)
    off = _vector(offset, n, 'offset', 0.)
    if np.any(w <= 0):
        raise ValueError('weights must be positive; explicitly exclude zero-weight rows')
    return X, y, w, off


def _inverse_info(X, w):
    # QR avoids forming/inverting X'WX for fitting and model covariance.
    q, r = np.linalg.qr(X * np.sqrt(w)[:, None], mode='reduced')
    if np.linalg.cond(r) > 1e12:
        raise ValueError('Weighted design is ill-conditioned; rescale or remove columns')
    ri = np.linalg.solve(r, np.eye(r.shape[0]))
    return ri @ ri.T, q, r


def fit_linear(X, y, weights=None, offset=None):
    """R stats::lm (OLS/WLS): positive precision weights, sigma²=Σw e²/(n-p).

    Does not add an intercept or silently omit NA. bread=n*(X'WX)^-1 follows
    sandwich::bread.lm; scores_i=x_i*w_i*e_i follows sandwich::estfun.lm.
    """
    X, y, w, off = _inputs(X, y, weights, offset)
    n, p = X.shape
    inv, q, r = _inverse_info(X, w)
    beta = np.linalg.solve(r, q.T @ (np.sqrt(w) * (y - off)))
    mu = X @ beta + off
    e = y - mu
    sigma2 = np.dot(w, e * e) / (n - p)
    return dict(family='gaussian', X=X, y=y, weights=w, offset=off, n=n, p=p,
                coefficients=beta, fitted=mu, eta=mu, residuals=e,
                working_residuals=e.copy(), working_weights=w.copy(),
                information=X.T @ (w[:, None] * X), inverse_information=inv,
                bread=n * inv, scores=X * (w * e)[:, None],
                hat=np.sum(q*q, axis=1), dispersion=sigma2,
                model_cov=sigma2 * inv, df_resid=n-p, converged=True, iterations=1)


def _glm_state(eta, y, w, family):
    if family == 'binomial':
        mu = special.expit(eta)
        v = mu * (1 - mu)
        objective = np.sum(w * (np.logaddexp(0., eta) - y * eta))
    else:
        with np.errstate(over='ignore', invalid='ignore'):
            mu = np.exp(eta)
            v = mu.copy()
            objective = np.sum(w * (mu - y * eta))
    return mu, v, objective


def fit_glm(X, y, family='binomial', weights=None, offset=None,
            tol=1e-12, max_iter=100):
    """R stats::glm canonical binomial(logit)/poisson(log), dispersion fixed 1.

    IRLS/Newton with step halving. Binomial y is 0/1 or a proportion, with
    weights=trials for grouped binomial; n/df count rows, not sum(weights).
    Poisson y must be nonnegative integers. Offsets are on the link scale.
    Recomputes final information/working weights at the returned coefficients.
    Raises on nonconvergence, numerical boundary/separation, or singular design.
    Complete/quasi separation is not formally diagnosed by a linear program.
    """
    if family not in ('binomial', 'poisson'):
        raise ValueError('family must be binomial or poisson')
    if not np.isfinite(tol) or tol <= 0 or not isinstance(max_iter, int) or max_iter < 1:
        raise ValueError('tol > 0 and integer max_iter >= 1 required')
    X, y, w, off = _inputs(X, y, weights, offset)
    n, p = X.shape
    if family == 'binomial' and np.any((y < 0) | (y > 1)):
        raise ValueError('binomial y must lie in [0, 1]')
    if family == 'poisson' and np.any((y < 0) | (y != np.floor(y))):
        raise ValueError('poisson y must contain nonnegative integers')
    # R-style initial means, projected onto the supplied design including offset.
    initial_mu = (w*y + .5)/(w + 1.) if family == 'binomial' else y + .1
    initial_eta = special.logit(initial_mu) if family == 'binomial' else np.log(initial_mu)
    beta = np.linalg.lstsq(X, initial_eta - off, rcond=None)[0]
    converged = False
    for iteration in range(1, max_iter + 1):
        eta = X @ beta + off
        mu, v, loss = _glm_state(eta, y, w, family)
        if not np.isfinite(loss) or np.any(v <= 1e-14):
            raise ValueError('GLM reached a numerical boundary; check separation/extreme offsets')
        inv, _, _ = _inverse_info(X, w*v)
        step = inv @ (X.T @ (w * (y-mu)))
        alpha = 1.
        for _ in range(50):
            candidate = beta + alpha*step
            _, _, new_loss = _glm_state(X @ candidate + off, y, w, family)
            if np.isfinite(new_loss) and new_loss <= loss + 1e-13*(1+abs(loss)):
                break
            alpha *= .5
        else:
            raise ValueError('IRLS step halving failed')
        beta = candidate
        if np.max(np.abs(alpha*step)) <= tol*(1+np.max(np.abs(beta))):
            converged = True
            break
    if not converged:
        raise ValueError('IRLS did not converge; check separation or increase max_iter')
    eta = X @ beta + off
    mu, v, _ = _glm_state(eta, y, w, family)
    if np.any(v <= 1e-14):
        raise ValueError('GLM converged at a numerical boundary')
    ww = w*v
    inv, q, _ = _inverse_info(X, ww)
    e = y-mu
    if family == 'binomial':
        dev = 2*np.sum(w*(special.xlogy(y, y/mu) + special.xlogy(1-y, (1-y)/(1-mu))))
    else:
        dev = 2*np.sum(w*(special.xlogy(y, y/mu) - (y-mu)))
    return dict(family=family, X=X, y=y, weights=w, offset=off, n=n, p=p,
                coefficients=beta, fitted=mu, eta=eta, residuals=e,
                working_residuals=e/v, working_weights=ww,
                information=X.T @ (ww[:, None]*X), inverse_information=inv,
                bread=n*inv, scores=X*(w*e)[:, None], hat=np.sum(q*q, axis=1),
                dispersion=1., model_cov=inv.copy(), df_resid=n-p,
                converged=True, iterations=iteration, deviance=dev)


def _sandwich(fit, meat, **extra):
    """Normalized R sandwich convention: V = bread @ meat @ bread / n."""
    b = fit['bread']
    cov = b @ meat @ b / fit['n']
    return dict(cov=(cov+cov.T)/2, bread=b.copy(), meat=meat, **extra)


def vcov_hc(fit, kind='HC3'):
    """sandwich::vcovHC/meatHC types HC0, HC1, HC2, HC3 for lm/glm.

    HC1 uses n/(n-p). HC2/3 use weighted/IRLS hat diagonals, not unweighted X.
    Returns covariance, normalized bread/meat, adjusted row scores and factors.
    """
    n, p = fit['n'], fit['p']
    factors = np.ones(n)
    if kind == 'HC1':
        factors *= n/(n-p)
    elif kind in ('HC2', 'HC3'):
        gap = 1-fit['hat']
        if np.any(gap <= 1e-12):
            raise ValueError('HC2/HC3 undefined or unstable for leverage near one')
        factors = gap**(-1 if kind == 'HC2' else -2)
    elif kind != 'HC0':
        raise ValueError('kind must be HC0, HC1, HC2, or HC3')
    scores = fit['scores'] * np.sqrt(factors)[:, None]
    return _sandwich(fit, scores.T @ scores/n, kind=kind,
                     adjusted_scores=scores, factors=factors)


def _clusters(cluster, n):
    a = np.asarray(cluster)
    if a.shape != (n,) or np.any(pd.isna(a)):
        raise ValueError('cluster must have one nonmissing label per retained row')
    codes, labels = pd.factorize(a, sort=True)
    if len(labels) < 2:
        raise ValueError('At least two observed clusters are required')
    return codes, np.asarray(labels)


def vcov_cluster(fit, cluster, kind='CR1S', target=None):
    """clubSandwich::vcovCR CR0/CR1/CR1S/CR2, one-way clusters.

    CR1 = G/(G-1); CR1S = G/(G-1)*(n-1)/(n-p) (Stata style).
    CR0/CR1 map to sandwich::vcovCL(type='HC0',cadjust=FALSE/TRUE).
    CR1S maps to vcovCL(type='HC1',cadjust=TRUE).
    CR2 is Bell-McCaffrey with diagonal working target: default identity for
    lm (including WLS), variance(mu)/prior_weights for glm. Specify 1/weights
    for precision-weighted WLS target. No automatic Satterthwaite df.
    CR2 returns cluster adjustment matrices and target; singular residual
    blocks are rejected rather than silently generalized-inverted.
    """
    if kind not in ('CR0', 'CR1', 'CR1S', 'CR2'):
        raise ValueError('kind must be CR0, CR1, CR1S, or CR2')
    if target is not None and kind != 'CR2':
        raise ValueError('target applies only to CR2')
    n, p = fit['n'], fit['p']
    codes, labels = _clusters(cluster, n)
    g = len(labels)
    factor = 1. if kind in ('CR0', 'CR2') else g/(g-1)
    if kind == 'CR1S':
        factor *= (n-1)/(n-p)
    scores = np.zeros((g, p))
    adjustments = []
    theta = None
    if kind != 'CR2':
        np.add.at(scores, codes, fit['scores'])
        scores *= np.sqrt(factor)
    else:
        X, w, e = fit['X'], fit['weights'], fit['residuals']
        if fit['family'] == 'gaussian':
            U, W = X, w
            default_target = np.ones(n)
        else:
            var = fit['working_weights']/w
            U, W = var[:, None]*X, w/var
            default_target = var/w
        theta = default_target if target is None else _vector(target, n, 'target')
        if np.any(theta <= 0):
            raise ValueError('CR2 diagonal target must be positive')
        M = fit['inverse_information']
        K = M @ (U.T @ ((W*W*theta)[:, None]*U)) @ M
        for j in range(g):
            idx = np.flatnonzero(codes == j)
            u, ww, th = U[idx], W[idx], theta[idx]
            H = (u @ M @ u.T)*ww[None, :]
            C = np.diag(th) - H*th[None, :] - th[:, None]*H.T + u @ K @ u.T
            root = np.sqrt(th)
            D = root[:, None]*C*root[None, :]
            vals, vecs = np.linalg.eigh((D+D.T)/2)
            if vals[0] <= 1e-12*max(abs(vals[-1]), np.finfo(float).tiny):
                raise ValueError('CR2 residual block singular/ill-conditioned; no generalized inverse supported')
            A = root[:, None]*((vecs*(vals**-.5)) @ vecs.T)*root[None, :]
            adjustments.append(A)
            scores[j] = u.T @ (ww*(A @ e[idx]))
    return _sandwich(fit, scores.T @ scores/n, kind=kind, factor=factor,
                     cluster_scores=scores, clusters=labels, n_clusters=g,
                     df_cluster=g-1, adjustments=adjustments, target=theta)


def coefficient_test(fit, covariance=None, df=np.inf, level=.95):
    """lmtest::coeftest with EXPLICIT df (Inf -> normal; finite -> Student t).

    Typical choices: lm n-p, glm Inf, cluster G-1. The latter is a convention,
    not clubSandwich's coefficient-specific Satterthwaite small-sample test.
    Returns beta, SE, t/z, two-sided p, CI, and df. No implicit df guessing.
    """
    if not (df > 0) or not 0 < level < 1:
        raise ValueError('df must be positive (or Inf); 0 < level < 1')
    V = _covariance(fit, covariance)
    if np.any(np.diag(V) <= 0):
        raise ValueError('Tests require strictly positive standard errors')
    se = np.sqrt(np.diag(V))
    beta = fit['coefficients']
    statistic = beta/se
    dist = stats.norm if np.isinf(df) else stats.t(df)
    critical = dist.ppf((1+level)/2)
    return dict(coefficients=beta.copy(), se=se, statistic=statistic,
                p_value=2*dist.sf(np.abs(statistic)), df=float(df),
                conf_low=beta-critical*se, conf_high=beta+critical*se)


def _covariance(fit, covariance):
    V = np.asarray(fit['model_cov'] if covariance is None else covariance, float)
    if V.shape != (fit['p'], fit['p']) or not np.all(np.isfinite(V)) or not np.allclose(V, V.T):
        raise ValueError('covariance must be finite, symmetric and p x p')
    return (V+V.T)/2


def wald_test(fit, contrast, null=0., covariance=None, df=np.inf):
    """Wald R beta = null; chi-square(q) for Inf or F(q,df)=W/q for finite df.

    Equivalent to an explicit R quadratic-form Wald test, and for q=1 to
    lmtest::coeftest squared (with the same covariance and df). Rejects rank
    deficient contrasts/covariance instead of inventing degrees of freedom.
    contrast_estimate is the null-centered difference R @ beta - null.
    """
    R = np.atleast_2d(np.asarray(contrast, float))
    if R.shape[1] != fit['p'] or not np.all(np.isfinite(R)) or np.linalg.matrix_rank(R) != len(R):
        raise ValueError('contrast must be finite, full row rank, with p columns')
    if not df > 0:
        raise ValueError('df must be positive or Inf')
    null = np.broadcast_to(np.asarray(null, float), (len(R),))
    if not np.all(np.isfinite(null)):
        raise ValueError('null must be finite')
    difference = R @ fit['coefficients'] - null
    V = R @ _covariance(fit, covariance) @ R.T
    try:
        L = np.linalg.cholesky(V)
    except np.linalg.LinAlgError as exc:
        raise ValueError('Contrast covariance must be positive definite') from exc
    z = np.linalg.solve(L, difference)
    W = float(z @ z)
    q = len(R)
    statistic = W if np.isinf(df) else W/q
    pval = stats.chi2.sf(W, q) if np.isinf(df) else stats.f.sf(statistic, q, df)
    return dict(wald=W, statistic=statistic, df_num=q, df_denom=float(df),
                p_value=float(pval), contrast_estimate=difference,
                contrast_cov=V, reference='chi2' if np.isinf(df) else 'F')
