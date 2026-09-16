// 轻量差量更新:生成 delta.json —— 列出这次更新相对上一版真正变化的预编译文件。
// 多数更新只有主程序 exe 变(前端 JS 已嵌进 exe;模型/dsh 运行时/技能不变)→ 用户只需下 ~10MB。
// 资源(模型/技能/dsh 运行时)也变时(跨大版本),标记 fullRequired=true,app 端回退整包安装器。
//
// 用法:node scripts/build-delta.mjs --version 0.2.6 \
//         --exe src-tauri/target-bundle/release/biodsh-desktop.exe \
//         --base <上一版 delta.json 或 files-manifest.json,可选> \
//         --out src-tauri/target-bundle/release/delta.json
// 产物 delta.json 由发布脚本再用 minisign 私钥签名(delta.json.sig),app 端验签同一把公钥。
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync, statSync, existsSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import path from 'node:path';

const args = process.argv.slice(2);
const opt = (k, d) => (args.includes(k) ? args[args.indexOf(k) + 1] : d);
const version = opt('--version');
const exe = opt('--exe', 'src-tauri/target-bundle/release/biodsh-desktop.exe');
const basePath = opt('--base');
const out = opt('--out', 'src-tauri/target-bundle/release/delta.json');
const owner = opt('--owner', 'sagirimo');
const repo = opt('--repo', 'BioDSH');
const signKey = opt('--sign');        // 传私钥路径则顺带用 tauri signer 签出 <out>.sig(空密码)
if (!version) { console.error('必须 --version'); process.exit(1); }

const sha256 = (p) => createHash('sha256').update(readFileSync(p)).digest('hex');
const relUrl = (name) => `https://github.com/${owner}/${repo}/releases/download/desktop-tauri-v${version}/${name}`;

// v1:只跟踪主程序 exe(覆盖 95% 的代码更新)。资源清单后续接入(--base 比对 sha 决定是否 fullRequired)。
if (!existsSync(exe)) { console.error(`找不到 exe:${exe}`); process.exit(1); }
const exeName = path.basename(exe); // biodsh-desktop.exe
const files = [{
  target: 'biodsh-desktop.exe',           // 安装目录下的相对路径
  url: relUrl(exeName),
  sha256: sha256(exe),
  size: statSync(exe).size,
}];

// 若给了上一版清单,比对判断是否需要整包(暂只对比 exe;资源比对留待接入资源清单)
let fullRequired = false;
if (basePath && existsSync(basePath)) {
  try {
    const base = JSON.parse(readFileSync(basePath, 'utf8'));
    // 预留:若资源清单存在且有差异 → fullRequired=true
    void base;
  } catch { /* 上一版清单读不了就当普通差量 */ }
}

const delta = {
  version,
  minFromVersion: '0.2.0',                 // 低于此版本没有轻量更新器,走整包
  fullRequired,                            // true → app 端回退 tauri 整包安装器
  fullInstallerUrl: relUrl(`BioDSH_${version}_x64-setup.exe`),
  files,
  generatedAt: new Date().toISOString(),
};
writeFileSync(out, JSON.stringify(delta, null, 2));
console.log(`delta.json 生成:${out}`);
console.log(`  version=${version} files=${files.length} fullRequired=${fullRequired}`);
console.log(`  exe sha256=${files[0].sha256.slice(0, 16)}… size=${(files[0].size / 1e6).toFixed(1)}MB`);

// 用 tauri signer(与 tauri updater 同一把 minisign 私钥)签 delta.json → <out>.sig(空密码)。
// app 端 updater::verify_sig 会 base64 解一层拿到 minisign 文本再验(已本地 roundtrip 验证)。
if (signKey) {
  if (!existsSync(signKey)) { console.error(`找不到签名私钥:${signKey}`); process.exit(1); }
  // 直接用当前 node 跑 tauri CLI 的 JS 入口:跨平台,且 args 数组能原样传空字符串密码(-p '');
  // 不走 .bin/tauri.cmd(execFileSync 起不了 .cmd)也不走 shell(shell 会丢掉空字符串参数)。stdin 忽略防交互卡住。
  const tauriJs = path.join('node_modules', '@tauri-apps', 'cli', 'tauri.js');
  execFileSync(process.execPath, [tauriJs, 'signer', 'sign', '-f', signKey, '-p', '', out], { stdio: ['ignore', 'inherit', 'inherit'] });
  if (!existsSync(`${out}.sig`)) { console.error('签名失败:没生成 .sig'); process.exit(1); }
  console.log(`  已签名 → ${out}.sig`);
}
