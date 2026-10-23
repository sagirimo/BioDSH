---
name: anova-designs
description: 在只能使用 numpy/scipy/pandas 时计算平衡或不平衡析因 ANOVA 的 I/II/III 型平方和、随机区组与裂区的多误差层 ANOVA、完整重复测量 ANOVA、单随机截距 REML 和等权估计边际均值。需要复现 R aov(Error(...)) 的 SS/df/MS/F/p、选择正确整区/亚区分母，或避免把缺失格和对比编码处理错时使用；实现经 R car、nlme、emmeans 逐项验证。
---

# ANOVA designs：纯 Python 统计实现

使用同目录 `anova_py.py`，或把需要的函数及其辅助函数和 imports 复制到分析脚本。
运行时仅依赖 numpy、scipy、pandas，无文件读写、全局可变状态或 R 依赖。
验证程序才需要 R。逐项误差、优化精度例外及复跑命令见 [VALIDATION.md](VALIDATION.md)。

## 步骤

1. **识别实验单位和随机化层级。** 先确定响应、区组、整区单位、亚区单位、受试者、组间及组内因素。
   同名处理不代表同一实验单位。裂区整区键为 `(block, A)`；受试者 ID 必须在组间全局唯一。
2. **显式处理缺失。** 按研究约定对齐行、记录删除的样本与格频数。代码拒绝 NaN/Inf，不会自动删行、补零或插补。
   各格样本数不同但所有格都存在，可以计算固定效应 I/II/III 型 SS。
   完整交互模型存在空格时会秩亏，本实现拒绝任意选择别名系数；需要重新定义可估计假设或有科学依据的较小模型。
3. **编码和模型。** `factorial_design(data, ['A','B'], coding='sum')` 默认生成截距、A、B、A:B，
   对应 R `contr.sum`。显式 `levels={'A': [...], 'B': [...]}` 固定水平顺序；默认按值排序。
   `terms=[('A',),('B',)]` 指定加性模型；其他有层级的析因模型可指定有序 terms。
   交互列按 R 的第一个因素变化最快排序。该构建设计函数仅处理分类因素，数值协变量应手动构造 X 用于 OLS/REML。
4. **选择检验和分母。** 普通固定效应模型用 `anova(y, design, typ='I'/'II'/'III')`。
   多层随机化设计用下表的包装函数；不要把普通 OLS 的残差 MS 套给所有层的效应。
5. **混合模型或边际均值。** 若研究模型是单随机截距，可用 `random_intercept_reml(y, X, groups)`；
   报告固定系数、协方差、残差方差 `sigma2`、随机截距方差 `tau2`、REML loglik 和边界状态。
   完整分类固定模型的等权边际均值用 `marginal_means(fit, design, by='A')`。
6. **报告。** 每个效应列出 `stratum, term, ss, df, ms, F, p, denominator_df, denominator_ms`，
   同时说明 SS 类型、因素顺序、对比编码、格频数、缺失处理、重复测量假设和混合模型的自由度约定。

```python
from anova_py import factorial_design, anova, split_plot, marginal_means

design = factorial_design(data, ['A', 'B'], coding='sum')
fixed = anova(data['y'], design, typ='III', include_intercept=True)
fixed_table = fixed['table']
emm = marginal_means(fixed['fit'], design, 'A')
# 仅当实验确实采用 block/A 随机化时：
stratified = split_plot(data, response='y', block='block', whole='A', sub='B')
strata_table = stratified['table']
```

## 误差层与自由度

以下简式要求所述完整设计。函数实际根据投影空间的秩计算 df；不平衡时不要硬套简式。

