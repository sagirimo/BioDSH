# R 逐项验证：anova-designs

验证日期：2026-10-20。所有数据均由本技能的模拟器生成，没有使用 benchmark 题目或答案。

## 环境与判据

```text
R version 4.6.0 (2026-04-24 ucrt)
car 3.1.5
nlme 3.1.169
emmeans 2.0.4
Python 3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]
numpy 2.5.2; scipy 1.18.1; pandas 2.3.3
```

共 **23 个数据案例，16,159 个数值/NA 位置**，R/Python 键集合完全一致。
严格判据为 `abs(Python-R) <= 1e-10 + 1e-8*abs(R)`；成对 NA 必须一致。
下表“相对误差”使用 `abs(diff)/abs(R)`，只统计 `abs(R)>=1e-8`，
近零/结构零另列绝对误差，避免 QR/SVD 投影中约 1e-15 的结构零被相对误差放大。
详细到每个位置的 Python 值、R 值、差值和严格判定保存在
[comparisons.csv](validation/results/comparisons.csv)，不只比较四舍五入后的表格。

普通 ANOVA/分层/EMM 的 6,552 项和独立 R REML 根的 3,735 项全部通过严格判据；
这 10,287 项的最大相对误差 **4.535e-11**，最大绝对误差 **9.095e-13**。
直接 `nlme::lme` 对照有 **625 项**未达到严格目标，原因和完整误差表见下文；
不能把这个结果概括为“所有项均小于 1e-8”。

## 数据与参考计算

每个 seed（17、83）生成 11 个案例：

| 数据 | 行数 / 构造 | R 参考 |
|---|---|---|
| fixed_bal | 48；3×2 因素，每格8条 | `lm`、`anova`、`car::Anova(type=2/3)`、`emmeans(~A, weights="equal")` |
| fixed_unbal | 47；格频数 [[3,12],[9,4],[5,14]] | 同上，另比较 B*A 的 I 型顺序及 treatment 编码的 III 型敏感性 |
| split_bal | 48；8区组×3整区水平×2亚区水平 | `aov(y~A*B+Error(block/A))` |
| split_unbal | 44；从完整裂区删除4条不同亚区记录 | 同上；固定效应会跨多个层出现 |
| block_bal / block_unbal | 24 / 22；完整随机区组及删除2个区组×处理格 | `aov(y~A+Error(block))` |
| rm_bal / rm_unbal | 48 / 51；2组各8人 / 6与11人，每人3次完整测量 | `aov(y~A*B+Error(subject/B))` |
| reml_bal / reml_unbal | 168 / 159；24组，每组7条 / 3至11条，固定截距、二水平因素、连续x | `nlme::lme(y~A+x, random=~1|group, method="REML")` |
| reml_boundary | 60；12组各5条，拟合截距后每组均值为0 | `lme(y~1, random=~1|group)` 与精确 lambda=0 的矩阵解 |

另有 seed 9001 的 **reml_multimodal** 压力案例（55行；组大小2、3、10、40）：
生成器固定复现第168次模拟，不依赖外部题目。该案例使用异方差模拟噪声，
用于检查同方差随机截距 REML 优化的多个驻点，不声称所拟合模型是其真实生成模型。

固定模型核对设计矩阵、系数、完整协方差/未缩放协方差、逐行拟合和残差、SSE、sigma²、秩、n、残差df，
三类平方和表的 SS/df/MS/F/p 及分母、EMM 的 L/估计/完整协方差/SE/df/CI。
误差层核对 R `aov` 实际 error QR 投影的 `X'X`、`X'y`、y'y、维度、拟合秩、残差 SS/df，
以及每层完整检验表、截距SS和总SS。QR坐标的任意符号/旋转及别名系数不是稳定可比对象，
因此比较投影不变量。零df项按 R 规则不输出。

REML 同时对照两条参考路径：

1. `nlme::lme` 的系数、vcov、方差分量、logLik、ranef、逐行边际/条件拟合与残差；
   用该拟合的 lambda 独立构造稠密 C，计算信息矩阵、rhs、广义 RSS、logdet 和 score。
2. R 独立构造 n×n 的 C、求逆并以 `uniroot` 解 profile score，再计算全部上述量（键前缀 `root/`）。
   多驻点案例用与 Python 不同密度的 log 网格找到所有变号根，并比较似然。
   Python 则采用组内求和的 Woodbury 形式，未使用 R 导出的系数或方差参数。

