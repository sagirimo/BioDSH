<div align="center">

<a href="http://43.167.193.205"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/wordmark-dark.png"><img src="docs/wordmark-light.png" alt="BioDSH" height="60"></picture></a>

**面向医生与湿实验科学家的生信智能体桌面端——构建于 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) 之上。**

一切皆插件，分析只需一句话。

[English](README.md) · [官网](http://43.167.193.205) · [下载](https://github.com/sagirimo/BioDSH/releases/latest) · [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)

</div>

---

BioDSH 是一个一键安装的桌面软件，把生信智能体交到不用命令行的人手里。把数据拖进去，用大白话说你想干什么，直接读结论。全程在本地运行，不改动你的原始文件，也可以在医院/实验室内网里完全离线运行。

它是对 **DeepSeek Harness（`dsh`）** 的一层友好封装：智能体运行时、插件系统、可复现的会话日志都来自 `dsh`。BioDSH 在此之上加了面向医生的界面、一个生信技能商店、一套自带的 Python 分析环境，以及若干经过评测的官方技能。

<div align="center">
<img src="docs/screenshot-store.png" width="49%" alt="技能商店" />
<img src="docs/screenshot-data.png" width="49%" alt="数据结果" />
</div>

## 下载

到 [**最新发行版**](https://github.com/sagirimo/BioDSH/releases/latest) 拿安装包：

| 平台 | 文件 | 说明 |
| --- | --- | --- |
| Windows 10/11 | `BioDSH_*_x64-setup.exe` | 双击安装。首次运行点「更多信息 → 仍要运行」。 |
| macOS 12+（Apple 芯片） | `BioDSH_*_aarch64.dmg` | 未签名——见下方 macOS 说明。 |
| Linux | `BioDSH_*_amd64.deb` | Debian/Ubuntu。 |

> **macOS 用户注意:** BioDSH 没有 Apple 开发者签名,macOS 可能提示 *「已损坏,无法打开」*。**这不是真的损坏**,是 Gatekeeper 拦截未签名应用。把 BioDSH 拖进**「应用程序」**,然后打开**「终端」**运行:
>
> ```bash
> sudo xattr -cr /Applications/BioDSH.app
> ```
>
> 输入开机密码(不显示,直接回车)后再打开 BioDSH 即可。每次安装只需做一次。

软件会在后台检查新版本，发现后提供一键 **下载 → 校验签名 → 安装 → 重启**。不上传任何东西；更新源就是本仓库的 `latest.json`。

## 能做什么

- **一切皆插件。** 收编了开源社区里最好的生信技能——2,000+ 社区技能按 10 个领域整理——外加几个评测过、可离线、可复现的官方技能。想要的能力，点一下就装上。
- **每一次分析都有迹可循。** 模型看到的一切都写进只追加的会话日志。对话里中间步骤折成一行、可逐级展开；对话可导出给导师或审稿人。
- **四个真实示范项目** 随软件自带：单细胞分析与作图、文献调研、公共数据库抓取、电脑控制与 Zotero。
- **不用编程。** 自带一键 Python 分析环境（scanpy、anndata、pandas、matplotlib）；需要它的技能装一次即可。
- **电脑控制。** 智能体能用真实的鼠标键盘操作其它软件（Excel、Prism、SPSS……），屏幕上有醒目的「BioDSH 正在控制电脑」提示。
- **数据安全与离线。** 原始文件从不改动，每次分析写进一个新子文件夹。纯离线模式只连本地或内网的模型接口，不发起任何外网请求。

## 工作原理

```
┌────────────────────────────────────────────┐
│  BioDSH（Tauri 桌面外壳）                    │
│  • 面向医生的界面（React）                   │
│  • 技能商店 · 数据页 · 分析环境              │
│  • 自带 Python + 官方技能                    │
│  ┌──────────────────────────────────────┐  │
│  │  DeepSeek Harness（dsh）              │  │
│  │  智能体运行时 · 插件 · 会话日志         │  │
│  └──────────────────────────────────────┘  │
└────────────────────────────────────────────┘
```

一个「技能」就是一个 `dsh` 插件：一个包含 `SKILL.md`（给智能体看的说明）和可选脚本的文件夹。官方技能在 [`biodsh-core/skills/`](biodsh-core/skills)，桌面 App 在 [`desktop/`](desktop)。

## 配合原版 DeepSeek Harness 使用

BioDSH 的官方技能就是标准的 dsh 原生 `SKILL.md` 技能——不需要 BioDSH 这个 App，原版 `dsh` 会自动识别。dsh 会扫描若干技能目录，最简单的是项目内的 `.agents/skills/`：

```bash
git clone https://github.com/sagirimo/BioDSH
cd BioDSH
# 把技能复制进你的 dsh 项目（或在该项目里直接跑，写入 ./.agents/skills）
./scripts/install-into-dsh.sh /你的/dsh项目/.agents/skills
#   加 --global 则装到 ~/.agents/skills
```

Windows 用 `scripts/install-into-dsh.ps1`。之后从这个工作区启动 `dsh`，BioDSH 的技能就能用了。（单细胞/作图类技能需要 PATH 上有带 scanpy、anndata、pandas、matplotlib 的 Python 环境。）

## 从源码构建

前置：**Node.js 22+**、**Rust（stable）**，以及各平台的 Tauri 依赖（Linux 上：`libwebkit2gtk-4.1-dev libappindicator3-dev librsvg2-dev patchelf`）。

```bash
cd desktop
npm ci                        # 安装依赖
node scripts/stage-dsh.mjs    # 准备 dsh 运行时
node scripts/sync-skills.mjs  # 官方技能 → resources + 商店目录
npm run tauri dev             # 运行
# 或完整打安装包：
npm run tauri build
```

发布配方在 [`docs/release.workflow.yml`](docs/release.workflow.yml)——把它复制到 `.github/workflows/release.yml`，再打一个形如 `desktop-tauri-v0.2.1` 的 tag，即可为所有平台构建安装包并发布带 `latest.json` 的发行版。自动更新签名需要两个仓库 Secret，见该文件顶部注释。

## 目录结构

| 路径 | 内容 |
| --- | --- |
| `desktop/` | Tauri 桌面 App——React 界面（`src/`）、Rust 后端（`src-tauri/`）、构建脚本（`scripts/`）、商店目录（`store/`）。 |
| `biodsh-core/skills/` | 随软件发布、经过评测的官方技能。 |
| `desktop/resources/` | 打包进软件的资源：分析环境规格、示范项目会话、辅助脚本。 |

## 许可

BioDSH 自身代码采用 [MIT](LICENSE)。打包及下载的组件——DeepSeek Harness、社区技能、Python 工具链与依赖包——各自保留其许可。

## 致谢

构建于 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)。BioDSH 是独立项目，与 DeepSeek 无隶属关系，也未获其背书。
