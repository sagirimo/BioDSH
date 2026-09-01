// 下载官方 Node 运行时到 resources/node/<platform-arch>/，作为 dsh 的专用解释器打进安装包。
// 原因：dsh 需要 `node --expose-internals`，而打包后的 Electron 内置 Node 不接受这个开关。
// 用法：node scripts/fetch-node.mjs [--all] [--version 24.18.1]
import { existsSync, mkdirSync, rmSync, readdirSync, renameSync, chmodSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const outRoot = path.join(here, '..', 'resources', 'node');
const args = process.argv.slice(2);
const version = args.includes('--version') ? args[args.indexOf('--version') + 1] : '24.18.1';
const all = args.includes('--all');
const mirror = process.env.NODE_DIST_MIRROR ?? (process.env.CI ? 'https://nodejs.org/dist' : 'https://npmmirror.com/mirrors/node');

const TARGETS = {
  'win32-x64': { asset: `node-v${version}-win-x64.zip`, bin: 'node.exe' },
  'darwin-arm64': { asset: `node-v${version}-darwin-arm64.tar.gz`, bin: 'bin/node' },
  'darwin-x64': { asset: `node-v${version}-darwin-x64.tar.gz`, bin: 'bin/node' },
  'linux-x64': { asset: `node-v${version}-linux-x64.tar.xz`, bin: 'bin/node' },
};
const wanted = all ? Object.keys(TARGETS) : [`${process.platform}-${process.arch}`];

for (const key of wanted) {
  const t = TARGETS[key];
  if (!t) { console.warn(`skip unsupported ${key}`); continue; }
  const dir = path.join(outRoot, key);
  const dst = path.join(dir, t.bin);
  if (existsSync(dst)) { console.log(`ok ${key} (cached)`); continue; }
  rmSync(dir, { recursive: true, force: true });
  mkdirSync(dir, { recursive: true });
  const url = `${mirror}/v${version}/${t.asset}`;
  console.log(`fetch ${url}`);
  const archive = path.join(dir, t.asset);
  execFileSync('curl', ['-L', '--retry', '5', '--retry-delay', '3', '--connect-timeout', '30', '-o', archive, url], { stdio: 'inherit' });
  if (t.asset.endsWith('.zip')) {
    // zip 里只留 node.exe（其余 npm 等不需要）
    execFileSync('python3', ['-c', `import zipfile,sys; z=zipfile.ZipFile(sys.argv[1]); n=[x for x in z.namelist() if x.endswith('/node.exe')][0]; open(sys.argv[2]+'/node.exe','wb').write(z.read(n))`, archive, dir], { stdio: 'inherit' });
  } else {
    const flag = t.asset.endsWith('.xz') ? '-xJf' : '-xzf';
    execFileSync('tar', [flag, archive, '--strip-components=1', '-C', dir, `node-v${version}-${key.replace('win32', 'win')}/bin/node`], { stdio: 'inherit' });
  }
  rmSync(archive);
  // 只保留 node 可执行文件
  for (const n of readdirSync(dir)) if (n !== 'bin' && n !== 'node.exe') rmSync(path.join(dir, n), { recursive: true, force: true });
  if (t.bin !== 'node.exe') chmodSync(dst, 0o755);
  console.log(`ok ${key}`);
}