## 普通 ANOVA、误差层与边际均值

| 量（跨案例最大值） | 位置数 | 最大相对误差 | 最大绝对误差 | 近零项最大绝对误差 |
|---|---:|---:|---:|---:|
| `design/X` | 3708 | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `diagnostics/df_residual` | 28 | 0.000e+00 | 0.000e+00 | — |
| `diagnostics/dimension` | 28 | 0.000e+00 | 0.000e+00 | — |
| `diagnostics/rank` | 28 | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `diagnostics/sse` | 28 | 4.600e-15 | 1.279e-13 | — |
| `diagnostics/xtx` | 792 | 1.191e-14 | 5.684e-14 | 1.580e-14 |
| `diagnostics/xty` | 144 | 8.829e-14 | 7.461e-14 | 1.664e-14 |
| `diagnostics/y_ss` | 28 | 4.429e-15 | 1.279e-13 | — |
| `emm/L` | 72 | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `emm/SE` | 12 | 2.545e-15 | 5.551e-16 | — |
| `emm/df` | 12 | 0.000e+00 | 0.000e+00 | — |
| `emm/emmean` | 12 | 2.695e-15 | 4.441e-15 | — |
| `emm/lower.CL` | 12 | 3.990e-15 | 4.885e-15 | — |
| `emm/upper.CL` | 12 | 2.714e-15 | 5.773e-15 | — |
| `emm/vcov` | 36 | 4.252e-15 | 4.996e-16 | 5.551e-17 |
| `fit/beta` | 24 | 1.120e-14 | 4.441e-15 | — |
| `fit/df_residual` | 4 | 0.000e+00 | 0.000e+00 | — |
| `fit/fitted` | 190 | 5.837e-15 | 1.044e-14 | — |
| `fit/n` | 4 | 0.000e+00 | 0.000e+00 | — |
| `fit/rank` | 4 | 0.000e+00 | 0.000e+00 | — |
| `fit/residual` | 190 | 1.081e-13 | 6.661e-15 | — |
| `fit/sigma2` | 4 | 2.756e-15 | 3.331e-15 | — |
| `fit/sse` | 4 | 1.075e-15 | 4.974e-14 | — |
| `fit/unscaled_vcov` | 144 | 9.950e-15 | 8.327e-17 | 1.419e-17 |
| `fit/vcov` | 144 | 1.067e-14 | 9.714e-17 | 1.844e-17 |
| `fixed_anova/F` | 68 | 6.775e-13 | 3.979e-13 | — |
| `fixed_anova/denominator_df` | 52 | 0.000e+00 | 0.000e+00 | — |
| `fixed_anova/denominator_ms` | 52 | 2.756e-15 | 3.331e-15 | — |
| `fixed_anova/df` | 68 | 0.000e+00 | 0.000e+00 | — |
| `fixed_anova/ms` | 68 | 6.756e-13 | 2.842e-13 | — |
| `fixed_anova/p` | 68 | 4.344e-14 | 3.675e-14 | 5.793e-31 |
| `fixed_anova/ss` | 68 | 6.756e-13 | 2.842e-13 | — |
| `intercept_ss` | 12 | 3.733e-15 | 9.095e-13 | — |
| `table/F` | 68 | 5.061e-13 | 4.619e-14 | — |
| `table/denominator_df` | 40 | 0.000e+00 | 0.000e+00 | — |
| `table/denominator_ms` | 40 | 8.026e-15 | 3.908e-14 | — |
| `table/df` | 68 | 0.000e+00 | 0.000e+00 | — |
| `table/ms` | 68 | 5.026e-13 | 1.171e-13 | — |
| `table/p` | 68 | 2.308e-14 | 2.109e-14 | — |
| `table/ss` | 68 | 5.026e-13 | 1.279e-13 | — |
| `total_ss` | 12 | 1.437e-15 | 5.116e-13 | — |

## REML：独立 R 矩阵求根参考

