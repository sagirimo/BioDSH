# Validation of limma_py.py against R

Reference: R 4.6.0, limma 3.68.5, edgeR 4.10.6 (2026-10-20).

Data: `validation/make_data.py SEED counts.csv covars.csv` — 4000 genes x 24 samples, negative binomial counts scaled
by U(0.85, 1) to make RSEM-like fractional counts, 10% of genes with a group effect, a continuous covariate (age), 50
all-zero genes. Design `~ grp + age`, TMM effective library sizes, voom with default (adaptive) span, lmFit, eBayes.
Run: `Rscript validation/limma_ref.R counts.csv covars.csv OUTDIR` then `python validation/compare.py SKILLDIR OUTDIR`.

| quantity | seed 1 max relative difference | seed 2 |
|---|---|---|
| TMM norm factors | 4.6e-15 | 4.5e-15 |
| voom trend x, y | 4.9e-13, 5.4e-15 | 8.5e-13, 5.1e-15 |
| lowess trend line | 3.3e-14 | 2.5e-14 |
| voom weights | 1.2e-13 | 8.9e-14 |
| prior df / prior variance | 30.7192393901 vs R 30.7192393901 | 34.0573601009 vs 34.0573601009 |
| coefficient, moderated t | 1.7e-10 | 6.0e-11 |
| p value, BH q | 7.1e-13, 8.9e-13 | 7.6e-13, 5.9e-13 |
| df.total | 4.9e-15 | 1.5e-14 |

Also checked: voom with `span=0.5` against `voom(adaptive.span=FALSE)` (weights 1.5e-13); eBayes with a finite large
prior df (383.297, identical t) and with an infinite prior df (R `Inf`, s2.prior 1.194163, df.total 5000: identical).

Finding while validating: limma 3.68 voom defaults to `adaptive.span=TRUE` (span from `chooseLowessSpan(ngenes)`), so a
fixed span of 0.5 — the long-standing default — gave weights up to 7% off and a prior df of 28.5 instead of 30.7.
