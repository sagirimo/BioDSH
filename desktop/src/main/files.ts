import { readdirSync, statSync, openSync, readSync, closeSync } from 'node:fs';
import path from 'node:path';

export interface FileEntry { name: string; rel: string; size: number; modified: number; kind: string; preview?: string }

const kindOf = (n: string): string => {
  const l = n.toLowerCase();
  const ext = l.split('.').pop() ?? '';
  if (ext === 'h5ad') return 'singlecell';
  if (['h5', 'loom', 'rds', 'zarr'].includes(ext)) return 'matrix';
  if (['csv', 'tsv', 'txt', 'xlsx', 'parquet'].includes(ext)) return 'table';
  if (['png', 'jpg', 'jpeg', 'svg', 'pdf'].includes(ext)) return 'figure';
  if (['fastq', 'fq', 'fasta', 'fa', 'bam', 'sam', 'vcf', 'bed', 'gtf', 'gff'].includes(ext) || /\.(fastq|fq|vcf)\.gz$/.test(l)) return 'seq';
  if (['json', 'yaml', 'yml'].includes(ext)) return 'meta';
  if (['md', 'html'].includes(ext)) return 'report';
  return 'other';
};

export function listWorkspaceFiles(root: string): FileEntry[] {
  const out: FileEntry[] = [];
  const walk = (dir: string, depth: number) => {
    let names: string[] = [];
    try { names = readdirSync(dir); } catch { return; }
    for (const name of names) {
      if (name.startsWith('.') || name === '__pycache__' || name === 'node_modules') continue;
      const p = path.join(dir, name);
      let st; try { st = statSync(p); } catch { continue; }
      if (st.isDirectory()) { if (depth < 2) walk(p, depth + 1); continue; }
      const kind = kindOf(name);
      if (kind === 'other' && st.size < 200) continue;
      let preview: string | undefined;
      if (kind === 'table' && st.size < 50_000_000) {
        try {
          const fd = openSync(p, 'r'); const buf = Buffer.alloc(4096); const n = readSync(fd, buf, 0, 4096, 0); closeSync(fd);
          const line = buf.toString('utf8', 0, n).split(/\r?\n/)[0] ?? '';
          const sep = line.includes('\t') ? '\t' : ',';
          const cols = line.split(sep).slice(0, 8);
          if (cols.length >= 2) preview = cols.join(' · ').slice(0, 120);
        } catch { /* */ }
      }
      out.push({ name, rel: path.relative(root, p).replaceAll('\\', '/'), size: st.size, modified: Math.floor(st.mtimeMs / 1000), kind, preview });
      if (out.length >= 500) return;
    }
  };
  walk(root, 0);
  return out.sort((a, b) => b.modified - a.modified);
}
