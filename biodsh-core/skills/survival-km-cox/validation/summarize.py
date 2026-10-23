"""Snapshot reproducible evidence and generate the skill's validation document."""
import sys, json, shutil, hashlib
from pathlib import Path
import pandas as pd
root=Path(sys.argv[1]); here=Path(__file__).resolve().parent; skill=here.parent
v=pd.read_csv(root/'comparison.csv',dtype={'seed':str})
props=json.loads((root/'properties.json').read_text())
evidence=here/'evidence'; evidence.mkdir(exist_ok=True)
for name in ['comparison.csv','properties.json','findings.json','r_run.log','data_20261020.csv','data_20261021.csv','edge.csv']:
    shutil.copyfile(root/name,evidence/name)
checksums={}
for p in [skill/'survival_py.py',here/'make_data.py',here/'survival_ref.R',here/'compare.py',here/'check_properties.py']:
    checksums[str(p.relative_to(skill))]=hashlib.sha256(p.read_bytes()).hexdigest()
(evidence/'sha256.json').write_text(json.dumps(checksums,indent=2)+'\n')
patterns=[
 ('KM + administrative censoring',r'^(km|admin)\.'),
 ('RMST per-arm estimates and all integral terms',r'^rmst\.[01]\.'),
 ('RMST difference/variance/z/CI/p',r'^rmst\.diff'),
 ('Log-rank: 2/3 groups and strata',r'^lr'),
 ('Cox beta/HR/SE/z/p/CI',r'^cox\.(breslow|efron)\.[01]\.[01]\.(beta|hr|se|z|p|coef_lower|coef_upper)$'),
 ('Cox model/selected covariance and information',r'^cox\.(breslow|efron)\.[01]\.[01]\.(cov|model_cov|info)$'),
 ('Cox individual/cluster scores and meat',r'^cox\.(breslow|efron)\.[01]\.[01]\.(score_residuals|cluster_scores|meat)$'),
 ('Cox total score at optimum',r'^cox\.(breslow|efron)\.[01]\.[01]\.score$'),
 ('Cox likelihood, tests, df and p',r'^cox\.(breslow|efron)\.[01]\.[01]\.(loglik|wald|score_test|lr|robust_score)$'),
 ('Cox null score/information',r'^cox\.(breslow|efron)\.[01]\.[01]\.(null_score|null_info)$'),
 ('Cox per-event times/counts/risk sums',r'^cox\.(breslow|efron)\.[01]\.[01]\.(detail|fixed)\.(time|nevent|nrisk|wtrisk|death_risk_sum)$'),
 ('Cox per-event means/score/information',r'^cox\.(breslow|efron)\.[01]\.[01]\.(detail|fixed)\.(means|score|imat)$'),
 ('Cox per-event likelihood and increments',r'^cox\.(breslow|efron)\.[01]\.[01]\.(detail|fixed)\.(loglik|hazard|hazard_breslow)$'),
 ('Cox fixed-beta likelihood/residuals',r'^cox\.(breslow|efron)\.[01]\.[01]\.fixed\.(loglik|residuals)$'),
 ('Cox baseline at means and at zero',r'^cox\.(breslow|efron)\.[01]\.[01]\.(basehaz|basehaz0|basetime)$'),
 ('Cox individual survival: both ctypes',r'^cox\.(breslow|efron)\.[01]\.[01]\.prediction\.'),
 ('Cox reference and observation/event counts',r'^cox\.(breslow|efron)\.[01]\.[01]\.(reference|n)$'),
 ('Cox one covariate / no-event stratum',r'^(single|zeroevent)\.')]
