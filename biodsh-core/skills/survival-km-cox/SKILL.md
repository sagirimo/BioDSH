---
name: survival-km-cox
description: Analyse right-censored time-to-event data using Kaplan–Meier, log/log-log Greenwood confidence intervals, ordinary or stratified log-rank tests, Breslow/Efron Cox regression with stratification and cluster-robust covariance, baseline hazards, individual survival curves, and RMST differences in numpy/scipy/pandas when R is unavailable. Validated numerically against R survival and survRM2.
---

# Survival analysis in Python

Use the adjacent `survival_py.py` library, or copy its required functions and helpers into a self-contained analysis script. It uses only numpy, scipy and pandas, has no file IO or global mutable state, and does not change inputs. The supported data are **one right-censored record per subject, unweighted, with fixed covariates**. Read [VALIDATION.md](VALIDATION.md) for reference versions, numeric comparisons and reproduction commands.

## Workflow

1. Align outcome, covariates, group, stratum and cluster by subject ID. Set `status=1` for the event of interest and `0` for right censoring; use finite nonnegative follow-up in a common time unit. Missing values raise an error. If exclusion is justified, create **one shared complete-case mask**, apply it to every array, and report exclusions. Do not turn a competing event into an ordinary event without defining the estimand.
2. If administrative censoring is requested, call `administrative_censor(time, status, tau)` before every relevant fit: `time=min(time,tau)`, `status=status*(time<=tau)`. An event exactly at tau remains an event. RMST integrates to tau directly; pre-truncating yields the same RMST and variance.
3. For descriptive curves, fit `kaplan_meier(t, e, conf_type='log-log')` in each group. `conf_type='log'` is also supported. Results cover **all** unique observation times, including censor-only times. Plot as right-continuous steps starting at `(0,1)` before applying any event at time zero; report `n_risk`, `n_event`, `n_censor`, `survival`, `se`, `lower`, `upper`.
4. For group comparison, call `logrank(t,e,group,strata=None)` or supply strata. Report the full `covariance`, `observed`, `expected`, `score=observed-expected`, chi-square `statistic`, `df` and `p_value`. For k groups, df is the number with positive expected events minus one. Strata pool scores and covariances, not chi-square statistics. `observed_by_stratum` and `expected_by_stratum` are group × stratum; `covariance_by_stratum` is stratum × group × group. Labels are sorted.
5. For adjusted hazard ratios, construct a finite n × p design **without an intercept**, with explicit reference levels. Call `coxph(t,e,X,strata=s,cluster=subject_cluster,ties='efron')`; omit optional arrays as appropriate. Choose the tie method from the analysis specification. Strata receive separate baseline hazards and share coefficients; a cluster defines score aggregation and can cross strata. Record design columns and their order. Singular models and nonconvergence raise errors instead of silently returning estimates.
6. Read `coefficients`, `hazard_ratio`, `se`, `z`, `p_value`, `coef_lower`, `coef_upper`, `covariance` and `model_covariance`. Coefficient intervals are on the **log hazard** scale; exponentiate them for hazard-ratio intervals. `wald`, `score_test`, `likelihood_ratio`, and (with clusters) `robust_score` contain `statistic`, `df`, `p_value`. The global null is beta=0; coefficient tests use a normal reference, global tests chi-square with p df, with no cluster t or G−1 adjustment.
7. Obtain `baseline_hazard(fit,method='breslow')` and `predict_survival(fit,newx,times,strata=new_strata,method='breslow')`. Each baseline table contains `time`, `increment`, `cumulative_hazard`, `stratum`, `reference`. The default reference is the column means used internally. Set `reference=np.zeros(p)` to obtain a literal x=0 baseline. Predictions are nnew × ntimes, right-continuous; times may be unordered. Specify a known stratum per new row for stratified fits. Prediction beyond a requested stratum's last observation raises an error.
8. For RMST, predefine a common tau within each arm's observed support. `rmst(t,e,tau)` returns the KM area, variance, SE and normal CI. `rmst_difference(t,e,group,tau)` requires groups 0 and 1 and returns **arm 1 minus arm 0**, independent-arm variance, z, p and CI, plus individual `arms`. Report the time unit and tau. These CIs are not clipped to [0,tau].

