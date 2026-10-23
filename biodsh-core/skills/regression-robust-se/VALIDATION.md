# R 逐项数值验证：regression-robust-se

验证日期：2026-10-20。环境：

```text
R 4.6.0
sandwich 3.1.3
clubSandwich 0.7.0
lmtest 0.9.40
Python 3.12.3; numpy 2.5.2; scipy 1.18.1; pandas 2.3.3
```

R 在 Windows 下执行，Python 在 WSL 下执行。R 提示所装二进制包由 R 4.6.1 构建，
当前执行器为 R 4.6.0；所有实际检查通过，但没有据此声称在其他版本上验证过。
R 只作独立参考，库运行时只依赖 numpy/scipy/pandas。

## 数据与覆盖

`validation/make_data.py` 的固定 seed 1/2，包含不平衡簇、单观测簇、
高杠杆连续变量、重复的离散协变量值、异方差、簇级随机效应、非恒定权重、
offset、二项 0/1、分组二项比例和有重复值/零值的 Poisson 计数。
每组分别在 x、连续响应及 cluster 上各置一个缺失值。
R `complete.cases` 和 Python `notna().all` 的共同掩码也逐项比较。
这是通用模拟，不读取任何 benchmark 题目或答案。

| 数据 | 原始/保留 n | p | G | 保留簇大小 | OLS 最大 h |
|---|---|---|---|---|---|
| seed 1 | 115 / 112 | 3 | 11 | 1,2,3,4,6,8,11,14,17,21,25 | 0.2844773850 |
| seed 2 | 84 / 81 | 3 | 7 | 1,3,3,7,12,21,34 | 0.3811825125 |

每组分别拟合 OLS、WLS、Bernoulli Logistic、Poisson、带 trials 的分组 Logistic、
带 prior weights 的 Poisson。全部带 offset。参考为 `lm`/`glm`、
`sandwich::bread/estfun/vcovHC/meatHC/vcovCL/meatCL`、
`clubSandwich::vcovCR` 及 `lmtest::coeftest`。
CR2 额外比较任意对角 target=0.7+0.3|x|；WLS 再比较 target=1/w。
CR0/1/1S 与四种 vcovCL HC0/HC1 × cadjust TRUE/FALSE 均检查。

系数检验对每个模型方差及 HC/CR 协方差，分别使用正态、t(n−p)、t(G−1)；
比较估计、SE、t/z、p、df 和 95% CI。联合 Wald 使用两行对比矩阵、
非零 null=(0.1,−0.1)，比较对比估计/协方差、W、χ²/F 统计量、两个 df 和 p。
联合 Wald 的 R 参考是显式矩阵二次型加 `pchisq/pf`，没有声称等价于 HTZ。
所有公开返回的数值估计/方差/分解均纳入；输入副本、类型/标签等元数据
及算法迭代次数不作为 R 数值相等目标。收敛标志与 n/p 已核对。

## 结果

**6,050 个数值量组、94,821 个标量比较全部通过。**
比较脚本先要求 R/Python 的量名集合及形状完全一致、有限值状态一致，
并逐元素判定 `abs(Python−R) <= 1e-12 + 1e-8*abs(R)`。
Inf 自由度单独要求一致；不存在用 NaN 跳过失败项。

† 表中相对误差只统计 |R|≥1e-8 的元素，最大为
**3.57765091e-09**；|R|<1e-8 的最大绝对误差为
**9.77156052e-16**。原始相对指标定义为
`abs(Python−R)/max(abs(R),1e-12)`，包括近零项的最大值为
**9.77156052e-04**，并不满足严格逐元素 1e-8 相对误差要求；
原因是 R 通过逆 bread 从 influence 重构簇得分时，对数学上为零的元素留下约
1e-15 舍入。原始指标没有隐藏：
[comparison.csv](validation/comparison.csv) 逐 seed/模型/量记录 max_abs、
max_rel、max_rel_nonzero、near_zero_abs 和 passed；
[max_relative_errors.csv](validation/max_relative_errors.csv) 保留全部量的原始最大相对误差。
下表聚合相同返回字段，系数/Wald 检验字段跨所有协方差类型和三种 df 取最大。

