// 本地离线 embedding 内核：transformers.js + int8 多语模型（multilingual-e5-small）。
// 只做一件事：把文本编码成归一化向量。技能向量离线预计算(precompute-skill-vectors.mjs)，
// 运行时只给「用户这句话」算一次向量，再和预计算好的技能向量做余弦排序（skill-router.mjs）。
// e5 约定：查询前缀 "query: "，被检索文本前缀 "passage: "。
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
export const MODEL_ID = process.env.BIODSH_EMBED_MODEL || 'Xenova/multilingual-e5-small';
export const EMBED_DIM = 384;

let _extractorPromise = null;

async function getExtractor() {
  if (_extractorPromise) return _extractorPromise;
  _extractorPromise = (async () => {
    const { pipeline, env } = await import('@huggingface/transformers');
    // 模型缓存目录：默认放在本模块同级 models 下，随 resources 一起分发；离线加载。
    // 注意：故意不用 .models（点开头隐藏目录）——tauri 打包资源时对点目录的收录不稳,
    // 用普通目录名确保模型一定被塞进 exe/dmg。
    env.cacheDir = process.env.BIODSH_EMBED_CACHE || path.join(__dirname, 'models');
    env.localModelPath = env.cacheDir;
    // 国内直连 huggingface.co 常超时：默认走 hf-mirror.com（可用 BIODSH_HF_MIRROR 覆盖）。仅下载时用到，离线加载不影响。
    env.remoteHost = process.env.BIODSH_HF_MIRROR || 'https://hf-mirror.com';
    if (process.env.BIODSH_EMBED_OFFLINE === '1') { env.allowRemoteModels = false; env.allowLocalModels = true; }
    env.backends.onnx.wasm ??= {};
    const dtype = process.env.BIODSH_EMBED_DTYPE || 'q8';
    return pipeline('feature-extraction', MODEL_ID, { dtype });
  })();
  return _extractorPromise;
}

/** 编码若干文本 → 归一化向量数组(number[][])。isQuery 决定 e5 前缀。 */
export async function embed(texts, isQuery = false) {
  const arr = Array.isArray(texts) ? texts : [texts];
  const prefix = isQuery ? 'query: ' : 'passage: ';
  const input = arr.map((t) => prefix + String(t ?? '').replace(/\s+/g, ' ').trim().slice(0, 512));
  const extractor = await getExtractor();
  const out = await extractor(input, { pooling: 'mean', normalize: true });
  return out.tolist();
}

export function cosine(a, b) {
  let s = 0;
  const n = Math.min(a.length, b.length);
  for (let i = 0; i < n; i++) s += a[i] * b[i];
  return s; // 向量已归一化 → 点积即余弦
}
