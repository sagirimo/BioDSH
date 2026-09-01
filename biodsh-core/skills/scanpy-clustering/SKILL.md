---
name: scanpy-clustering
description: Run a minimal deterministic Scanpy pipeline (QC, normalization, HVG, PCA, Leiden clustering, UMAP) on an h5ad file and write clusters.csv, umap.png and summary.json.
---

# Scanpy single-cell clustering

对 scRNA-seq 数据跑一条最小单细胞流程：

1. 质控与过滤
2. 归一化
3. 高变基因选择
4. PCA
5. 邻域图与 Leiden 聚类
6. UMAP 可视化

## 输入

当前 demo 版不读取外部输入，使用固定 seed 的合成数据；真实版改为接收 `adata.h5ad` 或 mtx 三件套。

## 输出

- `clusters.csv`
- `umap.png`
- `summary.json`

## 调用

由 `runner.py` 统一调用，不直接手工跑。

