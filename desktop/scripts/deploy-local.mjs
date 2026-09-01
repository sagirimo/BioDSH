// 把本机构建结果直接同步到已安装的 BioDSH 目录（不走安装包）。
// 用法：node scripts/deploy-local.mjs [--full] [--install-dir "C:\...\BioDSH"] [--from src-tauri/target-bundle/release]
//   默认只同步程序本体 + 技能资源（秒级）；--full 连 dsh 运行时 / Node / uv 一起同步（几百 MB，只在这些变了时用）。
// Windows 下应用正在运行时 exe 被锁，脚本会先检查并提示。
import { cpSync, existsSync, statSync, copyFileSync, renameSync, rmSync, readFileSync, writeFileSync, readdirSync } from 'node:fs';
import { execSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const opt = (k, d) => (args.includes(k) ? args[args.indexOf(k) + 1] : d);
const full = args.includes('--full');
const from = path.resolve(here, '..', opt('--from', 'src-tauri/target-bundle/release'));
const installDir = opt('--install-dir', process.env.BIODSH_INSTALL_DIR ?? 'C:\\Users\\MOLIEX-DESKTOP\\Desktop\\BioDSH');
const onWsl = process.platform === 'linux' && existsSync('/mnt/c');
const toLocal = (win) => (onWsl ? '/mnt/c/' + win.replace(/^[A-Za-z]:\\/, '').replace(/\\/g, '/') : win);
const dst = toLocal(installDir);

if (!existsSync(dst)) { console.error(`安装目录不存在：${installDir}`); process.exit(1); }
const exe = path.join(from, 'biodsh-desktop.exe');
if (!existsSync(exe)) { console.error(`没有构建产物：${exe}（先 tauri build --no-bundle）`); process.exit(1); }

// 正在运行就不能覆盖 exe
try {
  const ps = onWsl ? '/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe' : 'powershell.exe';
  const out = execSync(`"${ps}" -NoProfile -Command "Get-Process biodsh-desktop -ErrorAction SilentlyContinue | Where-Object { $_.Path -like '*${installDir.split('\\').pop()}*' } | ForEach-Object { $_.Id }"`, { encoding: 'utf8' }).trim();
  if (out) { console.error(`BioDSH 正在运行（pid ${out}），请先关闭再同步。`); process.exit(2); }
} catch { /* 查不到进程就继续 */ }

const step = (label, fn) => { const t = Date.now(); fn(); console.log(`${label} ✓ ${((Date.now() - t) / 1000).toFixed(1)}s`); };
step('程序本体 biodsh-desktop.exe', () => {
  const target = path.join(dst, 'biodsh-desktop.exe');
  if (existsSync(target)) {
    // .bak 偶尔被 Windows 占用删不掉（杀毒扫描等）：删不掉就换个名字，攒多了下次再清
    let bak = target + '.bak';
    try { rmSync(bak, { force: true }); } catch { bak = `${target}.bak-${Date.now()}`; }
    try { renameSync(target, bak); } catch { /* 旧 exe 挪不动就直接覆盖 */ }
    for (const n of ['.bak', '.bak-']) void n; // 占位
  }
  copyFileSync(exe, target);
});
// 资源目录很大（community-skills 2000+ 文件夹），只在“指纹”变化时复制：skills 看 catalog.json，其余看目录 mtime
const walkStamp = (dir) => { let acc = 0, n = 0; const rec = (d) => { for (const e of readdirSync(d, { withFileTypes: true })) { const p = path.join(d, e.name); if (e.isDirectory()) rec(p); else { const st = statSync(p); acc += st.size + Math.floor(st.mtimeMs / 1000); n++; } } }; try { rec(dir); } catch { /* */ } return `${n}-${acc}`; };
// 资源以 desktop/resources 为准（构建输出里的副本是上次 tauri build 时拷的，可能过期）
const resSrc = (r) => path.join(here, '..', 'resources', r);
const fingerprint = (r) => { if (r === 'demos' || r === 'skills' || r === 'scripts') return walkStamp(resSrc(r)); const probe = r === 'community-skills' ? path.join(resSrc('skills'), 'catalog.json') : resSrc(r); try { const st = statSync(probe); return `${st.size}-${st.mtimeMs}`; } catch { return ''; } };
for (const r of ['skills', 'community-skills', 'bioenv', 'demos', 'scripts']) {
  const src = resSrc(r);
  if (!existsSync(src)) continue;
  const stamp = path.join(dst, `.${r}.stamp`);
  const fp = fingerprint(r);
  let prev = ''; try { prev = readFileSync(stamp, 'utf8'); } catch { /* 无 */ }
  if (prev === fp && existsSync(path.join(dst, r))) { console.log(`资源 ${r} 未变化，跳过`); continue; }
  step(`资源 ${r}`, () => { rmSync(path.join(dst, r), { recursive: true, force: true }); cpSync(src, path.join(dst, r), { recursive: true }); writeFileSync(stamp, fp); });
}
if (full) {
  for (const r of ['dsh', 'node', 'bin']) {
    const src = path.join(from, r);
    if (existsSync(src)) step(`运行时 ${r}`, () => { rmSync(path.join(dst, r), { recursive: true, force: true }); cpSync(src, path.join(dst, r), { recursive: true }); });
  }
}
console.log(`已同步到 ${installDir}（exe ${(statSync(exe).size / 1e6).toFixed(1)} MB，${new Date().toLocaleTimeString()}）`);
