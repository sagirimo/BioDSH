# Numerical validation against R

Run date: 2026-10-20. Reference: **R 4.6.0, survival 3.8.6, survRM2 1.0.4**. Python uses numpy 2.5.2, scipy 1.18.1, pandas 2.3.3. No statsmodels or R calls occur inside the implementation. R reports that the installed survRM2 binary was built under R 4.6.1; its numerical checks below passed on R 4.6.0.

## Fixtures and scope

These are generic independently generated simulations, with no benchmark questions or answers read.

- Seed 20261020: n=257, group sizes 191/66, 170 events, continuous times, independent random right censoring; 3 unequal strata, 52 clusters of up to 5 subjects crossing strata.
- Seed 20261021: n=403, group sizes 274/129, 268 events; times rounded to half-units, with tied events/censors and time-zero events; 3 unequal strata, 81 clusters crossing strata.
- Edge fixture: 8 records, follow-up at 0/1/2/3/4, tied event/censor times, a terminal risk set in which everybody fails, tau exactly on an event; additionally all-censored and all-event-at-zero curves.
- Both seeds: KM log/log-log CIs before/after administrative censoring at tau=10; independent-arm RMST and difference; 2- and 3-group log-rank with/without strata. Cox crosses both tie methods × stratified/unstratified × model/cluster covariance (16 full fits). Fixed beta=(0.23,−0.17) and beta=0 are also evaluated. Additional one-covariate and no-event-stratum Cox fits run for both tie methods and both seeds.

R settings: `coxph.control(eps=1e-12,toler.chol=1e-14,iter.max=60,timefix=FALSE)`, `nocenter=NULL` to center binary columns consistently; Python uses its default score convergence tolerance 1e-10. No point-estimate mismatch was hidden by changing the mathematical estimand.

## Comparison criterion and complete result

**1,145 array/scalar comparisons, 101,587 numeric entries, zero failures.** NaN and ±Inf masks are checked exactly, as are shapes.

For every entry we retain raw relative error `abs(P−R)/max(abs(R),1e−12)` and absolute error. The pass threshold is 1e−8 relative for `abs(R)>1e−7`, and 1e−8 absolute near zero; scaled error `abs(P−R)/max(1,abs(R))` must also be ≤1e−8. This prevents an effectively zero fitted score or a zero information entry from being judged by unstable relative division. It does not omit those entries.

Global maxima: absolute **5.002e-12**, scaled **2.826e-13**, relative on nonzero references **4.629e-12**, absolute near zero **2.826e-13**. The literal relative maximum is **0.282573**, from a fitted score whose absolute difference is only 2.826e-13; thus the literal relative-only 1e−8 goal is not met at numerical zeros, and this exception is explicit.

| Quantity | Seed 20261020 raw relative | relative (>1e−7) | Seed 20261021 raw relative | relative (>1e−7) | max absolute (both) |
|---|---:|---:|---:|---:|---:|
| KM + administrative censoring | 5.210e-15 | 5.210e-15 | 4.653e-15 | 4.653e-15 | 4.974e-14 |
| RMST per-arm estimates and all integral terms | 4.792e-15 | 4.792e-15 | 4.168e-15 | 4.168e-15 | 6.217e-15 |
| RMST difference/variance/z/CI/p | 2.194e-15 | 2.194e-15 | 6.457e-15 | 6.457e-15 | 5.329e-15 |
| Log-rank: 2/3 groups and strata | 1.718e-14 | 1.718e-14 | 2.794e-14 | 2.794e-14 | 4.832e-13 |
| Cox beta/HR/SE/z/p/CI | 3.540e-14 | 3.540e-14 | 2.752e-14 | 2.752e-14 | 9.770e-15 |
| Cox model/selected covariance and information | 6.269e-15 | 6.269e-15 | 2.745e-14 | 2.745e-14 | 3.126e-13 |
| Cox individual/cluster scores and meat | 1.910e-12 | 1.910e-12 | 8.091e-13 | 8.091e-13 | 4.547e-13 |
| Cox total score at optimum | 6.161e-02 | 0.000e+00 | 2.826e-01 | 0.000e+00 | 2.826e-13 |
| Cox likelihood, tests, df and p | 5.701e-13 | 3.426e-13 | 1.819e-12 | 1.419e-13 | 4.775e-12 |
| Cox null score/information | 9.724e-13 | 9.724e-13 | 1.122e-14 | 1.122e-14 | 5.684e-13 |
| Cox per-event times/counts/risk sums | 5.355e-15 | 5.355e-15 | 4.634e-15 | 4.634e-15 | 7.390e-13 |
| Cox per-event means/score/information | 1.110e-04 | 3.613e-13 | 9.327e-05 | 6.357e-13 | 5.507e-14 |
| Cox per-event likelihood and increments | 4.845e-15 | 4.845e-15 | 4.505e-15 | 4.505e-15 | 5.002e-12 |
| Cox fixed-beta likelihood/residuals | 1.711e-12 | 1.711e-12 | 4.629e-12 | 4.629e-12 | 5.002e-12 |
| Cox baseline at means and at zero | 4.572e-15 | 4.572e-15 | 4.543e-15 | 4.543e-15 | 4.974e-14 |
| Cox individual survival: both ctypes | 6.735e-16 | 6.735e-16 | 2.262e-15 | 2.262e-15 | 6.106e-16 |
| Cox reference and observation/event counts | 1.640e-15 | 1.640e-15 | 1.364e-14 | 1.364e-14 | 4.441e-16 |
| Cox one covariate / no-event stratum | 1.331e-14 | 1.331e-14 | 2.146e-15 | 2.146e-15 | 6.661e-16 |

