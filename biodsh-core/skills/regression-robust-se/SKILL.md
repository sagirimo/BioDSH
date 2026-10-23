---
name: regression-robust-se
description: OLS/WLS and logistic or Poisson regression with HC0-HC3 heteroskedasticity-robust SEs, one-way cluster CR0/CR1/CR1S and Bell–McCaffrey CR2, explicit Wald/t/normal inference and bread/meat diagnostics in numpy/scipy/pandas; use when R or statsmodels is unavailable and robust covariance conventions must match R sandwich, clubSandwich and lmtest.
---

# 回归与稳健标准误

将同目录的 `robust_se.py` 复制到分析脚本旁，或复制所需函数及其依赖辅助函数。
运行只需 numpy/scipy/pandas；实现不读写文件、不修改输入、不维护全局状态。
R 只用于离线验证，不是运行依赖。数值证据和复跑命令见 [VALIDATION.md](VALIDATION.md)。

## 操作步骤

1. **对齐行并处理缺失。** 按样本 ID 对齐响应、设计、权重、offset 与 cluster。
   在拟合前为本次分析所需字段建立同一个完整行掩码，记录排除样本数。
   函数拒绝缺失/非有限数值，不会自动删行。验证数据为了让六个模型可直接比较，
   对所有模拟字段用了共同掩码；真实分析按具体研究问题选择字段。
2. **构建设计。** `X` 是 n×p、满列秩，截距需要显式添加；分类变量由调用者编码。
   `p` 包含截距及所有调整变量。要求 n>p、所有权重为正；
   零权重行先显式排除，秩亏或病态设计需要重新参数化。
3. **拟合。** OLS：`fit_linear(X,y)`；WLS：`fit_linear(X,y,weights=w)`，
   其中 w 为相对精度。Logistic：`fit_glm(X,y,family="binomial")`；
   Poisson：`fit_glm(X,y,family="poisson")`。
   GLM 采用 IRLS/Newton 和步长减半；不收敛会抛出异常，不能据此报告 Wald 推断。
   `offset` 在线性模型中加到均值，在 GLM 中加到线性预测子；Poisson exposure 用 `np.log(exposure)`。
   分组二项输入 `y=successes/trials, weights=trials`，不要把成功数直接作为 y。
4. **选择协方差。** 模型方差是 `fit["model_cov"]`；独立观测的异方差稳健估计用
   `vcov_hc(fit,"HC3")`，聚类依赖用 `vcov_cluster(fit,cluster,"CR1S")`。
   不以默认值替代题目/方案指定的方法。CR2 的工作方差目标需要单独确定，见下文。
5. **显式指定参考分布。** `coefficient_test(fit,V,df=...)` 返回系数、SE、t/z、
   双侧 p、置信区间及 df。默认 df=∞，即正态；OLS 常规 t 使用 n−p，
   单向聚类常见约定为 G−1。`wald_test(fit,R,null,covariance=V,df=...)`
   检验 Rβ=null，返回二次型 W、统计量、分子/分母 df、p 以及对比估计和协方差。
   其中 `contrast_estimate` 是已减去零假设值的 Rβ−null。
6. **报告。** 说明响应/链接、设计列顺序、保留 n、p、聚类层级及 G/簇大小，
   权重/offset 的含义、协方差类型与 CR2 target、参考分布/df，
   然后报告估计、SE、置信区间、统计量和 p。

```python
import numpy as np
from robust_se import fit_linear, vcov_cluster, coefficient_test, wald_test

# samples 已按 ID 对齐；这里只筛本模型实际使用的字段。
fields = ["outcome", "treatment", "age", "cluster"]
d = samples.loc[samples[fields].notna().all(axis=1)]
X = np.column_stack([np.ones(len(d)), d["treatment"], d["age"]])
fit = fit_linear(X, d["outcome"])
robust = vcov_cluster(fit, d["cluster"], kind="CR1S")
table = coefficient_test(fit, robust["cov"], df=robust["df_cluster"])
joint = wald_test(fit, [[0, 1, 0], [0, 0, 1]],
                  covariance=robust["cov"], df=robust["df_cluster"])
```

