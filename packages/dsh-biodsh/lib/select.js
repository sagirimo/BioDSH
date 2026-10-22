// BioDSH skill selection. When a new human message arrives, a model reads the whole skill catalog (official skills and
// the community library; names plus short summaries, sorted so the prefix stays cacheable) and picks the skills whose
// full instructions would materially help. High-fit picks are injected into that step in the same shape as an explicit
// /name invocation (<skill_content>, source kind skill-invocation), so the agent does not have to decide to load them.
// Background (2026-10 audits): embedding routing recalled 16% of the skills an oracle judged high-fit, and models almost
// never called the skill tool on their own. Any failure (no credentials, timeout, unparsable answer) falls back silently.
import { setting } from './settings.js';

export const name = 'biodsh-skill-select';
export const inject = ['skills', 'llm'];
const TIMEOUT_MS = 60000;
const DESCRIPTION_CHARS = 160;

const SYSTEM_HEAD = 'You select skills for a biomedical data-analysis agent. Below is the complete skill catalog (name: summary).\n\n';
const SYSTEM_TAIL = '\n\nGiven the user request, choose at most 3 skills whose full instructions would MATERIALLY help carry out the specific '
  + 'analysis the request needs (not merely the same broad field; not generic plotting/report/writing tools). Mark "high" only when the '
  + 'skill prescribes the method the request actually asks for. Skills tagged [BioDSH] are validated BioDSH workflows: when one '
  + 'covers the request, prefer it over a similar untagged skill. If none qualifies, return an empty list. Answer strictly as JSON: '
  + '{"skills":[{"name":"<exact catalog name>","fit":"high|medium","why":"<15 words>"}]}';

const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
// Same shape as @deepseek-ai/dsh-skill renderSkillContent (shared by the skill tool and /name injections).
export function renderSkillContent(skill) {
  const b = skill.resourceBase;
  const hint = !b ? [`Resources for this skill are managed by provider "${esc(skill.provider)}".`, 'Load referenced resources only as needed.']
    : b.kind === 'directory' ? [`Base directory for this skill: ${esc(b.path)}`, 'Resolve relative paths mentioned by this skill against the base directory before using them. Load referenced resources only as needed.']
    : b.kind === 'url' ? [`Base URL for this skill: ${esc(b.url)}`, 'Resolve relative URLs mentioned by this skill against the base URL before using them. Load referenced resources only as needed.']
    : [`Resources for this skill: ${esc(b.description)}`, 'Load referenced resources only as needed.'];
  return [`<skill_content name="${esc(skill.name).replace(/"/g, '&quot;')}">`, '<skill_resources>', ...hint, '</skill_resources>', '',
    '<skill_instructions>', skill.content, '</skill_instructions>', '</skill_content>'].join('\n');
}

// Text the human typed in this step's claimed messages (reminders and injections carry other source kinds).
export function humanText(messages) {
  let q = '';
  for (const m of messages || []) {
    if (!m || m.source?.kind !== 'user') continue;
    for (const b of m.content || []) if (b?.type === 'text' && typeof b.text === 'string') q += b.text + '\n';
  }
  return q.trim();
}

export function parseSelection(text, known) {
  const m = String(text).match(/\{[\s\S]*\}/);
  if (!m) return [];
  const obj = JSON.parse(m[0]);
  return (Array.isArray(obj.skills) ? obj.skills : []).filter((s) => s && known.has(s.name)).slice(0, 3)
    .map((s) => ({ name: s.name, fit: s.fit === 'high' ? 'high' : 'medium', why: String(s.why || '').slice(0, 200) }));
}

