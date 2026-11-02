// Verification-first convergence notices; thresholds remain configurable.
import { setting } from './settings.js';
import { workspaceRoot } from './task_policy.js';
import { roleOf } from './magi.js';

// The MAGI arbiter reconciles two finished candidates: v18 evaluated it with a tighter budget (45/800 s, 60/1000 s, max 70).
const ARBITER = { guardSoftSteps: 45, guardSoftSeconds: 800, guardHardSteps: 60, guardHardSeconds: 1000, guardMaxSteps: 70 };

export const name = 'biodsh-step-guard';

const SOURCE = 'biodsh-step-guard';
const SOFT = (step, sec) => `本轮已用 ${step} 步、约 ${sec} 秒。优先保存完整代码，集中处理必要核验和已发现的问题，跑完核验再收尾。`
  + '遵循公开方法和输出规范；不能用近似值满足精确合同。开放问答按要求输出末行 ANSWER，数值科学计数使用 ASCII e，保留题面要求的比例或百分比。';
const HARD = (step, sec) => `本轮已用 ${step} 步、约 ${sec} 秒，剩余预算有限。先保存代码和已有结果，优先完成关键核验。`
  + '无法在预算内完成时如实报告未完成的部分与失败检查；不要猜数、跳过合同或宣称尚未完成的验证通过。';

export function apply(ctx) {
  const base = (k) => setting(ctx, k);
  const get = base;
  const roles = new WeakMap();
  const dbg = (s) => { if (get('debug') || process.env.BIODSH_GUARD_DEBUG) { try { process.stderr.write(`[biodsh-guard] ${s}\n`); } catch {} } };
  const state = new WeakMap(); // agent -> { turn, t0, soft, hard }
  const notice = (text, summary) => ({ id: globalThis.crypto.randomUUID(), role: 'user', content: [{ type: 'text', text }],
    source: { kind: SOURCE, form: 'notice', summary } });

  ctx.on('agent/pre-step', async (payload, next) => {
    if (payload?.agent && !roles.has(payload.agent)) roles.set(payload.agent, roleOf(workspaceRoot(ctx, payload.agent) || '.'));
    const role = payload?.agent ? roles.get(payload.agent) : null;
    const get = (k) => (role === 'arbiter' && k in ARBITER) ? ARBITER[k] : base(k);
    if (!get('guardEnabled')) return next();
    const step = Number(payload?.step) || 0;
    const max = get('guardMaxSteps');
    if (max > 0 && step > max) {
      dbg(`turn ${payload.turn}: step ${step} > ${max}, rejecting`);
      return { kind: 'reject' };
    }
    const decision = await next();
    try {
      if (!decision || decision.kind !== 'enter' || !payload?.agent) return decision;
      let st = state.get(payload.agent);
      if (!st || st.turn !== payload.turn) { st = { turn: payload.turn, t0: Date.now(), soft: false, hard: false }; state.set(payload.agent, st); }
      const sec = Math.round((Date.now() - st.t0) / 1000);
      let m = null;
      if (!st.hard && (step >= get('guardHardSteps') || sec >= get('guardHardSeconds'))) { st.hard = st.soft = true; m = notice(HARD(step, sec), `final answer now (${step} steps, ${sec}s)`); }
      else if (!st.soft && (step >= get('guardSoftSteps') || sec >= get('guardSoftSeconds'))) { st.soft = true; m = notice(SOFT(step, sec), `wrap up (${step} steps, ${sec}s)`); }
      if (!m) return decision;
      dbg(`turn ${payload.turn} step ${step} ${sec}s -> ${st.hard ? 'hard' : 'soft'}`);
      return { ...decision, messages: [...(decision.messages || []), m] };
    } catch (e) { dbg('error ' + (e?.message || e)); return decision; }
  });
}