```python
import numpy as np
from survival_py import coxph, predict_survival, rmst_difference

# Arrays t, event, treatment, age, site, cluster have already been aligned.
X = np.column_stack([treatment, (age - 50) / 10])
f = coxph(t, event, X, strata=site, cluster=cluster, ties='efron')
hr = np.exp(f['coefficients'])
hr_ci = np.column_stack([np.exp(f['coef_lower']), np.exp(f['coef_upper'])])
# Use time points supported by every requested site.
s = predict_survival(f, [[0, 0], [1, 0]], [1, 3, 5],
                     strata=[site[0], site[0]], method='breslow')
r = rmst_difference(t, event, treatment, tau=5)
```

## Numerical conventions and intermediate outputs

- **KM:** `S(t)=prod(1-d_j/n_j)` and Greenwood `G(t)=sum[d_j/(n_j*(n_j-d_j))]`. The survival-scale variance is `S²G`. `std_err_log=sqrt(G)` matches the raw R `survfit` object; `se=S*sqrt(G)` matches the summary scale where finite. Log intervals transform `log(S) ± z*sqrt(G)`; log-log intervals transform `log(-log(S)) ± z*sqrt(G)/abs(log(S))` with endpoints reversed on back-transform.
- **Log-rank:** at each pooled event time let p be group risk proportions and d total events. Add `d*p` to expected counts and `d*(n-d)/(n-1)*(diag(p)-p*p.T)` to covariance, with zero contribution for n≤1. Tied censoring stays in the risk set. The full covariance is singular; one active group is removed to form the chi-square contrast. No events returns statistic=0, df=0, p=NaN (an explicit library convention); disconnected/nonestimable contrasts raise.
- **Cox:** each event-time contribution is `sum_event(x beta)-sum_l log(S0-f_l*E0)`, where f_l=l/d for Efron and 0 for Breslow; risk-set weighted first and second moments give the score and observed information. `cox_components(t,e,X,beta,strata,ties)` evaluates these at any supplied beta, with per-time risk sums, death-risk sums, means, scores, information and log likelihood. Its X is used directly. In fitted `tables`, X is centered at `fit['reference']`, so add the reference to `mean` when comparing raw R `coxph.detail$means`. Time/risk/event/hazard arrays use all observed times; other arrays use `event_time` only. Information is event × p × p.
- **Robust Cox covariance:** with individual score residuals U_i and cluster scores U_g, `meat=sum_g U_g U_g.T`, `model_covariance=information^-1`, and `covariance=model_covariance @ meat @ model_covariance`. There is no small-sample multiplier. Individual scores include risk-set contributions from censored observations and Efron tied-death corrections. `score_residuals`, `cluster_scores`, `meat`, `null_score`, and `null_information` are exposed. Wald/SE use selected covariance; ordinary score and LR remain model-based. `robust_score` uses clustered null-score residuals, matching R's separate robust score test.
- **RMST:** widths run from 0 through observation times to tau; `areas=widths*left_interval_survival`, `estimate=sum(areas)`. The variance is `sum_j tail_area_j²*d_j/[n_j*(n_j-d_j)]`; the tail area starts **after** event j. When n_j=d_j its contribution is 0 because survival afterwards is 0. Outputs include interval `widths`, `areas`, `tail_areas`, `greenwood_increment`, `variance_contributions` for audit.

## Pitfalls that change numbers

