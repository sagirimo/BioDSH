---
name: pipeline-builder
description: Turn a completed BioDSH task, or an existing analysis procedure someone else wrote (script, notebook, Snakefile/Nextflow, methods text), into a reproducible, re-runnable workflow through a guided plan the user confirms step by step, with user-chosen validation checks; writes pipelines/<id>/pipeline.json plus step scripts and verifies a clean re-run.
---

# pipeline-builder

把一个已完成的任务（或一份别人写好的分析流程）整理成可复现的工作流：只保留真正产生结果的步骤，开放用户想换的参数和输入，按用户选的验证项做一次干净复现。结果写到项目文件夹的 `pipelines/<id>/`（目录名和 `biodsh.pipeline/1` 格式沿用旧称，界面上叫「工作流」），BioDSH 的「工作流」页面会读取它。

## 什么时候用

- 用户说"存为工作流""做成可复用流程""换一批数据再跑一遍同样的分析"。
- 用户给了一份别人或以前写的脚本、笔记本、流程文件或方法描述，想"照着这个做""学会这个流程"（见下面「从已有文件学习」）。
- 任务已经跑完、有确定的结果；正在探索中的任务先完成再整理。

## 流程（每一步都要等用户确认）

1. **提取步骤。** 回顾本任务里实际执行过的代码与命令（读你写过的脚本文件，不凭记忆重写）。列成编号清单：每步一句话说明、来源脚本、输入、输出。把没被后续步骤用到的探索性尝试标为"建议不保留"。**停下来问用户**保留哪些。
2. **参数与输入。** 列出保留步骤里所有硬编码的值（文件路径、阈值、分辨率、随机种子、样本分组列名）。建议哪些开放为参数、默认值取本任务实际用的值。输入文件改为参数，不写死绝对路径。**停下来问用户**确认。
3. **验证选项。** 给出可选验证项并说明各自代价，让用户勾选：
   - `seed`：固定随机种子，重跑两次结果一致；
   - `compare_original`：用本任务的原始输入重跑，关键数值/表格与原任务输出一致（给出比较的具体量和容差）；
   - `schema`：输出表的列名和类型符合约定；
   - `env`：把用到的包版本写进工作流。
   **停下来问用户**选哪些。
4. **写出文件。** 在 `pipelines/<id>/` 下写：`pipeline.json`（格式见下）、`steps/NN_<name>.py`（每步一个脚本，从参数读输入，不读写工作流目录以外的固定路径）、`run.py`（按依赖顺序执行全部步骤，参数可由命令行或 `params.json` 覆盖）。
5. **复现验证。** 在新的输出目录里执行 `run.py`，逐项跑用户选的验证，把结果写进 `pipeline.json` 的 `validation[].last_result` 和 `runs`。有任何一项不通过，如实报告差异，不要改容差去凑通过。

## 从已有文件学习（学习模式）

用户在「工作流」页点「学习已有流程」时，文件会被复制到 `pipelines/_sources/` 并在提示里给出路径。也可能直接在对话里给你一个项目内的文件。

1. **读懂原流程。** 完整读取文件（.py/.R/.ipynb/.Rmd/Snakefile/.nf/.sh，或论文方法、实验记录等文字）。笔记本按单元格顺序读，注意被注释掉或从未执行的单元格。用编号清单复述：每步做什么、用什么工具和关键参数、输入、输出，以及原作者写死的路径、物种、参考基因组、阈值。看不懂或文件里没写的地方明确标为"原文未说明"，**不要猜**。**停下来问用户**这份理解对不对、要保留哪些步骤。
2. **对齐到当前项目。** 列出原流程需要的输入，和当前项目里实际有的数据逐一对应（文件名、格式、列名/分组）。缺的输入、物种或参考版本不一致、本机环境缺的包，都在这一步说清楚，给出替代方案。**停下来问用户**确认对应关系和参数默认值。
3. **验证选项**与**写出文件**同上面流程的第 3、4 步。`source` 字段写 `{ "learned_from": "pipelines/_sources/<文件名>", "created": "<日期>" }`。原流程用 R、Snakemake 等时，可以在步骤脚本里调用原工具，不必强行改写成 Python，但要在 `env` 里记下依赖。
4. **在用户的数据上跑一次。** 在新输出目录运行 `run.py`。原文件若附带了参考结果（图、表、论文里的数字），把可比较的量写成 `compare_original` 验证项；没有参考结果时只做 `schema`/`seed`，并在报告里说明"无法与原作者结果比对"。

学习模式的要点：忠实于原流程，改动（换工具、换参数、补步骤）都要先告诉用户理由并经同意；原文件只读，不修改 `_sources/` 里的副本。

## pipeline.json 格式

```json
{
  "schema": "biodsh.pipeline/1",
  "id": "scrna-qc-cluster",
  "name": "scRNA 质控到聚类",
  "version": "1.0",
  "description": "h5ad 计数矩阵 → 质控过滤 → 标准化 → Leiden 聚类与 UMAP",
  "source": { "task": "GSE120575 质控与聚类", "session_id": "session-…", "created": "2026-10-17" },
  "inputs": [ { "name": "counts", "format": "h5ad", "description": "细胞 × 基因计数矩阵" } ],
  "params": [ { "name": "min_genes", "default": 200, "description": "每个细胞最少基因数" } ],
  "outputs": [ { "name": "clusters.csv", "description": "每个细胞的簇标签" } ],
  "steps": [ { "id": "qc", "title": "质控过滤", "script": "steps/02_qc.py", "depends_on": ["load"], "description": "基因数 200–6000，线粒体比例 < 15%" } ],
  "validation": [ { "kind": "compare_original", "description": "过滤后细胞数与原任务一致", "expected": "15804", "last_result": { "passed": true, "observed": "15804", "at": "2026-10-17T10:20:00" } } ],
  "env": { "python": "3.12", "packages": { "scanpy": "1.12.4" } },
  "runs": [ { "at": "2026-10-17T10:20:00", "status": "passed", "outdir": "pipelines/scrna-qc-cluster/runs/2026-10-17_1020", "note": "复现验证" } ]
}
```

`id` 用小写字母、数字和连字符；`steps[].id` 在 `depends_on` 里引用；`validation[].kind` 只用上面四种之一。

## 常见错误

- 凭记忆重写代码，导致工作流和原任务算法不一致。必须从实际执行过的脚本整理。
- 把原任务的绝对路径写死在步骤脚本里，换数据就跑不了。
- 复现失败时放宽容差或删掉验证项来"通过"。失败要如实写进 `last_result`。
- 一次性问完所有问题。按上面的顺序分三次确认，每次只问一件事。
- 学习模式里把原文件没写的参数当成"原作者就是这么做的"。不确定就标出来问。
