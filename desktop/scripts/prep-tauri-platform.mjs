// mac 有 arm64 / x64 两种，tauri.macos.conf.json 里固定引用 resources/{node,bin}/darwin-current；
// 这里按当前（或 --arch 指定的）架构把对应目录复制过去。Windows/Linux 的配置直接引用平台目录，不需要这一步。
import { cpSync, rmSync, existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const here = path.dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const arch = args.includes('--arch') ? args[args.indexOf('--arch') + 1] : process.arch;
for (const kind of ['node', 'bin']) {
  const src = path.join(here, '..', 'resources', kind, `darwin-${arch}`);
  const dst = path.join(here, '..', 'resources', kind, 'darwin-current');
  if (!existsSync(src)) { console.error(`missing ${src} — run fetch-${kind === 'node' ? 'node' : 'uv'}.mjs --all first`); process.exit(1); }
  rmSync(dst, { recursive: true, force: true });
  cpSync(src, dst, { recursive: true });
  console.log(`${kind}: darwin-${arch} → darwin-current`);
}
