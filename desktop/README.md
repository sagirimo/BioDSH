# BioDSH Desktop

> **v0.2 起改用 Tauri**（`src-tauri/`，Rust）：不再自带 Chromium，用系统 WebView（Windows WebView2 / macOS WKWebView），安装包从 245 MB 降到 ~100 MB。Electron 版（`src/main`、`electron-builder.yml`）暂留作对照，两者共用同一套 React 界面（`src/renderer`），差别只在桥接层：Electron 用 preload，Tauri 用 `src/renderer/src/tauri-bridge.ts`。
>
> Tauri 命令：`npm run tauri:dev` / `npm run tauri:build`（在 WSL 里给 Windows 打包：`node.exe node_modules/@tauri-apps/cli/tauri.js build --config '{"build":{"beforeBuildCommand":""}}'`，前端先用 `npx vite build --config vite.tauri.config.ts` 在 WSL 里构建）。mac 走 `.github/workflows/desktop-tauri.yml`（tag `desktop-tauri-v*`），arm64 与 x64 各出一个 dmg；`scripts/prep-tauri-platform.mjs` 负责把对应架构的 Node/uv 放到 `darwin-current`。

给不会敲命令的医生 / 湿实验科学家用的桌面版：**双击安装 → 填 API Key → 一键装好分析环境 → 在商店里点「获取」装技能 → 用白话对话做分析**。

- 内核：[DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) 的网页界面（`dsh web`），原样嵌在窗口里，不改一行 dsh 代码。
- 我们加的：左侧壳子（对话 / 技能商店 / 分析环境 / 设置）+ 首次引导 + 自带 `uv` 建 Python 生信环境 + 技能一键安装。
- 一切状态在 `~/BioDSH/`（`dsh-home/`、`bioenv/`、`workspace/`、`logs/`），删掉即彻底重置。

## 它是怎么工作的

| 事情 | 做法 |
|---|---|
| 启动智能体 | 主进程用**安装包自带的官方 Node 24**（`resources/node/`）起 `node --expose-internals dsh/bin.js web --port 0 --no-open`，读到 `dsh web: http://127.0.0.1:<port>` 后用 `WebContentsView` 贴进「对话」页。不用 Electron 内置 Node：打包后它不接受 `--expose-internals`，而 dsh 的 HMR/补丁热加载强依赖该开关 |
| API Key | 写入 `~/BioDSH/dsh-home/.credentials.yaml`（`DEEPSEEK_API_KEY: sk-…`），dsh 自己的设置页也认这份文件 |
| 分析环境 | 打包自带的 `uv`：`uv python install 3.12` → `uv venv` → `uv sync --frozen`（`resources/bioenv/uv.lock` 锁死版本）；国内默认走 npmmirror / 清华镜像 |
| 技能怎么被模型看到 | 「获取」= 把 `resources/skills/<id>` 复制到 `~/BioDSH/dsh-home/skills/<id>`，dsh 的 skill-filesystem 监听该目录并热加载 |
| 技能怎么跑 | 启动 dsh 时把 `bioenv/.venv/bin` 放到 `PATH` 最前，`python` 就是生信环境；安装时给 SKILL.md 追加一段「怎么运行」 |

## 开发

```bash
cd desktop
npm i                       # 依赖（.npmrc 已指向 npmmirror）
node scripts/sync-skills.mjs   # biodsh-core/skills → resources/skills + catalog.json
node scripts/fetch-uv.mjs      # 下载当前平台 uv（--all 下载全部平台）
node scripts/fetch-node.mjs    # 下载当前平台 Node 24 运行时（--all 全部平台）
node scripts/stage-dsh.mjs     # 把 @deepseek-ai/dsh 整棵依赖树装到 dsh-runtime/（打包原样带走）
npm run dev                    # 开发模式
npm run build && npx electron-builder --win   # 或 --mac / --linux
```

WSL 里跑 Electron 需要 `--no-sandbox`，并把 libnss3/libasound 放进 `LD_LIBRARY_PATH`（见 `.tools/electron-libs`）。调试截图：`BIODSH_SCREENSHOT="store=/tmp/a.png" electron .`。

## 发布

打 tag `desktop-v0.1.0` 触发 `.github/workflows/desktop-release.yml`，在 macOS / Windows / Linux 三个 runner 上出 `.dmg`（arm64 + x64）/ `.exe`（一键 NSIS，装到用户目录不需要管理员）/ `.AppImage`，自动挂到 GitHub Release。

- 未配置 Apple 证书时 dmg 未签名，macOS 用户首次需右键「打开」。
- Windows 未签名会弹 SmartScreen「更多信息 → 仍要运行」。

## 打包为什么这样做

- dsh 运行时不走 electron-builder 的依赖裁剪（会漏掉 dsh 按名动态加载的 19 个插件包），而是 `stage-dsh.mjs` 单独 `npm install --omit=dev` 一棵树，作为 `extraResources` 原样复制到 `resources/dsh/node_modules`。
- 安装包体积：Windows 约 240 MB（Electron 110 + Node 90 + dsh 依赖 250 压缩后）。

## 社区技能收编

`scripts/harvest_skills.py` 扫描 `../competitors/` 下各家 agent 技能库（ClawBio、GPTomics-bioSkills、MemOmics、SciAgent、BioHarness、hcls-agent-skills、omics-skills、OmicVerse、PantheonOS、awesome-bio-agent-skills 等）：解析 SKILL.md frontmatter → 过滤非生信 → 按内容哈希去重（原始仓优先于聚合仓，同名不同内容加来源后缀）→ 统一分类 → 复制到 `resources/community-skills/<id>/`（单文件 ≤300KB、目录 ≤3MB），索引写到 `store/community-index.json`；`sync-skills.mjs` 把它合并进 `catalog.json`，商店里以「社区收编」层展示（标来源仓、许可证、是否含脚本，明确写「未经 BioDSH 评测」）。

- 社区技能的 SKILL.md 会被改写 `name`＝目录 id（dsh 要求 kebab-case 且同层唯一），并在安装时追加一段「桌面版怎么跑」说明（python/uv 已在 PATH）。
- `competitors/` 与 `resources/community-skills/` 都不入库；CI 出包前需要先 clone 上游仓再跑一遍 harvest（待接入）。

## 商店目录

`store/skill-meta.json` 维护每个技能的中文名、白话简介、分类、图标、证据；`scripts/sync-skills.mjs` 把它和 `biodsh-core/skills/*/skill.json`、`SKILL.md` frontmatter 合成为 `resources/skills/catalog.json`。分数只写评测记录里真实存在的数字。
