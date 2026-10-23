# Rscript reference.R DATADIR OUTDIR ; all path args must be Windows paths on WSL.
if (nzchar(Sys.getenv('R_LIMMA_LIB'))) .libPaths(c(Sys.getenv('R_LIMMA_LIB'), .libPaths()))
suppressPackageStartupMessages({library(sandwich); library(clubSandwich); library(lmtest)})
args <- commandArgs(TRUE)
dir.create(args[2], recursive=TRUE, showWarnings=FALSE)
options(digits=17)
versions <- c(paste('R', getRversion()), sapply(c('sandwich','clubSandwich','lmtest'), function(p) paste(p, packageVersion(p))))
writeLines(versions, file.path(args[2], 'versions.txt'))
for (seed in 1:2) {
  raw <- read.csv(file.path(args[1], paste0('seed',seed,'.csv')))
  keep <- complete.cases(raw)
  d <- raw[keep, ]
  fits <- list(
    ols=lm(y~x+z+offset(offset), d),
    wls=lm(y~x+z+offset(offset), d, weights=weight),
    binomial=glm(binomial~x+z+offset(offset), d, family=binomial(), control=glm.control(epsilon=1e-14, maxit=100)),
    poisson=glm(poisson~x+z+offset(offset), d, family=poisson(), control=glm.control(epsilon=1e-14, maxit=100)),
    grouped_binomial=glm(proportion~x+z+offset(offset), d, weights=trials, family=binomial(), control=glm.control(epsilon=1e-14,maxit=100)),
    weighted_poisson=glm(poisson~x+z+offset(offset), d, weights=weight, family=poisson(), control=glm.control(epsilon=1e-14,maxit=100)))
  rows <- list()
  put <- function(name, value) {
    value <- as.vector(value)
    rows[[length(rows)+1L]] <<- data.frame(quantity=name, index=seq_along(value), value=value)
  }
  put('data.keep', as.integer(keep))
  for (model in names(fits)) {
    f <- fits[[model]]
    # glm stores the QR/weights from BEFORE its final coefficient update.
    # Refit from the converged coefficients so exported bread/hat/weights refer
    # to the same solution as the Python final-information convention.
    if(inherits(f,'glm') && !(length(args)>=3 && args[3]=='unpolished')) {
      f <- update(f, start=coef(f), control=glm.control(epsilon=1e-14,maxit=100))
    }
    prefix <- paste0(model,'.')
    add <- function(name,value) put(paste0(prefix,name),value)
    X <- model.matrix(f); n <- nrow(X); p <- ncol(X); G <- length(unique(d$cluster))
    add('n',n); add('p',p); add('converged',if(inherits(f,'glm')) f$converged else TRUE)
    ww <- if(inherits(f,'glm')) f$weights else if(is.null(weights(f))) rep(1,n) else weights(f)
    add('coefficients', coef(f)); add('fitted', fitted(f)); add('residuals', residuals(f,type='response'))
    add('eta', if(inherits(f,'glm')) f$linear.predictors else fitted(f))
    add('working_residuals', if(inherits(f,'glm')) residuals(f,type='working') else residuals(f))
    add('working_weights', ww); add('information', crossprod(X,ww*X))
    add('inverse_information', bread(f)/n); add('bread', bread(f)); add('scores', estfun(f))
    add('hat', hatvalues(f)); add('dispersion', if(inherits(f,'glm')) 1 else summary(f)$sigma^2)
    add('model_cov', vcov(f)); add('df_resid', df.residual(f))
    if(inherits(f,'glm')) add('deviance', deviance(f))
    test_cov <- function(label,V) {
      for (nm in c('normal','residual','cluster')) {
        df <- switch(nm, normal=Inf,residual=n-p,cluster=G-1)
        ct <- coeftest(f,vcov.=V,df=df)
        add(paste0(label,'.test.',nm,'.coefficients'),ct[,1])
        add(paste0(label,'.test.',nm,'.se'),ct[,2])
        add(paste0(label,'.test.',nm,'.statistic'),ct[,3])
        add(paste0(label,'.test.',nm,'.p_value'),ct[,4])
        add(paste0(label,'.test.',nm,'.df'),attr(ct,'df'))
        crit <- if(is.infinite(df)) qnorm(.975) else qt(.975,df)
        add(paste0(label,'.test.',nm,'.conf_low'),ct[,1]-crit*ct[,2])
        add(paste0(label,'.test.',nm,'.conf_high'),ct[,1]+crit*ct[,2])
        C <- rbind(c(0,1,0),c(0,0,1)); delta <- drop(C%*%coef(f))-c(.1,-.1)
        cv <- C%*%V%*%t(C); W <- drop(t(delta)%*%solve(cv,delta)); q <- nrow(C)
        stat <- if(is.infinite(df)) W else W/q
        pv <- if(is.infinite(df)) pchisq(W,q,lower.tail=FALSE) else pf(stat,q,df,lower.tail=FALSE)
        for (key in c('wald','statistic','df_num','df_denom','p_value','contrast_estimate','contrast_cov')) {
          value <- switch(key,wald=W,statistic=stat,df_num=q,df_denom=df,p_value=pv,contrast_estimate=delta,contrast_cov=cv)
          add(paste0(label,'.wald.',nm,'.',key),value)
        }
      }
    }
    test_cov('model',vcov(f))
    for (type in c('HC0','HC1','HC2','HC3')) {
      V <- vcovHC(f,type=type); add(paste0(type,'.cov'),V)
      add(paste0(type,'.meat'),meatHC(f,type=type))
      factors <- switch(type,HC0=rep(1,n),HC1=rep(n/(n-p),n),HC2=1/(1-hatvalues(f)),HC3=1/(1-hatvalues(f))^2)
      add(paste0(type,'.factors'),factors)
      add(paste0(type,'.adjusted_scores'),estfun(f)*sqrt(factors))
      test_cov(type,V)
    }
    for (type in c('CR0','CR1','CR1S','CR2','CR2_precision','CR2_custom')) {
      actual <- if(type %in% c('CR2_precision','CR2_custom')) 'CR2' else type
      if(type=='CR2_precision' && model!='wls') next
      target <- if(type=='CR2_precision') 1/d$weight else NULL
      if(type=='CR2_custom') target <- .7+.3*abs(d$x)
      V <- vcovCR(f,cluster=d$cluster,type=actual,target=target)
      add(paste0(type,'.cov'),V)
      add(paste0(type,'.meat'),vcovCR(f,cluster=d$cluster,type=actual,target=target,form='meat'))
      ef <- vcovCR(f,cluster=d$cluster,type=actual,target=target,form='estfun')
      components <- t(solve(bread(f)/n,ef))
      add(paste0(type,'.cluster_scores'),components)
      add(paste0(type,'.n_clusters'),G); add(paste0(type,'.df_cluster'),G-1)
      factor <- switch(actual,CR0=1,CR1=G/(G-1),CR1S=G/(G-1)*(n-1)/(n-p),CR2=1)
      add(paste0(type,'.factor'),factor)
      if(actual=='CR2') {
        add(paste0(type,'.adjustments'),unlist(lapply(attr(V,'adjustments'),as.vector)))
        targets <- numeric(n)
        for(j in seq_along(attr(V,'target'))) targets[d$cluster==sort(unique(d$cluster))[j]] <- diag(attr(V,'target')[[j]])
        add(paste0(type,'.target'),targets)
      }
      test_cov(type,V)
    }
    for (typ in c('HC0','HC1')) for (cadj in c(FALSE,TRUE)) {
      label <- paste0('CL_',typ,'_',if(cadj) 'TRUE' else 'FALSE')
      add(paste0(label,'.cov'),vcovCL(f,cluster=d$cluster,type=typ,cadjust=cadj))
      add(paste0(label,'.meat'),meatCL(f,cluster=d$cluster,type=typ,cadjust=cadj))
    }
  }
  write.csv(do.call(rbind,rows),file.path(args[2],paste0('reference_seed',seed,'.csv')),row.names=FALSE)
}
cat(paste(versions,collapse='; '),'\nAll reference quantities written.\n')
