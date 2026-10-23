"""limma-voom and edgeR TMM in plain numpy/scipy (no R, no statsmodels).

Follows the R sources: edgeR calcNormFactors(method="TMM"), limma voom, lmFit (per-gene weighted least squares),
squeezeVar/fitFDist (no covariate, robust=FALSE), eBayes, p.adjust(method="BH"), and R's stats::lowess (clowess, iter=3,
delta=0.01*range) which voom uses for the mean-variance trend. Validated against limma/edgeR in R (see SKILL.md).

Copy the functions you need into your own script; nothing here reads files or keeps state.
Conventions: matrices are genes x samples (rows = genes), design is samples x coefficients.
"""
import numpy as np
from scipy import special, stats


# ---------------------------------------------------------------- normalization

def tmm_factors(counts, lib_size=None, logratio_trim=0.3, sum_trim=0.05, a_cutoff=-1e10):
    """edgeR calcNormFactors(method="TMM") with doWeighting=TRUE. Returns factors with geometric mean 1.

    Effective library size = lib_size * factor. Rows that are zero in every sample are dropped first, as in edgeR.
    """
    x = np.asarray(counts, float)
    lib = x.sum(0) if lib_size is None else np.asarray(lib_size, float)
    x = x[(x > 0).any(1)]
    f75 = np.array([np.quantile(x[:, j] / lib[j], 0.75) for j in range(x.shape[1])])  # R quantile type 7
    ref = int(np.argmax(np.sqrt(x).sum(0))) if np.median(f75) < 1e-20 else int(np.argmin(np.abs(f75 - f75.mean())))
    f = np.array([_tmm_one(x[:, j], x[:, ref], lib[j], lib[ref], logratio_trim, sum_trim, a_cutoff) for j in range(x.shape[1])])
    return f / np.exp(np.mean(np.log(f)))


def _tmm_one(obs, ref, n_o, n_r, logratio_trim, sum_trim, a_cutoff):
    with np.errstate(divide='ignore', invalid='ignore'):
        log_r = np.log2((obs / n_o) / (ref / n_r))
        abs_e = (np.log2(obs / n_o) + np.log2(ref / n_r)) / 2
        v = (n_o - obs) / n_o / obs + (n_r - ref) / n_r / ref
    fin = np.isfinite(log_r) & np.isfinite(abs_e) & (abs_e > a_cutoff)
    log_r, abs_e, v = log_r[fin], abs_e[fin], v[fin]
    if np.max(np.abs(log_r)) < 1e-6:
        return 1.0
    n = len(log_r)
    lo_l = np.floor(n * logratio_trim) + 1
    hi_l = n + 1 - lo_l
    lo_s = np.floor(n * sum_trim) + 1
    hi_s = n + 1 - lo_s
    rl, ra = stats.rankdata(log_r), stats.rankdata(abs_e)  # ties: average, as R rank()
    keep = (rl >= lo_l) & (rl <= hi_l) & (ra >= lo_s) & (ra <= hi_s)
    f = np.nansum(log_r[keep] / v[keep]) / np.nansum(1 / v[keep])
    return 2 ** (0.0 if np.isnan(f) else f)


# ---------------------------------------------------------------- R lowess

def lowess_r(x, y, f=2 / 3, iters=3, delta=None):
    """R stats::lowess (C clowess). Returns (x sorted, fitted y) like R's list(x=, y=)."""
    o = np.argsort(x, kind='stable')
    x, y = np.asarray(x, float)[o], np.asarray(y, float)[o]
    n = len(x)
    if delta is None:
        delta = 0.01 * (x[-1] - x[0])
    if n < 2:
        return x, y.copy()
    ns = max(2, min(n, int(f * n + 1e-7)))
    ys, rw = np.zeros(n), np.ones(n)
    for it in range(1, iters + 2):
        nleft, nright, last, i = 0, ns - 1, -1, 0
        while True:
            if nright < n - 1:
                if x[i] - x[nleft] > x[nright + 1] - x[i]:
                    nleft += 1
                    nright += 1
                    continue
            ys[i] = _lowest(x, y, n, x[i], nleft, nright, rw if it > 1 else None, y[i])
            if last < i - 1:
                a = (x[last + 1:i] - x[last]) / (x[i] - x[last])
                ys[last + 1:i] = a * ys[i] + (1 - a) * ys[last]
            last = i
            cut = x[last] + delta
            i = last + 1
            while i < n:
                if x[i] > cut:
                    break
                if x[i] == x[last]:
                    ys[i] = ys[last]
                    last = i
                i += 1
            i = max(last + 1, i - 1)
            if last >= n - 1:
                break
        res = y - ys
        if it > iters:
            break
        r = np.abs(res)
        m1 = n // 2
        srt = np.sort(r)
        cmad = 3 * (srt[m1] + srt[n - m1 - 1]) if n % 2 == 0 else 6 * srt[m1]
        if cmad < 1e-7 * np.mean(r):
            break
        rw = np.where(r <= 0.001 * cmad, 1.0, np.where(r <= 0.999 * cmad, (1 - (r / cmad) ** 2) ** 2, 0.0))
    return x, ys


