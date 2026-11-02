// Deployment-only accounting around every native model stream, including selector and title calls.
// No prompts, outputs, headers, or credentials are recorded. Missing usage remains missing.
import fs from 'node:fs';
import { randomUUID } from 'node:crypto';
import { spawn } from 'node:child_process';
export function admission(script, signal) {
  const windows=process.platform==='win32';
  return new Promise((resolve,reject)=>{
    const child=spawn(windows?'wsl.exe':'bash',windows?['--exec','bash',script]:[script],{signal,windowsHide:true,stdio:'ignore'});
    child.on('error',reject);child.on('close',c=>c===0?resolve():reject(new Error('model-request admission failed')));
  });
}
export function registerRequestMeter(ctx, {file=process.env.BIODSH_USAGE_FILE,script=process.env.BIODSH_ADMISSION_SCRIPT,admit=admission}={}) {
  if(!file)return;
  const record=r=>fs.appendFileSync(file,JSON.stringify(r)+'\n');
  ctx.on('llm/stream',async function*(options,next){
    const id=randomUUID(),start=Date.now();let usage=null,finish=null,error=null,admitted=false;
    record({event:'start',id,at:start,provider:options.provider,model:options.model});
    try {
      if(script)await admit(script,options.signal);
      admitted=true;record({event:'admitted',id,at:Date.now()});
      for await(const chunk of next()) {
        if(chunk.type==='usage')usage=chunk.usage;
        if(chunk.type==='finish')finish=chunk.reason?.kind || 'unknown';
        yield chunk;
      }
    } catch(e) {
      error={name:e?.name,code:e?.code,status:e?.status};throw e;
    } finally {
      record({event:'end',id,at:Date.now(),seconds:(Date.now()-start)/1000,admitted,usage,finish,error});
    }
  });
}
