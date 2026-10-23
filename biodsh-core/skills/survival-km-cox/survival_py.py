"""Right-censored survival analysis in numpy/scipy/pandas; no IO or global state.

R references: survival::{survfit,survdiff,coxph,basehaz}, survRM2::rmst2.
Unweighted observations, fixed covariates, exact time equality; missing data raise.
Time is nonnegative; status is 0=censored, 1=event. See SKILL.md and VALIDATION.md.
"""
import numpy as np
import pandas as pd
from scipy import stats


def _outcome(time, status):
    t, d = np.asarray(time, float), np.asarray(status, float)
    if t.ndim != 1 or d.shape != t.shape or not len(t):
        raise ValueError('time and status must be nonempty vectors of equal length')
    if not np.all(np.isfinite(t)) or np.any(t < 0):
        raise ValueError('time must be finite and nonnegative; remove missing rows explicitly')
    if not np.all(np.isin(d, [0, 1])):
        raise ValueError('status must be 0=censored or 1=event, with no missing values')
    return t, d.astype(int)


def _labels(values, n, name):
    a = np.zeros(n, int) if values is None else np.asarray(values)
    if a.shape != (n,) or np.any(pd.isna(a)):
        raise ValueError(f'{name} must be a length-n vector without missing values')
    codes, labels = pd.factorize(a, sort=True)
    return codes, np.asarray(labels)


def _alpha(alpha):
    if not np.isscalar(alpha) or not 0 < alpha < 1:
        raise ValueError('alpha must lie strictly between 0 and 1')
    return stats.norm.isf(alpha / 2)


def administrative_censor(time, status, tau):
    """Truncate at tau: Surv(pmin(time,tau), status*(time<=tau)); retain events AT tau."""
    t, d = _outcome(time, status)
    if not np.isfinite(tau) or tau < 0:
        raise ValueError('tau must be finite and nonnegative')
    return np.minimum(t, tau), d * (t <= tau)


def kaplan_meier(time, status, alpha=0.05, conf_type='log-log'):
    """survival::survfit(Surv(time,status)~1, conf.type=..., timefix=FALSE).

    One curve, at ALL unique observation times, right-continuous. Greenwood is
    Var(log S), variance is S^2*Greenwood, se is on the survival scale. std_err_log
    corresponds to the raw R survfit object's std.err (not summary(fit)$std.err).
    At terminal S=0: Greenwood/log-SE=Inf, variance/se and CIs are NaN, as R.
    Censors tied with events remain in the risk set. No implicit NA omission.
    """
    t, d = _outcome(time, status)
    z = _alpha(alpha)
    if conf_type not in ('log', 'log-log'):
        raise ValueError('conf_type must be log or log-log')
    u, inv, counts = np.unique(t, return_inverse=True, return_counts=True)
    risk = len(t) - np.r_[0, np.cumsum(counts)[:-1]]
    events = np.bincount(inv, weights=d).astype(int)
    surv = np.cumprod(1 - events / risk)
    inc = np.divide(events, risk * (risk - events), out=np.full(len(u), np.inf),
                    where=risk > events)
    greenwood = np.cumsum(inc)
    with np.errstate(invalid='ignore'):
        variance = surv ** 2 * greenwood
    log_se = np.sqrt(greenwood)
    lower, upper = np.full(len(u), np.nan), np.full(len(u), np.nan)
    pos = surv > 0
    if conf_type == 'log':
        lower[pos] = np.exp(np.log(surv[pos]) - z * log_se[pos])
        upper[pos] = np.exp(np.minimum(0, np.log(surv[pos]) + z * log_se[pos]))
    else:
        interior = (surv > 0) & (surv < 1)
        a = np.log(-np.log(surv[interior]))
        b = z * log_se[interior] / np.abs(np.log(surv[interior]))
        lower[interior] = np.exp(-np.exp(a + b))
        upper[interior] = np.exp(-np.exp(a - b))
        lower[surv == 1] = upper[surv == 1] = 1
    return dict(time=u, n_risk=risk, n_event=events, n_censor=counts-events,
                survival=surv, greenwood=greenwood, variance=variance,
                se=np.sqrt(variance), std_err_log=log_se, lower=lower, upper=upper)


