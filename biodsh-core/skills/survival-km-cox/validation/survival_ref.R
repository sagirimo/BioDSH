# R references; input/output only in caller-specified directory. No package install.
if (nzchar(Sys.getenv('R_LIMMA_LIB'))) .libPaths(c(Sys.getenv('R_LIMMA_LIB'), .libPaths()))
suppressMessages(library(survival))
suppressMessages(library(survRM2))
args <- commandArgs(TRUE); root <- args[1]
options(digits=17)
cat(R.version.string, '\nsurvival', as.character(packageVersion('survival')), '\nsurvRM2',as.character(packageVersion('survRM2')),'\n')
for (seed in c('20261020','20261021','edge')) {
 d <- read.csv(file.path(root,if(seed=='edge') 'edge.csv' else paste0('data_',seed,'.csv')))
 values <- list()
 put <- function(key,x) { values[[key]] <<- as.numeric(x) }
 kmout <- function(pre,t,e) {
  for (ct in c('log','log-log')) {
   f <- survfit(Surv(t,e)~1,conf.type=ct,timefix=FALSE)
   p <- paste0(pre,'.',ct,'.')
   for(nm in c('time','n.risk','n.event','n.censor','surv','std.err','lower','upper')) put(paste0(p,nm),f[[nm]])
   gw <- cumsum(f$n.event/(f$n.risk*(f$n.risk-f$n.event)))
   put(paste0(p,'greenwood'),gw); put(paste0(p,'variance'),f$surv^2*gw)
   put(paste0(p,'se'),summary(f,censored=TRUE)$std.err)
  }
 }
 kmout('km',d$time,d$status)
 tau <- if(seed=='edge') 3 else 10
 td <- pmin(d$time,tau); ed <- d$status*(d$time<=tau)
 put('admin.time',td); put('admin.status',ed); kmout('admin.km',td,ed)
 for (k in 0:1) {
  a <- d[d$group==k,]; f <- survRM2:::rmst1(a$time,a$status,tau)
  p <- paste0('rmst.',k,'.'); put(paste0(p,'summary'),c(f$rmst,f$rmst.var,f$rmtl[1],tau))
  sf <- f$fit; ix <- sf$time<=tau
  tt <- sf$time[ix]; widths <- diff(c(0,tt,tau)); areas <- widths*c(1,sf$surv[ix]); tail <- rev(cumsum(rev(areas[-1])))
  inc <- ifelse(sf$n.risk[ix]==sf$n.event[ix],0,sf$n.event[ix]/(sf$n.risk[ix]*(sf$n.risk[ix]-sf$n.event[ix])))
  for (nm in c('tt','widths','areas','tail','inc')) put(paste0(p,nm),get(nm))
  put(paste0(p,'contrib'),tail^2*inc)
 }
 rr <- rmst2(d$time,d$status,d$group,tau=tau)
 put('rmst.diff',rr$unadjusted.result[1,])
 rv <- rr$RMST.arm1$rmst.var+rr$RMST.arm0$rmst.var
 put('rmst.diff_details',c(rv,sqrt(rv),rr$unadjusted.result[1,1]/sqrt(rv)))
 lrout <- function(pre,a,strat=FALSE) {
  # survival 3.8.6 passes explicit timefix into model.frame; use its default
  # after verifying that fuzzy-time repair leaves these simulated times unchanged.
  yy <- Surv(a$time,a$status); stopifnot(identical(yy,survival::aeqSurv(yy)))
  f <- if(strat) survdiff(Surv(time,status)~group+strata(stratum),a) else survdiff(Surv(time,status)~group,a)
  for(nm in c('obs','exp','var','chisq')) put(paste0(pre,'.',nm),f[[nm]])
  df <- sum(if(is.matrix(f$exp)) rowSums(f$exp)>0 else f$exp>0)-1
  put(paste0(pre,'.df'),df); put(paste0(pre,'.p'),pchisq(f$chisq,df,lower.tail=FALSE))
 }
 lrout('lr',d)
 if(seed=='edge') {
  kmout('allcensored',c(0,1,1,3),c(0,0,0,0))
  kmout('allzero',c(0,0,0),c(1,1,1))
  term <- survRM2:::rmst1(d$time,d$status,4)
  put('terminal.rmst',c(term$rmst,term$rmst.var))
  next
 }
 d3 <- d; d3$group <- d3$cluster %% 3
 lrout('lr.three',d3); lrout('lr.three.strata',d3,TRUE)
 lrout('lr.strata',d,TRUE)
 for(ti in c('breslow','efron')) {
  dz <- d; dz$status[dz$stratum==2] <- 0
  fz <- coxph(Surv(time,status)~group+x+strata(stratum),dz,ties=ti,nocenter=NULL,control=coxph.control(eps=1e-12,toler.chol=1e-14,timefix=FALSE))
  put(paste0('zeroevent.',ti,'.beta'),coef(fz)); put(paste0('zeroevent.',ti,'.cov'),fz$var)
  fs <- coxph(Surv(time,status)~x,d,ties=ti,nocenter=NULL,control=coxph.control(eps=1e-12,toler.chol=1e-14,timefix=FALSE))
  put(paste0('single.',ti,'.beta'),coef(fs)); put(paste0('single.',ti,'.cov'),fs$var)
 }

 for(s in sort(unique(d$stratum))) lrout(paste0('lr.stratum',s),d[d$stratum==s,])
 for(ties in c('breslow','efron')) for(st in c(FALSE,TRUE)) for(cl in c(FALSE,TRUE)) {
  pre <- paste('cox',ties,as.integer(st),as.integer(cl),sep='.')
  form <- if(st) Surv(time,status)~group+x+strata(stratum) else Surv(time,status)~group+x
  ctrl <- coxph.control(eps=1e-12,toler.chol=1e-14,iter.max=60,timefix=FALSE)
  fit <- if(cl) coxph(form,d,ties=ties,cluster=cluster,x=TRUE,y=TRUE,model=TRUE,control=ctrl,nocenter=NULL) else coxph(form,d,ties=ties,x=TRUE,y=TRUE,model=TRUE,control=ctrl,nocenter=NULL)
  sm <- summary(fit); mc <- if(cl) fit$naive.var else fit$var
  sr <- residuals(fit,type='score'); cs <- rowsum(sr,d$cluster,reorder=TRUE)
  put(paste0(pre,'.beta'),coef(fit)); put(paste0(pre,'.cov'),fit$var); put(paste0(pre,'.model_cov'),mc)
  put(paste0(pre,'.info'),solve(mc)); put(paste0(pre,'.score_residuals'),sr); put(paste0(pre,'.score'),colSums(sr))
  put(paste0(pre,'.se'),sqrt(diag(fit$var))); put(paste0(pre,'.z'),coef(fit)/sqrt(diag(fit$var)))
  put(paste0(pre,'.p'),sm$coefficients[,ncol(sm$coefficients)])
  put(paste0(pre,'.hr'),exp(coef(fit))); put(paste0(pre,'.coef_lower'),coef(fit)-qnorm(.975)*sqrt(diag(fit$var)))
  put(paste0(pre,'.coef_upper'),coef(fit)+qnorm(.975)*sqrt(diag(fit$var)))
  put(paste0(pre,'.loglik'),fit$loglik); put(paste0(pre,'.reference'),fit$means)
  put(paste0(pre,'.n'),c(fit$n,fit$nevent))
  put(paste0(pre,'.wald'),c(fit$wald.test,2,pchisq(fit$wald.test,2,lower.tail=FALSE))) # summary rounds only the displayed statistic
  put(paste0(pre,'.score_test'),sm$sctest); put(paste0(pre,'.lr'),sm$logtest)
  if(cl) {put(paste0(pre,'.cluster_scores'),cs); put(paste0(pre,'.meat'),crossprod(cs)); put(paste0(pre,'.robust_score'),sm$robscore)}
  null <- coxph(form,d,ties=ties,init=c(0,0),control=coxph.control(iter.max=0,timefix=FALSE),x=TRUE,y=TRUE,nocenter=NULL)
  put(paste0(pre,'.null_score'),colSums(residuals(null,type='score'))); put(paste0(pre,'.null_info'),solve(null$var))
  detailout <- function(f,p) {
   dd <- coxph.detail(f)
   for(nm in c('time','nevent','nrisk','means','score','imat','hazard','wtrisk')) put(paste0(p,'.',nm),dd[[nm]])
   # Additional risk-set intermediates independently computed from R fit$coef.
   xc <- sweep(as.matrix(d[,c('group','x')]),2,f$means)
   eta <- as.vector(xc %*% coef(f)); risk <- exp(eta)
   pertime <- list()
   for(sid in if(st) 0:2 else 0) {
    select <- if(st) d$stratum==sid else rep(TRUE,nrow(d))
    for(tt in sort(unique(d$time[select & d$status==1]))) {
     rr <- select & d$time>=tt; ev <- select & d$time==tt & d$status==1
     ne <- sum(ev); r0 <- sum(risk[rr]); e0 <- sum(risk[ev])
     frac <- if(ties=='efron') (0:(ne-1))/ne else rep(0,ne)
     pertime[[length(pertime)+1]] <- c(death_risk_sum=e0,loglik=sum(eta[ev])-sum(log(r0-frac*e0)),hazard_breslow=ne/r0)
    }
   }
   vv <- do.call(rbind,pertime)
   for(nm in colnames(vv)) put(paste0(p,'.',nm),vv[,nm])
  }
  detailout(fit,paste0(pre,'.detail'))
  fixed <- coxph(form,d,ties=ties,init=c(.23,-.17),control=coxph.control(iter.max=0,timefix=FALSE),x=TRUE,y=TRUE,nocenter=NULL)
  detailout(fixed,paste0(pre,'.fixed'))
  put(paste0(pre,'.fixed.loglik'),fixed$loglik[2]); put(paste0(pre,'.fixed.residuals'),residuals(fixed,type='score'))
  bh <- basehaz(fit,centered=TRUE); put(paste0(pre,'.basehaz'),bh$hazard); put(paste0(pre,'.basetime'),bh$time)
  bh0 <- basehaz(fit,centered=FALSE); put(paste0(pre,'.basehaz0'),bh0$hazard)
  # Breslow baseline after any tie-method fit, and predictions for both ctypes.
  for(ctype in 1:2) {
   for(s in if(st) 0:2 else 0) {
    nd <- data.frame(group=0.4,x=-.2,stratum=s)
    sf <- survfit(fit,newdata=nd,ctype=ctype,se.fit=FALSE)
    put(paste0(pre,'.prediction.',ctype,'.',s),summary(sf,times=c(0,1,3,7,10),extend=TRUE)$surv)
   }
  }
 }
 # Persist a long-form full precision reference table, including non-finite values.
 out <- do.call(rbind,lapply(names(values),function(k) data.frame(key=k,index=seq_along(values[[k]]),value=values[[k]])))
 write.table(out,file.path(root,paste0('r_',seed,'.csv')),sep=',',row.names=FALSE,na='NaN')
}
# edge loop's next deliberately skips Cox; write its accumulated results here.
out <- do.call(rbind,lapply(names(values),function(k) data.frame(key=k,index=seq_along(values[[k]]),value=values[[k]])))
write.table(out,file.path(root,'r_edge.csv'),sep=',',row.names=FALSE,na='NaN')
if(length(warnings())) print(warnings())
