import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { setting } from './settings.js';
import { CONTRACT_FILES, workspaceRoot } from './task_policy.js';
import { snapshotPublicSources, observePlan, SEMANTIC_INSTRUCTIONS } from './semantic_plan.js';
import {reviewCoverage} from './coverage_review.js';
import { roleOf, triggerReasons, runMagi } from './magi.js';
export const name = 'biodsh-delivery';
export const inject = ['llm'];
export function toLinux(p) {
  return String(p).replace(/^([a-z]):[\\/]/i, (_,d)=>`/mnt/${d.toLowerCase()}/`).replace(/\\/g,'/');
}
export function snapshotContracts(root) {
  const docs={};
  for (const n of CONTRACT_FILES) {
    const p=path.join(root,n);
    if (fs.existsSync(p)) docs[n]=JSON.parse(fs.readFileSync(p,'utf8').replace(/^\uFEFF/,''));
  }
  return docs;
}
export function checkDelivery(root, docs, config, signal) {
  const isWsl = process.platform === 'win32' && /(?:^|[\\/])wsl(?:\.exe)?$/i.test(config.python);
  const convert = isWsl ? toLinux : x=>x;
  const script = fileURLToPath(new URL('./delivery_check.py',import.meta.url));
  const args = [...config.args, convert(script), '--public', convert(root), '--snapshot-stdin', '--seconds', String(config.seconds), ...(config.reconcileChecks ? ['--reconcile-checks'] : [])];
  return new Promise((resolve,reject)=> {
    const child=spawn(config.python,args,{cwd:root,windowsHide:true,signal,stdio:['pipe','pipe','pipe']});
    let stdout='',stderr='';
    const timer=setTimeout(()=>child.kill(),(config.seconds+90)*1000);
    child.stdout.on('data',b=>{stdout+=b; if(stdout.length>8*1024*1024)child.kill();});
    child.stderr.on('data',b=>{stderr=(stderr+b).slice(-3000);});
    child.on('error',e=>{clearTimeout(timer);reject(e);});
    child.stdin.on('error',()=>{});
    child.on('close',code=>{clearTimeout(timer);try{const result=JSON.parse(stdout);resolve({...result,ok:code===0 && result.ok});}
      catch {reject(new Error(`delivery validator exit ${code}: ${stderr}`));}});
    child.stdin.end(JSON.stringify(config.semantic ? {__biodsh_snapshot_version:14,contracts:docs,semantic:config.semantic} : docs));
  });
}
// Exported controller lets offline tests exercise the real turn-stopping callback without an LLM.
export function registerDelivery(ctx, get, check=checkDelivery) {
  const states=new WeakMap();
  // BioDSH-MAGI needs the user's request of the turn: the latest user-authored message (source kind 'user' or none).
  const prompts=new Map();
  ctx.on?.('session/event',(session,event)=>{
    if(event?.type!=='user/message' || (event.data?.source && event.data.source.kind!=='user'))return;
    const text=(event.data?.content||[]).filter(c=>c.type==='text').map(c=>c.text).join('\n');
    if(text)prompts.set(session?.id??session?.header?.id,text);
  });
  ctx.on('agent/pre-step',async(payload,next)=>{
    const roots=ctx.get?.('agents')?.roots?.();
    // Child agents are skipped, except BioDSH-MAGI's Replicator and Arbiter (marked by a role file in their workspace).
    if (roots && !roots.includes(payload?.agent) && !roleOf(workspaceRoot(ctx,payload?.agent) || '.')) return next();
    if (get('deliveryEnabled') && payload?.agent) {
      const previous=states.get(payload.agent);
      if (!previous || previous.turn!==payload.turn) {
        const root=workspaceRoot(ctx,payload.agent);
        if (root) {
          let docs={},error=null;try{docs=snapshotContracts(root);}catch(e){error=String(e);}
          const semantic=get('semanticEnabled') && Object.keys(docs).length ? snapshotPublicSources(root) : null;
          states.set(payload.agent,{turn:payload.turn,root,docs,error,semantic,repairs:0,steps:0,t0:Date.now(),role:roleOf(root)});
          if(semantic?.applicable || (semantic && get('coverageReviewEnabled')))payload.agent.inject({id:randomUUID(),role:'user',content:[{type:'text',text:SEMANTIC_INSTRUCTIONS}],source:{kind:'biodsh-semantic-plan',form:'notice',summary:'declare public source consistency checks'}});
        }
      }
      const st=states.get(payload.agent);
      if(st?.semantic?.applicable)observePlan(st.root,st.semantic,'pre-step:'+st.steps++);
    }
    return next();
  });
  ctx.on('agent/turn-stopping',async({agent,turn,signal})=>{
    if (!get('deliveryEnabled')) return;
    const st=states.get(agent);
    if (!st || st.turn!==turn || (!st.error && !Object.keys(st.docs).length))return;
    let result;
    try {
      if(st.error)throw new Error(st.error);
      if(st.semantic?.error)throw new Error(st.semantic.error);
      if(st.semantic?.applicable)observePlan(st.root,st.semantic,'turn-stopping');
      result=await check(st.root,st.docs,{python:get('deliveryPython') || process.env.BIODSH_PYTHON || 'python3',
        args:get('deliveryPythonArgs') || [],seconds:get('deliveryReplaySeconds'),reconcileChecks:get('reconcileChecks') || st.role==='arbiter',semantic:st.semantic?.applicable ? st.semantic : null},signal);
      if(result.ok && st.semantic && get('coverageReviewEnabled')){
        result.coverage_review=await reviewCoverage(ctx,agent,st.root,st.docs,st.semantic,result,{python:get('deliveryPython')||process.env.BIODSH_PYTHON||'python3',args:get('deliveryPythonArgs')||[]},signal);
        if(!result.coverage_review.ok){result.ok=false;result.errors.push('Independent public-contract coverage review requires repair: '+JSON.stringify({issues:result.coverage_review.issues,uncertain_columns:result.coverage_review.uncertain_columns,error:result.coverage_review.error}));}
      }
    } catch(e) {
      if(signal?.aborted)throw e;
      result={ok:false,errors:[String(e)],infrastructureError:true};
    }
    const reviewError=Boolean(result.coverage_review?.error);
    if(reviewError)result.infrastructureError=true;
    const exhausted=!result.ok && (reviewError || st.repairs>=get('deliveryMaxRepairs'));
    const receipt={...result,turn,recorded_at:new Date().toISOString(),repairs:st.repairs,semantic_applicable:st.semantic?.applicable ?? false,semantic_source_manifest:st.semantic?.public_files ?? {},semantic_plan_history:st.semantic?.plan_history ?? [],status:result.ok?'accepted':exhausted?'rejected':'repair-required'};
    fs.appendFileSync(path.join(st.root,'.biodsh-delivery-events.jsonl'),JSON.stringify(receipt)+'\n');
    fs.writeFileSync(path.join(st.root,'.biodsh-delivery.json'),JSON.stringify(receipt,null,2));
    // BioDSH-MAGI: once the Analyst's delivery is final (accepted or rejected), review it if its own records show risk.
    const mode=get('magiMode');
    if(mode && mode!=='off' && !st.role && (result.ok || exhausted)) {
      const reasons=mode==='always' ? ['always'] : triggerReasons(st.root,receipt,{steps:st.steps,seconds:(Date.now()-st.t0)/1000,stepLimit:get('magiSteps'),secondLimit:get('magiSeconds')});
      const prompt=prompts.get(agent?.session?.header?.id);
      if(reasons.length && prompt) {
        const report=await runMagi(ctx,agent,{root:st.root,prompt,reasons,python:get('deliveryPython') || process.env.BIODSH_PYTHON || 'python3',pythonArgs:get('deliveryPythonArgs') || [],signal});
        if(report.status==='arbiter_delivery_adopted')return;
      }
    }
    if(result.ok)return;
    if(exhausted)throw new Error('BIODSH_DELIVERY_REJECTED: public contract/replay check failed; repair limit reached');
    st.repairs++;
    const feedback=result.coverage_review ? {...result,coverage_review:{ok:result.coverage_review.ok,issues:result.coverage_review.issues,uncertain_columns:result.coverage_review.uncertain_columns,error:result.coverage_review.error,required_columns:result.coverage_review.required_columns,reviewed_columns:result.coverage_review.reviewed_columns}} : result;
    // A deterministic tool-result notice. Do not fabricate a tool-call ID absent from the transcript.
    agent.inject({id:randomUUID(),role:'user',content:[{type:'text',text:
      'Delivery validator result: '+JSON.stringify(feedback)+'\nDelivery is blocked. Fix these public-contract/source-consistency/replay errors, save the code and rerun before finishing. Do not alter the contracts or source inputs. Repair round '+st.repairs+'/'+get('deliveryMaxRepairs')+'.'}],
      source:{kind:'biodsh-delivery',form:'notice',summary:'deterministic delivery validation failed'}});
  });
}
export function apply(ctx) { registerDelivery(ctx,k=>setting(ctx,k)); }