def logrank(time, status, group, strata=None):
    """survival::survdiff(..., rho=0, timefix=FALSE), optionally +strata(...).

    Returns observed/expected counts per group and stratum, their sums, full
    hypergeometric covariance, O-E, chi-square, df and p. Sorted group/strata labels.
    Only groups with positive expected events enter the test (R convention).
    No events gives statistic=0, df=0, p=NaN; nonestimable contrasts raise.
    """
    t, d = _outcome(time, status)
    g, levels = _labels(group, len(t), 'group')
    s, sl = _labels(strata, len(t), 'strata')
    k, ns = len(levels), len(sl)
    if k < 2:
        raise ValueError('log-rank needs at least two observed groups')
    obs, exp = np.zeros((k, ns)), np.zeros((k, ns))
    vs = np.zeros((ns, k, k))
    for j in range(ns):
        ids = np.flatnonzero(s == j)
        ids = ids[np.argsort(t[ids], kind='stable')]
        _, starts = np.unique(t[ids], return_index=True)
        indicators = np.eye(k)[g[ids]]
        risk = np.cumsum(indicators[::-1], axis=0)[::-1][starts]
        deaths = np.add.reduceat(indicators * d[ids, None], starts, axis=0)
        nr, nd = risk.sum(1), deaths.sum(1)
        probs = risk / nr[:, None]
        obs[:, j], exp[:, j] = deaths.sum(0), (nd[:, None] * probs).sum(0)
        fac = np.divide(nd * (nr - nd), nr - 1, out=np.zeros_like(nd), where=nr > 1)
        vs[j] = np.diag((fac[:, None] * probs).sum(0)) - np.einsum('i,ij,ik->jk', fac, probs, probs)
    observed, expected, cov = obs.sum(1), exp.sum(1), vs.sum(0)
    score = observed - expected
    active = np.flatnonzero(expected > 0)
    df = max(0, len(active) - 1)
    if df:
        use = active[1:]
        sub = cov[np.ix_(use, use)]
        if np.linalg.matrix_rank(sub) < df:
            raise ValueError('log-rank contrasts are not identifiable across strata')
        chisq = float(score[use] @ np.linalg.solve(sub, score[use]))
    else:
        chisq = 0.0
    return dict(groups=levels, strata=sl, observed=observed, expected=expected,
                observed_by_stratum=obs, expected_by_stratum=exp,
                covariance_by_stratum=vs, covariance=cov, score=score,
                statistic=chisq, df=df, p_value=float(stats.chi2.sf(chisq, df)) if df else np.nan)


def rmst(time, status, tau, alpha=0.05):
    """survRM2:::rmst1: KM area [0,tau], Greenwood integral variance and normal CI.

    tau must not exceed largest follow-up in this arm (conservative support rule).
    CI is not clipped to [0,tau], matching R. At n=d, variance contribution is 0.
    Returns interval widths/areas, tail areas and event variance contributions.
    """
    t, d = _outcome(time, status)
    z = _alpha(alpha)
    if not np.isfinite(tau) or tau < 0 or tau > t.max():
        raise ValueError('tau must be in [0, max observed time] for every arm')
    km = kaplan_meier(t, d)
    keep = km['time'] <= tau
    tt, ss = km['time'][keep], km['survival'][keep]
    widths = np.diff(np.r_[0, tt, tau])
    areas = widths * np.r_[1, ss]
    tail = np.cumsum(areas[:0:-1])[::-1]
    nr, nd = km['n_risk'][keep], km['n_event'][keep]
    inc = np.divide(nd, nr * (nr-nd), out=np.zeros(len(nr)), where=nr > nd)
    contributions = tail ** 2 * inc
    est, var = float(areas.sum()), float(contributions.sum())
    se = np.sqrt(var)
    return dict(tau=float(tau), estimate=est, variance=var, se=se,
                lower=est-z*se, upper=est+z*se, rmtl=tau-est,
                time=tt, widths=widths, areas=areas, tail_areas=tail,
                greenwood_increment=inc, variance_contributions=contributions)