def _lowest(x, y, n, xs, nleft, nright, rw, fallback):
    rng = x[n - 1] - x[0]
    h = max(xs - x[nleft], x[nright] - xs)
    h9, h1 = 0.999 * h, 0.001 * h
    # scan from nleft until the first point beyond the window on the right (picks up all ties), as the C loop does
    stop = np.flatnonzero((np.abs(x[nleft:] - xs) > h9) & (x[nleft:] > xs))
    nrt = nleft + (stop[0] if len(stop) else n - nleft) - 1
    xj, yj = x[nleft:nrt + 1], y[nleft:nrt + 1]
    r = np.abs(xj - xs)
    w = np.where(r <= h1, 1.0, np.where(r <= h9, (1 - (r / h) ** 3) ** 3, 0.0)) if h > 0 else (r <= h9).astype(float)
    if rw is not None:
        w = w * rw[nleft:nrt + 1]
    a = w.sum()
    if a <= 0:
        return fallback
    w = w / a
    if h > 0:
        a = np.sum(w * xj)
        c = np.sum(w * (xj - a) ** 2)
        if np.sqrt(c) > 0.001 * rng:
            w = w * ((xs - a) / c * (xj - a) + 1)
    return float(np.sum(w * yj))


def approx_rule2(xp, yp, xq):
    """R approxfun(x, y, rule=2, ties=mean): linear interpolation, constant beyond the ends, ties averaged."""
    ux, inv = np.unique(xp, return_inverse=True)
    uy = np.bincount(inv, weights=yp) / np.bincount(inv)
    return np.interp(xq, ux, uy)


# ---------------------------------------------------------------- linear models

def lm_fit(y, design, weights=None):
    """limma lmFit: per-gene (weighted) least squares. Returns dict like MArrayLM.

    y: genes x samples; design: samples x p (full rank); weights: genes x samples or None.
    """
    y = np.asarray(y, float)
    X = np.asarray(design, float)
    g, n = y.shape
    p = X.shape[1]
    W = np.ones_like(y) if weights is None else np.broadcast_to(np.asarray(weights, float), y.shape)
    xtwx = np.einsum('gs,sp,sq->gpq', W, X, X)
    xtwy = np.einsum('gs,sp,gs->gp', W, X, y)
    inv = np.linalg.inv(xtwx)
    coef = np.einsum('gpq,gq->gp', inv, xtwy)
    resid = y - coef @ X.T
    df = np.full(g, n - p, float)
    sigma2 = np.sum(W * resid ** 2, 1) / df
    return dict(coefficients=coef, stdev_unscaled=np.sqrt(np.einsum('gpp->gp', inv)), cov_unscaled=inv,
                sigma=np.sqrt(sigma2), df_residual=df, Amean=y.mean(1), design=X, fitted=coef @ X.T)


def choose_lowess_span(n, small_n=50, min_span=0.3, power=1 / 3):
    """limma chooseLowessSpan."""
    return min(min_span + (1 - min_span) * (small_n / n) ** power, 1.0)


