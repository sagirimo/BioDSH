# BioDSH Desktop 更新记录

版本号对应 GitHub Release tag `desktop-tauri-v<版本>`；安装包由 CI（`.github/workflows/desktop-tauri.yml`）在打 tag 后自动构建 Windows / macOS(arm64+x64) / Linux 三平台。

---

## 0.3.0

**与 dsh 解耦(正交化)—— 这是本版核心**
- 打包的 dsh 运行时升级到 **0.1.5**。同时把 BioDSH 对 dsh 的改动全部搬到**官方扩展面**上,让今后 dsh 升级不再动辄破坏 BioDSH:
  - **技能语义路由改成官方 cordis 插件**(`@biodsh/skill-router`),订阅 `agent/pre-step`、包装官方 `skills` 服务做 top-K 重排,不再打补丁改 dsh 源码。
  - **人设(persona)改走全局 `system-prompt` loader**,不再手搓 agent 预设(0.1.5 预设 schema 变了,旧写法会挂)。
- 新增兼容自测 `dsh-compat-test.mjs`:换 dsh 版本时一键跑鉴权/会话/工作区矩阵,红了才补。

**修复**
- **SSE 容忍缺 `[DONE]`**:自建 / 离线 OpenAI 兼容端点收尾不发 `data: [DONE]` 时,不再整轮 `STREAM_CLOSED`,收过正文就正常收尾。
- 升级时清掉不在本版的旧范例,避免 Mac 上新旧范例并存。
- 更新检查在 `latest.json` 缺当前平台条目时显示「已是最新」,不再报红。

**数据库**
- 新增 **CoMMpass(MMRF 多发性骨髓瘤)**队列到癌症队列目录。

---

## 0.2.6

**数据库(重做)**
- 目录改为**按研究域分类分层**(11 类 46 库),不再平铺;每个库配白话说明 + 示例问题 + 官网。
- **智能语义搜索**:用包里的 e5 模型对你输入的问题算向量、匹配最相关的数据库(不再是摆设);即时词法筛 + 回车语义搜索。
- 每个库接**真实社区技能**,「让智能体抓取」按技能流程成体系地做(不再只一句提示词)。
- 大幅补强**公共健康队列**(面向临床/流行病学):老年老龄化(CHARLS/CLHLS/ELSA/HRS/SHARE/KLoSA/LASI/CRELES/MHAS)、膳食营养(NHANES/KNHANES/CHNS/NHIS)、青少年(Add Health/GSHS)、重症(MIMIC/eICU),动作为「提取变量→队列研究」。

**分析模块**
- 数据文件改为卡片式,直接列出**推荐分析动作**(按类型:单细胞质控/聚类/注释、表格描述统计/组间比较/相关性…),一点即做,不再只有一个泛按钮。

**修复**
- 严重:`session/prompt` 缺 `requestId` 被 dsh 0.1.2 拒 →「数据库/让智能体分析」点了没反应,已修。
- 严重:dsh 流式工具调用身份被空值覆盖(`unknown tool ""`,走 OpenAI 兼容中转触发)——上游修在 master 未发版,已在打包 dsh 内打补丁(acceptIdentity + call-<index> 兜底 id)。
- 对话页顶部两条 header 重复/标题截断 → 隐藏 dsh 冗余会话栏,只留一条干净的栏。

**范例(全部重做)**
- 4 个范例**全部在当前 dsh 0.1.2 上重新真跑**、去掉编号、每个只做一件事、一眼看明白:**单细胞数据一键体检**、**临床表格自动统计与作图**、**基因列表富集分析出图**、**文献速览·代表文献成表**。每个都带真数据 + 成品图表/表格 + 完整对话记录(步数/工具/图齐全),打开即读全过程,也可到分析页在自己数据上照着跑。
- 修复升级后范例对话变**空**的问题:旧版本导入时只建了空壳会话(只有种子记录),本版改为真正导入对话内容,并自动清掉遗留的空壳/旧编号范例。
- 升级到本版会显示一次性提示:你**自己**的旧对话可能显示异常、新对话不受影响、如何衔接。

**更新方式**
- 新增**轻量差量更新**:之后的更新只下载变化的部分(约 10MB),不再每次下整包;失败自动回退整包安装。

## 0.2.5

- 彻底修复升级 dsh 0.1.2 后「新增本地文件夹/项目显示"选择工作区"、用不了」——改为读 dsh 原生 `workspace.json` 真实工作区,并把老项目一次性迁移进来,会话正确绑定工作区。
- 修 dsh 子 webview 的原生文件/文件夹选择框被 Tauri 拖放拦截吞掉的问题。
- embedding 模型随安装包分发的目录修正(确保离线语义路由的模型一定在包里)。
- 首次采用「本机签名打包 + REST API 发布」流程(省 CI 额度);CI 改为 macOS 按需构建。

## 0.2.4

**技能商店 UI**
- 小类（subcategory）改为**整行横向排列**（可横向滚动），不再和右侧控件挤在一行。
- 「评分说明」按钮 + 「N 个 / 未经评测」计数 + 安装目录说明，统一**下沉到列表最底部**，顶部只留分类筛选，界面更清爽。

**设置页 UI**
- 各分区大段说明小字改为**右上角圆形 i 图标 + 悬停气泡**（`InfoDot`），离线模式、MCP 的免责说明同样收进图标。以后新页面沿用这一规范。

