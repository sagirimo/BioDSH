// 修「离线/自建 OpenAI 兼容端点」下 `SSE stream ended without [DONE]`(STREAM_CLOSED)整轮失败的 bug。
// 现象:很多 OpenAI 兼容服务(vLLM / LMStudio / ollama / one-api 中转等)在最后一个 chunk 之后直接关闭 SSE,
// 不发 OpenAI 标准的 `data: [DONE]` 终止符。dsh-llm-deepseek 的 parseSse 严格要求 [DONE],收不到就抛
// STREAM_CLOSED → 整轮对话报错(见用户反馈截图,GPT-6 自建端点)。DeepSeek 官方端点始终发 [DONE],不受影响。
// 修法:流已经产出过至少一个 data(说明是正常回完、只是没发终止符)时,合成一个 [DONE] 让下游正常收尾;
// 只有一个 data 都没收到(真·空/立即断开)才报错。幂等,随打包存活。
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, '..');

export function patchSse(runtimeDir = path.join(root, 'dsh-runtime')) {
  const f = path.join(runtimeDir, 'node_modules', '@deepseek-ai', 'dsh-llm-deepseek', 'lib', 'index.js');
  if (!existsSync(f)) { console.log(`[patch-dsh-sse] 跳过:找不到 ${f}`); return false; }
  let s = readFileSync(f, 'utf8');
  if (s.includes('BIODSH_SSE_TOLERANT')) { console.log('[patch-dsh-sse] 已打过,跳过'); return true; }
  const NEEDLE_LOOP = '\tfor await (const { data } of events) {\n\t\tyield data;\n\t\tif (data === "[DONE]") return;\n\t}';
  const REPL_LOOP = '\tlet __biodshSseSeen = 0; /*BIODSH_SSE_TOLERANT*/\n\tfor await (const { data } of events) {\n\t\t__biodshSseSeen++;\n\t\tyield data;\n\t\tif (data === "[DONE]") return;\n\t}';
  const NEEDLE_THROW = '\tthrow new LlmError("SSE stream ended without [DONE]", "STREAM_CLOSED");';
  const REPL_THROW = '\tif (__biodshSseSeen > 0) { yield "[DONE]"; return; }\n\tthrow new LlmError("SSE stream ended without [DONE]", "STREAM_CLOSED");';
  if (!s.includes(NEEDLE_LOOP) || !s.includes(NEEDLE_THROW)) { console.log('[patch-dsh-sse] ⚠ 未找到锚点,dsh 版本可能已变,未打补丁'); return false; }
  s = s.replace(NEEDLE_LOOP, REPL_LOOP);
  s = s.replace(NEEDLE_THROW, REPL_THROW);
  writeFileSync(f, s);
  console.log('[patch-dsh-sse] ✅ 已容忍缺 [DONE] 的 SSE 流(自建/离线端点不再整轮失败)');
  return true;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const ok = patchSse(process.argv[2] ? path.resolve(process.argv[2]) : undefined);
  process.exit(ok ? 0 : 1);
}