| 设计 / API | R 模型 | 效应分母和 df |
|---|---|---|
| 随机区组 `randomized_block(d,'y','block','A')` | `aov(y ~ A + Error(block))` | 每区组每处理一条记录：A 用 Within 残差 MS，df=(r−1)(a−1)；block 层保留区组 SS |
| 裂区 `split_plot(d,'y','block','A','B')` | `aov(y ~ A*B + Error(block/A))` | r 区组、a 整区水平、b 亚区水平，每亚区一条记录：A 用 block:A 残差，df=(r−1)(a−1)；B、A:B 用 Within 残差，df=a(r−1)(b−1) |
| 单因素重复测量 `repeated_measures(d,'y','id','time')` | `aov(y ~ time + Error(id/time))` | N 受试者、k 时点：time 用 id:time 残差，df=(N−1)(k−1) |
| 混合重复测量 `repeated_measures(d,'y','id','time','group')` | `aov(y ~ group*time + Error(id/time))` | g 个组、N 受试者、k 时点：group 用 id 层残差，df=N−g；time、group:time 用 id:time 残差，df=(N−g)(k−1) |

`strata_anova(y, design, error_terms)` 提供一般接口。`error_terms` 是按顺序给出的
`[(层名, 误差设计矩阵), ...]`，例如区组 indicator，再接区组×整区 indicator。
实现先移除截距，再顺序正交化各误差空间，剩余空间命名为 `Within`。
每个层对固定效应依 terms 顺序投影；`df=新增空间秩`，`SS=投影长度平方`，
`F=(SS/df)/(该层剩余SS/剩余df)`，p 来自对应 F 分布。
没有剩余自由度时返回 NaN F/p，不借用其他层的误差。

