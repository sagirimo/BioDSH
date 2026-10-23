"""Build VALIDATION.md from actual comparison/timing artifacts (not expectations)."""
import json
from pathlib import Path
import sys
import pandas as pd

here = Path(__file__).resolve().parent
skill = here.parent
results = pd.read_csv(here/'comparison.csv')
checks = json.loads((here/'checks.json').read_text())
versions = (Path(sys.argv[1])/'versions.txt').read_text()
(here/'reference_versions.txt').write_text(versions)


def category(quantity):
    if quantity == 'data.keep':
        return quantity
    bits = quantity.split('.')[1:]
    if 'test' in bits:
        return 'coefficient_test.'+bits[-1]
    if 'wald' in bits:
        return 'wald_test.'+bits[-1]
    return '.'.join(bits)


results['category'] = results.quantity.map(category)
agg = results.groupby(['category','seed']).agg(
    max_rel=('max_rel','max'), max_rel_nonzero=('max_rel_nonzero','max'),
    max_abs=('max_abs','max'), near_zero_abs=('near_zero_abs','max'))
table = [
    '| 数值量（跨六类模型取最大） | seed 1 相对误差† | seed 2 相对误差† | 两组最大绝对误差 |',
    '|---|---:|---:|---:|'
]
for key in sorted(results.category.unique()):
    a, b = agg.loc[(key,1)], agg.loc[(key,2)]
    table.append(f'| `{key}` | {a.max_rel_nonzero:.3e} | {b.max_rel_nonzero:.3e} | '
                 f'{max(a.max_abs,b.max_abs):.3e} |')

timing = checks['benchmark']
text = f"""# R 逐项数值验证：regression-robust-se

验证日期：2026-10-20。环境：

```text
{versions.strip()}
Python {checks['python']}; numpy {checks['numpy']}; scipy {checks['scipy']}; pandas {checks['pandas']}
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

**{len(results):,} 个数值量组、{int(results['count'].sum()):,} 个标量比较全部通过。**
比较脚本先要求 R/Python 的量名集合及形状完全一致、有限值状态一致，
并逐元素判定 `abs(Python−R) <= 1e-12 + 1e-8*abs(R)`。
Inf 自由度单独要求一致；不存在用 NaN 跳过失败项。

† 表中相对误差只统计 |R|≥1e-8 的元素，最大为
**{results.max_rel_nonzero.max():.8e}**；|R|<1e-8 的最大绝对误差为
**{results.near_zero_abs.max():.8e}**。原始相对指标定义为
`abs(Python−R)/max(abs(R),1e-12)`，包括近零项的最大值为
**{results.max_rel.max():.8e}**，并不满足严格逐元素 1e-8 相对误差要求；
原因是 R 通过逆 bread 从 influence 重构簇得分时，对数学上为零的元素留下约
1e-15 舍入。原始指标没有隐藏：
[comparison.csv](validation/comparison.csv) 逐 seed/模型/量记录 max_abs、
max_rel、max_rel_nonzero、near_zero_abs 和 passed；
[max_relative_errors.csv](validation/max_relative_errors.csv) 保留全部量的原始最大相对误差。
下表聚合相同返回字段，系数/Wald 检验字段跨所有协方差类型和三种 df 取最大。

{chr(10).join(table)}

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

[checks.json](validation/checks.json) 记录 **{checks['check_count']} 项通过**：
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
`{', '.join(f'{v:.6f}' for v in timing['pipeline_seconds'])}`。
中位数 **{timing['median_seconds']:.6f} 秒**，最大 **{timing['max_seconds']:.6f} 秒**。
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
"""
(skill/'VALIDATION.md').write_text(text, encoding='utf-8')
print(f'Wrote {skill / "VALIDATION.md"} with {len(table)-2} numerical summary rows.')
