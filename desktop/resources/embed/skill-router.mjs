// 运行时技能语义路由：加载离线预计算的技能向量，给「用户这句话」算一次查询向量，
// 余弦排序后只保留最相关的 top-K 进上下文。官方/已装技能(source!=='bundled')恒留；社区(bundled)按阈值。
// dsh-tool-skill 的补丁会 import 本文件并调用 rankCap；任何异常都会回退到补丁里的词法匹配。
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { embed, cosine } from './embed-core.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
let _vecs = null;

function loadVectors() {
  if (_vecs) return _vecs;
  const idxPath = process.env.BIODSH_SKILL_VECTORS || path.join(__dirname, '..', 'skills', 'skill-vectors.json');
  const binPath = idxPath.replace(/\.json$/, '.bin');
  const idx = JSON.parse(readFileSync(idxPath, 'utf8'));
  const raw = readFileSync(binPath);
  const buf = new Float32Array(raw.buffer, raw.byteOffset, raw.byteLength / 4);
  const dim = idx.dim, map = new Map();
  for (let r = 0; r < idx.ids.length; r++) map.set(idx.ids[r], buf.subarray(r * dim, r * dim + dim));
  _vecs = { dim, map };
  return _vecs;
}

/** 语义排序 + 截断。skills: dsh 候选技能(带 .name/.source)；query: 用户最新一句话。 */
export async function rankCap(skills, query, opts = {}) {
  const max = Math.max(1, opts.max || 40);
  const { map } = loadVectors();
  const qv = (await embed(query, true))[0];
  const scored = skills.map((sk, idx) => {
    const bundled = !!(sk && sk.source === 'bundled');
    const v = map.get(sk && sk.name) || (sk && sk.id && map.get(sk.id));
    const sc = v ? cosine(qv, v) : -1;
    return { sk, idx, bundled, sc, key: 0 };
  });
  const bs = scored.filter((x) => x.bundled && x.sc >= 0).map((x) => x.sc);
  const top = bs.length ? Math.max(...bs) : 0;
  // e5 余弦基线偏高(~0.80)，靠排序区分而非绝对阈值。floor 只滤掉明显无关；
  // 弱匹配门控：最高分都不高(问题跟任何技能都不太沾边)时，只放少量，避免噪声塞满上下文。
  const floor = Number(process.env.BIODSH_EMBED_FLOOR ?? 0.80);
  const gate = Number(process.env.BIODSH_EMBED_GATE ?? 0.87);
  const few = Number(process.env.BIODSH_EMBED_FEW ?? 8);
  const effMax = top >= gate ? max : Math.min(max, few);
  for (const x of scored) x.key = x.bundled ? (x.sc >= floor ? x.sc : -1) : (1e6 + x.sc);
  scored.sort((a, b) => b.key - a.key || a.idx - b.idx);
  const keptNonBundled = scored.filter((x) => !x.bundled);
  const bundledPass = scored.filter((x) => x.bundled && x.sc >= floor).slice(0, Math.max(0, effMax - keptNonBundled.length));
  const picked = [...keptNonBundled, ...bundledPass].slice(0, max);
  return picked.sort((a, b) => a.idx - b.idx).map((x) => x.sk);
}
