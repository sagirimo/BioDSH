# 公共数据库抓取

**输入**：`genes.txt`（15 个 T 细胞耗竭相关的人类基因，一行一个）。

**三段对话**：
- 从 NCBI Gene / UniProt 抓官方全名、功能、编号，整理成 `gene_annotations.xlsx`
- MSigDB Hallmark 通路富集分析（`enrichment_hallmark.csv` + 柱状图）
- GTEx 正常组织表达热图，分出免疫特异 / 全身广泛 / 低表达

**怎么照着做**：换掉 `genes.txt`，照样提问。「数据库 → 本地参考包」下载后富集分析可完全离线。
