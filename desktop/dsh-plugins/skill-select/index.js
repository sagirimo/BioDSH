// BioDSH 技能精选 —— cordis 插件(dsh 0.2,只走官方扩展点:ctx.llm / ctx.skills / agent/pre-step)。
// 问题(2026-10-16 审计):2000+ 技能的 embedding 路由召回很差(oracle 高匹配技能 top-10 只召回 16%),
//   且模型几乎从不主动调用 `skill` 工具(试点 15 次仅 1 次)。
// 做法:每当有新的人类消息,用便宜模型(默认 deepseek-flash,即 DeepSeek-V4.1-Flash)对照**全库目录**(名称+简介,按名称排序 →
//   固定前缀可命中上下文缓存)选 0–3 个技能;fit=high 的最多 2 个,把正文按官方 `/name` 显式调用的同一形态
//   (<skill_content>,source kind 'skill-invocation')注入本步,模型无需自己决定加载。
//   选中名单同时写到 globalThis.__biodshSkillSelect,供 skill-router 把它们排在目录最前。
// 任何失败(无凭据/超时/解析失败)都静默回退:不注入,目录照旧由 skill-router 的 embedding 排序。
// 环境变量:BIODSH_SELECT_OFF=1 关闭;BIODSH_SELECT_PROVIDER / BIODSH_SELECT_MODEL 指定选择模型;
//   BIODSH_SELECT_TIMEOUT_MS(默认 60000);BIODSH_SELECT_MAX_INJECT(默认 2);BIODSH_SELECT_DEBUG=1 打日志。
export const name = 'biodsh-skill-select';
export const inject = ['skills', 'llm'];

const dbg = (s) => { if (process.env.BIODSH_SELECT_DEBUG) { try { process.stderr.write(`[biodsh-select] ${s}\n`); } catch {} } };
const uuid = () => globalThis.crypto.randomUUID();
const DESC_MAX = 160;
const SYSTEM_HEAD = 'You select skills for a biomedical data-analysis agent. Below is the complete skill catalog (name: summary).\n\n';
const SYSTEM_TAIL = '\n\nGiven the user request, choose at most 3 skills whose full instructions would MATERIALLY help carry out the specific '
  + 'analysis the request needs (not merely the same broad field; not generic plotting/report/writing tools). If none qualifies, return an '
  + 'empty list. Answer strictly as JSON: {"skills":[{"name":"<exact catalog name>","fit":"high|medium","why":"<15 words>"}]}';

const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
// 与 @deepseek-ai/dsh-skill 的 renderSkillContent 同形(工具加载与 /name 注入共用的规范形态)
function renderSkillContent(skill) {
  const b = skill.resourceBase;
  const hint = !b ? [`Resources for this skill are managed by provider "${esc(skill.provider)}".`, 'Load referenced resources only as needed.']
    : b.kind === 'directory' ? [`Base directory for this skill: ${esc(b.path)}`, 'Resolve relative paths mentioned by this skill against the base directory before using them. Load referenced resources only as needed.']
    : b.kind === 'url' ? [`Base URL for this skill: ${esc(b.url)}`, 'Resolve relative URLs mentioned by this skill against the base URL before using them. Load referenced resources only as needed.']
    : [`Resources for this skill: ${esc(b.description)}`, 'Load referenced resources only as needed.'];
  return [`<skill_content name="${esc(skill.name).replace(/"/g, '&quot;')}">`, '<skill_resources>', ...hint, '</skill_resources>', '',
    '<skill_instructions>', skill.content, '</skill_instructions>', '</skill_content>'].join('\n');
}

function humanText(messages) {
  let q = '';
  for (const m of messages || []) {
    if (!m || m.source?.kind !== 'user') continue;
    for (const b of m.content || []) if (b?.type === 'text' && typeof b.text === 'string') q += b.text + '\n';
  }
  q = q.trim();
  return /^【(系统提醒|最终提醒)】/.test(q) ? '' : q;
}

function parseSelection(text, known) {
  const m = String(text).match(/\{[\s\S]*\}/);
  if (!m) return [];
  const obj = JSON.parse(m[0]);
  return (Array.isArray(obj.skills) ? obj.skills : []).filter((s) => s && known.has(s.name)).slice(0, 3)
    .map((s) => ({ name: s.name, fit: s.fit === 'high' ? 'high' : 'medium', why: String(s.why || '').slice(0, 200) }));
}

