// 下载各平台 uv 二进制到 resources/bin/<platform-arch>/，打包时按目标平台带入。
// 用法：node scripts/fetch-uv.mjs [--all] [--version 0.12.7]
import { existsSync, mkdirSync, chmodSync, rmSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const outRoot = path.join(here, '..', 'resources', 'bin');
const args = process.argv.slice(2);
const version = args.includes('--version') ? args[args.indexOf('--version') + 1] : '0.12.7';
const all = args.includes('--all');

const TARGETS = {
  'win32-x64': { asset: 'uv-x86_64-pc-windows-msvc.zip', bin: 'uv.exe' },
  'darwin-arm64': { asset: 'uv-aarch64-apple-darwin.tar.gz', bin: 'uv' },
  'darwin-x64': { asset: 'uv-x86_64-apple-darwin.tar.gz', bin: 'uv' },
  'linux-x64': { asset: 'uv-x86_64-unknown-linux-gnu.tar.gz', bin: 'uv' },
};
const wanted = all ? Object.keys(TARGETS) : [`${process.platform}-${process.arch}`];
const mirror = process.env.UV_RELEASE_MIRROR ?? 'https://github.com/astral-sh/uv/releases/download';

for (const key of wanted) {
  const t = TARGETS[key];
  if (!t) { console.warn(`skip unsupported ${key}`); continue; }
  const dir = path.join(outRoot, key);
  const dst = path.join(dir, t.bin);
  if (existsSync(dst)) { console.log(`ok ${key} (cached)`); continue; }
  mkdirSync(dir, { recursive: true });
  const url = `${mirror}/${version}/${t.asset}`;
  console.log(`fetch ${url}`);
  const archive = path.join(dir, t.asset);
  // 用 curl 而不是 fetch：curl 会遵守系统代理设置，且带重试。
  execFileSync('curl', ['-L', '--retry', '5', '--retry-delay', '3', '--connect-timeout', '30', '-o', archive, url], { stdio: 'inherit' });
  if (t.asset.endsWith('.zip')) {
    execFileSync('python3', ['-c', `import zipfile,sys; z=zipfile.ZipFile(sys.argv[1]); [open(sys.argv[2]+'/'+n.split('/')[-1],'wb').write(z.read(n)) for n in z.namelist() if not n.endswith('/')]`, archive, dir], { stdio: 'inherit' });
  } else {
    execFileSync('tar', ['-xzf', archive, '--strip-components=1', '-C', dir], { stdio: 'inherit' });
  }
  rmSync(archive);
  if (t.bin === 'uv') chmodSync(dst, 0o755);
  console.log(`ok ${key}`);
}
