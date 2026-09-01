import { execFile } from 'node:child_process';
import { existsSync, writeFileSync } from 'node:fs';
import path from 'node:path';

export interface GitStatus { available: boolean; isRepo: boolean; branch?: string; dirty: number; lastCommit?: string; error?: string }

const git = (cwd: string, args: string[]) => new Promise<string>((resolve, reject) => {
  execFile('git', args, { cwd, windowsHide: true }, (err, out, errOut) => (err ? reject(new Error(errOut || err.message)) : resolve(out.trim())));
});

export async function gitStatus(p: string): Promise<GitStatus> {
  if (!existsSync(p)) return { available: false, isRepo: false, dirty: 0, error: '目录不存在' };
  try { await git(p, ['--version']); } catch { return { available: false, isRepo: false, dirty: 0 }; }
  const inside = await git(p, ['rev-parse', '--is-inside-work-tree']).then((s) => s === 'true').catch(() => false);
  if (!inside) return { available: true, isRepo: false, dirty: 0 };
  const branch = await git(p, ['rev-parse', '--abbrev-ref', 'HEAD']).catch(() => undefined);
  const dirty = await git(p, ['status', '--porcelain']).then((s) => s.split('\n').filter((l) => l.trim()).length).catch(() => 0);
  const lastCommit = await git(p, ['log', '-1', '--format=%s (%cr)']).catch(() => undefined);
  return { available: true, isRepo: true, branch, dirty, lastCommit: lastCommit || undefined };
}
export async function gitInit(p: string): Promise<GitStatus> {
  await git(p, ['init', '-q', '-b', 'main']).catch(() => git(p, ['init', '-q']));
  const gi = path.join(p, '.gitignore');
  if (!existsSync(gi)) writeFileSync(gi, '# BioDSH 默认忽略大文件与中间产物\n*.h5ad\n*.h5\n*.bam\n*.fastq*\n*.fq*\n__pycache__/\n.ipynb_checkpoints/\n');
  return gitStatus(p);
}
export async function gitCommit(p: string, message: string): Promise<GitStatus> {
  await git(p, ['add', '-A']);
  await git(p, ['-c', 'user.name=BioDSH', '-c', 'user.email=biodsh@local', 'commit', '-q', '-m', message.trim() || 'BioDSH 快照']).catch(() => undefined);
  return gitStatus(p);
}