def rmst_difference(time, status, group, tau, alpha=0.05):
    """survRM2::rmst2 unadjusted RMST(arm=1)-RMST(arm=0); independent arms.

    Groups must be exactly 0/1. Returns arm details, difference, summed variance,
    normal z, two-sided p, normal CI. Ratios/covariate adjustment not implemented.
    """
    t, d = _outcome(time, status)
    g = np.asarray(group)
    if g.shape != t.shape or not np.array_equal(np.unique(g), [0, 1]):
        raise ValueError('RMST difference requires both groups coded 0 and 1')
    zcrit = _alpha(alpha)
    arms = [rmst(t[g == k], d[g == k], tau, alpha) for k in (0, 1)]
    diff = arms[1]['estimate'] - arms[0]['estimate']
    var = arms[0]['variance'] + arms[1]['variance']
    se = np.sqrt(var)
    z = diff / se if se else (np.nan if diff == 0 else np.copysign(np.inf, diff))
    return dict(arms=arms, estimate=diff, variance=var, se=se, z=z,
                lower=diff-zcrit*se, upper=diff+zcrit*se,
                p_value=float(2*stats.norm.sf(abs(z))))


def _cox_inputs(time, status, x, strata):
    t, d = _outcome(time, status)
    x = np.asarray(x, float)
    if x.ndim != 2 or x.shape[0] != len(t) or x.shape[1] < 1 or not np.all(np.isfinite(x)):
        raise ValueError('x must be a finite n by p matrix, p>=1, without an intercept')
    s, levels = _labels(strata, len(t), 'strata')
    return t, d, x, s, levels


def _prepare(t, d, x, s):
    cache = []
    for sid in np.unique(s):
        ids = np.flatnonzero(s == sid)
        ids = ids[np.argsort(t[ids], kind='stable')]
        u, starts, counts = np.unique(t[ids], return_index=True, return_counts=True)
        nd = np.add.reduceat(d[ids], starts)
        has = np.flatnonzero(nd)
        ndev = nd[has]
        rep = np.repeat(np.arange(len(has)), ndev)
        offsets = (np.arange(ndev.sum()) - np.repeat(np.r_[0, np.cumsum(ndev)[:-1]], ndev)
                   if len(ndev) else np.empty(0))
        cache.append(dict(sid=int(sid), ids=ids, x=x[ids], d=d[ids], time=u, starts=starts,
                          counts=counts, nd=nd, has=has, rep=rep,
                          fractions=offsets/ndev[rep] if len(rep) else np.empty(0)))
    return cache


