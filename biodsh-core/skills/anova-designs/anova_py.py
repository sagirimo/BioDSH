"""ANOVA and one random-intercept REML; numpy/scipy/pandas only, no I/O.

Conventions follow R stats::anova/aov, car::Anova, nlme::lme and
emmeans::emmeans(weights='equal'). See SKILL.md for model restrictions.
All arrays use observations as rows; missing/non-finite inputs are rejected.
"""
from itertools import product
import numpy as np
import pandas as pd
from scipy import linalg, optimize, stats


def _response(y):
    y = np.asarray(y, dtype=float)
    if y.ndim != 1 or not len(y) or not np.isfinite(y).all():
        raise ValueError('y must be a nonempty finite vector; handle missing rows explicitly')
    return y


def _matrix(X, n):
    X = np.asarray(X, dtype=float)
    if X.ndim != 2 or X.shape[0] != n or not np.isfinite(X).all():
        raise ValueError('X must be finite with one row per observation')
    return X


def _codes(values):
    a = np.asarray(values)
    if a.ndim != 1 or pd.isna(a).any():
        raise ValueError('factor/group values must be one-dimensional and nonmissing')
    codes, levels = pd.factorize(a, sort=True)
    return codes, list(levels)


def indicator(values):
    """Group indicator matrix (R model.matrix(~ group - 1)); sorted levels."""
    codes, levels = _codes(values)
    return np.eye(len(levels))[codes]


def factorial_design(data, factors, terms=None, levels=None, coding='sum'):
    """Categorical model.matrix; R contr.sum or contr.treatment, intercept included.

    factors is an ordered list of names. terms is an ordered list of tuples,
    e.g. [('A',), ('B',), ('A','B')]; default is all interactions by degree.
    Supply levels explicitly to reproduce R factor levels. Interactions use R's
    first-factor-varies-fastest column order. No formula parser or numeric covariates.
    """
    from itertools import combinations
    factors = list(factors)
    if not factors or len(set(factors)) != len(factors):
        raise ValueError('supply distinct factor names')
    if coding not in ('sum', 'treatment'):
        raise ValueError("coding must be 'sum' or 'treatment'")
    if terms is None:
        terms = [t for k in range(1, len(factors)+1) for t in combinations(factors, k)]
    terms = [tuple(t) for t in terms]
    if len(set(terms)) != len(terms) or any(not t or len(set(t)) != len(t) or not set(t) <= set(factors) for t in terms):
        raise ValueError('invalid or duplicate terms')
    lev, basis, labels = {}, {}, {}
    n = len(data)
    for name in factors:
        a = np.asarray(data[name])
        if len(a) != n or pd.isna(a).any():
            raise ValueError('missing factors are not silently dropped')
        lv = list(levels[name]) if levels is not None else _codes(a)[1]
        if len(lv) < 2 or len(set(lv)) != len(lv):
            raise ValueError('each factor needs at least two distinct declared levels')
        code = pd.Categorical(a, categories=lv).codes
        if (code < 0).any():
            raise ValueError('observed factor value absent from declared levels')
        C = np.vstack([np.eye(len(lv)-1), -np.ones((1,len(lv)-1))]) if coding == 'sum' else np.eye(len(lv))[:,1:]
        basis[name] = C[code]
        labels[name] = [f'{name}{j+1}' for j in range(len(lv)-1)] if coding == 'sum' else [f'{name}{v}' for v in lv[1:]]
        lev[name] = lv
    columns, names, slices = [np.ones((n,1))], ['(Intercept)'], {}
    offset = 1
    for term in terms:
        combos = [tuple(reversed(c)) for c in product(*(range(basis[f].shape[1]) for f in reversed(term)))]
        mat = np.column_stack([np.prod(np.column_stack([basis[f][:,j] for f,j in zip(term,c)]),axis=1) for c in combos])
        name = ':'.join(term)
        slices[name] = np.arange(offset, offset+mat.shape[1])
        names += [':'.join(labels[f][j] for f,j in zip(term,c)) for c in combos]
        columns.append(mat)
        offset += mat.shape[1]
    return dict(X=np.column_stack(columns), columns=names, terms=terms,
                term_columns=slices, levels=lev, factors=factors, coding=coding)


