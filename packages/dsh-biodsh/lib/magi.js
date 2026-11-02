// BioDSH-MAGI (Multi-Analyst Gated Inspection): in-app form of the independent double analysis evaluated as v18.
//
// After the Analyst's turn on a contracted task, the run's own records decide whether to review it (same rule as the
// evaluation harness, report/continuation_20261028/pilot_v18w/trigger.py): delivery not accepted or repaired, a failed
// source-consistency check, >= magiSteps steps or >= magiSeconds seconds. Mode 'always' reviews every contracted turn.
// A Replicator then solves the same request in a fresh copy of the public inputs, without the Analyst's files, and an
// Arbiter reconciles the two frozen candidates under the v18 instructions (magi_reconcile.md). The delivery gate
// requires the Arbiter's executable checks (reconcile_checks.py) on a clean replay. Only an accepted Arbiter delivery
// replaces the Analyst's submission; the Analyst's original is kept under .biodsh-magi/.
//
// Difference from the evaluation (documented in the paper): the children are in-process dsh subagents under the same
// OS account, in their own directories under .biodsh-magi/, so the Replicator's blindness is by separation of
// directories and sessions, not by an OS namespace. Open requests without a public output contract are not reviewed.
import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

export const ROLE_FILE = '.biodsh-magi-role';
const RECONCILE = fileURLToPath(new URL('./magi_reconcile.md', import.meta.url));
const COMPARE = fileURLToPath(new URL('./magi_compare.py', import.meta.url));

export function roleOf(root) {
  try { return fs.readFileSync(path.join(root, ROLE_FILE), 'utf8').trim(); } catch { return null; }
}

/** The v18 trigger rule on the Analyst's own delivery records (no grades, no model confidence). */
export function triggerReasons(root, receipt, { steps = 0, seconds = 0, stepLimit = 60, secondLimit = 900 } = {}) {
  const reasons = [];
  if (!receipt) reasons.push('no_delivery_receipt');
  else {
    if (receipt.status !== 'accepted') reasons.push('delivery_' + receipt.status);
    if ((receipt.repairs || 0) > 0) reasons.push('delivery_repairs_' + receipt.repairs);
  }
  try {
    for (const line of fs.readFileSync(path.join(root, '.biodsh-delivery-events.jsonl'), 'utf8').split('\n')) {
      if (!line.trim()) continue;
      const e = JSON.parse(line);
      if (e.semantic && e.semantic.ok === false) { reasons.push('semantic_check_failed'); break; }
    }
  } catch {}
  if (steps >= stepLimit) reasons.push(`long_run_${steps}_steps`);
  if (seconds >= secondLimit) reasons.push(`long_run_${Math.round(seconds)}s`);
  return [...new Set(reasons)].sort();
}

/** Copy the public task material (everything except outputs, harness state and VCS) into dest. */
export function copyPublic(root, dest) {
  const skip = n => n.startsWith('.biodsh') || ['submission', '.git', 'node_modules', '__pycache__'].includes(n);
  const visit = (dir, out) => {
    fs.mkdirSync(out, { recursive: true });
    for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
      if (skip(ent.name) || ent.isSymbolicLink()) continue;
      const src = path.join(dir, ent.name), dst = path.join(out, ent.name);
      if (ent.isDirectory()) visit(src, dst); else if (ent.isFile()) fs.copyFileSync(src, dst);
    }
  };
  visit(root, dest);
}

function copyTree(src, dst) { if (fs.existsSync(src)) fs.cpSync(src, dst, { recursive: true }); }

function compare(python, args, contract, left, right, out) {
  return new Promise(resolve => {
    const child = spawn(python, [...args, COMPARE, contract, left, right, out], { windowsHide: true, stdio: 'ignore' });
    child.on('error', () => resolve(false)); child.on('close', c => resolve(c === 0));
  });
}

async function child(ctx, parent, { cwd, prompt, label, signal }) {
  const subagents = ctx.get?.('subagents') || ctx.subagents;
  if (!subagents?.startActivation) throw new Error('MAGI needs the dsh subagent service with the spawn provider');
  const activation = await subagents.startActivation({ provider: 'spawn', label, signal, delivery: 'caller',
    request: { cwd, prompt: [{ type: 'text', text: prompt }], parent, maxDepth: 1 } });  // depth 1 = direct children only
  try { return await activation.result; } finally { await activation.dispose?.().catch(() => {}); }
}

