// BioDSH convergence guard. Long analyses tend to keep exploring until a wall clock ends them (R1: every one of 8
// failures was a timeout, none a wrong answer). Within one turn, at the soft threshold the agent is asked to wrap up
// from what it already has; at the hard threshold, to answer now without tools. Each level fires once per turn. Past
// guardMaxSteps the step is rejected so a runaway turn ends instead of burning tokens.
// Time is the primary signal: a fast model takes ~7 s per step, so step counts tuned on slower models cut verification
// short (2026-10-19 loop: every pilot run hit a 20-step nudge at ~140 s). Step thresholds remain as a backstop.
// Reminders carry their own source kind with form "notice", like the official repeat-tool-reminder, so transcripts show
// them as harness notices rather than as something the user typed. Settings: Host row `biodsh` (lib/settings.js).
import { setting } from './settings.js';

export const name = 'biodsh-step-guard';

const SOURCE = 'biodsh-step-guard';
const SOFT = (step, sec) => `本轮你已经用了 ${step} 步、约 ${sec} 秒。请停止继续探索或尝试新方法/新包，基于目前已经得到的结果，在接下来最多 2 步内给出最终答案。`
  + '如果无法精确计算，就给出你最有把握的近似值并说明依据；题目若要求固定格式（如最后一行 ANSWER: …），务必按格式输出。';
const HARD = (step, sec) => `已用 ${step} 步、约 ${sec} 秒，时间快到了。现在就直接给出最终结论，不要再调用任何工具；`
  + '按题目要求的格式输出最终答案（拿不准就给最佳估计并注明不确定）。';

export function apply(ctx) {
  const get = (k) => setting(ctx, k);
  const dbg = (s) => { if (get('debug') || process.env.BIODSH_GUARD_DEBUG) { try { process.stderr.write(`[biodsh-guard] ${s}\n`); } catch {} } };
  const state = new WeakMap(); // agent -> { turn, t0, soft, hard }
  const notice = (text, summary) => ({ id: globalThis.crypto.randomUUID(), role: 'user', content: [{ type: 'text', text }],
    source: { kind: SOURCE, form: 'notice', summary } });

  ctx.on('agent/pre-step', async (payload, next) => {
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