Edge fixtures: 113 comparisons, 379 entries; max nonzero relative error 2.728e-15, max absolute 4.441e-15; all nonfinite masks match.

Every individual key, including each covariance entry, event-time information entry, CI endpoint, statistic, df and p-value, is represented in [evidence/comparison.csv](validation/evidence/comparison.csv). The table above aggregates them only for readability. Native R risk-set means, scores, information and hazard increments come from `coxph.detail`; native individual score residuals come from `residuals(type="score")`. Additional death-risk sums, per-time log likelihood and Breslow increments are reconstructed independently from R's fitted coefficient and risk sets. RMST interval contributions are independently reconstructed from R `survfit` alongside the native `rmst2`/`rmst1` estimates and variances. Those reconstructions are identified in the R script rather than presented as native object fields.

`basehaz(centered=TRUE/FALSE)` and `survfit(newdata,ctype=1/2)` are checked. `ctype=2` after a **Breslow-fitted** model is not exposed by this library and is explicitly skipped; ctype=1 is checked for both fits and ctype=2 for Efron fits. Iteration counts are optimizer-dependent metadata, not promised to match R; convergence and derivatives are checked instead. Names/labels are implementation metadata; numeric ordering is explicit.

## Findings that affected the implementation

1. At terminal S=0, native `survfit$std.err` is **Inf**, not NaN; the inherited partial implementation was corrected. Survival-scale variance/SE and transformed CI endpoints remain NaN. All-censored curves give S=1, SE=0, CI=[1,1].
2. A stratum without events exposed an empty-array preprocessing bug, now fixed; both R coefficient/covariance comparisons and the S=1 prediction property pass.
3. With ties, unstratified treatment coefficients are **0.395803784040823 (Breslow)** and **0.411648495416424 (Efron)**. Without ties both are **0.631365045433048**. Matching Cox coefficients alone would not validate an incorrectly computed Efron cluster covariance; score residuals and meat are checked separately.
4. R `survdiff` 3.8.6 incorrectly forwards an explicitly supplied `timefix` argument into `model.frame`, causing a length error. The reference script uses its default only after asserting `identical(Surv(...), aeqSurv(Surv(...)))`; no near-tie repair occurs in the tested data. The library always uses exact time equality.
5. R `summary.coxph` rounds the displayed Wald statistic to 2 decimals. The comparator uses the unrounded `fit$wald.test`, and separately compares df and p. Robust and ordinary score tests are distinct.
6. RMST arm1−arm0 at tau=10 is **−1.720691379128456** and **−1.199499726149262**. Area, eventwise variance contributions, per-arm variance, summed difference variance, z, CI and p are all compared.

## Behavioral and speed checks

`check_properties.py` passed **60** assertions: finite-difference score/Hessian at nonzero beta, sum of individual scores, sum of information/log-likelihood contributions, row permutation and covariate translation invariance, reference-invariant predictions, no-event strata, terminal RMST, administrative-boundary behavior, and rejection of missing/invalid data, intercept/collinearity, separation, failed convergence and unsupported extrapolation.

Single-thread timing uses OPENBLAS_NUM_THREADS=OMP_NUM_THREADS=MKL_NUM_THREADS=1, n=5000, p=2, three strata and clusters of five. Import and IO are excluded; one warm-up then five timed calls. This meets the requested 1-second target on this workload, not a guarantee for high-dimensional designs (Cox moment storage is O(np²)).

| Function | Median seconds | Maximum seconds |
|---|---:|---:|
| km | 0.000262 | 0.000321 |
| logrank_stratified | 0.001093 | 0.001157 |
| rmst_difference | 0.001025 | 0.001079 |
| cox_breslow | 0.008971 | 0.009712 |
| cox_efron | 0.008319 | 0.009405 |

## Reproduce

From the repository root in the specified WSL/Windows environment:

```bash
bash biodsh-core/skills/survival-km-cox/validation/run.sh
```

The runner sets thread limits, disables Python bytecode writes, passes `R_LIMMA_LIB=C:/Users/MOLIEX-DESKTOP/bench-rlib` into Windows R through `WSLENV`, and routes R temporary files and data under `C:/Users/MOLIEX-DESKTOP/bench-codex-scratch/skill-survival/`. It installs nothing. Required R packages are survival and survRM2. `R_LIMMA_LIB` is read by the R script; on another machine, run the scripts individually with an appropriate R library, Python executable and scratch path:

```text
python validation/make_data.py SCRATCH
Rscript --vanilla validation/survival_ref.R SCRATCH
python validation/compare.py SCRATCH
python validation/check_properties.py SCRATCH
python validation/summarize.py SCRATCH
```

The R script writes full native reference values as `r_20261020.csv`, `r_20261021.csv`, `r_edge.csv` in scratch. Summarization snapshots the per-key comparison table, simulation inputs, runtime/version metadata, R log and source SHA-256 into `validation/evidence/` and regenerates this file. [Evidence](validation/evidence/comparison.csv) and [property results](validation/evidence/properties.json) accompany the skill. `probe.R` is the preserved early environment/KM diagnostic, not required by the runner.

## Limits

Validation covers these simulated and edge cases, not every possible floating-point range, sample size or singular design. Missing values are tested as explicit errors, not as an automatic complete-case estimator. The all-no-event log-rank convention (df=0,p=NaN) is a library choice, not asserted to match R's degenerate behavior. Covariance/prediction confidence bands and other unsupported extensions are listed in SKILL.md. The package must not be presented as covering time-dependent or competing-risk models.
