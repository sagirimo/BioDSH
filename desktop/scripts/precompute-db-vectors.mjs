// 预计算数据库目录每个库的向量(name+描述+标签+示例),供 DatabaseView 语义搜索。
// 产物 resources/databases/vectors.json:{ dim, ids:[dbId], vecs:[[..384..]] }。31 个库,文件很小,随包分发。
// 用法:node scripts/precompute-db-vectors.mjs (需 resources/embed 已装 + 模型已在 resources/embed/models)
import { readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { embed, EMBED_DIM } from '../resources/embed/embed-core.mjs';

const root = path.dirname(fileURLToPath(import.meta.url));
const cat = JSON.parse(readFileSync(path.join(root, '..', 'resources/databases/catalog.json'), 'utf8'));
const ids = [], texts = [];
for (const c of cat.categories) {
  for (const d of c.databases) {
    ids.push(d.id);
    // passage 文本:名字(中英)+ 分类 + 描述 + 标签 + 示例,尽量覆盖用户可能的问法
    texts.push([d.name, d.name_en, c.name, d.desc, (d.tags || []).join(' '), (d.examples || []).join(' ')].filter(Boolean).join('。'));
  }
}
const vecs = await embed(texts, false); // passage
const out = { dim: EMBED_DIM, ids, vecs: vecs.map((v) => Array.from(v).map((x) => Math.round(x * 1e5) / 1e5)) };
writeFileSync(path.join(root, '..', 'resources/databases/vectors.json'), JSON.stringify(out));
console.log(`db vectors: ${ids.length} 个库, dim=${out.dim} → resources/databases/vectors.json`);
