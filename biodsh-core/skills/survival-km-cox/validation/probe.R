.libPaths(c(Sys.getenv('R_LIMMA_LIB'), .libPaths()))
suppressMessages(library(survival))
cat(R.version.string, '\nsurvival ', as.character(packageVersion('survival')), '\nsurvRM2 ', as.character(packageVersion('survRM2')), '\n')
for (tp in c('log','log-log')) {
 f <- survfit(Surv(c(0,1,1,2),c(0,1,0,1))~1, conf.type=tp)
 print(data.frame(time=f$time,surv=f$surv,se=f$std.err,lower=f$lower,upper=f$upper))
}
print(survival:::survfit_confint)