| 量（跨案例最大值） | 位置数 | 最大相对误差 | 最大绝对误差 | 近零项最大绝对误差 |
|---|---:|---:|---:|---:|
| `beta` | 15 | 3.766e-14 | 5.040e-14 | — |
| `blup` | 124 | 4.336e-13 | 6.728e-14 | 0.000e+00 |
| `df_residual` | 7 | 0.000e+00 | 0.000e+00 | — |
| `fitted_conditional` | 829 | 1.771e-13 | 1.021e-14 | — |
| `fitted_marginal` | 829 | 1.239e-11 | 7.017e-14 | — |
| `group_counts` | 124 | 0.000e+00 | 0.000e+00 | — |
| `info_unscaled` | 39 | 1.892e-13 | 4.690e-13 | 8.327e-17 |
| `logdet_correlation` | 7 | 6.618e-15 | 4.707e-14 | 0.000e+00 |
| `logdet_information` | 7 | 3.097e-15 | 2.132e-14 | — |
| `loglik` | 7 | 1.405e-15 | 2.842e-13 | — |
| `residual_conditional` | 829 | 4.176e-11 | 8.660e-15 | — |
| `residual_marginal` | 829 | 4.535e-11 | 7.017e-14 | — |
| `rhs` | 15 | 5.678e-14 | 1.794e-13 | — |
| `rss_generalized` | 7 | 1.681e-15 | 1.137e-13 | — |
| `score` | 7 | 0.000e+00 | 1.465e-14 | 1.465e-14 |
| `sigma2` | 7 | 2.166e-15 | 8.882e-16 | — |
| `tau2` | 7 | 1.077e-14 | 9.992e-15 | 0.000e+00 |
| `variance_ratio` | 7 | 1.081e-14 | 2.176e-14 | 0.000e+00 |
| `vcov` | 39 | 1.700e-12 | 2.665e-15 | — |

## REML：直接 nlme 输出及其参数下的矩阵参考

| 量（跨案例最大值） | 位置数 | 最大相对误差 | 最大绝对误差 | 近零项最大绝对误差 |
|---|---:|---:|---:|---:|
| `beta` | 15 | 3.222e-07 | 6.952e-08 | — |
| `blup` | 124 | 3.308e-07 | 3.042e-07 | 5.436e-22 |
| `design/X` | 2137 | 4.451e-15 | 4.885e-15 | — |
| `df_residual` | 7 | 0.000e+00 | 0.000e+00 | — |
| `fitted_conditional` | 829 | 3.415e-07 | 3.737e-07 | — |
| `fitted_marginal` | 829 | 3.222e-07 | 6.952e-08 | — |
| `group_counts` | 124 | 0.000e+00 | 0.000e+00 | — |
| `info_unscaled` | 39 | 4.904e-07 | 1.885e-05 | 8.327e-17 |
| `logdet_correlation` | 7 | 1.000e+00 | 3.771e-06 | — |
| `logdet_information` | 7 | 3.109e-07 | 4.904e-07 | — |
| `loglik` | 7 | 2.169e-08 | 1.728e-06 | — |
| `residual_conditional` | 829 | 9.251e-06 | 3.737e-07 | — |
| `residual_marginal` | 829 | 2.985e-06 | 6.952e-08 | — |
| `rhs` | 15 | 3.142e-07 | 3.771e-05 | — |
| `rss_generalized` | 7 | 2.567e-08 | 2.054e-06 | — |
| `score` | 7 | 1.000e+00 | 8.641e-06 | — |
| `sigma2` | 7 | 2.567e-08 | 3.803e-08 | — |
| `tau2` | 7 | 1.000e+00 | 5.503e-07 | — |
| `variance_ratio` | 7 | 1.000e+00 | 5.691e-07 | — |
| `vcov` | 39 | 4.648e-07 | 1.422e-07 | — |

### 未达到 1e-8 的解释与验收边界

`lmeControl(opt="optim", optimMethod="BFGS", maxIter=200, msMaxIter=1000,
 tolerance=1e-10, msTol=1e-12, apVar=FALSE)` 仍采用数值优化，
与解析 score 求根的 lambda 有约 1e-7 至 1e-6 的相对差异。
例如多驻点案例的 lambda：Python 0.626305128198973、nlme 0.626304740633144；
两者 logLik 差仅约 1.56e-13，nlme 在该点的 profile score 约 −4.45e-7，Python 约 −2.66e-15。
小残差的相对误差会被放大，因此必须同时看绝对误差。

边界案例 Python tau² 精确为0；nlme 返回 4.8085183e-8 / 5.2639631e-8，
导致 C 的 logdet 等接近零的量仍有约 3.77e-6 绝对差异。
这不是通过删去边界数据或把接近零的方差报告成完全一致来处理的。