def _basis(X, tol=1e-10):
    if X.shape[1] == 0:
        return np.empty((X.shape[0],0))
    U, s, _ = linalg.svd(X, full_matrices=False, check_finite=False)
    rank = int(np.sum(s > tol * max(1., s[0])))
    return U[:,:rank]


def _sse(y, X):
    Q = _basis(X)
    r = y - Q @ (Q.T @ y)
    return float(r @ r), Q.shape[1]


def ols(y, X):
    """R lm full-rank unweighted fit: beta, vcov, residuals, SSE, df and sigma2.

    Rejects singular designs rather than selecting arbitrary aliased coefficients.
    """
    y = _response(y); X = _matrix(X, len(y))
    n,p = X.shape
    if not p or _basis(X).shape[1] != p or n <= p:
        raise ValueError('full column rank and positive residual df required (check empty cells)')
    Q,R = linalg.qr(X, mode='economic', check_finite=False)
    beta = linalg.solve_triangular(R, Q.T@y, check_finite=False)
    residual = y-X@beta
    sse = float(residual@residual); df = n-p; sigma2 = sse/df
    ri = linalg.solve_triangular(R, np.eye(p), check_finite=False)
    unscaled = ri@ri.T
    return dict(beta=beta, vcov=unscaled*sigma2, unscaled_vcov=unscaled,
                fitted=X@beta, residual=residual, sse=sse, df_residual=df,
                sigma2=sigma2, rank=p, n=n)


def anova(y, design, typ='II', include_intercept=False):
    """R anova(lm) (I), car::Anova(lm,type=2/3) (II/III).

    Type I follows supplied term order. Type II adjusts for terms not containing
    the tested term and uses full-model MSE. Type III tests coefficient blocks
    in a sum-coded categorical design; intercept test optional (R includes it).
    All types reject rank deficiency. Result includes full OLS fit and table.
    """
    y = _response(y); X = _matrix(design['X'],len(y))
    typ = str(typ).upper()
    typ = {'1':'I','2':'II','3':'III'}.get(typ,typ)
    if typ not in ('I','II','III'):
        raise ValueError('typ must be I, II, or III')
    if typ == 'III' and design.get('coding') != 'sum':
        raise ValueError('Type III categorical tests require sum coding here')
    fit = ols(y,X); rows=[]; allcols=list(range(X.shape[1])); previous=[0]
    for term in ([()] if include_intercept and typ == 'III' else [])+design['terms']:
        name = ':'.join(term) if term else '(Intercept)'
        cols = list(design['term_columns'][name]) if term else [0]
        if typ == 'I':
            base=previous.copy(); augmented=base+cols; previous=augmented
        elif typ == 'II':
            base=[0]
            for other in design['terms']:
                if not set(term) <= set(other):
                    base += list(design['term_columns'][':'.join(other)])
            augmented=base+cols
        else:
            base=[c for c in allcols if c not in cols]; augmented=allcols
        ss0,r0=_sse(y,X[:,base]); ss1,r1=_sse(y,X[:,augmented])
        ss=max(0.,ss0-ss1); df=r1-r0; ms=ss/df
        F=ms/fit['sigma2']; p=stats.f.sf(F,df,fit['df_residual'])
        rows.append(dict(term=name,ss=ss,df=df,ms=ms,F=F,p=p,
                         denominator_df=fit['df_residual'],denominator_ms=fit['sigma2']))
    rows.append(dict(term='Residuals',ss=fit['sse'],df=fit['df_residual'],ms=fit['sigma2'],
                     F=np.nan,p=np.nan,denominator_df=np.nan,denominator_ms=np.nan))
    return dict(table=pd.DataFrame(rows),fit=fit,type=typ)


