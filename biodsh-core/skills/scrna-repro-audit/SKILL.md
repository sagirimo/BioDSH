---
name: scrna-repro-audit
description: Read-only reproducibility audit of a completed BioDSH run bundle: verifies input/command/output hashes and result consistency from a result.json.
---

# scrna-repro-audit

对一次已完成的 BioDSH 运行做只读复现审计。输入是该运行的 `result.json`，审计在
bundle 内部核对五类一致性：

1. **bundle_complete**：input/env/command/outputs/result/stdout/stderr 七件套齐全；
2. **input_consistency**：被审计运行引用的输入文件当前哈希仍等于执行前快照；
3. **command_consistency**：`command.sh` 与 `input.json` 记录的 seed、输入、outdir 一致；
4. **output_integrity**：每个输出文件当前哈希等于 `outputs.json` 记录；
5. **result_consistency / declared_outputs_present / grader_evidence / offline_evidence**：
   `result.json` 的哈希、状态、分数与 grader、离线观测证据互相自洽。

## 边界

- 审计只读文件，不重跑分析，不修改 bundle；
- `audit_passed` 只表示 bundle 内部一致，不评估生物学结论（`biological_validity: not_evaluated`）；
- 任一检查失败时进程以非零退出，让 runner 按 fail-closed 记为失败。

## 用法

```bash
./bioenv/.venv/bin/python biodsh-core/runner.py run scrna-repro-audit \
  --input biodsh-core/runs/<run_id>/result.json
```

输出：`repro_audit_report.json`（机器可读全量证据）、`repro_audit_summary.csv`（逐检查摘要）。
报告不含时间戳，同一输入同一 seed 重复审计输出逐字节一致。