const readJson = p => { try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch { return null; } };

/**
 * Run the Replicator and Arbiter for one Analyst turn. Returns a report; never throws for a review that fails
 * (the Analyst's delivery then stands). `prompt` is the user's request for this turn.
 */
export async function runMagi(ctx, agent, { root, prompt, reasons, python, pythonArgs = [], signal, log = () => {} }) {
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  // Children inherit the parent's permission roots, so their workspaces live under the user's folder
  // (.biodsh-magi/<stamp>/), which the Analyst's public-file copy skips.
  const keep = path.join(root, '.biodsh-magi', stamp), base = keep;
  const report = { started_at: new Date().toISOString(), reasons, temp: base, status: 'running' };
  const save = () => { fs.mkdirSync(keep, { recursive: true }); fs.writeFileSync(path.join(keep, 'report.json'), JSON.stringify(report, null, 2)); };
  save();
  try {
    const rep = path.join(base, 'replicator');
    copyPublic(root, rep); fs.writeFileSync(path.join(rep, ROLE_FILE), 'replicator');
    log('MAGI 2/3: replicator'); report.replicator = { cwd: rep };
    await child(ctx, agent, { cwd: rep, prompt, label: 'BioDSH-MAGI replicator', signal });
    report.replicator.delivery = readJson(path.join(rep, '.biodsh-delivery.json'))?.status ?? null; save();

    const arb = path.join(base, 'arbiter');
    copyPublic(root, arb); fs.writeFileSync(path.join(arb, ROLE_FILE), 'arbiter');
    copyTree(path.join(root, 'submission'), path.join(arb, '.biodsh-candidates/primary/submission'));
    copyTree(path.join(rep, 'submission'), path.join(arb, '.biodsh-candidates/blind/submission'));
    copyTree(path.join(root, 'submission'), path.join(arb, 'submission'));
    for (const [from, label] of [[root, 'primary'], [rep, 'blind']]) {
      const plan = path.join(from, '.biodsh-semantic-plan.json');
      if (fs.existsSync(plan)) fs.copyFileSync(plan, path.join(arb, '.biodsh-candidates', label, 'semantic-plan.json'));
    }
    if (fs.existsSync(path.join(root, '.biodsh-semantic-plan.json'))) fs.copyFileSync(path.join(root, '.biodsh-semantic-plan.json'), path.join(arb, '.biodsh-semantic-plan.json'));
    if (fs.existsSync(path.join(arb, 'TABLE_CONTRACT.json')))
      await compare(python, pythonArgs, path.join(arb, 'TABLE_CONTRACT.json'), path.join(arb, '.biodsh-candidates/primary/submission'),
                    path.join(arb, '.biodsh-candidates/blind/submission'), path.join(arb, '.biodsh-candidates/comparison.json'));
    const arbPrompt = prompt + '\n\n' + fs.readFileSync(RECONCILE, 'utf8');
    log('MAGI 3/3: arbiter'); report.arbiter = { cwd: arb };
    await child(ctx, agent, { cwd: arb, prompt: arbPrompt, label: 'BioDSH-MAGI arbiter', signal });
    const gate = readJson(path.join(arb, '.biodsh-delivery.json'));
    report.arbiter.delivery = gate?.status ?? null;
    report.arbiter.reconcile_checks = gate?.reconcile_checks ? { ok: gate.reconcile_checks.ok, checks: gate.reconcile_checks.checks } : null;
    if (gate?.status === 'accepted') {
      // Move (never delete) the Analyst's delivery aside, then place the Arbiter's.
      if (fs.existsSync(path.join(root, 'submission'))) fs.renameSync(path.join(root, 'submission'), path.join(keep, 'analyst-submission'));
      copyTree(path.join(arb, 'submission'), path.join(root, 'submission'));
      report.status = 'arbiter_delivery_adopted';
    } else report.status = 'arbiter_not_accepted_analyst_kept';
  } catch (e) {
    if (signal?.aborted) { report.status = 'cancelled'; save(); throw e; }
    report.status = 'review_failed_analyst_kept'; report.error = String(e?.message || e);
  }
  report.ended_at = new Date().toISOString(); save();
  return report;
}