| 数值量（跨六类模型取最大） | seed 1 相对误差† | seed 2 相对误差† | 两组最大绝对误差 |
|---|---:|---:|---:|
| `CL_HC0_FALSE.cov` | 7.429e-14 | 1.303e-13 | 1.596e-16 |
| `CL_HC0_FALSE.meat` | 3.960e-15 | 6.736e-15 | 1.332e-14 |
| `CL_HC0_TRUE.cov` | 8.811e-14 | 1.441e-13 | 5.690e-16 |
| `CL_HC0_TRUE.meat` | 4.167e-15 | 1.048e-14 | 1.066e-14 |
| `CL_HC1_FALSE.cov` | 1.509e-13 | 1.326e-13 | 2.498e-16 |
| `CL_HC1_FALSE.meat` | 4.236e-15 | 9.506e-15 | 9.770e-15 |
| `CL_HC1_TRUE.cov` | 1.267e-13 | 1.331e-13 | 3.608e-16 |
| `CL_HC1_TRUE.meat` | 5.403e-15 | 9.333e-15 | 1.155e-14 |
| `CR0.cluster_scores` | 6.370e-14 | 4.930e-13 | 5.862e-14 |
| `CR0.cov` | 5.241e-14 | 8.914e-14 | 1.596e-16 |
| `CR0.df_cluster` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `CR0.factor` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `CR0.meat` | 6.632e-15 | 3.182e-15 | 1.332e-14 |
| `CR0.n_clusters` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `CR1.cluster_scores` | 6.166e-14 | 5.534e-13 | 4.796e-14 |
| `CR1.cov` | 6.036e-14 | 9.749e-14 | 6.245e-16 |
| `CR1.df_cluster` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `CR1.factor` | 0.000e+00 | 2.855e-15 | 3.331e-15 |
| `CR1.meat` | 4.295e-15 | 4.502e-15 | 1.243e-14 |
| `CR1.n_clusters` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `CR1S.cluster_scores` | 6.032e-14 | 7.173e-13 | 5.329e-14 |
| `CR1S.cov` | 2.628e-14 | 9.169e-14 | 4.025e-16 |
| `CR1S.df_cluster` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `CR1S.factor` | 1.784e-15 | 2.969e-15 | 3.553e-15 |
| `CR1S.meat` | 5.065e-15 | 4.044e-15 | 1.421e-14 |
| `CR1S.n_clusters` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `CR2.adjustments` | 7.208e-10 | 1.724e-10 | 3.708e-14 |
| `CR2.cluster_scores` | 1.867e-12 | 3.745e-13 | 6.750e-14 |
| `CR2.cov` | 4.017e-13 | 4.525e-14 | 4.718e-16 |
| `CR2.df_cluster` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `CR2.factor` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `CR2.meat` | 1.415e-14 | 2.783e-14 | 3.020e-14 |
| `CR2.n_clusters` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `CR2.target` | 4.594e-15 | 3.977e-15 | 5.773e-15 |
| `CR2_custom.adjustments` | 1.626e-10 | 3.578e-09 | 2.252e-13 |
| `CR2_custom.cluster_scores` | 3.444e-13 | 8.939e-13 | 1.976e-13 |
| `CR2_custom.cov` | 1.213e-13 | 2.570e-13 | 2.776e-16 |
| `CR2_custom.df_cluster` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `CR2_custom.factor` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `CR2_custom.meat` | 1.136e-14 | 6.361e-14 | 2.665e-14 |
| `CR2_custom.n_clusters` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `CR2_custom.target` | 4.586e-15 | 3.945e-15 | 4.663e-15 |
| `CR2_precision.adjustments` | 1.126e-11 | 7.488e-12 | 9.992e-15 |
| `CR2_precision.cluster_scores` | 1.064e-14 | 2.222e-13 | 8.171e-14 |
| `CR2_precision.cov` | 2.104e-14 | 3.607e-14 | 1.457e-16 |
| `CR2_precision.df_cluster` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `CR2_precision.factor` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `CR2_precision.meat` | 9.178e-15 | 9.022e-15 | 1.954e-14 |
| `CR2_precision.n_clusters` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `CR2_precision.target` | 4.550e-15 | 4.619e-15 | 4.885e-15 |
| `HC0.adjusted_scores` | 1.065e-13 | 5.744e-13 | 7.105e-14 |
| `HC0.cov` | 1.274e-14 | 1.093e-14 | 1.110e-16 |
| `HC0.factors` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `HC0.meat` | 7.497e-15 | 6.938e-15 | 9.770e-15 |
| `HC1.adjusted_scores` | 1.100e-13 | 5.748e-13 | 4.263e-14 |
| `HC1.cov` | 9.641e-15 | 1.224e-14 | 5.829e-16 |
| `HC1.factors` | 3.241e-15 | 1.497e-15 | 3.331e-15 |
| `HC1.meat` | 5.625e-15 | 6.288e-15 | 7.994e-15 |
| `HC2.adjusted_scores` | 1.065e-13 | 5.744e-13 | 5.329e-14 |
| `HC2.cov` | 3.125e-14 | 1.169e-13 | 5.412e-16 |
| `HC2.factors` | 5.032e-15 | 4.860e-15 | 5.107e-15 |
| `HC2.meat` | 8.109e-15 | 3.331e-15 | 7.105e-15 |
| `HC3.adjusted_scores` | 1.101e-13 | 5.747e-13 | 6.395e-14 |
| `HC3.cov` | 1.385e-14 | 2.464e-14 | 1.943e-16 |
| `HC3.factors` | 4.979e-15 | 4.858e-15 | 1.954e-14 |
| `HC3.meat` | 8.371e-15 | 4.407e-15 | 3.553e-14 |
| `bread` | 3.039e-14 | 2.412e-14 | 7.105e-15 |
| `coefficient_test.coefficients` | 4.998e-15 | 3.567e-15 | 3.997e-15 |
| `coefficient_test.conf_high` | 5.674e-13 | 5.398e-12 | 7.994e-15 |
| `coefficient_test.conf_low` | 8.208e-15 | 3.627e-13 | 5.551e-15 |
| `coefficient_test.df` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `coefficient_test.p_value` | 2.693e-14 | 9.659e-14 | 1.665e-15 |
| `coefficient_test.se` | 4.603e-15 | 5.029e-15 | 9.714e-16 |
| `coefficient_test.statistic` | 7.540e-15 | 4.783e-15 | 4.619e-14 |
| `coefficients` | 4.998e-15 | 3.567e-15 | 3.997e-15 |
| `converged` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `data.keep` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `deviance` | 3.323e-15 | 3.968e-15 | 4.263e-13 |
| `df_resid` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `dispersion` | 3.078e-15 | 5.262e-16 | 3.775e-15 |
| `eta` | 9.741e-14 | 1.173e-13 | 1.310e-14 |
| `fitted` | 9.042e-14 | 1.173e-13 | 1.310e-14 |
| `hat` | 4.955e-15 | 4.444e-15 | 7.772e-16 |
| `information` | 7.952e-15 | 4.004e-15 | 3.695e-13 |
| `inverse_information` | 3.683e-14 | 2.129e-14 | 1.388e-16 |
| `model_cov` | 3.083e-14 | 2.196e-14 | 1.388e-16 |
| `n` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `p` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `residuals` | 1.095e-13 | 5.741e-13 | 1.821e-14 |
| `scores` | 1.065e-13 | 5.744e-13 | 7.105e-14 |
| `wald_test.contrast_cov` | 1.295e-13 | 2.570e-13 | 5.829e-16 |
| `wald_test.contrast_estimate` | 7.520e-15 | 1.765e-14 | 1.554e-15 |
| `wald_test.df_denom` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `wald_test.df_num` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `wald_test.p_value` | 3.848e-14 | 1.420e-14 | 3.109e-15 |
| `wald_test.statistic` | 8.353e-15 | 8.825e-15 | 8.882e-14 |
| `wald_test.wald` | 8.353e-15 | 8.825e-15 | 8.527e-14 |
| `working_residuals` | 1.082e-13 | 5.741e-13 | 1.821e-14 |
| `working_weights` | 4.560e-15 | 4.571e-15 | 5.773e-15 |