## 数值约定与返回值

设 a 为 prior/precision weights、e=y−μ。线性模型 I=X′diag(a)X；
GLM 固定 dispersion=1，v=μ(1−μ) 或 μ，I=X′diag(av)X。
返回 `information=I`、`inverse_information=I⁻¹`、`scores_i=x_i a_i e_i`、
`bread=n I⁻¹`，以及 coefficients、fitted、eta、response/working residuals、
working_weights、hat、dispersion、df_resid、n、p、converged、iterations；
GLM 另返回 deviance。迭代次数是诊断信息，不要求与 R 的算法一致。
线性模型 `model_cov = [Σa e²/(n−p)] I⁻¹`；GLM 为 I⁻¹。

所有稳健协方差统一为 `cov = bread @ meat @ bread / n`，
meat 是校正后的行/簇得分外积和除以 n。不能再乘一次 dispersion 或校正因子。
`vcov_hc` 另返回每行 factors、adjusted_scores；
`vcov_cluster` 另返回排序后的 clusters、cluster_scores、factor、n_clusters、
df_cluster、CR2 adjustments 与逐行 target。CR2 时 factor=1，但矩阵调整已经生效。

| Python 类型 | 得分外积的校正 | R 对照 |
|---|---|---|
| HC0 | 1 | `sandwich::vcovHC(type="HC0")` |
| HC1 | n/(n−p) | `vcovHC(type="HC1")` |
| HC2 | 每行 1/(1−hᵢ) | `vcovHC(type="HC2")` |
| HC3 | 每行 1/(1−hᵢ)² | `vcovHC(type="HC3")` |
| CR0 | 每簇先求和再外积，无额外乘数 | `vcovCL(type="HC0",cadjust=FALSE)`；`vcovCR(type="CR0")` |
| CR1 | G/(G−1) | `vcovCL(type="HC0",cadjust=TRUE)`；`vcovCR(type="CR1")` |
| CR1S | G/(G−1) × (n−1)/(n−p) | `vcovCL(type="HC1",cadjust=TRUE)`；`vcovCR(type="CR1S")` |
| CR2 | Bell–McCaffrey 簇内残差矩阵调整 | `clubSandwich::vcovCR(type="CR2",target=...)` |

`vcovCL(type="HC1",cadjust=FALSE)` 等于 CR0 × (n−1)/(n−p)，可对其 cov 和 meat
同时乘该因子；它不同于逐观测 HC1。R 默认类型因模型类而异，验证时始终显式指定。

### CR2 工作模型

对应 `clubSandwich` 0.7.0：OLS 与 WLS 的默认 target 都是单位矩阵；
若 WLS 的精度权重确实指定观测方差，应显式传 `target=1/fit["weights"]`。
GLM 默认逐行 target=v/a。可传任意有限正对角 target 向量，不支持非对角目标。
这些默认值已对照包源码及逐项验证，不推断用户的权重语义。

具体实现使用线性化设计 U=X、W=diag(a)（lm），或 U=diag(v)X、
W=diag(a/v)（GLM），M=(U′WU)⁻¹，Θ=diag(target)。
对簇 g，Hgg=Ug M Ug′ Wg，
Cg=Θg−HggΘg−ΘgHgg′+Ug M U′WΘWU M Ug′，
Ag=Θg½(Θg½ Cg Θg½)⁻½Θg½，调整得分为 Ug′Wg Ag eg。
返回的 adjustments 就是这些 Ag；没有把 CR2 近似成逐观测 HC2。
零/近零特征值会报错，不悄悄使用广义逆。

### 推断自由度

`coefficient_test` 的 df=∞ 是正态，有限正 df 是 Student t。
联合 Wald 的 q=rank(R)：无限 df 用 χ²q 的 W，有限 df 用 F(q,df) 的 W/q。
q=1 时与相同协方差/df 的系数检验一致。
G−1 是常见聚类 t/F 约定，**不是** `clubSandwich::coef_test(test="Satterthwaite")`
或 `Wald_test(test="HTZ")`。CR2 协方差本身不生成这些小样本自由度；
簇少或极不平衡时尤其不能把它们混称。

