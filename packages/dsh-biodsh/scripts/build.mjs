// Build the dsh-biodsh bundle for one dsh release.
//
// An agent preset has no inheritance: a new preset restates its complete plugin list. So the BioDSH preset is generated
// from the standard preset shipped in the target dsh (dsh-web-app/presets/standard.patch.yml) with three changes:
// the persona prefix, the BioDSH plugins inserted after tool-skill, and id/name/description/order. `!!js` conditions are
// carried over verbatim. Re-run for every dsh release the bundle targets and publish with the matching version.
// Also copies the skills: skills/official (catalog) and skills/library (community library, hidden from the catalog).
//
// usage: node scripts/build.mjs --dsh <dsh runtime dir with node_modules> [--official <dir>] [--library <dir>] [--no-skills]
import { readFileSync, writeFileSync, existsSync, rmSync, cpSync, readdirSync, mkdirSync } from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const pkgDir = path.join(here, '..');
const repo = path.join(pkgDir, '..', '..');
const arg = (k, d) => { const i = process.argv.indexOf(k); return i >= 0 ? process.argv[i + 1] : d; };
const runtime = path.resolve(arg('--dsh', path.join(repo, 'desktop', 'dsh-runtime')));
const official = path.resolve(arg('--official', path.join(repo, 'desktop', 'resources', 'skills')));
const library = path.resolve(arg('--library', path.join(repo, 'desktop', 'resources', 'community-skills')));

const PERSONA = [
  'You are BioDSH (中文名同样叫 BioDSH), a bioinformatics assistant powered by the {{model}} model. Your users are doctors and',
  'wet-lab scientists, often with no programming or bioinformatics background.',
  '',
  'When greeted or asked who you are, introduce yourself as BioDSH 生信助手 and give three concrete examples they could ask,',
  'e.g. 「帮我看看这份单细胞数据的质量」「比较有效和无效病人的细胞组成差异」「解读这个结果文件夹」. Never call yourself a generic coding agent.',
  '',
  'How you work on analyses:',
  '- Reply in the language the user writes in. Plain language first, technical detail second; briefly explain any format,',
  '  tool or statistic you mention.',
  '- Skills: BioDSH skills are listed in the session catalog; skills that clearly fit a request may already be injected as',
  '  <skill_content>; follow them. For a specific method, tool or database no listed skill covers, search the 2000+ skill',
  '  library with the skill_library tool before improvising.',
  '- Keep original data untouched; write outputs to a new subfolder and tell the user its name.',
  '- Stay within the working folder and the files the user gave you. Do not search parent or unrelated folders for',
  '  examples, earlier results or reference answers; when a format is unclear, follow the files provided or ask.',
  '- Check the units and the unit of inference (patients vs cells vs samples), state assumptions, and report what you',
  '  actually computed, including failures. Do not present a finished run as a validated scientific result.',
  '- When a decision is needed (thresholds, which group is the control), ask one clear question instead of guessing.',
  '',
  'When the request comes with a written specification (a task description, a protocol, output contracts):',
  '- Read all of it, including every file it names, before writing code. Then map the ambiguous or transformed output',
  '  fields to their source or formula, units, row scope and missing-value rules. Keep raw identifiers and values separate',
  '  from derived representations; use named ID columns. Do not silently trim values, change units or infer an undefined',
  '  field from its name: look again in the provided material, and say what stays unresolved.',
  '- Join and group by the identifiers the specification names (sample labels, IDs), never by column or row order.',
  '- An output column with the same name as an input column carries the input value unchanged, unless the specification',
  '  explicitly defines a new value for that column (a derived quantity with a similar name is not that column).',
  '- Batch related input inspection and verification; each step is a model call the user waits for. Write a complete first',
  '  implementation after resolving the specification, then make targeted fixes to failed checks rather than rewrites.',
  '  The script must run from any location under any file name: take paths from its arguments, refer to itself through',
  '  __file__. If a time or CPU budget is stated, measure the script against it and vectorize loops over rows or genes.',
  '- Check the saved outputs, re-read from disk, with rules taken from the specification and independently of the code',
  '  that produced them: JSON containers, exact key sets, scalar types, allowed options and table bindings; then source',
  '  values kept, units, row masks and group sizes, before repeating expensive fits. Do not add wrappers or fields the',
  '  specification does not request. A successful run or reproducible numbers alone do not validate the output contract.',
  '  Print every check in one run, fix what it reports in one edit, and rerun the same check.',
].join('\n');