def strata_anova(y, design, error_terms, tol=1e-10):
    """R aov(y ~ fixed + Error(...)): sequential fits in orthogonal error strata.

    error_terms is ordered [(name, matrix), ...] for the error-model term spaces;
    use group indicators for nested strata: block, then block:A. Intercept is
    removed first; the orthogonal complement is named 'Within'. Full-data fixed
    model must be identifiable. No weights, missing values, or denominator pooling.
    Each effect's F uses the residual MS/df IN THAT STRATUM. Without balance an
    effect can appear in several strata; this is R's sequential decomposition,
    not a single efficient mixed-model test. Tables omit zero-df terms.

    diagnostics exposes basis-invariant projected cross-products and sums of
    squares, rather than arbitrary signed QR coordinates or aliased coefficients.
    """
    y=_response(y); X=_matrix(design['X'],len(y)); n=len(y)
    if _basis(X).shape[1] != X.shape[1]:
        raise ValueError('fixed design is singular; empty cells require explicit estimable hypotheses')
    names=[t[0] for t in error_terms]
    if len(set(names)) != len(names) or any(s in ('Within','(Intercept)') for s in names):
        raise ValueError('error stratum names must be unique and not reserved')
    Q=np.ones((n,1))/np.sqrt(n); strata=[]
    for name,Z in error_terms:
        Z=_matrix(Z,n)
        R=Z-Q@(Q.T@Z)
        R-=Q@(Q.T@R)
        U=_basis(R,tol)
        if U.shape[1]:
            strata.append((name,U.shape[1],U.T@y,U.T@X))
            Q=np.column_stack([Q,U])
    if Q.shape[1]<n:
        yy=y-Q@(Q.T@y); XX=X-Q@(Q.T@X)
        strata.append(('Within',n-Q.shape[1],yy,XX))
    rows=[]; diagnostics={}
    for name,dimension,yy,XX in strata:
        # Type I term projections; absolute floor suppresses roundoff-only columns.
        U=np.empty((len(yy),0)); effect_rows=[]
        for term in design['terms']:
            tname=':'.join(term); W=XX[:,design['term_columns'][tname]]
            W=W-U@(U.T@W); W-=U@(U.T@W)
            V=_basis(W,tol)
            if not V.shape[1]:
                continue
            ss=float(np.sum((V.T@yy)**2))
            effect_rows.append(dict(stratum=name,term=tname,ss=ss,df=V.shape[1],ms=ss/V.shape[1]))
            U=np.column_stack([U,V])
        residual=yy-U@(U.T@yy); sse=float(residual@residual)
        rdf=dimension-U.shape[1]; mse=sse/rdf if rdf>0 else np.nan
        for row in effect_rows:
            row.update(F=row['ms']/mse if rdf>0 and mse>0 else np.nan,
                       denominator_df=rdf,denominator_ms=mse)
            row['p']=stats.f.sf(row['F'],row['df'],rdf) if rdf>0 else np.nan
        rows.extend(effect_rows)
        if rdf>0:
            rows.append(dict(stratum=name,term='Residuals',ss=sse,df=rdf,ms=mse,F=np.nan,p=np.nan,
                             denominator_df=np.nan,denominator_ms=np.nan))
        diagnostics[name]=dict(dimension=dimension,rank=U.shape[1],y_ss=float(yy@yy),
                               xtx=XX.T@XX,xty=XX.T@yy,sse=sse,df_residual=rdf)
    return dict(table=pd.DataFrame(rows),diagnostics=diagnostics,
                intercept_ss=float(np.sum(y)**2/n),total_ss=float(y@y))


def randomized_block(data, response, block, treatment):
    """R aov(y ~ treatment + Error(block)); one or more observations per cell.

    Balanced one-per-cell: treatment denominator df=(blocks-1)*(treatments-1).
    """
    d=factorial_design(data,[treatment])
    return strata_anova(data[response],d,[(block,indicator(data[block]))])


def split_plot(data, response, block, whole, sub):
    """R aov(y ~ A*B + Error(block/A)); block/whole labels identify whole plots.

    Balanced one-per-subplot: A denominator df=(r-1)*(a-1); B and A:B
    denominator df=a*(r-1)*(b-1). Unbalanced results are stratified Type I only.
    """
    d=factorial_design(data,[whole,sub])
    plot=pd.MultiIndex.from_frame(data[[block,whole]]).to_flat_index().to_numpy()
    return strata_anova(data[response],d,[(block,indicator(data[block])),
                        (f'{block}:{whole}',indicator(plot))])


