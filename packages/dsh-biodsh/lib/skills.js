// BioDSH skills: one skill provider for the bundled BioDSH skills plus the `skill_library` tool.
//
// Official BioDSH skills (skills/official) are model-invocable and appear in the session catalog. The community library
// (skills/library, 2000+) is registered with modelInvocable:false: it stays out of the catalog, so the catalog is small
// and stable (the official tool-skill re-publishes it only when its digest changes, which keeps the prompt cache), while
// skills remain loadable through ctx.skills.get (biodsh-skill-select injects the ones that fit) and through
// `skill_library`, which lets the model search the library mid-task. Users can still invoke any of them with /name.
import { readdirSync, readFileSync, existsSync, statSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { hostImport } from './host.js';
import { setting } from './settings.js';

const { defineTool } = await hostImport('@deepseek-ai/dsh-tools');

export const name = 'biodsh-skills';
export const inject = ['skills', 'tools'];

const ROOT = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'skills');
const RANK = 600; // BUNDLED_SKILL_RANK: project and user skills with the same name win

// ---- frontmatter (name, description, optional whenToUse) ----
function frontmatter(text) {
  const m = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?/.exec(text);
  if (!m) return null;
  const fm = {};
  let key = null;
  for (const line of m[1].split(/\r?\n/)) {
    const kv = /^([A-Za-z][\w-]*):\s*(.*)$/.exec(line);
    if (kv) { key = kv[1]; fm[key] = kv[2].replace(/^(['"])(.*)\1$/, '$2'); }
    else if (key && /^\s+\S/.test(line)) fm[key] += ' ' + line.trim(); // folded continuation
  }
  return { fm, body: text.slice(m[0].length) };
}

function scan(dir, modelInvocable) {
  const out = [];
  if (!existsSync(dir)) return out;
  for (const entry of readdirSync(dir)) {
    const file = path.join(dir, entry, 'SKILL.md');
    if (!existsSync(file) || !statSync(path.join(dir, entry)).isDirectory()) continue;
    try {
      const parsed = frontmatter(readFileSync(file, 'utf8'));
      const n = parsed?.fm.name;
      if (!n || !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(n) || !parsed.fm.description) continue;
      out.push({ name: n, description: parsed.fm.description.trim(), whenToUse: parsed.fm.whenToUse || undefined,
        file, base: path.join(dir, entry), modelInvocable });
    } catch { /* unreadable skill: skip, like skill-filesystem */ }
  }
  return out;
}

// ---- lexical search over the library (names weigh most; CJK text as character pairs) ----
function terms(q) {
  const s = String(q || '').toLowerCase();
  const out = new Set(s.match(/[a-z0-9][a-z0-9.+-]*/g) || []);
  const cjk = s.replace(/[^㐀-鿿]/g, '');
  for (let i = 0; i < cjk.length - 1; i++) out.add(cjk.slice(i, i + 2));
  return [...out].filter((t) => t.length > 1);
}
function score(skill, ts) {
  const nm = skill.name.toLowerCase(), hay = `${nm} ${skill.description.toLowerCase()} ${(skill.whenToUse || '').toLowerCase()}`;
  let sc = 0;
  for (const t of ts) { if (nm.includes(t)) sc += 3; else if (hay.includes(t)) sc += 1; }
  return sc;
}

export function apply(ctx) {
  const library = setting(ctx, 'library');
  let cache = null;
  const dir = (key, sub) => setting(ctx, key) || path.join(ROOT, sub);
  const all = () => (cache ??= [...scan(dir('officialSkillsDir', 'official'), true), ...(library ? scan(dir('librarySkillsDir', 'library'), false) : [])]);
  const candidate = (s) => ({
    name: s.name, description: s.description, ...(s.whenToUse ? { whenToUse: s.whenToUse } : {}),
    invocation: { modelInvocable: s.modelInvocable, userInvocable: true }, source: 'bundled', provider: 'biodsh',
    path: s.file, resourceBase: { kind: 'directory', path: s.base }, rank: RANK, locator: s,
  });
  // registerProvider takes a factory: (control: { signal, invalidate }) => provider
  ctx.skills.registerProvider(() => ({
    name: 'biodsh',
    list: async () => all().map(candidate),
    get: async (c) => {
      const s = c.locator;
      const parsed = frontmatter(readFileSync(s.file, 'utf8'));
      return { ...candidate(s), content: parsed ? parsed.body : '' };
    },
  }));
  if (!library) return;

  const tool = defineTool({
    name: 'skill_library',
    description: 'Search the BioDSH skill library (2000+ bioinformatics, clinical and data skills not listed in the session catalog) and load one. '
      + 'Use it when the task needs a specific method, tool or database that no catalog skill covers: first search with a few English keywords, then load the best match by name and follow its instructions.',
    parameters: {
      query: { type: 'string', description: 'Keywords describing the method, tool or data type, e.g. "cox proportional hazards time-varying".' },
      load: { type: 'string', description: 'Exact skill name from a previous search result to load its full instructions.' },
    },
    output: { schema: { type: 'string' }, render: (_args, value) => [{ type: 'text', text: value }] },
    isConcurrencySafe: () => true,
    async execute(args, exec) {
      if (args.load) {
        const lookup = { signal: exec.signal, scope: exec.agent };
        const skill = await ctx.skills.get(String(args.load), lookup);
        if (!skill) throw new Error(`skill "${args.load}" is unknown`);
        const b = skill.resourceBase;
        return [`<skill_content name="${skill.name}">`, '<skill_resources>',
          b?.kind === 'directory' ? `Base directory for this skill: ${b.path}\nResolve relative paths mentioned by this skill against the base directory before using them. Load referenced resources only as needed.` : '',
          '</skill_resources>', '', '<skill_instructions>', skill.content, '</skill_instructions>', '</skill_content>'].join('\n');
      }
      const ts = terms(args.query);
      if (!ts.length) throw new Error('give a query (keywords) or load (a skill name)');
      const hits = all().map((s) => [score(s, ts), s]).filter(([sc]) => sc > 0)
        .sort((a, b) => b[0] - a[0] || (a[1].name < b[1].name ? -1 : 1)).slice(0, setting(ctx, 'librarySearchLimit'));
      if (!hits.length) return `No library skill matches "${args.query}". Proceed without one.`;
      return hits.map(([, s]) => `- ${s.name}: ${s.description.replace(/\s+/g, ' ').slice(0, 220)}`).join('\n')
        + '\n\nLoad one with skill_library {"load": "<name>"} only if it clearly fits the task.';
    },
    presentCall(args) {
      return { card: 'generic', title: args.load ? `Load library skill ${args.load}` : `Search skill library: ${args.query ?? ''}`, kind: 'read', rawInput: args.load ?? args.query ?? '' };
    },
  });
  ctx.tools.register(tool);
}