export function apply(ctx) {
  const get = (k) => setting(ctx, k);
  const dbg = (s) => { if (get('debug') || process.env.BIODSH_SELECT_DEBUG) { try { process.stderr.write(`[biodsh-select] ${s}\n`); } catch {} } };
  let catalogCache = null;

  function route(agent) {
    const provider = get('selectProvider'), model = get('selectModel');
    if (provider && model) return { provider, model };
    const prev = agent?.session?.requestHeader?.()?.config;
    if (prev?.provider && prev?.model) return { provider: prev.provider, model: prev.model };
    try { const d = ctx.get('agentDefaultModel')?.currentSelection?.(); if (d?.provider && d?.model) return { provider: d.provider, model: d.model }; } catch {}
    return null;
  }

  async function catalog(agent, signal) {
    const snap = await ctx.skills.snapshot({ scope: agent, signal });
    // Official BioDSH skills (validated, in the session catalog) are tagged so the selector can prefer them.
    const list = (snap?.skills || [])
      .map((s) => [s.name, (s.provider === 'biodsh' && s.invocation?.modelInvocable ? '[BioDSH] ' : '')
        + String(s.description || '').replace(/\s+/g, ' ').trim().slice(0, DESCRIPTION_CHARS)])
      .sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0));
    const key = list.map((x) => x[0]).join(',');
    if (catalogCache?.key !== key) {
      catalogCache = { key, known: new Set(list.map((x) => x[0])), system: SYSTEM_HEAD + list.map(([n, d]) => `- ${n}: ${d}`).join('\n') + SYSTEM_TAIL };
    }
    return catalogCache;
  }

  async function select(agent, query, outer) {
    const r = route(agent);
    if (!r) throw new Error('no model route for the selector');
    const ac = new AbortController();
    const to = setTimeout(() => ac.abort(new Error('selector timeout')), TIMEOUT_MS);
    const onAbort = () => ac.abort(outer.reason);
    outer?.addEventListener?.('abort', onAbort, { once: true });
    try {
      const { system, known } = await catalog(agent, ac.signal);
      let text = '';
      for await (const chunk of ctx.llm.stream({ ...r, system, maxTokens: 6000, signal: ac.signal,
        messages: [{ role: 'user', content: [{ type: 'text', text: 'USER REQUEST:\n' + query.slice(0, 3000) }] }] })) {
        if (chunk.type === 'text-delta') text += chunk.text;
        else if (chunk.type === 'finish' && (chunk.reason?.kind === 'error' || chunk.reason?.kind === 'aborted')) {
          throw new Error(`${chunk.reason.failure?.code || chunk.reason.kind}: ${chunk.reason.failure?.message || ''}`);
        }
      }
      dbg(`route ${r.provider}/${r.model}`);
      return parseSelection(text, known);
    } finally { clearTimeout(to); outer?.removeEventListener?.('abort', onAbort); }
  }

  ctx.on('agent/pre-step', async (payload, next) => {
    if (!get('selectEnabled')) return next();
    let picked = null;
    try {
      const query = payload?.agent ? humanText(payload.messages) : '';
      if (query) {
        const t0 = Date.now();
        picked = await select(payload.agent, query, payload.signal);
        dbg(`picked ${JSON.stringify(picked)} in ${Date.now() - t0}ms`);
      }
    } catch (e) {
      if (payload?.signal?.aborted) throw e;
      dbg('fallback: ' + (e?.message || e));
    }
    const decision = await next();
    if (!picked?.length || !decision || decision.kind !== 'enter') return decision;
    try {
      // Skip skills already in this step (an explicit /name of the same skill, or a repeat).
      const present = new Set((decision.messages || []).filter((m) => m.source?.kind === 'skill-invocation').map((m) => m.source.name));
      const injections = [];
      for (const s of picked.filter((x) => x.fit === 'high' && !present.has(x.name)).slice(0, get('selectMaxInject'))) {
        const def = await ctx.skills.get(s.name, { scope: payload.agent, signal: payload.signal });
        if (!def) continue;
        injections.push({ id: globalThis.crypto.randomUUID(), role: 'user', content: [{ type: 'text', text: renderSkillContent(def) }],
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
}