## 会改变结果的坑

- **校正名称不统一。** seed 1 的 n=112,p=3,G=11，CR1 乘数为 1.1，
  Stata 式 CR1S 为 1.1201834862，OLS x 系数 SE 分别 0.1688286553 和 0.1703705015。
  先明确乘数公式，不能只写“CR1”。
- **参考分布能显著改变 p。** 同一 seed 1 CR1S 协方差，x 的正态 p=0.0002128732；
  用 t₁₀ 得 p=0.0040866822。函数不会从 covariance 自动猜 df。
- **高杠杆影响 HC。** seed 2 最大 h=0.3811825125；
  x 的 HC0 SE=0.1488999161、HC3 SE=0.2275616782。WLS/GLM 的 h 来自加权/IRLS 设计。
- **WLS 的 CR2 target 不是装饰。** seed 2 默认 identity 的 x SE=0.1609866772，
  precision target=1/w 时为 0.1713709182。先写清目标方差。
- **权重不等于重复行。** 分组二项用 trials 权重，但 n、残差 df 和校正乘数按保留的行数计，
  不按 trials 总和计；频数权重展开成逐事件数据属于另一种分析。
- **缺失必须同步处理 cluster。** 两组验证各排除 3 行，保留 112/81 行及 11/7 个簇。
  在拟合后才删 cluster 缺失行会让得分与标签错位。
- **GLM 最后一次更新。** R 的 QR/working weights 可能属于最后系数更新前一轮；
  即使 `epsilon=1e-14`，首轮对照的一个 information 元素相对差仍为 5.45×10⁻⁸。
  本实现总在最终 β 上重算；验证 R 从收敛系数再拟合一次，同时保留原始差异记录。
- **接近零的相对误差不稳定。** 某簇某设计列全零时，重构 R 得分会有约 10⁻¹⁵ 的舍入；
  用绝对误差核查零项，不能把分母下限产生的相对误差当作方法差异。

## 报告前检查

- 样本顺序与掩码一致，n/p/G 和实际观测簇大小正确；空 factor 水平不计入 G。
- 权重、offset、target 的语义已写明；列名/参考组/对比方向明确。
- 拟合收敛；hat 在合理范围；没有把分离/秩亏/CR2 奇异块错误忽略。
- SE 有限且为正；联合 Wald 的对比满行秩、对比协方差正定。
- 协方差类型与校正乘数准确；p/CI 使用同一个 df；未额外重复校正。
- 若声称小样本 Satterthwaite/HTZ 推断，必须使用另外经过验证的实现。

## 未实现与适用范围

不实现多向/嵌套多层聚类合成（它们是本任务可选项）、CR1p/CR3、HC4–HC5、HAC、
调查抽样设计、GEE/GLMM、任意非规范链接、quasi/负二项模型、惩罚或 Firth Logistic、
Satterthwaite/HTZ 自由度、非对角 CR2 target、奇异 CR2 的广义逆。
可显式选择一个层级做单向聚类；不能把多个交叉标签拼接后当作多向稳健估计。
不进行严格的线性规划分离诊断；完全分离测试会因边界/不收敛被拒绝，但异常不是完整诊断器。

单线程 3000 行、5 列、60 个大小为 50 的簇，四类模型加全部协方差及检验共约 0.1 秒
（实测详情见 VALIDATION）。CR2 需要簇内稠密特征分解，耗时随 Σn_g³ 增长，
内存随最大簇大小平方增长；此计时不承诺任意巨型簇都在 1 秒内。

## 方法来源

实现采用 R 的显式约定，验证使用已安装包的实际函数。
[sandwich bread 源码](https://github.com/cran/sandwich/blob/master/R/bread.R)、
[vcovCL 源码](https://github.com/cran/sandwich/blob/master/R/vcovCL.R)
给出归一化及有限样本因子；
[clubSandwich lm 文档](https://jepusto.github.io/clubSandwich/reference/vcovCR.lm.html)、
[GLM 方法源码](https://github.com/jepusto/clubSandwich/blob/main/R/glm.R)
说明工作方差、权重及线性化设计。