def repeated_measures(data, response, subject, within, between=None):
    """R aov(y ~ [group*]time + Error(subject/time)), one row per subject/time.

    Supports one within factor and optional one between factor. Classical
    univariate F tests assume sphericity; no GG/HF correction. Missing occasions
    rejected because this wrapper promises the complete repeated-measures design.
    Unequal numbers of subjects per between group are allowed.
    """
    if data.duplicated([subject,within]).any():
        raise ValueError('one observation per subject/occasion required')
    if data.groupby(subject,observed=True)[within].nunique().min()!=data[within].nunique():
        raise ValueError('incomplete repeated measures: specify a suitable mixed model')
    if between and data.groupby(subject,observed=True)[between].nunique().max()!=1:
        raise ValueError('between factor must be constant within each subject')
    d=factorial_design(data,[between,within] if between else [within])
    # subject:occasion spans all n rows; the complement of subject has that label.
    out=strata_anova(data[response],d,[(subject,indicator(data[subject]))])
    label=f'{subject}:{within}'
    out['table']['stratum']=out['table']['stratum'].replace({'Within':label})
    out['diagnostics'][label]=out['diagnostics'].pop('Within')
    return out


def random_intercept_reml(y, X, groups):
    """One random intercept, R nlme::lme(method='REML', random=~1|group).

    V=sigma2*(I+lambda*ZZ'); profile sigma2=RSS_V/(n-p), optimize lambda>=0.
    Uses group sums (no n-by-n covariance). Returns marginal beta/covariance,
    variance components, restricted log likelihood, information/cross-products,
    BLUPs and conditional residuals. No automatic fixed-effect df/p-values:
    nlme containment, Satterthwaite and Kenward-Roger are NOT interchangeable.
    Boundary lambda=0 is explicitly allowed; reject nonidentifiable variance split.
    Unbalanced groups can produce several stationary points: compare score roots
    bracketed on a log grid (1e-10 .. 1e8) with the boundary, rather than deciding
    from the score at zero alone. Extremely narrow unsampled extrema are not
    guaranteed; a best solution at the upper search limit raises an error.
    """
    y=_response(y); X=_matrix(X,len(y)); n,p=X.shape
    if not p or _basis(X).shape[1]!=p or n<=p:
        raise ValueError('full rank X and n>p required')
    code,levels=_codes(groups)
    if len(code)!=n:
        raise ValueError('groups must align with y')
    g=len(levels); counts=np.bincount(code).astype(float)
    sx=np.zeros((g,p)); sy=np.bincount(code,weights=y)
    np.add.at(sx,code,X)
    if g<2 or np.all(counts==1):
        raise ValueError('need at least two groups and some repeated observations')
    # Z must retain information after removing fixed effects.
    if np.sum(counts)-np.trace(linalg.solve(X.T@X,sx.T@sx)) < 1e-8*n:
        raise ValueError('group intercepts are absorbed by fixed effects')
    xtx=X.T@X; xty=X.T@y
    def evaluate(lam):
        w=lam/(1+lam*counts)
        info=xtx-sx.T@(w[:,None]*sx)
        rhs=xty-sx.T@(w*sy)
        cf=linalg.cho_factor(info,lower=True,check_finite=False)
        beta=linalg.cho_solve(cf,rhs,check_finite=False)
        r=y-X@beta; sr=np.bincount(code,weights=r)
        rss=float(r@r-np.sum(w*sr*sr))
        if rss<=0:
            raise ValueError('nonpositive residual variance; degenerate response or numerical scaling')
        sigma2=rss/(n-p)
        logdetC=float(np.log1p(lam*counts).sum())
        logdetI=float(2*np.log(np.diag(cf[0])).sum())
        nll=.5*((n-p)*(np.log(2*np.pi*sigma2)+1)+logdetC+logdetI)
        cov0=linalg.cho_solve(cf,np.eye(p),check_finite=False)
        # Exact derivative of profiled restricted likelihood w.r.t lambda.
        # Z'C^-1 r = sr/(1+lambda*m), Z'C^-1 X = sx/(1+lambda*m).
        zcx=sx/(1+lam*counts)[:,None]
        trP=float(np.sum(counts/(1+lam*counts))-np.sum((zcx@cov0)*zcx))
        score=.5*(trP-np.sum((sr/(1+lam*counts))**2)/sigma2)
        return nll,score,beta,cov0,sigma2,r,info,rhs,rss,logdetC,logdetI,sr
    grid=np.r_[0.,np.geomspace(1e-10,1e8,161)]
    evaluations=[evaluate(v) for v in grid]
    candidates=[(0.,evaluations[0][0])]
    for i in range(len(grid)-1):
        left,right=evaluations[i][1],evaluations[i+1][1]
        if left==0:
            candidates.append((grid[i],evaluations[i][0]))
        if left*right<0:
            root=optimize.brentq(lambda v:evaluate(v)[1],grid[i],grid[i+1],
                                xtol=1e-12,rtol=1e-14)
            candidates.append((root,evaluate(root)[0]))
    lam,best=min(candidates,key=lambda item:item[1])
    if evaluations[-1][0]<best:
        raise ValueError('best variance ratio exceeds search range; check model/scaling')
    status='boundary' if lam==0 else 'interior'
    nll,score,beta,cov0,sigma2,r,info,rhs,rss,ldc,ldi,sr=evaluate(lam)
    blup=lam*sr/(1+lam*counts)
    fitted=X@beta+blup[code]
    return dict(beta=beta,vcov=cov0*sigma2,sigma2=sigma2,tau2=lam*sigma2,
                variance_ratio=lam,loglik=-nll,score=score,df_residual=n-p,
                group_levels=levels,group_counts=counts,blup=blup,
                fitted_marginal=X@beta,fitted_conditional=fitted,
                residual_marginal=r,residual_conditional=y-fitted,
                info_unscaled=info,rhs=rhs,rss_generalized=rss,
                logdet_correlation=ldc,logdet_information=ldi,status=status)


