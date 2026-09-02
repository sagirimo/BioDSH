// 把 biodsh-core/skills 同步到 resources/skills，并生成商店目录 catalog.json。
// 只收录真实存在、带 SKILL.md 的技能；商店里的分数来自 store/skill-meta.json（人工维护，可缺省）。
import { readdirSync, readFileSync, writeFileSync, mkdirSync, rmSync, cpSync, existsSync, statSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.join(here, '..', '..');
const srcRoot = path.join(root, 'biodsh-core', 'skills');
const outRoot = path.join(here, '..', 'resources', 'skills');
const metaPath = path.join(here, '..', 'store', 'skill-meta.json');
const meta = existsSync(metaPath) ? JSON.parse(readFileSync(metaPath, 'utf8')) : {};
const DOMAIN_ICON = {
  '单细胞与空间': '🧫', '转录组与表达': '🧬', '基因组与变异': '🧬', '表观与调控': '🎚️', '蛋白与结构': '🧊', '药物与化学': '💊',
  '临床与医学': '🏥', '微生物与免疫': '🦠', '代谢与其他组学': '⚗️', '数据与工具': '🧰',
};
const CATEGORY_ICON = {
  'single-cell': '🧫', spatial: '🗺️', transcriptomics: '🧬', genomics: '🧬', epigenomics: '🎚️', proteomics: '🧊', metabolomics: '⚗️',
  metagenomics: '🦠', immunology: '🛡️', clinical: '🏥', drug: '💊', pathway: '🕸️', database: '🗄️', visualization: '📊',
  statistics: '📈', workflow: '⚙️', imaging: '🔬', writing: '✍️', general: '🧩', qc: '🩺', analysis: '🧫', audit: '🔏',
};

function frontmatter(md) {
  const m = md.match(/^---\r?\n([\s\S]*?)\r?\n---/);
  const out = {};
  if (!m) return out;
  for (const line of m[1].split(/\r?\n/)) {
    const i = line.indexOf(':');
    if (i > 0) out[line.slice(0, i).trim()] = line.slice(i + 1).trim().replace(/^["']|["']$/g, '');
  }
  return out;
}

// 目录可能被别的进程当作 cwd 占着（Windows 上 rmdir 会 EACCES）：能删多少删多少，剩下的靠 cpSync 覆盖
try { rmSync(outRoot, { recursive: true, force: true }); } catch (e) { console.warn(`warn: could not fully remove ${outRoot}: ${e.code ?? e}`); for (const n of readdirSync(outRoot)) { try { rmSync(path.join(outRoot, n), { recursive: true, force: true }); } catch { /* held open */ } } }
mkdirSync(outRoot, { recursive: true });
const skills = [];
for (const name of readdirSync(srcRoot).sort()) {
  const dir = path.join(srcRoot, name);
  if (!statSync(dir).isDirectory()) continue;
  const skillMd = path.join(dir, 'SKILL.md');
  const skillJson = path.join(dir, 'skill.json');
  if (!existsSync(skillMd) || !existsSync(skillJson)) { console.warn(`skip ${name}: missing SKILL.md/skill.json`); continue; }
  const fm = frontmatter(readFileSync(skillMd, 'utf8'));
  if (!fm.name || !fm.description) { console.warn(`skip ${name}: SKILL.md lacks name/description frontmatter`); continue; }
  const sj = JSON.parse(readFileSync(skillJson, 'utf8'));
  const m = meta[name] ?? {};
  if (m.hidden) { console.warn(`skip ${name}: hidden`); continue; }
  cpSync(dir, path.join(outRoot, name), {
    recursive: true,
    filter: (p) => !/__pycache__|\.pyc$/.test(p),
  });
  skills.push({
    id: name,
    name: m.title ?? sj.name ?? name,
    summary: m.summary ?? sj.description ?? fm.description,
    description: fm.description,
    domain: sj.domain ?? m.domain ?? 'other',
    category: m.category ?? 'analysis',
    icon: m.icon ?? '🧬',
    tags: m.tags ?? [],
    inputs: sj.inputs ?? [],
    outputs: sj.outputs ?? [],
    offline: !!sj.offline,
    mutates_input: !!sj.mutates_input,
    version: m.version ?? '0.3.1',
    evidence: m.evidence ?? null,
    featured: !!m.featured,
    requires: { python: true, env: 'bioenv' },
    entry: sj.entry ?? null,
  });
  console.log(`ok ${name}`);
}
// 技能评分模型：五维加权综合分(0-100)。权重依据公认评测实践(正确性主导)。
// 只有拿到「正确性」信号(公认 benchmark 或内部自动评测)的技能才评分；否则记为未评测(unrated)，绝不臆造分数。
const SCORE_WEIGHTS = { correctness: 0.45, robustness: 0.15, reproducibility: 0.15, offline: 0.15, efficiency: 0.10 };
function computeScore(sc) {
  if (!sc || typeof sc.correctness !== 'number') return null; // 无正确性数据 = 未评测
  let num = 0, den = 0;
  for (const [k, w] of Object.entries(SCORE_WEIGHTS)) {
    if (typeof sc[k] === 'number') { num += w * Math.max(0, Math.min(100, sc[k])); den += w; }
  }
  return den > 0 ? Math.round(num / den) : null; // 只按已有维度归一,不给缺失维度补分
}

for (const s of skills) { const mm = meta[s.id] ?? {}; s.tier = 'official'; s.bundle = 'skills'; s.domain_zh = mm.domain_zh ?? '单细胞与空间'; s.subcategory = mm.subcategory ?? { qc: '单细胞预处理与质控', analysis: '聚类与降维', clinical: '细胞类型注释', audit: '流程与环境' }[s.category] ?? ''; if (s.id === 'scrna-treatment-response') s.subcategory = '细胞类型注释'; if (s.id === 'scrna-cellstate-annotation') s.subcategory = '细胞类型注释';
  // 评分：多维度加权综合分(0-100)。维度分来自 skill-meta 的 scores;没有正确性数据则不评分(unrated)。
  const sc = mm.scores ?? null; s.score = computeScore(sc); s.scoreBreakdown = sc; s.benchmarks = mm.benchmarks ?? null;
}

// 社区收编技能：由 scripts/harvest_skills.py 从 competitors/ 收集到 resources/community-skills/，索引在 store/community-index.json
const communityIndex = path.join(here, '..', 'store', 'community-index.json');
const communityRoot = path.join(here, '..', 'resources', 'community-skills');
let community = [];
if (existsSync(communityIndex) && existsSync(communityRoot)) {
  const officialIds = new Set(skills.map((s) => s.id));
  const zhPath = path.join(here, '..', 'store', 'community-zh.json');
  const zh = existsSync(zhPath) ? JSON.parse(readFileSync(zhPath, 'utf8')).items : {};
  community = JSON.parse(readFileSync(communityIndex, 'utf8')).skills
    .filter((c) => !officialIds.has(c.id) && existsSync(path.join(communityRoot, c.id, 'SKILL.md')))
    .map((c) => { const z = zh[c.id] ?? {}; return ({
      id: c.id, name: z.title_zh ?? c.name, name_en: c.name, summary: z.summary_zh ?? c.description, description: c.description,
      domain: c.category, category: c.category, icon: DOMAIN_ICON[z.domain] ?? CATEGORY_ICON[c.category] ?? '🧩', tags: z.tags_zh ?? c.tags ?? [],
      domain_zh: z.domain ?? '数据与工具', subcategory: z.subcategory ?? '', level: z.level ?? '',
      inputs: [], outputs: [], offline: false, mutates_input: false, version: c.version ?? '1.0.0',
      evidence: null, featured: false, requires: { python: !!c.has_scripts, env: 'bioenv' },
      tier: 'community', bundle: 'community-skills', origin: c.origin, has_scripts: !!c.has_scripts,
    }); });
}
// 社区精选：来源可靠 + 附带脚本 + 简介够长，每个领域最多 6 个
const GOOD_REPOS = new Set(['OmicVerse', 'GPTomics-bioSkills', 'ClawBio', 'hcls-agent-skills', 'omics-skills', 'SciAgent-Skills']);
const perDomain = new Map();
for (const c of community) {
  if (!c.has_scripts || !GOOD_REPOS.has(c.origin?.repo) || (c.summary ?? '').length < 30) continue;
  const n = perDomain.get(c.domain_zh) ?? 0;
  if (n >= 6) continue;
  c.featured = true; perDomain.set(c.domain_zh, n + 1);
}
const all = [...skills, ...community];
writeFileSync(path.join(outRoot, 'catalog.json'), JSON.stringify({
  meta: { name: 'BioDSH Skill Store', generated: new Date().toISOString().slice(0, 10), count: all.length, official: skills.length, community: community.length },
  skills: all,
}, null, 2));
console.log(`catalog: ${skills.length} official + ${community.length} community`);
