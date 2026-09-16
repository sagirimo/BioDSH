// BioDSH 技能语义路由 —— cordis 插件版(正交化 0.3.0)。
// 取代旧的 patch-dsh-skill-router 补丁:不再改 dsh 编译后的代码,而是用 dsh 官方扩展面——
//   ① ctx.skills(SkillRegistry 服务,官方"技能能力接缝")的 snapshot() 方法;
//   ② agent/pre-step 事件(拿最新用户消息当 query)。
// 作用:2000+ 技能全量可发现,但每步只把与"最新一条用户消息"最相关的 top-K 塞进上下文
// (BIODSH_SKILL_CATALOG_MAX,默认 40),避免撑爆上下文/烧 token。embedding(离线)优先,失败回退词法。
// 通过 cordis.patch.yml 以官方插件方式加载。dsh 升级只要 ctx.skills.snapshot / agent/pre-step 还在就不受影响。

export const name = 'biodsh-skill-router';
export const inject = ['skills'];

const MAX = () => Math.max(1, Number(process.env.BIODSH_SKILL_CATALOG_MAX || 40) || 40);
const FLOOR = () => Number(process.env.BIODSH_SKILL_SCORE_FLOOR ?? 3) || 0;

// ---- 从消息里取最新一条用户文本当 query ----
function latestQuery(messages) {
  let q = '';
  for (let i = (messages?.length || 0) - 1; i >= 0; i--) {
    const m = messages[i];
    if (!m || !m.source || m.source.kind !== 'user') continue;
    for (const b of (m.content || [])) if (b && b.type === 'text' && typeof b.text === 'string') q = b.text + ' ' + q;
    if (q.trim()) break;
  }
  return q;
}

// ---- 词法兜底(零依赖,中文 char-bigram + 英文词 + 命名加权) ----
function queryToks(q) {
  q = (q || '').toLowerCase().slice(-600);
  const out = new Map();
  const put = (k, w) => { if (k) { const c = out.get(k); if (c === undefined || c < w) out.set(k, w); } };
  for (const m of q.matchAll(/[a-z0-9]{2,}/g)) put(m[0], 2);
  const s = q.replace(/[^一-鿿]/g, '');
  for (let i = 0; i < s.length - 1; i++) put(s.slice(i, i + 2), 1.5);
  if (s.length <= 3) for (const c of s) put(c, 0.5);
  return [...out.entries()];
}
function lexScore(sk, toks) {
  if (!toks.length) return 0;
  let sc = 0; const nm = (sk.name || '').toLowerCase(); const hay = nm + ' ' + (sk.description || '').toLowerCase();
  for (const [t, w] of toks) { if (hay.includes(t)) { sc += w; if (nm.includes(t)) sc += w; } }
  return sc;
}
function lexRankCap(skills, query, max) {
  try {
    if (!Array.isArray(skills) || skills.length <= max) return skills;
    const floor = FLOOR(); const toks = queryToks(query);
    const scored = skills.map((sk, idx) => {
      const bundled = !!(sk && sk.source === 'bundled'); const sc = lexScore(sk, toks);
      return { sk, idx, bundled, sc, key: bundled ? (sc >= floor ? sc : -1) : (1e6 + sc) };
    });
    scored.sort((a, b) => b.key - a.key || a.idx - b.idx);
    const picked = scored.filter(x => !x.bundled || x.sc >= floor).slice(0, max);
    return picked.sort((a, b) => a.idx - b.idx).map(x => x.sk);
  } catch { return skills; }
}

// ---- embedding 优先(离线,resources/embed/skill-router.mjs 的 rankCap),失败回退词法 ----
let embMod, embFail = false;
async function rankCap(skills, query, max) {
  try {
    if (!Array.isArray(skills) || skills.length <= max) return skills;
    const rp = process.env.BIODSH_EMBED_ROUTER;
    if (rp && !embFail) {
      if (!embMod) embMod = (async () => { const { pathToFileURL } = await import('node:url'); return import(pathToFileURL(rp).href); })().catch(() => { embFail = true; return null; });
      const mod = await embMod;
      if (mod && mod.rankCap && query && query.trim()) {
        const r = await mod.rankCap(skills, query, { max });
        if (Array.isArray(r) && r.length) return r;
      }
    }
  } catch { embFail = true; }
  return lexRankCap(skills, query, max);
}

export function apply(ctx) {
  const perAgentQuery = new WeakMap();
  let lastQuery = '';
  // 每步捕获最新 query(agent/pre-step 官方事件,payload 带 messages + agent)
  ctx.on('agent/pre-step', async (payload, next) => {
    try { const q = latestQuery(payload?.messages); if (q) { lastQuery = q; if (payload.agent) perAgentQuery.set(payload.agent, q); } } catch {}
    return next();
  });
  // 包一层官方 SkillRegistry.snapshot:返回前按 query 重排 + 截断 top-K
  const reg = ctx.skills;
  if (process.env.BIODSH_ROUTER_DEBUG) { try { process.stderr.write(`[biodsh-router] apply: ctx.skills=${!!reg} snapshotFn=${!!(reg && typeof reg.snapshot === 'function')}\n`); } catch {} }
  if (reg && typeof reg.snapshot === 'function' && !reg.__biodshRouterWrapped) {
    const orig = reg.snapshot.bind(reg);
    reg.snapshot = async (opts = {}) => {
      const snap = await orig(opts);
      if (process.env.BIODSH_ROUTER_DEBUG) { try { process.stderr.write(`[biodsh-router] snapshot called: skills=${snap?.skills?.length} max=${MAX()}\n`); } catch {} }
      try {
        if (!Array.isArray(snap?.skills) || snap.skills.length <= MAX()) return snap;
        const q = (opts.scope && perAgentQuery.get(opts.scope)) || lastQuery || '';
        const skills = await rankCap(snap.skills, q, MAX());
        if (process.env.BIODSH_ROUTER_DEBUG && skills.length !== snap.skills.length) {
          try { process.stderr.write(`[biodsh-router] capped ${snap.skills.length}->${skills.length} (max ${MAX()}) q="${String(q).slice(0, 40)}"\n`); } catch {}
        }
        return { ...snap, skills };
      } catch { return snap; }
    };
    reg.__biodshRouterWrapped = true;
    ctx.on('dispose', () => { try { reg.snapshot = orig; reg.__biodshRouterWrapped = false; } catch {} });
  }
}
