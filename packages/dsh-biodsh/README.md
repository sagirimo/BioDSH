# dsh-biodsh

[中文](#中文说明) | English

BioDSH for [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness): a bundle that adds a **BioDSH agent preset** for bioinformatics work. Your other presets are not changed.

The BioDSH preset is the standard preset of your dsh release plus:

| Part | What it does |
|---|---|
| BioDSH persona | Answers for doctors and wet-lab scientists, in the user's language; keeps raw data untouched; reports what was actually computed. |
| BioDSH skills | 17 validated BioDSH workflows in the session skill catalog: single-cell QC, clustering, annotation and treatment response; bulk RNA-seq limma-voom; survival (KM, Cox), regression with robust SEs and ANOVA designs, each checked against R; workflow building, and more. |
| Skill library | 2000+ community bioinformatics, clinical and data skills. Kept out of the catalog so it stays small and cacheable; the model searches it with the `skill_library` tool, and you can still run any of them with `/name`. |
| Skill selection | On each new message, a model reads the whole catalog (BioDSH skills and library) and injects the one or two skills that fit the request, in the same form as `/name`. |
| Convergence guard | In a long turn, asks the agent to wrap up (480 s, or 40 steps) and then to answer without tools (780 s, or 60 steps); ends a turn past 80 steps. |

## Install

Requires DeepSeek Harness 0.2.1 or later and [pnpm](https://pnpm.io/installation) on `PATH` (dsh's plugin manager runs pnpm).

- **Command line**

  ```bash
  dsh plugin --profile web add dsh-biodsh
  ```

- **Web UI**: open **Plugins**, choose **Install**, enter `dsh-biodsh`.
- **Ask the agent** (Creator mode): "install the dsh-biodsh bundle".

Restart dsh after installing, then pick **BioDSH** in the agent preset menu, or make it the default:

```yaml
# ~/.dsh/cordis.patch.yml
- id: agent-preset-registry
  config:
    default: biodsh
```

**BioDSH (PTC)** (`biodsh-ptc`) is the same preset with programmatic tool calling, like dsh's own `ptc` preset: the model calls tools from one program per step, so writing a script, running it and checking its output take one step instead of three. On 15 development tasks it cut the median from 23 to 16 steps and from 129 s to 97 s at the same accuracy.

## Configure

The bundle adds a settings namespace `biodsh` (a Host row, so you never edit the preset itself). Change it in `~/.dsh/settings.yaml`, on the Settings page, or with `settings.mutate`; most fields apply to the next step without a restart.

```yaml
# ~/.dsh/settings.yaml
biodsh:
  selectProvider: deepseek-official   # skill selection model; empty = same route as the agent
  selectModel: deepseek-flash
  selectMaxInject: 2
  guardSoftSeconds: 480               # ask to wrap up (time is the main signal; steps are a backstop)
  guardSoftSteps: 40
  guardHardSeconds: 780               # ask for a final answer without tools
  guardHardSteps: 60
  guardMaxSteps: 80                   # end the turn (0 = no cap)
  library: true                       # 2000+ skill library and the skill_library tool (restart to apply)
```

## Versions

A dsh agent preset restates its full plugin list, so each `dsh-biodsh` release is built against one dsh release (`dshTarget` in `package.json`) by `scripts/build.mjs`, which copies the standard preset of that release and changes only the persona and the three BioDSH rows. `scripts/install-test.mjs` installs a build through dsh's own plugin manager in a fresh home and runs a real turn on the preset.

## Licenses

BioDSH code and skills: MIT. Skills under `skills/library` come from community repositories and keep their own licenses; see each skill's folder.

---

## 中文说明

为 DeepSeek Harness 增加一个 **BioDSH 智能体预设**，用于生信分析。你原有的预设不受影响。

BioDSH 预设 = 你当前 dsh 版本的标准预设，再加上：

- **BioDSH 人设**：面向医生和湿实验科学家，跟随用户语言作答，不改原始数据，如实报告实际算了什么。
- **BioDSH 官方技能**：17 个经过验证的流程（单细胞质控/聚类/注释/治疗响应、bulk RNA-seq limma-voom、生存分析 KM/Cox、稳健标准误回归、方差分析设计等，统计类均与 R 逐项对照），出现在会话技能目录里。
- **技能库**：2000+ 社区技能，不放进目录（目录保持小而稳定，利于缓存）。模型用 `skill_library` 工具检索，你也可以用 `/技能名` 直接调用。
- **技能精选**：每条新消息，用模型对照全部技能选出最合适的一两个，以 `/name` 同样的形式注入。
- **收敛护栏**：长任务到 480 秒（或 40 步）先提醒收尾，780 秒（或 60 步）要求直接作答；超过 80 步停止本轮。

设置：在 `~/.dsh/settings.yaml` 写 `biodsh:` 一段（字段见上方英文说明），或在设置页修改，大多数改动下一步就生效。

安装：需要 DeepSeek Harness 0.2.1 及以上，并且 `PATH` 里有 pnpm。

- 命令行：`dsh plugin --profile web add dsh-biodsh`
- 网页：「插件」→「安装」，输入 `dsh-biodsh`

装好后重启 dsh，在智能体预设菜单里选 **BioDSH**，或按上面的 YAML 设为默认。

**BioDSH (PTC)**（`biodsh-ptc`）是同一预设加上程序化工具调用（同 dsh 自带的 `ptc` 预设）：模型每步写一段程序来调用工具，写脚本、运行、检查输出一步完成。在 15 道开发题上，步数中位数从 23 降到 16，耗时从 129 秒降到 97 秒，正确率不变。