所有未达严格判据项均列入 [outside_target.csv](validation/results/outside_target.csv)。
重放脚本对直接 nlme 结果另设明确上限：`rtol=1e-6, atol=1e-6`；
边界案例仅把 `atol` 放宽到 `1e-5`，以容纳趋零的 logdet。
独立 R 根及全部 ANOVA/EMM 的严格阈值不放宽。超出任一适用上限，脚本以非零退出。

### 修复并保留的回归案例

旧实现仅根据 lambda=0 的 score 决定边界，在多驻点案例会错误返回 lambda=0。
边界负loglik=92.0130180036、score=+0.2894928235；较优内部点的负loglik=91.5777575676。
当前实现扫描 lambda∈[1e-10,1e8] 的161个log网格点，比较变号根与0边界，
回归检查要求内部解且 logLik 至少改善0.4。有限网格不能证明不存在极窄的未采样极值，
这个限制已在函数 docstring 和 SKILL.md 明示。

## 边界/行为检查与单线程性能

[check_edges.py](validation/check_edges.py) 的 **67 项**检查全部通过：
SS/df 守恒、正确整区/亚区分母、OLS 正规方程、III型 Wald 等价、II型编码不变性、
REML 行顺序不变性、零方差边界、多驻点回归，以及缺失响应/因子、空格、重复/缺失时点、
组间因素在受试者内变化、组截距被固定效应吸收、全单例组、混合EMM缺少df的显式拒绝。

环境变量 `OPENBLAS_NUM_THREADS=OMP_NUM_THREADS=MKL_NUM_THREADS=1`；每项3次，
排除导入与数据生成。这里的低维案例支持“几千行低于1秒”，不保证任意高维因子模型。

| 方法（均为3000行） | 中位秒数 | 最大秒数 |
|---|---:|---:|
| anova_II_60_columns | 0.023645 | 0.023873 |
| split_plot_50_blocks_3x20 | 0.069615 | 0.073150 |
| randomized_block_50_blocks | 0.007383 | 0.007833 |
| repeated_measures_300_subjects_10_times | 0.098163 | 0.103331 |
| reml_300_groups_4_columns | 0.020368 | 0.021038 |

## 完整复跑

从仓库根目录运行：

```bash
bash biodsh-core/skills/anova-designs/validation/run_validation.sh
```

脚本默认使用 `~/bench/env/bin/python` 和 Windows R 4.6.0；可通过
`STRATA_PYTHON`、`STRATA_RSCRIPT` 指定其他可执行文件。
R 脚本启动时从环境变量 `R_LIMMA_LIB` 读取私有库（默认 `C:/Users/MOLIEX-DESKTOP/bench-rlib`）。
所需 R 包为 car、nlme、emmeans，不自动安装，不依赖 jsonlite。
Windows R 的 TMPDIR/TMP/TEMP 通过 WSLENV 显式传入并指向允许的 scratch/r-tmp。

输入与 R 输出写入 `/mnt/c/Users/MOLIEX-DESKTOP/bench-codex-scratch/skill-strata/`，
核对结果和日志写入本技能 validation/，成功后复制输入和 R 参考输出到
[validation/data](validation/data/) 与 [validation/r-reference](validation/r-reference/) 留存。
不删除文件、不修改生产技能、不提交 git。

仅用已保存的 R 结果重新比较（无需启动R）：

```bash
OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 ~/bench/env/bin/python \
  biodsh-core/skills/anova-designs/validation/compare.py \
  biodsh-core/skills/anova-designs/validation/data \
  biodsh-core/skills/anova-designs/validation/r-reference \
  biodsh-core/skills/anova-designs/validation/results
```

按案例类别/量汇总的文件为
[validation/results/summary.csv](validation/results/summary.csv)。
`write_validation.py` 可根据现有结果重建本报告；统计重放与报告生成分开，避免用文档生成掩盖验证失败。

## 验证覆盖限制

数值 R 对照覆盖表中分类结构和一随机截距模型；没有验证多随机层、随机斜率、
数值协变量的边际均值、异方差拟合或奇异设计可估计假设，这些也未实现。
单组内因素且无组间因素的重复测量包装器采用相同的误差层算法，性能测试执行了该分支；
本次 R 逐项重复测量参考使用有组间因素的设计，不把性能运行冒充额外的 R 数值对照。