def _evaluate(beta, cache, n, details=False):
    p = len(beta)
    ll, score, info = 0.0, np.zeros(p), np.zeros((p, p))
    residuals = np.zeros((n, p)) if details else None
    tables = []
    for c in cache:
        x, d, starts, has, rep = c['x'], c['d'], c['starts'], c['has'], c['rep']
        if not len(has):
            if details:
                tables.append(dict(stratum=c['sid'], time=c['time'], n_risk=len(x)-starts,
                    n_event=c['nd'], hazard=np.zeros(len(starts)),
                    hazard_breslow=np.zeros(len(starts)),
                    event_time=np.empty(0), risk_sum=np.empty(0),
                    death_risk_sum=np.empty(0), mean=np.empty((0, p)),
                    score=np.empty((0, p)), information=np.empty((0, p, p)),
                    loglik=np.empty(0)))
            continue
        eta = x @ beta
        shift = float(eta.max())
        risk = np.exp(eta-shift)
        rx = risk[:, None]*x
        rxx = rx[:, :, None]*x[:, None, :]
        r0 = np.cumsum(risk[::-1])[::-1][starts][has]
        r1 = np.cumsum(rx[::-1], axis=0)[::-1][starts][has]
        r2 = np.cumsum(rxx[::-1], axis=0)[::-1][starts][has]
        e0 = np.add.reduceat(risk*d, starts)[has]
        e1 = np.add.reduceat(rx*d[:, None], starts, axis=0)[has]
        e2 = np.add.reduceat(rxx*d[:, None, None], starts, axis=0)[has]
        dx = np.add.reduceat(x*d[:, None], starts, axis=0)[has]
        f = c['fractions']
        denom = r0[rep] - f*e0[rep]
        means = (r1[rep] - f[:, None]*e1[rep])/denom[:, None]
        vv = ((r2[rep] - f[:, None, None]*e2[rep])/denom[:, None, None]
              - means[:, :, None]*means[:, None, :])
        nd = c['nd'][has]
        offsets = np.r_[0, np.cumsum(nd)[:-1]]
        summeans = np.add.reduceat(means, offsets, axis=0)
        us = dx - summeans
        ims = np.add.reduceat(vv, offsets, axis=0)
        lls = dx @ beta - np.add.reduceat(np.log(denom)+shift, offsets)
        ll += lls.sum()
        score += us.sum(0)
        info += ims.sum(0)
        if details:
            h = np.add.reduceat(1/denom, offsets)
            xh = np.add.reduceat(means/denom[:, None], offsets, axis=0)
            hf = np.add.reduceat(f/denom, offsets)
            xhf = np.add.reduceat(means*(f/denom)[:, None], offsets, axis=0)
            h_all = np.zeros(len(starts)); h_all[has] = h
            xh_all = np.zeros((len(starts), p)); xh_all[has] = xh
            cumh = np.repeat(np.cumsum(h_all), c['counts'])
            cumxh = np.repeat(np.cumsum(xh_all, axis=0), c['counts'], axis=0)
            res = -risk[:, None]*(x*cumh[:, None]-cumxh)
            avg = np.zeros((len(starts), p)); avg[has] = summeans/nd[:, None]
            fh = np.zeros(len(starts)); fh[has] = hf
            fxh = np.zeros((len(starts), p)); fxh[has] = xhf
            res += d[:, None]*(x - np.repeat(avg, c['counts'], axis=0)
                    + risk[:, None]*(x*np.repeat(fh, c['counts'])[:, None]
                                     - np.repeat(fxh, c['counts'], axis=0)))
            residuals[c['ids']] = res
            hb = np.zeros(len(starts)); hb[has] = nd/r0*np.exp(-shift)
            tables.append(dict(stratum=c['sid'], time=c['time'], n_risk=len(x)-starts,
                n_event=c['nd'], hazard=h_all*np.exp(-shift), hazard_breslow=hb,
                event_time=c['time'][has], risk_sum=r0*np.exp(shift),
                death_risk_sum=e0*np.exp(shift), mean=summeans/nd[:, None],
                score=us, information=ims, loglik=lls))
    return dict(loglik=float(ll), score=score, information=(info+info.T)/2,
                score_residuals=residuals, tables=tables)


def cox_components(time, status, x, beta, strata=None, ties='efron'):
    """Partial likelihood, score, observed information at fixed beta (coxph.detail).

    Includes individual score residuals (residuals(coxph,type='score')), per-time
    event summaries and both Breslow/Efron hazard increments. x is NOT centered
    here: risk sums and hazard refer to x=0. Sum residuals equals total score.
    """
    t, d, x, s, levels = _cox_inputs(time, status, x, strata)
    b = np.asarray(beta, float)
    if b.shape != (x.shape[1],) or not np.all(np.isfinite(b)):
        raise ValueError('beta must be finite with one value per x column')
    if ties not in ('breslow', 'efron'):
        raise ValueError('ties must be breslow or efron')
    cache = _prepare(t, d, x, s)
    if ties == 'breslow':
        for c in cache:
            c['fractions'] = np.zeros_like(c['fractions'])
    out = _evaluate(b, cache, len(t), details=True)
    out['strata'] = levels
    return out


def _quadratic(v, cov):
    return float(v @ np.linalg.solve(cov, v))


