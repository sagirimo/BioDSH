if (nzchar(Sys.getenv("R_LIMMA_LIB"))) .libPaths(c(Sys.getenv("R_LIMMA_LIB"), .libPaths()))
suppressMessages({library(limma); library(edgeR)})
a <- commandArgs(TRUE); cnt <- as.matrix(read.csv(a[1], row.names=1)); cv <- read.csv(a[2])
X <- model.matrix(~ grp + age, cv)
nf <- calcNormFactors(DGEList(cnt), method="TMM")$samples$norm.factors
lib <- colSums(cnt) * nf
v <- voom(cnt, X, lib.size=lib, save.plot=TRUE)
fit <- eBayes(lmFit(v, X))
lw <- v$voom.line
write.csv(data.frame(nf=nf), file.path(a[3], "r_nf.csv"), row.names=FALSE)
write.csv(v$weights, file.path(a[3], "r_w.csv"), row.names=FALSE)
write.csv(data.frame(lx=lw$x, ly=lw$y), file.path(a[3], "r_lowess.csv"), row.names=FALSE)
write.csv(data.frame(sx=v$voom.xy$x, sy=v$voom.xy$y), file.path(a[3], "r_xy.csv"), row.names=FALSE)
tt <- data.frame(coef=fit$coefficients[,2], t=fit$t[,2], p=fit$p.value[,2], padj=p.adjust(fit$p.value[,2], "BH"), s2post=fit$s2.post, dft=fit$df.total)
write.csv(tt, file.path(a[3], "r_fit.csv"), row.names=FALSE)
write.csv(data.frame(d0=fit$df.prior, s0=fit$s2.prior), file.path(a[3], "r_prior.csv"), row.names=FALSE)
cat("limma", as.character(packageVersion("limma")), "edgeR", as.character(packageVersion("edgeR")), "\n")
