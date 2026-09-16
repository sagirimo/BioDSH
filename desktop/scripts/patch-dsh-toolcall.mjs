// 修 dsh 流式工具调用「身份被空值覆盖」的 bug(上游已在 master 修、但未发版;我们打包的 0.1.2-rc.1 仍是旧代码)。
// 现象:走 OpenAI 兼容中转时,续帧送 {"id":"","name":null,...},旧代码 `!== void 0` 判定通过,
// 把真实工具名/ id 覆盖成 null/""  → 报 `unknown tool ""` → 每个工具调用都失败、会话废掉。
// 上游修法(acceptIdentity):只接受「非空字符串」才覆盖;并给个 call-<index> 兜底 id。
// 见 deepseek-harness Discussions #2343/#3069;master 提交 a1271a4→b03261c。幂等,随打包存活。
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, '..');

export function patchToolcall(runtimeDir = path.join(root, 'dsh-runtime')) {
  const f = path.join(runtimeDir, 'node_modules', '@deepseek-ai', 'dsh-llm-deepseek', 'lib', 'index.js');
  if (!existsSync(f)) { console.log(`[patch-dsh-toolcall] 跳过:找不到 ${f}`); return false; }
  let s = readFileSync(f, 'utf8');
  if (s.includes('BIODSH_TOOLCALL_ID')) { console.log('[patch-dsh-toolcall] 已打过,跳过'); return true; }
  const A1 = 'if (call.id !== void 0) block.callId = call.id;';
  const A2 = 'if (call.function?.name !== void 0) block.name = call.function.name;';
  if (!s.includes(A1) || !s.includes(A2)) { console.log('[patch-dsh-toolcall] ⚠ 未找到锚点,dsh 版本可能已修/已变,未打补丁'); return false; }
  // 只在「非空字符串」时才覆盖身份;都没收到有效 id 时给个稳定的 call-<index> 兜底 id。
  s = s.replace(A1, '/*BIODSH_TOOLCALL_ID*/if (typeof call.id === "string" && call.id.length > 0) block.callId = call.id;');
  s = s.replace(A2, 'if (typeof call.function?.name === "string" && call.function.name.length > 0) block.name = call.function.name; if (!block.callId) block.callId = "call-" + block.index;');
  writeFileSync(f, s);
  console.log('[patch-dsh-toolcall] ✅ 已修流式工具调用身份覆盖 bug(acceptIdentity + call-<index> 兜底)');
  return true;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const ok = patchToolcall(process.argv[2] ? path.resolve(process.argv[2]) : undefined);
  process.exit(ok ? 0 : 1);
}