def _test(stat, df):
    return dict(statistic=float(stat), df=int(df), p_value=float(stats.chi2.sf(stat, df)))


def coxph(time, status, x, strata=None, cluster=None, ties='efron',
          alpha=0.05, tol=1e-10, max_iter=50):
    """survival::coxph(Surv(time,status)~x+strata(s), ties=..., cluster=id).

    Fixed covariates, unweighted, no intercept, no missing values. Newton with
    step halving; internal centering/scaling. Nonconvergence or singularity raises.
    model_covariance=I^-1; cluster covariance=I^-1 sum_g(Ug Ug') I^-1 (no finite
    sample factor). Cluster labels span strata. Wald and coefficient z use selected
    covariance; score/LR remain model-based, as summary.coxph. robust_score uses
    null score residuals clustered, matching summary.coxph$robscore.
    Baseline hazards are at reference=x.mean(0), NOT R's special binary centering.
    """
    t, d, x, s, levels = _cox_inputs(time, status, x, strata)
    zcrit = _alpha(alpha)
    if ties not in ('breslow', 'efron'):
        raise ValueError('ties must be breslow or efron')
    if not np.any(d):
        raise ValueError('Cox model needs events')
    if not np.isfinite(tol) or tol <= 0 or not isinstance(max_iter, (int, np.integer)) or max_iter < 1:
        raise ValueError('tol must be positive and max_iter a positive integer')
    center, scale = x.mean(0), x.std(0)
    if np.any(scale == 0) or np.linalg.matrix_rank(x-center) < x.shape[1]:
        raise ValueError('constant/intercept or collinear columns are not identifiable')
    xc = (x-center)/scale
    cache = _prepare(t, d, xc, s)
    if ties == 'breslow':
        for c in cache:
            c['fractions'] = np.zeros_like(c['fractions'])
    b = np.zeros(x.shape[1])
    null = _evaluate(b, cache, len(t), details=True)
    fit = null
    converged = False
    for it in range(max_iter):
        try:
            np.linalg.cholesky(fit['information'])
            step = np.linalg.solve(fit['information'], fit['score'])
        except np.linalg.LinAlgError as e:
            raise ValueError('singular Cox information: check within-stratum identifiability/separation') from e
        if np.max(np.abs(fit['score'])) <= tol and np.max(np.abs(step)) <= np.sqrt(tol):
            converged = True
            break
        factor = 1.0
        for _ in range(40):
            trial = _evaluate(b+factor*step, cache, len(t))
            if np.isfinite(trial['loglik']) and trial['loglik'] >= fit['loglik'] - 1e-12:
                break
            factor *= 0.5
        else:
            raise RuntimeError('Cox line search failed')
        b += factor*step
        fit = trial
    if not converged:
        raise RuntimeError('Cox did not converge; possible separation or insufficient max_iter')
    beta = b/scale
    # Return all components on the original covariate scale, centered consistently.
    comp = cox_components(t, d, x-center, beta, s, ties)
    info = comp['information']
    model_cov = np.linalg.inv(info)
    cov = model_cov.copy()
    cl, cluster_labels = _labels(cluster, len(t), 'cluster') if cluster is not None else (None, None)
    meat, cluster_scores, robust_score = None, None, None
    if cl is not None:
        cluster_scores = np.zeros((len(cluster_labels), x.shape[1]))
        np.add.at(cluster_scores, cl, comp['score_residuals'])
        meat = cluster_scores.T @ cluster_scores
        cov = model_cov @ meat @ model_cov
        null_scores = np.zeros_like(cluster_scores)
        np.add.at(null_scores, cl, null['score_residuals'] * scale)
        robust_score = _test(_quadratic(null_scores.sum(0), null_scores.T @ null_scores), x.shape[1])
    se = np.sqrt(np.diag(cov))
    z = beta/se
    wald = _test(_quadratic(beta, cov), len(beta))
    score_test = _test(_quadratic(null['score'], null['information']), len(beta))
    lr = _test(max(0, 2*(comp['loglik']-null['loglik'])), len(beta))
    return dict(coefficients=beta, hazard_ratio=np.exp(beta), covariance=cov,
                model_covariance=model_cov, information=info, score=comp['score'],
                score_residuals=comp['score_residuals'], cluster_scores=cluster_scores,
                cluster_labels=cluster_labels, meat=meat, se=se, z=z,
                p_value=2*stats.norm.sf(np.abs(z)),
                coef_lower=beta-zcrit*se, coef_upper=beta+zcrit*se,
                loglik=comp['loglik'], loglik_null=null['loglik'],
                null_score=null['score']*scale,
                null_information=null['information']*np.outer(scale, scale),
                wald=wald, score_test=score_test, likelihood_ratio=lr, robust_score=robust_score,
                reference=center, strata=levels, tables=comp['tables'], ties=ties,
                iterations=it, converged=True, n=len(t), n_event=int(d.sum()))


