// 给 dsh-agent-loop 注入「步数护栏」：智能体连续执行超过 DSH_MAX_STEPS 步仍未收敛，
// 自动 abort 当前 turn（复用 dsh 现成的优雅中止路径），防止无限循环烧 token / 卡死。
// 幂等：已打过就跳过。stage-dsh 每次重新打包后会再调用它，所以补丁随打包存活。
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, '..');

export function patchGuard(runtimeDir = path.join(root, 'dsh-runtime')) {
  const f = path.join(runtimeDir, 'node_modules', '@deepseek-ai', 'dsh-agent-loop', 'lib', 'index.js');
  if (!existsSync(f)) { console.log(`[patch-dsh-guard] 跳过：找不到 ${f}`); return false; }
  let s = readFileSync(f, 'utf8');
  if (s.includes('BIODSH_STEP_GUARD')) { console.log('[patch-dsh-guard] 已打过，跳过'); return true; }
  const ANCHOR = 'const step = phase.step + 1;';
  if (!s.includes(ANCHOR)) { console.log('[patch-dsh-guard] ⚠ 未找到注入锚点，dsh 版本可能变了，未打补丁'); return false; }
  const GUARD = ANCHOR +
    '\n\t\t\t\t/*BIODSH_STEP_GUARD*/{ const __dshMax = Number(process.env.DSH_MAX_STEPS ?? 60) || 0;' +
    ' if (__dshMax > 0 && step > __dshMax) {' +
    ' try { process.stderr.write(`\\n[BioDSH] 智能体已连续执行 ${__dshMax} 步仍未完成，自动停止以避免无限循环烧费用（DSH_MAX_STEPS 可调）。\\n`); } catch {}' +
    ' phase.abort.abort(new Error(`BioDSH：智能体已连续执行 ${__dshMax} 步仍未完成，已自动停止以避免无限循环烧费用（可用环境变量 DSH_MAX_STEPS 调整上限）。`));' +
    ' signal.throwIfAborted(); } }';
  s = s.replace(ANCHOR, GUARD);
  writeFileSync(f, s);
  console.log('[patch-dsh-guard] ✅ 已注入步数护栏 (默认 DSH_MAX_STEPS=60)');
  return true;
}

// 独立运行
if (import.meta.url === `file://${process.argv[1]}`) {
  const ok = patchGuard(process.argv[2] ? path.resolve(process.argv[2]) : undefined);
  process.exit(ok ? 0 : 1);
}