// ---- read the shipped standard preset (keep !!js values) ----
const YAML = createRequire(path.join(runtime, 'package.json'))('yaml');
const src = path.join(runtime, 'node_modules', '@deepseek-ai', 'dsh-web-app', 'presets', 'standard.patch.yml');
const dshVersion = JSON.parse(readFileSync(path.join(runtime, 'node_modules', '@deepseek-ai', 'dsh', 'package.json'), 'utf8')).version;
const JS = Symbol('js');
const rows = YAML.parse(readFileSync(src, 'utf8'), { customTags: [{ tag: 'tag:yaml.org,2002:js', resolve: (s) => ({ [JS]: s }) }] });
const standard = rows[0].insert.find((r) => r.id === 'preset-standard');
if (!standard) throw new Error(`no preset-standard in ${src}`);
// shallow copies: structuredClone would drop the symbol that marks !!js values
const plugins = standard.config.plugins.map((p) => ({ ...p, ...(p.config && !Array.isArray(p.config) ? { config: { ...p.config } } : {}) }));
const at = (id) => { const i = plugins.findIndex((p) => p.id === id); if (i < 0) throw new Error(`standard preset has no ${id}`); return i; };
plugins[at('persona')].config = { ...(plugins[at('persona')].config || {}), prefix: PERSONA };
plugins.splice(at('tool-skill') + 1, 0,
  { id: 'biodsh-skills', name: 'dsh-biodsh/skills' },
  { id: 'biodsh-skill-select', name: 'dsh-biodsh/select' },
  { id: 'biodsh-step-guard', name: 'dsh-biodsh/guard' });
plugins.splice(at('persona') + 1, 0, { id: 'biodsh-context', name: 'dsh-biodsh/context' });
const preset = { id: 'preset-biodsh', name: '@deepseek-ai/dsh-agent-preset', config: {
  id: 'biodsh', name: 'BioDSH', order: 0.5,
  description: 'Bioinformatics assistant: BioDSH skills in the catalog, a 2000+ skill library, automatic skill selection and a convergence guard.',
  plugins } };
// PTC variant, like the official `ptc` preset (standard + tool-presentation ptc): the model sees one run_code tool and
// writes a program that calls the other tools, so writing a script, running it and printing checks take one step.
const ptcPlugins = [...plugins];
ptcPlugins.splice(at('tool-web') + 1, 0, { id: 'tool-presentation', name: '@deepseek-ai/dsh-agent-tool-presentation', config: { mode: 'ptc' } });
const ptcPreset = { id: 'preset-biodsh-ptc', name: '@deepseek-ai/dsh-agent-preset', config: {
  id: 'biodsh-ptc', name: 'BioDSH (PTC)', order: 0.6,
  description: 'BioDSH with programmatic tool calling: tools are called from one program per step (fewer model calls).',
  plugins: ptcPlugins } };

// ---- serialize with !!js preserved ----
// Host row `biodsh` carries the user-facing settings (a settings namespace); the preset rows read it.
const settingsRow = { id: 'biodsh', name: 'dsh-biodsh/settings' };
let text = YAML.stringify([{ insert: [settingsRow, preset, ptcPreset] }], { lineWidth: 0, aliasDuplicateObjects: false, customTags: [{ tag: 'tag:yaml.org,2002:js', identify: (v) => v && typeof v === 'object' && JS in v,
  stringify: (item) => JSON.stringify(item.value[JS]) }] });
text = `# dsh-biodsh bundle patch, generated by scripts/build.mjs from the standard preset of dsh ${dshVersion}.\n`
  + '# Adds the BioDSH agent presets (native and PTC) and their settings row `biodsh`; other presets are not changed.\n'
  + '# Do not edit by hand: rebuild for each dsh release. Change settings in settings.yaml (`biodsh:`) or the Settings page.\n' + text;
writeFileSync(path.join(pkgDir, 'cordis.patch.yml'), text);

// ---- version follows the dsh release it was built against ----
const pkgFile = path.join(pkgDir, 'package.json');
const pkg = JSON.parse(readFileSync(pkgFile, 'utf8'));
pkg.version = `${pkg.version.split('+')[0].replace(/-dsh.*$/, '')}`;
pkg.dshTarget = dshVersion;
writeFileSync(pkgFile, JSON.stringify(pkg, null, 2) + '\n');

// ---- skills ----
if (!process.argv.includes('--no-skills')) {
  const out = path.join(pkgDir, 'skills');
  rmSync(out, { recursive: true, force: true });
  for (const [from, to] of [[official, 'official'], [library, 'library']]) {
    if (!existsSync(from)) { console.warn(`skip ${to}: ${from} missing`); continue; }
    mkdirSync(path.join(out, to), { recursive: true });
    for (const d of readdirSync(from)) if (existsSync(path.join(from, d, 'SKILL.md'))) cpSync(path.join(from, d), path.join(out, to, d), { recursive: true });
    console.log(`skills/${to}: ${readdirSync(path.join(out, to)).length}`);
  }
}
console.log(`cordis.patch.yml built from dsh ${dshVersion} standard preset (${plugins.length} plugins)`);
