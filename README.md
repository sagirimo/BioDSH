<div align="center">

# BioDSH

**A bioinformatics agent for clinicians and wet-lab scientists. Describe the analysis in plain language and get the result, with no coding.**

[中文](README.zh.md) · [Download](#download) · [dsh plugin](#use-it-inside-deepseek-harness) · [Results](#results)

[![release](https://img.shields.io/github/v/release/sagirimo/BioDSH?include_prereleases&label=release)](https://github.com/sagirimo/BioDSH/releases)
[![npm](https://img.shields.io/npm/v/dsh-biodsh?label=dsh-biodsh)](https://www.npmjs.com/package/dsh-biodsh)
[![license](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

</div>

You add your data (single-cell `h5ad`, count matrices, clinical tables, gene lists…) and ask a question such as *"Do responders and non-responders differ in CD8A expression?"* The agent loads the data, picks the right method, writes and runs the code, and reports the conclusion along with the figures, the tables and every step it took.

BioDSH runs on your own computer and is built on [DeepSeek Harness (dsh)](https://github.com/deepseek-ai/deepseek-harness). It comes in two forms: a one-click **desktop app** and a **dsh plugin** (`dsh-biodsh`).

## Why BioDSH

- **Plain language in, conclusions out.** You don't need to write code or set up an environment. A Python analysis environment (scanpy, anndata, pandas, statsmodels, matplotlib…) installs itself on first launch.
- **Validated methods instead of improvised code.** It ships 17 official analysis skills: single-cell QC, clustering, annotation and treatment response; bulk RNA-seq with limma-voom; Kaplan–Meier and Cox survival; regression with robust standard errors; ANOVA designs; and more. The statistics skills were checked against R on tens of thousands of cases (for example, 101,587 survival comparisons with zero mismatches).
- **The right skill picked automatically.** For each request, a model selects the one or two relevant skills from the 17 official skills and a library of 2,000+ community skills, and loads only those. The context stays small and cheap.
- **Low cost.** BioDSH runs on DeepSeek models. On our analysis tasks its accuracy is on par with Claude Code (Sonnet/Haiku) at about 3–13× lower cost per task (see [Results](#results)).
- **Long analyses always finish.** A convergence guard keeps the agent from running in circles. It first asks the agent to wrap up, then asks for a final answer, so you always get a result.
- **Your data stays safe.** Original files are never modified, and every analysis writes into a new folder. In offline mode BioDSH talks only to a model on your own machine or intranet and makes no outbound requests, which suits hospitals and labs.
- **Every result can be traced.** Every step goes into an append-only session log that you can review, export or hand to a reviewer.
- **Reusable workflows.** You can save a finished analysis as a workflow and rerun it on new data. BioDSH can also build a workflow from an existing script, notebook or methods paragraph.
- **Your choice of model.** BioDSH works with DeepSeek's official API, any OpenAI-compatible endpoint, or a local or intranet model, and you can configure several of them side by side.

## Download

| Version | Platform | Get it |
| --- | --- | --- |
| **1.0.0 Preview 1** (new) | Windows 10/11 | [`BioDSH_1.0.0_x64-setup.exe`](https://github.com/sagirimo/BioDSH/releases/tag/desktop-tauri-v1.0.0-preview.1) |
| 0.3.0 (stable) | Windows, macOS (Apple silicon) | [Latest release](https://github.com/sagirimo/BioDSH/releases/latest) |

- **1.0.0 Preview** is a pre-release. Installed 0.3.0 apps are not auto-updated to it. It installs over 0.3.0, and conversations made with 0.3.0 may not open in 1.0, so back up projects you care about first. macOS and Linux builds will come with 1.0 final.
- **Windows:** on first run, click *More info → Run anyway*. The installer is not code-signed.
- **macOS:** the app is not notarized, so macOS may report it as "damaged". Move it to Applications and run `sudo xattr -cr /Applications/BioDSH.app` once.

The stable app checks for updates in the background and installs them with one click. Updates are signature-verified, and the app sends no data when it checks.

## Use it inside DeepSeek Harness

If you already use dsh, you can install the BioDSH agent as a plugin without the desktop app:

```bash
dsh plugin --profile web add dsh-biodsh
```

You can also install it from the dsh web UI: **Plugins → Install → `dsh-biodsh`**. Restart dsh, then pick **BioDSH** in the agent preset menu. Your other presets are left unchanged. The plugin requires dsh 0.2.1+ and pnpm. For details, see [`packages/dsh-biodsh`](packages/dsh-biodsh).

If you only want the skills, the official skills are plain dsh `SKILL.md` folders. `./scripts/install-into-dsh.sh <your-project>/.agents/skills` copies them in (use `install-into-dsh.ps1` on Windows).

## Results

These are rough numbers from our development benchmarks. A full write-up is in preparation.

**Each layer adds accuracy.** We ran 74 BixBench open-answer analysis questions with deterministic grading, using the same DeepSeek model in every configuration:

| Configuration | Correct |
| --- | --- |
| Chat only (the model answers without running anything) | 6/74 (8%) |
| BioDSH without skills | 38/74 (51%) |
| BioDSH with skills | 46/74 (62%) |

**Comparison with coding agents.** We used 38 data-analysis tasks graded by replaying each answer against a reference, with the same task text for every agent:

| Agent | Correct | Cost per task |
| --- | --- | --- |
| **BioDSH** (DeepSeek V4 Flash) | 35/38 (mean of 2 runs) | ≈ $0.02–0.05 |
| Claude Code · Opus | 37/38 | ≈ $0.32 |
| Claude Code · Sonnet | 35/38 | ≈ $0.13 |
| Claude Code · Haiku | 34/38 | — |
| Codex · Astra / Sol / Luna | 37 / 37 / 30 | ≈ $0.44 (Astra) |

The convergence guard turned 8 timeouts into 0 on the hardest questions. Programmatic tool calling (the default **BioDSH (PTC)** preset) cut the median number of steps from 23 to 16 at the same accuracy.

Caveats: these are single or double runs, and individual runs vary by about ±2 tasks. The 38-task set is our own. A run on the full public BixBench (205 questions) and BioMed-AQA is in progress.

## Build from source

You need Node.js 22+, stable Rust and the [Tauri prerequisites](https://tauri.app/start/prerequisites/).

```bash
cd desktop
npm ci
node scripts/stage-dsh.mjs     # dsh runtime + the dsh-biodsh bundle
node scripts/sync-skills.mjs   # official skills → resources
npm run tauri dev              # or: npm run tauri build
```

| Path | Contents |
| --- | --- |
| `desktop/` | The desktop app: React UI (`src/`), Rust backend (`src-tauri/`) and build scripts. |
| `packages/dsh-biodsh/` | The `dsh-biodsh` plugin: BioDSH presets, skill selection and the convergence guard. |
| `biodsh-core/skills/` | Official skills. |

## License

[MIT](LICENSE) for BioDSH's own code. Bundled components (DeepSeek Harness, community skills, Python packages) keep their own licenses.

BioDSH is an independent project built on [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness). It is not affiliated with or endorsed by DeepSeek.
