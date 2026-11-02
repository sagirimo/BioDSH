import { existsSync } from 'node:fs';
import path from 'node:path';
export const CONTRACT_FILES = ['TABLE_CONTRACT.json', 'ROW_SETS.json', 'PUBLIC_OUTPUT_NAMING_AND_TYPES.json', 'CLAIMS.json'];
export function workspaceRoot(ctx, agent) {
  // The working-directory service knows a child's own cwd; a subagent's session header still records its parent's.
  let wd; try { wd = ctx.get('workingDirectory')?.get(agent?.session); } catch {}
  return (typeof wd === 'string' && wd) || agent?.session?.header?.cwd;
}
export function selectorPolicy({ enabled = true, adaptive = true, root, query = '', hasFile = existsSync }) {
  if (!enabled) return { enabled: false, reason: 'disabled-by-setting' };
  if (!adaptive) return { enabled: true, reason: 'adaptive-disabled' };
  if (root && CONTRACT_FILES.some(n => hasFile(path.join(root, n)))) return { enabled: false, reason: 'public-output-contract' };
  // Text-only requests must explicitly supply both a method and an output schema.
  // A mere mention of CSV, ANSWER or a desired number is insufficient.
  const method = /(?:use exactly|method\s*:|prescribed method|严格使用|指定方法\s*[:：])/i.test(query);
  const schema = /(?:required columns\s*:|primary key\s*:|output schema\s*:|列名\s*[:：]|主键\s*[:：])/i.test(query);
  return { enabled: !(method && schema), reason: method && schema ? 'explicit-method-and-schema' : 'open-request' };
}
