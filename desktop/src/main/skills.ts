import { readFileSync, writeFileSync, existsSync, cpSync, rmSync, readdirSync } from 'node:fs';
import path from 'node:path';
import type { AppPaths, CatalogSkill, SkillStatus } from '../shared/types';
import { resourcePath } from './paths';

// 技能商店的“安装”非常朴素：把 resources/skills/<id> 复制到 $DSH_HOME/skills/<id>。
// dsh 的 skill-filesystem 会监听这个目录并热加载，模型下一轮就能看到新技能。
export class SkillStore {
  constructor(private paths: AppPaths) {}

  catalog(): CatalogSkill[] {
    const f = resourcePath('skills', 'catalog.json');
    if (!existsSync(f)) return [];
    return (JSON.parse(readFileSync(f, 'utf8')) as { skills: CatalogSkill[] }).skills;
  }

  statuses(): SkillStatus[] {
    return this.catalog().map((s) => {
      const dir = path.join(this.paths.skills, s.id);
      if (!existsSync(path.join(dir, 'SKILL.md'))) return { id: s.id, state: 'not_installed' as const };
      const vf = path.join(dir, '.biodsh-version');
      const installedVersion = existsSync(vf) ? readFileSync(vf, 'utf8').trim() : undefined;
      return {
        id: s.id,
        state: installedVersion && installedVersion !== s.version ? 'update_available' as const : 'installed' as const,
        installedVersion,
      };
    });
  }

  installedIds(): string[] {
    if (!existsSync(this.paths.skills)) return [];
    return readdirSync(this.paths.skills).filter((n) => existsSync(path.join(this.paths.skills, n, 'SKILL.md')));
  }

  install(id: string): SkillStatus {
    const skill = this.catalog().find((s) => s.id === id);
    if (!skill) return { id, state: 'error', error: '目录中没有这个技能' };
    const src = resourcePath(skill.bundle ?? 'skills', id);
    const dst = path.join(this.paths.skills, id);
    rmSync(dst, { recursive: true, force: true });
    cpSync(src, dst, { recursive: true, filter: (p) => !/__pycache__|\.pyc$/.test(p) });
    // 给 SKILL.md 追加“桌面版怎么跑”的说明：PATH 里的 python 就是 BioDSH 生信环境。
    const md = path.join(dst, 'SKILL.md');
    const runNote = `

## Running in BioDSH Desktop

The BioDSH Python environment (scanpy, anndata, …) is already first on PATH; \`python\` resolves to it. Run this skill's script directly:

\`\`\`bash
python "${dst.replace(/\\/g, '/')}/${(skill as { entry?: { script?: string } }).entry?.script ?? 'run.py'}" --input <input file> --outdir <output directory> --seed 0
\`\`\`

Write outputs into a fresh directory under the current workspace, then summarize the generated files (${skill.outputs.join(', ')}) for the user in plain language.
`;
    const communityNote = `

## Running in BioDSH Desktop

This skill was collected from ${skill.origin?.repo ?? 'a community repository'} (${skill.origin?.license ?? 'see repo license'}). The BioDSH Python environment (scanpy, anndata, pandas, …) is first on PATH, so \`python\` resolves to it; install any extra package the skill needs with \`uv pip install <pkg>\` (uv is on PATH) or \`python -m pip install <pkg>\`. Scripts referenced by this skill live in \`${dst.replace(/\\/g, '/')}\`. Explain results to the user in plain language.
`;
    writeFileSync(md, readFileSync(md, 'utf8').trimEnd() + (skill.tier === 'community' ? communityNote : runNote));
    writeFileSync(path.join(dst, '.biodsh-version'), skill.version + '\n');
    return { id, state: 'installed', installedVersion: skill.version };
  }

  uninstall(id: string): SkillStatus {
    rmSync(path.join(this.paths.skills, id), { recursive: true, force: true });
    return { id, state: 'not_installed' };
  }

  readme(id: string): string {
    const skill = this.catalog().find((s) => s.id === id);
    const f = resourcePath(skill?.bundle ?? 'skills', id, 'SKILL.md');
    return existsSync(f) ? readFileSync(f, 'utf8').replace(/^---[\s\S]*?---\s*/, '') : '';
  }
}