**不平衡的多层 aov：** 同一效应可能出现在多个层，这是 R 的顺序分解，不能任选一行当作该效应的唯一检验。
本实现返回各层全部结果，不合并分母；缺失记录的裂区和区组已与 R 对照。
R 官方也指出多误差层 `aov` 主要面向平衡设计，不平衡时应考虑符合实际随机结构的混合模型。
本技能的单随机截距模型不能代替含两个随机层的完整裂区混合模型。
见 [R aov 文档](https://www.stat.ethz.ch/R-manual/R-devel/library/stats/html/aov.html)。

## 三类平方和

- **I 型**：依 terms 顺序逐项加入；以新增投影空间的 SS 为分子，最终完整模型的残差 MS 为分母。
- **II 型**：待检效应调整所有不包含它的效应，不调整包含它的高阶交互；两组嵌套模型的 SSE 差为 SS，
  分母仍取完整模型的残差 MS。含交互时，先明确这个主效应假设是否回答研究问题。
- **III 型**：在完整模型中删除待检效应的系数块，比较 SSE；分类模型必须使用 sum 编码。
  默认不输出截距行，需要复现 `car::Anova(type=3)` 全表时设 `include_intercept=True`。
  普通 ANOVA 不自动换成异方差稳健检验。

## 改变数值结果的坑

- **错误分母会改变结论。** seed 17 裂区中，A 的正确分母 MS=1.1316962812、df=14，F=12.1529100467；
  亚区分母 MS=0.3144212859、df=21。把它用于 A 会把 F 错放大到约 43.74。
- **I 型顺序和 SS 类型。** seed 17 不平衡固定模型 A 的 I/II/III 型 SS 分别为
  49.8223168508 / 49.9201787299 / 28.9575069401。把 B 放在 A 前面，A 的 I 型 SS 变成 49.9201787299。
- **III 型不是任意编码下的同一个主效应。** 同一数据使用 treatment 编码的 `car::Anova(type=3)`，A 的 SS
  是 6.5113794581，sum 编码为 28.9575069401。本接口会拒绝 treatment 编码的 III 型检验。
  参见 [car::Anova 文档](https://rdrr.io/cran/car/man/Anova.html)。
- **重复测量不是独立重复。** 同一受试者各时点必须完整且唯一；缺时点会报错。组间人数可以不同。
  单变量重复测量 F 需要球形性；k=2 时该约束自动成立，k>2 时本实现不作 GG/HF 校正。
- **等权 EMM 不等于原始组均值。** `marginal_means` 在每个其他因素水平上等权平均设计行，返回 `L`、
  `L @ beta`、`L @ vcov @ L.T`、SE、t 置信区间。存在交互时，它是平均效应，不能掩盖水平间异质性。
  普通 OLS 默认 df=n−p；混合模型必须显式给出 df，`np.inf` 才表示正态近似。
- **REML 的边界和多驻点。** 不平衡压力案例在 lambda=0 的负 loglik 导数为 +0.28949，
  但较优的内部驻点 lambda=0.6263051、loglik=−91.577758，比边界 loglik=−92.013018 高约 0.43526。
  不能只凭零点导数就把随机方差设为零。本实现比较 log 网格找到的所有变号根与边界；
  搜索范围为 lambda∈[0,1e8]，极窄且网格未覆盖的极值不保证发现，最佳值仍向上界降低时会报错。
- **优化算法的小差别不应伪装成逐位一致。** Python 允许精确 tau²=0，`nlme::lme` 边界案例返回
  约 4.81e−8 或 5.26e−8。所有偏离目标的 nlme 数值都保留在验证记录中；独立 R 矩阵方程求根验证通过。
- **数值秩阈值。** Python SVD 阈值为 `1e-10 * max(1, 最大奇异值)`；R aov 有不同的列过滤和 QR 阈值。
  极端缩放或近共线数据不在逐项一致的保证内；重标度并核对秩，不能通过改 df 掩盖问题。

## REML 约定和输出

`random_intercept_reml` 拟合 `V = sigma2 I + tau2 ZZ'`，lambda=tau2/sigma2。
以组内求和计算 `(I+lambda ZZ')^{-1}`，不建立 n×n 协方差；`beta` 是 GLS 系数。
令 C=I+lambda ZZ'、q=n−p，则 sigma²=(y−Xbeta)'C⁻¹(y−Xbeta)/q，
restricted loglik 为 `−0.5 * [q*(log(2π sigma²)+1) + log|C| + log|X'C⁻¹X|]`。
`vcov=sigma²*(X'C⁻¹X)⁻¹`，`blup` 为按 `group_levels` 排序的随机截距预测。
同时返回边际/条件拟合与残差、广义 RSS、信息矩阵、右端项、两个 logdet 和负 loglik 的 lambda 导数 `score`。

这里的 `df_residual=n−p` 是残差方差 profile 的自由度，不是任意固定效应 t 检验的分母自由度。
没有自动采用 nlme containment、Satterthwaite 或 Kenward–Roger 规则。
协方差以估计的方差分量代入，不含 Kenward–Roger 修正。
若只有单例组，或组截距完全被 X 吸收，则拒绝不可识别的方差分解。
R 接口约定见 [nlme::lme](https://stat.ethz.ch/R-manual/R-devel/library/nlme/html/lme.html)；
参考网格等权平均约定见 [emmeans](https://rvlenth.github.io/emmeans/reference/emmeans.html)。

## 报告前检查

- 实验单位、block/A 嵌套键、全局唯一 subject ID 与研究设计一致。
- 行顺序与因子列对齐；格频数、缺失/删除行数、模型矩阵秩和列顺序已记录。
- 平衡设计的 df 与上表一致；误差层 SS 加截距 SS 等于 y'y，所有层 df 加截距 df 等于 n。
- 每个 F 的分母来自同层残差；不平衡时同一效应的跨层行全部保留并解释。
- REML 方差非负、内部解 score 近零，边界状态显式报告；没有把 profile df 当成混合模型检验 df。
- EMM 的权重、置信水平和 df 已明确；比较多个 EMM 时没有误称已做多重检验校正。

## 未实现与适用范围

- 缺失格的可估计函数、秩亏模型的广义逆假设选择、插补和缺失重复测量专用推断。
- 多随机截距层、随机斜率、异方差/相关残差、AR(1)、ML 拟合、方差分量的区间或检验。
- GG/HF 校正、MANOVA、Kenward–Roger/Satterthwaite 或自动 nlme containment df。
- 加权 ANOVA、稳健/置换 ANOVA、一般公式解析、数值协变量 EMM、EMM 成对比较和多重校正。
- 不平衡多误差层的“II/III 型分层 ANOVA”；这里分层表始终对应 R aov 的顺序分解。
- 高维或极端病态设计的严格性能/全局优化保证。单线程实测 3,000 行、50 区组/300 受试者及所列低维模型均小于一秒，见验证报告。
