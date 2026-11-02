本阶段是两个独立提交冻结后的复核与合并阶段。只允许使用公开任务、原始 inputs 与 .biodsh-candidates/primary/submission、.biodsh-candidates/blind/submission 中的候选。两者都不是参考答案；没有私有评分结果。
submission/ 已以第一份候选初始化。.biodsh-candidates/comparison.json 列出两份候选逐表逐列的字面差异（可能含格式差异）。先比较两份候选各表、逐项 CLAIMS、代码与公开定义；差异要按公开依据及原始输入计算裁决，不因多数、一致、较复杂或更自信就选用。两份相同也可能共同误解定义，仍应独立检查人群/分母/单位/缺失与证据支持/收敛等关键语义。只修改有依据的地方；模型的模糊疑问不自动成为错误，不为消除疑问而偏离指定方法。

可执行核查（v17，交付门强制）：
1. 写 submission/reconcile_checks.py。它只接受 `--inputs DIR --outputs DIR` 两个参数，只读原始 inputs 与 outputs 目录中的最终交付文件，不得 import 或调用 analysis.py，也不得读候选目录。
2. 对每个有差异的列，以及每个比例、计数、均值、分母或真假命题类列（即使两份候选一致），在脚本里从原始 inputs 用独立代码重新计算公开定义要求的值，然后逐行与 outputs 中对应的 CSV/JSON 单元格比较（数值用公开容差；未给容差时用相对 1e-9）。每项核查打印一行 `CHECK <id> PASS|FAIL <表>.<列> <检查的行数>`，任何 FAIL 时以非零码退出。
3. 交付门会在干净目录重放 analysis.py 后，用重放产物运行 reconcile_checks.py；脚本失败、缺失或零项核查都会阻止交付。核查失败时修改 analysis.py（或在公开依据显示核查本身理解错误时修改核查并写明理由），不要删除核查来通过。
4. submission/reconciliation.json 中每条 comparisons 必须用 "check_ids" 列出 reconcile_checks.py 中实际执行的核查编号；未被脚本覆盖的结论写进 "unresolved"，不得声称已核对。

格式为 {"version":2,"comparisons":[{"table":"实际表名","columns":["实际列名"],"difference":"发现或无差异","decision":"保留或修改及理由","public_basis":"文件与原文依据","check_ids":["C1"]}],"unresolved":[]}。不要把候选文件当原始源数据写进来源校验计划。

步数预算 70 步：最迟在第 50 步停止新的修改，转入"保存代码 → 干净重放 → 运行 reconcile_checks.py → 交付"。最终仍须生成整个原任务规定的所有输出、interpretation_claims.json 和可独立重放的 analysis.py。最终评价固定使用本阶段提交，不会事后挑选得分最高的候选。
