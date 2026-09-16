// 把一句查询编码成归一化向量(供数据库/技能的语义搜索)。离线用包里的 e5 模型。
// 用法:node embed-query.mjs "用户输入的问题"  → stdout 打印 JSON 数组(384 维)。
import { embed } from './embed-core.mjs';
const q = process.argv.slice(2).join(' ').trim();
if (!q) { process.stdout.write('[]'); process.exit(0); }
try {
  const [v] = await embed([q], true); // isQuery=true → e5 "query:" 前缀
  process.stdout.write(JSON.stringify(Array.from(v)));
} catch (e) {
  process.stderr.write(String(e && e.message || e));
  process.exit(1);
}