## 发现的数值差异及处理

1. **R GLM 最终权重滞后一轮。** 首次直接使用 `glm(epsilon=1e-14)` 的结果，
   在 5,414 组 / 70,305 个标量的对照中，82 组原始相对误差超过 1e-8，
   其中包括近零簇得分，也包括 GLM 的 information/bread/方差及派生 p/CI。
   information 最大绝对差 1.4806730064e-7，相应相对差 5.452685e-8；
   某个加权 Poisson HC2 协方差元素相对差 7.440594e-8。
   Python 在最终 β 重算信息矩阵；R `glm.fit` 返回的 working weights/QR
   来自更新前一轮。参考脚本用 `update(f,start=coef(f),control=...)` 再拟合，
   让两侧比较同一个收敛点；没有修改 R 的统计公式或把 Python 中间量喂给 R。
   初次结果保存在 [initial_comparison.csv](validation/initial_comparison.csv)。
   给 `reference.R DATADIR OUTDIR unpolished` 可取消这一步，复核现象；
   请使用独立 OUTDIR，初次记录早于新增 custom target 和 n/p/converged 字段。
2. **CR2 默认 target。** WLS 默认 identity 与显式 1/w 均对照；
   seed 2 的 x SE 为 0.1609866772 与 0.1713709182，不能把它们混写。
