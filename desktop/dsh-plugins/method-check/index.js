// BioDSH 方法核对 + 置信标注 —— cordis 插件,走 dsh 官方扩展点 agent/pre-step,不改 dsh 代码。
// 针对 R1 实测的两类失败:
//   ① 方法/编码歧义(bix-10 有序回归怎么编码、bix-30 用哪种差异方法、bix-53 库版本):agent 挑一种就闷头算,算错也不说明。
//   ② 自信答错:护栏逼出答案后,拿不准也不标注。
// 做法:每轮第 1 步追加一条用户消息,要求 agent 动手前先(a)复述任务 (b)列出关键方法/参数选择点、采用哪种及理由
//   (c)若结果依赖主观选择则把另一种也算一遍并报两个;最终答案末尾附 CONFIDENCE: 高/中/低 + 一句理由。
// 只在 turn 的第一步注入一次;BIODSH_METHOD_CHECK_OFF=1 关闭;BIODSH_METHOD_CHECK_DEBUG=1 打日志。
export const name = 'biodsh-method-check';

const dbg = (s) => { if (process.env.BIODSH_METHOD_CHECK_DEBUG) { try { process.stderr.write(`[biodsh-method-check] ${s}\n`); } catch {} } };
function uuid() {
  try { return globalThis.crypto.randomUUID(); } catch {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => { const r = Math.random() * 16 | 0; return (c === 'x' ? r : (r & 3 | 8)).toString(16); });
  }
}
const TEXT =
  `【分析规范】在开始运行任何代码之前,先用 3–6 行写出:\n` +
  `1) 任务复述:要算什么、比较哪两组、输出是什么量。\n` +
  `2) 关键选择点:这道题里有哪些"不同做法会得到不同答案"的地方(例如:分类变量怎么编码/排序、用哪种检验或差异分析方法、阈值取多少、用哪个参考库或版本、按细胞还是按样本/患者统计)。对每一个,写明你采用的选项和理由,优先采用该领域的常规默认做法。\n` +
  `3) 如果最终答案明显依赖其中某个主观选择,请把最主要的另一种选项也算一遍,在回答里同时报告两个结果,并说明你最终采用哪个、为什么。\n` +
  `然后再动手。最终答案的最后一行之后,再加一行:CONFIDENCE: 高/中/低 —— <一句话理由>(例如数据不完整、方法有歧义、结果与预期不符等)。拿不准就如实写"低"。`;

export function apply(ctx) {
  if (process.env.BIODSH_METHOD_CHECK_OFF) { dbg('disabled'); return; }
  const seen = new WeakMap(); // agent -> last turn already injected
  ctx.on('agent/pre-step', async (payload, next) => {
    const decision = await next();
    try {
      if (!decision || decision.kind !== 'enter' || !payload || !payload.agent) return decision;
      if (Number(payload.step) !== 1) return decision;                 // 只在每轮第一步
      if (seen.get(payload.agent) === payload.turn) return decision;   // 同一轮不重复
      seen.set(payload.agent, payload.turn);
      dbg(`turn=${payload.turn} inject method-check`);
      return { ...decision, messages: [...(decision.messages || []), { id: uuid(), role: 'user', content: [{ type: 'text', text: TEXT }], source: { kind: 'user' } }] };
    } catch (e) { dbg('error ' + (e && e.message)); return decision; }
  });
  dbg('apply');
}