def baseline_hazard(fit, method='breslow', reference=None):
    """Cox baseline cumulative hazard, one table per stratum, all observed times.

    Default is Breslow sum d/sum(exp(x beta)), including after an Efron fit.
    method='efron' uses fitted Efron denominators (requires an Efron fit).
    R basehaz inherits fit ties: compare method=fit['ties']; centered=FALSE matches
    reference=zeros(p). Default reference=fit['reference'] for numerical stability.
    No uncertainty bands. Reference changes rescale hazard, not individual curves.
    """
    if method not in ('breslow', 'efron') or (method == 'efron' and fit['ties'] != 'efron'):
        raise ValueError('method must be breslow, or efron for an Efron fit')
    ref = fit['reference'] if reference is None else np.asarray(reference, float)
    if ref.shape != fit['reference'].shape or not np.all(np.isfinite(ref)):
        raise ValueError('reference must be a finite p-vector')
    factor = np.exp((ref-fit['reference']) @ fit['coefficients'])
    result = []
    for table in fit['tables']:
        h = table['hazard_breslow' if method == 'breslow' else 'hazard'] * factor
        result.append(dict(stratum=fit['strata'][table['stratum']], time=table['time'].copy(),
                           increment=h, cumulative_hazard=np.cumsum(h), reference=ref.copy()))
    return result


def predict_survival(fit, newx, times, strata=None, method='breslow'):
    """exp(-H_ref(t)*exp((newx-ref)beta)); right-continuous step lookup, nnew x ntimes.

    For R survfit(fit,newdata=...,ctype=1) use Breslow even for an Efron fit;
    default R ctype follows fit ties, so use method=fit['ties'] to match it.
    Explicit new strata required for stratified fits. Reject extrapolation beyond
    each stratum's largest observed time. Does not compute confidence intervals.
    """
    x, tt = np.asarray(newx, float), np.asarray(times, float)
    if x.ndim != 2 or x.shape[1] != len(fit['coefficients']) or not np.all(np.isfinite(x)):
        raise ValueError('newx must be a finite nnew by p matrix')
    if tt.ndim != 1 or not np.all(np.isfinite(tt)) or np.any(tt < 0):
        raise ValueError('times must be a finite nonnegative vector')
    if strata is None:
        if len(fit['strata']) != 1:
            raise ValueError('provide a stratum for every new observation')
        ss = np.repeat(fit['strata'][0], len(x))
    else:
        ss = np.asarray(strata)
    if ss.shape != (len(x),) or np.any(pd.isna(ss)) or np.any(~np.isin(ss, fit['strata'])):
        raise ValueError('new strata must be observed in the fit, one per row')
    out = np.empty((len(x), len(tt)))
    rr = np.exp((x-fit['reference']) @ fit['coefficients'])
    for table in baseline_hazard(fit, method=method):
        rows = ss == table['stratum']
        if not rows.any():
            continue
        if np.any(tt > table['time'][-1]):
            raise ValueError('prediction exceeds observed follow-up in a requested stratum')
        pos = np.searchsorted(table['time'], tt, side='right')
        h = np.r_[0, table['cumulative_hazard']][pos]
        out[rows] = np.exp(-rr[rows, None]*h)
    return out
