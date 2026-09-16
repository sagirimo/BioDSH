// 离线预计算全部技能的向量（构建期跑一次）。读 resources/skills/catalog.json，
// 对每个技能的「名称。描述」编码成向量，存成紧凑二进制 + id 索引，运行时 skill-router 直接加载做余弦匹配。
// 用法：node scripts/precompute-skill-vectors.mjs   （需先 npm install 好 resources/embed 并能联网下模型，或已缓存）
import { readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { embed, EMBED_DIM, MODEL_ID } from '../resources/embed/embed-core.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.join(here, '..');
const catalog = JSON.parse(readFileSync(path.join(root, 'resources/skills/catalog.json'), 'utf8'));
const skills = (catalog.skills || []).filter((s) => s && s.id);
console.log(`skills to embed: ${skills.length} (model ${MODEL_ID}, dim ${EMBED_DIM})`);

const text = (s) => `${s.name || s.id}. ${(s.description || s.summary || '').replace(/\s+/g, ' ').trim()}`.slice(0, 512);
const ids = [];
const buf = Buffer.alloc(skills.length * EMBED_DIM * 4);
let row = 0;
const BATCH = 64;
const t0 = Date.now();
for (let i = 0; i < skills.length; i += BATCH) {
  const chunk = skills.slice(i, i + BATCH);
  const vecs = await embed(chunk.map(text), false);
  for (let j = 0; j < chunk.length; j++) {
    ids.push(chunk[j].id);
    const v = vecs[j];
    for (let k = 0; k < EMBED_DIM; k++) buf.writeFloatLE(v[k] ?? 0, (row * EMBED_DIM + k) * 4);
    row++;
  }
  if (i % (BATCH * 8) === 0) console.log(`  ${Math.min(i + BATCH, skills.length)}/${skills.length}  (${((Date.now() - t0) / 1000).toFixed(0)}s)`);
}
const binPath = path.join(root, 'resources/skills/skill-vectors.bin');
const idxPath = path.join(root, 'resources/skills/skill-vectors.json');
writeFileSync(binPath, buf.subarray(0, row * EMBED_DIM * 4));
writeFileSync(idxPath, JSON.stringify({ model: MODEL_ID, dim: EMBED_DIM, count: row, ids }));
console.log(`✅ wrote ${binPath} (${(row * EMBED_DIM * 4 / 1e6).toFixed(1)} MB) + ${idxPath} (${row} ids) in ${((Date.now() - t0) / 1000).toFixed(0)}s`);
