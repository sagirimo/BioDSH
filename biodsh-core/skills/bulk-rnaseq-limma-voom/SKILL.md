---
name: bulk-rnaseq-limma-voom
description: Bulk RNA-seq differential expression with limma-voom (and edgeR TMM) in plain Python/numpy/scipy, matching R limma; use for count matrices (including fractional RSEM expected counts) with covariates, moderated t statistics, empirical Bayes prior df/variance, voom weights or LOWESS mean-variance trends when R is unavailable.
---

# Bulk RNA-seq differential expression: limma-voom in Python

Use when a bulk RNA-seq count matrix must be analysed with limma-style linear models and you cannot (or must not) call R:
voom precision weights, weighted per-gene least squares, empirical Bayes variance moderation (prior df, prior variance,
moderated t), BH adjustment, optionally TMM effective library sizes. `limma_py.py` (next to this file) is a tested
implementation that follows the R sources; copy the functions you need into your own script so it stays self-contained.

## Steps

1. **Counts and samples.** Rows = genes, columns = samples, aligned to the sample table **by sample ID**, never by
   position. Keep fractional counts (RSEM expected counts) as floats: do not round, do not treat as integers.
   Decide the gene set explicitly (all genes, or a filter the specification names) and apply it before voom; all-zero
   genes are excluded from the voom trend automatically but still get weights.
2. **Library sizes.** Default: column sums of the counts used. With TMM: `lib = colsums * tmm_factors(counts)`; compute
   factors on the same gene set edgeR would see (it drops all-zero rows itself). If the specification defines library
   size differently (e.g. totals over all genes before filtering), follow it.
3. **Design.** Build the design matrix by name: intercept first, then the coefficient of interest, then covariates in the
   stated order; reference level coded 0. Drop samples with missing covariates only as the specification says, and
   record how many were dropped and why. Check full column rank (`np.linalg.matrix_rank`).
4. **voom.** `v = voom(counts, X, lib_size=lib)` gives `E` (log2-CPM with +0.5 / +1 offsets) and `weights`.
   One voom per model when models use different samples or designs.
5. **Fit and moderate.** `fit = e_bayes(lm_fit(v['E'], X, v['weights']))`. Read `fit['df_prior']` (may be `inf`),
   `fit['s2_prior']`, `fit['s2_post']`, `fit['t']`, `fit['df_total']` (capped at the pooled residual df, as limma does),
   `fit['p_value']`. Adjust per coefficient with `p_adjust_bh`, over the genes tested in that model.
6. **Report.** Coefficient (log2 fold change), its moderated t and p, BH q, residual df, prior df and variance, number
   of genes tested and selected, sample counts per group (cases and comparison group), and any sensitivity model.

## Pitfalls that change numbers

- log-CPM is `log2((count + 0.5) / (lib + 1) * 1e6)`; the voom trend x is `Amean + mean(log2(lib + 1)) - log2(1e6)`,
  y is `sqrt(sigma)` from an **unweighted** fit; weights are `1 / trend(log2 fitted count)^4`, with constant
  extrapolation beyond the ends.
- Span: current limma (3.68) voom uses an adaptive span from the number of genes (`span=None` here, the default);
  limma releases before adaptive span used 0.5. If the specification names a span or a limma version, pass it; the
  choice moves every weight (7% on 4000 genes) and the prior df.
- R `lowess` is not statsmodels lowess: it uses `delta = 1% of the x range` (interpolates between fitted points) and 3
  robustness iterations. Use `lowess_r`; a different smoother changes every weight.
- Prior df can be infinite (all genes share one variance); then `s2_post = s2_prior` and `df_total` equals the pooled
  residual df. Report it as infinite, not as a large number, if the output asks.
- `df_total` is capped at the sum of residual df over genes; t uses the posterior variance, not the gene's own.
- BH must be computed within each model/coefficient over exactly the tested genes; NaN p-values are left out.
- `contrast()` gives exact per-gene SEs; limma's `contrasts.fit` approximates them for weighted, non-orthogonal designs.
- Not implemented: `eBayes(trend=TRUE)`, `robust=TRUE`, `duplicateCorrelation`, `voomWithQualityWeights`. Say so if the
  specification asks for them instead of silently using the plain versions.

## Checks before reporting

- Group sizes and dropped samples match the sample table; design columns are named and in order.
- Weights are finite and positive; `E` has no NaN; the number of tested genes equals the gene set chosen in step 1.
- Signs: the case coefficient is case minus reference.
- Spot-check one gene by hand: weighted least squares with its weights reproduces its coefficient.

## Validation

`limma_py.py` was compared with R 4.6 limma/edgeR (voom, lmFit, eBayes, calcNormFactors TMM, lowess, p.adjust) on
synthetic fractional-count data with a group effect, a continuous covariate and all-zero genes: see `VALIDATION.md`.