3. **df 约定。** seed 1 的 OLS CR1S x 检验，
   正态 p=0.0002128732，t(10) p=0.0040866822。
   CR2 协方差验证不包含 Satterthwaite 或 HTZ 检验。

## 独立边界检查与速度

[checks.json](validation/checks.json) 记录 **122 项通过**：
输入不变、行重排不变、得分方程、hat trace、WLS 权重缩放不变、
簇数等于 n 时的 CR0=HC0 / CR1S=HC1 / CR2=HC2
（WLS CR2 使用 precision target），以及 Wald=t² 和相同 p。
拒绝测试覆盖缺失、n≤p、秩亏、零/负权重、非法响应/offset/家族、
未收敛与完全分离、单簇/缺失簇、无效 target、单位杠杆、
奇异 CR2 残差块、负方差、无效 df/CI、秩亏对比与奇异 Wald 方差。
这不是对所有可能分离模式的证明。

单线程环境 OPENBLAS_NUM_THREADS=OMP_NUM_THREADS=MKL_NUM_THREADS=1。
3000 行、p=5、60 个簇（每簇 50 行），一次计时包含 OLS/WLS/Logistic/Poisson
四个模型，每个模型全部 HC0–HC3、CR0/1/1S/2，加聚类系数与 Wald 检验。
导入和一次预热不计时；五次秒数：
`0.089413, 0.092717, 0.100606, 0.104051, 0.094458`。
中位数 **0.094458 秒**，最大 **0.104051 秒**。
CR2 的大簇稠密分解成本随 Σn_g³ 增长，不能将本结果外推到任意簇大小。

## 复跑

在仓库根执行：

```bash
bash biodsh-core/skills/regression-robust-se/validation/run.sh
```

脚本顺序为生成数据、运行 R、Python 全量比较、独立检查/计时、生成本文。
`PYTHON_BIN`、`RSCRIPT`、`SANDWICH_SCRATCH`、`R_LIMMA_LIB` 可覆盖默认路径。
默认 scratch：
`/mnt/c/Users/MOLIEX-DESKTOP/bench-codex-scratch/skill-sandwich/`；
默认私有库 `C:/Users/MOLIEX-DESKTOP/bench-rlib`。
使用 Windows R 的命令行路径必须转换为 Windows 路径；
`run.sh` 通过 WSLENV 传递 R_LIMMA_LIB/TMP/TEMP，将 R 临时文件放在 scratch/r-temp。
R 脚本优先把环境变量 R_LIMMA_LIB 加入 `.libPaths`。
所需参考包已安装；主库与验证脚本不会自动安装依赖。

R 原始逐元素结果和两份模拟 CSV 在 scratch 的 reference/ 与 data/ 中；
工作目录保存比较摘要、版本、检查/计时和可复跑脚本。
`skill-creator/scripts/quick_validate.py` 另用于检查 SKILL.md 元数据，
它不替代统计数值验证。

## 未验证/未实现

多向/嵌套聚类合成、Satterthwaite/HTZ、奇异 CR2 广义逆、非对角目标、
非规范链接、其他 GLM 家族及调查权重未实现。没有声称跨包版本完全相同，
也没有把本次两组模拟等同于统计有效性或覆盖率证明。
