// BioDSH 收敛护栏(治"跑飞")—— cordis 插件,走 dsh 官方扩展点 agent/pre-step,不改 dsh 代码。
// 问题:难题上 agent 会一直探索/换方法直到撞时间墙(R1 实测:8 个失败全是 400s 超时,0 个算错)。
// 做法:每步看"本轮已用步数 / 已用秒数",到软阈值追加一条"请收尾"的用户消息,到硬阈值追加"必须现在作答";
//       每级每轮只提醒一次。消息通过 pre-step 的 enter 决定追加进本步 messages(确定性生效,不依赖 inject 时机)。
// 阈值(可用环境变量覆盖,默认按实测:成功的题 3–15 步/≤200s,跑飞的 10–25 步撞 400s):
//   BIODSH_GUARD_SOFT_STEPS=8  BIODSH_GUARD_SOFT_SEC=150  BIODSH_GUARD_HARD_STEPS=12  BIODSH_GUARD_HARD_SEC=240
//   BIODSH_GUARD_DEBUG=1 打日志;BIODSH_GUARD_OFF=1 关闭。
export const name = 'biodsh-step-guard';

const num = (k, d) => { const v = Number(process.env[k]); return Number.isFinite(v) && v > 0 ? v : d; };
const SOFT_STEPS = () => num('BIODSH_GUARD_SOFT_STEPS', 8);
const SOFT_SEC = () => num('BIODSH_GUARD_SOFT_SEC', 150);
const HARD_STEPS = () => num('BIODSH_GUARD_HARD_STEPS', 12);
const HARD_SEC = () => num('BIODSH_GUARD_HARD_SEC', 240);
const dbg = (s) => { if (process.env.BIODSH_GUARD_DEBUG) { try { process.stderr.write(`[biodsh-guard] ${s}\n`); } catch {} } };

function uuid() {
  try { return globalThis.crypto.randomUUID(); } catch {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => { const r = Math.random() * 16 | 0; return (c === 'x' ? r : (r & 3 | 8)).toString(16); });
  }
}
function msg(text) {
  return { id: uuid(), role: 'user', content: [{ type: 'text', text }], source: { kind: 'user' } };
}
const SOFT_TEXT = (step, sec) =>
  `【系统提醒】本轮你已经用了 ${step} 步、约 ${sec} 秒。请停止继续探索或尝试新方法/新包,基于目前已经得到的结果,在接下来最多 2 步内给出最终答案。` +
  `如果无法精确计算,就给出你最有把握的近似值并说明依据;题目若要求固定格式(如最后一行 ANSWER: …),务必按格式输出。`;
const HARD_TEXT = (step, sec) =>
  `【最终提醒】已用 ${step} 步、约 ${sec} 秒,时间快到了。现在就直接给出最终结论,不要再调用任何工具;` +
  `按题目要求的格式输出最终答案(拿不准就给最佳估计并注明不确定)。`;

export function apply(ctx) {
  if (process.env.BIODSH_GUARD_OFF) { dbg('disabled by BIODSH_GUARD_OFF'); return; }
  // 每个 agent 的当前轮状态:{turn, t0, softDone, hardDone}
  const state = new WeakMap();
  ctx.on('agent/pre-step', async (payload, next) => {
    const decision = await next();
    try {
      if (!decision || decision.kind !== 'enter' || !payload || !payload.agent) return decision;
      const a = payload.agent;
      let st = state.get(a);
      if (!st || st.turn !== payload.turn) { st = { turn: payload.turn, t0: Date.now(), softDone: false, hardDone: false }; state.set(a, st); }
      const step = Number(payload.step) || 0;
      const sec = Math.round((Date.now() - st.t0) / 1000);
      let text = null;
      if (!st.hardDone && (step >= HARD_STEPS() || sec >= HARD_SEC())) { st.hardDone = true; st.softDone = true; text = HARD_TEXT(step, sec); }
      else if (!st.softDone && (step >= SOFT_STEPS() || sec >= SOFT_SEC())) { st.softDone = true; text = SOFT_TEXT(step, sec); }
      if (!text) return decision;
      dbg(`turn=${payload.turn} step=${step} sec=${sec} -> ${st.hardDone ? 'HARD' : 'SOFT'} nudge`);
      return { ...decision, messages: [...(decision.messages || []), msg(text)] };
    } catch (e) { dbg('error ' + (e && e.message)); return decision; }
  });
  dbg(`apply: soft ${SOFT_STEPS()} steps/${SOFT_SEC()}s, hard ${HARD_STEPS()} steps/${HARD_SEC()}s`);
}