- Breslow and Efron are different with ties. In the tied simulation, the treatment log-HR is **0.3958037840 versus 0.4116484954**; without ties both are **0.6313650454**. Do not quietly change tie methods.
- R `basehaz()` inherits the model's tie method. An Efron-fitted model therefore needs `baseline_hazard(fit,method='efron')` to match `basehaz`, while the default here remains **Breslow** as its name specifies. R `survfit(fit,ctype=1)` matches Breslow and `ctype=2` matches Efron after an Efron fit. Efron hazard reconstruction after a Breslow fit is not exposed.
- Baseline hazards depend on the reference covariate vector. This library centers **all** columns at their means; R by default excludes binary columns from centering. For validation use R `nocenter=NULL`, or compare x=0 hazards / predictions for the same explicit covariates. Coefficients and subject predictions are unaffected by the choice of reference.
- A censor at an event time remains at risk for that event. In the small edge data, time 1 has risk set **7**, one event and one censor, giving survival **6/7**, not 5/6. `time<=tau`, not `<tau`, retains a boundary event.
- When the final risk set all fail, KM survival is 0: raw R log-SE and Greenwood are **Inf**, survival variance/SE and both transformed CIs are **NaN**. Preserve these undefined quantities. For all-censored data, S=1, variance=0, CI=[1,1]. RMST variance can remain finite even when terminal Greenwood diverges.
- Use the **full score residual**, not only the event contribution, for cluster covariance. Never treat strata as clusters unless that is the intended sampling unit. Cluster adjustment does not handle dependent observations for KM, log-rank or RMST in this library.
- RMST is a step-function integral, not trapezoidal interpolation. At tau=10 the two validation arm differences are **−1.7206913791** and **−1.1994997261**. The library conservatively rejects tau beyond each arm's last observation, even if some R endpoint conventions permit it.
- Exact floating-point equality defines ties here. R may merge nearby times via `timefix`; harmonize times explicitly when that behavior is wanted. These fixtures assert that R's `aeqSurv` makes no changes before log-rank comparison.
- R `summary.coxph$waldtest['test']` rounds the statistic to 2 decimals. Compare `fit$wald.test` for full precision. At the fitted optimum, a score of order 1e−13 is numerical zero: pure relative errors are misleading there; use absolute error as documented in validation.
- A stratum with no events contributes zero likelihood/score/information, has zero baseline cumulative hazard and predicted S=1. A globally event-free Cox model or a model with insufficient within-stratum covariate variation is not estimable and raises.

## Checks before reporting

- Subject counts, exclusions, group sizes, event counts, units, event definition and administrative tau are explicit.
- Labels/design columns and comparison direction match the question; no intercept or duplicate columns entered Cox.
- Tie method, reference covariates, strata and cluster units are recorded; model and robust covariance are distinguished.
- Fit converged; coefficients/SEs are finite; information is identifiable. There are enough independent clusters to justify the intended asymptotic inference.
- KM/predicted curves are nonincreasing in sorted time, in [0,1]; risk/event/censor counts agree with the data.
- RMST uses the same tau for both arms, lies in [0,tau], and its difference has the declared direction.
- Assess independent-censoring and proportional-hazards assumptions in context. This library does not automatically diagnose them.

## Not implemented

Left truncation or start-stop data; time-varying covariates; recurrent events; interval censoring; competing-risk/Aalen–Johansen models; observation weights; exact Cox ties; offsets, penalization, frailty or random effects; automatic time repair or NA omission; Schoenfeld PH tests; Cox survival-curve confidence bands; robust KM/log-rank/RMST; RMST ratios or covariate-adjusted RMST; finite-cluster corrections or cluster t inference. Do not substitute supported methods silently when these are required.

## References

R [coxph](https://www.stat.ethz.ch/R-manual/R-devel/library/survival/html/coxph.html), [coxph.detail](https://www.stat.ethz.ch/R-manual/R-devel/library/survival/html/coxph.detail.html), [survfit.coxph](https://www.stat.ethz.ch/R-manual/R-devel/library/survival/html/survfit.coxph.html), and [survRM2::rmst2](https://search.r-project.org/CRAN/refmans/survRM2/html/rmst2.html). Numerical authority is the installed package versions recorded in VALIDATION.md, including direct checks of `survfit`, `survdiff`, `coxph`, `basehaz`, and `rmst2`.
