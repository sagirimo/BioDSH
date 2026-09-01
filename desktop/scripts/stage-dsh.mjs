// 把 dsh 运行时（@deepseek-ai/dsh 及其全部依赖）单独装到 dsh-runtime/node_modules，
// 打包时整棵树作为 extraResources 原样带走。不用 electron-builder 的依赖裁剪：它会漏掉 dsh 动态按名加载的插件包。
import { mkdirSync, writeFileSync, readFileSync, rmSync, existsSync, readdirSync, statSync } from 'node:fs';
import { execSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.join(here, '..');
const pkg = JSON.parse(readFileSync(path.join(root, 'package.json'), 'utf8'));
const version = pkg.devDependencies['@deepseek-ai/dsh'];
const dir = path.join(root, 'dsh-runtime');
mkdirSync(dir, { recursive: true });
writeFileSync(path.join(dir, 'package.json'), JSON.stringify({ name: 'biodsh-dsh-runtime', private: true, dependencies: { '@deepseek-ai/dsh': version } }, null, 2));
const registry = process.env.NPM_REGISTRY ?? (process.env.CI ? 'https://registry.npmjs.org/' : 'https://registry.npmmirror.com/');
const platformsOnly = process.argv.includes('--platforms-only');
if (!platformsOnly) {
  console.log(`staging @deepseek-ai/dsh@${version} into dsh-runtime/ (registry ${registry})`);
  execSync(`npm install --omit=dev --no-audit --no-fund --no-package-lock --loglevel=error --registry=${registry}`, { cwd: dir, stdio: 'inherit', env: { ...process.env, NODE_OPTIONS: '--max-old-space-size=4096' } });
}

// 平台原生包：koffi / ripgrep / sharp / node-addon-require-builtin 等把二进制拆成 `<name>-<os>-<arch>` 的 optionalDependencies，
// npm 只会装当前平台的那份。这里把其它目标平台的也装进来，让一棵树能在 win/mac/linux 上都跑。
const TARGETS = (process.env.BIODSH_TARGETS ?? 'win32-x64,darwin-arm64,darwin-x64,linux-x64').split(',');
const wanted = new Set();
function walk(d, depth = 0) {
  if (depth > 3 || !existsSync(d)) return;
  for (const n of readdirSync(d)) {
    const p = path.join(d, n);
    if (n.startsWith('@')) { walk(p, depth); continue; }
    const pj = path.join(p, 'package.json');
    if (existsSync(pj)) {
      let j; try { j = JSON.parse(readFileSync(pj, 'utf8')); } catch { continue; }
      for (const [name, ver] of Object.entries(j.optionalDependencies ?? {})) {
        for (const t of TARGETS) {
          const [os, arch] = t.split('-');
          if (name.includes(`${os}-${arch}`) || name.includes(`${os === 'win32' ? 'win32' : os}-${arch}`)) wanted.add(`${name}@${ver}`);
        }
      }
      const nm = path.join(p, 'node_modules');
      if (existsSync(nm) && statSync(nm).isDirectory()) walk(nm, depth + 1);
    }
  }
}
walk(path.join(dir, 'node_modules'));
const missing = [...wanted].filter((spec) => !existsSync(path.join(dir, 'node_modules', spec.slice(0, spec.lastIndexOf('@')))));
console.log(`platform packages: ${wanted.size} wanted, ${missing.length} to install`);
if (missing.length) {
  execSync(`npm install --no-save --force --omit=dev --no-audit --no-fund --no-package-lock --loglevel=error --registry=${registry} ${missing.join(' ')}`, { cwd: dir, stdio: 'inherit', env: { ...process.env, NODE_OPTIONS: '--max-old-space-size=4096' } });
}
// .bin 里全是符号链接，运行时用不到；在 WSL 装出来的链接会让 Windows 侧 7-Zip 打包失败。
rmSync(path.join(dir, 'node_modules', '.bin'), { recursive: true, force: true });
console.log('ok');