export function apply(ctx) {
  if (process.env.BIODSH_SELECT_OFF) { dbg('disabled'); return; }
  const provider = process.env.BIODSH_SELECT_PROVIDER || 'deepseek-official';
  const model = process.env.BIODSH_SELECT_MODEL || 'deepseek-flash'; // DeepSeek-V4.1-Flash(接口 id deepseek-flash)
  const timeoutMs = Number(process.env.BIODSH_SELECT_TIMEOUT_MS) || 60000;
  const maxInject = Math.max(0, Number(process.env.BIODSH_SELECT_MAX_INJECT ?? 2));
  const shared = (globalThis.__biodshSkillSelect ??= new WeakMap()); // agent -> [{name, fit, why}]
  let catalogCache = null; // { key, system, known }

  async function catalog(agent, signal) {
    // 按 agent scope 取合并目录(0.2 起技能目录由 preset 内的 skill-filesystem 注册到 preset 层):只取名称+简介,按名称排序,作为固定前缀命中缓存
    const snap = await ctx.skills.snapshot({ scope: agent, signal, __biodshFull: true });
    const list = (snap?.skills || []).filter((s) => s?.invocation?.modelInvocable !== false)
      .map((s) => [s.name, String(s.description || '').replace(/\s+/g, ' ').trim().slice(0, DESC_MAX)])
      .sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0));
    const key = list.length + ':' + list.map((x) => x[0]).join(',').length;
    if (catalogCache?.key !== key) {
      catalogCache = { key, known: new Set(list.map((x) => x[0])),
        system: SYSTEM_HEAD + list.map(([n, d]) => `- ${n}: ${d}`).join('\n') + SYSTEM_TAIL };
    }
    return catalogCache;
  }

  async function select(agent, query, outerSignal) {
    const ac = new AbortController();
    const to = setTimeout(() => ac.abort(new Error('selector timeout')), timeoutMs);
    const onAbort = () => ac.abort(outerSignal.reason);
    outerSignal?.addEventListener?.('abort', onAbort, { once: true });
    try {
      const { system, known } = await catalog(agent, ac.signal);
      let text = '';
      for await (const chunk of ctx.llm.stream({ provider, model, system, maxTokens: 6000, signal: ac.signal,
        messages: [{ role: 'user', content: [{ type: 'text', text: 'USER REQUEST:\n' + query.slice(0, 3000) }] }] })) {
        if (chunk.type === 'text-delta') text += chunk.text;
        else if (chunk.type === 'finish' && chunk.reason && (chunk.reason.kind === 'error' || chunk.reason.kind === 'aborted')) {
          throw new Error(`${chunk.reason.failure?.code || chunk.reason.kind}: ${chunk.reason.failure?.message || ''}`);
        }
      }
      return parseSelection(text, known);
    } finally { clearTimeout(to); outerSignal?.removeEventListener?.('abort', onAbort); }
  }

  ctx.on('agent/pre-step', async (payload, next) => {
    // 先选(在 next() 之前),这样无论挂载顺序如何,下游的目录监听器(tool-skill)取 snapshot 时都能看到选中名单
    let picked = null;
    try {
      const query = payload?.agent ? humanText(payload.messages) : '';
      if (query) {
        const t0 = Date.now();
        picked = await select(payload.agent, query, payload.signal);
        shared.set(payload.agent, picked);
        dbg(`picked ${JSON.stringify(picked)} in ${Date.now() - t0}ms`);
      }
    } catch (e) {
      if (payload?.signal?.aborted) throw e;
      dbg('fallback: ' + (e?.message || e));
    }
    const decision = await next();
    if (!picked?.length || !decision || decision.kind !== 'enter') return decision;
    try {
      const injections = [];
      for (const s of picked.filter((x) => x.fit === 'high').slice(0, maxInject)) {
        const def = await ctx.skills.get(s.name, { scope: payload.agent, signal: payload.signal });
        if (!def || def.invocation?.modelInvocable === false) continue;
        injections.push({ id: uuid(), role: 'user', content: [{ type: 'text', text: renderSkillContent(def) }],
          source: { kind: 'skill-invocation', name: def.name, form: 'instructions' } });
      }
      dbg(`injected ${injections.map((m) => m.source.name).join(', ') || 'none'}`);
      return injections.length ? { ...decision, messages: [...decision.messages, ...injections] } : decision;
    } catch (e) {
      if (payload?.signal?.aborted) throw e;
      dbg('inject failed: ' + (e?.message || e));
      return decision;
    }
  });
  dbg(`apply: provider=${provider} model=${model} timeout=${timeoutMs}ms maxInject=${maxInject}`);
}
