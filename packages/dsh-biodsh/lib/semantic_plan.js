import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';

export const PLAN_NAME = '.biodsh-semantic-plan.json';
export const SEMANTIC_INSTRUCTIONS = `v16: Deterministic public-source and clean replay checks are enabled. Before implementation, map output fields to their exact public definitions, source/formula, scope, units and missing-value rules. For every evidence statement distinguish a measured negative from missing measurement, lack of relevant source coverage, and unsupported external claims. Evaluate the stated proposition against actual inputs; neither a field name nor successful code execution establishes its scientific meaning. Inspect numerical diagnostics for numerical claims. Do not substitute a convenient proxy for a defined status. These are general principles, not task-specific answer rules. Model uncertainty alone is not a deterministic failure. Independent stages, if supplied later by the supervisor, are candidates rather than reference answers.
For tasks without original CSV/TSV inputs no executable source-rule plan is required. When original CSV/TSV inputs exist, read the public definitions and, before implementing the analysis, save .biodsh-semantic-plan.json in the workspace root. This is a partial executable interpretation, not proof of scientific correctness. Do not claim untested columns are verified.
Schema: {"version":1,"rules":[{"id":"unique-name","operation":"aggregate|preserve|predicate","source":"inputs/original.csv","target":"declared-output.csv","target_column":"column","keys":[["target_key","source_key"]],"citation":{"path":"prompt.md","quote":"exact public definition of at least 8 characters"}}],"unverified":["columns or methods not expressible and why"]}.
Use unchanged ORIGINAL public CSV/TSV inputs, never generated intermediates. Match raw string identities. Each target key must be unique. For aggregate rules add "aggregate":{"kind":"count_rows|count_distinct|sum|mean|ratio"}; count_distinct/sum/mean require "column"; ratio requires nested "numerator" and "denominator" aggregate objects. Aggregates may have "where" predicates and explicit "skip_missing":true. A rule-level "where" filters the source cohort before grouping. For preserve rules add "source_column"; for predicate rules add "predicate". Both require exactly one source row per target identity.
Predicate grammar: {"column":"name","op":"eq|ne|in|lt|le|gt|ge|is_missing|is_present","value":...}, or {"all":[predicates]}, {"any":[predicates]}, {"not":predicate}. Missing tokens default to [""]; override with "missing_tokens" only if the public definition requires it. Counts are compared exactly; other numbers use fixed rtol=1e-9/atol=1e-12. No literal expected answer, eval, arbitrary expressions, model-selected tolerance or private answers. Unsupported methods belong in unverified. At least one meaningful rule is required when applicable. Cite the actual public definition, not an invented interpretation. Plan revisions are retained and are not independent validation. After a failed check, repair the analysis against the public definition, not just the plan to fit its output.`;

function digest(file) {
  const fd=fs.openSync(file,'r'), hash=createHash('sha256'), buffer=Buffer.alloc(1024*1024);
  try { let n; while((n=fs.readSync(fd,buffer,0,buffer.length,null)))hash.update(buffer.subarray(0,n)); }
  finally {fs.closeSync(fd);}
  return hash.digest('hex');
}

// The caller must supply a fresh public-only workspace. This is integrity checking,
// not an OS read sandbox and not a private-answer leakage detector.
export function snapshotPublicSources(root) {
  const state={public_files:{},plan:null,plan_history:[],applicable:false,error:null};
  function visit(dir) {
    for(const ent of fs.readdirSync(dir,{withFileTypes:true})) {
      if(ent.name.startsWith('.biodsh') || ['submission','.git','node_modules'].includes(ent.name))continue;
      const file=path.join(dir,ent.name), rel=path.relative(root,file).split(path.sep).join('/');
      if(ent.isSymbolicLink())throw new Error('public source symlink unsupported: '+rel);
      if(ent.isDirectory())visit(file);
      else if(ent.isFile()) {state.public_files[rel]=digest(file);if(/\.(csv|tsv)$/i.test(rel))state.applicable=true;}
    }
  }
  try {visit(root);}catch(e){state.error=String(e);state.applicable=true;}
  return state;
}

export function observePlan(root,state,phase) {
  const file=path.join(root,PLAN_NAME);
  if(!fs.existsSync(file)){state.plan=null;return;}
  try {
    if(fs.lstatSync(file).isSymbolicLink())throw new Error('semantic plan symlink unsupported');
    if(fs.statSync(file).size>512*1024)throw new Error('semantic plan exceeds 512 KiB');
    const raw=fs.readFileSync(file,'utf8'),sha256=createHash('sha256').update(raw).digest('hex');
    const plan=JSON.parse(raw.replace(/^\uFEFF/,''));
    if(state.plan_history.at(-1)?.sha256!==sha256)state.plan_history.push({sha256,phase,submission_present:fs.existsSync(path.join(root,'submission')),plan});
    state.plan=plan;state.plan_error=null;
  }catch(e){state.plan=null;state.plan_error=String(e);}
}
