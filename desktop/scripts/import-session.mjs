// 把一份 dsh 会话日志（session.jsonl.zstd 或 .jsonl）改写工作区路径后写到目标 dsh-home。
// 用法：node import-session.mjs <src session file> <dst session file> [<oldPath> <newPath>]
// 路径在日志里是 JSON 字符串（反斜杠被转义成 \\），所以按 JSON 转义后的形式替换。
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname } from 'node:path';
import { zstdCompressSync, zstdDecompressSync } from 'node:zlib';
const [src, dst, oldPath, newPath] = process.argv.slice(2);
if (!src || !dst) { console.error('usage: import-session.mjs <src> <dst> [oldPath newPath]'); process.exit(2); }
let buf = readFileSync(src);
// dsh 的日志是"每次追加一帧"的多帧 zstd；Node 的一次性 API 只解第一帧，所以按帧魔数切开逐帧解，
// 切错了（魔数恰好出现在压缩数据里）会校验失败，就把该段并入下一段重试。
function decodeFrames(b) {
  const starts = [];
  for (let i = 0; i + 3 < b.length; i++) if (b[i] === 0x28 && b[i + 1] === 0xb5 && b[i + 2] === 0x2f && b[i + 3] === 0xfd) starts.push(i);
  if (starts.length === 0 || starts[0] !== 0) throw new Error('not a zstd stream');
  const parts = []; let from = 0;
  for (let k = 1; k <= starts.length; k++) {
    const to = k < starts.length ? starts[k] : b.length;
    try { parts.push(zstdDecompressSync(b.subarray(from, to))); from = to; } catch { /* 假边界：继续并入下一段 */ }
  }
  if (from !== b.length) throw new Error('trailing undecodable zstd data');
  return Buffer.concat(parts);
}
if (src.endsWith('.zstd')) buf = decodeFrames(buf);
let text = buf.toString('utf8');
let replaced = 0;
if (oldPath && newPath && oldPath !== newPath) {
  const esc = (p) => JSON.stringify(p).slice(1, -1); // JSON 转义后的形式（不含引号）
  for (const [a, b] of [[esc(oldPath), esc(newPath)], [oldPath, newPath], [oldPath.replace(/\\/g, '/'), newPath.replace(/\\/g, '/')]]) {
    if (!a) continue;
    const n = text.split(a).length - 1; if (n) { text = text.split(a).join(b); replaced += n; }
  }
}
mkdirSync(dirname(dst), { recursive: true });
const out = Buffer.from(text, 'utf8');
// dsh 要求：第一帧必须恰好是一行头（header），后面每次追加一帧；这里按"头一帧 + 每行一帧"写，和原始日志同构。
function encodeFrames(t) {
  const lines = t.split('\n').filter(Boolean).map((l) => l + '\n');
  return Buffer.concat(lines.map((l) => zstdCompressSync(Buffer.from(l, 'utf8'))));
}
writeFileSync(dst, dst.endsWith('.zstd') ? encodeFrames(text) : out);
console.log(JSON.stringify({ lines: text.split('\n').filter(Boolean).length, bytes: out.length, replaced }));
