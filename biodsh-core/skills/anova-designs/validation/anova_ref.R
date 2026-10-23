# R reference outputs, no Python calculations are imported.
lib <- Sys.getenv('R_LIMMA_LIB', 'C:/Users/MOLIEX-DESKTOP/bench-rlib')
.libPaths(c(lib, .libPaths()))
args <- commandArgs(trailingOnly=TRUE)
stopifnot(length(args)==2)
input <- args[1]; output <- args[2]
dir.create(output, recursive=TRUE, showWarnings=FALSE)
stopifnot(requireNamespace('car'),requireNamespace('nlme'),requireNamespace('emmeans'))
options(contrasts=c('contr.sum','contr.poly'), digits=17)
vals <- list()
put <- function(key,x) {
  z <- as.numeric(x)
  # R column-major order, identical to Python ravel(order='F').
  for(i in seq_along(z)) vals[[paste0(key,'/',i)]] <<- z[i]
}
put_table <- function(prefix,tab) {
  for(i in seq_len(nrow(tab))) {
    term <- trimws(rownames(tab)[i]); row <- tab[i,,drop=FALSE]
    ss <- as.numeric(row[['Sum Sq']]); df <- as.numeric(row[['Df']])
    put(paste(prefix,term,'ss',sep='/'),ss)
    put(paste(prefix,term,'df',sep='/'),df)
    put(paste(prefix,term,'ms',sep='/'),ss/df)
    if ('F value' %in% names(row)) put(paste(prefix,term,'F',sep='/'),row[['F value']])
    if ('Pr(>F)' %in% names(row)) put(paste(prefix,term,'p',sep='/'),row[['Pr(>F)']])
    if(term!='Residuals') {
      rdf <- tab['Residuals','Df']; mse <- tab['Residuals','Sum Sq']/rdf
      put(paste(prefix,term,'denominator_df',sep='/'),rdf)
      put(paste(prefix,term,'denominator_ms',sep='/'),mse)
    }
  }
}
put_fit <- function(m) {
  put('fit/beta',coef(m)); put('fit/vcov',vcov(m))
  put('fit/unscaled_vcov',summary(m)$cov.unscaled)
  put('fit/fitted',fitted(m)); put('fit/residual',residuals(m))
  put('fit/sse',sum(residuals(m)^2)); put('fit/df_residual',df.residual(m))
  put('fit/sigma2',sigma(m)^2); put('fit/rank',m$rank); put('fit/n',nobs(m))
}
put_strata <- function(d, fixed, err) {
  formula <- as.formula(paste(deparse(fixed),'+Error(',err,')'))
  m <- aov(formula,data=d)
  sm <- summary(m)
  for(nm in names(sm)) put_table(paste0('table/',sub('Error: ','',nm,fixed=TRUE)), sm[[nm]][[1]])
  # Reconstruct the actual R error-model QR and compare coordinate-free quantities.
  qe <- attr(m,'error.qr'); Q <- qr.Q(qe,complete=TRUE)
  op <- options(contrasts=c('contr.helmert','contr.poly'))
  em <- lm(as.formula(paste('y~',err)),data=d)
  options(op)
  labels <- c('(Intercept)',attr(terms(em),'term.labels'))
  assignment <- em$assign[qe$pivot[seq_len(qe$rank)]]
  if(nrow(d)>qe$rank) { assignment <- c(assignment,rep(length(labels),nrow(d)-qe$rank)); labels <- c(labels,'Within') }
  X <- model.matrix(fixed,d); put('design/X',X)
  for(i in seq_along(labels)) {
    nm <- labels[i]; if(nm=='(Intercept)') next
    select <- which(assignment==i-1); if(!length(select)) next
    yy <- crossprod(Q[,select,drop=FALSE],d$y); XX <- crossprod(Q[,select,drop=FALSE],X)
    pre <- paste0('diagnostics/',nm,'/')
    put(paste0(pre,'dimension'),length(select)); put(paste0(pre,'rank'),m[[nm]]$rank)
    put(paste0(pre,'y_ss'),sum(yy^2)); put(paste0(pre,'xtx'),crossprod(XX)); put(paste0(pre,'xty'),crossprod(XX,yy))
    put(paste0(pre,'sse'),sum(residuals(m[[nm]])^2)); put(paste0(pre,'df_residual'),df.residual(m[[nm]]))
  }
  put('intercept_ss',sum(d$y)^2/nrow(d)); put('total_ss',sum(d$y^2))
}
put_reml <- function(d,boundary=FALSE) {
  fm <- if(!'A' %in% names(d)) y~1 else y~A+x
  m <- nlme::lme(fm,random=~1|group,data=d,method='REML',
    control=nlme::lmeControl(opt='optim',optimMethod='BFGS',maxIter=200,msMaxIter=1000,tolerance=1e-10,msTol=1e-12,apVar=FALSE))
  X <- model.matrix(fm,d); y <- d$y; n <- length(y); p <- ncol(X)
  Z <- model.matrix(~group-1,d); counts <- colSums(Z)
  sigma2 <- m$sigma^2; tau2 <- as.numeric(nlme::VarCorr(m)[1,'Variance']); lam <- tau2/sigma2
  # Matrix reference independent of Python's grouped Woodbury implementation.
  C <- diag(n)+lam*tcrossprod(Z); ci <- solve(C)
  info <- crossprod(X,ci%*%X); rhs <- crossprod(X,ci%*%y)
  beta <- nlme::fixef(m); r <- as.numeric(y-X%*%beta)
  rss <- as.numeric(crossprod(r,ci%*%r)); sr <- crossprod(Z,r)
  put('design/X',X)
  put('beta',beta); put('vcov',vcov(m)); put('sigma2',sigma2); put('tau2',tau2)
  put('variance_ratio',lam); put('loglik',logLik(m)); put('df_residual',n-p)
  put('group_counts',counts); put('blup',nlme::ranef(m)[,1])
  put('fitted_marginal',fitted(m,level=0)); put('fitted_conditional',fitted(m,level=1))
  put('residual_marginal',residuals(m,level=0)); put('residual_conditional',residuals(m,level=1))
  put('info_unscaled',info); put('rhs',rhs); put('rss_generalized',rss)
  put('logdet_correlation',determinant(C,logarithm=TRUE)$modulus)
  put('logdet_information',determinant(info,logarithm=TRUE)$modulus)
  P <- ci-ci%*%X%*%solve(info)%*%t(X)%*%ci
  score <- .5*(sum(diag(crossprod(Z,P%*%Z)))-sum(crossprod(Z,ci%*%r)^2)/sigma2)
  put('score',score)
  # Extra reference: solve the REML score independently in R for optimizer precision.
  profile <- function(lambda, export=FALSE) {
    C <- diag(n)+lambda*tcrossprod(Z); ci <- solve(C)
    info <- crossprod(X,ci%*%X); v <- solve(info)
    b <- v%*%crossprod(X,ci%*%y); r <- y-X%*%b; s2 <- as.numeric(crossprod(r,ci%*%r))/(n-p)
    P <- ci-ci%*%X%*%v%*%t(X)%*%ci
    score <- .5*(sum(diag(crossprod(Z,P%*%Z)))-sum(crossprod(Z,ci%*%r)^2)/s2)
    ldc <- as.numeric(determinant(C,logarithm=TRUE)$modulus)
    ldi <- as.numeric(determinant(info,logarithm=TRUE)$modulus)
    ll <- -.5*((n-p)*(log(2*pi*s2)+1)+ldc+ldi)
    if(export) {
      blup <- lambda*crossprod(Z,ci%*%r)
      fitted0 <- X%*%b; fitted1 <- fitted0+Z%*%blup
      all <- list(beta=b,vcov=v*s2,sigma2=s2,tau2=lambda*s2,variance_ratio=lambda,
        loglik=ll,score=score,df_residual=n-p,group_counts=counts,blup=blup,
        fitted_marginal=fitted0,fitted_conditional=fitted1,
        residual_marginal=r,residual_conditional=y-fitted1,
        info_unscaled=info,rhs=crossprod(X,ci%*%y),
        rss_generalized=as.numeric(crossprod(r,ci%*%r)),
        logdet_correlation=ldc,logdet_information=ldi)
      for(k in names(all)) put(paste0('root/',k),all[[k]])
    }
    c(score=score,loglik=ll)
  }
  if(!'A' %in% names(d) && !boundary) {
    # Independent dense-matrix search for the multimodal counterexample.
    grid <- c(0,exp(seq(log(1e-8),log(1e4),length.out=121)))
    scores <- sapply(grid,function(z)profile(z)[1]); roots <- 0
    for(i in seq_len(length(grid)-1)) if(scores[i]*scores[i+1]<0)
      roots <- c(roots,uniroot(function(z)profile(z)[1],grid[c(i,i+1)],tol=1e-12)$root)
    root <- roots[which.max(sapply(roots,function(z)profile(z)[2]))]
  } else root <- if(boundary) 0 else uniroot(function(z)profile(z)[1],c(0,1000),tol=1e-12)$root
  profile(root,export=TRUE)
}
cases <- expand.grid(kind=c('fixed_bal','fixed_unbal','split_bal','split_unbal','block_bal','block_unbal','rm_bal','rm_unbal','reml_bal','reml_unbal','reml_boundary'), seed=c(17,83),stringsAsFactors=FALSE)
cases <- rbind(cases,data.frame(kind='reml_multimodal',seed=9001))
for(ci in seq_len(nrow(cases))) {
  seed <- cases$seed[ci]; kind <- cases$kind[ci]
  vals <- list(); name <- paste(seed,kind,sep='_')
  d <- read.csv(file.path(input,paste0(name,'.csv')),stringsAsFactors=TRUE)
  if(startsWith(kind,'fixed')) {
    m <- lm(y~A*B,d); put('design/X',model.matrix(m)); put_fit(m)
    put_table('I',anova(m)); put_table('II',car::Anova(m,type=2)); put_table('III',car::Anova(m,type=3))
    reverse <- lm(y~B*A,d); put_table('I_reverse',anova(reverse))
    treatment <- lm(y~A*B,d,contrasts=list(A='contr.treatment',B='contr.treatment'))
    put_table('III_treatment',car::Anova(treatment,type=3))
    em <- emmeans::emmeans(m,~A,weights='equal'); et <- as.data.frame(em)
    for(k in c('emmean','SE','df','lower.CL','upper.CL')) put(paste0('emm/',k),et[[k]])
    put('emm/L',em@linfct); put('emm/vcov',vcov(em))
  } else if(startsWith(kind,'split')) put_strata(d,y~A*B,'block/A')
  else if(startsWith(kind,'block')) put_strata(d,y~A,'block')
  else if(startsWith(kind,'rm')) put_strata(d,y~A*B,'subject/B')
  else put_reml(d,kind=='reml_boundary')
  write.csv(data.frame(key=names(vals),value=unlist(vals)),file.path(output,paste0(name,'.csv')),row.names=FALSE,na='NA')
  cat(name, length(vals),'values\n')
}
writeLines(c(R.version.string,sapply(c('car','nlme','emmeans'),function(p)paste(p,packageVersion(p)))),file.path(output,'versions.txt'))