def marginal_means(fit, design, by, df=None, level=.95):
    """R emmeans(lm, ~by, weights='equal') categorical reference grid.

    Averages model rows over every nuisance-factor level equally, including
    interactions. Supports full-rank OLS; mixed-model covariance allowed only
    with caller-supplied df (np.inf selects asymptotic normal inference).
    Returns linear functions L, estimates, full covariance, SE, t CI, df.
    No multiplicity adjustment, no numeric covariates, no rank-deficient fits.
    """
    by=[by] if isinstance(by,str) else list(by)
    if len(set(by))!=len(by) or not set(by)<=set(design['factors']):
        raise ValueError('by must contain distinct model factor names')
    if df is None:
        if 'variance_ratio' in fit:
            raise ValueError('mixed-model marginal means require an explicit df convention')
        df=fit['df_residual']
    if not df>0 or not 0<level<1:
        raise ValueError('positive df and 0<level<1 required')
    factors=design['factors']; lev=design['levels']
    grid=pd.DataFrame(list(product(*(lev[f] for f in factors))),columns=factors)
    gd=factorial_design(grid,factors,design['terms'],lev,design['coding'])
    keys=list(product(*(lev[f] for f in by))) if by else [()]
    L=[]
    for key in keys:
        mask=np.ones(len(grid),bool)
        for f,v in zip(by,key):
            mask &= np.asarray(grid[f]==v)
        L.append(gd['X'][mask].mean(0))
    L=np.asarray(L); mean=L@fit['beta']; cov=L@fit['vcov']@L.T
    se=np.sqrt(np.maximum(0,np.diag(cov))); crit=stats.t.ppf((1+level)/2,df)
    table=pd.DataFrame(keys,columns=by)
    table['emmean']=mean; table['SE']=se; table['df']=df
    table['lower.CL']=mean-crit*se; table['upper.CL']=mean+crit*se
    return dict(table=table,L=L,vcov=cov,grid=grid)