**技能全量可用 + 语义路由（无需手动安装）**
- 全部技能（官方 12 走 `customSkillDirs`、社区 2174 走 `DSH_BUNDLED_SKILL_DIR`）都挂成可发现的技能根，**无需复制安装**即可被智能体调用；商店里一律显示「✓ 可用」，去掉了「获取/未安装」「已安装」标签页与批量安装按钮。
- 给 `dsh-tool-skill` 打补丁（`scripts/patch-dsh-skill-router.mjs`）：渲染 `<available_skills>` 目录前，按**最新一条用户消息**对全部候选技能做相关性排序，只把 top-K（`BIODSH_SKILL_CATALOG_MAX`，默认 40）放进上下文（官方/已装恒留，社区过阈值）——量大管饱又省 token/钱。
- **本地 embedding 向量匹配（离线）**：`resources/embed/`(transformers.js + int8 多语模型 multilingual-e5-small)对「用户这句话」算查询向量，与离线预计算的 2186 个技能向量(`skill-vectors.bin`)做余弦排序取 top-K；embedding 不可用时自动回退词法匹配。首次约 1.3s(载模型)、之后每次 ~7ms。弱匹配门控：跟任何技能都不太沾边时只放少量。模型经 hf-mirror 下载、随 `resources/embed` 分发、运行时纯离线加载。
- 技能数 ≤ 上限时行为与旧版一致（回退：删掉 `DSH_BUNDLED_SKILL_DIR` / `customSkillDirs` 即恢复旧逻辑）。

**技能商店 UI（续）**
- 小类横条**隐藏滚动条**，改为鼠标按住拖拽 / 滚轮横向滑动（像手指滑）。

**设置 UI（续）**
- 说明改到**每个字段后面的圈-i**（不再只在分区顶部/底部一个）；纯离线模式表单重排更清爽。

**运行时：适配 dsh 0.1.2-rc.1（web /api RPC 协议大改）**
- 0.1.2 重写了 web /api：①新增 token→签名 cookie 鉴权;②路径改 `/api/<ns>/<method>`(斜杠);③信封 `payload={args:{<wire>:值}}`;④**去掉 workspace 模型**,`session/list` 返回扁平会话列表(带 cwd),「项目」=会话按 cwd 分组。旧 app 的 RPC 会全 401/404 → 项目列不出来(数据没丢)。
- 解法：在 `lib.rs` 加**兼容层 shim**（renderer 不动）——`dsh_call` 把旧方法翻译到 0.1.2：`workspace.list`→`session/list` 按 cwd 分组重塑;`session.list` 透传;`session.create/rename/prompt`→对应 `session/*`;cookie 交换（读 303 上的 Set-Cookie，ureq 禁跟随重定向）+ 401 重试 + URL 源解析加固。
- **项目/范例名称**：0.1.2 去掉了 workspace 标题字段，新增**项目标题库**(`dsh-home/storages/biodsh-project-titles.json`)兜住 `workspace.create/rename`；**一次性升级迁移**把旧 `workspace.json` 的用户项目名 + 范例名搬进来 → 老用户升级后项目/范例仍显示原名(而非文件夹名)，纯读旧数据不动内容。范例复制为增量式(不覆盖用户改过的文件)。

**稳定性**
- dsh 步数护栏（`scripts/patch-dsh-guard.mjs`，`DSH_MAX_STEPS` 默认 60）：智能体连续执行超上限自动优雅中止，防止无限循环烧费用 / 截断（源于 benchmark 发现的 runaway 缺陷）。

**打包**
- 安装包仅打包 `desktop/resources/*` 与 `desktop/dsh-runtime/node_modules`；不会包含用户本地运行目录（`~/BioDSH`、工作区、bioenv 实际数据等）。

> 待补：本轮之前反馈的若干 bug 修复（见提交记录）。

---

## 0.2.3

- 多模型提供商预设（DeepSeek / OpenAI / Moonshot / 通义 / 智谱 / 硅基流动），离线模式可接内网 OpenAI 兼容端点或课题组 Linux dsh 服务器。
- 技能商店：基于 benchmark 的技能评分体系 + 应用内「评分说明」弹窗（五维加权，公认 benchmark scIB/BEELINE/DUD-E/CASF/BixBench 的接入说明，诚实标注「未评测 ≠ 编造」）。
- 新增专项技能：虚拟敲除、分子对接、分子动力学。
- 每次启动的 Star 提示（可关闭 / 「已 Star」永久关闭）；首次引导第 3 步引导用户 Star 仓库。
- 修复：侧栏右键菜单被变换祖先裁剪（改用 body portal 渲染）；Star 提示打开时隐藏 dsh 子 webview 避免原生层遮挡。
- 加固：应用内升级不再损坏 dsh 运行时 / 丢失历史。
- 站点：下载按钮指向 releases 页；macOS「已损坏」提示 `xattr -cr`。

## 0.2.2 / 0.2.1 / 0.2.0

早期一键安装包迭代（Tauri 外壳内嵌 dsh web + 技能商店；社区技能打包进安装器；Windows 改用体积更小的 NSIS 安装器；发行/更新基础设施统一指向公开仓库 `sagirimo/BioDSH`）。详见对应 tag 的提交记录。