def voom(counts, design, lib_size=None, span=None):
    """limma voom. lib_size: effective library sizes (e.g. column sums x TMM factors); default column sums.

    span=None follows current limma (3.68: adaptive.span=TRUE, span from the number of genes, all-zero rows included);
    pass span=0.5 for older limma releases or when the specification fixes the span.
    Returns dict(E=logCPM, weights, lib_size, span, trend=(sx, sy, lowess x, lowess y)).
    """
    counts = np.asarray(counts, float)
    if span is None:
        span = choose_lowess_span(counts.shape[0])
    lib = counts.sum(0) if lib_size is None else np.asarray(lib_size, float)
    E = np.log2((counts + 0.5) / (lib + 1) * 1e6)
    fit = lm_fit(E, design)
    sx = fit['Amean'] + np.mean(np.log2(lib + 1)) - np.log2(1e6)
    sy = np.sqrt(fit['sigma'])
    keep = counts.sum(1) != 0
    lx, ly = lowess_r(sx[keep], sy[keep], f=span)
    fitted_count = 1e-6 * (2 ** fit['fitted']) * (lib + 1)
    w = 1 / approx_rule2(lx, ly, np.log2(fitted_count)) ** 4
    return dict(E=E, weights=w, lib_size=lib, span=span, trend=(sx, sy, lx, ly))


# ---------------------------------------------------------------- empirical Bayes

def trigamma_inverse(x):
    """limma trigammaInverse: y with trigamma(y) = x (Newton iteration as in limma)."""
    x = np.asarray(x, float)
    y = 0.5 + 1 / x
    big, small = x > 1e7, x < 1e-6
    for _ in range(50):
        tri = special.polygamma(1, y)
        dif = tri * (1 - tri / x) / special.polygamma(2, y)
        y = y + dif
        if np.max(-dif / y) < 1e-8:
            break
    y = np.where(big, 1 / np.sqrt(x), y)
    return np.where(small, 1 / x, y)


def fit_f_dist(s2, df1):
    """limma fitFDist without covariate: returns (scale s0^2, df2 prior df). df2 may be inf."""
    s2 = np.asarray(s2, float)
    df1 = np.broadcast_to(np.asarray(df1, float), s2.shape)
    ok = np.isfinite(s2) & np.isfinite(df1) & (s2 > -1e-15) & (df1 > 1e-15)
    x, d = np.maximum(s2[ok], 0), df1[ok]
    m = np.median(x)
    x = np.maximum(x, 1e-5 * (m if m > 0 else 1))
    e = np.log(x) - special.digamma(d / 2) + np.log(d / 2)
    emean = e.mean()
    evar = np.sum((e - emean) ** 2) / (len(e) - 1) - np.mean(special.polygamma(1, d / 2))
    if evar > 0:
        df2 = 2 * float(trigamma_inverse(evar))
        return float(np.exp(emean + special.digamma(df2 / 2) - np.log(df2 / 2))), df2
    return float(np.mean(x)), np.inf


def e_bayes(fit):
    """limma eBayes (trend=FALSE, robust=FALSE). Adds s2_prior, df_prior, s2_post, t, df_total, p_value."""
    s2 = fit['sigma'] ** 2
    df = fit['df_residual']
    s0, d0 = fit_f_dist(s2, df)
    s2_post = np.full_like(s2, s0) if np.isinf(d0) else (d0 * s0 + df * s2) / (d0 + df)
    df_total = np.minimum(df + d0, np.sum(df))  # limma caps at the pooled residual df
    t = fit['coefficients'] / fit['stdev_unscaled'] / np.sqrt(s2_post)[:, None]
    p = 2 * stats.t.sf(np.abs(t), df_total[:, None])
    return dict(fit, s2_prior=s0, df_prior=d0, s2_post=s2_post, t=t, df_total=df_total, p_value=p)


def contrast(fit, c):
    """Exact per-gene contrast c'beta with SE from each gene's own (X'WX)^-1.

    Note: limma contrasts.fit uses the unweighted design correlation for weighted fits, so for non-orthogonal
    designs with voom weights its unscaled SE differs slightly from this exact value. Run before e_bayes.
    """
    c = np.asarray(c, float)
    return dict(fit, coefficients=(fit['coefficients'] @ c)[:, None],
                stdev_unscaled=np.sqrt(np.einsum('p,gpq,q->g', c, fit['cov_unscaled'], c))[:, None])


def p_adjust_bh(p):
    """R p.adjust(method="BH") for one vector (NaN kept as NaN, not counted)."""
    p = np.asarray(p, float)
    out = np.full_like(p, np.nan)
    ok = ~np.isnan(p)
    q = p[ok]
    n = len(q)
    o = np.argsort(q)[::-1]
    adj = np.minimum.accumulate(q[o] * n / np.arange(n, 0, -1))
    res = np.empty(n)
    res[o] = np.minimum(adj, 1)
    out[ok] = res
    return out