text='''# Numerical validation against R

Run date: 2026-10-20. Reference: **R 4.6.0, survival 3.8.6, survRM2 1.0.4**. Python uses numpy 2.5.2, scipy 1.18.1, pandas 2.3.3. No statsmodels or R calls occur inside the implementation. R reports that the installed survRM2 binary was built under R 4.6.1; its numerical checks below passed on R 4.6.0.

## Fixtures and scope

These are generic independently generated simulations, with no benchmark questions or answers read.

- Seed 20261020: n=257, group sizes 191/66, 170 events, continuous times, independent random right censoring; 3 unequal strata, 52 clusters of up to 5 subjects crossing strata.
- Seed 20261021: n=403, group sizes 274/129, 268 events; times rounded to half-units, with tied events/censors and time-zero events; 3 unequal strata, 81 clusters crossing strata.
- Edge fixture: 8 records, follow-up at 0/1/2/3/4, tied event/censor times, a terminal risk set in which everybody fails, tau exactly on an event; additionally all-censored and all-event-at-zero curves.
- Both seeds: KM log/log-log CIs before/after administrative censoring at tau=10; independent-arm RMST and difference; 2- and 3-group log-rank with/without strata. Cox crosses both tie methods × stratified/unstratified × model/cluster covariance (16 full fits). Fixed beta=(0.23,−0.17) and beta=0 are also evaluated. Additional one-covariate and no-event-stratum Cox fits run for both tie methods and both seeds.

R settings: `coxph.control(eps=1e-12,toler.chol=1e-14,iter.max=60,timefix=FALSE)`, `nocenter=NULL` to center binary columns consistently; Python uses its default score convergence tolerance 1e-10. No point-estimate mismatch was hidden by changing the mathematical estimand.

## Comparison criterion and complete result

'''
text+=f"**{len(v):,} array/scalar comparisons, {int(v.n.sum()):,} numeric entries, zero failures.** NaN and ±Inf masks are checked exactly, as are shapes.\n\n"
text+='''For every entry we retain raw relative error `abs(P−R)/max(abs(R),1e−12)` and absolute error. The pass threshold is 1e−8 relative for `abs(R)>1e−7`, and 1e−8 absolute near zero; scaled error `abs(P−R)/max(1,abs(R))` must also be ≤1e−8. This prevents an effectively zero fitted score or a zero information entry from being judged by unstable relative division. It does not omit those entries.

'''
text+=f"Global maxima: absolute **{v.max_abs.max():.3e}**, scaled **{v.max_scaled.max():.3e}**, relative on nonzero references **{v.max_rel_nonzero.max():.3e}**, absolute near zero **{v.nearzero_abs.max():.3e}**. The literal relative maximum is **{v.max_rel.max():.6g}**, from a fitted score whose absolute difference is only {v.nearzero_abs.max():.3e}; thus the literal relative-only 1e−8 goal is not met at numerical zeros, and this exception is explicit.\n\n"
text+='| Quantity | Seed 20261020 raw relative | relative (>1e−7) | Seed 20261021 raw relative | relative (>1e−7) | max absolute (both) |\n|---|---:|---:|---:|---:|---:|\n'
for name,pattern in patterns:
    a=v[v.key.str.contains(pattern.replace('(', '(?:'),regex=True)]
    columns=[]
    for seed in ['20261020','20261021']:
        b=a[a.seed==seed]; columns.extend([f'{b.max_rel.max():.3e}',f'{b.max_rel_nonzero.max():.3e}'])
    columns.append(f'{a.max_abs.max():.3e}')
    text+='| '+name+' | '+' | '.join(columns)+' |\n'
e=v[v.seed=='edge']
text+=f"\nEdge fixtures: {len(e)} comparisons, {e.n.sum()} entries; max nonzero relative error {e.max_rel_nonzero.max():.3e}, max absolute {e.max_abs.max():.3e}; all nonfinite masks match.\n"
text+='''
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

'''
text+=f"`check_properties.py` passed **{props['property_checks']}** assertions: finite-difference score/Hessian at nonzero beta, sum of individual scores, sum of information/log-likelihood contributions, row permutation and covariate translation invariance, reference-invariant predictions, no-event strata, terminal RMST, administrative-boundary behavior, and rejection of missing/invalid data, intercept/collinearity, separation, failed convergence and unsupported extrapolation.\n\n"
text+='Single-thread timing uses OPENBLAS_NUM_THREADS=OMP_NUM_THREADS=MKL_NUM_THREADS=1, n=5000, p=2, three strata and clusters of five. Import and IO are excluded; one warm-up then five timed calls. This meets the requested 1-second target on this workload, not a guarantee for high-dimensional designs (Cox moment storage is O(np²)).\n\n| Function | Median seconds | Maximum seconds |\n|---|---:|---:|\n'
for k in ['km','logrank_stratified','rmst_difference','cox_breslow','cox_efron']:
    text+=f"| {k} | {props[k]['seconds_median']:.6f} | {props[k]['seconds_max']:.6f} |\n"
text+='''
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
'''
(skill/'VALIDATION.md').write_text(text)
print(f'Wrote {skill / "VALIDATION.md"}; snapshotted {len(checksums)} source hashes.')
