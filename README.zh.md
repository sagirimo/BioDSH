<div align="center">

# BioDSH

**给医生和湿实验科研人员的生信分析智能体：用一句话描述分析，直接拿结论，不用写代码。**

[English](README.md) · [下载](#下载) · [dsh 插件](#在-deepseek-harness-里用) · [实验结果](#实验结果)

[![release](https://img.shields.io/github/v/release/sagirimo/BioDSH?include_prereleases&label=release)](https://github.com/sagirimo/BioDSH/releases)
[![npm](https://img.shields.io/npm/v/dsh-biodsh?label=dsh-biodsh)](https://www.npmjs.com/package/dsh-biodsh)
[![license](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

</div>

把数据（单细胞 `h5ad`、表达矩阵、临床表格、基因列表……）放进来，问一句「响应组和非响应组的 CD8A 表达有没有差异？」。智能体会读数据、选方法、写代码并运行，最后给出结论，同时附上图、表和每一步的完整记录。

BioDSH 在你自己的电脑上运行，基于 [DeepSeek Harness（dsh）](https://github.com/deepseek-ai/deepseek-harness)。它有两种形态：一键安装的**桌面版**，以及 **dsh 插件**（`dsh-biodsh`）。

## 优势

- **一句话进，结论出。** 不用写代码，也不用配环境。首次启动会自动装好 Python 分析环境（scanpy、anndata、pandas、statsmodels、matplotlib 等）。
- **用验证过的方法，而不是现编代码。** 内置 17 个官方分析技能：单细胞质控、聚类、注释、治疗响应，bulk RNA-seq limma-voom，KM/Cox 生存分析，稳健标准误回归，方差分析设计等。统计类技能逐项和 R 对照过，每个都有上万次比对（例如生存分析 101,587 次比对、零差异）。
- **自动挑技能。** 每次提问时，由模型从 17 个官方技能和 2000+ 社区技能中挑出最合适的一两个加载。上下文保持精简，也更省钱。
- **便宜。** 基于 DeepSeek 模型。在我们的分析题上，准确率和 Claude Code（Sonnet/Haiku）相当，每题成本低 3–13 倍（见[实验结果](#实验结果)）。
- **长任务一定有结果。** 收敛护栏防止智能体原地打转：先提醒它收尾，再要求直接作答，不会跑一晚上没有结果。
- **数据安全。** 原始文件从不改动，每次分析都写进一个新文件夹。离线模式只连本机或内网的模型，不发起任何外网请求，适合医院和实验室内网。
- **结果可追溯。** 每一步都写进只追加的会话日志，可以回看、导出，交给导师或审稿人。
- **可复用的工作流。** 做完的分析可以存成工作流，换一批数据一键重跑；也可以从已有的脚本、notebook 或方法学段落生成工作流。
- **模型随你选。** 支持 DeepSeek 官方 API、任意 OpenAI 兼容接口、本地或内网模型，可以同时配置多个。

## 下载

| 版本 | 平台 | 下载 |
| --- | --- | --- |
| **1.0.0 预览版**（新） | Windows 10/11 | [`BioDSH_1.0.0_x64-setup.exe`](https://github.com/sagirimo/BioDSH/releases/tag/desktop-tauri-v1.0.0-preview.1) |
| 0.3.0（稳定版） | Windows、macOS（Apple 芯片） | [最新发行版](https://github.com/sagirimo/BioDSH/releases/latest) |

- **1.0.0 预览版**是预发布版，已装的 0.3.0 不会被自动更新过去。它会覆盖安装 0.3.0，而 0.3.0 里的旧对话在 1.0 里可能打不开，重要项目请先备份。macOS 和 Linux 安装包随 1.0 正式版提供。
- **Windows**：安装包没有代码签名，首次运行时点「更多信息 → 仍要运行」。
- **macOS**：应用没有经过公证，系统可能提示「已损坏」。把它拖进「应用程序」后，在终端运行一次 `sudo xattr -cr /Applications/BioDSH.app` 即可。

稳定版会在后台检查更新，一键安装。更新包会校验签名，检查更新时不上传任何数据。

## 在 DeepSeek Harness 里用

如果你已经在用 dsh，可以不装桌面版，直接把 BioDSH 智能体装成插件：

```bash
dsh plugin --profile web add dsh-biodsh
```

也可以在 dsh 网页里装：**插件 → 安装 → `dsh-biodsh`**。装好后重启 dsh，在智能体预设菜单里选 **BioDSH**，你原有的预设不受影响。插件需要 dsh 0.2.1 及以上，且装有 pnpm。详见 [`packages/dsh-biodsh`](packages/dsh-biodsh)。

如果只想要技能：官方技能是标准的 dsh `SKILL.md` 文件夹，运行 `./scripts/install-into-dsh.sh <你的项目>/.agents/skills` 即可复制进去（Windows 用 `install-into-dsh.ps1`）。

## 实验结果

以下是我们开发阶段测得的粗略数字，完整报告整理中。

**逐层叠加带来的提升**：74 道 BixBench 开放作答分析题，确定性判分，所有配置使用同一个 DeepSeek 模型。

| 配置 | 答对 |
| --- | --- |
| 纯聊天（模型直接回答，不运行任何代码） | 6/74（8%） |
| BioDSH 不带技能 | 38/74（51%） |
| BioDSH 带技能 | 46/74（62%） |

**和编程智能体对比**：38 道数据分析题，用参考答案回放判分，所有智能体拿到的题面完全相同。

| 智能体 | 答对 | 每题成本 |
| --- | --- | --- |
| **BioDSH**（DeepSeek V4 Flash） | 35/38（2 次平均） | 约 $0.02–0.05 |
| Claude Code · Opus | 37/38 | 约 $0.32 |
| Claude Code · Sonnet | 35/38 | 约 $0.13 |
| Claude Code · Haiku | 34/38 | — |
| Codex · Astra / Sol / Luna | 37 / 37 / 30 | 约 $0.44（Astra） |

在最难的几道题上，收敛护栏把 8 次超时降到 0 次。程序化工具调用（默认预设 **BioDSH (PTC)**）把步数中位数从 23 降到 16，准确率不变。

说明：以上是 1–2 次运行的结果，单次之间会有 ±2 题左右的波动；38 题题库是我们自建的。在公开数据集上的测试（BixBench 全量 205 题、BioMed-AQA）正在进行中。

## 从源码构建

需要 Node.js 22+、Rust（stable）以及 [Tauri 依赖](https://tauri.app/start/prerequisites/)。

```bash
cd desktop
npm ci
node scripts/stage-dsh.mjs     # dsh 运行时 + dsh-biodsh 插件
node scripts/sync-skills.mjs   # 官方技能 → resources
npm run tauri dev              # 或 npm run tauri build
```

| 路径 | 内容 |
| --- | --- |
| `desktop/` | 桌面版：React 界面（`src/`）、Rust 后端（`src-tauri/`）和构建脚本。 |
| `packages/dsh-biodsh/` | `dsh-biodsh` 插件：BioDSH 预设、技能精选和收敛护栏。 |
| `biodsh-core/skills/` | 官方技能。 |

## 许可

BioDSH 自身代码采用 [MIT](LICENSE) 许可。随附组件（DeepSeek Harness、社区技能、Python 包）沿用各自的许可。

BioDSH 是基于 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) 的独立项目，与 DeepSeek 没有隶属或背书关系。
